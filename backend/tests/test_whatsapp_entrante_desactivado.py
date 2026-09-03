"""
El receptor de WhatsApp no puede tocar plata: ahora no tiene con qué.

HISTORIA
    Un número de WhatsApp autorizado cerraba órdenes sin pasar por el Panel:
    «listo» las completaba, «cancelar» las cancelaba y reembolsaba —siempre a
    `balance_ris`, aunque el envío se hubiera pagado en USDT o USDC—. La Fase 1
    puso un `if` delante y dejó el código detrás. Esta es la Fase 2: el código
    se fue.

QUE PRUEBA ESTE ARCHIVO, Y POR QUE ASI
    Con el flujo apagado detrás de una bandera, lo único que se podía exigir era
    «no escribe». Con el flujo BORRADO se puede exigir algo mucho más fuerte y
    mucho más difícil de romper sin querer:

        `routes/webhooks.py` no importa la base de datos. Ni arriba, ni dentro
        de una función, ni por un camino perezoso.

    Se comprueba de dos maneras que se tapan los agujeros la una a la otra:

      1. Sobre el AST. Recorre TODOS los `import` del archivo —incluidos los que
         estén metidos dentro de una función, que es exactamente donde alguien
         los volvería a colar— y exige que la lista de módulos importados esté
         dentro de un conjunto chico y declarado. Se mira el árbol y no el
         texto, así que ni el docstring ni los comentarios (que sí nombran «db»
         y «listo», porque cuentan la historia) pueden hacer pasar o fallar el
         test por error.

      2. Cargando el módulo de verdad, en un subproceso limpio, con `MONGO_URL`
         sin definir y con un `database` envenenado que revienta si alguien lo
         importa. Si el módulo carga y la ruta queda registrada, es que no lo
         necesita.

    Y encima quedan los tests de comportamiento: los comandos de antes entran
    firmados con la HMAC real de Twilio y desde el número autorizado —el peor
    caso, no un mensaje que igual iba a ser rechazado— y no producen nada.
"""
import ast
import asyncio
import importlib.util
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from twilio.request_validator import RequestValidator

BACKEND = Path(__file__).resolve().parent.parent
FUENTE = BACKEND / "routes" / "webhooks.py"

AUTH_TOKEN = "test-twilio-auth-token"
ADMIN_NUMBER = "whatsapp:+584140000000"
PUBLIC_HOST = "www.risappbr.com"
WEBHOOK_PATH = "/api/webhooks/twilio/whatsapp"

# Lo único que este receptor tiene permitido necesitar. La lista es corta a
# propósito: cada nombre que se agregue acá tiene que justificarse en la
# revisión, que es justo lo que se quiere que pase.
IMPORTS_PERMITIDOS = {"logging", "os", "fastapi", "twilio.request_validator"}


def _cargar_modulo_aislado():
    """Carga `routes/webhooks.py` SIN pasar por el paquete `routes`.

    `routes/__init__.py` arrastra el motor contable y con él la base de datos.
    Importándolo por archivo se prueba el módulo solo, que es de lo que trata
    este archivo, y de paso el test deja de depender de que el paquete entero
    sea importable.
    """
    spec = importlib.util.spec_from_file_location("webhooks_aislado", FUENTE)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


wh = _cargar_modulo_aislado()


# --------------------------------------------------------------------------
# 1. El módulo no importa la base de datos: sobre el AST, no sobre el texto
# --------------------------------------------------------------------------

def _modulos_importados(arbol):
    """Todo lo que el archivo importa, esté donde esté el `import`."""
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                nombres.add(alias.name)
        elif isinstance(nodo, ast.ImportFrom):
            # `level > 0` es un import relativo (`from .algo import x`): dentro
            # del paquete `routes`, y por lo tanto capaz de arrastrar la base.
            nombres.add(("." * nodo.level) + (nodo.module or ""))
    return nombres


@pytest.fixture(scope="module")
def arbol():
    return ast.parse(FUENTE.read_text(encoding="utf-8"))


def test_el_webhook_no_importa_nada_fuera_de_la_lista(arbol):
    """La guarda central: si vuelve a entrar la base, este test lo grita."""
    de_mas = _modulos_importados(arbol) - IMPORTS_PERMITIDOS
    assert de_mas == set(), (
        "routes/webhooks.py importa módulos que un receptor desactivado no "
        f"debería necesitar: {sorted(de_mas)}. Si de verdad hace falta, "
        "agregalo a IMPORTS_PERMITIDOS en este test y explicá por qué."
    )


def test_no_hay_imports_escondidos_dentro_de_funciones(arbol):
    """Un `from database import db` adentro de la ruta esquiva la lectura rápida."""
    adentro = [
        nodo
        for funcion in ast.walk(arbol)
        if isinstance(funcion, (ast.FunctionDef, ast.AsyncFunctionDef))
        for nodo in ast.walk(funcion)
        if isinstance(nodo, (ast.Import, ast.ImportFrom))
    ]
    assert adentro == [], (
        "hay imports dentro de funciones en routes/webhooks.py "
        f"(líneas {[n.lineno for n in adentro]})"
    )


def test_la_lista_de_permitidos_no_esconde_la_base():
    """Que no se cuele el módulo de la base disfrazado de permitido."""
    for nombre in IMPORTS_PERMITIDOS:
        raiz = nombre.split(".")[0]
        assert raiz not in {"database", "services", "models", "motor", "pymongo"}, (
            f"IMPORTS_PERMITIDOS contiene {nombre!r}: eso es justo lo que este "
            "archivo tiene que impedir"
        )


