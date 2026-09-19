"""
tests/test_la_via_que_funciona.py — Que el «no se puede» diga qué SI se puede.

POR QUE EXISTE ESTE ARCHIVO

    Tres mensajes distintos terminaban en «podés recargar tu saldo»:

      · el del pago al final apagado,
      · el de los depósitos en cripto cerrados,
      · el de la vía cripto cerrada del todo.

    Los tres quedaron mintiendo el mismo día: cuando se pudo cerrar la carga
    de saldo, los tres seguían mandando a recargar a alguien que no puede
    recargar. Y la pantalla de recarga, además, lo rebota al panel — así que
    el usuario apretaba, volvía al principio y no se enteraba de por qué.

    Mintieron A LA VEZ porque los tres tenían la misma frase escrita por
    separado. Corregir las tres frases no alcanzaba: la respuesta correcta
    depende de la configuración, que se cambia desde el panel sin desplegar,
    así que cualquier frase fija vuelve a mentir en cuanto alguien aprieta un
    botón.

LO QUE ESTE ARCHIVO NO DEJA QUE SE ROMPA

    1. Que la salida que se nombra sea una que de verdad esté abierta.
    2. Que sin ninguna abierta no se invente ninguna.
    3. Que los TRES mensajes la pidan, y que ninguno vuelva a tener la suya.
"""
import asyncio
import os
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base                                # noqa: E402
from services import configuracion as cfg                     # noqa: E402
from services import la_via_que_funciona as via               # noqa: E402
from services import pago_al_final as paf                     # noqa: E402
from services import recarga_abierta as ra                    # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def poner(base, clave, valor):
    normalizado, error = cfg.normalizar(clave, valor)
    assert error is None, f"el panel rechazaría {valor}: {error}"
    corre(cfg.escribir(base, clave, normalizado))


# ══════════════════════════════════════════════════════════════════════════
# 1. Se nombra la vía que de verdad está abierta
# ══════════════════════════════════════════════════════════════════════════

def test_CON_LA_CARGA_ABIERTA_se_ofrece_cargar(base):
    """Es el estado de fábrica y el de hoy: nada cambia para nadie."""
    assert corre(via.para_poner_plata(base)) == via.CARGANDO_SALDO


def test_CON_LA_CARGA_CERRADA_se_ofrece_PAGAR_AL_FINAL(base):
    """El caso por el que existe este archivo."""
    poner(base, paf.CLAVE, 1)              # el seguro exige este orden
    poner(base, ra.CLAVE, ra.CERRADA)
    assert corre(via.para_poner_plata(base)) == via.PAGANDO_AL_FINAL


def test_CON_LA_CARGA_CERRADA_NO_SE_NOMBRA_LA_RECARGA(base):
    """La comprobación directa de la mentira: la palabra no puede aparecer."""
    poner(base, paf.CLAVE, 1)
    poner(base, ra.CLAVE, ra.CERRADA)
    assert "recarg" not in corre(via.para_poner_plata(base)).lower()


def test_la_carga_abierta_MANDA_aunque_el_pago_al_final_este_prendido(base):
    """Con las dos abiertas se nombra una sola: dos opciones en un mensaje de
    error es una decisión que el usuario no pidió tomar. Se nombra la que ya
    conoce."""
    poner(base, paf.CLAVE, 1)
    assert corre(via.para_poner_plata(base)) == via.CARGANDO_SALDO


# ══════════════════════════════════════════════════════════════════════════
# 2. Sin ninguna abierta no se inventa ninguna
# ══════════════════════════════════════════════════════════════════════════

def test_SIN_NINGUNA_VIA_manda_a_soporte_y_no_inventa(base):
    """No se llega por el panel —el seguro de `revisar_las_parejas` no deja
    guardar esa combinación—, se llega escribiendo en la base. Que es justo
    cuando un mensaje honesto más importa."""
    corre(cfg.escribir(base, ra.CLAVE, ra.CERRADA))
    corre(cfg.escribir(base, paf.CLAVE, 0))
    frase = corre(via.para_poner_plata(base))
    assert frase == via.NI_UNA_NI_OTRA
    assert "recarg" not in frase.lower()
    assert "al final" not in frase.lower()
    assert "soporte" in frase.lower()


