"""
Routes module - API endpoints organized by domain
"""
from fastapi import APIRouter

# Create main router
api_router = APIRouter(prefix="/api")

# Import sub-routers
from routes.basic import router as basic_router
from routes.auth import router as auth_router
from routes.transactions import router as transactions_router
from routes.admin import router as admin_router
from routes.gestor import router as gestor_router
from routes.partner import router as partner_router
from routes.gestor_pix import router as gestor_pix_router, webhook_router

# Include sub-routers
api_router.include_router(basic_router)
api_router.include_router(auth_router)
api_router.include_router(transactions_router)
api_router.include_router(admin_router)
api_router.include_router(gestor_router)
api_router.include_router(partner_router)
api_router.include_router(gestor_pix_router)
api_router.include_router(webhook_router)

__all__ = ["api_router"]
