"""CelesTrak GP CSV, validated before atomic cache replacement."""

import csv
import hashlib
import io
import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

import numpy as np
from skyfield.api import EarthSatellite, load

from .models import iso, utc

MIN_REFRESH_S = 7200
MAX_BYTES = 32 * 1024 * 1024
REQUIRED = {
    "OBJECT_NAME",
    "NORAD_CAT_ID",
    "EPOCH",
    "MEAN_MOTION",
    "ECCENTRICITY",
    "INCLINATION",
    "RA_OF_ASC_NODE",
    "ARG_OF_PERICENTER",
    "MEAN_ANOMALY",
    "BSTAR",
    "MEAN_MOTION_DOT",
    "MEAN_MOTION_DDOT",
    "REV_AT_EPOCH",
    "ELEMENT_SET_NO",
    "CLASSIFICATION_TYPE",
    "OBJECT_ID",
    "EPHEMERIS_TYPE",
}


class CatalogError(ValueError):
    pass


@dataclass
class Catalog:
    satellites: list
    source: str
    sha256: str
    fetched_at: str | None = None
    warnings: list[str] = field(default_factory=list)


def parse_csv(text: str, source: str = "local CSV", fetched_at=None) -> Catalog:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not REQUIRED.issubset(reader.fieldnames or []):
        raise CatalogError("Not a CelesTrak GP/OMM CSV: required columns are missing.")
    ts = load.timescale(builtin=True)
    satellites, ids = [], set()
    try:
        for row in reader:
            if len(satellites) >= 30000:
                raise ValueError("Catalog exceeds 30,000 satellites.")
            number = int(row["NORAD_CAT_ID"])
            if number in ids or not 1 <= number <= 999999999:
                raise ValueError("Duplicate or invalid NORAD ID.")
            if not 0 < float(row["MEAN_MOTION"]) < 20:
                raise ValueError("Invalid mean motion.")
            if not 0 <= float(row["ECCENTRICITY"]) < 1:
                raise ValueError("Invalid eccentricity.")
            if not 0 <= float(row["INCLINATION"]) <= 180:
                raise ValueError("Invalid inclination.")
            numeric = [
                float(row[k])
                for k in (
                    "RA_OF_ASC_NODE",
                    "ARG_OF_PERICENTER",
                    "MEAN_ANOMALY",
                    "BSTAR",
                    "MEAN_MOTION_DOT",
                    "MEAN_MOTION_DDOT",
                )
            ]
            if not np.all(np.isfinite(numeric)):
                raise ValueError("Non-finite orbital element.")
            # SGP4's identifier encoder is still Alpha-5 limited; propagation
            # does not depend on that identifier. Preserve full GP IDs ourselves.
            model_row = dict(row, NORAD_CAT_ID=str(number if number <= 339999 else 0))
            sat = EarthSatellite.from_omm(ts, model_row)
            sat.norad_id = number
            state = sat.at(sat.epoch)
            if state.message or not np.all(np.isfinite(state.position.km)):
                raise ValueError(f"Invalid SGP4 state: {state.message}")
            ids.add(number)
            satellites.append(sat)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise CatalogError(f"Invalid GP row {reader.line_num}: {exc}") from exc
    if not satellites:
        raise CatalogError("The catalog contains no satellites.")
    return Catalog(satellites, source, hashlib.sha256(text.encode("utf-8")).hexdigest(), fetched_at)


def local_catalog(path: Path) -> Catalog:
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise CatalogError("Catalog file exceeds 32 MiB.")
    result = parse_csv(path.read_text(encoding="utf-8-sig"), str(path.resolve()))
    result.warnings.append("Local CSV: acquisition time is unknown; check its source and epochs.")
    return result


def default_cache() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache"))
    return base / "DodgeSatelite" / "cache"


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Dodge-Satelite/0.1.0", "Accept": "text/csv"})
    with build_opener(NoRedirect).open(request, timeout=30) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise CatalogError("CelesTrak response exceeds 32 MiB.")
    return data.decode("utf-8-sig")


