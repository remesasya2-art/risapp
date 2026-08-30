"""
User related Pydantic models
"""
from pydantic import BaseModel, field_validator
from bson.decimal128 import Decimal128
from typing import Optional, List
from datetime import datetime

class User(BaseModel):
    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    password_hash: Optional[str] = None
    password_set: bool = False
    must_change_password: bool = False
    google_id: Optional[str] = None
    profile_picture: Optional[str] = None
    # De dónde despacha el usuario sus paquetes. Se guarda una vez y el
    # formulario de envíos lo trae precargado: es el dato que más se repite y el
    # que más se tipea mal.
    cep_origen: Optional[str] = None
    balance_ris: float = 0.0
    balance_ves: float = 0.0
    balance_ris_terceros: float = 0.0  # For gestor third-party funds
    balance_usdt: float = 0.0  # Creditos USDT (deposito cripto via NOWPayments, separado de RIS)
    balance_usdc: float = 0.0  # Creditos USDC (deposito cripto via NOWPayments, separado de RIS)
    @field_validator("balance_ris", "balance_ves", "balance_ris_terceros", "balance_usdt", "balance_usdc", mode="before")
    @classmethod
    def coerce_money(cls, v):
        """Tolera saldos guardados como Decimal128 (Mongo) y los entrega como float."""
        if isinstance(v, Decimal128):
            return float(v.to_decimal())
        return v
    role: str = "user"  # user, socio, socio_gestor, admin, super_admin
    permissions: List[str] = []
    verification_status: str = "unverified"  # unverified, pending, verified
    kyc_documents: List[str] = []
    is_admin: bool = False
    push_token: Optional[str] = None
    push_token_web: Optional[str] = None
    web_push_subscription: Optional[dict] = None
    is_online: bool = False
    last_seen: Optional[datetime] = None
    email_verified: bool = False
    email_verification_code: Optional[str] = None
    email_verification_expires: Optional[datetime] = None
    password_reset_token: Optional[str] = None
    password_reset_expires: Optional[datetime] = None
    referred_by: Optional[str] = None
    referral_code: Optional[str] = None
    partner_code: Optional[str] = None
    gestor_code: Optional[str] = None
    is_partner: bool = False
    became_partner_at: Optional[datetime] = None
    became_gestor_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    is_deleted: bool = False

class UserSession(BaseModel):
    session_id: str
    session_token: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    is_active: bool = True

class SessionDataResponse(BaseModel):
    session_token: str
    user: dict
    is_new_user: bool = False
