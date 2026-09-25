"""
models/panel_libro.py — Lo que el panel ve del libro de cuentas: el diario, el
mayor, el balance, los tres controles (reconciliación, pozo, integridad), el
cofre de los documentos, los cobros sin acreditar, y las rutas viejas de
reconciliación. Más las dos rutas de contabilidad que el panel usa: la lista
de bancos y el borrado de la contabilidad.

CASI TODO SE ARMA CAMPO POR CAMPO

    Los servicios del libro (`services/contabilidad.py`,
    `services/cobros_sin_acreditar.py`, `services/cofre.py`) arman cada
    respuesta a mano, con la plata en texto para no perder un centavo en el
    camino. Los contratos fijan esa forma: el día que alguien agregue «un dato
    más», no sale solo. Un test compara cada ruta con su servicio llamado a
    mano, con datos que llenan cada lista.

LA LINEA DEL LIBRO SALE CASI ENTERA, A PROPOSITO

    `/entries` muestra las líneas de un usuario tal como se escribieron. Es el
    registro que se mira cuando algo no cuadra, lo lee sólo el super
    administrador, y cortarle partes lo haría inútil para eso. El contrato fija
    los campos que escribe `services/ledger.record_ris_entry` —la única función
    que escribe líneas, incluida la apertura y el cierre—, y deja libres los
    cuatro que son objetos (`reference`, `actor`, `counterparty`, `metadata`):
    hay líneas viejas escritas con otra forma, y un contrato estricto ahí
    convertiría una línea vieja en un error 500 en la pantalla de control.

LA LLAVE NUEVA DEL COFRE SI SALE

    `/cofre/llave-nueva` devuelve la llave que acaba de sortear: es para lo que
    existe, y no la guarda en ningún lado (ver `routes/ledger_admin.py`). Es la
    única respuesta de este archivo con un secreto adentro, y lo es a propósito.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar


def _simple(nombre, campos, **extra):
    return create_model(nombre, **{c: (Escalar, None) for c in campos}, **extra)


# ── El plan de cuentas ────────────────────────────────────────────────────

CuentaContable = _simple("CuentaContable", ("codigo", "nombre", "tipo"))
AsientoDelPlan = _simple("AsientoDelPlan", ("movement_type", "contra", "glosa"))


class PlanDeCuentas(BaseModel):
    cuentas: List[CuentaContable] = []
    asientos: List[AsientoDelPlan] = []
    cuenta_del_usuario: Dict[str, Escalar] = {}


# ── El diario, el mayor y el balance ──────────────────────────────────────

AsientoDelDiario = _simple("AsientoDelDiario", (
    "numero", "entry_id", "fecha", "libro", "glosa", "movement_type", "monto", "moneda", "clasificado",
    "usuario", "user_id", "referencia", "actor", "nota"),
    debe=(Optional[CuentaContable], None),
    haber=(Optional[CuentaContable], None))


class LibroDiario(BaseModel):
    desde: Escalar = None
    hasta: Escalar = None
    tz_min: Escalar = None
    asientos_totales: Escalar = None
    suma_debe: Escalar = None
    suma_haber: Escalar = None
    sin_clasificar: Escalar = None
    truncado: Escalar = None
    hay_mas: Escalar = None
    asientos: List[AsientoDelDiario] = []


MovimientoDelMayor = _simple("MovimientoDelMayor", (
    "fecha", "glosa", "referencia", "usuario", "debe", "haber", "saldo"))

_CUENTA_CON_SALDO = ("codigo", "nombre", "tipo", "naturaleza", "suma_debe", "suma_haber", "saldo")

CuentaDelMayor = _simple("CuentaDelMayor", (*_CUENTA_CON_SALDO, "hay_mas_movimientos"),
                         movimientos=(List[MovimientoDelMayor], []))
CuentaDelBalance = _simple("CuentaDelBalance", _CUENTA_CON_SALDO)


class LibroMayor(BaseModel):
    desde: Escalar = None
    hasta: Escalar = None
    tz_min: Escalar = None
    truncado: Escalar = None
    cuentas: List[CuentaDelMayor] = []


class BalanceDeComprobacion(BaseModel):
    desde: Escalar = None
    hasta: Escalar = None
    tz_min: Escalar = None
    truncado: Escalar = None
    cuentas: List[CuentaDelBalance] = []
    total_debe: Escalar = None
    total_haber: Escalar = None
    cuadra: Escalar = None
    por_grupo: Dict[str, Escalar] = {}


# ── Control 1: la reconciliación ──────────────────────────────────────────

DescuadreDeUnUsuario = _simple("DescuadreDeUnUsuario", (
    "user_id", "email", "nombre", "cuenta", "cuenta_contable", "saldo_guardado", "suma_del_libro",
    "diferencia"))
LineasSinUsuario = _simple("LineasSinUsuario", ("user_id", "cuenta", "suma_del_libro"))


class Reconciliacion(BaseModel):
    libro: Escalar = None
    usuarios_revisados: Escalar = None
    lineas_leidas: Escalar = None
    truncado: Escalar = None
    cuadra: Escalar = None
    descuadres_totales: Escalar = None
    descuadres: List[DescuadreDeUnUsuario] = []
    hay_mas_descuadres: Escalar = None
    lineas_sin_usuario: List[LineasSinUsuario] = []


# ── Control 2: la integridad ──────────────────────────────────────────────

HallazgoDelLibro = _simple("HallazgoDelLibro", ("clave", "titulo", "explicacion", "gravedad", "cuantas"),
                           ejemplos=(List[Escalar], []))


class IntegridadDelLibro(BaseModel):
    libro: Escalar = None
    lineas_revisadas: Escalar = None
    truncado: Escalar = None
    sano: Escalar = None
    hallazgos: List[HallazgoDelLibro] = []
    limitaciones: List[Escalar] = []


# ── Control 3: el pozo ────────────────────────────────────────────────────

PasivoDelPozo = _simple("PasivoDelPozo", ("total", "usuarios_revisados", "usuarios_con_saldo", "truncado"),
                        por_cuenta=(Dict[str, Escalar], {}))
CuentaQueRespalda = _simple("CuentaQueRespalda", ("bank_id", "nombre", "moneda", "saldo", "es_pasarela", "oculta"))
ActivoDelPozo = _simple("ActivoDelPozo", ("total", "cuentas_ocultas"),
                        cuentas=(List[CuentaQueRespalda], []))
CajaDeTrabajo = _simple("CajaDeTrabajo", ("total", "cuentas"))
BonoEnElPozo = _simple("BonoEnElPozo", ("liberado_y_en_el_pasivo", "bloqueado_y_fuera_del_pasivo"))


class ConciliacionDelPozo(BaseModel):
    moneda: Escalar = None
    pasivo: Optional[PasivoDelPozo] = None
    activo: Optional[ActivoDelPozo] = None
    cubre: Escalar = None
    diferencia: Escalar = None
    capital_de_trabajo: Dict[str, CajaDeTrabajo] = {}
    bono_de_bienvenida: Optional[BonoEnElPozo] = None
    no_incluido: List[Escalar] = []


# ── El cofre de los documentos ────────────────────────────────────────────

EstadoDelCofre = _simple("EstadoDelCofre", (
    "modo", "huella", "hay_llave", "hay_llave_anterior", "ok", "motivo", "detalle"))
LlaveNuevaDelCofre = _simple("LlaveNuevaDelCofre", ("llave", "huella"))
CotejoDeLaLlave = _simple("CotejoDeLaLlave", ("sirve", "huella", "es_la_que_corre", "abre_los_documentos",
                                               "detalle"))

# ── Los cobros de Mercado Pago sin acreditar ──────────────────────────────

CobroSinAcreditar = _simple("CobroSinAcreditar", (
    "medio", "pago", "pago_en_mercadopago", "cuenta", "cliente", "estado_en_la_app", "cuando",
    "cuando_lo_aprobo_mercadopago", "monto_en_mercadopago", "monto_en_la_app"))


class CobrosSinAcreditar(BaseModel):
    desde: Escalar = None
    hasta: Escalar = None
    dias: Escalar = None
    tope: Escalar = None
    candidatos: Escalar = None
    mirados: Escalar = None
    sin_mirar: Escalar = None
    sin_respuesta: Escalar = None
    pudo_preguntar: Escalar = None
    cuantos: Escalar = None
    total_brl: Escalar = None
    cobros: List[CobroSinAcreditar] = []
    cuantos_descuadres: Escalar = None
    total_descuadres_brl: Escalar = None
    descuadres: List[CobroSinAcreditar] = []


# ── Las rutas viejas: apertura, reconciliación por usuario y sus líneas ───

AperturaDelLibro = _simple("AperturaDelLibro", ("revisados", "aperturas_creadas", "error"))

DescuadreViejo = _simple("DescuadreViejo", (
    "user_id", "email", "name", "role", "balance_ris", "ledger_sum", "diff"))


class ReconciliacionVieja(BaseModel):
    checked: Escalar = None
    mismatches_count: Escalar = None
    ok: Escalar = None
    mismatches: List[DescuadreViejo] = []


# Los campos que escribe `services/ledger.record_ris_entry` (y el libro
# cripto, que escribe un subconjunto). Los cuatro objetos, libres: ver arriba.
LineaDelLibro = _simple("LineaDelLibro", (
    "entry_id", "created_at", "book", "user_id", "user_email", "user_name", "user_role",
    "movement_type", "direction", "amount", "signed_amount", "currency", "account",
    "balance_before", "balance_after", "transaction_id", "display_id",
    "rate", "rate_kind", "amount_output", "currency_output", "notes"),
    **{c: (Optional[Any], None) for c in ("reference", "actor", "counterparty", "metadata")})


class LineasDeUnUsuario(BaseModel):
    user_id: Escalar = None
    balance_ris: Escalar = None
    ledger_sum: Escalar = None
    diff: Escalar = None
    count: Escalar = None
    entries: List[LineaDelLibro] = []


# ── Contabilidad: la lista de bancos y el borrado ─────────────────────────

# Sin `created_by`: el identificador de quien cargó el banco. Retiros y
# Recargas en bolívares leen el código, el nombre y la moneda.
BancoDeLaContabilidad = _simple("BancoDeLaContabilidad", ("bank_id", "name", "currency", "balance", "created_at"))
BancosDeLaContabilidad = List[BancoDeLaContabilidad]

ContabilidadBorrada = _simple("ContabilidadBorrada", ("success", "message", "total_deleted", "hidden_transactions"),
                              deleted=(Dict[str, Escalar], {}))


# ── El borrado total, lo que se esconde y lo que queda anotado ────────────
#
# Van al lado del borrado de la contabilidad porque son la misma familia: el
# botón que borra (`WipeButton.jsx`), el que devuelve lo escondido
# (`RestoreButton.jsx`), y el registro donde queda asentado quién apretó cada
# uno. Todas se arman campo por campo en `routes/admin.py`; los contratos fijan
# esos campos.

CierreDelLibro = _simple("CierreDelLibro", ("revisados", "cierres_creados", "error"),
                         por_cuenta=(Dict[str, Escalar], {}))

BorradoTotal = _simple("BorradoTotal", (
    "success", "message", "total_deleted", "users_balance_reset", "libro_conservado"),
    deleted=(Dict[str, Escalar], {}),
    cierre_del_libro=(Optional[CierreDelLibro], None))

ColeccionABorrar = _simple("ColeccionABorrar", ("coleccion", "documentos"))
ElLibroEnElBorrado = _simple("ElLibroEnElBorrado", ("lineas", "se_borra", "que_pasa"))


class VistaPreviaDelBorrado(BaseModel):
    es_una_simulacion: Escalar = None
    se_borrarian: List[ColeccionABorrar] = []
    documentos_a_borrar: Escalar = None
    saldos_que_se_ponen_en_cero: Dict[str, Escalar] = {}
    usuarios_con_saldo: Escalar = None
    libro: Optional[ElLibroEnElBorrado] = None
    no_se_toca: List[Escalar] = []


OperacionEscondida = _simple("OperacionEscondida", (
    "transaction_id", "display_id", "type", "status", "amount_input", "amount_output", "currency", "route",
    "user_id", "user_name", "user_email", "created_at"))


class OperacionesEscondidas(BaseModel):
    transactions: List[OperacionEscondida] = []
    count: Escalar = None


OperacionesRestauradas = _simple("OperacionesRestauradas", ("success", "message", "restored"))

# Lo que escribe `routes/admin._record_audit`, el único que escribe en
# `audit_log`. `extra` queda libre: cada acción anota lo suyo.
AccionSensible = _simple("AccionSensible", ("admin_email", "admin_user_id", "action", "total_deleted", "timestamp"),
                         deleted=(Dict[str, Escalar], {}),
                         extra=(Optional[Any], None))


class RegistroDeAccionesSensibles(BaseModel):
    entries: List[AccionSensible] = []
    count: Escalar = None
