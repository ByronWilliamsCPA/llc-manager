"""Entity API endpoints: legal entities, individuals, and households."""

# #CRITICAL: Security - entity endpoints currently unauthenticated; deferred to Phase 1.
# Responses include individual and household rows (personal names) and bank
# account last-4 digits, so real individual or household data must not be
# loaded into a database this API serves beyond localhost until then.
# #VERIFY: authentication dependency wired before any non-localhost deployment.

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from llc_manager.db.session import get_async_session
from llc_manager.models.entity import Entity, EntityType
from llc_manager.schemas.entity import (
    EntityCreate,
    EntityListResponse,
    EntityResponse,
    EntityUpdate,
)

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_async_session)]

_UNIQUE_CONFLICT = "An entity with this EIN or Xero tenant ID already exists"


async def _ensure_xero_tenant_free(
    db: AsyncSession, xero_tenant_id: str, exclude: UUID | None = None
) -> None:
    """Raise 409 when another live entity already holds the Xero tenant ID.

    This pre-check gives a clear message in the common case. It is not
    atomic: :func:`_flush_or_conflict` maps the unique-index violation from a
    concurrent request to the same 409.

    Args:
        db (AsyncSession): Database session.
        xero_tenant_id (str): Tenant ID requested by the caller.
        exclude (UUID | None): Entity being updated, ignored in the check.

    Raises:
        HTTPException: 409 when the tenant ID is already mapped.
    """
    # #ASSUME: Concurrency - check-then-write; two requests can both pass.
    # The partial unique index ix_entities_xero_tenant_id_active is the real
    # guard, and its violation is mapped to 409 at flush.
    # #VERIFY: tests/unit/test_entities_xero_api.py covers the flush-time 409.
    query = select(Entity.id).where(
        Entity.xero_tenant_id == xero_tenant_id, Entity.deleted_at.is_(None)
    )
    if exclude is not None:
        query = query.where(Entity.id != exclude)
    existing = await db.execute(query)
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An entity with this Xero tenant ID already exists",
        )


async def _flush_or_conflict(db: AsyncSession) -> None:
    """Flush pending writes, mapping a unique-constraint violation to 409.

    Args:
        db (AsyncSession): Database session.

    Raises:
        HTTPException: 409 when the flush violates a unique constraint (EIN
            or Xero tenant ID), for example after a concurrent request.
    """
    try:
        await db.flush()
    except IntegrityError:
        # from None: the IntegrityError text carries the row's values.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_UNIQUE_CONFLICT
        ) from None


@router.get(
    "",
    response_model=EntityListResponse,
    status_code=status.HTTP_200_OK,
    summary="List entities",
    description=(
        "Return a paginated, optionally filtered list of entities (legal "
        "entities, individuals, and households). "
        "Supports full-text search across `legal_name`, `ein`, and "
        "`dba_names`, plus `is_active`, `entity_type`, and exact "
        "`xero_tenant_id` filters. Soft-deleted entities are excluded."
    ),
    responses={
        200: {"description": "Paginated list of entities"},
    },
)
async def list_entities(
    db: DBSession,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: str | None = Query(None, description="Search by legal name or EIN"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    entity_type: EntityType | None = Query(None, description="Filter by entity type"),
    xero_tenant_id: str | None = Query(
        None, max_length=64, description="Exact match on the Xero tenant ID"
    ),
) -> EntityListResponse:
    """List all entities with pagination and filtering.

    Args:
        db (DBSession): Database session.
        page (int): Page number (1-indexed).
        size (int): Number of items per page.
        search (str | None): Optional search string for legal name or EIN.
        is_active (bool | None): Optional filter for active/inactive entities.
        entity_type (EntityType | None): Optional filter by entity type.
        xero_tenant_id (str | None): Optional exact match on Xero tenant ID.

    Returns:
        EntityListResponse: Paginated list of entities.
    """
    query = select(Entity).where(Entity.deleted_at.is_(None))

    if search:
        search_filter = f"%{search}%"
        query = query.where(
            (Entity.legal_name.ilike(search_filter))
            | (Entity.ein.ilike(search_filter))
            | (Entity.dba_names.ilike(search_filter))
        )

    if is_active is not None:
        query = query.where(Entity.is_active == is_active)

    if entity_type is not None:
        query = query.where(Entity.entity_type == entity_type)

    if xero_tenant_id is not None:
        query = query.where(Entity.xero_tenant_id == xero_tenant_id)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(Entity.legal_name)

    result = await db.execute(query)
    entities = result.scalars().all()

    pages = (total + size - 1) // size if total > 0 else 1

    return EntityListResponse(
        items=[EntityResponse.model_validate(e) for e in entities],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.post(
    "",
    response_model=EntityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create entity",
    description=(
        "Create a new entity. The optional `ein` and `xero_tenant_id` fields "
        "must be unique across non-deleted entities; a duplicate value returns "
        "409. An `individual` or `household` entity must not set `ein`, "
        "`formation_state`, or `formation_date` (422)."
    ),
    responses={
        201: {"description": "Entity created successfully"},
        409: {"description": "Entity with the supplied EIN or Xero tenant ID exists"},
        422: {"description": "Validation error"},
    },
)
async def create_entity(
    db: DBSession,
    entity_in: EntityCreate,
) -> EntityResponse:
    """Create a new entity.

    Args:
        db (DBSession): Database session.
        entity_in (EntityCreate): Entity creation data.

    Returns:
        EntityResponse: Created entity.

    Raises:
        HTTPException: If an entity with the supplied EIN or Xero tenant ID
            already exists.
    """
    if entity_in.ein:
        existing = await db.execute(select(Entity).where(Entity.ein == entity_in.ein))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An entity with this EIN already exists",
            )

    if entity_in.xero_tenant_id:
        await _ensure_xero_tenant_free(db, entity_in.xero_tenant_id)

    entity = Entity(**entity_in.model_dump())
    db.add(entity)
    await _flush_or_conflict(db)
    await db.refresh(entity)

    return EntityResponse.model_validate(entity)


@router.get(
    "/{entity_id}",
    response_model=EntityResponse,
    status_code=status.HTTP_200_OK,
    summary="Get entity by ID",
    description="Fetch a single entity by its UUID. Soft-deleted entities are not returned.",
    responses={
        200: {"description": "Entity retrieved"},
        404: {"description": "Entity not found"},
    },
)
async def get_entity(
    db: DBSession,
    entity_id: UUID,
) -> EntityResponse:
    """Get an entity by ID.

    Args:
        db (DBSession): Database session.
        entity_id (UUID): Entity UUID.

    Returns:
        EntityResponse: Entity details.

    Raises:
        HTTPException: If entity not found.
    """
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.deleted_at.is_(None))
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity with ID {entity_id} not found",
        )

    return EntityResponse.model_validate(entity)


