"""
Authentication routes
"""
import uuid
import re
import secrets
import logging
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException, Header, Response
from typing import Optional
from pydantic import BaseModel, Field

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from database import db
from services import sesiones
from services.money import from_db, to_float, to_decimal128
from models.user import User, UserSession
from models.requests import (
    SetPasswordRequest, LoginWithPasswordRequest, RegisterUserRequest,
    VerifyEmailCodeRequest, ResendVerificationCodeRequest,
    ChangePasswordRequest, PedirCodigoDeCambioRequest, SetNewPasswordRequest
)
from routes.dependencies import get_current_user, set_session_cookie, clear_session_cookie
from services import alta_de_cuenta, codigos, correo, cpf_de_la_cuenta
from services.email import send_verification_email
from services.email_notifications import notify_login, notify_password_change
from utils.security import (hash_password_async, validate_password,
                            verify_password_async)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# La lista de lo que una persona ve de su propia cuenta vive en
# `services/perfil.py`, y no acá, porque hay CINCO rutas que le mandan ese mismo
# documento al navegador —ésta y las cuatro puertas de entrada— y las cinco
# alimentan el mismo `setUser()` del frontend. Con una lista por ruta, acordarse
# de tapar un campo en una no protegía a las otras cuatro: así fue como
# `pin_hash` terminó tapado sólo en la de la huella. El motivo largo está allá.
#
# Se reexportan los nombres porque los tests y otras rutas los buscan acá.
from models.cuenta import EstadoDeLaClave, PerfilDelDueno                  # noqa: E402
from models.acciones_de_acceso import (MiCodigoReenviado, MiEntrada, MiInvitacion,  # noqa: E402
                                       MiLatido, MiMensaje, MiRegistroEmpezado)
from services.perfil import (                                      # noqa: E402
    LO_QUE_VE_SU_DUENO, LOS_SALDOS, para_su_dueno, terminar_de_armar)


@router.get("/me", response_model=Optional[PerfilDelDueno], response_model_exclude_unset=True)
async def get_me(current_user: User = Depends(get_current_user)):
    """El perfil de quien pregunta. Dos capas de lo permitido: la proyección
    (`LO_QUE_VE_SU_DUENO`) y el contrato, generado de la MISMA lista para que
    no puedan divergir (models/cuenta.py). `exclude_unset` hace que un campo
    que la cuenta no tiene siga sin salir, en vez de salir como `null`: la
    pantalla distingue «no está» de «está vacío» en más de un lugar."""
    user = await db.users.find_one({"user_id": current_user.user_id},
                                   LO_QUE_VE_SU_DUENO)
    if user:
        user['password_set'] = user.get('password_set', False)
        # La proyección ya recortó: acá sólo quedan los saldos a número y el
        # bono interpretado, que es lo mismo que hacen las cuatro puertas.
        terminar_de_armar(user)
    return user


from models.cuenta import MiApariencia                              # noqa: E402


@router.put("/me/apariencia", response_model=MiApariencia)
async def guardar_apariencia(pedido: MiApariencia,
                             current_user: User = Depends(get_current_user)):
    """Guarda en la cuenta si la persona quiere la app clara, oscura o como
    diga su aparato.

    EN LA CUENTA Y NO SOLO EN EL NAVEGADOR, por pedido expreso: quien la
    eligió en el celular la encuentra igual en la computadora. El navegador
    guarda además una copia, pero sólo para pintar bien la portada y el login,
    que se ven antes de saber de quién es la cuenta.

    Se escribe con `$set` sobre un único campo y el filtro es el `user_id` de
    la sesión: por acá no se puede tocar otro dato de la cuenta ni la cuenta
    de otro, y el contrato de entrada no acepta más que los tres valores."""
    await db.users.update_one({"user_id": current_user.user_id},
                              {"$set": {"apariencia": pedido.apariencia}})
    return {"apariencia": pedido.apariencia}


@router.post("/logout", response_model=MiMensaje, response_model_exclude_unset=True)
async def logout(request: Request, response: Response, current_user: User = Depends(get_current_user)):
    """Logout current session"""
    # Resolver el token igual que get_current_user: cookie -> Authorization: Bearer -> X-Session-ID
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        token = request.headers.get("X-Session-ID")
    # Invalidar la sesion en el servidor: borrar por token y todas las sesiones del usuario
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    await db.user_sessions.delete_many({"user_id": current_user.user_id})
    clear_session_cookie(response)
    return {"message": "Sesión cerrada exitosamente"}

