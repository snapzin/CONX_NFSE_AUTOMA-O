# -*- mode: python ; coding: utf-8 -*-
"""
Spec PyInstaller para NFSe Automacao - macOS (.app bundle)
Uso: pyinstaller --noconfirm NFSE_Automacao_mac.spec
Gera: dist/NFSe_Automacao.app
"""
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SPEC_DIR = Path(SPECPATH)

import playwright as _pw
PW_DIR = Path(_pw.__file__).parent

# ── Dados ──────────────────────────────────────────────────────────────────────
datas = []
datas += collect_data_files("customtkinter")
datas += collect_data_files("tkcalendar")
datas += collect_data_files("babel")

# Driver Playwright (node + package/) — necessario para controlar Chrome
datas += [(str(PW_DIR / "driver"), "playwright/driver")]

# ── Imports ocultos ────────────────────────────────────────────────────────────
hiddenimports = []
hiddenimports += collect_submodules("babel")
hiddenimports += collect_submodules("playwright")
hiddenimports += [
    "tkinter", "tkinter.ttk", "tkinter.messagebox", "tkinter.filedialog",
    "customtkinter", "tkcalendar",
    "PIL._tkinter_finder",
    "cryptography", "cryptography.hazmat.primitives",
    "cryptography.hazmat.backends.openssl",
    "openpyxl", "openpyxl.styles", "openpyxl.utils",
    "cert_reader", "nfse_automacao", "dominio_importer",
    "ui_widgets", "ui_animations",
    "runtime_settings",
]

# ── Arquivos do projeto ────────────────────────────────────────────────────────
project_datas = [
    (str(SPEC_DIR / "runtime_settings.json"), "."),
]
for f in project_datas:
    if Path(f[0]).exists():
        datas.append(f)

# ── Analise ────────────────────────────────────────────────────────────────────
a = Analysis(
    [str(SPEC_DIR / "gui_app.py")],
    pathex=[str(SPEC_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "config",
        "pygetwindow",          # Windows-only, nao necessario no mac
        "winreg",               # Windows-only
        "flask", "fastapi", "uvicorn", "selenium",
        "notebook", "IPython", "matplotlib",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NFSe_Automacao",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="NFSe_Automacao",
    contents_directory=".",
)

# Bundle macOS (.app)
app = BUNDLE(
    coll,
    name="NFSe_Automacao.app",
    icon=None,                  # coloque "icone.icns" aqui se tiver
    bundle_identifier="br.com.conx.nfse-automacao",
    info_plist={
        "CFBundleName": "NFSe Automacao",
        "CFBundleDisplayName": "NFSe Automacao",
        "CFBundleVersion": "2.4",
        "CFBundleShortVersionString": "2.4",
        "NSHighResolutionCapable": True,
        # Accessibility necessaria para pyautogui funcionar no mac
        "NSAppleEventsUsageDescription": "Necessario para automacao do Chrome.",
        "NSAccessibilityUsageDescription": "Necessario para clicar em elementos do Chrome.",
    },
)
