# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for LLM Cluster Windows app
# Build with: pyinstaller windows/build.spec

import os
from pathlib import Path

APP_DIR = Path("windows/app")

a = Analysis(
    [str(APP_DIR / "main.py")],
    pathex=[str(APP_DIR)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "zeroconf",
        "zeroconf._utils.ipaddress",
        "zeroconf._dns",
        "pystray._win32",
        "PIL._tkinter_finder",
        "winreg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "scipy", "pandas"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="LLMCluster",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # No console window – GUI only
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # Add icon.ico here if you have one
    uac_admin=True,         # Request admin elevation for firewall rules
    version=None,
)