@router.post("/register", response_model=MiRegistroEmpezado, response_model_exclude_unset=True)
async def register_user(request: RegisterUserRequest, pedido: Request):
    """Register new user with email verification"""
    from routes.security_2fa import frenar

    # 10/hora. Cada llamada crea una cuenta pendiente y manda un correo desde
    # NUESTRO dominio: sin tope, una IP puede fabricar cuentas en volumen y, de
    # paso, usar el servidor para bombardear una casilla ajena. Diez por hora es
    # holgado para una persona y cierra las dos cosas.
    await frenar(pedido, "auth.register", "10/hour")

    # Validate email
    email_regex = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    if not re.match(email_regex, request.email):
        raise HTTPException(status_code=400, detail="Email inválido")
    
    email_lower = request.email.lower().strip()

    # Rechazar correos en la lista negra
    if await db.blacklist.find_one({"type": "email", "value": email_lower}):
        raise HTTPException(status_code=400, detail="Este correo no puede registrarse. Contacta a soporte.")

    # ─── El CPF ──────────────────────────────────────────────────────────
    #
    # Se comprueba ACA, antes de crear nada: que esté bien formado, que no esté
    # vetado, y que no sea el de otra cuenta. Un CPF, una cuenta.
    #
    # Por qué en el registro y no recién en la primera recarga: la recarga lo
    # pide igual —es la identificación del pagador que exige PIX— y pedirlo dos
    # veces obliga a la persona a tipear el mismo número dos veces, con lo que
    # eso trae de dedos equivocados. El de la verificación también le va a
    # llegar puesto desde acá.
    try:
        cpf_normalizado = await cpf_de_la_cuenta.revisar_para_registrar(
            db, request.cpf_number, correo=email_lower)
    except (cpf_de_la_cuenta.CpfInvalido, cpf_de_la_cuenta.CpfVetado,
            cpf_de_la_cuenta.CpfEnUso) as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check existing user
    existing = await db.users.find_one({"email": email_lower})
    if existing:
        if existing.get("email_verified", False):
            raise HTTPException(status_code=400, detail="Este email ya está registrado")
        else:
            await db.users.delete_one({"email": email_lower})
            await db.pending_verifications.delete_many({"email": email_lower})
            # La cuenta sin verificar que se acaba de borrar podía tener su CPF
            # anclado. Si no se suelta acá, ese CPF queda anclado a una cuenta
            # que ya no existe: bloqueado para todos, sin dueño que lo use, y
            # sin nadie que sepa que hay que limpiarlo.
            await cpf_de_la_cuenta.soltar_el_ancla(
                db, existing.get("cpf_number"), existing.get("user_id") or "")
    
    # Validate passwords
    if request.password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")
    
    is_valid, message = validate_password(request.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)

    # ─── El código de quien refirió ──────────────────────────────────────
    #
    # `codigos.normalizar` y no `.strip().upper()`: el código se comparte por
    # WhatsApp y llega pegado con espacios adentro («REF 3A9F 2B01»), que
    # `strip` no toca porque sólo saca los de las puntas.
    #
    # SE RECHAZA UN CODIGO QUE NO EXISTE, en vez de guardarlo o ignorarlo.
    # Ignorarlo es lo que venía pasando de hecho, y es la peor de las tres: el
    # que se registró por el enlace de un amigo pierde su bono, el amigo
    # pierde el suyo, y ninguno de los dos se enteró nunca. Un 400 con el
    # motivo le da la chance de mirar el enlace otra vez.
    #
    # Esto deja saber si un código existe, probándolo. No es un problema acá:
    # el código son ocho símbolos —miles de millones de combinaciones— y esta
    # ruta está frenada en diez pedidos por hora y por IP, que ahora es una IP
    # que no se puede elegir (services/borde.py). Y lo que se averigua es que
    # el código existe, no de quién es.
    codigo_de_quien_refiere = codigos.normalizar(request.referred_by or "")
    if codigo_de_quien_refiere:
        # Proyección por lista de lo permitido: acá alcanza con saber que hay
        # alguien. Sin proyección esto traería el usuario entero —documento,
        # teléfono, saldos— para responder que sí o que no.
        quien_refiere = await db.users.find_one(
            {"referral_code": codigo_de_quien_refiere}, {"_id": 1})
        if not quien_refiere:
            raise HTTPException(
                status_code=400,
                detail="Ese código de invitación no existe. Revisá el enlace, "
                       "o dejá el campo vacío para registrarte sin código.")

    # Generate verification code
    verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    
    # Store pending registration
    pending = {
        "email": email_lower,
        "name": request.name.strip(),
        "password_hash": await hash_password_async(request.password),
        "verification_code": verification_code,
        "code_expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
        "created_at": datetime.now(timezone.utc),
        "attempts": 0,
        # Ya normalizado y comprobado arriba. Se guarda vacío como None y no
        # como "" para que el documento del usuario diga «sin código» de una
        # sola forma.
        "referred_by": codigo_de_quien_refiere or None,
        # Ya normalizado y comprobado arriba. Viaja acá porque la cuenta no
        # existe hasta que se verifica el correo.
        "cpf_number": cpf_normalizado,
    }
    
    # ─── Se toma el CPF ──────────────────────────────────────────────────
    #
    # ACA, y no cuando confirme el correo. Entre una cosa y la otra pasan hasta
    # quince minutos, y durante esos quince minutos el CPF no estaba en ninguna
    # cuenta: otra persona se registraba con el mismo y pasaba igual. Así
    # aparecieron los CPF repetidos que hoy hay en la base.
    #
    # Va después de todas las comprobaciones —contraseña, código de invitación—
    # para no tomarle el CPF a nadie por un registro que igual iba a fallar.
    # Lo primero, soltar lo que este mismo correo hubiera tomado antes: quien se
    # equivocó de CPF y vuelve a empezar no puede dejar el equivocado tomado
    # quince minutos por nada. `salvo` deja en pie el que está por tomar de
    # nuevo, para no soltarlo un instante y que otro se lo lleve en el medio.
    await cpf_de_la_cuenta.soltar_las_del_correo(
        db, email_lower, salvo=cpf_normalizado)
    try:
        await cpf_de_la_cuenta.tomar(db, cpf_normalizado, correo=email_lower)
    except (cpf_de_la_cuenta.CpfInvalido, cpf_de_la_cuenta.CpfEnUso) as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.pending_verifications.delete_many({"email": email_lower})
    await db.pending_verifications.insert_one(pending)
    
    # Send email
    email_sent = await send_verification_email(email_lower, verification_code, request.name.strip())
    
    # Sin el correo: el registro lo lee más gente de la que tiene por qué
    # saber quién se está registrando, y queda escrito en un servicio de
    # terceros. Que hubo un registro es lo que hace falta para operar.
    logger.info("Registro iniciado")
    
    return {
        "message": "Código de verificación enviado a tu correo",
        "email": email_lower,
        "email_sent": email_sent,
        "code_expires_in_minutes": 15
    }

