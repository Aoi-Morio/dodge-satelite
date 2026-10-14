"""Sampled ICRS topocentric geometry with conservative segment blocking.

The segment test can detect crossings between samples, but is not a rigorous
bound on a curved physical trajectory. No astrometric accuracy is claimed.
"""

from datetime import UTC, datetime
from threading import Event

import numpy as np
from astropy import units as u
from astropy.coordinates import get_body_barycentric
from astropy.time import Time
from skyfield.api import load, wgs84

from . import __version__
from .catalog import Catalog
from .models import Interval, PlanConfig, PlanResult, Transit, iso
from .schedule import merge, overlaps, schedule

EARTH_RADIUS_KM = 6378.137
SUN_RADIUS_KM = 695700.0


class CancelledError(RuntimeError):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise CancelledError("Calculation cancelled.")


def unit(v):
    return v / np.linalg.norm(v, axis=0)


def target_vector(ra_deg, dec_deg):
    ra, dec = np.radians([ra_deg, dec_deg])
    return np.array([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)])


def segment_hits(directions, target, radius_deg):
    """Distance from target unit vector to each chord, not endpoint-only tests.

    A chord is inside the unit sphere: this intentionally admits false positives.
    This handles RA wrap and polar fields without tangent-plane singularities.
    """
    a, b = directions[:, :-1], directions[:, 1:]
    delta = b - a
    denom = np.sum(delta * delta, axis=0)
    fraction = np.divide(
        np.sum((target[:, None] - a) * delta, axis=0),
        denom,
        out=np.zeros_like(denom),
        where=denom > 1e-30,
    )
    nearest = a + delta * np.clip(fraction, 0, 1)
    distance = np.linalg.norm(nearest - target[:, None], axis=0)
    return distance <= 2 * np.sin(np.radians(radius_deg) / 2)


def sunlit(satellite_km, earth_to_sun_km):
    """False only in full geometric umbra; partial sunlight remains a risk."""
    to_sun = earth_to_sun_km - satellite_km
    to_earth = -satellite_km
    r = np.linalg.norm(to_earth, axis=0)
    earth_angle = np.arcsin(np.clip(EARTH_RADIUS_KM / r, 0, 1))
    sun_angle = np.arcsin(np.clip(SUN_RADIUS_KM / np.linalg.norm(to_sun, axis=0), 0, 1))
    separation = np.arccos(np.clip(np.sum(unit(to_earth) * unit(to_sun), axis=0), -1, 1))
    return separation + sun_angle >= earth_angle


def mask_intervals(mask, seconds):
    """Convert N-1 segment flags into full, closed sample-cell intervals."""
    edges = np.diff(np.r_[False, mask, False].astype(int))
    return [
        Interval(float(seconds[a]), float(seconds[b]))
        for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))
    ]


