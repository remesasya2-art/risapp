"""
services/pendientes.py — Cuánto trabajo espera en cada sección del panel.

POR QUE EXISTE

    El panel tiene veintitrés secciones y sólo el Resumen decía algo: cuatro
    números. Para saber si había un KYC sin revisar, una orden sin procesar o
    un caso de soporte sin tomar, había que ENTRAR A CADA PESTAÑA a mirar.

    Quien entra al panel no sabe por dónde empezar, y lo que no se mira no se
    hace. Un indicador en la pestaña convierte veintitrés visitas en una.

Y POR QUE NO SE CUENTA EN LA PANTALLA

    Los cuatro números del Resumen se calculaban descargando LISTAS ENTERAS y
    midiendo su largo en el navegador. Dos cosas salían mal:

        «Usuarios totales» mentía pasados los 1000, porque la ruta manda como
        mucho mil usuarios completos —correo, documento, teléfono— y la
        pantalla contaba cuántos habían llegado.

        «Recargas pendientes» mentía pasadas las 100, por lo mismo.

    Un número que miente en silencio es peor que ninguno: nadie lo audita.
    Acá se cuenta con `count_documents`, que cuenta en la base y devuelve un
    número, sin traerse una sola fila.

CADA NUMERO SE MUESTRA SOLO A QUIEN PUEDE ABRIR ESA SECCION

    El criterio es el mismo que usa la puerta de la sección, y por el mismo
    motivo: un contador es información. «Hay 14 retiros pendientes» le dice a
    quien no puede verlos cuánto dinero está esperando salir.

    Donde hay permiso declarado se pregunta por el permiso —igual que
    `services/notifications.avisar_al_personal`—; donde la sección la guarda
    `get_super_admin` directamente, se pide ser super administrador.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

# Quién puede ver una sección que no tiene permiso propio.
SOLO_SUPER = object()


# Las que ya están reservadas en un lote de pagos salen de la cuenta, igual que
# salen de la lista: si el contador las siguiera contando, la pestaña diría
# diez y la pantalla mostraría cuatro. Un número que discrepa de lo que hay
# abajo es peor que ninguno — es el motivo por el que este módulo existe.
_FUERA_DE_UN_LOTE = {"estado_admin": {"$ne": "en_lote"}}


def _retiros():
    return {"type": "withdrawal", "status": "pending",
            "hidden_from_admin": {"$ne": True}, **_FUERA_DE_UN_LOTE}


def _recargas_ves():
    return {"type": "recharge_ves", "status": "pending",
            "hidden_from_admin": {"$ne": True}, **_FUERA_DE_UN_LOTE}


async def _contar(coleccion, filtro) -> int:
    from database import db
    return await db[coleccion].count_documents(filtro)


async def _ordenes_por_procesar() -> int:
    """La bandeja unificada junta tres flujos, así que el número también.

    Es la misma consulta que arma `GET /admin/ordenes/pendientes`. Sí, las
    órdenes de Bitcoin se cuentan acá Y en su propia pestaña: es el mismo
    trabajo visto desde dos lados, y así lo muestra el panel.
    """
    partes = await asyncio.gather(
        _contar("transactions", _retiros()),
        _contar("btc_remesas", {"estado": "pagado", **_FUERA_DE_UN_LOTE}),
        _contar("transactions", _recargas_ves()),
    )
    return sum(partes)


async def _casos_de_soporte() -> int:
    from services import soporte
    return await _contar("soporte_casos", {"estado": {"$in": list(soporte.ABIERTOS)}})


# (clave de la pestaña, quién la puede ver, cómo se cuenta).
#
# La clave es la MISMA que usa la pantalla para la pestaña: sin eso hay que
# mantener una traducción aparte, y la traducción se desactualiza.
# ─── Qué cuenta como «hay trabajo» en la cola de envíos ──────────────────
#
# EL DEFECTO QUE ESTO CIERRA
#
#     Antes se contaba una sola parada: `disponible_retiro` («En el
#     mostrador»). La cola tiene SIETE, así que la pestaña decía 1 mientras el
#     operador entraba, caía en «Por verificar», veía 0, y pensaba que el
#     número estaba pegado. Y al revés, que es peor: con cinco paquetes
#     esperando verificación y tres para repesar, la pestaña decía 0.
#
# POR QUE ESTAS CINCO Y NO LAS SIETE
#
#     Un número en una pestaña contesta una pregunta: «¿tengo que hacer algo
#     acá?». Así que se cuentan las paradas donde el trabajo es NUESTRO:
#
#       · en_transito_origen  — hay que leer el peso y emitir el cobro
#       · disponible_retiro   — hay que ir a retirar el lote
#       · recibido_pacaraima  — hay que repesar
#       · repesado            — hay que despachar
#       · retenido            — hay que resolverlo
#
#     Quedan afuera las dos donde se espera a otro, porque un número que no
#     baja haciendo trabajo deja de mirarse:
#
#       · pago_pendiente  — espera que el CLIENTE pague. Es la palanca de
#         cobro del negocio y se ve en su propia parada, pero no es tarea
#         nuestra.
#       · en_transito_int — está en la ruta a Santa Elena. Cuando llegue pasa
#         a entregarse; hasta entonces no hay nada que hacer.
#
#     Si algún día conviene otro criterio, es esta tupla y nada más.
PARADAS_QUE_ESPERAN = (
    "en_transito_origen",
    "disponible_retiro",
    "recibido_pacaraima",
    "repesado",
    "retenido",
)

SECCIONES = (
    ("ordenes",     SOLO_SUPER,     _ordenes_por_procesar),
    ("diferencias", SOLO_SUPER,     lambda: _contar("transactions", {
        "status": "underpaid_review", "hidden_from_admin": {"$ne": True}})),
    ("withdrawals", SOLO_SUPER,     lambda: _contar("transactions", _retiros())),
    ("recharges",   SOLO_SUPER,     lambda: _contar("transactions", _recargas_ves())),
    ("btc",         SOLO_SUPER,     lambda: _contar("btc_remesas", {
        "estado": {"$in": ["pagado", "revision_manual"]}})),
    ("credits",     SOLO_SUPER,     lambda: _contar("crypto_deposits",
                                                    {"status": "pending"})),
    ("kyc",         "kyc.view",     lambda: _contar("verifications",
                                                    {"status": "pending"})),
    ("support",     "support.view", _casos_de_soporte),
    ("operacion",   "envios.view",  lambda: _contar("envios",
                                                    {"estado": {"$in": PARADAS_QUE_ESPERAN}})),
)


def puede_ver(usuario, quien) -> bool:
    """¿Este usuario puede abrir la sección cuyo guardián es `quien`?"""
    from services import permisos

    rol = getattr(usuario, "role", None) or "user"
    if quien is SOLO_SUPER:
        return rol == permisos.SUPER_ADMIN
    return permisos.tiene(usuario, quien)


async def contar_para(usuario) -> dict:
    """Los pendientes de cada sección que ESTE usuario puede abrir.

    NO LEVANTA. Es un adorno del panel: si una consulta falla, esa sección
    queda sin número y el panel abre igual. Que no se pueda contar los KYC no
    puede dejar a nadie sin poder trabajar.
    """
    mios = [(clave, contar) for clave, quien, contar in SECCIONES
            if puede_ver(usuario, quien)]

    async def _uno(clave, contar):
        try:
            return clave, await contar()
        except Exception as e:
            logger.warning("no se pudo contar los pendientes de %s: %s", clave, e)
            return clave, None

    resultados = await asyncio.gather(*[_uno(c, f) for c, f in mios])
    return {clave: n for clave, n in resultados if n is not None}


async def total_de_usuarios() -> int:
    """Las cuentas ACTIVAS. El número que la tarjeta del Resumen muestra.

    El Resumen los contaba midiendo el largo de la lista que trae
    `GET /admin/users`, que corta en 1000. Con 1200 usuarios seguía diciendo
    1000, y nadie tenía cómo darse cuenta.

    Y después contaba `is_deleted != True`, o sea que metía adentro a los
    vetados y a los suspendidos: gente que no puede entrar, contada como si
    pudiera. Mientras tanto la tabla de al lado escondía a los vetados, así
    que la tarjeta y la tabla nunca coincidían y no había forma de saber por
    qué. Ahora las dos salen del mismo lugar.
    """
    from database import db
    from services import estado_de_la_cuenta
    return (await estado_de_la_cuenta.resumen(db))[estado_de_la_cuenta.ACTIVA]
