"""
De qué IP viene un pedido, y por qué no es la respuesta obvia.

EL AGUJERO QUE ESTE MODULO CIERRA

    Todos los límites de intentos de la aplicación —el ingreso, el reseteo de
    contraseña, la invitación del personal, el segundo factor— cuentan por IP.
    La IP la resolvía esto:

        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()

    Es decir: el PRIMER valor de una cabecera que manda el cliente.

    Un proxy normal no reemplaza `X-Forwarded-For`: le AGREGA la IP real al
    final. Así que un pedido enviado con

        X-Forwarded-For: 1.2.3.4

    llega a la aplicación como

        X-Forwarded-For: 1.2.3.4, <ip real del cliente>

    y `split(",")[0]` devuelve 1.2.3.4 — el valor que eligió el atacante.
    Cambiándolo en cada pedido, cada intento cae en un contador distinto y
    NINGUN límite de la aplicación se aplica. No es que fueran flojos: no
    existían.

COMO SE RESUELVE

    Se lee de DERECHA A IZQUIERDA, no de izquierda a derecha.

    La cabecera se arma por acumulación: cada proxy agrega al final la IP de
    quien le habló. El último valor lo escribió el proxy que tenemos adelante
    —el único que no podemos falsear desde afuera— así que es el único en el
    que se puede confiar. Todo lo que está a su izquierda lo pudo haber puesto
    el cliente.

    Con más de un proxy encadenado se salta uno por cada hop de confianza:
    `PROXIES_DE_CONFIANZA` dice cuántos hay. Con el valor por defecto de 1 —un
    solo proxy adelante— se toma el último.

    Y antes que todo eso se mira `CF-Connecting-IP`: cuando Cloudflare está
    adelante la escribe él, PISANDO lo que venga del cliente, así que no se
    puede falsear. Es la fuente más confiable de las tres.

POR QUE NO SE PUEDE «ARREGLAR» CONFIANDO EN LA PRIMERA IP

    Es tentador decir «el primero es el cliente original». Lo es sólo si todos
    los proxies de la cadena son honestos, y el primero de la cadena es el
    propio cliente, que por definición no lo es. Esa lectura es correcta para
    saber de dónde dice venir alguien; es equivocada para decidir a quién
    frenar.

SI NO HAY NINGUNA CABECERA

    Se usa la dirección del socket. Es la verdad de la conexión y no se puede
    falsear, aunque sin proxy adelante sea la del propio balanceador.
"""
import logging
import os

logger = logging.getLogger(__name__)


# Cuántos proxies de confianza hay entre el cliente e esta aplicación. Con uno
# —lo normal: Railway, o un balanceador— el último valor de X-Forwarded-For es
# la IP real. Con Cloudflare por delante de Railway serían dos, pero en ese
# caso manda `CF-Connecting-IP` y este número no se usa.
def _proxies_de_confianza() -> int:
    try:
        n = int(os.environ.get("PROXIES_DE_CONFIANZA", "1"))
    except (TypeError, ValueError):
        n = 1
    # El piso de 1 es intención, no protección: quien protege de verdad es el
    # recorte de `ip_del_cliente`, que con un número absurdo termina devolviendo
    # igual el último valor de la cadena. Se probó rompiendo esta línea —los
    # tests siguen en verde— así que si algún día se saca el recorte, esto NO
    # alcanza para reemplazarlo.
    return max(1, n)


# Cloudflare la escribe él y pisa cualquier valor que mande el cliente.
CABECERA_CLOUDFLARE = "cf-connecting-ip"
CABECERA_REENVIO = "x-forwarded-for"


def _limpia(valor) -> str:
    return (valor or "").strip()


def ip_del_cliente(request) -> str:
    """La IP en la que se puede confiar para contar intentos.

    Nunca levanta: si algo falta o viene raro devuelve lo que haya, y en el
    peor caso la cadena vacía. Un límite que revienta al resolver la IP deja
    de frenar, que es exactamente lo contrario de lo que se busca.
    """
    cabeceras = getattr(request, "headers", None) or {}

    try:
        cf = _limpia(cabeceras.get(CABECERA_CLOUDFLARE))
        if cf:
            return cf

        xff = _limpia(cabeceras.get(CABECERA_REENVIO))
        if xff:
            partes = [p.strip() for p in xff.split(",") if p.strip()]
            if partes:
                # De derecha a izquierda: se descarta un valor por cada proxy
                # de confianza que hay adelante, y se toma el siguiente.
                indice = len(partes) - _proxies_de_confianza()
                return partes[max(0, min(indice, len(partes) - 1))]
    except Exception as e:                                    # pragma: no cover
        logger.warning("ip_cliente: no se pudo leer la cabecera: %s", e)

    try:
        cliente = getattr(request, "client", None)
        return _limpia(getattr(cliente, "host", None))
    except Exception:                                         # pragma: no cover
        return ""


def desde_donde_dice_venir(request) -> str:
    """La primera IP de la cadena: de dónde DICE venir el pedido.

    Sirve para registrar y para investigar, NUNCA para decidir a quién frenar
    ni a quién dejar pasar: la escribe quien quiera. Existe como función
    aparte, con este nombre, justamente para que nadie la use por error donde
    va la otra.
    """
    cabeceras = getattr(request, "headers", None) or {}
    xff = _limpia(cabeceras.get(CABECERA_REENVIO))
    if xff:
        partes = [p.strip() for p in xff.split(",") if p.strip()]
        if partes:
            return partes[0]
    return ip_del_cliente(request)
