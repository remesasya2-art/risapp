"""Los cuatro rechazos (4xx) que sí se guardan en «Errores», y el freno.

QUE PASABA

    «Errores» guardaba los 500 y nada más. Los 429 de los límites de dinero
    —los que se pusieron justamente para que nadie vacíe una cuenta a fuerza
    de pedidos— no se veían en ningún lado: `slowapi` registra su propio
    manejador y Starlette elige el MAS ESPECIFICO, así que el de la
    aplicación no los veía pasar. Y los intentos de contraseña fallidos no
    quedaban asentados en ninguna parte.

LO QUE SE PRUEBA

    1. Que se elijan los cuatro rechazos y NINGUN otro: el 400, el 404 y el
       409 no entran, y un 401 fuera de las puertas de ingreso tampoco.
    2. Que el freno frene: una sola línea por ventana, por más rechazos que
       lleguen, y recién al llegar al umbral.
    3. Que la memoria del freno no crezca sin fin.
    4. Que el manejador del 429 sea el de la aplicación y no el de `slowapi`,
       y que igual devuelva la misma respuesta.
    5. Que las puertas de ingreso nombradas existan de verdad.
    6. Que nunca levante: es el manejador de errores el que lo llama.
"""
import asyncio
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base                                      # noqa: E402
from services import rechazos                                       # noqa: E402

AHORA = 1_800_000_000.0


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_rechazos"]
    usar_base(b)
    yield b


@pytest.fixture(autouse=True)
def memoria_limpia():
    """El contador del freno es global (lo comparten todos los pedidos del
    proceso); entre tests se vacía para que uno no arrastre lo del anterior."""
    rechazos._contados.clear()
    yield
    rechazos._contados.clear()


async def _anotar(base, situacion, clave="1.2.3.4", ahora=AHORA, status=401):
    return await rechazos.anotar_si_importa(
        base, situacion=situacion, clave=clave, rastro="r-1", metodo="POST",
        ruta="/api/auth/login-password", status=status, ahora=ahora)


# ══════════════════════════════════════════════════════════════════════════
# 1. Cuáles se eligen, y cuáles no
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("status,ruta,esperado", [
    (401, "/api/auth/login-password", "ingreso_rechazado"),
    (401, "/api/auth/2fa/verify", "ingreso_rechazado"),
    (401, "/api/webauthn/login/verify", "ingreso_rechazado"),
    (403, "/api/admin/rrhh", "panel_sin_permiso"),
    (423, "/api/pin/verify", "pin_bloqueado"),
])
def test_los_rechazos_que_cuentan_una_historia(status, ruta, esperado):
    assert rechazos.que_situacion(status, ruta) == esperado


@pytest.mark.parametrize("status,ruta", [
    # El 400 es el formulario diciendo que no: 185 sitios en el código.
    (400, "/api/envios/cotizar"),
    (404, "/api/transactions/{transaction_id}"),
    (409, "/api/beneficiaries"),
    # Un 401 fuera de las puertas es una SESION VENCIDA, que pasa todo el día.
    (401, "/api/transactions"),
    (401, "/api/auth/heartbeat"),
    (401, "/api/auth/me"),
    # Un 403 de cliente es el sistema andando bien.
    (403, "/api/envios/crear"),
])
def test_los_rechazos_que_son_ruido_NO_entran(status, ruta):
    assert rechazos.que_situacion(status, ruta) is None


def test_el_429_no_se_elige_por_el_numero():
    """El piso de peticiones también devuelve 429 y se anota solo. Elegirlo
    por el número mezclaría los dos y el registro diría cualquier cosa."""
    assert rechazos.que_situacion(429, "/api/reais/send") is None


# ══════════════════════════════════════════════════════════════════════════
# 2. El freno
# ══════════════════════════════════════════════════════════════════════════

def test_una_contrasena_errada_no_se_anota(base):
    """Errar una contraseña es normal. Anotar la primera convierte el
    registro en el diario de los dedos gordos de todo el mundo."""
    async def cuerpo():
        assert await _anotar(base, "ingreso_rechazado") is False
        assert await base.errores.count_documents({}) == 0
    corre(cuerpo())


def test_al_quinto_intento_se_anota_UNA_sola_vez(base):
    async def cuerpo():
        anotados = [await _anotar(base, "ingreso_rechazado") for _ in range(12)]
        assert anotados.count(True) == 1, "salió más de una línea por ventana"
        assert anotados[4] is True, "no salió justo al llegar al umbral"
        assert await base.errores.count_documents({}) == 1
        linea = await base.errores.find_one({}, {"_id": 0})
        assert linea["tipo"] == "rechazo.ingreso_rechazado"
        assert linea["status"] == 401
        assert "5 en 1 h" in linea["mensaje"], linea["mensaje"]
    corre(cuerpo())


def test_dos_conexiones_distintas_no_se_suman(base):
    """Sumarlas haría que cinco personas distintas erréndole una vez cada una
    se lea como alguien probando contraseñas."""
    async def cuerpo():
        for i in range(4):
            await _anotar(base, "ingreso_rechazado", clave=f"ip_{i}")
        for i in range(4):
            await _anotar(base, "ingreso_rechazado", clave=f"ip_{i}")
        assert await base.errores.count_documents({}) == 0
    corre(cuerpo())


def test_la_ventana_nueva_vuelve_a_empezar(base):
    async def cuerpo():
        for _ in range(5):
            await _anotar(base, "ingreso_rechazado")
        assert await base.errores.count_documents({}) == 1
        # Una hora más tarde: otra ventana, y hace falta llegar al umbral otra vez.
        for _ in range(4):
            await _anotar(base, "ingreso_rechazado", ahora=AHORA + 3600)
        assert await base.errores.count_documents({}) == 1
        await _anotar(base, "ingreso_rechazado", ahora=AHORA + 3600)
        assert await base.errores.count_documents({}) == 2
    corre(cuerpo())