@router.patch(
    "/{entity_id}",
    response_model=EntityResponse,
    status_code=status.HTTP_200_OK,
    summary="Update entity",
    description=(
        "Partially update an entity. Only fields included in the request body "
        "are modified. Updating `ein` or `xero_tenant_id` to a value already "
        "held by another entity returns 409. Sending `xero_tenant_id: null` "
        "clears the mapping."
    ),
    responses={
        200: {"description": "Entity updated"},
        404: {"description": "Entity not found"},
        409: {"description": "Entity with the supplied EIN or Xero tenant ID exists"},
        422: {"description": "Validation error"},
    },
)
async def update_entity(
    db: DBSession,
    entity_id: UUID,
    entity_in: EntityUpdate,
) -> EntityResponse:
    """Update an entity.

    Args:
        db (DBSession): Database session.
        entity_id (UUID): Entity UUID.
        entity_in (EntityUpdate): Entity update data.

    Returns:
        EntityResponse: Updated entity.

    Raises:
        HTTPException: 404 if the entity is not found; 409 if the EIN or Xero
            tenant ID is already held by another entity.
    """
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.deleted_at.is_(None))
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity with ID {entity_id} not found",
        )

    if entity_in.ein and entity_in.ein != entity.ein:
        existing = await db.execute(
            select(Entity).where(Entity.ein == entity_in.ein, Entity.id != entity_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An entity with this EIN already exists",
            )

    if entity_in.xero_tenant_id and entity_in.xero_tenant_id != entity.xero_tenant_id:
        await _ensure_xero_tenant_free(db, entity_in.xero_tenant_id, exclude=entity_id)

    update_data = entity_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entity, field, value)

    await _flush_or_conflict(db)
    await db.refresh(entity)

    return EntityResponse.model_validate(entity)


@router.delete(
    "/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete entity",
    description=(
        "Soft-delete an entity by stamping `deleted_at`. The record is "
        "retained for audit but excluded from list and detail responses."
    ),
    responses={
        204: {"description": "Entity soft-deleted"},
        404: {"description": "Entity not found"},
    },
)
async def delete_entity(
    db: DBSession,
    entity_id: UUID,
) -> None:
    """Soft delete an entity.

    Args:
        db (DBSession): Database session.
        entity_id (UUID): Entity UUID.

    Raises:
        HTTPException: If entity not found.
    """
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.deleted_at.is_(None))
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity with ID {entity_id} not found",
        )

    entity.deleted_at = datetime.now(UTC)
    # #ASSUME: deleted_by populated once authentication ships; AuditMixin field intentionally None now.
    await db.flush()
