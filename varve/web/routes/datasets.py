from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from datetime import datetime, timezone
import re

from varve.web.auth import make_require_manager
from varve.web.app import _RepoHolder
from varve.state.models import DatasetRecord


def make_router(holder: _RepoHolder, templates: Jinja2Templates,
                manager_token: str | None) -> APIRouter:
    router = APIRouter()
    mgr = make_require_manager(manager_token)

    def _slugify(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64]

    @router.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        repo = holder.get()
        datasets = repo.list_datasets()
        recent_runs = []
        for ds in datasets[:10]:
            runs = repo.list_runs(ds.slug)
            if runs:
                recent_runs.append(runs[0])
        return templates.TemplateResponse(request, "dashboard.html", {
            "datasets": datasets, "recent_runs": recent_runs,
        })

    @router.get("/datasets", response_class=HTMLResponse)
    async def dataset_list(request: Request):
        repo = holder.get()
        datasets = repo.list_datasets()
        return templates.TemplateResponse(request, "datasets/list.html", {
            "datasets": datasets,
        })

    @router.get("/datasets/new", response_class=HTMLResponse, dependencies=[Depends(mgr)])
    async def dataset_new_form(request: Request):
        return templates.TemplateResponse(request, "datasets/form.html", {"dataset": None})

    @router.get("/datasets/{slug}", response_class=HTMLResponse)
    async def dataset_detail(request: Request, slug: str):
        repo = holder.get()
        dataset = repo.get_dataset(slug)
        if dataset is None:
            raise HTTPException(status_code=404, detail=f"Dataset '{slug}' not found")
        runs = repo.list_runs(slug)
        mirrors = repo.list_mirrors(slug)
        return templates.TemplateResponse(request, "datasets/detail.html", {
            "dataset": dataset, "runs": runs, "mirrors": mirrors,
        })

    @router.post("/datasets", dependencies=[Depends(mgr)])
    async def dataset_create(
        request: Request,
        name: str = Form(...),
        source_url: str = Form(...),
        source_urls_text: str = Form(""),
        detector_type: str = Form("url"),
        notes: str = Form(""),
    ):
        repo = holder.get()
        slug = _slugify(name)
        source_urls = [u.strip() for u in source_urls_text.splitlines() if u.strip()]
        record = DatasetRecord(
            slug=slug, name=name, source_url=source_url,
            source_urls=source_urls, detector_type=detector_type,
            detector_config={}, enabled=False, notes=notes,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            last_fingerprint=None, last_checked_at=None,
        )
        repo.write_dataset(record)
        repo.commit_and_push(f"varve: add dataset {slug}")
        return RedirectResponse(url=f"/datasets/{slug}", status_code=303)

    @router.patch("/datasets/{slug}/toggle", dependencies=[Depends(mgr)])
    async def dataset_toggle(slug: str):
        repo = holder.get()
        dataset = repo.get_dataset(slug)
        if dataset is None:
            raise HTTPException(status_code=404)
        dataset.enabled = not dataset.enabled
        repo.write_dataset(dataset)
        repo.commit_and_push(f"varve: {'enable' if dataset.enabled else 'disable'} {slug}")
        return {"slug": slug, "enabled": dataset.enabled}

    return router
