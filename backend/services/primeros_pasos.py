"""
services/primeros_pasos.py — Qué le falta a una cuenta nueva para andar.

PARA QUE

    El registro deja a la persona logueada y la manda al panel: saldo en
    cero, historial vacío, y nada que diga qué hacer. Los empujones a
    verificarse estaban repartidos —Perfil, Recarga, BTC, encomiendas, y la
    ventana que salta cuando se agota el cupo—, o sea que aparecían recién
    cuando algo se trababa. Esto los junta en una tarjeta que se ve al
    llegar y desaparece sola cuando ya no hace falta.

POR QUE EL ESTADO LO CALCULA EL SERVIDOR Y NO LA PANTALLA

    «Ya recargó» no está en un solo lugar: una recarga puede haber entrado
    por PIX, por tarjeta, por cripto, desde Venezuela, o como un ajuste a
    mano del panel, y cada una vive en su colección. La pantalla sólo ve el
    historial de `transactions`, así que decidiría mal para tres de las
    cinco. Y lo que se calcula acá se prueba acá, contra la base, en vez
    de deducirlo mirando JSX.

LO QUE DEVUELVE, Y NADA MAS

    Cuatro estados y un «completo». Ni saldos, ni documentos, ni el motivo
    de un rechazo: la tarjeta no los muestra, así que no viajan.
"""
from services.money import from_db

# Lo que dice la base -> lo que dice la tarjeta. Lo que no esté acá se
# trata como «sin enviar»: una cuenta con un estado raro no puede quedarse
# sin el paso más importante.
ESTADOS_DE_VERIFICACION = {
    "unverified": "sin_enviar",
    "pending": "en_revision",
    "verified": "aprobada",
    "rejected": "rechazada",
}

# Un envío que fue rechazado, cancelado o vencido no cuenta como hecho: la
# persona no llegó a enviar nada, y el paso tiene que seguir invitándola.
_ENVIO_QUE_NO_FUE = ("rejected", "cancelled", "canceled", "failed", "expired")

LO_QUE_DEVUELVE = ("verificacion", "recarga", "envio", "huella", "completo")


async def _ya_recargo(db, user_id: str, cuenta: dict) -> bool:
    # Saldo en positivo: entró plata por donde sea, incluido un ajuste a
    # mano. Es la señal más simple y la primera que se mira.
    if from_db(cuenta.get("balance_ris")) > 0:
        return True
    # Y cada puerta por la que entra plata, en su colección, TERMINADA: un
    # PIX vencido o una tarjeta rechazada no son una recarga.
    puertas = (
        ("transactions", {"type": {"$in": ["recharge", "recharge_ves"]}, "status": "completed"}),
        ("gestor_pix_payments", {"status": {"$in": ["paid", "approved"]}}),
        ("card_payments", {"status": "approved"}),
        ("crypto_deposits", {"credited": True}),
    )
    for coleccion, filtro in puertas:
        if await db[coleccion].find_one({"user_id": user_id, **filtro}, {"_id": 1}):
            return True
    return False


async def _ya_envio(db, user_id: str) -> bool:
    puertas = (
        ("transactions", {"type": "withdrawal", "status": {"$nin": list(_ENVIO_QUE_NO_FUE)}}),
        ("btc_remesas", {"estado": {"$nin": ["cancelado"]}}),
        ("envios", {"confirmado_at": {"$exists": True, "$ne": None}}),
    )
    for coleccion, filtro in puertas:
        if await db[coleccion].find_one({"user_id": user_id, **filtro}, {"_id": 1}):
            return True
    return False


async def estado(db, user_id: str) -> dict:
    cuenta = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "verification_status": 1, "balance_ris": 1, "webauthn_credentials": 1},
    ) or {}
    verificacion = ESTADOS_DE_VERIFICACION.get(cuenta.get("verification_status"), "sin_enviar")
    recarga = await _ya_recargo(db, user_id, cuenta)
    envio = await _ya_envio(db, user_id)
    huella = bool(cuenta.get("webauthn_credentials"))
    # La huella NO entra en «completo»: es opcional y depende del
    # dispositivo. Una tarjeta que nunca se va porque el teléfono no tiene
    # lector es una tarjeta que la persona aprende a ignorar.
    completo = verificacion == "aprobada" and recarga and envio
    return {
        "verificacion": verificacion,
        "recarga": recarga,
        "envio": envio,
        "huella": huella,
        "completo": completo,
    }
