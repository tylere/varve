from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from varve.web.auth import make_require_manager
from varve.web.app import _RepoHolder


def make_router(holder: _RepoHolder, templates: Jinja2Templates,
                manager_token: str | None) -> APIRouter:
    router = APIRouter()

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

    return router
