"""
tests/test_el_rastro_del_pedido.py — Unir un error con su línea del registro.

EL PROBLEMA, EN UNA ESCENA

    Alguien escribe a soporte: «me dio error al recargar, como a las tres». Del
    otro lado hay un registro con miles de líneas por minuto y ninguna forma de
    saber cuál es la suya. Se termina adivinando por la hora.

    Con un rastro, esa conversación es: «pasame el código que te mostró».

LO QUE SE VIGILA, POR ORDEN DE DAÑO

    1. Que un rastro que viene de AFUERA no pueda fabricar líneas de registro.
       Esa cabecera la escribe quien hace el pedido y termina en cada línea:
       sin limpiarla, un salto de línea la parte en dos y la segunda mitad se
       lee como una línea más, con la forma que quiera quien la mandó.
    2. Que un error no previsto NO le devuelva al usuario el texto de la
       excepción, que nombra tablas y rutas — pero sí el rastro, que es lo
       único que le sirve a soporte.
    3. Que el rastro aparezca en las líneas escritas ADENTRO del handler, que
       es lo único que hace que todo esto sirva para algo.
"""
import logging
import os
import re
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base                              # noqa: E402
from services import rastro                                 # noqa: E402


@pytest.fixture(scope="module")
def cliente():
    usar_base(mongomock_motor.AsyncMongoMockClient()["ris_test_rastro"])
    from fastapi.testclient import TestClient
    import server
    return TestClient(server.app, raise_server_exceptions=False)


# ══════════════════════════════════════════════════════════════════════════
# 1. Lo que viene de afuera se limpia
# ══════════════════════════════════════════════════════════════════════════

def test_UN_SALTO_DE_LINEA_NO_FABRICA_LINEAS_DE_REGISTRO(cliente):
    """EL TEST QUE IMPORTA. El rastro va en TODAS las líneas del pedido, y lo
    escribe quien llama. Sin limpiarlo es una máquina de escribir en nuestro
    registro con la forma que quiera."""
    r = cliente.get("/api/health",
                    headers={"X-Request-ID": "x\nERROR:banco:transferencia aprobada"})
    devuelto = r.headers.get("x-request-id")
    assert "\n" not in devuelto
    assert "ERROR" not in devuelto


@pytest.mark.parametrize("veneno", [
    "a" * 65,                       # más largo que el tope
    "con espacios",
    "coma,punto:y;otros",
    "",
    "√±emojis🙂",
])
def test_CUALQUIER_COSA_RARA_SE_DESCARTA(veneno):
    """Se prueba la limpieza sola: por la cabecera HTTP no entra todo lo que
    puede llegar por otros caminos."""
    limpio = rastro.limpiar(veneno)
    assert re.match(r"^[A-Za-z0-9._-]{1,64}$", limpio), limpio
    assert limpio != veneno


def test_UNO_LIMPIO_SE_RESPETA(cliente):
    """Así el rastro cruza desde el sistema de quien llama y se puede seguir de
    punta a punta. Es la mitad del valor de esto."""
    r = cliente.get("/api/health", headers={"X-Request-ID": "sistema-del-socio-42"})
    assert r.headers.get("x-request-id") == "sistema-del-socio-42"


# ══════════════════════════════════════════════════════════════════════════
# 2. Cada pedido tiene el suyo, y sale en la respuesta
# ══════════════════════════════════════════════════════════════════════════

def test_TODA_RESPUESTA_TRAE_SU_RASTRO(cliente):
    r = cliente.get("/api/health")
    assert r.headers.get("x-request-id")


def test_DOS_PEDIDOS_NO_COMPARTEN_RASTRO(cliente):
    """Si lo compartieran, el rastro no serviría para encontrar UNO."""
    a = cliente.get("/api/health").headers.get("x-request-id")
    b = cliente.get("/api/health").headers.get("x-request-id")
    assert a != b


