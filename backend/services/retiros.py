"""
services/retiros.py — La cola de pagos, como cola de pagos.

QUE ESTABA MAL, VERIFICADO CONTRA EL CODIGO

    1. EL TOTAL A PROVISIONAR MEZCLABA MONEDAS. `queue-stats` sumaba
       `amount_output` de TODOS los retiros pendientes en una sola cifra y la
       pantalla la rotulaba «TOTAL VES NECESARIOS». Pero un retiro puede salir
       en VES o en BRL —los dos se guardan con `type: "withdrawal"`— así que un
       envío en reales sumaba sus reales al total de bolívares. Quien mira ese
       número para saber cuánta plata poner en las cuentas venezolanas
       provisiona de menos o de más, y no tiene cómo darse cuenta.

       Acá el total va SIEMPRE por moneda de salida. No hay una cifra única
       porque no existe: son dos cajas distintas.

    2. EL TOTAL EN RIS SIEMPRE DECIA CERO. La pantalla leía
       `total_ris_pending` y `queue-stats` nunca devolvió ese campo, así que
       era `undefined` y se formateaba como «0,00». Un número que siempre
       miente es peor que no mostrarlo.

    3. SE TRAIAN 200 RETIROS DE CUALQUIER ESTADO Y SE FILTRABA EN EL NAVEGADOR.
       Mismo defecto que tenía la cola de recargas: pasados los 200, el
       pendiente MAS VIEJO se caía de la lista, y es gente esperando su plata.

    4. NO ERA FIFO. Salían del más nuevo al más viejo, que entierra al que más
       esperó. En una cola de pagos eso importa todavía más que en una de
       aprobaciones: del otro lado hay alguien esperando un cobro.

    5. UNA CONSULTA A `users` POR CADA RETIRO.

    6. EL NOMBRE SALIA SOLO DE `name`, y los usuarios nuevos guardan
       `full_name`: al operador le aparecía «Unknown» sobre plata real.

LO QUE ESTE MODULO NO HACE
    No paga ni rechaza: eso sigue en `POST /admin/withdrawals/process`, intacto.
    Acá sólo se lee la cola.
"""

from datetime import datetime, timezone

LIMITE_MAXIMO = 200
LIMITE_POR_DEFECTO = 50

ESTADOS = ("pending", "completed", "rejected")

# Umbrales de antigüedad, en horas. Más exigentes que en las recargas: una
# recarga que tarda es un saldo que no aparece; un retiro que tarda es plata
# que alguien ya no tiene y todavía no recibió.
ANTIGUEDAD_ATENCION = 3
ANTIGUEDAD_URGENTE = 12


