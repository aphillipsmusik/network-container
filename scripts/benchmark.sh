#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# benchmark.sh  –  Measure tokens/sec and inter-node latency
#
# Usage:
#   ./scripts/benchmark.sh [orchestrator-ip] [inference-port]
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ORCH_IP="${1:-localhost}"
INF_PORT="${2:-8080}"
API_BASE="http://$ORCH_IP:$INF_PORT"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[bench]${NC} $*"; }
info() { echo -e "${CYAN}       $*${NC}"; }

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║     LLM Cluster Benchmark                        ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
log "Target: $API_BASE"
echo ""

# ── Connectivity check ────────────────────────────────────────────────────────
log "Checking server health…"
if ! curl -sf --max-time 5 "$API_BASE/health" > /dev/null; then
    echo "  Inference server not reachable. Is it running?"
    exit 1
fi
echo "  Server is up"
echo ""

# ── Token generation benchmark ────────────────────────────────────────────────
PROMPT="Write a detailed technical explanation of how transformer neural networks process tokens in parallel, including attention mechanisms, positional encodings, and layer normalization. Be thorough."
MAX_TOKENS=256

log "Running token generation benchmark (${MAX_TOKENS} tokens)…"
START=$(date +%s%3N)

RESPONSE=$(curl -sf --max-time 120 "$API_BASE/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d "{
        \"model\": \"local\",
        \"messages\": [{\"role\": \"user\", \"content\": \"$PROMPT\"}],
        \"max_tokens\": $MAX_TOKENS,
        \"stream\": false
    }" 2>/dev/null || echo "ERROR")

END=$(date +%s%3N)
ELAPSED_MS=$((END - START))

if [ "$RESPONSE" = "ERROR" ]; then
    echo "  Benchmark request failed – is a model loaded?"
    exit 1
fi

# Parse response
COMPLETION_TOKENS=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d['usage']['completion_tokens'])
except:
    print(0)
" 2>/dev/null || echo "0")

PROMPT_TOKENS=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d['usage']['prompt_tokens'])
except:
    print(0)
" 2>/dev/null || echo "0")

ELAPSED_S=$(echo "scale=2; $ELAPSED_MS / 1000" | bc)
if [ "$COMPLETION_TOKENS" -gt 0 ]; then
    TOKS_PER_SEC=$(echo "scale=1; $COMPLETION_TOKENS / $ELAPSED_S" | bc)
else
    TOKS_PER_SEC="N/A"
fi

echo ""
log "Results:"
info "  Prompt tokens:     $PROMPT_TOKENS"
info "  Completion tokens: $COMPLETION_TOKENS"
info "  Total time:        ${ELAPSED_S}s"
info "  Throughput:        ${TOKS_PER_SEC} tokens/sec"
echo ""

# ── Reference points ──────────────────────────────────────────────────────────
log "Reference throughput benchmarks:"
echo "  ┌─────────────────────────────────────┬──────────────┐"
echo "  │ Setup                               │  tokens/sec  │"
echo "  ├─────────────────────────────────────┼──────────────┤"
echo "  │ Single A100 80GB (70B Q4)           │    50-100    │"
echo "  │ 4× RTX 4090 wired GbE (70B Q4)     │    20-40     │"
echo "  │ 4× CPU nodes wired GbE (70B Q4)    │     5-15     │"
echo "  │ 4× nodes over WiFi 6 (70B Q4)      │     1-8      │"
echo "  │ Petals / internet distributed       │     1-3      │"
echo "  └─────────────────────────────────────┴──────────────┘"
echo ""

# ── Concurrency test ──────────────────────────────────────────────────────────
log "Running concurrency test (4 parallel requests)…"
CONCURRENT=4
PIDS=()
TMPDIR_BM=$(mktemp -d)

for i in $(seq 1 $CONCURRENT); do
    (
        T_START=$(date +%s%3N)
        R=$(curl -sf --max-time 30 "$API_BASE/v1/chat/completions" \
            -H "Content-Type: application/json" \
            -d '{"model":"local","messages":[{"role":"user","content":"Count from 1 to 20."}],"max_tokens":64}' \
            2>/dev/null || echo "ERROR")
        T_END=$(date +%s%3N)
        T_MS=$((T_END - T_START))
        echo "$T_MS" > "$TMPDIR_BM/req_$i"
    ) &
    PIDS+=($!)
done

for pid in "${PIDS[@]}"; do wait "$pid"; done

TOTAL_MS=0
COUNT=0
for f in "$TMPDIR_BM"/req_*; do
    MS=$(cat "$f")
    TOTAL_MS=$((TOTAL_MS + MS))
    COUNT=$((COUNT + 1))
done
rm -rf "$TMPDIR_BM"

if [ "$COUNT" -gt 0 ]; then
    AVG_MS=$((TOTAL_MS / COUNT))
    info "  $CONCURRENT parallel requests avg latency: ${AVG_MS}ms"
fi
echo ""
log "Benchmark complete."
