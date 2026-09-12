"""
tests/test_el_codigo_de_referido_llega.py — Que el enlace de invitar funcione.

EL DEFECTO QUE ESTE ARCHIVO CIERRA, Y QUE ESTUVO VIVO TODO ESTE TIEMPO

    La pantalla de registro lee el `?ref=` de la dirección, lo pone en
    mayúsculas y lo manda al servidor. Eso estaba bien hecho desde el
    principio. Pero lo mandaba con el nombre `referral_code`, y el modelo del
    servidor declaraba el campo como `referred_by`.

    Lo que hace Pydantic con un campo que no conoce es IGNORARLO. No levanta,
    no devuelve 400, no escribe nada en el registro. Así que `referred_by`
    llegaba en `None` siempre:

        >>> RegisterUserRequest(name="Ana", email="a@example.com",
        ...                     password="X", confirm_password="X",
        ...                     referral_code="REF3A9F2B01").referred_by
        None

    Consecuencia: el enlace de referido NUNCA funcionó. Cada persona que se
    registró entrando por el enlace de otra quedó guardada como si hubiera
    llegado sola, y el dato no se escribió en ninguna parte, así que tampoco
    se puede recuperar hacia atrás.

    Un nombre distinto de un lado y del otro, y silencio. No hay error que
    mirar, no hay alerta que suene. Por eso la guarda que más importa de este
    archivo no prueba una función: prueba que LOS DOS LADOS SIGAN DE ACUERDO.

COMO SE VIGILA QUE NO VUELVA A PASAR

    `test_el_servidor_acepta_todos_los_campos_que_manda_la_pantalla` abre el
    archivo del frontend, saca los nombres de los campos que le manda a
    `/auth/register`, y exige que el modelo acepte cada uno.

    Lee el archivo de verdad y no una copia de los nombres escrita acá, porque
    una copia escrita a mano se desactualiza exactamente igual que se
    desactualizó el original: sería el mismo defecto, movido de lugar.

    Y trae su propia comprobación: si el extractor dejara de encontrar los
    campos —porque alguien reescribe la llamada de otra forma—, el test se
    pondría verde por no tener nada que revisar. Eso es lo peor que le puede
    pasar a una guarda, así que `test_el_extractor_de_campos_sirve` falla si
    el extractor devuelve poco o no encuentra el campo del código.
"""
import os
import pathlib
import re
import sys

import pytest

_BACKEND = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))

_REPO = _BACKEND.parent
PANTALLA_DE_REGISTRO = _REPO / "frontend" / "src" / "pages" / "Register.jsx"

from models.requests import RegisterUserRequest      # noqa: E402
from services import codigos                         # noqa: E402


DATOS_MINIMOS = {
    "name": "Ana",
    "email": "ana@example.com",
    "password": "Clave.larga1!",
    "confirm_password": "Clave.larga1!",
}


# ─── El modelo acepta el nombre que manda la pantalla ─────────────────────

def test_el_codigo_llega_con_el_nombre_QUE_MANDA_LA_PANTALLA():
    """La reproducción del defecto. Si esto se pone rojo, el enlace no paga."""
    pedido = RegisterUserRequest(**DATOS_MINIMOS, referral_code="REF3A9F2B01")
    assert pedido.referred_by == "REF3A9F2B01"


def test_el_codigo_llega_con_el_nombre_DE_LA_BASE():
    """`referred_by` es el nombre del campo en el documento del usuario.

    Lo usan los tests y los scripts, así que tiene que seguir entrando.
    """
    pedido = RegisterUserRequest(**DATOS_MINIMOS, referred_by="REF3A9F2B01")
    assert pedido.referred_by == "REF3A9F2B01"


def test_sin_codigo_el_campo_queda_vacio():
    assert RegisterUserRequest(**DATOS_MINIMOS).referred_by is None


# ─── La guarda: que los dos lados no se separen otra vez ──────────────────

def _campos_que_manda_la_pantalla() -> set[str]:
    """Los nombres de los campos del cuerpo de `api.post('/auth/register', …)`.

    Se hace con una expresión y no con un analizador de JavaScript porque en
    este entorno no hay ninguno, y agregar uno para leer un objeto literal
    sería traer una dependencia entera para nada. Lo que se extrae son las
    claves `nombre:` del bloque entre llaves que sigue a la llamada.
    """
    texto = PANTALLA_DE_REGISTRO.read_text(encoding="utf-8")
    llamada = re.search(
        r"""api\.post\(\s*['"]/auth/register['"]\s*,\s*\{(.*?)\}\s*\)""",
        texto, re.DOTALL)
    if llamada is None:
        return set()
    return set(re.findall(r"(\w+)\s*:", llamada.group(1)))


