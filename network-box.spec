# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules


hiddenimports = []
for package in ("ui", "core", "netmiko", "pysnmp"):
    hiddenimports += collect_submodules(package)


a = Analysis(
    ["scripts\\gui_app.py"],
    pathex=["."],
    binaries=[],
    datas=[("config", "config")],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtNetwork",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtSvg",
        "PySide6.QtWebEngine",
        "PySide6.QtWebChannel",
        "PySide6.QtPositioning",
        "PySide6.QtBluetooth",
        "PySide6.QtSensors",
        "PySide6.QtMultimedia",
        "PySide6.QtXml",
        "PySide6.QtTest",
        "PySide6.QtHelp",
        "PySide6.QtDesigner",
    ],
    noarchive=False,
    optimize=0,
)
a.binaries = [
    entry
    for entry in a.binaries
    if not os.path.basename(entry[0]).lower().startswith("icu")
]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="交换机巡检工具v1.2.1",
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
)
