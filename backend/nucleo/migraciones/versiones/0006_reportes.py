"""Reportes regulatorios: la tabla de reportes generados y transmitidos, y
la fecha de cierre de las cuentas (que el CCS informa).

Revisión: 0006
Anterior: 0005

Escrita a mano a partir de `nucleo/esquema.py`; el test de las migraciones
la compara con el metadata. El único de `(tipo, periodo, version)` es el que
hace que una corrección sea una versión nueva y no una segunda «primera».
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cuentas") as lote:
        lote.add_column(sa.Column("cerrada_en", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "reportes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("periodo", sa.String(10), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("documento", sa.String(30), nullable=False),
        sa.Column("archivo", sa.Text, nullable=False),
        sa.Column("resumen", sa.Text, nullable=False),
        sa.Column("generado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generado_por", sa.String(80), nullable=False),
        sa.Column("transmitido_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transmitido_por", sa.String(80), nullable=True),
        sa.Column("protocolo", sa.String(60), nullable=True),
        sa.Column("transmisor", sa.String(40), nullable=True),
        sa.UniqueConstraint("tipo", "periodo", "version", name="uq_reportes_tipo_periodo_version"),
    )
    op.create_index("ix_reportes_tipo_periodo", "reportes", ["tipo", "periodo"])


def downgrade():
    # Lo que se le mandó al regulador se conserva. No se baja con un comando.
    raise RuntimeError("El esquema del núcleo no se baja: los reportes transmitidos se conservan.")
