# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Marine P-Value Simulator
#
# Build command:
#   pip install pyinstaller
#   pyinstaller build.spec
#
# Output: dist/PValueSimulator/ (one-folder) or dist/PValueSimulator.exe (one-file)

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['pvalue/desktop.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('examples', 'examples'),
    ],
    hiddenimports=[
        'pvalue',
        'pvalue.models',
        'pvalue.data',
        'pvalue.simulation',
        'pvalue.visualization',
        'pvalue.reporting',
        'pvalue.analysis',
        'pvalue.gui',
        'pvalue.gui.main_window',
        'pvalue.gui.tabs',
        'pvalue.gui.widgets',
        'pvalue.gui.workers',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'matplotlib.backends.backend_qtagg',
        'numpy',
        'pandas',
        'openpyxl',
        'openpyxl.styles',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'streamlit',
        'plotly',
        'tkinter',
    ],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PValueSimulator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window — pure GUI
    icon=None,      # Add .ico path here for custom icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PValueSimulator',
)
