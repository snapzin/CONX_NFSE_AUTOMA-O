# -*- mode: python ; coding: utf-8 -*-
"""
Spec PyInstaller para NFSe Automacao (gui_app.py).
Usa Chrome do sistema (CHROME_CHANNEL=chrome) — nao bundeia browser.
config.py fica FORA do bundle para poder ser editado sem rebuild.
"""
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# ── Caminhos base ──────────────────────────────────────────────────────────────
SPEC_DIR = Path(SPECPATH)

# Localiza o playwright instalado no Python ativo
import playwright as _pw
PW_DIR = Path(_pw.__file__).parent

# ── Dados a incluir no bundle ──────────────────────────────────────────────────
datas = []
datas += collect_data_files("customtkinter")
datas += collect_data_files("tkcalendar")
datas += collect_data_files("babel")

# Driver do Playwright (node.exe + package/) — necessário para controle do Chrome
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
    # módulos do projeto (exceto config.py — fica externo)
    "cert_reader", "nfse_automacao", "dominio_importer",
    "ui_widgets", "ui_animations",
    "runtime_settings",
]

# ── Arquivos do projeto a incluir como dado ────────────────────────────────────
project_datas = [
    (str(SPEC_DIR / "runtime_settings.json"), "."),
]
# Inclui apenas se existir
for f in project_datas:
    if Path(f[0]).exists():
        datas.append(f)

# ── Análise ────────────────────────────────────────────────────────────────────
a = Analysis(
    [str(SPEC_DIR / "gui_app.py")],
    pathex=[str(SPEC_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # config fica externo ao bundle (copiado pelo build_exe.bat)
    excludes=[
        "config",
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
    console=False,           # sem janela de console
    icon=None,               # coloque o caminho de um .ico aqui se quiser
    version=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="NFSe_Automacao",
    contents_directory=".",
)
