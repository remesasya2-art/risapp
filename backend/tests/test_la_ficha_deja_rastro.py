"""La ficha de un cliente: se descarga del servidor, y queda asentado quién.

QUE HABIA ANTES

    Un botón en el panel armaba un PDF con los datos del cliente y lo SUBIA A
    GOOGLE DRIVE. Tres cosas de eso estaban mal:

    1. Los datos salían del sistema a una cuenta de Google. Aunque sea la del
       dueño, es otro lugar: no lo alcanza el cofre, no lo alcanza la tabla de
       permisos, y no queda en la auditoría.

    2. El token de Google quedaba guardado en la base y NO VENCE. Una
       credencial permanente hacia un Drive ajeno, adentro de la base de una
       app financiera.

    3. Se guardaba dos veces: a nombre del administrador que conectó, y bajo
       la clave `"global"`. Al subir, si el administrador no tenía las suyas,
       caía a las `"global"`. O sea que la primera persona que conectó su
       Drive quedó como destino por omisión de todo el equipo.

    Y no dejaba rastro en ningún lado: no había forma de saber quién se llevó
    la ficha de qué cliente, ni cuándo.

LO QUE SE PRUEBA ACA

    1. Que no quede nada de Google Drive en el código.
    2. Que la descarga escriba una línea de auditoría, con el actor y el
       cliente, ANTES de mandar el archivo.
    3. Que la ruta pida un permiso PROPIO, y no el de ver el KYC: mirar la
       ficha en pantalla y llevársela en un archivo no son lo mismo.
    4. Que la ficha NO lleve las fotos del documento ni la selfie.

POR QUE EL PUNTO 4 SE PRUEBA, SI YA ERA ASI

    Porque era así por casualidad. El generador busca las imágenes en el
    documento de `users`, y el KYC las guarda en `verifications`: nunca las
    encontraba y las salteaba en silencio. Alguien que vea ese código de aquí
    a un año lo va a leer como un defecto y lo va a «arreglar».

    Una ficha con el documento y la selfie de alguien es un archivo con el
    que se puede abrir una cuenta a nombre de esa persona. Este test convierte
    la casualidad en una decisión.
"""
import ast
import asyncio
import os
import pathlib
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)
_RAIZ = pathlib.Path(_BACKEND, "..").resolve()

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from starlette.requests import Request as PedidoReal                # noqa: E402

from conftest import usar_base, ensenarle_decimal128_a_mongomock    # noqa: E402
from models.user import User                                        # noqa: E402
from services import auditoria, permisos                            # noqa: E402
from services import ficha_del_cliente                              # noqa: E402
from services import perfil                                         # noqa: E402

ensenarle_decimal128_a_mongomock()

def _foto_de_verdad() -> str:
    """Una foto que la librería de imágenes ACEPTE.

    Acá había un PNG de 1×1 escrito a mano, y no servía: PIL lo rechazaba con
    «broken data stream», el generador salteaba la imagen en silencio y la
    ficha quedaba chica igual. O sea que el test de abajo pasaba aunque las
    fotos SI hubieran entrado —comprobado rompiendo el código a propósito y
    viéndolo seguir en verde—.

    Una foto que no se puede dibujar no prueba nada sobre un PDF que dibuja
    fotos.
    """
    import base64
    import io
    from PIL import Image as PILImage
    # Con ruido, no de un color liso: un JPEG de un color sólido comprime a
    # casi nada y el PDF apenas engorda, con lo cual un umbral de tamaño no
    # distingue «entró la foto» de «no entró».
    img = PILImage.new("RGB", (300, 300))
    img.putdata([((x * 7) % 256, (y * 13) % 256, (x * y) % 256)
                 for y in range(300) for x in range(300)])
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


FOTO = _foto_de_verdad()


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_ficha"]
    usar_base(b)
    yield b


# La PLANTILLA, que es lo que FastAPI pone en `scope["route"].path` y lo que
# la tabla de permisos compara. Con el camino concreto —`.../u1/ficha`— no
# matchea ninguna entrada y la tabla falla cerrado, que es lo correcto de su
# parte y un error del test.
PLANTILLA = "/api/admin/users/{user_id}/ficha"


def pedido(camino="/api/admin/users/u1/ficha", plantilla=PLANTILLA):
    r = PedidoReal({
        "type": "http", "method": "GET", "path": camino, "query_string": b"",
        "headers": [(b"x-forwarded-for", b"10.0.0.7"), (b"user-agent", b"test")],
        "client": ("10.0.0.7", 0),
    })

    class _Ruta:
        path = plantilla
    r.scope["route"] = _Ruta()
    return r


