"""Entry point for the PyQt6 desktop application.

Usage:
    python -m pvalue.desktop
    # or after pip install:
    pvalue-desktop
"""

import sys


def main():
    from PyQt6.QtWidgets import QApplication

    from pvalue.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Marine P-Value Simulator")
    app.setOrganizationName("PValue")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
