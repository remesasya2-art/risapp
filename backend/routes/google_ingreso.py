"""Entrar y registrarse con Google.

DOS PUERTAS Y UNA VENTANA

    GET  /auth/google/config      el id de cliente, público, para dibujar el botón
    POST /auth/google             con la credencial de Google: entra, o pide completar
    POST /auth/google/completar   nombre, CPF y términos: la cuenta nace sin contraseña

LA CUENTA QUE YA EXISTE ENTRA COMO SI HUBIERA PUESTO LA CONTRASEÑA

    Mismas guardas —borrada, suspendida, correo en la lista negra—, en el
    mismo orden y con las mismas respuestas que `/auth/login-password`, y el
    MISMO segundo factor obligatorio para el personal y los administradores.
    Google confirma quién es; no reemplaza el segundo paso. Una puerta que lo
    saltara convertiría el 2FA obligatorio en decorativo.

LA CUENTA NUEVA NO NACE EN EL PRIMER PASO

    Google trae el correo y el nombre; el CPF y la aceptación de los términos
    los tiene que dar la persona. Así que el primer paso deja una invitación
    corta (quince minutos, en `twofa_pending`, con su propio propósito) y el
    segundo la consume y crea la cuenta por `services/alta_de_cuenta.py`, el
    mismo lugar por el que nace una cuenta con correo y contraseña.

    La invitación se consume RECIEN cuando todo lo demás pasó: un CPF mal
    tipeado no obliga a volver a tocar el botón de Google.
"""
import asyncio
import logging
import secrets as py_secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from database import db
from routes.dependencies import set_session_cookie
from services import alta_de_cuenta, codigos, cpf_de_la_cuenta, google_ingreso
from models.reglas_publicas import ConfigDelBotonDeGoogle
from models.acciones_de_acceso import MiEntrada
from services import personal as _personal
from services.email_notifications import notify_login
from services.perfil import para_su_dueno

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["Google"])

# El propósito con el que la invitación vive en `twofa_pending`: distinto
# de los del segundo factor, para que un token de uno no sirva en el otro.
PROPOSITO_DEL_REGISTRO = "google_registro"
MINUTOS_PARA_COMPLETAR = 15

# Las mismas frases que la puerta de la contraseña, letra por letra: lo
# borrado contesta como una contraseña equivocada y lo suspendido como lo
# vetado, por los motivos escritos en routes/auth.py.
CREDENCIALES_INVALIDAS = "Credenciales inválidas"
CUENTA_SUSPENDIDA = "Tu cuenta ha sido suspendida. Contacta al administrador."
NO_SE_PUDO_VERIFICAR = "No pudimos verificar tu cuenta de Google. Probá de nuevo."
INVITACION_VENCIDA = ("La invitación de Google venció. Volvé a tocar «Continuar "
                      "con Google» para empezar de nuevo.")


class EntrarConGoogleRequest(BaseModel):
    credential: str = Field(..., max_length=google_ingreso.TOPE_DE_LA_CREDENCIAL)


class CompletarRegistroGoogleRequest(BaseModel):
    pending_token: str = Field(..., max_length=200)
    name: Optional[str] = Field(None, max_length=100)
    cpf_number: str = Field(..., max_length=20)
    referred_by: Optional[str] = Field(None, max_length=40)
    accept_terms: bool = False


@router.get("/config", response_model=ConfigDelBotonDeGoogle)
async def config():
    """Pública a propósito: el id de cliente de Google es público por
    diseño (va en el HTML de cualquier sitio que use el botón). Sin él, el
    navegador no dibuja el botón, y así configurar es poner UNA variable."""
    return {"client_id": google_ingreso.id_de_cliente()}


