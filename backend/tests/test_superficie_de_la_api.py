"""
tests/test_superficie_de_la_api.py — Lo que la aplicación muestra sin que le pidan.

DOS COSAS QUE NO SE VEN AL USAR LA APLICACION

    1. LA DOCUMENTACION AUTOMATICA. FastAPI publica `/docs`, `/redoc` y
       `/openapi.json` sin pedir nada. Eso es el mapa completo de la API: las
       341 rutas con sus parámetros y sus tipos, incluidas las de
       administración, las del puente con adminbrl y las de mantenimiento.

       Ninguna deja de estar protegida por eso. Pero saber que
       `/api/admin/fix-media-urls` existe y qué recibe es la mitad del trabajo
       de quien está buscando por dónde entrar, y no hay una sola razón para
       regalarlo.

    2. EL TAMAÑO DEL CUERPO. Nada limitaba cuánto se podía mandar. Un pedido con
       un cuerpo de varios gigabytes se leía entero en memoria antes de que
       ninguna ruta lo mirara. No hace falta ninguna credencial: la validación
       de la ruta corre DESPUES de que el cuerpo ya se armó.

    Las dos son configuración, no lógica. Se pierden en un merge sin que nada
    deje de funcionar, que es exactamente por qué necesitan un test.
"""
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from conftest import usar_base                                      # noqa: E402,F401


@pytest.fixture(scope="module")
def cliente():
    try:
        from fastapi.testclient import TestClient
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    return TestClient(app)


# ══════════════════════════════════════════════════════════════════════════
# 1. La documentación no se publica
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ruta", ["/docs", "/redoc", "/openapi.json"])
def test_EL_MAPA_DE_LA_API_NO_SE_PUBLICA(cliente, ruta):
    """No se pide un 404 exacto: la aplicación sirve el frontend en `/{path}`,
    así que una ruta que no existe devuelve el index.html del SPA. Lo que se
    exige es que NO vuelva la documentación."""
    r = cliente.get(ruta)
    cuerpo = r.text.lower()
    assert "swagger" not in cuerpo, f"{ruta} devolvió la documentación"
    assert "redoc" not in cuerpo, f"{ruta} devolvió la documentación"
    assert '"openapi"' not in cuerpo, f"{ruta} devolvió el esquema OpenAPI"


def test_la_app_se_arma_sin_las_rutas_de_documentacion():
    """Directo sobre el objeto: `docs_url=None` es lo que las saca del router."""
    from server import app
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_SE_PUEDEN_PRENDER_EN_DESARROLLO_pero_apagadas_por_defecto():
    """El valor por defecto tiene que ser el seguro: lo que alguien se olvida
    de configurar no puede ser lo que abre la puerta."""
    fuente = open(os.path.join(_BACKEND, "server.py"), encoding="utf-8").read()
    assert "EXPONER_DOCUMENTACION_API" in fuente
    # La variable se lee con un default vacío: sin ella puesta, apagado.
    assert 'os.getenv("EXPONER_DOCUMENTACION_API", "")' in fuente


# ══════════════════════════════════════════════════════════════════════════
# 2. El tope del cuerpo
# ══════════════════════════════════════════════════════════════════════════

from services.limite_de_cuerpo import LimiteDeCuerpo                # noqa: E402


