from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from varve.slug import slugify
from varve.web.auth import make_require_manager
from varve.web.app import _RepoHolder
from varve.state.models import AssignmentRecord


def make_router(holder: _RepoHolder, templates: Jinja2Templates,
                manager_token: str | None) -> APIRouter:
    router = APIRouter()
    mgr = make_require_manager(manager_token)

    def _slugify(a: str, b: str) -> str:
        try:
            return slugify(f"{a}-{b}")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/assignments", response_class=HTMLResponse, dependencies=[Depends(mgr)])
    async def assignment_list(request: Request):
        repo = holder.get()
        assignments = repo.list_assignments()
        datasets = {d.slug: d for d in repo.list_datasets()}
        destinations = {d.slug: d for d in repo.list_destinations()}
        return templates.TemplateResponse(request, "assignments/list.html", {
            "assignments": assignments,
            "datasets": datasets, "destinations": destinations,
        })

    @router.get("/assignments/new", response_class=HTMLResponse, dependencies=[Depends(mgr)])
    async def assignment_new_form(request: Request):
        datasets = holder.get().list_datasets()
        destinations = holder.get().list_destinations()
        return templates.TemplateResponse(request, "assignments/form.html", {
            "datasets": datasets, "destinations": destinations, "token": manager_token,
        })

    @router.post("/assignments", dependencies=[Depends(mgr)])
    async def assignment_create(
        dataset_slug: str = Form(...),
        destination_slug: str = Form(...),
        check_interval_hours: int = Form(48),
    ):
        repo = holder.get()
        if repo.get_dataset(dataset_slug) is None:
            raise HTTPException(status_code=400, detail=f"dataset '{dataset_slug}' not found")
        if repo.get_destination(destination_slug) is None:
            raise HTTPException(status_code=400, detail=f"destination '{destination_slug}' not found")
        slug = _slugify(dataset_slug, destination_slug)
        if repo.get_assignment(slug) is not None:
            raise HTTPException(status_code=409, detail=f"assignment '{slug}' already exists")
        record = AssignmentRecord(
            slug=slug, dataset_slug=dataset_slug, destination_slug=destination_slug,
            check_interval_hours=check_interval_hours, enabled=True,
        )
        repo.write_assignment(record)
        repo.commit_and_push(f"varve: assign {dataset_slug} → {destination_slug}")
        return RedirectResponse(url="/assignments", status_code=303)

    @router.patch("/assignments/{slug}/toggle", dependencies=[Depends(mgr)])
    async def assignment_toggle(slug: str):
        repo = holder.get()
        a = repo.get_assignment(slug)
        if a is None:
            raise HTTPException(status_code=404)
        a.enabled = not a.enabled
        repo.write_assignment(a)
        repo.commit_and_push(f"varve: {'enable' if a.enabled else 'disable'} assignment {slug}")
        return {"slug": slug, "enabled": a.enabled}

    return router
