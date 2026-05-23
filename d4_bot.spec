# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for D4Bot standalone .exe
# Build command: pyinstaller --clean d4_bot.spec

import sys
from pathlib import Path

block_cipher = None

# Project root
PROJ_DIR = Path(SPECPATH)  # directory containing this .spec file

# Collect PyQt5 platform plugins (fixes silent crash)
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
datas = []

# Include PyQt5 data files (platforms/qwindows.dll etc.)
try:
    datas += collect_data_files('PyQt5')
except Exception:
    pass

# Collect all asset files
for data_dir in ['assets', 'config', 'record']:
    src_dir = PROJ_DIR / data_dir
    if src_dir.exists():
        datas.append((str(src_dir), data_dir))

# Collect all Python source
a = Analysis(
    [str(PROJ_DIR / 'src' / 'main.py')],
    pathex=[str(PROJ_DIR / 'src')],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # PyQt5
        'PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets',
        'PyQt5.sip', 'PyQt5.QtNetwork',
        # OpenCV
        'cv2', 'cv2.data',
        # Input
        'pynput', 'pynput.keyboard', 'pynput.mouse',
        'pydirectinput',
        'pyautogui',
        'pytweening',          # pyautogui dependency, silently crashes if missing
        'keyboard',
        'pywintypes', 'win32api', 'win32gui', 'win32con',
        'win32process', 'win32clipboard',
        # Data
        'numpy', 'numpy.core._methods', 'numpy.lib.format',
        'PIL', 'PIL.Image', 'PIL.ImageDraw',
        # Stdlib
        'yaml', 'logging', 'queue', 'threading', 'json',
        'signal', 'collections', 'functools', 'math',
        'random', 'time', 'os', 'sys', 'ctypes',
        # New modules
        'bot.inventory', 'bot.dungeon', 'bot.campaign', 'bot.calibrate', 'bot.calibration_loader',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure, a.zipped_data,
    cipher=block_cipher
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='D4Bot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJ_DIR / 'assets' / 'layout' / 'mmorpg_helper.ico'),
    uac_admin=False,         # Don't require admin
)
