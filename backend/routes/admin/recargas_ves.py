"""
routes/admin/recargas_ves.py — Las recargas en bolívares: la cola, tomar y soltar una orden, revisar la
referencia, aprobar o rechazar; y la verificación del pago en bolívares de
un envío a Brasil.

Parte de lo que era `routes/admin.py`. Por qué está dividido, y en qué orden
se registran las partes: `routes/admin/__init__.py`.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from database import db
from services import las_fotos
from services import quien_es, transacciones
from services.money import from_db, para_mostrar, to_float, to_decimal, to_decimal128
from models.user import User
from models.acciones_del_panel import (EstadoCambiado, OrdenLiberada, OrdenTomada,
                                       RecargaProcesada)
from models.panel_recargas import ColaDeRecargasVes, ControlDeReferencia, RecargasVesPendientes
from models.panel_ordenes import OrdenesPorProcesar
from pydantic import BaseModel
from routes.dependencies import get_super_admin
from services.notifications import create_notification
from services import (auditoria, kyc_quota,
                      lotes_de_pago)
from routes.admin._comun import logger

router = APIRouter(prefix="/admin", tags=["admin"])


# ============== PARTNERS/GESTORS ==============

# ============== VES RECHARGES ADMIN ==============

@router.get("/recharges/ves/pending", response_model=RecargasVesPendientes, response_model_exclude_unset=True)
async def get_pending_ves_recharges(admin: User = Depends(get_super_admin)):
    """Get pending VES recharge requests"""
    # `proof_image` SI se pide acá: es la foto que el operador viene a mirar
    # para aprobar la recarga. Lo que no se pide es `proof_images`, que en esta
    # cola no existe —se escribe al completar un retiro— y venía igual.
    filas = await db.transactions.find(
        {"type": "recharge_ves", "status": "pending",
         "hidden_from_admin": {"$ne": True}},
        las_fotos.solo("transaction_id", "user_id", "status",
                       "amount_ves", "amount_ris", "rate_used",
                       "destination_bank", "destination_bank_id",
                       "destination_bank_name", "proof_image", "created_at"),
    ).sort("created_at", -1).limit(100).to_list(100)

    quien = await quien_es.de_las_filas(db, filas)

    recharges = []
    for tx in filas:
        user = quien.ya_conocido(tx.get("user_id"))
        recharges.append({
            "transaction_id": tx.get("transaction_id"),
            "user_id": tx.get("user_id"),
            "user_name": user.get("name") if user else "Unknown",
            "user_email": user.get("email") if user else "",
            "amount_ves": tx.get("amount_ves", 0),
            "amount_ris": tx.get("amount_ris", 0),
            "rate_used": tx.get("rate_used", 0),
            "status": tx.get("status", "pending"),
            "proof_image": tx.get("proof_image"),
            # Esta proyeccion NO los traia, y son justo los que el panel lee
            # para mostrar el banco y decidir si hace falta elegirlo a mano. Es
            # el mismo defecto de clase que el de la creacion: un campo que
            # existe en la base y se pierde en el camino.
            "destination_bank": tx.get("destination_bank"),
            "destination_bank_id": tx.get("destination_bank_id"),
            "destination_bank_name": tx.get("destination_bank_name"),
            "created_at": tx.get("created_at"),
        })

    # El tamaño del problema, para no tener que contarlo a mano. Son las que
    # nacieron rotas: el arreglo de la creacion no las alcanza y las tiene que
    # resolver una persona, una por una, mirando el comprobante.
    faltantes = {"total_pendientes": len(recharges),
                 "sin_banco": sum(1 for r in recharges if not r["destination_bank_id"]),
                 "sin_comprobante": sum(1 for r in recharges if not r["proof_image"])}

    return {"recharges": recharges, "faltantes": faltantes}


class OrdenClaimRequest(BaseModel):
    orden_id: str
    flujo: str  # ris_ves | ris_reais | ves_ris | btc_ves


def _resolver_coleccion_orden(flujo: str, orden_id: str):
    """Ubica la colección y el filtro correcto para una orden del panel unificado,
    según su flujo. Devuelve (None, None) si el flujo no es válido."""
    if flujo in ("ris_ves", "ris_reais", "usdt_ves", "usdc_ves"):
        return db.transactions, {"transaction_id": orden_id, "type": "withdrawal"}
    if flujo == "ves_ris":
        return db.transactions, {"transaction_id": orden_id, "type": "recharge_ves"}
    if flujo == "btc_ves":
        return db.btc_remesas, {"remesa_id": orden_id}
    return None, None


@router.post("/ordenes/tomar", response_model=OrdenTomada, response_model_exclude_unset=True)
async def tomar_orden(data: OrdenClaimRequest, admin: User = Depends(get_super_admin)):
    """El operador 'reclama' una orden pendiente para dejar claro que él la está
    procesando y evitar que otro administrador la trabaje en simultáneo."""
    coleccion, query = _resolver_coleccion_orden(data.flujo, data.orden_id)
    if coleccion is None:
        raise HTTPException(status_code=400, detail="Flujo inválido")

    doc = await coleccion.find_one(query)
    if not doc:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    admin_name = getattr(admin, "full_name", None) or getattr(admin, "name", None) or admin.email
    assigned_to = doc.get("assigned_to")

    if assigned_to and assigned_to != admin.user_id:
        return {
            "success": False,
            "assigned_to": assigned_to,
            "assigned_to_name": doc.get("assigned_to_name") or "otro operador",
        }

    await coleccion.update_one(query, {"$set": {
        "assigned_to": admin.user_id,
        "assigned_to_name": admin_name,
        "assigned_at": datetime.now(timezone.utc),
        "estado_admin": "en_proceso",
    }})
    return {"success": True, "assigned_to": admin.user_id, "assigned_to_name": admin_name}


@router.post("/ordenes/liberar", response_model=OrdenLiberada, response_model_exclude_unset=True)
async def liberar_orden(data: OrdenClaimRequest, admin: User = Depends(get_super_admin)):
    """Libera una orden previamente reclamada, para que cualquier operador
    pueda tomarla de nuevo."""
    coleccion, query = _resolver_coleccion_orden(data.flujo, data.orden_id)
    if coleccion is None:
        raise HTTPException(status_code=400, detail="Flujo inválido")

    doc = await coleccion.find_one(query)
    if not doc:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    if doc.get("assigned_to") and doc.get("assigned_to") != admin.user_id:
        raise HTTPException(status_code=403, detail="Esta orden está asignada a otro operador")

    await coleccion.update_one(query, {"$set": {
        "assigned_to": None,
        "assigned_to_name": None,
        "assigned_at": None,
        "estado_admin": "pendiente",
    }})
    return {"success": True}


@router.get("/ordenes/pendientes", response_model=OrdenesPorProcesar, response_model_exclude_unset=True)
async def get_ordenes_pendientes(admin: User = Depends(get_super_admin)):
    """Área unificada de 'Órdenes por procesar'.

    Junta en una sola lista normalizada todas las órdenes pendientes de los
    distintos flujos (RIS→VES, BTC→VES, VES→RIS) para que el super_admin las
    procese desde un solo lugar. NO descuenta bancos internos: la contabilidad
    se lleva en la app externa. La info completa queda disponible aquí.
    """
    ordenes = []
    # Este diccionario estaba escrito a mano acá, y copiado igual en otras dos
    # pantallas. Las tres copias pedían el usuario ENTERO para leerle el
    # nombre. Ahora es uno solo, con lista de lo permitido.
    #
    # Sigue siendo una consulta por cliente DISTINTO y no por fila, que es lo
    # que la caché ya lograba: acá se recorren varios cursores distintos y no
    # hay una lista sola que se pueda precargar de una.
    quien = quien_es.Directorio(db)

    # 1) RIS → VES y RIS → Reais (retiros): el admin paga y sube comprobante.
    #    Se distinguen por currency_output (VES vs BRL).
    # Las que están en un lote salen de la cola: ya las tomó alguien para
    # pagarlas. Se las ve en el panel de lotes abiertos, no acá — si no
    # estuvieran en ningún lado, para el operador habrían desaparecido.
    async for tx in db.transactions.find(
        {"type": "withdrawal", "status": "pending", "hidden_from_admin": {"$ne": True},
         "estado_admin": {"$ne": lotes_de_pago.EN_LOTE}},
        las_fotos.solo("transaction_id", "display_id", "user_id",
                       "amount_input", "amount_output", "amount_ris", "amount_ves",
                       "currency_input", "currency_output", "beneficiary_data",
                       "payment_type", "estado_admin", "assigned_to",
                       "assigned_to_name", "created_at"),
    ).sort("created_at", 1):
        u = await quien.de(tx.get("user_id"))
        b = tx.get("beneficiary_data", {}) or {}
        cur_in = str(tx.get("currency_input") or "RIS").upper()
        cur_out = str(tx.get("currency_output") or "VES").upper()
        if cur_in in ("USDT", "USDC"):
            flujo = "usdt_ves" if cur_in == "USDT" else "usdc_ves"
            flujo_label = f"{cur_in}RIS → VES"
            unidad_dest = "VES"
            beneficiario = {
                "nombre": b.get("full_name") or b.get("name", ""),
                "documento": b.get("cedula") or b.get("id_document", ""),
                "banco": b.get("bank") or b.get("bank_code", ""),
                # El CODIGO aparte del nombre. El campo `banco` de arriba se
                # queda con lo primero que encuentre, y en una transferencia eso
                # es el nombre: el código se perdía. Para agrupar pagos por banco
                # y para el formulario de pago móvil hace falta el código.
                "banco_codigo": b.get("bank_code") or "",
                "telefono": b.get("phone") or b.get("phone_number", ""),
                "cuenta": b.get("account_number", ""),
                "tipo_pago": b.get("payment_type") or tx.get("payment_type", ""),
                "pix_key": "",
            }
        elif cur_out in ("BRL", "REAIS", "REAL"):
            flujo, flujo_label, unidad_dest = "ris_reais", "RIS → Reais", "BRL"
            beneficiario = {
                "nombre": b.get("full_name") or b.get("name", ""),
                "documento": b.get("cpf") or b.get("documento", ""),
                "banco": "",
                "telefono": "",
                "cuenta": "",
                "tipo_pago": "pix_br",
                "pix_key": b.get("pix_key", ""),
            }
        else:
            flujo, flujo_label, unidad_dest = "ris_ves", "RIS → VES", "VES"
            beneficiario = {
                "nombre": b.get("full_name") or b.get("name", ""),
                "documento": b.get("cedula") or b.get("id_document", ""),
                "banco": b.get("bank") or b.get("bank_code", ""),
                "banco_codigo": b.get("bank_code") or "",
                "telefono": b.get("phone") or b.get("phone_number", ""),
                "cuenta": b.get("account_number", ""),
                "tipo_pago": b.get("payment_type") or tx.get("payment_type", ""),
                "pix_key": "",
            }
        ordenes.append({
            "orden_id": tx.get("transaction_id"),
            "flujo": flujo,
            "flujo_label": flujo_label,
            "accion": "pagar",
            "display_id": tx.get("display_id"),
            "created_at": tx.get("created_at"),
            "user_name": u.get("full_name") or u.get("name") or "—",
            "user_email": u.get("email", ""),
            "origen": {"valor": tx.get("amount_input", 0), "unidad": cur_in},
            "destino": {"valor": tx.get("amount_output", 0), "unidad": unidad_dest},
            "beneficiario": beneficiario,
            "comprobante_usuario": None,
            "assigned_to": tx.get("assigned_to"),
            "assigned_to_name": tx.get("assigned_to_name"),
            "estado_admin": tx.get("estado_admin", "pendiente"),
        })

    # 2) BTC → VES (remesas pagadas): el admin paga VES y sube comprobante
    async for r in db.btc_remesas.find(
        {"estado": "pagado", "estado_admin": {"$ne": lotes_de_pago.EN_LOTE}},
        {"_id": 0}).sort("pagado_en", 1):
        u = await quien.de(r.get("user_id"))
        b = r.get("beneficiario_data", {}) or {}
        ordenes.append({
            "orden_id": r.get("remesa_id"),
            "flujo": "btc_ves",
            "flujo_label": "BTC → VES",
            "accion": "pagar",
            "display_id": r.get("display_id") or (r.get("remesa_id") or "")[:8],
            "created_at": r.get("pagado_en") or r.get("creado_en"),
            "user_name": u.get("full_name") or u.get("name") or "—",
            "user_email": u.get("email", ""),
            "origen": {"valor": r.get("usd_cliente", 0), "unidad": "USD"},
            "destino": {"valor": r.get("ves_recibe", 0), "unidad": "VES"},
            "beneficiario": {
                "nombre": b.get("full_name") or b.get("name", ""),
                "documento": b.get("cedula", ""),
                "banco": b.get("bank", ""),
                "banco_codigo": b.get("bank_code") or "",
                "telefono": b.get("phone", ""),
                "cuenta": b.get("account_number", ""),
                "tipo_pago": b.get("payment_type", ""),
            },
            "comprobante_usuario": None,
            "assigned_to": r.get("assigned_to"),
            "assigned_to_name": r.get("assigned_to_name"),
            "estado_admin": r.get("estado_admin", "pendiente"),
        })

    # 3) VES → RIS (recargas): el admin REVISA el comprobante del usuario y aprueba
    # `proof_image` SI se pide acá: es la foto que el operador viene a mirar
    # para aprobar la recarga. Lo que no viaja es `proof_images`, que en esta
    # cola no existe —se escribe al completar un retiro— y venía igual.
    async for tx in db.transactions.find(
        {"type": "recharge_ves", "status": "pending", "hidden_from_admin": {"$ne": True},
         "estado_admin": {"$ne": lotes_de_pago.EN_LOTE}},
        las_fotos.solo("transaction_id", "display_id", "user_id",
                       "amount_input", "amount_output", "amount_ris", "amount_ves",
                       "currency_input", "currency_output", "payment_type",
                       "estado_admin", "assigned_to", "assigned_to_name",
                       "proof_image", "created_at"),
    ).sort("created_at", 1):
        u = await quien.de(tx.get("user_id"))
        ordenes.append({
            "orden_id": tx.get("transaction_id"),
            "flujo": "ves_ris",
            "flujo_label": "VES → RIS",
            "accion": "aprobar",
            "display_id": tx.get("display_id"),
            "created_at": tx.get("created_at"),
            "user_name": u.get("full_name") or u.get("name") or "—",
            "user_email": u.get("email", ""),
            "origen": {"valor": tx.get("amount_ves", 0), "unidad": "VES"},
            "destino": {"valor": tx.get("amount_ris", 0), "unidad": "RIS"},
            "beneficiario": None,
            "comprobante_usuario": tx.get("proof_image"),
            "assigned_to": tx.get("assigned_to"),
            "assigned_to_name": tx.get("assigned_to_name"),
            "estado_admin": tx.get("estado_admin", "pendiente"),
        })

    # Más antiguas primero (orden cronológico robusto ante created_at None)
    ordenes.sort(key=lambda o: str(o.get("created_at") or ""))
    return {"ordenes": ordenes, "total": len(ordenes)}


@router.get("/recharges/ves", response_model=ColaDeRecargasVes, response_model_exclude_unset=True)
async def get_all_ves_recharges(
    status: str = "pending",
    q: str = "",
    limit: int = 50,
    skip: int = 0,
    admin: User = Depends(get_super_admin),
):
    """La cola de recargas VES: una página filtrada, ordenada y contada.

    Antes devolvía **las 100 más nuevas de cualquier estado** y la pantalla
    filtraba las pendientes en el navegador. Eso escondía dos defectos:

      - con cien recargas viejas y ninguna pendiente, la pantalla quedaba muda
        (ni lista ni cartel de «no hay nada»);
      - con más de cien recargas, la pendiente MAS VIEJA caía fuera del corte y
        desaparecía de la cola. Plata esperando que nadie veía.

    Ahora el filtro y el conteo van en la base, y las pendientes salen FIFO: la
    que más esperó, primero.
    """
    from services import recargas_ves
    try:
        pagina = await recargas_ves.cola(
            db, estado=status, texto=q, limite=limit, saltear=skip)
    except recargas_ves.ColaInvalida as e:
        raise HTTPException(status_code=e.http, detail=e.mensaje)
    except Exception as e:
        logger.error(f"recargas_ves: no se pudo leer la cola: {e}")
        raise HTTPException(
            status_code=503,
            detail="No se pudo leer la cola de recargas. Reintentá en un momento.")
    pagina["counters"] = await recargas_ves.contadores(db)
    return pagina


@router.get("/recharges/ves/check-reference", response_model=ControlDeReferencia, response_model_exclude_unset=True)
async def check_ves_reference(
    digits: str,
    exclude_transaction_id: str = "",
    admin: User = Depends(get_super_admin)
):
    """Avisa si esos 3 digitos de referencia ya aparecen en OTRA recarga VES
    (posible pago duplicado/colusion). Solo informa; no aprueba ni rechaza.
    El criterio: el RIS le corresponde a quien la registro primero."""
    digits = str(digits or "").strip()[:3]
    if len(digits) < 3:
        return {"digits": digits, "has_collision": False, "matches": []}
    current = None
    if exclude_transaction_id:
        current = await db.transactions.find_one(
            {"transaction_id": exclude_transaction_id}, {"user_id": 1}
        )
    current_user_id = (current or {}).get("user_id")
    q = {"type": "recharge_ves", "reference_digits": digits}
    if exclude_transaction_id:
        q["transaction_id"] = {"$ne": exclude_transaction_id}
    matches = []
    filas = await db.transactions.find(
        q, las_fotos.solo("transaction_id", "user_id", "status",
                          "amount_input", "amount_ves", "created_at"),
    ).sort("created_at", 1).limit(20).to_list(20)
    quien = await quien_es.de_las_filas(db, filas)
    for t in filas:
        u = quien.ya_conocido(t.get("user_id"))
        matches.append({
            "transaction_id": t.get("transaction_id"),
            "user_id": t.get("user_id"),
            "user_name": u.get("full_name") or u.get("name"),
            "user_email": u.get("email"),
            "amount_ves": t.get("amount_ves") or t.get("amount_input"),
            "status": t.get("status"),
            "created_at": t.get("created_at"),
            "is_other_user": t.get("user_id") != current_user_id,
        })
    other_user = [m for m in matches if m["is_other_user"]]
    return {
        "digits": digits,
        "has_collision": len(other_user) > 0,
        "matches": matches,
        "first_registered": matches[0] if matches else None,
    }


@router.post("/recharges/ves/process/{transaction_id}", response_model=RecargaProcesada, response_model_exclude_unset=True)
async def process_ves_recharge(
    transaction_id: str, 
    request: dict,
    admin: User = Depends(get_super_admin)
):
    """Process a VES recharge (approve/reject).
    The bank to credit is taken automatically from the transaction's
    destination_bank_id (set when the user created the recharge)."""
    action = request.get("action")
    rejection_reason = request.get("rejection_reason", "")
    reference_digits = str(request.get("reference_digits", "") or "").strip()[:3]
    
    if action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Accion invalida")
    
    recharge = await db.transactions.find_one({
        "transaction_id": transaction_id,
        "type": "recharge_ves"
    })
    
    if not recharge:
        raise HTTPException(status_code=404, detail="Recarga no encontrada")

    force = bool(request.get("force"))
    if recharge.get("assigned_to") and recharge.get("assigned_to") != admin.user_id and not force:
        raise HTTPException(
            status_code=409,
            detail=f"Esta orden está siendo procesada por {recharge.get('assigned_to_name') or 'otro operador'}",
        )

    if recharge.get("status") != "pending":
        return {"message": "Esta recarga ya fue procesada", "already_processed": True}
    
    user_id = recharge.get("user_id")
    amount_ris = recharge.get("amount_ris") or recharge.get("amount_output", 0)
    amount_ves = recharge.get("amount_ves") or recharge.get("amount_input", 0)
    
    # Resolve destination bank from the transaction itself.
    # Backwards compatibility: older transactions may only have `destination_bank` (legacy code).
    bank_id = recharge.get("destination_bank_id")
    if not bank_id and recharge.get("destination_bank"):
        from routes.transactions import resolve_ves_bank
        bank_id, _ = await resolve_ves_bank(recharge.get("destination_bank"))
    # Final fallback: optional override from request body
    #
    # Es la red para las recargas que ya estan cargadas SIN banco: nacieron
    # rotas y el arreglo de la creacion no las alcanza. Las resuelve una
    # persona, mirando el comprobante. Se anota QUIEN y CUANDO porque es una
    # decision manual sobre plata ajena, y dentro de seis meses la unica forma
    # de entender por que esa recarga entro a ese banco es esto.
    banco_elegido_a_mano = False
    if not bank_id:
        bank_id = request.get("bank_id")
        banco_elegido_a_mano = bool(bank_id)
    
    if action == "approve":
        if not bank_id:
            # El mensaje viejo decia "El usuario no eligio un banco valido al
            # crear la recarga". Era FALSO —la pantalla no lo deja avanzar sin
            # elegirlo; lo perdia el servidor— y le llegaba al operador, que se
            # lo repetia al cliente. Que diga lo que pasa y que hacer.
            raise HTTPException(
                status_code=400,
                detail="Esta solicitud no tiene registrado el banco destino. Elegilo "
                       "abajo mirando el comprobante, o pedile al usuario que confirme "
                       "por dónde pagó."
            )
        bank = await db.bank_accounts.find_one({"bank_id": bank_id})
        if not bank:
            raise HTTPException(status_code=404, detail="Banco destino no encontrado en contabilidad")
        
        # TODO LO QUE ESCRIBE LA APROBACION, EN UNA TRANSACCION
        #
        #   El banco, su libro, el estado de la recarga, el saldo del cliente y
        #   su línea: con un Mongo de un solo nodo son cinco escrituras
        #   separadas, y un corte a la mitad deja, por ejemplo, el banco
        #   acreditado y el cliente no. Con réplicas van juntas. El aviso del
        #   cupo va DESPUES: una transacción que choca se reintenta, y un aviso
        #   no se puede reintentar sin mandarlo dos veces.
        async def trabajo(session):
            # Register in bank ledger (VES received from user)
            #
            # Esta línea hacía `bank["balance"] + amount_ves`. Cuando la cuenta ya
            # había pasado por el ajuste manual de contabilidad, su saldo es
            # `Decimal128`, y sumarle un float levanta TypeError: un 500 crudo, sin
            # `try` que lo atrape, en TODA aprobación sobre esa cuenta. Además el
            # saldo posterior salía de una lectura anterior al `$inc`, así que con
            # dos aprobaciones simultáneas las dos anotaban el mismo número.
            from services import bancos
            _mov = await bancos.ajustar(db, bank_id, amount_ves, session=session)
            new_balance = to_float(_mov["saldo_nuevo"])
        
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "full_name": 1, "name": 1, "email": 1})
            user_name = user_doc.get("full_name", user_doc.get("name", user_doc.get("email", ""))) if user_doc else ""
        
            await db.bank_ledger.insert_one({
                "bank_id": bank_id, "bank_name": bank["name"],
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "type": "entrada",
                "concept": f"Recarga VES de {user_name} (TX {transaction_id[:8]})",
                "amount": amount_ves, "balance_after": new_balance,
                "reference": transaction_id, "notes": "Recarga VES aprobada",
                "created_at": datetime.now(timezone.utc).isoformat()
            }, session=session)
        
            # Update recharge status
            await db.transactions.update_one(
                {"transaction_id": transaction_id},
                {"$set": {
                    "status": "approved",
                    "processed_at": datetime.now(timezone.utc),
                    "processed_by": admin.user_id,
                    "received_in_bank": bank_id,
                    "destination_bank_id": bank_id,
                    "destination_bank_name": bank["name"],
                    "reference_digits": reference_digits,
                    **({"banco_elegido_a_mano": True,
                        "banco_elegido_por": admin.user_id,
                        "banco_elegido_at": datetime.now(timezone.utc)}
                       if banco_elegido_a_mano else {}),
                }},
                session=session,
            )
        
            # Add balance to user
            _rch_user = await db.users.find_one_and_update(
                {"user_id": user_id},
                {"$inc": {"balance_ris": to_decimal128(to_decimal(amount_ris)), **kyc_quota.consume_inc(amount_ris)}},
                return_document=True,
                session=session,
            )
            # Libro mayor RIS (no interrumpe la aprobación)
            try:
                from services.ledger import record_ris_entry
                _rch_after = (_rch_user or {}).get("balance_ris")
                _rch_after = to_float(from_db(_rch_after)) if _rch_after is not None else None
                await record_ris_entry(
                    user_id=user_id,
                    movement_type="recarga_ves",
                    amount=amount_ris,
                    direction="credit",
                    account="balance_ris",
                    balance_before=(_rch_after - amount_ris) if _rch_after is not None else None,
                    balance_after=_rch_after,
                    reference_kind="transaction",
                    reference_id=transaction_id,
                    transaction_id=transaction_id,
                    actor_type="admin",
                    actor_id=admin.user_id,
                    rate=(amount_ves / amount_ris) if amount_ris else None,
                    rate_kind="ves_to_ris",
                    amount_output=amount_ves,
                    currency_output="VES",
                    metadata={"destination_bank_id": bank_id},
                    notes="Recarga VES → RIS aprobada",
                    session=session,
                )
            except Exception as e:
                # Sin transacción, el libro no interrumpe la aprobación. Con
                # transacción, sí: tragarse el error confirmaría el crédito sin su
                # línea.
                if session is not None:
                    raise
                logger.warning(f"Ledger recarga_ves no registrado: {e}")
            return _rch_user

        _rch_user = await transacciones.en_una_transaccion(trabajo)
        # Si esta recarga le agoto el cupo sin KYC, avisarle. Nunca interrumpe.
        await kyc_quota.notify_if_exhausted(_rch_user)
        
        # Notify user
        await create_notification(
            user_id=user_id,
            title="Tu recarga se acreditó",
            message=f"Acreditamos {para_mostrar(amount_ris, 'RIS')} en tu saldo por tu recarga de {para_mostrar(amount_ves, 'VES')}.",
            notification_type="recharge_approved",
            data={"transaction_id": transaction_id, "amount_ris": amount_ris}
        )
        
        message = f"Recarga aprobada. Se añadieron {amount_ris:.2f} RIS al usuario."
        
    elif action == "reject":
        if not rejection_reason:
            raise HTTPException(status_code=400, detail="Debes proporcionar un motivo de rechazo")
        
        # Update recharge status
        await db.transactions.update_one(
            {"transaction_id": transaction_id},
            {
                "$set": {
                    "status": "rejected",
                    "rejection_reason": rejection_reason,
                    "processed_at": datetime.now(timezone.utc),
                    "processed_by": admin.user_id
                }
            }
        )
        
        # Notify user
        await create_notification(
            user_id=user_id,
            title="Tu recarga fue rechazada",
            message=f"No pudimos aprobar tu recarga de {para_mostrar(amount_ves, 'VES')}. Motivo: {rejection_reason}",
            notification_type="recharge_rejected",
            data={"transaction_id": transaction_id, "reason": rejection_reason}
        )
        
        message = "Recarga rechazada."
    
    logger.info(f"VES recharge {transaction_id} {action}d by {admin.user_id}")
    
    return {"message": message}


# ══════════════════════════════════════════════════════════════════════════
# Verificar el pago en bolívares de un envío a Brasil
# ══════════════════════════════════════════════════════════════════════════
#
# El cliente cotizó, transfirió en bolívares y subió el comprobante. Acá
# alguien lo abre y dice si esa plata entró.
#
# POR QUE NO REUSA `process_ves_recharge`
#
#   Aquélla acredita SALDO y trabaja sobre `type: "recharge_ves"`. Esto no
#   acredita nada: hace avanzar una orden que ya existe hacia la cola de
#   despacho. Meterlas en la misma función obligaría a un `if` que decide si
#   mueve plata o no, en el único lugar donde eso no se puede confundir.

class VerificarPagoEnBolivares(BaseModel):
    action: str                          # "approve" o "reject"
    motivo: Optional[str] = None         # obligatorio al rechazar


@router.post("/envios-reais/{transaction_id}/verificar", response_model=EstadoCambiado, response_model_exclude_unset=True)
async def verificar_pago_en_bolivares(
    transaction_id: str,
    body: VerificarPagoEnBolivares,
    admin: User = Depends(get_super_admin),
):
    """Confirma o rechaza el comprobante de un envío pagado en bolívares."""
    from services import pago_al_final
    from services.notifications import create_notification

    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Acción inválida")

    if body.action == "approve":
        orden = await pago_al_final.verificar_el_pago(
            db, transaction_id, admin.user_id)
        await auditoria.registrar(
            db, "envio_brl.verificado", quien=admin,
            objetivo_tipo="transaction", objetivo_id=transaction_id,
            objetivo_desc=f"Envío {orden.get('display_id')}",
            detalle={"amount_ves": orden.get("amount_input"),
                     "amount_brl": orden.get("amount_output"),
                     "banco": orden.get("destination_bank")})
        await create_notification(
            user_id=orden.get("user_id"),
            title="Confirmamos tu pago",
            message="Tu envío ya está en la cola para despacharse.",
            notification_type="withdrawal_pending",
            data={"transaction_id": transaction_id})
        return {"message": "Pago verificado. La orden pasó a la cola.",
                "status": orden.get("status")}

    # RECHAZAR EXIGE UN MOTIVO ESCRITO.
    #
    #   Sin él, el cliente recibe un «no» sin saber qué corregir y termina en
    #   soporte. Y queda en el libro de auditoría: rechazar el comprobante de
    #   alguien que sí pagó es el error caro de esta pantalla.
    motivo = (body.motivo or "").strip()
    if not motivo:
        raise HTTPException(
            status_code=400,
            detail="Escribí por qué no sirve el comprobante. El cliente lo va a "
                   "leer para mandarte el correcto.")

    orden = await pago_al_final.rechazar_el_comprobante(
        db, transaction_id, admin.user_id, motivo)
    await auditoria.registrar(
        db, "envio_brl.rechazado", quien=admin,
        objetivo_tipo="transaction", objetivo_id=transaction_id,
        objetivo_desc=f"Envío {orden.get('display_id')}",
        detalle={"motivo": motivo})
    await create_notification(
        user_id=orden.get("user_id"),
        title="Necesitamos otro comprobante",
        message=motivo,
        notification_type="warning",
        data={"transaction_id": transaction_id})
    return {"message": "Comprobante rechazado.", "status": orden.get("status")}
