"""Versioned, one-request stdio protocol for the N.I.N.A. exposure gate.

No network listener, camera access, or shell execution. Only CelesTrak requests
are sent externally. A failed or stale forecast never produces usable windows.
"""

import json
import sys
from datetime import UTC, datetime, timedelta

from . import __version__
from .catalog import Catalog, fetch_catalog, local_catalog
from .models import PlanConfig, iso, utc
from .predict import plan
from .schedule import available

SCHEMA_VERSION = 1
MAX_REQUEST_BYTES = 65536


def evaluate(request: dict, *, catalog: Catalog | None = None, now=None) -> dict:
    if not isinstance(request, dict) or request.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported NINA bridge schema_version; expected 1.")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
        raise ValueError("request_id must be a nonempty string of at most 100 characters.")
    config = PlanConfig.from_dict(request["config"])
    if config.duration_s > 3600:
        raise ValueError("NINA forecasts are limited to one hour; reduce the look-ahead time.")
    if config.max_epoch_age_days > 7:
        raise ValueError("NINA max_epoch_age_days cannot exceed 7 days.")
    if catalog is None:
        if request.get("catalog_path"):
            catalog = local_catalog(request["catalog_path"])
        else:
            if not isinstance(request.get("offline", False), bool):
                raise ValueError("offline must be true or false.")
            catalog = fetch_catalog(
                request.get("group", "visual"), offline=request.get("offline", False)
            )
    reference_now = utc(now or datetime.now(UTC))
    if catalog.fetched_at:
        download_age = (reference_now - utc(catalog.fetched_at)).total_seconds()
        if download_age < -300 or download_age > 86400:
            raise ValueError(
                "Orbital-data download is more than 24 hours old or in the future. Refresh the catalog."
            )
    max_offset = max(
        max(
            abs((edge - sat.epoch.utc_datetime()).total_seconds())
            for edge in (config.start, config.end)
        )
        / 86400
        for sat in catalog.satellites
    )
    if max_offset > config.max_epoch_age_days:
        raise ValueError(
            f"Orbital elements exceed the configured epoch limit "
            f"({max_offset:.3f} > {config.max_epoch_age_days:g} days). Refresh the catalog "
            "or select an appropriate, documented catalog/threshold. No exposure authorized."
        )
    result = plan(config, catalog)
    # This is an availability interval, not the standalone fixed-cadence schedule.
    # The plugin rechecks the entire next exposure plus handoff buffer against it.
    windows = available(result.blocked, config.duration_s)
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "status": "ok",
        "engine_version": __version__ + "+nina-bridge1",
        "generated_at_utc": iso(reference_now),
        "session_start_utc": iso(config.start),
        "valid_until_utc": iso(config.end),
        "windows": [
            {
                "start_utc": iso(config.start + timedelta(seconds=w.start_s)),
                "end_utc": iso(config.start + timedelta(seconds=w.end_s)),
            }
            for w in windows
        ],
        "satellite_count": len(catalog.satellites),
        "catalog_sha256": catalog.sha256,
        "catalog_source": catalog.source,
        "catalog_fetched_at_utc": catalog.fetched_at,
        "max_epoch_offset_days": max_offset,
        "warnings": result.warnings,
    }


def main():
    request_id = None
    try:
        payload = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(payload) > MAX_REQUEST_BYTES:
            raise ValueError("NINA bridge request exceeds 64 KiB.")
        request = json.loads(payload.decode("utf-8-sig"))
        if isinstance(request, dict):
            request_id = request.get("request_id")
        response = evaluate(request)
        code = 0
    except Exception as exc:
        response = {
            "schema_version": SCHEMA_VERSION,
            "request_id": request_id,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "windows": [],
        }
        code = 2
    # Stable UTF-8 even on Windows hosts using a legacy console code page.
    sys.stdout.buffer.write(
        (json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    )
    sys.stdout.buffer.flush()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
