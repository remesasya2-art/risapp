"""
Endpoints de administración del libro mayor RIS (solo super_admin).
- POST /admin/ledger/opening   -> crea las líneas de apertura (una sola vez).
- GET  /admin/ledger/reconcile -> compara balance_ris vs suma del ledger y lista descuadres.
- GET  /admin/ledger/entries   -> lista las líneas del ledger de un usuario.
- GET  /admin/ledger/pozo      -> solvencia: RIS que se debe vs reales que hay.
- GET  /admin/ledger/cobros-sin-acreditar -> pagos de Mercado Pago cobrados y
  nunca acreditados (solo mira; no acredita nada).
"""
import logging

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from database import db
from models.user import User
from routes.dependencies import get_super_admin
from services import cobros_sin_acreditar
from services.ledger import sum_ris_balance, create_opening_entries
from services.money import from_db, quantize_money, to_float

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/ledger", tags=["ledger"])

# Tolerancia al comparar saldos. Se mantiene en un centavo porque estas dos
# rutas viejas comparan contra una suma del libro cuyos montos son floats; la
# reconciliación nueva (`/reconciliacion`, en services/contabilidad.py) suma en
# Decimal y por eso puede exigir cero.
EPS = quantize_money("0.01")


@router.post("/opening")
async def run_opening(admin: User = Depends(get_super_admin)):
    """Crea las líneas de saldo de apertura (idempotente: se puede llamar varias
    veces sin duplicar). A partir de aquí el ledger cuadra contra los saldos."""
    result = await create_opening_entries()
    return result


@router.get("/reconcile")
async def reconcile(admin: User = Depends(get_super_admin)):
    """Compara, por usuario, el balance_ris guardado contra la suma del ledger.
    Lista solo los que NO cuadran (diferencia mayor a la tolerancia)."""
    mismatches = []
    checked = 0
    async for u in db.users.find(
        {},
        {"user_id": 1, "email": 1, "full_name": 1, "name": 1,
         "balance_ris": 1, "role": 1},
    ):
        uid = u.get("user_id")
        if not uid:
            continue
        checked += 1
        # `float(u.get("balance_ris") or 0)` reventaba con el saldo en
        # Decimal128 —que es como lo escribe toda la app desde services/saldos—
        # y el `or 0` no salvaba nada porque un Decimal128 es truthy. `from_db`
        # lee las dos formas.
        bal = from_db(u.get("balance_ris"))
        led = await sum_ris_balance(uid, "balance_ris")
        diff = quantize_money(bal - led)
        if abs(diff) > EPS:
            mismatches.append({
                "user_id": uid,
                "email": u.get("email"),
                "name": u.get("full_name") or u.get("name"),
                "role": u.get("role", "user"),
                "balance_ris": to_float(bal),
                "ledger_sum": to_float(led),
                "diff": to_float(diff),
            })
    mismatches.sort(key=lambda x: abs(x["diff"]), reverse=True)
    return {
        "checked": checked,
        "mismatches_count": len(mismatches),
        "ok": len(mismatches) == 0,
        "mismatches": mismatches,
    }


