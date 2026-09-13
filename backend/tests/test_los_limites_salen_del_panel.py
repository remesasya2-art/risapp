"""
tests/test_los_limites_salen_del_panel.py — Las guardas del cambio que sacó los
límites de dinero de los archivos .py.

QUE CAMBIO, Y QUE PUEDE SALIR MAL

    Los límites de cada vía —el mínimo y el máximo de PIX, los de tarjeta, el
    piso en bolívares y el cupo de la cuenta sin verificar— estaban escritos a
    mano en tres archivos distintos. Ahora salen del catálogo del panel.

    El precio de eso es que cuatro funciones que eran puras pasaron a ser
    asíncronas y a pedir la base de datos. De ahí salen las tres guardas de este
    archivo, cada una para un modo de fallar distinto:

      1. QUE ALGUIEN SE OLVIDE EL `await`. En Python, una corrutina sin esperar
         es un objeto verdadero. `if error_monto:` sería siempre cierto y TODA
         operación se rechazaría con un mensaje absurdo. Ruidoso, sí — pero
         ruidoso en producción, que no es donde hay que enterarse.

      2. QUE ALGUIEN VUELVA A ESCRIBIR EL NUMERO EN EL CODIGO. Es el estado
         anterior, y es el que se siente natural cuando hace falta un límite
         nuevo y con prisa.

      3. QUE UN MINIMO QUEDE POR ENCIMA DE SU MAXIMO. Es la regla que ningún
         campo puede comprobar mirándose a sí mismo, y su consecuencia es que
         la vía entera deja de funcionar para todos.
"""
import ast
import asyncio
import os
import pathlib
import sys
from decimal import Decimal

import pytest

_BACKEND = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from fastapi import FastAPI                                 # noqa: E402
from fastapi.testclient import TestClient                   # noqa: E402

from conftest import usar_base                              # noqa: E402
from models.user import User                                # noqa: E402
from routes import configuracion as rutas                   # noqa: E402
from routes import dependencies as deps                     # noqa: E402
from services import configuracion as cfg                   # noqa: E402
from services import kyc_quota, limits                      # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


_QUIEN = {"actual": None}


@pytest.fixture
def cliente(base):
    app = FastAPI()
    app.include_router(rutas.router, prefix="/api")
    app.dependency_overrides[deps.get_current_user] = lambda: _QUIEN["actual"]
    _QUIEN["actual"] = User(user_id="u_jefe", name="Jefe",
                            email="jefe@example.com", role="super_admin")
    return TestClient(app)


# ══════════════════════════════════════════════════════════════════════════
# 1. El `await` que no se puede olvidar
# ══════════════════════════════════════════════════════════════════════════

# Las funciones que pasaron a ser asíncronas con este cambio. Si se agrega otra,
# va acá: es la lista de lo que esta guarda vigila.
LAS_QUE_HAY_QUE_ESPERAR = {
    "validate_pix_amount",
    "validate_card_amount",
    "validate_ves_amount",
    "limits_payload",
    "check_amount",
    "quota_payload",
    "is_exhausted",
}

# Dónde se buscan. El frontend no entra, y las pruebas tampoco: una prueba que
# a propósito llame sin esperar para comprobar el error es legítima.
DONDE_SE_BUSCA = ("routes", "services")


def _nombre_llamado(nodo):
    """`kyc_quota.check_amount(...)` y `check_amount(...)` dan lo mismo."""
    if isinstance(nodo.func, ast.Attribute):
        return nodo.func.attr
    if isinstance(nodo.func, ast.Name):
        return nodo.func.id
    return None


def _llamadas_sin_esperar(fuente):
    """Las llamadas a las funciones vigiladas que NO están dentro de un `await`.

    Se recorre el árbol dos veces en vez de rastrear padres: primero se anotan
    las llamadas que cuelgan de un `await`, y después se recorren todas y se
    mira cuáles no estaban en esa lista. Se comparan por identidad del nodo, que
    es exacto — comparar por texto confundiría dos llamadas iguales en líneas
    distintas.
    """
    arbol = ast.parse(fuente)
    esperadas = {id(n.value) for n in ast.walk(arbol) if isinstance(n, ast.Await)}
    sueltas = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        nombre = _nombre_llamado(nodo)
        if nombre in LAS_QUE_HAY_QUE_ESPERAR and id(nodo) not in esperadas:
            sueltas.append((nombre, nodo.lineno))
    return sueltas


