"""API v1 router configuration.

Every ``/api/v1`` route requires the ``X-API-Key`` header (see
``llc_manager.core.auth``).
"""

from fastapi import APIRouter, Depends

from llc_manager.api.v1.endpoints import documents, entities
from llc_manager.core.auth import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])

router.include_router(entities.router, prefix="/entities", tags=["Entities"])
router.include_router(documents.router, prefix="/documents", tags=["Documents"])
