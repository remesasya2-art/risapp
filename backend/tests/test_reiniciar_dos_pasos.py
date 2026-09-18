"""La salida para quien perdió el teléfono Y los códigos de respaldo.

QUE PASABA

    Apagar el segundo factor exige un código del teléfono. Quien lo perdió,
    y perdió también sus códigos de respaldo, no podía entrar ni podía
    apagarlo, y NADIE podía ayudarlo: no existía ninguna ruta para
    limpiárselo. Recursos Humanos lo mostraba y no lo tocaba.

    Para el personal el segundo factor es OBLIGATORIO y está en uso, así que
    ese caso no era hipotético: era cuestión de tiempo.

LO QUE SE PRUEBA

    1. Que limpie los CINCO campos. Dejar uno solo —la semilla a medias—
       significa que el alta siguiente lo reutiliza y el teléfono perdido
       sigue generando códigos válidos.
    2. Que cierre las sesiones de esa persona, y sólo las de esa persona.
    3. Que NO se pueda contra un super administrador ni contra uno mismo.
       Una ruta que le saca un factor a otra cuenta es, ella misma, una
       forma de tomar esa cuenta.
    4. Que quede en el libro de auditoría con el motivo.
    5. Que se le avise por correo al dueño de la cuenta, y que el correo no
       pueda dejar el reinicio a medias.
    6. Que después del reinicio, esa persona quede OBLIGADA a darse de alta
       de nuevo al entrar. Esto es comportamiento, no forma: sin esto, el
       reinicio dejaría a alguien del equipo con un solo factor para
       siempre.
"""
import asyncio
import os
import pathlib
import sys
from datetime import datetime, timezone

import pytest

_BACKEND = pathlib.Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))
_PANTALLA = pathlib.Path(_BACKEND, "..", "frontend", "src", "components", "admin",
                         "RecursosHumanos.jsx").resolve()

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from fastapi import HTTPException                                   # noqa: E402
from starlette.datastructures import State                          # noqa: E402
from starlette.requests import Request as PedidoReal                # noqa: E402

from conftest import usar_base                                      # noqa: E402
from models.user import User                                        # noqa: E402
from routes import recursos_humanos as rrhh                         # noqa: E402

LO_DEL_SEGUNDO_FACTOR = ("two_factor_enabled", "two_factor_secret",
                         "two_factor_secret_pending", "two_factor_backup_hashes",
                         "two_factor_enabled_at")

JEFA = User(user_id="u_jefa", email="jefa@ejemplo.com", name="Jefa",
            role="super_admin")


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_reinicio"]
    usar_base(b)
    corre(b.users.insert_one({"user_id": "u_jefa", "email": "jefa@ejemplo.com",
                              "name": "Jefa", "role": "super_admin",
                              "two_factor_enabled": True,
                              "two_factor_secret": "SEMILLADEJEFA123"}))
    yield b


@pytest.fixture(autouse=True)
def sin_correo(monkeypatch):
    """El correo se reemplaza por una lista: los tests no mandan correos, y
    así se puede comprobar QUE se avisó y a quién."""
    enviados = []

    async def _fingido(**k):
        enviados.append(k)
    monkeypatch.setattr(rrhh, "notify_dos_pasos_reiniciado", _fingido)
    return enviados


def pedido():
    return PedidoReal({
        "type": "http", "method": "POST", "path": "/", "query_string": b"",
        "headers": [(b"cf-connecting-ip", b"10.0.0.5"), (b"user-agent", b"test")],
        "client": ("10.0.0.5", 0), "state": {},
    })


async def sembrar(base, uid="u_agente", rol="agent", con_2fa=True, sesiones=2):
    doc = {"user_id": uid, "email": f"{uid}@ejemplo.com", "name": "Persona",
           "role": rol, "is_active": True}
    if con_2fa:
        doc.update({"two_factor_enabled": True, "two_factor_secret": "SEMILLA123456789",
                    "two_factor_secret_pending": "PENDIENTE1234567",
                    "two_factor_backup_hashes": ["$2b$12$uno", "$2b$12$dos"],
                    "two_factor_enabled_at": datetime.now(timezone.utc)})
    await base.users.insert_one(doc)
    for i in range(sesiones):
        await base.user_sessions.insert_one({"session_id": f"s{uid}{i}",
                                             "session_token": f"t{uid}{i}",
                                             "user_id": uid})
    return doc


