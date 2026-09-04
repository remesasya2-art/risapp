"""
Los permisos del personal: qué puede tocar cada quien, y dónde se decide.

EL PROBLEMA QUE RESUELVE

    Recursos Humanos deja marcar permisos por persona, y esos permisos casi no
    se verificaban. Medido sobre la aplicación armada: 209 rutas de
    administración exigían ROL, y las comprobaciones de permiso existían sólo
    dentro de `admin_routes.py`. En todo el resto —KYC, envíos, soporte,
    listas negras, la lista completa de usuarios— alcanzaba con ser `admin` o
    `agent` para entrar a todo.

    Peor: de las veinte comprobaciones que había, NUEVE estaban en rutas
    duplicadas que FastAPI nunca atendía, porque `routes/` se registra antes.
    Quien leía `admin_routes.py` concluía que el KYC estaba protegido por
    `kyc.approve`. No lo estaba.

    O sea que marcar permisos en la pantalla de RRHH era, en la práctica,
    decorativo: cualquier colaborador podía hacer todo lo que podía hacer
    cualquier otro.

COMO SE ARREGLA, Y POR QUE ASI

    No se agrega una comprobación adentro de cada ruta. Sesenta y siete
    comprobaciones sueltas son sesenta y siete lugares donde olvidarse de una,
    y la que falta no avisa: simplemente deja pasar.

    Se hace en las dos dependencias por las que YA pasan todas: `get_admin_user`
    y `get_crm_user`. Ellas miran esta tabla y deciden. Una ruta nueva hereda
    la comprobación por el solo hecho de usar el guard de siempre.

QUE PASA CON UNA RUTA QUE NO ESTA EN LA TABLA

    Se niega, y queda un ERROR en el log con el método y el camino. Es la
    decisión importante de este módulo: fallar cerrado.

    Un mapa incompleto que deja pasar es exactamente el agujero que estamos
    tapando, y no avisa nunca. Un mapa incompleto que frena se nota el primer
    día, se arregla agregando una línea acá, y mientras tanto el super
    administrador sigue pudiendo hacer el trabajo —a él la tabla no lo
    alcanza—. Además hay un test que recorre la aplicación armada y falla si
    alguna ruta quedó sin mapear, así que esto no debería llegar a producción.
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

SUPER_ADMIN = "super_admin"


# ─── El catálogo ──────────────────────────────────────────────────────────
#
# Lo que se ve en la pantalla de RRHH al marcar permisos. La regla al agregar
# uno: que se pueda explicar en una línea a quien lo va a otorgar. "Ver" y
# "hacer" van separados, porque leer los datos de un cliente y decidir sobre
# su plata no son la misma confianza.

# Se sacaron seis que estaban en el catálogo viejo y no gobernaban ninguna
# ruta: `dashboard.view`, `users.edit`, `admins.create`, `admins.edit`,
# `withdrawals.view` y `withdrawals.process`. El panel principal, el alta de
# administradores y los retiros pasaron a ser cosa del super administrador o
# del puente con clave de API, así que marcarlos no habilitaba nada. Un
# permiso que se puede otorgar y no hace nada es peor que no ofrecerlo: quien
# lo marca cree que repartió trabajo. Hay un test que impide que vuelvan.
CATALOGO = {
    "users.view":            "Ver usuarios y su historial",
    "users.blacklist":       "Bloquear y desbloquear usuarios",

    "saldos.ajustar":        "Ajustar saldos a mano (MUEVE DINERO)",

    "kyc.view":              "Ver verificaciones de identidad",
    "kyc.approve":           "Aprobar, rechazar y calificar KYC",

    "recharges.view":        "Ver recargas",
    "recharges.approve":     "Aprobar recargas (MUEVE DINERO)",

    "transactions.view":     "Ver transacciones",
    "transactions.export":   "Exportar transacciones",

    "support.view":          "Ver chats y pedidos de soporte",
    "support.respond":       "Responder y tomar soporte",
    "support.close":         "Cerrar chats de soporte",

    "envios.view":           "Ver envíos y transportistas",
    "envios.operar":         "Operar envíos (despachar, entregar, pesar)",
    "envios.dinero":         "Cargar fletes y costos de viaje (MUEVE DINERO)",

    "settings.view":         "Ver configuración y tasas",
    "settings.edit":         "Editar configuración y tasas",

    "admins.view":           "Ver administradores",
}


# ─── La tabla ─────────────────────────────────────────────────────────────
#
# (método, camino) -> permiso. El camino es la PLANTILLA que declara la ruta,
# con las llaves adentro, no el camino concreto del pedido.

MAPA = {
    # ── Panel y usuarios ──────────────────────────────────────────────────
    ("GET",    "/api/admin/users"):                          "users.view",
    ("GET",    "/api/admin/users/{user_id}"):                "users.view",
    ("GET",    "/api/admin/users/{user_id}/complete"):       "users.view",
    # Ajustar un saldo a mano es la acción más peligrosa del panel: crea o
    # borra dinero sin una operación detrás. Va con permiso propio y no con
    # `users.edit`, que suena a cambiar un teléfono.
    ("PUT",    "/api/admin/users/{user_id}/balance"):        "saldos.ajustar",
    ("POST",   "/api/admin/ban"):                            "users.blacklist",
    ("GET",    "/api/admin/blacklist"):                      "users.blacklist",
    ("POST",   "/api/admin/blacklist"):                      "users.blacklist",
    ("DELETE", "/api/admin/blacklist/{blacklist_id}"):       "users.blacklist",

    # ── KYC ───────────────────────────────────────────────────────────────
    ("GET",    "/api/admin/kyc/list"):                       "kyc.view",
    ("GET",    "/api/admin/kyc/document-types"):             "kyc.view",
    ("GET",    "/api/admin/kyc/rejection-reasons"):          "kyc.view",
    ("GET",    "/api/admin/kyc/export.csv"):                 "kyc.view",
    ("GET",    "/api/admin/kyc/{verification_id}"):          "kyc.view",
    ("GET",    "/api/admin/kyc/{verification_id}/history"):  "kyc.view",
    ("POST",   "/api/admin/kyc/{verification_id}/approve"):  "kyc.approve",
    ("POST",   "/api/admin/kyc/{verification_id}/reject"):   "kyc.approve",
    ("POST",   "/api/admin/kyc/{verification_id}/re-review"): "kyc.approve",
    ("POST",   "/api/admin/kyc/{verification_id}/risk"):     "kyc.approve",
    ("PATCH",  "/api/admin/kyc/{verification_id}/note"):     "kyc.approve",

    # ── Recargas ──────────────────────────────────────────────────────────
    ("GET",    "/api/admin/recharges/pending"):              "recharges.view",
    ("GET",    "/api/admin/recharges/{transaction_id}/proof"): "recharges.view",
    ("POST",   "/api/admin/recharges/approve"):              "recharges.approve",

    # ── Transacciones ─────────────────────────────────────────────────────
    ("GET",    "/api/admin/transactions"):                   "transactions.view",
    ("GET",    "/api/admin/transactions/{transaction_id}"):  "transactions.view",
    ("GET",    "/api/admin/transactions/export"):            "transactions.export",
    ("GET",    "/api/admin/payment-records"):                "transactions.view",
    ("GET",    "/api/admin/payment-records/{record_id}"):    "transactions.view",

    # ── Soporte ───────────────────────────────────────────────────────────
    ("GET",    "/api/admin/support/chats"):                  "support.view",
    ("GET",    "/api/admin/support/chat/{user_id}"):         "support.view",
    ("GET",    "/api/admin/support-requests"):               "support.view",
    ("GET",    "/api/admin/quick-replies"):                  "support.view",
    ("POST",   "/api/admin/support/respond"):                "support.respond",
    ("POST",   "/api/admin/support/claim"):                  "support.respond",
    ("POST",   "/api/admin/support/release"):                "support.respond",
    ("POST",   "/api/admin/quick-replies"):                  "support.respond",
    ("DELETE", "/api/admin/quick-replies/{qr_id}"):          "support.respond",
    ("POST",   "/api/admin/support-requests/{request_id}/claim"):    "support.respond",
    ("POST",   "/api/admin/support-requests/{request_id}/release"):  "support.respond",
    ("POST",   "/api/admin/support-requests/{request_id}/reply"):    "support.respond",
    ("POST",   "/api/admin/support-requests/{request_id}/priority"): "support.respond",
    ("POST",   "/api/admin/support/close"):                  "support.close",
    ("POST",   "/api/admin/support-requests/{request_id}/resolve"):  "support.close",

    # ── Envíos ────────────────────────────────────────────────────────────
    ("GET",    "/api/admin/envios/envios/cola"):             "envios.view",
    ("GET",    "/api/admin/envios/envios/historial"):        "envios.view",
    ("GET",    "/api/admin/envios/envios/viajes/{lote_id}"): "envios.view",
    ("GET",    "/api/admin/envios/envios/{envio_id}/ticket"): "envios.view",
    ("GET",    "/api/admin/envios/envios/{envio_id}/foto/{asset_id}"): "envios.view",
    ("GET",    "/api/admin/envios/retiro"):                  "envios.view",
    ("GET",    "/api/admin/envios/transportistas"):          "envios.view",
    ("GET",    "/api/admin/envios/transportistas/{transportista_id}/agencias"): "envios.view",
    ("POST",   "/api/admin/envios/envios/retiro-lote"):      "envios.operar",
    ("POST",   "/api/admin/envios/envios/{envio_id}/despachar"):   "envios.operar",
    ("POST",   "/api/admin/envios/envios/{envio_id}/disponible"):  "envios.operar",
    ("POST",   "/api/admin/envios/envios/{envio_id}/entregar"):    "envios.operar",
    ("POST",   "/api/admin/envios/envios/{envio_id}/retiro-final"): "envios.operar",
    ("POST",   "/api/admin/envios/envios/{envio_id}/repesar"):     "envios.operar",
    ("POST",   "/api/admin/envios/envios/{envio_id}/desviar/{hacia}"): "envios.operar",
    ("POST",   "/api/admin/envios/envios/{envio_id}/comprobante/verificar"): "envios.operar",
    # Estas tres tocan plata: el flete que se le cobra al cliente y el costo
    # del viaje que se le paga al transportista.
    ("PUT",    "/api/admin/envios/envios/{envio_id}/flete"):          "envios.dinero",
    ("POST",   "/api/admin/envios/envios/{envio_id}/flete/acreditar"): "envios.dinero",
    ("PUT",    "/api/admin/envios/envios/viajes/{lote_id}/costo"):    "envios.dinero",

    # ── Configuración ─────────────────────────────────────────────────────
    ("GET",    "/api/admin/bcv-rates"):                      "settings.view",
    ("GET",    "/api/admin/bcv-rates/history"):              "settings.view",
    ("POST",   "/api/admin/bcv-rates/refresh"):              "settings.edit",

    # ── Administradores ───────────────────────────────────────────────────
    ("GET",    "/api/admin/permissions-list"):               "admins.view",
}


class SinPermiso(Exception):
    """Le falta el permiso. Trae cuál, para que el mensaje lo diga."""
    def __init__(self, permiso: str):
        self.permiso = permiso
        etiqueta = CATALOGO.get(permiso, permiso)
        super().__init__(
            f"Te falta el permiso «{etiqueta}». Pedíselo al administrador.")


class RutaSinMapear(Exception):
    """Una ruta de administración que nadie declaró. Se niega."""
    def __init__(self, metodo: str, camino: str):
        self.metodo, self.camino = metodo, camino
        super().__init__(
            "Esta función todavía no tiene permiso asignado. Avisale al "
            "administrador.")


def _leer(usuario, clave, defecto=None):
    if isinstance(usuario, dict):
        return usuario.get(clave, defecto)
    return getattr(usuario, clave, defecto)


def tiene(usuario, permiso: str) -> bool:
    """¿Este usuario tiene este permiso? El super administrador, siempre."""
    if usuario is None:
        return False
    if _leer(usuario, "role", "user") == SUPER_ADMIN:
        return True
    return permiso in (_leer(usuario, "permissions", None) or [])


def permiso_de(metodo: str, camino: str) -> Optional[str]:
    """El permiso que pide (método, camino), o None si no está declarado."""
    return MAPA.get((metodo.upper(), camino))


def _camino_de(request) -> Optional[str]:
    """La PLANTILLA de la ruta que atendió el pedido.

    `request.scope["route"].path` la trae ya resuelta por el router. Si por
    alguna razón no estuviera, se cae al camino concreto y se lo compara
    contra las plantillas de la tabla: preferimos gastar una comparación de
    más antes que quedarnos sin saber qué ruta es y dejar pasar.
    """
    ruta = request.scope.get("route") if hasattr(request, "scope") else None
    plantilla = getattr(ruta, "path", None)
    if plantilla:
        return plantilla
    concreto = (getattr(request, "scope", {}) or {}).get("path")
    if not concreto:
        return None
    metodo = ((getattr(request, "scope", {}) or {}).get("method") or "").upper()
    for (m, p) in MAPA:
        if m == metodo and _patron(p).match(concreto):
            return p
    return concreto


_cache_patrones: dict = {}


def _patron(plantilla: str):
    pat = _cache_patrones.get(plantilla)
    if pat is None:
        escapado = re.escape(plantilla).replace(r"\{", "{").replace(r"\}", "}")
        pat = _cache_patrones[plantilla] = re.compile(
            "^" + re.sub(r"\{[^}]+\}", "[^/]+", escapado) + "$")
    return pat


def exigir(usuario, request) -> None:
    """Frena el pedido si a este usuario le falta el permiso de esta ruta.

    Al super administrador no lo toca: los permisos existen para repartir
    trabajo, y él es de quien se reparte.
    """
    if _leer(usuario, "role", "user") == SUPER_ADMIN:
        return

    metodo = ((getattr(request, "scope", {}) or {}).get("method") or "").upper()
    camino = _camino_de(request)
    permiso = permiso_de(metodo, camino) if camino else None

    if permiso is None:
        # Fallar cerrado. Un mapa incompleto que deja pasar es el agujero que
        # este módulo tapa, y no avisa nunca; uno que frena se nota enseguida.
        logger.error(
            "RUTA DE ADMIN SIN PERMISO DECLARADO: %s %s. Se negó el acceso a "
            "%s. Agregala a MAPA en services/permisos.py.",
            metodo, camino, _leer(usuario, "user_id", "?"))
        raise RutaSinMapear(metodo, camino or "?")

    if not tiene(usuario, permiso):
        raise SinPermiso(permiso)