@router.post("/verify-email", response_model=MiEntrada, response_model_exclude_unset=True)
async def verify_email_code(request: VerifyEmailCodeRequest, response: Response,
                            pedido: Request):
    """Verify email code and complete registration"""
    from routes.security_2fa import frenar

    # 20/15min. Adentro hay un contador de cinco intentos por solicitud, pero
    # `resend-verification-code` lo devuelve a cero. Ese reenvío ya está frenado
    # a 5/15min, así que el techo era 25 pruebas cada 15 minutos contra un código
    # de seis dígitos; ahora hay además un tope que no depende de esa cadena.
    await frenar(pedido, "auth.verify_email", "20/15minutes")

    email_lower = request.email.lower().strip()
    
    pending = await db.pending_verifications.find_one({"email": email_lower})
    if not pending:
        raise HTTPException(status_code=400, detail="No hay verificación pendiente")
    
    # Check expiration
    expires_at = pending["code_expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    if datetime.now(timezone.utc) > expires_at:
        await db.pending_verifications.delete_one({"email": email_lower})
        # El registro murió, así que el CPF vuelve a estar libre en el acto. La
        # caducidad de la base haría lo mismo sola, pero hasta un minuto
        # después: no hay motivo para que el dueño del CPF espere eso.
        await cpf_de_la_cuenta.soltar_las_del_correo(db, email_lower)
        raise HTTPException(status_code=400, detail="El código ha expirado")
    
    # Check attempts
    if pending.get("attempts", 0) >= 5:
        await db.pending_verifications.delete_one({"email": email_lower})
        await cpf_de_la_cuenta.soltar_las_del_correo(db, email_lower)
        raise HTTPException(status_code=400, detail="Demasiados intentos fallidos")
    
    # Verify code
    if pending["verification_code"] != request.code.strip():
        await db.pending_verifications.update_one(
            {"email": email_lower},
            {"$inc": {"attempts": 1}}
        )
        raise HTTPException(status_code=400, detail="Código incorrecto")
    
    # LA CUENTA NACE EN `services/alta_de_cuenta.py`, que es el mismo lugar
    # por el que nace una cuenta con Google: un solo sitio decide con qué
    # campos nace una cuenta, ancla el CPF antes del insert y libera el bono.
    # Acá vivían esos treinta renglones; se fueron para no tener dos copias.
    try:
        user = await alta_de_cuenta.crear(
            db, email=email_lower, name=pending["name"],
            password_hash=pending["password_hash"],
            referred_by=pending.get("referred_by"),
            cpf_number=pending.get("cpf_number"))
    except alta_de_cuenta.NoSePudoCrear as e:
        raise HTTPException(status_code=400, detail=str(e))
    user_id = user["user_id"]

    await db.pending_verifications.delete_one({"email": email_lower})

    # ESTA PUERTA NO MIRA EL SEGUNDO FACTOR, Y ES CORRECTO. POR QUE:
    #
    #   La cuenta se acaba de crear tres líneas más arriba, y `crear` rechaza
    #   un correo repetido. O sea que la sesión que sale de acá es siempre de
    #   una cuenta nacida hace segundos, y una cuenta recién nacida no puede
    #   tener el segundo factor activado: no hubo cuándo.
    #
    #   QUE LA VOLVERIA UN AGUJERO: que algún día esta ruta sirva para que
    #   una cuenta que YA EXISTE vuelva a entrar —por ejemplo, reverificando
    #   el correo—. Ahí sí habría que preguntar `personal.pide_dos_pasos` y
    #   devolver un `pending_token`, como hacen el ingreso con contraseña y
    #   el de Google. `tests/test_segundo_factor_del_cliente.py` tiene la
    #   lista de puertas exentas con su motivo, y se pone rojo si aparece una
    #   puerta nueva que emite sesión sin declarar por qué no mira.
    #
    # Create session
    session_token = secrets.token_urlsafe(32)
    session = {
        "session_id": f"sess_{uuid.uuid4().hex[:12]}",
        "session_token": session_token,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "is_active": True
    }
    await db.user_sessions.insert_one(session)
    set_session_cookie(response, session_token)
    
    logger.info("Registro completado: %s", user_id)
    
    return {
        "message": "Registro completado exitosamente",
        "session_token": session_token,
        "user": {
            "user_id": user_id,
            "email": email_lower,
            "name": pending["name"],
            "role": "user"
        }
    }

@router.post("/resend-verification-code", response_model=MiCodigoReenviado, response_model_exclude_unset=True)
async def resend_verification_code(request: Request, body: ResendVerificationCodeRequest):
    """Resend verification code"""
    from routes.security_2fa import frenar

    async def _do_resend(request: Request, body: ResendVerificationCodeRequest):
        # 5/15min: sin esto, resend resetea el contador de intentos de
        # /verify-email a 0 cada vez, permitiendo fuerza bruta indefinida del
        # código de 6 dígitos.
        await frenar(request, "auth.resend_verification", "5/15minutes")
        email_lower = body.email.lower().strip()

        pending = await db.pending_verifications.find_one({"email": email_lower})
        if not pending:
            raise HTTPException(status_code=400, detail="No hay verificación pendiente")

        verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])

        await db.pending_verifications.update_one(
            {"email": email_lower},
            {
                "$set": {
                    "verification_code": verification_code,
                    "code_expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
                    "attempts": 0
                }
            }
        )

        # Si la reserva del CPF no acompañara estos minutos nuevos, el CPF
        # quedaría libre mientras el código todavía sirve, y otro podría
        # tomarlo justo antes de que el dueño confirme.
        await cpf_de_la_cuenta.renovar_las_del_correo(db, email_lower)

        email_sent = await send_verification_email(email_lower, verification_code, pending["name"])

        return {
            "message": "Nuevo código enviado",
            "email_sent": email_sent
        }

    return await _do_resend(request, body)

