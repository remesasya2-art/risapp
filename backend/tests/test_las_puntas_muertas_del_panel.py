"""
tests/test_las_puntas_muertas_del_panel.py — Ninguna pantalla llama a una
ruta que no existe.

QUE PASABA

    La revisión general del 21 de septiembre de 2026 cruzó cada llamada del
    frontend contra la tabla de rutas viva del servidor, y encontró tres
    pantallas pidiendo rutas que no existían:

      · Libro mayor → «Órdenes BTC» pedía `GET /admin/ledger/btc`, que nunca
        existió. Dos avisos «Not Found» y una tabla vacía.
      · Panel → «Limpieza de Retiros» borraba contra
        `DELETE /admin/withdrawals/delete/{id}`, que no existe. Y además
        nadie abría ese modal: no había ningún botón que lo mostrara.
      · Recargar con VES → «mis recargas» pedía `GET /recharge/ves/status`,
        que existió hasta junio y se fue en una limpieza. La lista quedaba
        vacía en silencio, con un 404 por visita.

    Las dos primeras se sacaron; la tercera volvió, por lista de lo
    permitido. Y este archivo deja el guardián que faltaba: la próxima ruta
    que alguien borre con una pantalla todavía pidiéndola hace ruido acá.

COMO SE PRUEBA EL GUARDIAN, Y POR QUE ASI

    Contra la tabla de rutas VIVA (`server.app.routes`), no contra el texto
    de los archivos de rutas: los prefijos de cada router (`/api`, `/admin`,
    `/envios`…) se arman al incluirlos, y leyendo los decoradores a mano la
    primera versión de esta comprobación dio 170 falsos positivos.
"""
import asyncio
import os
import pathlib
import re
import sys
import types
from datetime import datetime, timezone

import pytest

_BACKEND = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))
_SRC = _BACKEND.parent / "frontend" / "src"

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor", reason="hace falta mongomock_motor para estos tests")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402
from services.money import to_decimal128                      # noqa: E402

CLIENTE_ID = "u_ana"


def _ya(corrutina):
    return asyncio.run(corrutina)


def _sin_webpush():
    """`pywebpush` no compila en este entorno y las rutas lo arrastran."""
    if "pywebpush" not in sys.modules:                        # pragma: no cover
        stub = types.ModuleType("pywebpush")
        stub.WebPushException = type("WebPushException", (Exception,), {})
        stub.webpush = lambda *a, **k: None
        sys.modules["pywebpush"] = stub


# ══════════════════════════════════════════════════════════════════════════
# 1. Las dos puntas que se sacaron no vuelven
# ══════════════════════════════════════════════════════════════════════════

def _todo_el_frontend():
    return "\n".join(
        f.read_text(encoding="utf-8")
        for f in list(_SRC.rglob("*.jsx")) + list(_SRC.rglob("*.js")))


def test_NINGUNA_PANTALLA_PIDE_EL_LIBRO_BTC():
    """La ruta nunca existió. Si alguien la vuelve a pedir, que primero la
    escriba."""
    assert "/admin/ledger/btc" not in _todo_el_frontend()
    assert not (_SRC / "components" / "admin" / "LibroBtc.jsx").exists(), (
        "volvió LibroBtc.jsx: es una pantalla que pide una ruta que no existe")


def test_el_libro_mayor_no_ofrece_una_vista_que_no_puede_cargar():
    libro = (_SRC / "components" / "admin" / "LibroMayor.jsx").read_text(encoding="utf-8")
    assert "'btc'" not in libro
    assert "Órdenes BTC" not in libro


def test_NADIE_BORRA_RETIROS_DESDE_EL_PANEL():
    """Un retiro es un movimiento de dinero: el libro mayor y la auditoría
    existen para que eso no desaparezca. Borrarlo a mano no tiene que ser
    fácil, y la ruta que lo haría no existe."""
    frontend = _todo_el_frontend()
    assert "withdrawals/delete" not in frontend
    assert "Limpieza de Retiros" not in frontend
    assert "deleteSingleWithdrawal" not in frontend


# ══════════════════════════════════════════════════════════════════════════
# 2. «Mis recargas» vuelve, por lista de lo permitido
# ══════════════════════════════════════════════════════════════════════════

