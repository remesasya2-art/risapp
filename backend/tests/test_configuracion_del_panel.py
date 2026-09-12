"""
tests/test_configuracion_del_panel.py — Los números que se cambian sin desplegar.

QUE SE ESTA PROBANDO

    `services/configuracion.py` y su pantalla. Son los números que hasta ahora
    vivían escritos a mano en archivos .py, y el primero de ellos decide
    cuánta plata se le regala a cada cuenta que se registra.

LAS TRES COSAS QUE MAS IMPORTAN ACA

    1. QUE UN VALOR MALO NO SE GUARDE COMO CERO.

       `money.to_decimal` está escrito para ser tolerante: un valor inválido
       devuelve `Decimal('0')` en vez de levantar, porque leer un saldo viejo
       y raro no puede tirar abajo una pantalla.

       Para escribir hace falta lo contrario. Si el campo del bono acepta
       «abc» y guarda cero, el bono deja de pagarse y nadie se entera hasta
       que un cliente pregunta. Lo mismo con «15,50», que es como se escribe
       un monto en Brasil.

    2. QUE UNA CLAVE DESCONOCIDA SE RECHACE, NO SE IGNORE.

       Es la lección del enlace de referido: la pantalla mandaba
       `referral_code`, el servidor esperaba `referred_by`, Pydantic descartó
       el campo en silencio y el enlace no funcionó nunca. Acá una clave que
       no existe es un 400 con su nombre adentro.

    3. QUE LA PANTALLA Y EL SERVIDOR NO SE SEPAREN.

       `test_el_api_le_manda_a_la_pantalla_todos_los_campos_que_lee` abre el
       componente de React, saca los campos que lee de cada ajuste, y exige
       que el API los mande. Es la misma guarda que se puso para el enlace de
       referido, y por el mismo motivo: dos lados que se tienen que poner de
       acuerdo y nada que avise cuando dejan de estarlo.
"""
import asyncio
import os
import pathlib
import re
import sys
from decimal import Decimal

import pytest
from bson import Decimal128

_BACKEND = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))

_REPO = _BACKEND.parent
PANTALLA = _REPO / "frontend" / "src" / "components" / "admin" / "Configuracion.jsx"

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from fastapi import FastAPI                                 # noqa: E402
from fastapi.testclient import TestClient                   # noqa: E402

from conftest import usar_base                              # noqa: E402
from models.user import User                                # noqa: E402
from routes import configuracion as rutas                   # noqa: E402
from routes import dependencies as deps                     # noqa: E402
from services import auditoria, configuracion as cfg        # noqa: E402


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
    # Se sustituye SOLO quién está conectado. `get_super_admin` sigue siendo el
    # de verdad, porque parte de lo que se prueba es que él rechace.
    app.dependency_overrides[deps.get_current_user] = lambda: _QUIEN["actual"]
    return TestClient(app)


def como(rol, user_id="u_1"):
    _QUIEN["actual"] = User(user_id=user_id, name="Quien", email="q@example.com",
                            role=rol)


# ══════════════════════════════════════════════════════════════════════════
# 1. Que un valor malo no se guarde como cero
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("escrito, esperado", [
    ("15", Decimal("15.00")),
    ("15.5", Decimal("15.50")),
    ("15,50", Decimal("15.50")),          # la coma, como se escribe en Brasil
    (" 15.50 ", Decimal("15.50")),
    ("0", Decimal("0.00")),
    (20, Decimal("20.00")),
])
def test_un_monto_bien_escrito_se_entiende(escrito, esperado):
    valor, motivo = cfg.normalizar("bono_al_referido", escrito)
    assert motivo is None, motivo
    assert valor == esperado
    assert isinstance(valor, Decimal), "la plata tiene que salir en Decimal"


@pytest.mark.parametrize("escrito", ["abc", "", "   ", "15.5.5", None, True,
                                     "NaN", "Infinity", [], {}])
