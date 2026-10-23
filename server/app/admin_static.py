"""Serve the admin panel, the editor and the widget bundle from the API itself.

Hosting the panel on the API's own origin keeps the session cookie first
party, so no cross-site cookies or CORS with credentials are ever needed. The
files come from the built widget output (``npm run build`` in widget/), whose
location is ``ASKHARBOR_ADMIN_DIST``. Only top level files are served, by name.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse

_MISSING = (
    "The admin panel files are not built. Run 'npm ci && npm run build' in widget/ "
    "or point ASKHARBOR_ADMIN_DIST at a built widget output directory."
)


def build_static_router(dist: Path) -> APIRouter:
    router = APIRouter(include_in_schema=False)

    def serve(name: str) -> FileResponse:
        if "/" in name or name.startswith(".") or name != Path(name).name:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        path = dist / name
        if not path.is_file():
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, _MISSING if name == "admin.html" else "Not found."
            )
        return FileResponse(path)

    @router.get("/admin")
    def admin_root() -> RedirectResponse:
        return RedirectResponse("/admin/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    @router.get("/admin/")
    def admin_index() -> FileResponse:
        return serve("admin.html")

    @router.get("/admin/{name}")
    def admin_file(name: str) -> FileResponse:
        return serve(name)

    return router
