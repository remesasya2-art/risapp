"""El cliente puede activar la verificación en dos pasos, y el ingreso la mira.

QUE PASABA

    El segundo factor era sólo del personal. Para el cliente el factor extra
    era la huella, y el camino del perfil estaba RETIRADO a propósito: había
    existido, encendía la marca, y las puertas de entrada no la miraban. O
    sea que quien lo usara quedaba con una protección que el ingreso
    ignoraba, y que encima no podía apagar sin un código del teléfono.

    Volver a poner el alta sin lo demás habría reconstruido ese agujero. Lo
    que faltaba no era la pantalla: era que las puertas respetaran la marca.

LO QUE SE PRUEBA

    1. Que la regla viva en UN lugar y diga lo correcto para cada caso.
    2. Que el ingreso con contraseña le pida el código a un CLIENTE que lo
       activó, que es lo que antes no pasaba.
    3. Que activarlo desde el perfil funcione, y que no se pueda dos veces.
    4. Que nada quede encendido hasta que llegue el primer código correcto.
    5. Que la huella siga entrando sin código, que es una decisión tomada.
"""
import asyncio
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

pyotp = pytest.importorskip("pyotp")

from conftest import usar_base                                      # noqa: E402
from services import personal                                       # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_2fa_cliente"]
    usar_base(b)
    yield b


CLIENTE = {"user_id": "u_1", "email": "cliente@ejemplo.com", "name": "Cliente",
           "role": "user"}


# ══════════════════════════════════════════════════════════════════════════
# 1. La regla, en un solo lugar
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cuenta,obliga,pide", [
    # Un cliente sin nada: ni obligado ni se le pide.
    ({"role": "user"}, False, False),
    # UN CLIENTE QUE LO ACTIVO: no está obligado, pero SE LE PIDE.
    # Esto es todo el cambio. Antes daba (False, False) y la marca era humo.
    ({"role": "user", "two_factor_enabled": True}, False, True),
    # El personal: obligado siempre, se le pide siempre.
    ({"role": "admin"}, True, True),
    ({"role": "agent"}, True, True),
    ({"role": "super_admin"}, True, True),
    ({"role": "user", "es_personal": True}, True, True),
    # Personal que además lo tiene puesto: sigue dando lo mismo.
    ({"role": "admin", "two_factor_enabled": True}, True, True),
])
def test_quien_esta_obligado_y_a_quien_se_le_pide(cuenta, obliga, pide):
    assert personal.exige_dos_pasos(cuenta) is obliga, "obligación"
    assert personal.pide_dos_pasos(cuenta) is pide, "se le pide al entrar"


def test_la_regla_no_se_cae_con_una_cuenta_vacia():
    for vacia in (None, {}, {"role": None}):
        assert personal.exige_dos_pasos(vacia) is False
        assert personal.pide_dos_pasos(vacia) is False


def test_un_cliente_obligado_NO_existe_por_tener_la_marca():
    """Activarlo no convierte a nadie en personal. Si lo hiciera, el cliente
    caería bajo la regla de «no puede hacer transacciones a título personal»
    y dejaría de poder mandar plata por activar una protección."""
    cliente = {"role": "user", "two_factor_enabled": True}
    assert personal.exige_dos_pasos(cliente) is False
    assert personal.es_personal(cliente) is False


# ══════════════════════════════════════════════════════════════════════════
# 2. El ingreso se lo pide
# ══════════════════════════════════════════════════════════════════════════

def test_de_punta_a_punta_al_cliente_con_dos_pasos_le_piden_el_codigo():
    """Lo que antes no pasaba: un cliente lo activaba y entraba igual con la
    contraseña sola, porque la condición era `(is_admin or obliga) and
    twofa_enabled` y él no entraba por ninguna de las dos ramas.

    Va por la ruta de verdad, con la aplicación entera en el medio: los tests
    de la regla de arriba pasarían igual si nadie la llamara.
    """
    try:
        import server
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    from fastapi.testclient import TestClient
    from utils.security import hash_password

    b = mongomock_motor.AsyncMongoMockClient()["ris_2fa_e2e"]
    usar_base(b)
    anterior, server.db = server.db, b
    try:
        corre(b.users.insert_one({
            **CLIENTE, "password_hash": hash_password("SuperSecreta123"),
            "password_set": True, "is_active": True, "email_verified": True,
            "two_factor_enabled": True,
            "two_factor_secret": pyotp.random_base32()}))
        with TestClient(server.app) as cliente:
            r = cliente.post("/api/auth/login-password",
                             json={"email": CLIENTE["email"],
                                   "password": "SuperSecreta123"})
        assert r.status_code == 200, r.text
        salida = r.json()
        assert salida.get("two_factor_required") is True, salida
        assert salida.get("pending_token"), "sin token no puede seguir"
        assert "session_token" not in salida, "¡entró sin el código!"
        assert not r.cookies.get("session_token"), "¡le dejaron la cookie de sesión!"
    finally:
        server.db = anterior


