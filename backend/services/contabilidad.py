"""
services/contabilidad.py — El libro contable de verdad: diario, mayor y balance.

QUE HABIA
    Una pantalla llamada «Libro mayor» que NO era un libro mayor: era una
    herramienta de reconciliación con dos botones. La colección `ledger` sí
    existe y guarda cada movimiento del saldo RIS, pero:

    1. NO ES PARTIDA DOBLE. Cada línea es un movimiento de UN lado —la billetera
       del usuario— y no dice contra qué. Sin la contrapartida no hay balance de
       comprobación, no hay estado de resultados y no hay balance general.

    2. NO HAY PLAN DE CUENTAS. El campo `account` vale `balance_ris` o
       `balance_ris_terceros`. Eso no es un plan de cuentas: no distingue activo
       de pasivo, ni ingreso de egreso.

    3. LOS MONTOS SON `float`. `ledger.py` hace `abs(float(amount or 0))`,
       mientras el resto de la app cuida los saldos con `Decimal128`.
       (`sum_ris_balance` sumaba además con `$sum` de Mongo; hoy suma en
       Decimal, pero las líneas siguen guardándose en float.)

       HONESTIDAD SOBRE ESTE PUNTO: busqué un caso donde eso diera un total
       distinto y NO lo encontré. Redondeando a dos decimales, sumar cien mil
       líneas en float da lo mismo que en Decimal, y también con saldos de once
       cifras. Así que esto NO es un defecto con síntoma; es una diferencia de
       garantía. Acá se suma en Decimal porque es exacto POR CONSTRUCCIÓN y no
       por suerte, y porque es lo que usa el resto de la app — pero decir que
       «el libro estaba mal por los floats» sería inventar un problema.

    4. NO SE PUEDE NAVEGAR. `/admin/ledger/entries` existe pero exige un
       `user_id`, y la pantalla no tiene por dónde pedirlo. En la práctica el
       libro no se podía leer.

QUE HACE ESTE MODULO
    Construye, sobre esas mismas líneas, los tres libros que la contabilidad
    pide, con aritmética exacta:

      · LIBRO DIARIO   — cada asiento, cronológico, con sus dos partidas.
      · LIBRO MAYOR    — los movimientos agrupados por cuenta, con saldo
                         acumulado.
      · BALANCE DE COMPROBACION — sumas y saldos por cuenta.

    Y tres controles: la reconciliación contra los saldos guardados, la
    verificación de integridad, y el arqueo de cuentas.

LA CONTRAPARTIDA SE DERIVA, Y ESO TIENE UN LIMITE QUE HAY QUE DECIR
    Cada `movement_type` tiene una contrapartida determinada: una recarga por PIX
    entra por el banco de Brasil, un cobro de envío es un ingreso, un bono de
    referido es un egreso. `ASIENTOS` es ese mapa, y con él cada línea produce
    sus dos partidas.

    **Por eso el balance de comprobación CUADRA POR CONSTRUCCION.** No es un
    control de que los datos estén bien: es la estructura correcta sobre los
    datos que hay. El control de verdad son las otras dos cosas —la
    reconciliación contra `balance_ris` y el arqueo contra los extractos
    bancarios reales— y las dos están acá.

    Una partida doble NATIVA —dos asientos escritos en el momento de la
    operación, cada uno con su cuenta— es un cambio en los siete archivos que
    mueven plata. Es el paso siguiente, no este.

EL SALDO DEL USUARIO ES UN PASIVO
    Es la decisión contable que ordena todo lo demás: la plata que un usuario
    tiene en la app **es plata que la empresa le debe**. Por eso el saldo de los
    usuarios vive en el pasivo, una recarga lo AUMENTA (y aumenta el activo en el
    banco), y un retiro lo DISMINUYE (y disminuye el activo).
"""

import logging
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from services.money import ZERO, quantize_money, to_decimal

logger = logging.getLogger(__name__)

TOPE_ESCANEO = 200_000
FILAS_POR_PAGINA = 100
TOPE_FILAS = 2000


