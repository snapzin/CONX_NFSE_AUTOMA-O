# -*- mode: python ; coding: utf-8 -*-
"""
Spec PyInstaller para o backend FastAPI (api/server.py).
Gera dist/server/server.exe — executavel standalone, sem Python no sistema.
config.py fica FORA do bundle (copiado pelo build script ao lado do server.exe).
"""
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SPEC_DIR = Path(SPECPATH)          # .../nfse/api/
ROOT_DIR = SPEC_DIR.parent         # .../nfse/

import playwright as _pw
PW_DIR = Path(_pw.__file__).parent

# ── Dados ─────────────────────────────────────────────────────────────────────
datas = []
datas += collect_data_files("playwright")
datas += [(str(PW_DIR / "driver"), "playwright/driver")]

# ── Imports ocultos ────────────────────────────────────────────────────────────
hiddenimports = []
hiddenimports += collect_submodules("playwright")
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("fastapi")
hiddenimports += collect_submodules("starlette")
hiddenimports += collect_submodules("anyio")
hiddenimports += collect_submodules("babel")
hiddenimports += [
    "cryptography", "cryptography.hazmat.primitives",
    "cryptography.hazmat.backends.openssl",
    "cryptography.hazmat.primitives.serialization.pkcs12",
    "openpyxl", "openpyxl.styles", "openpyxl.utils",
    "h11", "h11._readers", "h11._writers",
    "email.mime.multipart", "email.mime.text",
    "nfse_automacao", "cert_reader", "dominio_importer", "config_defaults",
    "runtime_settings",
]

# ── Análise ────────────────────────────────────────────────────────────────────
a = Analysis(
    [str(SPEC_DIR / "server.py")],
    pathex=[str(ROOT_DIR)],        # projeto root → importa nfse_automacao, cert_reader, etc.
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "config",                  # fica externo, ao lado do server.exe
        "customtkinter", "tkcalendar", "PIL", "tkinter",
        "notebook", "IPython", "matplotlib", "selenium",
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
    name="server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # mostra console para log (main.js captura stdout)
    version=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="server",
    contents_directory=".",   # todos os arquivos na mesma pasta do server.exe
)
