"""
Basic routes - Health check, rates, etc.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from database import db
from models.fuera_del_panel import ColaDePagos
from models.user import User
from routes.dependencies import get_current_user, get_super_admin

logger = logging.getLogger(__name__)
router = APIRouter(tags=["basic"])

from models.reglas_publicas import LaTasa, RaizDeLaApi

@router.get("/", response_model=RaizDeLaApi)
async def root():
    """Root endpoint"""
    return {"message": "RISApp API", "version": "2.0.0"}

class PingDeVida(BaseModel):
    status: str
    base: Optional[bool] = None    # lo último que vio el reloj de salud; None hasta la primera vuelta


@router.get("/health", response_model=PingDeVida)
async def health_check():
    """El ping de vida. Sigue contestando 200 aunque la base esté caída
    (reiniciar el proceso no la levanta), pero lo dice en `base`, con lo
    último que vio el reloj de salud, sin consultar nada en cada llamada.
    Ver services/salud_de_la_app.py."""
    from services import salud_de_la_app
    return {"status": "healthy", "base": salud_de_la_app.ultimo_ok_de_la_base()}


class Comprobacion(BaseModel):
    nombre: str
    ok: bool
    detalle: str
    grave: bool


class SaludDeLaApp(BaseModel):
    ok: bool
    revisado_en: str
    comprobaciones: list[Comprobacion]
    vigilancia: dict


@router.get("/admin/salud", response_model=SaludDeLaApp)
async def salud_de_la_aplicacion(_: User = Depends(get_super_admin)):
    """La revisión completa, ahora, con el detalle y los últimos cambios de
    estado. Sólo el super administrador: el detalle dice cómo está armada
    la casa."""
    from services import salud_de_la_app
    r = await salud_de_la_app.vigilar(db, forzar=True)
    return {**r, "vigilancia": salud_de_la_app.estado()}

@router.get("/rate", response_model=LaTasa, response_model_exclude_unset=True)
async def get_current_rate():
    """La tasa vigente: la que cargó el super administrador, tal cual."""
    rate = await db.rates.find_one(sort=[("updated_at", -1)])
    base = {
        "ris_to_ves": (rate or {}).get("ris_to_ves", 110.0),
        "ves_to_ris_rate": (rate or {}).get("ves_to_ris_rate", 140.0),
        "brl_to_ris": (rate or {}).get("brl_to_ris", 1.0),
        "usd_to_ves": (rate or {}).get("usd_to_ves", 50.0),
    }
    # SIN TASA NOCTURNA
    #
    #   Acá se le aplicaba un ajuste fuera del horario laboral (la «tasa
    #   automática»): de noche, los domingos y los feriados, se restaba un delta
    #   a BRL→VES y se sumaba otro a VES→BRL. Se eliminó por decisión del dueño
    #   del proyecto, con su tarjeta del panel y sus dos rutas. La tasa es la
    #   que se carga a mano, a cualquier hora.
    #
    #   Si vuelve, tiene que volver en los cinco lugares a la vez: esta ruta y
    #   los cuatro de `routes/transactions.py` que convierten plata. Una tasa
    #   distinta entre lo que muestra la pantalla y lo que cobra la orden es
    #   exactamente lo que `test_sin_tasa_nocturna.py` impide.
    effective = dict(base)
    if rate:
        effective["updated_at"] = rate.get("updated_at")
    # Tasas de envío con saldo cripto (USDT/USDC → VES): un valor fijo que
    # configura el admin aparte.
    effective["usdtris_to_ves"] = (rate or {}).get("usdtris_to_ves")
    effective["usdcris_to_ves"] = (rate or {}).get("usdcris_to_ves")

    # Expose BCV USD/EUR rates publicly (read-only)
    #
    # VIAJA CON SU ANTIGÜEDAD, y no es adorno. Estas pantallas dicen «Referencia
    # BCV» al lado de un número; mientras el raspador estuvo roto ese número era
    # de semanas atrás y la pantalla lo mostraba igual, sin decir nada. Un dato
    # viejo presentado como de hoy miente por omisión.
    bcv = await db.bcv_rates.find_one({}, {"_id": 0, "rates": 1, "value_date": 1, "fetched_at": 1}, sort=[("fetched_at", -1)])
    if bcv and bcv.get("rates"):
        effective["bcv_usd_ves"] = bcv["rates"].get("dolar")
        effective["bcv_eur_ves"] = bcv["rates"].get("euro")
        effective["bcv_value_date"] = bcv.get("value_date")
        try:
            from services.bcv_scraper import vigencia
            estado = await vigencia(db)
            effective["bcv_vencida"] = estado["vencida"]
            effective["bcv_edad_horas"] = estado["edad_horas"]
        except Exception as e:
            # Esta ruta la consulta cada visitante y cada diez segundos la
            # pantalla de envíos. Que no se pueda calcular la antigüedad no
            # puede tumbarla.
            logger.warning(f"No se pudo calcular la antigüedad del BCV: {e}")

    # El historial de la tasa ya no se escribe desde acá. Esta ruta anotaba los
    # saltos del ajuste nocturno, que ya no existe; los cambios a mano los anota
    # `POST /admin/rates` en el momento en que se hacen, con quién los hizo.
    return effective

# `GET /download-build` vivía acá y se sacó.
#
# Era PUBLICA y SIN AUTENTICAR, y servía `/app/backend/dist.zip` a cualquiera
# que la pidiera. Hoy ese archivo no se genera —el build del frontend va a
# `frontend/dist`, no ahí— así que en la práctica devolvía «no disponible».
#
# O sea que era una puerta abierta cuya inocencia dependía de que un archivo NO
# existiera. El día que alguien deje un zip en esa ruta, se lo lleva medio
# mundo. No la usaba el frontend ni ningún proceso.

@router.get("/withdrawal/queue-stats", response_model=ColaDePagos, response_model_exclude_unset=True)
async def get_withdrawal_queue_stats(admin=Depends(get_super_admin)):
    """Resumen de la cola de pagos, para la cabecera del panel.

    DOS COSAS QUE ESTABAN MAL

    1. NO PEDIA SESION. Cualquiera que supiera la URL veía cuánta plata había
       esperando pago y cuántas órdenes había en cola. Es información operativa
       del negocio y ahora exige super admin, como el resto del panel. Tiene un
       solo consumidor —la cabecera del panel de administración— así que no
       rompe nada más.

    2. EL TOTAL MEZCLABA MONEDAS. Sumaba `amount_output` de todos los retiros
       pendientes en una cifra rotulada «total VES necesarios», pero un retiro
       puede salir en VES o en BRL. Un envío en reales sumaba sus reales al
       total de bolívares, y quien mira ese número para saber cuánto poner en
       las cuentas venezolanas provisionaba mal sin poder notarlo.

       `total_ves_pending` ahora es SOLO lo que sale en VES. El detalle por
       moneda va en `por_moneda`, que es lo que la pantalla muestra.
    """
    from services import retiros
    c = await retiros.contadores(db)
    ves = next((m["total"] for m in c["por_moneda"] if m["moneda"] == "VES"), 0.0)
    return {
        "total_pending": c["pendientes"],
        # Sin cola de WhatsApp, todo lo pendiente esta esperando a un operador.
        "waiting_in_queue": c["pendientes"],
        "total_ves_pending": ves,
        # La pantalla leía este campo y la ruta nunca lo devolvió: era
        # `undefined` y se dibujaba como «0,00». Un número que siempre miente
        # es peor que no mostrarlo.
        "total_ris_pending": next(
            (m["total"] for m in c["por_origen"] if m["moneda"] == "RIS"), 0.0),
        "por_moneda": c["por_moneda"],
        "por_origen": c["por_origen"],
    }
