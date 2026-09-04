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

    Qué directiva se violó y de qué dirección venía el recurso, recortados. Con
    eso alcanza para completar la política. El resto —la URL donde pasó, la
    línea del script— identifica a quien estaba navegando y no hace falta.
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


def _primero(datos: dict, nombres) -> str:
    for nombre in nombres:
        valor = datos.get(nombre)
        if valor:
            # Recortado: lo que llega lo escribe quien hace el pedido.
            return str(valor)[:120]
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
                "CSP habría bloqueado: directiva=%s origen=%s",
                _primero(reporte, CAMPOS[0]), _primero(reporte, CAMPOS[1]))
    except Exception:
        # Un aviso mal formado no es un problema nuestro y no vale una línea de
        # error: quien manda basura acá busca justamente eso.
        pass

    return Response(status_code=204)
