"""
llama-server launcher for Windows orchestrator.
Builds the --rpc flag list from discovered workers and manages the process.
"""
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import config as cfg_module
from discovery import WorkerRegistry

log = logging.getLogger(__name__)
HEALTH_CHECK_INTERVAL = 15


class InferenceLauncher:
    def __init__(self, registry: WorkerRegistry,
                 on_status_change: Optional[Callable[[str], None]] = None):
        self.registry = registry
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._start_time: float = 0
        self._on_status = on_status_change
        self._monitor_thread: Optional[threading.Thread] = None
        self._stopping = False

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self, conf: cfg_module.OrchestratorConfig) -> bool:
        with self._lock:
            self._conf = conf
            return self._launch()

    def restart(self) -> None:
        """Rebuild --rpc list and relaunch (called when workers change)."""
        with self._lock:
            log.info("Restarting inference server…")
            self._stop_internal()
            time.sleep(1)
            self._launch()

    def stop(self) -> None:
        self._stopping = True
        with self._lock:
            self._stop_internal()

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def uptime_s(self) -> float:
        return round(time.time() - self._start_time, 1) if self._start_time else 0.0

    def active_worker_count(self) -> int:
        return len(self.registry.active_workers())

    # ── Internals ─────────────────────────────────────────────────────────────

    def _bin_path(self, name: str) -> str:
        p = Path(self._conf.install_dir) / "bin" / name
        if p.exists():
            return str(p)
        p2 = Path(sys.executable).parent / name
        return str(p2) if p2.exists() else name

    def _build_cmd(self) -> list[str]:
        workers = self.registry.active_workers()
        cmd = [
            self._bin_path("llama-server.exe"),
            "--model",        self._conf.model_path,
            "--host",         "0.0.0.0",
            "--port",         str(self._conf.llama_server_port),
            "--ctx-size",     str(self._conf.context_size),
            "--parallel",     str(self._conf.parallel),
            "--n-gpu-layers", str(self._conf.gpu_layers),
        ]
        if workers:
            rpc = ",".join(w.rpc_endpoint for w in workers)
            cmd += ["--rpc", rpc]
            log.info("RPC backends (%d): %s", len(workers), rpc)
        else:
            log.warning("No workers – running inference locally only")
        return cmd

    def _launch(self) -> bool:
        if not self._conf.model_path or not os.path.exists(self._conf.model_path):
            log.error("Model not found: %s", self._conf.model_path)
            self._notify("Model file not found")
            return False

        cmd = self._build_cmd()
        log.info("Launching: %s", " ".join(cmd))
        self._notify(f"Starting with {self.active_worker_count()} worker(s)…")

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except FileNotFoundError:
            self._notify("llama-server.exe not found in install directory")
            return False

        self._start_time = time.time()
        self._stopping = False

        # Log output in background thread
        threading.Thread(target=self._log_output, daemon=True).start()

        # Monitor process
        self._monitor_thread = threading.Thread(
            target=self._monitor, daemon=True
        )
        self._monitor_thread.start()

        self._notify(f"Inference server running on :{self._conf.llama_server_port}")
        return True

    def _stop_internal(self) -> None:
        if self._proc and self._proc.poll() is None:
            log.info("Stopping llama-server (pid %d)", self._proc.pid)
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        self._start_time = 0

    def _log_output(self) -> None:
        if self._proc and self._proc.stdout:
            for line in self._proc.stdout:
                log.debug("[llama-server] %s", line.decode(errors="replace").rstrip())

    def _monitor(self) -> None:
        while not self._stopping:
            time.sleep(HEALTH_CHECK_INTERVAL)
            if self._stopping:
                break
            if self._proc and self._proc.poll() is not None:
                rc = self._proc.returncode
                log.warning("llama-server exited (rc=%d) – restarting", rc)
                self._notify(f"Server crashed (rc={rc}), restarting…")
                with self._lock:
                    self._stop_internal()
                    self._launch()
                break

    def _notify(self, msg: str) -> None:
        log.info(msg)
        if self._on_status:
            self._on_status(msg)
