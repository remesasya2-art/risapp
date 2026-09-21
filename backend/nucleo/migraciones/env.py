"""
Las migraciones del núcleo, con Alembic.

    En producción el esquema lo llevan estas migraciones: `alembic upgrade
    head` desde `backend/`, con `NUCLEO_DATABASE_URL` en el entorno. En los
    tests se crea el esquema desde el metadata, y un test comprueba que las
    migraciones y el metadata digan lo mismo: una tabla que se agregue al
    esquema sin su migración se pone en rojo.
"""
import asyncio
import os
import sys

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from nucleo.esquema import metadata  # noqa: E402

target_metadata = metadata


def _url():
    return (os.environ.get("NUCLEO_DATABASE_URL") or "").strip()


def run_migrations_offline():
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    url = _url()
    if not url:
        raise SystemExit("Falta NUCLEO_DATABASE_URL: el núcleo no sabe dónde migrar.")
    motor = create_async_engine(url)
    async with motor.connect() as conn:
        await conn.run_sync(_do_run)
    await motor.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
