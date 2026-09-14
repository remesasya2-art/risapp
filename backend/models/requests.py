"""
Request/Response Pydantic models
"""
from pydantic import AliasChoices, BaseModel, Field
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

    # El CPF se pide acá y no más adelante porque es lo que ata la cuenta a una
    # persona: un CPF, una cuenta. Se valida de verdad —los dos dígitos
    # verificadores— en `services/cpf.py`, no contando once cifras.
    #
    # Llega como texto libre («123.456.789-09» o «12345678909»): la pantalla
    # lo formatea mientras se escribe y el servidor lo normaliza antes de
    # guardarlo, así que las dos formas son el mismo documento.
    cpf_number: str

    # ─── EL NOMBRE DEL CAMPO, Y POR QUE ESTAN LOS DOS ────────────────────
    #
    # La pantalla de registro manda el código de referido con el nombre
    # `referral_code` (frontend/src/pages/Register.jsx). Este modelo lo
    # declaraba SOLO como `referred_by`, y Pydantic con un campo que no
    # conoce no se queja: lo ignora. Así que `referred_by` llegaba en `None`
    # siempre y el enlace de referido NUNCA FUNCIONO. Ni un error, ni un 400,
    # ni una línea en el registro: un nombre distinto y silencio.
    #
    # Se acepta por los dos nombres, no por indecisión:
    #
    #   · `referral_code` es el que manda la pantalla que está desplegada, y
    #     el bundle vive en el navegador de cada visitante. Un usuario con la
    #     página abierta desde ayer sigue mandando ese nombre después de
    #     desplegar esto.
    #   · `referred_by` es el nombre del campo en el documento del usuario y
    #     el que usan los tests y los scripts. Sacarlo obligaría a tocarlos
    #     para nada.
    #
    # El atributo se sigue llamando `referred_by` para que coincida con la
    # base. Quien agregue un tercer nombre tiene que agregarlo acá, y
    # `tests/test_el_codigo_de_referido_llega.py` se pone rojo si la pantalla
    # empieza a mandar uno que esta lista no tenga.
    referred_by: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("referral_code", "referred_by"),
    )

class VerifyEmailCodeRequest(BaseModel):
    email: str
    code: str

class ResendVerificationCodeRequest(BaseModel):
    email: str

class PedirCodigoDeCambioRequest(BaseModel):
    current_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str
    # El código que llegó al correo. Ver `routes/auth.change_password`.
    codigo: str

class SetNewPasswordRequest(BaseModel):
    """La contraseña que elige quien llega obligado a cambiarla.

    NO PIDE LA ACTUAL, Y ESA ES LA DIFERENCIA CON `ChangePasswordRequest`

        Quien llega a esta pantalla tiene una contraseña temporal que le puso
        un administrador —porque avisó que le tomaron la cuenta, o porque
        perdió la suya—. Pedirle la actual sería pedirle que copie de nuevo lo
        que acaba de tipear para entrar, y pedirle un código al correo sería
        una segunda vuelta para alguien que ya demostró que entra a esa
        casilla si el reseteo llegó por ahí.

        Lo que autoriza a saltarse las dos comprobaciones es una sola cosa: que
        la cuenta tenga puesta la marca `must_change_password`. Sin esa marca
        esta ruta no hace nada, y el motivo está escrito en
        `routes/auth.set_new_password`.
    """
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
    idempotency_key: Optional[str] = None

class ProcessWithdrawalRequest(BaseModel):
    transaction_id: str
    action: str  # approve, reject
    proof_images: Optional[List[str]] = None
    notes: Optional[str] = None

class UpdateRateRequest(BaseModel):
    ris_to_ves: Optional[float] = None       # Tasa para envíos: 1 RIS = X VES
    ves_to_ris_rate: Optional[float] = None  # Tasa para recargas VES: X VES = 1 RIS  
    brl_to_ris: Optional[float] = None       # Tasa para recargas PIX: 1 BRL = X RIS
    usdtris_to_ves: Optional[float] = None   # Tasa para envíos con saldo USDT: 1 USDT = X VES
    usdcris_to_ves: Optional[float] = None   # Tasa para envíos con saldo USDC: 1 USDC = X VES

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
    new_role: str  # user, super_admin
    partner_code: Optional[str] = None
    gestor_code: Optional[str] = None

class ResetPasswordAdminRequest(BaseModel):
    user_id: str
