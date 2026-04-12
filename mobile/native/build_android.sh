#!/usr/bin/env bash
# Build llama-rpc-server for Android ARM64 using the NDK.
# Output: mobile/android/app/src/main/jniLibs/arm64-v8a/libllama-rpc-server.so
set -euo pipefail

LLAMA_DIR="${LLAMA_DIR:-/opt/llama.cpp}"
NDK="${ANDROID_NDK_HOME:-$HOME/Android/Sdk/ndk/26.3.11579264}"
API_LEVEL="${API_LEVEL:-24}"    # Android 7.0 minimum
ABI="${ABI:-arm64-v8a}"
OUT_DIR="$(dirname "$0")/../android/app/src/main/jniLibs/$ABI"

echo "[build-android] NDK: $NDK"
echo "[build-android] API: $API_LEVEL"
echo "[build-android] ABI: $ABI"

# Clone / update llama.cpp
if [ ! -d "$LLAMA_DIR/.git" ]; then
  git clone --depth 1 https://github.com/ggerganov/llama.cpp "$LLAMA_DIR"
else
  git -C "$LLAMA_DIR" pull --ff-only
fi

TOOLCHAIN="$NDK/build/cmake/android.toolchain.cmake"

cmake -B "$LLAMA_DIR/build-android-$ABI" "$LLAMA_DIR" \
  -DCMAKE_TOOLCHAIN_FILE="$TOOLCHAIN" \
  -DANDROID_ABI="$ABI" \
  -DANDROID_PLATFORM="android-$API_LEVEL" \
  -DLLAMA_RPC=ON \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON

cmake --build "$LLAMA_DIR/build-android-$ABI" \
  --config Release \
  --target llama-rpc-server \
  -j"$(nproc)"

mkdir -p "$OUT_DIR"
# Rename to .so so Android package manager extracts it to nativeLibraryDir
cp "$LLAMA_DIR/build-android-$ABI/bin/llama-rpc-server" \
   "$OUT_DIR/libllama-rpc-server.so"

echo "[build-android] Done: $OUT_DIR/libllama-rpc-server.so"
