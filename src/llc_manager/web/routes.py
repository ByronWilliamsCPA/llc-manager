"""HTMX/Jinja2 server-rendered routes for the entity UI."""

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llc_manager.db.session import get_async_session
from llc_manager.models.entity import Entity, EntityType

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["Web"])

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


@router.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirect the site root to the entity list."""
    return RedirectResponse(
        url="/entities", status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )


@router.get("/entities", response_class=HTMLResponse)
async def entities_list_page(
    request: Request,
    db: DBSession,
    q: str | None = Query(None, description="Search by legal name or EIN"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> HTMLResponse:
    """Render the entity list page (or the table-body partial for HTMX requests)."""
    query = select(Entity).where(Entity.deleted_at.is_(None))
    if q:
        like = f"%{q}%"
        query = query.where(
            Entity.legal_name.ilike(like)
            | Entity.ein.ilike(like)
            | Entity.dba_names.ilike(like)
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(Entity.legal_name)
    entities = (await db.execute(query)).scalars().all()

    pages = (total + size - 1) // size if total > 0 else 1
    context = {
        "request": request,
        "entities": entities,
        "search": q or "",
        "page": page,
        "size": size,
        "total": total,
        "pages": pages,
    }

    template = (
        "entities/partials/table_rows.html"
        if _is_htmx(request)
        else "entities/list.html"
    )
    return templates.TemplateResponse(request, template, context)


async def _get_entity_or_404(db: AsyncSession, entity_id: UUID) -> Entity:
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.deleted_at.is_(None))
    )
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity with ID {entity_id} not found",
        )
    return entity


@router.get("/entities/{entity_id}", response_class=HTMLResponse)
async def entity_detail_page(
    request: Request,
    db: DBSession,
    entity_id: UUID,
) -> HTMLResponse:
    """Render the entity detail page."""
    entity = await _get_entity_or_404(db, entity_id)
    return templates.TemplateResponse(
        request,
        "entities/detail.html",
        {"request": request, "entity": entity},
    )


@router.get("/entities/{entity_id}/card", response_class=HTMLResponse)
async def entity_detail_card(
    request: Request,
    db: DBSession,
    entity_id: UUID,
) -> HTMLResponse:
    """HTMX fragment: the read-only detail card (used by the edit-form Cancel button)."""
    entity = await _get_entity_or_404(db, entity_id)
    return templates.TemplateResponse(
        request,
        "entities/partials/detail_card.html",
        {"request": request, "entity": entity},
    )


@router.get("/entities/{entity_id}/edit", response_class=HTMLResponse)
async def entity_edit_form(
    request: Request,
    db: DBSession,
    entity_id: UUID,
) -> HTMLResponse:
    """HTMX fragment: the inline edit form for an entity."""
    entity = await _get_entity_or_404(db, entity_id)
    return templates.TemplateResponse(
        request,
        "entities/partials/edit_form.html",
        {
            "request": request,
            "entity": entity,
            "entity_types": list(EntityType),
        },
    )
