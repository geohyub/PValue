"""Helper script to build standalone .exe with PyInstaller.

Usage:
    python build_exe.py            # one-folder build (recommended)
    python build_exe.py --onefile  # single .exe (slower startup)

If the build hangs at "Looking for dynamic libraries", you likely have
heavy packages (tensorflow, torch, etc.) installed globally.
This script excludes known offenders. For best results, build inside
a clean virtual environment:

    python -m venv .build_venv
    .build_venv\\Scripts\\activate
    pip install -e ".[desktop,excel,build]"
    python build_exe.py
"""

import subprocess
import sys

# Packages to exclude — these are never used by PValueSimulator but
# PyInstaller will try to scan them if they're installed, causing
# massive build times or hangs.
_EXCLUDE = [
    "streamlit",
    "plotly",
    "tkinter",
    "tensorflow",
    "torch",
    "keras",
    "scipy.spatial.cKDTree",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "sphinx",
    "docutils",
    "PIL.ImageTk",
    "cv2",
    "sklearn",
    "sqlalchemy",
    "flask",
    "django",
    "boto3",
    "botocore",
    "setuptools",
    "pkg_resources",
    "_pydevd_bundle",
    "pydevd",
    "debugpy",
]


def main():
    onefile = "--onefile" in sys.argv

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "PValueSimulator",
        "--noconsole",
        "--add-data", "examples;examples",  # Windows uses ; as separator
        # --- hidden imports (required) ---
        "--hidden-import", "pvalue",
        "--hidden-import", "pvalue.gui",
        "--hidden-import", "pvalue.gui.main_window",
        "--hidden-import", "pvalue.gui.tabs",
        "--hidden-import", "pvalue.gui.widgets",
        "--hidden-import", "pvalue.gui.workers",
        "--hidden-import", "pvalue.models",
        "--hidden-import", "pvalue.data",
        "--hidden-import", "pvalue.simulation",
        "--hidden-import", "pvalue.visualization",
        "--hidden-import", "pvalue.reporting",
        "--hidden-import", "pvalue.analysis",
        "--hidden-import", "matplotlib.backends.backend_qtagg",
        "--hidden-import", "PyQt6.QtCore",
        "--hidden-import", "PyQt6.QtGui",
        "--hidden-import", "PyQt6.QtWidgets",
        "--hidden-import", "openpyxl",
    ]

    # Exclude heavy/unused packages
    for mod in _EXCLUDE:
        cmd += ["--exclude-module", mod]

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
