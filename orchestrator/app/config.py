"""Orchestrator configuration – loaded from environment variables."""
import os
import socket

MGMT_PORT: int = int(os.environ.get("MGMT_PORT", "8888"))
LLAMA_SERVER_PORT: int = int(os.environ.get("LLAMA_SERVER_PORT", "8080"))
MODEL_PATH: str = os.environ.get("MODEL_PATH", "")
GPU_LAYERS: int = int(os.environ.get("GPU_LAYERS", "0"))
CONTEXT_SIZE: int = int(os.environ.get("CONTEXT_SIZE", "4096"))
PARALLEL: int = int(os.environ.get("PARALLEL", "4"))
WORKER_STALE_TIMEOUT: int = int(os.environ.get("WORKER_STALE_TIMEOUT", "90"))
DISCOVERY_TIMEOUT: int = int(os.environ.get("DISCOVERY_TIMEOUT", "10"))
LLAMA_SERVER_BIN: str = os.environ.get("LLAMA_SERVER_BIN", "llama-server")
NODE_NAME: str = os.environ.get("NODE_NAME", f"orchestrator-{socket.gethostname()}")
