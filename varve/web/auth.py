import secrets

from fastapi import HTTPException, Request


def make_require_manager(token: str | None):
    async def require_manager(request: Request) -> None:
        if token is None:
            raise HTTPException(status_code=403, detail="Manager token required")
        auth = request.headers.get("authorization", "")
        query = request.query_params.get("token", "")
        provided = auth.removeprefix("Bearer ").strip() or query
        if not secrets.compare_digest(provided, token):
            raise HTTPException(status_code=403, detail="Manager token required")
    return require_manager
