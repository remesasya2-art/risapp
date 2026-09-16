"""
routes/csp_reporte.py — Dónde avisa el navegador lo que habría bloqueado.

PARA QUE EXISTE

    La política de contenido sale en modo reporte (ver `services/csp.py`): el
    navegador no bloquea nada y avisa acá lo que habría bloqueado. Sin este
    endpoint, ese aviso se pierde y la única forma de saber si la política está
    bien es prenderla y esperar a que alguien no pueda pagar.

    Con esto, después de unos días de tráfico real se puede mirar el registro y
    decidir con datos: si no hay reportes, se pasa a bloquear cambiando
    `CSP_MODO`. Si los hay, dicen exactamente qué falta.

ESTA RUTA ES PUBLICA, Y ESO OBLIGA A CUIDARLA

    Tiene que ser pública: el navegador manda el aviso sin sesión, y a veces
    justo cuando la página no cargó bien. Eso la convierte en un buzón abierto
    en internet, así que:

      * TIENE TOPE DE INTENTOS. Sin él, es un generador de líneas de registro
        gratis para cualquiera.
      * NO SE REGISTRA EL CUERPO QUE LLEGA. Se leen tres campos conocidos y se
        recortan. Un reporte de política lo arma el navegador, pero a esta
        dirección le puede escribir cualquiera, y volcar lo que mande es
        convertir nuestro registro en su bloc de notas.
      * SIEMPRE CONTESTA 204. Un aviso del navegador no tiene a nadie del otro
        lado esperando una respuesta, y un código de error sólo provocaría
        reintentos.

QUE SE GUARDA

    Qué directiva se violó, de qué dirección venía el recurso, DE QUE DOMINIO
    era el script culpable y los primeros caracteres de su código. Todo
    recortado.

    Los dos últimos se agregaron porque sin ellos los avisos no tenían nombre.
    Aparecieron tres seguidos —un script en línea, uno que usa WebAssembly y el
    medidor de Cloudflare— y se comprobó que NINGUNO era nuestro: el HTML que
    construimos no lleva un solo script en línea y la palabra `WebAssembly` no
    aparece en el paquete. Pero saber de quién SI eran —¿el SDK de pagos?, ¿el
    anti-bots de Cloudflare?, ¿una extensión del navegador de un visitante?—
    era imposible con lo que se guardaba, y de esa respuesta depende si un
    origen se permite o no.

    LO QUE SIGUE SIN GUARDARSE ES LA RUTA. Del `source-file` va el dominio y
    nada más: el dominio dice de quién es el script, y la ruta, cuando el
    script es de la propia aplicación, es la PANTALLA que estaba mirando una
    persona concreta. La muestra del código identifica al culpable por lo que
    hace, que no señala a nadie.
"""
import logging

from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)
router = APIRouter(tags=["csp"])

# Un reporte de política pesa menos de 1 KB. Con 8 hay margen de sobra y se
# corta muy antes de que alguien lo use para mandar cualquier cosa.
TOPE_BYTES = 8 * 1024

# Lo único que se lee. Los navegadores mandan la misma información con dos
# nombres distintos según la versión del estándar.
CAMPOS = (("effective-directive", "violated-directive", "effectiveDirective"),
          ("blocked-uri", "blockedURL", "blockedURI"))

# De dónde salió el script culpable. Se guarda SOLO EL DOMINIO (ver abajo).
CAMPO_ARCHIVO = ("source-file", "sourceFile", "sourceURL")

# Los primeros caracteres del código bloqueado. Es lo único que identifica a un
# script EN LINEA, que por definición no tiene dirección propia.
CAMPO_MUESTRA = ("script-sample", "sample", "scriptSample")


def _primero(datos: dict, nombres) -> str:
    for nombre in nombres:
        valor = datos.get(nombre)
        if valor:
            # Recortado, y en UNA SOLA LINEA. Lo que llega acá lo escribe quien
            # hace el pedido: si se copiara tal cual, un salto de línea metido a
            # propósito parte el aviso en dos y la segunda mitad se lee como una
            # línea de registro más, escrita por un desconocido.
            return " ".join(str(valor).split())[:120] or "?"
    return "?"


def _solo_el_dominio(valor: str) -> str:
    """De una dirección, el esquema y el dominio. Nunca la ruta.

        https://sdk.mercadopago.com/v2/security.js  ->  https://sdk.mercadopago.com

    El dominio dice de quién es el script, que es lo que hace falta para
    completar la política. La ruta no aporta nada a esa decisión y sí cuenta,
    cuando el script es de la propia aplicación, qué pantalla estaba mirando
    alguien.

    Lo que no es una dirección —un `inline`, un `eval`, un `?`— vuelve tal cual:
    son justamente los casos que esto viene a poder nombrar.
    """
    if "://" not in valor:
        return valor
    try:
        from urllib.parse import urlsplit
        partes = urlsplit(valor)
        if partes.scheme and partes.netloc:
            return f"{partes.scheme}://{partes.netloc}"[:120]
    except ValueError:
        pass
    return "?"


@router.post("/csp-reporte", status_code=204, include_in_schema=False)
async def recibir_reporte(request: Request):
    """Anota qué habría bloqueado la política. Nunca falla."""
    from routes.security_2fa import frenar

    # 60/15min. Una página con un recurso bloqueado manda un aviso por carga, no
    # cientos; el tope corta el uso de esta dirección como generador de ruido
    # sin perder los avisos de un problema real.
    frenar(request, "csp.reporte", "60/15minutes")

    try:
        crudo = await request.body()
        if len(crudo) > TOPE_BYTES:
            return Response(status_code=204)

        import json
        cuerpo = json.loads(crudo or b"{}")
        # Los navegadores lo mandan de dos formas: `{"csp-report": {...}}` (el
        # formato viejo) o una lista de reportes (`report-to`).
        if isinstance(cuerpo, list):
            reportes = [r.get("body", r) for r in cuerpo if isinstance(r, dict)]
        else:
            reportes = [cuerpo.get("csp-report") or cuerpo]

        for reporte in reportes[:10]:
            if not isinstance(reporte, dict):
                continue
            logger.warning(
                "CSP habría bloqueado: directiva=%s origen=%s desde=%s "
                "muestra=%s",
                _primero(reporte, CAMPOS[0]), _primero(reporte, CAMPOS[1]),
                _solo_el_dominio(_primero(reporte, CAMPO_ARCHIVO)),
                _primero(reporte, CAMPO_MUESTRA))
    except Exception:
        # Un aviso mal formado no es un problema nuestro y no vale una línea de
        # error: quien manda basura acá busca justamente eso.
        pass

    return Response(status_code=204)
