#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# download-model.sh  –  Download a GGUF model from Hugging Face
#
# Usage:
#   ./scripts/download-model.sh [model-name] [quant] [output-dir]
#
# Examples:
#   ./scripts/download-model.sh llama3-8b Q4_K_M /models
#   ./scripts/download-model.sh llama3-70b Q5_K_M /models
#   ./scripts/download-model.sh mistral-7b Q4_K_M /models
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[download]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }

# Predefined model URLs (HuggingFace GGUF repos)
declare -A MODEL_URLS=(
    ["llama3-8b-Q4_K_M"]="https://huggingface.co/bartowski/Meta-Llama-3-8B-Instruct-GGUF/resolve/main/Meta-Llama-3-8B-Instruct-Q4_K_M.gguf"
    ["llama3-70b-Q4_K_M"]="https://huggingface.co/bartowski/Meta-Llama-3-70B-Instruct-GGUF/resolve/main/Meta-Llama-3-70B-Instruct-Q4_K_M.gguf"
    ["llama3-70b-Q5_K_M"]="https://huggingface.co/bartowski/Meta-Llama-3-70B-Instruct-GGUF/resolve/main/Meta-Llama-3-70B-Instruct-Q5_K_M.gguf"
    ["mistral-7b-Q4_K_M"]="https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
    ["phi3-mini-Q4_K_M"]="https://huggingface.co/bartowski/Phi-3-mini-4k-instruct-GGUF/resolve/main/Phi-3-mini-4k-instruct-Q4_K_M.gguf"
    ["qwen2-72b-Q4_K_M"]="https://huggingface.co/bartowski/Qwen2-72B-Instruct-GGUF/resolve/main/Qwen2-72B-Instruct-Q4_K_M.gguf"
)

MODEL="${1:-}"
QUANT="${2:-Q4_K_M}"
OUTPUT_DIR="${3:-/models}"

if [ -z "$MODEL" ]; then
    echo "Available models:"
    for key in "${!MODEL_URLS[@]}"; do
        echo "  $key"
    done
    echo ""
    echo "Usage: $0 <model-name> [quant] [output-dir]"
    echo "Example: $0 llama3-70b Q4_K_M /models"
    exit 0
fi

KEY="${MODEL}-${QUANT}"
URL="${MODEL_URLS[$KEY]:-}"

if [ -z "$URL" ]; then
    warn "Model '$KEY' not in predefined list."
    warn "You can provide a direct HuggingFace URL by setting HF_URL env var:"
    warn "  HF_URL=https://... $0 custom Q4_K_M /models"
    URL="${HF_URL:-}"
    [ -z "$URL" ] && { echo "No URL provided, exiting."; exit 1; }
fi

mkdir -p "$OUTPUT_DIR"
FILENAME=$(basename "$URL")
DEST="$OUTPUT_DIR/$FILENAME"

if [ -f "$DEST" ]; then
    log "Model already exists: $DEST"
    log "Delete it first if you want to re-download."
    exit 0
fi

log "Downloading $KEY…"
log "  URL: $URL"
log "  Dest: $DEST"
echo ""

# Prefer aria2c for parallel downloads, fall back to curl/wget
if command -v aria2c &>/dev/null; then
    aria2c -x 8 -s 8 --dir "$OUTPUT_DIR" --out "$FILENAME" "$URL"
elif command -v curl &>/dev/null; then
    curl -L --progress-bar -o "$DEST" "$URL"
elif command -v wget &>/dev/null; then
    wget --progress=bar -O "$DEST" "$URL"
else
    echo "Install curl, wget, or aria2c to download models."
    exit 1
fi

SIZE=$(du -sh "$DEST" | cut -f1)
log "Download complete: $DEST ($SIZE)"
log "Set MODEL_PATH=$DEST in your orchestrator .env"
