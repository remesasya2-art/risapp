"""
tests/test_nucleo_frontera_y_migraciones.py — el núcleo no se mezcla con la
aplicación, y su esquema se lleva con migraciones.

LA FRONTERA

    El paquete `nucleo` no importa nada de la aplicación salvo la puerta del
    super administrador (`routes.dependencies.get_super_admin`), el modelo
    de usuario y la lectura de la configuración. La aplicación no importa
    nada de `nucleo` salvo `server.py` (registrar el router y anunciar el
    estado). El día que el núcleo se separe en su propio servicio, tiene que
    poder salir sin arrastrar nada.

LAS MIGRACIONES

    Los tests crean el esquema desde el metadata; producción lo crea con
    Alembic. Acá se corre la migración de verdad sobre un SQLite temporal y
    se comprueba que deje las mismas tablas y columnas que el metadata.
"""
import os
import pathlib
import re
import subprocess
import sys

import pytest

_BACKEND = pathlib.Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))
NUCLEO = _BACKEND / "nucleo"

# Lo único que el núcleo puede tomar de la aplicación: la puerta del super
# administrador, el modelo de usuario, la lectura de la configuración (para
# el interruptor) y la base de Mongo sólo para leer ese interruptor.
PERMITIDO_DESDE_EL_NUCLEO = {"routes.dependencies", "models.user", "services.configuracion", "database.db"}


def _imports_de(archivo: pathlib.Path):
    """Cada módulo importado, con su nombre completo: `from services import
    configuracion` cuenta como `services.configuracion`, que es lo que hay que
    cotejar contra la lista de lo permitido."""
    texto = archivo.read_text(encoding="utf-8")
    for m in re.finditer(r"^\s*from\s+([\w.]+)\s+import\s+([^\n#]+)", texto, re.M):
        paquete, nombres = m.group(1), m.group(2)
        for nombre in nombres.replace("(", "").replace(")", "").split(","):
            nombre = nombre.strip().split(" as ")[0].strip()
            if nombre:
                yield f"{paquete}.{nombre}" if "." not in paquete else paquete
    for m in re.finditer(r"^\s*import\s+([\w.]+)", texto, re.M):
        yield m.group(1)


def test_EL_NUCLEO_NO_IMPORTA_LA_APLICACION():
    culpables = []
    for archivo in NUCLEO.rglob("*.py"):
        for mod in _imports_de(archivo):
            raiz = mod.split(".")[0]
            if raiz in ("routes", "services", "models", "database", "admin_routes", "server", "utils"):
                if mod not in PERMITIDO_DESDE_EL_NUCLEO:
                    culpables.append(f"{archivo.relative_to(_BACKEND)}: {mod}")
    assert not culpables, "\n".join(culpables)


def test_LA_APLICACION_SOLO_TOCA_EL_NUCLEO_DESDE_SERVER():
    culpables = []
    for carpeta in ("routes", "services", "models", "utils"):
        for archivo in (_BACKEND / carpeta).rglob("*.py"):
            if re.search(r"^\s*(from|import)\s+nucleo\b", archivo.read_text(encoding="utf-8"), re.M):
                culpables.append(str(archivo.relative_to(_BACKEND)))
    if re.search(r"^\s*(from|import)\s+nucleo\b", (_BACKEND / "admin_routes.py").read_text(encoding="utf-8"), re.M):
        culpables.append("admin_routes.py")
    assert not culpables, culpables
    assert re.search(r"^\s*from nucleo\.rutas import router", (_BACKEND / "server.py").read_text(encoding="utf-8"), re.M)


def test_la_migracion_deja_las_mismas_tablas_que_el_metadata(tmp_path):
    pytest.importorskip("alembic")
    from sqlalchemy import create_engine, inspect
    from nucleo.esquema import metadata
    ruta = tmp_path / "nucleo.db"
    env = dict(os.environ, NUCLEO_DATABASE_URL=f"sqlite+aiosqlite:///{ruta}")
    r = subprocess.run([sys.executable, "-m", "alembic", "-c", str(NUCLEO / "migraciones" / "alembic.ini"),
                        "upgrade", "head"], cwd=_BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-1500:]
    motor = create_engine(f"sqlite:///{ruta}")
    ins = inspect(motor)
    tablas = set(ins.get_table_names()) - {"alembic_version"}
    assert tablas == set(metadata.tables), (tablas, set(metadata.tables))
    for nombre, tabla in metadata.tables.items():
        columnas = {c["name"] for c in ins.get_columns(nombre)}
        assert columnas == {c.name for c in tabla.columns}, (nombre, columnas)


def test_el_esquema_no_se_baja():
    """El downgrade está escrito para fallar: el libro no se borra con un comando."""
    texto = (NUCLEO / "migraciones" / "versiones" / "0001_el_libro.py").read_text(encoding="utf-8")
    m = re.search(r"def downgrade\(\):(.*)", texto, re.S)
    assert m and "raise" in m.group(1)
