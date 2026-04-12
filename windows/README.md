# Windows Installer

A native Windows `.exe` installer that turns any Windows 10/11 PC into an
LLM cluster node with a setup wizard and system tray icon.

## What it does

1. **Setup wizard** — choose Worker or Orchestrator, configure your IP and
   GPU settings, browse for your model file
2. **Firewall rules** — opens the required ports automatically (requires Admin)
3. **System tray** — runs silently in the background; right-click for status,
   worker discovery, and restart
4. **Auto-start** — optional Windows startup entry
5. **mDNS discovery** — nodes find each other automatically, no IP config needed

---

## Download (Easiest)

The GitHub Actions workflow builds the installer automatically on every push
to `main`. Download `LLMCluster-Setup.exe` from the
[**Releases page**](https://github.com/aphillipsmusik/network-container/releases).

---

## Build It Yourself

You need a **Windows machine** (or the GitHub Actions workflow).

### Prerequisites

```powershell
# Python 3.11+
winget install Python.Python.3.11

# Inno Setup 6
winget install JRSoftware.InnoSetup

# Chocolatey (for CI) – or install Inno Setup manually above
```

### Steps

```powershell
# 1. Install Python deps
pip install -r windows/app/requirements.txt

# 2. Download llama.cpp Windows binaries
#    Get the latest release from https://github.com/ggerganov/llama.cpp/releases
#    Download llama-bXXXX-bin-win-avx2-x64.zip, extract *.exe and *.dll to dist/bin/

# 3. Build the .exe with PyInstaller
pyinstaller windows/build.spec --distpath dist

# 4. Build the installer with Inno Setup
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" windows\installer\setup.iss

# 5. The installer is at dist/LLMCluster-Setup.exe
```

### Automated build via GitHub Actions

Push to `main` (with changes in `windows/`) and the
[build-windows workflow](../.github/workflows/build-windows.yml) will:

1. Set up Python on a `windows-latest` runner
2. Download the latest llama.cpp binaries
3. Bundle everything with PyInstaller
4. Wrap it in an Inno Setup installer
5. Upload `LLMCluster-Setup.exe` as a release artifact and create a GitHub Release

---

## File Structure

```
windows/
├── app/
│   ├── main.py         entry point
│   ├── gui.py          tkinter wizard + system tray (pystray)
│   ├── node.py         llama-rpc-server / llama-server lifecycle + mDNS
│   ├── firewall.py     netsh firewall rule management
│   ├── config.py       JSON config in %APPDATA%\LLMCluster
│   └── requirements.txt
├── build.spec          PyInstaller spec
├── installer/
│   └── setup.iss       Inno Setup script
└── README.md           this file
```

---

## GPU Support

The default build uses CPU-only AVX2 binaries. For NVIDIA GPU support:

1. Download the CUDA variant from llama.cpp releases:
   `llama-bXXXX-bin-win-cuda-cu12.2.0-x64.zip`
2. Place the CUDA `.exe` and `.dll` files in `dist/bin/`
3. In the setup wizard, set **GPU layers** to `99` (offload all to GPU)

---

## Ports Used

| Port  | Protocol | Purpose                        |
|-------|----------|-------------------------------|
| 50052 | TCP      | RPC server (worker nodes)      |
| 8080  | TCP      | Inference API (orchestrator)   |
| 8888  | TCP      | Management API (orchestrator)  |
| 8765  | TCP      | Sidecar health API             |
| 5353  | UDP      | mDNS node discovery            |

All opened automatically during installation (requires Admin).
