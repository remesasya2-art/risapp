"""
tests/test_direcciones_que_no_existen.py — Que una puerta que no existe lo diga.

DE DONDE SALE ESTE ARCHIVO

    De un defecto real que estuvo meses sin verse. Mercado Pago avisaba de cada
    pago a la RAIZ del sitio en vez de a `/api/webhook/mercadopago`:

        POST /?data.id=177862590765&type=payment  →  405 Method Not Allowed

    Ninguna alarma. Un 405 suelto entre miles de líneas normales. Se encontró de
    casualidad, mirando otra cosa, y sólo no costó plata porque la pantalla del
    cliente pregunta mientras espera y venía tapando el agujero.

LO QUE SE VIGILA, Y EN QUE ORDEN DE IMPORTANCIA

    1. Que las pantallas del navegador SIGAN saliendo. `/envios/ABC123` no es
       una ruta del servidor: la resuelve el navegador. Un 404 ahí rompe la
       aplicación entera para todos. Es el riesgo grande de este cambio y por
       eso tiene su test antes que ninguno.

    2. Que las rutas de verdad no queden tapadas por el comodín. La del aviso de
       Mercado Pago y la de salud son las dos que, si se caen, no se arreglan
       solas: una deja de acreditar cobros y la otra impide que el despliegue
       levante.

    3. Que el grito salga cuando tiene que salir, DICIENDO la dirección buena.

    4. Y que NO salga el resto del tiempo. Por acá pasan todos los escáneres de
       internet: un aviso por cada uno es un registro que nadie lee, que es el
       problema que esto vino a resolver.
"""
import logging
import os
import sys
from pathlib import Path

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from conftest import usar_base                                    # noqa: E402,F401
from services import sin_ruta                                     # noqa: E402

# `frontend/dist` NO está versionado, así que en CI la aplicación corre sin
# build — y ahí no hay ninguna pantalla que servir. Eso cambia qué se PUEDE
# exigir, y no da lo mismo: escribir los tests dando por sentado que el build
# está fue lo que dejó pasar un defecto que rompía el sitio entero sin él.
HAY_BUILD = (Path(_BACKEND).parent / "frontend" / "dist" / "index.html").is_file()
sin_build = pytest.mark.skipif(
    not HAY_BUILD,
    reason="sin `frontend/dist` no hay ninguna pantalla que servir: correr "
           "`npm run build` en frontend/ para que esto se pruebe de verdad")


@pytest.fixture(scope="module")
def cliente():
    try:
        from fastapi.testclient import TestClient
        from server import app
    except Exception as e:                                        # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    return TestClient(app)


# ══════════════════════════════════════════════════════════════════════════
# 1. Lo que NO se puede romper
# ══════════════════════════════════════════════════════════════════════════

PANTALLAS = ["/", "/envios/ABC123", "/history", "/admin",
             "/seguimiento/un-token-largo", "/recharge",
             "/una-que-no-existe-todavia"]


@pytest.mark.parametrize("pantalla", PANTALLAS)
def test_UNA_PANTALLA_DEL_NAVEGADOR_NUNCA_CONTESTA_405(cliente, pantalla):
    """Este test existe por un defecto que metí y que agarró CI.

    Al registrar el comodín de POST/PUT/PATCH/DELETE, el camino
    `/{full_path:path}` pasó a existir sólo para esos cuatro métodos cuando no
    hay build. Entonces un GET a cualquier dirección —la raíz incluida— se
    encontraba con una ruta que no acepta su método: 405. El sitio entero
    contestando «método no permitido».

    Vale HAYA O NO build, que es justo lo que le faltaba al test de abajo.
    """
    r = cliente.get(pantalla)
    assert r.status_code != 405, (
        f"{pantalla} contesta «método no permitido» a un GET normal")


@sin_build
@pytest.mark.parametrize("pantalla", PANTALLAS)
def test_LAS_PANTALLAS_DEL_NAVEGADOR_SIGUEN_SALIENDO(cliente, pantalla):
    """Ninguna de éstas es una ruta del servidor: las resuelve el navegador.

    Un 404 acá deja la aplicación inservible para todo el que entre por un
    enlace directo o recargue estando adentro. Es el riesgo grande del cambio.
    """
    r = cliente.get(pantalla)
    assert r.status_code == 200, f"{pantalla} dejó de servir la aplicación"
    assert "text/html" in r.headers.get("content-type", ""), pantalla


def test_LA_RUTA_DEL_AVISO_DE_MERCADOPAGO_NO_QUEDA_TAPADA(cliente):
    """El comodín se registra al final, pero si tapara a las rutas de verdad
    dejaría de acreditarse cada cobro y nadie se enteraría — que es exactamente
    la clase de silencio que este archivo existe para impedir.

    Sin la variable del secreto contesta 401 (es fail-closed). Lo que importa
    es que NO sea 404: eso querría decir que la ruta desapareció.
    """
    r = cliente.post(sin_ruta.DONDE_AVISA_MERCADOPAGO)
    assert r.status_code != 404, "el comodín se comió la ruta del webhook"


def test_la_ruta_de_salud_sigue_viva(cliente):
    """Railway le pega a ésta para saber si la aplicación vive. Un 404 acá y el
    despliegue no levanta nunca."""
    r = cliente.get("/api/health")
    assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════════
