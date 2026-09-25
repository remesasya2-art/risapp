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
    fuente = open(os.path.join(_BACKEND, "routes", "admin", "tasas.py"),
                  encoding="utf-8").read()
    cuerpo = fuente.split("async def refresh_bcv_rates", 1)[1].split("@router")[0]
    assert "turnos.me_toca(db, TURNO" in cuerpo, (
        "el botón de refrescar no pide el turno del raspador")
    assert "turnos.soltar(db, TURNO)" in cuerpo, (
        "el botón no suelta el turno al terminar")


# ══════════════════════════════════════════════════════════════════════════
# EL LATIDO
# ══════════════════════════════════════════════════════════════════════════
#
# QUE PASO
#
#     Cinco horas de registro sin una sola línea del raspador. Desde afuera eso
#     significaba dos cosas a la vez y no había cómo distinguirlas:
#
#         · raspó cada hora, la tasa no cambió, todo bien
#         · el reloj está muerto y la tasa está congelada
#
#     Porque la vuelta sin novedad escribía un `logger.debug` y el registro
#     corre en INFO. El caso normal era, literalmente, invisible.
#
#     Hubo que preguntarle la antigüedad a `/api/rate` para salir de la duda.
#     Un reloj que sólo habla cuando pasa algo no se puede vigilar.

def _la_vuelta():
    """El árbol de `_scheduler_loop` y su fuente, para mirarlo por dentro."""
    import ast

    ruta = os.path.join(_BACKEND, "services", "bcv_scraper.py")
    fuente = open(ruta, encoding="utf-8").read()
    arbol = ast.parse(fuente, ruta)
    vuelta = next(n for n in ast.walk(arbol)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == "_scheduler_loop")
    return vuelta, fuente


def _escribe(nodos):
    """¿Hay alguna llamada a `logger.info/warning/error` acá adentro?"""
    import ast

    for raiz in nodos:
        for n in ast.walk(raiz):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("info", "warning", "error")
                    and isinstance(n.func.value, ast.Name)
                    and n.func.value.id == "logger"):
                return True
    return False


def test_NINGUNA_RAMA_DE_LA_VUELTA_SE_QUEDA_CALLADA():
    """Cada forma de terminar una vuelta deja su línea.

    SE MIRA RAMA POR RAMA, Y NO SE CUENTAN LAS ESCRITURAS. La primera versión
    de esta guarda contaba: exigía cuatro o más. Y sobrevivió a borrarle la
    línea a la rama del turno salteado, porque quedaban cuatro igual.

    Justamente esa rama es la que más importa con varios procesos: con dos
    workers, la mitad de las vueltas termina ahí. Si se calla, el reloj parece
    muerto cuando está sano — el mismo susto que motivó todo esto, al revés.
    """
    import ast

    vuelta, _ = _la_vuelta()

    assert not any(isinstance(n, ast.Attribute) and n.attr == "debug"
                   for n in ast.walk(vuelta)), (
        "la vuelta escribe un `debug`, y el registro corre en INFO: esa línea "
        "no se ve. Es exactamente lo que hacía invisible al caso normal.")

    # 1. El turno se lo llevó otro proceso.
    salteada = [n for n in ast.walk(vuelta)
                if isinstance(n, ast.If)
                and any(isinstance(c, ast.Attribute) and c.attr == "me_toca"
                        for c in ast.walk(n.test))]
    assert salteada, "no se encontró la rama del turno en la vuelta"
    assert _escribe(salteada[0].body), (
        "la vuelta se saltea sin escribir nada. Con varios procesos ésta es la "
        "rama más frecuente: callada, un reloj sano parece muerto.")

    # 2. y 3. Raspó: la tasa cambió, o no cambió.
    guardo = [n for n in ast.walk(vuelta)
              if isinstance(n, ast.If) and isinstance(n.test, ast.Name)
              and n.test.id == "saved"]
    assert guardo, "no se encontró la rama de «se guardó la tasa»"
    assert _escribe(guardo[0].body), "no dice nada cuando la tasa cambió"
    assert _escribe(guardo[0].orelse), (
        "no dice nada cuando la tasa NO cambió, que es el caso normal y el que "
        "estuvo invisible cinco horas")

    # 4. Se cayó la raspada.
    fallos = [n for n in ast.walk(vuelta) if isinstance(n, ast.ExceptHandler)]
    assert fallos, "la vuelta no atrapa fallos"
    for f in fallos:
        assert _escribe(f.body), "un fallo de la vuelta se traga sin escribir"


def test_TODAS_LAS_LINEAS_DE_LA_VUELTA_LLEVAN_LA_MISMA_MARCA():
    """Que el pulso se pueda buscar con UN solo término.

    Sin una marca común hay que acordarse de cuatro frases distintas para
    comprobar si el reloj late, y quien mira el registro a las dos de la mañana
    no se acuerda de ninguna.

    Se lee con `ast` y no con una expresión regular: la primera versión de esta
    guarda usaba una, se quedaba con el primer renglón de cada llamada, y daba
    por «sin marca» a las que la tenían en la línea siguiente. Una guarda que
    grita en falso es una guarda que alguien apaga.
    """
    import ast
    from services import bcv_scraper

    ruta = os.path.join(_BACKEND, "services", "bcv_scraper.py")
    fuente = open(ruta, encoding="utf-8").read()
    arbol = ast.parse(fuente, ruta)

    vuelta = next(n for n in ast.walk(arbol)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == "_scheduler_loop")

    sin_marca = []
    for n in ast.walk(vuelta):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if not (isinstance(f, ast.Attribute)
                and f.attr in ("info", "warning", "error")
                and isinstance(f.value, ast.Name) and f.value.id == "logger"):
            continue
        texto = ast.get_source_segment(fuente, n) or ""
        if "LATIDO" not in texto:
            sin_marca.append(" ".join(texto.split())[:70])

    assert not sin_marca, (
        f"estas líneas de la vuelta no llevan la marca del latido: {sin_marca}. "
        f"Buscar «{bcv_scraper.LATIDO}» en el registro tiene que mostrar el "
        "pulso completo del reloj.")

    assert bcv_scraper.LATIDO, "la marca quedó vacía: no se puede buscar"


def test_EL_LATIDO_ES_MAS_SEGUIDO_QUE_LA_PACIENCIA_DE_QUIEN_MIRA():
    """Un pulso que late cada seis horas no sirve para saber si está vivo.

    Se lee el intervalo de verdad desde `server.py`, igual que la guarda del
    turno: si alguien lo sube a seis horas, el latido deja de ser útil como
    señal de vida y esto lo dice.
    """
    import re

    arranque = open(os.path.join(_BACKEND, "server.py"), encoding="utf-8").read()
    horas = re.search(r"start_scheduler\(db,\s*interval_hours=([\d.]+)\)", arranque)
    assert horas, "no se encontró cómo arranca el reloj del BCV"
    assert float(horas.group(1)) <= 2, (
        f"el reloj late cada {horas.group(1)}h. Más de dos horas de silencio "
        "normal vuelve a hacer indistinguible «tranquilo» de «muerto».")