def _app(nombre):
    _sin_webpush()
    base = mongomock_motor.AsyncMongoMockClient()[nombre]
    usar_base(base)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.transactions import router
    from routes import dependencies as deps

    ana = User(user_id=CLIENTE_ID, name="Ana", email="ana@ejemplo.test", role="user")
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: ana
    return TestClient(app), base


def _recarga(**extra):
    """Una recarga en bolívares como la deja el panel después de procesarla.

    La plata con `to_decimal128`, igual que la escribe la aplicación: un test
    que escriba `4400.0` a secas pasa con el producto roto."""
    return {
        "transaction_id": "rech_1", "display_id": "000123", "user_id": CLIENTE_ID,
        "type": "recharge_ves", "status": "rejected",
        "amount_ves": to_decimal128("4400.00"), "amount_ris": to_decimal128("40.00"),
        "amount_input": to_decimal128("4400.00"), "amount_output": to_decimal128("40.00"),
        "created_at": datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
        "processed_at": datetime(2026, 9, 20, 13, 0, tzinfo=timezone.utc),
        "rejection_reason": "El comprobante no coincide con el monto.",
        "destination_bank": "0102", "payment_method": "transferencia",
        # Lo que escribe el panel y NO tiene por qué viajar al cliente.
        "processed_by": "adm_9", "proof_image": "/uploads/x.jpg",
        **extra,
    }


def test_MIS_RECARGAS_VUELVE_Y_TRAE_LO_QUE_LA_PANTALLA_MUESTRA():
    cliente, base = _app("ris_mis_recargas")
    _ya(base.transactions.insert_one(_recarga()))
    r = cliente.get("/api/recharge/ves/status")
    assert r.status_code == 200, r.text
    filas = r.json()
    assert len(filas) == 1
    fila = filas[0]
    # Lo que `RechargeVES.jsx` lee, campo por campo.
    for campo in ("transaction_id", "amount_ves", "amount_ris", "status",
                  "created_at", "rejection_reason"):
        assert campo in fila, f"la pantalla muestra «{campo}» y no llega"
    assert fila["amount_ves"] == 4400.0
    assert fila["rejection_reason"] == "El comprobante no coincide con el monto."


def test_LO_QUE_ESCRIBE_EL_PANEL_NO_SALE():
    """`processed_by` es el identificador del administrador que la procesó.
    La versión vieja de la ruta devolvía el documento entero."""
    cliente, base = _app("ris_mis_recargas_panel")
    _ya(base.transactions.insert_one(_recarga()))
    fila = cliente.get("/api/recharge/ves/status").json()[0]
    assert "processed_by" not in fila
    assert "proof_image" not in fila


def test_solo_las_recargas_del_propio_usuario():
    cliente, base = _app("ris_mis_recargas_ajenas")
    _ya(base.transactions.insert_one(_recarga()))
    _ya(base.transactions.insert_one(_recarga(transaction_id="rech_2", user_id="u_otro")))
    filas = cliente.get("/api/recharge/ves/status").json()
    assert [f["transaction_id"] for f in filas] == ["rech_1"]


def test_solo_recargas_en_bolivares_y_no_todo_el_historial():
    cliente, base = _app("ris_mis_recargas_tipo")
    _ya(base.transactions.insert_one(_recarga()))
    _ya(base.transactions.insert_one(_recarga(transaction_id="tx_9", type="withdrawal")))
    filas = cliente.get("/api/recharge/ves/status").json()
    assert [f["transaction_id"] for f in filas] == ["rech_1"]


def test_la_ruta_declara_su_contrato():
    from routes import transactions
    fuente = pathlib.Path(transactions.__file__).read_text(encoding="utf-8")
    assert '@router.get("/recharge/ves/status", response_model=list[UnaRecargaEnBolivares])' in fuente


# ══════════════════════════════════════════════════════════════════════════
# 3. EL GUARDIAN: cada llamada fija del frontend tiene una ruta viva
# ══════════════════════════════════════════════════════════════════════════

_LLAMADA = re.compile(r"api\.(get|post|put|patch|delete)\(\s*[`'\"]([^`'\"]+)")


