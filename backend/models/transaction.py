"""
Transaction related Pydantic models
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class ExchangeRate(BaseModel):
    rate_id: str
    ris_to_ves: float
    ves_to_ris: float
    updated_at: Optional[datetime] = None

class VESPaymentInfo(BaseModel):
    cedula: str
    phone: str
    bank: str
    amount: float
    ves_rate: float
    created_at: datetime = None
    expires_at: datetime = None

class Beneficiary(BaseModel):
    beneficiary_id: str
    user_id: str
    full_name: str
    id_document: str
    bank: str
    bank_code: Optional[str] = None
    phone_number: Optional[str] = None
    account_number: Optional[str] = None
    payment_type: str = "transferencia"  # "pago_movil" or "transferencia"
    created_at: datetime = None

class Transaction(BaseModel):
    transaction_id: str
    display_id: Optional[str] = None
    user_id: str
    type: str  # recharge_ris, recharge_ves, withdrawal, transfer
    status: str  # pending, completed, failed, rejected
    amount_input: float
    amount_output: float
    rate: Optional[float] = None
    commission: Optional[float] = None
    beneficiary_id: Optional[str] = None
    beneficiary_data: Optional[dict] = None
    payment_type: Optional[str] = None
    proof_image: Optional[str] = None
    proof_images: List[str] = []
    pending_images: List[str] = []
    whatsapp_active: bool = False
    is_gestor_transaction: bool = False
    gestor_transaction_id: Optional[str] = None
    client_name: Optional[str] = None
    client_phone: Optional[str] = None
    processed_by: Optional[str] = None
    created_at: datetime = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
