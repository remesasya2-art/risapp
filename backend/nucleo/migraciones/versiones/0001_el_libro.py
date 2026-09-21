"""El esquema inicial del núcleo: plan de cuentas, cuentas, asientos, partidas y cierres.

Revisión: 0001
Anterior: ninguna

Escrita a mano a partir de `nucleo/esquema.py`, y un test comprueba que
las dos digan lo mismo. Los CHECK se repiten acá porque un esquema
migrado sin ellos aceptaría una partida con debe y haber a la vez.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "plan_de_cuentas",
        sa.Column("codigo", sa.String(20), primary_key=True),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("grupo", sa.String(20), nullable=False),
        sa.Column("naturaleza", sa.String(10), nullable=False),
        sa.Column("de_titulares", sa.Boolean, nullable=False, default=False),
        sa.CheckConstraint("naturaleza in ('deudora','acreedora')", name="naturaleza_valida"),
    )
    op.create_table(
        "cuentas",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("titular_ref", sa.String(80), nullable=False),
        sa.Column("cuenta_contable", sa.String(20), sa.ForeignKey("plan_de_cuentas.codigo"), nullable=False),
        sa.Column("moneda", sa.String(3), nullable=False, default="BRL"),
        sa.Column("estado", sa.String(12), nullable=False, default="activa"),
        sa.Column("de_prueba", sa.Boolean, nullable=False, default=True),
        sa.Column("creada", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("estado in ('activa','bloqueada','cerrada')", name="estado_valido"),
    )
    op.create_index("ix_cuentas_titular", "cuentas", ["titular_ref"])
    op.create_table(
        "asientos",
        sa.Column("numero", sa.BigInteger, primary_key=True, autoincrement=False),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("descripcion", sa.String(200), nullable=False),
        sa.Column("referencia", sa.String(120), nullable=False),
        sa.Column("comando", sa.String(40), nullable=False),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("hash_previo", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("referencia", name="uq_asientos_referencia"),
        sa.UniqueConstraint("hash", name="uq_asientos_hash"),
    )
    op.create_index("ix_asientos_fecha", "asientos", ["fecha"])
    op.create_table(
        "partidas",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("asiento", sa.BigInteger, sa.ForeignKey("asientos.numero"), nullable=False),
        sa.Column("orden", sa.Integer, nullable=False),
        sa.Column("cuenta_contable", sa.String(20), sa.ForeignKey("plan_de_cuentas.codigo"), nullable=False),
        sa.Column("cuenta", sa.String(40), sa.ForeignKey("cuentas.id"), nullable=True),
        sa.Column("debe", sa.BigInteger, nullable=False, default=0),
        sa.Column("haber", sa.BigInteger, nullable=False, default=0),
        sa.CheckConstraint("debe >= 0 and haber >= 0", name="montos_no_negativos"),
        sa.CheckConstraint("(debe > 0) <> (haber > 0)", name="una_sola_columna"),
    )
    op.create_index("ix_partidas_cuenta", "partidas", ["cuenta"])
    op.create_index("ix_partidas_asiento", "partidas", ["asiento"])
    op.create_table(
        "cierres",
        sa.Column("dia", sa.Date, primary_key=True),
        sa.Column("hasta_asiento", sa.BigInteger, nullable=False),
        sa.Column("hash_final", sa.String(64), nullable=False),
        sa.Column("asientos", sa.Integer, nullable=False),
        sa.Column("total_debe", sa.BigInteger, nullable=False),
        sa.Column("total_haber", sa.BigInteger, nullable=False),
        sa.Column("cerrado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("cerrado_por", sa.String(80), nullable=False),
        sa.Column("nota", sa.Text, nullable=True),
    )


def downgrade():
    # El libro no se baja: un downgrade que borre asientos es lo contrario
    # de lo que este esquema promete. Si hace falta, se hace a mano y con
    # respaldo.
    raise RuntimeError("El esquema del núcleo no se baja: el libro es inmutable.")