def reiniciar(uid, motivo="perdió el teléfono", admin=JEFA):
    return corre(rrhh.reiniciar_dos_pasos(
        uid, rrhh.ReinicioDeDosPasos(motivo=motivo), pedido(), admin))


def levanta(fn, status):
    with pytest.raises(HTTPException) as e:
        fn()
    assert e.value.status_code == status, e.value.detail
    return e.value.detail


# ══════════════════════════════════════════════════════════════════════════
# 1 y 2. Limpia todo, y cierra las sesiones
# ══════════════════════════════════════════════════════════════════════════

def test_LIMPIA_LOS_CINCO_CAMPOS(base):
    """Dejar uno solo —la semilla a medias— significa que el alta siguiente lo
    reutiliza, y el teléfono perdido sigue generando códigos válidos."""
    corre(sembrar(base))
    reiniciar("u_agente")
    doc = corre(base.users.find_one({"user_id": "u_agente"}))
    quedaron = [c for c in LO_DEL_SEGUNDO_FACTOR if c in doc]
    assert not quedaron, f"quedó {quedaron} en la cuenta"
    # Y no se lleva puesto lo que no es suyo.
    assert doc["email"] == "u_agente@ejemplo.com" and doc["role"] == "agent"
    assert doc["is_active"] is True


def test_CIERRA_LAS_SESIONES_DE_ESA_PERSONA_Y_SOLO_ESAS(base):
    """El motivo más probable para usar esto es un teléfono perdido o robado:
    una sesión suya viva en ese teléfono es lo que no hay que dejar."""
    corre(sembrar(base, "u_agente", sesiones=3))
    corre(sembrar(base, "u_otra", sesiones=2))
    r = reiniciar("u_agente")
    assert r["sesiones_cerradas"] == 3
    assert corre(base.user_sessions.count_documents({"user_id": "u_agente"})) == 0
    assert corre(base.user_sessions.count_documents({"user_id": "u_otra"})) == 2


# ══════════════════════════════════════════════════════════════════════════
# 3. Contra quién NO
# ══════════════════════════════════════════════════════════════════════════

def test_NO_CONTRA_UN_SUPER_ADMINISTRADOR(base):
    """Es la decisión más importante de la ruta: si alcanzara, UNA sola sesión
    de super administrador tomada bajaría a todos los demás a un solo factor."""
    corre(sembrar(base, "u_otro_jefe", rol="super_admin"))
    detalle = levanta(lambda: reiniciar("u_otro_jefe"), 403)
    assert "super administrador" in detalle
    doc = corre(base.users.find_one({"user_id": "u_otro_jefe"}))
    assert doc["two_factor_enabled"] is True, "no puede haberlo tocado"
    assert corre(base.user_sessions.count_documents({"user_id": "u_otro_jefe"})) == 2
    assert corre(base.auditoria.count_documents({})) == 0


def test_NO_CONTRA_UNO_MISMO(base):
    """Quien se apaga su propio segundo factor no está recuperando un acceso,
    lo está bajando.

    Se prueba el COMPORTAMIENTO y no qué guarda lo produce: hoy lo atrapa la
    del rol, porque a esta ruta sólo llega un super administrador y su propia
    cuenta lo es. Una guarda aparte para este caso no se podía poner en rojo
    rompiéndola, así que se sacó (ver el comentario en la ruta)."""
    levanta(lambda: reiniciar("u_jefa"), 403)
    doc = corre(base.users.find_one({"user_id": "u_jefa"}))
    assert doc["two_factor_enabled"] is True


def test_UNA_CUENTA_QUE_NO_EXISTE_DA_404(base):
    levanta(lambda: reiniciar("u_fantasma"), 404)


def test_SIN_SEGUNDO_FACTOR_NO_HAY_NADA_QUE_REINICIAR(base):
    """Y no se cierran sesiones por las dudas: sería una forma silenciosa de
    echar a alguien sin dejar el motivo de verdad."""
    corre(sembrar(base, "u_agente", con_2fa=False))
    levanta(lambda: reiniciar("u_agente"), 400)
    assert corre(base.user_sessions.count_documents({"user_id": "u_agente"})) == 2


# ══════════════════════════════════════════════════════════════════════════
# 4 y 5. Queda escrito, y el dueño se entera
# ══════════════════════════════════════════════════════════════════════════

