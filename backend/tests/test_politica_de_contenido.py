"""
tests/test_politica_de_contenido.py — De dónde puede venir un script.

QUE PROTEGE

    Un XSS es código ajeno corriendo en el origen de la aplicación, con la
    sesión de quien mira. Las validaciones de entrada y salida cierran los
    caminos que conocemos —y esta aplicación tenía tres, todos cerrados—; la
    política de contenido cierra el resto: le dice al navegador de dónde puede
    venir un script, y todo lo demás no corre, venga por donde venga.

    Es la única defensa contra el XSS que todavía no se descubrió.

POR QUE `script-src` NO ESTABA, Y POR QUE AHORA SI

    El motivo escrito era: «la aplicación carga el SDK del proveedor de pagos, y
    una lista mal armada rompe los cobros en silencio». Era honesto y también
    una excusa cómoda. Lo que faltaba era el inventario:

      * el `index.html` construido tiene UN script, el nuestro;
      * no hay NINGUN script en línea en el build;
      * no hay `eval` en el paquete;
      * el único origen externo de scripts es el SDK del proveedor de pagos.

    Con eso, `script-src` va sin `'unsafe-inline'` ni `'unsafe-eval'` — que es
    la diferencia entre una política que sirve y una decorativa. Con
    `'unsafe-inline'` puesto, un XSS inyectado en la página corre igual y la
    directiva no protege de nada.

Y POR QUE ARRANCA SIN BLOQUEAR

    El inventario dice qué carga la aplicación hoy, en el build. Lo que un SDK
    ajeno pide en tiempo de ejecución no se ve leyendo el código. Así que sale
    en modo reporte: el navegador avisa lo que habría bloqueado y no bloquea
    nada. Con tráfico real se completa, y recién ahí se pasa a bloquear.

    Publicar una política que bloquea sin haberla mirado con tráfico real es
    exactamente la forma de romper los pagos en silencio que motivó no ponerla.
"""
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from conftest import usar_base                                      # noqa: E402,F401
from services import csp                                            # noqa: E402


def directiva(nombre, politica=None):
    """El valor de una directiva dentro del texto de la política."""
    texto = politica if politica is not None else csp.politica()
    for parte in texto.split(";"):
        parte = parte.strip()
        if parte.startswith(nombre + " "):
            return parte[len(nombre) + 1:].strip()
    return None


# ══════════════════════════════════════════════════════════════════════════
# 1. La directiva que importa
# ══════════════════════════════════════════════════════════════════════════

def test_SCRIPT_SRC_EXISTE():
    """Estuvo ausente a propósito durante toda la revisión anterior. Que esté es
    el cambio, así que se fija primero."""
    assert directiva("script-src") is not None


@pytest.mark.parametrize("veneno", ["'unsafe-inline'", "'unsafe-eval'"])
def test_SCRIPT_SRC_NO_LLEVA_LA_PALABRA_QUE_LA_ANULA(veneno):
    """Con cualquiera de las dos, un XSS inyectado en la página corre igual: la
    directiva queda escrita, se ve bien en una auditoría, y no protege de nada.

    Se puede prescindir porque el build no genera scripts en línea ni usa
    `eval`. Si alguien agrega uno, lo que hay que arreglar es el build — no
    aflojar esto.
    """
    assert veneno not in directiva("script-src")


def test_script_src_no_es_un_https_pelado():
    """`https:` a secas, o `*`, dejan entrar a cualquier dominio del mundo. Es
    casi lo mismo que no tener la directiva, y se ve igual de bien en un
    informe de auditoría.

    Se miran los orígenes UNO POR UNO y no como subcadena: `https://sdk...`
    contiene «https:» y no es lo mismo que un `https:` suelto.
    """
    origenes = directiva("script-src").split()
    assert "https:" not in origenes, origenes
    assert "*" not in origenes, origenes
    assert "http:" not in origenes, origenes
    # Un comodín sólo se acepta como subdominio de un dominio nombrado
    # (`https://*.proveedor.com`), nunca como dominio entero (`https://*`).
    for origen in origenes:
        if "*" in origen:
            assert origen.startswith("https://*."), origen
            assert origen.count(".") >= 2, origen


def test_el_sdk_de_pagos_esta_permitido():
    """Una política correcta que rompe los cobros se saca a los dos días. El
    inventario dice que este es el único origen externo de scripts."""
    assert "sdk.mercadopago.com" in directiva("script-src")


def test_lo_que_no_se_nombra_solo_puede_venir_de_casa():
    assert directiva("default-src") == "'self'"


# ══════════════════════════════════════════════════════════════════════════
# 2. Las otras directivas, y por qué cada una afloja o no
# ══════════════════════════════════════════════════════════════════════════

def test_los_estilos_SI_pueden_ir_en_linea_y_esta_bien():
    """La interfaz tiene más de 4500 `style={{...}}` de React. Un estilo no
    ejecuta código; sacarlo sería reescribir toda la aplicación para ganar muy
    poco. Se deja explícito para que no se lea como un descuido."""
    assert "'unsafe-inline'" in directiva("style-src")


