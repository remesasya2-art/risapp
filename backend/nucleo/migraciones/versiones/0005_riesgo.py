"""Riesgo: alertas del monitoreo, casos, sus notas y las comunicaciones al
COAF.

Revisión: 0005
Anterior: 0004

Escrita a mano a partir de `nucleo/esquema.py`; el test de las migraciones
la compara con el metadata. El único de `(operacion, regla)` es el que hace
que evaluar dos veces una operación no deje dos alertas.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "casos",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("titular", sa.String(40), nullable=False),
        sa.Column("origen", sa.String(10), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("analista", sa.String(80), nullable=True),
        sa.Column("detalle", sa.String(300), nullable=True),
        sa.Column("abierto_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analizar_hasta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("concluido_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conclusion", sa.Text, nullable=True),
        sa.Column("comunicar", sa.Boolean, nullable=True),
        sa.Column("comunicar_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aprobado_por", sa.String(80), nullable=True),
        sa.Column("comunicado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acuse", sa.String(60), nullable=True),
        sa.Column("archivado_en", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("estado in ('abierto','en_analisis','concluido','comunicado','archivado')", name="estado_del_caso_valido"),
    )
    op.create_index("ix_casos_titular", "casos", ["titular"])
    op.create_table(
        "alertas",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("titular", sa.String(40), nullable=False),
        sa.Column("cuenta", sa.String(40), sa.ForeignKey("cuentas.id"), nullable=False),
        sa.Column("operacion", sa.String(40), sa.ForeignKey("operaciones.id"), nullable=False),
        sa.Column("regla", sa.String(30), nullable=False),
        sa.Column("detalle", sa.Text, nullable=True),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("caso", sa.String(40), sa.ForeignKey("casos.id"), nullable=True),
        sa.UniqueConstraint("operacion", "regla", name="uq_alertas_operacion_regla"),
    )
    op.create_index("ix_alertas_titular", "alertas", ["titular"])
    op.create_table(
        "caso_notas",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("caso", sa.String(40), sa.ForeignKey("casos.id"), nullable=False),
        sa.Column("autor", sa.String(80), nullable=False),
        sa.Column("texto", sa.Text, nullable=False),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_caso_notas_caso", "caso_notas", ["caso"])
    op.create_table(
        "comunicaciones",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("caso", sa.String(40), sa.ForeignKey("casos.id"), nullable=True),
        sa.Column("tipo", sa.String(15), nullable=False),
        sa.Column("periodo", sa.Integer, nullable=True),
        sa.Column("archivo", sa.Text, nullable=False),
        sa.Column("acuse", sa.String(60), nullable=False),
        sa.Column("enviada_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enviada_por", sa.String(80), nullable=False),
        sa.Column("aprobada_por", sa.String(80), nullable=False),
        sa.Column("comunicador", sa.String(40), nullable=False),
    )


def downgrade():
    # Los casos y las comunicaciones al COAF se conservan diez años. No se
    # bajan con un comando.
    raise RuntimeError("El esquema del núcleo no se baja: los casos y las comunicaciones se conservan.")
