"""Los rechazos —los 4xx— que vale la pena guardar en «Errores».

QUE PASABA

    «Errores» guardaba los 500 y los 5xx que el código levanta a propósito.
    Los 4xx no, y con razón: un 404 o un 403 es el sistema diciendo que no,
    no algo roto, y guardarlos todos llena el registro de cosas que andan
    bien. Con 185 sitios que levantan un 400 y 91 que levantan un 404, un
    día de tráfico normal tapaba cualquier error de verdad.

    Pero cuatro rechazos sí cuentan una historia, y no había dónde verlos.

QUE SE GUARDA, Y POR QUE ESOS CUATRO

    · **429 de los límites de dinero.** El hueco más caro de los cuatro:
      esos límites se pusieron y nunca se veían. `slowapi` registra su
      propio manejador para `RateLimitExceeded`, y Starlette elige siempre
      el manejador MAS ESPECIFICO, así que el nuestro no lo veía pasar. El
      piso de peticiones sí se veía —porque se anota él solo, a mano—, y
      quedaban dos limitadores en la misma aplicación, uno visible y el
      otro invisible.

    · **401 en las puertas de ingreso, y sólo ahí.** Contraseña, código de
      dos pasos o huella equivocados. En cualquier otra ruta un 401 es una
      sesión vencida, que pasa todo el día y no dice nada.

    · **403 en las rutas del panel.** Alguien con sesión pidió una ruta de
      administración sin el rol. Es raro, y siempre significa algo: o una
      pantalla que ofrece lo que no debería, o alguien tanteando.

    · **423 del PIN bloqueado.** Un solo sitio en todo el código. Cuando
      salta, alguien erró el PIN tantas veces que se bloqueó.

    Lo que NO entra: el 400 (es el formulario diciendo «ese CPF no vale»; un
    evento suelto no distingue a quien se equivocó tipeando de un formulario
    que confunde a todos, y esa pregunta la contesta el contador de «Uso»),
    el 404 y el 409.

EL FRENO, QUE ES LA MITAD DEL DISEÑO

    Cada situación tiene UMBRAL y VENTANA, y se anota una sola línea por
    ventana. Sin eso, lo que se guarda no es información: alguien probando
    contraseñas escribe una línea por intento y el registro queda inservible
    justo cuando más se lo necesita.

    El umbral además es lo que separa el ruido de la historia. Una
    contraseña errada es normal; cinco en una hora desde la misma conexión
    no lo es, y la línea lo dice con el número adentro.

    El conteo vive en memoria, como el del piso de peticiones, y por lo
    mismo: con dos workers cada uno lleva el suyo y en el peor caso salen
    dos líneas en vez de una. Guardarlo en la base sería una escritura por
    rechazo, que es exactamente lo que este archivo evita.

NUNCA LEVANTA

    Corre dentro del manejador de errores. Si esto revienta, revienta la
    respuesta que el usuario estaba esperando.
"""
import logging
import time

from services import errores

logger = logging.getLogger(__name__)

# Las puertas que emiten sesión. La lista es explícita y no una regla sobre
# el nombre: `/api/auth/heartbeat` también empieza con `/api/auth/` y un 401
# ahí es una sesión vencida, no una contraseña equivocada.
PUERTAS_DE_INGRESO = frozenset({
    "/api/auth/login-password",
    "/api/auth/verify-email",
    "/api/auth/personal/activar",
    "/api/auth/2fa/verify",
    "/api/auth/2fa/enroll-confirm",
    "/api/auth/google",
    "/api/auth/google/completar",
    "/api/webauthn/login/verify",
})

RUTAS_DEL_PANEL = "/api/admin/"

# (situación) -> (umbral, ventana en segundos, qué dice la línea)
SITUACIONES = {
    "limite_de_dinero": (
        1, 60,
        "Se pasó del límite de pedidos de una ruta de dinero. Si es la propia "
        "aplicación reintentando, es un error de la aplicación; si es una sola "
        "cuenta a mano, mirá qué estaba haciendo."),
    "ingreso_rechazado": (
        5, 3600,
        "Intentos de ingreso rechazados desde la misma conexión: contraseña, "
        "código de dos pasos o huella equivocados."),
    "panel_sin_permiso": (
        1, 3600,
        "Una sesión sin el rol pidió una ruta del panel. O una pantalla ofrece "
        "lo que no debería, o alguien está tanteando."),
    "pin_bloqueado": (
        1, 3600,
        "El PIN quedó bloqueado por errarlo demasiadas veces."),
}