def test_el_limite_de_dinero_se_anota_al_primero(base):
    """Que salte un límite de dinero ES la noticia: no hace falta que se
    repita para que valga la pena mirarlo."""
    async def cuerpo():
        assert await _anotar(base, "limite_de_dinero", status=429) is True
        assert await _anotar(base, "limite_de_dinero", status=429) is False
        assert await base.errores.count_documents({}) == 1
        linea = await base.errores.find_one({}, {"_id": 0})
        assert "1 en 1 min" in linea["mensaje"], linea["mensaje"]
    corre(cuerpo())


def test_la_memoria_del_freno_no_crece_sin_fin():
    """Cada conexión nueva que erra una contraseña es una clave más. Una
    tanda de miles las dejaba todas adentro para siempre."""
    for i in range(rechazos._MAX_EN_MEMORIA + 50):
        rechazos._sumar_y_ver_si_toca("ingreso_rechazado", f"ip_{i}", AHORA - 99999)
    rechazos._sumar_y_ver_si_toca("ingreso_rechazado", "ip_nueva", AHORA)
    assert len(rechazos._contados) < 100, "no se olvidó lo viejo"


@pytest.mark.parametrize("situacion", [
    "inventada",                       # un nombre con un error de tipeo
    ["no", "se", "puede", "buscar"],   # algo que ni siquiera se puede buscar
])
def test_una_situacion_que_no_existe_no_anota_nada_y_no_levanta(base, situacion):
    """Los dos casos caen en el MISMO `try`, y por eso están en un solo test.

    Antes había además una comprobación explícita contra el catálogo. Se
    comprobó rompiéndola y no ponía nada en rojo: la tapaba este `try`. Dos
    tests dando a entender que hay dos guardas serían dos tests mintiendo.
    """
    async def cuerpo():
        assert await _anotar(base, situacion) is False
        assert await base.errores.count_documents({}) == 0
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 3. Nunca levanta
# ══════════════════════════════════════════════════════════════════════════

def test_si_la_base_falla_NO_levanta():
    """Corre dentro del manejador de errores: si esto revienta, revienta la
    respuesta que el usuario estaba esperando.

    Devuelve `True` con la base caída, y está bien: lo que devuelve es «el
    freno lo dejó pasar», no «se escribió». `errores.anotar` se traga el
    fallo de escritura —tiene que hacerlo, es el último que queda de pie—,
    así que desde acá no hay forma de saber si llegó a la base.
    """
    class _Rota:
        def __getitem__(self, _):
            raise RuntimeError("base caída")

    async def cuerpo():
        assert await _anotar(_Rota(), "limite_de_dinero", status=429) is True
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 4. El enganche en la aplicación
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def aplicacion():
    try:
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    return app


def test_el_429_lo_maneja_la_aplicacion_y_no_slowapi(aplicacion):
    """`RateLimitExceeded` ES una excepción HTTP, pero Starlette elige el
    manejador MAS ESPECIFICO: con el de `slowapi` registrado, el de la
    aplicación no lo veía pasar y esos 429 no llegaban a «Errores»."""
    from slowapi.errors import RateLimitExceeded
    from starlette.exceptions import HTTPException as SHE
    assert issubclass(RateLimitExceeded, SHE), "la trampa era justamente ésta"
    manejador = aplicacion.exception_handlers.get(RateLimitExceeded)
    assert manejador is not None, "nadie maneja el 429"
    assert manejador.__name__ == "_paso_del_limite", manejador.__name__


def test_las_puertas_de_ingreso_existen_de_verdad(aplicacion):
    """Una puerta mal escrita no excluye ni incluye nada: los 401 de esa
    ruta se pierden sin que nadie se entere."""
    from fastapi.routing import APIRoute
    vivas = {r.path for r in aplicacion.routes if isinstance(r, APIRoute)}
    assert len(vivas) > 100
    muertas = sorted(p for p in rechazos.PUERTAS_DE_INGRESO if p not in vivas)
    assert not muertas, muertas


def test_ninguna_puerta_de_ingreso_es_del_panel():
    """Serían dos reglas sobre la misma ruta diciendo cosas distintas."""
    assert not [p for p in rechazos.PUERTAS_DE_INGRESO
                if p.startswith(rechazos.RUTAS_DEL_PANEL)]


def test_de_punta_a_punta_cinco_contrasenas_erradas_dejan_UNA_linea():
    """El enganche de verdad: un pedido real contra la puerta de ingreso, con
    el manejador de errores de la aplicación en el medio.

    Sin esto, los tests de arriba prueban el servicio y nadie prueba que el
    manejador lo llame: se puede quitar la llamada entera de `server.py` y
    todo sigue en verde.
    """
    try:
        import server
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    from fastapi.testclient import TestClient

    b = mongomock_motor.AsyncMongoMockClient()["ris_rechazos_e2e"]
    usar_base(b)
    anterior, server.db = server.db, b
    try:
        with TestClient(server.app) as cliente:
            for _ in range(5):
                r = cliente.post("/api/auth/login-password",
                                 json={"email": "nadie@ejemplo.com",
                                       "password": "loquesea"})
                assert r.status_code == 401, r.text
        cuantas = asyncio.run(b.errores.count_documents({}))
        assert cuantas == 1, f"quedaron {cuantas} líneas, tenía que quedar una"
        linea = asyncio.run(b.errores.find_one({}, {"_id": 0}))
        assert linea["tipo"] == "rechazo.ingreso_rechazado"
        assert linea["ruta"] == "/api/auth/login-password"
        assert linea["status"] == 401
    finally:
        server.db = anterior
