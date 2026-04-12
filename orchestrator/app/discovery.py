"""
Node Discovery via mDNS
=======================
Listens for worker nodes that advertise themselves as _llama-rpc._tcp.local.
Maintains a live registry and marks stale entries after WORKER_STALE_TIMEOUT
seconds of silence.
"""
import asyncio
import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

import config

log = logging.getLogger(__name__)

SERVICE_TYPE = "_llama-rpc._tcp.local."


@dataclass
class WorkerNode:
    name: str
    ip: str
    port: int
    properties: Dict[str, str] = field(default_factory=dict)
    last_seen: float = field(default_factory=time.time)

    @property
    def rpc_endpoint(self) -> str:
        return f"{self.ip}:{self.port}"

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.last_seen) > config.WORKER_STALE_TIMEOUT

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ip": self.ip,
            "port": self.port,
            "rpc_endpoint": self.rpc_endpoint,
            "properties": self.properties,
            "last_seen": self.last_seen,
            "stale": self.is_stale,
        }


class WorkerRegistry:
    """Thread-safe registry of discovered worker nodes."""

    def __init__(self, on_change: Optional[Callable] = None):
        self._workers: Dict[str, WorkerNode] = {}
        self._lock = asyncio.Lock()
        self._on_change = on_change  # async callback when workers change

    async def register(self, node: WorkerNode) -> None:
        async with self._lock:
            existing = self._workers.get(node.name)
            self._workers[node.name] = node
            if not existing:
                log.info("Worker joined: %s @ %s", node.name, node.rpc_endpoint)
                if self._on_change:
                    asyncio.ensure_future(self._on_change("join", node))

    async def unregister(self, name: str) -> None:
        async with self._lock:
            node = self._workers.pop(name, None)
            if node:
                log.info("Worker left: %s", name)
                if self._on_change:
                    asyncio.ensure_future(self._on_change("leave", node))

    async def touch(self, name: str) -> None:
        async with self._lock:
            if name in self._workers:
                self._workers[name].last_seen = time.time()

    async def active_workers(self) -> list[WorkerNode]:
        async with self._lock:
            return [w for w in self._workers.values() if not w.is_stale]

    async def all_workers(self) -> list[WorkerNode]:
        async with self._lock:
            return list(self._workers.values())

    async def prune_stale(self) -> list[WorkerNode]:
        """Remove and return stale workers."""
        async with self._lock:
            stale = [w for w in self._workers.values() if w.is_stale]
            for w in stale:
                log.warning("Pruning stale worker: %s (last seen %.0fs ago)",
                            w.name, time.time() - w.last_seen)
                del self._workers[w.name]
            return stale


class DiscoveryService:
    """Wraps zeroconf browsing in an async-friendly interface."""

    def __init__(self, registry: WorkerRegistry):
        self.registry = registry
        self._zc: Optional[AsyncZeroconf] = None
        self._browser: Optional[AsyncServiceBrowser] = None

    async def start(self) -> None:
        self._zc = AsyncZeroconf()
        listener = _ZeroconfListener(self.registry, self._zc.zeroconf)
        self._browser = AsyncServiceBrowser(
            self._zc.zeroconf, SERVICE_TYPE, listener=listener
        )
        log.info("mDNS discovery started (listening for %s)", SERVICE_TYPE)

    async def stop(self) -> None:
        if self._browser:
            await self._browser.async_cancel()
        if self._zc:
            await self._zc.async_close()
        log.info("mDNS discovery stopped")


class _ZeroconfListener(ServiceListener):
    """Zeroconf callback bridge → WorkerRegistry."""

    def __init__(self, registry: WorkerRegistry, zc: Zeroconf):
        self.registry = registry
        self.zc = zc

    def _resolve(self, name: str) -> Optional[WorkerNode]:
        info = self.zc.get_service_info(SERVICE_TYPE, name)
        if not info or not info.addresses:
            return None
        ip = socket.inet_ntoa(info.addresses[0])
        props = {
            k.decode(): v.decode() if isinstance(v, bytes) else str(v)
            for k, v in (info.properties or {}).items()
        }
        return WorkerNode(
            name=props.get("node_name", name.replace(f".{SERVICE_TYPE}", "")),
            ip=ip,
            port=info.port,
            properties=props,
        )

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        node = self._resolve(name)
        if node:
            asyncio.ensure_future(self.registry.register(node))

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        node = self._resolve(name)
        if node:
            asyncio.ensure_future(self.registry.touch(node.name))

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        short = name.replace(f".{SERVICE_TYPE}", "")
        asyncio.ensure_future(self.registry.unregister(short))


async def stale_prune_loop(registry: WorkerRegistry, launcher_restart_fn: Callable) -> None:
    """Periodically prune stale workers and trigger launcher restart."""
    while True:
        await asyncio.sleep(30)
        stale = await registry.prune_stale()
        if stale:
            log.info("Restarting inference server after %d stale worker(s) removed",
                     len(stale))
            asyncio.ensure_future(launcher_restart_fn())