# ══════════════════════════════════════════════════════════════════════════
# 1. Que no quede nada de Drive
# ══════════════════════════════════════════════════════════════════════════

def _archivos_del_proyecto():
    for sub, patron in (("backend", "*.py"), ("frontend/src", "*.jsx"),
                        ("frontend/src", "*.js")):
        raiz = _RAIZ / sub
        if not raiz.is_dir():
            continue
        for p in raiz.rglob(patron):
            rel = p.relative_to(_RAIZ).as_posix()
            if "/venv/" in rel or "node_modules" in rel or "/tests/" in rel:
                continue
            yield rel, p.read_text(encoding="utf-8", errors="ignore")


def test_no_quedo_nada_de_google_drive():
    HUELLAS = ("oauth/drive", "drive_credentials", "googleapis.com/auth/drive",
               "upload-kyc", "drive_kyc_link", "DriveCallback")
    encontradas = []
    for rel, fuente in _archivos_del_proyecto():
        for huella in HUELLAS:
            if huella in fuente:
                encontradas.append(f"{rel}: «{huella}»")
    assert not encontradas, (
        "Volvió a aparecer algo de Google Drive:\n\n"
        + "\n".join(f"    {x}" for x in encontradas)
        + "\n\nLos datos de los clientes no salen a una cuenta de Google. La "
          "ficha se descarga del servidor y queda asentada en la auditoría."
    )


def test_el_recorrido_mira_de_verdad_los_dos_lados():
    """Sin esto, el de arriba pasaría si el recorrido no encontrara archivos."""
    vistos = [rel for rel, _ in _archivos_del_proyecto()]
    assert sum(1 for r in vistos if r.startswith("backend/")) >= 100, vistos[:5]
    assert sum(1 for r in vistos if r.startswith("frontend/")) >= 20, vistos[:5]


# ══════════════════════════════════════════════════════════════════════════
# 2. El rastro
# ══════════════════════════════════════════════════════════════════════════

def test_descargar_la_ficha_deja_una_linea_en_la_auditoria(base):
    async def cuerpo():
        await base.users.insert_one({
            "user_id": "u1", "email": "ana@ejemplo.com", "name": "Ana Ribeiro",
            "full_name": "Ana Ribeiro", "cpf_number": "12345678901",
            "role": "user", "verification_status": "verified",
        })
        from routes import admin as ra
        quien = User(user_id="sa_1", email="jefa@ejemplo.com", name="Jefa",
                     role="super_admin")
        r = await ra.descargar_ficha_del_cliente("u1", pedido(), admin=quien)

        assert r.media_type == "application/pdf"
        assert r.body[:5] == b"%PDF-"

        lineas = await base.auditoria.find({}).to_list(10)
        assert len(lineas) == 1, f"se escribieron {len(lineas)} líneas"
        linea = lineas[0]
        assert linea["accion"] == "kyc.ficha_descargada"
        assert linea["actor"]["user_id"] == "sa_1"
        assert linea["objetivo"]["id"] == "u1"
        assert "Ana" in str(linea["objetivo"]["descripcion"])
    corre(cuerpo())


def test_la_linea_se_escribe_ANTES_de_mandar_el_archivo():
    """Al revés, una descarga que se corta a la mitad se lleva los datos igual
    y no queda anotada."""
    fuente = pathlib.Path(_BACKEND, "routes", "admin.py").read_text()
    arbol = ast.parse(fuente)
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.AsyncFunctionDef)
              and n.name == "descargar_ficha_del_cliente")
    cuerpo = ast.unparse(fn)
    assert cuerpo.index("kyc.ficha_descargada") < cuerpo.index("ficha_del_cliente.armar"), (
        "la auditoría quedó DESPUES de armar el archivo")


def test_de_un_cliente_que_no_existe_no_se_baja_nada(base):
    async def cuerpo():
        from routes import admin as ra
        quien = User(user_id="sa_1", email="jefa@ejemplo.com", name="Jefa",
                     role="super_admin")
        with pytest.raises(Exception) as e:
            await ra.descargar_ficha_del_cliente("no_existe", pedido(), admin=quien)
        assert getattr(e.value, "status_code", None) == 404
        assert await base.auditoria.count_documents({}) == 0
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 3. El permiso, propio
# ══════════════════════════════════════════════════════════════════════════

def test_la_ficha_pide_su_propio_permiso():
    """Ver la ficha en pantalla y LLEVARSELA no son lo mismo."""
    p = permisos.permiso_de("GET", PLANTILLA)
    assert p == "kyc.ficha", f"la ruta pide «{p}»"
    assert p != "kyc.view", "descargar no puede ir con el permiso de mirar"
    assert "kyc.ficha" in permisos.CATALOGO


