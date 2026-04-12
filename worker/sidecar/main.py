"""
Worker Sidecar
==============
Responsibilities:
  1. Start and supervise the llama-rpc-server process.
  2. Advertise this node on the local network via mDNS (_llama-rpc._tcp.local).
  3. Re-broadcast the mDNS record every HEARTBEAT_INTERVAL seconds.
  4. Expose a REST API for health checks and inference proxying.
  5. [Full-node mode] Also run llama-server using all discovered cluster
     workers (including self) as RPC backends, giving this node direct
     model access. Advertises its inference port in mDNS so any client
     can find and query it directly.
  6. Gracefully deregister on shutdown (SIGTERM / SIGINT).
"""
import asyncio
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import asynccontextmanager

import httpx
import psutil
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from zeroconf import ServiceBrowser, ServiceInfo, ServiceListener, Zeroconf
from zeroconf.asyncio import AsyncZeroconf

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(message)s")
log = logging.getLogger(__name__)

SERVICE_TYPE = "_llama-rpc._tcp.local."

# ── Global state ──────────────────────────────────────────────────────────────
_rpc_proc: subprocess.Popen | None = None
_inf_proc: subprocess.Popen | None = None
_zeroconf: AsyncZeroconf | None = None
_service_info: ServiceInfo | None = None
_start_time: float = time.time()
_inf_start_time: float = 0
_peer_registry: dict[str, dict] = {}   # name → {ip, port}
_inf_restart_lock: asyncio.Lock | None = None


# ── Resource helpers ──────────────────────────────────────────────────────────

def _ram_gb() -> float:
    return round(psutil.virtual_memory().total / (1024 ** 3), 1)


def _disk_gb() -> float:
    return round(psutil.disk_usage("/").free / (1024 ** 3), 1)


def _gpu_info() -> dict:
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


# ── Peer discovery (for building --rpc list) ──────────────────────────────────

class _PeerListener(ServiceListener):
    """Sync zeroconf listener that updates _peer_registry."""

    def _resolve(self, zc: Zeroconf, name: str) -> dict | None:
        info = zc.get_service_info(SERVICE_TYPE, name)
        if not info or not info.addresses:
            return None
        props = {
            k.decode(): (v.decode() if isinstance(v, bytes) else str(v))
            for k, v in (info.properties or {}).items()
        }
        return {
            "name": props.get("node_name", name),
            "ip": socket.inet_ntoa(info.addresses[0]),
            "port": info.port,
        }

    def add_service(self, zc, type_, name):
        peer = self._resolve(zc, name)
        if peer and peer["name"] != config.NODE_NAME:
            _peer_registry[peer["name"]] = peer
            log.info("Peer discovered: %s @ %s:%d", peer["name"], peer["ip"], peer["port"])
            asyncio.ensure_future(_restart_inference_if_needed())

    def update_service(self, zc, type_, name):
        pass

    def remove_service(self, zc, type_, name):
        gone = [k for k, v in _peer_registry.items()
                if name.startswith(k)]
        for k in gone:
            log.info("Peer left: %s", k)
            del _peer_registry[k]
        if gone:
            asyncio.ensure_future(_restart_inference_if_needed())


def _build_rpc_list() -> str:
    """Build comma-separated RPC endpoint list: self + all known peers."""
    endpoints = [f"127.0.0.1:{config.RPC_PORT}"]  # always include self
    for peer in _peer_registry.values():
        endpoints.append(f"{peer['ip']}:{peer['port']}")
    return ",".join(endpoints)


# ── llama-rpc-server ──────────────────────────────────────────────────────────

def _start_rpc_server() -> subprocess.Popen:
    cmd = [config.LLAMA_RPC_BIN, "--host", "0.0.0.0", "--port", str(config.RPC_PORT)]
    log.info("Starting RPC server: %s", " ".join(cmd))
    return subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)