def test_QUEDA_EN_EL_LIBRO_DE_AUDITORIA_CON_EL_MOTIVO(base):
    corre(sembrar(base))
    reiniciar("u_agente", motivo="se le rompió el teléfono en el viaje")
    linea = corre(base.auditoria.find_one({}))
    assert linea["accion"] == "personal.dos_pasos_reiniciado"
    assert linea["actor"]["user_id"] == "u_jefa"
    assert linea["objetivo"]["id"] == "u_agente"
    assert linea["objetivo"]["descripcion"] == "u_agente@ejemplo.com"
    assert linea["detalle"]["motivo"] == "se le rompió el teléfono en el viaje"
    assert linea["detalle"]["sesiones_cerradas"] == 2
    assert linea["antes"] == {"dos_pasos": True}
    assert linea["despues"] == {"dos_pasos": False}
    assert linea["origen"]["ip"] == "10.0.0.5"


def test_LA_ACCION_ESTA_DECLARADA_EN_EL_CATALOGO_DEL_LIBRO():
    """Una acción sin declarar sale en el libro sin etiqueta, y el filtro por
    tipo no la encuentra nunca."""
    from services import auditoria
    assert "personal.dos_pasos_reiniciado" in auditoria.ACCIONES


def test_SE_LE_AVISA_AL_DUENO_DE_LA_CUENTA(base, sin_correo):
    """Es la mitad de la defensa: el libro lo mira alguien algún día, y el
    dueño se entera ahora."""
    corre(sembrar(base))
    reiniciar("u_agente")
    assert len(sin_correo) == 1
    aviso = sin_correo[0]
    assert aviso["email"] == "u_agente@ejemplo.com"
    assert aviso["quien"] == "jefa@ejemplo.com", "el aviso tiene que decir QUIEN"


def test_SI_EL_CORREO_FALLA_EL_REINICIO_NO_QUEDA_A_MEDIAS(base, monkeypatch):
    async def _revienta(**k):
        raise RuntimeError("Resend caído")
    monkeypatch.setattr(rrhh, "notify_dos_pasos_reiniciado", _revienta)
    corre(sembrar(base))
    r = reiniciar("u_agente")           # no levanta
    assert r["sesiones_cerradas"] == 2
    doc = corre(base.users.find_one({"user_id": "u_agente"}))
    assert "two_factor_enabled" not in doc
    assert corre(base.auditoria.count_documents({})) == 1


def test_EL_MOTIVO_NO_PUEDE_IR_VACIO():
    """Es lo único que explica meses después por qué a alguien le sacaron un
    factor."""
    import pydantic
    for malo in ("", "  ", "ab"):
        with pytest.raises(pydantic.ValidationError):
            rrhh.ReinicioDeDosPasos(motivo=malo)


# ══════════════════════════════════════════════════════════════════════════
# 6. Después del reinicio, el ingreso la obliga a darse de alta
# ══════════════════════════════════════════════════════════════════════════

def test_DESPUES_DEL_REINICIO_EL_INGRESO_OBLIGA_A_DARSE_DE_ALTA(base):
    """COMPORTAMIENTO, no forma. Sin esto, el reinicio dejaría a alguien del
    equipo con un solo factor para siempre, que es lo contrario de lo que
    esta ruta viene a hacer."""
    from services import personal
    corre(sembrar(base))
    reiniciar("u_agente")
    doc = corre(base.users.find_one({"user_id": "u_agente"}))
    # Las dos mitades de la condición que usan las puertas de ingreso.
    assert personal.exige_dos_pasos(doc) is True, "sigue siendo personal"
    assert bool(doc.get("two_factor_enabled")) is False, "y ya no lo tiene"


# ══════════════════════════════════════════════════════════════════════════
# 7. La pantalla
# ══════════════════════════════════════════════════════════════════════════

def test_LA_PANTALLA_PIDE_EL_MOTIVO_Y_PEGA_A_LA_RUTA():
    fuente = _PANTALLA.read_text(encoding="utf-8")
    assert "/reiniciar-dos-pasos`, { motivo })" in fuente
    assert "pedirTexto({" in fuente.split("reiniciarDosPasos")[1][:900], \
        "tiene que pedir el motivo antes de llamar"


def test_EL_BOTON_NO_APARECE_CONTRA_UN_SUPER_ADMINISTRADOR():
    """El servidor lo rechaza igual, pero un botón que siempre falla enseña a
    desconfiar de la pantalla."""
    fuente = _PANTALLA.read_text(encoding="utf-8")
    linea = next(l for l in fuente.splitlines() if "acceso?.dos_pasos" in l)
    assert "p.rol !== 'super_admin'" in linea
