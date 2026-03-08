"""
Routes module - API endpoints organized by domain
"""
from fastapi import APIRouter

# Create main router
api_router = APIRouter(prefix="/api")

# Import sub-routers
from routes.basic import router as basic_router
from routes.gestor import router as gestor_router
from routes.partner import router as partner_router

# Include sub-routers
api_router.include_router(basic_router)
api_router.include_router(gestor_router)
api_router.include_router(partner_router)

__all__ = ["api_router"]
