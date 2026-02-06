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
QMainWindow { background-color: #f5f5f5; }
QTabWidget::pane { border: 1px solid #ccc; background: white; }

QPushButton#primary {
    background-color: #0066cc; color: white;
    font-weight: bold; padding: 6px 18px; border-radius: 4px;
}
QPushButton#primary:hover { background-color: #0052a3; }
QPushButton#primary:disabled { background-color: #99c2e8; }

QGroupBox {
    font-weight: bold; border: 1px solid #ccc;
    border-radius: 5px; margin-top: 10px; padding-top: 14px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }

QProgressBar {
    border: 1px solid #ccc; border-radius: 4px; text-align: center;
}
QProgressBar::chunk { background-color: #0066cc; border-radius: 3px; }

QTableWidget { gridline-color: #e0e0e0; }
QHeaderView::section {
    background-color: #4472C4; color: white;
    font-weight: bold; padding: 4px; border: none;
}
"""


class MainWindow(QMainWindow):
    """Top-level window with tab navigation."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Marine P-Value Simulator v{__version__}")
        self.resize(1200, 800)
        self.setStyleSheet(_STYLESHEET)

        # Shared state
        self.df: pd.DataFrame | None = None
        self.interval_min: int = 60
        self.results_df: pd.DataFrame | None = None
        self.summary_df: pd.DataFrame | None = None

        self._build_menu()
        self._build_tabs()
        self.statusBar().showMessage("Ready")

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
