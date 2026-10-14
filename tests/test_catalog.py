import json
import os
import subprocess
import sys
from datetime import timedelta
from importlib.resources import files
from urllib.error import HTTPError

import pytest

from dodge_satelite import catalog as module
from dodge_satelite.catalog import CatalogError, fetch_catalog, local_catalog, parse_csv
from dodge_satelite.models import utc


@pytest.fixture
def payload():
    return files("dodge_satelite").joinpath("data/demo.csv").read_text(encoding="utf-8")


def test_nine_digit_id_preserved(payload):
    result = parse_csv(payload)
    assert result.satellites[0].norad_id == 999999001
    assert result.satellites[0].model.satnum == 0


@pytest.mark.parametrize("text", ["<html>rate limited</html>", "", "OBJECT_NAME,EPOCH\nISS,today"])
def test_bad_response_rejected(text):
    with pytest.raises(CatalogError):
        parse_csv(text)


def test_duplicates_and_bad_numbers(payload):
    with pytest.raises(CatalogError, match="Duplicate"):
        parse_csv(payload + payload.splitlines()[1] + "\n")
    with pytest.raises(CatalogError):
        parse_csv(payload.replace(",15.5,", ",nan,"))
    with pytest.raises(CatalogError):
        parse_csv(payload.replace(",0.0004,", ",2.0,"))


def test_cache_reuse_and_offline(payload, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(module, "download", lambda url: calls.append(url) or payload)
    now = utc("2026-10-14T00:00:00Z")
    first = fetch_catalog("stations", tmp_path, now=now)
    second = fetch_catalog("stations", tmp_path, now=now + timedelta(minutes=119))
    assert first.sha256 == second.sha256
    assert len(calls) == 1
    offline = fetch_catalog("stations", tmp_path, offline=True, now=now + timedelta(days=1))
    assert "Offline cache" in offline.warnings[0]
    fetch_catalog("stations", tmp_path, now=now + timedelta(hours=2))
    assert len(calls) == 2


def test_download_error_keeps_cache_and_throttles(payload, monkeypatch, tmp_path):
    now = utc("2026-10-14T00:00:00Z")
    monkeypatch.setattr(module, "download", lambda _: payload)
    fetch_catalog("visual", tmp_path, now=now)
    before = (tmp_path / "visual.json").read_bytes()
    calls = []

    def failure(url):
        calls.append(url)
        raise HTTPError(url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(module, "download", failure)
    result = fetch_catalog("visual", tmp_path, now=now + timedelta(hours=3))
    assert "STALE CACHE FALLBACK" in result.warnings[0]
    result = fetch_catalog("visual", tmp_path, now=now + timedelta(hours=3, minutes=1))
    assert "cooldown" in result.warnings[0]
    assert len(calls) == 1
    assert (tmp_path / "visual.json").read_bytes() == before


def test_bad_download_not_cached_and_no_retry(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(module, "download", lambda _: calls.append(1) or "error page")
    with pytest.raises(CatalogError):
        fetch_catalog("stations", tmp_path)
    with pytest.raises(CatalogError, match="cooldown"):
        fetch_catalog("stations", tmp_path)
    assert len(calls) == 1
    assert not (tmp_path / "stations.json").exists()


def test_corruption_and_missing_offline(payload, monkeypatch, tmp_path):
    with pytest.raises(CatalogError, match="offline"):
        fetch_catalog("visual", tmp_path, offline=True)
    monkeypatch.setattr(module, "download", lambda _: payload)
    fetch_catalog("visual", tmp_path)
    path = tmp_path / "visual.json"
    data = json.loads(path.read_text())
    data["sha256"] = "wrong"
    path.write_text(json.dumps(data))
    with pytest.raises(CatalogError, match="checksum"):
        fetch_catalog("visual", tmp_path, offline=True)


def test_group_path_injection_and_lock(tmp_path):
    with pytest.raises(CatalogError):
        fetch_catalog("../../escape", tmp_path)
    (tmp_path / "visual.lock").touch()
    with pytest.raises(CatalogError, match="in use"):
        fetch_catalog("visual", tmp_path)


def test_local_catalog_provenance(payload, tmp_path):
    path = tmp_path / "satellites.csv"
    path.write_text(payload, encoding="utf-8-sig")
    catalog = local_catalog(path)
    assert catalog.fetched_at is None
    assert "unknown" in catalog.warnings[0]


def test_live_owner_lock_is_not_removed(tmp_path):
    lock = tmp_path / "visual.lock"
    lock.write_text(json.dumps({"pid": os.getpid()}))
    with pytest.raises(CatalogError, match="in use"):
        fetch_catalog("visual", tmp_path)
    assert lock.exists()


def test_killed_fetch_can_be_used_again(payload, monkeypatch, tmp_path):
    # Kill an actual owner while inside the fetch, as NINA does on cancellation.
    script = """
import sys, time
from dodge_satelite import catalog
def pending(*args):
    print('READY', flush=True)
    time.sleep(30)
catalog._fetch_catalog = pending
catalog.fetch_catalog('visual', sys.argv[1])
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)], stdout=subprocess.PIPE, text=True
    )
    try:
        assert process.stdout.readline().strip() == "READY"
    finally:
        process.kill()
        process.wait(timeout=10)
        process.stdout.close()
    assert (tmp_path / "visual.lock").exists()
    monkeypatch.setattr(module, "download", lambda _: payload)
    result = fetch_catalog("visual", tmp_path)
    assert result.satellites
    assert not (tmp_path / "visual.lock").exists()
