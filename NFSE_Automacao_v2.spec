# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for a single GUI executable: dist/NFSE_Automacao_v2.exe.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = []
datas += collect_data_files("customtkinter")
datas += collect_data_files("tkcalendar")
datas += collect_data_files("babel")

hiddenimports = []
hiddenimports += collect_submodules("babel")
hiddenimports += ["PIL._tkinter_finder"]

a = Analysis(
    ["gui_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="NFSE_Automacao_v2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
