#!/usr/bin/env bash
# Build llama-rpc-server as a static library for iOS (arm64).
# Output: mobile/ios/Frameworks/llama_rpc.a + llama_rpc.h
set -euo pipefail

LLAMA_DIR="${LLAMA_DIR:-/opt/llama.cpp}"
IOS_MIN="${IOS_MIN:-16.0}"
OUT_DIR="$(dirname "$0")/../ios/Frameworks"

echo "[build-ios] Building for iOS arm64 (min $IOS_MIN)"

if [ ! -d "$LLAMA_DIR/.git" ]; then
  git clone --depth 1 https://github.com/ggerganov/llama.cpp "$LLAMA_DIR"
else
  git -C "$LLAMA_DIR" pull --ff-only
fi

cmake -B "$LLAMA_DIR/build-ios" "$LLAMA_DIR" \
  -DCMAKE_SYSTEM_NAME=iOS \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET="$IOS_MIN" \
  -DLLAMA_RPC=ON \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF \
  -DGGML_METAL=ON

cmake --build "$LLAMA_DIR/build-ios" \
  --config Release \
  -j"$(nproc 2>/dev/null || sysctl -n hw.logicalcpu)"

mkdir -p "$OUT_DIR"

# Combine relevant static libs into one for easy linking
libtool -static -o "$OUT_DIR/llama_rpc.a" \
  "$LLAMA_DIR/build-ios/src/libllama.a" \
  "$LLAMA_DIR/build-ios/ggml/src/libggml.a" \
  "$LLAMA_DIR/build-ios/ggml/src/ggml-metal/libggml-metal.a" \
  2>/dev/null || true

# Copy header
cp "$LLAMA_DIR/include/llama.h" "$OUT_DIR/" 2>/dev/null || true

echo "[build-ios] Done: $OUT_DIR/llama_rpc.a"
echo "[build-ios] Add to Xcode: Build Phases → Link Binary with Libraries"