# (situación, clave, ventana) -> cuántos van. Se limpia sola.
_contados: dict = {}
_MAX_EN_MEMORIA = 5_000


def _ventana_de(ahora: float, segundos: int) -> int:
    return int(ahora // segundos)


def _sumar_y_ver_si_toca(situacion: str, clave: str, ahora=None) -> int:
    """Suma uno y devuelve cuántos van si toca anotar; 0 si no toca.

    Toca EXACTAMENTE cuando se alcanza el umbral, ni antes ni después: así
    sale una sola línea por ventana por más rechazos que sigan llegando.
    """
    umbral, ventana, _ = SITUACIONES[situacion]
    ahora = time.time() if ahora is None else ahora
    v = _ventana_de(ahora, ventana)
    llave = (situacion, clave, v)
    cuantos = _contados.get(llave, 0) + 1
    _contados[llave] = cuantos
    if len(_contados) > _MAX_EN_MEMORIA:
        _olvidar_lo_viejo(ahora)
    return cuantos if cuantos == umbral else 0


def _olvidar_lo_viejo(ahora: float) -> None:
    """Deja sólo la ventana en curso de cada situación. El diccionario no
    puede crecer sin fin: cada IP nueva que erra una contraseña es una clave,
    y una tanda de miles las deja todas adentro."""
    for llave in [k for k in _contados
                  if k[2] < _ventana_de(ahora, SITUACIONES[k[0]][1])]:
        _contados.pop(llave, None)


def que_situacion(status: int, ruta: str):
    """Qué rechazo es éste, o None si no es de los que se guardan.

    El 429 no sale de acá: llega nombrado desde el manejador de `slowapi`,
    porque el de la propia aplicación —el piso de peticiones— también es un
    429 y ya se anota solo. Decidirlo por el número los confundiría.
    """
    if status == 401 and ruta in PUERTAS_DE_INGRESO:
        return "ingreso_rechazado"
    if status == 403 and ruta.startswith(RUTAS_DEL_PANEL):
        return "panel_sin_permiso"
    if status == 423:
        return "pin_bloqueado"
    return None


async def anotar_si_importa(db, *, situacion, clave, rastro, metodo, ruta,
                            status, detalle=None, user_id=None, ip=None,
                            ahora=None) -> bool:
    """Asienta el rechazo si llegó al umbral. Devuelve si LLEGO AL UMBRAL.

    Devuelve eso y no «se escribió en la base» a propósito, porque no hay
    forma de saberlo: `errores.anotar` se traga el fallo de escritura y deja
    un ERROR en el log, y así tiene que ser —es el último que queda de pie
    cuando todo lo demás se cayó—. Prometer lo que no se puede saber sería
    peor que decir lo que sí: si esto devuelve `True`, el freno dejó pasar
    este rechazo.

    NUNCA LEVANTA: corre dentro del manejador de errores.
    """
    # Acá había además un «si la situación no está en el catálogo, salir». Se
    # comprobó rompiéndolo: NO ponía ningún test en rojo, porque una situación
    # que no existe revienta igual dos líneas más abajo y la cazaba el `try`.
    # Dos guardas donde una tapa a la otra son dos guardas de las que ninguna
    # está probada de verdad. Se fue la que no se podía probar, y de paso
    # quedó mejor: una situación inventada es un error de programación, y así
    # deja un aviso con su nombre en el registro en vez de irse en silencio.
    try:
        cuantos = _sumar_y_ver_si_toca(situacion, str(clave or "-"), ahora)
        if not cuantos:
            return False
        _, ventana, explicacion = SITUACIONES[situacion]
        veces = (f"{cuantos} en {ventana // 60} min" if ventana < 3600
                 else f"{cuantos} en {ventana // 3600} h")
        await errores.anotar(
            db, rastro=rastro, metodo=metodo, ruta=ruta, status=status,
            tipo=f"rechazo.{situacion}",
            mensaje=f"{explicacion} ({veces}). {detalle or ''}".strip(),
            user_id=user_id, ip=ip)
        return True
    except Exception as e:                                # pragma: no cover
        logger.warning("rechazos: no se pudo anotar %s: %s", situacion, e)
        return False