def test_el_buscador_de_awaits_sirve():
    """La comprobación de la guarda de abajo.

    Si el buscador dejara de reconocer un `await`, la guarda pasaría siempre y
    no protegería nada — que es peor que no tenerla, porque figura en la lista.
    """
    con_await = "async def f(db):\n    x = await validate_pix_amount(db, 1)\n"
    sin_await = "async def f(db):\n    x = validate_pix_amount(db, 1)\n"
    assert _llamadas_sin_esperar(con_await) == []
    assert _llamadas_sin_esperar(sin_await) == [("validate_pix_amount", 2)]

    # Y con el módulo por delante, que es como se llama en casi todos lados.
    assert _llamadas_sin_esperar(
        "async def f(db):\n    await kyc_quota.check_amount(db, u, 1)\n") == []
    assert _llamadas_sin_esperar(
        "async def f(db):\n    kyc_quota.check_amount(db, u, 1)\n") != []


def test_NADIE_LLAMA_A_ESTAS_FUNCIONES_SIN_ESPERARLAS():
    """Una corrutina sin `await` es un valor VERDADERO.

    O sea que `error_monto = validate_pix_amount(...)` sin esperar hace que
    `if error_monto:` sea siempre cierto y que ninguna operación se pueda
    completar, con un mensaje que además no se entiende.
    """
    sueltas = []
    for carpeta in DONDE_SE_BUSCA:
        for archivo in sorted((_BACKEND / carpeta).rglob("*.py")):
            for nombre, linea in _llamadas_sin_esperar(
                    archivo.read_text(encoding="utf-8")):
                sueltas.append(f"{carpeta}/{archivo.name}:{linea} → {nombre}()")
    assert not sueltas, (
        "Estas llamadas devuelven una corrutina que nadie espera, y una "
        "corrutina es un valor verdadero:\n  " + "\n  ".join(sueltas))


# ══════════════════════════════════════════════════════════════════════════
# 2. Los números no vuelven al código
# ══════════════════════════════════════════════════════════════════════════

LAS_QUE_SE_FUERON = (
    (limits, "PIX_MIN_BRL"),
    (limits, "PIX_MAX_BRL"),
    (limits, "VES_MIN"),
    (kyc_quota, "UNVERIFIED_MAX_RIS"),
    (kyc_quota, "UNVERIFIED_MAX_OPS"),
)


@pytest.mark.parametrize("modulo, constante", LAS_QUE_SE_FUERON)
def test_LOS_LIMITES_NO_VUELVEN_A_ESTAR_ESCRITOS_EN_EL_CODIGO(modulo, constante):
    """Cada una de estas era un despliegue para cambiar un número.

    Volver a ponerlas es lo que se siente natural el día que haga falta un
    límite nuevo y con prisa. Y lo peor no es la constante: es que quedaría una
    vía leyendo del panel y otra del código, sin nada que lo diga.
    """
    assert not hasattr(modulo, constante), (
        f"«{constante}» volvió a {modulo.__name__}. Ese número va en el "
        "catálogo de services/configuracion.py, no acá.")


def test_el_unico_limite_que_sigue_en_el_codigo_es_el_que_no_es_un_numero():
    """`VES_MAX = None` se queda, y con motivo: «sin techo» no es un número, y
    el catálogo guarda números."""
    assert limits.VES_MAX is None


@pytest.mark.parametrize("clave", [
    "pix_minimo", "pix_maximo", "tarjeta_minimo", "tarjeta_maximo",
    "ves_minimo", "cupo_sin_verificar_ris", "cupo_sin_verificar_operaciones",
])
def test_cada_limite_esta_en_el_catalogo_con_su_texto(clave):
    """Y con etiqueta y ayuda, porque la pantalla se dibuja con eso.

    Un ajuste sin texto sale en el panel como una casilla sin nombre, y nadie se
    anima a tocar una casilla sin nombre que cambia cuánta plata puede mover un
    usuario.
    """
    ajuste = cfg.AJUSTES[clave]
    assert ajuste.etiqueta and ajuste.ayuda and ajuste.unidad
    assert ajuste.minimo is not None and ajuste.maximo is not None


# ══════════════════════════════════════════════════════════════════════════
# 3. Un mínimo por encima de su máximo deja la vía muerta
# ══════════════════════════════════════════════════════════════════════════

def test_EL_MINIMO_NO_PUEDE_QUEDAR_POR_ENCIMA_DEL_MAXIMO(base, cliente):
    r = cliente.put("/api/admin/configuracion",
                    json={"valores": {"pix_minimo": "400", "pix_maximo": "100"}})
    assert r.status_code == 400, r.text
    assert "mínimo de PIX" in r.json()["detail"]


def test_SE_MIRA_COMO_QUEDARIA_Y_NO_SOLO_LO_QUE_SE_MANDO(base, cliente):
    """El caso probable de verdad: se manda UN campo solo.

    Alguien sube el mínimo a 400 un día —perfectamente válido— y otro día baja
    el máximo a 100 sin acordarse del primero. Comprobar la pareja sólo cuando
    vienen los dos campos juntos dejaría pasar el segundo guardado y mataría la
    vía.

    Cada uno de los dos números, por separado, está dentro de su propio rango.
    Lo que está mal es cómo quedan juntos, y eso sólo se ve mirando el
    resultado.
    """
    assert cliente.put("/api/admin/configuracion",
                       json={"valores": {"pix_minimo": "400"}}).status_code == 200

    r = cliente.put("/api/admin/configuracion",
                    json={"valores": {"pix_maximo": "100"}})
    assert r.status_code == 400, r.text
    assert "400" in r.json()["detail"] and "100" in r.json()["detail"]
    # Y el máximo viejo sigue en pie: no se escribió nada.
    assert corre(cfg.leer(base, "pix_maximo")) == Decimal("5000.00")


