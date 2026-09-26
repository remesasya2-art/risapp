"""
tests/test_remesas_cerradas.py — La llave del servicio de remesas.

POR QUE EXISTE ESTE ARCHIVO

    Remesas no tenía llave: sus dos puertas principales —gastar en Venezuela y
    en Brasil— no miraban nada. El día que el banco opere con un socio
    regulado, remesas se tiene que poder pausar desde el panel. El por qué y
    qué corta cada cosa: services/remesas_abiertas.py.

LO QUE ESTE ARCHIVO NO DEJA QUE SE ROMPA

    1. Que la llave venga abierta de fábrica y esté en Configuración.
    2. Que cerrarla cierre las CINCO puertas por las que nace un envío, y
       ninguna de las que terminan algo que ya empezó.
    3. Que sea la llave madre: cerrada, cierra la carga de saldo y la entrada
       de cripto aunque sus llaves digan otra cosa — y deja la salida de
       cripto abierta.
    4. Que la pantalla lo sepa por /api/limits, ya recortado.
    5. Que no nazca un bono de bienvenida que no se puede gastar, y que los
       mensajes no manden a nadie a una puerta cerrada.
"""
import asyncio
import logging
import os
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from fastapi import HTTPException                             # noqa: E402

from conftest import usar_base                                # noqa: E402
from services import configuracion as cfg                     # noqa: E402
from services import cripto_abierta, recarga_abierta          # noqa: E402
from services import remesas_abiertas as ra                   # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_remesas"]
    usar_base(b)
    return b


def poner(base, clave, valor):
    normalizado, error = cfg.normalizar(clave, valor)
    assert error is None, f"el panel rechazaría {valor}: {error}"
    corre(cfg.escribir(base, clave, normalizado))


# ══════════════════════════════════════════════════════════════════════════
# 1. La llave
# ══════════════════════════════════════════════════════════════════════════

def test_DE_FABRICA_REMESAS_SIGUE_ABIERTA(base):
    """El despliegue no pausa nada: eso lo decide una persona, en el panel."""
    assert corre(ra.esta_abierta(base)) is True


def test_la_llave_esta_en_configuracion_y_es_de_dos_estados():
    """Si no está en el catálogo, no se puede pausar sin tocar código, que es
    lo que la regla de la casa prohíbe."""
    ajuste = cfg.AJUSTES[ra.CLAVE]
    assert ajuste.tipo == cfg.ENTERO
    assert (ajuste.minimo, ajuste.maximo) == (ra.CERRADAS, ra.ABIERTAS)
    assert ajuste.defecto == ra.ABIERTAS


def test_cerrada_frena_con_503_y_dice_que_lo_empezado_sigue(base):
    poner(base, ra.CLAVE, ra.CERRADAS)
    with pytest.raises(HTTPException) as e:
        corre(ra.exigir_abierta(base))
    assert e.value.status_code == 503
    assert e.value.detail == ra.EN_PAUSA
    assert "en curso sigue igual" in ra.EN_PAUSA


def test_el_mensaje_usa_el_vocabulario_de_la_aplicacion():
    """«Gastar», como el menú. No «enviar dinero»: ver cripto_abierta.py."""
    assert "Gastar en Venezuela" in ra.EN_PAUSA
    assert "enviar dinero" not in ra.EN_PAUSA.lower()


class _BaseRota:
    def __getattr__(self, nombre):
        raise ConnectionError("la base no contesta")

    def __getitem__(self, nombre):
        raise ConnectionError("la base no contesta")


def test_SI_LA_BASE_NO_CONTESTA_DEJA_PASAR():
    assert corre(ra.esta_abierta(_BaseRota())) is True


# ══════════════════════════════════════════════════════════════════════════
# 2. Las puertas, mirando la aplicación armada
# ══════════════════════════════════════════════════════════════════════════

# Las cinco por las que nace un envío. Escritas una por una: agregar la sexta
# tiene que ser una decisión visible.
PUERTAS = {
    ("POST", "/api/withdraw"),
    ("POST", "/api/withdrawal/create"),
    ("POST", "/api/reais/send"),
    ("POST", "/api/withdraw-ves/cotizar"),
    ("POST", "/api/enviar-reais/cotizar"),
}