@router.post("/login-password", response_model=MiEntrada, response_model_exclude_unset=True)
async def login_with_password(request: Request, response: Response, body: LoginWithPasswordRequest):
    """Login with email and password.

    Security layer:
    - super_admin with 2FA enabled → returns pending_token (frontend must POST /api/auth/2fa/verify)
    - super_admin without 2FA → returns pending_token + enrollment_required=true
    - admin/super_admin sessions expire in 30 min; regular users in 7 days
    """
    # Rate limit imported lazily to avoid circular imports
    from routes.security_2fa import (
        frenar, issue_session_token, _create_pending_token, ADMIN_ROLES,
    )

    async def _do_login(request: Request, body):
        # 20/15min por IP — bloquea fuerza bruta pero NO penaliza a usuarios
        # reales detrás de NAT/oficina/wifi compartido. La defensa fuerte
        # contra ataques a cuentas privilegiadas es el 2FA obligatorio.
        await frenar(request, "auth.login", "20/15minutes")
        email_lower = body.email.lower().strip()

        user = await db.users.find_one({"email": email_lower})
        if not user:
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        if not user.get("email_verified"):
            raise HTTPException(status_code=401, detail="Email no verificado")

        if not user.get("password_set") or not user.get("password_hash"):
            raise HTTPException(status_code=401, detail="No tienes contraseña configurada")

        if not await verify_password_async(body.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        # ─── Las tres guardas, y por que van DESPUES de la contraseña ─────
        #
        # LO QUE FALTABA
        #
        #     Acá se miraba SOLO `status == "suspended"`, y el botón de banear
        #     del panel no escribe ese campo: escribe `is_banned`
        #     (`/admin/ban`, en routes/admin.py). O sea que banear no cerraba
        #     esta puerta.
        #
        #     Comprobado corriéndolo antes de tocar nada: una cuenta con
        #     `is_banned: True` recibía «Login exitoso» y una sesión nueva. Lo
        #     mismo una con `is_deleted: True`.
        #
        #     Para un usuario común el daño quedaba contenido —entraba, y
        #     después `get_current_user` le daba 403 en cada pantalla—, pero
        #     eso no es una defensa: es una casualidad de por dónde pasa cada
        #     ruta. Para un colaborador baneado no quedaba contenido en
        #     absoluto, porque las 14 rutas de `admin_routes.py` entraban por
        #     una puerta que tampoco miraba `is_banned`.
        #
        #     Y el correo en la lista negra se miraba sólo en el registro. Una
        #     cuenta vieja cuyo correo se agrega a mano a la lista seguía
        #     entrando: la puerta del registro no la alcanza, ya está creada.
        #
        # POR QUE ACA Y NO ARRIBA
        #
        #     Puestas antes de comprobar la contraseña, estas tres guardas
        #     contestan preguntas que nadie debería poder hacer sin la clave:
        #     «¿esta cuenta está baneada?», «¿este correo está en la lista
        #     negra?». Cualquiera con una lista de correos las averigua.
        #     Detrás de la contraseña, para contestarlas hay que ser el dueño.
        #
        #     (Las de arriba —correo sin verificar, sin contraseña puesta— ya
        #     estaban antes y filtran lo mismo. No se mueven en este cambio
        #     porque la pantalla de entrada usa esas dos respuestas para
        #     mandar a verificar o a poner contraseña; moverlas es otro cambio
        #     con otra pantalla que mirar.)
        #
        # POR QUE LA LISTA NEGRA CONTESTA LO MISMO QUE EL BANEO
        #
        #     Decir «tu correo está vetado» le confirma a quien prueba correos
        #     ajenos cuáles están en la lista. Y lo borrado contesta lo mismo
        #     que una contraseña equivocada, por la misma razón: que no se
        #     pueda distinguir una cuenta que existió de una que nunca existió.
        if user.get("is_deleted"):
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        if user.get("is_banned") or user.get("status") == "suspended":
            raise HTTPException(status_code=403, detail="Tu cuenta ha sido suspendida. Contacta al administrador.")

        if await db.blacklist.find_one({"type": "email", "value": email_lower}):
            raise HTTPException(status_code=403, detail="Tu cuenta ha sido suspendida. Contacta al administrador.")

        from services import personal as _personal

        role = user.get("role", "user")
        is_admin = role in ADMIN_ROLES
        twofa_enabled = bool(user.get("two_factor_enabled", False))
        # Quién no puede operar con contraseña sola. La lista vive en
        # services/personal.py para que sea UNA sola, y hoy incluye a los
        # colaboradores de `agent` para arriba, más cualquiera que RRHH haya
        # marcado como personal.
        obliga_dos_pasos = _personal.exige_dos_pasos(user)

        # Personal sin 2FA → enrolamiento obligatorio antes de la sesión.
        #
        # Antes esto era sólo para `super_admin`, y el personal de RRHH se da
        # de alta con rol `admin`: una cuenta con permisos para aprobar KYC,
        # aprobar recargas y mover saldos entraba con contraseña sola. El
        # enrolamiento pasa acá mismo, en el login, así que nadie queda
        # afuera: se sale con sesión, no con un rechazo.
        if obliga_dos_pasos and not twofa_enabled:
            pending = await _create_pending_token(user["user_id"], purpose="2fa_enroll")
            return {
                "message": "Configura 2FA para continuar",
                "two_factor_enrollment_required": True,
                "pending_token": pending,
                "email": user["email"],
                "user_id": user["user_id"],
            }

        # Ya lo tiene puesto → se le pide el código.
        #
        # LA CONDICION VIVE EN `services/personal.py` Y NO ACA. Estaba escrita
        # a mano —`(is_admin or obliga_dos_pasos) and twofa_enabled`— y
        # copiada igual en la puerta de Google: dos copias de la misma regla.
        # Y dejaba afuera al cliente que lo activaba por su cuenta, que no
        # entraba por ninguna de las dos ramas.
        if _personal.pide_dos_pasos(user):
            pending = await _create_pending_token(user["user_id"], purpose="2fa_login")
            return {
                "message": "Ingresa tu código 2FA para continuar",
                "two_factor_required": True,
                "pending_token": pending,
                "email": user["email"],
            }

        # Usuario común. Un admin no llega acá sin 2FA: lo frenó el bloque de arriba.
        token = await issue_session_token(user, request=request, two_factor_used=False)

        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"last_login": datetime.now(timezone.utc)}}
        )

        logger.info(f"User {user['user_id']} logged in with password (2FA={twofa_enabled})")

        try:
            await notify_login(
                email=user["email"],
                user_name=user.get("name", "Usuario"),
                device="Web Browser"
            )
        except Exception as e:
            logger.warning(f"Failed to send login notification: {e}")

        # Lo que es suyo para ver, y nada más. La lista y el motivo están en
        # `services/perfil.py`: acá había una lista de lo PROHIBIDO de cinco
        # nombres, y dejaba salir quince campos que no son de su dueño, entre
        # ellos el hash del PIN y las credenciales de la huella.
        user_response = para_su_dueno(user)

        return {
            "message": "Login exitoso",
            "session_token": token,
            "user": user_response,
            "must_change_password": user.get("must_change_password", False)
        }

    result = await _do_login(request, body)
    if isinstance(result, dict) and result.get("session_token"):
        set_session_cookie(response, result["session_token"])
    return result

