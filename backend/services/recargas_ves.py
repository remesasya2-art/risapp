"""
services/recargas_ves.py — La cola de recargas VES, como cola de trabajo.

QUE ESTABA MAL, VERIFICADO CONTRA EL CODIGO
    La pantalla pedía `GET /admin/recharges/ves`, que devolvía **las 100 más
    nuevas de cualquier estado**, y recién ahí el navegador filtraba las
    pendientes. De ahí salen dos defectos que no se ven mirando la pantalla un
    día tranquilo:

      1. PANTALLA EN BLANCO. El cartel de «no hay nada» estaba atado a que la
         lista viniera vacía, pero lo que se dibuja es la lista YA FILTRADA. Con
         cien recargas viejas y ninguna pendiente, la lista no está vacía, el
         cartel no aparece, y el filtro no deja nada: el operador ve una página
         muda y no puede saber si está al día o si la pantalla se rompió.

      2. UNA ORDEN PENDIENTE SE PUEDE PERDER. El corte de 100 se aplica ANTES
         de filtrar y ordenando de la más nueva a la más vieja. Cuando hay más
         de cien recargas, la pendiente más vieja queda fuera del corte y
         desaparece de la cola. Es plata esperando que nadie ve.

    Los dos se arreglan del mismo modo: filtrar y contar en la base, y paginar
    sobre el resultado filtrado.

POR QUE LAS PENDIENTES SALEN DE LA MAS VIEJA A LA MAS NUEVA
    Al revés de como estaban. Una cola de trabajo se atiende FIFO: quien más
    esperó, primero. Ordenar de la más nueva a la más vieja es exactamente lo
    que entierra la orden que más urge, que es la que lleva tres días parada.
    Las ya procesadas sí salen de la más nueva a la más vieja, porque ahí lo que
    se busca es «qué pasó recién».

UNA CONSULTA POR USUARIO, NO CIEN
    La ruta hacía un `find_one` a `users` POR CADA recarga. Cien recargas, cien
    viajes a la base en una sola petición. Acá los usuarios se traen todos
    juntos con un `$in`.

LOS CONTADORES SE CUENTAN SOBRE TODO, NO SOBRE LA PAGINA
    Si el total de pendientes saliera de contar lo que entró en la página, con
    paginación diría «50» para siempre. Van en su propia consulta.
"""

from datetime import datetime, timezone

# Tope duro de lectura. La paginación es lo que evita traer la colección
# entera; esto es el cinturón por si alguien pide `limite=99999`.
LIMITE_MAXIMO = 200
LIMITE_POR_DEFECTO = 50

ESTADOS = ("pending", "approved", "rejected")

# Umbrales de antigüedad, en horas. No son un SLA contractual: son el semáforo
# que le dice al operador qué mirar primero. Una orden de hace tres días y una
# de hace dos minutos se veían EXACTAMENTE IGUAL en la pantalla vieja.
ANTIGUEDAD_ATENCION = 6
ANTIGUEDAD_URGENTE = 24


