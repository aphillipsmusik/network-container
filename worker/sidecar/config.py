"""Worker sidecar configuration – loaded from environment variables."""
import os
import socket


def _default_ip() -> str:
    """Best-effort: get the outbound IP of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


RPC_PORT: int = int(os.environ.get("RPC_PORT", "50052"))
SIDECAR_PORT: int = int(os.environ.get("SIDECAR_PORT", "8765"))
ADVERTISE_IP: str = os.environ.get("ADVERTISE_IP", "") or _default_ip()
NODE_NAME: str = os.environ.get("NODE_NAME", "") or f"worker-{socket.gethostname()}"
GPU_LAYERS: int = int(os.environ.get("GPU_LAYERS", "0"))
ORCHESTRATOR_HOST: str = os.environ.get("ORCHESTRATOR_HOST", "")
ORCHESTRATOR_PORT: int = int(os.environ.get("ORCHESTRATOR_PORT", "8888"))
HEARTBEAT_INTERVAL: int = int(os.environ.get("HEARTBEAT_INTERVAL", "60"))
LLAMA_RPC_BIN: str = os.environ.get("LLAMA_RPC_BIN", "llama-rpc-server")

# ── Full-node / inference settings ────────────────────────────────────────────
# Set ENABLE_INFERENCE=true to also run llama-server on this worker node,
# giving it direct access to the model via the full cluster as RPC backends.
ENABLE_INFERENCE: bool = os.environ.get("ENABLE_INFERENCE", "false").lower() == "true"
MODEL_PATH: str = os.environ.get("MODEL_PATH", "")
LLAMA_SERVER_PORT: int = int(os.environ.get("LLAMA_SERVER_PORT", "8080"))
CONTEXT_SIZE: int = int(os.environ.get("CONTEXT_SIZE", "4096"))
PARALLEL: int = int(os.environ.get("PARALLEL", "4"))
LLAMA_SERVER_BIN: str = os.environ.get("LLAMA_SERVER_BIN", "llama-server")