def _app_de_prueba(tope):
    """Una app mínima con el tope puesto, para no depender de qué rutas existan."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    chica = FastAPI()

    @chica.post("/eco")
    async def eco(cuerpo: dict):
        return {"largo": len(str(cuerpo))}

    chica.add_middleware(LimiteDeCuerpo, tope=tope)
    return TestClient(chica)


def test_UN_CUERPO_QUE_PASA_EL_TOPE_SE_RECHAZA():
    c = _app_de_prueba(tope=1024)
    r = c.post("/eco", json={"x": "y" * 5000})
    assert r.status_code == 413


def test_un_cuerpo_normal_pasa():
    c = _app_de_prueba(tope=1024)
    r = c.post("/eco", json={"x": "y" * 10})
    assert r.status_code == 200


def test_EL_QUE_MIENTE_EN_CONTENT_LENGTH_TAMBIEN_SE_CORTA():
    """`Content-Length` lo manda el cliente. Rechazar sólo por lo declarado deja
    pasar al que declara chico y manda grande, que es el caso que importa."""
    c = _app_de_prueba(tope=1024)
    grande = b'{"x":"' + b"y" * 5000 + b'"}'
    r = c.post("/eco", content=grande,
               headers={"content-type": "application/json",
                        "content-length": "20"})
    # El cliente HTTP puede reescribir el content-length; lo que se comprueba es
    # que de ninguna manera se devuelva un 200 con el cuerpo entero procesado.
    assert r.status_code != 200


def test_el_que_declara_de_mas_se_corta_SIN_LEER_NADA():
    """Cuando el `Content-Length` ya dice que no entra, no hace falta leer un
    solo byte. Es la mitad barata de la defensa."""
    leidos = []

    class _Espia(LimiteDeCuerpo):
        async def __call__(self, scope, receive, send):
            async def anotando():
                mensaje = await receive()
                leidos.append(len(mensaje.get("body", b"") or b""))
                return mensaje
            await super().__call__(scope, anotando, send)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    chica = FastAPI()

    @chica.post("/eco")
    async def eco(cuerpo: dict):
        return {"ok": True}

    chica.add_middleware(_Espia, tope=64)
    r = TestClient(chica).post("/eco", json={"x": "y" * 5000})
    assert r.status_code == 413
    assert sum(leidos) == 0, "leyó el cuerpo aunque el Content-Length ya no entraba"


def test_el_tope_por_defecto_alcanza_para_el_kyc():
    """El pedido más grande de la aplicación son las cuatro fotos del KYC, hasta
    8 MB cada una. Un tope que las corta rompe la verificación de identidad, que
    es peor que no tener tope."""
    from services.imagen_recibida import TOPE_BYTES as TOPE_IMAGEN
    from services.limite_de_cuerpo import _tope
    assert _tope() >= 4 * TOPE_IMAGEN


@pytest.mark.parametrize("valor", ["0", "-5", "abc", ""])
def test_una_variable_de_entorno_absurda_no_saca_el_tope(valor, monkeypatch):
    from services.limite_de_cuerpo import _tope
    monkeypatch.setenv("TOPE_CUERPO_MB", valor)
    assert _tope() >= 1024 * 1024


def test_EL_TOPE_ES_EL_PRIMERO_QUE_VE_EL_PEDIDO():
    """No se mira el orden en el que está escrito en `server.py`, porque ese
    orden ENGAÑA: Starlette inserta cada middleware al principio de la lista, o
    sea que el último registrado queda por fuera y corre primero. Escribirlo
    arriba del archivo —que es lo que parece «primero»— lo deja pegado a la
    ruta, con CORS y el limitador trabajando sobre el pedido gigante antes de
    que nadie lo corte.

    Así que se mira la cadena ya armada: el tope tiene que estar más afuera que
    el CORS y que el limitador.
    """
    from server import app
    clases = [m.cls.__name__ for m in app.user_middleware]
    assert "LimiteDeCuerpo" in clases, "el tope no está registrado"
    donde = clases.index("LimiteDeCuerpo")
    # El primero de la lista es el más externo.
    for otro in ("CORSMiddleware", "SlowAPIMiddleware"):
        if otro in clases:
            assert donde < clases.index(otro), (
                f"{otro} corre antes que el tope: hace su trabajo sobre un "
                "pedido que todavía no se sabe si entra")


# ══════════════════════════════════════════════════════════════════════════
# 3. Las directivas de CSP que no dependen de qué scripts carga la app
# ══════════════════════════════════════════════════════════════════════════

def test_las_tres_directivas_de_csp_estan(cliente):
    """`object-src 'none'` corta la ejecución por plugin con un archivo subido;
    `base-uri 'self'` impide que un `<base>` inyectado cambie a dónde apuntan
    TODAS las rutas relativas, scripts incluidos; `frame-ancestors` es lo mismo
    que X-Frame-Options para los navegadores que ya no lo miran."""
    csp = cliente.get("/api/limits").headers.get("content-security-policy", "")
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_script_src_NO_esta_y_es_a_proposito():
    """Queda escrito para que no se lea como un olvido. La aplicación carga el
    SDK de Mercado Pago y otros scripts de terceros: una lista mal armada rompe
    los pagos en silencio. Ponerla requiere revisar qué carga cada pantalla."""
    fuente = open(os.path.join(_BACKEND, "server.py"), encoding="utf-8").read()
    bloque = fuente[fuente.index("Content-Security-Policy") - 1600:
                    fuente.index("Content-Security-Policy") + 300]
    assert "script-src" in bloque, "falta la explicación de por qué no está"
    assert "Mercado Pago" in bloque
