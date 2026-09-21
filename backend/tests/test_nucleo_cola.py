"""
tests/test_nucleo_cola.py — la bandeja de salida y la cola del núcleo.

    Lo que un banco necesita de una cola, regla por regla: el evento entra
    con el asiento o no entra; el mismo trabajo no corre dos veces; un
    trabajo tomado por un proceso que murió lo retoma otro cuando vence el
    turno; un fallo espera cada vez más; demasiados fallos son un muerto que
    una persona puede revivir; y con el núcleo apagado el trabajador no
    toca nada.

    Corre sobre SQLite en memoria con la misma lógica que Postgres. El
    reloj se pasa a mano (`ahora=`) para que los turnos y las esperas se
    prueben sin dormir.
"""
import asyncio
import os
import pathlib
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from nucleo import base, cola, comandos, libro, plan, tareas, trabajador   # noqa: E402
from nucleo.esquema import eventos, trabajos                               # noqa: E402
from nucleo.libro import AsientoInvalido, Partida                          # noqa: E402

HOY = date(2026, 9, 21)
T0 = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def ya(c):
    return asyncio.run(c)


@pytest.fixture(autouse=True)
def base_limpia():
    base.usar("sqlite+aiosqlite://")
    ya(base.crear_todo())

    async def sembrar():
        async with base.sesion() as s:
            await plan.sembrar(s)
    ya(sembrar())


def cuenta(titular="u_ana"):
    from _nucleo_comun import cuenta_aprobada
    return cuenta_aprobada(titular)


async def _eventos():
    from sqlalchemy import select
    async with base.sesion() as s:
        return (await s.execute(select(eventos).order_by(eventos.c.id))).all()


async def _trabajo(id_):
    from sqlalchemy import select
    async with base.sesion() as s:
        return (await s.execute(select(trabajos).where(trabajos.c.id == id_))).first()


def encolar(tipo="eco", clave="k1", carga=None, ahora=T0):
    async def _():
        async with base.sesion() as s:
            return await cola.encolar(s, tipo=tipo, clave=clave, carga=carga or {}, ahora=ahora)
    return ya(_())


def tomar(quien="w1", ahora=T0):
    async def _():
        async with base.sesion() as s:
            return await cola.tomar(s, trabajador=quien, ahora=ahora)
    return ya(_())


def fallar(id_, quien="w1", ahora=T0, azar=0.0):
    async def _():
        async with base.sesion() as s:
            return await cola.fallar(s, id_, trabajador=quien, error="se rompió", ahora=ahora, azar=azar)
    return ya(_())


# ─── la bandeja de salida ─────────────────────────────────────────────────

def test_EL_ASIENTO_Y_SU_EVENTO_ENTRAN_JUNTOS():
    c = cuenta()
    n = ya(comandos.acreditar(cuenta_id=c, monto="10.00", referencia="r1", actor="t", fecha=HOY))
    filas = ya(_eventos())
    assert [(e.tipo, e.clave, e.publicado) for e in filas] == [("asiento_registrado", f"asiento:{n}", None)]
    assert '"referencia":"r1"' in filas[0].carga


def test_UN_ASIENTO_QUE_NO_ENTRA_NO_DEJA_EVENTO():
    async def intento():
        async with base.sesion() as s:
            await libro.asentar(s, fecha=HOY, descripcion="x", referencia="mal", comando="ajuste", actor="t",
                                lineas=[Partida(plan.LIQUIDACION, debe=100), Partida(plan.CAPITAL, haber=99)])
    with pytest.raises(AsientoInvalido):
        ya(intento())
    assert ya(_eventos()) == []


def test_SI_EL_EVENTO_NO_SE_PUEDE_ESCRIBIR_EL_ASIENTO_TAMPOCO_QUEDA(monkeypatch):
    """La garantía de la bandeja de salida es de ida y vuelta: no hay
    asiento sin evento. Se simula la base rechazando el evento y se mira
    que el asiento no haya quedado."""
    c = cuenta()

    async def rota(*a, **k):
        raise RuntimeError("no se pudo anotar el evento")
    monkeypatch.setattr(cola, "anotar_evento", rota)
    with pytest.raises(RuntimeError):
        ya(comandos.acreditar(cuenta_id=c, monto="10.00", referencia="r1", actor="t", fecha=HOY))
    assert ya(comandos.estado())["asientos"] == 0


