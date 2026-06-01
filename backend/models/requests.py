"""
Request/Response Pydantic models
"""
from pydantic import BaseModel
from typing import Optional, List

# Auth requests
class SetPasswordRequest(BaseModel):
    password: str
    confirm_password: str

class LoginWithPasswordRequest(BaseModel):
    email: str
    password: str

class RegisterUserRequest(BaseModel):
    name: str
    email: str
    password: str
    confirm_password: str
    referred_by: Optional[str] = None

class VerifyEmailCodeRequest(BaseModel):
    email: str
    code: str

class ResendVerificationCodeRequest(BaseModel):
    email: str

class RequestPasswordResetRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    temp_password: str
    new_password: str
    confirm_password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

class UpdatePhoneRequest(BaseModel):
    email: str
    phone: str

# Transaction requests
class RechargeRequest(BaseModel):
    amount: float
    method: str = "pix"

class WithdrawalRequest(BaseModel):
    amount: float
    beneficiary_id: str

class ProcessWithdrawalRequest(BaseModel):
    transaction_id: str
    action: str  # approve, reject
    proof_images: Optional[List[str]] = None
    notes: Optional[str] = None

class UpdateRateRequest(BaseModel):
    ris_to_ves: Optional[float] = None       # Tasa para envíos: 1 RIS = X VES
    ves_to_ris_rate: Optional[float] = None  # Tasa para recargas VES: X VES = 1 RIS  
    brl_to_ris: Optional[float] = None       # Tasa para recargas PIX: 1 BRL = X RIS

class BeneficiaryCreate(BaseModel):
    full_name: str
    id_document: str
    bank: str
    bank_code: Optional[str] = None
    phone_number: Optional[str] = None
    account_number: Optional[str] = None
    payment_type: str = "transferencia"

# Verification requests
class VerificationRequest(BaseModel):
    full_name: str
    document_number: str
    cpf_number: str
    phone_number: str
    id_document_image: str
    cpf_image: str
    selfie_image: str
    # Legacy fields (optional for backward compatibility)
    document_type: Optional[str] = "rg"
    front_image: Optional[str] = None
    back_image: Optional[str] = None
    
class VerificationDecision(BaseModel):
    user_id: str
    action: str  # approve, reject
    reason: Optional[str] = None

# Gestor requests
class GestorBeneficiaryRequest(BaseModel):
    full_name: str
    id_document: str
    bank: str
    bank_code: Optional[str] = None
    phone_number: Optional[str] = None
    account_number: Optional[str] = None
    payment_type: str = "pago_movil"

class GestorTransactionRequest(BaseModel):
    beneficiary_id: str
    amount_ris: float
    client_name: str
    client_phone: Optional[str] = None
    payment_type: str

class GestorRechargeTercerosRequest(BaseModel):
    amount: float

# Admin requests
class ChangeRoleRequest(BaseModel):
    user_id: str
    new_role: str  # user, socio, socio_gestor
    partner_code: Optional[str] = None
    gestor_code: Optional[str] = None

class ResetPasswordAdminRequest(BaseModel):
    user_id: str
