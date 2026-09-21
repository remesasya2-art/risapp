"""
¿Se pueden mandar encomiendas nuevas? Una sola definición, y la miran todas las
puertas.

POR QUE ESTO EXISTE

    El servicio de encomiendas se suspende por ahora. Es una decisión del dueño
    del proyecto, tomada mientras reordena qué ofrece la empresa y bajo qué
    figura —el mismo movimiento por el que se cerró la recarga
    (`services/recarga_abierta.py`) y se apagó la vía cripto—.

    El módulo no tenía llave. Tenía un diagnóstico de puesta en marcha
    (`services/envios_puesta_en_marcha.py`) que dice si FALTA configurar algo,
    y cuando falta, `/envios/limites` contesta `disponible: false`. Pero con
    todo configurado no había forma de apagarlo a propósito: la única era
    borrar la tarifa, que es romperlo para apagarlo — y el día de volver a
    prender, volver a cargarla.

    Esto es la llave. Se apaga y se prende desde Configuración, sin tocar
    código, como manda la regla de la casa.

QUE SE APAGA Y QUE NO

    Se apaga CREAR ENCOMIENDAS NUEVAS: cotizar y confirmar. Son las dos rutas
    por las que nace un envío.

    NO se apaga lo que ya está en viaje. «Mis envíos», el detalle de cada uno,
    el seguimiento público, subir el comprobante y pagar los cobros de un envío
    en curso siguen funcionando. Un paquete que ya salió tiene que poder
    terminar su viaje, y quien lo mandó tiene que poder verlo. Cerrarle eso
    sería dejarle una caja en el limbo, que es peor que la suspensión que se
    quiso hacer.

    Tampoco se apaga el panel de Encomiendas: el operador tiene que despachar y
    entregar lo que quedó en camino, y desde ahí se vuelve a prender.

DOS ESTADOS

        1  abierta   se pueden mandar encomiendas, como siempre. De fábrica.
        0  cerrada   no nacen envíos nuevos. Los que hay siguen su curso.

    De fábrica viene ABIERTA porque el despliegue no cambia el comportamiento
    de la aplicación: eso lo decide una persona, en el panel, cuando quiere.
    Es la misma regla con la que se hizo la recarga.

FALLA ABIERTO, COMO LA RECARGA

    Si la base no contesta, esta guarda DEJA MANDAR. El motivo es el mismo que
    está escrito en `recarga_abierta.py`: mandar un paquete es algo que la
    aplicación viene haciendo y que no le hace mal a nadie. Negárselo a alguien
    porque nuestra base tuvo un mal momento es cobrarle al usuario una falla
    nuestra.
"""
import logging

from fastapi import HTTPException

logger = logging.getLogger(__name__)

CLAVE = "encomiendas_abiertas"

CERRADA = 0
ABIERTA = 1

# Lo que ve el usuario. Dice que lo que ya mandó sigue igual: sin eso, «no
# disponible» lo manda a soporte a preguntar por la caja que ya salió.
SUSPENDIDO = ("El envío de paquetes está suspendido por ahora. Los envíos que "
              "ya están en camino siguen igual y los podés ver en «Mis envíos».")


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


async def esta_abierta(db=None) -> bool:
    """¿Se pueden mandar encomiendas nuevas?"""
    from services import configuracion
    try:
        return int(await configuracion.leer(await _db(db), CLAVE)) == ABIERTA
    except Exception as e:                                    # pragma: no cover
        # Falla ABIERTO. Ver el encabezado: acá el daño está en frenar.
        logger.error("No se pudo leer %s, se asume abierta: %s", CLAVE, e)
        return True


async def exigir_abierta(db=None) -> None:
    """Frena la ruta si el servicio está suspendido.

    503 y no 403: no es que esta cuenta no tenga permiso, es que el servicio no
    está dando eso ahora.
    """
    if not await esta_abierta(db):
        raise HTTPException(status_code=503, detail=SUSPENDIDO)