class ColaInvalida(Exception):
    def __init__(self, mensaje, http=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.http = http


def _a_float(valor):
    if valor is None:
        return 0.0
    try:
        return float(valor)
    except (TypeError, ValueError):
        try:
            return float(str(valor))
        except (TypeError, ValueError):
            return 0.0


def _fecha(valor):
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if isinstance(valor, str) and valor:
        try:
            fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
            return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def antiguedad(creado, ahora=None):
    """Cuánto lleva esperando, y con qué urgencia.

    Sin fecha devuelve `None`, no cero: una orden sin fecha se vería como
    recién llegada, que es lo contrario de lo que hay que sospechar.
    """
    fecha = _fecha(creado)
    if fecha is None:
        return {"horas": None, "nivel": "desconocida"}
    ahora = ahora or datetime.now(timezone.utc)
    horas = (ahora - fecha).total_seconds() / 3600.0
    if horas >= ANTIGUEDAD_URGENTE:
        nivel = "urgente"
    elif horas >= ANTIGUEDAD_ATENCION:
        nivel = "atencion"
    else:
        nivel = "normal"
    return {"horas": round(horas, 2), "nivel": nivel}


async def _usuarios_que_matchean(db, texto):
    if not texto:
        return set()
    cursor = db.users.find(
        {"$or": [
            {"email": {"$regex": texto, "$options": "i"}},
            {"full_name": {"$regex": texto, "$options": "i"}},
            {"name": {"$regex": texto, "$options": "i"}},
        ]},
        {"user_id": 1},
    ).limit(500)
    return {u.get("user_id") async for u in cursor if u.get("user_id")}


async def _usuarios_por_id(db, ids):
    ids = [i for i in ids if i]
    if not ids:
        return {}
    cursor = db.users.find(
        {"user_id": {"$in": ids}},
        {"_id": 0, "user_id": 1, "email": 1, "full_name": 1, "name": 1},
    )
    return {u["user_id"]: u async for u in cursor if u.get("user_id")}


def _filtro(estado, texto, ids_de_usuarios, moneda):
    filtro = {"type": "withdrawal", "hidden_from_admin": {"$ne": True}}
    if estado != "all":
        filtro["status"] = estado
    if moneda:
        filtro["currency_output"] = moneda.upper()
    if texto:
        # Lo que el operador tiene a mano cuando alguien reclama: el número de
        # orden, el nombre del beneficiario, o el usuario que lo pidió.
        o = [
            {"display_id": {"$regex": texto, "$options": "i"}},
            {"transaction_id": {"$regex": texto, "$options": "i"}},
            {"beneficiary_data.full_name": {"$regex": texto, "$options": "i"}},
            {"beneficiary_data.cedula": {"$regex": texto, "$options": "i"}},
            {"beneficiary_data.account_number": {"$regex": texto, "$options": "i"}},
            {"beneficiary_data.phone": {"$regex": texto, "$options": "i"}},
        ]
        if ids_de_usuarios:
            o.append({"user_id": {"$in": list(ids_de_usuarios)}})
        filtro["$or"] = o
    return filtro


async def contadores(db, ahora=None):
    """El tamaño de la cola, y cuánta plata hay que tener lista EN CADA MONEDA.

    `por_moneda` es lo que reemplaza al «total VES necesarios» de una sola
    cifra: cada moneda de salida con su total y su cantidad de órdenes. Sumarlas
    en un número daría un total que no existe en ninguna cuenta bancaria.
    """
    base = {"type": "withdrawal", "hidden_from_admin": {"$ne": True}}
    por_estado = {estado: 0 for estado in ESTADOS}
    por_moneda = {}      # moneda de salida -> {total, ordenes}
    por_origen = {}      # moneda de origen  -> total debitado a los usuarios
    sin_beneficiario = 0
    mas_vieja = None
    total = 0

    cursor = db.transactions.find(base, {
        "_id": 0, "status": 1, "amount_output": 1, "currency_output": 1,
        "amount_input": 1, "currency_input": 1,
        "beneficiary_data": 1, "created_at": 1,
    })
    async for tx in cursor:
        total += 1
        estado = tx.get("status") or "pending"
        if estado in por_estado:
            por_estado[estado] += 1
        if estado != "pending":
            continue

        salida = (tx.get("currency_output") or "VES").upper()
        caja = por_moneda.setdefault(salida, {"total": 0.0, "ordenes": 0})
        caja["total"] += _a_float(tx.get("amount_output"))
        caja["ordenes"] += 1

        origen = (tx.get("currency_input") or "RIS").upper()
        por_origen[origen] = por_origen.get(origen, 0.0) + _a_float(tx.get("amount_input"))

        beneficiario = tx.get("beneficiary_data") or {}
        if not (beneficiario.get("full_name") or beneficiario.get("name")):
            sin_beneficiario += 1

        fecha = _fecha(tx.get("created_at"))
        if fecha and (mas_vieja is None or fecha < mas_vieja):
            mas_vieja = fecha

    for caja in por_moneda.values():
        caja["total"] = round(caja["total"], 2)

    return {
        "total": total,
        "pendientes": por_estado["pending"],
        "pagados": por_estado["completed"],
        "rechazados": por_estado["rejected"],
        # A provisionar, por moneda. NO hay una cifra única: son cajas distintas.
        "por_moneda": [{"moneda": m, **v} for m, v in
                       sorted(por_moneda.items(), key=lambda kv: -kv[1]["total"])],
        # Lo que ya se le debitó al usuario y todavía no se pagó, por moneda de
        # origen. Es el pasivo vivo de la cola.
        "por_origen": [{"moneda": m, "total": round(t, 2)} for m, t in
                       sorted(por_origen.items(), key=lambda kv: -kv[1])],
        "sin_beneficiario": sin_beneficiario,
        "mas_vieja": antiguedad(mas_vieja, ahora=ahora) if mas_vieja else
                     {"horas": None, "nivel": "desconocida"},
    }


def _comprobantes(tx):
    """Cuántos comprobantes de pago tiene, mirando los dos campos.

    Conviven `proof_images` (lista) y `proof_image` (uno solo, viejo). Contar
    sólo el nuevo mostraría «0 imágenes» en retiros que sí tienen su
    comprobante.
    """
    imagenes = tx.get("proof_images") or []
    if imagenes:
        return len(imagenes)
    return 1 if tx.get("proof_image") else 0


async def cola(db, estado="pending", texto="", moneda=None,
               limite=LIMITE_POR_DEFECTO, saltear=0, ahora=None):
    """Una página de la cola de pagos, filtrada, ordenada y contada."""
    estado = (estado or "pending").strip().lower()
    if estado not in ESTADOS and estado != "all":
        raise ColaInvalida(
            f"Estado inválido: {estado!r}. Los válidos son "
            f"{', '.join(ESTADOS)} o 'all'.")
    try:
        limite = int(limite)
        saltear = int(saltear)
    except (TypeError, ValueError):
        raise ColaInvalida("El límite y el salteo tienen que ser números.")
    limite = max(1, min(limite, LIMITE_MAXIMO))
    saltear = max(0, saltear)
    texto = (texto or "").strip()

    ids_usuarios = await _usuarios_que_matchean(db, texto)
    filtro = _filtro(estado, texto, ids_usuarios, moneda)

    # FIFO para lo pendiente: del otro lado hay alguien esperando un cobro.
    orden = 1 if estado == "pending" else -1

    total = await db.transactions.count_documents(filtro)
    cursor = (db.transactions.find(filtro, {"_id": 0})
              .sort("created_at", orden).skip(saltear).limit(limite))
    crudas = [tx async for tx in cursor]

    usuarios = await _usuarios_por_id(db, [tx.get("user_id") for tx in crudas])
    ahora = ahora or datetime.now(timezone.utc)

    filas = []
    for posicion, tx in enumerate(crudas, start=saltear + 1):
        u = usuarios.get(tx.get("user_id")) or {}
        b = tx.get("beneficiary_data") or {}
        filas.append({
            "transaction_id": tx.get("transaction_id"),
            "display_id": tx.get("display_id") or (tx.get("transaction_id") or "")[:8],
            "posicion": posicion if estado == "pending" else None,
            "user_id": tx.get("user_id"),
            "user_name": u.get("full_name") or u.get("name") or "",
            "user_email": u.get("email") or "",
            "amount_input": _a_float(tx.get("amount_input")),
            "currency_input": (tx.get("currency_input") or "RIS").upper(),
            "amount_output": _a_float(tx.get("amount_output")),
            "currency_output": (tx.get("currency_output") or "VES").upper(),
            "rate": _a_float(tx.get("rate")),
            "status": tx.get("status") or "pending",
            "beneficiary_data": b,
            "payment_type": tx.get("payment_type") or b.get("payment_type"),
            "is_gestor_transaction": bool(tx.get("is_gestor_transaction")),
            "client_name": tx.get("client_name"),
            "created_at": tx.get("created_at"),
            "completed_at": tx.get("completed_at"),
            "rejection_reason": tx.get("rejection_reason"),
            "proof_image": tx.get("proof_image"),
            "proof_images": tx.get("proof_images") or [],
            "pending_images": tx.get("pending_images") or [],
            "comprobantes": _comprobantes(tx),
            "processed_by": tx.get("processed_by"),
            "paid_from_bank": tx.get("paid_from_bank"),
            # Existe en la base y la ruta no lo devolvía: la pantalla no tenía
            # cómo mostrar que otro operador ya estaba pagando esta orden.
            "assigned_to": tx.get("assigned_to"),
            "assigned_to_name": tx.get("assigned_to_name"),
            "antiguedad": antiguedad(tx.get("created_at"), ahora=ahora),
            # Sin datos del beneficiario no hay a quién pagarle. Se calcula acá
            # para que el listado y el botón no puedan discrepar.
            "falta_beneficiario": not (b.get("full_name") or b.get("name")),
            "falta_destino": not (b.get("account_number") or b.get("phone")),
        })

    return {
        "withdrawals": filas,
        "total": total,
        "limite": limite,
        "saltear": saltear,
        "hay_mas": saltear + len(filas) < total,
        "estado": estado,
        "busqueda": texto,
        "moneda": (moneda or "").upper() or None,
    }
