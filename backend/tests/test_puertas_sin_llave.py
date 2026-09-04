"""
tests/test_puertas_sin_llave.py — Las rutas que cualquiera puede golpear.

DE QUE SE TRATA

    De las 337 rutas de la aplicación, la enorme mayoría exige sesión. Las que
    no —el ingreso, el registro, el reseteo, el seguimiento público, los
    webhooks— son las únicas que alguien sin cuenta puede llamar, y por eso son
    las únicas que se pueden llamar un millón de veces.

    Ahí un tope por IP no es un detalle de rendimiento: es lo que convierte
    «probar el código de seis dígitos» de una tarea de segundos en una
    imposible, y lo que impide que un pedido barato de mandar y caro de atender
    —cualquiera que corra bcrypt, o que mande un correo— ocupe el servidor.

POR QUE ESTE TEST NO ENUMERA LAS RUTAS QUE FALTAN

    Una lista de «estas cinco necesitan tope» se arregla una vez y no dice nada
    de la sexta. Este test hace lo contrario: recorre TODAS las rutas sin
    sesión, y exige que cada una tenga tope o esté declarada abajo, con el
    motivo escrito.

    Agregar una ruta pública sin tope pone esto en rojo, y para pasarlo hay que
    escribir por qué no lleva. Esa frase es el control.
"""
import inspect
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from conftest import usar_base                                      # noqa: E402,F401


# ══════════════════════════════════════════════════════════════════════════
# Las que NO llevan tope, y por qué
# ══════════════════════════════════════════════════════════════════════════
#
# Cada línea es una decisión, no una excepción administrativa. Si mañana una de
# estas empieza a hacer trabajo caro, la razón de acá deja de valer y hay que
# ponerle tope.

SIN_TOPE_A_PROPOSITO = {
    # ── Lecturas fijas: contestan lo mismo para todo el mundo, no tocan la
    #    sesión de nadie y no cuestan nada. Un tope acá sólo rompería a un
    #    usuario detrás de una IP compartida.
    ("GET", "/api/"): "el ping de vida",
    ("GET", "/api/health"): "el ping de vida",
    ("GET", "/api/rate"): "la tasa del día, igual para todos",
    ("GET", "/api/limits"): "los límites publicados",
    ("GET", "/api/policies"): "las políticas publicadas",
    ("GET", "/api/ves-payment-info"): "los datos de pago publicados",
    ("GET", "/api/btc/precio"): "el precio publicado",
    ("GET", "/api/push/web/vapid-public-key"): "una clave pública",
    ("GET", "/api/download-build"): "un archivo estático",
    ("GET", "/{full_path:path}"): "el frontend, no es una API",

    # ── Webhooks. El tope se mide por IP, y un webhook llega SIEMPRE desde las
    #    mismas pocas IPs del proveedor: un pico legítimo de pagos se cortaría
    #    solo, y lo que se pierde es la confirmación de que alguien ya pagó.
    #    Lo que protege a un webhook es la firma, no el tope — y eso se prueba
    #    en el archivo de cada uno, no acá.
    ("POST", "/api/webhook/mercadopago"): "webhook: lo protege la firma",
    ("POST", "/api/webhooks/twilio/whatsapp"): "webhook: lo protege la firma",
    ("POST", "/api/btc/webhook/blink"): "webhook: lo protege la firma",
    ("POST", "/api/credits/webhook"): "webhook: lo protege la firma",
    ("POST", "/api/crypto-send/webhook"): "webhook: lo protege la firma",

    # ── El puente con adminbrl y el centro de gestión. No usan sesión: entran
    #    con una clave compartida en una cabecera, y esa clave es lo que los
    #    protege. Que la clave se exija SIEMPRE lo prueba
    #    `test_puente_con_llave.py`; un tope por IP acá cortaría a la aplicación
    #    externa, que llama desde una sola dirección.
    ("GET", "/api/adminbrl/btc/pending"): "entra con clave, no con sesión",
    ("POST", "/api/adminbrl/btc/process"): "entra con clave, no con sesión",
    ("POST", "/api/adminbrl/rates/sync"): "entra con clave, no con sesión",
    ("GET", "/api/adminbrl/withdrawals/pending"): "entra con clave, no con sesión",
    ("POST", "/api/adminbrl/withdrawals/process"): "entra con clave, no con sesión",
    ("GET", "/api/centro-gestion/health"): "entra con clave, no con sesión",
    ("GET", "/api/centro-gestion/log"): "entra con clave, no con sesión",
    ("GET", "/api/centro-gestion/log/{transaction_id}"): "entra con clave, no con sesión",
    ("GET", "/api/centro-gestion/stats"): "entra con clave, no con sesión",

    # ── Enrolamiento del segundo factor. El `pending_token` se CONSUME al
    #    entrar (`_consume_pending_token` marca `consumed` en el mismo
    #    `find_one_and_update`), así que cada token da un solo intento. Repetir
    #    no sirve de nada: no hay nada que adivinar dos veces.
    ("POST", "/api/auth/2fa/enroll-init"): "el token se consume: un solo intento",
    ("POST", "/api/auth/2fa/enroll-confirm"): "el token se consume: un solo intento",

    # ── Los límites de envío, publicados y sin datos de nadie.
    ("GET", "/api/envios/limites"): "los límites publicados",
}


