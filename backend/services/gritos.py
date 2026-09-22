"""
services/gritos.py — Lo que no puede quedarse en el registro.

POR QUE

    Dos cosas gritaban en el log y nada más.

    Una: el asiento del libro que no se escribe. `record_ris_entry` se traga
    su error por contrato (no puede tumbar un flujo de plata que ya ocurrió) y
    devuelve `None`; `saldos.mover` lo escribe como `LIBRO SIN LINEA`. El saldo
    se movió y el libro no lo sabe. Es el agujero exacto que el libro vino a
    tapar, y la única señal era una línea entre miles en Railway.

    Otra: el aviso de un cobro que llega a una dirección que no existe.
    Mercado Pago avisó meses a la raíz del sitio y se supo de casualidad. Hoy
    `sin_ruta` lo reconoce y lo escribe en el log. Lo lee quien esté mirando
    el log en ese momento, o sea nadie.

    El informe de arquitectura lo pide con estas palabras: «el asiento del
    libro que falla no se calla: además del error en el registro, una fila en
    la pestaña Errores y un aviso».

QUE HACE

    `gritar` deja las tres marcas a la vez:

      1. la línea en el log, como hasta ahora;
      2. una fila en la pestaña Errores (`services/errores.py`), que es donde
         el super administrador ya mira lo que se rompe;
      3. un aviso por la campana del equipo, sólo a los super administradores.

    Y NUNCA LEVANTA: quien la llama está en medio de un error, y un error al
    contar un error es el peor de los dos.

LA CAMPANA NO SE REPITE CADA VEZ; LA FILA SI

    Si el libro deja de escribirse por un motivo que se repite —un índice
    roto, un campo que Mongo rechaza—, cada movimiento de plata dispara un
    grito. Cien filas en Errores son útiles: dicen cuántas líneas hay que
    reponer. Cien avisos en la campana en diez minutos son un aviso que
    alguien silencia, y silenciado ya no sirve para la próxima.

    Así que la fila va SIEMPRE y la campana como mucho una vez cada
    `CADA_CUANTO_SE_REPITE` por tipo de grito. El freno vive en memoria del
    proceso a propósito: si son dos procesos, son dos avisos, y eso es
    aceptable; lo que no es aceptable es que el freno dependa de la base
    cuando el grito puede ser, justamente, que la base no escribe.
"""
import logging
import time
from decimal import Decimal

logger = logging.getLogger(__name__)

CADA_CUANTO_SE_REPITE = 600      # segundos entre dos campanas del mismo tipo

# Los tipos que existen. Se nombran acá para que la pestaña Errores pueda
# filtrar por ellos y para que un test pueda comprobar que cada uno se grita.
LIBRO_SIN_LINEA = "libro_sin_linea"
PAGO_A_DIRECCION_EQUIVOCADA = "pago_a_direccion_equivocada"

_ultima_campana: dict[str, float] = {}


def _hay_que_avisar(tipo: str, ahora: float) -> bool:
    anterior = _ultima_campana.get(tipo)
    if anterior is not None and ahora - anterior < CADA_CUANTO_SE_REPITE:
        return False
    _ultima_campana[tipo] = ahora
    return True


def reiniciar_para_tests() -> None:
    _ultima_campana.clear()


async def gritar(db, *, tipo: str, titulo: str, mensaje: str, ruta: str,
                 user_id=None, metodo: str = "interno", status: int = 500) -> dict:
    """Log + fila en Errores + campana (con freno). Nunca levanta."""
    from services import errores, rastro

    logger.error("%s: %s", titulo, mensaje)
    resultado = {"asentado": False, "avisados": 0}

    try:
        await errores.anotar(db, rastro=rastro.actual(), metodo=metodo, ruta=ruta,
                             status=status, tipo=tipo, mensaje=mensaje, user_id=user_id)
        resultado["asentado"] = True
    except Exception as e:                                    # pragma: no cover
        logger.error("gritos: no se pudo asentar %s en Errores: %s", tipo, e)

    if not _hay_que_avisar(tipo, time.monotonic()):
        return resultado

    try:
        from services.notifications import avisar_al_personal
        resultado["avisados"] = await avisar_al_personal(
            title=titulo, message=mensaje, notification_type="error",
            solo_super_admin=True, data={"seccion": "errores", "tipo": tipo})
    except Exception as e:                                    # pragma: no cover
        logger.error("gritos: no se pudo avisar por %s: %s", tipo, e)
    return resultado


async def libro_sin_linea(db, *, libro: str, user_id, movement_type: str,
                          amount, account, error) -> dict:
    """El saldo se movió y el asiento no se escribió. Va con lo necesario para
    reponer la línea a mano: cuenta, movimiento y monto."""
    monto = amount if isinstance(amount, Decimal) else str(amount)
    return await gritar(
        db, tipo=LIBRO_SIN_LINEA,
        titulo=f"LIBRO SIN LINEA ({libro})",
        mensaje=(f"el asiento no se escribió y el saldo sí se movió: "
                 f"user_id={user_id} cuenta={account} movimiento={movement_type} "
                 f"monto={monto} · {type(error).__name__}: {error}"),
        ruta=f"libro/{libro}", user_id=user_id)


async def pago_a_direccion_equivocada(db, *, metodo: str, camino: str, motivo: str,
                                      pago=None) -> dict:
    """Llegó el aviso de un cobro a una dirección que no existe: el cobro NO se
    acreditó por esa vía."""
    from services.sin_ruta import DONDE_AVISA_MERCADOPAGO
    if motivo == "mercadopago":
        mensaje = (f"llegó un {metodo} a «{camino}» con forma de aviso de Mercado Pago "
                   f"(pago {pago or '(sin id)'}). El cobro NO se acreditó por esta vía. "
                   f"La dirección correcta es «{DONDE_AVISA_MERCADOPAGO}»: corregirla en el panel de Mercado Pago.")
    else:
        mensaje = (f"llegó un {metodo} a «{camino}» con parámetros. Si es la notificación "
                   f"de un proveedor de pagos, está mal configurada.")
    return await gritar(db, tipo=PAGO_A_DIRECCION_EQUIVOCADA,
                        titulo="AVISO DE PAGO A LA DIRECCION EQUIVOCADA",
                        mensaje=mensaje, ruta=camino, metodo=metodo, status=404)