def _stop_proc(proc: subprocess.Popen | None, name: str) -> None:
    if proc and proc.poll() is None:
        log.info("Stopping %s (pid %d)", name, proc.pid)
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


# ── llama-server (full-node inference) ────────────────────────────────────────

def _start_inference_server() -> subprocess.Popen | None:
    if not config.ENABLE_INFERENCE:
        return None
    if not config.MODEL_PATH or not os.path.exists(config.MODEL_PATH):
        log.warning("ENABLE_INFERENCE=true but MODEL_PATH not found: %s", config.MODEL_PATH)
        return None

    rpc_list = _build_rpc_list()
    cmd = [
        config.LLAMA_SERVER_BIN,
        "--model",       config.MODEL_PATH,
        "--host",        "0.0.0.0",
        "--port",        str(config.LLAMA_SERVER_PORT),
        "--ctx-size",    str(config.CONTEXT_SIZE),
        "--parallel",    str(config.PARALLEL),
        "--n-gpu-layers", str(config.GPU_LAYERS),
        "--rpc",         rpc_list,
    ]
    log.info("Starting inference server with RPC backends: %s", rpc_list)
    log.info("  Command: %s", " ".join(cmd))
    return subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)


async def _restart_inference_if_needed() -> None:
    global _inf_proc, _inf_start_time
    if not config.ENABLE_INFERENCE or _inf_restart_lock is None:
        return
    async with _inf_restart_lock:
        _stop_proc(_inf_proc, "inference server")
        await asyncio.sleep(1)
        _inf_proc = _start_inference_server()
        _inf_start_time = time.time() if _inf_proc else 0
        if _inf_proc:
            log.info("Inference server restarted with %d peer(s)", len(_peer_registry))


# ── mDNS advertisement ────────────────────────────────────────────────────────

def _build_service_info() -> ServiceInfo:
    gpu = _gpu_info()
    props: dict[str, str] = {
        "node_name":     config.NODE_NAME,
        "rpc_port":      str(config.RPC_PORT),
        "ram_gb":        str(_ram_gb()),
        "disk_free_gb":  str(_disk_gb()),
        "gpu_layers":    str(config.GPU_LAYERS),
        "full_node":     "true" if config.ENABLE_INFERENCE else "false",
    }
    if config.ENABLE_INFERENCE:
        props["inference_port"] = str(config.LLAMA_SERVER_PORT)
    if gpu:
        props["gpu_name"]    = gpu["name"]
        props["gpu_vram_mb"] = str(gpu["vram_mb"])

    return ServiceInfo(
        type_=SERVICE_TYPE,
        name=f"{config.NODE_NAME}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(config.ADVERTISE_IP)],
        port=config.RPC_PORT,
        properties={k: v.encode() for k, v in props.items()},
        server=f"{socket.gethostname()}.local.",
    )


async def _heartbeat_loop(zc: AsyncZeroconf, info: ServiceInfo) -> None:
    while True:
        await asyncio.sleep(config.HEARTBEAT_INTERVAL)
        try:
            await zc.async_update_service(info)
            log.info("mDNS heartbeat sent")
        except Exception as exc:
            log.warning("mDNS heartbeat failed: %s", exc)


