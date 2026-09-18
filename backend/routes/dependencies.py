"""
Common dependencies for route handlers
"""
import logging
from typing import Optional
from datetime import datetime, timezone, timedelta
from fastapi import Request, Header, HTTPException, Depends, Response
from database import db
from bson.decimal128 import Decimal128
from models.user import User

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "session_token"
SESSION_COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 días (coincide con la sesión de usuario más larga)


# ─── Lo que se trae de la base en CADA pedido ─────────────────────────────
#
# ESTO CORRE MAS QUE NINGUNA OTRA CONSULTA DE LA APLICACION
#
#     Dos lecturas por cada pedido autenticado, y los pedidos los generan los
#     relojes: la campana cada 30 segundos, los pendientes cada 60, las órdenes
#     cada 15. Con dos mil personas con la aplicación abierta son unos 67
#     pedidos por segundo, o sea 134 documentos por segundo cruzando la red.
#
#     Las dos consultas venían SIN proyección: traían el documento entero de la
#     sesión y el documento entero del usuario, con todo lo que tenga adentro.
#
# LISTA DE LO PERMITIDO, que es la regla del proyecto y acá faltaba
#
#     Una lista de lo prohibido deja pasar cada campo nuevo hasta que alguien
#     se acuerde de agregarlo.
#
# Y SE ARMA SOLA A PARTIR DEL MODELO
#
#     Una lista escrita a mano se desincroniza el día que alguien le agrega un
#     campo a `User`: el campo nuevo llega vacío, con su valor por omisión, y
#     el defecto aparece lejos de acá —en la pantalla que lo usa— sin nada que
#     apunte a esta línea. Derivándola del modelo, agregar un campo al modelo
#     lo agrega a la consulta y no hay nada que recordar.
DEL_USUARIO = {campo: 1 for campo in User.model_fields}
DEL_USUARIO["_id"] = 0
# El único que mira ESTA función y no está en el modelo. Sin él, una cuenta
# suspendida entraría igual: `user.get("is_banned")` daría None siempre.
DEL_USUARIO["is_banned"] = 1

# De la sesión sólo se usan dos cosas: de quién es y cuándo vence.
DE_LA_SESION = {"_id": 0, "user_id": 1, "expires_at": 1}


def set_session_cookie(response: Response, token: str) -> None:
    """Setea el token de sesión como cookie httpOnly + Secure + SameSite=Lax."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Borra la cookie de sesión (usado en logout)."""
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")

async def get_current_user(request: Request, authorization: Optional[str] = Header(None)) -> Optional[User]:
    """Get current user from session token (cookie or header)"""
    session_token = None
    
    # Check cookie first
    session_token = request.cookies.get('session_token')
    
    # Fallback to Authorization header
    if not session_token and authorization:
        if authorization.startswith('Bearer '):
            session_token = authorization[7:]
    
    # Fall back to X-Session-ID header
    if not session_token:
        session_token = request.headers.get("X-Session-ID")
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Find session (use user_sessions collection like server.py)
    session = await db.user_sessions.find_one(
        {"session_token": session_token},
        DE_LA_SESION
    )
    
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    # Check expiration
    expires_at = session.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Session expired")
    
    # Get user
    user = await db.users.find_one(
        {"user_id": session["user_id"]},
        DEL_USUARIO
    )
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    if user.get("is_deleted"):
        raise HTTPException(status_code=401, detail="Account has been deleted")
    if user.get("is_banned"):
        raise HTTPException(status_code=403, detail="Esta cuenta ha sido suspendida")

    # Colgado del pedido para el manejador de errores: cuando algo se rompe
    # más adelante, la línea del registro dice a QUIEN le pasó. Sin esto un
    # 500 es anónimo y soporte no tiene por dónde empezar.
    # `getattr` y no `request.state` a secas: los tests arman pedidos falsos
    # sin `state`, y autenticar no puede depender de una comodidad del
    # registro de errores. Si no hay dónde colgarlo, no se cuelga.
    estado = getattr(request, "state", None)
    if estado is not None:
        estado.user_id = user.get("user_id")
        # Y el rol, para el contador de uso (services/uso.py): cuenta a los
        # clientes y a nadie más, y lo decide con esto sin volver a la base.
        estado.rol = user.get("role")

    # Convert BSON Decimal128 fields to float for Pydantic compatibility
    for _k, _v in list(user.items()):
        if isinstance(_v, Decimal128):
            user[_k] = float(_v.to_decimal())
    return User(**user)

