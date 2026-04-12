#!/usr/bin/env bash
# Build llama-server binary locally (outside Docker) for the orchestrator node.
set -euo pipefail

LLAMA_DIR="${LLAMA_DIR:-/opt/llama.cpp}"
BUILD_TYPE="${BUILD_TYPE:-Release}"
CUDA="${CUDA:-0}"

echo "[build] Cloning llama.cpp into $LLAMA_DIR"
if [ ! -d "$LLAMA_DIR/.git" ]; then
  git clone --depth 1 https://github.com/ggerganov/llama.cpp "$LLAMA_DIR"
else
  git -C "$LLAMA_DIR" pull --ff-only
fi

cd "$LLAMA_DIR"

CMAKE_ARGS="-DLLAMA_RPC=ON -DCMAKE_BUILD_TYPE=$BUILD_TYPE"
if [ "$CUDA" = "1" ]; then
  CMAKE_ARGS="$CMAKE_ARGS -DGGML_CUDA=ON"
  echo "[build] CUDA support enabled"
fi

cmake -B build $CMAKE_ARGS
cmake --build build --config "$BUILD_TYPE" --target llama-server -j"$(nproc)"

echo "[build] Binary: $LLAMA_DIR/build/bin/llama-server"
echo "[build] Done."