@router.post("", response_model=MiEntrada, response_model_exclude_unset=True)
async def entrar(request: Request, response: Response, body: EntrarConGoogleRequest):
    from routes.security_2fa import frenar

    # 20/15min por IP, como el ingreso con contraseña: es la misma puerta
    # con otra llave, y cada llamada es un viaje a Google.
    await frenar(request, "auth.google", "20/15minutes")

    if not google_ingreso.configurado():
        raise HTTPException(status_code=503,
                            detail="Entrar con Google no está disponible por ahora.")
    try:
        quien = await asyncio.to_thread(google_ingreso.verificar_credencial, body.credential)
    except google_ingreso.CredencialInvalida as e:
        logger.info("credencial de Google rechazada: %s", e)
        raise HTTPException(status_code=401, detail=NO_SE_PUDO_VERIFICAR)

    user = await db.users.find_one({"email": quien["email"]})
    if user is None:
        return await _empezar_el_registro(quien)

    resultado = await _entrar_a_la_cuenta(request, user, quien)
    if resultado.get("session_token"):
        set_session_cookie(response, resultado["session_token"])
    return resultado


async def _entrar_a_la_cuenta(request: Request, user: dict, quien: dict) -> dict:
    from routes.security_2fa import ADMIN_ROLES, _create_pending_token, issue_session_token

    # Las tres guardas de la contraseña, en el mismo orden. Acá van DESPUES
    # de verificar la credencial por el mismo motivo por el que allá van
    # después de la contraseña: para preguntar si una cuenta está baneada
    # hay que ser su dueño.
    if user.get("is_deleted"):
        raise HTTPException(status_code=401, detail=CREDENCIALES_INVALIDAS)
    if user.get("is_banned") or user.get("status") == "suspended":
        raise HTTPException(status_code=403, detail=CUENTA_SUSPENDIDA)
    if await db.blacklist.find_one({"type": "email", "value": user["email"]}):
        raise HTTPException(status_code=403, detail=CUENTA_SUSPENDIDA)

    role = user.get("role", "user")
    is_admin = role in ADMIN_ROLES
    twofa_enabled = bool(user.get("two_factor_enabled", False))
    obliga_dos_pasos = _personal.exige_dos_pasos(user)

    # Personal sin segundo factor: enrolamiento obligatorio antes de la
    # sesión. Con Google o con contraseña, la regla es una sola.
    if obliga_dos_pasos and not twofa_enabled:
        pending = await _create_pending_token(user["user_id"], purpose="2fa_enroll")
        return {
            "message": "Configura 2FA para continuar",
            "two_factor_enrollment_required": True,
            "pending_token": pending,
            "email": user["email"],
            "user_id": user["user_id"],
        }
    # La condición vive en `services/personal.py`: acá estaba copiada de
    # `routes/auth.py`, palabra por palabra. Ver el comentario de allá.
    if _personal.pide_dos_pasos(user):
        pending = await _create_pending_token(user["user_id"], purpose="2fa_login")
        return {
            "message": "Ingresa tu código 2FA para continuar",
            "two_factor_required": True,
            "pending_token": pending,
            "email": user["email"],
        }

    token = await issue_session_token(user, request=request, two_factor_used=False)

    cambios = {"last_login": datetime.now(timezone.utc)}
    # El identificador de la cuenta de Google se guarda la primera vez y no
    # se pisa: si un día cambia para el mismo correo, es algo para mirar,
    # no para sobrescribir en silencio.
    if not user.get("google_sub"):
        cambios["google_sub"] = quien["sub"]
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": cambios})

    logger.info("User %s logged in with Google", user["user_id"])
    try:
        await notify_login(email=user["email"], user_name=user.get("name", "Usuario"),
                           device="Google")
    except Exception as e:                                # pragma: no cover
        logger.warning(f"Failed to send login notification: {e}")

    return {
        "message": "Login exitoso",
        "session_token": token,
        "user": para_su_dueno(user),
        "must_change_password": user.get("must_change_password", False),
    }


