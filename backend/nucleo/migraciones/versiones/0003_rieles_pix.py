"""Los rieles de pago: operaciones, su línea de tiempo, los avisos del riel
y el directorio de claves del simulador.

Revisión: 0003
Anterior: 0002

Escrita a mano a partir de `nucleo/esquema.py`; el test de las migraciones
la compara con el metadata, únicos e índices incluidos. Los únicos importan:
`end_to_end` único es lo que hace que un aviso repetido del SPI no cree
dos operaciones, y `(riel, id_externo)` único es lo que hace que un aviso
repetido no se procese dos veces.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "operaciones",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("riel", sa.String(20), nullable=False),
        sa.Column("direccion", sa.String(12), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("cuenta", sa.String(40), sa.ForeignKey("cuentas.id"), nullable=False),
        sa.Column("monto", sa.BigInteger, nullable=False),
        sa.Column("referencia", sa.String(120), nullable=False),
        sa.Column("txid", sa.String(35), nullable=True),
        sa.Column("end_to_end", sa.String(32), nullable=True),
        sa.Column("clave", sa.String(120), nullable=True),
        sa.Column("contraparte", sa.Text, nullable=True),
        sa.Column("descripcion", sa.String(140), nullable=True),
        sa.Column("motivo", sa.String(200), nullable=True),
        sa.Column("origen", sa.String(40), sa.ForeignKey("operaciones.id"), nullable=True),
        sa.Column("codigo_br", sa.Text, nullable=True),
        sa.Column("creada", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("actualizada", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("referencia", name="uq_operaciones_referencia"),
        sa.UniqueConstraint("end_to_end", name="uq_operaciones_end_to_end"),
        sa.CheckConstraint("direccion in ('entrada','salida','devolucion')", name="direccion_valida"),
        sa.CheckConstraint("monto > 0", name="monto_positivo"),
    )
    op.create_index("ix_operaciones_cuenta", "operaciones", ["cuenta"])
    op.create_index("ix_operaciones_txid", "operaciones", ["txid"])
    op.create_table(
        "operacion_estados",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("operacion", sa.String(40), sa.ForeignKey("operaciones.id"), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("detalle", sa.String(300), nullable=True),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_operacion_estados_operacion", "operacion_estados", ["operacion"])
    op.create_table(
        "avisos_riel",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("riel", sa.String(20), nullable=False),
        sa.Column("id_externo", sa.String(120), nullable=False),
        sa.Column("tipo", sa.String(40), nullable=False),
        sa.Column("carga", sa.Text, nullable=False),
        sa.Column("recibido", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("procesado", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resultado", sa.String(200), nullable=True),
        sa.UniqueConstraint("riel", "id_externo", name="uq_avisos_riel_externo"),
    )
    op.create_table(
        "sim_claves",
        sa.Column("clave", sa.String(120), primary_key=True),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("documento", sa.String(20), nullable=False),
        sa.Column("ispb", sa.String(8), nullable=False),
        sa.Column("banco", sa.String(80), nullable=False),
        sa.Column("comportamiento", sa.String(12), nullable=False, default="normal"),
    )


def downgrade():
    # Las operaciones y los avisos son el rastro de cada real que entró o
    # salió por un riel. No se bajan con un comando.
    raise RuntimeError("El esquema del núcleo no se baja: las operaciones son parte del libro.")
