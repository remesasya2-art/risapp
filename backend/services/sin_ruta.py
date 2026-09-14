"""
services/sin_ruta.py — Lo que llega a una dirección que no existe.

POR QUE ESTE MODULO EXISTE

    Durante meses, Mercado Pago avisó de cada pago a la RAIZ del sitio en vez
    de a `/api/webhook/mercadopago`. En el registro se veía así:

        POST /?data.id=177862590765&type=payment  →  405 Method Not Allowed

    La raíz sólo contesta a `GET` —es la que sirve la aplicación al navegador—,
    así que el aviso no tenía a quién ir. Ninguna alarma, ninguna traza
    distinguible: un 405 suelto entre miles de líneas de registro normal.

    El defecto se encontró de casualidad, mirando otra cosa. Y sólo no costó
    plata porque la pantalla del cliente pregunta mientras espera y tapaba el
    agujero. El día que alguien pague y cierre el navegador, eso no alcanza.

    Este módulo hace que ese caso GRITE la primera vez que pasa.

Y LA OTRA MITAD: UNA DIRECCION QUE NO EXISTE TIENE QUE DECIR QUE NO EXISTE

    La aplicación sirve el frontend en `/{lo que sea}`, así que CUALQUIER
    dirección contestaba 200 con la página. `/api/una-que-me-invente` también.

    Eso hace dos daños. Al que se equivoca de dirección le dice «cargó bien»
    cuando no cargó nada —un integrador puede estar mandándole pagos a una
    dirección inexistente y verlo como éxito—. Y a quien está probando puertas
    le contesta que sí a todo: el escáner de WordPress que pasó por acá se
    llevó doscientos 200, y ninguno quedó distinguible después.

    Debajo de `/api/` no hay ninguna pantalla que servir. Lo que no es una ruta
    es un error, y se dice: 404.

    Fuera de `/api/` la página SIGUE saliendo, y tiene que seguir saliendo:
    `/envios/ABC123` no es una ruta del servidor, la resuelve el navegador. Un
    404 ahí rompería la aplicación entera.
"""
import logging

logger = logging.getLogger(__name__)

# Debajo de esto no hay nada que mirar con los ojos: son rutas de programa.
PREFIJO_API = "/api/"

# La única dirección por la que Mercado Pago tiene que avisar. Se nombra en el
# aviso a propósito: un error que dice qué está mal pero no cuál es lo correcto
# obliga a ir a buscarlo, y eso es media hora más de agujero abierto.
DONDE_AVISA_MERCADOPAGO = "/api/webhook/mercadopago"

# Cómo se reconoce un aviso de Mercado Pago. Son las formas que usa: la nueva
# (`data.id`), la vieja de IPN (`topic` + `id`), el tipo de evento, y la firma.
# Alcanza con UNA.
SENALES_EN_LA_CONSULTA = ("data.id", "topic")
CABECERA_DE_LA_FIRMA = "x-signature"


def es_de_la_api(camino: str) -> bool:
    """¿Esta dirección es de programa y no de pantalla?

    Se compara sobre la ruta con la barra inicial puesta, y `/api` pelado
    cuenta: sin eso, `/api` a secas caía del lado de las pantallas y devolvía
    el index.html, que es justo lo que se está sacando.
    """
    if not camino.startswith("/"):
        camino = "/" + camino
    return camino == "/api" or camino.startswith(PREFIJO_API)


def parece_aviso_de_mercadopago(consulta, cabeceras) -> bool:
    """¿Esto que llegó tiene forma de aviso de pago de Mercado Pago?

    Se mira la forma y NO se confía en ella para nada más que para registrar.
    Cualquiera puede fabricar un pedido con esta pinta; lo único que consigue
    es una línea en el registro. Acreditar sigue exigiendo la firma HMAC en la
    ruta de verdad, que no cambió.
    """
    if any(clave in consulta for clave in SENALES_EN_LA_CONSULTA):
        return True
    if str(consulta.get("type", "")).lower() == "payment":
        return True
    return CABECERA_DE_LA_FIRMA in {c.lower() for c in cabeceras}


def _nombres(consulta) -> str:
    """Los NOMBRES de los parámetros, no sus valores.

    Un registro es un lugar donde las cosas se quedan escritas y lo lee gente
    que no es dueña del dato. Los nombres alcanzan para diagnosticar; los
    valores pueden traer cualquier cosa que a alguien se le ocurrió mandar.
    La excepción es el identificador del pago, que se registra aparte porque
    sin él no se puede ir a buscar QUE pago se perdió — y un id de pago de
    Mercado Pago no es un secreto.
    """
    return ", ".join(sorted(consulta.keys())) or "(sin parámetros)"


def avisar_si_es_un_pago_perdido(metodo: str, camino: str, consulta, cabeceras):
    """Grita si lo que acaba de rebotar era el aviso de un cobro.

    Devuelve el motivo registrado, o `None` si no había nada que decir. El
    valor de retorno existe para los tests: comprobar contra el registro exige
    capturarlo, y un test que depende de capturar registro se rompe con
    cualquier cambio de configuración de logging.

    NO SE REGISTRA CUALQUIER COSA QUE REBOTE

        La tentación es avisar de todo pedido que cae acá. Pero por acá pasan
        todos los escáneres de internet probando `/wp-login.php` y trescientas
        direcciones más: un aviso por cada uno es un registro que nadie lee, y
        un registro que nadie lee es lo mismo que no tenerlo. Justamente el
        problema que este módulo vino a resolver.

        Así que sólo dos casos, los dos raros de verdad:
    """
    if metodo == "GET":
        return None

    # 1. Tiene forma de aviso de Mercado Pago y llegó a cualquier lado que no
    #    sea su dirección. Es el caso exacto que estuvo meses sin verse.
    if parece_aviso_de_mercadopago(consulta, cabeceras):
        pago = consulta.get("data.id") or consulta.get("id") or "(sin id)"
        motivo = "mercadopago"
        logger.error(
            "AVISO DE PAGO A LA DIRECCION EQUIVOCADA: llegó un %s a «%s» con "
            "forma de notificación de Mercado Pago (pago %s). Esa dirección no "
            "existe, así que el cobro NO se acreditó por esta vía. La dirección "
            "correcta es «%s» y hay que corregirla en el panel de Mercado Pago.",
            metodo, camino, pago, DONDE_AVISA_MERCADOPAGO)
        return motivo

    # 2. Un POST a la raíz del sitio con parámetros. Nadie hace eso de casualidad
    #    ni por equivocarse de enlace: la raíz es una página. Está acá para que,
    #    si mañana otro proveedor de pagos queda mal configurado de la misma
    #    forma pero con otra pinta, tampoco pase inadvertido.
    if camino in ("/", "") and consulta:
        logger.error(
            "PEDIDO RARO A LA RAIZ: llegó un %s a «/» con parámetros (%s). La "
            "raíz sirve la aplicación, no recibe datos. Si esto es la "
            "notificación de un proveedor, está mal configurada: tiene que ir a "
            "una dirección bajo %s.", metodo, _nombres(consulta), PREFIJO_API)
        return "raiz"

    return None
