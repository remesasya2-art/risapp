"""
El plan de cuentas inicial del núcleo, y quién puede tocar qué.

    Reducido a lo que hace falta para una instituição de pagamento que emite
    dinero electrónico, con la numeración en el espíritu del COSIF (activo 1,
    pasivo 2, patrimonio 3, ingreso 4, egreso 5). Los códigos exactos del
    COSIF se ajustan el día del reporte regulatorio; la estructura es la que
    importa ahora, y está en un solo lugar.

    La cuenta 2.1.01 es la única de la que cuelgan cuentas de pago de
    titulares: el saldo de un cliente es un PASIVO de la institución, igual
    que en `services/contabilidad.py`.
"""

CUENTAS = (
    # código,   nombre,                                    grupo,        naturaleza,  de titulares
    ("1.1.01", "Caja y disponibilidades",                  "activo",     "deudora",   False),
    ("1.1.02", "Bancos: cuenta de liquidación",            "activo",     "deudora",   False),
    ("1.1.03", "Reserva en el Banco Central (Conta PI)",   "activo",     "deudora",   False),
    ("1.2.01", "Cobros en tránsito",                       "activo",     "deudora",   False),
    ("2.1.01", "Cuentas de pago de titulares",             "pasivo",     "acreedora", True),
    ("2.1.02", "Obligaciones por pagos en tránsito",       "pasivo",     "acreedora", False),
    ("2.2.01", "Tarifas cobradas por adelantado",          "pasivo",     "acreedora", False),
    ("3.1.01", "Capital social",                           "patrimonio", "acreedora", False),
    ("3.2.01", "Resultados acumulados",                    "patrimonio", "acreedora", False),
    ("4.1.01", "Ingresos por tarifas",                     "ingreso",    "acreedora", False),
    ("4.2.01", "Ingresos por cambio",                      "ingreso",    "acreedora", False),
    ("5.1.01", "Costos de rieles de pago",                 "egreso",     "deudora",   False),
    ("5.1.02", "Pérdidas por fraude y devoluciones",       "egreso",     "deudora",   False),
    ("5.9.99", "Cuenta puente (movimientos sin clasificar)", "egreso",   "deudora",   False),
)

# Las que usan los comandos del libro. Nombradas acá y no repartidas por el
# código: si un día cambia un código, cambia en un lugar.
DE_TITULARES = "2.1.01"
LIQUIDACION = "1.1.02"
TRANSITO = "2.1.02"        # pagos salientes ya ordenados y todavía no liquidados por el SPI
TARIFAS = "4.1.01"
CAPITAL = "3.1.01"
PUENTE = "5.9.99"


async def sembrar(sesion):
    """Deja el plan en la base si no está. Idempotente."""
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql, sqlite
    from nucleo.esquema import plan_de_cuentas
    existentes = {c for (c,) in (await sesion.execute(select(plan_de_cuentas.c.codigo))).all()}
    filas = [dict(codigo=c, nombre=n, grupo=g, naturaleza=nat, de_titulares=t)
             for c, n, g, nat, t in CUENTAS if c not in existentes]
    if filas:
        await sesion.execute(plan_de_cuentas.insert(), filas)
    return len(filas)
