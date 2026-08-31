from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from varve.web.auth import make_require_manager
from varve.web.app import _RepoHolder


def make_router(holder: _RepoHolder, templates: Jinja2Templates,
                manager_token: str | None) -> APIRouter:
    router = APIRouter()
    mgr = make_require_manager(manager_token)

    @router.get("/destinations", response_class=HTMLResponse, dependencies=[Depends(mgr)])
    async def destination_list(request: Request):
        destinations = holder.get().list_destinations()
        return templates.TemplateResponse(request, "destinations/list.html", {
            "destinations": destinations,
        })

    return router
