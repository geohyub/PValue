# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['pvalue\\desktop.py'],
    pathex=[],
    binaries=[],
    datas=[('examples', 'examples')],
    hiddenimports=['pvalue', 'pvalue.gui', 'pvalue.gui.main_window', 'pvalue.gui.tabs', 'pvalue.gui.widgets', 'pvalue.gui.workers', 'pvalue.models', 'pvalue.data', 'pvalue.simulation', 'pvalue.visualization', 'pvalue.reporting', 'pvalue.analysis', 'matplotlib.backends.backend_qtagg', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'openpyxl'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['streamlit', 'plotly', 'tkinter', 'tensorflow', 'torch', 'keras', 'scipy.spatial.cKDTree', 'IPython', 'jupyter', 'notebook', 'pytest', 'sphinx', 'docutils', 'PIL.ImageTk', 'cv2', 'sklearn', 'sqlalchemy', 'flask', 'django', 'boto3', 'botocore', 'setuptools', 'pkg_resources', '_pydevd_bundle', 'pydevd', 'debugpy'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
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