def _para_el_json(valor):
    """Decimal128 → número, en cualquier profundidad del documento. Sólo para
    mostrar: el cálculo sigue en Decimal."""
    from bson.decimal128 import Decimal128
    if isinstance(valor, Decimal128):
        return float(valor.to_decimal())
    if isinstance(valor, dict):
        return {k: _para_el_json(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_para_el_json(v) for v in valor]
    return valor


@router.get("/entries")
async def list_entries(
    user_id: str = Query(...),
    limit: int = Query(100),
    admin: User = Depends(get_super_admin),
):
    """Lista las líneas del ledger de un usuario (más recientes primero) y
    muestra su saldo guardado vs la suma del ledger."""
    rows = []
    cursor = db.ledger.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(min(max(limit, 1), 500))
    async for r in cursor:
        # Las líneas nuevas guardan la plata en Decimal128, que el JSON no
        # sabe escribir: un 500 en esta pantalla, exactamente el que ya pasó
        # dos veces en producción con los saldos. Se convierte en el borde.
        rows.append(_para_el_json(r))
    bal_doc = await db.users.find_one({"user_id": user_id}, {"balance_ris": 1})
    led = await sum_ris_balance(user_id, "balance_ris")
    bal = from_db((bal_doc or {}).get("balance_ris"))
    return {
        "user_id": user_id,
        "balance_ris": to_float(bal),
        "ledger_sum": to_float(led),
        "diff": to_float(quantize_money(bal - led)),
        "count": len(rows),
        "entries": rows,
    }


# ─── El libro contable ────────────────────────────────────────────────────
#
# Lo de arriba es lo que habia: crear la apertura, reconciliar y listar las
# lineas de UN usuario. Lo de abajo es el libro propiamente dicho — diario,
# mayor y balance de comprobacion — que la pantalla nunca tuvo.

from fastapi import HTTPException                                  # noqa: E402
from fastapi.responses import Response, StreamingResponse          # noqa: E402

from services import contabilidad                                  # noqa: E402


def _error(e: Exception):
    if isinstance(e, contabilidad.ContabilidadInvalida):
        return HTTPException(e.http, e.mensaje)
    logger.error(f"contabilidad: falló una consulta del libro: {e}")
    return HTTPException(503, "No se pudo leer el libro. Reintentá en un momento.")


@router.get("/plan-de-cuentas")
async def plan_de_cuentas(admin: User = Depends(get_super_admin)):
    """El plan de cuentas y el mapa de asientos.

    La pantalla NO los tiene escritos: los pide. Así el plan vive en un solo
    lugar, y un `movement_type` nuevo aparece en la pantalla sin tocar el
    frontend.
    """
    return {
        "cuentas": [{"codigo": codigo, **ficha}
                    for codigo, ficha in contabilidad.PLAN_DE_CUENTAS.items()],
        "asientos": [{"movement_type": tipo, "contra": regla["contra"],
                      "glosa": regla["glosa"]}
                     for tipo, regla in sorted(contabilidad.ASIENTOS.items())],
        "cuenta_del_usuario": contabilidad.CUENTA_DEL_USUARIO,
    }


@router.get("/diario")
async def ver_diario(
    desde: str = Query(..., description="AAAA-MM-DD"),
    hasta: str = Query(..., description="AAAA-MM-DD"),
    libro: str = Query(None, description="RIS | USDT | USDC"),
    user_id: str = Query(None),
    movement_type: str = Query(None),
    tz_min: int = Query(0, ge=-840, le=840),
    limite: int = Query(100, ge=1, le=2000),
    saltear: int = Query(0, ge=0),
    admin: User = Depends(get_super_admin),
):
    """El libro diario: cada asiento, cronológico, con sus dos partidas."""
    try:
        return await contabilidad.libro_diario(
            desde=desde, hasta=hasta, libro=libro, user_id=user_id,
            movement_type=movement_type, tz_min=tz_min,
            limite=limite, saltear=saltear)
    except Exception as e:
        raise _error(e)


@router.get("/mayor")
async def ver_mayor(
    desde: str = Query(..., description="AAAA-MM-DD"),
    hasta: str = Query(..., description="AAAA-MM-DD"),
    libro: str = Query(None),
    tz_min: int = Query(0, ge=-840, le=840),
    admin: User = Depends(get_super_admin),
):
    """El libro mayor: los movimientos agrupados por cuenta, con saldo."""
    try:
        return await contabilidad.libro_mayor(
            desde=desde, hasta=hasta, libro=libro, tz_min=tz_min)
    except Exception as e:
        raise _error(e)


@router.get("/balance")
async def ver_balance(
    desde: str = Query(..., description="AAAA-MM-DD"),
    hasta: str = Query(..., description="AAAA-MM-DD"),
    libro: str = Query(None),
    tz_min: int = Query(0, ge=-840, le=840),
    formato: str = Query("json", pattern="^(json|csv|xlsx)$"),
    admin: User = Depends(get_super_admin),
):
    """El balance de comprobación: sumas y saldos por cuenta.

    **Cuadra por construcción** —las partidas se derivan de cada línea— así que
    no es un control de que los datos estén bien: es la estructura. Los controles
    son `/reconciliacion` y `/integridad`.
    """
    try:
        balance = await contabilidad.libro_mayor(
            desde=desde, hasta=hasta, libro=libro, tz_min=tz_min)
        resumen = await contabilidad.balance_de_comprobacion(
            desde=desde, hasta=hasta, libro=libro, tz_min=tz_min)
    except Exception as e:
        raise _error(e)

    if formato == "json":
        return resumen

    from services import contabilidad_export
    quien = getattr(admin, "email", "") or getattr(admin, "user_id", "")
    nombre = f"risapp_balance_{desde}_a_{hasta}.{formato}"
    if formato == "csv":
        return StreamingResponse(
            iter([contabilidad_export.balance_a_csv(resumen, balance, quien)]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
    return Response(
        content=contabilidad_export.balance_a_xlsx(resumen, balance, quien),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/reconciliacion")
async def ver_reconciliacion(
    libro: str = Query("RIS"),
    limite: int = Query(200, ge=1, le=1000),
    admin: User = Depends(get_super_admin),
):
    """Compara el saldo guardado de cada usuario contra la suma de su libro.

    Reemplaza a `/reconcile`, que hacía una agregación POR USUARIO —con diez mil
    usuarios, diez mil viajes en una sola petición— y sumaba floats con una
    tolerancia de un centavo por cuenta. Acá son dos lecturas, la suma es en
    Decimal y la tolerancia es cero.
    """
    try:
        return await contabilidad.reconciliacion(libro=libro, limite=limite)
    except Exception as e:
        raise _error(e)


@router.get("/pozo")
async def ver_conciliacion_del_pozo(admin: User = Depends(get_super_admin)):
    """¿Por cada RIS que un usuario tiene, hay un real nuestro?

    El control de solvencia de la cuenta ómnibus: lo que la empresa DEBE (la
    suma de los saldos de los usuarios) contra lo que la empresa TIENE (los
    reales en los bancos, incluidas las cuentas de las pasarelas).

    Es distinto de `/reconciliacion`, y las dos hacen falta: aquella compara el
    saldo de cada usuario contra SU libro —si no cuadra, la app perdió una
    línea—; ésta compara la suma de todos los saldos contra el dinero real —si
    no cuadra, falta plata—. Un libro perfecto sobre un pozo vacío cuadra igual.
    """
    try:
        return await contabilidad.conciliacion_pozo()
    except Exception as e:
        raise _error(e)


@router.get("/integridad")
async def ver_integridad(
    libro: str = Query(None),
    admin: User = Depends(get_super_admin),
):
    """Los defectos que impiden defender el libro ante un auditor.

    No corrige nada: un libro que se auto-corrige es un libro que nadie puede
    auditar. Devuelve también lo que este libro **todavía no puede probar**.
    """
    try:
        return await contabilidad.integridad(libro=libro)
    except Exception as e:
        raise _error(e)


@router.get("/cofre")
async def estado_del_cofre(admin: User = Depends(get_super_admin)):
    """El estado del cofre de los documentos, para la pantalla de seguridad.

    POR QUE ESTA RUTA EXISTE

        `services/cofre.py` promete que la huella de la llave «se puede mirar en
        el panel». Sin esta ruta esa frase era mentira, y el procedimiento de
        `docs/la-llave-del-cofre.md` —cotejar la llave que está corriendo contra
        la que está anotada en papel— no se podía completar sin entrar al
        servidor por consola.

        Esa comprobación es la que convierte «respaldá la llave» en algo que se
        puede verificar de un vistazo, así que tiene que estar donde se mira.

    QUE DEVUELVE Y QUE NO

        La HUELLA, que son ocho caracteres derivados de la llave y no permiten
        reconstruirla. Nunca la llave. Es la misma distinción que hace el módulo:
        la huella es pública a propósito.
    """
    from services import cofre
    return await cofre.revisar(db)


# ── La llave del cofre, desde el panel ─────────────────────────────────────
#
# POR QUE ESTAS DOS RUTAS EXISTEN
#
#   Sortear la llave y cotejar la que se anotó eran dos órdenes de un guión que
#   se corría en una terminal. Eso dejaba los dos pasos que de verdad protegen
#   los documentos —sortear una llave fuerte, y comprobar que la copia de
#   respaldo está bien— fuera del alcance de la persona que tiene que darlos, que
#   no escribe código.
#
#   El proyecto tiene una regla escrita sobre esto: configurar nunca puede
#   requerir tocar código.
#
# POR QUE ESTAS DOS PUEDEN IR DETRAS DE UN BOTON, Y CIFRAR LOS VIEJOS NO
#
#   Ninguna de las dos escribe nada. Sortear una llave y no guardarla en ningún
#   lado es texto en una pantalla: hasta que alguien la copie a la variable de
#   entorno, no pasó nada. Cifrar los documentos históricos, en cambio, reescribe
#   datos de personas reales, y eso sigue siendo un guión que se corre a mano
#   después de leer qué hace. Un botón invita a apretarlo.


class LlaveParaCotejar(BaseModel):
    """El texto que la persona anotó.

    El largo máximo no es una regla sobre la llave: es para no aceptar que
    alguien pegue un archivo entero en la casilla.
    """

    llave: str = Field(default="", max_length=2000)


@router.post("/cofre/llave-nueva")
async def llave_nueva_del_cofre(request: Request,
                                admin: User = Depends(get_super_admin)):
    """Sortea una llave nueva y su huella. No la guarda en ningún lado.

    QUE QUEDA EN LOS REGISTROS

        Que el super administrador generó una llave, y su HUELLA. Nunca la
        llave. La huella es pública a propósito —sirve para reconocer cuál es
        cuál— y tenerla acá permite, meses después, saber si la llave que está
        corriendo salió de este botón o apareció de otro lado.
    """
    from services import auditoria, cofre

    nueva = cofre.llave_nueva()
    await auditoria.registrar(
        db, "cofre.llave_generada", quien=admin, request=request,
        detalle={"huella": nueva["huella"]})
    return nueva


@router.post("/cofre/cotejar")
async def cotejar_la_llave_del_cofre(cuerpo: LlaveParaCotejar,
                                     admin: User = Depends(get_super_admin)):
    """¿La llave que anoté sirve, es la que corre, y abre los documentos?

    NO SE AUDITA, Y ES A PROPOSITO

        Esta ruta no escribe nada y se usa varias veces seguidas: la persona
        prueba la copia del gestor de contraseñas, después la del papel, se
        equivoca y prueba otra vez. Un registro por intento llenaría la auditoría
        de ruido sin dejar un hecho que a alguien le sirva.

        Y sobre todo: la llave escrita NO se guarda en ningún lado, ni cuando es
        la correcta ni cuando no. Lo único que sale de acá es la respuesta.
    """
    from services import cofre
    return await cofre.cotejar(db, cuerpo.llave)


# ── Cobros de Mercado Pago que nadie acreditó ──────────────────────────────
#
# POR QUE ESTA RUTA VIVE EN EL LIBRO MAYOR Y NO EN LAS RUTAS DE PAGOS
#
#     Porque la pregunta que contesta no es «¿cómo salió este pago?» sino «¿hay
#     plata cobrada que el libro no registra?». Quien decide es el libro, y
#     `services/cobros_sin_acreditar.py` explica por qué. Las pantallas de
#     control del dinero ya leen de `/admin/ledger/*` y la puerta es la misma
#     —`get_super_admin`—, así que el control nuevo entra donde se lo va a
#     buscar en vez de abrir un vecindario propio.

@router.get("/cobros-sin-acreditar")
async def ver_cobros_sin_acreditar(
    dias: int = Query(cobros_sin_acreditar.DIAS_POR_DEFECTO),
    tope: int = Query(cobros_sin_acreditar.TOPE_POR_DEFECTO),
    admin: User = Depends(get_super_admin),
):
    """¿Alguien pagó y la app no le acreditó nada? SOLO MIRA.

    No acredita, no corrige y no toca un saldo. Mover plata es una decisión de
    una persona y va por otro camino, con su registro en la auditoría: una
    consulta que además arregla es una consulta que nadie se anima a correr.

    Los dos límites —`dias` y `tope`— los acota el servicio, no esta ruta:
    dejarlos acá los ponía a un `?dias=99999` de distancia.
    """
    try:
        return await cobros_sin_acreditar.revisar(db, dias=dias, tope=tope)
    except Exception as e:
        logger.error("cobros sin acreditar: la revisión falló: %s", e)
        raise HTTPException(
            503, "No se pudo revisar los cobros. Reintentá en un momento.")