def _owner_is_gone(pid: int) -> bool:
    """Only recover a lock if its recorded owner is definitely no longer running."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER: no such PID
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value != 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        pass
    return False


@contextmanager
def _catalog_lock(lock: Path):
    # A separate OS lock serializes recovery. The legacy .lock remains compatible
    # with v0.1.0; the persistent .guard is automatically unlocked on process death.
    with lock.with_suffix(".guard").open("a+b") as guard:
        guard.seek(0, os.SEEK_END)
        if not guard.tell():
            guard.write(b"0")
            guard.flush()
        guard.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(guard.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise CatalogError(
                "Catalog is in use; retry after the other instance finishes."
            ) from exc
        if lock.exists():
            try:
                record = json.loads(lock.read_text(encoding="ascii"))
                pid = record["pid"]
                dead = type(pid) is int and _owner_is_gone(pid)
            except (ValueError, KeyError, TypeError, OSError):
                dead = False
            if dead:
                lock.unlink()
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise CatalogError(
                f"Catalog is in use: {lock}. For a legacy/unidentified lock, close all "
                "DodgeSatelite instances before removing that lock file."
            ) from exc
        try:
            with os.fdopen(descriptor, "w", encoding="ascii") as owner:
                json.dump({"pid": os.getpid()}, owner)
            yield
        finally:
            lock.unlink(missing_ok=True)


def fetch_catalog(group="visual", cache_dir=None, offline=False, now=None) -> Catalog:
    if not re.fullmatch(r"[a-zA-Z0-9-]{1,64}", group):
        raise CatalogError("Invalid CelesTrak group.")
    root = Path(cache_dir) if cache_dir is not None else default_cache()
    root.mkdir(parents=True, exist_ok=True)
    lock = root / f"{group.lower()}.lock"
    with _catalog_lock(lock):
        return _fetch_catalog(group, root, offline, now)


def _fetch_catalog(group="visual", cache_dir=None, offline=False, now=None) -> Catalog:
    if not re.fullmatch(r"[a-zA-Z0-9-]{1,64}", group):
        raise CatalogError("Invalid CelesTrak group; use a group such as visual or stations.")
    group = group.lower()
    now = utc(now or datetime.now(UTC))
    root = Path(cache_dir) if cache_dir is not None else default_cache()
    path, attempt = root / f"{group}.json", root / f"{group}.attempt.json"
    url = f"https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=CSV"
    cached, cache_error = None, None
    age = float("inf")
    if path.exists():
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            cached = parse_csv(record["csv"], url, record["fetched_at"])
            if cached.sha256 != record["sha256"]:
                raise CatalogError("Cache checksum mismatch.")
            age = (now - utc(record["fetched_at"])).total_seconds()
            if age < 0:
                raise CatalogError("Cache acquisition time is in the future; check the clock.")
        except (ValueError, KeyError, TypeError, OSError) as exc:
            cached, cache_error = None, str(exc)
    if cached and (offline or age < MIN_REFRESH_S):
        if age >= MIN_REFRESH_S:
            cached.warnings.append(f"Offline cache: last downloaded {age / 3600:.1f} hours ago.")
        return cached
    if offline:
        raise CatalogError(
            f"No valid offline cache for {group}. {cache_error or 'Fetch online first.'}"
        )
    if attempt.exists():
        try:
            last = json.loads(attempt.read_text(encoding="utf-8"))
            wait = MIN_REFRESH_S - (now - utc(last["at"])).total_seconds()
        except (ValueError, KeyError, TypeError) as exc:
            raise CatalogError(
                f"Invalid request history: {attempt}. Inspect it before retrying."
            ) from exc
        if wait > 0:
            message = (
                f"Request cooldown: retry in {wait / 60:.0f} minutes. Last status: {last['status']}"
            )
            if cached:
                cached.warnings.append("STALE CACHE FALLBACK. " + message)
                return cached
            raise CatalogError(message)
    # Record every attempt, including errors. No automatic retries or redirect loops.
    atomic_json(attempt, {"at": iso(now), "status": "started"})
    try:
        payload = download(url)
        result = parse_csv(payload, url, iso(now))
        atomic_json(path, {"csv": payload, "fetched_at": iso(now), "sha256": result.sha256})
        atomic_json(attempt, {"at": iso(now), "status": "ok"})
        return result
    except (URLError, OSError, ValueError, UnicodeError) as exc:
        message = f"Download failed ({exc}). No automatic retry for two hours."
        atomic_json(attempt, {"at": iso(now), "status": message})
        if cached:
            cached.warnings.append("STALE CACHE FALLBACK. " + message)
            return cached
        raise CatalogError(message) from exc
