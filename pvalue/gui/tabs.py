"""Tab pages for the desktop GUI."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt, QDate, QSettings
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from pvalue.data import get_time_interval_minutes, load_csv, validate_metocean
from pvalue.gui.widgets import ChartWidget, SummaryTable, TaskTable
from pvalue.gui.workers import KhoaFetchWorker, KmaFetchWorker
from pvalue.khoa import KHOA_STATIONS
from pvalue.khoa import get_station_label as khoa_get_station_label
from pvalue.kma import ALL_STATIONS, STATION_TYPES, get_station_label
from pvalue.models import SimulationConfig, Task
from pvalue.reporting import generate_excel_report
from pvalue.simulation import summarize_pxx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _guide(text: str) -> QLabel:
    """Create a styled guide/hint label."""
    lbl = QLabel(text)
    lbl.setObjectName("guide")
    lbl.setWordWrap(True)
    return lbl


def _section(text: str) -> QLabel:
    """Create a bold section header."""
    lbl = QLabel(text)
    lbl.setObjectName("hero")
    return lbl


# =====================================================================
# Tab 1 — Data Loading (with CSV / KMA API sub-tabs)
# =====================================================================

class DataTab(QWidget):
    """Load and validate metocean data from CSV file or KMA API."""

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # --- Header ---
        layout.addWidget(_section("Step 1: Load Metocean Data"))

        # --- Sub-tabs: CSV / KMA API ---
        self.source_tabs = QTabWidget()
        self.source_tabs.setDocumentMode(True)

        self._csv_widget = _CsvSourceWidget(self)
        self._kma_widget = _KmaSourceWidget(self)
        self._khoa_widget = _KhoaSourceWidget(self)
        self.source_tabs.addTab(self._csv_widget, "CSV 파일")
        self.source_tabs.addTab(self._kma_widget, "KMA API (기상청)")
        self.source_tabs.addTab(self._khoa_widget, "KHOA API (해양조사원)")
        layout.addWidget(self.source_tabs)

        # --- Shared: Status ---
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # --- Shared: Data preview ---
        self.preview = QTableWidget()
        self.preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.preview.setAlternatingRowColors(True)
        layout.addWidget(self.preview, stretch=1)

        self.preview_note = QLabel("")
        self.preview_note.setStyleSheet("color: #888; font-size: 11px; padding: 2px;")
        self.preview_note.setVisible(False)
        layout.addWidget(self.preview_note)

    # --- Shared finalization (called by both source widgets) ---

    def finalize_data(self, df: pd.DataFrame, source_label: str):
        """Validate, store, preview, and unlock downstream tabs."""
        ok, msg = validate_metocean(df)
        if not ok:
            QMessageBox.critical(
                self, "Validation Failed",
                f"{msg}\n\n"
                f"Required: DatetimeIndex + 'Hs' (0-20m) + 'Wind' (0-70m/s) columns, "
                f"minimum 24 records, less than 50% missing values."
            )
            return

        interval = get_time_interval_minutes(df)
        self.mw.df = df
        self.mw.interval_min = interval

        # Build status text with missing-data warning
        hs_nan = df["Hs"].isna().sum()
        wind_nan = df["Wind"].isna().sum()
        total = len(df)
        status = (
            f"<b style='color:green'>OK</b> — {source_label} | "
            f"{total:,} records | {interval}-min interval | "
            f"{df.index.min().date()} to {df.index.max().date()}"
        )
        if hs_nan > 0 or wind_nan > 0:
            pct_hs = hs_nan / total * 100
            pct_wind = wind_nan / total * 100
            parts = []
            if hs_nan > 0:
                parts.append(f"Hs {hs_nan:,}건({pct_hs:.1f}%)")
            if wind_nan > 0:
                parts.append(f"Wind {wind_nan:,}건({pct_wind:.1f}%)")
            status += (
                f"<br><span style='color:#cc6600'>⚠ 결측 데이터: "
                f"{', '.join(parts)} — 결측 구간은 시뮬레이션에서 작업 가능으로 처리됩니다 "
                f"(NA handling: permissive)</span>"
            )

        self.status_label.setText(status)
        self._show_preview(df)
        self.mw.unlock_after_data_loaded()
        self.mw.statusBar().showMessage(
            f"Data loaded: {source_label} — Go to Tab 2 to configure tasks"
        )

    def _show_preview(self, df: pd.DataFrame, max_rows=200):
        cols = list(df.columns)
        self.preview.setColumnCount(len(cols) + 1)
        self.preview.setHorizontalHeaderLabels(["Timestamp"] + cols)
        n = min(len(df), max_rows)
        self.preview.setRowCount(n)
        for i in range(n):
            self.preview.setItem(i, 0, QTableWidgetItem(str(df.index[i])))
            for j, col in enumerate(cols):
                val = df.iloc[i, j]
                text = f"{val:.3f}" if isinstance(val, float) else str(val)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.preview.setItem(i, j + 1, item)
        self.preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # Show truncation notice
        if len(df) > max_rows:
            self.preview_note.setText(f"Showing first {n:,} of {len(df):,} records")
            self.preview_note.setVisible(True)
        else:
            self.preview_note.setVisible(False)


# --- CSV Source Sub-widget ---

class _CsvSourceWidget(QWidget):
    """CSV file loading panel (sub-tab of DataTab)."""

    def __init__(self, data_tab: DataTab):
        super().__init__()
        self.data_tab = data_tab
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(_guide(
            "Select a CSV file containing historical wave height (Hs) and wind speed data. "
            "Supported formats: General CSV (with 'timestamp', 'Hs', 'Wind' columns) "
            "or ERA5 Hindcast CSV (auto-detected)."
        ))

        # File selection
        file_group = QGroupBox("CSV File")
        fg = QHBoxLayout(file_group)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Click Browse to select a CSV file...")
        self.path_edit.setReadOnly(True)
        btn_browse = QPushButton("Browse...")
        btn_browse.setToolTip("Open file dialog to select a metocean CSV")
        btn_browse.clicked.connect(self._browse)
        fg.addWidget(self.path_edit, stretch=1)
        fg.addWidget(btn_browse)
        layout.addWidget(file_group)

        # Options row
        opts = QHBoxLayout()
        opts.addWidget(QLabel("Format:"))
        self.csv_type_combo = QComboBox()
        self.csv_type_combo.addItems(["general", "hindcast"])
        self.csv_type_combo.setToolTip(
            "general: Standard CSV with 'timestamp', 'Hs', 'Wind' columns\n"
            "hindcast: ERA5 format with 5-line header (auto-detected columns)"
        )
        self.csv_type_combo.currentTextChanged.connect(self._toggle_hindcast)
        opts.addWidget(self.csv_type_combo)

        opts.addSpacing(20)
        self.date_check = QCheckBox("Date filter")
        self.date_check.setToolTip("Filter hindcast data to a specific date range")
        opts.addWidget(self.date_check)
        self.start_date = QLineEdit()
        self.start_date.setPlaceholderText("Start (YYYY-MM-DD)")
        self.start_date.setMaximumWidth(150)
        self.start_date.setEnabled(False)
        opts.addWidget(self.start_date)
        self.end_date = QLineEdit()
        self.end_date.setPlaceholderText("End (YYYY-MM-DD)")
        self.end_date.setMaximumWidth(150)
        self.end_date.setEnabled(False)
        opts.addWidget(self.end_date)
        self.date_check.toggled.connect(lambda on: (self.start_date.setEnabled(on), self.end_date.setEnabled(on)))
        opts.addStretch()

        btn_load = QPushButton("Load && Validate")
        btn_load.setObjectName("primary")
        btn_load.setToolTip("Load the selected CSV and run data quality checks")
        btn_load.clicked.connect(self._load)
        opts.addWidget(btn_load)

        btn_example = QPushButton("Load Example")
        btn_example.setToolTip(
            "Load bundled sample metocean data and config\n"
            "to try the simulator without your own data"
        )
        btn_example.clicked.connect(self._load_example)
        opts.addWidget(btn_example)
        layout.addLayout(opts)

        # CSV format help
        help_label = QLabel(
            "<b>General CSV example:</b><br>"
            "<code>timestamp,Hs,Wind<br>"
            "2020-01-01 00:00:00,1.2,8.5<br>"
            "2020-01-01 01:00:00,1.3,9.1</code>"
        )
        help_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")
        layout.addWidget(help_label)

        self._toggle_hindcast(self.csv_type_combo.currentText())

    def _toggle_hindcast(self, text):
        is_h = text == "hindcast"
        self.date_check.setVisible(is_h)
        self.start_date.setVisible(is_h)
        self.end_date.setVisible(is_h)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open CSV", "", "CSV Files (*.csv);;All Files (*)")
        if path:
            self.path_edit.setText(path)

    def _load(self):
        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "Warning", "Please select a CSV file first.")
            return

        csv_type = self.csv_type_combo.currentText()
        sd = self.start_date.text().strip() or None
        ed = self.end_date.text().strip() or None
        if not self.date_check.isChecked():
            sd = ed = None

        try:
            df = load_csv(path, csv_type, sd, ed)
        except Exception as exc:
            QMessageBox.critical(
                self, "Load Error",
                f"Failed to load file:\n{exc}\n\n"
                f"Make sure the file is a valid CSV with the correct format."
            )
            return

        self.data_tab.finalize_data(df, os.path.basename(path))

    def _load_example(self):
        """Load bundled example data and config."""
        import sys
        if getattr(sys, "frozen", False):
            base = os.path.join(sys._MEIPASS, "examples")
        else:
            base = os.path.join(os.path.dirname(__file__), "..", "..", "examples")
        base = os.path.normpath(base)

        csv_path = os.path.join(base, "sample_metocean.csv")
        config_path = os.path.join(base, "sample_config.json")

        if not os.path.isfile(csv_path):
            QMessageBox.warning(self, "Missing", f"Example CSV not found:\n{csv_path}")
            return

        try:
            df = load_csv(csv_path, "general")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to load example CSV:\n{exc}")
            return

        self.path_edit.setText(csv_path)
        self.data_tab.finalize_data(df, "Example Data")

        # Also load example config if available
        mw = self.data_tab.mw
        if os.path.isfile(config_path):
            try:
                with open(config_path, encoding="utf-8") as f:
                    data = json.load(f)
                if "tasks" in data:
                    mw.config_tab.task_table.load_tasks(data["tasks"])
                if "n_sims" in data:
                    mw.config_tab.n_sims_spin.setValue(data["n_sims"])
                if "pvals" in data:
                    mw.config_tab.pvals_edit.setText(",".join(str(p) for p in data["pvals"]))
            except Exception:
                pass

        mw.statusBar().showMessage(
            "Example data and config loaded — Go to Tab 2 to review, then Tab 3 to run"
        )


# --- KMA API Source Sub-widget ---

class _KmaSourceWidget(QWidget):
    """KMA API data fetching panel (sub-tab of DataTab)."""

    _SETTINGS_KEY = "kma_api_key"

    def __init__(self, data_tab: DataTab):
        super().__init__()
        self.data_tab = data_tab
        self._worker = None
        self._settings = QSettings("PValue", "MarinePValueSimulator")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(_guide(
            "기상청 API Hub에서 해양기상부이/등표/기상1호 관측 데이터를 자동으로 가져옵니다. "
            "API 인증키는 apihub.kma.go.kr에서 무료 발급 가능합니다."
        ))

        # API Key
        key_group = QGroupBox("API 인증키")
        kg = QHBoxLayout(key_group)
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("API Hub 인증키 입력...")
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        saved_key = self._settings.value(self._SETTINGS_KEY, "")
        if saved_key:
            self.key_edit.setText(saved_key)
        self.key_show_btn = QPushButton("표시")
        self.key_show_btn.setCheckable(True)
        self.key_show_btn.setMaximumWidth(50)
        self.key_show_btn.toggled.connect(
            lambda on: self.key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        btn_save_key = QPushButton("저장")
        btn_save_key.setMaximumWidth(50)
        btn_save_key.setToolTip("인증키를 로컬에 저장 (Windows 레지스트리, 암호화 없음)")
        btn_save_key.clicked.connect(self._save_key)
        kg.addWidget(self.key_edit, stretch=1)
        kg.addWidget(self.key_show_btn)
        kg.addWidget(btn_save_key)
        layout.addWidget(key_group)

        # Station selection
        stn_group = QGroupBox("관측소 선택")
        sg = QHBoxLayout(stn_group)

        sg.addWidget(QLabel("관측 유형:"))
        self.type_combo = QComboBox()
        for stype, info in STATION_TYPES.items():
            self.type_combo.addItem(info["label"], stype)
        self.type_combo.currentIndexChanged.connect(self._update_stations)
        sg.addWidget(self.type_combo)

        sg.addSpacing(10)
        sg.addWidget(QLabel("관측소:"))
        self.station_combo = QComboBox()
        self.station_combo.setMinimumWidth(200)
        sg.addWidget(self.station_combo, stretch=1)
        layout.addWidget(stn_group)

        # Date range
        date_group = QGroupBox("조회 기간")
        dg = QHBoxLayout(date_group)
        dg.addWidget(QLabel("시작:"))
        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDate(QDate.currentDate().addYears(-3))
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        dg.addWidget(self.date_start)

        dg.addSpacing(10)
        dg.addWidget(QLabel("종료:"))
        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDate(QDate.currentDate())
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        dg.addWidget(self.date_end)

        dg.addStretch()

        self.btn_fetch = QPushButton("Fetch Data")
        self.btn_fetch.setObjectName("primary")
        self.btn_fetch.clicked.connect(self._fetch)
        dg.addWidget(self.btn_fetch)

        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_fetch)
        dg.addWidget(self.btn_cancel)

        self.btn_save_csv = QPushButton("Save CSV")
        self.btn_save_csv.setToolTip("가져온 데이터를 CSV 파일로 저장")
        self.btn_save_csv.setEnabled(False)
        self.btn_save_csv.clicked.connect(self._save_csv)
        dg.addWidget(self.btn_save_csv)
        layout.addWidget(date_group)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.fetch_status = QLabel("")
        self.fetch_status.setWordWrap(True)
        layout.addWidget(self.fetch_status)

        layout.addStretch()

        # Populate station combo
        self._update_stations()

        # Store fetched df for CSV save
        self._fetched_df = None

    def _save_key(self):
        key = self.key_edit.text().strip()
        self._settings.setValue(self._SETTINGS_KEY, key)
        self.fetch_status.setText("<b style='color:green'>인증키 저장 완료</b>")

    def _update_stations(self):
        """Populate station combo based on selected type."""
        self.station_combo.clear()
        stype = self.type_combo.currentData()
        if not stype:
            return
        stations = ALL_STATIONS.get(stype, {})
        for stn_id, name in sorted(stations.items(), key=lambda x: x[0]):
            self.station_combo.addItem(f"{name} ({stn_id})", stn_id)

    def _fetch(self):
        api_key = self.key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Warning", "API 인증키를 입력해주세요.")
            return

        stype = self.type_combo.currentData()
        station_id = self.station_combo.currentData()
        if not station_id:
            QMessageBox.warning(self, "Warning", "관측소를 선택해주세요.")
            return

        qstart = self.date_start.date()
        qend = self.date_end.date()
        start = datetime(qstart.year(), qstart.month(), qstart.day())
        end = datetime(qend.year(), qend.month(), qend.day(), 23, 59)

        if end <= start:
            QMessageBox.warning(self, "Warning", "종료일이 시작일보다 뒤여야 합니다.")
            return

        # Cancel previous fetch if running
        if self._worker is not None and self._worker.isRunning():
            self._worker.finished.disconnect()
            self._worker.error.disconnect()
            self._worker.status.disconnect()
            self._worker.cancel()

        # Disable UI during fetch
        self.btn_fetch.setEnabled(False)
        self.btn_fetch.setText("수신 중...")
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.fetch_status.setText("")
        self._fetched_df = None
        self.btn_save_csv.setEnabled(False)

        self._worker = KmaFetchWorker(api_key, stype, station_id, start, end, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.status.connect(self._on_status)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _on_status(self, msg):
        self.fetch_status.setText(msg)

    def _cancel_fetch(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self.btn_fetch.setEnabled(True)
            self.btn_fetch.setText("Fetch Data")
            self.btn_cancel.setEnabled(False)
            self.progress_bar.setVisible(False)
            self.fetch_status.setText("<b style='color:#cc6600'>수신 취소됨</b>")

    def _on_finished(self, df):
        self.btn_fetch.setEnabled(True)
        self.btn_fetch.setText("Fetch Data")
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setVisible(False)
        self._fetched_df = df
        self.btn_save_csv.setEnabled(True)

        stype = self.type_combo.currentData()
        station_id = self.station_combo.currentData()
        label = get_station_label(stype, station_id)
        self.fetch_status.setText(
            f"<b style='color:green'>수신 완료</b> — {label} | {len(df):,}건 | "
            f"{df.index.min().date()} ~ {df.index.max().date()}<br>"
            f"<span style='color:#cc6600'>⚠ API 데이터는 파고(Hs) 소수점 1자리 정밀도로 제공됩니다 "
            f"(P값 차이 ~1% 이내)</span>"
        )

        # Finalize: validate and load into program
        self.data_tab.finalize_data(df, f"KMA API: {label}")

    def _on_error(self, msg):
        self.btn_fetch.setEnabled(True)
        self.btn_fetch.setText("Fetch Data")
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.fetch_status.setText(f"<b style='color:red'>오류</b> — {msg}")

    def _save_csv(self):
        if self._fetched_df is None:
            return
        stype = self.type_combo.currentData()
        station_id = self.station_combo.currentData()
        label = get_station_label(stype, station_id)
        name = label.split("(")[0].strip().replace(" ", "_")
        df = self._fetched_df
        start = df.index.min().strftime("%y%m")
        end = df.index.max().strftime("%y%m")
        default_name = f"{name}_{start}_{end}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", default_name, "CSV (*.csv)")
        if not path:
            return
        out = df.copy()
        out.index.name = "timestamp"
        out.to_csv(path)
        self.fetch_status.setText(
            f"<b style='color:green'>CSV 저장 완료</b> — {os.path.basename(path)}"
        )


# --- KHOA API Source Sub-widget ---

class _KhoaSourceWidget(QWidget):
    """KHOA API data fetching panel (sub-tab of DataTab)."""

    _SETTINGS_KEY = "khoa_api_key"

    def __init__(self, data_tab: DataTab):
        super().__init__()
        self.data_tab = data_tab
        self._worker = None
        self._settings = QSettings("PValue", "MarinePValueSimulator")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(_guide(
            "국립해양조사원(KHOA) 해양관측부이 데이터를 공공데이터포털(data.go.kr)에서 가져옵니다.\n"
            "⚠ API 데이터는 파고(Hs) 소수점 1자리 정밀도로 제공됩니다 (P값 차이 ~1% 이내). "
            "고정밀(소수 2자리) 데이터가 필요하면 KHOA 홈페이지에서 CSV를 다운받아 사용하세요."
        ))

        # API Key
        key_group = QGroupBox("API 인증키 (공공데이터포털)")
        kg = QHBoxLayout(key_group)
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("data.go.kr 인증키 입력...")
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        saved_key = self._settings.value(self._SETTINGS_KEY, "")
        if saved_key:
            self.key_edit.setText(saved_key)
        self.key_show_btn = QPushButton("표시")
        self.key_show_btn.setCheckable(True)
        self.key_show_btn.setMaximumWidth(50)
        self.key_show_btn.toggled.connect(
            lambda on: self.key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        btn_save_key = QPushButton("저장")
        btn_save_key.setMaximumWidth(50)
        btn_save_key.setToolTip("인증키를 로컬에 저장 (Windows 레지스트리, 암호화 없음)")
        btn_save_key.clicked.connect(self._save_key)
        kg.addWidget(self.key_edit, stretch=1)
        kg.addWidget(self.key_show_btn)
        kg.addWidget(btn_save_key)
        layout.addWidget(key_group)

        # Station selection
        stn_group = QGroupBox("관측소 선택")
        sg = QHBoxLayout(stn_group)
        sg.addWidget(QLabel("관측소:"))
        self.station_combo = QComboBox()
        self.station_combo.setMinimumWidth(250)
        for obs_code, name in sorted(KHOA_STATIONS.items(), key=lambda x: x[0]):
            self.station_combo.addItem(f"{name} ({obs_code})", obs_code)
        sg.addWidget(self.station_combo, stretch=1)
        layout.addWidget(stn_group)

        # Date range
        date_group = QGroupBox("조회 기간")
        dg = QHBoxLayout(date_group)
        dg.addWidget(QLabel("시작:"))
        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDate(QDate.currentDate().addYears(-3))
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        dg.addWidget(self.date_start)

        dg.addSpacing(10)
        dg.addWidget(QLabel("종료:"))
        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDate(QDate.currentDate())
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        dg.addWidget(self.date_end)

        dg.addStretch()

        self.btn_fetch = QPushButton("Fetch Data")
        self.btn_fetch.setObjectName("primary")
        self.btn_fetch.clicked.connect(self._fetch)
        dg.addWidget(self.btn_fetch)

        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_fetch)
        dg.addWidget(self.btn_cancel)

        self.btn_save_csv = QPushButton("Save CSV")
        self.btn_save_csv.setToolTip("가져온 데이터를 CSV 파일로 저장")
        self.btn_save_csv.setEnabled(False)
        self.btn_save_csv.clicked.connect(self._save_csv)
        dg.addWidget(self.btn_save_csv)
        layout.addWidget(date_group)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.fetch_status = QLabel("")
        self.fetch_status.setWordWrap(True)
        layout.addWidget(self.fetch_status)

        layout.addStretch()
        self._fetched_df = None

    def _save_key(self):
        key = self.key_edit.text().strip()
        self._settings.setValue(self._SETTINGS_KEY, key)
        self.fetch_status.setText("<b style='color:green'>인증키 저장 완료</b>")

    def _fetch(self):
        service_key = self.key_edit.text().strip()
        if not service_key:
            QMessageBox.warning(self, "Warning", "API 인증키를 입력해주세요.")
            return

        obs_code = self.station_combo.currentData()
        if not obs_code:
            QMessageBox.warning(self, "Warning", "관측소를 선택해주세요.")
            return

        qstart = self.date_start.date()
        qend = self.date_end.date()
        start = datetime(qstart.year(), qstart.month(), qstart.day())
        end = datetime(qend.year(), qend.month(), qend.day(), 23, 59)

        if end <= start:
            QMessageBox.warning(self, "Warning", "종료일이 시작일보다 뒤여야 합니다.")
            return

        # Warn about long date ranges
        days = (end - start).days
        if days > 365:
            reply = QMessageBox.question(
                self, "장기간 조회",
                f"조회 기간이 {days}일입니다. 하루 단위로 API를 호출하므로 "
                f"시간이 오래 걸릴 수 있습니다.\n계속하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Cancel previous fetch if running
        if self._worker is not None and self._worker.isRunning():
            self._worker.finished.disconnect()
            self._worker.error.disconnect()
            self._worker.status.disconnect()
            self._worker.cancel()

        self.btn_fetch.setEnabled(False)
        self.btn_fetch.setText("수신 중...")
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.fetch_status.setText("")
        self._fetched_df = None
        self.btn_save_csv.setEnabled(False)

        self._worker = KhoaFetchWorker(service_key, obs_code, start, end, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.status.connect(self._on_status)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _on_status(self, msg):
        self.fetch_status.setText(msg)

    def _cancel_fetch(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self.btn_fetch.setEnabled(True)
            self.btn_fetch.setText("Fetch Data")
            self.btn_cancel.setEnabled(False)
            self.progress_bar.setVisible(False)
            self.fetch_status.setText("<b style='color:#cc6600'>수신 취소됨</b>")

    def _on_finished(self, df):
        self.btn_fetch.setEnabled(True)
        self.btn_fetch.setText("Fetch Data")
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setVisible(False)
        self._fetched_df = df
        self.btn_save_csv.setEnabled(True)

        obs_code = self.station_combo.currentData()
        label = khoa_get_station_label(obs_code)
        self.fetch_status.setText(
            f"<b style='color:green'>수신 완료</b> — {label} | {len(df):,}건 | "
            f"{df.index.min().date()} ~ {df.index.max().date()}<br>"
            f"<span style='color:#cc6600'>⚠ API 데이터는 파고(Hs) 소수점 1자리 정밀도로 제공됩니다 "
            f"(P값 차이 ~1% 이내)</span>"
        )

        self.data_tab.finalize_data(df, f"KHOA API: {label}")

    def _on_error(self, msg):
        self.btn_fetch.setEnabled(True)
        self.btn_fetch.setText("Fetch Data")
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.fetch_status.setText(f"<b style='color:red'>오류</b> — {msg}")

    def _save_csv(self):
        if self._fetched_df is None:
            return
        from pvalue.khoa import get_station_label as khoa_label, KHOA_STATIONS
        obs_code = self.station_combo.currentData()
        name = KHOA_STATIONS.get(obs_code, obs_code).replace(" ", "_")
        df = self._fetched_df
        start = df.index.min().strftime("%y%m")
        end = df.index.max().strftime("%y%m")
        default_name = f"{name}_{start}_{end}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", default_name, "CSV (*.csv)")
        if not path:
            return
        out = df.copy()
        out.index.name = "timestamp"
        out.to_csv(path)
        self.fetch_status.setText(
            f"<b style='color:green'>CSV 저장 완료</b> — {os.path.basename(path)}"
        )


# =====================================================================
# Tab 2 — Task & Config
# =====================================================================

class ConfigTab(QWidget):
    """Task definitions + simulation parameters."""

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(_section("Step 2: Define Tasks & Settings"))
        layout.addWidget(_guide(
            "Each task represents one operation phase (e.g. mobilization, installation). "
            "Set the weather thresholds — work is blocked when Hs or Wind exceeds these limits."
        ))

        # --- Task table ---
        task_group = QGroupBox("Tasks")
        tg = QVBoxLayout(task_group)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Add Task")
        btn_add.setToolTip("Add a new task row to the table")
        btn_add.clicked.connect(lambda: self.task_table.add_row())
        btn_remove = QPushButton("- Remove Selected")
        btn_remove.setToolTip("Remove the selected task row")
        btn_remove.clicked.connect(lambda: self.task_table.remove_selected())
        btn_import = QPushButton("Import JSON...")
        btn_import.setToolTip("Load task and config definitions from a JSON file")
        btn_import.clicked.connect(self._import_json)
        btn_export = QPushButton("Export JSON...")
        btn_export.setToolTip("Save current tasks and settings to a JSON file for reuse")
        btn_export.clicked.connect(self._export_json)
        for b in (btn_add, btn_remove, btn_import, btn_export):
            btn_row.addWidget(b)
        btn_row.addStretch()
        tg.addLayout(btn_row)

        self.task_table = TaskTable()
        tg.addWidget(self.task_table)
        layout.addWidget(task_group, stretch=1)

        # --- Simulation settings ---
        sim_group = QGroupBox("Simulation Settings")
        sg = QHBoxLayout(sim_group)

        # Column 1
        col1 = QVBoxLayout()
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Simulations:"))
        self.n_sims_spin = QSpinBox()
        self.n_sims_spin.setRange(100, 50000)
        self.n_sims_spin.setValue(1000)
        self.n_sims_spin.setSingleStep(100)
        self.n_sims_spin.setToolTip(
            "Number of Monte Carlo iterations.\n"
            "More = more accurate but slower.\n"
            "Recommended: 1000 for quick analysis, 5000+ for final reports."
        )
        r1.addWidget(self.n_sims_spin)
        col1.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Percentiles:"))
        self.pvals_edit = QLineEdit("50,75,90")
        self.pvals_edit.setToolTip(
            "Comma-separated percentile values to report (0-100).\n"
            "P50 = median estimate\n"
            "P75 = 75% confidence\n"
            "P90 = conservative estimate (90% confidence)"
        )
        r2.addWidget(self.pvals_edit)
        col1.addLayout(r2)

        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Seed:"))
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 99999)
        self.seed_spin.setValue(7)
        self.seed_spin.setToolTip(
            "Random seed for reproducibility.\n"
            "Same seed = same results every time.\n"
            "Change to get different random samples."
        )
        r3.addWidget(self.seed_spin)
        col1.addLayout(r3)
        sg.addLayout(col1)

        # Column 2
        col2 = QVBoxLayout()
        self.radio_continuous = QRadioButton("Continuous mode")
        self.radio_continuous.setChecked(True)
        self.radio_continuous.setToolTip(
            "Work requires an uninterrupted weather window.\n"
            "If bad weather hits mid-task, the entire block must restart."
        )
        self.radio_split = QRadioButton("Split (accumulated) mode")
        self.radio_split.setToolTip(
            "Work can be paused and resumed.\n"
            "Worked hours accumulate across multiple weather windows."
        )
        # Explicit QButtonGroup to prevent cross-group interference
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.radio_continuous)
        self._mode_group.addButton(self.radio_split)
        col2.addWidget(self.radio_continuous)
        col2.addWidget(self.radio_split)

        col2.addSpacing(8)
        self.radio_permissive = QRadioButton("Permissive NA (work OK)")
        self.radio_permissive.setChecked(True)
        self.radio_permissive.setToolTip(
            "Missing data (NA) is treated as 'work possible'.\n"
            "Use when data gaps are likely calm periods."
        )
        self.radio_conservative = QRadioButton("Conservative NA (work blocked)")
        self.radio_conservative.setToolTip(
            "Missing data (NA) is treated as 'work blocked'.\n"
            "Use for worst-case planning."
        )
        self._na_group = QButtonGroup(self)
        self._na_group.addButton(self.radio_permissive)
        self._na_group.addButton(self.radio_conservative)
        col2.addWidget(self.radio_permissive)
        col2.addWidget(self.radio_conservative)
        sg.addLayout(col2)

        # Column 3
        col3 = QVBoxLayout()
        month_row = QHBoxLayout()
        self.month_check = QCheckBox("Start month:")
        self.month_check.setToolTip(
            "Restrict simulation start to a specific month.\n"
            "Useful if the campaign has a planned start season."
        )
        self.month_combo = QComboBox()
        _MONTH_LABELS = [
            "1 - Jan", "2 - Feb", "3 - Mar", "4 - Apr", "5 - May", "6 - Jun",
            "7 - Jul", "8 - Aug", "9 - Sep", "10 - Oct", "11 - Nov", "12 - Dec",
        ]
        for i, label in enumerate(_MONTH_LABELS, 1):
            self.month_combo.addItem(label, i)
        self.month_combo.setEnabled(False)
        self.month_check.toggled.connect(self.month_combo.setEnabled)
        month_row.addWidget(self.month_check)
        month_row.addWidget(self.month_combo)
        col3.addLayout(month_row)

        cal_row = QHBoxLayout()
        self.cal_check = QCheckBox("Business hours:")
        self.cal_check.setToolTip(
            "Restrict work to specific hours of the day.\n"
            "Example: 8-18 means work only between 08:00 and 18:00."
        )
        self.cal_start = QSpinBox()
        self.cal_start.setRange(0, 23)
        self.cal_start.setValue(8)
        self.cal_start.setEnabled(False)
        self.cal_end = QSpinBox()
        self.cal_end.setRange(1, 24)
        self.cal_end.setValue(18)
        self.cal_end.setEnabled(False)
        self.cal_check.toggled.connect(self.cal_start.setEnabled)
        self.cal_check.toggled.connect(self.cal_end.setEnabled)
        cal_row.addWidget(self.cal_check)
        cal_row.addWidget(self.cal_start)
        cal_row.addWidget(QLabel("–"))
        cal_row.addWidget(self.cal_end)
        col3.addLayout(cal_row)
        col3.addStretch()
        sg.addLayout(col3)

        layout.addWidget(sim_group)

    def build_config(self) -> SimulationConfig:
        """Build SimulationConfig from current widget state."""
        tasks = self.task_table.get_tasks()
        if not tasks:
            raise ValueError("At least one task is required.")

        try:
            pvals = [int(x.strip()) for x in self.pvals_edit.text().split(",") if x.strip()]
            if not pvals:
                raise ValueError("At least one percentile is required")
            if any(not 0 <= p <= 100 for p in pvals):
                raise ValueError("Percentiles must be between 0 and 100")
        except ValueError as exc:
            raise ValueError(f"Invalid percentiles: {exc}")
        start_month = self.month_combo.currentData() if self.month_check.isChecked() else None
        cal_hours = (self.cal_start.value(), self.cal_end.value()) if self.cal_check.isChecked() else None

        return SimulationConfig(
            tasks=tasks,
            n_sims=self.n_sims_spin.value(),
            start_month=start_month,
            split_mode=self.radio_split.isChecked(),
            na_handling="conservative" if self.radio_conservative.isChecked() else "permissive",
            pvals=pvals,
            calendar_hours=cal_hours,
            seed=self.seed_spin.value(),
        )

    def _import_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Config", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if "tasks" in data:
                self.task_table.load_tasks(data["tasks"])
            else:
                QMessageBox.warning(self, "Warning", "JSON file has no 'tasks' key.")
                return
            # Always reset all fields to defaults first, then apply JSON values.
            # This prevents stale state when importing a JSON that omits some fields.
            self.n_sims_spin.setValue(data.get("n_sims", 1000))
            self.pvals_edit.setText(",".join(str(p) for p in data.get("pvals", [50, 75, 90])))
            self.seed_spin.setValue(data.get("seed", 7))

            # Split mode (default: continuous)
            if data.get("split_mode", False):
                self.radio_split.setChecked(True)
            else:
                self.radio_continuous.setChecked(True)

            # NA handling (default: permissive)
            if data.get("na_handling", "permissive") == "conservative":
                self.radio_conservative.setChecked(True)
            else:
                self.radio_permissive.setChecked(True)

            # Start month (default: None / unchecked)
            if data.get("start_month") is not None:
                self.month_check.setChecked(True)
                idx = data["start_month"] - 1
                if 0 <= idx < self.month_combo.count():
                    self.month_combo.setCurrentIndex(idx)
            else:
                self.month_check.setChecked(False)

            # Calendar / business hours (default: unchecked, 8-18)
            cal_applied = False
            cal = data.get("calendar")
            if isinstance(cal, list) and len(cal) >= 3:
                hours_str = cal[2]
                try:
                    sh, eh = map(int, str(hours_str).split("-"))
                    self.cal_start.setValue(sh)
                    self.cal_end.setValue(eh)
                    self.cal_check.setChecked(cal[0] == "custom")
                    cal_applied = True
                except ValueError:
                    pass

            # calendar_hours (refactored format) — takes precedence
            ch = data.get("calendar_hours")
            if isinstance(ch, (list, tuple)) and len(ch) == 2:
                self.cal_check.setChecked(True)
                self.cal_start.setValue(ch[0])
                self.cal_end.setValue(ch[1])
                cal_applied = True

            if not cal_applied:
                self.cal_check.setChecked(False)
                self.cal_start.setValue(8)
                self.cal_end.setValue(18)

            self.mw.statusBar().showMessage(f"Config imported from {os.path.basename(path)}")
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", str(exc))

    def _export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Config", "config.json", "JSON (*.json)")
        if not path:
            return
        try:
            config = self.build_config()
            data = {
                "tasks": [
                    {"name": t.name, "duration_h": t.duration_h, "thresholds": t.thresholds, "setup_h": t.setup_h, "teardown_h": t.teardown_h}
                    for t in config.tasks
                ],
                "n_sims": config.n_sims,
                "pvals": config.pvals,
                "split_mode": config.split_mode,
                "na_handling": config.na_handling,
                "start_month": config.start_month,
                "seed": config.seed,
            }
            if config.calendar_hours:
                data["calendar_hours"] = list(config.calendar_hours)
                data["calendar"] = ["custom", "UTC", f"{config.calendar_hours[0]}-{config.calendar_hours[1]}"]
            else:
                data["calendar"] = ["all"]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.mw.statusBar().showMessage(f"Config exported to {os.path.basename(path)}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))


# =====================================================================
# Tab 3 — Run Simulation
# =====================================================================

class RunTab(QWidget):
    """Execute simulation with progress feedback."""

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(_section("Step 3: Run Simulation"))
        self.info_label = QLabel(
            "Click <b>Start Simulation</b> to run. "
            "The simulator randomly samples start dates from historical data "
            "and measures how long each campaign takes under real weather conditions."
        )
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("Start Simulation")
        self.btn_start.setObjectName("primary")
        self.btn_start.setToolTip("Begin Monte Carlo simulation with current data and settings")
        self.btn_start.clicked.connect(self._start)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setToolTip("Stop the running simulation")
        self.btn_cancel.clicked.connect(self._cancel)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(self.log_area, stretch=1)

    def _start(self):
        if self.mw.df is None:
            QMessageBox.warning(self, "No Data", "Please load data in the Data tab first.")
            return
        try:
            config = self.mw.config_tab.build_config()
        except Exception as exc:
            QMessageBox.warning(self, "Config Error", str(exc))
            return

        # Clean up previous worker if still running
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.worker.finished.disconnect()
            self.worker.error.disconnect()

        self.log_area.clear()
        self.progress.setValue(0)
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self._last_config = config  # cache for use in _on_finished

        n_tasks = len(config.tasks)
        total_h = sum(t.total_hours for t in config.tasks)
        self.info_label.setText(
            f"Running: {config.n_sims} sims | {n_tasks} task(s) | "
            f"{total_h}h total work | "
            f"{'split' if config.split_mode else 'continuous'} mode"
        )

        from pvalue.gui.workers import SimulationWorker

        self.worker = SimulationWorker(self.mw.df, config, self.mw.interval_min)
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self._on_log)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _cancel(self):
        if self.worker:
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)

    def _on_progress(self, current, total):
        self.progress.setValue(int(current / total * 100))
        self.progress.setFormat(f"{current}/{total} ({current / total * 100:.0f}%)")

    def _on_log(self, msg):
        self.log_area.append(msg)

    def _on_finished(self, res_df, summary_df):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setValue(100)
        self.log_area.append("Done! Switching to Results tab...")

        self.mw.results_df = res_df
        self.mw.summary_df = summary_df
        self.mw.results_tab.load_results(res_df, summary_df)
        self.mw.charts_tab.update_charts(res_df, self._last_config.pvals)
        self.mw.unlock_after_simulation()
        self.mw.tabs.setCurrentWidget(self.mw.results_tab)
        self.mw.statusBar().showMessage("Simulation complete — Review results in Tab 4")

    def _on_error(self, msg):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.log_area.append(f"ERROR: {msg}")
        QMessageBox.critical(self, "Simulation Error", msg)


# =====================================================================
# Tab 4 — Results
# =====================================================================

_P_EXPLANATIONS = {
    "P50": "Median — 50% chance of finishing within this duration",
    "P75": "75% confidence — reasonable planning estimate",
    "P90": "Conservative — 90% chance of finishing within this duration",
    "Mean": "Average duration across all simulations",
    "Std": "Standard deviation — measures spread of results",
    "Min": "Best-case scenario (shortest simulation)",
    "Max": "Worst-case scenario (longest simulation)",
}


class ResultsTab(QWidget):
    """Display summary statistics and raw results."""

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(_section("Results"))

        # Interpretation panel
        self.interpretation = QLabel("")
        self.interpretation.setObjectName("interpretation")
        self.interpretation.setWordWrap(True)
        self.interpretation.setVisible(False)
        layout.addWidget(self.interpretation)

        # Export buttons
        btn_row = QHBoxLayout()
        btn_csv = QPushButton("Export CSV...")
        btn_csv.setToolTip("Save raw simulation results as a CSV file")
        btn_csv.clicked.connect(self._export_csv)
        btn_excel = QPushButton("Export Excel...")
        btn_excel.setToolTip("Save formatted report with summary, results, and task info")
        btn_excel.clicked.connect(self._export_excel)
        btn_row.addWidget(btn_csv)
        btn_row.addWidget(btn_excel)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: summary + explanation
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.summary_table = SummaryTable()
        left_layout.addWidget(self.summary_table)

        self.explain_area = QTextEdit()
        self.explain_area.setReadOnly(True)
        self.explain_area.setMaximumHeight(180)
        self.explain_area.setStyleSheet("font-size: 12px; color: #555; background: #fafafa;")
        left_layout.addWidget(self.explain_area)

        splitter.addWidget(left_panel)

        # Right: full results
        self.results_view = QTableWidget()
        self.results_view.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_view.setAlternatingRowColors(True)
        self.results_view.setSortingEnabled(True)
        splitter.addWidget(self.results_view)

        splitter.setSizes([350, 650])
        layout.addWidget(splitter, stretch=1)

    def load_results(self, res_df: pd.DataFrame, summary_df: pd.DataFrame):
        self.summary_table.load_summary(summary_df)
        self._populate_table(res_df)
        self._update_interpretation(summary_df)
        self._update_explanations(summary_df)

    def _update_interpretation(self, summary_df: pd.DataFrame):
        """Show a plain-language interpretation of key results."""
        vals = {row["Metric"]: row["Value_days"] for _, row in summary_df.iterrows()}
        p50 = vals.get("P50", 0)
        p90 = vals.get("P90", 0)

        self.interpretation.setText(
            f"<b>Summary:</b> The campaign is expected to take approximately "
            f"<b>{p50:.1f} days</b> (median). "
            f"For conservative planning, allow <b>{p90:.1f} days</b> "
            f"(90% confidence level)."
        )
        self.interpretation.setVisible(True)

    def _update_explanations(self, summary_df: pd.DataFrame):
        """Fill the explanation panel with metric descriptions."""
        lines = []
        for _, row in summary_df.iterrows():
            metric = str(row["Metric"])
            value = row["Value_days"]
            desc = _P_EXPLANATIONS.get(metric, "")
            lines.append(f"<b>{metric} = {value:.2f} days</b><br>{desc}")
        self.explain_area.setHtml("<br>".join(lines))

    def _populate_table(self, df: pd.DataFrame):
        cols = list(df.columns)
        self.results_view.setColumnCount(len(cols))
        self.results_view.setHorizontalHeaderLabels(cols)
        self.results_view.setRowCount(len(df))
        for i in range(len(df)):
            for j, col in enumerate(cols):
                val = df.iloc[i, j]
                text = f"{val:.4f}" if isinstance(val, float) else str(val)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.results_view.setItem(i, j, item)
        self.results_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def _export_csv(self):
        if self.mw.results_df is None:
            QMessageBox.information(self, "Info", "시뮬레이션을 먼저 실행해주세요.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "results.csv", "CSV (*.csv)")
        if path:
            try:
                self.mw.results_df.to_csv(path, index=False)
                self.mw.statusBar().showMessage(f"CSV saved: {path}")
            except Exception as exc:
                QMessageBox.critical(self, "Export Error", f"CSV 저장 실패:\n{exc}")

    def _export_excel(self):
        if self.mw.results_df is None or self.mw.summary_df is None:
            QMessageBox.information(self, "Info", "시뮬레이션을 먼저 실행해주세요.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Excel", "report.xlsx", "Excel (*.xlsx)")
        if path:
            try:
                tasks_data = [
                    {"name": t.name, "duration_h": t.duration_h, "thresholds": t.thresholds,
                     "setup_h": t.setup_h, "teardown_h": t.teardown_h}
                    for t in self.mw.config_tab.task_table.get_tasks()
                ]
                ok = generate_excel_report(self.mw.results_df, self.mw.summary_df, {"tasks": tasks_data}, path)
                if ok:
                    self.mw.statusBar().showMessage(f"Excel saved: {path}")
                else:
                    QMessageBox.warning(self, "Warning",
                        "openpyxl이 설치되어 있지 않아 Excel 저장이 불가합니다.\n"
                        "pip install openpyxl 로 설치 후 다시 시도하세요.")
            except Exception as exc:
                QMessageBox.critical(self, "Export Error", f"Excel 저장 실패:\n{exc}")


# =====================================================================
# Tab 5 — Charts
# =====================================================================

class ChartsTab(QWidget):
    """Embedded matplotlib visualisations."""

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(_section("Charts"))

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Chart:"))
        self.chart_combo = QComboBox()
        self.chart_combo.addItems(["Histogram + P-values", "CDF", "Work vs Wait Scatter", "Timeline (Top 5)"])
        self.chart_combo.setToolTip(
            "Histogram: Duration distribution with percentile lines\n"
            "CDF: Cumulative probability curve\n"
            "Scatter: Work time vs. weather waiting time\n"
            "Timeline: Longest simulations broken into work/wait"
        )
        self.chart_combo.currentIndexChanged.connect(self._switch_chart)
        ctrl.addWidget(self.chart_combo)

        btn_save = QPushButton("Save Chart...")
        btn_save.setToolTip("Save the current chart as PNG or PDF")
        btn_save.clicked.connect(self._save)
        ctrl.addWidget(btn_save)

        btn_save_all = QPushButton("Save All Charts...")
        btn_save_all.setToolTip("Save all chart types to a folder")
        btn_save_all.clicked.connect(self._save_all)
        ctrl.addWidget(btn_save_all)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        self.chart = ChartWidget(figsize=(11, 6))
        layout.addWidget(self.chart, stretch=1)

        self._res = None
        self._pvals = [50, 75, 90]

    def update_charts(self, res_df, pvals):
        self._res = res_df
        self._pvals = pvals
        self._switch_chart(self.chart_combo.currentIndex())

    def _switch_chart(self, idx):
        if self._res is None:
            return
        self.chart.clear()
        ax = self.chart.figure.add_subplot(111)
        days = self._res["elapsed_days"]

        if idx == 0:
            self._draw_histogram(ax, days)
        elif idx == 1:
            self._draw_cdf(ax, days)
        elif idx == 2:
            self._draw_scatter(ax)
        elif idx == 3:
            self._draw_timeline()
            return  # timeline manages its own axes

        self.chart.refresh()

    def _draw_histogram(self, ax, days):
        ax.hist(days, bins=40, alpha=0.7, color="skyblue", edgecolor="black")
        colors = {50: "royalblue", 75: "orange", 90: "crimson"}
        for p in self._pvals:
            val = np.percentile(days, p)
            ax.axvline(val, color=colors.get(p, "gray"), lw=2, ls="--", label=f"P{p} = {val:.1f}d")
        ax.set_xlabel("Campaign Duration (days)")
        ax.set_ylabel("Frequency")
        ax.set_title("Campaign Duration Distribution")
        ax.legend()
        ax.grid(alpha=0.3)
        self.chart.refresh()

    def _draw_cdf(self, ax, days):
        s = np.sort(days)
        cdf = np.arange(1, len(s) + 1) / len(s) * 100
        ax.plot(s, cdf, lw=2, color="navy")
        ax.set_xlabel("Campaign Duration (days)")
        ax.set_ylabel("Cumulative Probability (%)")
        ax.set_title("CDF")
        ax.grid(alpha=0.3)
        self.chart.refresh()

    def _draw_scatter(self, ax):
        ax.scatter(self._res["work_hours"] / 24, self._res["wait_hours"] / 24, alpha=0.5, s=20, color="steelblue")
        ax.set_xlabel("Active Time incl. Setup/Teardown (days)")
        ax.set_ylabel("Weather Wait (days)")
        ax.set_title("Active vs. Wait Time")
        ax.grid(alpha=0.3)
        self.chart.refresh()

    def _draw_timeline(self):
        self.chart.figure.clear()
        samples = self._res.nlargest(5, "elapsed_days")
        n = len(samples)
        axes = self.chart.figure.subplots(n, 1, sharex=True)
        if n == 1:
            axes = [axes]
        for i, (_, row) in enumerate(samples.iterrows()):
            ax = axes[i]
            wd = row["work_hours"] / 24
            wtd = row["wait_hours"] / 24
            td = row["elapsed_days"]
            ax.barh(0, wd, color="seagreen", alpha=0.8, label="Work")
            ax.barh(0, wtd, left=wd, color="tomato", alpha=0.8, label="Wait")
            ax.text(wd / 2, 0, f"{wd:.1f}d", ha="center", va="center", fontsize=8, fontweight="bold")
            ax.text(wd + wtd / 2, 0, f"{wtd:.1f}d", ha="center", va="center", fontsize=8, fontweight="bold")
            ax.set_yticks([])
            ax.set_xlim(0, td * 1.05)
            ax.set_title(f'Sim #{int(row["sim"]) + 1} — {td:.1f}d', fontsize=9, loc="left")
            if i == 0:
                ax.legend(fontsize=8, loc="upper right")
            ax.grid(axis="x", alpha=0.3)
        axes[-1].set_xlabel("Duration (days)")
        self.chart.figure.suptitle("Work / Wait Timeline (Top 5)", fontweight="bold", y=0.995)
        self.chart.figure.tight_layout()
        self.chart.refresh()

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Chart", "chart.png", "PNG (*.png);;PDF (*.pdf)")
        if path:
            self.chart.figure.savefig(path, dpi=150, bbox_inches="tight")
            self.mw.statusBar().showMessage(f"Chart saved: {path}")

    def _save_all(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if not folder or self._res is None:
            return
        from pvalue.visualization import save_all_charts
        save_all_charts(self._res, self._pvals, folder)
        self.mw.statusBar().showMessage(f"All charts saved to {folder}")


# =====================================================================
# Tab 6 — Optimal Month
# =====================================================================

class OptimalMonthTab(QWidget):
    """Analyse all 12 months to find the best campaign start."""

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(_section("Optimal Start Month"))
        layout.addWidget(_guide(
            "Runs the simulation for each of the 12 months to find which month "
            "gives the shortest P90 campaign duration. Useful for scheduling "
            "when you have flexibility on start date."
        ))

        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("Analyze All 12 Months")
        self.btn_run.setObjectName("primary")
        self.btn_run.setToolTip("Run simulation for each start month using current tasks and settings")
        self.btn_run.clicked.connect(self._run)
        btn_row.addWidget(self.btn_run)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 12)
        layout.addWidget(self.progress)

        self.result_label = QLabel("")
        self.result_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.result_label)

        mid = QSplitter(Qt.Orientation.Horizontal)

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        mid.addWidget(self.table)

        self.chart = ChartWidget(figsize=(8, 5))
        mid.addWidget(self.chart)

        mid.setSizes([300, 700])
        layout.addWidget(mid, stretch=1)

    def _run(self):
        if self.mw.df is None:
            QMessageBox.warning(self, "No Data", "Please load data first.")
            return
        try:
            config = self.mw.config_tab.build_config()
        except Exception as exc:
            QMessageBox.warning(self, "Config Error", str(exc))
            return

        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)

        from pvalue.gui.workers import OptimalMonthWorker

        self.worker = OptimalMonthWorker(self.mw.df, config, self.mw.interval_min)
        self.worker.progress.connect(lambda m: self.progress.setValue(m))
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _cancel(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.btn_run.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.progress.setValue(0)
            self.result_label.setText("분석 취소됨")

    def _on_finished(self, result_df, optimal):
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        p90_min = result_df["P90_days"].min()
        p90_max = result_df["P90_days"].max()
        _MNAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        self.result_label.setText(
            f"Optimal start month: {optimal} ({_MNAMES[optimal]})  "
            f"(P90 = {p90_min:.1f} days vs worst {p90_max:.1f} days)"
        )

        # Table
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Month", "P90 (days)", "Mean (days)"])
        self.table.setRowCount(12)
        for i, (_, row) in enumerate(result_df.iterrows()):
            m = int(row["Month"])
            self.table.setItem(i, 0, QTableWidgetItem(f"{m} - {_MNAMES[m]}"))
            self.table.setItem(i, 1, QTableWidgetItem(f'{row["P90_days"]:.2f}'))
            self.table.setItem(i, 2, QTableWidgetItem(f'{row["Mean_days"]:.2f}'))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # Chart
        self.chart.clear()
        ax = self.chart.figure.add_subplot(111)
        ax.plot(result_df["Month"], result_df["P90_days"], marker="o", lw=2, label="P90")
        ax.plot(result_df["Month"], result_df["Mean_days"], marker="s", lw=2, alpha=0.7, label="Mean")
        ax.axvline(optimal, color="red", ls="--", alpha=0.5, label=f"Optimal: Month {optimal}")
        ax.set_xlabel("Start Month")
        ax.set_ylabel("Campaign Duration (days)")
        ax.set_title("Monthly Analysis")
        ax.set_xticks(range(1, 13))
        ax.legend()
        ax.grid(alpha=0.3)
        self.chart.refresh()

        self.mw.statusBar().showMessage(f"Optimal month: {optimal}")

    def _on_error(self, msg):
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        QMessageBox.critical(self, "Error", msg)