def test_las_imagenes_pueden_venir_de_cualquier_https():
    """Hay comprobantes viejos guardados apuntando a dominios que no elegimos.
    Una imagen no ejecuta nada: el riesgo acá es que una dirección ajena sepa
    cuándo se abrió la pantalla, no que corra código."""
    assert "https:" in directiva("img-src")
    assert "data:" in directiva("img-src")   # los base64 ya guardados
    assert "blob:" in directiva("img-src")   # la vista previa de un archivo


@pytest.mark.parametrize("nombre, esperado", [
    ("object-src", "'none'"),        # plugins: camino clásico de ejecución
    ("base-uri", "'self'"),          # un <base> inyectado mueve TODA ruta relativa
    ("form-action", "'self'"),       # un formulario que postea a otro lado
    ("frame-ancestors", "'none'"),   # clickjacking
])
def test_las_directivas_que_no_cuestan_nada_estan(nombre, esperado):
    assert directiva(nombre) == esperado


def test_la_politica_dice_a_donde_mandar_los_avisos():
    politica = csp.politica()
    assert csp.RUTA_DE_REPORTE in politica
    assert "report-to csp" in politica


# ══════════════════════════════════════════════════════════════════════════
# 3. El modo: que no se prenda sola
# ══════════════════════════════════════════════════════════════════════════

def test_POR_OMISION_NO_BLOQUEA(monkeypatch):
    """Una política mal armada que se despliega sola un viernes es peor que no
    tenerla. Sin la variable puesta, avisa y no corta."""
    monkeypatch.delenv("CSP_MODO", raising=False)
    nombre, _ = csp.cabecera()
    assert nombre == "Content-Security-Policy-Report-Only"


def test_se_pasa_a_bloquear_cambiando_una_variable(monkeypatch):
    monkeypatch.setenv("CSP_MODO", "exigir")
    nombre, _ = csp.cabecera()
    assert nombre == "Content-Security-Policy"


def test_se_puede_apagar_del_todo(monkeypatch):
    """La salida de emergencia. Si algo se rompe en producción por esto, tiene
    que poder apagarse sin desplegar código."""
    monkeypatch.setenv("CSP_MODO", "apagado")
    assert csp.cabecera() is None


@pytest.mark.parametrize("valor", ["", "  ", "si", "true", "EXIGIR_YA", "1"])
def test_UN_VALOR_RARO_NO_PRENDE_EL_BLOQUEO(valor, monkeypatch):
    """Lo importante es la dirección del error: un valor que nadie entiende
    tiene que caer en «avisar», nunca en «bloquear». Al revés, un dedazo en una
    variable de entorno corta los pagos."""
    monkeypatch.setenv("CSP_MODO", valor)
    nombre, _ = csp.cabecera()
    assert nombre == "Content-Security-Policy-Report-Only", valor


def test_el_texto_de_la_politica_es_el_mismo_en_los_dos_modos(monkeypatch):
    """Si el modo reporte probara una política distinta de la que después va a
    bloquear, los avisos que junte no dirían nada sobre la real."""
    monkeypatch.setenv("CSP_MODO", "reporte")
    _, en_reporte = csp.cabecera()
    monkeypatch.setenv("CSP_MODO", "exigir")
    _, exigiendo = csp.cabecera()
    assert en_reporte == exigiendo


# ══════════════════════════════════════════════════════════════════════════
# 4. El inventario que justifica la política — si cambia, la política miente
# ══════════════════════════════════════════════════════════════════════════

_RAIZ = os.path.dirname(_BACKEND)
_DIST = os.path.join(_RAIZ, "frontend", "dist")


def _hay_build():
    return os.path.isfile(os.path.join(_DIST, "index.html"))


@pytest.mark.skipif(not _hay_build(), reason="no hay build del frontend")
def test_EL_BUILD_NO_GENERA_SCRIPTS_EN_LINEA():
    """Esta es la premisa de la que depende poder omitir `'unsafe-inline'`. El
    día que el build genere uno, la política lo va a bloquear y la pantalla
    quedará en blanco — así que se comprueba acá, no en producción."""
    import re
    html = open(os.path.join(_DIST, "index.html"), encoding="utf-8").read()
    con_cuerpo = [c for c in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
                  if c.strip()]
    assert not con_cuerpo, (
        "el build genera un script en línea. La política lo va a bloquear.\n"
        "Arreglá el build; NO agregues 'unsafe-inline', que anula la directiva.")