def test_un_colaborador_que_solo_mira_no_se_lleva_la_ficha():
    quien = User(user_id="c1", email="operador@ejemplo.com", name="Operador",
                 role="admin", permissions=["kyc.view"])
    with pytest.raises(permisos.SinPermiso):
        permisos.exigir(quien, pedido())


def test_con_el_permiso_puesto_si_pasa():
    quien = User(user_id="c2", email="jefa@ejemplo.com", name="Jefa",
                 role="admin", permissions=["kyc.ficha"])
    permisos.exigir(quien, pedido())       # no levanta


def test_la_accion_esta_declarada_en_el_libro():
    assert "kyc.ficha_descargada" in auditoria.ACCIONES


# ══════════════════════════════════════════════════════════════════════════
# 4. La ficha no lleva el documento ni la selfie
# ══════════════════════════════════════════════════════════════════════════

def test_la_ficha_no_lleva_las_fotos_del_kyc(base):
    """El KYC las guarda en `verifications`, no en `users`, y la ruta lee
    `users`. Era casualidad; acá se vuelve una decisión."""
    async def cuerpo():
        await base.users.insert_one({
            "user_id": "u1", "email": "ana@ejemplo.com", "name": "Ana",
            "full_name": "Ana Ribeiro", "cpf_number": "12345678901",
        })
        # El KYC, con sus fotos, donde de verdad vive.
        await base.verifications.insert_one({
            "verification_id": "v1", "user_id": "u1",
            "id_document_image": FOTO, "cpf_image": FOTO, "selfie_image": FOTO,
        })
        from routes import admin as ra
        quien = User(user_id="sa_1", email="jefa@ejemplo.com", name="Jefa",
                     role="super_admin")
        r = await ra.descargar_ficha_del_cliente("u1", pedido(), admin=quien)

        # SE COMPARA CONTRA UNA FICHA SIN FOTOS, no contra un umbral fijo.
        #
        # Un umbral no servía: la primera versión usaba un JPEG de un color
        # liso, que comprime a casi nada, y el PDF engordaba tan poco que el
        # test pasaba aunque las fotos SI entraran. Se descubrió rompiendo el
        # código a propósito —haciendo que la ruta leyera `verifications`— y
        # viendo el test seguir en verde.
        #
        # Comparar contra la misma ficha sin fotos no depende de cuánto
        # comprima una imagen: si entrara aunque sea una, el tamaño cambia.
        # Con la MISMA proyección que usa la ruta. Con `{"_id": 0}` el
        # documento trae otros campos, el PDF sale con otro texto y la
        # comparación fallaba por seis bytes que no eran ninguna foto.
        como_lo_lee_la_ruta = await base.users.find_one(
            {"user_id": "u1"}, perfil.LO_QUE_VE_EL_PANEL)
        sin_fotos = ficha_del_cliente.armar(como_lo_lee_la_ruta)

        # Y que el test PUEDA notarlo: la misma foto, puesta a mano, tiene que
        # cambiar el tamaño. Si no, no está probando nada.
        con_una = ficha_del_cliente.armar({**como_lo_lee_la_ruta, "picture": FOTO})
        assert len(con_una) != len(sin_fotos), (
            "la foto de prueba no cambia el tamaño del PDF: este test no "
            "puede notar que le entren las del KYC")

        assert len(r.body) == len(sin_fotos), (
            f"la ficha pesa {len(r.body)} bytes y sin fotos pesaría "
            f"{len(sin_fotos)}: le entraron las fotos del KYC")
    corre(cuerpo())


def test_la_ficha_si_lleva_los_datos(base):
    """La otra mitad: que no se haya vaciado de contenido."""
    crudo = ficha_del_cliente.armar({
        "full_name": "Ana Ribeiro", "email": "ana@ejemplo.com",
        "cpf_number": "12345678901", "document_number": "RNM123",
        "phone_number": "+5511999", "verification_status": "verified",
        "role": "user", "created_at": "2026-01-01", "email_verified": True,
    })
    assert crudo[:5] == b"%PDF-"
    assert len(crudo) > 800, "la ficha salió vacía"


def test_la_ficha_no_queda_en_el_disco_del_servidor():
    """Devuelve bytes, no una ruta a un archivo. En Railway el disco se borra
    en cada despliegue, y un temporal que nadie borra son datos de un cliente
    tirados en el servidor."""
    fuente = pathlib.Path(_BACKEND, "services", "ficha_del_cliente.py").read_text()
    arbol = ast.parse(fuente)
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "armar")
    assert "mktemp" not in ast.unparse(fn), (
        "la ficha volvió a escribirse en el disco del servidor")
