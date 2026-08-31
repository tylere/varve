from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from varve.web.auth import make_require_manager
from varve.web.app import _RepoHolder


def make_router(holder: _RepoHolder, templates: Jinja2Templates,
                manager_token: str | None) -> APIRouter:
    router = APIRouter()
    mgr = make_require_manager(manager_token)

    @router.get("/assignments", response_class=HTMLResponse, dependencies=[Depends(mgr)])
    async def assignment_list(request: Request):
        assignments = holder.get().list_assignments()
        datasets = {d.slug: d for d in holder.get().list_datasets()}
        destinations = {d.slug: d for d in holder.get().list_destinations()}
        return templates.TemplateResponse(request, "assignments/list.html", {
            "assignments": assignments,
            "datasets": datasets, "destinations": destinations,
        })

    return router
