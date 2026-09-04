"""
Cerrar las sesiones de alguien. Un solo lugar, porque estaba en ninguno.

EL AGUJERO QUE ESTE MODULO CIERRA

    Hay cuatro formas de cambiar una contraseña en esta aplicación:

        /auth/change-password      el usuario, desde adentro
        /auth/reset-password       con la contraseña temporal del correo
        /recovery/reset-password   con el código de recuperación
        /admin/reset-password      un administrador se la resetea a alguien

    Las cuatro escribían el `password_hash` nuevo y no tocaban nada más. Las
    sesiones abiertas seguían abiertas.

    Eso rompe la única defensa que una persona sabe usar sola. Alguien entra a
    una cuenta ajena —una computadora prestada, una sesión que quedó abierta en
    un locutorio, un token robado—, la dueña lo sospecha y hace lo que todo el
    mundo sabe hacer: cambia la contraseña. Y no pasa nada. El intruso sigue
    adentro, leyendo, con la sesión que ya tenía.

    El caso del administrador es peor todavía: nos avisan que una cuenta está
    comprometida, la reseteamos, contestamos «listo, ya está» — y no está. Le
    dimos a la persona una certeza que no era cierta.

QUE HACE

    Borra las sesiones del servidor. La sesión de esta aplicación es opaca y
    vive en `user_sessions`: el navegador tiene una cookie con un valor que no
    dice nada, y toda la autoridad está en la fila de la base. Borrada la fila,
    la cookie es un papel sin valor. No hace falta esperar a que venza nada.

POR QUE SE PUEDE DEJAR UNA AFUERA

    Cuando la persona cambia su propia contraseña estando adentro, cerrarle
    TODO la echaría de la pantalla en la que está, justo después de hacer algo
    bien. Se conserva la suya y se cierran las demás, que es lo que hacen los
    servicios grandes y es lo que la gente espera.

    En los otros tres caminos no hay «sesión actual» que conservar: quien
    resetea desde el correo no está adentro, y el administrador que resetea no
    es el dueño de esas sesiones. Ahí se cierran todas, sin excepción.

LO QUE ESTO NO ALCANZA A CUBRIR

    Un intruso que además cambió la contraseña, o que se llevó los códigos de
    respaldo del segundo factor, no se saca con esto. Para eso está el reseteo
    del administrador, que ahora sí cierra todo.
"""
import logging

logger = logging.getLogger(__name__)

COLECCION = "user_sessions"


def token_del_pedido(request) -> str:
    """El identificador de sesión de este pedido, mirando en los tres lados.

    Es el mismo orden que usa `get_current_user`: cookie, después
    `Authorization: Bearer`, después `X-Session-ID`. Se repite acá para no
    importar el módulo de dependencias —que arrastra media aplicación— y para
    que quede en un solo lugar en vez de copiado en cada ruta que lo necesita.
    """
    try:
        cookies = getattr(request, "cookies", None) or {}
        token = cookies.get("session_token")
        if token:
            return token
        cabeceras = getattr(request, "headers", None) or {}
        autorizacion = cabeceras.get("Authorization") or cabeceras.get("authorization") or ""
        if autorizacion.startswith("Bearer "):
            return autorizacion[7:]
        return cabeceras.get("X-Session-ID") or cabeceras.get("x-session-id") or ""
    except Exception:                                         # pragma: no cover
        return ""


async def cerrar_todas(db, user_id: str, *, excepto: str = "", motivo: str = "") -> int:
    """Cierra las sesiones de `user_id`. Devuelve cuántas cerró.

    `excepto` conserva UNA sesión —la de quien está haciendo el cambio—; sin él
    se cierran todas.

    Nunca levanta. Esto se llama justo después de guardar la contraseña nueva, y
    una excepción acá dejaría a la persona sin saber si el cambio se aplicó.
    Fallar cerrando sesiones es malo; fallar de una forma que hace dudar de si
    la contraseña cambió es peor.
    """
    if not user_id:
        return 0

    filtro = {"user_id": user_id}
    if excepto:
        filtro["session_token"] = {"$ne": excepto}

    try:
        resultado = await db[COLECCION].delete_many(filtro)
        cuantas = getattr(resultado, "deleted_count", 0) or 0
    except Exception as e:                                    # pragma: no cover
        logger.error(
            "SESIONES NO CERRADAS: se cambió la contraseña de %s (%s) y las "
            "sesiones abiertas siguen vivas: %s", user_id, motivo or "sin motivo", e)
        return 0

    if cuantas:
        logger.info("Se cerraron %d sesión(es) de %s por %s",
                    cuantas, user_id, motivo or "cambio de contraseña")
    return cuantas
