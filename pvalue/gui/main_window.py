"""Main application window for the desktop GUI."""

from __future__ import annotations

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QTabWidget,
)

from pvalue import __version__
from pvalue.gui.tabs import ChartsTab, ConfigTab, DataTab, OptimalMonthTab, ResultsTab, RunTab

_STYLESHEET = """
/* ── Global ── */
* {
    font-family: "Segoe UI", "Malgun Gothic", sans-serif;
    font-size: 13px;
}
QMainWindow { background-color: #F6F8FB; }
QStatusBar { font-size: 12px; color: #5B6778; }

/* ── Tabs ── */
QTabWidget::pane {
    border: 1px solid #D0D7E2;
    border-top: none;
    background: white;
}
QTabBar::tab {
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 500;
    color: #6B7280;
    border: none;
    border-bottom: 3px solid transparent;
    margin-right: 2px;
    background: transparent;
}
QTabBar::tab:selected {
    color: #1F5B92;
    font-weight: 600;
    border-bottom: 3px solid #1F5B92;
}
QTabBar::tab:hover:!selected {
    color: #374151;
    border-bottom: 3px solid #D0D7E2;
}
QTabBar::tab:disabled { color: #C0C5CE; }

/* ── Buttons ── */
QPushButton {
    padding: 7px 16px;
    border: 1px solid #D0D7E2;
    border-radius: 5px;
    background-color: white;
    color: #374151;
    font-weight: 500;
}
QPushButton:hover { background-color: #F0F4F8; border-color: #9CA3AF; }
QPushButton:pressed { background-color: #E5E9EF; }
QPushButton:disabled {
    color: #B0B8C4; background-color: #F9FAFB; border-color: #E5E7EB;
}
QPushButton#primary {
    background-color: #1F5B92; color: white;
    font-weight: 600; padding: 8px 22px; border: none; border-radius: 5px;
}
QPushButton#primary:hover { background-color: #174A78; }
QPushButton#primary:pressed { background-color: #123D63; }
QPushButton#primary:disabled { background-color: #9CBCD8; }

/* ── GroupBox (card style) ── */
QGroupBox {
    font-weight: 600;
    font-size: 13px;
    color: #1F2937;
    background-color: #F0F4F8;
    border: none;
    border-radius: 6px;
    margin-top: 16px;
    padding: 16px 12px 12px 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #1F5B92;
    font-weight: 600;
}

/* ── Tables ── */
QTableWidget {
    gridline-color: #E5E7EB;
    background-color: white;
    alternate-background-color: #F8FAFB;
    border: 1px solid #D0D7E2;
    border-radius: 4px;
}
QHeaderView::section {
    background-color: #E8EEF4;
    color: #1F2937;
    font-weight: 600;
    padding: 6px 8px;
    border: none;
    border-bottom: 2px solid #1F5B92;
    border-right: 1px solid #D0D7E2;
}

/* ── Progress Bar ── */
QProgressBar {
    border: 1px solid #D0D7E2;
    border-radius: 5px;
    text-align: center;
    background-color: #F0F4F8;
    min-height: 22px;
    font-size: 12px;
}
QProgressBar::chunk { background-color: #1F5B92; border-radius: 4px; }

/* ── Inputs ── */
QLineEdit, QSpinBox, QComboBox, QDateEdit {
    padding: 5px 8px;
    border: 1px solid #D0D7E2;
    border-radius: 4px;
    background: white;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QDateEdit:focus {
    border-color: #1F5B92;
}

/* ── Labels ── */
QLabel#guide {
    color: #5B6778;
    font-size: 12px;
    padding: 8px 12px;
    background-color: #F0F4F8;
    border-radius: 4px;
    border-left: 3px solid #1F5B92;
}
QLabel#hero {
    font-size: 20px;
    font-weight: 700;
    color: #1F2937;
    padding: 12px 0 4px 0;
}
QLabel#interpretation {
    background-color: #EAF1F7;
    border: 1px solid #B8CCDD;
    border-left: 4px solid #1F5B92;
    border-radius: 4px;
    padding: 12px 16px;
    color: #1F2937;
}

/* ── Status Badges ── */
QLabel#statusSuccess {
    background-color: #ECFDF5; color: #065F46;
    border: 1px solid #A7F3D0; border-radius: 4px;
    padding: 8px 12px; font-weight: 500;
}
QLabel#statusWarning {
    background-color: #FFFBEB; color: #92400E;
    border: 1px solid #FDE68A; border-radius: 4px;
    padding: 8px 12px; font-weight: 500;
}
QLabel#statusError {
    background-color: #FEF2F2; color: #991B1B;
    border: 1px solid #FECACA; border-radius: 4px;
    padding: 8px 12px; font-weight: 500;
}

/* ── TextEdit (log area) ── */
QTextEdit {
    border: 1px solid #D0D7E2;
    border-radius: 4px;
    background: #FAFBFC;
    font-family: "Consolas", "D2Coding", monospace;
    font-size: 12px;
}

/* ── Radio & Checkbox ── */
QRadioButton, QCheckBox {
    spacing: 6px;
    color: #374151;
}
"""


