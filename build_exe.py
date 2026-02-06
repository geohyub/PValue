"""Helper script to build standalone .exe with PyInstaller.

Usage:
    python build_exe.py            # one-folder build (recommended)
    python build_exe.py --onefile  # single .exe (slower startup)
"""

import subprocess
import sys


def main():
    onefile = "--onefile" in sys.argv

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "PValueSimulator",
        "--noconsole",
        "--add-data", "examples:examples",
        "--hidden-import", "pvalue",
        "--hidden-import", "pvalue.gui",
        "--hidden-import", "pvalue.gui.main_window",
        "--hidden-import", "pvalue.gui.tabs",
        "--hidden-import", "pvalue.gui.widgets",
        "--hidden-import", "pvalue.gui.workers",
        "--hidden-import", "matplotlib.backends.backend_qtagg",
        "--hidden-import", "PyQt6.QtCore",
        "--hidden-import", "PyQt6.QtGui",
        "--hidden-import", "PyQt6.QtWidgets",
        "--hidden-import", "pvalue.models",
        "--hidden-import", "pvalue.data",
        "--hidden-import", "pvalue.simulation",
        "--hidden-import", "pvalue.visualization",
        "--hidden-import", "pvalue.reporting",
        "--hidden-import", "pvalue.analysis",
        "--hidden-import", "openpyxl",
        "--exclude-module", "streamlit",
        "--exclude-module", "plotly",
        "--exclude-module", "tkinter",
    ]

    if onefile:
        cmd.append("--onefile")

    cmd.append("pvalue/desktop.py")

    print(f"Building {'one-file' if onefile else 'one-folder'} executable...")
    print(f"Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd)

    if result.returncode == 0:
        if onefile:
            print("\nBuild complete: dist/PValueSimulator.exe")
        else:
            print("\nBuild complete: dist/PValueSimulator/PValueSimulator.exe")
        print("You can distribute the dist/ folder to users.")
    else:
        print("\nBuild failed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
