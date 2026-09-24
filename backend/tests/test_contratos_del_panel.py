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