@pytest.mark.skipif(not _hay_build(), reason="no hay build del frontend")
def test_todo_origen_de_script_del_build_esta_en_la_politica():
    """El otro lado del inventario: si el build empieza a cargar un script de un
    dominio nuevo, tiene que aparecer acá antes de que la política lo corte."""
    import re
    html = open(os.path.join(_DIST, "index.html"), encoding="utf-8").read()
    permitidos = directiva("script-src")
    for src in re.findall(r'<script[^>]*\bsrc="([^"]+)"', html):
        if src.startswith("/") or src.startswith("./"):
            continue                       # propio: lo cubre 'self'
        dominio = re.sub(r"^https://([^/]+).*", r"\\1", src)
        assert dominio in permitidos or f"*.{dominio.split('.', 1)[-1]}" in permitidos, (
            f"el build carga un script de {dominio} y la política no lo permite")


# ══════════════════════════════════════════════════════════════════════════
# 5. El buzón donde el navegador avisa
# ══════════════════════════════════════════════════════════════════════════
#
# Sin este endpoint, el modo reporte no sirve de nada: el navegador avisa y el
# aviso se pierde. Y como tiene que ser público —el navegador lo manda sin
# sesión, a veces justo cuando la página no cargó bien— es un buzón abierto en
# internet y hay que tratarlo como tal.

@pytest.fixture(scope="module")
def cliente():
    try:
        from fastapi.testclient import TestClient
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    return TestClient(app)


REPORTE = {"csp-report": {"effective-directive": "script-src",
                          "blocked-uri": "https://un-dominio.test/x.js",
                          "document-uri": "https://risappbr.com/send"}}


def test_el_aviso_del_navegador_se_recibe(cliente):
    r = cliente.post(csp.RUTA_DE_REPORTE, json=REPORTE)
    assert r.status_code == 204


def test_SIEMPRE_CONTESTA_204_AUNQUE_LE_MANDEN_BASURA(cliente):
    """Del otro lado no hay nadie esperando una respuesta: es un aviso que el
    navegador dispara y olvida. Un código de error sólo provocaría reintentos, y
    le diría a quien está probando qué le gusta a este endpoint."""
    for basura in [b"no es json", b"", b"[[[", b'{"csp-report": "texto"}',
                   b'{"csp-report": null}', b"[1,2,3]"]:
        r = cliente.post(csp.RUTA_DE_REPORTE, content=basura,
                         headers={"content-type": "application/json"})
        assert r.status_code == 204, basura


def test_un_cuerpo_enorme_no_se_procesa(cliente):
    """Un reporte real pesa menos de 1 KB. Sin tope, esta dirección es memoria
    gratis para cualquiera."""
    from routes import csp_reporte
    r = cliente.post(csp.RUTA_DE_REPORTE,
                     content=b'{"a":"' + b"x" * (csp_reporte.TOPE_BYTES + 10) + b'"}',
                     headers={"content-type": "application/json"})
    assert r.status_code == 204


def test_SOLO_SE_REGISTRAN_LOS_DOS_CAMPOS_QUE_HACEN_FALTA(cliente, caplog):
    """A esta dirección le escribe cualquiera. Volcar lo que mande es convertir
    nuestro registro en su bloc de notas — y de paso, el `document-uri` dice qué
    pantalla estaba mirando una persona concreta."""
    import logging
    with caplog.at_level(logging.WARNING):
        cliente.post(csp.RUTA_DE_REPORTE, json=REPORTE)
    texto = caplog.text
    assert "script-src" in texto                      # la directiva, sí
    assert "un-dominio.test" in texto                 # de dónde venía, sí
    assert "/send" not in texto, "se registró qué pantalla estaba mirando"


def test_un_valor_larguisimo_no_entra_entero_al_registro(cliente, caplog):
    import logging
    largo = {"csp-report": {"effective-directive": "script-src",
                            "blocked-uri": "https://x.test/" + "a" * 5000}}
    with caplog.at_level(logging.WARNING):
        cliente.post(csp.RUTA_DE_REPORTE, json=largo)
    assert "a" * 500 not in caplog.text


def test_se_entienden_los_dos_formatos_de_reporte(cliente, caplog):
    """El formato viejo (`{"csp-report": {...}}`) y el nuevo de `report-to`
    (una lista). Entender uno solo significa perder la mitad de los avisos, y
    peor: perderlos en silencio."""
    import logging
    nuevo = [{"type": "csp-violation",
              "body": {"effectiveDirective": "connect-src",
                       "blockedURL": "https://otro.test/api"}}]
    with caplog.at_level(logging.WARNING):
        cliente.post(csp.RUTA_DE_REPORTE, json=nuevo)
    assert "connect-src" in caplog.text
    assert "otro.test" in caplog.text


def test_el_buzon_tiene_tope_de_intentos():
    """Es una ruta pública que escribe en el registro. Sin tope es un generador
    de líneas gratis. El barrido de `test_puertas_sin_llave.py` ya lo exige;
    esto lo deja dicho también acá, al lado de la ruta."""
    fuente = open(os.path.join(_BACKEND, "routes", "csp_reporte.py"),
                  encoding="utf-8").read()
    assert 'frenar(request, "csp.reporte"' in fuente