# Las que TERMINAN algo que ya empezó, o lo muestran. Cerrarlas con remesas en
# pausa dejaría una operación pagada a medio camino.
NO_SE_CIERRAN = {
    ("POST", "/api/enviar-reais/comprobante"),
    ("POST", "/api/payments/card/envio"),
    ("POST", "/api/gestor/pix/cancel/{payment_id}"),
    ("POST", "/api/webhook/mercadopago"),
    ("POST", "/api/credits/webhook"),
    ("POST", "/api/crypto-send/webhook"),
    ("POST", "/api/btc/webhook/blink"),
    ("GET", "/api/transactions"),
    ("GET", "/api/withdrawal/pending"),
}


def _nombres_de_dependencias(dependant, visto=None):
    visto = visto if visto is not None else set()
    salida = []
    for d in getattr(dependant, "dependencies", []) or []:
        if id(d) in visto:
            continue
        visto.add(id(d))
        if getattr(d, "call", None):
            salida.append(d.call.__name__)
        salida.extend(_nombres_de_dependencias(d, visto))
    return salida


@pytest.fixture(scope="module")
def rutas():
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "ris_test")
    try:
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    salida = {}
    for ruta in app.routes:
        for metodo in getattr(ruta, "methods", None) or ():
            salida[(metodo, ruta.path)] = "con_remesas_abiertas" in \
                _nombres_de_dependencias(ruta.dependant)
    return salida


def test_LAS_CINCO_PUERTAS_LLEVAN_LA_LLAVE(rutas):
    faltan = sorted(f"{m} {c}" for m, c in PUERTAS if not rutas.get((m, c)))
    assert not faltan, ("estas rutas crean un envío y no miran la llave de "
                        "remesas: " + ", ".join(faltan))


def test_NINGUNA_RUTA_QUE_TERMINA_ALGO_LLEVA_LA_LLAVE(rutas):
    for clave in NO_SE_CIERRAN:
        assert clave in rutas, f"ya no existe {clave}: revisá esta lista"
    cerradas = sorted(f"{m} {c}" for m, c in NO_SE_CIERRAN if rutas[(m, c)])
    assert not cerradas, ("estas rutas terminan una operación que ya empezó y "
                          "quedarían cerradas con remesas en pausa: "
                          + ", ".join(cerradas))


def test_LA_LLAVE_NO_APARECE_EN_RUTAS_QUE_NADIE_DECIDIO(rutas):
    """Si otra ruta la lleva, que sea porque alguien la agregó a PUERTAS."""
    de_mas = sorted(f"{m} {c}" for (m, c), lleva in rutas.items()
                    if lleva and (m, c) not in PUERTAS)
    assert not de_mas, "llevan la llave sin estar en PUERTAS: " + ", ".join(de_mas)


