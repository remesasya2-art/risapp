"""La bandeja de salida y la cola de trabajos.

Revisión: 0002
Anterior: 0001

Escrita a mano a partir de `nucleo/esquema.py`; el mismo test que compara
la 0001 con el metadata compara ésta. Los CHECK y los únicos se repiten
acá porque una cola sin la restricción única aceptaría el mismo trabajo
dos veces, que es justamente lo que la cola promete que no pasa.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "eventos",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tipo", sa.String(60), nullable=False),
        sa.Column("clave", sa.String(120), nullable=False),
        sa.Column("carga", sa.Text, nullable=False),
        sa.Column("creado", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("publicado", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tipo", "clave", name="uq_eventos_tipo_clave"),
    )
    op.create_index("ix_eventos_publicado", "eventos", ["publicado"])
    op.create_table(
        "trabajos",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tipo", sa.String(60), nullable=False),
        sa.Column("clave", sa.String(120), nullable=False),
        sa.Column("carga", sa.Text, nullable=False),
        sa.Column("estado", sa.String(12), nullable=False, default="pendiente"),
        sa.Column("intentos", sa.Integer, nullable=False, default=0),
        sa.Column("max_intentos", sa.Integer, nullable=False, default=6),
        sa.Column("proximo_intento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tomado_por", sa.String(80), nullable=True),
        sa.Column("tomado_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_error", sa.Text, nullable=True),
        sa.Column("resultado", sa.Text, nullable=True),
        sa.Column("origen_evento", sa.Integer, sa.ForeignKey("eventos.id"), nullable=True),
        sa.Column("creado", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("terminado", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tipo", "clave", name="uq_trabajos_tipo_clave"),
        sa.CheckConstraint("estado in ('pendiente','en_curso','hecho','muerto')", name="estado_del_trabajo_valido"),
        sa.CheckConstraint("intentos >= 0 and max_intentos > 0", name="intentos_validos"),
    )
    op.create_index("ix_trabajos_para_tomar", "trabajos", ["estado", "proximo_intento"])


def downgrade():
    # Igual que la 0001: la bandeja de salida es parte del registro de lo
    # que pasó. No se baja con un comando.
    raise RuntimeError("El esquema del núcleo no se baja: los eventos son parte del libro.")