# 2. Lo que sí cambia: una dirección que no existe lo dice
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("inventada", [
    "/api/una-que-me-invente", "/api/admin/no-existe", "/api",
])
def test_una_direccion_de_la_api_que_no_existe_contesta_404(cliente, inventada):
    """Antes devolvía el index.html con un 200, y entonces quien le pegaba a una
    dirección inexistente lo veía como si hubiera funcionado."""
    r = cliente.get(inventada)
    assert r.status_code == 404, inventada
    assert "text/html" not in r.headers.get("content-type", ""), (
        f"{inventada} devolvió la página en vez de un error")


@pytest.mark.parametrize("metodo", ["post", "put", "patch", "delete"])
def test_mandar_datos_a_una_direccion_que_no_existe_contesta_404(cliente, metodo):
    r = getattr(cliente, metodo)("/una-direccion-que-no-existe")
    assert r.status_code == 404, metodo
    assert "text/html" not in r.headers.get("content-type", ""), metodo


def test_un_post_a_una_ruta_que_solo_acepta_get_tambien_da_404(cliente):
    """Efecto lateral buscado: antes daba 405, que le confirma a quien prueba
    puertas que esa dirección existe. Eso no se le debe a nadie."""
    r = cliente.post("/api/health")
    assert r.status_code == 404


def test_que_es_de_la_api_y_que_no():
    assert sin_ruta.es_de_la_api("/api/loquesea")
    assert sin_ruta.es_de_la_api("api/loquesea")
    assert sin_ruta.es_de_la_api("/api")
    assert not sin_ruta.es_de_la_api("/envios/ABC123")
    assert not sin_ruta.es_de_la_api("/")
    # No alcanza con que EMPIECE con esas letras: una pantalla que se llamara
    # `/apitos` no es de la API y tiene que seguir saliendo.
    assert not sin_ruta.es_de_la_api("/apitos")


# ══════════════════════════════════════════════════════════════════════════
# 3. El grito
# ══════════════════════════════════════════════════════════════════════════

def _gritar(caplog, metodo="POST", camino="/", consulta=None, cabeceras=()):
    with caplog.at_level(logging.ERROR, logger="services.sin_ruta"):
        return sin_ruta.avisar_si_es_un_pago_perdido(
            metodo, camino, consulta or {}, cabeceras)


def test_EL_AVISO_DE_PAGO_PERDIDO_GRITA_Y_DICE_LA_DIRECCION_BUENA(caplog):
    """El caso exacto de producción, con su número de pago y todo.

    Que el mensaje NOMBRE la dirección correcta no es adorno: un error que dice
    qué está mal pero no cuál es lo bueno obliga a ir a buscarlo, y eso son
    horas más de agujero abierto.
    """
    motivo = _gritar(caplog, consulta={"data.id": "177862590765", "type": "payment"})
    assert motivo == "mercadopago"
    texto = caplog.text
    assert sin_ruta.DONDE_AVISA_MERCADOPAGO in texto, texto
    assert "177862590765" in texto, "sin el id no se puede ir a buscar qué pago fue"


@pytest.mark.parametrize("consulta,cabeceras", [
    ({"data.id": "1"}, ()),                       # la forma nueva
    ({"topic": "payment", "id": "1"}, ()),        # la vieja, de IPN
    ({"type": "payment"}, ()),                    # el tipo de evento
    ({}, ("X-Signature", "Content-Type")),        # la firma, aunque no haya consulta
])
def test_las_cuatro_formas_del_aviso_se_reconocen(caplog, consulta, cabeceras):
    assert _gritar(caplog, consulta=consulta, cabeceras=cabeceras) == "mercadopago"


def test_un_post_a_la_raiz_con_parametros_tambien_grita(caplog):
    """Nadie le manda datos a la raíz por equivocarse de enlace. Está para que,
    si mañana otro proveedor queda mal configurado igual pero con otra pinta,
    tampoco pase inadvertido."""
    assert _gritar(caplog, consulta={"cualquier_cosa": "1"}) == "raiz"


def test_EL_REGISTRO_NO_COPIA_LOS_VALORES_DE_LOS_PARAMETROS(caplog):
    """Un registro se queda escrito y lo lee gente que no es dueña del dato.
    Los nombres alcanzan para diagnosticar; los valores pueden traer lo que a
    cualquiera se le ocurrió mandar."""
    _gritar(caplog, consulta={"token": "SECRETO-QUE-NO-VA-AL-REGISTRO"})
    assert "token" in caplog.text, "sin el nombre no se puede diagnosticar nada"
    assert "SECRETO-QUE-NO-VA-AL-REGISTRO" not in caplog.text, caplog.text


# ══════════════════════════════════════════════════════════════════════════
# 4. Y el silencio, que vale lo mismo
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("camino", [
    "/wp-login.php", "/.env", "/admin/config.php", "/xmlrpc.php",
])
def test_UN_ESCANER_CUALQUIERA_NO_DEJA_RUIDO(caplog, camino):
    """Por acá pasan todos los escáneres de internet. Un aviso por cada uno es
    un registro que nadie lee, y un registro que nadie lee es el problema que
    esto vino a resolver."""
    assert _gritar(caplog, camino=camino) is None
    assert caplog.text == "", caplog.text


def test_un_post_a_la_raiz_SIN_parametros_no_grita(caplog):
    assert _gritar(caplog, consulta={}) is None
    assert caplog.text == ""


def test_un_GET_nunca_grita(caplog):
    """Mercado Pago avisa con POST. Un GET con esa pinta es alguien que pegó un
    enlace en el navegador, y no es un cobro perdido."""
    assert _gritar(caplog, metodo="GET", consulta={"data.id": "1"}) is None
    assert caplog.text == ""
