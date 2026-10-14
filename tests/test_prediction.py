from dataclasses import replace
from datetime import timedelta
from threading import Event

import numpy as np
import pytest
from skyfield.api import load, wgs84

from dodge_satelite.models import Target
from dodge_satelite.predict import (
    CancelledError,
    mask_intervals,
    plan,
    segment_hits,
    sunlit,
    target_vector,
)
from dodge_satelite.schedule import overlaps


def test_fast_crossing_between_samples_ra_wrap():
    directions = np.column_stack([target_vector(359, 0), target_vector(1, 0)])
    assert segment_hits(directions, target_vector(0, 0), 0.01)[0]
    assert not segment_hits(directions, target_vector(0, 2), 0.1)[0]


def test_stationary_and_polar_geometry():
    north = target_vector(40, 90)
    assert segment_hits(np.column_stack([north, north]), north, 0.001)[0]
    directions = np.column_stack([target_vector(0, 89), target_vector(180, 89)])
    assert segment_hits(directions, north, 0.01)[0]


def test_sunlight_umbra_and_penumbra():
    sun = np.array([[149597870.7], [0.0], [0.0]])
    assert sunlit(np.array([[7000.0], [0.0], [0.0]]), sun)[0]
    assert not sunlit(np.array([[-7000.0], [0.0], [0.0]]), sun)[0]
    assert sunlit(np.array([[-7000.0], [7000.0], [0.0]]), sun)[0]
    assert sunlit(np.array([[-7000.0], [6378.137], [0.0]]), sun)[0]


def test_mask_full_cell_boundaries():
    result = mask_intervals([True, True, False, True], np.array([0, 1, 2, 3, 4]))
    assert [(x.start_s, x.end_s) for x in result] == [(0, 2), (3, 4)]


def test_demo_crossing_and_schedule(demo_result):
    result = demo_result
    assert len(result.transits) == 1
    assert len(result.exposures) > 0
    assert result.baseline_at_risk >= 1
    assert result.transits[0].start_s < 300 < result.transits[0].end_s
    assert all(not overlaps(e, b) for e in result.exposures for b in result.blocked)
    assert all(0 <= e.start_s < e.end_s <= result.config.duration_s for e in result.exposures)
    assert any("DEMO" in warning for warning in result.warnings)


def test_dense_sample_reference_inside_reported_interval(inputs, demo_result):
    config, catalog = inputs
    ts = load.timescale(builtin=True)
    offsets = np.arange(260, 340, 0.01)
    start = ts.from_datetime(config.start)
    t = ts.tt_jd(start.whole, start.tt_fraction + offsets / 86400)
    observer = wgs84.latlon(
        config.site.latitude_deg, config.site.longitude_deg, config.site.elevation_m
    )
    topocentric = (catalog.satellites[0] - observer).at(t)
    ra, dec, _ = topocentric.radec()
    target_ra, target_dec = np.radians([config.target.ra_deg, config.target.dec_deg])
    cos_sep = np.sin(dec.radians) * np.sin(target_dec) + np.cos(dec.radians) * np.cos(
        target_dec
    ) * np.cos(ra.radians - target_ra)
    inside = offsets[
        np.degrees(np.arccos(np.clip(cos_sep, -1, 1)))
        <= config.equipment.radius_deg + config.angular_margin_deg
    ]
    assert len(inside) > 0
    interval = demo_result.transits[0]
    assert inside.min() >= interval.start_s
    assert inside.max() <= interval.end_s


def test_smaller_step_agrees_on_demo(inputs, demo_result):
    fine = plan(replace(inputs[0], sample_s=0.1), inputs[1])
    assert len(fine.transits) == len(demo_result.transits)
    for coarse, refined in zip(demo_result.transits, fine.transits):
        assert abs(coarse.start_s - refined.start_s) <= 0.5
        assert abs(coarse.end_s - refined.end_s) <= 0.5


def test_no_observing_window_and_stale_warning(inputs):
    config, catalog = inputs
    result = plan(replace(config, max_sun_alt_deg=-90, max_epoch_age_days=0.1), catalog)
    assert not result.exposures
    assert any("STALE ORBITAL" in warning for warning in result.warnings)
    assert any("No complete exposure" in warning for warning in result.warnings)


def test_far_target_has_no_transits(inputs):
    config, catalog = inputs
    result = plan(replace(config, target=Target(150, -80)), catalog)
    assert not result.transits
    assert not result.exposures


def test_cancel_and_work_limit(inputs):
    event = Event()
    event.set()
    with pytest.raises(CancelledError):
        plan(*inputs, cancel=event)
    config, catalog = inputs
    catalog.satellites *= 200
    with pytest.raises(ValueError, match="workload"):
        plan(replace(config, end=config.start + timedelta(hours=24), sample_s=0.25), catalog)


def test_propagation_error_aborts(inputs, monkeypatch):
    config, catalog = inputs
    sat = catalog.satellites[0]
    original = sat.at

    def broken(t):
        pos = original(t)
        pos.message = "synthetic propagation failure"
        return pos

    monkeypatch.setattr(sat, "at", broken)
    with pytest.raises(ValueError, match="No plan produced"):
        plan(config, catalog)


def test_solar_altitude_against_astropy(inputs, demo_result):
    from astropy import units as u
    from astropy.coordinates import AltAz, EarthLocation, get_sun
    from astropy.time import Time
    from astropy.utils import iers

    iers.conf.auto_download = False
    config, _ = inputs
    time = Time([config.start, config.end])
    location = EarthLocation.from_geodetic(
        config.site.longitude_deg * u.deg,
        config.site.latitude_deg * u.deg,
        config.site.elevation_m * u.m,
    )
    altitude = get_sun(time).transform_to(AltAz(obstime=time, location=location)).alt.deg
    actual = demo_result.metadata["sun_altitude_range_deg"]
    np.testing.assert_allclose(actual, [min(altitude), max(altitude)], atol=0.03)
