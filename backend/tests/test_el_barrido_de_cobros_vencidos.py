"""
tests/test_el_barrido_de_cobros_vencidos.py

POR QUE EXISTE ESTE ARCHIVO

    `vencer_las_viejas` estaba escrita, probada y completa. Lo único que le
    faltaba era que alguien la llamara: SOLO LA LLAMABAN LOS TESTS. En
    producción no corría nunca.

    Tres cosas pasaban por eso:

      1. Una orden que nadie pagó se quedaba en «esperando pago» para siempre.
         El cliente veía «en curso» un pedido que ya no podía pagar.
      2. El bono descontado al cotizar nunca volvía. Es plata de alguien.
      3. Un pago que entraba tarde avanzaba igual —la orden nunca llegaba a
         estar «vencida»—, y el envío salía a la tasa congelada hacía horas.
         Esa diferencia la pagaba la empresa, en silencio.

    El código tenía escrita la rama que atajaba el caso 3. Nunca se alcanzaba.

LO QUE ESTE ARCHIVO NO DEJA QUE SE ROMPA

    1. Que el barrido ARRANQUE con la aplicación. Es lo que faltaba.
    2. Que alcance a LOS DOS corredores, no a uno.
    3. Que un pago tardío no avance ni se pierda: queda apartado y se avisa.
    4. Que un pago a tiempo siga avanzando exactamente igual.
"""
import asyncio
import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base, ensenarle_decimal128_a_mongomock   # noqa: E402
from services import pago_al_final as paf                          # noqa: E402
from services.money import to_decimal128                           # noqa: E402

ensenarle_decimal128_a_mongomock()


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


# LA HORA SE MIRA AL SEMBRAR, NO AL IMPORTAR.
#
#   Estaba congelada en una constante de módulo. En la suite completa pasan
#   minutos entre que se importa este archivo y que le toca el turno, así que
#   «vence en 5 minutos» puede ser «ya venció» cuando el test corre.
#
#   Acá no llegó a fallar —los márgenes son grandes— pero es la misma trampa
#   que sí hizo fallar a `test_volver_al_pago`, y un test que sólo pasa cuando
#   corre primero es un test que un día frena un despliegue por nada.
def ahora():
    return datetime.now(timezone.utc)



def una_orden(base, *, referencia, vence_en_minutos, estado=None, bono=0,
              tx="tx_1"):
    corre(base.transactions.insert_one({
        "transaction_id": tx, "display_id": "1001", "user_id": "u1",
        "type": "withdrawal", "status": estado or paf.ESPERANDO_PAGO,
        "payment_order_id": referencia,
        "payment_expires_at": ahora() + timedelta(minutes=vence_en_minutos),
        "bono_aplicado": bono, "created_at": ahora()}))
    corre(base.gestor_pix_payments.insert_one({
        "payment_id": referencia, "gestor_id": "u1",
        "proposito": paf.PROPOSITO, "status": "pending"}))


def estado_de(base, tx="tx_1"):
    return corre(base.transactions.find_one({"transaction_id": tx}))["status"]


# ══════════════════════════════════════════════════════════════════════════
# 1. EL BARRIDO ARRANCA. Es lo que faltaba.
# ══════════════════════════════════════════════════════════════════════════

def _lo_que_el_arranque_le_llama_a(modulo):
    """Los nombres de función que `server.py` llama SOBRE ese módulo.

    SE LEE EL ARBOL Y SE RESUELVE EL ALIAS. Las dos cosas las enseñó una
    mutación, una después de la otra:

      1. La primera versión buscaba `"_paf.arrancar(db)"` en el texto.
         Comentando la línea —`pass  # _paf.arrancar(db)`— los tests siguieron
         en verde: el texto seguía ahí, adentro de un comentario.

      2. La segunda leía el árbol, pero juntaba los nombres sueltos y
         preguntaba si «arrancar» estaba entre ellos. BORRANDO LA LLAMADA DEL
         TODO los tests siguieron en verde, porque `uso.arrancar(db)` también
         se llama «arrancar».

    Así que hay que mirar el par: sobre QUE módulo se llama QUE función. Y el
    módulo se importa con alias (`from services import pago_al_final as _paf`),
    así que el alias se resuelve leyendo los imports en vez de darlo por
    sentado — si alguien lo renombra, el test tiene que seguir funcionando.
    """
    import ast
    arbol = ast.parse((_BACKEND / "server.py").read_text(encoding="utf-8"))

    alias = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom):
            for n in nodo.names:
                if n.name == modulo:
                    alias.add(n.asname or n.name)
        elif isinstance(nodo, ast.Import):
            for n in nodo.names:
                if n.name.split(".")[-1] == modulo:
                    alias.add(n.asname or n.name.split(".")[-1])

    llamadas = set()
    for nodo in ast.walk(arbol):
        if (isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Attribute)
                and isinstance(nodo.func.value, ast.Name)
                and nodo.func.value.id in alias):
            llamadas.add(nodo.func.attr)
    return llamadas


