"""
tests/test_contratos_del_panel.py — Las rutas del panel sobre los clientes
salen por un contrato, y ningún contrato se come un campo que su ruta
devuelve.

Primera tanda del panel: las acciones sobre la cuenta, la verificación de
identidad y los retiros. La lectura de las claves desde el código es la de
las acciones del cliente (`test_contratos_de_acceso.py`), importada: una sola.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from test_contratos_de_acceso import _claves                    # noqa: E402

# (archivo, cómo se llama el router ahí, método, camino, contrato)
ACCIONES = [
    ("routes/admin.py", "router", "POST", "/change-role", "RolCambiado"),
    ("routes/admin.py", "router", "POST", "/users/{user_id}/set-agent", "AgenteAsignado"),
    ("routes/admin.py", "router", "POST", "/reset-password", "ClaveReiniciada"),
    ("routes/admin.py", "router", "POST", "/withdrawals/process", "AccionDelPanel"),
    ("routes/admin.py", "router", "POST", "/verifications/decide", "AccionDelPanel"),
    ("routes/admin.py", "router", "POST", "/verifications/process", "AccionDelPanel"),
    ("routes/admin.py", "router", "POST", "/users/{user_id}/suspend", "AccionDelPanel"),
    ("routes/admin.py", "router", "DELETE", "/users/{user_id}", "AccionDelPanel"),
    ("routes/admin.py", "router", "POST", "/ban", "CuentaVetada"),
    ("routes/kyc_admin.py", "router", "POST", "/{verification_id}/approve", "AccionDelPanel"),
    ("routes/kyc_admin.py", "router", "POST", "/{verification_id}/risk", "RiesgoMarcado"),
    ("routes/kyc_admin.py", "router", "POST", "/{verification_id}/re-review", "AccionDelPanel"),
    ("routes/kyc_admin.py", "router", "POST", "/{verification_id}/reject", "VerificacionRechazada"),
    ("routes/kyc_admin.py", "router", "PATCH", "/{verification_id}/note", "NotaGuardada"),
    ("admin_routes.py", "admin_router", "PUT", "/users/{user_id}/balance", "SaldoAjustado"),
    ("routes/admin.py", "router", "POST", "/ordenes/tomar", "OrdenTomada"),
    ("routes/admin.py", "router", "POST", "/ordenes/liberar", "OrdenLiberada"),
    ("routes/admin.py", "router", "POST", "/ordenes/{transaction_id}/aprobar-con-diferencia", "EstadoCambiado"),
    ("routes/admin.py", "router", "POST", "/ordenes/{transaction_id}/rechazar-y-reembolsar-saldo",
     "OrdenRechazadaYReembolsada"),
    ("routes/admin.py", "router", "POST", "/recharges/ves/process/{transaction_id}", "RecargaProcesada"),
    ("routes/admin.py", "router", "POST", "/envios-reais/{transaction_id}/verificar", "EstadoCambiado"),
    ("admin_routes.py", "admin_router", "POST", "/recharges/approve", "EstadoCambiado"),
    ("routes/credits_admin.py", "router", "POST", "/manual-credit", "CreditoManual"),
]
_IDS = [f"{m} {a.split('/')[-1][:-3]}{c}" for a, _, m, c, _ in ACCIONES]


def _ruta(archivo, nombre, metodo, camino):
    router = getattr(importlib.import_module(archivo[:-3].replace("/", ".")), nombre)
    (r,) = [r for r in router.routes
            if r.path == (router.prefix or "") + camino and metodo in r.methods]
    return r


# ══════════════════════════════════════════════════════════════════════════
# 1. Las acciones
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("archivo,nombre,metodo,camino,modelo", ACCIONES, ids=_IDS)
def test_CADA_ACCION_DEL_PANEL_TIENE_SU_CONTRATO(archivo, nombre, metodo, camino, modelo):
    ruta = _ruta(archivo, nombre, metodo, camino)
    assert ruta.response_model is not None and ruta.response_model.__name__ == modelo
    assert ruta.response_model_exclude_unset is True, "lo que la ruta no pone no tiene que salir como null"


@pytest.mark.parametrize("archivo,nombre,metodo,camino,modelo", ACCIONES, ids=_IDS)
def test_EL_CONTRATO_NO_SE_COME_NINGUN_CAMPO_QUE_LA_ACCION_DEVUELVE(archivo, nombre, metodo, camino, modelo):
    ruta = _ruta(archivo, nombre, metodo, camino)
    claves = _claves(archivo, metodo, camino, None)
    assert claves, f"no encontré qué devuelve {camino}: sin claves este test no prueba nada"
    faltan = claves - set(ruta.response_model.model_fields)
    assert not faltan, f"{camino} devuelve {sorted(faltan)} y su contrato no los tiene: el panel los perdería"


# Lo que estas acciones leen para decidir, y no tiene que salir en la respuesta.
LO_QUE_LEYERON = {
    "password_hash": "$2b$12$clave", "pin_hash": "$2b$12$pin", "two_factor_secret": "JBSWY3DPEHPK3PXP",
    "webauthn_credentials": [{"public_key": "CLAVE-PUBLICA"}], "selfie_image": "data:image/jpeg;base64,SELFIE",
    "cpf_number": "12345678909",
}


@pytest.mark.parametrize("archivo,nombre,metodo,camino,modelo", ACCIONES, ids=_IDS)
def test_LO_QUE_LA_ACCION_LEYO_NO_SALE_AUNQUE_LA_RUTA_LO_DEVUELVA(archivo, nombre, metodo, camino, modelo):
    from fastapi.encoders import jsonable_encoder
    contrato = _ruta(archivo, nombre, metodo, camino).response_model
    hoy = {k: "x" for k in _claves(archivo, metodo, camino, None)}
    sale = jsonable_encoder(contrato.model_validate({**LO_QUE_LEYERON, **hoy}).model_dump(exclude_unset=True))
    assert sale == hoy, f"{camino} devolvió {sorted(set(sale) - set(hoy))} de más, o perdió algo de lo suyo"


# ══════════════════════════════════════════════════════════════════════════
# 2. Los catálogos del KYC
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("camino,modelo", [("/document-types", "TipoDeDocumento"),
                                           ("/rejection-reasons", "MotivoDeRechazo")])
def test_LOS_CATALOGOS_DEL_KYC_PASAN_ENTEROS_POR_SU_CONTRATO(camino, modelo):
    """Son listas escritas en el código: se pasan las de verdad por el
    contrato y tienen que salir iguales. Un campo nuevo en el catálogo que el
    contrato no tenga se ve acá."""
    from fastapi.encoders import jsonable_encoder
    from routes import kyc_admin
    ruta = _ruta("routes/kyc_admin.py", "router", "GET", camino)
    assert ruta.response_model.__args__[0].__name__ == modelo
    real = (kyc_admin.DOCUMENT_TYPES if camino == "/document-types"
            else [{"code": c, "label": t} for c, t in kyc_admin.REJECTION_REASONS.items()])
    item = ruta.response_model.__args__[0]
    assert [jsonable_encoder(item.model_validate(x).model_dump(exclude_unset=True)) for x in real] == real


# ══════════════════════════════════════════════════════════════════════════
# 3. Lo que el panel lee de un cliente
# ══════════════════════════════════════════════════════════════════════════

# Lo que las pantallas del panel LEEN de cada respuesta, buscado en
# frontend/src (AdminPanel.jsx). Si un contrato no lo tiene, la pantalla
# queda con un hueco y nadie se entera: es la lista que el contrato no puede
# perder.
LO_QUE_LEE_EL_PANEL = {
    "/users": {
        "users": {"user_id", "name", "email", "estado", "balance_ris", "verification_status", "role"},
        "resumen": {"total", "activa", "vetada", "suspendida", "borrada"},
    },
    "/users/{user_id}/complete": {
        "profile": {"cpf_number", "name", "phone_number", "verification_status", "email", "role", "created_at",
                    "last_login", "email_verified", "gestor_code", "referral_code", "balance_ris",
                    "balance_ris_terceros", "status", "profile_picture", "id_document_image", "cpf_image",
                    "selfie_image"},
        "kyc": {"cpf_number", "phone_number", "document_number", "status"},
        "stats": {"total_recharged_ris", "total_withdrawn_ris", "total_ves_sent"},
        "recharges": {"transaction_id", "created_at", "status", "amount_ris", "amount_brl"},
        "withdrawals": {"transaction_id", "created_at", "status", "amount_ris", "amount_ves", "beneficiary"},
        "beneficiaries": {"full_name", "bank", "account_number"},
    },
}


def _campos(anotacion):
    """Los campos del modelo que hay adentro de `Optional[X]` o `List[X]`."""
    import typing
    for a in typing.get_args(anotacion) or (anotacion,):
        if hasattr(a, "model_fields"):
            return set(a.model_fields)
        if typing.get_args(a):
            return _campos(a)
    raise AssertionError(f"no encontré un modelo en {anotacion}")    # pragma: no cover


@pytest.mark.parametrize("camino", sorted(LO_QUE_LEE_EL_PANEL))
def test_EL_CONTRATO_TIENE_TODO_LO_QUE_EL_PANEL_LEE(camino):
    contrato = _ruta("routes/admin.py", "router", "GET", camino).response_model
    for parte, lee in LO_QUE_LEE_EL_PANEL[camino].items():
        faltan = lee - _campos(contrato.model_fields[parte].annotation)
        assert not faltan, f"{camino}: el panel lee {parte}.{sorted(faltan)} y el contrato no los deja pasar"


mongomock_motor = pytest.importorskip("mongomock_motor")

SECRETOS = {"two_factor_secret": "JBSWY3DPEHPK3PXP", "pin_hash": "$2b$12$pindelcliente",
            "webauthn_credentials": [{"public_key": "CLAVE-PUBLICA"}], "push_token": "ExponentPushToken[x]"}


@pytest.fixture
def panel():
    """El router del panel con un cliente de verdad adentro: saldos y montos
    en Decimal128, como los guarda la aplicación, y los secretos puestos."""
    import asyncio
    from datetime import datetime, timezone
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from conftest import usar_base, ensenarle_decimal128_a_mongomock
    from models.user import User
    from routes import admin as rutas_admin
    from routes import dependencies as deps
    from services.money import to_decimal128

    ensenarle_decimal128_a_mongomock()
    base = mongomock_motor.AsyncMongoMockClient()["contratos_del_panel"]
    usar_base(base)
    t0 = datetime(2026, 9, 1, tzinfo=timezone.utc)

    async def sembrar():
        await base.users.insert_one({
            "user_id": "u_ana", "name": "Ana Cliente", "email": "ana@ejemplo.com", "role": "user",
            "verification_status": "verified", "cpf_number": "12345678909", "created_at": t0,
            "balance_ris": to_decimal128("150.25"), "balance_ris_terceros": to_decimal128("0"),
            "password_hash": "$2b$12$clave", **SECRETOS})
        await base.verifications.insert_one({
            "verification_id": "v1", "user_id": "u_ana", "status": "approved", "cpf_number": "12345678909",
            "phone_number": "+5511999999999", "document_number": "RG123", "submitted_at": t0,
            "selfie_image": "data:image/jpeg;base64,SELFIE", "id_document_image": "data:image/jpeg;base64,DOC",
            "cpf_image": "data:image/jpeg;base64,CPF", "admin_note": "nota interna del equipo",
            "risk_level": "alto"})
        await base.transactions.insert_many([
            {"transaction_id": "tx_r", "display_id": "000001", "user_id": "u_ana", "type": "recharge",
             "status": "completed", "amount_ris": to_decimal128("100.00"), "amount_brl": to_decimal128("100.00"),
             "amount_input": to_decimal128("100.00"), "amount_output": to_decimal128("100.00"), "created_at": t0},
            {"transaction_id": "tx_w", "display_id": "000002", "user_id": "u_ana", "type": "withdrawal",
             "status": "completed", "amount_ris": to_decimal128("40.00"), "amount_ves": to_decimal128("4400.00"),
             "amount_input": to_decimal128("40.00"), "amount_output": to_decimal128("4400.00"), "created_at": t0,
             "beneficiary": {"full_name": "José Pérez", "bank": "Banesco", "account_number": "0134",
                             "user_id": "u_ana", "nota_interna": "revisar"}},
        ])
        await base.beneficiaries.insert_one({
            "beneficiary_id": "b1", "user_id": "u_ana", "full_name": "José Pérez", "bank": "Banesco",
            "account_number": "01340000000000000000", "payment_type": "transferencia",
            "nota_interna": "revisar", "creado_por_ip": "10.0.0.7"})
    asyncio.run(sembrar())

    app = FastAPI()
    app.include_router(rutas_admin.router, prefix="/api")
    jefe = User(user_id="u_jefe", name="Jefe", email="jefe@ejemplo.com", role="super_admin")
    for dep in (deps.get_current_user, deps.get_crm_user, deps.get_super_admin):
        app.dependency_overrides[dep] = lambda: jefe
    return TestClient(app, raise_server_exceptions=False)


def _sin_secretos(texto):
    for campo, valor in {**SECRETOS, "password_hash": "$2b$12$clave"}.items():
        assert campo not in texto, f"salió «{campo}»"
        assert str(valor) not in texto, f"salió el valor de «{campo}»"


def test_LA_LISTA_DE_USUARIOS_SALE_CON_LA_PLATA_EN_NUMERO_Y_SIN_SECRETOS(panel):
    r = panel.get("/api/admin/users")
    assert r.status_code == 200, r.text
    (ana,) = r.json()["users"]
    assert ana["balance_ris"] == 150.25 and ana["estado"] == "activa" and ana["name"] == "Ana Cliente"
    assert r.json()["resumen"]["total"] == 1
    _sin_secretos(r.text)


def test_EL_DETALLE_DE_UN_USUARIO_SALE_CON_SUS_MOVIMIENTOS(panel):
    r = panel.get("/api/admin/users/u_ana")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["balance_ris"] == 150.25
    assert {t["transaction_id"]: t["amount_output"] for t in r.json()["transactions"]} == {"tx_r": 100.0, "tx_w": 4400.0}
    _sin_secretos(r.text)


def test_LA_FICHA_COMPLETA_TRAE_LO_QUE_EL_PANEL_MUESTRA_Y_NADA_DE_LO_INTERNO(panel):
    r = panel.get("/api/admin/users/u_ana/complete")
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["profile"]["selfie_image"] == "data:image/jpeg;base64,SELFIE" and f["profile"]["balance_ris"] == 150.25
    assert f["kyc"]["cpf_number"] == "12345678909" and f["kyc"]["document_number"] == "RG123"
    assert f["stats"]["total_recharged_ris"] == 100.0 and f["stats"]["total_withdrawn_ris"] == 40.0
    assert f["withdrawals"][0]["beneficiary"]["full_name"] == "José Pérez"
    assert f["beneficiaries"][0]["account_number"] == "01340000000000000000"
    _sin_secretos(r.text)
    # Lo que el equipo anota y lo que es de la base, no: la ficha lo devolvía entero.
    for interno in ("nota interna del equipo", "risk_level", "nota_interna", "creado_por_ip", "10.0.0.7"):
        assert interno not in r.text, f"la ficha dejó salir «{interno}»"
    # Las fotos van UNA vez, en el perfil: la verificación ya no las repite.
    assert r.text.count("base64,SELFIE") == 1


def test_LOS_TOTALES_DE_LA_FICHA_SE_SUMAN_CON_DECIMAL128_DE_VERDAD():
    """Los tests de arriba corren con `Decimal128` sabiendo sumar, porque
    mongomock lo necesita (tests/conftest.py) y esa lección vale para todo el
    proceso. En producción no sabe: `sum()` sobre montos guardados así daba
    500. Esto se comprueba en un Python aparte, sin la lección."""
    import subprocess
    import textwrap
    codigo = textwrap.dedent("""
        import asyncio, os, sys
        os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
        os.environ.setdefault("DB_NAME", "ris_test")
        from bson.decimal128 import Decimal128
        try:
            0 + Decimal128("1")
            sys.exit("este Python ya sabe sumar Decimal128: la prueba no probaria nada")
        except TypeError:
            pass

        class Cursor:
            def __init__(self, filas): self.filas = filas
            def sort(self, *a, **k): return self
            async def to_list(self, n): return self.filas

        class Coleccion:
            def __init__(self, filas): self.filas = filas
            async def find_one(self, *a, **k): return dict(self.filas[0]) if self.filas else None
            def find(self, *a, **k): return Cursor([dict(f) for f in self.filas])

        class Base:
            users = Coleccion([{"user_id": "u", "name": "Ana"}])
            verifications = Coleccion([])
            beneficiaries = Coleccion([])
            transactions = Coleccion([
                {"transaction_id": "r", "type": "recharge", "status": "completed",
                 "amount_ris": Decimal128("100.00")},
                {"transaction_id": "w", "type": "withdrawal", "status": "completed",
                 "amount_ris": Decimal128("40.00"), "amount_ves": Decimal128("4400.00")},
            ])

        from routes import admin
        admin.db = Base()
        r = asyncio.run(admin.get_user_complete_history("u", admin=None))
        print(r["stats"]["total_recharged_ris"], r["stats"]["total_withdrawn_ris"], r["stats"]["total_ves_sent"])
    """)
    backend = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    salida = subprocess.run([sys.executable, "-c", codigo], cwd=backend, capture_output=True, text=True,
                            env={**os.environ, "PYTHONPATH": backend})
    assert salida.returncode == 0, salida.stderr[-2000:]
    assert salida.stdout.strip().splitlines()[-1] == "100.0 40.0 4400.0"


# ══════════════════════════════════════════════════════════════════════════
# 4. La cola de pagos
# ══════════════════════════════════════════════════════════════════════════

BENEFICIARIO_QUE_SE_PAGA = {"full_name": "José Pérez", "cedula": "V12345678", "bank": "Banesco",
                            "account_number": "01340000000000000001", "phone": "04141234567",
                            "payment_type": "transferencia"}


@pytest.fixture
def cola(panel):
    """Dos retiros: uno con el beneficiario limpio, otro con el documento
    entero copiado —como lo guardaba el envío por Bitcoin—."""
    import asyncio
    from datetime import datetime, timezone
    from services.money import to_decimal128
    from routes import admin as rutas_admin
    base = rutas_admin.db    # la misma base que sembró `panel`
    t0 = datetime(2026, 9, 20, tzinfo=timezone.utc)

    async def sembrar():
        await base.transactions.insert_many([
            {"transaction_id": "tx_p1", "display_id": "000101", "user_id": "u_ana", "type": "withdrawal",
             "status": "pending", "amount_input": to_decimal128("50.00"), "currency_input": "RIS",
             "amount_output": to_decimal128("5500.00"), "currency_output": "VES", "rate": to_decimal128("110.00"),
             "beneficiary_data": dict(BENEFICIARIO_QUE_SE_PAGA), "created_at": t0},
            {"transaction_id": "tx_p2", "display_id": "000102", "user_id": "u_ana", "type": "withdrawal",
             "status": "pending", "amount_input": to_decimal128("20.00"), "currency_input": "RIS",
             "amount_output": to_decimal128("2200.00"), "currency_output": "VES", "rate": to_decimal128("110.00"),
             "beneficiary_data": {**BENEFICIARIO_QUE_SE_PAGA, "user_id": "u_ana", "nota_interna": "revisar",
                                  "creado_por_ip": "10.0.0.7", "_etiqueta": "copia-entera"},
             "created_at": t0},
        ])
    asyncio.run(sembrar())
    return panel


def test_LA_COLA_DE_PAGOS_SALE_IGUAL_QUE_LA_ARMA_EL_SERVICIO(cola):
    """Nada de lo que la cola arma se pierde en el contrato: la respuesta de la
    ruta es la del servicio, salvo lo que sobra del beneficiario."""
    import asyncio
    from fastapi.encoders import jsonable_encoder
    from routes import admin as rutas_admin
    from services import retiros
    r = cola.get("/api/admin/withdrawals/all")
    assert r.status_code == 200, r.text
    pagina = asyncio.run(retiros.cola(rutas_admin.db))
    pagina["counters"] = asyncio.run(retiros.contadores(rutas_admin.db))
    esperado = jsonable_encoder(pagina)
    for fila in esperado["withdrawals"]:
        fila["beneficiary_data"] = {k: v for k, v in fila["beneficiary_data"].items() if k in BENEFICIARIO_QUE_SE_PAGA}
    recibido = r.json()
    # La antigüedad se calcula con el reloj en cada llamada: puede diferir en
    # un segundo entre las dos. Se compara aparte, sólo que esté.
    for a in (recibido, esperado):
        for fila in a["withdrawals"]:
            assert fila.pop("antiguedad")["nivel"]
        assert a["counters"].pop("mas_vieja")["nivel"]
    assert recibido == esperado


def test_EL_BENEFICIARIO_DE_LA_COLA_SALE_CON_LO_QUE_SE_PAGA_Y_NADA_MAS(cola):
    for camino in ("/api/admin/withdrawals/all", "/api/admin/withdrawals/pending"):
        r = cola.get(camino)
        assert r.status_code == 200, r.text
        filas = r.json()["withdrawals"] if camino.endswith("all") else r.json()
        assert {f["transaction_id"]: f["beneficiary_data"] for f in filas}["tx_p2"] == BENEFICIARIO_QUE_SE_PAGA
        for interno in ("nota_interna", "creado_por_ip", "10.0.0.7", "copia-entera"):
            assert interno not in r.text, f"{camino} dejó salir «{interno}»"
        assert {f["transaction_id"]: f["amount_output"] for f in filas} == {"tx_p1": 5500.0, "tx_p2": 2200.0}


# ══════════════════════════════════════════════════════════════════════════
# 5. Las verificaciones de identidad
# ══════════════════════════════════════════════════════════════════════════

# Lo que leen KycPanel.jsx y KycDetailModal.jsx. La ventana del detalle
# arranca con la fila de la lista y le encima el detalle: el riesgo y la lista
# negra vienen sólo de la lista.
# Largas a propósito: el KYC descarta como marcador vacío una imagen de menos
# de 30 caracteres (`_normalize_image`).
FOTO_SELFIE = "data:image/jpeg;base64," + "SELFIE" * 8
FOTO_DOC = "data:image/jpeg;base64," + "DOCUMENTO" * 5

LO_QUE_LEE_EL_KYC = {
    "lista": {"verification_id", "user_id", "status", "has_selfie", "full_name", "blacklist_match", "email",
              "cpf_number", "document_number", "phone_number", "submitted_at", "rejection_reason",
              "risk_level", "risk_suggested", "admin_note"},
    "detalle": {"verification_id", "status", "admin_note", "document_type", "document_type_label",
                "id_document_image", "id_document_image_back", "cpf_image", "selfie_image", "full_name", "email",
                "phone_number", "document_number", "cpf_number", "submitted_at", "rejection_reason",
                "processed_by_name", "processed_at"},
    "historia": {"audit_id", "created_at", "action", "admin_name"},
    "detalles": {"final_reason", "previous_value", "new_value"},
}


@pytest.fixture
def kyc():
    import asyncio
    from datetime import datetime, timezone
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from conftest import usar_base, ensenarle_decimal128_a_mongomock
    from models.user import User
    from routes import dependencies as deps
    from routes import kyc_admin
    from services.money import to_decimal128

    ensenarle_decimal128_a_mongomock()
    base = mongomock_motor.AsyncMongoMockClient()["contratos_del_kyc"]
    usar_base(base)
    t0 = datetime(2026, 9, 20, tzinfo=timezone.utc)

    async def sembrar():
        await base.users.insert_one({"user_id": "u_ana", "email": "ana@ejemplo.com", "full_name": "Ana Cliente",
                                     "balance_ris": to_decimal128("150.25"), "role": "user", **SECRETOS})
        await base.verifications.insert_one({
            "verification_id": "v1", "user_id": "u_ana", "status": "pending", "full_name": "Ana Cliente",
            "document_type": "rg", "document_number": "RG123", "cpf_number": "12345678909",
            "phone_number": "+5511999999999", "submitted_at": t0, "admin_note": "mirar la foto",
            "risk_level": "alto", "selfie_image": FOTO_SELFIE,
            "id_document_image": FOTO_DOC, "campo_interno": "no sale"})
        await base.kyc_audit_log.insert_one({
            "audit_id": "aud_1", "verification_id": "v1", "user_id": "u_ana", "action": "note_updated",
            "admin_id": "u_revisora", "admin_email": "revisora@ejemplo.com", "admin_name": "Revisora",
            "details": {"previous_value": "", "new_value": "mirar la foto", "previous_length": 0,
                        "new_length": 13}, "created_at": t0})
    asyncio.run(sembrar())
    app = FastAPI()
    app.include_router(kyc_admin.router, prefix="/api")
    jefe = User(user_id="u_jefe", name="Jefe", email="jefe@ejemplo.com", role="super_admin")
    for dep in (deps.get_current_user, deps.get_crm_user, deps.get_super_admin):
        app.dependency_overrides[dep] = lambda: jefe
    return TestClient(app, raise_server_exceptions=False)


def test_EL_CONTRATO_DEL_KYC_TIENE_TODO_LO_QUE_LA_PANTALLA_LEE():
    from models.panel_kyc import DetalleDeLaAuditoria, LineaDeLaHistoria, VerificacionQueVeElPanel
    campos = set(VerificacionQueVeElPanel.model_fields)
    assert not LO_QUE_LEE_EL_KYC["lista"] - campos
    assert not LO_QUE_LEE_EL_KYC["detalle"] - campos
    assert not LO_QUE_LEE_EL_KYC["historia"] - set(LineaDeLaHistoria.model_fields)
    assert not LO_QUE_LEE_EL_KYC["detalles"] - set(DetalleDeLaAuditoria.model_fields)


def test_LA_LISTA_DEL_KYC_TRAE_SI_HAY_FOTOS_PERO_NO_LAS_FOTOS(kyc):
    r = kyc.get("/api/admin/kyc/list")
    assert r.status_code == 200, r.text
    (v,) = r.json()["items"]
    assert v["has_selfie"] is True and v["risk_level"] == "alto" and v["blacklist_match"] is False
    assert "selfie_image" not in v and "base64" not in r.text, "la lista no trae las fotos: pesan"
    assert r.json()["counts"] == {"pending": 1, "approved": 0, "rejected": 0, "total": 1}
    assert "campo_interno" not in r.text


def test_EL_DETALLE_DEL_KYC_TRAE_LAS_FOTOS_Y_EL_SALDO_EN_NUMERO(kyc):
    r = kyc.get("/api/admin/kyc/v1")
    assert r.status_code == 200, r.text
    assert r.json()["verification"]["selfie_image"] == FOTO_SELFIE
    assert r.json()["user"]["balance_ris"] == 150.25
    _sin_secretos(r.text)
    assert "campo_interno" not in r.text


def test_LA_HISTORIA_DEL_KYC_DICE_QUIEN_POR_SU_NOMBRE_Y_NO_POR_SU_CORREO(kyc):
    r = kyc.get("/api/admin/kyc/v1/history")
    assert r.status_code == 200, r.text
    nota = next(h for h in r.json()["history"] if h["audit_id"] == "aud_1")
    assert nota["admin_name"] == "Revisora" and nota["details"]["new_value"] == "mirar la foto"
    for interno in ("revisora@ejemplo.com", "admin_email", "u_revisora"):
        assert interno not in r.text, f"la historia dejó salir «{interno}»"


# ══════════════════════════════════════════════════════════════════════════
# 6. Las órdenes por pagar y los lotes
# ══════════════════════════════════════════════════════════════════════════

def _igual_a_llamarla_directo(respuesta, directo, sin=()):
    """La ruta, por HTTP con su contrato, contesta lo mismo que su función
    llamada a mano: el contrato no se comió nada. `sin` son las claves que el
    contrato deja afuera A PROPOSITO."""
    from fastapi.encoders import jsonable_encoder
    from services import json_de_mongo
    # Lo directo trae la plata cruda de la base: se traduce con la red, como
    # la traduce el servidor de verdad cuando una ruta no tiene contrato.
    json_de_mongo.ensenarle_decimal128_a_fastapi()
    esperado = {k: v for k, v in jsonable_encoder(directo).items() if k not in sin}
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == esperado


@pytest.fixture
def ordenes(panel):
    """Un retiro a Venezuela y una recarga en bolívares, esperando."""
    import asyncio
    from datetime import datetime, timezone
    from routes import admin as rutas_admin
    from services.money import to_decimal128
    base = rutas_admin.db
    t0 = datetime(2026, 9, 20, tzinfo=timezone.utc)
    asyncio.run(base.transactions.insert_many([
        {"transaction_id": "tx_o1", "display_id": "000201", "user_id": "u_ana", "type": "withdrawal",
         "status": "pending", "currency_input": "RIS", "currency_output": "VES",
         "amount_input": to_decimal128("50.00"), "amount_output": to_decimal128("5500.00"),
         "beneficiary_data": {"full_name": "José Pérez", "id_document": "V12345678", "bank": "Banesco",
                              "bank_code": "0134", "account_number": "01340000000000000001",
                              "payment_type": "transferencia", "nota_interna": "no sale"},
         "created_at": t0},
        {"transaction_id": "tx_o2", "display_id": "000202", "user_id": "u_ana", "type": "recharge_ves",
         "status": "pending", "amount_ves": to_decimal128("1100.00"), "amount_ris": to_decimal128("10.00"),
         "proof_image": "data:image/jpeg;base64," + "PAGO" * 10, "created_at": t0},
    ]))
    return panel


def _jefe():
    from models.user import User
    return User(user_id="u_jefe", name="Jefe", email="jefe@ejemplo.com", role="super_admin")


def test_LAS_ORDENES_POR_PROCESAR_SALEN_IGUAL_QUE_LAS_ARMA_LA_RUTA(ordenes):
    import asyncio
    from routes import admin as rutas_admin
    r = ordenes.get("/api/admin/ordenes/pendientes")
    _igual_a_llamarla_directo(r, asyncio.run(rutas_admin.get_ordenes_pendientes(admin=_jefe())))
    assert {o["orden_id"] for o in r.json()["ordenes"]} == {"tx_o1", "tx_o2"}
    assert "nota_interna" not in r.text


def test_LA_REVISION_DE_PAGO_Y_LOS_BANCOS_SALEN_IGUAL_QUE_LOS_ARMA_LA_RUTA(ordenes):
    import asyncio
    from routes import admin as rutas_admin
    _igual_a_llamarla_directo(ordenes.get("/api/admin/ordenes/revision-pago"),
                              asyncio.run(rutas_admin.get_ordenes_revision_pago(admin=_jefe())))
    _igual_a_llamarla_directo(ordenes.get("/api/admin/ordenes/bancos-para-pagar"),
                              asyncio.run(rutas_admin.bancos_para_pagar(admin=_jefe())))


def test_UN_LOTE_SE_ARMA_SE_LISTA_SE_BAJA_Y_SE_CANCELA_SIN_PERDER_NADA(ordenes):
    """El ciclo del lote por HTTP. Cada lectura, igual a su servicio; armarlo
    no devuelve las órdenes con sus beneficiarios (ya están en el archivo)."""
    import asyncio
    from routes import admin as rutas_admin
    from services import comprobantes_del_lote, lotes_de_pago
    base = rutas_admin.db
    r = ordenes.post("/api/admin/lotes", json={"orden_ids": ["tx_o1"], "banco_pagador": "0102"})
    assert r.status_code == 200, r.text
    lote = r.json()
    assert lote["total"] == 1 and lote["texto"] and lote["banco_pagador"]["codigo"] == "0102"
    assert "ordenes" not in lote and "creado_por" not in lote
    lote_id = lote["lote_id"]

    _igual_a_llamarla_directo(ordenes.get("/api/admin/lotes"), {"lotes": asyncio.run(lotes_de_pago.abiertos(base))})
    _igual_a_llamarla_directo(ordenes.get(f"/api/admin/lotes/{lote_id}/archivo"),
                              asyncio.run(lotes_de_pago.archivo(base, lote_id)))
    _igual_a_llamarla_directo(ordenes.get(f"/api/admin/lotes/{lote_id}/comprobantes"),
                              asyncio.run(comprobantes_del_lote.listar(base, lote_id)))

    r = ordenes.post(f"/api/admin/lotes/{lote_id}/cancelar")
    assert r.status_code == 200, r.text
    assert r.json()["devueltas"] == 1
    _igual_a_llamarla_directo(ordenes.get("/api/admin/lotes/cerrados"),
                              {"lotes": asyncio.run(lotes_de_pago.cerrados(base))})


LO_QUE_LEEN_ORDENES_Y_LOTES = {
    "OrdenPorProcesar": {"orden_id", "flujo", "flujo_label", "accion", "display_id", "created_at", "user_name",
                         "origen", "destino", "comprobante_usuario", "assigned_to", "assigned_to_name",
                         "beneficiario"},
    "BeneficiarioDeLaOrden": {"nombre", "documento", "banco", "telefono", "cuenta", "tipo_pago", "pix_key"},
    "OrdenEnRevisionDePago": {"orden_id", "display_id", "topup_expired", "user_name", "user_email", "created_at",
                              "paid_ratio", "pay_amount", "moneda", "actually_paid", "topup_actually_paid",
                              "faltante", "recibido_total", "red", "amount_output", "currency_output",
                              "beneficiario"},
    "LoteEnLaLista": {"lote_id", "numero", "total", "banco_pagador", "creado_por_nombre", "creado_en",
                      "sin_datos", "cerrado_por_nombre", "cerrado_en"},
    "LoteArmado": {"texto", "numero", "banco_pagador", "total", "por_seccion", "sin_datos",
                   "no_se_pudieron_tomar", "ya_no_estan"},
    "ComprobanteDelLote": {"orden_id", "comprobante_id", "estado", "motivo", "leido"},
    "OrdenDelLote": {"orden_id", "display_id", "beneficiario", "monto", "tiene_comprobante", "listo_para_registrar"},
    "ComprobantesDelLote": {"estado", "hay_lector", "por_que_no_hay_lector", "descartadas", "comprobantes",
                            "ordenes"},
    "LoLeido": {"cuentas", "telefonos", "montos"},
}


@pytest.mark.parametrize("modelo", sorted(LO_QUE_LEEN_ORDENES_Y_LOTES))
def test_LOS_CONTRATOS_DE_ORDENES_Y_LOTES_TIENEN_TODO_LO_QUE_LAS_PANTALLAS_LEEN(modelo):
    """OrdenesPorProcesar.jsx, DiferenciasPago.jsx, LotesDePago y
    ComprobantesDelLote.jsx."""
    from models import panel_ordenes
    faltan = LO_QUE_LEEN_ORDENES_Y_LOTES[modelo] - set(getattr(panel_ordenes, modelo).model_fields)
    assert not faltan, f"la pantalla lee {modelo}.{sorted(faltan)} y el contrato no lo deja pasar"


# ══════════════════════════════════════════════════════════════════════════
# 7. Las recargas
# ══════════════════════════════════════════════════════════════════════════

def _sin_reloj(pagina):
    """La antigüedad se calcula con el reloj en cada llamada: puede diferir
    en un segundo entre dos llamadas. Se saca, comprobando que esté."""
    for fila in pagina.get("recharges", []):
        assert fila.pop("antiguedad")["nivel"]
    if "counters" in pagina:
        assert pagina["counters"].pop("mas_vieja")["nivel"]
    return pagina


def test_LA_COLA_DE_RECARGAS_EN_BOLIVARES_SALE_IGUAL_QUE_LA_ARMA_LA_RUTA(ordenes):
    import asyncio
    from fastapi.encoders import jsonable_encoder
    from routes import admin as rutas_admin
    from services import json_de_mongo
    json_de_mongo.ensenarle_decimal128_a_fastapi()
    r = ordenes.get("/api/admin/recharges/ves")
    assert r.status_code == 200, r.text
    directo = asyncio.run(rutas_admin.get_all_ves_recharges(
        status="pending", q="", limit=50, skip=0, admin=_jefe()))
    assert _sin_reloj(r.json()) == _sin_reloj(jsonable_encoder(directo))
    assert r.json()["recharges"][0]["amount_ves"] == 1100.0
    _igual_a_llamarla_directo(ordenes.get("/api/admin/recharges/ves/pending"),
                              asyncio.run(rutas_admin.get_pending_ves_recharges(admin=_jefe())))


def test_EL_CONTROL_DE_REFERENCIA_CONTESTA_IGUAL_CON_Y_SIN_COINCIDENCIAS(ordenes):
    import asyncio
    from routes import admin as rutas_admin
    for digitos in ("12", "345"):
        _igual_a_llamarla_directo(
            ordenes.get("/api/admin/recharges/ves/check-reference", params={"digits": digitos}),
            asyncio.run(rutas_admin.check_ves_reference(digits=digitos, admin=_jefe())))


LO_QUE_LEE_RECARGAS_VES = {
    "RecargaEnLaCola": {"transaction_id", "status", "user_name", "user_email", "amount_ris", "amount_ves",
                        "rate_used", "proof_image", "falta_banco", "falta_comprobante", "assigned_to",
                        "assigned_to_name", "rejection_reason", "reference_digits", "processed_at",
                        "processed_by", "posicion", "created_at", "destination_bank", "destination_bank_name",
                        "referencia", "banco_elegido_a_mano", "antiguedad"},
    "ContadoresDeRecargas": {"pendientes", "aprobadas", "rechazadas", "total", "ves_pendiente", "sin_banco",
                             "sin_comprobante", "mas_vieja"},
    "ControlDeReferencia": {"has_collision", "first_registered"},
}


@pytest.mark.parametrize("modelo", sorted(LO_QUE_LEE_RECARGAS_VES))
def test_LOS_CONTRATOS_DE_RECARGAS_TIENEN_TODO_LO_QUE_LA_PANTALLA_LEE(modelo):
    """RecargasVES.jsx."""
    from models import panel_recargas
    faltan = LO_QUE_LEE_RECARGAS_VES[modelo] - set(getattr(panel_recargas, modelo).model_fields)
    assert not faltan, f"la pantalla lee {modelo}.{sorted(faltan)} y el contrato no lo deja pasar"


@pytest.fixture
def rutas_viejas(monkeypatch):
    """Las rutas de `admin_routes.py`, que abren su propia conexión."""
    import asyncio
    from datetime import datetime, timezone
    import admin_routes
    from _lote_c_comun import app_con, SUPER
    from routes import dependencies as deps
    from services.money import to_decimal128
    c, base = app_con(admin_routes.admin_router, deps.get_admin_user, SUPER, "rutas_viejas")
    monkeypatch.setattr(admin_routes, "db", base)
    t0 = datetime(2026, 9, 20, tzinfo=timezone.utc)
    asyncio.run(base.transactions.insert_one({
        "transaction_id": "tx_r9", "user_id": "u_ana", "type": "recharge", "status": "pending",
        "amount_input": to_decimal128("100.00"), "currency_input": "BRL", "created_at": t0,
        "proof_image": "data:image/jpeg;base64," + "PIX" * 12,
        "mp_payment_id": "123456789", "nota_interna": "revisar el titular", "ip_del_cliente": "10.0.0.7"}))
    asyncio.run(base.admin_payment_records.insert_one({
        "record_type": "recharge", "transaction_id": "tx_r8", "user_id": "u_ana", "amount_ris": to_decimal128("50.00"),
        "proof_image": "data:image/jpeg;base64," + "PIX" * 12, "approved_by": "u_jefe", "created_at": t0,
        "nota_interna": "revisar el titular"}))
    return c


def test_LAS_RUTAS_VIEJAS_DE_RECARGAS_YA_NO_DEVUELVEN_EL_DOCUMENTO_ENTERO(rutas_viejas):
    r = rutas_viejas.get("/api/admin/recharges/pending")
    assert r.status_code == 200, r.text
    (rec,) = r.json()["recharges"]
    assert rec["transaction_id"] == "tx_r9" and rec["amount_input"] == 100.0
    r_lista = rutas_viejas.get("/api/admin/payment-records")
    assert r_lista.status_code == 200, r_lista.text
    assert r_lista.json()["records"][0]["amount_ris"] == 50.0
    for texto in (r.text, r_lista.text):
        for interno in ("nota_interna", "revisar el titular", "ip_del_cliente", "10.0.0.7", "mp_payment_id", "base64"):
            assert interno not in texto, f"salió «{interno}»"
    r = rutas_viejas.get("/api/admin/recharges/tx_r9/proof")
    assert r.status_code == 200, r.text
    assert r.json()["proof_image"].startswith("data:image/jpeg;base64,") and "nota_interna" not in r.text


# ══════════════════════════════════════════════════════════════════════════
# 8. Los depósitos en cripto
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def creditos():
    import asyncio
    from datetime import datetime, timezone
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from conftest import usar_base, ensenarle_decimal128_a_mongomock
    from routes import credits_admin, dependencies as deps

    ensenarle_decimal128_a_mongomock()
    base = mongomock_motor.AsyncMongoMockClient()["contratos_creditos"]
    usar_base(base)
    t0 = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)
    asyncio.run(base.users.insert_one({"user_id": "u_ana", "email": "ana@ejemplo.com", "name": "Ana"}))
    asyncio.run(base.crypto_deposits.insert_one({
        "order_id": "cr_1", "user_id": "u_ana", "currency": "usdt", "pay_currency": "usdttrc20", "network": "TRC20",
        # Como float, igual que lo guardan `routes/credits.py` y la acreditación
        # manual: acá la plata no se guarda en Decimal128.
        "amount": 25.0, "credit_amount": 25.0, "status": "finished", "credited": True, "created_at": t0,
        "credited_at": t0, "source": "nowpayments", "admin_note": "",
        "pay_address": "TQ4ZDireccionDePago", "payin_extra_id": "memo-777",
        "credit_error": "Traceback interno", "webhook_last_seen": t0, "admin_id": "u_jefe"}))
    app = FastAPI()
    app.include_router(credits_admin.router, prefix="/api")
    app.dependency_overrides[deps.get_super_admin] = _jefe
    return TestClient(app)


def test_LOS_DEPOSITOS_CRIPTO_SALEN_CON_LO_QUE_LA_PANTALLA_MUESTRA_Y_SIN_LO_INTERNO(creditos):
    r = creditos.get("/api/admin/credits/deposits")
    assert r.status_code == 200, r.text
    (d,) = r.json()["items"]
    lee = {"order_id", "created_at", "user_name", "user_email", "amount", "currency", "source", "admin_note", "status"}
    assert lee <= set(d), f"la pantalla lee {sorted(lee - set(d))} y no vino"
    assert d["amount"] == 25.0 and d["user_email"] == "ana@ejemplo.com"
    r2 = creditos.get("/api/admin/credits/report", params={"date_from": "2026-09-20", "date_to": "2026-09-20"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["totals"]["usdt"] == 25.0 and r2.json()["by_day"][0]["count"] == 1
    for texto in (r.text, r2.text):
        for interno in ("TQ4ZDireccionDePago", "memo-777", "Traceback interno", "webhook_last_seen", "u_jefe"):
            assert interno not in texto, f"salió «{interno}»"


def test_EL_REPORTE_EN_CSV_SIGUE_SIENDO_UN_ARCHIVO(creditos):
    """El contrato no toca un archivo: FastAPI lo devuelve tal cual."""
    r = creditos.get("/api/admin/credits/report",
                     params={"date_from": "2026-09-20", "date_to": "2026-09-20", "format": "csv"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv") and "cr_1" in r.text
