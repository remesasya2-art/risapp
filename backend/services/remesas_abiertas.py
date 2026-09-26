"""
services/remesas_abiertas.py — ¿Se pueden hacer envíos nuevos a Venezuela y a
Brasil? La llave del servicio de remesas entero.

POR QUE EXISTE

    RIS tiene tres servicios que se prenden por separado: remesas, encomiendas
    y el banco. El día que el banco opere con un socio regulado, ese socio no
    va a aceptar una empresa que haga remesas internacionales sin licencia:
    remesas se tiene que poder APAGAR desde el panel, sin tocar código, y
    volver a prender el día que haya licencia. Ver docs/banco/README.md.

    Encomiendas ya tenía su llave (`services/encomiendas_abiertas.py`) y el
    banco la suya (`nucleo/modo.py`). Remesas no tenía ninguna: sus dos
    puertas principales —gastar en Venezuela y gastar en Brasil— no miraban
    nada. Recarga y cripto sí tenían llave, pero son partes de remesas y no
    el servicio: cerrar las dos dejaba igual a cualquiera con saldo gastando.

ES LA LLAVE MADRE

    Cerrada, además de sus propias puertas, cierra la carga de saldo y la
    entrada de cripto AUNQUE SUS LLAVES DIGAN OTRA COSA. Es un solo botón: no
    hay que acordarse de cerrar tres cosas en orden, ni volver a abrirlas.
    Las llaves de recarga y cripto no se tocan: al abrir remesas vuelven a
    valer las suyas, como estaban.

    Con cripto no la cierra del todo: la deja en «sólo salida». Quien tiene
    saldo cripto lo tiene que poder sacar; cerrar la salida le atraparía la
    plata, que es exactamente lo que el estado «sólo salida» existe para
    evitar (ver services/cripto_abierta.py).

QUE SE APAGA Y QUE NO

    Se apaga lo que CREA una operación nueva:

        POST /api/withdraw, /api/withdrawal/create   gastar en Venezuela
        POST /api/reais/send                         gastar en Brasil
        POST /api/withdraw-ves/cotizar               Venezuela pagando al final
        POST /api/enviar-reais/cotizar               Brasil pagando en bolívares
        la carga de saldo y los depósitos cripto     (por la llave madre)
        el bono de bienvenida nuevo                  (sólo se gasta en envíos)

    NO se apaga lo que termina algo que ya empezó, ni lo que se lee:

      · el historial, el detalle y el estado de cada operación;
      · subir el comprobante de un envío ya cotizado, pagar con tarjeta uno ya
        creado, cancelar;
      · los avisos de pago que acreditan (Mercado Pago, cripto, Lightning):
        alguien pudo haber pagado un minuto antes de cerrar, y esa plata ya
        salió de su bolsillo;
      · el panel entero, para que el equipo termine lo que quedó pendiente.

    La lista de puertas no vive sólo acá: `tests/test_remesas_cerradas.py`
    la recorre en la aplicación armada y falla si una de estas rutas pierde
    la guarda.

DOS ESTADOS, NO TRES

    Se evaluó un tercero, «sólo gerencia», para probar el servicio antes de
    abrirlo. No funcionaría: las cuentas del personal tienen prohibido mover
    plata (`services/personal.py`), así que nadie podría probar nada en ese
    modo. Un estado que promete algo que no hace es peor que no tenerlo.

FALLA ABIERTO, COMO ENCOMIENDAS Y RECARGA

    Si la base no contesta, deja pasar. La operación misma necesita la base,
    así que con la base caída tampoco llega lejos; y con la base bien, lo que
    se decide acá es no frenarle a nadie algo que la aplicación hace desde
    siempre por un mal momento nuestro.
"""
import logging

from fastapi import HTTPException

logger = logging.getLogger(__name__)

CLAVE = "remesas_abiertas"

CERRADAS = 0
ABIERTAS = 1

# Lo que ve el cliente. El vocabulario es el del menú —«gastar», no «enviar
# dinero»— y dice que lo que ya empezó sigue igual: sin eso, «en pausa» lo
# manda a soporte a preguntar por la operación que ya pagó.
EN_PAUSA = ("Gastar en Venezuela y en Brasil está en pausa por ahora. Lo que "
            "ya tenés en curso sigue igual y lo ves en tu historial.")


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


async def esta_abierta(db=None) -> bool:
    """¿Se pueden hacer envíos nuevos?"""
    from services import configuracion
    try:
        return int(await configuracion.leer(await _db(db), CLAVE)) == ABIERTAS
    except Exception as e:                                    # pragma: no cover
        # Falla ABIERTO. Ver el encabezado.
        logger.error("No se pudo leer %s, se asume abierta: %s", CLAVE, e)
        return True


async def exigir_abierta(db=None) -> None:
    """Frena la ruta si remesas está cerrada.

    503 y no 403: no es que esta cuenta no tenga permiso, es que el servicio
    no está dando eso ahora. Un 403 le haría pensar que hizo algo mal.
    """
    if not await esta_abierta(db):
        raise HTTPException(status_code=503, detail=EN_PAUSA)
