"""
services/turnos.py — Que una tarea de fondo la haga UN solo proceso.

PARA QUE EXISTE

    La aplicación arranca hoy con `uvicorn server:app` sin `--workers`: un
    proceso, una réplica. Las tareas de fondo que viven adentro del proceso
    —el raspador del BCV es la única por ahora— corren una vez porque hay un
    solo proceso, no porque nadie las haya frenado.

    El día que se prendan varios procesos para aguantar más gente, cada uno
    arranca su propio reloj y la tarea se hace CUATRO veces por hora. Eso no
    es sólo desperdicio: son cuatro pedidos al sitio del BCV —un sitio del
    gobierno venezolano, lento, que puede bloquear por exceso— y cuatro
    escrituras que se pisan entre sí.

COMO SE REPARTE EL TURNO

    El que quiere hacer la tarea pide el turno. Se lo lleva UNO solo, y los
    demás se saltan la vuelta sin hacer nada.

    La condición —«el turno anterior ya caducó»— va DENTRO del filtro de la
    escritura, no en un `if` antes. Es el mismo patrón que la reserva del CPF
    y los lotes de pago: leer y después escribir deja una ventana por la que
    pasan los dos. Así, el primero que llega mueve el vencimiento al futuro y
    el segundo ya no encuentra a quién escribirle.

EL TURNO CADUCA SOLO, Y POR ESO NO HAY QUE DEVOLVERLO

    Si el proceso que se llevó el turno se muere a la mitad —se reinicia el
    servicio, se corta la red— nadie queda esperando para siempre: pasados los
    segundos del turno, el siguiente que pregunte se lo lleva.

    Por eso el turno tiene que durar MENOS que cada cuánto se repite la tarea.
    Un turno de diez minutos sobre una tarea que corre cada hora está bien; uno
    de dos horas sobre la misma tarea la apagaría para siempre, porque nunca
    estaría caducado cuando alguien pregunte.

EL VENCIMIENTO SE GUARDA COMO NUMERO, NO COMO FECHA

    Y no es capricho. El driver devuelve las fechas SIN zona horaria, y
    comparar una con zona contra una sin zona no devuelve `False`: levanta
    `TypeError`. En este mismo repositorio eso ya vació un informe entero.
    Un número comparado contra otro número no tiene ese problema en ningún
    lado, ni contra Mongo ni contra el doble que se usa en los tests.
"""
import logging
import os
import time
import uuid

from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

COLECCION = "turnos"

# Quién es este proceso. Sólo para poder leer en el registro cuál se lo llevó;
# no se usa para decidir nada.
QUIEN_SOY = f"{os.getpid()}-{uuid.uuid4().hex[:6]}"


async def me_toca(db, nombre: str, *, segundos: float) -> bool:
    """¿Le toca a este proceso hacer `nombre`? Devuelve True al que se lo lleva.

    `segundos` es cuánto dura el turno: tiene que alcanzar para hacer la tarea
    y ser MENOS que cada cuánto se repite. Ver el encabezado.

    NO LEVANTA NUNCA. Si la base no contesta, devuelve False: mejor saltarse
    una vuelta que tumbar el reloj de fondo con una excepción que nadie mira.
    """
    ahora = time.time()
    hasta = ahora + segundos

    try:
        # Primera vez: no existe el turno. `_id` es único por construcción, así
        # que de dos procesos que arrancan juntos entra uno solo.
        try:
            await db[COLECCION].insert_one(
                {"_id": nombre, "vence_en": hasta, "tomado_en": ahora,
                 "quien": QUIEN_SOY})
            return True
        except DuplicateKeyError:
            pass

        # Ya existe: se lo lleva quien lo encuentre caducado. La condición va
        # adentro del filtro, que es lo que lo hace atómico.
        resultado = await db[COLECCION].update_one(
            {"_id": nombre, "vence_en": {"$lte": ahora}},
            {"$set": {"vence_en": hasta, "tomado_en": ahora,
                      "quien": QUIEN_SOY}},
        )
        return getattr(resultado, "modified_count", 0) == 1
    except Exception as e:                                # pragma: no cover
        logger.warning("turnos: no se pudo pedir el turno %r (%s)", nombre, e)
        return False


async def soltar(db, nombre: str) -> bool:
    """Devuelve el turno antes de tiempo, si todavía es de este proceso.

    No hace falta para que el turno se libere —caduca solo— pero sirve cuando
    la tarea terminó rápido y conviene que el siguiente pueda entrar enseguida:
    el botón de refrescar del panel, por ejemplo, no tiene por qué dejar el
    turno tomado dos minutos después de haber terminado en treinta segundos.

    Sólo suelta el turno PROPIO. Sin esa condición, un proceso que tardó de más
    le soltaría al siguiente un turno que ya no era suyo.
    """
    try:
        resultado = await db[COLECCION].delete_one(
            {"_id": nombre, "quien": QUIEN_SOY})
        return bool(getattr(resultado, "deleted_count", 0))
    except Exception as e:                                # pragma: no cover
        logger.warning("turnos: no se pudo soltar el turno %r (%s)", nombre, e)
        return False