def _exigir_permiso(request: Request, current_user: User) -> None:
    """Aplica la tabla de `services/permisos.py` a esta ruta.

    Está acá y no adentro de cada handler a propósito: por estas dos
    dependencias pasan las 67 rutas de administración que no son exclusivas
    del super administrador. Sesenta y siete comprobaciones sueltas serían
    sesenta y siete lugares donde olvidarse de una, y la que falta no avisa:
    deja pasar. Una ruta nueva hereda la comprobación por usar el guard.
    """
    from services import permisos

    try:
        permisos.exigir(current_user, request)
    except permisos.SinPermiso as e:
        # El mensaje nombra el permiso que falta: sin eso, el colaborador ve
        # un 403 pelado y el administrador no sabe qué tildar en RRHH.
        raise HTTPException(status_code=403, detail=str(e))
    except permisos.RutaSinMapear as e:
        raise HTTPException(status_code=403, detail=str(e))


async def get_admin_user(request: Request,
                         current_user: User = Depends(get_current_user)) -> User:
    """Require admin or super_admin role, y el permiso que pida la ruta."""
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    _exigir_permiso(request, current_user)
    return current_user

async def get_crm_user(request: Request,
                       current_user: User = Depends(get_current_user)) -> User:
    """Require CRM access: agent, admin o super_admin, y el permiso de la ruta."""
    if current_user.role not in ["agent", "admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="CRM access required")
    _exigir_permiso(request, current_user)
    return current_user

async def get_super_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require super_admin role"""
    if current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin access required")
    return current_user

async def get_verified_user(current_user: User = Depends(get_current_user)) -> User:
    """Require verified user"""
    if current_user.verification_status != "verified":
        raise HTTPException(status_code=403, detail="User verification required")
    return current_user

async def sin_transacciones_personales(
        request: Request,
        current_user: User = Depends(get_current_user)) -> User:
    """La puerta de las rutas donde un usuario mueve plata.

    Hace dos cosas, y las dos acá porque ésta es la ÚNICA dependencia por la
    que pasan todas esas rutas —retiros, envíos, recargas, PIX, tarjeta,
    cripto, BTC—. Una ruta nueva que la use hereda las dos.

    1. FRENA A UNA CUENTA DE PERSONAL. Da el mensaje claro. El candado de
       fondo está en `saldos.mover`, porque nueve de las diez formas de mover
       plata liquidan después por un webhook que no pasa por acá. Ver
       services/personal.py.

    2. FRENA A QUIEN OPERA DEMASIADO SEGUIDO. Por cuenta y por IP.

       Ninguna ruta de dinero tenía límite. De 157 rutas POST frenaban 17, y
       las 17 eran de entrada y recuperación: una cuenta con sesión podía
       crear pedidos de retiro sin parar. Y todos los límites eran por IP,
       que para quien ya tiene sesión y cambia de red —datos, wifi, VPN— es
       no tener límite. Por eso acá hay dos contadores y no uno.

       Los dos números se cambian desde el panel (Configuración), no acá.
       Van holgados para una persona y cortos para un programa: nadie hace
       treinta retiros en una hora con las manos.
    """
    from services import configuracion, personal
    from routes.security_2fa import frenar, frenar_por_cuenta

    if personal.es_personal(current_user):
        raise HTTPException(
            status_code=403,
            detail="Las cuentas del personal no pueden hacer transacciones a "
                   "título personal. Usá una cuenta propia, no la del trabajo.")

    por_cuenta = await configuracion.leer(db, "dinero_operaciones_por_cuenta_por_hora")
    por_ip = await configuracion.leer(db, "dinero_operaciones_por_ip_por_hora")
    await frenar_por_cuenta(current_user.user_id, "dinero.cuenta", f"{por_cuenta}/hour")
    await frenar(request, "dinero.ip", f"{por_ip}/hour")
    return current_user


def has_permission(user: User, permission: str) -> bool:
    """Check if user has a specific permission"""
    if user.role == "super_admin":
        return True
    return permission in (user.permissions or [])

def require_permission(permission: str):
    """Decorator to require a specific permission"""
    async def permission_checker(current_user: User = Depends(get_current_user)):
        if not has_permission(current_user, permission):
            raise HTTPException(status_code=403, detail=f"Permission required: {permission}")
        return current_user
    return permission_checker

# NOTA — acá abajo estaba TODO este archivo otra vez.
#
# Las líneas 129 a 235 repetían, byte por byte, el docstring del módulo, los
# imports y las siete funciones de arriba: get_current_user, get_admin_user,
# get_crm_user, get_super_admin, get_verified_user, has_permission y
# require_permission. Al importarse, la segunda definición pisaba a la
# primera, así que las que corrían eran las de abajo y las de arriba estaban
# muertas.
#
# No cambiaba el comportamiento —eran idénticas— pero era una trampa cara:
# éste es el archivo que decide quién es admin. Quien buscara `get_super_admin`
# desde arriba iba a encontrar la copia muerta, editarla, y ver que su cambio
# no hacía absolutamente nada. En un guard de permisos, un cambio que no surte
# efecto y no avisa es peor que un error.
