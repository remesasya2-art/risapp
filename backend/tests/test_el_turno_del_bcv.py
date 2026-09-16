"""
tests/test_el_turno_del_bcv.py — Que una tarea de fondo la haga UN solo proceso.

DE DONDE SALE

    De la revisión de capacidad para dos mil usuarios activos. Correr más de un
    proceso es lo que más capacidad agrega, y no se podía: el raspador del BCV
    vive adentro del proceso de la aplicación, así que cada proceso arranca su
    propio reloj.

QUE COSTARIA SIN ESTO, CON CUATRO PROCESOS

    · Cuatro pedidos por hora al sitio del BCV. Es un sitio del gobierno
      venezolano, lento, y que puede bloquear por exceso.
    · Filas duplicadas en el historial de tasas: `save_snapshot` mira la última
      fila y DESPUES escribe, y entre esas dos cosas pasa el otro proceso.
    · El aviso de «la tasa venció» repetido a cada super administrador, por la
      misma razón.

Y UNA DE ESAS CARRERAS YA EXISTE HOY, CON UN SOLO PROCESO

    El panel tiene un botón para refrescar la tasa a mano, y ese camino llama
    al mismo `save_snapshot`. Si alguien lo aprieta justo cuando el reloj de la
    hora dispara, entran dos filas. Por eso el botón pide el MISMO turno.
"""
import asyncio
import os
import sys
import time

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base                              # noqa: E402
from services import turnos                                 # noqa: E402


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test_turnos"]
    usar_base(b)
    return b


def correr(corrutina):
    return asyncio.run(corrutina)


# ══════════════════════════════════════════════════════════════════════════
# 1. El turno se lo lleva uno solo
# ══════════════════════════════════════════════════════════════════════════

def test_EL_PRIMERO_SE_LLEVA_EL_TURNO(base):
    assert correr(turnos.me_toca(base, "bcv", segundos=60)) is True


def test_EL_SEGUNDO_NO_SE_LO_LLEVA(base):
    """EL TEST QUE IMPORTA. Es la diferencia entre una raspada por hora y
    cuatro, y entre un aviso al equipo y cuatro."""
    assert correr(turnos.me_toca(base, "bcv", segundos=60)) is True
    assert correr(turnos.me_toca(base, "bcv", segundos=60)) is False


def test_DE_VARIOS_A_LA_VEZ_GANA_EXACTAMENTE_UNO(base):
    """Cuatro procesos arrancando juntos es justo el caso del despliegue: los
    relojes de todos quedan alineados y disparan en el mismo instante."""
    async def cuatro():
        return await asyncio.gather(*[
            turnos.me_toca(base, "bcv", segundos=60) for _ in range(4)])

    assert sum(1 for gano in correr(cuatro()) if gano) == 1


def test_CADA_TAREA_TIENE_SU_PROPIO_TURNO(base):
    """Sin el nombre, prender una segunda tarea de fondo apagaría la primera."""
    assert correr(turnos.me_toca(base, "bcv", segundos=60)) is True
    assert correr(turnos.me_toca(base, "otra-cosa", segundos=60)) is True


# ══════════════════════════════════════════════════════════════════════════
# 2. El turno caduca solo
# ══════════════════════════════════════════════════════════════════════════

def test_CUANDO_CADUCA_LO_TOMA_EL_SIGUIENTE(base):
    """Si el proceso que se llevó el turno se muere a la mitad, nadie puede
    quedar esperando para siempre: la tasa dejaría de actualizarse y no habría
    ningún error que lo dijera."""
    assert correr(turnos.me_toca(base, "bcv", segundos=0.05)) is True
    time.sleep(0.1)
    assert correr(turnos.me_toca(base, "bcv", segundos=60)) is True


def test_MIENTRAS_NO_CADUCA_NO_LO_TOMA_NADIE(base):
    """La mutación de la de arriba: que la caducidad no sea una puerta abierta
    que deja pasar a todos."""
    assert correr(turnos.me_toca(base, "bcv", segundos=60)) is True
    time.sleep(0.1)
    assert correr(turnos.me_toca(base, "bcv", segundos=60)) is False


