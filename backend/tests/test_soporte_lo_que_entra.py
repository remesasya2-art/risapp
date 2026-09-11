"""
tests/test_soporte_lo_que_entra.py — Qué se puede mandar por el chat de soporte.

DE QUE SE TRATA

    El chat es el único lugar de la aplicación donde cualquiera con una cuenta
    escribe texto libre y sube un archivo, y donde lo que manda lo abre un
    asesor —alguien que puede aprobar KYCs y mover plata—. Es el peor par
    posible, y por eso este canal es más estricto que el resto.

    Dos barreras, y cada una cierra algo distinto:

    LOS ENLACES, sólo del lado del cliente. El texto se pinta como texto plano
    en las dos pantallas, así que un enlace no ejecuta nada ni es clicable: el
    daño es el engaño, una dirección falsa que alguien convence al otro de
    abrir. El asesor SI puede mandar enlaces, porque a veces tiene que pasar un
    seguimiento o un formulario.

    LOS ADJUNTOS, de los dos lados. Acá lo que se cierra no es código: es que
    el adjunto pueda ser una dirección ajena. La pantalla lo pinta como
    `<img src>`, así que cada vez que se abre el caso, el servidor de quien la
    mandó se entera de la IP, el navegador y la hora — y puede cambiar la imagen
    después de que la revisaron.

LO QUE ESTOS TESTS CUIDAN MAS

    El falso positivo. Un filtro de enlaces que rechaza «esto.es urgente» o
    «mi correo es ana@ejemplo.com» molesta a todos los clientes honestos y no
    frena a ninguno de los otros. La mitad de este archivo son frases normales
    que TIENEN que pasar.
"""
import asyncio
import base64
import io
import os
import sys
import types

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor", reason="hace falta mongomock_motor para estos tests")

from services.soporte import problema_por_enlaces                     # noqa: E402
from services.imagen_recibida import (ImagenInvalida,                 # noqa: E402
                                      limpiar_foto_del_chat,
                                      tipo_por_los_bytes)


# ══════════════════════════════════════════════════════════════════════════
# 1. Los enlaces: lo que NO se puede mandar
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("texto", [
    "mirá acá https://sitio-falso.com/login",
    "entrá a www.banco-falso.com y poné tu clave",
    "descargá el archivo en bit.ly/abc123",
    "mi web es ejemplo.com.br",
    "conectate a 192.168.1.50:8080",
    # Las formas de escribir un punto sin escribirlo. Quien las usa lo hace
    # justamente para esquivar un filtro, así que se normalizan antes de mirar.
    "andá a sitiofalso(.)com ahora",
    "escribí banco punto falso punto com",
    "hxxps://malicioso.net/pago",
    "sitio [.] com",
    # Esquemas que no llevan `//` y abren algo igual.
    "mandame un mail a mailto:otro@x.com",
    "magnet:?xt=urn:btih:abc",
])
def test_un_enlace_del_cliente_no_pasa(texto):
    problema = problema_por_enlaces(texto)
    assert problema is not None, f"pasó un enlace: {texto!r}"
    # El mensaje le dice al cliente qué hacer, no sólo que no.
    assert "enlaces" in problema.lower()
    assert "asesor" in problema.lower()


# ══════════════════════════════════════════════════════════════════════════
# 2. Los enlaces: lo que SI tiene que pasar
# ══════════════════════════════════════════════════════════════════════════
#
# Esta mitad vale más que la otra. Un filtro que rechaza de más convierte a
# todos los clientes honestos en un ticket de soporte.

@pytest.mark.parametrize("texto", [
    "Mi envío de ayer no llegó al beneficiario, ¿me ayudan?",
    "Mandé los documentos hace 3 días y sigue en revisión.",
    # Un correo es una frase normal en soporte: «escribime a…». Se saca del
    # texto ANTES de buscar dominios, o el filtro lo leería como una dirección.
    "Mi correo es ana.pereira@ejemplo.com por si necesitan escribirme",
    # Decimales y fechas, que tienen puntos y no son direcciones.
    "Pagué 1.250,50 reales y no se acreditó",
    "El comprobante dice 3.50 y me cobraron 4.20",
    "Hablé con el Sr. Pérez el 11.09.2026",
    # Nombres de archivo: la extensión no es un dominio.
    "Adjunto la foto.png del comprobante",
    "el archivo se llama comprobante.pdf",
    "Mi caso es el S-000123 y ya van 5 días",
    # Portugués: «data» es fecha, y la mitad de los clientes escriben así. Un
    # `data:` a secas en la lista de esquemas rechazaba esta frase.
    "A data: 11/09/2026, o envio não chegou",
    # Español: «tel:» es como se escribe un teléfono.
    "Mi tel: 555-1234 por si quieren llamarme",
])
def test_una_frase_normal_pasa(texto):
    assert problema_por_enlaces(texto) is None, f"se rechazó prosa normal: {texto!r}"


