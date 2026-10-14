import json
import subprocess
import sys
from dataclasses import replace
from datetime import timedelta

import pytest

from dodge_satelite.cli import demo_inputs
from dodge_satelite.models import utc
from dodge_satelite.nina_bridge import evaluate


def request_for(config):
    return {"schema_version": 1, "request_id": "test-unique-id", "config": config.to_dict()}


def test_bridge_returns_full_available_windows(inputs):
    config, catalog = inputs
    result = evaluate(request_for(config), catalog=catalog, now=config.start)
    assert result["request_id"] == "test-unique-id"
    assert result["status"] == "ok"
    assert result["satellite_count"] == 1
    assert len(result["windows"]) == 2
    assert utc(result["windows"][0]["end_utc"]) < config.start + timedelta(seconds=300)
    assert utc(result["windows"][1]["start_utc"]) > config.start + timedelta(seconds=300)
    assert result["warnings"]


def test_bridge_fails_on_stale_orbits(inputs):
    config, catalog = inputs
    config = replace(config, max_epoch_age_days=0.1)
    with pytest.raises(ValueError, match="No exposure authorized"):
        evaluate(request_for(config), catalog=catalog, now=config.start)


@pytest.mark.parametrize("hours", [-1, 25])
def test_bridge_fails_on_bad_download_age(inputs, hours):
    config, catalog = inputs
    catalog.fetched_at = (config.start - timedelta(hours=hours)).isoformat()
    with pytest.raises(ValueError, match="24 hours"):
        evaluate(request_for(config), catalog=catalog, now=config.start)


def test_bridge_has_no_windows_when_conditions_fail(inputs):
    config, catalog = inputs
    config = replace(config, max_sun_alt_deg=-90)
    result = evaluate(request_for(config), catalog=catalog, now=config.start)
    assert result["windows"] == []


@pytest.mark.parametrize(
    "payload", [{}, {"schema_version": 2}, {"schema_version": 1, "request_id": ""}]
)
def test_bad_protocol_fails(payload):
    with pytest.raises(ValueError):
        evaluate(payload)


def test_stdio_outputs_only_json_and_handles_unicode(tmp_path):
    config, _ = demo_inputs()
    from importlib.resources import files

    path = tmp_path / "衛星.csv"
    path.write_text(
        files("dodge_satelite").joinpath("data/demo.csv").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    request = dict(request_for(config), catalog_path=str(path))
    run = subprocess.run(
        [sys.executable, "-m", "dodge_satelite", "nina-bridge"],
        input=json.dumps(request).encode(),
        capture_output=True,
        timeout=60,
    )
    assert run.returncode == 0, run.stderr
    response = json.loads(run.stdout)
    assert response["status"] == "ok"
    assert response["catalog_source"].endswith("衛星.csv")


@pytest.mark.parametrize(
    "payload", [b"not-json", b"null", b"x" * 65537], ids=["invalid-json", "null", "oversized"]
)
def test_stdio_failure_never_authorizes_exposure(payload):
    result = subprocess.run(
        [sys.executable, "-m", "dodge_satelite.nina_bridge"],
        input=payload,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 2
    response = json.loads(result.stdout)
    assert response["status"] == "error"
    assert response["windows"] == []