async def _empezar_el_registro(quien: dict) -> dict:
    # La lista negra se mira ACA, antes de dejar una invitación: un correo
    # vetado no tiene por qué llegar al formulario del CPF.
    if await db.blacklist.find_one({"type": "email", "value": quien["email"]}):
        raise HTTPException(status_code=400,
                            detail="Este correo no puede registrarse. Contacta a soporte.")
    ahora = datetime.now(timezone.utc)
    token = py_secrets.token_urlsafe(24)
    await db.twofa_pending.insert_one({
        "_id": uuid.uuid4().hex,
        "token": token,
        "user_id": None,
        "purpose": PROPOSITO_DEL_REGISTRO,
        "email": quien["email"],
        "nombre": quien["nombre"],
        "google_sub": quien["sub"],
        "created_at": ahora,
        "expires_at": ahora + timedelta(minutes=MINUTOS_PARA_COMPLETAR),
        "consumed": False,
    })
    return {
        "registro_incompleto": True,
        "pending_token": token,
        "email": quien["email"],
        "nombre": quien["nombre"],
    }


@router.post("/completar", response_model=MiEntrada, response_model_exclude_unset=True)
async def completar(request: Request, response: Response,
                    body: CompletarRegistroGoogleRequest):
    from routes.security_2fa import _consume_pending_token, frenar, issue_session_token

    # 10/hora por IP, como el registro con correo: cada llamada puede crear
    # una cuenta.
    await frenar(request, "auth.google.completar", "10/hour")

    if not body.accept_terms:
        raise HTTPException(status_code=400,
                            detail="Tenés que aceptar los Términos y la Política de Privacidad.")

    ahora = datetime.now(timezone.utc)
    pendiente = await db.twofa_pending.find_one({
        "token": body.pending_token, "purpose": PROPOSITO_DEL_REGISTRO,
        "consumed": False, "expires_at": {"$gt": ahora},
    })
    if not pendiente:
        raise HTTPException(status_code=400, detail=INVITACION_VENCIDA)

    # El correo sale de la invitación, NUNCA del pedido: es lo que Google
    # confirmó. Un correo en el cuerpo sería un correo que eligió quien
    # manda el pedido.
    email = pendiente["email"]

    if await db.blacklist.find_one({"type": "email", "value": email}):
        raise HTTPException(status_code=400,
                            detail="Este correo no puede registrarse. Contacta a soporte.")
    if await db.users.find_one({"email": email}, {"_id": 1}):
        raise HTTPException(status_code=400,
                            detail="Ese correo ya tiene una cuenta. Entrá con Google desde "
                                   "«Iniciar sesión».")

    nombre = (body.name or "").strip() or (pendiente.get("nombre") or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="Decinos tu nombre.")

    # El código de quien refirió, con las mismas reglas que el registro con
    # correo: se normaliza y, si no existe, se rechaza con el motivo.
    codigo = codigos.normalizar(body.referred_by or "")
    if codigo and not await db.users.find_one({"referral_code": codigo}, {"_id": 1}):
        raise HTTPException(
            status_code=400,
            detail="Ese código de invitación no existe. Revisá el enlace, "
                   "o dejá el campo vacío para registrarte sin código.")

    try:
        cpf = await cpf_de_la_cuenta.revisar_para_registrar(db, body.cpf_number, correo=email)
    except (cpf_de_la_cuenta.CpfInvalido, cpf_de_la_cuenta.CpfVetado,
            cpf_de_la_cuenta.CpfEnUso) as e:
        raise HTTPException(status_code=400, detail=str(e))

    # RECIEN ACA se consume la invitación: todo lo de arriba puede fallar y
    # la persona corregir el dato sin volver a Google. Y se consume en un
    # solo paso atómico: dos pedidos con el mismo token crean UNA cuenta.
    if not await _consume_pending_token(body.pending_token):
        raise HTTPException(status_code=400, detail=INVITACION_VENCIDA)

    try:
        user = await alta_de_cuenta.crear(
            db, email=email, name=nombre, password_hash=None,
            referred_by=codigo or None, cpf_number=cpf,
            google_sub=pendiente.get("google_sub"))
    except alta_de_cuenta.NoSePudoCrear as e:
        raise HTTPException(status_code=400, detail=str(e))

    token = await issue_session_token(user, request=request, two_factor_used=False)
    set_session_cookie(response, token)
    logger.info("Registro completado con Google: %s", user["user_id"])
    return {
        "message": "Registro completado exitosamente",
        "session_token": token,
        "user": para_su_dueno(user),
    }
