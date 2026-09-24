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