class ColaInvalida(Exception):
    """Lo que pidieron no se puede contestar, y la culpa no es del servidor."""

    def __init__(self, mensaje, http=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.http = http


def _a_float(valor):
    """Los montos vienen como float, Decimal128 o string según quién los grabó."""
    if valor is None:
        return 0.0
    try:
        return float(valor)
    except (TypeError, ValueError):
        try:
            return float(str(valor))
        except (TypeError, ValueError):
            return 0.0


def referencia_humana(transaction_id):
    """Un número de orden que una persona pueda dictar por teléfono.

    Las recargas VES nunca tuvieron `display_id` —lo tienen los retiros, no
    ellas— así que el operador sólo contaba con `rech_9f2c8a1b4d5e`. Esto se
    deriva del mismo id, no lo inventa: no hace falta migrar nada y dos llamadas
    distintas dan siempre lo mismo. No es un correlativo y no pretende serlo;
    para un correlativo de verdad hace falta un contador, y eso es otra cosa.
    """
    texto = str(transaction_id or "")
    cola = texto.split("_")[-1][-8:].upper()
    return f"RV-{cola}" if cola else ""


def _fecha(valor):
    """`created_at` está a veces como datetime y a veces como texto ISO."""
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if isinstance(valor, str) and valor:
        try:
            limpio = valor.replace("Z", "+00:00")
            fecha = datetime.fromisoformat(limpio)
            return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def antiguedad(creado, ahora=None):
    """Cuánto lleva esperando, y con qué urgencia hay que mirarla.

    Devuelve `None` en `horas` cuando no hay fecha utilizable, y `nivel` queda
    en «desconocida». Inventar cero horas ahí sería peor que no decir nada: una
    orden sin fecha se vería como recién llegada.
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


def _filtro(estado, texto, ids_de_usuarios):
    filtro = {"type": "recharge_ves", "hidden_from_admin": {"$ne": True}}
    if estado != "all":
        filtro["status"] = estado
    if texto:
        # Se busca por lo que el operador tiene a mano cuando alguien reclama:
        # el id de la orden, los tres dígitos de la referencia, o el usuario.
        o = [
            {"transaction_id": {"$regex": texto, "$options": "i"}},
            {"reference_digits": texto[:3]},
        ]
        if ids_de_usuarios:
            o.append({"user_id": {"$in": list(ids_de_usuarios)}})
        filtro["$or"] = o
    return filtro


async def _usuarios_que_matchean(db, texto):
    """Los usuarios cuyo nombre o mail contiene el texto buscado.

    Va aparte porque `users` y `transactions` son colecciones distintas y no hay
    join: primero se resuelve quiénes son, después se filtran sus recargas.
    """
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
    """Todos los usuarios de la página, en UNA consulta."""
    ids = [i for i in ids if i]
    if not ids:
        return {}
    cursor = db.users.find(
        {"user_id": {"$in": ids}},
        {"_id": 0, "user_id": 1, "email": 1, "full_name": 1, "name": 1, "phone": 1},
    )
    return {u["user_id"]: u async for u in cursor if u.get("user_id")}


async def contadores(db, ahora=None):
    """El tamaño real de la cola, contado sobre TODO y no sobre la página.

    Incluye la exposición en VES —cuánta plata hay esperando aprobación— y la
    orden más vieja sin atender, que es el único número que dice si la cola se
    está atrasando.
    """
    base = {"type": "recharge_ves", "hidden_from_admin": {"$ne": True}}
    por_estado = {estado: 0 for estado in ESTADOS}
    pendiente_ves = 0.0
    sin_banco = 0
    sin_comprobante = 0
    mas_vieja = None
    total = 0

    cursor = db.transactions.find(base, {
        "_id": 0, "status": 1, "amount_ves": 1, "amount_input": 1,
        "destination_bank_id": 1, "destination_bank": 1,
        "proof_image": 1, "created_at": 1,
    })
    async for tx in cursor:
        total += 1
        estado = tx.get("status") or "pending"
        if estado in por_estado:
            por_estado[estado] += 1
        if estado != "pending":
            continue
        pendiente_ves += _a_float(tx.get("amount_ves") or tx.get("amount_input"))
        if not (tx.get("destination_bank_id") or tx.get("destination_bank")):
            sin_banco += 1
        if not tx.get("proof_image"):
            sin_comprobante += 1
        fecha = _fecha(tx.get("created_at"))
        if fecha and (mas_vieja is None or fecha < mas_vieja):
            mas_vieja = fecha

    return {
        "total": total,
        "pendientes": por_estado["pending"],
        "aprobadas": por_estado["approved"],
        "rechazadas": por_estado["rejected"],
        "ves_pendiente": round(pendiente_ves, 2),
        "sin_banco": sin_banco,
        "sin_comprobante": sin_comprobante,
        "mas_vieja": antiguedad(mas_vieja, ahora=ahora) if mas_vieja else
                     {"horas": None, "nivel": "desconocida"},
    }


async def cola(db, estado="pending", texto="", limite=LIMITE_POR_DEFECTO,
               saltear=0, ahora=None):
    """Una página de la cola, ya filtrada y ordenada, más el tamaño total.

    `total` es cuántas cumplen el filtro, no cuántas entraron en la página: sin
    eso la paginación no puede saber si hay una siguiente.
    """
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
    filtro = _filtro(estado, texto, ids_usuarios)

    # FIFO para lo pendiente: primero quien más esperó. Para lo ya procesado, al
    # revés, porque ahí se busca lo último que pasó.
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
        banco_id = tx.get("destination_bank_id")
        filas.append({
            "transaction_id": tx.get("transaction_id"),
            "referencia": referencia_humana(tx.get("transaction_id")),
            "posicion": posicion if estado == "pending" else None,
            "user_id": tx.get("user_id"),
            # El nombre salía sólo de `name`, y los usuarios nuevos guardan
            # `full_name`: al operador le aparecía «Unknown» sobre plata real.
            "user_name": u.get("full_name") or u.get("name") or "",
            "user_email": u.get("email") or "",
            "user_phone": u.get("phone") or "",
            "amount_ves": _a_float(tx.get("amount_ves") or tx.get("amount_input")),
            "amount_ris": _a_float(tx.get("amount_ris") or tx.get("amount_output")),
            "rate_used": _a_float(tx.get("rate_used") or tx.get("rate")),
            "status": tx.get("status") or "pending",
            "proof_image": tx.get("proof_image"),
            "destination_bank": tx.get("destination_bank"),
            "destination_bank_id": banco_id,
            "destination_bank_name": tx.get("destination_bank_name"),
            "reference_digits": tx.get("reference_digits"),
            "rejection_reason": tx.get("rejection_reason"),
            "payment_method": tx.get("payment_method"),
            "created_at": tx.get("created_at"),
            "processed_at": tx.get("processed_at"),
            "processed_by": tx.get("processed_by"),
            # Existe en la base y la ruta no lo devolvía, así que la pantalla no
            # tenía cómo mostrar que otro operador ya estaba en esta orden.
            "assigned_to": tx.get("assigned_to"),
            "assigned_to_name": tx.get("assigned_to_name"),
            "banco_elegido_a_mano": bool(tx.get("banco_elegido_a_mano")),
            "antiguedad": antiguedad(tx.get("created_at"), ahora=ahora),
            # Lo que le falta a ESTA orden para poder aprobarse. Se calcula acá
            # y no en la pantalla para que el listado y el botón no puedan
            # discrepar sobre si una orden está lista.
            "falta_banco": not banco_id,
            "falta_comprobante": not tx.get("proof_image"),
        })

    return {
        "recharges": filas,
        "total": total,
        "limite": limite,
        "saltear": saltear,
        "hay_mas": saltear + len(filas) < total,
        "estado": estado,
        "busqueda": texto,
    }
