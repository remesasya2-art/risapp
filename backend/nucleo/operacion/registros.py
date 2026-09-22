"""
Los registros del núcleo en JSON, y las métricas.

REGISTROS

    Un registro de texto suelto se lee a ojo y nada más. En JSON con campos
    fijos (momento, nivel, quién escribe, mensaje, y lo que la línea traiga:
    quién actuó, sobre qué, cuánto tardó) lo lee una persona Y lo indexa un
    servicio de registros. `instalar()` cuelga el formateador del logger
    «nucleo», del que descienden todos los del paquete, y les corta la
    propagación para que la misma línea no salga dos veces (una en JSON y
    otra en texto por el logger raíz de la aplicación).

METRICAS

    Números que un tablero externo lee sin entrar al panel: cuentas, asientos
    de hoy, saldo de los titulares, trabajos por estado, operaciones por
    estado, pedidos pendientes, obligaciones vencidas. En JSON para la
    pestaña y en texto plano `nombre valor` (la forma que entienden los
    recolectores de métricas) para el tablero. Se calculan al pedirlas; no
    hay un contador que pueda desincronizarse de la base.
"""
import json
import logging
import sys
from datetime import date, datetime, timezone

from sqlalchemy import func, select

from nucleo import base
from nucleo.esquema import aprobaciones, asientos, bitacora, cuentas, operaciones, partidas, reportes, trabajos

CAMPOS_EXTRA = ("quien", "accion", "objetivo", "duracion_ms", "trabajo", "operacion")


class FormateadorJson(logging.Formatter):
    def format(self, registro: logging.LogRecord) -> str:
        linea = {"momento": datetime.fromtimestamp(registro.created, tz=timezone.utc).isoformat(),
                 "nivel": registro.levelname, "quien_escribe": registro.name, "mensaje": registro.getMessage()}
        for campo in CAMPOS_EXTRA:
            if hasattr(registro, campo):
                linea[campo] = getattr(registro, campo)
        if registro.exc_info:
            linea["error"] = self.formatException(registro.exc_info)
        return json.dumps(linea, ensure_ascii=False, default=str)


NOMBRE_DEL_MANEJADOR = "nucleo-json"


def instalar(salida=None) -> logging.Logger:
    """Idempotente: dos arranques no cuelgan dos manejadores."""
    raiz = logging.getLogger("nucleo")
    for m in raiz.handlers:
        if getattr(m, "name", None) == NOMBRE_DEL_MANEJADOR:
            if salida is not None:
                m.setStream(salida)
            return raiz
    manejador = logging.StreamHandler(salida or sys.stdout)
    manejador.name = NOMBRE_DEL_MANEJADOR
    manejador.setFormatter(FormateadorJson())
    raiz.addHandler(manejador)
    raiz.propagate = False
    if raiz.level == logging.NOTSET:
        raiz.setLevel(logging.INFO)
    return raiz


# ─── métricas ─────────────────────────────────────────────────────────────

async def resumen() -> dict:
    from nucleo import plan
    from nucleo.cumplimiento import calendario, incidentes, ouvidoria
    hoy = datetime.now(timezone.utc).date()
    async with base.sesion() as s:
        n_cuentas = int((await s.execute(select(func.count()).select_from(cuentas).where(cuentas.c.estado == "activa"))).scalar_one())
        n_asientos = int((await s.execute(select(func.count()).select_from(asientos))).scalar_one())
        n_hoy = int((await s.execute(select(func.count()).select_from(asientos).where(asientos.c.fecha == hoy))).scalar_one())
        haber, debe = (await s.execute(select(func.coalesce(func.sum(partidas.c.haber), 0), func.coalesce(func.sum(partidas.c.debe), 0))
                                       .where(partidas.c.cuenta_contable == plan.DE_TITULARES))).one()
        por_estado = {e: int(n) for e, n in (await s.execute(select(trabajos.c.estado, func.count()).group_by(trabajos.c.estado))).all()}
        ops = {e: int(n) for e, n in (await s.execute(select(operaciones.c.estado, func.count()).group_by(operaciones.c.estado))).all()}
        n_reportes = int((await s.execute(select(func.count()).select_from(reportes))).scalar_one())
        n_transmitidos = int((await s.execute(select(func.count()).select_from(reportes).where(reportes.c.protocolo.isnot(None)))).scalar_one())
        n_pendientes = int((await s.execute(select(func.count()).select_from(aprobaciones).where(aprobaciones.c.estado == "pendiente"))).scalar_one())
        n_bitacora = int((await s.execute(select(func.count()).select_from(bitacora))).scalar_one())
    cal = await calendario.resumen()
    return {
        "cuentas_activas": n_cuentas, "asientos_total": n_asientos, "asientos_hoy": n_hoy,
        "saldo_de_titulares_centavos": int(haber) - int(debe),
        "trabajos_pendientes": por_estado.get("pendiente", 0), "trabajos_en_curso": por_estado.get("en_curso", 0),
        "trabajos_hechos": por_estado.get("hecho", 0), "trabajos_muertos": por_estado.get("muerto", 0),
        "operaciones_activas": ops.get("activa", 0), "operaciones_enviadas": ops.get("enviada", 0),
        "operaciones_liquidadas": ops.get("liquidada", 0), "operaciones_rechazadas": ops.get("rechazada", 0),
        "reportes_generados": n_reportes, "reportes_transmitidos": n_transmitidos,
        "obligaciones_pendientes": cal["pendientes"], "obligaciones_vencidas": cal["vencidas"],
        "acciones_con_plazo_vencidas": cal["acciones_vencidas"],
        "aprobaciones_pendientes": n_pendientes,
        "incidentes_abiertos": (await incidentes.resumen())["abierto"],
        "reclamos_vencidos": (await ouvidoria.resumen())["vencidos"],
        "bitacora_renglones": n_bitacora,
    }


def en_texto(metricas: dict) -> str:
    """`nucleo_<nombre> <valor>`, una por línea, como las lee un recolector."""
    lineas = [f"# nucleo: metricas al {datetime.now(timezone.utc).isoformat()}"]
    for nombre, valor in metricas.items():
        lineas.append(f"nucleo_{nombre} {int(valor)}")
    return "\n".join(lineas) + "\n"