def test_EL_ARRANQUE_DE_LA_APLICACION_PRENDE_EL_BARRIDO():
    """El test que no existía, y por eso nadie vio que no corría.

    `vencer_las_viejas` tenía sus propios tests y todos pasaban: probaban la
    función, no que alguien la llamara. Una función perfecta que nadie invoca
    es una función que no hace nada.
    """
    assert "arrancar" in _lo_que_el_arranque_le_llama_a("pago_al_final"), (
        "el arranque de la aplicación no prende el barrido de cobros "
        "vencidos: las órdenes que nadie paga se quedan en «esperando pago» "
        "para siempre y el bono descontado no vuelve.")


def test_el_apagado_lo_corta():
    """Una tarea que sigue viva después del apagado escribe sobre una base
    que se está cerrando."""
    assert "parar" in _lo_que_el_arranque_le_llama_a("pago_al_final")


def test_el_barrido_NO_SE_CORTA_por_un_error_de_una_vuelta():
    """Si una excepción matara el bucle, la aplicación se quedaría sin barrido
    hasta el próximo despliegue — que es exactamente el estado del que este
    lote la saca, y sin que nada avise."""
    fuente = (_BACKEND / "services" / "pago_al_final.py").read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("async def _bucle("):]
    cuerpo = cuerpo[:cuerpo.index("\ndef arrancar(")]
    assert "try:" in cuerpo and "except Exception" in cuerpo, (
        "el bucle del barrido no atrapa los errores: una falla de base en una "
        "vuelta deja la aplicación sin barrido hasta el próximo despliegue")


def test_arrancar_dos_veces_no_deja_dos_barridos(base):
    """Dos bucles vencen lo mismo dos veces y devuelven el bono dos veces."""
    async def _probar():
        paf.arrancar(base)
        primera = paf._tarea
        paf.arrancar(base)
        assert paf._tarea is primera, "arrancó un segundo barrido"
        await paf.parar()
        assert paf._tarea is None
    corre(_probar())


def test_el_barrido_corre_mas_seguido_que_lo_que_dura_un_cobro():
    """Si barriera cada más de siete minutos, el cliente vería «en curso» un
    cobro muerto durante todo ese rato."""
    assert paf.CADA_CUANTO_SE_BARRE < paf.MINUTOS_DEL_COBRO * 60


# ══════════════════════════════════════════════════════════════════════════
# 2. LOS DOS CORREDORES, y antes era uno
# ══════════════════════════════════════════════════════════════════════════

def test_vence_las_de_VENEZUELA(base):
    una_orden(base, referencia="venv_1", vence_en_minutos=-1)
    assert corre(paf.vencer_las_viejas(base)) == 1
    assert estado_de(base) == paf.PAGO_VENCIDO


def test_VENCE_TAMBIEN_LAS_DE_BRASIL(base):
    """El filtro pedía sólo `venv_`. Las del corredor inverso se quedaban en
    «esperando pago» para siempre: `recibir_comprobante` las rechaza por
    vencidas, pero nadie las movía de estado.

    Así que el cliente veía «en curso» un pedido que la aplicación ya no le
    iba a aceptar.
    """
    una_orden(base, referencia="brl_1", vence_en_minutos=-1)
    assert corre(paf.vencer_las_viejas(base)) == 1, (
        "las órdenes del corredor a Brasil no vencen nunca")
    assert estado_de(base) == paf.PAGO_VENCIDO


def test_NO_toca_una_orden_de_OTRO_flujo(base):
    """El prefijo sigue estando por esto: el camino cripto también usa
    «awaiting_payment». Vencerle una orden viva sería romperle el flujo a otro
    corredor sin que nada avise."""
    una_orden(base, referencia="cripto_1", vence_en_minutos=-1)
    assert corre(paf.vencer_las_viejas(base)) == 0
    assert estado_de(base) == paf.ESPERANDO_PAGO


