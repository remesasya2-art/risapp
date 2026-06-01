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
from routes.notifications import router as notifications_router
from routes.support import router as support_router
from routes.push import router as push_router
from routes.misc import router as misc_router
from routes.webhooks import router as webhooks_router
from routes.recovery import router as recovery_router
from routes.media import router as media_router
from routes.google_drive import router as google_drive_router
from routes.accounting import router as accounting_router
from routes.accounting_v2 import router as accounting_v2_router
from routes.security_2fa import router as security_2fa_router
from routes.payments_card import router as payments_card_router
from routes.kyc_admin import router as kyc_admin_router

# Include sub-routers
api_router.include_router(basic_router)
api_router.include_router(auth_router)
api_router.include_router(transactions_router)
api_router.include_router(admin_router)
api_router.include_router(gestor_router)
api_router.include_router(partner_router)
api_router.include_router(gestor_pix_router)
api_router.include_router(webhook_router)
api_router.include_router(notifications_router)
api_router.include_router(support_router)
api_router.include_router(push_router)
api_router.include_router(misc_router)
api_router.include_router(webhooks_router)
api_router.include_router(recovery_router)
api_router.include_router(media_router)
api_router.include_router(google_drive_router)
api_router.include_router(accounting_router)
api_router.include_router(accounting_v2_router)
api_router.include_router(security_2fa_router)
api_router.include_router(payments_card_router)
api_router.include_router(kyc_admin_router)

__all__ = ["api_router"]
