"""
tests/test_los_datos_no_se_mezclan.py — Los clientes y el dinero del banco no
se mezclan con los de remesas y encomiendas, en ninguna de las dos direcciones.

POR QUE HACE FALTA, ADEMAS DE LA FRONTERA DE CODIGO

    `test_nucleo_frontera_y_migraciones.py` ya cuida que el núcleo y la
    aplicación no se importen el uno al otro. Eso es la frontera de CÓDIGO.
    Esto es la de DATOS, que es la que el dueño del proyecto pidió: que los
    clientes del banco no se mezclen con los de los otros servicios, para
    que el día que el banco opere con un socio regulado se pueda apagar todo
    lo demás sin arrastrar nada.

    Son dos bases distintas: la aplicación guarda en Mongo; el banco, en su
    propio Postgres (`NUCLEO_DATABASE_URL`). Las reglas:

      1. El banco no lee ni escribe ninguna colección de Mongo. Lo único que
         toma de ahí son sus propias llaves de Configuración (el modo, los
         umbrales), y lo hace por `services/configuracion`, no a mano.
      2. La aplicación no abre la base del banco: ningún módulo fuera de
         `nucleo/` trae el controlador de Postgres ni lee su dirección.
      3. Las tablas del banco no guardan identificadores de clientes de la
         aplicación: una cuenta del banco cuelga del legajo de SU titular, y
         un `user_id` de la aplicación no sirve para abrirla.
      4. La aplicación no tiene colecciones con los clientes o las cuentas
         del banco.
"""
import asyncio
import os
import pathlib
import re
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")
NUCLEO = _BACKEND / "nucleo"

# Lo que es de la aplicación y no del banco. `tests` y `scripts` no son
# código que corra en producción.
_SE_SALTEA = {"nucleo", "tests", "scripts", "__pycache__", "node_modules"}


def _codigo_de_la_aplicacion():
    for archivo in _BACKEND.rglob("*.py"):
        partes = archivo.relative_to(_BACKEND).parts
        if partes[0] in _SE_SALTEA:
            continue
        yield archivo


def _sin_comentarios(texto: str) -> str:
    return re.sub(r"#[^\n]*", "", texto)


# ══════════════════════════════════════════════════════════════════════════
# 1. El banco no toca Mongo
# ══════════════════════════════════════════════════════════════════════════

def test_EL_BANCO_NO_LEE_NI_ESCRIBE_COLECCIONES_DE_MONGO():
    """Ni `db.users`, ni `db["transactions"]`, ni ninguna otra. Si un día el
    banco necesita saber algo de un cliente de remesas, eso es mezclar."""
    culpables = []
    for archivo in NUCLEO.rglob("*.py"):
        texto = _sin_comentarios(archivo.read_text(encoding="utf-8"))
        for m in re.finditer(r"\bdb\.[a-z_]+\b|\bdb\[", texto):
            culpables.append(f"{archivo.relative_to(_BACKEND)}: {m.group(0)}")
    assert not culpables, "el banco toca colecciones de Mongo:\n" + "\n".join(culpables)


def test_LO_QUE_EL_BANCO_TOMA_DE_MONGO_SON_SUS_LLAVES_Y_NADA_MAS():
    """Los tres lugares que abren la base de la aplicación la usan sólo para
    pasársela a `configuracion`, que lee y escribe en su colección y en
    ninguna otra."""
    abren = sorted(str(a.relative_to(_BACKEND)) for a in NUCLEO.rglob("*.py")
                   if re.search(r"^\s*from database import db", a.read_text(encoding="utf-8"), re.M))
    assert abren == ["nucleo/modo.py", "nucleo/operacion/aprobaciones.py",
                     "nucleo/riesgo/monitoreo.py"], (
        "cambió quién abre la base de la aplicación desde el banco: " + ", ".join(abren))
    for archivo in abren:
        assert "configuracion" in (_BACKEND / archivo).read_text(encoding="utf-8")