# LA CONTRASEÑA TEMPORAL POR CORREO SE FUE
#
#   Acá vivían `/request-password-reset` y `/reset-password`. Mandaban por
#   correo una CONTRASEÑA DE VERDAD —doce caracteres al azar, válida una hora,
#   que dejaba entrar a la cuenta— y ninguna pantalla de la aplicación las
#   usaba: el botón «¿Olvidaste tu contraseña?» va a `/recovery/*`, que pide
#   los datos de identidad y manda un CODIGO, que no deja entrar a ningún lado.
#
#   Una credencial completa viajando por correo, por una puerta que nadie
#   miraba, es superficie regalada. Quien olvida la contraseña entra por
#   `routes/recovery.py`.


# Cuánto vive el código del cambio de contraseña, y cuántas veces se puede
# errar. Diez minutos alcanzan para ir al correo y volver; tres intentos
# alcanzan para equivocarse tipeando y no alcanzan para adivinar.
_MINUTOS_DEL_CODIGO = 10
_INTENTOS_DEL_CODIGO = 3


@router.post("/change-password/pedir-codigo")
async def pedir_codigo_de_cambio(request: PedirCodigoDeCambioRequest, pedido: Request,
                                 current_user: User = Depends(get_current_user)):
    """Primer paso para cambiar la contraseña: manda un código al correo.

    POR QUE HACE FALTA UN CODIGO

        Antes alcanzaba con la contraseña actual. Quien se llevaba un teléfono
        con la sesión abierta, o robaba una sesión, tenía la cuenta: entraba a
        Perfil, ponía la contraseña que veía guardada en el navegador, y
        cambiaba la contraseña dejando al dueño afuera.

        Con el código hay que tener TAMBIEN el correo. Y si alguien lo
        intenta, al dueño le llega un correo que no pidió, que es la primera
        señal de que algo pasa.
    """
    from routes.security_2fa import frenar

    # 5/15min. Esta ruta comprueba la contraseña actual, así que sin freno se
    # puede usar para adivinarla desde una sesión robada, de a una por pedido.
    await frenar(pedido, "auth.pedir_codigo_de_cambio", "5/15minutes")

    user = await db.users.find_one({"user_id": current_user.user_id})
    if not await verify_password_async(request.current_password, user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")

    codigo = codigos.nuevo()
    await db.codigos_de_cambio.delete_many({"user_id": current_user.user_id})
    await db.codigos_de_cambio.insert_one({
        "user_id": current_user.user_id,
        "codigo": codigo,
        "intentos": 0,
        "expira_en": datetime.now(timezone.utc) + timedelta(minutes=_MINUTOS_DEL_CODIGO),
        "creado_en": datetime.now(timezone.utc),
    })

    # Se ESPERA a que salga. Si no sale, la persona se queda mirando una
    # pantalla que le pide un código que nunca va a llegar, y eso hay que
    # decírselo ahora y no dejarlo esperando.
    salio = await correo.enviar(
        user["email"],
        "Tu código para cambiar la contraseña",
        f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #6366f1;">Código para cambiar tu contraseña</h2>
            <p>Hola {user.get('name') or ''},</p>
            <p>Pediste cambiar la contraseña de tu cuenta. Tu código es:</p>
            <div style="background: #f3f4f6; padding: 20px; text-align: center; border-radius: 10px; margin: 20px 0;">
                <span style="font-size: 30px; font-weight: bold; letter-spacing: 6px; color: #111827;">{codigo}</span>
            </div>
            <p style="color: #ef4444; font-weight: 600;">Vence en {_MINUTOS_DEL_CODIGO} minutos.</p>
            <p style="color: #6b7280; font-size: 14px;"><strong>Si no pediste este cambio, alguien tiene tu
               contraseña.</strong> No uses el código y escribinos por soporte.</p>
        </div>
        """,
        que_es="código de cambio de contraseña")

    if not salio:
        raise HTTPException(
            status_code=503,
            detail="No pudimos enviarte el código. Probá de nuevo en un rato.")

    correo_tapado = user["email"]
    return {"success": True,
            "email_enmascarado": correo_tapado[:3] + "***"
                                 + correo_tapado[correo_tapado.index("@"):],
            "minutos": _MINUTOS_DEL_CODIGO}


@router.post("/change-password")
async def change_password(request: ChangePasswordRequest, pedido: Request,
                          current_user: User = Depends(get_current_user)):
    """Cambia la contraseña. Pide la actual Y el código que llegó al correo."""
    user = await db.users.find_one({"user_id": current_user.user_id})

    if not await verify_password_async(request.current_password, user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")

    # El código se comprueba ANTES de tocar nada. Y el contador de intentos se
    # sube en la MISMA escritura que lo lee, para que dos pedidos a la vez no
    # se regalen un intento cada uno.
    pendiente = await db.codigos_de_cambio.find_one_and_update(
        {"user_id": current_user.user_id},
        {"$inc": {"intentos": 1}},
        return_document=ReturnDocument.BEFORE)

    if not pendiente:
        raise HTTPException(
            status_code=400,
            detail="Pedí un código primero: te lo mandamos por correo.")

    vence = pendiente["expira_en"]
    if vence.tzinfo is None:
        vence = vence.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > vence:
        await db.codigos_de_cambio.delete_many({"user_id": current_user.user_id})
        raise HTTPException(status_code=400, detail="El código venció. Pedí uno nuevo.")

    if pendiente["intentos"] >= _INTENTOS_DEL_CODIGO:
        await db.codigos_de_cambio.delete_many({"user_id": current_user.user_id})
        raise HTTPException(
            status_code=400,
            detail="Se acabaron los intentos. Pedí un código nuevo.")

    if not codigos.coincide(request.codigo, pendiente["codigo"]):
        quedan = _INTENTOS_DEL_CODIGO - pendiente["intentos"] - 1
        raise HTTPException(
            status_code=400,
            detail=(f"Ese código no es. Te quedan {quedan} intentos."
                    if quedan > 0 else
                    "Ese código no es, y se acabaron los intentos. Pedí uno nuevo."))

    if request.new_password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")
    
    is_valid, message = validate_password(request.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)
    
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {
            "$set": {
                "password_hash": await hash_password_async(request.new_password),
                "must_change_password": False
            }
        }
    )
    
    # El código se gasta: sirve una vez y no queda dando vueltas en la base.
    await db.codigos_de_cambio.delete_many({"user_id": current_user.user_id})

    # Cambiar la contraseña es lo que hace alguien que sospecha que le entraron
    # a la cuenta. Si las demás sesiones sobreviven, ese gesto no sirve de nada.
    # Se conserva la de esta pantalla —echarla de acá justo después de hacer las
    # cosas bien se lee como un error— y se cierran todas las otras.
    cerradas = await sesiones.cerrar_todas(
        db, current_user.user_id,
        excepto=sesiones.token_del_pedido(pedido),
        motivo="cambio de contraseña propio")

    # Send password change notification
    try:
        await notify_password_change(
            email=user["email"],
            user_name=user.get("name", "Usuario")
        )
    except Exception as e:
        logger.warning(f"Failed to send password change notification: {e}")

    return {"message": "Contraseña cambiada exitosamente",
            "sesiones_cerradas": cerradas}

@router.post("/set-new-password")
async def set_new_password(request: SetNewPasswordRequest, pedido: Request,
                           current_user: User = Depends(get_current_user)):
    """La contraseña nueva de quien entró con una temporal puesta por un admin.

    LA RUTA QUE FALTABA, Y LO QUE COSTO QUE FALTARA

        `frontend/src/pages/ForceChangePassword.jsx` la llamaba desde el
        principio. Nunca existió en el servidor. Así que TODA persona a la que
        un administrador le reseteó la contraseña quedó encerrada: la
        aplicación la manda a esa pantalla desde cualquier lado mientras tenga
        la marca puesta, y esa pantalla era la única que no funcionaba. El
        único botón que le servía era «Cerrar sesión».

        El cartel decía «Not Found» —el `detail` de una dirección que no
        existe— y antes decía «Method Not Allowed», que es lo mismo de
        inútil. Ninguno de los dos se parece a «esta función no está hecha»,
        que es lo que pasaba.

    POR QUE NO PIDE LA CONTRASEÑA ACTUAL NI UN CODIGO

        Las dos comprobaciones que sí hace `/change-password` sobran acá y
        estorban: la actual es la temporal que la persona acaba de tipear para
        entrar, y el código al correo es una segunda vuelta para quien ya pasó
        por el reseteo.

        LO QUE AUTORIZA A SALTARSELAS ES LA MARCA, Y NADA MAS. Sin
        `must_change_password`, esta ruta sería una forma de cambiar la
        contraseña de cualquier cuenta cuya sesión alguien haya conseguido,
        sin saber la actual y sin pasar por el correo — o sea, de quedarse con
        la cuenta para siempre. Por eso la marca se comprueba ANTES que nada y
        se baja en la MISMA escritura que guarda la contraseña: entre mirarla
        y borrarla no queda ventana para usar la ruta dos veces.

    LA NUEVA NO PUEDE SER LA TEMPORAL

        Dejarla pasar sería dar el trámite por hecho con la contraseña que el
        administrador conoce, que es exactamente lo que este paso viene a
        deshacer.
    """
    from routes.security_2fa import frenar

    # 10/15min. La ruta no adivina nada —no hay secreto que probar acá— pero
    # cada llamada hashea una contraseña, que cuesta a propósito. Diez es
    # holgado para alguien que se equivoca tipeando y corta el abuso.
    await frenar(pedido, "auth.set_new_password", "10/15minutes")

    user = await db.users.find_one({"user_id": current_user.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if not user.get("must_change_password"):
        # No se le cuenta al cliente que existe una marca: para quien llegó
        # acá sin que le corresponda, esto no es un camino.
        logger.warning("set-new-password: %s la pidió sin tener la marca puesta",
                       current_user.user_id)
        raise HTTPException(
            status_code=403,
            detail="Tu cuenta no tiene un cambio de contraseña pendiente. "
                   "Para cambiarla, entrá a tu perfil.")

    if request.new_password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")

    es_valida, mensaje = validate_password(request.new_password)
    if not es_valida:
        raise HTTPException(status_code=400, detail=mensaje)

    if await verify_password_async(request.new_password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=400,
            detail="Esa es la contraseña temporal que te dieron. Elegí una "
                   "distinta, que sólo sepas vos.")

    # La marca va en el FILTRO, no sólo en el `$set`: si entre la lectura de
    # arriba y esta escritura la cuenta dejó de tener el cambio pendiente
    # —otra pestaña lo hizo, un admin la tocó— acá no se escribe nada.
    resultado = await db.users.update_one(
        {"user_id": current_user.user_id, "must_change_password": True},
        {"$set": {"password_hash": await hash_password_async(request.new_password),
                  "password_set": True,
                  "must_change_password": False,
                  "password_cambiada_en": datetime.now(timezone.utc)}},
    )
    if getattr(resultado, "modified_count", 0) != 1:
        raise HTTPException(
            status_code=409,
            detail="Tu contraseña ya se cambió desde otro lado. Volvé a "
                   "iniciar sesión con la nueva.")

    # Este camino existe porque alguien avisó que le tomaron la cuenta. Si las
    # otras sesiones sobrevivieran, el cambio no serviría de nada. Se conserva
    # la de esta pantalla: echar a la persona justo después de hacer las cosas
    # bien se lee como un error.
    cerradas = await sesiones.cerrar_todas(
        db, current_user.user_id,
        excepto=sesiones.token_del_pedido(pedido),
        motivo="cambio obligado tras un reseteo del administrador")

    try:
        await notify_password_change(email=user["email"],
                                     user_name=user.get("name", "Usuario"))
    except Exception as e:
        logger.warning(f"set-new-password: no salió el aviso por correo: {e}")

    logger.info("set-new-password: %s eligió su contraseña; %s sesión(es) cerradas",
                current_user.user_id, cerradas)
    return {"message": "Contraseña actualizada", "sesiones_cerradas": cerradas}


@router.get("/password-status", response_model=EstadoDeLaClave)
async def get_password_status(current_user: User = Depends(get_current_user)):
    """Check if user needs to change password"""
    user = await db.users.find_one({"user_id": current_user.user_id})
    return {
        "password_set": user.get("password_set", False),
        "must_change_password": user.get("must_change_password", False)
    }

@router.post("/register-fcm-token")
async def register_fcm_token(request: Request, current_user: User = Depends(get_current_user)):
    """Register FCM token for push notifications"""
    data = await request.json()
    fcm_token = data.get('fcm_token')
    
    if not fcm_token:
        raise HTTPException(status_code=400, detail="FCM token required")
    
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"push_token": fcm_token}}
    )
    
    return {"message": "Token registrado"}

@router.post("/heartbeat", response_model=MiLatido, response_model_exclude_unset=True)
async def heartbeat(current_user: User = Depends(get_current_user)):
    """Update user online status"""
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"is_online": True, "last_seen": datetime.now(timezone.utc)}}
    )
    return {"status": "ok"}

@router.post("/offline", response_model=MiLatido, response_model_exclude_unset=True)
async def mark_offline(current_user: User = Depends(get_current_user)):
    """Mark user as offline"""
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"is_online": False, "last_seen": datetime.now(timezone.utc)}}
    )
    return {"status": "ok"}

# ============================================================
# Primer acceso del personal
#
# El alta de Recursos Humanos crea la cuenta con rol y permisos, pero sin
# contraseña y sin el correo verificado. Sin esta puerta esa persona no puede
# entrar por ninguna otra: `login-password` la frena en `email_verified`,
# `resend-verification-code` lee una colección donde el alta no escribe, y el
# "olvidé mi contraseña" le manda una clave temporal que tampoco pasa el
# mismo control.
#
# Acá configura su clave con el token que le llegó por correo y sale
# directo al enrolamiento de dos pasos, que para el personal es obligatorio.
# ============================================================

class VerificarInvitacionRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=200)


class ActivarPersonalRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=200)
    password: str
    confirm_password: str


async def _persona_invitada(user_id: str) -> dict:
    """El usuario detrás de una invitación, si todavía corresponde.

    Una invitación emitida no alcanza: entre el correo y el click pudieron
    darla de baja. Se vuelve a mirar el estado en el momento de usarla.
    """
    from services import personal as _personal

    user = await db.users.find_one({"user_id": user_id})
    if not user or not _personal.es_personal(user):
        raise HTTPException(status_code=400,
                            detail="Esta invitación ya no es válida.")
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=403,
            detail="Esta cuenta está dada de baja. Contactá a tu administrador.")
    return user


@router.post("/personal/invitacion", response_model=MiInvitacion, response_model_exclude_unset=True)
async def verificar_invitacion(request: Request, body: VerificarInvitacionRequest):
    """Mira si el token sirve, SIN gastarlo, para que la pantalla salude.

    El token va en el cuerpo y no en la URL a propósito: una URL queda en el
    log de accesos del servidor, en el historial del navegador y en la
    cabecera Referer de cualquier recurso que cargue la página.
    """
    from routes.security_2fa import frenar
    from services import invitaciones

    async def _verificar(request: Request, body: VerificarInvitacionRequest):
        # 10/15min: es un token de 32 bytes, no se adivina a fuerza bruta,
        # pero tampoco hace falta dejar que alguien pruebe sin límite.
        await frenar(request, "auth.invitacion_verificar", "10/15minutes")
        try:
            inv = await invitaciones.mirar(db, body.token)
        except invitaciones.InvitacionInvalida:
            raise HTTPException(
                status_code=400,
                detail="Esta invitación no es válida o ya venció. "
                       "Pedile a tu administrador que te la reenvíe.")

        user = await _persona_invitada(inv["user_id"])
        return {
            "valido": True,
            "email": user.get("email"),
            "nombre": user.get("name"),
            "cargo": (user.get("legajo") or {}).get("cargo"),
        }

    return await _verificar(request, body)


@router.post("/personal/activar", response_model=MiEntrada, response_model_exclude_unset=True)
async def activar_personal(request: Request, body: ActivarPersonalRequest):
    """Configura la contraseña del personal y lo manda a activar el 2FA.

    No devuelve sesión: devuelve un `pending_token` de enrolamiento. Una
    cuenta con permisos de administración no queda usable con contraseña
    sola ni por un rato.
    """
    from routes.security_2fa import frenar, _create_pending_token
    from services import auditoria, invitaciones

    async def _activar(request: Request, body: ActivarPersonalRequest):
        await frenar(request, "auth.personal_activar", "10/15minutes")
        # La contraseña se valida ANTES de tocar el token. Al revés, un error
        # de tipeo quemaría la invitación y habría que pedir otra.
        if body.password != body.confirm_password:
            raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")
        ok, mensaje = validate_password(body.password)
        if not ok:
            raise HTTPException(status_code=400, detail=mensaje)

        try:
            inv = await invitaciones.mirar(db, body.token)
        except invitaciones.InvitacionInvalida:
            raise HTTPException(
                status_code=400,
                detail="Esta invitación no es válida o ya venció. "
                       "Pedile a tu administrador que te la reenvíe.")

        await _persona_invitada(inv["user_id"])

        # Recién acá se gasta. `consumir` es atómico: si dos pedidos llegan
        # con el mismo token, uno solo lo consigue.
        try:
            inv = await invitaciones.consumir(db, body.token)
        except invitaciones.InvitacionInvalida:
            raise HTTPException(status_code=400,
                                detail="Esta invitación ya fue usada.")

        user = await _persona_invitada(inv["user_id"])

        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "password_hash": await hash_password_async(body.password),
                "password_set": True,
                # El token viajó por correo a esta casilla y sólo su dueño
                # pudo traerlo de vuelta: eso ES la verificación del correo.
                "email_verified": True,
                "must_change_password": False,
                "updated_at": datetime.now(timezone.utc),
            }})

        # Lo normal es que no haya ninguna: la cuenta existía como invitación y
        # sin contraseña no se podía entrar. Va igual por el caso que sí importa
        # — que a alguien del personal le REINVITEN la cuenta porque se la
        # tomaron. Estas son las sesiones con permisos de administración; dejar
        # una viva acá es dejar la peor de todas.
        await sesiones.cerrar_todas(db, user["user_id"],
                                    motivo="activación del personal")

        await auditoria.registrar(
            db, "personal.activacion", quien=user, request=request,
            objetivo_tipo="usuario", objetivo_id=user["user_id"],
            objetivo_desc=user.get("email"),
            despues={"clave_configurada": True, "correo_verificado": True},
            detalle={"invitacion_emitida_por": inv.get("emitida_por")})

        pending = await _create_pending_token(user["user_id"], purpose="2fa_enroll")
        return {
            "message": "Contraseña configurada. Ahora activá la verificación en dos pasos.",
            "two_factor_enrollment_required": True,
            "pending_token": pending,
            "email": user["email"],
            "user_id": user["user_id"],
        }

    return await _activar(request, body)


# NOTA — acá abajo estaba TODO este archivo otra vez, y no se podía borrar
# desde cualquiera de las dos puntas.
#
# Las líneas 508 a 1014 repetían el docstring, los imports, el `router` y los
# trece handlers de arriba. Los cuerpos eran idénticos, pero los imports NO:
# la segunda copia importaba
#
#     from fastapi import APIRouter, Request, Depends, HTTPException, Header
#     from routes.dependencies import get_current_user
#
# sin `Response`, sin `set_session_cookie` y sin `clear_session_cookie` — que
# sus propios cuerpos usaban en logout, verify_email_code y
# login_with_password. Andaba de casualidad: esos tres nombres estaban en el
# namespace del módulo porque los había importado la PRIMERA copia.
#
# Y la que atendía los pedidos era la segunda, porque `router = APIRouter(...)`
# se volvía a asignar en la línea 534: los trece handlers de arriba quedaban
# registrados en un router huérfano que nadie incluía.
#
# O sea que el "borrar el duplicado" evidente —sacar la primera mitad, la que
# parece muerta— dejaba a login, logout y verificación de email levantando
# NameError en la primera llamada. Se conserva la primera copia, que tiene los
# imports completos, y se borra la segunda.
