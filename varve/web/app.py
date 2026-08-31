from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from varve.state.repo import LocalGitRepo
import varve.config as config

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


class _RepoHolder:
    """Lazy-pulls the local clone at most once per PULL_INTERVAL_SECONDS."""

    def __init__(self, repo_path: Path) -> None:
        self.repo = LocalGitRepo(repo_path)
        self._last_pull: float = 0.0

    def get(self) -> LocalGitRepo:
        now = time.monotonic()
        if now - self._last_pull > config.PULL_INTERVAL_SECONDS:
            try:
                self.repo.pull()
            except Exception:
                pass
            self._last_pull = now
        return self.repo


def create_app(repo_path: Path, manager_token: str | None = None) -> FastAPI:
    if manager_token is None:
        manager_token = config.MANAGER_TOKEN

    holder = _RepoHolder(repo_path)
    app = FastAPI(title="Varve")
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Attach dependencies
    app.state.holder = holder
    app.state.manager_token = manager_token
    app.state.templates = templates

    from varve.web.routes import datasets, destinations, assignments
    app.include_router(datasets.make_router(holder, templates, manager_token))
    app.include_router(destinations.make_router(holder, templates, manager_token))
    app.include_router(assignments.make_router(holder, templates, manager_token))

    return app