class ContabilidadInvalida(Exception):
    def __init__(self, mensaje: str, http: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.http = http


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


# ─── El plan de cuentas ───────────────────────────────────────────────────
#
# Estructura estandar de cinco grupos. El codigo jerarquico permite sumar por
# nivel —todo el activo, todo el pasivo— sin que la pantalla tenga que saber
# quien es hijo de quien.
#
# ESTE PLAN ES UNA PROPUESTA Y TIENE QUE VALIDARLO UN CONTADOR. Los nombres y
# los cortes son los habituales, pero el plan definitivo depende del pais donde
# se presenta y de como estan constituidas las sociedades.

ACTIVO, PASIVO, PATRIMONIO, INGRESO, EGRESO = (
    "activo", "pasivo", "patrimonio", "ingreso", "egreso")

# Las cuentas de activo y egreso AUMENTAN por el debe; las de pasivo,
# patrimonio e ingreso aumentan por el haber. Es lo que decide el signo del
# saldo de cada cuenta en el balance.
NATURALEZA_DEUDORA = frozenset({ACTIVO, EGRESO})

PLAN_DE_CUENTAS = OrderedDict([
    ("1.1.01", {"nombre": "Bancos en Brasil (BRL)", "tipo": ACTIVO}),
    ("1.1.02", {"nombre": "Bancos en Venezuela (VES)", "tipo": ACTIVO}),
    ("1.1.03", {"nombre": "Billeteras cripto (USDT / USDC)", "tipo": ACTIVO}),
    ("1.1.04", {"nombre": "Pasarelas de pago en tránsito", "tipo": ACTIVO}),
    ("1.1.99", {"nombre": "Efectivo sin identificar", "tipo": ACTIVO}),

    ("2.1.01", {"nombre": "Saldo RIS de usuarios", "tipo": PASIVO}),
    ("2.1.02", {"nombre": "Saldo RIS de terceros", "tipo": PASIVO}),
    ("2.1.03", {"nombre": "Créditos USDT de usuarios", "tipo": PASIVO}),
    ("2.1.04", {"nombre": "Créditos USDC de usuarios", "tipo": PASIVO}),
    # Contrapartida de los traspasos entre dos cuentas del MISMO usuario. Las
    # dos patas del traspaso caen acá con signos opuestos, así que esta cuenta
    # tiene que quedar SIEMPRE en cero: si no, hay un traspaso a medias.
    ("2.1.99", {"nombre": "Traspasos internos entre saldos", "tipo": PASIVO}),

    ("3.1.01", {"nombre": "Saldos de apertura", "tipo": PATRIMONIO}),

    ("4.1.01", {"nombre": "Ingresos por servicio de envíos", "tipo": INGRESO}),
    ("4.1.02", {"nombre": "Otros ingresos", "tipo": INGRESO}),

    ("5.1.01", {"nombre": "Bonos y promociones", "tipo": EGRESO}),
    ("5.1.02", {"nombre": "Reembolsos y ajustes", "tipo": EGRESO}),
    ("5.1.99", {"nombre": "Movimientos sin clasificar", "tipo": EGRESO}),
])

# La cuenta a la que va todo lo que el mapa no conoce. Existe para que un
# `movement_type` nuevo NO desaparezca del libro en silencio: aparece acá, con
# su nombre, y el chequeo de integridad lo denuncia.
SIN_CLASIFICAR = "5.1.99"


# ─── Los asientos ─────────────────────────────────────────────────────────
#
# Para cada `movement_type`, contra que cuenta va. La cuenta del USUARIO la pone
# el propio movimiento (`account`), asi que aca solo se declara la contrapartida
# y una descripcion legible.
#
# `direction` en el ledger dice si la billetera del usuario recibio (`credit`) o
# entrego (`debit`). Como la billetera es un PASIVO:
#   · credit  -> el pasivo AUMENTA -> se acredita el pasivo y se debita la contra
#   · debit   -> el pasivo DISMINUYE -> se debita el pasivo y se acredita la contra

ASIENTOS = {
    "saldo_apertura": {
        "contra": "3.1.01",
        "glosa": "Saldo de apertura del libro"},
    "recarga_pix": {
        "contra": "1.1.01",
        "glosa": "Recarga por PIX (Brasil)"},
    "recarga_ves": {
        "contra": "1.1.02",
        "glosa": "Recarga en bolívares (Venezuela)"},
    # Recarga en reales aprobada a mano por un administrador (comprobante de
    # transferencia). Va contra el mismo banco que el PIX: la plata entró igual.
    "recarga_brl": {
        "contra": "1.1.01",
        "glosa": "Recarga en reales (aprobación manual)"},
    "pago_tarjeta": {
        "contra": "1.1.04",
        "glosa": "Recarga con tarjeta"},
    "envio_ves": {
        "contra": "1.1.02",
        "glosa": "Remesa pagada en bolívares"},
    "envio_reais": {
        "contra": "1.1.01",
        "glosa": "Remesa pagada en reales"},
    # El reembolso de una remesa vuelve por donde salio. Cual de los dos bancos
    # es lo dice `currency_output`, y si no viene se usa la cuenta puente —que
    # es visible y se puede reclasificar, en vez de elegir un banco al azar.
    "refund_envio": {
        "contra": "1.1.99", "contra_por_moneda": {"VES": "1.1.02", "BRL": "1.1.01"},
        "glosa": "Reembolso de remesa"},
    # LOS UNICOS DOS QUE SON RESULTADO: el servicio de envios es lo que la
    # empresa vende, asi que su cobro es un INGRESO y no un movimiento de caja.
    "pago_envio_paquete": {
        "contra": "4.1.01",
        "glosa": "Cobro del servicio de envío"},
    "refund_envio_paquete": {
        "contra": "4.1.01",
        "glosa": "Devolución del servicio de envío"},
    "bono_referido": {
        "contra": "5.1.01",
        "glosa": "Bono por referido"},
    "reembolso_pago_incompleto": {
        "contra": "5.1.02",
        "glosa": "Reembolso por pago incompleto"},
    # El libro de creditos cripto comparte coleccion con el de RIS y se
    # distingue por `book`.
    "deposito_cripto": {
        "contra": "1.1.03",
        "glosa": "Depósito de créditos cripto"},
    "ajuste_admin_cripto": {
        "contra": "5.1.02",
        "glosa": "Ajuste manual de créditos cripto"},
    # El ajuste a mano del saldo RIS. No tiene una operación detrás que lo
    # explique, así que va contra la cuenta de ajustes: si esta cuenta crece,
    # es que se está corrigiendo mucho a mano y eso hay que mirarlo.
    "ajuste_admin": {
        "contra": "5.1.02",
        "glosa": "Ajuste manual de saldo RIS"},
    # El gestor pasando plata de su saldo personal al de terceros. No entra ni
    # sale dinero de la empresa: las dos patas se anulan en 2.1.99.
    "traspaso_interno": {
        "contra": "2.1.99",
        "glosa": "Traspaso entre saldos del mismo usuario"},
}

# La cuenta del usuario, segun donde vive el saldo.
CUENTA_DEL_USUARIO = {
    "balance_ris": "2.1.01",
    "balance_ris_terceros": "2.1.02",
    "balance_usdt": "2.1.03",
    "balance_usdc": "2.1.04",
}


def cuenta(codigo: str) -> dict:
    ficha = PLAN_DE_CUENTAS.get(codigo)
    return {"codigo": codigo,
            "nombre": (ficha or {}).get("nombre", "Cuenta desconocida"),
            "tipo": (ficha or {}).get("tipo", EGRESO)}


def _monto(valor) -> Decimal:
    """El monto como Decimal exacto. Nunca lanza.

    Las lineas del ledger guardan `amount` como float —lo escribe
    `ledger.record_ris_entry` con `abs(float(...))`— asi que la conversion pasa
    por `str` para no arrastrar el error binario del float a la suma.
    """
    if valor is None or valor == "":
        return ZERO
    try:
        numero = to_decimal(valor)
        return numero if numero.is_finite() else ZERO
    except Exception:
        logger.warning(f"contabilidad: monto ilegible en una línea: {valor!r}")
        return ZERO


def asiento_de(linea: dict) -> dict:
    """Las DOS partidas de una línea del ledger.

    Devuelve `{debe, haber, monto, glosa, clasificado}`. `clasificado` es False
    cuando el `movement_type` no está en el mapa: la línea igual aparece, con la
    cuenta puente, y el chequeo de integridad la denuncia. Desaparecerla sería
    peor que clasificarla mal.
    """
    tipo = str(linea.get("movement_type") or "").strip()
    regla = ASIENTOS.get(tipo)
    clasificado = regla is not None
    nombre_crudo = tipo or "sin tipo"
    regla = regla or {"contra": SIN_CLASIFICAR,
                      "glosa": f"Movimiento «{nombre_crudo}»"}

    contra = regla["contra"]
    por_moneda = regla.get("contra_por_moneda") or {}
    moneda = str(linea.get("currency_output") or "").upper()
    if moneda in por_moneda:
        contra = por_moneda[moneda]

    del_usuario = CUENTA_DEL_USUARIO.get(
        str(linea.get("account") or ""),
        CUENTA_DEL_USUARIO["balance_ris"])

    # La billetera del usuario es un PASIVO. Si su saldo sube, el pasivo se
    # acredita; si baja, se debita. La contrapartida va del otro lado.
    entra = str(linea.get("direction") or "credit") == "credit"
    debe, haber = ((contra, del_usuario) if entra else (del_usuario, contra))

    return {"debe": debe, "haber": haber,
            "monto": _monto(linea.get("amount")),
            "glosa": regla["glosa"], "clasificado": clasificado}


# ─── Lectura del libro ────────────────────────────────────────────────────

_PROYECCION = {
    "_id": 0, "entry_id": 1, "created_at": 1, "book": 1, "user_id": 1,
    "user_email": 1, "user_name": 1, "movement_type": 1, "direction": 1,
    "amount": 1, "currency": 1, "account": 1, "currency_output": 1,
    "amount_output": 1, "rate": 1, "transaction_id": 1, "display_id": 1,
    "actor": 1, "notes": 1, "balance_before": 1, "balance_after": 1,
}


def _rango(desde: str, hasta: str, tz_min: int = 0):
    try:
        inicio = datetime.strptime(desde, "%Y-%m-%d")
        fin = datetime.strptime(hasta, "%Y-%m-%d") + timedelta(days=1)
    except (TypeError, ValueError):
        raise ContabilidadInvalida("Las fechas van en formato AAAA-MM-DD.")
    if fin <= inicio:
        raise ContabilidadInvalida(
            "La fecha «desde» tiene que ser anterior o igual a «hasta».")
    corrimiento = timedelta(minutes=tz_min)
    return (inicio.replace(tzinfo=timezone.utc) - corrimiento,
            fin.replace(tzinfo=timezone.utc) - corrimiento)


async def _lineas(base, inicio, fin, filtros: dict) -> tuple:
    consulta = {"created_at": {"$gte": inicio, "$lt": fin}}
    if filtros.get("libro"):
        consulta["book"] = filtros["libro"]
    if filtros.get("user_id"):
        consulta["user_id"] = filtros["user_id"]
    if filtros.get("movement_type"):
        consulta["movement_type"] = filtros["movement_type"]
    try:
        crudas = await base.ledger.find(
            consulta, _PROYECCION).sort("created_at", 1).to_list(TOPE_ESCANEO + 1)
    except Exception as e:
        logger.error(f"contabilidad: no se pudo leer el libro: {e}")
        raise ContabilidadInvalida(
            "No se pudo leer el libro. Reintentá en un momento.", http=503) from e
    crudas = crudas or []
    return crudas[:TOPE_ESCANEO], len(crudas) > TOPE_ESCANEO


def _fecha(valor, tz_min: int) -> str:
    if not isinstance(valor, datetime):
        return ""
    momento = valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    return (momento + timedelta(minutes=tz_min)).strftime("%Y-%m-%d %H:%M")


async def libro_diario(*, desde: str, hasta: str, libro: str = None,
                       user_id: str = None, movement_type: str = None,
                       tz_min: int = 0, limite: int = FILAS_POR_PAGINA,
                       saltear: int = 0, db=None) -> dict:
    """Cada asiento del periodo, cronológico, con sus dos partidas.

    Es el libro que un auditor pide primero: qué pasó, cuándo, por cuánto y
    contra qué cuentas — en el orden en que pasó.
    """
    base = await _db(db)
    inicio, fin = _rango(desde, hasta, tz_min)
    crudas, truncado = await _lineas(base, inicio, fin, {
        "libro": libro, "user_id": user_id, "movement_type": movement_type})

    asientos, total_debe, sin_clasificar = [], ZERO, 0
    for numero, linea in enumerate(crudas, start=1):
        a = asiento_de(linea)
        total_debe += a["monto"]
        if not a["clasificado"]:
            sin_clasificar += 1
        asientos.append({
            # El numero es la POSICION dentro del periodo pedido, no un folio
            # contable: el ledger no tiene numeracion correlativa propia (ver el
            # chequeo de integridad, que lo denuncia).
            "numero": numero,
            "entry_id": linea.get("entry_id"),
            "fecha": _fecha(linea.get("created_at"), tz_min),
            "libro": linea.get("book") or "RIS",
            "glosa": a["glosa"],
            "movement_type": linea.get("movement_type"),
            "debe": cuenta(a["debe"]),
            "haber": cuenta(a["haber"]),
            "monto": str(quantize_money(a["monto"])),
            "moneda": linea.get("currency") or "RIS",
            "clasificado": a["clasificado"],
            "usuario": linea.get("user_name") or linea.get("user_email") or "",
            "user_id": linea.get("user_id"),
            "referencia": linea.get("display_id") or linea.get("transaction_id") or "",
            "actor": (linea.get("actor") or {}).get("email")
                     or (linea.get("actor") or {}).get("type") or "",
            "nota": linea.get("notes") or "",
        })

    limite = max(1, min(int(limite or FILAS_POR_PAGINA), TOPE_FILAS))
    saltear = max(0, int(saltear or 0))
    return {
        "desde": desde, "hasta": hasta, "tz_min": tz_min,
        "asientos_totales": len(asientos),
        # En partida doble el total del debe es el total del haber, siempre.
        "suma_debe": str(quantize_money(total_debe)),
        "suma_haber": str(quantize_money(total_debe)),
        "sin_clasificar": sin_clasificar,
        "truncado": truncado,
        "asientos": asientos[saltear:saltear + limite],
        "hay_mas": len(asientos) > saltear + limite,
    }


async def libro_mayor(*, desde: str, hasta: str, libro: str = None,
                      tz_min: int = 0, db=None) -> dict:
    """Los movimientos agrupados POR CUENTA, con saldo acumulado.

    Esto es lo que la pantalla anterior decía ser y no era. Contesta la pregunta
    contable básica: qué pasó en cada cuenta y con qué saldo quedó.
    """
    base = await _db(db)
    inicio, fin = _rango(desde, hasta, tz_min)
    crudas, truncado = await _lineas(base, inicio, fin, {"libro": libro})

    cuentas = {}
    for linea in crudas:
        a = asiento_de(linea)
        for codigo, lado in ((a["debe"], "debe"), (a["haber"], "haber")):
            libro_de_cuenta = cuentas.setdefault(codigo, {
                "debe": ZERO, "haber": ZERO, "movimientos": []})
            libro_de_cuenta[lado] += a["monto"]
            libro_de_cuenta["movimientos"].append({
                "fecha": _fecha(linea.get("created_at"), tz_min),
                "glosa": a["glosa"],
                "referencia": linea.get("display_id") or linea.get("transaction_id") or "",
                "usuario": linea.get("user_name") or linea.get("user_email") or "",
                "debe": str(quantize_money(a["monto"])) if lado == "debe" else "",
                "haber": str(quantize_money(a["monto"])) if lado == "haber" else "",
            })

    salida = []
    for codigo in sorted(cuentas):
        ficha = cuenta(codigo)
        datos = cuentas[codigo]
        # El saldo se presenta en la NATURALEZA de la cuenta: una de activo con
        # saldo deudor se muestra positiva; si diera acreedor, negativa — y eso
        # es una señal, no un detalle de presentación.
        bruto = (datos["debe"] - datos["haber"] if ficha["tipo"] in NATURALEZA_DEUDORA
                 else datos["haber"] - datos["debe"])
        movimientos = datos["movimientos"]
        # Se acumula el saldo linea por linea, que es como se lee un mayor.
        acumulado = ZERO
        for movimiento in movimientos:
            monto = _monto(movimiento["debe"] or movimiento["haber"])
            suma = monto if bool(movimiento["debe"]) else -monto
            if ficha["tipo"] not in NATURALEZA_DEUDORA:
                suma = -suma
            acumulado += suma
            movimiento["saldo"] = str(quantize_money(acumulado))
        salida.append({
            **ficha,
            "naturaleza": "deudora" if ficha["tipo"] in NATURALEZA_DEUDORA else "acreedora",
            "suma_debe": str(quantize_money(datos["debe"])),
            "suma_haber": str(quantize_money(datos["haber"])),
            "saldo": str(quantize_money(bruto)),
            "movimientos": movimientos[:TOPE_FILAS],
            "hay_mas_movimientos": len(movimientos) > TOPE_FILAS,
        })

    return {"desde": desde, "hasta": hasta, "tz_min": tz_min,
            "truncado": truncado, "cuentas": salida}


async def balance_de_comprobacion(*, desde: str, hasta: str, libro: str = None,
                                  tz_min: int = 0, db=None) -> dict:
    """Sumas y saldos por cuenta, con los totales de cada grupo.

    LO QUE ESTE BALANCE SI PRUEBA Y LO QUE NO
        Cuadra por construcción: las partidas se derivan de cada línea, así que
        el debe siempre iguala al haber. **No es un control de que los datos
        estén bien.** Lo que sí muestra es la ESTRUCTURA: cuánto se le debe a los
        usuarios, cuánto hay declarado en bancos, cuánto se ingresó por
        servicios. Los controles reales son la reconciliación y la verificación
        de integridad, que están aparte.
    """
    mayor = await libro_mayor(desde=desde, hasta=hasta, libro=libro,
                              tz_min=tz_min, db=db)
    filas, por_grupo = [], {}
    total_debe = total_haber = ZERO
    for c in mayor["cuentas"]:
        debe, haber = _monto(c["suma_debe"]), _monto(c["suma_haber"])
        total_debe += debe
        total_haber += haber
        grupo = por_grupo.setdefault(c["tipo"], ZERO)
        por_grupo[c["tipo"]] = grupo + _monto(c["saldo"])
        filas.append({k: c[k] for k in
                      ("codigo", "nombre", "tipo", "naturaleza",
                       "suma_debe", "suma_haber", "saldo")})

    return {
        "desde": desde, "hasta": hasta, "tz_min": tz_min,
        "truncado": mayor["truncado"],
        "cuentas": filas,
        "total_debe": str(quantize_money(total_debe)),
        "total_haber": str(quantize_money(total_haber)),
        "cuadra": quantize_money(total_debe) == quantize_money(total_haber),
        "por_grupo": {tipo: str(quantize_money(monto))
                      for tipo, monto in sorted(por_grupo.items())},
    }


# ─── Control 1: la reconciliación ─────────────────────────────────────────

async def reconciliacion(*, libro: str = "RIS", limite: int = 200, db=None) -> dict:
    """Compara el saldo GUARDADO de cada usuario contra la suma de su libro.

    QUE ARREGLA DE LA VERSION ANTERIOR
        La que había recorría a los usuarios de a uno y por cada uno lanzaba una
        agregación (`sum_ris_balance`). Con diez mil usuarios son diez mil
        viajes a la base dentro de una sola petición: no es lento, es un
        timeout. Acá son DOS lecturas: las líneas del libro y los saldos.

        Y sumaba con `$sum` de Mongo sobre `signed_amount`, que es un float.
        Acá se suma con Decimal, que es la única forma de que «cuadra» signifique
        cuadra. (`sum_ris_balance` también suma en Decimal desde entonces; lo
        que queda de aquella versión es el viaje por usuario.)

    LA TOLERANCIA ES CERO, Y ES A PROPOSITO
        La versión anterior toleraba un centavo por usuario (`EPS = 0.01`). Un
        libro que acepta un centavo de deriva por cuenta es un libro donde un
        redondeo sistemático se esconde: con diez mil usuarios, ese centavo
        tolerado son cien unidades que nadie mira. Si hay diferencia, se muestra.
    """
    base = await _db(db)
    try:
        lineas = await base.ledger.find(
            {"book": libro},
            {"_id": 0, "user_id": 1, "account": 1, "direction": 1, "amount": 1},
        ).to_list(TOPE_ESCANEO + 1)
    except Exception as e:
        logger.error(f"contabilidad: no se pudo leer el libro para reconciliar: {e}")
        raise ContabilidadInvalida(
            "No se pudo leer el libro. Reintentá en un momento.", http=503) from e

    lineas = lineas or []
    truncado = len(lineas) > TOPE_ESCANEO
    lineas = lineas[:TOPE_ESCANEO]

    # Suma por (usuario, cuenta), en Decimal.
    sumas = {}
    for linea in lineas:
        clave = (linea.get("user_id"), linea.get("account") or "balance_ris")
        monto = _monto(linea.get("amount"))
        if str(linea.get("direction") or "credit") != "credit":
            monto = -monto
        sumas[clave] = sumas.get(clave, ZERO) + monto

    campos = {"_id": 0, "user_id": 1, "email": 1, "full_name": 1, "name": 1,
              "role": 1}
    cuentas_del_libro = sorted({c for _, c in sumas} | {"balance_ris"})
    for campo in cuentas_del_libro:
        campos[campo] = 1
    try:
        usuarios = await base.users.find({}, campos).to_list(TOPE_ESCANEO)
    except Exception as e:
        logger.error(f"contabilidad: no se pudieron leer los saldos: {e}")
        raise ContabilidadInvalida(
            "No se pudieron leer los saldos. Reintentá en un momento.",
            http=503) from e

    descuadres, revisados = [], 0
    for u in usuarios or []:
        uid = u.get("user_id")
        if not uid:
            continue
        revisados += 1
        for campo in cuentas_del_libro:
            guardado = _monto(u.get(campo))
            del_libro = sumas.pop((uid, campo), ZERO)
            diferencia = quantize_money(guardado - del_libro)
            if diferencia == ZERO:
                continue
            descuadres.append({
                "user_id": uid,
                "email": u.get("email") or "",
                "nombre": u.get("full_name") or u.get("name") or "",
                "cuenta": campo,
                "cuenta_contable": CUENTA_DEL_USUARIO.get(campo, "—"),
                "saldo_guardado": str(quantize_money(guardado)),
                "suma_del_libro": str(quantize_money(del_libro)),
                "diferencia": str(diferencia),
            })

    # Lo que quedó en `sumas` es libro SIN usuario: líneas de alguien que ya no
    # existe en `users`. Es un descuadre distinto y más grave —plata registrada
    # contra nadie— así que se reporta aparte en vez de perderse.
    huerfanas = [{"user_id": uid, "cuenta": campo,
                  "suma_del_libro": str(quantize_money(monto))}
                 for (uid, campo), monto in sumas.items() if monto != ZERO]

    descuadres.sort(key=lambda d: abs(_monto(d["diferencia"])), reverse=True)
    return {
        "libro": libro,
        "usuarios_revisados": revisados,
        "lineas_leidas": len(lineas),
        "truncado": truncado,
        "cuadra": not descuadres and not huerfanas,
        "descuadres_totales": len(descuadres),
        "descuadres": descuadres[:limite],
        "hay_mas_descuadres": len(descuadres) > limite,
        "lineas_sin_usuario": huerfanas[:limite],
    }


# ─── Control 2: la integridad del libro ───────────────────────────────────

async def integridad(*, libro: str = None, limite: int = 100, db=None) -> dict:
    """Los defectos que hacen que un libro no se pueda defender ante un auditor.

    Cada hallazgo dice QUE pasa, CUANTAS líneas y un ejemplo. No se corrige nada
    automáticamente: un libro que se auto-corrige es un libro que nadie puede
    auditar.
    """
    base = await _db(db)
    consulta = {"book": libro} if libro else {}
    try:
        lineas = await base.ledger.find(consulta, {
            "_id": 0, "entry_id": 1, "created_at": 1, "user_id": 1,
            "movement_type": 1, "amount": 1, "direction": 1, "account": 1,
            "balance_before": 1, "balance_after": 1, "reference": 1, "book": 1,
        }).to_list(TOPE_ESCANEO + 1)
    except Exception as e:
        logger.error(f"contabilidad: no se pudo leer el libro: {e}")
        raise ContabilidadInvalida(
            "No se pudo leer el libro. Reintentá en un momento.", http=503) from e

    lineas = lineas or []
    truncado = len(lineas) > TOPE_ESCANEO
    lineas = lineas[:TOPE_ESCANEO]

    hallazgos = OrderedDict()

    def anotar(clave, titulo, explicacion, gravedad, ejemplo):
        h = hallazgos.setdefault(clave, {
            "clave": clave, "titulo": titulo, "explicacion": explicacion,
            "gravedad": gravedad, "cuantas": 0, "ejemplos": []})
        h["cuantas"] += 1
        if len(h["ejemplos"]) < 5:
            h["ejemplos"].append(ejemplo)

    vistos, referencias = set(), {}
    ahora = datetime.now(timezone.utc)
    for linea in lineas:
        eid = linea.get("entry_id")
        ref = f"{eid or 'sin id'}"

        if not eid:
            anotar("sin_id", "Líneas sin identificador",
                   "Una línea sin `entry_id` no se puede citar ni referenciar "
                   "en una auditoría.", "alta", ref)
        elif eid in vistos:
            anotar("id_repetido", "Identificadores repetidos",
                   "Dos líneas con el mismo `entry_id`. El índice único debería "
                   "impedirlo: si aparecen, el índice no está creado.", "alta", ref)
        vistos.add(eid)

        if not linea.get("user_id"):
            anotar("sin_usuario", "Líneas sin titular",
                   "Plata registrada contra nadie.", "alta", ref)

        monto = _monto(linea.get("amount"))
        if monto <= ZERO:
            anotar("monto_cero", "Líneas con monto cero o negativo",
                   "El signo lo da `direction`; el monto siempre es positivo. "
                   "Un cero o un negativo acá es un dato mal escrito.",
                   "media", ref)

        if str(linea.get("movement_type") or "") not in ASIENTOS:
            anotar("sin_clasificar", "Movimientos sin cuenta asignada",
                   "Su `movement_type` no está en el plan de asientos, así que "
                   "van a la cuenta puente. Hay que clasificarlos para que el "
                   "balance signifique algo.", "media",
                   f"{ref} · {linea.get('movement_type')}")

        # EL CONTROL MAS FUERTE QUE PERMITEN ESTOS DATOS: la linea dice el saldo
        # antes y despues. Si la diferencia no es el monto, la linea NO describe
        # el movimiento que dice describir.
        antes, despues = linea.get("balance_before"), linea.get("balance_after")
        if antes is not None and despues is not None:
            esperado = monto if str(linea.get("direction")) == "credit" else -monto
            real = _monto(despues) - _monto(antes)
            if quantize_money(real) != quantize_money(esperado):
                anotar("saldo_no_coincide",
                       "El saldo antes/después no coincide con el monto",
                       "La línea dice que el saldo pasó de A a B, pero B − A no "
                       "es el monto que declara. O el monto está mal, o el "
                       "movimiento real fue otro.", "alta",
                       f"{ref} · declara {esperado}, movió {quantize_money(real)}")

        clave_ref = (linea.get("reference") or {}).get("id")
        if clave_ref:
            referencias.setdefault(clave_ref, []).append(eid)

        creada = linea.get("created_at")
        if isinstance(creada, datetime):
            momento = creada if creada.tzinfo else creada.replace(tzinfo=timezone.utc)
            if momento > ahora + timedelta(minutes=5):
                anotar("fecha_futura", "Líneas con fecha futura",
                       "Un asiento fechado adelante desordena cualquier cierre "
                       "de periodo.", "alta", ref)
        else:
            anotar("sin_fecha", "Líneas sin fecha",
                   "Sin fecha no entran en ningún periodo.", "alta", ref)

    for clave_ref, ids in referencias.items():
        if len(ids) > 1:
            anotar("referencia_repetida",
                   "Una misma operación registrada más de una vez",
                   "Varias líneas apuntan al mismo documento de origen. Puede "
                   "ser legítimo (un cobro y su reembolso) o una doble "
                   "contabilización: hay que mirarlas.", "media",
                   f"{clave_ref} → {len(ids)} líneas")

    orden = {"alta": 0, "media": 1, "baja": 2}
    encontrados = sorted(hallazgos.values(),
                         key=lambda h: (orden.get(h["gravedad"], 3), -h["cuantas"]))
    return {
        "libro": libro or "todos",
        "lineas_revisadas": len(lineas),
        "truncado": truncado,
        "sano": not encontrados,
        "hallazgos": encontrados[:limite],
        # Lo que este libro NO puede probar todavía, dicho en la respuesta para
        # que la pantalla lo muestre en vez de sugerir una garantía que no hay.
        "limitaciones": [
            "El libro no tiene numeración correlativa propia: los identificadores "
            "son aleatorios, así que no se puede demostrar que no falte una línea.",
            "Las líneas no están encadenadas por hash, así que una modificación "
            "posterior no dejaría rastro.",
            "No hay cierre de periodo: nada impide escribir una línea con fecha "
            "de un mes ya presentado.",
            "`ledger.record_ris_entry` atrapa cualquier error y sigue: un "
            "movimiento puede haber ocurrido sin que su línea exista.",
        ],
    }
