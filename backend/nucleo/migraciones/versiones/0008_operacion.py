"""Operación: la bitácora encadenada y los pedidos de cuatro ojos.

Revisión: 0008
Anterior: 0007

Escrita a mano a partir de `nucleo/esquema.py`; el test de las migraciones
la compara con el metadata. El único del hash de la bitácora es el que hace
que dos renglones no puedan decir lo mismo en el mismo eslabón.
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bitacora",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("accion", sa.String(40), nullable=False),
        sa.Column("objetivo", sa.String(120), nullable=False),
        sa.Column("antes", sa.Text, nullable=True),
        sa.Column("despues", sa.Text, nullable=True),
        sa.Column("detalle", sa.String(300), nullable=True),
        sa.Column("hash_previo", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("hash", name="uq_bitacora_hash"),
    )
    op.create_index("ix_bitacora_accion", "bitacora", ["accion"])
    op.create_index("ix_bitacora_objetivo", "bitacora", ["objetivo"])
    op.create_table(
        "aprobaciones",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("accion", sa.String(40), nullable=False),
        sa.Column("objetivo", sa.String(120), nullable=False),
        sa.Column("carga", sa.Text, nullable=False),
        sa.Column("motivo", sa.String(300), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("pedido_por", sa.String(80), nullable=False),
        sa.Column("pedido_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vence_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decidido_por", sa.String(80), nullable=True),
        sa.Column("decidido_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("nota", sa.String(300), nullable=True),
        sa.Column("ejecutado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resultado", sa.Text, nullable=True),
        sa.CheckConstraint("estado in ('pendiente','aprobado','rechazado','ejecutado','fallido','vencido')", name="estado_de_la_aprobacion_valido"),
    )
    op.create_index("ix_aprobaciones_estado", "aprobaciones", ["estado"])


def downgrade():
    # La bitácora es la prueba de quién hizo qué. No se baja con un comando.
    raise RuntimeError("El esquema del núcleo no se baja: la bitácora y las aprobaciones se conservan.")
