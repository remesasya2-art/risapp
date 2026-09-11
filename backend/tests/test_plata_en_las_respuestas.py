"""
tests/test_plata_en_las_respuestas.py — Que el dinero salga como lo quiere el
JSON, y no como sale de Mongo.

EL DEFECTO, QUE LLEGO A PRODUCCION

    En esta base la plata se guarda en `Decimal128` — lo escribe
    `services/saldos.py` con `to_decimal128`, y es lo correcto: un float no
    guarda dinero. Pero FastAPI no sabe serializar ese tipo. Prueba
    `dict(obj)`, prueba `vars(obj)`, las dos fallan:

        ValueError: [TypeError("'Decimal128' object is not iterable"),
                     TypeError('vars() argument must have __dict__ attribute')]

    Y ocurre en `serialize_response`, DESPUES de que el manejador retornó, así
    que ningún try/except de la ruta lo atrapa. El resultado es un 500 pelado:
    la pantalla queda en blanco y el registro habla de un tipo de bson.

    Se vio en la consola de la mesa de ayuda. Buscándolo, el mismo defecto
    estaba en el detalle de KYC.

POR QUE NINGUN TEST LO VEIA

    Porque todos escribían la plata como número de Python. `mongomock` SI
    conserva `Decimal128` cuando se le inserta uno: la única razón por la que
    esto pasó fue que ningún test la escribía como la escribe la aplicación.

    Por eso este archivo insertA SIEMPRE con `to_decimal128`, igual que el
    código de verdad. Un test que use `1234.56` a secas pasa con el producto
    roto, que es exactamente lo que hay que evitar.
"""
import asyncio
import os
import sys
import types
from decimal import Decimal

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor", reason="hace falta mongomock_motor para estos tests")

from bson.decimal128 import Decimal128                                # noqa: E402


def _ya(corrutina):
    return asyncio.run(corrutina)


def _sin_webpush():
    if "pywebpush" not in sys.modules:                        # pragma: no cover
        stub = types.ModuleType("pywebpush")
        stub.WebPushException = type("WebPushException", (Exception,), {})
        stub.webpush = lambda *a, **k: None
        sys.modules["pywebpush"] = stub


from models.user import User                                          # noqa: E402

REVISOR = User(user_id="s_rev", name="Rita Revisora", email="rita@t.com",
               role="admin", permissions=["kyc.view", "kyc.approve"])


def _app_kyc(nombre):
    _sin_webpush()
    from conftest import usar_base
    base = mongomock_motor.AsyncMongoMockClient()[nombre]
    usar_base(base)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.kyc_admin import router
    from routes import dependencies as deps

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[deps.get_crm_user] = lambda: REVISOR
    return TestClient(app), base


def test_la_ficha_de_kyc_abre_con_el_saldo_en_decimal128():
    """El 500 que tenía la pantalla de revisión de KYC.

    No hacía falta nada raro: cualquier usuario con saldo —o sea, cualquiera
    que haya operado— rompía la ficha.
    """
    cliente, base = _app_kyc("ris_kyc_d128")

    async def sembrar():
        from services.money import to_decimal128
        await base.users.insert_one({
            "user_id": "u_ana", "email": "ana@t.com", "full_name": "Ana Cliente",
            "role": "user", "verification_status": "pending",
            # Como lo escribe `services/saldos.py`, no como lo escribía el test.
            "balance_ris": to_decimal128(Decimal("1234.56")),
        })
        await base.verifications.insert_one({
            "verification_id": "v_1", "user_id": "u_ana", "status": "pending",
            "submitted_at": None,
        })

    _ya(sembrar())

    r = cliente.get("/api/admin/kyc/v_1")
    assert r.status_code == 200, f"la ficha de KYC no abre: {r.text[:300]}"
    assert r.json()["user"]["balance_ris"] == 1234.56


@pytest.mark.parametrize("guardado,esperado", [
    (Decimal128(Decimal("1234.56")), 1234.56),   # lo que escribe la app hoy
    (1234.56, 1234.56),                          # float de los datos viejos
    ("1234.56", 1234.56),                        # string, que también hay
    (0, 0.0),
])
def test_el_saldo_de_la_ficha_sale_como_numero_venga_como_venga(guardado, esperado):
    """La base tiene la plata escrita de tres formas según quién la tocó. La
    pantalla tiene que abrir con todas."""
    cliente, base = _app_kyc(f"ris_kyc_{type(guardado).__name__}_{guardado}")

    async def sembrar():
        await base.users.insert_one({
            "user_id": "u_ana", "email": "ana@t.com", "role": "user",
            "verification_status": "pending", "balance_ris": guardado})
        await base.verifications.insert_one({
            "verification_id": "v_1", "user_id": "u_ana", "status": "pending",
            "submitted_at": None})

    _ya(sembrar())
    r = cliente.get("/api/admin/kyc/v_1")
    assert r.status_code == 200, r.text[:300]
    assert r.json()["user"]["balance_ris"] == esperado


def test_una_ficha_sin_saldo_no_inventa_un_cero():
    """Ausente y cero no son lo mismo: cero dice «no tiene plata», la ausencia
    dice «este campo no está cargado»."""
    cliente, base = _app_kyc("ris_kyc_sin_saldo")

    async def sembrar():
        await base.users.insert_one({
            "user_id": "u_ana", "email": "ana@t.com", "role": "user",
            "verification_status": "pending"})
        await base.verifications.insert_one({
            "verification_id": "v_1", "user_id": "u_ana", "status": "pending",
            "submitted_at": None})

    _ya(sembrar())
    r = cliente.get("/api/admin/kyc/v_1")
    assert r.status_code == 200, r.text[:300]
    assert "balance_ris" not in r.json()["user"]


# ─── La red que atrapa al próximo ─────────────────────────────────────────

def test_ninguna_ruta_devuelve_balance_ris_sin_convertirlo():
    """Los dos defectos eran la misma causa: proyectar `balance_ris` y devolver
    el documento tal cual.

    Este test no prueba un comportamiento, prueba una FORMA — y por eso vale:
    el que escriba la tercera ruta que proyecte el saldo se entera acá, y no en
    el registro de producción tres semanas después.

    Si agregás una ruta que proyecte `balance_ris`, convertilo con `to_float`
    antes de devolverlo (o sumá el archivo a la lista de abajo explicando por
    qué no hace falta).
    """
    import re
    from pathlib import Path

    rutas = Path(_BACKEND) / "routes"
    # Archivos donde proyectar el saldo NO implica devolverlo crudo, con el
    # motivo al lado. Se revisan a mano cuando cambian.
    sabidos = {
        # Construye su respuesta campo por campo, ya convertida con to_float().
        "ledger_admin.py",
    }

    culpables = []
    for archivo in sorted(rutas.glob("*.py")):
        if archivo.name in sabidos:
            continue
        texto = archivo.read_text(encoding="utf-8")
        if not re.search(r'["\']balance_ris["\']\s*:\s*1', texto):
            continue
        if "to_float" not in texto and "from_db" not in texto:
            culpables.append(archivo.name)

    assert not culpables, (
        "estas rutas proyectan `balance_ris` y no lo convierten: "
        f"{culpables}. En Mongo el saldo es Decimal128 y FastAPI no lo "
        "serializa: es un 500 en la cara del usuario."
    )