class MainWindow(QMainWindow):
    """Top-level window with tab navigation."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Marine P-Value Simulator v{__version__}")
        self.resize(1200, 800)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(_STYLESHEET)

        # Shared state
        self.df: pd.DataFrame | None = None
        self.interval_min: int = 60
        self.results_df: pd.DataFrame | None = None
        self.summary_df: pd.DataFrame | None = None

        self._build_menu()
        self._build_tabs()
        self._enforce_tab_access()
        self.statusBar().showMessage("Ready — Load data from CSV or KMA API in the Data tab")

    # ----- Menu bar -----

    def _build_menu(self):
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")
        act_exit = QAction("E&xit", self)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        help_menu = menu.addMenu("&Help")
        act_about = QAction("&About", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _show_about(self):
        QMessageBox.about(
            self,
            "About",
            f"<h3>Marine P-Value Simulator</h3>"
            f"<p>Version {__version__}</p>"
            f"<p>Monte Carlo simulation for offshore operations.</p>"
            f"<p>Analyse weather-dependent campaign feasibility<br>"
            f"using historical metocean data.</p>",
        )

    # ----- Tabs -----

    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.data_tab = DataTab(self)
        self.config_tab = ConfigTab(self)
        self.run_tab = RunTab(self)
        self.results_tab = ResultsTab(self)
        self.charts_tab = ChartsTab(self)
        self.optimal_tab = OptimalMonthTab(self)

        self.tabs.addTab(self.data_tab, "1. Data")
        self.tabs.addTab(self.config_tab, "2. Tasks & Config")
        self.tabs.addTab(self.run_tab, "3. Run")
        self.tabs.addTab(self.results_tab, "4. Results")
        self.tabs.addTab(self.charts_tab, "5. Charts")
        self.tabs.addTab(self.optimal_tab, "6. Optimal Month")

    # ----- Tab access enforcement -----

    def _enforce_tab_access(self):
        """Disable tabs that can't be used yet."""
        # Run tab needs data
        self.tabs.setTabEnabled(2, False)  # Run
        self.tabs.setTabEnabled(3, False)  # Results
        self.tabs.setTabEnabled(4, False)  # Charts
        self.tabs.setTabEnabled(5, False)  # Optimal Month

        self.tabs.setTabToolTip(2, "Load data first to enable this tab")
        self.tabs.setTabToolTip(3, "Run a simulation first to see results")
        self.tabs.setTabToolTip(4, "Run a simulation first to see charts")
        self.tabs.setTabToolTip(5, "Load data first to enable this tab")

    def unlock_after_data_loaded(self):
        """Called by DataTab after successful data load."""
        self.tabs.setTabEnabled(2, True)   # Run
        self.tabs.setTabEnabled(5, True)   # Optimal Month
        self.tabs.setTabToolTip(2, "")
        self.tabs.setTabToolTip(5, "")

    def unlock_after_simulation(self):
        """Called by RunTab after simulation completes."""
        self.tabs.setTabEnabled(3, True)   # Results
        self.tabs.setTabEnabled(4, True)   # Charts
        self.tabs.setTabToolTip(3, "")
        self.tabs.setTabToolTip(4, "")
