from __future__ import annotations

import asyncio
import subprocess
import sys
import uuid
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from varve.web.auth import make_require_manager
from varve.web.app import _RepoHolder
import varve.config as config

# In-memory store for active run log queues
_run_queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)


def make_router(holder: _RepoHolder, templates: Jinja2Templates,
                manager_token: str | None) -> APIRouter:
    router = APIRouter()
    mgr = make_require_manager(manager_token)

    @router.post("/monitor/trigger/{slug}", dependencies=[Depends(mgr)])
    async def trigger(slug: str, request: Request):
        repo = holder.get()
        if repo.get_dataset(slug) is None:
            raise HTTPException(status_code=404, detail=f"Dataset '{slug}' not found")

        run_id = str(uuid.uuid4())
        queue: asyncio.Queue = asyncio.Queue()
        _run_queues[run_id] = queue

        async def _run():
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "varve", "monitor", "run", "--id", slug, "--force",
                env={**__import__("os").environ, "VARVE_STATE_REPO_PATH": str(holder.repo.root)},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            async for line in proc.stdout:
                await queue.put({"data": line.decode().rstrip(), "event": "log"})
            await proc.wait()
            await queue.put({"data": "DONE", "event": "done"})

        asyncio.create_task(_run())
        return {"run_id": run_id}

    @router.get("/monitor/stream/{run_id}", dependencies=[Depends(mgr)])
    async def stream(run_id: str):
        queue = _run_queues.get(run_id)
        if queue is None:
            raise HTTPException(status_code=404, detail="Run not found")

        async def generator():
            while True:
                msg = await queue.get()
                yield msg
                if msg.get("event") == "done":
                    _run_queues.pop(run_id, None)
                    break

        return EventSourceResponse(generator())

    return router