@pytest.mark.parametrize("texto", [
    "esto.es urgente por favor",
    "no quiero nada.de eso, quiero mi dinero",
    "ya te dije.no me contestan",
])
def test_el_punto_sin_espacio_no_es_un_dominio(texto):
    """En español se escribe «esto.es urgente» cuando falta el espacio tras el
    punto, y `.es` y `.de` son dominios de país.

    Los de dos letras que chocan con palabras del idioma sólo cuentan
    acompañados: con esquema, con `www.` o con una barra después.
    """
    assert problema_por_enlaces(texto) is None, f"falso positivo: {texto!r}"


def test_pero_ese_mismo_dominio_con_una_ruta_si_se_bloquea():
    """La otra mitad de la regla anterior: sin esto, `.es` sería una puerta
    abierta y el test de arriba pasaría con el filtro roto."""
    assert problema_por_enlaces("visitá esto.es/promocion") is not None


@pytest.mark.parametrize("vacio", [None, "", "   "])
def test_un_mensaje_vacio_no_es_un_enlace(vacio):
    assert problema_por_enlaces(vacio) is None


# ══════════════════════════════════════════════════════════════════════════
# 3. Los adjuntos
# ══════════════════════════════════════════════════════════════════════════

def _png(color=(200, 30, 30), tam=(40, 40)):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", tam, color).save(b, format="PNG")
    return b.getvalue()


def _como_data(crudos, etiqueta="png"):
    return f"data:image/{etiqueta};base64," + base64.b64encode(crudos).decode()


def test_una_foto_de_verdad_se_acepta():
    salida = limpiar_foto_del_chat(_como_data(_png()))
    assert salida.startswith("data:image/png;base64,")


@pytest.mark.parametrize("valor,por_que", [
    ("https://servidor-del-atacante.com/foto.png",
     "una dirección ajena convierte cada apertura del caso en un aviso"),
    ("/api/media/abc.png", "ni siquiera una ruta nuestra: acá sólo sube el navegador"),
    ("javascript:alert(document.cookie)", "el esquema que se ejecutaba al abrir"),
    ("data:text/html;base64,PHNjcmlwdD4=", "no es una imagen"),
    ("data:image/svg+xml;base64,PHN2Zz4=", "el SVG lleva scripts adentro"),
])
def test_lo_que_no_es_una_foto_subida_no_entra(valor, por_que):
    with pytest.raises(ImagenInvalida):
        limpiar_foto_del_chat(valor)


def test_la_etiqueta_no_alcanza_hay_que_ser_una_foto():
    """`data:image/png;base64,` con cualquier cosa adentro pasaba el filtro
    viejo: le creía a la etiqueta. Los bytes son lo único que no se puede
    mentir."""
    basura = _como_data(b"esto no es una imagen, es texto cualquiera")
    with pytest.raises(ImagenInvalida) as e:
        limpiar_foto_del_chat(basura)
    assert "no es una foto" in str(e.value)


def test_el_tipo_que_se_guarda_es_el_que_dicen_los_bytes():
    """Si la etiqueta miente, gana el archivo. Guardar «jpeg» sobre un PNG deja
    un dato falso en la base que después alguien va a creerse."""
    mintiendo = _como_data(_png(), etiqueta="jpeg")
    salida = limpiar_foto_del_chat(mintiendo)
    assert salida.startswith("data:image/png;base64,")


def test_a_la_foto_se_le_quitan_los_metadatos():
    """Una foto de teléfono lleva las coordenadas GPS de dónde se tomó. Un
    cliente que manda un comprobante no está decidiendo mandar su domicilio."""
    from PIL import Image
    b = io.BytesIO()
    imagen = Image.new("RGB", (40, 40), (10, 90, 200))
    exif = imagen.getexif()
    exif[271] = "FabricanteDePrueba"          # Make
    exif[272] = "ModeloDePrueba"              # Model
    imagen.save(b, format="JPEG", exif=exif)
    con_metadatos = b.getvalue()
    assert Image.open(io.BytesIO(con_metadatos)).getexif(), "el escenario no sirve"

    salida = limpiar_foto_del_chat(_como_data(con_metadatos, "jpeg"))
    limpia = base64.b64decode(salida.split(",", 1)[1])
    assert not Image.open(io.BytesIO(limpia)).getexif(), "los metadatos sobrevivieron"


@pytest.mark.parametrize("crudos,esperado", [
    (b"\xff\xd8\xff\xe0" + b"\x00" * 20, "jpeg"),
    (b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, "png"),
    (b"GIF89a" + b"\x00" * 20, "gif"),
    (b"BM" + b"\x00" * 20, "bmp"),
    (b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 20, "webp"),
    (b"\x00" * 4 + b"ftypavif" + b"\x00" * 20, "avif"),
    (b"no soy nada", None),
    (b"", None),
])
def test_las_firmas_cubren_todo_lo_que_el_chat_acepta(crudos, esperado):
    """WEBP es lo que mandan los móviles modernos y AVIF ya empieza a aparecer.
    `services/envios_archivos.py` no los conoce —cubre otro camino— así que si
    esta tabla se quedara corta se rechazarían fotos legítimas."""
    assert tipo_por_los_bytes(crudos) == esperado


