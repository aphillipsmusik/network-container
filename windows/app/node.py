"""
Node process management – starts/stops llama-rpc-server or llama-server,
registers/deregisters via mDNS, and reports health.
"""
import asyncio
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from zeroconf import ServiceInfo, Zeroconf

import config as cfg_module

log = logging.getLogger(__name__)

SERVICE_TYPE = "_llama-rpc._tcp.local."
_proc: Optional[subprocess.Popen] = None
_zc: Optional[Zeroconf] = None
_svc_info: Optional[ServiceInfo] = None
_start_time: float = 0


def bin_path(name: str, install_dir: str) -> str:
    """Return path to a bundled binary."""
    p = Path(install_dir) / "bin" / name
    if p.exists():
        return str(p)
    # Fallback: same dir as this script (dev mode)
    p2 = Path(sys.executable).parent / name
    return str(p2) if p2.exists() else name


def start(conf: cfg_module.NodeConfig) -> None:
    global _proc, _start_time
    stop()

    if conf.role == "worker":
        exe = bin_path("llama-rpc-server.exe", conf.install_dir)
        cmd = [exe, "--host", "0.0.0.0", "--port", str(conf.rpc_port)]
    else:
        exe = bin_path("llama-server.exe", conf.install_dir)
        cmd = [
            exe,
            "--host", "0.0.0.0",
            "--port", str(conf.llama_server_port),
            "--ctx-size", str(conf.context_size),
            "--parallel", str(conf.parallel),
            "--n-gpu-layers", str(conf.gpu_layers),
        ]
        if conf.model_path:
            cmd += ["--model", conf.model_path]

    log.info("Starting: %s", " ".join(cmd))
    _proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    _start_time = time.time()
    _register_mdns(conf)


def stop() -> None:
    global _proc
    _deregister_mdns()
    if _proc and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _proc = None


def is_running() -> bool:
    return _proc is not None and _proc.poll() is None


def uptime() -> float:
    return round(time.time() - _start_time, 1) if _start_time else 0.0


def status() -> dict:
    return {
        "running": is_running(),
        "pid": _proc.pid if _proc else None,
        "uptime_s": uptime(),
    }


# ── mDNS ──────────────────────────────────────────────────────────────────────

def _register_mdns(conf: cfg_module.NodeConfig) -> None:
    global _zc, _svc_info
    try:
        import psutil
        ram_gb = str(round(psutil.virtual_memory().total / (1024 ** 3), 1))
    except Exception:
        ram_gb = "?"

    props = {
        b"node_name": conf.node_name.encode(),
        b"rpc_port":  str(conf.rpc_port).encode(),
        b"ram_gb":    ram_gb.encode(),
        b"gpu_layers": str(conf.gpu_layers).encode(),
        b"os":        b"windows",
    }
    _svc_info = ServiceInfo(
        type_=SERVICE_TYPE,
        name=f"{conf.node_name}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(conf.advertise_ip)],
        port=conf.rpc_port,
        properties=props,
        server=f"{socket.gethostname()}.local.",
    )
    _zc = Zeroconf()
    _zc.register_service(_svc_info)
    log.info("mDNS registered: %s @ %s:%d", conf.node_name,
             conf.advertise_ip, conf.rpc_port)


def _deregister_mdns() -> None:
    global _zc, _svc_info
    if _zc and _svc_info:
        try:
            _zc.unregister_service(_svc_info)
            _zc.close()
        except Exception:
            pass
    _zc = None
    _svc_info = None


def discover_workers(timeout: int = 5) -> list[dict]:
    """Browse mDNS for worker nodes. Returns list of dicts."""
    from zeroconf import ServiceBrowser, ServiceListener

    found = []

    class _Listener(ServiceListener):
        def add_service(self, zc, type_, name):
            info = zc.get_service_info(type_, name)
            if info and info.addresses:
                ip = socket.inet_ntoa(info.addresses[0])
                props = {
                    k.decode(): v.decode() if isinstance(v, bytes) else str(v)
                    for k, v in (info.properties or {}).items()
                }
                found.append({
                    "name": props.get("node_name", name),
                    "ip": ip,
                    "port": info.port,
                    "properties": props,
                })

        def update_service(self, *_): pass
        def remove_service(self, *_): pass

    zc = Zeroconf()
    browser = ServiceBrowser(zc, SERVICE_TYPE, _Listener())
    time.sleep(timeout)
    browser.cancel()
    zc.close()
    return found
