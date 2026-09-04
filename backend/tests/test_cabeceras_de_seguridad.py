"""
tests/test_cabeceras_de_seguridad.py — Las cuatro cabeceras que van en TODA respuesta.

QUE PROTEGE

    Cuatro defensas que no cuestan nada y que se pierden en silencio:

      Strict-Transport-Security   el navegador no vuelve a hablar por HTTP con
                                  este dominio, ni siquiera si lo escriben a
                                  mano o si un enlace lo lleva ahí.
      X-Frame-Options: DENY       nadie puede meter la aplicación dentro de un
                                  iframe y superponerle su propia pantalla
                                  (clickjacking sobre el botón de confirmar).
      X-Content-Type-Options      el navegador no adivina el tipo de un archivo
                                  subido por un usuario.
      Referrer-Policy             una dirección con identificadores adentro no
                                  se filtra al sitio de destino al salir.

    El middleware que las pone son cinco líneas en `server.py`, y ahí está el
    riesgo: cinco líneas se borran en un merge y nadie se entera, porque la
    aplicación sigue funcionando igual. Un control que sólo se nota cuando ya
    fue explotado necesita una prueba.

    También se fija el origen del CORS. `allow_credentials=True` con
    `allow_origins=["*"]` es la combinación que permite que cualquier sitio
    haga peticiones con la cookie de sesión de la víctima. Acá la lista es
    blanca y explícita.
"""
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from conftest import usar_base                                      # noqa: E402,F401

ESPERADAS = {
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "x-frame-options": "DENY",
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
}


@pytest.fixture(scope="module")
def cliente():
    try:
        from fastapi.testclient import TestClient
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    return TestClient(app)


def _una_respuesta(cliente):
    """Una respuesta cualquiera sirve: el middleware corre para todas."""
    return cliente.get("/api/limits")


def _una_respuesta_de_error(cliente):
    """Un 401: sin sesión no se pasa, y la respuesta igual tiene que traer las
    cabeceras. `/ruta-que-no-existe` no sirve acá —la aplicación sirve el
    frontend y devuelve 200 para cualquier camino desconocido—."""
    return cliente.get("/api/auth/me")


def test_las_cuatro_cabeceras_salen_en_toda_respuesta(cliente):
    r = _una_respuesta(cliente)
    for nombre, valor in ESPERADAS.items():
        assert nombre in r.headers, f"falta la cabecera {nombre}"
        assert r.headers[nombre] == valor, (
            f"{nombre} vale «{r.headers[nombre]}», se esperaba «{valor}»")


def test_tambien_salen_cuando_la_respuesta_es_un_error(cliente):
    """Es el caso que se olvida: un 404 o un 500 también se renderiza en el
    navegador, y también se puede meter en un iframe."""
    r = _una_respuesta_de_error(cliente)
    assert r.status_code == 401
    for nombre, valor in ESPERADAS.items():
        assert r.headers.get(nombre) == valor, f"en un 401 falta o cambia {nombre}"


def test_el_hsts_dura_al_menos_un_ano():
    """Menos de un año y las listas de precarga de los navegadores no lo
    aceptan."""
    edad = int(ESPERADAS["strict-transport-security"].split("=")[1].split(";")[0])
    assert edad >= 31536000


def test_el_cors_no_es_comodin():
    """`allow_origins=["*"]` junto a `allow_credentials=True` deja que
    cualquier sitio haga pedidos con la cookie de sesión de la víctima."""
    try:
        from server import ALLOWED_ORIGINS
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")

    assert ALLOWED_ORIGINS, "la lista de orígenes no puede quedar vacía"
    assert "*" not in ALLOWED_ORIGINS
    for origen in ALLOWED_ORIGINS:
        assert origen.startswith("https://"), (
            f"«{origen}» no es https: una cookie de sesión no viaja a un origen en claro")


def test_un_origen_ajeno_no_recibe_permiso(cliente):
    r = cliente.get("/api/limits",
                    headers={"Origin": "https://sitio-de-un-atacante.example"})
    permitido = r.headers.get("access-control-allow-origin")
    assert permitido != "https://sitio-de-un-atacante.example"
    assert permitido != "*"