def _llamadas_fijas():
    """(método, ruta, archivo) de cada `api.<verbo>('/…')` con ruta literal.

    Las partes variables (`${id}`) se vuelven un comodín. Las llamadas que
    arman la ruta entera con variables no se pueden comprobar así y no se
    miran."""
    salida = set()
    for f in list(_SRC.rglob("*.jsx")) + list(_SRC.rglob("*.js")):
        s = f.read_text(encoding="utf-8", errors="ignore")
        for m in _LLAMADA.finditer(s):
            ruta = m.group(2).split("?")[0]
            ruta = re.sub(r"\$\{[^}]+\}", "{X}", ruta)
            if not ruta.startswith("/"):
                continue
            salida.add((m.group(1).upper(), "/api" + ruta, f.relative_to(_SRC).as_posix()))
    return salida


@pytest.fixture(scope="module")
def rutas_vivas():
    _sin_webpush()
    import server
    return [(m, r.path) for r in server.app.routes
            for m in (getattr(r, "methods", None) or []) if m not in ("HEAD", "OPTIONS")]


def _existe(metodo, ruta, vivas):
    """Una ruta de la pantalla contra la tabla del servidor.

    `{X}` casa con cualquier tramo. Una ruta que termina en `/` es un prefijo
    al que la pantalla le pega el identificador con `+`: casa con cualquier
    ruta viva que empiece así. Y `{X}` pegado sin barra es una cadena de
    consulta que la pantalla concatena: se ignora."""
    ruta = re.sub(r"(?<!/)\{X\}$", "", ruta)
    for m, viva in vivas:
        if m != metodo:
            continue
        patron = "^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(viva)) + "$"
        objetivo = ruta.replace("{X}", "x")
        if re.match(patron, objetivo):
            return True
        if ruta.endswith("/") and viva.startswith(ruta):
            return True
    return False


def test_EL_GUARDIAN_ENCUENTRA_LAS_LLAMADAS():
    """Si baja de golpe, el recorrido dejó de reconocer cómo llama el
    frontend, y el test de abajo pasa vacío — que es la peor forma de pasar."""
    assert len(_llamadas_fijas()) >= 250, len(_llamadas_fijas())


def test_NINGUNA_PANTALLA_LLAMA_A_UNA_RUTA_QUE_NO_EXISTE(rutas_vivas):
    huerfanas = sorted(
        f"{m:6} {r:50} {archivo}"
        for m, r, archivo in _llamadas_fijas() if not _existe(m, r, rutas_vivas))
    assert not huerfanas, (
        "estas pantallas piden rutas que el servidor no tiene — van a dar 404 "
        "en la cara del usuario:\n  " + "\n  ".join(huerfanas))


def test_EL_GUARDIAN_DISTINGUE_UNA_RUTA_VIVA_DE_UNA_INVENTADA(rutas_vivas):
    """Sin esto, un `_existe` que devolviera siempre True dejaría el guardián
    en verde sin mirar nada. Se le da una ruta real y una inventada."""
    assert _existe("GET", "/api/limits", rutas_vivas) is True
    assert _existe("GET", "/api/envios/{X}/como-pagar", rutas_vivas) is True
    assert _existe("GET", "/api/btc/status/", rutas_vivas) is True      # prefijo + id
    assert _existe("GET", "/api/admin/rate-history{X}", rutas_vivas) is True  # + consulta
    assert _existe("GET", "/api/esta-ruta-no-existe", rutas_vivas) is False
    assert _existe("DELETE", "/api/admin/withdrawals/delete/{X}", rutas_vivas) is False
    assert _existe("GET", "/api/admin/ledger/btc", rutas_vivas) is False


def test_LA_PROYECCION_TAMPOCO_LEE_LO_DEL_PANEL():
    """Dos capas, cada una con su test: `response_model` recorta lo que sale
    por HTTP (el test de arriba), y la proyección evita LEER de la base lo que
    no hace falta. Con sólo el de arriba, una proyección que dejara pasar
    `processed_by` seguía en verde porque el contrato lo tapaba — pasó al
    romperla a propósito. Acá se llama a la función a secas, sin el contrato
    en el medio."""
    from routes.transactions import mis_recargas_en_bolivares
    base = mongomock_motor.AsyncMongoMockClient()["ris_mis_recargas_proyeccion"]
    usar_base(base)
    _ya(base.transactions.insert_one(_recarga()))
    ana = User(user_id=CLIENTE_ID, name="Ana", email="ana@ejemplo.test", role="user")
    fila = _ya(mis_recargas_en_bolivares(current_user=ana))[0]
    assert "processed_by" not in fila
    assert "proof_image" not in fila