def test_LA_PUERTA_CONTESTA_503_DE_VERDAD(base, monkeypatch):
    """No sólo que la dependencia esté colgada: que corra, y que frene."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from models.user import User
    from routes import dependencies, transactions

    async def nada(*a, **k):
        return None
    import routes.security_2fa as seg
    monkeypatch.setattr(seg, "frenar", nada)
    monkeypatch.setattr(seg, "frenar_por_cuenta", nada)

    app = FastAPI()
    app.include_router(transactions.router, prefix="/api")
    app.dependency_overrides[dependencies.get_current_user] = lambda: User(
        user_id="u_cliente", name="Cliente", email="cliente@ejemplo.test",
        role="user", verification_status="verified")
    poner(base, ra.CLAVE, ra.CERRADAS)
    r = TestClient(app).post("/api/withdraw", json={})
    assert r.status_code == 503, r.text
    assert r.json()["detail"] == ra.EN_PAUSA

    # Abierta, la llave no frena: lo que contesta ya es otra cosa (acá, el
    # pedido vacío que no pasa la validación).
    poner(base, ra.CLAVE, ra.ABIERTAS)
    assert TestClient(app).post("/api/withdraw", json={}).status_code != 503


# ══════════════════════════════════════════════════════════════════════════
# 3. La llave madre
# ══════════════════════════════════════════════════════════════════════════

def test_CERRADA_CIERRA_LA_CARGA_DE_SALDO_AUNQUE_SU_LLAVE_DIGA_ABIERTA(base):
    poner(base, recarga_abierta.CLAVE, recarga_abierta.ABIERTA)
    assert corre(recarga_abierta.esta_abierta(base)) is True
    poner(base, ra.CLAVE, ra.CERRADAS)
    assert corre(recarga_abierta.esta_abierta(base)) is False
    with pytest.raises(HTTPException) as e:
        corre(recarga_abierta.exigir_abierta(base))
    assert e.value.status_code == 503


def test_AL_ABRIR_VUELVE_A_VALER_LA_LLAVE_DE_LA_RECARGA(base):
    """La llave madre no toca las otras: abrir remesas no abre una recarga
    que estaba cerrada por su cuenta."""
    poner(base, "pago_al_final", 1)            # el seguro exige esto para cerrar la recarga
    poner(base, recarga_abierta.CLAVE, recarga_abierta.CERRADA)
    poner(base, ra.CLAVE, ra.CERRADAS)
    poner(base, ra.CLAVE, ra.ABIERTAS)
    assert corre(recarga_abierta.esta_abierta(base)) is False


def test_CERRADA_DEJA_LA_CRIPTO_EN_SOLO_SALIDA(base):
    """No entra plata nueva; la que está, sale. Cerrar la salida le atraparía
    el saldo a quien lo tenga."""
    poner(base, cripto_abierta.CLAVE, cripto_abierta.ABIERTA)
    poner(base, ra.CLAVE, ra.CERRADAS)
    assert corre(cripto_abierta.acepta_depositos(base)) is False
    assert corre(cripto_abierta.acepta_envios(base)) is True
    assert corre(cripto_abierta.se_le_muestra(base)) is True


def test_UNA_CRIPTO_CERRADA_SIGUE_CERRADA(base):
    poner(base, cripto_abierta.CLAVE, cripto_abierta.CERRADA)
    poner(base, ra.CLAVE, ra.CERRADAS)
    assert corre(cripto_abierta.acepta_envios(base)) is False


# ══════════════════════════════════════════════════════════════════════════
# 4. Lo que ve la pantalla
# ══════════════════════════════════════════════════════════════════════════

def test_LIMITS_PUBLICA_REMESAS_Y_LO_DEMAS_YA_RECORTADO(base):
    from models.reglas_publicas import LosLimites
    from services import limits
    poner(base, cripto_abierta.CLAVE, cripto_abierta.ABIERTA)

    abierta = corre(limits.limits_payload(base))
    assert abierta["remesas"] is True and abierta["recarga"] is True
    assert abierta["cripto"]["deposito"] is True

    poner(base, ra.CLAVE, ra.CERRADAS)
    cerrada = corre(limits.limits_payload(base))
    assert cerrada["remesas"] is False
    assert cerrada["recarga"] is False, "la pantalla ofrecería recargar y el servidor diría 503"
    assert cerrada["cripto"]["deposito"] is False
    assert cerrada["cripto"]["envio"] is True, "quien tiene saldo cripto no podría sacarlo"
    # El contrato de salida de /limits lo deja pasar: sin el campo en
    # LosLimites, la respuesta lo tiraría en silencio.
    assert LosLimites(**cerrada).model_dump()["remesas"] is False


# ══════════════════════════════════════════════════════════════════════════
# 5. El bono y los mensajes
# ══════════════════════════════════════════════════════════════════════════

def test_CON_REMESAS_EN_PAUSA_NO_NACE_EL_BONO_DE_BIENVENIDA(base):
    """El bono sólo se gasta en envíos a Venezuela: con remesas en pausa sería
    plata que la cuenta no puede usar y que la empresa igual debe."""
    from services import bonos
    corre(base.users.insert_one({"user_id": "u_dueno", "referral_code": "ABC123"}))
    corre(base.users.insert_one({"user_id": "u_nuevo"}))
    poner(base, ra.CLAVE, ra.CERRADAS)
    informe = corre(bonos.al_registrarse(base, "u_nuevo", "ABC123"))
    assert informe == {"acreditado": False, "motivo": "remesas_en_pausa"}
    assert "bono" not in corre(base.users.find_one({"user_id": "u_nuevo"}))


def test_EL_MENSAJE_DE_LA_VIA_QUE_FUNCIONA_NO_MANDA_A_UNA_PUERTA_CERRADA(base, caplog):
    """Con remesas en pausa, recargar y pagar al final están cerradas. Y no
    es la falla del seguro de la configuración: no deja ERROR."""
    from services import la_via_que_funciona
    poner(base, "pago_al_final", 1)
    poner(base, ra.CLAVE, ra.CERRADAS)
    with caplog.at_level(logging.ERROR):
        frase = corre(la_via_que_funciona.para_poner_plata(base))
    assert frase == ra.EN_PAUSA
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
