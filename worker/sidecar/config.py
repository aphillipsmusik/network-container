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
