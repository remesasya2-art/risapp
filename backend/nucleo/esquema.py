"""
El esquema del núcleo. Cinco tablas, y cada columna con su porqué.

    plan_de_cuentas   el plan contable (estilo COSIF, reducido). Cada cuenta
                      tiene naturaleza deudora o acreedora: es lo que decide
                      si un débito la sube o la baja.
    cuentas           las cuentas de pago de los titulares. Cada una cuelga
                      de una cuenta del plan (el pasivo «contas de pagamento»).
    asientos          el libro: uno por movimiento, con número correlativo,
                      hash del anterior y hash propio. NUNCA se edita ni se
                      borra: no hay función que lo haga.
    partidas          las líneas de cada asiento: debe o haber, en centavos.
                      La suma de debes es igual a la de haberes, siempre; lo
                      exige el código antes de escribir.
    cierres           un renglón por día cerrado: hasta qué asiento, con qué
                      hash, y los totales. Después del cierre no se asienta
                      con fecha de ese día ni anterior.

EL DINERO ES BIGINT EN CENTAVOS

    Ver el encabezado del paquete. Un `NUMERIC` sería exacto en Postgres y
    flotante en SQLite; el entero es exacto en las dos y no hay dos caminos.
"""
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey,
    Index, Integer, MetaData, String, Table, Text, UniqueConstraint, func,
)

metadata = MetaData()

# Naturalezas contables. Deudora: el débito la aumenta (activo, egreso).
# Acreedora: el crédito la aumenta (pasivo, patrimonio, ingreso).
DEUDORA = "deudora"
ACREEDORA = "acreedora"

plan_de_cuentas = Table(
    "plan_de_cuentas", metadata,
    Column("codigo", String(20), primary_key=True),          # «2.1.01»
    Column("nombre", String(120), nullable=False),
    Column("grupo", String(20), nullable=False),              # activo, pasivo, patrimonio, ingreso, egreso
    Column("naturaleza", String(10), nullable=False),
    Column("de_titulares", Boolean, nullable=False, default=False),  # ¿cuelgan cuentas de pago de acá?
    CheckConstraint("naturaleza in ('deudora','acreedora')", name="naturaleza_valida"),
)

cuentas = Table(
    "cuentas", metadata,
    Column("id", String(40), primary_key=True),               # «cta_…»
    Column("titular_ref", String(80), nullable=False),        # referencia al titular en la app (user_id)
    Column("cuenta_contable", String(20), ForeignKey("plan_de_cuentas.codigo"), nullable=False),
    Column("moneda", String(3), nullable=False, default="BRL"),
    Column("estado", String(12), nullable=False, default="activa"),  # activa, bloqueada, cerrada
    Column("de_prueba", Boolean, nullable=False, default=True),      # todo lo del laboratorio es de prueba
    Column("creada", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("estado in ('activa','bloqueada','cerrada')", name="estado_valido"),
    Index("ix_cuentas_titular", "titular_ref"),
)

asientos = Table(
    "asientos", metadata,
    Column("numero", BigInteger, primary_key=True, autoincrement=False),  # correlativo, lo asigna el libro
    Column("fecha", Date, nullable=False),                    # día contable
    Column("momento", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("descripcion", String(200), nullable=False),
    Column("referencia", String(120), nullable=False),        # idempotencia: una referencia, un asiento
    Column("comando", String(40), nullable=False),            # acreditar, debitar, transferir, tarifa, ajuste
    Column("actor", String(80), nullable=False),              # quién lo ordenó
    Column("hash_previo", String(64), nullable=False),
    Column("hash", String(64), nullable=False),
    UniqueConstraint("referencia", name="uq_asientos_referencia"),
    UniqueConstraint("hash", name="uq_asientos_hash"),
    Index("ix_asientos_fecha", "fecha"),
)

partidas = Table(
    "partidas", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("asiento", BigInteger, ForeignKey("asientos.numero"), nullable=False),
    Column("orden", Integer, nullable=False),                 # posición dentro del asiento
    Column("cuenta_contable", String(20), ForeignKey("plan_de_cuentas.codigo"), nullable=False),
    Column("cuenta", String(40), ForeignKey("cuentas.id"), nullable=True),  # sólo si es de un titular
    Column("debe", BigInteger, nullable=False, default=0),    # centavos
    Column("haber", BigInteger, nullable=False, default=0),   # centavos
    CheckConstraint("debe >= 0 and haber >= 0", name="montos_no_negativos"),
    CheckConstraint("(debe > 0) <> (haber > 0)", name="una_sola_columna"),
    Index("ix_partidas_cuenta", "cuenta"),
    Index("ix_partidas_asiento", "asiento"),
)

cierres = Table(
    "cierres", metadata,
    Column("dia", Date, primary_key=True),
    Column("hasta_asiento", BigInteger, nullable=False),      # el último asiento incluido (0 si no hubo)
    Column("hash_final", String(64), nullable=False),
    Column("asientos", Integer, nullable=False),
    Column("total_debe", BigInteger, nullable=False),
    Column("total_haber", BigInteger, nullable=False),
    Column("cerrado_en", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("cerrado_por", String(80), nullable=False),
    Column("nota", Text, nullable=True),
)

# El hash del que no tiene anterior. Sesenta y cuatro ceros: se lee a simple
# vista como «el principio».
HASH_DEL_PRINCIPIO = "0" * 64