def test_la_misma_referencia_no_deja_dos_eventos():
    c = cuenta()
    ya(comandos.acreditar(cuenta_id=c, monto="10.00", referencia="misma", actor="t", fecha=HOY))
    ya(comandos.acreditar(cuenta_id=c, monto="10.00", referencia="misma", actor="t", fecha=HOY))
    assert len(ya(_eventos())) == 1


def test_el_cierre_del_dia_tambien_deja_su_evento():
    ya(comandos.cerrar_dia(dia=HOY, actor="t"))
    filas = ya(_eventos())
    assert [(e.tipo, e.clave) for e in filas] == [("dia_cerrado", "cierre:2026-09-21")]


def test_DESPACHAR_CONVIERTE_EL_EVENTO_EN_TRABAJO_Y_NO_LO_DESPACHA_DOS_VECES():
    c = cuenta()
    ya(comandos.acreditar(cuenta_id=c, monto="10.00", referencia="r1", actor="t", fecha=HOY))

    async def despachar():
        async with base.sesion() as s:
            return await cola.despachar_eventos(s, tareas.SUSCRIPCIONES, ahora=T0)
    assert ya(despachar()) == 1
    assert ya(despachar()) == 0
    (e,) = ya(_eventos())
    assert e.publicado is not None

    async def listar():
        async with base.sesion() as s:
            return await cola.listar_trabajos(s)
    (t,) = ya(listar())
    assert t["tipo"] == "avisar_asiento" and t["clave"] == "asiento_registrado:asiento:1"
    assert t["origen_evento"] == e.id and t["estado"] == "pendiente"


def test_un_evento_sin_suscriptores_se_publica_igual():
    async def _():
        async with base.sesion() as s:
            await cola.anotar_evento(s, tipo="algo_raro", clave="x", carga={})
            return await cola.despachar_eventos(s, {}, ahora=T0)
    assert ya(_()) == 1
    assert ya(_resumen())["eventos_sin_publicar"] == 0


def _resumen():
    async def _():
        async with base.sesion() as s:
            return await cola.resumen(s)
    return _()


# ─── la cola ──────────────────────────────────────────────────────────────

def test_EL_MISMO_TRABAJO_PEDIDO_DOS_VECES_ES_UNO():
    a = encolar(clave="k1")
    b = encolar(clave="k1")
    assert a["nuevo"] is True and b["nuevo"] is False and a["id"] == b["id"]
    assert ya(_resumen())["pendiente"] == 1


def test_TOMAR_DA_EL_TURNO_A_UNO_SOLO():
    encolar(clave="k1")
    t = tomar("w1")
    assert t and t["intentos"] == 1
    assert tomar("w2") is None                       # w1 lo tiene, el turno está vigente
    fila = ya(_trabajo(t["id"]))
    assert fila.estado == "en_curso" and fila.tomado_por == "w1"


def test_UN_TURNO_VENCIDO_LO_RETOMA_OTRO():
    """El proceso w1 murió con el trabajo en la mano. Pasado el turno, w2
    se lo lleva, y el intento cuenta."""
    encolar(clave="k1")
    t = tomar("w1", ahora=T0)
    despues = T0 + timedelta(seconds=cola.DURACION_DEL_TURNO + 1)
    assert tomar("w2", ahora=T0 + timedelta(seconds=cola.DURACION_DEL_TURNO - 1)) is None
    t2 = tomar("w2", ahora=despues)
    assert t2 and t2["id"] == t["id"] and t2["intentos"] == 2
    assert ya(_trabajo(t["id"])).tomado_por == "w2"


def test_EL_QUE_PERDIO_EL_TURNO_NO_PISA_EL_RESULTADO():
    encolar(clave="k1")
    t = tomar("w1", ahora=T0)
    tomar("w2", ahora=T0 + timedelta(seconds=cola.DURACION_DEL_TURNO + 1))

    async def terminar_como_w1():
        async with base.sesion() as s:
            return await cola.terminar(s, t["id"], trabajador="w1", resultado="tarde")
    assert ya(terminar_como_w1()) is False
    assert ya(_trabajo(t["id"])).estado == "en_curso"
    assert fallar(t["id"], quien="w1").get("ajeno") is True


