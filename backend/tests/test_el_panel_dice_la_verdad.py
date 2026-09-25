"""Que la tabla de usuarios muestre lo que hay, y lo diga bien.

LOS TRES DEFECTOS QUE SE ARREGLAN, COMPROBADOS CORRIENDOLOS

    Con once cuentas sembradas —una borrada, dos con el correo vetado, un
    `admin` y un `agent`— el panel contestaba tres números distintos:

        GET /admin/users           -> 11   todo, borrados incluidos
        la tabla en pantalla       ->  9   escondía a los vetados
        la tarjeta «Usuarios»      -> 10   escondía a los borrados

    1. LA TABLA ESCONDIA A LOS VETADOS. `AdminPanel.jsx` filtraba la lista
       contra los correos de la lista negra. Vetabas a alguien y desaparecía:
       no lo veías, no le mirabas el saldo, no lo sacabas de la lista desde
       ahí. Y desde que el login también los frena, quedaba una cuenta sobre
       la que acabás de actuar y que ya no podés mirar.

    2. LOS TRES NUMEROS NO SE PODIAN CONCILIAR, porque ninguno decía cuál
       estaba midiendo.

    3. `admin` Y `agent` SE VEIAN COMO «Usuario». La columna hacía
       `role === 'super_admin' ? 'Administrador' : 'Usuario'`. Un colaborador
       que aprueba KYC y mueve saldos se veía idéntico a un cliente. Es el que
       podía hacer tomar una decisión equivocada mirando la pantalla.

POR QUE LAS GUARDAS DEL FRONTEND ESTAN EN UN TEST DE PYTHON

    El frontend no tiene corredor de tests propio: su CI es compilar y pasar
    `scripts/lint-bloqueante.mjs`. Así que lo que hay que vigilar de
    `AdminPanel.jsx` se vigila leyendo el archivo desde acá, como ya hacen
    otros tests de este repositorio.
"""
import asyncio
import os
import pathlib
import re
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)
_PANEL = pathlib.Path(_BACKEND, "..", "frontend", "src", "pages", "AdminPanel.jsx").resolve()

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base, ensenarle_decimal128_a_mongomock       # noqa: E402
from services import estado_de_la_cuenta as estado                     # noqa: E402
from services import perfil                                           # noqa: E402
from services.money import to_decimal128                              # noqa: E402

ensenarle_decimal128_a_mongomock()


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_panel_verdad"]
    usar_base(b)
    yield b


async def _once_cuentas(b):
    """Las mismas once con las que se midió el defecto."""
    for i in range(1, 12):
        d = {"user_id": f"u{i}", "email": f"u{i}@ejemplo.com", "name": f"Cliente {i}",
             "role": "user", "balance_ris": to_decimal128("10.00")}
        if i == 9:
            d["is_deleted"] = True
        if i == 10:
            d["role"] = "admin"
        if i == 11:
            d["role"] = "agent"
        await b.users.insert_one(d)
    for i in (1, 2):
        await b.blacklist.insert_one({"type": "email", "value": f"u{i}@ejemplo.com"})


# ══════════════════════════════════════════════════════════════════════════
# El estado: uno por cuenta, y excluyentes
# ══════════════════════════════════════════════════════════════════════════

def test_cada_cuenta_tiene_exactamente_un_estado():
    casos = [
        ({}, estado.ACTIVA),
        ({"status": "suspended"}, estado.SUSPENDIDA),
        ({"is_banned": True}, estado.VETADA),
        ({"is_deleted": True}, estado.BORRADA),
    ]
    for doc, esperado in casos:
        assert estado.de(doc) == esperado, doc


def test_el_correo_vetado_a_mano_tambien_cuenta():
    """La lista negra se edita a mano, y a mano se agrega el correo sin tocar
    la cuenta: `is_banned` se queda en falso y la cuenta parecería activa."""
    doc = {"email": "Ana@Ejemplo.com "}
    assert estado.de(doc) == estado.ACTIVA
    assert estado.de(doc, frozenset({"ana@ejemplo.com"})) == estado.VETADA


def test_lo_mas_definitivo_gana():
    """Una borrada que además estaba vetada cuenta como borrada, una sola vez.
    Si contara en los dos grupos, la suma no daría el total y los números
    volverían a no poder conciliarse."""
    doc = {"is_deleted": True, "is_banned": True, "status": "suspended",
           "email": "x@ejemplo.com"}
    assert estado.de(doc, frozenset({"x@ejemplo.com"})) == estado.BORRADA


def test_los_grupos_suman_el_total(base):
    async def cuerpo():
        await _once_cuentas(base)
        r = await estado.resumen(base)
        assert r["total"] == 11
        suma = sum(r[e] for e in estado.LOS_ESTADOS)
        assert suma == r["total"], (
            f"los grupos suman {suma} y el total dice {r['total']}: los "
            f"números del panel vuelven a no poder conciliarse")
        assert r[estado.BORRADA] == 1
        assert r[estado.VETADA] == 2
        assert r[estado.ACTIVA] == 8
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# La ruta: la lista completa, marcada, y el resumen que la explica
# ══════════════════════════════════════════════════════════════════════════

def test_la_ruta_devuelve_a_todos_incluidos_los_vetados(base):
    async def cuerpo():
        await _once_cuentas(base)
        from routes.admin import usuarios as ra
        r = await ra.get_all_users(admin=None)
        assert len(r["users"]) == 11
        por_id = {u["user_id"]: u for u in r["users"]}
        assert por_id["u1"]["estado"] == estado.VETADA
        assert por_id["u9"]["estado"] == estado.BORRADA
        assert por_id["u3"]["estado"] == estado.ACTIVA
    corre(cuerpo())


