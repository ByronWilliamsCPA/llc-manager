"""Entity (LLC) API endpoints."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llc_manager.db.session import get_async_session
from llc_manager.models.entity import Entity
from llc_manager.schemas.entity import (
    EntityCreate,
    EntityListResponse,
    EntityResponse,
    EntityUpdate,
)

router = APIRouter()

# Type alias for database session dependency
DBSession = Annotated[AsyncSession, Depends(get_async_session)]


@router.get("", response_model=EntityListResponse)
async def list_entities(
    db: DBSession,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: str | None = Query(None, description="Search by legal name or EIN"),
    is_active: bool | None = Query(None, description="Filter by active status"),
) -> EntityListResponse:
    """List all entities with pagination and filtering.

    Args:
        db: Database session.
        page: Page number (1-indexed).
        size: Number of items per page.
        search: Optional search string for legal name or EIN.
        is_active: Optional filter for active/inactive entities.

    Returns:
        Paginated list of entities.
    """
    # Build base query
    query = select(Entity).where(Entity.deleted_at.is_(None))

    # Apply filters
    if search:
        search_filter = f"%{search}%"
        query = query.where(
            (Entity.legal_name.ilike(search_filter))
            | (Entity.ein.ilike(search_filter))
            | (Entity.dba_names.ilike(search_filter))
        )

    if is_active is not None:
        query = query.where(Entity.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(Entity.legal_name)

    # Execute query
    result = await db.execute(query)
    entities = result.scalars().all()

    # Calculate total pages
    pages = (total + size - 1) // size if total > 0 else 1

    return EntityListResponse(
        items=[EntityResponse.model_validate(e) for e in entities],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.post("", response_model=EntityResponse, status_code=status.HTTP_201_CREATED)
async def create_entity(
    db: DBSession,
    entity_in: EntityCreate,
) -> EntityResponse:
    """Create a new entity.

    Args:
        db: Database session.
        entity_in: Entity creation data.

    Returns:
        Created entity.
    """
    # Check for duplicate EIN if provided
    if entity_in.ein:
        existing = await db.execute(select(Entity).where(Entity.ein == entity_in.ein))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Entity with EIN {entity_in.ein} already exists",
            )

    entity = Entity(**entity_in.model_dump())
    db.add(entity)
    await db.flush()
    await db.refresh(entity)

    return EntityResponse.model_validate(entity)


@router.get("/{entity_id}", response_model=EntityResponse)
async def get_entity(
    db: DBSession,
    entity_id: UUID,
) -> EntityResponse:
    """Get an entity by ID.

    Args:
        db: Database session.
        entity_id: Entity UUID.

    Returns:
        Entity details.

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


@router.patch("/{entity_id}", response_model=EntityResponse)
async def update_entity(
    db: DBSession,
    entity_id: UUID,
    entity_in: EntityUpdate,
) -> EntityResponse:
    """Update an entity.

    Args:
        db: Database session.
        entity_id: Entity UUID.
        entity_in: Entity update data.

    Returns:
        Updated entity.

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

    # Check for duplicate EIN if being updated
    if entity_in.ein and entity_in.ein != entity.ein:
        existing = await db.execute(
            select(Entity).where(Entity.ein == entity_in.ein, Entity.id != entity_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Entity with EIN {entity_in.ein} already exists",
            )

    # Update fields
    update_data = entity_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entity, field, value)

    await db.flush()
    await db.refresh(entity)

    return EntityResponse.model_validate(entity)


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity(
    db: DBSession,
    entity_id: UUID,
) -> None:
    """Soft delete an entity.

    Args:
        db: Database session.
        entity_id: Entity UUID.

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

    # Soft delete
    entity.deleted_at = datetime.now(UTC)
    await db.flush()