def test_el_modulo_carga_sin_base_de_datos_en_un_proceso_limpio():
    """La prueba de verdad: se importa con `database` envenenado y sin MONGO_URL.

    El AST dice qué está escrito; esto dice qué pasa al ejecutarlo. Si el módulo
    tocara la base por cualquier camino, el import de abajo reventaría.
    """
    guion = textwrap.dedent(
        f"""
        import sys, types, importlib.util

        # Cualquiera que haga `import database` se lleva una explosión.
        trampa = types.ModuleType("database")
        class _Bomba:
            def __getattr__(self, nombre):
                raise AssertionError(
                    "routes/webhooks.py tocó la base de datos: database." + nombre
                )
        trampa.__getattr__ = _Bomba().__getattr__
        sys.modules["database"] = trampa

        spec = importlib.util.spec_from_file_location("w", {str(FUENTE)!r})
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)

        assert modulo.WHATSAPP_INBOUND_DISABLED is True
        rutas = [r.path for r in modulo.router.routes]
        assert rutas == ["/webhooks/twilio/whatsapp"], rutas
        print("OK")
        """
    )
    entorno = {k: v for k, v in os.environ.items() if k != "MONGO_URL"}
    entorno["PYTHONPATH"] = str(BACKEND)
    proceso = subprocess.run(
        [sys.executable, "-c", guion],
        capture_output=True, text=True, cwd=str(BACKEND), env=entorno,
    )
    assert proceso.returncode == 0, (
        f"el módulo no carga sin base de datos:\n{proceso.stderr}"
    )
    assert "OK" in proceso.stdout


# --------------------------------------------------------------------------
# 2. Comportamiento: el peor caso entra firmado y no pasa nada
# --------------------------------------------------------------------------

class FakeURL:
    def __init__(self, path):
        self.scheme = "https"
        self.path = path
        self.query = ""


class FakeRequest:
    def __init__(self, params, signature):
        self._params = params
        self.url = FakeURL(WEBHOOK_PATH)
        self.headers = {
            "X-Twilio-Signature": signature,
            "x-forwarded-proto": "https",
            "x-forwarded-host": PUBLIC_HOST,
            "host": PUBLIC_HOST,
        }

    async def form(self):
        return self._params


def _firmado(params):
    """Firma el payload igual que lo haría Twilio contra la URL pública."""
    url = f"https://{PUBLIC_HOST}{WEBHOOK_PATH}"
    firma = RequestValidator(AUTH_TOKEN).compute_signature(url, params)
    return FakeRequest(params, firma)


@pytest.fixture
def configurado(monkeypatch):
    monkeypatch.setattr(wh, "TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    monkeypatch.setattr(wh, "ADMIN_WHATSAPP_NUMBER", ADMIN_NUMBER)


def _post(body="", num_media=0, desde=ADMIN_NUMBER, **extra):
    params = {
        "From": desde,
        "To": "whatsapp:+14155238886",
        "Body": body,
        "NumMedia": str(num_media),
        "MessageSid": "SM00000000000000000000000000000000",
    }
    params.update(extra)
    return asyncio.run(wh.twilio_whatsapp_webhook(_firmado(params)))


def _descartado(res):
    """Lo que tiene que contestar: 200 con un cuerpo vacío, sin TwiML."""
    assert res.status_code == 200
    assert res.body == b"", f"el webhook contestó algo: {res.body!r}"


@pytest.mark.parametrize("comando", [
    "listo", "lista", "hecho", "completado", "ok", "done",   # cerraban la orden
    "cancelar", "cancel", "rechazar",                        # cancelaban y reembolsaban
    "info", "  LISTO  ", "cualquier otra cosa",
])
def test_ningun_comando_de_antes_produce_nada(configurado, comando):
    _descartado(_post(body=comando))


def test_una_imagen_tampoco_se_descarga(configurado):
    """Las imágenes ya no se bajan de Twilio ni se acumulan en ninguna orden."""
    _descartado(_post(
        num_media=1,
        MediaUrl0="https://api.twilio.com/2010-04-01/Accounts/AC0/Messages/MM0/Media/ME0",
        MediaContentType0="image/jpeg",
    ))


def test_firma_invalida_sigue_siendo_403(configurado):
    """Apagar el flujo no aflojó la validación: lo no firmado se rechaza igual."""
    req = FakeRequest({"From": ADMIN_NUMBER, "Body": "listo", "NumMedia": "0"}, "firma-falsa")
    res = asyncio.run(wh.twilio_whatsapp_webhook(req))
    assert res.status_code == 403


def test_sin_token_no_se_contesta_200(configurado, monkeypatch):
    """Sin token no se puede saber quién llama: se dice que no está configurado."""
    monkeypatch.setattr(wh, "TWILIO_AUTH_TOKEN", "")
    req = FakeRequest({"From": ADMIN_NUMBER, "Body": "listo", "NumMedia": "0"}, "x")
    res = asyncio.run(wh.twilio_whatsapp_webhook(req))
    assert res.status_code == 503


def test_un_numero_ajeno_se_descarta(configurado):
    """Firma válida pero otro número: se descarta igual, y se registra."""
    _descartado(_post(body="listo", desde="whatsapp:+000000000000"))


def test_la_bandera_de_corte_esta_puesta():
    """Guarda explícita: si alguien la apaga sin querer, este test lo grita."""
    assert wh.WHATSAPP_INBOUND_DISABLED is True