def test_EL_RASTRO_APARECE_EN_LAS_LINEAS_DEL_HANDLER(cliente, caplog):
    """LO QUE HACE QUE TODO ESTO SIRVA. Un `logger.info` escrito hace dos años,
    adentro de un servicio que no sabe que este módulo existe, sale con su
    rastro igual — porque el rastro viaja en la tarea, no en un parámetro."""
    with caplog.at_level(logging.WARNING):
        cliente.post("/api/csp-reporte",
                     headers={"X-Request-ID": "rastro-de-prueba"},
                     json={"csp-report": {"effective-directive": "script-src",
                                          "blocked-uri": "https://x.test/y.js"}})
    del caplog
    # `caplog` no pasa por los manejadores de la raíz, así que el formato no se
    # ve ahí. Se comprueba sobre el filtro, que es lo que pone el valor.
    assert rastro.FORMATO.count("%(rastro)s") == 1


# ══════════════════════════════════════════════════════════════════════════
# 3. El error no previsto
# ══════════════════════════════════════════════════════════════════════════

def test_UN_ERROR_NO_PREVISTO_DEVUELVE_EL_RASTRO_Y_NO_LAS_TRIPAS(cliente):
    """El texto de una excepción nombra tablas, rutas y a veces cadenas de
    conexión. No es para el cliente. El rastro sí."""
    import server

    secreto = "mongodb://usuario:clave@interno:27017/ris"

    async def revienta():
        raise RuntimeError(f"no se pudo conectar a {secreto}")

    # Va al PRINCIPIO de la lista: la aplicación tiene un comodín
    # `/{full_path:path}` que sirve el frontend, y agregada al final se la come
    # ese comodín y contesta 404. Es la misma trampa de orden que ya mordió dos
    # veces a este repositorio (`tests/test_rutas_alcanzables.py`).
    server.app.add_api_route("/api/__prueba_de_error__", revienta, methods=["GET"])
    server.app.router.routes.insert(0, server.app.router.routes.pop())
    try:
        r = cliente.get("/api/__prueba_de_error__")
    finally:
        server.app.router.routes = [
            x for x in server.app.router.routes
            if getattr(x, "path", "") != "/api/__prueba_de_error__"]

    assert r.status_code == 500
    cuerpo = r.text
    assert secreto not in cuerpo, "el cuerpo del error filtra datos internos"
    assert "RuntimeError" not in cuerpo
    assert r.json().get("request_id"), "no vino el rastro para darle a soporte"
    assert r.json()["request_id"] in r.json()["detail"], (
        "el rastro tiene que estar en el mensaje: el usuario no lee cabeceras")


# ══════════════════════════════════════════════════════════════════════════
# 4. Lo demás de esta tanda
# ══════════════════════════════════════════════════════════════════════════

def test_LA_PUERTA_DE_DESCARGA_YA_NO_EXISTE(cliente):
    """Era pública y sin autenticar, y servía un archivo a cualquiera. Su
    inocencia dependía de que ese archivo NO existiera."""
    assert cliente.get("/api/download-build").status_code == 404


def test_NO_QUEDA_NINGUN_EXCEPT_PELADO():
    """`except:` atrapa hasta un Ctrl-C y un KeyboardInterrupt. Nunca es lo que
    alguien quiso escribir."""
    import pathlib

    culpables = []
    for archivo in sorted(pathlib.Path(_BACKEND).rglob("*.py")):
        if "tests" in archivo.parts or "__pycache__" in archivo.parts:
            continue
        for n, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*except\s*:\s*(#.*)?$", linea):
                culpables.append(f"{archivo.relative_to(_BACKEND)}:{n}")
    assert not culpables, f"except pelados: {culpables}"


def test_EL_REGISTRO_NO_ESCRIBE_EL_CORREO_DE_QUIEN_SE_REGISTRA():
    """El registro lo lee más gente de la que tiene por qué saber quién se
    está registrando, y queda escrito en un servicio de terceros."""
    fuente = open(os.path.join(_BACKEND, "routes", "auth.py"),
                  encoding="utf-8").read()
    culpables = [l.strip() for l in fuente.splitlines()
                 if "logger." in l and "email_lower" in l]
    assert not culpables, f"el correo va al registro: {culpables}"
