"""
llama-server Launcher
=====================
Builds the --rpc flag list from discovered workers and manages the
llama-server subprocess lifecycle. Restarts gracefully when the worker
roster changes.
"""
import asyncio
import logging
import os
import signal
import sys
import time
from typing import Optional

import httpx

import config
from discovery import WorkerRegistry

log = logging.getLogger(__name__)

_HEALTH_URL = f"http://127.0.0.1:{config.LLAMA_SERVER_PORT}/health"
_DRAIN_TIMEOUT = 15   # seconds to wait for in-flight requests to finish
_STARTUP_TIMEOUT = 60 # seconds to wait for llama-server to become healthy


class InferenceLauncher:
    """Manages the llama-server subprocess."""

    def __init__(self, registry: WorkerRegistry):
        self.registry = registry
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._restart_lock = asyncio.Lock()
        self._start_time: float = 0.0

    # ── Public interface ──────────────────────────────────────────────────────

    async def start(self) -> None:
        async with self._restart_lock:
            await self._launch()

    async def restart(self) -> None:
        """Called when the worker roster changes."""
        async with self._restart_lock:
            log.info("Restarting inference server with updated worker list")
            await self._stop_server()
            await self._launch()

    async def stop(self) -> None:
        async with self._restart_lock:
            await self._stop_server()

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    @property
    def uptime_s(self) -> float:
        return round(time.time() - self._start_time, 1) if self._start_time else 0.0

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _build_cmd(self) -> list[str]:
        workers = await self.registry.active_workers()
        cmd = [
            config.LLAMA_SERVER_BIN,
            "--model", config.MODEL_PATH,
            "--host", "0.0.0.0",
            "--port", str(config.LLAMA_SERVER_PORT),
            "--ctx-size", str(config.CONTEXT_SIZE),
            "--parallel", str(config.PARALLEL),
            "--n-gpu-layers", str(config.GPU_LAYERS),
        ]
        if workers:
            rpc_list = ",".join(w.rpc_endpoint for w in workers)
            cmd += ["--rpc", rpc_list]
            log.info("Using %d remote worker(s): %s", len(workers), rpc_list)
        else:
            log.warning("No workers discovered – running inference locally only")
        return cmd

    async def _launch(self) -> None:
        if not config.MODEL_PATH:
            log.error("MODEL_PATH is not set – cannot start inference server")
            return
        if not os.path.exists(config.MODEL_PATH):
            log.error("Model not found at %s", config.MODEL_PATH)
            return

        cmd = await self._build_cmd()
        log.info("Launching: %s", " ".join(cmd))
        self._proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=sys.stdout, stderr=sys.stderr
        )
        self._start_time = time.time()
        asyncio.ensure_future(self._watch_process())
        await self._wait_for_healthy()

    async def _stop_server(self) -> None:
        if not self._proc or self._proc.returncode is not None:
            return
        log.info("Draining in-flight requests (up to %ds)…", _DRAIN_TIMEOUT)
        self._proc.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=_DRAIN_TIMEOUT)
        except asyncio.TimeoutError:
            log.warning("Drain timeout – sending SIGKILL")
            self._proc.kill()
            await self._proc.wait()
        self._proc = None
        self._start_time = 0.0
        log.info("Inference server stopped")

    async def _wait_for_healthy(self) -> None:
        deadline = time.time() + _STARTUP_TIMEOUT
        async with httpx.AsyncClient() as client:
            while time.time() < deadline:
                try:
                    r = await client.get(_HEALTH_URL, timeout=2.0)
                    if r.status_code == 200:
                        log.info("Inference server healthy (port %d)",
                                 config.LLAMA_SERVER_PORT)
                        return
                except Exception:
                    pass
                await asyncio.sleep(2)
        log.warning("Inference server did not become healthy within %ds",
                    _STARTUP_TIMEOUT)

    async def _watch_process(self) -> None:
        """Log unexpected process exits."""
        if self._proc:
            rc = await self._proc.wait()
            if rc != 0:
                log.error("llama-server exited unexpectedly (rc=%d)", rc)
