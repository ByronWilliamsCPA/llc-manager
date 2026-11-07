"""HTML page routes served via Jinja2 templates."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from llc_manager.auth.dependencies import require_user
from llc_manager.core.templates import templates

# #CRITICAL: this router answers GET / ahead of the web router, so it needs its
# own gate; a page added here without it would be open.
# #VERIFY: tests/unit/test_web_gating.py::test_every_web_route_is_gated.
router = APIRouter(include_in_schema=False, dependencies=[Depends(require_user)])


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the main dashboard page."""
    return templates.TemplateResponse(request, "index.html")
