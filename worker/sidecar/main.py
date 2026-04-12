"""
Worker Sidecar
==============
Responsibilities:
  1. Start and supervise the llama-rpc-server process.
  2. Advertise this node on the local network via mDNS (_llama-rpc._tcp.local).
  3. Re-broadcast the mDNS record every HEARTBEAT_INTERVAL seconds.
  4. Expose a tiny REST API so the orchestrator can query status.
  5. Gracefully deregister on shutdown (SIGTERM / SIGINT).
"""
import asyncio
import logging
import signal
import socket
import subprocess
import sys
import time
from contextlib import asynccontextmanager

import psutil
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from zeroconf import ServiceInfo, Zeroconf
from zeroconf.asyncio import AsyncZeroconf

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(message)s")
log = logging.getLogger(__name__)

# ── Global state ──────────────────────────────────────────────────────────────
_rpc_proc: subprocess.Popen | None = None
_zeroconf: AsyncZeroconf | None = None
_service_info: ServiceInfo | None = None
_start_time: float = time.time()


# ── Resource helpers ──────────────────────────────────────────────────────────

def _ram_gb() -> float:
    return round(psutil.virtual_memory().total / (1024 ** 3), 1)


def _disk_gb() -> float:
    return round(psutil.disk_usage("/").free / (1024 ** 3), 1)


def _gpu_info() -> dict:
    """Return basic GPU info if nvidia-smi is available."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            timeout=3, stderr=subprocess.DEVNULL
        ).decode().strip()
        parts = out.split(",")
        return {"name": parts[0].strip(), "vram_mb": int(parts[1].strip())}
    except Exception:
        return {}


# ── mDNS advertisement ────────────────────────────────────────────────────────

def _build_service_info() -> ServiceInfo:
    gpu = _gpu_info()
    props = {
        "node_name": config.NODE_NAME,
        "rpc_port": str(config.RPC_PORT),
        "ram_gb": str(_ram_gb()),
        "disk_free_gb": str(_disk_gb()),
        "gpu_layers": str(config.GPU_LAYERS),
    }
    if gpu:
        props["gpu_name"] = gpu["name"]
        props["gpu_vram_mb"] = str(gpu["vram_mb"])

    return ServiceInfo(
        type_="_llama-rpc._tcp.local.",
        name=f"{config.NODE_NAME}._llama-rpc._tcp.local.",
        addresses=[socket.inet_aton(config.ADVERTISE_IP)],
        port=config.RPC_PORT,
        properties={k: v.encode() for k, v in props.items()},
        server=f"{socket.gethostname()}.local.",
    )


async def _heartbeat_loop(zc: AsyncZeroconf, info: ServiceInfo) -> None:
    """Re-register every HEARTBEAT_INTERVAL seconds to signal liveness."""
    while True:
        await asyncio.sleep(config.HEARTBEAT_INTERVAL)
        try:
            await zc.async_update_service(info)
            log.info("mDNS heartbeat sent")
        except Exception as exc:
            log.warning("mDNS heartbeat failed: %s", exc)


# ── llama-rpc-server subprocess ───────────────────────────────────────────────

def _start_rpc_server() -> subprocess.Popen:
    cmd = [
        config.LLAMA_RPC_BIN,
        "--host", "0.0.0.0",
        "--port", str(config.RPC_PORT),
    ]
    log.info("Starting RPC server: %s", " ".join(cmd))
    proc = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)
    return proc


def _stop_rpc_server(proc: subprocess.Popen) -> None:
    if proc and proc.poll() is None:
        log.info("Stopping RPC server (pid %d)", proc.pid)
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


# ── FastAPI app ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _rpc_proc, _zeroconf, _service_info

    # 1. Start RPC server
    _rpc_proc = _start_rpc_server()
    await asyncio.sleep(1)  # give it a moment to bind

    # 2. Register with mDNS
    _service_info = _build_service_info()
    _zeroconf = AsyncZeroconf()
    await _zeroconf.async_register_service(_service_info)
    log.info("Registered as '%s' on %s:%d", config.NODE_NAME,
             config.ADVERTISE_IP, config.RPC_PORT)

    # 3. Start heartbeat
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(_zeroconf, _service_info)
    )

    yield  # ── app is running ──

    # 4. Shutdown
    heartbeat_task.cancel()
    await _zeroconf.async_unregister_service(_service_info)
    await _zeroconf.async_close()
    _stop_rpc_server(_rpc_proc)
    log.info("Worker sidecar shut down cleanly")


app = FastAPI(title="LLM Cluster Worker", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    alive = _rpc_proc is not None and _rpc_proc.poll() is None
    return JSONResponse({
        "status": "ok" if alive else "rpc_down",
        "node_name": config.NODE_NAME,
        "advertise_ip": config.ADVERTISE_IP,
        "rpc_port": config.RPC_PORT,
        "uptime_s": round(time.time() - _start_time, 1),
        "ram_gb": _ram_gb(),
        "disk_free_gb": _disk_gb(),
        "gpu": _gpu_info(),
        "gpu_layers": config.GPU_LAYERS,
    })


@app.get("/status")
async def status():
    return await health()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.SIDECAR_PORT,
        log_level="info",
        access_log=False,
    )