def test_un_adjunto_vacio_sigue_siendo_vacio():
    assert limpiar_foto_del_chat(None) is None
    assert limpiar_foto_del_chat("") is None


# ══════════════════════════════════════════════════════════════════════════
# 4. Contra la aplicación de verdad
# ══════════════════════════════════════════════════════════════════════════
#
# Lo de arriba prueba las reglas. Esto prueba que estén CONECTADAS, y del lado
# correcto: al cliente sí, al asesor no.

def _ya(corrutina):
    return asyncio.run(corrutina)


def _mesa():
    if "pywebpush" not in sys.modules:                        # pragma: no cover
        stub = types.ModuleType("pywebpush")
        stub.WebPushException = type("WebPushException", (Exception,), {})
        stub.webpush = lambda *a, **k: None
        sys.modules["pywebpush"] = stub
    from conftest import usar_base
    base = mongomock_motor.AsyncMongoMockClient()["ris_lo_que_entra"]
    usar_base(base)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.soporte import router
    from routes import dependencies as deps

    app = FastAPI()
    app.include_router(router, prefix="/api")
    actual = {"u": None}
    app.dependency_overrides[deps.get_current_user] = lambda: actual["u"]
    app.dependency_overrides[deps.get_crm_user] = lambda: actual["u"]
    return TestClient(app), actual, base


from models.user import User                                          # noqa: E402

CLIENTA = User(user_id="u_ana", name="Ana Pereira", email="ana@t.com", role="user")
ASESOR = User(user_id="s_beto", name="Beto Nogueira", email="b@t.com", role="agent",
              permissions=["support.view", "support.respond", "support.close"])


def test_el_cliente_no_puede_abrir_un_caso_con_un_enlace():
    cliente, actual, base = _mesa()
    actual["u"] = CLIENTA
    r = cliente.post("/api/soporte/casos", json={
        "motivo": "envio",
        "mensaje": "no me llegó, mirá acá https://banco-falso.com/verificar"})
    assert r.status_code == 400, r.text
    assert "enlaces" in r.json()["detail"].lower()

    async def revisar():
        assert await base.soporte_casos.count_documents({}) == 0, "el caso se creó igual"

    _ya(revisar())


def test_el_cliente_tampoco_puede_responder_con_un_enlace():
    cliente, actual, base = _mesa()
    actual["u"] = CLIENTA
    caso = cliente.post("/api/soporte/casos", json={
        "motivo": "envio", "mensaje": "Mi envío no llegó al beneficiario"}).json()["caso"]
    r = cliente.post(f"/api/soporte/casos/{caso['caso_id']}/mensajes",
                     json={"mensaje": "mandame los datos a www.otro-sitio.com"})
    assert r.status_code == 400, r.text


def test_pero_su_consulta_normal_entra_sin_problema():
    """El contraste: sin esto, un filtro que rechaza TODO pasaría los dos tests
    de arriba."""
    cliente, actual, base = _mesa()
    actual["u"] = CLIENTA
    r = cliente.post("/api/soporte/casos", json={
        "motivo": "envio",
        "mensaje": "Mi envío de ayer no llegó. Mi correo es ana@ejemplo.com."})
    assert r.status_code == 200, r.text


def test_el_asesor_si_puede_mandar_un_enlace():
    """A veces tiene que pasar un seguimiento o un formulario. Bloquearlo le
    rompe el trabajo, y el asesor es de la casa."""
    cliente, actual, base = _mesa()
    actual["u"] = CLIENTA
    caso = cliente.post("/api/soporte/casos", json={
        "motivo": "envio", "mensaje": "Mi envío no llegó al beneficiario"}).json()["caso"]

    actual["u"] = ASESOR
    _ya(base.users.insert_one({"user_id": "s_beto", "name": "Beto Nogueira",
                               "role": "agent", "is_active": True}))
    cliente.post(f"/api/admin/soporte/casos/{caso['caso_id']}/tomar")
    r = cliente.post(f"/api/admin/soporte/casos/{caso['caso_id']}/mensajes",
                     json={"mensaje": "Seguí tu envío en https://risappbr.com/seguimiento"})
    assert r.status_code == 200, r.text


def test_el_cliente_no_puede_adjuntar_una_direccion_de_internet():
    cliente, actual, base = _mesa()
    actual["u"] = CLIENTA
    r = cliente.post("/api/soporte/casos", json={
        "motivo": "envio", "mensaje": "Adjunto el comprobante",
        "adjunto": "https://servidor-del-atacante.com/rastreo.png"})
    assert r.status_code == 400, r.text
    assert "dispositivo" in r.json()["detail"]


def test_una_foto_de_verdad_se_guarda_ya_limpia():
    cliente, actual, base = _mesa()
    actual["u"] = CLIENTA
    r = cliente.post("/api/soporte/casos", json={
        "motivo": "envio", "mensaje": "Adjunto el comprobante",
        "adjunto": _como_data(_png())})
    assert r.status_code == 200, r.text

    async def revisar():
        msg = await base.soporte_mensajes.find_one({}, {"_id": 0})
        assert msg["adjunto"].startswith("data:image/png;base64,")

    _ya(revisar())