def test_no_toca_una_que_TODAVIA_no_venció(base):
    una_orden(base, referencia="venv_1", vence_en_minutos=5)
    assert corre(paf.vencer_las_viejas(base)) == 0
    assert estado_de(base) == paf.ESPERANDO_PAGO


def test_EL_BONO_VUELVE_al_vencer(base):
    """Se descuenta al cotizar. Si la orden muere sin pagarse, esa plata es
    del cliente y nadie se la devolvía, porque el barrido no corría."""
    corre(base.users.insert_one({"user_id": "u1",
                                 "balance_ris_bono": to_decimal128("0")}))
    una_orden(base, referencia="venv_1", vence_en_minutos=-1, bono=15.0)
    assert corre(paf.vencer_las_viejas(base)) == 1
    usuario = corre(base.users.find_one({"user_id": "u1"}))
    assert float(usuario["balance_ris_bono"].to_decimal()) == 15.0


# ══════════════════════════════════════════════════════════════════════════
# 3. EL PAGO QUE LLEGA TARDE
# ══════════════════════════════════════════════════════════════════════════

def test_UN_PAGO_TARDIO_NO_AVANZA_AUNQUE_EL_BARRIDO_NO_HAYA_PASADO(base):
    """El caso que el filtro viejo dejaba pasar.

    Entre que el cobro muere y que el barrido pasa hay una ventana. Si el pago
    entra justo ahí, la orden todavía está en «esperando pago» — y el filtro
    viejo, que sólo miraba el estado, la hacía avanzar con la tasa congelada
    hace horas.
    """
    una_orden(base, referencia="venv_1", vence_en_minutos=-1)
    assert corre(paf.confirmar(base, {"payment_id": "venv_1"})) is False
    assert estado_de(base) != paf.PENDIENTE, (
        "un pago fuera de tiempo hizo avanzar el envío: sale a una tasa que "
        "ya no existe y la diferencia la paga la empresa")
    assert estado_de(base) == paf.PAGO_TARDIO


def test_un_pago_tardio_sobre_una_orden_YA_VENCIDA_tambien_se_aparta(base):
    una_orden(base, referencia="venv_1", vence_en_minutos=-1,
              estado=paf.PAGO_VENCIDO)
    assert corre(paf.confirmar(base, {"payment_id": "venv_1"})) is False
    assert estado_de(base) == paf.PAGO_TARDIO


def test_EL_APARTADO_NO_SE_CONFUNDE_CON_UNA_ORDEN_QUE_NADIE_PAGO(base):
    """La razón de que el estado sea propio y no «vencida».

    Una orden vencida sin pagar es una venta que no se hizo: no hay nada que
    resolver. Una con plata adentro es un cliente esperando. Si las dos
    quedaran en el mismo estado, la única diferencia sería una línea de
    registro que nadie mira.
    """
    una_orden(base, referencia="venv_1", vence_en_minutos=-1, tx="sin_pagar")
    una_orden(base, referencia="venv_2", vence_en_minutos=-1, tx="pagada")
    corre(paf.vencer_las_viejas(base))
    corre(paf.confirmar(base, {"payment_id": "venv_2"}))

    assert estado_de(base, "sin_pagar") == paf.PAGO_VENCIDO
    assert estado_de(base, "pagada") == paf.PAGO_TARDIO
    assert paf.PAGO_VENCIDO != paf.PAGO_TARDIO


def test_dos_webhooks_del_mismo_pago_apartan_UNA_vez(base):
    """Mercado Pago reintenta. Apartar dos veces avisaría dos veces al equipo
    por el mismo problema."""
    una_orden(base, referencia="venv_1", vence_en_minutos=-1)
    assert corre(paf.confirmar(base, {"payment_id": "venv_1"})) is False
    assert corre(paf.confirmar(base, {"payment_id": "venv_1"})) is False
    doc = corre(base.transactions.find_one({"transaction_id": "tx_1"}))
    assert doc["status"] == paf.PAGO_TARDIO


def test_queda_anotado_CUAL_pago_y_CUANDO(base):
    """Quien lo mire tiene que poder cruzarlo con Mercado Pago sin adivinar."""
    una_orden(base, referencia="venv_1", vence_en_minutos=-1)
    corre(paf.confirmar(base, {"payment_id": "venv_1"}))
    doc = corre(base.transactions.find_one({"transaction_id": "tx_1"}))
    assert doc["late_payment_ref"] == "venv_1"
    assert doc.get("late_payment_at") is not None


