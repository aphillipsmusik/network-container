"""
Orchestrator Entry Point
========================
Startup sequence:
  1. Start mDNS discovery (listen for worker nodes)
  2. Wait DISCOVERY_TIMEOUT seconds to collect initial workers
  3. Launch llama-server with discovered workers as --rpc backends
  4. Start management REST API on MGMT_PORT
  5. Run stale-worker pruning loop in the background

The orchestrator will automatically restart llama-server whenever
the worker roster changes (workers join or leave).
"""
import asyncio
import logging
import signal
import sys

import uvicorn

import config
from api import build_api
from discovery import DiscoveryService, WorkerRegistry, stale_prune_loop
from launcher import InferenceLauncher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [orchestrator] %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)


async def main() -> None:
    log.info("=== LLM Cluster Orchestrator starting ===")
    log.info("Node: %s | Model: %s", config.NODE_NAME, config.MODEL_PATH or "(none)")

    # ── 1. Worker registry + discovery ───────────────────────────────────────
    launcher: InferenceLauncher  # forward reference for the callback

    async def on_worker_change(event: str, node) -> None:
        log.info("Worker %s: %s – restarting inference server", event, node.name)
        if launcher.running:
            await launcher.restart()
        else:
            await launcher.start()

    registry = WorkerRegistry(on_change=on_worker_change)
    launcher = InferenceLauncher(registry)

    discovery = DiscoveryService(registry)
    await discovery.start()

    # ── 2. Initial discovery window ───────────────────────────────────────────
    log.info("Waiting %ds for workers to appear…", config.DISCOVERY_TIMEOUT)
    await asyncio.sleep(config.DISCOVERY_TIMEOUT)

    initial_workers = await registry.active_workers()
    log.info("Found %d worker(s) at startup", len(initial_workers))

    # ── 3. Start inference server ─────────────────────────────────────────────
    if config.MODEL_PATH:
        await launcher.start()
    else:
        log.warning("MODEL_PATH not set – inference server will not start. "
                    "Set MODEL_PATH and call POST /restart.")

    # ── 4. Background stale-prune loop ────────────────────────────────────────
    prune_task = asyncio.create_task(
        stale_prune_loop(registry, launcher.restart)
    )

    # ── 5. Management API ─────────────────────────────────────────────────────
    api = build_api(registry, launcher)

    uv_config = uvicorn.Config(
        app=api,
        host="0.0.0.0",
        port=config.MGMT_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(uv_config)

    # Graceful shutdown
    loop = asyncio.get_running_loop()

    def _handle_signal():
        log.info("Shutdown signal received")
        server.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    log.info("Management API listening on :%d", config.MGMT_PORT)
    log.info("Inference API (OpenAI-compatible) on :%d", config.LLAMA_SERVER_PORT)
    await server.serve()

    # ── Cleanup ───────────────────────────────────────────────────────────────
    prune_task.cancel()
    await launcher.stop()
    await discovery.stop()
    log.info("=== Orchestrator shut down ===")


if __name__ == "__main__":
    asyncio.run(main())