def test_el_seguro_del_panel_NO_deja_llegar_a_ese_estado(base):
    """Y por eso el caso de arriba se siembra sin pasar por `normalizar`: el
    panel lo rechaza. Si un día dejara de rechazarlo, este test avisa."""
    motivo = corre(cfg.revisar_las_parejas(
        base, {ra.CLAVE: ra.CERRADA, "pago_al_final": 0}))
    assert motivo is not None


# ══════════════════════════════════════════════════════════════════════════
# 3. Las tres frases la piden, y ninguna tiene la suya
# ══════════════════════════════════════════════════════════════════════════

LOS_TRES = (
    ("services/pago_al_final.py", "SIN_PAGO_AL_FINAL"),
    ("services/cripto_abierta.py", "SIN_DEPOSITOS"),
    ("services/cripto_abierta.py", "CERRADA_DEL_TODO"),
)


@pytest.mark.parametrize("archivo, constante", LOS_TRES)
def test_NINGUNA_de_las_tres_vuelve_a_escribir_la_salida(archivo, constante):
    """Si una se escribe su propia salida, vuelve a mentir sola — y esta vez
    sin las otras dos al lado para que se note."""
    fuente = (_BACKEND / archivo).read_text(encoding="utf-8")
    i = fuente.index(f"{constante} = ")
    frase = fuente[i:fuente.index("\n\n", i)]
    for prohibido in ("recarg", "Podés", "PIX"):
        assert prohibido not in frase, (
            f"{constante} volvió a escribir su propia salida («{prohibido}»): "
            f"el día que esa vía se apague, este mensaje va a mentir y nadie "
            f"se va a enterar.")


@pytest.mark.parametrize("archivo, funcion", [
    ("services/pago_al_final.py", "exigir_activo"),
    ("services/cripto_abierta.py", "exigir_deposito"),
    ("services/cripto_abierta.py", "exigir_envio"),
])
def test_LAS_TRES_GUARDAS_piden_la_salida(archivo, funcion):
    fuente = (_BACKEND / archivo).read_text(encoding="utf-8")
    i = fuente.index(f"async def {funcion}(")
    cuerpo = fuente[i:]
    fin = cuerpo.find("\nasync def ")
    cuerpo = cuerpo if fin < 0 else cuerpo[:fin]
    assert "la_via_que_funciona.con" in cuerpo, (
        f"{funcion} dejó de pedir la salida: su mensaje va a quedarse en «no "
        f"disponible» sin decir qué hacer.")


def test_el_mensaje_entero_tiene_LAS_DOS_MITADES(base):
    """Lo que no se puede, y qué hacer en su lugar. Una sola de las dos deja
    al usuario sabiendo que falló o sabiendo qué hacer, nunca las dos cosas."""
    entero = corre(via.con(base, "Esto no está disponible."))
    assert entero.startswith("Esto no está disponible.")
    assert via.CARGANDO_SALDO in entero


# ══════════════════════════════════════════════════════════════════════════
# 4. El vocabulario de la aplicación
# ══════════════════════════════════════════════════════════════════════════

def test_se_dice_GASTAR_y_no_enviar_dinero():
    """El menú del cliente dice «Gastar en Venezuela» y «Gastar en Brasil».
    Dos vocabularios para la misma acción es como se termina llamándola de
    tres formas — la lección ya está escrita en `cripto_abierta.py`."""
    for frase in (via.CARGANDO_SALDO, via.PAGANDO_AL_FINAL, via.NI_UNA_NI_OTRA):
        assert "enviar dinero" not in frase.lower()
        assert "envio de dinero" not in frase.lower()


def test_la_de_pagar_al_final_NOMBRA_LAS_DOS_FORMAS_DE_PAGARLO():
    """PIX y tarjeta. Nombrar sólo una esconde la que a esa persona le sirve."""
    assert "PIX" in via.PAGANDO_AL_FINAL
    assert "tarjeta" in via.PAGANDO_AL_FINAL
