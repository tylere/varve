from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import re

from varve.web.auth import make_require_manager
from varve.web.app import _RepoHolder
from varve.state.models import DestinationRecord


def make_router(holder: _RepoHolder, templates: Jinja2Templates,
                manager_token: str | None) -> APIRouter:
    router = APIRouter()
    mgr = make_require_manager(manager_token)

    def _slugify(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64]

    @router.get("/destinations", response_class=HTMLResponse, dependencies=[Depends(mgr)])
    async def destination_list(request: Request):
        destinations = holder.get().list_destinations()
        return templates.TemplateResponse(request, "destinations/list.html", {
            "destinations": destinations,
        })

    @router.get("/destinations/new", response_class=HTMLResponse, dependencies=[Depends(mgr)])
    async def destination_new_form(request: Request):
        return templates.TemplateResponse(request, "destinations/form.html", {"token": manager_token})

    @router.post("/destinations", dependencies=[Depends(mgr)])
    async def destination_create(
        name: str = Form(...),
        type: str = Form(...),
        credentials_env: str = Form(...),
    ):
        repo = holder.get()
        slug = _slugify(name)
        record = DestinationRecord(
            slug=slug, name=name, type=type,
            credentials_env=credentials_env, enabled=True,
        )
        repo.write_destination(record)
        repo.commit_and_push(f"varve: add destination {slug}")
        return RedirectResponse(url="/destinations", status_code=303)

    return router
