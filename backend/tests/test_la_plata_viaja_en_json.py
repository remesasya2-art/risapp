"""
tests/test_la_plata_viaja_en_json.py — Que una respuesta con plata adentro no
se caiga con un 500.

QUE PASO

    La plata se guarda en Mongo como `Decimal128`, y el traductor a JSON de
    FastAPI no conoce ese tipo. Toda ruta que devuelva un documento tal como
    sale de la base se caía en cuanto ese documento tuviera un saldo:

        ValueError: [TypeError("'Decimal128' object is not iterable"), ...]

    `GET /api/admin/users` —la lista de usuarios del panel— estuvo caída desde
    el 3 de septiembre, el día en que el registro empezó a guardar `balance_ris`
    con este tipo. Las cuentas viejas tenían un número común, así que fallaba
    sólo si en la lista había alguna cuenta nueva. O sea: casi siempre, y sin
    que nadie supiera por qué.

POR QUE ESTAS PRUEBAS MIRAN EL COMPORTAMIENTO Y NO LA TABLA

    La red se pone agregando una entrada a `encoders_by_class_tuples`, que es
    una tabla INTERNA de FastAPI. El día que FastAPI la mueva, la red se cae
    sola y en silencio.

    Por eso acá no se comprueba que la tabla tenga la entrada —eso pasaría
    igual con la red rota— sino que un `Decimal128` de verdad SE SERIALICE. Si
    FastAPI cambia por dentro, esto se pone rojo al actualizar la librería, que
    es cuando arreglarlo es barato.
"""
import os
import sys
from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from fastapi import FastAPI                                     # noqa: E402
from fastapi.encoders import jsonable_encoder                   # noqa: E402
from fastapi.testclient import TestClient                       # noqa: E402

from conftest import usar_base                                  # noqa: E402
from models.user import User                                    # noqa: E402
from services import json_de_mongo                              # noqa: E402
from services.money import to_decimal128                        # noqa: E402


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


@pytest.fixture(autouse=True)
def con_la_red():
    """La red, puesta como la pone el servidor de verdad.

    No se saca al terminar: sacarla dejaría a los demás archivos de prueba
    corriendo sin ella, que es justo lo que no queremos que pase nunca.
    """
    json_de_mongo.ensenarle_decimal128_a_fastapi()


# ══════════════════════════════════════════════════════════════════════════
# 1. La red, probada por su comportamiento
# ══════════════════════════════════════════════════════════════════════════

def test_UN_DECIMAL128_SE_PUEDE_SERIALIZAR():
    """La prueba que se pondría roja si FastAPI mueve su tabla interna."""
    assert jsonable_encoder(to_decimal128("1234.56")) == 1234.56


def test_un_documento_entero_con_plata_adentro_se_serializa():
    """Como sale de la base: anidado, en listas, mezclado con lo demás."""
    documento = {
        "users": [
            {"user_id": "u1", "name": "Ana",
             "balance_ris": to_decimal128("150.25"),
             "balance_ves": to_decimal128(0),
             "kyc_quota": {"ops": 1, "ris": 120.5}},
        ],
        "total": 1,
    }
    salida = jsonable_encoder(documento)
    assert salida["users"][0]["balance_ris"] == 150.25
    assert salida["users"][0]["balance_ves"] == 0.0
    assert salida["total"] == 1


def test_LA_CRIPTO_NO_SE_REDONDEA_A_DOS_DECIMALES():
    """LA GUARDA QUE PROTEGE LOS SALDOS CHICOS.

    `to_float` redondea a dos decimales, que está bien para reales y es
    destructivo para cripto: 0,00123456 BTC saldría como 0,00.

    Un cero donde hay plata es PEOR que el error 500. El 500 se ve y alguien lo
    arregla; el cero se cree, y quien lo mire va a pensar que esa cuenta está
    vacía.
    """
    assert jsonable_encoder(Decimal128("0.00123456")) == 0.00123456
    assert jsonable_encoder(Decimal128("0.000000012")) == 0.000000012


def test_poner_la_red_dos_veces_no_la_duplica():
    """Los tests importan el servidor varias veces en el mismo proceso.

    Esto pasa porque la tabla se indexa por la función que convierte, y
    `_a_float` es siempre el mismo objeto — no porque haya una comprobación que
    lo impida. Hubo una, y se sacó: al romperla a propósito no se puso roja
    ninguna prueba, o sea que no estaba haciendo nada.

    El test se queda igual, contando lo que de verdad lo hace cierto.
    """
    from fastapi import encoders

    tabla = getattr(encoders, json_de_mongo.TABLA)
    antes = len(tabla)
    json_de_mongo.ensenarle_decimal128_a_fastapi()
    json_de_mongo.ensenarle_decimal128_a_fastapi()
    assert len(tabla) == antes
    assert sum(1 for clases in tabla.values() if Decimal128 in clases) == 1


def test_la_red_se_reconoce_a_si_misma():
    assert json_de_mongo.ya_esta_puesta() is True


# ══════════════════════════════════════════════════════════════════════════
# 2. Las rutas que se caían de verdad
# ══════════════════════════════════════════════════════════════════════════
#
# No alcanza con probar el traductor por su cuenta: lo que hay que probar es
# que la ruta que fallaba hoy conteste 200 con un usuario que tenga plata
# guardada como la guarda la aplicación.

