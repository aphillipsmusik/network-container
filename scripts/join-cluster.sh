#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# join-cluster.sh  –  Interactive wizard to join an existing LLM cluster
#
# Usage:
#   chmod +x scripts/join-cluster.sh
#   ./scripts/join-cluster.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[join]${NC} $*"; }
info() { echo -e "${CYAN}       $*${NC}"; }
prompt() { echo -e "${YELLOW}▶ $*${NC}"; }

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║     LLM Cluster – Node Join Wizard               ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── Role selection ────────────────────────────────────────────────────────────
prompt "Select this node's role:"
echo "  1) Worker  – contributes RAM/GPU compute to the cluster"
echo "  2) Orchestrator – manages workers, hosts the model file, exposes the API"
read -rp "  Enter 1 or 2: " ROLE_NUM

case "$ROLE_NUM" in
  1) ROLE="worker" ;;
  2) ROLE="orchestrator" ;;
  *) echo "Invalid choice"; exit 1 ;;
esac
log "Role selected: $ROLE"

# ── Detect outbound IP ────────────────────────────────────────────────────────
DEFAULT_IP=$(python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(('8.8.8.8', 80))
print(s.getsockname()[0])
s.close()
" 2>/dev/null || hostname -I | awk '{print $1}')

# ── Common env vars ───────────────────────────────────────────────────────────
prompt "Node name (unique identifier for this machine):"
read -rp "  [default: $(hostname)]: " NODE_NAME
NODE_NAME="${NODE_NAME:-$(hostname)}"

if [ "$ROLE" = "worker" ]; then
    prompt "IP address other nodes should use to reach this machine:"
    read -rp "  [default: $DEFAULT_IP]: " ADVERTISE_IP
    ADVERTISE_IP="${ADVERTISE_IP:-$DEFAULT_IP}"

    prompt "RPC server port:"
    read -rp "  [default: 50052]: " RPC_PORT
    RPC_PORT="${RPC_PORT:-50052}"

    prompt "Orchestrator IP (for status reporting, optional):"
    read -rp "  [press Enter to skip]: " ORCHESTRATOR_HOST

    prompt "GPU layers to offload (0 = CPU only, 99 = all layers to GPU):"
    read -rp "  [default: 0]: " GPU_LAYERS
    GPU_LAYERS="${GPU_LAYERS:-0}"

    # Write .env into worker dir
    ENV_FILE="$REPO_ROOT/worker/.env"
    cat > "$ENV_FILE" <<EOF
NODE_NAME=$NODE_NAME
ADVERTISE_IP=$ADVERTISE_IP
RPC_PORT=$RPC_PORT
ORCHESTRATOR_HOST=$ORCHESTRATOR_HOST
ORCHESTRATOR_PORT=8888
GPU_LAYERS=$GPU_LAYERS
MODEL_DIR=/tmp/models
EOF

    log "Written: $ENV_FILE"

    # Detect GPU
    USE_GPU=""
    if [ "${GPU_LAYERS:-0}" -gt 0 ] && lspci 2>/dev/null | grep -qi nvidia; then
        USE_GPU="-f docker-compose.gpu.yml"
        log "NVIDIA GPU detected – using GPU compose override"
    fi

    log "Starting worker node…"
    cd "$REPO_ROOT/worker"
    docker compose $USE_GPU up -d --build

    echo ""
    info "Worker '$NODE_NAME' is running!"
    info "  RPC endpoint: $ADVERTISE_IP:$RPC_PORT"
    info "  Health:       http://$ADVERTISE_IP:8765/health"

else
    # Orchestrator
    prompt "Path to your GGUF model file:"
    read -rp "  e.g. /home/user/models/llama3-70b.Q4_K_M.gguf: " MODEL_PATH

    prompt "Context size (tokens):"
    read -rp "  [default: 4096]: " CONTEXT_SIZE
    CONTEXT_SIZE="${CONTEXT_SIZE:-4096}"

    prompt "Parallel inference slots:"
    read -rp "  [default: 4]: " PARALLEL
    PARALLEL="${PARALLEL:-4}"

    prompt "GPU layers (0 = CPU only):"
    read -rp "  [default: 0]: " GPU_LAYERS
    GPU_LAYERS="${GPU_LAYERS:-0}"

    MODEL_DIR=$(dirname "$MODEL_PATH")

    ENV_FILE="$REPO_ROOT/orchestrator/.env"
    cat > "$ENV_FILE" <<EOF
NODE_NAME=$NODE_NAME
MODEL_PATH=$MODEL_PATH
MODEL_DIR=$MODEL_DIR
CONTEXT_SIZE=$CONTEXT_SIZE
PARALLEL=$PARALLEL
GPU_LAYERS=$GPU_LAYERS
MGMT_PORT=8888
LLAMA_SERVER_PORT=8080
WORKER_STALE_TIMEOUT=90
DISCOVERY_TIMEOUT=15
EOF

    log "Written: $ENV_FILE"

    USE_GPU=""
    if [ "${GPU_LAYERS:-0}" -gt 0 ] && lspci 2>/dev/null | grep -qi nvidia; then
        USE_GPU="-f docker-compose.gpu.yml"
        log "NVIDIA GPU detected – using GPU compose override"
    fi

    log "Starting orchestrator node…"
    cd "$REPO_ROOT/orchestrator"
    docker compose $USE_GPU up -d --build

    echo ""
    info "Orchestrator '$NODE_NAME' is running!"
    info "  Management API: http://$DEFAULT_IP:8888"
    info "  Inference API:  http://$DEFAULT_IP:8080 (OpenAI-compatible)"
    info "  Workers:        http://$DEFAULT_IP:8888/workers"
fi