def test_el_extractor_de_campos_sirve():
    """La comprobación de la guarda: que tenga algo que revisar.

    Si el extractor devolviera vacío —porque alguien escribió la llamada de
    otra forma, o movió el registro a otro archivo—, el test de abajo pasaría
    por no tener nada que comparar. Una guarda que se pone verde cuando deja
    de mirar es peor que no tener guarda: da tranquilidad falsa.
    """
    assert PANTALLA_DE_REGISTRO.exists(), (
        f"No está {PANTALLA_DE_REGISTRO}. Si la pantalla de registro se movió, "
        "hay que apuntar este test al archivo nuevo.")
    campos = _campos_que_manda_la_pantalla()
    assert len(campos) >= 4, (
        "El extractor encontró casi nada en la llamada a /auth/register. "
        f"Encontró {sorted(campos)}. Revisá cómo está escrita la llamada en "
        f"{PANTALLA_DE_REGISTRO.name}.")
    assert any("ref" in c.lower() for c in campos), (
        "La pantalla ya no manda ningún campo con «ref» en el nombre. Si el "
        "código de invitación se dejó de mandar, este archivo entero dejó de "
        f"tener sentido. Campos encontrados: {sorted(campos)}.")


def test_el_servidor_acepta_todos_los_campos_que_manda_la_pantalla():
    """LA GUARDA QUE IMPORTA.

    Un campo que la pantalla manda y el modelo no declara se descarta en
    silencio. Eso es lo que dejó el enlace de referido sin funcionar, y no lo
    vio nadie porque no hay nada que ver.
    """
    campos = _campos_que_manda_la_pantalla()
    aceptados = set()
    for nombre, campo in RegisterUserRequest.model_fields.items():
        aceptados.add(nombre)
        alias = getattr(campo, "validation_alias", None)
        for elegido in getattr(alias, "choices", []) or ([alias] if alias else []):
            if isinstance(elegido, str):
                aceptados.add(elegido)

    ignorados = campos - aceptados
    assert not ignorados, (
        f"La pantalla de registro manda {sorted(ignorados)} y el servidor no "
        "declara esos nombres, así que Pydantic los DESCARTA EN SILENCIO. Es "
        "el mismo defecto que dejó el enlace de referido sin funcionar. "
        "Agregalos a RegisterUserRequest, o al AliasChoices de un campo que ya "
        "exista.")


# ─── La normalización, y por qué no alcanza `.strip()` ────────────────────

@pytest.mark.parametrize("escrito", [
    "REF3A9F2B01",
    "ref3a9f2b01",
    "  REF3A9F2B01  ",
    "REF 3A9F 2B01",
    "REF\t3A9F2B01",
])
def test_el_codigo_se_entiende_como_lo_pega_la_gente(escrito):
    """El código se comparte por WhatsApp y llega con espacios adentro.

    `.strip().upper()` —que era lo que había— sólo saca los espacios de las
    puntas, así que «REF 3A9F 2B01» quedaba guardado con los espacios y no
    coincidía con ningún código de la base.
    """
    assert codigos.normalizar(escrito) == "REF3A9F2B01"


def test_normalizar_no_inventa_un_codigo_donde_no_hay():
    for vacio in ("", "   ", None):
        assert codigos.normalizar(vacio) == ""


# ─── La ruta de registro, contra una base simulada ────────────────────────
#
# Hasta acá se probó el modelo y la normalización, que es donde estaba el
# defecto. Lo que sigue prueba la decisión nueva: un código que no existe se
# RECHAZA, en vez de guardarse o ignorarse.
#
# Ignorarlo era lo que pasaba de hecho, y es la peor de las tres salidas: el
# que se registró por el enlace de un amigo pierde su bono, el amigo pierde el
# suyo, y ninguno de los dos se entera nunca.

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from fastapi import FastAPI                            # noqa: E402
from fastapi.testclient import TestClient              # noqa: E402

from conftest import usar_base                         # noqa: E402
from routes import auth as rutas_auth                  # noqa: E402
from routes import security_2fa                        # noqa: E402


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


@pytest.fixture
def cliente(base, monkeypatch):
    """La ruta de registro montada sola, sin correo y sin limitador.

    El correo se sustituye porque mandarlo de verdad desde la suite le
    escribiría a una casilla ajena; ya pasó en este repositorio.

    El limitador se vacía entre tests porque el cupo del registro es de diez
    por hora y por IP, y con `TestClient` todos los pedidos vienen de la misma
    IP. Sin esto, el test número once falla por el cupo y no por lo que mira,
    que es la forma más confusa de un rojo.
    """
    async def sin_correo(*a, **k):
        return True
    monkeypatch.setattr(rutas_auth, "send_verification_email", sin_correo)

    try:
        security_2fa.limiter.limiter.storage.reset()
    except Exception:
        # No todas las versiones de `limits` traen `reset` en su almacenamiento
        # en memoria. Si no está, los pocos registros de este archivo entran
        # holgados en el cupo de diez.
        pass

    app = FastAPI()
    app.include_router(rutas_auth.router, prefix="/api")
    return TestClient(app)


def _cuerpo(email, **extra):
    return {"name": "Ana", "email": email,
            "password": "Clave.larga1!", "confirm_password": "Clave.larga1!",
            **extra}


async def _leer_pendiente(base, email):
    return await base.pending_verifications.find_one({"email": email})


