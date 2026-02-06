"""Reusable Qt widgets: chart canvas, task table, etc."""

from __future__ import annotations

from typing import List

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Matplotlib canvas widget
# ---------------------------------------------------------------------------

class ChartWidget(QWidget):
    """Embeddable matplotlib chart with navigation toolbar."""

    def __init__(self, parent=None, figsize=(10, 6)):
        super().__init__(parent)
        self.figure = Figure(figsize=figsize, tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    def clear(self):
        self.figure.clear()
        self.canvas.draw()

    def refresh(self):
        self.canvas.draw()


# ---------------------------------------------------------------------------
# Summary metrics table
# ---------------------------------------------------------------------------

class SummaryTable(QTableWidget):
    """Formatted percentile summary table."""

    _COLORS = {
        "P50": "#2166AC",
        "P75": "#F28E2B",
        "P90": "#E15759",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(["Metric", "Value (days)"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)

    def load_summary(self, summary_df):
        self.setRowCount(len(summary_df))
        for i, (_, row) in enumerate(summary_df.iterrows()):
            metric = str(row["Metric"])
            value = f'{row["Value_days"]:.2f}'

            m_item = QTableWidgetItem(metric)
            v_item = QTableWidgetItem(value)
            v_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            if metric in self._COLORS:
                from PyQt6.QtGui import QColor

                color = QColor(self._COLORS[metric])
                m_item.setForeground(color)
                v_item.setForeground(color)
                font = m_item.font()
                font.setBold(True)
                m_item.setFont(font)
                v_item.setFont(font)

            self.setItem(i, 0, m_item)
            self.setItem(i, 1, v_item)


# ---------------------------------------------------------------------------
# Task editor table
# ---------------------------------------------------------------------------

class TaskTable(QTableWidget):
    """Editable table for defining simulation tasks."""

    _HEADERS = ["Name", "Duration (h)", "Hs limit (m)", "Wind limit (m/s)", "Setup (h)", "Teardown (h)"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(self._HEADERS))
        self.setHorizontalHeaderLabels(self._HEADERS)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setAlternatingRowColors(True)
        self.add_default_row()

    def add_default_row(self):
        row = self.rowCount()
        self.insertRow(row)
        defaults = ["Task 1", "24", "1.5", "10.0", "0", "0"]
        for col, val in enumerate(defaults):
            item = QTableWidgetItem(val)
            if col > 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(row, col, item)

    def add_row(self):
        row = self.rowCount()
        self.insertRow(row)
        defaults = [f"Task {row + 1}", "24", "1.5", "10.0", "0", "0"]
        for col, val in enumerate(defaults):
            item = QTableWidgetItem(val)
            if col > 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(row, col, item)

    def remove_selected(self):
        rows = sorted(set(idx.row() for idx in self.selectedIndexes()), reverse=True)
        for r in rows:
            self.removeRow(r)

    def get_tasks(self) -> list:
        """Return list of Task-compatible dicts."""
        from pvalue.models import Task

        tasks = []
        errors = []
        for row in range(self.rowCount()):
            try:
                name = self.item(row, 0).text().strip()
                duration = int(self.item(row, 1).text())
                hs = float(self.item(row, 2).text())
                wind = float(self.item(row, 3).text())
                setup = int(self.item(row, 4).text())
                teardown = int(self.item(row, 5).text())
                tasks.append(
                    Task(
                        name=name,
                        duration_h=duration,
                        thresholds={"Hs": hs, "Wind": wind},
                        setup_h=setup,
                        teardown_h=teardown,
                    )
                )
            except (ValueError, AttributeError) as exc:
                errors.append(f"Row {row + 1}: {exc}")
        if errors and not tasks:
            raise ValueError("No valid tasks: " + "; ".join(errors))
        return tasks

    def load_tasks(self, tasks: List[dict]):
        """Populate table from a list of task dicts."""
        self.setRowCount(0)
        for t in tasks:
            row = self.rowCount()
            self.insertRow(row)
            thr = t.get("thresholds", {})
            values = [
                t.get("name", ""),
                str(t.get("duration_h", 24)),
                str(thr.get("Hs", 1.5)),
                str(thr.get("Wind", 10.0)),
                str(t.get("setup_h", 0)),
                str(t.get("teardown_h", 0)),
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.setItem(row, col, item)