def _rutas_sin_sesion():
    """Cada ruta que no exige sesión, con si tiene tope o no."""
    try:
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")

    def _pide_sesion(dependiente):
        for sub in dependiente.dependencies:
            llamada = getattr(sub, "call", None)
            nombre = getattr(llamada, "__name__", "")
            if any(p in nombre for p in ("current_user", "verified", "admin",
                                         "gestor", "crm", "operador", "personal")):
                return True
            if _pide_sesion(sub):
                return True
        return False

    for r in app.routes:
        dependiente = getattr(r, "dependant", None)
        if dependiente is None or _pide_sesion(dependiente):
            continue
        metodos = sorted((r.methods or set()) - {"HEAD", "OPTIONS"})
        if not metodos:
            continue
        try:
            fuente = inspect.getsource(r.endpoint)
        except Exception:                                 # pragma: no cover
            fuente = ""
        tiene_tope = "frenar(" in fuente or "limiter.limit" in fuente
        for metodo in metodos:
            yield metodo, r.path, tiene_tope


def test_TODA_RUTA_PUBLICA_TIENE_TOPE_O_UNA_RAZON_ESCRITA():
    """El test que importa. Una ruta pública nueva sin tope lo pone en rojo, y
    la única forma de pasarlo es declararla arriba con el motivo."""
    huerfanas = []
    for metodo, path, tiene_tope in _rutas_sin_sesion():
        if tiene_tope:
            continue
        if (metodo, path) in SIN_TOPE_A_PROPOSITO:
            continue
        huerfanas.append(f"{metodo:5s} {path}")

    assert not huerfanas, (
        "una ruta que cualquiera puede llamar no tiene tope de intentos.\n"
        "Poné `frenar(request, \"<alcance>\", \"<regla>\")` o declarala en "
        "SIN_TOPE_A_PROPOSITO con el motivo:\n  " + "\n  ".join(sorted(huerfanas)))


def test_LA_LISTA_DE_EXCEPCIONES_NO_JUNTA_POLVO():
    """Una excepción para una ruta que ya no existe es una que nadie volvió a
    mirar. Y peor: si mañana vuelve una ruta con ese mismo camino, entra ya
    exceptuada sin que nadie lo haya decidido."""
    vivas = {(m, p) for m, p, _ in _rutas_sin_sesion()}
    muertas = [f"{m} {p}" for (m, p) in SIN_TOPE_A_PROPOSITO if (m, p) not in vivas]
    assert not muertas, (
        "hay excepciones declaradas para rutas que ya no existen:\n  "
        + "\n  ".join(sorted(muertas)))


def test_una_excepcion_sin_motivo_no_vale():
    for clave, motivo in SIN_TOPE_A_PROPOSITO.items():
        assert motivo and len(motivo) > 8, f"{clave}: el motivo no dice nada"


# ══════════════════════════════════════════════════════════════════════════
# Los topes que se acaban de poner, uno por uno
# ══════════════════════════════════════════════════════════════════════════

# El alcance separa los contadores: sin él, gastar el cupo de «olvidé mi
# contraseña» dejaría a esa IP sin poder registrarse.
TOPES_ESPERADOS = [
    ("routes/auth.py", "auth.register", "el registro crea cuentas y manda correos"),
    ("routes/auth.py", "auth.verify_email", "el código de seis dígitos del correo"),
    ("routes/auth.py", "auth.reset_password", "cada llamada corre bcrypt"),
    ("routes/recovery.py", "recovery.verify_code", "el código de recuperación"),
    ("routes/recovery.py", "recovery.reset_password", "cada llamada hashea"),
    ("routes/recovery.py", "recovery.support_contact", "manda un mensaje a soporte"),
    ("routes/webauthn_login.py", "webauthn.login_options", "distingue si la cuenta existe"),
    ("routes/webauthn_login.py", "webauthn.login_verify", "la otra puerta del ingreso"),
    ("routes/envios.py", "envios.seguimiento", "adivinar un token de seguimiento"),
]


@pytest.mark.parametrize("archivo, alcance, para_que", TOPES_ESPERADOS)
def test_el_tope_sigue_puesto(archivo, alcance, para_que):
    fuente = open(os.path.join(_BACKEND, archivo), encoding="utf-8").read()
    assert f'"{alcance}"' in fuente, f"se cayó el tope de {alcance} ({para_que})"


def test_CADA_TOPE_CUENTA_APARTE():
    """Dos rutas con el mismo alcance comparten contador: gastar el cupo de una
    deja a esa IP sin la otra. Se ve como «la aplicación anda mal», no como
    «llegaste al límite»."""
    import re
    alcances = {}
    rutas = os.path.join(_BACKEND, "routes")
    for archivo in sorted(os.listdir(rutas)):
        if not archivo.endswith(".py"):
            continue
        texto = open(os.path.join(rutas, archivo), encoding="utf-8").read()
        for m in re.finditer(r'frenar\(\s*\w+\s*,\s*"([^"]+)"', texto):
            alcances.setdefault(m.group(1), []).append(archivo)

    repetidos = {a: d for a, d in alcances.items() if len(d) > 1}
    assert not repetidos, f"alcances compartidos entre rutas distintas: {repetidos}"


def test_ninguna_regla_es_tan_alta_que_no_frene_nada():
    """Un tope de 100000/hora existe, pasa cualquier grep, y no frena a nadie."""
    import re
    rutas = os.path.join(_BACKEND, "routes")
    flojas = []
    por_hora = {"second": 3600, "minute": 60, "minutes": 60, "hour": 1, "hours": 1,
                "day": 1 / 24, "15minutes": 4}
    for archivo in sorted(os.listdir(rutas)):
        if not archivo.endswith(".py"):
            continue
        texto = open(os.path.join(rutas, archivo), encoding="utf-8").read()
        for m in re.finditer(r'frenar\([^)]*"(\d+)/(\w+)"\s*\)', texto):
            cantidad, unidad = int(m.group(1)), m.group(2)
            factor = por_hora.get(unidad)
            if factor is None:
                continue
            if cantidad * factor > 1000:
                flojas.append(f"{archivo}: {m.group(1)}/{m.group(2)}")
    assert not flojas, f"topes que no frenan nada: {flojas}"
