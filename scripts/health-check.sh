#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# health-check.sh  –  Check the health of the entire cluster
#
# Usage:
#   ./scripts/health-check.sh [orchestrator-ip] [mgmt-port]
#
# Examples:
#   ./scripts/health-check.sh                    # localhost
#   ./scripts/health-check.sh 192.168.1.50
#   ./scripts/health-check.sh 192.168.1.50 8888
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ORCH_IP="${1:-localhost}"
MGMT_PORT="${2:-8888}"
BASE_URL="http://$ORCH_IP:$MGMT_PORT"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; }
info() { echo -e "  ${CYAN}→${NC} $*"; }
warn() { echo -e "  ${YELLOW}!${NC} $*"; }

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║     LLM Cluster Health Check                     ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "  Orchestrator: $BASE_URL"
echo ""

# ── Orchestrator health ───────────────────────────────────────────────────────
echo "── Orchestrator ─────────────────────────────────────"
ORCH_HEALTH=$(curl -sf --max-time 5 "$BASE_URL/health" 2>/dev/null || echo "ERROR")
if [ "$ORCH_HEALTH" = "ERROR" ]; then
    fail "Orchestrator unreachable at $BASE_URL"
    echo ""
    echo "  Is the orchestrator running? Start it with:"
    echo "    cd orchestrator && docker compose up -d"
    exit 1
fi

STATUS=$(echo "$ORCH_HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "?")
UPTIME=$(echo "$ORCH_HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('uptime_s','?'))" 2>/dev/null || echo "?")
MODEL=$(echo "$ORCH_HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('model_path','(none)'))" 2>/dev/null || echo "?")
INF_RUNNING=$(echo "$ORCH_HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('inference_server_running','?'))" 2>/dev/null || echo "?")
ACTIVE_WORKERS=$(echo "$ORCH_HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('active_workers','?'))" 2>/dev/null || echo "?")

[ "$STATUS" = "ok" ] && ok "Status: $STATUS" || fail "Status: $STATUS"
info "Uptime: ${UPTIME}s"
info "Model: $MODEL"
info "Inference server running: $INF_RUNNING"
info "Active workers: $ACTIVE_WORKERS"
echo ""

# ── Worker nodes ──────────────────────────────────────────────────────────────
echo "── Workers ──────────────────────────────────────────"
WORKERS=$(curl -sf --max-time 5 "$BASE_URL/workers/active" 2>/dev/null || echo "ERROR")
if [ "$WORKERS" = "ERROR" ]; then
    warn "Could not fetch worker list"
else
    WORKER_COUNT=$(echo "$WORKERS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('workers',[])))" 2>/dev/null || echo "0")
    if [ "$WORKER_COUNT" -eq 0 ]; then
        warn "No active workers found"
        info "Start worker nodes on other machines:"
        info "  cd worker && docker compose up -d"
    else
        ok "$WORKER_COUNT active worker(s):"
        echo "$WORKERS" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for w in d.get('workers', []):
    print(f\"     • {w['name']} @ {w['rpc_endpoint']}  RAM:{w['properties'].get('ram_gb','?')}GB\")
" 2>/dev/null || true
    fi
fi
echo ""

# ── Inference server ──────────────────────────────────────────────────────────
echo "── Inference Server (llama-server) ──────────────────"
INF_PORT="${INF_PORT:-8080}"
INF_HEALTH=$(curl -sf --max-time 5 "http://$ORCH_IP:$INF_PORT/health" 2>/dev/null || echo "ERROR")
if [ "$INF_HEALTH" = "ERROR" ]; then
    if [ -z "$(curl -sf "$BASE_URL/health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('model_path',''))" 2>/dev/null)" ]; then
        warn "Inference server not running (MODEL_PATH not set)"
    else
        fail "Inference server unreachable at http://$ORCH_IP:$INF_PORT"
    fi
else
    ok "Inference server healthy at http://$ORCH_IP:$INF_PORT"
    info "OpenAI-compatible API:"
    info "  POST http://$ORCH_IP:$INF_PORT/v1/chat/completions"
    info "  GET  http://$ORCH_IP:$INF_PORT/v1/models"
fi
echo ""

echo "── Quick Test ───────────────────────────────────────"
info "Test inference with:"
echo "     curl http://$ORCH_IP:$INF_PORT/v1/chat/completions \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"model\":\"local\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello!\"}]}'"
echo ""
