import csv
import json
import subprocess
import sys

from dodge_satelite.cli import main
from dodge_satelite.export import export_result, spreadsheet_text
from dodge_satelite.gui import MainWindow


def test_export_contains_provenance_and_utc(demo_result, tmp_path):
    export_result(demo_result, tmp_path)
    data = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert len(data["metadata"]["catalog_sha256"]) == 64
    assert data["metadata"]["satellite_count"] == 1
    assert data["warnings"]
    with (tmp_path / "exposures.csv").open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len(demo_result.exposures)
    assert all(row["start_utc"].endswith("Z") for row in rows)
    assert (tmp_path / "timeline.svg").read_text(encoding="utf-8").startswith("<svg")
    assert spreadsheet_text("=1+1") == "'=1+1"
    assert spreadsheet_text("  @evil") == "'  @evil"


def test_cli_end_to_end(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "dodge_satelite", "demo", "--out", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "1 predicted crossings" in result.stdout
    assert "DEMO" in result.stderr
    assert (tmp_path / "report.json").exists()


def test_cli_invalid_config(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text("{}")
    assert main(["plan", str(path), "--catalog", "missing.csv"]) == 2
    assert "Error:" in capsys.readouterr().err


def test_gui_demo_worker_and_export(qtbot, monkeypatch, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.calculate()
    qtbot.waitUntil(lambda: window.worker is None, timeout=60000)
    assert window.result is not None
    assert window.transit_table.rowCount() == 1
    assert window.exposure_table.rowCount() > 0
    assert window.export_button.isEnabled()
    monkeypatch.setattr(
        "dodge_satelite.gui.QFileDialog.getExistingDirectory", lambda *a: str(tmp_path)
    )
    window.export()
    assert (tmp_path / "report.json").exists()
    window.fields["exposure_s"].setValue(45)
    assert not window.export_button.isEnabled()
    assert "recalculate" in window.status.text()


def test_gui_failure_and_recovery(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.source.setCurrentIndex(1)
    window.catalog_value.setText(str(tmp_path / "missing.csv"))
    window.calculate()
    qtbot.waitUntil(lambda: window.worker is None, timeout=60000)
    assert window.result is None
    assert window.calculate_button.isEnabled()
    assert not window.export_button.isEnabled()
    assert "No plan" in window.summary.text()


def test_gui_profile_roundtrip(qtbot, inputs):
    window = MainWindow()
    qtbot.addWidget(window)
    config, _ = inputs
    window.set_config(config)
    actual = window.get_config()
    assert abs(actual.target.ra_deg - config.target.ra_deg) < 0.000001
    assert actual.start == config.start
    assert actual.equipment == config.equipment
