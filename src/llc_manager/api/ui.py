"""HTML page routes served via Jinja2 templates."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from llc_manager.core.templates import templates

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the main dashboard page."""
    return templates.TemplateResponse(request, "index.html")
