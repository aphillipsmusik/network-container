"""
Management REST API (port 8888)
================================
Endpoints:
  GET  /health          – orchestrator health
  GET  /workers         – list all discovered workers
  GET  /workers/active  – list non-stale workers
  POST /restart         – rebuild RPC list and relaunch inference server
  GET  /server/status   – proxy the llama-server /health endpoint
"""
import logging
import time

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

import config
from discovery import WorkerRegistry
from launcher import InferenceLauncher

log = logging.getLogger(__name__)

_start_time = time.time()


def build_api(registry: WorkerRegistry, launcher: InferenceLauncher) -> FastAPI:
    app = FastAPI(
        title="LLM Cluster Management API",
        version="1.0.0",
        description=(
            "Manages a distributed llama.cpp inference cluster. "
            "Workers register via mDNS; the orchestrator auto-discovers them "
            "and builds the --rpc flag list for llama-server."
        ),
    )

    @app.get("/health")
    async def health():
        workers = await registry.active_workers()
        return {
            "status": "ok",
            "uptime_s": round(time.time() - _start_time, 1),
            "node_name": config.NODE_NAME,
            "model_path": config.MODEL_PATH,
            "active_workers": len(workers),
            "inference_server_running": launcher.running,
            "inference_server_uptime_s": launcher.uptime_s,
        }

    @app.get("/workers")
    async def list_all_workers():
        all_w = await registry.all_workers()
        return {"workers": [w.to_dict() for w in all_w], "total": len(all_w)}

    @app.get("/workers/active")
    async def list_active_workers():
        active = await registry.active_workers()
        return {
            "workers": [w.to_dict() for w in active],
            "total": len(active),
            "rpc_endpoints": [w.rpc_endpoint for w in active],
        }

    @app.post("/restart")
    async def restart_inference():
        """Rebuild the --rpc list from current workers and restart llama-server."""
        workers = await registry.active_workers()
        if not workers:
            raise HTTPException(
                status_code=400,
                detail="No active workers discovered. Start worker nodes first."
            )
        import asyncio
        asyncio.ensure_future(launcher.restart())
        return {"status": "restarting", "workers": [w.rpc_endpoint for w in workers]}

    @app.get("/server/status")
    async def server_status():
        """Proxy the llama-server /health endpoint."""
        url = f"http://127.0.0.1:{config.LLAMA_SERVER_PORT}/health"
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, timeout=5.0)
                return JSONResponse(content=r.json(), status_code=r.status_code)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Inference server unreachable: {exc}")

    @app.get("/server/models")
    async def server_models():
        """Proxy the llama-server /v1/models endpoint (OpenAI-compatible)."""
        url = f"http://127.0.0.1:{config.LLAMA_SERVER_PORT}/v1/models"
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, timeout=5.0)
                return JSONResponse(content=r.json(), status_code=r.status_code)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Inference server unreachable: {exc}")

    return app