def test_EL_VENCIMIENTO_SE_GUARDA_COMO_NUMERO(base):
    """Guardado como fecha, la comparación cruza una con zona horaria contra una
    sin zona —el driver las devuelve sin zona— y eso no da False: levanta
    TypeError. En este repositorio eso ya vació un informe entero."""
    correr(turnos.me_toca(base, "bcv", segundos=60))
    guardado = correr(base[turnos.COLECCION].find_one({"_id": "bcv"}))
    assert isinstance(guardado["vence_en"], (int, float)), guardado


# ══════════════════════════════════════════════════════════════════════════
# 3. Soltar el turno
# ══════════════════════════════════════════════════════════════════════════

def test_SOLTARLO_DEJA_ENTRAR_AL_SIGUIENTE_ENSEGUIDA(base):
    """El botón del panel termina en segundos y no tiene por qué dejar el turno
    tomado los dos minutos completos."""
    assert correr(turnos.me_toca(base, "bcv", segundos=120)) is True
    assert correr(turnos.soltar(base, "bcv")) is True
    assert correr(turnos.me_toca(base, "bcv", segundos=120)) is True


def test_NADIE_PUEDE_SOLTAR_UN_TURNO_QUE_NO_ES_SUYO(base):
    """Un proceso que tardó de más le soltaría al siguiente un turno que ya no
    era suyo, y entonces habría dos raspando a la vez — que es exactamente lo
    que todo esto viene a evitar."""
    correr(turnos.me_toca(base, "bcv", segundos=120))
    correr(base[turnos.COLECCION].update_one(
        {"_id": "bcv"}, {"$set": {"quien": "otro-proceso"}}))

    assert correr(turnos.soltar(base, "bcv")) is False
    assert correr(turnos.me_toca(base, "bcv", segundos=120)) is False


# ══════════════════════════════════════════════════════════════════════════
# 4. Cómo lo usa el raspador del BCV
# ══════════════════════════════════════════════════════════════════════════

def test_EL_TURNO_DURA_MENOS_QUE_CADA_CUANTO_SE_RASPA():
    """LA REGLA QUE APAGARIA LA TASA SI SE ROMPE. Un turno más largo que el
    intervalo nunca estaría caducado cuando el reloj pregunte, así que la
    segunda vuelta no raspa — ni la tercera, ni ninguna. Y no habría ningún
    error: simplemente la tasa se quedaría vieja para siempre.
    """
    from services import bcv_scraper
    import re

    arranque = open(os.path.join(_BACKEND, "server.py"), encoding="utf-8").read()
    horas = re.search(r"start_scheduler\(db,\s*interval_hours=([\d.]+)\)", arranque)
    assert horas, "no se encontró cómo arranca el reloj del BCV"

    intervalo = float(horas.group(1)) * 3600
    assert bcv_scraper.SEGUNDOS_DEL_TURNO < intervalo / 2, (
        f"el turno dura {bcv_scraper.SEGUNDOS_DEL_TURNO}s y el reloj corre "
        f"cada {intervalo}s: demasiado cerca")


def test_EL_RELOJ_PIDE_EL_TURNO_ANTES_DE_RASPAR():
    """Definir el turno y no pedirlo deja todo lo demás en verde y los cuatro
    procesos raspando igual."""
    fuente = open(os.path.join(_BACKEND, "services", "bcv_scraper.py"),
                  encoding="utf-8").read()
    cuerpo = fuente.split("async def _scheduler_loop", 1)[1]
    pedido = cuerpo.find("turnos.me_toca")
    raspada = cuerpo.find("fetch_bcv_rates()")
    assert pedido != -1, "el reloj no pide el turno"
    assert pedido < raspada, "el reloj raspa antes de pedir el turno"


def test_EL_BOTON_DEL_PANEL_PIDE_EL_MISMO_TURNO():
    """Si pidiera otro, el botón y el reloj podrían raspar a la vez — que es la
    carrera que ya existe hoy, con un solo proceso."""
    fuente = open(os.path.join(_BACKEND, "routes", "admin.py"),
                  encoding="utf-8").read()
    cuerpo = fuente.split("async def refresh_bcv_rates", 1)[1].split("@router")[0]
    assert "turnos.me_toca(db, TURNO" in cuerpo, (
        "el botón de refrescar no pide el turno del raspador")
    assert "turnos.soltar(db, TURNO)" in cuerpo, (
        "el botón no suelta el turno al terminar")
