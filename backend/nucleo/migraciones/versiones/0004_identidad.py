"""Identidad: el legajo del titular, sus verificaciones y sus cruces con
las listas, y las tablas de prueba del simulador.

Revisión: 0004
Anterior: 0003

Escrita a mano a partir de `nucleo/esquema.py`; el test de las migraciones
la compara con el metadata. El único de `documento` es el que hace que una
persona tenga UN legajo, y no uno por cada vez que alguien la cargó.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "titulares",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("documento", sa.String(14), nullable=False),
        sa.Column("tipo", sa.String(4), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("nacimiento", sa.Date, nullable=True),
        sa.Column("ocupacion", sa.String(80), nullable=True),
        sa.Column("renta_declarada", sa.BigInteger, nullable=True),
        sa.Column("pep_declarado", sa.Boolean, nullable=False, default=False),
        sa.Column("pep", sa.Boolean, nullable=False, default=False),
        sa.Column("origen_de_fondos", sa.String(30), nullable=True),
        sa.Column("nivel_de_riesgo", sa.String(8), nullable=True),
        sa.Column("estado", sa.String(12), nullable=False, default="incompleto"),
        sa.Column("vigente_hasta", sa.Date, nullable=True),
        sa.Column("motivo", sa.String(300), nullable=True),
        sa.Column("decidido_por", sa.String(80), nullable=True),
        sa.Column("cruzado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("actualizado", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("documento", name="uq_titulares_documento"),
        sa.CheckConstraint("estado in ('incompleto','en_revision','aprobado','rechazado','vencido')", name="estado_del_legajo_valido"),
    )
    op.create_table(
        "verificaciones",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("titular", sa.String(40), sa.ForeignKey("titulares.id"), nullable=False),
        sa.Column("proveedor", sa.String(40), nullable=False),
        sa.Column("puntaje_documento", sa.Integer, nullable=False),
        sa.Column("puntaje_vida", sa.Integer, nullable=False),
        sa.Column("puntaje_rostro", sa.Integer, nullable=False),
        sa.Column("situacion_cpf", sa.String(20), nullable=False),
        sa.Column("nombre_en_documento", sa.String(120), nullable=False),
        sa.Column("documento_vencido", sa.Boolean, nullable=False, default=False),
        sa.Column("aprobada", sa.Boolean, nullable=False),
        sa.Column("motivos", sa.Text, nullable=True),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_verificaciones_titular", "verificaciones", ["titular"])
    op.create_table(
        "cruces",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("titular", sa.String(40), sa.ForeignKey("titulares.id"), nullable=False),
        sa.Column("lista", sa.String(20), nullable=False),
        sa.Column("clase", sa.String(10), nullable=False),
        sa.Column("nombre_en_lista", sa.String(120), nullable=False),
        sa.Column("detalle", sa.String(300), nullable=True),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resuelto", sa.Boolean, nullable=False, default=False),
        sa.Column("resolucion", sa.String(300), nullable=True),
        sa.Column("resuelto_por", sa.String(80), nullable=True),
        sa.Column("resuelto_en", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cruces_titular", "cruces", ["titular"])
    op.create_table(
        "sim_personas",
        sa.Column("documento", sa.String(14), primary_key=True),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("nacimiento", sa.String(10), nullable=False),
        sa.Column("comportamiento", sa.String(20), nullable=False, default="normal"),
    )
    op.create_table(
        "sim_listas",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("lista", sa.String(20), nullable=False),
        sa.Column("documento", sa.String(14), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("detalle", sa.String(300), nullable=True),
        sa.UniqueConstraint("lista", "documento", name="uq_sim_listas_lista_documento"),
    )


def downgrade():
    # El legajo es lo que prueba a quién se le abrió una cuenta y por qué.
    # Se conserva diez años (Circular 3.978): no se baja con un comando.
    raise RuntimeError("El esquema del núcleo no se baja: los legajos se conservan.")