# ══════════════════════════════════════════════════════════════════════════
# 3. Activarlo desde el perfil
# ══════════════════════════════════════════════════════════════════════════

def test_activar_no_enciende_nada_hasta_el_primer_codigo_correcto(base):
    """Quien abre la pantalla y se arrepiente no queda a medio camino: hasta
    que no escribe un código válido, la cuenta sigue exactamente igual."""
    from models.user import User
    from routes import security_2fa

    async def cuerpo():
        await base.users.insert_one({**CLIENTE, "is_active": True})
        usuario = User(**CLIENTE, verification_status="unverified")
        datos = await security_2fa.activar_dos_pasos_init(current_user=usuario)
        assert datos["qr_code_data_url"].startswith("data:image/")
        doc = await base.users.find_one({"user_id": "u_1"})
        assert doc.get("two_factor_enabled") is None, "se encendió antes de tiempo"
        assert doc.get("two_factor_secret_pending"), "no quedó el secreto pendiente"
        assert doc.get("two_factor_secret") is None, "el secreto no es definitivo todavía"
    corre(cuerpo())


def test_no_se_puede_activar_dos_veces(base):
    from fastapi import HTTPException
    from models.user import User
    from routes import security_2fa

    async def cuerpo():
        await base.users.insert_one({**CLIENTE, "is_active": True,
                                     "two_factor_enabled": True})
        usuario = User(**CLIENTE, verification_status="unverified")
        with pytest.raises(HTTPException) as e:
            await security_2fa.activar_dos_pasos_init(current_user=usuario)
        assert e.value.status_code == 400
    corre(cuerpo())


def test_confirmar_sin_haber_pedido_el_QR_no_enciende_nada(base):
    from fastapi import HTTPException
    from models.user import User
    from routes import security_2fa

    async def cuerpo():
        await base.users.insert_one({**CLIENTE, "is_active": True})
        usuario = User(**CLIENTE, verification_status="unverified")
        with pytest.raises(HTTPException) as e:
            await security_2fa.activar_dos_pasos_confirm(
                _pedido_falso(), security_2fa.ActivarDosPasosConfirm(code="123456"),
                current_user=usuario)
        assert e.value.status_code == 400
        # EL MENSAJE, Y NO SOLO EL NUMERO. Las dos guardas de esta ruta
        # devuelven 400: «no pediste el QR» y «código incorrecto». Comprobando
        # sólo el número, sacar la primera dejaba el test en verde —caía en la
        # segunda y daba 400 igual—. Lo encontró una mutación.
        assert "QR" in e.value.detail, e.value.detail
        doc = await base.users.find_one({"user_id": "u_1"})
        assert doc.get("two_factor_enabled") is None
        assert doc.get("two_factor_secret") is None, "se guardó un secreto de la nada"
    corre(cuerpo())


def _pedido_falso():
    class _P:
        method = "POST"
        url = type("U", (), {"path": "/api/auth/2fa/activar-confirm"})()
        headers, cookies = {}, {}
        client = type("C", (), {"host": "1.2.3.4"})()
        scope = {"type": "http", "headers": []}
        state = type("S", (), {})()
    return _P()


def test_con_el_codigo_correcto_se_enciende_y_devuelve_los_de_respaldo(base, monkeypatch):
    from models.user import User
    from routes import security_2fa

    async def _sin_correo(*a, **k):
        return None
    monkeypatch.setattr(security_2fa, "notify_dos_pasos_activado", _sin_correo)

    async def cuerpo():
        await base.users.insert_one({**CLIENTE, "is_active": True})
        usuario = User(**CLIENTE, verification_status="unverified")
        datos = await security_2fa.activar_dos_pasos_init(current_user=usuario)
        codigo = pyotp.TOTP(datos["secret"]).now()
        salida = await security_2fa.activar_dos_pasos_confirm(
            _pedido_falso(), security_2fa.ActivarDosPasosConfirm(code=codigo),
            current_user=usuario)

        assert salida["backup_codes"], "sin códigos de respaldo queda encerrado"
        assert "session_token" not in salida, "no tiene que emitir otra sesión"
        doc = await base.users.find_one({"user_id": "u_1"})
        assert doc["two_factor_enabled"] is True
        assert doc["two_factor_secret"] == datos["secret"]
        assert doc.get("two_factor_secret_pending") is None, "el pendiente no se limpió"
        assert len(doc["two_factor_backup_hashes"]) == len(salida["backup_codes"])
        # Y ahora el ingreso se lo pide, que es el punto de todo esto.
        assert personal.pide_dos_pasos(doc) is True
    corre(cuerpo())