def test_no_se_escribe_nada_si_la_pareja_queda_al_reves(base, cliente):
    """Rechazar a medio camino sería peor que rechazar entero: dejaría el
    mínimo nuevo con el máximo viejo, que es justo la combinación rota."""
    cliente.put("/api/admin/configuracion",
                json={"valores": {"pix_minimo": "400", "pix_maximo": "100"}})
    assert corre(cfg.leer(base, "pix_minimo")) == Decimal("10.00")
    assert corre(cfg.leer(base, "pix_maximo")) == Decimal("5000.00")


def test_una_pareja_en_orden_se_guarda_sin_chistar(base, cliente):
    r = cliente.put("/api/admin/configuracion",
                    json={"valores": {"pix_minimo": "20", "pix_maximo": "3000"}})
    assert r.status_code == 200, r.text
    assert corre(cfg.leer(base, "pix_minimo")) == Decimal("20.00")
    assert corre(cfg.leer(base, "pix_maximo")) == Decimal("3000.00")


def test_el_minimo_y_el_maximo_pueden_ser_iguales(base, cliente):
    """Un solo monto válido es raro pero no es un error: puede ser una promoción
    de monto fijo. Lo que se prohíbe es que NINGUNO sea válido."""
    r = cliente.put("/api/admin/configuracion",
                    json={"valores": {"pix_minimo": "100", "pix_maximo": "100"}})
    assert r.status_code == 200, r.text


def test_la_tarjeta_tiene_su_propia_pareja(base, cliente):
    r = cliente.put("/api/admin/configuracion",
                    json={"valores": {"tarjeta_minimo": "400",
                                      "tarjeta_maximo": "100"}})
    assert r.status_code == 400, r.text
    assert "tarjeta" in r.json()["detail"]


def test_cruzar_las_vias_no_dispara_la_comprobacion(base, cliente):
    """El mínimo de PIX puede ser mayor que el máximo de tarjeta: son dos vías
    distintas y no se comparan entre sí."""
    r = cliente.put("/api/admin/configuracion",
                    json={"valores": {"pix_minimo": "400", "tarjeta_maximo": "100"}})
    assert r.status_code == 200, r.text


# ══════════════════════════════════════════════════════════════════════════
# 4. Un ajuste ilegible en la base no puede dejar una vía muerta
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("guardado", ["no soy un numero", "", "abc", [], {},
                                      True, None])
def test_UN_MONTO_ILEGIBLE_EN_LA_BASE_VUELVE_AL_VALOR_DE_FABRICA(base, guardado):
    """El defecto que encontró un test de esta misma entrega.

    La rama de los enteros ya volvía al valor de fábrica cuando lo guardado no
    se entendía. La de la plata no comprobaba nada y devolvía CERO — así que un
    `pix_maximo` ilegible dejaba el máximo en cero y nadie podía pagar por PIX,
    y un `bono_al_referido` ilegible le daba cero de bono a todo el mundo.

    Sin un solo error en ningún lado, que es lo que lo hacía peligroso.
    """
    corre(base[cfg.COLECCION].update_one(
        {"clave": "pix_maximo"},
        {"$set": {"clave": "pix_maximo", "valor": guardado}}, upsert=True))
    assert corre(cfg.leer(base, "pix_maximo")) == Decimal("5000.00")
    assert corre(cfg.leer_todo(base))["pix_maximo"] == Decimal("5000.00")


def test_un_monto_ilegible_no_deja_la_via_muerta(base):
    """La consecuencia, dicha en la moneda que importa: se puede seguir
    operando."""
    corre(base[cfg.COLECCION].update_one(
        {"clave": "pix_maximo"},
        {"$set": {"clave": "pix_maximo", "valor": "abc"}}, upsert=True))
    assert corre(limits.validate_pix_amount(base, 100)) is None


def test_un_monto_guardado_bien_si_se_lee(base):
    """La otra mitad: que la tolerancia no se haya comido lo que sí es válido.

    Sin esto, «volver siempre al valor de fábrica» pasaría las pruebas de arriba
    y el panel no serviría para nada.
    """
    poner = cfg.normalizar("pix_maximo", "1234.50")[0]
    corre(cfg.escribir(base, "pix_maximo", poner))
    assert corre(cfg.leer(base, "pix_maximo")) == Decimal("1234.50")