def test_el_resumen_viaja_con_la_lista(base):
    """Si el número saliera de otra consulta, podría discrepar con las filas.
    Es exactamente lo que pasaba entre la tarjeta y la tabla."""
    async def cuerpo():
        await _once_cuentas(base)
        from routes.admin import usuarios as ra
        r = await ra.get_all_users(admin=None)
        assert r["resumen"]["total"] == len(r["users"])
    corre(cuerpo())


def test_la_tarjeta_del_resumen_cuenta_lo_mismo_que_la_tabla(base):
    """El número de la tarjeta tiene que aparecer, igualito, en el resumen de
    la tabla. Antes la tarjeta decía 10 y la tabla mostraba 9."""
    async def cuerpo():
        await _once_cuentas(base)
        from routes.admin import usuarios as ra
        from services import pendientes
        r = await ra.get_all_users(admin=None)
        assert await pendientes.total_de_usuarios() == r["resumen"][estado.ACTIVA]
    corre(cuerpo())


def test_la_lista_del_panel_deja_ver_por_que_no_entra(base):
    """Sin `is_deleted` e `is_banned` en la lista de lo permitido, la pantalla
    no tiene con qué marcar la fila."""
    for campo in ("is_deleted", "is_banned"):
        assert perfil.LO_QUE_VE_EL_PANEL.get(campo) == 1, campo


def test_ninguna_llave_se_coló_con_los_dos_campos_nuevos(base):
    """Agregar campos a una lista de lo permitido es la ocasión de colar uno."""
    async def cuerpo():
        await base.users.insert_one({
            "user_id": "u1", "email": "a@ejemplo.com", "name": "Ana",
            "password_hash": "$2b$12$secreto", "two_factor_secret": "JBSWY3DPEHPK3PXP",
            "pin_hash": "$2b$12$pin", "webauthn_credentials": [{"public_key": "AAA"}],
        })
        from routes.admin import usuarios as ra
        r = await ra.get_all_users(admin=None)
        crudo = repr(r)
        for prohibido in ("secreto", "JBSWY3DPEHPK3PXP", "$2b$12$pin", "public_key"):
            assert prohibido not in crudo, f"«{prohibido}» salió en la respuesta"
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# La pantalla
# ══════════════════════════════════════════════════════════════════════════

def _panel() -> str:
    return _PANEL.read_text(encoding="utf-8")


def test_la_pantalla_existe_donde_este_test_la_busca():
    """Sin esto, los tres de abajo pasarían leyendo un archivo vacío."""
    assert _PANEL.is_file(), f"no está {_PANEL}"
    assert len(_panel()) > 10000, "AdminPanel.jsx quedó sospechosamente corto"


def test_la_tabla_no_esconde_a_los_de_la_lista_negra():
    fuente = _panel()
    # El filtro de la tabla, sin comentarios: una mención en un comentario
    # explicando qué pasaba no puede hacer pasar este test.
    sin_comentarios = re.sub(r"//[^\n]*", "", fuente)
    filtro = re.search(r"const filteredUsers = users\.filter\((.*?)\n  \);",
                       sin_comentarios, re.S)
    assert filtro, "no se encontró el filtro de la tabla de usuarios"
    assert "bannedEmails" not in filtro.group(1), (
        "la tabla de usuarios volvió a esconder a quien está en la lista "
        "negra. Vetar a alguien no puede hacerlo desaparecer del panel: se "
        "muestra marcado, con su estado.")


def test_la_columna_del_rol_no_aplasta_a_los_colaboradores():
    fuente = _panel()
    assert "NOMBRE_DEL_ROL" in fuente, "se fue el mapa de nombres de rol"
    for rol in ("super_admin", "admin", "agent", "user"):
        assert re.search(rf"\b{rol}\s*:", fuente), (
            f"«{rol}» no tiene nombre propio en la pantalla")
    sin_comentarios = re.sub(r"//[^\n]*", "", fuente)
    assert "? 'Administrador' : 'Usuario'" not in sin_comentarios, (
        "volvió el `role === 'super_admin' ? 'Administrador' : 'Usuario'`: un "
        "colaborador que mueve saldos se vuelve a ver como un cliente.")


def test_una_cuenta_borrada_no_ofrece_botones_que_la_toquen():
    """Se ve —sus transacciones viejas tienen que seguir teniendo dueño
    visible— pero cambiarle el rol o la clave a alguien que ya no existe sólo
    sirve para confundir a quien lo aprieta."""
    sin_comentarios = re.sub(r"\{/\*.*?\*/\}", "", _panel(), flags=re.S)
    assert "u.estado === 'borrada' ?" in sin_comentarios, (
        "la celda de acciones dejó de distinguir a las cuentas borradas: "
        "volvió a ofrecer Rol, Clave y Lista negra sobre una cuenta que ya "
        "no existe.")


def test_la_pantalla_no_deduce_sola_el_estado():
    """El estado lo decide el servidor. Si la pantalla lo dedujera, volvería a
    discrepar con el número del Resumen, que es de donde salió todo esto."""
    fuente = _panel()
    assert "u.estado" in fuente, "la fila dejó de leer el estado que manda el servidor"
    assert "resumenDeCuentas" in fuente, "se fue el resumen que reconcilia los números"
