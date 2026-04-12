# Mobile App (iOS & Android)

A Flutter app that turns any iPhone or Android phone into an LLM Cluster node
and gives it direct access to the model through the cluster.

---

## What it does

| Mode | Description |
|------|-------------|
| **Worker** | Phone contributes CPU/GPU compute via llama-rpc-server running as a foreground service |
| **Chat (cluster)** | Routes inference requests to the nearest full-node on the local WiFi network |
| **Chat (on-device)** | Falls back to a small local model (e.g. Phi-3 mini Q4) when no cluster is reachable |

Both modes can run simultaneously — the phone contributes compute to the pool
**and** makes use of the pool to run a larger model than it could run alone.

---

## Architecture

```
Phone (iOS or Android)
├── llama-rpc-server        ← contributes compute to cluster
│   └── ARM64 binary (Android: NDK / iOS: static lib via Metal)
├── Flutter app
│   ├── Worker screen       ← start/stop, status, peer list
│   ├── Chat screen         ← OpenAI-compatible chat UI
│   └── Services
│       ├── DiscoveryService  mDNS browse + register
│       ├── WorkerService     RPC server lifecycle + background service
│       └── InferenceService  routes to cluster or on-device
└── Background service
    ├── Android: Foreground Service (persistent notification)
    └── iOS:     UIBackgroundModes (app must be visible)
```

---

## Getting Started

### Prerequisites

```bash
# Flutter 3.22+
flutter --version

# For Android builds
export ANDROID_NDK_HOME=~/Android/Sdk/ndk/26.3.11579264

# For iOS builds (macOS only)
xcode-select --install
```

### 1. Build the native llama.cpp binaries

**Android (ARM64):**
```bash
chmod +x mobile/native/build_android.sh
./mobile/native/build_android.sh
```
Output: `mobile/android/app/src/main/jniLibs/arm64-v8a/libllama-rpc-server.so`

**iOS (macOS only):**
```bash
chmod +x mobile/native/build_ios.sh
./mobile/native/build_ios.sh
```
Output: `mobile/ios/Frameworks/llama_rpc.a`
Add to Xcode: Build Phases → Link Binary with Libraries

### 2. Install Flutter dependencies

```bash
cd mobile
flutter pub get
```

### 3. Run

```bash
# Android
flutter run -d android

# iOS (requires Mac + connected device or simulator)
flutter run -d ios
```

---

## Using the App

### Worker mode

1. Open the **Worker** tab
2. Set a node name (e.g. `android-pixel8`)
3. Tap **Start Worker**
4. The phone appears in any orchestrator's `/workers` list automatically

The worker keeps running in the background via:
- **Android**: A persistent foreground notification ("LLM Cluster Worker – active")
- **iOS**: Requires the app to stay in the foreground (screen on). For best results, plug in to power and keep the app open.

### Chat mode

1. Open the **Chat** tab
2. The app auto-discovers full-nodes on the network and connects to the best one
3. Tap **Switch** in the banner to manually choose a node or use on-device mode

---

## Platform Notes

### Android

- Minimum API level: 24 (Android 7.0)
- Worker process: Kotlin `RpcServerManager` executes the ARM64 binary
- Background: `FlutterBackgroundService` + Android Foreground Service
- mDNS: via `nsd` Flutter plugin (wraps Android `NsdManager`)
- GPU: llama.cpp uses Android's CPU NEON/SVE by default; OpenCL via `-DGGML_OPENCL=ON`

### iOS

- Minimum iOS version: 16.0
- Worker process: llama.cpp compiled as a static library, called via Swift FFI
- GPU: Metal acceleration enabled (`-DGGML_METAL=ON`)
- Background: UIBackgroundModes — the app must remain in the foreground
  to keep contributing compute. This is an iOS platform restriction.
- mDNS: via `nsd` Flutter plugin (wraps `NSNetServiceBrowser` / `NetService`)

---

## Governance Note

Mobile workers are full participants in the cluster under the same
[no-51% rule](../GOVERNANCE.md). A mobile worker's RAM counts toward
the cluster's total compute pool, and no single entity may contribute
more than 51% of total active RAM across all node types (desktop, server,
or mobile).

---

## On-Device Model

For offline / cellular use, the app can run inference locally using a small
quantized model. Recommended models that fit on phones:

| Model | Size | RAM needed | Quality |
|-------|------|-----------|---------|
| Phi-3 mini Q4_K_M | 2.2 GB | 3 GB | Good |
| Gemma 2B Q4_K_M   | 1.5 GB | 2.5 GB | Good |
| Llama 3.2 1B Q4   | 0.8 GB | 1.5 GB | Fast |

Download to the device via **Settings → Download Model** in the app, or
copy the GGUF file to the app's Documents folder.
