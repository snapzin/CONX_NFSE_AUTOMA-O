# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['app_gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # stdlib
        'schedule',
        'email.mime.text',
        'email.mime.multipart',
        'smtplib',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        # requests
        'requests',
        'requests.adapters',
        'requests.packages',
        # flask
        'flask',
        'flask.templating',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.routing',
        'jinja2',
        'click',
        'itsdangerous',
        # selenium
        'selenium',
        'selenium.webdriver',
        'selenium.webdriver.chrome',
        'selenium.webdriver.chrome.options',
        'selenium.webdriver.chrome.service',
        'selenium.webdriver.common.by',
        'selenium.webdriver.support.ui',
        'selenium.webdriver.support.expected_conditions',
        # webdriver-manager
        'webdriver_manager',
        'webdriver_manager.chrome',
        # cryptography
        'cryptography',
        'cryptography.hazmat.primitives.hashes',
        'cryptography.hazmat.primitives.serialization',
        'cryptography.hazmat.primitives.serialization.pkcs12',
        # projeto
        'api_server',
        'cert_manager',
        'nfse_browser',
        'nfse_automacao',
        'runtime_settings',
        'scheduler',
        'config',
    ],
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
    name='NFSeAutomacao',
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
