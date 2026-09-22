"""
El plan de cuentas inicial del núcleo, y quién puede tocar qué.

    Reducido a lo que hace falta para una instituição de pagamento que emite
    dinero electrónico, con la numeración en el espíritu del COSIF (activo 1,
    pasivo 2, patrimonio 3, ingreso 4, egreso 5). La estructura es la que
    importa, y está en un solo lugar.

EL CODIGO COSIF DE CADA CUENTA

    El COSIF es el plan de cuentas que el Banco Central le impone a todas las
    instituciones que supervisa; el balancete mensual (documento 4010) se
    manda con esos códigos, no con los nuestros. `COSIF` dice a qué código
    del COSIF va cada cuenta de acá. Varias cuentas nuestras pueden ir al
    mismo código: el balancete las suma.

    SON PROVISORIOS. Están en la familia correcta del COSIF (caixa, depósitos
    bancários, obrigações por contas de pagamento, receitas de serviços...),
    pero el código exacto, con su dígito verificador, lo confirma el contador
    antes del primer envío de verdad. El balancete lo dice en su cabecera
    (`"plan": "provisorio"`) para que nadie lo mande creyendo que ya está.
    Hay un test que exige que TODAS las cuentas tengan uno: una cuenta sin
    código COSIF es plata que se cae del balancete.

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

# Provisorios: ver el encabezado. Formato del COSIF sin dígito verificador.
COSIF = {
    "1.1.01": "1.1.1.10.00",   # CAIXA
    "1.1.02": "1.1.2.10.00",   # DEPÓSITOS BANCÁRIOS · bancos, conta de liquidação
    "1.1.03": "1.1.3.10.00",   # RESERVAS NO BANCO CENTRAL · Conta PI
    "1.2.01": "1.8.9.10.00",   # OUTROS CRÉDITOS · valores em trânsito
    "2.1.01": "4.9.1.10.00",   # OBRIGAÇÕES POR CONTAS DE PAGAMENTO · recursos de titulares
    "2.1.02": "4.9.1.20.00",   # OBRIGAÇÕES POR PAGAMENTOS EM TRÂNSITO
    "2.2.01": "4.9.9.10.00",   # OUTRAS OBRIGAÇÕES · receitas antecipadas
    "3.1.01": "6.1.1.10.00",   # CAPITAL SOCIAL
    "3.2.01": "6.1.7.10.00",   # LUCROS OU PREJUÍZOS ACUMULADOS
    "4.1.01": "7.1.7.10.00",   # RENDAS DE PRESTAÇÃO DE SERVIÇOS · tarifas
    "4.2.01": "7.1.5.10.00",   # RENDAS DE OPERAÇÕES DE CÂMBIO
    "5.1.01": "8.1.7.10.00",   # DESPESAS DE SERVIÇOS DO SISTEMA FINANCEIRO · rieles
    "5.1.02": "8.1.9.10.00",   # OUTRAS DESPESAS OPERACIONAIS · fraudes e devoluções
    "5.9.99": "8.1.9.99.00",   # OUTRAS DESPESAS · sem classificação
}


def cosif_de(codigo: str) -> str:
    """El código COSIF de una cuenta nuestra. Lanza si no tiene: es un
    error de programación, no un dato faltante."""
    return COSIF[codigo]


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