def test_un_codigo_equivocado_no_enciende_nada(base):
    from fastapi import HTTPException
    from models.user import User
    from routes import security_2fa

    async def cuerpo():
        await base.users.insert_one({**CLIENTE, "is_active": True})
        usuario = User(**CLIENTE, verification_status="unverified")
        datos = await security_2fa.activar_dos_pasos_init(current_user=usuario)
        malo = "000000" if pyotp.TOTP(datos["secret"]).now() != "000000" else "111111"
        with pytest.raises(HTTPException) as e:
            await security_2fa.activar_dos_pasos_confirm(
                _pedido_falso(), security_2fa.ActivarDosPasosConfirm(code=malo),
                current_user=usuario)
        assert e.value.status_code == 400
        doc = await base.users.find_one({"user_id": "u_1"})
        assert doc.get("two_factor_enabled") is None
    corre(cuerpo())


def test_el_aviso_por_correo_sale_al_activarlo(base, monkeypatch):
    """Es la mitad de la defensa, igual que en el reinicio: quien tenga la
    sesión tomada puede activarlo con SU teléfono y dejar al dueño afuera."""
    from models.user import User
    from routes import security_2fa

    avisados = []

    async def _anotar(email, nombre):
        avisados.append((email, nombre))
    monkeypatch.setattr(security_2fa, "notify_dos_pasos_activado", _anotar)

    async def cuerpo():
        await base.users.insert_one({**CLIENTE, "is_active": True})
        usuario = User(**CLIENTE, verification_status="unverified")
        datos = await security_2fa.activar_dos_pasos_init(current_user=usuario)
        await security_2fa.activar_dos_pasos_confirm(
            _pedido_falso(),
            security_2fa.ActivarDosPasosConfirm(code=pyotp.TOTP(datos["secret"]).now()),
            current_user=usuario)
        assert avisados == [(CLIENTE["email"], CLIENTE["name"])], avisados
    corre(cuerpo())


def test_si_el_correo_falla_la_activacion_NO_queda_a_medias(base, monkeypatch):
    """Los códigos de respaldo se muestran UNA vez. Si el correo tumbara la
    respuesta, la marca quedaría encendida y esos códigos perdidos."""
    from models.user import User
    from routes import security_2fa

    async def _revienta(*a, **k):
        raise RuntimeError("el correo no anda")
    monkeypatch.setattr(security_2fa, "notify_dos_pasos_activado", _revienta)

    async def cuerpo():
        await base.users.insert_one({**CLIENTE, "is_active": True})
        usuario = User(**CLIENTE, verification_status="unverified")
        datos = await security_2fa.activar_dos_pasos_init(current_user=usuario)
        salida = await security_2fa.activar_dos_pasos_confirm(
            _pedido_falso(),
            security_2fa.ActivarDosPasosConfirm(code=pyotp.TOTP(datos["secret"]).now()),
            current_user=usuario)
        assert salida["backup_codes"], "se perdieron los códigos por un correo"
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 4. La pantalla
# ══════════════════════════════════════════════════════════════════════════

def test_la_pantalla_existe_y_pega_a_las_dos_rutas():
    import pathlib
    fuente = pathlib.Path(_BACKEND, "..", "frontend", "src", "components",
                          "DosPasosSettings.jsx").resolve().read_text(encoding="utf-8")
    assert "/auth/2fa/activar-init" in fuente
    assert "/auth/2fa/activar-confirm" in fuente
    assert 'data-testid="dos-pasos"' in fuente


def test_la_pantalla_NO_se_le_ofrece_a_quien_ya_esta_obligado():
    """Al personal se lo exige el ingreso: ofrecerle un botón de «activar»
    sería ofrecerle algo que ya hizo."""
    import pathlib
    fuente = pathlib.Path(_BACKEND, "..", "frontend", "src", "components",
                          "DosPasosSettings.jsx").resolve().read_text(encoding="utf-8")
    assert "if (estado.is_required) return null;" in fuente


def test_la_pantalla_NO_se_cierra_sola_con_los_codigos_de_respaldo():
    """Se muestran una sola vez. Cerrarla con un aviso de éxito los perdería,
    y sin ellos quien pierde el teléfono queda afuera hasta que un
    administrador lo destrabe."""
    import pathlib
    fuente = pathlib.Path(_BACKEND, "..", "frontend", "src", "components",
                          "DosPasosSettings.jsx").resolve().read_text(encoding="utf-8")
    assert 'data-testid="dos-pasos-respaldos"' in fuente
    assert "Ya los guardé" in fuente
    assert "no se muestran de nuevo" in fuente


def test_la_tarjeta_esta_enganchada_en_el_perfil():
    import pathlib
    perfil = pathlib.Path(_BACKEND, "..", "frontend", "src", "pages",
                          "Profile.jsx").resolve().read_text(encoding="utf-8")
    assert "<DosPasosSettings />" in perfil
    assert "import DosPasosSettings" in perfil
