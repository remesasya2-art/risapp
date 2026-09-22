"""Cumplimiento: el registro de incidentes con sus notas, y los reclamos de
la ouvidoria.

Revisión: 0007
Anterior: 0006

Escrita a mano a partir de `nucleo/esquema.py`; el test de las migraciones
la compara con el metadata. El único del protocolo del reclamo es el que
hace que dos reclamos no se dicten con el mismo número.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "incidentes",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fin", sa.DateTime(timezone=True), nullable=True),
        sa.Column("impacto", sa.Text, nullable=False),
        sa.Column("clientes_afectados", sa.Integer, nullable=False),
        sa.Column("relevante", sa.Boolean, nullable=False),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("causa", sa.Text, nullable=True),
        sa.Column("acciones", sa.Text, nullable=True),
        sa.Column("abierto_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("abierto_por", sa.String(80), nullable=False),
        sa.Column("comunicar_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comunicado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comunicado_por", sa.String(80), nullable=True),
        sa.Column("protocolo", sa.String(60), nullable=True),
        sa.Column("cerrado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cerrado_por", sa.String(80), nullable=True),
        sa.CheckConstraint("estado in ('abierto','cerrado')", name="estado_del_incidente_valido"),
    )
    op.create_table(
        "incidente_notas",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("incidente", sa.String(40), sa.ForeignKey("incidentes.id"), nullable=False),
        sa.Column("autor", sa.String(80), nullable=False),
        sa.Column("texto", sa.Text, nullable=False),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_incidente_notas_incidente", "incidente_notas", ["incidente"])
    op.create_table(
        "reclamos",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("protocolo", sa.String(20), nullable=False),
        sa.Column("titular", sa.String(40), nullable=True),
        sa.Column("canal", sa.String(20), nullable=False),
        sa.Column("asunto", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text, nullable=False),
        sa.Column("caso_soporte", sa.String(20), nullable=True),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("abierto_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("abierto_por", sa.String(80), nullable=False),
        sa.Column("responder_hasta", sa.Date, nullable=False),
        sa.Column("respuesta", sa.Text, nullable=True),
        sa.Column("resultado", sa.String(15), nullable=True),
        sa.Column("respondido_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("respondido_por", sa.String(80), nullable=True),
        sa.UniqueConstraint("protocolo", name="uq_reclamos_protocolo"),
        sa.CheckConstraint("estado in ('abierto','respondido')", name="estado_del_reclamo_valido"),
    )


def downgrade():
    # Incidentes y reclamos se conservan cinco años como mínimo. No se bajan
    # con un comando.
    raise RuntimeError("El esquema del núcleo no se baja: los incidentes y los reclamos se conservan.")
