"""
Worker discovery via mDNS for Windows orchestrator.
Listens for _llama-rpc._tcp.local. services and maintains a live registry.
"""
import logging
import socket
import time
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from zeroconf import ServiceBrowser, ServiceInfo, ServiceListener, Zeroconf

log = logging.getLogger(__name__)
SERVICE_TYPE = "_llama-rpc._tcp.local."


@dataclass
class WorkerNode:
    name: str
    ip: str
    port: int
    ram_gb: float = 0.0
    gpu_layers: int = 0
    gpu_name: str = ""
    platform: str = "unknown"
    full_node: bool = False
    inference_port: Optional[int] = None
    last_seen: float = field(default_factory=time.time)

    @property
    def rpc_endpoint(self) -> str:
        return f"{self.ip}:{self.port}"

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.last_seen) > 90

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ip": self.ip,
            "port": self.port,
            "rpc_endpoint": self.rpc_endpoint,
            "ram_gb": self.ram_gb,
            "gpu_name": self.gpu_name,
            "platform": self.platform,
            "full_node": self.full_node,
            "stale": self.is_stale,
        }


class WorkerRegistry:
    def __init__(self, on_change: Optional[Callable] = None):
        self._workers: Dict[str, WorkerNode] = {}
        self._lock = threading.Lock()
        self._on_change = on_change

    def register(self, node: WorkerNode) -> None:
        with self._lock:
            existing = self._workers.get(node.name)
            self._workers[node.name] = node
            if not existing:
                log.info("Worker joined: %s @ %s", node.name, node.rpc_endpoint)
                if self._on_change:
                    self._on_change("join", node)

    def unregister(self, name: str) -> None:
        with self._lock:
            node = self._workers.pop(name, None)
            if node:
                log.info("Worker left: %s", name)
                if self._on_change:
                    self._on_change("leave", node)

    def touch(self, name: str) -> None:
        with self._lock:
            if name in self._workers:
                self._workers[name].last_seen = time.time()

    def active_workers(self) -> list[WorkerNode]:
        with self._lock:
            return [w for w in self._workers.values() if not w.is_stale]

    def all_workers(self) -> list[WorkerNode]:
        with self._lock:
            return list(self._workers.values())

    def prune_stale(self) -> list[WorkerNode]:
        with self._lock:
            stale = [w for w in self._workers.values() if w.is_stale]
            for w in stale:
                del self._workers[w.name]
            return stale

    def rpc_list(self) -> str:
        workers = self.active_workers()
        return ",".join(w.rpc_endpoint for w in workers)


class _Listener(ServiceListener):
    def __init__(self, registry: WorkerRegistry, zc: Zeroconf):
        self.registry = registry
        self.zc = zc

    def _resolve(self, name: str) -> Optional[WorkerNode]:
        info = self.zc.get_service_info(SERVICE_TYPE, name)
        if not info or not info.addresses:
            return None
        ip = socket.inet_ntoa(info.addresses[0])
        props = {
            k.decode(): (v.decode() if isinstance(v, bytes) else str(v))
            for k, v in (info.properties or {}).items()
        }
        return WorkerNode(
            name=props.get("node_name", name),
            ip=ip,
            port=info.port,
            ram_gb=float(props.get("ram_gb", "0") or "0"),
            gpu_layers=int(props.get("gpu_layers", "0") or "0"),
            gpu_name=props.get("gpu_name", ""),
            platform=props.get("platform", "unknown"),
            full_node=props.get("full_node", "false") == "true",
            inference_port=int(p) if (p := props.get("inference_port")) else None,
        )

    def add_service(self, zc, type_, name):
        node = self._resolve(name)
        if node:
            self.registry.register(node)

    def update_service(self, zc, type_, name):
        node = self._resolve(name)
        if node:
            self.registry.touch(node.name)

    def remove_service(self, zc, type_, name):
        short = name.replace(f".{SERVICE_TYPE}", "").replace(SERVICE_TYPE, "")
        self.registry.unregister(short)


class DiscoveryService:
    def __init__(self, registry: WorkerRegistry):
        self.registry = registry
        self._zc: Optional[Zeroconf] = None
        self._browser = None

    def start(self) -> None:
        self._zc = Zeroconf()
        self._browser = ServiceBrowser(self._zc, SERVICE_TYPE, _Listener(self.registry, self._zc))
        log.info("mDNS discovery started")

    def stop(self) -> None:
        if self._browser:
            self._browser.cancel()
        if self._zc:
            self._zc.close()
        log.info("mDNS discovery stopped")
