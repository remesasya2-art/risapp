"""
tests/test_contratos_de_seguridad.py — Las acciones con las que el cliente
cuida su cuenta salen por un contrato, y ningún contrato se come un campo que
su ruta devuelve.

Cuarta tanda de los contratos de las acciones. La lectura de las claves desde
el código es la misma de la tercera (`test_contratos_de_acceso.py`), y se usa
de ahí para que sea UNA: dos copias de un lector se separan igual que dos
listas de lo prohibido.

Además del chequeo por lectura, el PIN se recorre entero por HTTP —ponerlo,
comprobarlo, sacarlo—, con las claves exactas de cada respuesta: el contrato
que se come una o que agrega un `null` se ve ahí.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from test_contratos_de_acceso import _claves, _ruta              # noqa: E402

RUTAS = [
    ("routes/auth.py", "POST", "/change-password/pedir-codigo", "MiCodigoDeCambioPedido", None),
    ("routes/auth.py", "POST", "/change-password", "MiClaveCambiada", None),
    ("routes/auth.py", "POST", "/set-new-password", "MiClaveCambiada", None),
    ("routes/auth.py", "POST", "/register-fcm-token", "MiMensaje", None),
    ("routes/security_2fa.py", "POST", "/activar-init", "MiAltaDeDosPasos", None),
    ("routes/security_2fa.py", "POST", "/activar-confirm", "MisCodigosDeRespaldo", None),
    ("routes/security_2fa.py", "POST", "/disable", "MiMensaje", None),
    ("routes/security_2fa.py", "POST", "/regenerate-backup-codes", "MisCodigosDeRespaldo", None),
    ("routes/webauthn_login.py", "POST", "/register/verify", "MiResultado", None),
    ("routes/webauthn_login.py", "DELETE", "/credentials/{credential_id}", "MiResultado", None),
    ("routes/pin.py", "POST", "/set", "MiResultado", None),
    ("routes/pin.py", "POST", "/verify", "MiResultado", None),
    ("routes/pin.py", "POST", "/hint-check", "MiSugerenciaDePin", None),
    ("routes/pin.py", "POST", "/disable", "MiResultado", None),
    ("routes/recovery.py", "POST", "/verify-identity", "MiIdentidadComprobada", None),
    ("routes/recovery.py", "POST", "/verify-code", "MiCodigoDeRecuperacionComprobado", None),
    ("routes/recovery.py", "POST", "/reset-password", "MiResultado", None),
    ("routes/recovery.py", "POST", "/support-contact", "MiPedidoDeAyuda", None),
]
_IDS = [f"{m} {a.split('/')[-1][:-3]}{c}" for a, m, c, _, _ in RUTAS]


# ══════════════════════════════════════════════════════════════════════════
# 1. Cada acción tiene su contrato, y el contrato no se come nada
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("archivo,metodo,camino,modelo,fuente", RUTAS, ids=_IDS)
def test_CADA_ACCION_DE_SEGURIDAD_TIENE_SU_CONTRATO(archivo, metodo, camino, modelo, fuente):
    ruta = _ruta(archivo, metodo, camino)
    assert ruta.response_model is not None and ruta.response_model.__name__ == modelo
    assert ruta.response_model_exclude_unset is True, "lo que la ruta no pone no tiene que salir como null"


@pytest.mark.parametrize("archivo,metodo,camino,modelo,fuente", RUTAS, ids=_IDS)
def test_EL_CONTRATO_NO_SE_COME_NINGUN_CAMPO_QUE_LA_ACCION_DEVUELVE(archivo, metodo, camino, modelo, fuente):
    ruta = _ruta(archivo, metodo, camino)
    faltan = _claves(archivo, metodo, camino, fuente) - set(ruta.response_model.model_fields)
    assert not faltan, f"{camino} devuelve {sorted(faltan)} y su contrato no los tiene"


def test_LA_LECTURA_DEL_CODIGO_ENCUENTRA_CLAVES():
    vacias = [c for a, m, c, _, f in RUTAS if not _claves(a, m, c, f)]
    assert vacias == [], vacias


# Lo que estas rutas acaban de leer o de escribir, y no puede salir.
LO_QUE_NO_SALE = {
    "password_hash": "$2b$12$clave", "pin_hash": "$2b$12$pin",
    "two_factor_secret": "JBSWY3DPEHPK3PXP", "two_factor_backup_hashes": ["$2b$12$uno"],
    "webauthn_credentials": [{"public_key": "CLAVE-PUBLICA"}],
    "codigo": "123456", "code_hash": "$2b$12$codigo", "user_id": "u_ana",
}


# Las claves que estas rutas devuelven como lista. Hoy, sólo los códigos de
# respaldo: `plain_codes` en `routes/security_2fa.py`.
DEVUELVEN_UNA_LISTA = {"backup_codes"}


@pytest.mark.parametrize("archivo,metodo,camino,modelo,fuente", RUTAS, ids=_IDS)
def test_LO_QUE_SE_LEYO_PARA_DECIDIR_NO_SALE_AUNQUE_LA_RUTA_LO_DEVUELVA(archivo, metodo, camino, modelo, fuente):
    """El error que ya pasó en las puertas de entrada: contestar con el
    documento que se acaba de leer. Se le pasa al contrato lo que la ruta
    devuelve hoy MÁS todo eso, y no sale nada de lo segundo."""
    from fastapi.encoders import jsonable_encoder
    contrato = _ruta(archivo, metodo, camino).response_model
    # Un valor de relleno por clave, del tipo que la RUTA devuelve —no del que
    # dice el contrato: tomarlo del contrato hacía pasar un contrato que
    # declaraba los códigos como un valor suelto y los vaciaba—.
    hoy = {k: ["x"] if k in DEVUELVEN_UNA_LISTA else "x" for k in _claves(archivo, metodo, camino, fuente)}
    sale = jsonable_encoder(contrato.model_validate({**hoy, **LO_QUE_NO_SALE}).model_dump(exclude_unset=True))
    # Lo de hoy sale entero, con su valor: un tipo mal puesto en el contrato
    # —una lista donde se espera un valor suelto— lo vaciaría sin error, y los
    # códigos de respaldo se muestran UNA sola vez.
    assert {k: sale.get(k) for k in hoy} == hoy, f"{camino} vacía un campo que la pantalla muestra"
    salida = str(sale)
    for campo, valor in LO_QUE_NO_SALE.items():
        if campo in hoy:
            continue    # pragma: no cover — ninguna de estas lo devuelve hoy
        assert campo not in salida and str(valor) not in salida, f"{camino} dejó salir «{campo}»"


# ══════════════════════════════════════════════════════════════════════════
# 2. El PIN, de punta a punta, por HTTP
# ══════════════════════════════════════════════════════════════════════════

mongomock_motor = pytest.importorskip("mongomock_motor")

CLAVE = "Colibri!2026x"


@pytest.fixture
def cliente():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from conftest import usar_base
    from models.user import User
    from routes import dependencies as deps
    from routes import pin as rutas_pin
    from utils.security import hash_password

    base = mongomock_motor.AsyncMongoMockClient()["contratos_de_seguridad"]
    usar_base(base)
    asyncio.run(base.users.insert_one({
        "user_id": "u_ana", "email": "ana@ejemplo.com", "name": "Ana", "role": "user",
        "verification_status": "verified", "password_hash": hash_password(CLAVE)}))
    ana = User(user_id="u_ana", email="ana@ejemplo.com", name="Ana", verification_status="verified")
    app = FastAPI()
    app.include_router(rutas_pin.router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: ana
    app.dependency_overrides[deps.get_verified_user] = lambda: ana
    return TestClient(app)


def test_EL_PIN_SE_PONE_SE_COMPRUEBA_Y_SE_SACA_CON_LAS_MISMAS_RESPUESTAS_DE_SIEMPRE(cliente):
    r = cliente.post("/api/pin/set", json={"password": CLAVE, "pin": "4821"})
    assert r.status_code == 200 and r.json() == {"success": True, "message": "PIN configurado correctamente"}
    r = cliente.post("/api/pin/verify", json={"pin": "4821"})
    assert r.status_code == 200 and r.json() == {"success": True}, "sin `message: null` de más"
    r = cliente.post("/api/pin/hint-check")
    assert r.status_code == 200 and r.json() == {"hint": False}
    r = cliente.post("/api/pin/disable", json={"password": CLAVE})
    assert r.status_code == 200 and set(r.json()) == {"success", "message"}
    assert "$2b$" not in r.text and "pin_hash" not in r.text