def test_no_se_toma_antes_de_su_momento():
    encolar(clave="k1", ahora=T0 + timedelta(seconds=30))
    assert tomar(ahora=T0) is None
    assert tomar(ahora=T0 + timedelta(seconds=30)) is not None


def test_UN_FALLO_VUELVE_A_PENDIENTE_CON_ESPERA_CRECIENTE():
    encolar(clave="k1")
    t = tomar("w1", ahora=T0)
    r = fallar(t["id"], ahora=T0, azar=0.0)
    assert r["estado"] == "pendiente"
    fila = ya(_trabajo(t["id"]))
    assert fila.intentos == 1 and fila.ultimo_error == "se rompió" and fila.tomado_hasta is None
    # 5 segundos después del primer fallo, 10 del segundo, 20 del tercero.
    assert tomar("w1", ahora=T0 + timedelta(seconds=4)) is None
    t = tomar("w1", ahora=T0 + timedelta(seconds=5))
    assert t and t["intentos"] == 2
    fallar(t["id"], ahora=T0 + timedelta(seconds=5), azar=0.0)
    assert tomar("w1", ahora=T0 + timedelta(seconds=14)) is None
    assert tomar("w1", ahora=T0 + timedelta(seconds=15)) is not None


@pytest.mark.parametrize("fallos, base_", [(1, 5), (2, 10), (3, 20), (4, 40), (5, 80), (9, 600), (20, 600)])
def test_la_espera_dobla_con_tope_y_algo_de_azar(fallos, base_):
    assert cola.espera_antes_del_reintento(fallos, azar=0.0) == base_
    assert cola.espera_antes_del_reintento(fallos, azar=1.0) == base_ * 1.25
    for _ in range(20):
        assert base_ <= cola.espera_antes_del_reintento(fallos) <= base_ * 1.25


def test_DESPUES_DEL_ULTIMO_INTENTO_ES_UN_MUERTO_Y_SE_PUEDE_REVIVIR():
    encolar(clave="k1")
    ahora = T0
    for i in range(cola.INTENTOS_MAXIMOS):
        t = tomar("w1", ahora=ahora)
        assert t and t["intentos"] == i + 1, (i, t)
        r = fallar(t["id"], ahora=ahora, azar=0.0)
        ahora = ahora + timedelta(seconds=cola.ESPERA_TOPE + 1)
    assert r["estado"] == "muerto"
    fila = ya(_trabajo(t["id"]))
    assert fila.estado == "muerto" and fila.terminado is not None and fila.ultimo_error == "se rompió"
    assert tomar("w1", ahora=ahora) is None          # un muerto no se toma

    async def revivir():
        async with base.sesion() as s:
            return await cola.reintentar(s, t["id"], ahora=ahora)
    assert ya(revivir()) is True
    assert ya(revivir()) is False                     # ya no está muerto
    fila = ya(_trabajo(t["id"]))
    assert fila.estado == "pendiente" and fila.intentos == 0 and fila.ultimo_error == "se rompió"
    assert tomar("w1", ahora=ahora)["intentos"] == 1


def test_un_hecho_no_se_vuelve_a_tomar():
    encolar(clave="k1")
    t = tomar("w1", ahora=T0)

    async def terminar():
        async with base.sesion() as s:
            return await cola.terminar(s, t["id"], trabajador="w1", resultado="listo", ahora=T0)
    assert ya(terminar()) is True
    assert tomar("w1", ahora=T0 + timedelta(days=1)) is None
    fila = ya(_trabajo(t["id"]))
    assert fila.estado == "hecho" and fila.resultado == "listo"


# ─── el trabajador ────────────────────────────────────────────────────────

def test_EL_TRABAJADOR_CORRE_EL_ECO_Y_MATA_LO_QUE_FALLA():
    encolar(tipo="eco", clave="e1", carga={"mensaje": "hola"})
    encolar(tipo="fallar", clave="f1", carga={"motivo": "a propósito"})
    ahora = T0
    r = ya(trabajador.una_vuelta(ahora=ahora))
    assert r == {"despachados": 0, "corridos": 2, "hechos": 1, "muertos": 0, "reintentan": 1}
    for _ in range(cola.INTENTOS_MAXIMOS - 1):
        ahora = ahora + timedelta(seconds=cola.ESPERA_TOPE + 1)
        r = ya(trabajador.una_vuelta(ahora=ahora))
    assert r["muertos"] == 1
    async def listar():
        async with base.sesion() as s:
            return {t["clave"]: t for t in await cola.listar_trabajos(s)}
    filas = ya(listar())
    assert filas["e1"]["estado"] == "hecho" and filas["e1"]["resultado"] == "eco: hola"
    assert filas["f1"]["estado"] == "muerto" and "a propósito" in filas["f1"]["ultimo_error"]
    assert filas["f1"]["intentos"] == cola.INTENTOS_MAXIMOS


