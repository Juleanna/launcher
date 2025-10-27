# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

# Collect PyQt5 data/binaries/hidden imports in a portable way
pyqt5_datas, pyqt5_binaries, pyqt5_hidden = collect_all('PyQt5')

a = Analysis(
    ['Launcher.py'],
    pathex=[],
    binaries=pyqt5_binaries,
    datas=pyqt5_datas,
    hiddenimports=pyqt5_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['images\\logo.png'],
)