def test_un_monto_mal_escrito_SE_RECHAZA_Y_NO_SE_VUELVE_CERO(escrito):
    """La guarda que más importa de este archivo.

    `money.to_decimal` devolvería `Decimal('0')` para casi todos estos. Un
    bono guardado en cero no da error en ninguna parte: simplemente deja de
    pagarse, y se descubre cuando alguien reclama.
    """
    valor, motivo = cfg.normalizar("bono_al_referido", escrito)
    assert valor is None, (
        f"{escrito!r} se aceptó y quedó en {valor!r}. Un valor que no es un "
        "monto tiene que rechazarse, no convertirse en cero.")
    assert motivo, "un rechazo sin motivo no le dice nada a quien lo lee"


def test_el_rango_frena_un_cero_de_mas_al_tipear():
    """1500 en vez de 150 es plata que sale sola, a cada cuenta nueva."""
    valor, motivo = cfg.normalizar("bono_al_referido", "1500")
    assert valor is None
    assert "no puede ser más" in motivo

    valor, motivo = cfg.normalizar("bono_al_referido", "-1")
    assert valor is None
    assert "no puede ser menos" in motivo


def test_un_contador_no_acepta_decimales():
    valor, motivo = cfg.normalizar("referidos_que_pagan_con_solo_kyc", "10.5")
    assert valor is None
    assert "entero" in motivo


# ══════════════════════════════════════════════════════════════════════════
# 2. Que la plata se guarde como Decimal128 y vuelva como Decimal
# ══════════════════════════════════════════════════════════════════════════

def test_la_plata_se_guarda_en_decimal128_y_no_en_float(base):
    """La diferencia que `mongomock` no puede ver, y que ya causó dos 500.

    Se comprueba el tipo del valor guardado, no sólo el número: un `float`
    ahí adentro pasa todos los tests de igualdad y revienta en producción.
    """
    async def caso():
        valor, motivo = cfg.normalizar("bono_al_referido", "15,50")
        assert motivo is None
        await cfg.escribir(base, "bono_al_referido", valor)

        crudo = await base.config.find_one({"clave": "bono_al_referido"})
        assert isinstance(crudo["valor"], Decimal128), (
            f"se guardó como {type(crudo['valor']).__name__} y tiene que ser "
            "Decimal128, igual que los saldos.")

        leido = await cfg.leer(base, "bono_al_referido")
        assert isinstance(leido, Decimal)
        assert leido == Decimal("15.50")
    corre(caso())


def test_sin_nada_guardado_devuelve_el_valor_de_fabrica(base):
    async def caso():
        assert await cfg.leer(base, "bono_al_referido") == Decimal("15.00")
        assert await cfg.leer(base, "bono_a_quien_refiere") == Decimal("5.00")
        assert await cfg.leer(base, "referidos_que_pagan_con_solo_kyc") == 10
    corre(caso())


def test_un_valor_guardado_ilegible_no_deja_sin_bono_a_nadie(base):
    """Un ajuste roto en la base no puede cortar el bono de todo el mundo.

    Se cae al valor de fábrica y se grita en el registro, que es lo mismo que
    hace `services/borde.py` cuando no puede resolver un pedido: fallar hacia
    el lado que no rompe.
    """
    async def caso():
        await base.config.insert_one(
            {"clave": "referidos_que_pagan_con_solo_kyc", "valor": "diez"})
        assert await cfg.leer(base, "referidos_que_pagan_con_solo_kyc") == 10
        todo = await cfg.leer_todo(base)
        assert todo["referidos_que_pagan_con_solo_kyc"] == 10
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 3. La ruta: quién puede, y qué pasa con lo que manda
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("rol", ["user", "admin", "agent", "personal"])
def test_solo_el_super_administrador_entra(rol, cliente):
    """Acá se cambia cuánta plata se regala. No se delega.

    Y se comprueba por ROL, no por cuenta: proteger una cuenta por su nombre
    la publica, y el bundle del frontend se le sirve a cada visitante.
    """
    como(rol)
    assert cliente.get("/api/admin/configuracion").status_code == 403
    assert cliente.put("/api/admin/configuracion",
                       json={"valores": {"bono_al_referido": "20"}}
                       ).status_code == 403


