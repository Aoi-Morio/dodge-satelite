import json

import pytest

from dodge_satelite.cli import main
from dodge_satelite.migrate import CURRENT_TYPE, migrate_file, migrate_nodes


def test_migration_changes_only_matching_types_and_preserves_references():
    sequence = {
        "$id": "1",
        "Items": [
            {
                "$type": "Previous.NINA.SatelliteAwareExposure, Previous.NINA",
                "Parent": {"$ref": "1"},
                "ExposureTime": 60,
                "EnginePath": "custom.exe",
            },
            {"$type": "Another.Exposure, Another", "Name": "天体"},
        ],
    }
    assert migrate_nodes(sequence) == 1
    assert sequence["Items"][0]["$type"] == CURRENT_TYPE
    assert sequence["Items"][0]["Parent"] == {"$ref": "1"}
    assert sequence["Items"][0]["EnginePath"] == "custom.exe"
    assert sequence["Items"][1] == {"$type": "Another.Exposure, Another", "Name": "天体"}
    assert migrate_nodes(sequence) == 0
    assert migrate_nodes(sequence, bundled_engine=True) == 1
    assert sequence["Items"][0]["EnginePath"] == ""


def test_cli_writes_new_copy_without_overwriting_original(tmp_path):
    source, output = tmp_path / "input.json", tmp_path / "copy.json"
    original = json.dumps({"$type": "Previous.NINA.SatelliteAwareExposure, Previous.NINA"}).encode()
    source.write_bytes(original)
    assert main(["migrate-nina", str(source), "--out", str(output)]) == 0
    assert source.read_bytes() == original
    assert json.loads(output.read_text())["$type"] == CURRENT_TYPE
    with pytest.raises(FileExistsError):
        migrate_file(source, output)
    with pytest.raises(ValueError, match="different output"):
        migrate_file(source, source)


@pytest.mark.parametrize("data", [b"not json", b"[]"])
def test_invalid_input_does_not_create_output(tmp_path, data):
    source, output = tmp_path / "bad.json", tmp_path / "copy.json"
    source.write_bytes(data)
    with pytest.raises(ValueError):
        migrate_file(source, output)
    assert not output.exists()
