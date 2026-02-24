# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for CarrotSummary — standalone macOS .app bundle."""

import platform
from pathlib import Path

block_cipher = None

ROOT = Path(SPECPATH)
ASSETS_DIR = ROOT / "assets"
ENTRY_POINT = str(ROOT / "flowtrack" / "main.py")

IS_MACOS = platform.system() == "Darwin"

icon_file = str(ASSETS_DIR / "icon.icns") if IS_MACOS else str(ASSETS_DIR / "icon.ico")

hiddenimports = [
    "pystray",
    "pystray._darwin",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "flask",
    "flask.json",
    "jinja2",
    "markupsafe",
    "werkzeug",
    "werkzeug.serving",
    "werkzeug.debug",
    "itsdangerous",
    "click",
    "blinker",
    "email.mime.multipart",
    "email.mime.text",
    "email.mime.base",
    "sqlite3",
    "json",
    "smtplib",
]

datas = [
    (str(ASSETS_DIR), "assets"),
    (str(ROOT / "flowtrack" / "ui" / "templates"), "flowtrack/ui/templates"),
    (str(ROOT / "flowtrack" / "ui" / "static"), "flowtrack/ui/static"),
]

a = Analysis(
    [ENTRY_POINT],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "_tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CarrotSummary",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CarrotSummary",
)

if IS_MACOS:
    app = BUNDLE(
        coll,
        name="CarrotSummary.app",
        icon=icon_file,
        bundle_identifier="com.carrotsummary.app",
        info_plist={
            "CFBundleDisplayName": "CarrotSummary",
            "CFBundleShortVersionString": "2.0.0",
            "LSBackgroundOnly": False,
            "LSUIElement": True,
            "NSHighResolutionCapable": True,
            "NSAppleEventsUsageDescription": "CarrotSummary needs to detect which app is in the foreground.",
        },
    )