def test_el_super_administrador_lee_el_catalogo_con_los_valores(cliente):
    como("super_admin")
    r = cliente.get("/api/admin/configuracion")
    assert r.status_code == 200, r.text
    ajustes = r.json()["ajustes"]
    assert {a["clave"] for a in ajustes} == set(cfg.AJUSTES)
    bono = next(a for a in ajustes if a["clave"] == "bono_al_referido")
    assert bono["valor"] == "15.00", "la plata viaja como texto por el API"


def test_guardar_y_volver_a_leer(base, cliente):
    como("super_admin")
    r = cliente.put("/api/admin/configuracion",
                    json={"valores": {"bono_al_referido": "22,50"}})
    assert r.status_code == 200, r.text
    assert r.json()["cambiados"] == ["bono_al_referido"]

    de_nuevo = cliente.get("/api/admin/configuracion").json()["ajustes"]
    bono = next(a for a in de_nuevo if a["clave"] == "bono_al_referido")
    assert bono["valor"] == "22.50"


def test_UNA_CLAVE_DESCONOCIDA_SE_RECHAZA_CON_SU_NOMBRE(cliente):
    """La lección del enlace de referido, que nunca funcionó por esto mismo.

    Un campo que el servidor no conoce y descarta en silencio es un defecto
    que no deja rastro: ni error, ni 400, ni una línea en el registro.
    """
    como("super_admin")
    r = cliente.put("/api/admin/configuracion",
                    json={"valores": {"bono_inventado": "20"}})
    assert r.status_code == 400, r.text
    detalle = r.json()["detail"]
    assert "bono_inventado" in detalle, (
        "el 400 tiene que nombrar la clave, o hay que ir a leer el código "
        "para saber qué estaba mal")
    assert "bono_al_referido" in detalle, "conviene listar las que sí existen"


def test_si_uno_esta_mal_NO_SE_GUARDA_NINGUNO(base, cliente):
    """Sin esto la pantalla queda a mitad de camino: el primer número
    cambiado, el segundo no, y un cartel rojo que no dice qué quedó."""
    como("super_admin")
    r = cliente.put("/api/admin/configuracion", json={"valores": {
        "bono_al_referido": "30",          # este está bien
        "bono_a_quien_refiere": "abc",     # este no
    }})
    assert r.status_code == 400, r.text

    async def leer():
        return await cfg.leer(base, "bono_al_referido")
    assert corre(leer()) == Decimal("15.00"), (
        "se guardó el primero aunque el segundo falló")


def test_guardar_lo_mismo_no_cuenta_como_cambio(cliente):
    como("super_admin")
    r = cliente.put("/api/admin/configuracion",
                    json={"valores": {"bono_al_referido": "15.00"}})
    assert r.status_code == 200, r.text
    assert r.json()["cambiados"] == [], (
        "guardar el mismo valor no puede ensuciar el libro de auditoría")


def test_el_cuerpo_vacio_se_rechaza(cliente):
    como("super_admin")
    assert cliente.put("/api/admin/configuracion",
                       json={"valores": {}}).status_code == 400


# ══════════════════════════════════════════════════════════════════════════
# 4. Que quede anotado quién lo cambió
# ══════════════════════════════════════════════════════════════════════════

def test_el_cambio_queda_en_el_libro_de_auditoria(base, cliente):
    como("super_admin", user_id="u_jefa")
    r = cliente.put("/api/admin/configuracion",
                    json={"valores": {"bono_al_referido": "40"}})
    assert r.status_code == 200, r.text

    async def leer_libro():
        return await base[auditoria.COLECCION].find({}).to_list(10)
    lineas = corre(leer_libro())
    assert len(lineas) == 1, (
        f"se esperaba una línea de auditoría y hay {len(lineas)}. Un cambio "
        "que mueve plata de la empresa a los usuarios tiene que poder "
        "responder «quién y cuándo».")
    linea = lineas[0]
    assert linea["accion"] == "config.ajuste"
    assert linea["antes"] == {"bono_al_referido": "15.00"}
    assert linea["despues"] == {"bono_al_referido": "40.00"}