def test_UN_TIPO_SIN_MANEJADOR_MUERE_SIN_REINTENTAR():
    """Reintentar no inventa un manejador. Va directo a muerto para que
    alguien lo vea, en vez de fallar seis veces en silencio."""
    encolar(tipo="no_existe", clave="x")
    r = ya(trabajador.una_vuelta(ahora=T0))
    assert r["muertos"] == 1
    async def listar():
        async with base.sesion() as s:
            return await cola.listar_trabajos(s)
    (t,) = ya(listar())
    assert t["estado"] == "muerto" and t["intentos"] == 1 and "manejador" in t["ultimo_error"]


def test_de_punta_a_punta_un_asiento_termina_en_un_trabajo_hecho():
    c = cuenta()
    ya(comandos.acreditar(cuenta_id=c, monto="10.00", referencia="r1", actor="t", fecha=HOY))
    r = ya(trabajador.una_vuelta(ahora=T0))
    assert r["despachados"] == 1 and r["hechos"] == 1
    assert ya(_resumen()) == {"pendiente": 0, "en_curso": 0, "hecho": 1, "muerto": 0,
                               "eventos": 1, "eventos_sin_publicar": 0}


def test_los_manejadores_del_laboratorio_son_los_unicos_que_se_encolan_a_mano():
    assert set(tareas.DE_LABORATORIO) == {"eco", "fallar"}
    assert set(tareas.DE_LABORATORIO) <= set(tareas.MANEJADORES)
    for suscriptores in tareas.SUSCRIPCIONES.values():
        for t in suscriptores:
            assert t in tareas.MANEJADORES, t


def test_CON_EL_NUCLEO_APAGADO_EL_TRABAJADOR_NO_TOCA_NADA():
    mongomock_motor = pytest.importorskip("mongomock_motor")
    from conftest import usar_base
    from nucleo import modo
    mongo = mongomock_motor.AsyncMongoMockClient()["nucleo_trabajador"]
    usar_base(mongo)
    encolar(tipo="eco", clave="e1")
    assert ya(trabajador.latir(mongo)) is False
    assert ya(_resumen())["pendiente"] == 1
    ya(mongo.config.insert_one({"clave": modo.CLAVE, "valor": str(modo.LABORATORIO)}))
    assert ya(trabajador.latir(mongo)) is True
    assert ya(_resumen())["hecho"] == 1
    assert trabajador.estado()["ultimo_modo"] == "laboratorio"


def test_SIN_BASE_EL_TRABAJADOR_TAMPOCO(monkeypatch):
    mongomock_motor = pytest.importorskip("mongomock_motor")
    from conftest import usar_base
    from nucleo import modo
    mongo = mongomock_motor.AsyncMongoMockClient()["nucleo_trabajador_sin_base"]
    usar_base(mongo)
    ya(mongo.config.insert_one({"clave": modo.CLAVE, "valor": str(modo.LABORATORIO)}))
    monkeypatch.setattr(base, "_motor", None)
    monkeypatch.delenv(base.VARIABLE, raising=False)
    assert ya(trabajador.latir(mongo)) is False


def test_el_servidor_arranca_el_trabajador_y_lo_para_al_apagar():
    """Si nadie lo arranca, la cola existe y no corre: los eventos se
    acumulan sin despachar y nadie se entera. Se mira el arranque de la
    aplicación, que es el único lugar desde donde se llama."""
    import re
    fuente = (pathlib.Path(__file__).parent.parent / "server.py").read_text(encoding="utf-8")
    assert re.search(r"^\s*_nucleo_trabajador\.arrancar\(db\)", fuente, re.M)
    assert re.search(r"^\s*await _nucleo_trabajador\.parar\(\)", fuente, re.M)