def plan(config: PlanConfig, catalog: Catalog, progress=None, cancel: Event | None = None):
    count = int(np.ceil(config.duration_s / config.sample_s)) + 1
    if count * len(catalog.satellites) > 50_000_000:
        raise ValueError(
            "Session exceeds the v0.1 workload limit (50 million satellite samples). "
            "Use a smaller catalog, shorter session or larger sampling step."
        )
    check_cancel(cancel)
    if progress:
        progress(0, "Computing observing conditions / 観測条件を計算")
    ts = load.timescale(builtin=True)
    seconds = np.linspace(0, config.duration_s, count)
    start = ts.from_datetime(config.start)
    t = ts.tt_jd(start.whole, start.tt_fraction + seconds / 86400)
    observer = wgs84.latlon(
        config.site.latitude_deg, config.site.longitude_deg, elevation_m=config.site.elevation_m
    )
    observer_km = observer.at(t).position.km
    zenith = observer.rotation_at(t)[2]
    target = target_vector(config.target.ra_deg, config.target.dec_deg)
    target_alt = np.degrees(np.arcsin(np.clip(np.einsum("ij,i->j", zenith, target), -1, 1)))
    atime = Time(t.whole, t.tt_fraction, format="jd", scale="tt")
    sun_km = (
        get_body_barycentric("sun", atime, ephemeris="builtin")
        - get_body_barycentric("earth", atime, ephemeris="builtin")
    ).xyz.to_value(u.km)
    sun_alt = np.degrees(
        np.arcsin(np.clip(np.sum(zenith * unit(sun_km - observer_km), axis=0), -1, 1))
    )
    usable = (target_alt >= config.min_target_alt_deg) & (sun_alt <= config.max_sun_alt_deg)
    condition_blocked = mask_intervals(~(usable[:-1] & usable[1:]), seconds)
    check_cancel(cancel)
    warnings = list(catalog.warnings)
    warnings.extend(
        [
            "Prediction is limited to this catalog; uncatalogued/missing satellites are not covered.",
            "Sampled curved trajectories, orbital error and maneuvers can cause missed crossings. "
            "Margins are user choices, not statistical confidence bounds.",
            "Sunlight is geometric (partial eclipse counts as lit); brightness, flares, weather, "
            "refraction, terrain and telescope tracking errors are not modeled.",
            "Built-in Skyfield time/Earth-rotation tables and Astropy solar ephemeris are used offline. "
            "Update dependencies regularly; no measurement-validated accuracy is claimed.",
        ]
    )
    transits, epoch_info = [], []
    stale_count = 0
    for index, sat in enumerate(catalog.satellites):
        check_cancel(cancel)
        epoch = sat.epoch.utc_datetime()
        offset = (
            max(
                abs((config.start - epoch).total_seconds()),
                abs((config.end - epoch).total_seconds()),
            )
            / 86400
        )
        stale_count += offset > config.max_epoch_age_days
        epoch_info.append(
            {
                "norad_id": sat.norad_id,
                "name": sat.name,
                "epoch_utc": iso(epoch),
                "max_epoch_offset_days": offset,
            }
        )
        position = sat.at(t)
        messages = np.asarray(position.message, dtype=object)
        errors = [str(m) for m in messages.flat if m]
        if errors or not np.all(np.isfinite(position.position.km)):
            raise ValueError(
                f"SGP4 failed for {sat.name} ({sat.norad_id}): "
                f"{errors[0] if errors else 'non-finite position'}. No plan produced."
            )
        directions = unit(position.position.km - observer_km)
        hit = segment_hits(
            directions, target, config.equipment.radius_deg + config.angular_margin_deg
        )
        above = np.sum(zenith * directions, axis=0) >= 0
        hit &= above[:-1] | above[1:]
        lit = sunlit(position.position.km, sun_km)
        if config.sunlit_only:
            hit &= lit[:-1] | lit[1:]
        for item in mask_intervals(hit, seconds):
            transits.append(
                Transit(
                    sat.norad_id,
                    sat.name,
                    item.start_s,
                    item.end_s,
                    iso(epoch),
                    offset,
                    "sunlit-or-penumbra" if config.sunlit_only else "all-states",
                )
            )
        if progress:
            progress(
                round(100 * (index + 1) / len(catalog.satellites)),
                f"{index + 1}/{len(catalog.satellites)}: {sat.name}",
            )
    check_cancel(cancel)
    if stale_count:
        warnings.insert(
            0,
            f"STALE ORBITAL ELEMENTS: {stale_count}/{len(catalog.satellites)} satellites "
            f"are more than {config.max_epoch_age_days:g} days from their epoch "
            "during this session. Refresh data; this plan is not operationally validated.",
        )
    satellite_blocked = merge(
        [Interval(x.start_s - config.padding_s, x.end_s + config.padding_s) for x in transits],
        config.duration_s,
    )
    blocked = merge(condition_blocked + satellite_blocked, config.duration_s)
    exposures = schedule(blocked, config.duration_s, config.exposure_s, config.readout_s)
    baseline = schedule(condition_blocked, config.duration_s, config.exposure_s, config.readout_s)
    at_risk = sum(any(overlaps(e, b) for b in satellite_blocked) for e in baseline)
    if not baseline:
        warnings.insert(
            0, "No complete exposure fits the target-altitude and solar-altitude limits."
        )
    if not transits:
        warnings.append(
            "No crossings detected in the selected catalog. This is not a guarantee of clear frames."
        )
    return PlanResult(
        config,
        sorted(transits, key=lambda x: x.start_s),
        blocked,
        exposures,
        baseline,
        at_risk,
        warnings,
        {
            "version": __version__,
            "generated_at_utc": iso(datetime.now(UTC)),
            "catalog_source": catalog.source,
            "catalog_sha256": catalog.sha256,
            "catalog_fetched_at_utc": catalog.fetched_at,
            "satellite_count": len(catalog.satellites),
            "satellite_epochs": epoch_info,
            "actual_step_s": float(seconds[1] - seconds[0]),
            "fov_width_deg": config.equipment.width_deg,
            "fov_height_deg": config.equipment.height_deg,
            "blocking_radius_deg": config.equipment.radius_deg + config.angular_margin_deg,
            "condition_blocked": [vars(x) for x in condition_blocked],
            "satellite_blocked": [vars(x) for x in satellite_blocked],
            "target_altitude_range_deg": [float(target_alt.min()), float(target_alt.max())],
            "sun_altitude_range_deg": [float(sun_alt.min()), float(sun_alt.max())],
        },
    )
