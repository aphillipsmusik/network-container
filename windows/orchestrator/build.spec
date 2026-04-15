# PyInstaller spec – LLM Cluster Orchestrator (Windows)
# Run from windows/orchestrator/:
#   pyinstaller build.spec

import sys
from pathlib import Path

block_cipher = None
APP_DIR = Path("app")

a = Analysis(
    [str(APP_DIR / "main.py")],
    pathex=[str(APP_DIR)],
    binaries=[],
    datas=[],
    hiddenimports=[
        # zeroconf / ifaddr
        "zeroconf",
        "zeroconf._utils.ipaddress",
        "zeroconf._dns",
        "ifaddr",
        # pystray backends
        "pystray._win32",
        # Pillow
        "PIL._imaging",
        "PIL.Image",
        "PIL.ImageDraw",
        # tkinter (usually bundled, but be explicit)
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        # uvicorn / fastapi
        "uvicorn",
        "uvicorn.lifespan.on",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "fastapi",
        "httpx",
        # app modules
        "config",
        "discovery",
        "launcher",
        "gui",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="LLMClusterOrchestrator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # No console window
    uac_admin=True,         # Request elevation (for firewall rules)
    icon=None,              # Add icon path here if available
)
