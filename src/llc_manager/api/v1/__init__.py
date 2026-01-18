"""API v1 router configuration."""

from fastapi import APIRouter

from llc_manager.api.v1.endpoints import entities

router = APIRouter()

router.include_router(entities.router, prefix="/entities", tags=["Entities"])