# ── FastAPI app ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _rpc_proc, _inf_proc, _inf_start_time
    global _zeroconf, _service_info, _inf_restart_lock

    _inf_restart_lock = asyncio.Lock()

    # 1. Start RPC server
    _rpc_proc = _start_rpc_server()
    await asyncio.sleep(1)

    # 2. Register with mDNS
    _service_info = _build_service_info()
    _zeroconf = AsyncZeroconf()
    await _zeroconf.async_register_service(_service_info)
    log.info("Registered as '%s' (%s) on %s:%d",
             config.NODE_NAME,
             "full-node" if config.ENABLE_INFERENCE else "worker",
             config.ADVERTISE_IP, config.RPC_PORT)

    # 3. Start peer browser (for building --rpc list)
    _peer_browser = ServiceBrowser(_zeroconf.zeroconf, SERVICE_TYPE, _PeerListener())
    await asyncio.sleep(3)  # brief discovery window before starting inference

    # 4. Start inference server if full-node mode
    if config.ENABLE_INFERENCE:
        _inf_proc = _start_inference_server()
        _inf_start_time = time.time() if _inf_proc else 0
        if _inf_proc:
            log.info("Inference API available at http://%s:%d",
                     config.ADVERTISE_IP, config.LLAMA_SERVER_PORT)
        else:
            log.warning("Inference server did not start – check MODEL_PATH")

    # 5. Heartbeat
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(_zeroconf, _service_info)
    )

    yield  # ── running ──

    heartbeat_task.cancel()
    _peer_browser.cancel()
    await _zeroconf.async_unregister_service(_service_info)
    await _zeroconf.async_close()
    _stop_proc(_inf_proc, "inference server")
    _stop_proc(_rpc_proc, "RPC server")
    log.info("Worker sidecar shut down cleanly")


app = FastAPI(title="LLM Cluster Worker", version="1.0.0", lifespan=lifespan)


# ── Health / status ───────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    rpc_alive = _rpc_proc is not None and _rpc_proc.poll() is None
    inf_alive = _inf_proc is not None and _inf_proc.poll() is None
    return JSONResponse({
        "status": "ok" if rpc_alive else "rpc_down",
        "node_name": config.NODE_NAME,
        "advertise_ip": config.ADVERTISE_IP,
        "rpc_port": config.RPC_PORT,
        "uptime_s": round(time.time() - _start_time, 1),
        "ram_gb": _ram_gb(),
        "disk_free_gb": _disk_gb(),
        "gpu": _gpu_info(),
        "gpu_layers": config.GPU_LAYERS,
        "full_node": config.ENABLE_INFERENCE,
        "inference": {
            "enabled": config.ENABLE_INFERENCE,
            "running": inf_alive,
            "port": config.LLAMA_SERVER_PORT if config.ENABLE_INFERENCE else None,
            "model": config.MODEL_PATH if config.ENABLE_INFERENCE else None,
            "uptime_s": round(time.time() - _inf_start_time, 1) if _inf_start_time else 0,
            "rpc_peers": list(_peer_registry.keys()),
        },
    })


@app.get("/status")
async def status():
    return await health()


@app.get("/peers")
async def peers():
    """List all discovered cluster peers this node is aware of."""
    return JSONResponse({
        "peers": list(_peer_registry.values()),
        "self": {
            "name": config.NODE_NAME,
            "ip": config.ADVERTISE_IP,
            "rpc_port": config.RPC_PORT,
        },
        "rpc_list": _build_rpc_list(),
    })


# ── Inference proxy (full-node mode) ──────────────────────────────────────────
# These routes forward requests to the local llama-server so that clients
# hitting this worker's sidecar port get OpenAI-compatible responses.

@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_inference(path: str, request: Request):
    if not config.ENABLE_INFERENCE:
        raise HTTPException(
            status_code=503,
            detail="This node is not running in full-node mode (ENABLE_INFERENCE=false)."
        )
    if _inf_proc is None or _inf_proc.poll() is not None:
        raise HTTPException(status_code=503, detail="Inference server is not running.")

    target = f"http://127.0.0.1:{config.LLAMA_SERVER_PORT}/v1/{path}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length")}

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.request(
            method=request.method,
            url=target,
            content=body,
            headers=headers,
            params=dict(request.query_params),
        )

    # Stream back so token-by-token SSE works
    return StreamingResponse(
        content=resp.aiter_bytes(),
        status_code=resp.status_code,
        headers=dict(resp.headers),
        media_type=resp.headers.get("content-type", "application/json"),
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.SIDECAR_PORT,
        log_level="info",
        access_log=False,
    )