def test_la_accion_esta_declarada_en_el_catalogo_del_libro():
    """Si no está, `auditoria.registrar` levanta y el cambio se cae."""
    assert "config.ajuste" in auditoria.ACCIONES


# ══════════════════════════════════════════════════════════════════════════
# 5. Que la pantalla y el servidor no se separen
# ══════════════════════════════════════════════════════════════════════════

def _campos_que_lee_la_pantalla() -> set:
    """Los `a.algo` que el componente lee de cada ajuste.

    Se hace con una expresión y no con un analizador de JavaScript porque en
    este entorno no hay ninguno, y traer uno para leer unos accesos a
    propiedades sería una dependencia entera para nada.
    """
    texto = PANTALLA.read_text(encoding="utf-8")
    # Sin los comentarios: el encabezado de ese archivo nombra ajustes y
    # campos al explicar por qué la pantalla se dibuja sola.
    sin_comentarios = re.sub(r"/\*.*?\*/", " ", texto, flags=re.DOTALL)
    return set(re.findall(r"\ba\.(\w+)", sin_comentarios))


def test_el_extractor_de_campos_de_la_pantalla_sirve():
    """La comprobación de la guarda de abajo: que tenga algo que revisar."""
    assert PANTALLA.exists(), f"no está {PANTALLA}"
    campos = _campos_que_lee_la_pantalla()
    assert len(campos) >= 5, (
        f"el extractor encontró casi nada: {sorted(campos)}. Si el componente "
        "se reescribió de otra forma, hay que ajustar la expresión.")
    assert "etiqueta" in campos, (
        f"la pantalla ya no lee `a.etiqueta`. Encontrado: {sorted(campos)}")


def test_el_api_le_manda_a_la_pantalla_todos_los_campos_que_lee(cliente):
    """LA GUARDA QUE IMPORTA, y es la misma que la del enlace de referido.

    Un campo que la pantalla lee y el API no manda sale como `undefined`: no
    hay error, no hay 400, y el texto simplemente no aparece. Es el mismo tipo
    de silencio que dejó el código de invitación sin funcionar durante meses.
    """
    como("super_admin")
    ajustes = cliente.get("/api/admin/configuracion").json()["ajustes"]
    assert ajustes, "sin ajustes no hay nada que comparar"

    faltan = _campos_que_lee_la_pantalla() - set(ajustes[0])
    assert not faltan, (
        f"La pantalla lee {sorted(faltan)} de cada ajuste y el API no lo "
        f"manda. Lo que llega es {sorted(ajustes[0])}. En React eso sale como "
        "`undefined` y no se ve: ni error, ni 400, ni nada en el registro.")


def test_agregar_un_ajuste_no_necesita_tocar_la_pantalla():
    """El motivo por el que hay un catálogo y no una función por ajuste.

    Se agrega uno de verdad, se comprueba que el catálogo que va a la pantalla
    lo trae con todo lo que hace falta, y se saca.
    """
    cfg.AJUSTES["_de_prueba"] = cfg.Ajuste(
        tipo=cfg.ENTERO, defecto=7, minimo=1, maximo=9,
        etiqueta="Uno de prueba", ayuda="Nada.", unidad="cosas")
    try:
        entrada = next(e for e in cfg.catalogo_para_la_pantalla()
                       if e["clave"] == "_de_prueba")
        for campo in _campos_que_lee_la_pantalla() - {"valor"}:
            assert campo in entrada, (
                f"al ajuste nuevo le falta {campo!r}, que la pantalla lee")
        assert entrada["defecto"] == 7
    finally:
        del cfg.AJUSTES["_de_prueba"]
