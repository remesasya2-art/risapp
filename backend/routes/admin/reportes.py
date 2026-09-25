"""
routes/admin/reportes.py — Los reportes del panel y la hoja de pagos de Mercado Pago.

Parte de lo que era `routes/admin.py`. Por qué está dividido, y en qué orden
se registran las partes: `routes/admin/__init__.py`.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional

from database import db
from services import las_fotos
from services import quien_es
from services.money import from_db, to_float
from models.user import User
from models.panel_tablero import (FuentesDeReporte, MermaDeNowpayments, ReporteGenerado)
from pydantic import BaseModel
from routes.dependencies import (get_admin_user, get_super_admin)
from routes.admin._comun import logger

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/reportes/merma-nowpayments", response_model=MermaDeNowpayments, response_model_exclude_unset=True)
async def reporte_merma_nowpayments(
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD, inclusivo"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD, inclusivo"),
    admin: User = Depends(get_super_admin),
):
    """Solo lectura: cuanto VES se prometio de mas frente a lo que NOWPayments
    acredito realmente, ya descontada su comision interna de procesamiento.

    `merma_ves` se calcula en el webhook con el `rate` congelado al crear la
    orden, asi que mide la comision de NOWPayments y NO el movimiento de la tasa.
    Este endpoint no modifica nada: es para ver el tamano real del problema antes
    de decidir que hacer con el.

    El rango filtra por `created_at` de la orden (que es como se listan las
    ordenes en el resto del panel). Ambas fechas son opcionales: sin rango,
    devuelve todo el historico.
    """
    from datetime import timedelta as _td

    def _parse(d):
        return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    rango = {}
    try:
        if date_from:
            rango["$gte"] = _parse(date_from).replace(hour=0, minute=0, second=0, microsecond=0)
        if date_to:
            rango["$lt"] = _parse(date_to).replace(hour=0, minute=0, second=0, microsecond=0) + _td(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida (use YYYY-MM-DD)")
    if "$gte" in rango and "$lt" in rango and rango["$lt"] <= rango["$gte"]:
        raise HTTPException(status_code=400, detail="El rango de fechas es inválido (desde debe ser ≤ hasta)")

    base = {"funded_from": "payment"}
    if rango:
        base["created_at"] = rango

    # Este diccionario estaba escrito a mano acá, y copiado igual en otras dos
    # pantallas. Las tres copias pedían el usuario ENTERO para leerle el
    # nombre. Ahora es uno solo, con lista de lo permitido.
    #
    # Sigue siendo una consulta por cliente DISTINTO y no por fila, que es lo
    # que la caché ya lograba: acá se recorren varios cursores distintos y no
    # hay una lista sola que se pueda precargar de una.
    quien = quien_es.Directorio(db)

    ordenes = []
    total_merma = 0.0
    total_merma_positiva = 0.0
    total_merma_negativa = 0.0
    total_prometido = 0.0

    async for tx in db.transactions.find(
        {**base, "merma_ves": {"$ne": None}},
        las_fotos.solo("transaction_id", "display_id", "user_id", "status",
                       "amount_input", "amount_output", "currency_input", "rate",
                       "merma_ves", "merma_calculada_at", "paid_at", "created_at",
                       "actually_paid", "outcome_amount", "outcome_currency",
                       "paid_ratio", "pay_amount", "pay_currency", "network",
                       "topup_actually_paid", "topup_outcome_amount", "underpaid"),
    ).sort("created_at", 1):
        u = await quien.de(tx.get("user_id"))
        merma = to_float(from_db(tx.get("merma_ves"))) or 0.0
        prometido = to_float(from_db(tx.get("amount_output"))) or 0.0

        total_merma += merma
        total_prometido += prometido
        if merma >= 0:
            total_merma_positiva += merma
        else:
            total_merma_negativa += merma

        ordenes.append({
            "orden_id": tx.get("transaction_id"),
            "display_id": tx.get("display_id"),
            "created_at": tx.get("created_at"),
            "paid_at": tx.get("paid_at"),
            "merma_calculada_at": tx.get("merma_calculada_at"),
            "status": tx.get("status"),
            "user_email": u.get("email", ""),
            "user_name": u.get("full_name") or u.get("name") or "—",
            "moneda": str(tx.get("currency_input") or "").upper(),
            "red": tx.get("network") or tx.get("pay_currency"),
            "rate": to_float(from_db(tx.get("rate"), places=6), places=6),
            "amount_input": to_float(from_db(tx.get("amount_input"))),
            "amount_output": prometido,
            "pay_amount": tx.get("pay_amount"),
            "actually_paid": tx.get("actually_paid"),
            "outcome_amount": tx.get("outcome_amount"),
            "outcome_currency": tx.get("outcome_currency"),
            "topup_actually_paid": tx.get("topup_actually_paid"),
            "topup_outcome_amount": tx.get("topup_outcome_amount"),
            "paid_ratio": tx.get("paid_ratio"),
            "underpaid": bool(tx.get("underpaid")),
            "merma_ves": merma,
        })

    # Ordenes que si recibieron un IPN de pago pero cuyo IPN no trajo
    # outcome_amount: no se puede medir la merma y quedan fuera del total.
    # Se informa el conteo para que el numero de arriba no se lea como completo.
    sin_outcome = await db.transactions.count_documents(
        {**base, "merma_ves": None, "actually_paid": {"$ne": None}}
    )

    return {
        "desde": date_from,
        "hasta": date_to,
        "total": len(ordenes),
        "sin_outcome": sin_outcome,
        "totales": {
            "merma_ves": round(total_merma, 2),
            "merma_ves_a_favor_del_negocio": round(total_merma_negativa, 2),
            "merma_ves_en_contra": round(total_merma_positiva, 2),
            "ves_prometido": round(total_prometido, 2),
            "merma_pct_sobre_prometido": (
                round(total_merma / total_prometido * 100, 4) if total_prometido else None
            ),
        },
        "ordenes": ordenes,
    }


@router.get("/reportes/fuentes", response_model=FuentesDeReporte, response_model_exclude_unset=True)
async def reportes_fuentes(admin: User = Depends(get_super_admin)):
    """Los flujos de dinero sobre los que se puede pedir un reporte.

    La pantalla NO tiene la lista escrita: la pide. Así, agregar una fuente en
    `services/reportes.py` la hace aparecer en el panel sin tocar el frontend —
    y no puede pasar que el panel ofrezca un flujo que el motor no conoce.
    """
    from services import reportes
    return {"fuentes": [{"clave": k, "etiqueta": v["etiqueta"]}
                        for k, v in reportes.FUENTES.items()]}


@router.get("/reportes", response_model=ReporteGenerado, response_model_exclude_unset=True)
async def generar_reporte(
    desde: str = Query(..., description="AAAA-MM-DD"),
    hasta: str = Query(..., description="AAAA-MM-DD"),
    flujos: Optional[str] = Query(None, description="claves separadas por coma"),
    buscar: Optional[str] = Query(None, max_length=120),
    operador: Optional[str] = Query(None, max_length=120),
    monto_min: Optional[str] = Query(None, max_length=20),
    monto_max: Optional[str] = Query(None, max_length=20),
    tz_min: int = Query(0, ge=-840, le=840, description="minutos respecto de UTC"),
    limite: int = Query(100, ge=1, le=1000),
    saltear: int = Query(0, ge=0),
    formato: str = Query("json", pattern="^(json|csv|xlsx)$"),
    admin: User = Depends(get_super_admin),
):
    """El reporte de operaciones, ajustable.

    `json` devuelve los totales del periodo entero más una página de filas;
    `csv` y `xlsx` devuelven el archivo con TODAS las filas y el mismo bloque de
    totales, para que sumar la columna dé con el encabezado.

    Los totales se calculan siempre sobre el periodo completo, nunca sobre la
    página: un total que solo suma lo que se ve en pantalla es la forma más
    silenciosa de reportar de menos.
    """
    from fastapi.responses import Response, StreamingResponse
    from services import reportes, reportes_export

    criterios = dict(
        desde=desde, hasta=hasta,
        flujos=[f.strip() for f in flujos.split(",") if f.strip()] if flujos else None,
        buscar=buscar, operador=operador,
        monto_min=monto_min, monto_max=monto_max, tz_min=tz_min,
    )
    try:
        if formato == "json":
            return await reportes.generar(limite=limite, saltear=saltear, **criterios)
        reporte = await reportes.reporte_completo(**criterios)
    except reportes.ReporteInvalido as e:
        raise HTTPException(e.http, e.mensaje)
    except Exception as e:
        logger.error(f"reportes: no se pudo generar: {e}")
        raise HTTPException(503, "No se pudo generar el reporte. Reintentá en un momento.")

    quien = getattr(admin, "email", "") or getattr(admin, "user_id", "")
    nombre = reportes_export.nombre_de_archivo(reporte, formato)
    if formato == "csv":
        return StreamingResponse(
            iter([reportes_export.a_csv(reporte, quien)]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
    return Response(
        content=reportes_export.a_xlsx(reporte, quien),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/reportes/procesados")
async def reporte_procesados(
    period: str = Query("day", pattern="^(day|month|year|range)$"),
    date: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    formato: str = Query("json", pattern="^(json|csv)$"),
    admin: User = Depends(get_super_admin),
):
    """Reporte de TODO lo procesado (4 flujos) por día / mes / año o rango.
    Para period="range" usa date_from y date_to (ambos YYYY-MM-DD, inclusivos).
    Devuelve JSON (vista previa + totales) o CSV (descarga para Excel o para la
    app de contabilidad externa). La información completa se genera aquí.
    """
    from datetime import timedelta as _td
    def _parse(d):
        return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    try:
        if period == "range":
            if not date_from or not date_to:
                raise HTTPException(status_code=400, detail="Indica la fecha desde y hasta (YYYY-MM-DD)")
            start = _parse(date_from).replace(hour=0, minute=0, second=0, microsecond=0)
            end = _parse(date_to).replace(hour=0, minute=0, second=0, microsecond=0) + _td(days=1)
            if end <= start:
                raise HTTPException(status_code=400, detail="El rango de fechas es inválido (desde debe ser ≤ hasta)")
        else:
            if not date:
                raise HTTPException(status_code=400, detail="Indica la fecha (YYYY-MM-DD)")
            base = _parse(date)
            if period == "day":
                start = base.replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + _td(days=1)
            elif period == "month":
                start = base.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
            else:  # year
                start = base.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                end = start.replace(year=start.year + 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida (use YYYY-MM-DD)")

    # Este diccionario estaba escrito a mano acá, y copiado igual en otras dos
    # pantallas. Las tres copias pedían el usuario ENTERO para leerle el
    # nombre. Ahora es uno solo, con lista de lo permitido.
    #
    # Sigue siendo una consulta por cliente DISTINTO y no por fila, que es lo
    # que la caché ya lograba: acá se recorren varios cursores distintos y no
    # hay una lista sola que se pueda precargar de una.
    quien = quien_es.Directorio(db)

    rows = []

    # LA COLUMNA «comprobante» DICE «sí» O «no», Y ESO COSTABA MEGABYTES.
    #
    # Para escribir esas dos letras, este reporte se traía el documento entero
    # de cada fila —con la lista de fotos del comprobante en base64 adentro— y
    # después preguntaba si estaba vacía. Ahora la pregunta la contesta la
    # base y lo que vuelve es un booleano por fila. Es el problema que
    # `services/reportes.py` ya documenta en su encabezado, punto 1.
    filtro_retiros = {"type": "withdrawal", "status": "completed", "completed_at": {"$gte": start, "$lt": end}}
    filtro_recargas = {"type": "recharge_ves", "status": "approved", "processed_at": {"$gte": start, "$lt": end}}
    con_foto = await las_fotos.cuales_tienen_foto(db, filtro_retiros)
    con_foto |= await las_fotos.cuales_tienen_foto(db, filtro_recargas)

    # Retiros completados (RIS→VES y RIS→Reais)
    async for tx in db.transactions.find(
        filtro_retiros,
        las_fotos.solo("transaction_id", "display_id", "user_id",
                       "amount_input", "amount_output", "currency_output",
                       "beneficiary_data", "rate", "processed_by", "completed_at"),
    ):
        u = await quien.de(tx.get("user_id"))
        b = tx.get("beneficiary_data", {}) or {}
        es_brl = str(tx.get("currency_output") or "VES").upper() in ("BRL", "REAIS", "REAL")
        rows.append({
            "fecha_procesado": tx.get("completed_at"),
            "flujo": "RIS → Reais" if es_brl else "RIS → VES",
            "referencia": tx.get("display_id") or tx.get("transaction_id"),
            "usuario": u.get("full_name") or u.get("name") or "",
            "usuario_email": u.get("email", ""),
            "beneficiario": b.get("full_name") or b.get("name", ""),
            "documento": b.get("cpf") or b.get("cedula") or b.get("id_document", ""),
            "pix": b.get("pix_key", ""),
            "banco": "" if es_brl else (b.get("bank") or b.get("bank_code", "")),
            "monto_origen": tx.get("amount_input", 0),
            "unidad_origen": "RIS",
            "monto_destino": tx.get("amount_output", 0),
            "unidad_destino": "BRL" if es_brl else "VES",
            "tasa": tx.get("rate", ""),
            "procesado_por": tx.get("processed_by", ""),
            "comprobante": "sí" if tx.get("transaction_id") in con_foto else "no",
        })

    # Recargas VES aprobadas (VES→RIS)
    async for tx in db.transactions.find(
        filtro_recargas,
        las_fotos.solo("transaction_id", "display_id", "user_id",
                       "amount_ves", "amount_ris", "rate_used",
                       "processed_by", "processed_at"),
    ):
        u = await quien.de(tx.get("user_id"))
        rows.append({
            "fecha_procesado": tx.get("processed_at"),
            "flujo": "VES → RIS",
            "referencia": tx.get("display_id") or tx.get("transaction_id"),
            "usuario": u.get("full_name") or u.get("name") or "",
            "usuario_email": u.get("email", ""),
            "beneficiario": "",
            "documento": "",
            "pix": "",
            "banco": "",
            "monto_origen": tx.get("amount_ves", 0),
            "unidad_origen": "VES",
            "monto_destino": tx.get("amount_ris", 0),
            "unidad_destino": "RIS",
            "tasa": tx.get("rate_used", ""),
            "procesado_por": tx.get("processed_by", ""),
            "comprobante": "sí" if tx.get("transaction_id") in con_foto else "no",
        })

    # Remesas BTC enviadas (BTC→VES)
    async for r in db.btc_remesas.find(
        {"estado": "enviado", "enviado_en": {"$gte": start, "$lt": end}}, {"_id": 0}
    ):
        u = await quien.de(r.get("user_id"))
        b = r.get("beneficiario_data", {}) or {}
        rows.append({
            "fecha_procesado": r.get("enviado_en"),
            "flujo": "BTC → VES",
            "referencia": r.get("display_id") or r.get("remesa_id"),
            "usuario": u.get("full_name") or u.get("name") or "",
            "usuario_email": u.get("email", ""),
            "beneficiario": b.get("full_name") or b.get("name", ""),
            "documento": b.get("cedula", ""),
            "pix": "",
            "banco": b.get("bank", ""),
            "monto_origen": r.get("usd_cliente", 0),
            "unidad_origen": "USD",
            "monto_destino": r.get("ves_recibe", 0),
            "unidad_destino": "VES",
            "tasa": r.get("tasa_ves", ""),
            "procesado_por": r.get("operador_id", ""),
            "comprobante": "sí" if r.get("comprobante_pago") else "no",
        })

    rows.sort(key=lambda x: str(x.get("fecha_procesado") or ""))

    def fmtfecha(d):
        if not d:
            return ""
        try:
            return d.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(d)

    if formato == "csv":
        import csv as _csv
        import io as _io
        from fastapi.responses import StreamingResponse as _SR
        buf = _io.StringIO()
        buf.write("\ufeff")  # BOM para que Excel respete los acentos
        w = _csv.writer(buf)
        w.writerow(["Fecha", "Flujo", "Referencia", "Usuario", "Email",
                    "Beneficiario", "Documento", "Llave PIX", "Banco",
                    "Monto origen", "Unidad", "Monto destino", "Unidad",
                    "Tasa", "Procesado por", "Comprobante"])
        for r in rows:
            w.writerow([
                fmtfecha(r["fecha_procesado"]), r["flujo"], r["referencia"], r["usuario"], r["usuario_email"],
                r["beneficiario"], r["documento"], r["pix"], r["banco"],
                r["monto_origen"], r["unidad_origen"], r["monto_destino"], r["unidad_destino"],
                r["tasa"], r["procesado_por"], r["comprobante"],
            ])
        buf.seek(0)
        etiqueta = f"{date_from}_a_{date_to}" if period == "range" else (date or "")
        filename = f"reporte_{period}_{etiqueta}.csv"
        return _SR(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                   headers={"Content-Disposition": f"attachment; filename={filename}"})

    # JSON: vista previa + totales por flujo
    totales = {}
    for r in rows:
        totales[r["flujo"]] = totales.get(r["flujo"], 0) + 1
        r["fecha_procesado"] = fmtfecha(r["fecha_procesado"])
    return {
        "period": period,
        "date": date,
        "date_from": date_from,
        "date_to": date_to,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total": len(rows),
        "totales_por_flujo": totales,
        "rows": rows,
    }


# ══════════════════════════════════════════════════════════════════════════
# La hoja de pagos de Mercado Pago
# ══════════════════════════════════════════════════════════════════════════
#
# Qué nos avisó Mercado Pago, cuándo, y en qué terminó. Existe porque el 20 de
# septiembre de 2026 hubo que averiguar si Mercado Pago había llamado por un
# pago, y no había dónde mirar: la única huella era el registro del servidor.
#
# El por qué de cada cosa está en `services/hoja_de_mercadopago.py`.

class UnaFilaDeLaHoja(BaseModel):
    """Lo que se muestra de cada aviso, y nada más.

    Por lista de lo permitido: el documento puede crecer —Mercado Pago agrega
    campos— y lo nuevo no puede salir solo a una pantalla.
    """
    anotacion_id: str
    mp_payment_id: Optional[str] = None
    referencia: Optional[str] = None
    transaction_id: Optional[str] = None
    tipo_de_evento: Optional[str] = None
    llego_a_las: Optional[datetime] = None
    termino_a_las: Optional[datetime] = None
    como_termino: Optional[str] = None
    motivo: Optional[str] = None
    monto: Optional[float] = None
    estado_en_mp: Optional[str] = None


class LaHojaDeMercadoPago(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    filas: List[UnaFilaDeLaHoja]


@router.get("/hoja-mercadopago", response_model=LaHojaDeMercadoPago)
async def la_hoja_de_mercadopago(
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    buscar: Optional[str] = None,
    como_termino: Optional[str] = None,
    pagina: int = 1,
    por_pagina: int = 50,
    admin: User = Depends(get_admin_user),
):
    """Los avisos de Mercado Pago, filtrados por fecha y por identificador.

    LA VE UN ADMINISTRADOR, NO SOLO EL SUPER ADMINISTRADOR.

        Quien atiende a un cliente que dice «pagué y no me aparece» tiene que
        poder mirarlo en el momento. Obligarlo a pedirle a otra persona que
        abra la hoja convierte una consulta de treinta segundos en una espera
        de horas, y es exactamente la demora que este lote existe para sacar.

        No hay dinero que mover acá: es una hoja de sólo lectura, y lo que
        muestra no incluye datos del pagador.
    """
    from services import hoja_de_mercadopago
    return await hoja_de_mercadopago.buscar(
        db, desde=desde, hasta=hasta, texto=buscar,
        como_termino=como_termino, pagina=pagina, por_pagina=por_pagina)
