"""Copy a saved NINA sequence with current instruction type references.

Only JSON data is read; no embedded type is imported or instantiated.
"""

import json
from pathlib import Path

CURRENT_TYPE = "DodgeSatelite.NINA.SatelliteAwareExposure, DodgeSatelite.NINA"
MAX_BYTES = 16 * 1024 * 1024


def migrate_nodes(value, bundled_engine=False):
    changed = 0
    if isinstance(value, dict):
        type_name = value.get("$type")
        if isinstance(type_name, str) and type_name.split(",", 1)[0].endswith(
            ".NINA.SatelliteAwareExposure"
        ):
            edited = type_name != CURRENT_TYPE
            value["$type"] = CURRENT_TYPE
            if bundled_engine and value.get("EnginePath"):
                value["EnginePath"] = ""
                edited = True
            changed += int(edited)
        for child in value.values():
            changed += migrate_nodes(child, bundled_engine)
    elif isinstance(value, list):
        for child in value:
            changed += migrate_nodes(child, bundled_engine)
    return changed


def migrate_file(source: Path, destination: Path, bundled_engine=False):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("Choose a different output file; the original is never overwritten.")
    with source.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Sequence exceeds the 16 MiB migration limit.")
    payload = json.loads(data.decode("utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Expected a NINA sequence JSON object.")
    changed = migrate_nodes(payload, bundled_engine)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with destination.open("x", encoding="utf-8") as stream:
        stream.write(encoded)
    return changed