def test_un_codigo_que_no_existe_se_rechaza(cliente):
    r = cliente.post("/api/auth/register",
                     json=_cuerpo("nueva@example.com", referral_code="REFINVENTADO"))
    assert r.status_code == 400, r.text
    assert "no existe" in r.json()["detail"].lower()


def test_el_registro_sin_codigo_sigue_funcionando(cliente):
    """Que la guarda nueva no le cierre la puerta a quien llega solo."""
    r = cliente.post("/api/auth/register", json=_cuerpo("sola@example.com"))
    assert r.status_code == 200, r.text


def test_un_codigo_valido_se_guarda_normalizado(base, cliente):
    import asyncio

    async def preparar():
        await base.users.insert_one({
            "user_id": "user_quien_refiere",
            "email": "quien.refiere@example.com",
            "referral_code": "REF3A9F2B01",
        })
    asyncio.run(preparar())

    # Se manda como lo pega alguien desde WhatsApp: minúsculas y un espacio.
    r = cliente.post("/api/auth/register",
                     json=_cuerpo("invitada@example.com",
                                  referral_code="ref 3A9F2B01"))
    assert r.status_code == 200, r.text

    guardado = asyncio.run(_leer_pendiente(base, "invitada@example.com"))
    assert guardado is not None, "no se creó la verificación pendiente"
    assert guardado["referred_by"] == "REF3A9F2B01", (
        "El código quedó guardado sin normalizar, así que no va a coincidir "
        "con ningún código de la base.")


def test_el_codigo_vacio_se_guarda_como_nada_y_no_como_cadena_vacia(base, cliente):
    """Un `""` y un `None` conviven mal: la mitad del código pregunta por uno
    y la otra mitad por el otro. Se guarda `None` y se termina la duda."""
    import asyncio
    r = cliente.post("/api/auth/register",
                     json=_cuerpo("vacia@example.com", referral_code="   "))
    assert r.status_code == 200, r.text
    guardado = asyncio.run(_leer_pendiente(base, "vacia@example.com"))
    assert guardado["referred_by"] is None


# ─── La pantalla no promete plata que la aplicación no sabe pagar ─────────

PROMESAS_QUE_NO_SE_PUEDEN_CUMPLIR = (
    # Lo decía el navegador apenas la persona escribía una letra, mientras el
    # servidor rechazaba ese mismo código con un 400. El cartel verde y el
    # error rojo aparecían juntos en la misma pantalla.
    "código aplicado",
    "codigo aplicado",
    # El bono de bienvenida todavía no está construido.
    "bonificación",
    "bonificacion",
)


def _sin_comentarios(codigo: str) -> str:
    """El archivo sin sus comentarios.

    Hace falta porque los comentarios SI pueden nombrar lo que se sacó y por
    qué —son para quien lee el archivo, no para quien usa la aplicación— y el
    comentario que explica este cambio cita el cartel viejo palabra por
    palabra. Sin limpiar, la guarda se acusa a sí misma.

    Se saca primero el bloque `/* ... */`, que es el que usa JSX escrito como
    `{/* ... */}`. Después las líneas que EMPIEZAN con `//`: buscar `//` en
    cualquier posición borraría media URL, y este archivo tiene varias.
    """
    limpio = re.sub(r"/\*.*?\*/", " ", codigo, flags=re.DOTALL)
    return "\n".join(l for l in limpio.splitlines()
                     if not l.lstrip().startswith("//"))


def test_el_limpiador_de_comentarios_sirve():
    """La comprobación de la guarda de abajo.

    Si el limpiador dejara de reconocer los comentarios de JSX, la guarda se
    pondría roja por su propio comentario y alguien la borraría por molesta.
    Y si los borrara de más —tragándose el código— se pondría verde por no
    tener nada que mirar. Se exige que haga las dos cosas bien.
    """
    crudo = PANTALLA_DE_REGISTRO.read_text(encoding="utf-8")
    limpio = _sin_comentarios(crudo)
    assert "DECIA" not in limpio, (
        "El limpiador no sacó el comentario de JSX que explica este cambio. "
        "La guarda de abajo va a acusar al comentario en vez del cartel.")
    assert "register-referral-input" in limpio, (
        "El limpiador se comió código: el campo del código de invitación "
        "tiene que seguir estando después de limpiar.")


def test_la_pantalla_de_registro_no_promete_un_bono_que_no_existe():
    """Una promesa de plata escrita a mano en la pantalla.

    Cuando el bono exista, los montos se van a leer de la configuración del
    panel —no de un texto— y este test hay que cambiarlo para exigir eso, no
    para borrarlo. Mientras el bono no esté, un cartel que lo anuncia es algo
    que después hay que explicarle a un cliente.
    """
    vivo = _sin_comentarios(
        PANTALLA_DE_REGISTRO.read_text(encoding="utf-8")).lower()
    encontradas = [f for f in PROMESAS_QUE_NO_SE_PUEDEN_CUMPLIR if f in vivo]
    assert not encontradas, (
        f"La pantalla de registro promete {encontradas}. El bono de bienvenida "
        "todavía no está construido, y «código aplicado» lo decide el servidor "
        "—con un 400 si no existe—, no el navegador mientras se escribe.")
