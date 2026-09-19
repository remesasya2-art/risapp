"""
¿Se puede cargar saldo? Una sola definición, y la miran las cuatro puertas.

POR QUE ESTO EXISTE

    La empresa no puede custodiar dinero de terceros ni ofrecer recarga. No es
    una preferencia de producto que se prende y se apaga: es el límite dentro
    del que opera, por el mismo motivo por el que se apagó la vía cripto —ver
    `docs/politica-pld-ft.md`, sección 1—.

    Así que el estado al que hay que llegar es CERRADA. Lo que este archivo
    aporta es poder llegar ahí sin romper nada en el camino, y sin atrapar el
    saldo que alguien ya tenga.

    El ajuste viene de fábrica en ABIERTA por una sola razón, y no es pereza:
    el despliegue no puede ser el que apague la recarga, porque en ese mismo
    instante los envíos —que hoy exigen saldo— se quedarían sin forma de
    financiarse. Ver EL SEGURO, más abajo. Son dos clics del panel, en orden.

QUE SE APAGA Y QUE NO

    Se apaga CARGAR SALDO: el PIX de recarga, la tarjeta y la transferencia en
    bolívares. Son las cuatro rutas por las que hoy entra plata a la billetera.

    NO se apaga GASTAR EL SALDO. «Gastar en Venezuela» y «Gastar en Brasil»
    siguen funcionando igual, y es lo primero que pidió el dueño del proyecto.
    Quien tiene saldo lo sigue usando; lo que deja de poder es cargar más.

    Tampoco se apagan los reembolsos. `balance_ris` pasa a ser la billetera de
    devoluciones, así que tiene que poder seguir recibiendo.

DOS ESTADOS, NO TRES

    La vía cripto tiene tres porque se puede cerrar del todo. Esta no: el saldo
    recibe reembolsos para siempre, así que «cerrada» no existe.

        1  abierta   se puede cargar saldo, como siempre. De fábrica, y
                     sólo hasta que el pago al final esté prendido.
        0  cerrada   no entra saldo nuevo. El que hay se gasta y sigue
                     recibiendo devoluciones. ES EL ESTADO AL QUE SE VA.

EL SEGURO, Y ES LA PARTE IMPORTANTE DE ESTE ARCHIVO

    «Gastar en Venezuela» y «Gastar en Brasil» EXIGEN saldo cargado
    (`routes/transactions.py`, el `$gte` sobre `balance_ris` en las dos). El
    flujo que cobra al final —`services/pago_al_final.py`— es el único que
    permite enviar sin saldo previo, y de fábrica viene apagado.

    O sea que apagar la recarga con ese flujo apagado deja la aplicación SIN
    NINGUNA FORMA DE ENVIAR: no se puede cargar, y sin carga no se puede
    gastar. La pantalla no lo diría; simplemente nada funcionaría.

    Por eso hay una regla ENTRE LOS DOS AJUSTES, y vive donde ya viven las de
    su clase: `configuracion.revisar_las_parejas`, que se comprueba ANTES de
    escribir nada. Esa función existe porque poner el mínimo de PIX por encima
    del máximo mataba esa vía en silencio. Es exactamente el mismo problema,
    con dos ajustes en vez de uno.

    El panel rechaza apagar la recarga mientras «pagar al final» esté apagado,
    y lo dice con el motivo. Prender primero, apagar después.

FALLA ABIERTO, AL REVES QUE LA GUARDA DE LA CRIPTO

    Si la base no contesta, esta guarda DEJA CARGAR. Es lo contrario de
    `cripto_abierta`, y la diferencia tiene motivo:

      · Allá, dejar entrar plata sin poder comprobar el estado creaba custodia
        que quizá no se podía devolver. El daño estaba en dejar pasar.
      · Acá, el daño está en frenar: cargar saldo es algo que la aplicación
        viene haciendo desde siempre y que no le hace mal a nadie. Negárselo a
        alguien porque nuestra base tuvo un mal momento es cobrarle al usuario
        una falla nuestra, que es justo lo que la sección 9 del dossier dice
        que no se hace.
"""
import logging

from fastapi import HTTPException

logger = logging.getLogger(__name__)

CLAVE = "recarga_abierta"

CERRADA = 0
ABIERTA = 1

# Lo que ve el usuario. Nombra la vía que SI funciona: sin eso, «no disponible»
# lo manda a soporte a preguntar qué hacer.
SIN_RECARGA = ("Cargar saldo no está disponible por ahora. Podés enviar "
               "directamente y pagar el envío al final.")


async def esta_abierta(db) -> bool:
    """¿Se puede cargar saldo?"""
    from services import configuracion
    try:
        return int(await configuracion.leer(db, CLAVE)) == ABIERTA
    except Exception as e:                                    # pragma: no cover
        # Falla ABIERTO. Ver el encabezado: acá el daño está en frenar.
        logger.error("No se pudo leer %s, se asume abierta: %s", CLAVE, e)
        return True


async def exigir_abierta(db) -> None:
    """Frena la ruta si no se puede cargar saldo.

    503 y no 403: no es que esta cuenta no tenga permiso, es que el servicio no
    está dando eso ahora.
    """
    if not await esta_abierta(db):
        raise HTTPException(status_code=503, detail=SIN_RECARGA)


def motivo_si_deja_la_app_sin_salida(recarga: int, pago_al_final: int):
    """El seguro. Devuelve el motivo del rechazo, o None si la pareja cierra.

    Se llama desde `configuracion.revisar_las_parejas`, que arma cómo QUEDARIA
    la configuración —lo guardado más lo que se está por guardar— y la mira
    antes de escribir nada. Por eso acá llegan números, no la base: la decisión
    es sobre el resultado, no sobre lo que se mandó.
    """
    if int(recarga) == CERRADA and int(pago_al_final) == 0:
        return (
            "No se puede cerrar la carga de saldo mientras «pagar el envío al "
            "final» esté apagado. Los envíos a Venezuela y a Brasil exigen "
            "saldo cargado, así que con los dos apagados nadie podría enviar "
            "nada. Prendé primero el pago al final, y después cerrá la carga.")
    return None
