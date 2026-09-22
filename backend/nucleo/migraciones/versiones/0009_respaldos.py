"""Respaldos: el registro de cada exportación de lo que se conserva y de su
comprobación.

Revisión: 0009
Anterior: 0008

Escrita a mano a partir de `nucleo/esquema.py`; el test de las migraciones
la compara con el metadata. El único del hash es el que hace que el mismo
archivo no figure dos veces.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "respaldos",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("filas", sa.Integer, nullable=False),
        sa.Column("tablas", sa.Text, nullable=False),
        sa.Column("bytes", sa.Integer, nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("firmado", sa.Boolean, nullable=False),
        sa.Column("comprobado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comprobacion", sa.Text, nullable=True),
        sa.UniqueConstraint("hash", name="uq_respaldos_hash"),
    )


def downgrade():
    # El registro de los respaldos es la prueba de que se hicieron. No se
    # baja con un comando.
    raise RuntimeError("El esquema del núcleo no se baja: el registro de respaldos se conserva.")