def test_SE_AVISA_AL_EQUIPO(base):
    """Un ERROR en el registro lo ve quien mira los registros. Acá hay plata
    de un cliente esperando una decisión: tiene que llegarle a alguien.

    SE ESPIA LA LLAMADA, NO SE BUSCA EL NOMBRE EN EL ARCHIVO.

        La primera versión buscaba «avisar_al_personal» en el texto.
        Reemplazando el import por `avisar_al_personal = None`, los veinte
        tests siguieron en verde: el nombre seguía escrito.
    """
    import services.notifications as notif
    original = notif.avisar_al_personal
    avisos = []

    async def _espia(**kw):
        avisos.append(kw)
        return 1

    notif.avisar_al_personal = _espia
    try:
        una_orden(base, referencia="venv_1", vence_en_minutos=-1)
        corre(paf.confirmar(base, {"payment_id": "venv_1"}))
    finally:
        notif.avisar_al_personal = original

    assert len(avisos) == 1, (
        "no se le avisó a nadie de un pago que entró fuera de tiempo: hay "
        "plata de un cliente esperando una decisión que nadie sabe que existe")
    aviso = avisos[0]
    assert "1001" in aviso["message"], (
        "el aviso no dice de qué envío habla: quien lo reciba tiene que "
        "salir a buscarlo")
    assert aviso["data"]["transaction_id"] == "tx_1"


def test_el_aviso_dice_si_EL_BONO_YA_SE_DEVOLVIO(base):
    """Si la orden venció primero, el bono ya volvió a la cuenta del cliente.
    Despachar sin descontarlo otra vez es regalarlo — y quien decide no tiene
    forma de saberlo si el aviso no se lo dice."""
    import services.notifications as notif
    original = notif.avisar_al_personal
    avisos = []

    async def _espia(**kw):
        avisos.append(kw)
        return 1

    notif.avisar_al_personal = _espia
    try:
        una_orden(base, referencia="venv_1", vence_en_minutos=-1, bono=15.0,
                  estado=paf.PAGO_VENCIDO)
        corre(paf.confirmar(base, {"payment_id": "venv_1"}))
    finally:
        notif.avisar_al_personal = original

    assert avisos and avisos[0]["data"]["bono_ya_devuelto"] is True
    assert "bono" in avisos[0]["message"].lower()


def test_si_el_aviso_falla_la_orden_QUEDA_APARTADA_IGUAL(base):
    """Lo que protege la plata es el estado, no el aviso. Que no se pueda
    avisar se anota; no se deshace lo que ya está bien hecho."""
    import services.notifications as notif
    original = notif.avisar_al_personal

    async def _explota(*a, **k):
        raise RuntimeError("no hay a quién avisar")

    notif.avisar_al_personal = _explota
    try:
        una_orden(base, referencia="venv_1", vence_en_minutos=-1)
        assert corre(paf.confirmar(base, {"payment_id": "venv_1"})) is False
        assert estado_de(base) == paf.PAGO_TARDIO
    finally:
        notif.avisar_al_personal = original


# ══════════════════════════════════════════════════════════════════════════
# 4. Lo que NO cambió
# ══════════════════════════════════════════════════════════════════════════

def test_UN_PAGO_A_TIEMPO_SIGUE_AVANZANDO_IGUAL(base):
    """Es lo que más gente usa. Si esto se rompe, se rompió el producto."""
    una_orden(base, referencia="venv_1", vence_en_minutos=5)
    assert corre(paf.confirmar(base, {"payment_id": "venv_1"})) is True
    assert estado_de(base) == paf.PENDIENTE


def test_un_webhook_repetido_sobre_una_orden_YA_PAGADA_no_la_toca(base):
    una_orden(base, referencia="venv_1", vence_en_minutos=5)
    corre(paf.confirmar(base, {"payment_id": "venv_1"}))
    assert corre(paf.confirmar(base, {"payment_id": "venv_1"})) is False
    assert estado_de(base) == paf.PENDIENTE


def test_una_referencia_que_no_existe_no_rompe_el_webhook(base):
    """Mercado Pago reintenta lo que falla. Una excepción acá llena el
    registro de ruido y no arregla nada."""
    assert corre(paf.confirmar(base, {"payment_id": "venv_fantasma"})) is False
