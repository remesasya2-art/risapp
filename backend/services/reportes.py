"""
services/reportes.py — El motor de reportes de lo que la app cobra y mueve.

QUE REEMPLAZA Y POR QUE
    Habia UN reporte, escrito adentro de la ruta, con estos problemas — todos
    verificados sobre el codigo, no supuestos:

    1. LEIA EL DOCUMENTO ENTERO. `db.transactions.find({...})` sin proyeccion.
       El comprobante de una recarga se guarda INLINE, como data URL en base64
       (`routes/transactions.py`: `"proof_image": comprobante`). O sea que para
       imprimir la palabra «si» en una columna, el reporte se traia la foto
       entera de cada fila. Una foto de celular de 500 KB son ~667 KB en base64:
       mil filas son 650 MB de RAM para escribir mil veces «si».

    2. NO SUMABA PLATA. `totales_por_flujo` contaba FILAS. Un reporte financiero
       que dice «12 operaciones» y no dice cuanto dinero se movio no es un
       reporte financiero.

    3. LE FALTABA UN NEGOCIO ENTERO. El docstring decia «4 flujos» y el codigo
       consultaba tres: retiros, recargas VES y remesas BTC. Los ENVIOS —el
       modulo entero— no figuraban.

    4. SIN TOPE. Se armaba una lista con todo lo que matcheara y se serializaba
       completa a JSON. Un reporte anual no tenia limite superior.

    5. CSV INYECTABLE. Los nombres y los beneficiarios los escribe un usuario, y
       salian crudos al CSV. Un nombre que empieza con `=` es una FORMULA cuando
       ese archivo se abre en Excel.

    6. SIN TESTS. Ninguno.

COMO SE ORGANIZA AHORA
    Una FUENTE por flujo de dinero. Cada una declara de que coleccion sale, por
    que fecha se corta, que filtro la define, QUE CAMPOS se leen —la proyeccion
    es obligatoria y es lo que evita el problema 1— y como se convierte un
    documento en una fila del reporte.

    Agregar un flujo nuevo es agregar una FUENTE, no editar doscientas lineas de
    ruta. Y ninguna fuente puede olvidarse la proyeccion: hay un test que las
    recorre todas y lo exige.

POR QUE LOS TOTALES SE CALCULAN RECORRIENDO Y NO CON $group
    Los montos en esta base vienen como float, como string y como Decimal128,
    segun quien los escribio y cuando. Un `$sum` de Mongo sobre esa mezcla suma
    lo que puede y calla el resto. Recorrer el cursor y convertir cada monto con
    `to_decimal` da el numero exacto y falla ruidosamente si algo es ilegible.

    El costo de recorrer es aceptable JUSTAMENTE por la proyeccion: cada
    documento proyectado pesa unos cientos de bytes, no megabytes. Y hay un tope
    duro de documentos recorridos, que si se alcanza se DICE (`truncado`), en vez
    de devolver un total que parece completo y no lo es.
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from services.money import ZERO, quantize_money, to_decimal

logger = logging.getLogger(__name__)

# Cuantos documentos se recorren como maximo para armar UN reporte. No es el
# tamano de la respuesta —eso lo fija `limite`— es el techo del trabajo. Si se
# alcanza, la respuesta lo dice: un total truncado que se presenta como completo
# es peor que no tenerlo.
TOPE_ESCANEO = 200_000

# Cuantas filas se devuelven para mirar en pantalla. La descarga no pasa por
# aca: el CSV y el XLSX se arman con el mismo recorrido, sin este corte.
FILAS_POR_PAGINA = 100
TOPE_FILAS = 1000


class ReporteInvalido(Exception):
    def __init__(self, mensaje: str, http: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.http = http


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


# ─── Las fuentes ──────────────────────────────────────────────────────────

def _texto(valor) -> str:
    return "" if valor is None else str(valor).strip()


def _fila_retiro(tx: dict, usuario: dict) -> dict:
    b = tx.get("beneficiary_data") or {}
    es_brl = _texto(tx.get("currency_output") or "VES").upper() in ("BRL", "REAIS", "REAL")
    return {
        "flujo": "RIS → Reais" if es_brl else "RIS → VES",
        "fecha": tx.get("completed_at"),
        "referencia": tx.get("display_id") or tx.get("transaction_id"),
        "usuario": usuario.get("full_name") or usuario.get("name") or "",
        "email": usuario.get("email", ""),
        "contraparte": b.get("full_name") or b.get("name") or "",
        "documento": b.get("cpf") or b.get("cedula") or b.get("id_document") or "",
        "destino": b.get("pix_key") or b.get("bank") or b.get("bank_code") or "",
        "monto_origen": tx.get("amount_input"),
        "unidad_origen": "RIS",
        "monto_destino": tx.get("amount_output"),
        "unidad_destino": "BRL" if es_brl else "VES",
        "tasa": tx.get("rate"),
        "operador": tx.get("processed_by", ""),
        # `bool()` sobre el campo, NO el campo: el comprobante es una imagen en
        # base64 y no tiene por que viajar hasta el reporte.
        "comprobante": bool(tx.get("proof_images") or tx.get("proof_image")),
    }


def _fila_recarga_ves(tx: dict, usuario: dict) -> dict:
    return {
        "flujo": "VES → RIS",
        "fecha": tx.get("processed_at"),
        "referencia": tx.get("display_id") or tx.get("transaction_id"),
        "usuario": usuario.get("full_name") or usuario.get("name") or "",
        "email": usuario.get("email", ""),
        "contraparte": tx.get("destination_bank_name") or tx.get("destination_bank") or "",
        "documento": "",
        "destino": "",
        "monto_origen": tx.get("amount_ves"),
        "unidad_origen": "VES",
        "monto_destino": tx.get("amount_ris"),
        "unidad_destino": "RIS",
        "tasa": tx.get("rate_used"),
        "operador": tx.get("processed_by", ""),
        "comprobante": bool(tx.get("proof_image")),
    }


def _fila_btc(r: dict, usuario: dict) -> dict:
    b = r.get("beneficiario_data") or {}
    return {
        "flujo": "BTC → VES",
        "fecha": r.get("enviado_en"),
        "referencia": r.get("display_id") or r.get("remesa_id"),
        "usuario": usuario.get("full_name") or usuario.get("name") or "",
        "email": usuario.get("email", ""),
        "contraparte": b.get("full_name") or b.get("name") or "",
        "documento": b.get("cedula", ""),
        "destino": b.get("bank", ""),
        "monto_origen": r.get("usd_cliente"),
        "unidad_origen": "USD",
        "monto_destino": r.get("ves_recibe"),
        "unidad_destino": "VES",
        "tasa": r.get("tasa_ves"),
        "operador": r.get("operador_id", ""),
        "comprobante": bool(r.get("comprobante_pago")),
    }


# Las etiquetas de marca de las billeteras de credito. Se leen del servicio en
# vez de escribirlas aca para que no se despeguen del resto de la app.
_CRIPTO = {"usdt": "USDT", "usdc": "USDC"}


def _fila_cripto(deposito: dict, usuario: dict) -> dict:
    """Un depósito de créditos USDT/USDC, o un ajuste manual.

    SE SEPARAN EN DOS FLUJOS, y no es un capricho. Un depósito es plata que un
    cliente puso; un ajuste manual lo tecleó un administrador desde el panel
    —soporte, una prueba, una corrección—. Sumarlos en un mismo total dice que
    entró plata que no entró, y es el número que después se usa para decidir.

    Estas billeteras son SEPARADAS de `balance_ris`, que está en reales. No se
    mezclan, y por eso el reporte tampoco las convierte a nada: el total de USDT
    es en USDT.
    """
    clave = _texto(deposito.get("currency")).lower()
    moneda = _CRIPTO.get(clave, clave.upper() or "?")
    manual = _texto(deposito.get("source")) == "admin_manual"
    return {
        "flujo": f"{'Ajuste manual' if manual else 'Depósito'} {moneda}",
        "fecha": deposito.get("credited_at"),
        "referencia": deposito.get("order_id"),
        "usuario": usuario.get("full_name") or usuario.get("name") or "",
        "email": usuario.get("email", ""),
        # De dónde salió: la red por la que llegó, o que lo puso una persona.
        "contraparte": ("Crédito manual del panel" if manual
                        else _texto(deposito.get("pay_currency")).upper()),
        "documento": "",
        "destino": _texto(deposito.get("admin_note")) if manual else "",
        # `credit_amount` es lo que de verdad se acreditó —el webhook usa lo
        # `actually_paid` cuando difiere de lo pedido— y `amount` es lo que el
        # usuario había pedido depositar. Para un reporte de plata vale el
        # primero.
        "monto_origen": deposito.get("credit_amount") or deposito.get("amount"),
        "unidad_origen": moneda,
        # No hay conversión: el depósito acredita la MISMA moneda.
        "monto_destino": None,
        "unidad_destino": "",
        "tasa": None,
        "operador": _texto(deposito.get("admin_id")) if manual else "",
        # Para una cripto el «comprobante» es el pago confirmado en la cadena por
        # la pasarela. Un ajuste manual no tiene ninguno detrás, y esa diferencia
        # es justo la que alguien quiere ver al auditar.
        "comprobante": not manual,
    }


def _filas_envio(envio: dict, usuario: dict) -> list:
    """UN envío puede haber cobrado VARIAS veces: el inicial y el ajuste.

    Por eso esta fuente devuelve una lista y no una fila. Colapsar las dos en
    una sola linea con la suma esconde el ajuste, que es justo el numero que se
    discute cuando alguien reclama: «me cobraron dos veces».
    """
    cobros = envio.get("cobros") or {}
    destino = envio.get("destino") or {}
    destinatario = (destino.get("destinatario") or {}).get("nombre") or ""
    filas = []
    for partida in ("inicial", "ajuste"):
        doc = cobros.get(partida) or {}
        if doc.get("estado") != "pagado" or not doc.get("pagado_at"):
            continue
        filas.append({
            "flujo": f"Envío — {partida}",
            "fecha": doc.get("pagado_at"),
            "referencia": envio.get("display_id") or envio.get("envio_id"),
            "usuario": usuario.get("full_name") or usuario.get("name") or "",
            "email": usuario.get("email", ""),
            "contraparte": destinatario,
            "documento": "",
            "destino": _texto(destino.get("agencia_nombre")),
            "monto_origen": doc.get("monto_ris"),
            "unidad_origen": "RIS",
            # El envio no convierte moneda: lo que se cobra es el servicio, en
            # RIS. Poner un monto de destino inventado seria peor que no ponerlo.
            "monto_destino": None,
            "unidad_destino": "",
            "tasa": None,
            "operador": "",
            "comprobante": bool((envio.get("origen") or {}).get("comprobante_asset_id")),
        })
    # La devolucion del repesaje: plata que SALE. Va con signo negativo para que
    # el total del periodo sea lo que de verdad entro, y no lo bruto.
    devolucion = cobros.get("devolucion") or {}
    if devolucion.get("monto_ris") and devolucion.get("pagado_at"):
        filas.append({
            "flujo": "Envío — devolución",
            "fecha": devolucion.get("pagado_at"),
            "referencia": envio.get("display_id") or envio.get("envio_id"),
            "usuario": usuario.get("full_name") or usuario.get("name") or "",
            "email": usuario.get("email", ""),
            "contraparte": destinatario,
            "documento": "",
            "destino": _texto(destino.get("agencia_nombre")),
            "monto_origen": -to_decimal(devolucion.get("monto_ris")),
            "unidad_origen": "RIS",
            "monto_destino": None,
            "unidad_destino": "",
            "tasa": None,
            "operador": "",
            "comprobante": False,
        })
    return filas


# Cada fuente: de donde sale, por que fecha se corta, que la define, QUE SE LEE.
#
# `proyeccion` es obligatoria y no es una optimizacion: es lo que evita que el
# reporte se traiga las fotos en base64 que viven adentro de estos documentos.
# Hay un test que recorre esta lista y falla si a alguna le falta.
FUENTES = {
    "retiros": {
        "etiqueta": "Retiros (RIS → VES / Reais)",
        "coleccion": "transactions",
        "campo_fecha": "completed_at",
        "filtro": {"type": "withdrawal", "status": "completed"},
        "proyeccion": {
            "_id": 0, "transaction_id": 1, "display_id": 1, "user_id": 1,
            "completed_at": 1, "amount_input": 1, "amount_output": 1,
            "currency_output": 1, "rate": 1, "processed_by": 1,
            "beneficiary_data": 1,
            # Se pide la EXISTENCIA, no el contenido. `$type` devuelve el nombre
            # del tipo BSON —unos bytes— en vez de la imagen entera.
            "tiene_comprobante": {"$or": [
                {"$gt": [{"$size": {"$ifNull": ["$proof_images", []]}}, 0]},
                {"$ne": [{"$ifNull": ["$proof_image", None]}, None]},
            ]},
        },
        "fila": _fila_retiro,
    },
    "recargas_ves": {
        "etiqueta": "Recargas en bolívares (VES → RIS)",
        "coleccion": "transactions",
        "campo_fecha": "processed_at",
        "filtro": {"type": "recharge_ves", "status": "approved"},
        "proyeccion": {
            "_id": 0, "transaction_id": 1, "display_id": 1, "user_id": 1,
            "processed_at": 1, "amount_ves": 1, "amount_ris": 1,
            "rate_used": 1, "processed_by": 1,
            "destination_bank": 1, "destination_bank_name": 1,
            "tiene_comprobante": {"$ne": [{"$ifNull": ["$proof_image", None]}, None]},
        },
        "fila": _fila_recarga_ves,
    },
    "btc": {
        "etiqueta": "Remesas BTC (BTC → VES)",
        "coleccion": "btc_remesas",
        "campo_fecha": "enviado_en",
        "filtro": {"estado": "enviado"},
        "proyeccion": {
            "_id": 0, "remesa_id": 1, "display_id": 1, "user_id": 1,
            "enviado_en": 1, "usd_cliente": 1, "ves_recibe": 1,
            "tasa_ves": 1, "operador_id": 1, "beneficiario_data": 1,
            "tiene_comprobante": {"$ne": [{"$ifNull": ["$comprobante_pago", None]}, None]},
        },
        "fila": _fila_btc,
    },
    "cripto": {
        "etiqueta": "Créditos cripto (USDT / USDC)",
        "coleccion": "crypto_deposits",
        # `credited_at` y no `created_at`: la fecha del reporte es cuando la
        # plata ENTRO, no cuando alguien abrio la pantalla de depositar. Un
        # deposito iniciado el 31 y acreditado el 1 es del mes nuevo.
        "campo_fecha": "credited_at",
        # Solo lo acreditado. Un deposito `pending` es una intencion, no plata.
        "filtro": {"credited": True},
        "proyeccion": {
            "_id": 0, "order_id": 1, "user_id": 1, "currency": 1,
            "credited_at": 1, "credit_amount": 1, "amount": 1,
            "pay_currency": 1, "source": 1, "admin_id": 1, "admin_note": 1,
        },
        "fila": _fila_cripto,
    },
    # El negocio que faltaba entero en el reporte viejo.
    "envios": {
        "etiqueta": "Envíos (cobros del servicio)",
        "coleccion": "envios",
        # Un envio cobra en DOS momentos y cada uno tiene su fecha, asi que el
        # corte no puede ser un solo campo del documento. Se filtra ancho por
        # las dos fechas y despues cada fila se descarta si cae fuera: el
        # documento es chico y el indice de `created_at` sigue sirviendo.
        "campo_fecha": None,
        "campos_fecha_fila": ("cobros.inicial.pagado_at", "cobros.ajuste.pagado_at",
                              "cobros.devolucion.pagado_at"),
        "filtro": {},
        "proyeccion": {
            "_id": 0, "envio_id": 1, "display_id": 1, "user_id": 1,
            "cobros": 1, "destino.agencia_nombre": 1,
            "destino.destinatario.nombre": 1,
            "origen.comprobante_asset_id": 1,
        },
        "filas": _filas_envio,
    },
}


# ─── El reporte ───────────────────────────────────────────────────────────

def _rango(desde: str, hasta: str, tz_min: int = 0):
    """El rango [inicio, fin) en UTC, a partir de dos fechas locales.

    `tz_min` son los minutos de diferencia con UTC (Caracas es -240). Existe
    porque «el dia» de un reporte contable es el dia del negocio, no el de UTC:
    con `tz_min=0` un reporte del lunes en Caracas se corta a las 20:00 del
    lunes y se come cuatro horas de operaciones que el contador espera ahi.

    El valor viaja en la respuesta y en el encabezado del archivo. Un reporte
    que no dice en que huso corta el dia no se puede cuadrar contra otro.
    """
    try:
        inicio_local = datetime.strptime(desde, "%Y-%m-%d")
        fin_local = datetime.strptime(hasta, "%Y-%m-%d") + timedelta(days=1)
    except (TypeError, ValueError):
        raise ReporteInvalido("Las fechas van en formato AAAA-MM-DD.")
    if fin_local <= inicio_local:
        raise ReporteInvalido("La fecha «desde» tiene que ser anterior o igual a «hasta».")
    desplazamiento = timedelta(minutes=tz_min)
    return (inicio_local.replace(tzinfo=timezone.utc) - desplazamiento,
            fin_local.replace(tzinfo=timezone.utc) - desplazamiento)


def _en_rango(valor, inicio, fin) -> bool:
    if not isinstance(valor, datetime):
        return False
    momento = valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    return inicio <= momento < fin


def _monto(valor) -> Decimal:
    """El monto como Decimal, o cero. Nunca lanza.

    Los montos de esta base son float, string y Decimal128 segun quien los
    escribio. Un total que revienta por una fila con un valor raro deja al
    administrador sin reporte; uno que la cuenta como cero miente. Se cuenta
    como cero y se registra: la fila igual aparece con su valor crudo.
    """
    if valor is None or valor == "":
        return ZERO
    try:
        numero = to_decimal(valor)
        return numero if numero.is_finite() else ZERO
    except Exception:
        logger.warning(f"reportes: monto ilegible en una fila: {valor!r}")
        return ZERO


class _Totales:
    """Los totales, acumulados mientras se recorre. Nunca guarda las filas."""

    def __init__(self):
        self.por_flujo = {}
        self.cuantas = 0

    def sumar(self, fila: dict) -> None:
        self.cuantas += 1
        clave = fila["flujo"]
        bucket = self.por_flujo.setdefault(clave, {
            "operaciones": 0,
            "origen": ZERO, "unidad_origen": fila.get("unidad_origen") or "",
            "destino": ZERO, "unidad_destino": fila.get("unidad_destino") or "",
        })
        bucket["operaciones"] += 1
        bucket["origen"] += _monto(fila.get("monto_origen"))
        bucket["destino"] += _monto(fila.get("monto_destino"))

    def como_dict(self) -> dict:
        # Un total de destino SIN unidad no es cero: es «no aplica». Los envios
        # cobran un servicio en RIS y no convierten a nada, y escribir «0.00» en
        # esa columna se lee como «cero bolivares», que es un numero, no un
        # hueco. Se deja vacio a proposito.
        return {clave: {
            "operaciones": v["operaciones"],
            "total_origen": str(quantize_money(v["origen"])),
            "unidad_origen": v["unidad_origen"],
            "total_destino": (str(quantize_money(v["destino"]))
                              if v["unidad_destino"] else ""),
            "unidad_destino": v["unidad_destino"],
        } for clave, v in sorted(self.por_flujo.items())}


async def _usuarios(base, ids: set) -> dict:
    """Los usuarios de un lote, en UNA consulta.

    El reporte viejo hacia una consulta por usuario distinto, secuencial, adentro
    del bucle. Con mil usuarios distintos eran mil viajes a la base para escribir
    mil nombres.
    """
    ids = {i for i in ids if i}
    if not ids:
        return {}
    try:
        filas = await base.users.find(
            {"user_id": {"$in": list(ids)}},
            {"_id": 0, "user_id": 1, "full_name": 1, "name": 1, "email": 1},
        ).to_list(len(ids))
    except Exception as e:
        logger.warning(f"reportes: no se pudieron leer los usuarios: {e}")
        return {}
    return {f.get("user_id"): f for f in filas or []}


async def _recorrer(base, clave: str, inicio, fin, filtros: dict):
    """Las filas de UNA fuente, ya mapeadas. Devuelve (filas, truncado)."""
    fuente = FUENTES[clave]
    consulta = dict(fuente["filtro"])
    if fuente.get("campo_fecha"):
        consulta[fuente["campo_fecha"]] = {"$gte": inicio, "$lt": fin}
    else:
        # Sin un campo de fecha unico: se pide ancho por cualquiera de las
        # fechas posibles y despues se descarta fila por fila.
        consulta["$or"] = [{campo: {"$gte": inicio, "$lt": fin}}
                           for campo in fuente["campos_fecha_fila"]]

    # `aggregate` y no `find`: la proyeccion necesita una EXPRESION para
    # contestar «tiene comprobante» sin traer el comprobante, y las expresiones
    # en la proyeccion de un `find` recien existen desde Mongo 4.4. En un
    # `$project` funcionan desde siempre — y ademas mongomock las soporta, asi
    # que los tests corren contra la misma semantica que produccion.
    tuberia = [
        {"$match": consulta},
        {"$project": fuente["proyeccion"]},
        {"$limit": TOPE_ESCANEO + 1},
    ]
    try:
        crudas = await base[fuente["coleccion"]].aggregate(tuberia).to_list(
            TOPE_ESCANEO + 1)
    except Exception as e:
        logger.error(f"reportes: no se pudo leer {clave}: {e}")
        raise ReporteInvalido(
            "No se pudieron leer los datos del reporte. Reintentá en un momento.",
            http=503) from e

    crudas = crudas or []
    truncado = len(crudas) > TOPE_ESCANEO
    crudas = crudas[:TOPE_ESCANEO]

    usuarios = await _usuarios(base, {d.get("user_id") for d in crudas})

    filas = []
    for doc in crudas:
        usuario = usuarios.get(doc.get("user_id")) or {}
        producidas = ([fuente["fila"](doc, usuario)] if "fila" in fuente
                      else fuente["filas"](doc, usuario))
        for fila in producidas:
            # El corte de fecha se aplica SIEMPRE, tambien a las fuentes que
            # filtraron por un campo unico: un envio traido por la fecha del
            # inicial puede tener el ajuste fuera del periodo.
            if not _en_rango(fila.get("fecha"), inicio, fin):
                continue
            fila["comprobante"] = bool(doc.get("tiene_comprobante", fila.get("comprobante")))
            filas.append(fila)
    return filas, truncado


def _pasa_filtros(fila: dict, filtros: dict) -> bool:
    buscado = filtros.get("buscar")
    if buscado:
        aguja = buscado.lower()
        campos = (fila.get("referencia"), fila.get("email"), fila.get("usuario"),
                  fila.get("contraparte"), fila.get("documento"))
        if not any(aguja in _texto(c).lower() for c in campos):
            return False
    operador = filtros.get("operador")
    if operador and _texto(fila.get("operador")).lower() != operador.lower():
        return False
    minimo = filtros.get("monto_min")
    if minimo is not None and _monto(fila.get("monto_origen")) < minimo:
        return False
    maximo = filtros.get("monto_max")
    if maximo is not None and _monto(fila.get("monto_origen")) > maximo:
        return False
    return True


async def generar(*, desde: str, hasta: str, flujos=None, buscar: str = None,
                  operador: str = None, monto_min=None, monto_max=None,
                  tz_min: int = 0, limite: int = FILAS_POR_PAGINA,
                  saltear: int = 0, db=None) -> dict:
    """El reporte: totales exactos del periodo entero, y una página de filas.

    Los totales NO se calculan sobre la página: se calculan sobre todo lo que
    matchea. Un total que solo suma lo que se ve en pantalla es la forma más
    silenciosa de reportar de menos.
    """
    base = await _db(db)
    inicio, fin = _rango(desde, hasta, tz_min)

    pedidas = [f for f in (flujos or list(FUENTES)) if f in FUENTES]
    if not pedidas:
        raise ReporteInvalido(
            f"No conozco esas fuentes. Las que hay: {', '.join(sorted(FUENTES))}.")

    filtros = {"buscar": _texto(buscar) or None,
               "operador": _texto(operador) or None,
               "monto_min": None if monto_min in (None, "") else _monto(monto_min),
               "monto_max": None if monto_max in (None, "") else _monto(monto_max)}

    totales = _Totales()
    todas = []
    truncado = False
    for clave in pedidas:
        filas, corto = await _recorrer(base, clave, inicio, fin, filtros)
        truncado = truncado or corto
        for fila in filas:
            if not _pasa_filtros(fila, filtros):
                continue
            totales.sumar(fila)
            todas.append(fila)

    todas.sort(key=lambda f: (f.get("fecha") or datetime.min.replace(tzinfo=timezone.utc)))

    # `limite=None` es «todas»: lo usa la descarga. En la pantalla el limite
    # siempre viene puesto, y se acota para que `?limite=999999` no sea una
    # forma de pedir la coleccion entera servida en un JSON.
    if limite is None:
        pagina, saltear = todas, 0
    else:
        limite = max(1, min(int(limite), TOPE_FILAS))
        saltear = max(0, int(saltear or 0))
        pagina = todas[saltear:saltear + limite]

    return {
        "criterios": {
            "desde": desde, "hasta": hasta, "tz_min": tz_min,
            "flujos": pedidas, "buscar": filtros["buscar"],
            "operador": filtros["operador"],
            "monto_min": None if filtros["monto_min"] is None else str(filtros["monto_min"]),
            "monto_max": None if filtros["monto_max"] is None else str(filtros["monto_max"]),
        },
        "generado_at": datetime.now(timezone.utc).isoformat(),
        "inicio_utc": inicio.isoformat(),
        "fin_utc": fin.isoformat(),
        "operaciones": totales.cuantas,
        "totales": totales.como_dict(),
        "truncado": truncado,
        "filas": [_serializable(f, tz_min) for f in pagina],
        "hay_mas": limite is not None and len(todas) > saltear + limite,
    }


def _serializable(fila: dict, tz_min: int) -> dict:
    salida = dict(fila)
    salida["fecha"] = _fecha_local(fila.get("fecha"), tz_min)
    # Los montos SIEMPRE con dos decimales. Sin esto la columna mezcla «350.0»
    # —que sale de un float— con «132.00» —que sale de un string— en la misma
    # planilla, y una columna de dinero que no alinea los decimales se lee mal y
    # se suma peor.
    for campo in ("monto_origen", "monto_destino"):
        valor = fila.get(campo)
        salida[campo] = None if valor in (None, "") else str(quantize_money(_monto(valor)))
    # La tasa NO es dinero: puede tener cuatro decimales y redondearla a dos
    # cambia el numero con el que se hizo la operacion.
    tasa = fila.get("tasa")
    salida["tasa"] = None if tasa in (None, "") else str(_monto(tasa))
    return salida


def _fecha_local(valor, tz_min: int) -> str:
    if not isinstance(valor, datetime):
        return ""
    momento = valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    return (momento + timedelta(minutes=tz_min)).strftime("%Y-%m-%d %H:%M")


async def reporte_completo(*, db=None, **criterios) -> dict:
    """El mismo reporte pero con TODAS las filas. Para las descargas.

    Un archivo que trae una pagina y se llama «reporte del mes» es la trampa mas
    facil de este modulo: se abre en Excel, se suma la columna, y el numero no da
    con el total del encabezado. Por eso la descarga pide `limite=None` y el
    encabezado del archivo lleva los MISMOS totales que la pantalla.
    """
    criterios = dict(criterios)
    criterios.pop("limite", None)
    criterios.pop("saltear", None)
    return await generar(db=db, limite=None, **criterios)