def _un_usuario(user_id="u_ana", role="user"):
    return {
        "user_id": user_id,
        "name": "Ana Pereira",
        "email": "ana@ejemplo.com",
        "role": role,
        "is_active": True,
        "verification_status": "verified",
        # Así los escribe el registro desde el 3 de septiembre.
        "balance_ris": to_decimal128("150.25"),
        "balance_ves": to_decimal128(0),
        "balance_ris_bono": to_decimal128("15.00"),
        "password_hash": "no-se-devuelve",
    }


_QUIEN = {"actual": None}


@pytest.fixture
def cliente(base):
    from routes import admin as rutas_admin
    from routes import dependencies as deps

    app = FastAPI()
    app.include_router(rutas_admin.router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: _QUIEN["actual"]
    _QUIEN["actual"] = User(user_id="u_jefe", name="Jefe",
                            email="jefe@ejemplo.com", role="super_admin")
    return TestClient(app)


def test_LA_LISTA_DE_USUARIOS_DEL_PANEL_CONTESTA(base, cliente):
    """La ruta que estuvo caída diez días."""
    import asyncio

    async def sembrar():
        await base.users.insert_one(_un_usuario())
    asyncio.run(sembrar())

    r = cliente.get("/api/admin/users")
    assert r.status_code == 200, r.text
    usuarios = r.json()["users"]
    assert len(usuarios) == 1
    assert usuarios[0]["balance_ris"] == 150.25
    assert usuarios[0]["balance_ris_bono"] == 15.0


def test_la_lista_no_devuelve_la_contrasena(base, cliente):
    """De paso: lo que la ruta ya excluía tiene que seguir excluido.

    Un arreglo de serialización es exactamente el tipo de cambio que se lleva
    por delante una proyección sin que nadie lo note.
    """
    import asyncio

    async def sembrar():
        await base.users.insert_one(_un_usuario())
    asyncio.run(sembrar())

    r = cliente.get("/api/admin/users")
    assert r.status_code == 200
    assert "password_hash" not in r.json()["users"][0]


def test_la_ficha_de_un_usuario_contesta(base, cliente):
    import asyncio

    async def sembrar():
        await base.users.insert_one(_un_usuario())
    asyncio.run(sembrar())

    r = cliente.get("/api/admin/users/u_ana")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["balance_ris"] == 150.25


def test_LA_RUTA_QUE_DEVOLVIA_DOCUMENTOS_ENTEROS_YA_NO_ESTA(base, cliente):
    """`/verifications/pending` devolvía cada usuario pendiente entero, con la
    semilla del segundo factor y el hash del PIN. Ninguna pantalla la usaba y
    se sacó (ver el comentario en routes/admin.py). Si vuelve, que sea con un
    contrato: este test se pone rojo para que alguien lo mire."""
    import asyncio

    async def sembrar():
        doc = _un_usuario(user_id="u_pendiente")
        doc["verification_status"] = "pending"
        doc["two_factor_secret"] = "JBSWY3DPEHPK3PXP"
        await base.users.insert_one(doc)
    asyncio.run(sembrar())

    r = cliente.get("/api/admin/verifications/pending")
    assert r.status_code in (404, 405), r.text
    assert "JBSWY3DPEHPK3PXP" not in r.text


def test_SIN_LA_RED_LA_LISTA_SE_CAERIA(base):
    """La comprobación de que estas pruebas prueban algo.

    Se arma el mismo documento y se serializa SIN la red, a mano, para ver el
    error de producción con los ojos. Si esto dejara de fallar, las pruebas de
    arriba pasarían por el motivo equivocado y nadie se enteraría.
    """
    from fastapi import encoders

    tabla = getattr(encoders, json_de_mongo.TABLA)
    guardadas = {e: c for e, c in tabla.items() if Decimal128 in c}
    for encoder in guardadas:
        del tabla[encoder]
    try:
        assert json_de_mongo.ya_esta_puesta() is False
        with pytest.raises(ValueError) as fallo:
            jsonable_encoder({"users": [_un_usuario()]})
        assert "Decimal128" in str(fallo.value)
    finally:
        tabla.update(guardadas)
    assert json_de_mongo.ya_esta_puesta() is True


def test_el_servidor_pone_la_red_al_arrancar():
    """Que la función exista no sirve si nadie la llama.

    Se mira el código del arranque y no el estado del proceso, porque para
    cuando este test corre la red ya la pusieron otras pruebas.
    """
    import ast

    fuente = open(os.path.join(_BACKEND, "server.py"), encoding="utf-8").read()
    arbol = ast.parse(fuente)
    llamadas = [n for n in ast.walk(arbol)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "ensenarle_decimal128_a_fastapi"]
    assert llamadas, (
        "server.py no llama a ensenarle_decimal128_a_fastapi(). Sin esa "
        "llamada, toda ruta que devuelva un documento con plata adentro "
        "contesta 500.")

    # Y antes de importar las rutas: si se pusiera después, el traductor
    # quedaría sin conocer el tipo durante el armado de la aplicación.
    linea_llamada = min(n.lineno for n in llamadas)
    importa_rutas = [n.lineno for n in ast.walk(arbol)
                     if isinstance(n, ast.ImportFrom) and n.module == "routes"]
    assert importa_rutas and linea_llamada < min(importa_rutas), \
        "la red se pone después de importar las rutas"


def test_el_defecto_no_se_comio_la_precision_de_los_reales():
    """Dos decimales exactos, que es lo que la pantalla muestra."""
    assert jsonable_encoder(to_decimal128("0.01")) == 0.01
    assert jsonable_encoder(to_decimal128("99999.99")) == 99999.99
    assert Decimal(str(jsonable_encoder(to_decimal128("10.00")))) == Decimal("10")
