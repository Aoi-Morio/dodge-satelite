"""PySide6 desktop interface. Calculation and networking run on a worker thread."""

import json
import sys
from datetime import timedelta
from pathlib import Path
from threading import Event

from PySide6.QtCore import QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .catalog import fetch_catalog, local_catalog
from .cli import demo_inputs
from .export import export_result
from .models import Equipment, PlanConfig, Site, Target, iso
from .predict import CancelledError, plan


class Worker(QThread):
    result_ready = Signal(object)
    failed = Signal(str)
    progress = Signal(int, str)

    def __init__(self, config, source, value, parent=None):
        super().__init__(parent)
        self.config, self.source, self.value = config, source, value
        self.cancel = Event()

    def run(self):
        try:
            self.progress.emit(0, "Loading orbital elements / 軌道データ読み込み")
            if self.source == 0:
                _, catalog = demo_inputs()
            elif self.source == 1:
                catalog = local_catalog(Path(self.value))
            else:
                catalog = fetch_catalog(self.value, offline=self.source == 3)
            self.result_ready.emit(plan(self.config, catalog, self.progress.emit, self.cancel))
        except CancelledError:
            self.failed.emit("Cancelled / 中止しました")
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class Timeline(QWidget):
    def __init__(self):
        super().__init__()
        self.result = None
        self.setMinimumHeight(205)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111b2c"))
        painter.setPen(QColor("#dce8f7"))
        if self.result is None:
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Calculate to display timeline / 計算するとタイムラインを表示します",
            )
            return
        r = self.result
        rows = [
            ("Conditions / 観測条件", r.metadata["condition_blocked"], "#778195"),
            ("Satellite / 衛星リスク", r.metadata["satellite_blocked"], "#ffae66"),
            ("Exposure / 露光", [vars(x) for x in r.exposures], "#62dbbd"),
        ]
        left, width = 180, max(1, self.width() - 202)
        for i, (label, intervals, color) in enumerate(rows):
            y = 25 + i * 48
            painter.drawText(10, y + 20, label)
            painter.fillRect(QRectF(left, y, width, 28), QColor("#263247"))
            for interval in intervals:
                x = left + width * interval["start_s"] / r.config.duration_s
                w = max(1, width * (interval["end_s"] - interval["start_s"]) / r.config.duration_s)
                painter.fillRect(QRectF(x, y, w, 28), QColor(color))
        painter.drawText(10, 182, f"UTC  {iso(r.config.start)}  →  {iso(r.config.end)}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"dodge satelite {__version__}")
        self.resize(1240, 850)
        self.worker = None
        self.result = None
        self.close_pending = False
        self.fields = {}
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        title = QLabel("dodge satelite")
        title.setStyleSheet("font-size: 25px; font-weight: 600; color: #64ddbd;")
        outer.addWidget(title)
        subtitle = QLabel("衛星通過を考慮した撮影計画  /  Satellite-aware exposure planning")
        outer.addWidget(subtitle)
        notice = QLabel(
            "予測は選択した衛星データの範囲です。写り込みの回避・精度は保証されません。\n"
            "Planning assistance only. Catalog coverage and orbital errors limit every result."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("background: #3b3024; color: #ffcc8e; padding: 10px;")
        outer.addWidget(notice)
        split = QSplitter()
        outer.addWidget(split, 1)
        self.editor = QWidget()
        editor_layout = QVBoxLayout(self.editor)
        buttons = QHBoxLayout()
        for label, handler in [
            ("Demo / サンプル", self.load_demo),
            ("Open / 読込", self.open_profile),
            ("Save / 保存", self.save_profile),
        ]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        editor_layout.addLayout(buttons)
        self.source = QComboBox()
        self.source.addItems(
            [
                "Demo: synthetic / 架空データ",
                "Local GP CSV / ローカルCSV",
                "CelesTrak online / オンライン",
                "CelesTrak cache only / キャッシュのみ",
            ]
        )
        self.source.currentIndexChanged.connect(self.source_changed)
        source_box = QGroupBox("Orbital data / 衛星データ")
        source_form = QFormLayout(source_box)
        source_form.addRow(self.source)
        self.catalog_value = QLineEdit("visual")
        self.catalog_label = QLabel("Group or CSV / グループ名・CSV")
        source_form.addRow(self.catalog_label, self.catalog_value)
        self.browse_button = QPushButton("Browse CSV / CSV選択")
        self.browse_button.clicked.connect(self.browse_catalog)
        source_form.addRow(self.browse_button)
        subset = QLabel(
            "visual / stations は一部の衛星のみ。\n初回オンライン取得後は2時間キャッシュを再利用。"
        )
        subset.setWordWrap(True)
        source_form.addRow(subset)
        editor_layout.addWidget(source_box)

        self.add_group(
            editor_layout,
            "Site / 観測地 (東経・北緯が正)",
            [
                ("site_name", "Name / 名前", None),
                ("latitude_deg", "Latitude / 緯度 °", (-90, 90, 6)),
                ("longitude_deg", "Longitude / 経度 °", (-180, 180, 6)),
                ("elevation_m", "Elevation / 標高 m", (-500, 9000, 1)),
            ],
        )
        self.add_group(
            editor_layout,
            "Target / 対象 (ICRS固定座標)",
            [
                ("target_name", "Name / 名前", None),
                ("ra_deg", "RA / 赤経 ° (時ではなく度)", (0, 359.999999, 6)),
                ("dec_deg", "Dec / 赤緯 °", (-90, 90, 6)),
            ],
        )
        self.add_group(
            editor_layout,
            "Equipment / 機材",
            [
                ("focal_length_mm", "Focal length / 焦点距離 mm", (0.1, 100000, 2)),
                ("sensor_width_mm", "Sensor width / センサー幅 mm", (0.1, 1000, 2)),
                ("sensor_height_mm", "Sensor height / センサー高 mm", (0.1, 1000, 2)),
            ],
        )
        self.add_group(
            editor_layout,
            "Session / 撮影時間 (Z または +09:00 等を必須)",
            [
                ("start", "Start / 開始 ISO 8601", None),
                ("end", "End / 終了 ISO 8601", None),
                ("exposure_s", "Exposure / 露光 秒", (0.1, 86400, 2)),
                ("readout_s", "Readout / 読出し 秒", (0, 3600, 2)),
            ],
        )
        self.add_group(
            editor_layout,
            "Constraints / 判定条件",
            [
                ("min_target_alt_deg", "Min target altitude / 最低対象高度 °", (0, 90, 1)),
                ("max_sun_alt_deg", "Max Sun altitude / 最大太陽高度 °", (-90, 90, 1)),
                ("sample_s", "Sample step / サンプル間隔 秒", (0.05, 2, 2)),
                ("padding_s", "Time margin / 前後の余裕 秒", (0, 3600, 2)),
                ("angular_margin_deg", "Angular margin / 角度の余裕 °", (0, 10, 3)),
                ("max_epoch_age_days", "Epoch warning / 元期差の警告 日", (0.01, 365, 2)),
            ],
        )
        self.sunlit_only = QCheckBox("Sunlit + penumbra only / 日照・半影の衛星のみ回避")
        self.sunlit_only.setToolTip(
            "外すと地球の影にある衛星も回避します。明るさの予測ではありません。"
        )
        editor_layout.addWidget(self.sunlit_only)
        editor_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.editor)
        split.addWidget(scroll)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.summary = QLabel("Load the demo, then Calculate / サンプルを読み込んで計算できます")
        self.summary.setWordWrap(True)
        right_layout.addWidget(self.summary)
        self.timeline = Timeline()
        right_layout.addWidget(self.timeline)
        tabs = QTabWidget()
        self.exposure_table = self.table(["#", "Start UTC / 開始", "End UTC / 終了"])
        self.transit_table = self.table(
            ["NORAD", "Satellite / 衛星", "Start UTC", "End UTC", "元期差 days"]
        )
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        tabs.addTab(self.exposure_table, "Exposures / 露光")
        tabs.addTab(self.transit_table, "Transits / 通過")
        tabs.addTab(self.details, "Warnings & data / 警告・データ")
        right_layout.addWidget(tabs, 1)
        split.addWidget(right)
        split.setSizes([465, 775])
        actions = QHBoxLayout()
        self.calculate_button = QPushButton("Calculate / 計算")
        self.calculate_button.clicked.connect(self.calculate)
        self.cancel_button = QPushButton("Cancel / 中止")
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setEnabled(False)
        self.export_button = QPushButton("Export CSV + report / 結果保存")
        self.export_button.clicked.connect(self.export)
        self.export_button.setEnabled(False)
        self.progress = QProgressBar()
        for widget in (
            self.calculate_button,
            self.cancel_button,
            self.export_button,
            self.progress,
        ):
            actions.addWidget(widget)
        outer.addLayout(actions)
        self.status = QLabel("Ready / 準備完了")
        outer.addWidget(self.status)
        self.load_demo()
        for widget in self.fields.values():
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self.inputs_changed)
            else:
                widget.valueChanged.connect(self.inputs_changed)
        self.sunlit_only.toggled.connect(self.inputs_changed)
        self.source.currentIndexChanged.connect(self.inputs_changed)
        self.catalog_value.textChanged.connect(self.inputs_changed)

    def inputs_changed(self):
        if self.result is not None:
            self.export_button.setEnabled(False)
            self.status.setText(
                "Inputs changed — recalculate before export / 入力変更：保存前に再計算してください"
            )

    def add_group(self, layout, title, fields):
        group = QGroupBox(title)
        form = QFormLayout(group)
        for key, label, bounds in fields:
            if bounds:
                widget = QDoubleSpinBox()
                widget.setRange(bounds[0], bounds[1])
                widget.setDecimals(bounds[2])
                widget.setSingleStep(0.1 if bounds[2] else 1)
            else:
                widget = QLineEdit()
                widget.setMinimumWidth(220)
            self.fields[key] = widget
            form.addRow(label, widget)
        layout.addWidget(group)

    def table(self, headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        return table

    def source_changed(self):
        self.catalog_value.setEnabled(self.source.currentIndex() != 0)
        self.browse_button.setEnabled(self.source.currentIndex() == 1)

    def load_demo(self):
        config, _ = demo_inputs()
        self.set_config(config)
        self.source.setCurrentIndex(0)
        self.source_changed()

    def set_config(self, config):
        values = config.to_dict()
        values.update(values.pop("site"))
        values["site_name"] = config.site.name
        values.update(values.pop("target"))
        values["target_name"] = config.target.name
        values.update(values.pop("equipment"))
        for key, widget in self.fields.items():
            if isinstance(widget, QLineEdit):
                widget.setText(str(values[key]))
            else:
                widget.setValue(values[key])
        self.sunlit_only.setChecked(config.sunlit_only)

    def get_config(self):
        values = {
            key: (widget.text() if isinstance(widget, QLineEdit) else widget.value())
            for key, widget in self.fields.items()
        }
        site = Site(
            name=values.pop("site_name"),
            **{k: values.pop(k) for k in ("latitude_deg", "longitude_deg", "elevation_m")},
        )
        target = Target(
            name=values.pop("target_name"), **{k: values.pop(k) for k in ("ra_deg", "dec_deg")}
        )
        equipment = Equipment(
            **{k: values.pop(k) for k in ("focal_length_mm", "sensor_width_mm", "sensor_height_mm")}
        )
        return PlanConfig(
            site=site,
            target=target,
            equipment=equipment,
            sunlit_only=self.sunlit_only.isChecked(),
            **values,
        )

    def open_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open observation profile", "", "JSON (*.json)")
        if path:
            try:
                self.set_config(PlanConfig.load(Path(path)))
            except (ValueError, TypeError, KeyError, OSError) as exc:
                self.show_error(str(exc))

    def save_profile(self):
        try:
            config = self.get_config()
            path, _ = QFileDialog.getSaveFileName(
                self, "Save observation profile", "observation.json", "JSON (*.json)"
            )
            if path:
                config.save(Path(path))
        except (ValueError, OSError) as exc:
            self.show_error(str(exc))

    def browse_catalog(self):
        path, _ = QFileDialog.getOpenFileName(self, "CelesTrak GP CSV", "", "CSV (*.csv)")
        if path:
            self.catalog_value.setText(path)

    def calculate(self):
        try:
            config = self.get_config()
        except (ValueError, TypeError) as exc:
            self.show_error(str(exc))
            return
        self.result = None
        self.timeline.result = None
        self.timeline.update()
        self.export_button.setEnabled(False)
        self.exposure_table.setRowCount(0)
        self.transit_table.setRowCount(0)
        self.details.clear()
        self.summary.setText("Computing… / 計算中…")
        self.editor.setEnabled(False)
        self.calculate_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setValue(0)
        self.worker = Worker(
            config, self.source.currentIndex(), self.catalog_value.text().strip(), self
        )
        self.worker.progress.connect(self.on_progress)
        self.worker.result_ready.connect(self.show_result)
        self.worker.failed.connect(self.calculation_failed)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def on_progress(self, percent, message):
        self.progress.setValue(percent)
        self.status.setText(message)

    def cancel(self):
        if self.worker:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("Cancelling after the current operation / 現在の処理終了後に中止")

    def worker_finished(self):
        self.editor.setEnabled(True)
        self.calculate_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        if self.close_pending:
            self.close()

    def calculation_failed(self, message):
        self.summary.setText("No plan produced / 計画は生成されませんでした")
        self.status.setText(message)
        self.details.setPlainText(message)

    def show_result(self, result):
        self.result = result
        self.timeline.result = result
        self.timeline.update()
        self.export_button.setEnabled(True)
        self.summary.setText(
            f"{len(result.exposures)} exposures / 露光 · {len(result.transits)} crossings / 通過\n"
            f"Without avoidance: {len(result.baseline)} exposures, {result.baseline_at_risk} at risk\n"
            f"回避前: {len(result.baseline)} 枚中 {result.baseline_at_risk} 枚に予測リスク\n"
            f"Field / 視野: {result.config.equipment.width_deg:.2f}° × {result.config.equipment.height_deg:.2f}° "
            "(外接円で判定)"
        )

        def timestamp(seconds):
            return iso(result.config.start + timedelta(seconds=seconds))

        self.exposure_table.setRowCount(len(result.exposures))
        for row, item in enumerate(result.exposures):
            for column, value in enumerate(
                [row + 1, timestamp(item.start_s), timestamp(item.end_s)]
            ):
                self.exposure_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.transit_table.setRowCount(len(result.transits))
        for row, item in enumerate(result.transits):
            for column, value in enumerate(
                [
                    item.norad_id,
                    item.name,
                    timestamp(item.start_s),
                    timestamp(item.end_s),
                    f"{item.epoch_offset_days:.3f}",
                ]
            ):
                self.transit_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.details.setPlainText(
            "警告: データ不足・軌道変動・サンプル間の曲率により見逃す可能性があります。\n"
            "日照判定は明るさを保証しません。サンプルは架空の過去データです。\n\n"
            + "\n\n".join(result.warnings)
            + "\n\n"
            + json.dumps(result.metadata, indent=2, ensure_ascii=False)
        )
        self.status.setText("Complete — review warnings / 完了：警告・データを確認してください")
        self.progress.setValue(100)

    def export(self):
        if self.result is None:
            return
        path = QFileDialog.getExistingDirectory(self, "Choose output folder / 保存先")
        if path:
            try:
                export_result(self.result, Path(path))
                self.status.setText(f"Saved / 保存済: {path}")
            except OSError as exc:
                self.show_error(str(exc))

    def show_error(self, message):
        QMessageBox.warning(self, "dodge satelite", message)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.close_pending = True
            self.cancel()
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    # Bounded executable smoke check used by CI; no networking.
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(250, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