def test_LAS_LLAVES_QUE_EL_BANCO_LEE_SON_SUYAS():
    """Todas las que nombra empiezan con `nucleo_`: el banco no decide nada
    mirando las de remesas o las de encomiendas."""
    nombradas = set()
    for archivo in NUCLEO.rglob("*.py"):
        nombradas |= set(re.findall(r"[\"']((?:nucleo|remesas|encomiendas|recarga|cripto|pix|ves|bono)_\w+)[\"']",
                                    _sin_comentarios(archivo.read_text(encoding="utf-8"))))
    ajenas = sorted(c for c in nombradas if not c.startswith("nucleo_"))
    assert not ajenas, "el banco lee llaves de otros servicios: " + ", ".join(ajenas)


# ══════════════════════════════════════════════════════════════════════════
# 2. La aplicación no abre la base del banco
# ══════════════════════════════════════════════════════════════════════════

def test_LA_APLICACION_NO_ABRE_LA_BASE_DEL_BANCO():
    culpables = []
    for archivo in _codigo_de_la_aplicacion():
        texto = _sin_comentarios(archivo.read_text(encoding="utf-8"))
        if re.search(r"^\s*(from|import)\s+(sqlalchemy|alembic|asyncpg|aiosqlite|psycopg)", texto, re.M):
            culpables.append(f"{archivo.relative_to(_BACKEND)}: trae el controlador de la base del banco")
        if "NUCLEO_DATABASE_URL" in texto:
            culpables.append(f"{archivo.relative_to(_BACKEND)}: lee la dirección de la base del banco")
    assert not culpables, "\n".join(culpables)


# ══════════════════════════════════════════════════════════════════════════
# 3. Las tablas del banco no guardan clientes de la aplicación
# ══════════════════════════════════════════════════════════════════════════

# Cómo se llaman, en la aplicación, los datos que identifican a un cliente.
DE_LA_APLICACION = {"user_id", "email", "referral_code", "gestor_code", "partner_code",
                    "balance_ris", "cpf_number", "phone_number"}


def test_NINGUNA_TABLA_DEL_BANCO_TIENE_COLUMNAS_DE_LA_APLICACION():
    from nucleo import esquema
    culpables = [f"{t.name}.{c.name}" for t in esquema.metadata.tables.values()
                 for c in t.columns if c.name in DE_LA_APLICACION]
    assert not culpables, "el banco guarda datos de clientes de la aplicación: " + ", ".join(culpables)


def test_UN_USER_ID_DE_LA_APLICACION_NO_ABRE_UNA_CUENTA_DEL_BANCO():
    """La cuenta cuelga del legajo de su titular, que el banco verifica por su
    cuenta. Un cliente de remesas no tiene cuenta en el banco por serlo."""
    pytest.importorskip("aiosqlite")
    from nucleo import base, comandos, plan
    from nucleo.identidad import legajos

    async def todo():
        base.usar("sqlite+aiosqlite://")
        await base.crear_todo()
        async with base.sesion() as s:
            await plan.sembrar(s)
        with pytest.raises(legajos.LegajoNoApto):
            await comandos.crear_cuenta(titular_ref="user_4f2a9c1b7e3d")
        return (await comandos.estado())["cuentas"]
    assert asyncio.run(todo()) == 0


# ══════════════════════════════════════════════════════════════════════════
# 4. La aplicación no guarda clientes ni cuentas del banco
# ══════════════════════════════════════════════════════════════════════════

def test_LA_APLICACION_NO_TIENE_COLECCIONES_DEL_BANCO():
    """Los titulares y sus cuentas viven en la base del banco. Una colección
    de Mongo con esos nombres sería una copia, y una copia es una mezcla."""
    from nucleo import esquema
    del_banco = {"titulares", "cuentas", "partidas", "asientos", "verificaciones", "cruces"}
    assert del_banco <= set(esquema.metadata.tables), "revisá la lista: cambió el esquema del banco"
    culpables = []
    for archivo in _codigo_de_la_aplicacion():
        texto = _sin_comentarios(archivo.read_text(encoding="utf-8"))
        for nombre in del_banco:
            if re.search(rf"\bdb\.{nombre}\b|\bdb\[[\"']{nombre}[\"']\]", texto):
                culpables.append(f"{archivo.relative_to(_BACKEND)}: {nombre}")
    assert not culpables, "\n".join(culpables)
