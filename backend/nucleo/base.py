"""
La base de datos del núcleo: relacional, con transacciones de verdad.

POR QUE NO ES MONGO

    El informe de arquitectura lo marcó: un libro de cuentas necesita
    transacciones ACID entre varias tablas, numéricos exactos y un esquema
    con migraciones. Mongo las tiene sólo con conjunto de réplicas, y sin
    esquema. Postgres es lo que un auditor espera debajo de un libro.

DONDE ESTA

    `NUCLEO_DATABASE_URL`, por ejemplo `postgresql+asyncpg://…`. Sin ella el
    núcleo se declara «sin base»: las rutas del laboratorio contestan 503 con
    ese mensaje y el resto de la aplicación ni se entera. Los tests usan
    SQLite en memoria (`sqlite+aiosqlite://`) y la misma lógica; los enteros
    en centavos son exactos en las dos.

UN SOLO MOTOR POR PROCESO

    Se crea la primera vez que se pide y se guarda. `usar(url)` lo reemplaza,
    y existe para los tests y para la vista previa, igual que `usar_base` en
    `tests/conftest.py`.
"""
import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

VARIABLE = "NUCLEO_DATABASE_URL"

_motor = None
_sesiones = None
_url_en_uso = None


def url_configurada() -> str:
    return (os.environ.get(VARIABLE) or "").strip()


def usar(url: str):
    """Apunta el núcleo a esta base. Devuelve el motor."""
    global _motor, _sesiones, _url_en_uso
    if url.startswith("sqlite"):
        # Una base en memoria vive en UNA conexión; sin el StaticPool cada
        # sesión abriría la suya y vería una base vacía distinta.
        _motor = create_async_engine(url, poolclass=StaticPool,
                                     connect_args={"check_same_thread": False})
    else:
        _motor = create_async_engine(url, pool_pre_ping=True)
    _sesiones = async_sessionmaker(_motor, expire_on_commit=False, class_=AsyncSession)
    _url_en_uso = url
    return _motor


def motor():
    """El motor vigente, o None si no hay base configurada."""
    global _motor
    if _motor is None:
        url = url_configurada()
        if url:
            usar(url)
    return _motor


def hay_base() -> bool:
    return motor() is not None


@asynccontextmanager
async def sesion():
    """Una sesión con transacción: se confirma al salir, se deshace si algo
    falla. Todo lo que toca el libro pasa por acá."""
    if motor() is None:
        raise SinBase()
    async with _sesiones() as s:
        async with s.begin():
            yield s


class SinBase(RuntimeError):
    """No hay `NUCLEO_DATABASE_URL`. No es un error de la aplicación: es que
    el núcleo no tiene dónde escribir."""

    def __init__(self):
        super().__init__(f"El núcleo no tiene base: falta {VARIABLE}.")


def descripcion_de_la_url() -> str:
    """Para mostrar en el panel sin filtrar credenciales: sólo el motor."""
    url = _url_en_uso or url_configurada()
    if not url:
        return "sin configurar"
    return url.split(":", 1)[0]


async def crear_todo():
    """Crea el esquema desde el metadata. SOLO para tests y vista previa: en
    producción el esquema lo llevan las migraciones de Alembic."""
    from nucleo.esquema import metadata
    async with motor().begin() as conn:
        await conn.run_sync(metadata.create_all)
