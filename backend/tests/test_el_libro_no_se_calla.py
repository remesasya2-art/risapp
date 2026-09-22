"""
tests/test_el_libro_no_se_calla.py — el asiento del libro que no se escribe, y
el aviso de un cobro que llega a una dirección que no existe, dejan fila en la
pestaña Errores y avisan a los super administradores. No se quedan en el log.

Ver services/gritos.py.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip("mongomock_motor")

from conftest import usar_base                                # noqa: E402
from services import errores, gritos, ledger, ledger_crypto   # noqa: E402
from services.money import to_decimal128                      # noqa: E402
from services.notifications import TRABAJO                    # noqa: E402
from services.sin_ruta import DONDE_AVISA_MERCADOPAGO         # noqa: E402


def ya(c):
    return asyncio.run(c)


@pytest.fixture(autouse=True)
def base():
    m = mongomock_motor.AsyncMongoMockClient()["libro_no_se_calla"]
    _ROTAS.clear()
    usar_base(_BaseConRoturas(m, _ROTAS))
    gritos.reiniciar_para_tests()
    ya(m.users.insert_one({"user_id": "sa-1", "role": "super_admin", "is_active": True,
                           "name": "Súper", "email": "sa@example.com"}))
    # Un agente activo: la campana de esto es SOLO para super administradores.
    ya(m.users.insert_one({"user_id": "ag-1", "role": "agent", "is_active": True,
                           "name": "Agente", "email": "ag@example.com", "permissions": ["kyc"]}))
    ya(m.users.insert_one({"user_id": "cli-1", "role": "user", "is_active": True,
                           "name": "Cliente", "email": "c@example.com",
                           "balance_ris": to_decimal128("100.00")}))
    return m


class _ColeccionRota:
    """Una colección cuya escritura falla: lo que se ve con un índice roto o
    un campo que Mongo rechaza."""
    def __init__(self, error):
        self._error = error

    async def insert_one(self, *a, **k):
        raise self._error


class _BaseConRoturas:
    """La base de siempre, con algunas colecciones rotas. `mongomock_motor`
    devuelve un envoltorio nuevo en cada acceso, así que parchar la colección
    no sirve: hay que interceptar el acceso."""
    def __init__(self, base, rotas):
        self._base, self._rotas = base, rotas

    def __getitem__(self, nombre):
        return self._rotas.get(nombre) or self._base[nombre]

    def __getattr__(self, nombre):
        return self[nombre]


_ROTAS = {}


def _rompe(monkeypatch, coleccion: str, error):
    _ROTAS[coleccion] = _ColeccionRota(error)


def filas(base, tipo):
    return ya(base[errores.COLECCION].find({"tipo": tipo}).to_list(100))


def campanas(base):
    return ya(base.notifications.find({}).to_list(100))


def asentar_ris(**extra):
    datos = dict(user_id="cli-1", movement_type="recarga", amount="12.34", direction="credit",
                 account="balance_ris")
    datos.update(extra)
    return ya(ledger.record_ris_entry(**datos))


# ══════════════════════════════════════════════════════════════════════════
# 1. El asiento que no se escribe
# ══════════════════════════════════════════════════════════════════════════

def test_EL_ASIENTO_QUE_NO_SE_ESCRIBE_DEJA_FILA_EN_ERRORES_Y_AVISA(base, monkeypatch):
    _rompe(monkeypatch, ledger.LEDGER_COLLECTION, RuntimeError("índice roto"))
    assert asentar_ris() is None, "el contrato del libro sigue: no tumba el flujo"

    (fila,) = filas(base, gritos.LIBRO_SIN_LINEA)
    assert fila["user_id"] == "cli-1"
    assert fila["status"] == 500 and fila["ruta"] == "libro/RIS"
    # Lo necesario para reponer la línea a mano: cuenta, movimiento y monto.
    for pedazo in ("balance_ris", "recarga", "12.34", "índice roto"):
        assert pedazo in fila["mensaje"], fila["mensaje"]

    (aviso,) = campanas(base)
    assert aviso["user_id"] == "sa-1" and aviso["ambito"] == TRABAJO
    assert aviso["type"] == "error"
    assert "LIBRO SIN LINEA" in aviso["title"] and "cli-1" in aviso["message"]


def test_el_libro_cripto_tambien_grita(base, monkeypatch):
    _rompe(monkeypatch, ledger_crypto.LEDGER_COLLECTION, RuntimeError("cripto roto"))
    r = ya(ledger_crypto.record_crypto_entry(user_id="cli-1", currency="usdt", movement_type="deposito",
                                             amount="5", direction="credit"))
    assert r is None
    (fila,) = filas(base, gritos.LIBRO_SIN_LINEA)
    assert fila["ruta"] == "libro/cripto/usdt" and "balance_usdt" in fila["mensaje"]
    assert len(campanas(base)) == 1


def test_LA_FILA_VA_SIEMPRE_Y_LA_CAMPANA_UNA_VEZ_CADA_DIEZ_MINUTOS(base, monkeypatch):
    """Cien filas dicen cuántas líneas hay que reponer; cien campanas en diez
    minutos son un aviso que alguien silencia."""
    _rompe(monkeypatch, ledger.LEDGER_COLLECTION, RuntimeError("se rompió"))
    reloj = {"t": 1000.0}
    monkeypatch.setattr(gritos.time, "monotonic", lambda: reloj["t"])

    asentar_ris()
    reloj["t"] += 60
    asentar_ris()
    assert len(filas(base, gritos.LIBRO_SIN_LINEA)) == 2
    assert len(campanas(base)) == 1, "la segunda campana en un minuto sobra"

    reloj["t"] += gritos.CADA_CUANTO_SE_REPITE
    asentar_ris()
    assert len(filas(base, gritos.LIBRO_SIN_LINEA)) == 3
    assert len(campanas(base)) == 2, "pasados los diez minutos, vuelve a sonar"


def test_el_freno_es_por_tipo_de_grito(base, monkeypatch):
    """Que el libro haya sonado no tapa el grito de un pago perdido."""
    _rompe(monkeypatch, ledger.LEDGER_COLLECTION, RuntimeError("x"))
    asentar_ris()
    ya(gritos.pago_a_direccion_equivocada(_BaseConRoturas(base, _ROTAS), metodo="POST", camino="/", motivo="mercadopago", pago="9"))
    assert len(campanas(base)) == 2


def test_NUNCA_LEVANTA_AUNQUE_ERRORES_TAMBIEN_FALLE(base, monkeypatch):
    """Un error al contar un error es el peor de los dos."""
    _rompe(monkeypatch, ledger.LEDGER_COLLECTION, RuntimeError("libro"))
    _rompe(monkeypatch, errores.COLECCION, RuntimeError("errores también"))
    _rompe(monkeypatch, "notifications", RuntimeError("campana también"))
    assert asentar_ris() is None


def test_el_secreto_de_la_conexion_no_queda_en_la_fila(base, monkeypatch):
    """Pasa por `errores.anotar`, que tacha las formas conocidas. Escribir la
    fila por otro camino se saltaría eso."""
    _rompe(monkeypatch, ledger.LEDGER_COLLECTION,
           RuntimeError("timeout mongodb://ris:CLAVE-SECRETA@cluster.example/ris"))
    asentar_ris()
    (fila,) = filas(base, gritos.LIBRO_SIN_LINEA)
    assert "CLAVE-SECRETA" not in fila["mensaje"]
    assert "***" in fila["mensaje"]


def test_el_asiento_bueno_no_grita(base):
    assert asentar_ris() is not None
    assert filas(base, gritos.LIBRO_SIN_LINEA) == [] and campanas(base) == []


# ══════════════════════════════════════════════════════════════════════════
# 2. El aviso de pago a la dirección equivocada, por la aplicación entera
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def cliente():
    try:
        from fastapi.testclient import TestClient
        from server import app
    except Exception as e:                                        # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    return TestClient(app)


def test_EL_AVISO_DE_PAGO_A_LA_RAIZ_DEJA_FILA_Y_AVISA(base, cliente):
    r = cliente.post("/?data.id=177862590765&type=payment")
    assert r.status_code == 404

    (fila,) = filas(base, gritos.PAGO_A_DIRECCION_EQUIVOCADA)
    assert fila["status"] == 404 and fila["metodo"] == "POST" and fila["ruta"] == "/"
    assert "177862590765" in fila["mensaje"], "sin el id no se puede ir a buscar qué pago fue"
    assert DONDE_AVISA_MERCADOPAGO in fila["mensaje"], "tiene que decir cuál es la dirección buena"

    (aviso,) = campanas(base)
    assert aviso["user_id"] == "sa-1" and "DIRECCION EQUIVOCADA" in aviso["title"]
    assert DONDE_AVISA_MERCADOPAGO in aviso["message"]


def test_un_post_cualquiera_a_una_ruta_que_no_existe_no_grita(base, cliente):
    """Por acá pasan los escáneres de internet: un grito por cada uno es un
    registro que nadie lee."""
    assert cliente.post("/api/una-que-no-existe", json={"a": 1}).status_code == 404
    assert cliente.post("/wp-login.php", data={"log": "x"}).status_code == 404
    assert filas(base, gritos.PAGO_A_DIRECCION_EQUIVOCADA) == [] and campanas(base) == []
