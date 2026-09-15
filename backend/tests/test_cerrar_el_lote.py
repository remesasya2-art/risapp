"""
Cerrar el lote: asentar de una vez el pago de todas sus órdenes.

QUE SE PRUEBA ACA, Y POR QUE IMPORTA

    Un lote pagado no tenía cómo terminar. Sólo existían «abierto» y
    «cancelado», y cancelar DEVUELVE las órdenes a la cola — o sea, lo
    contrario de lo que hay que hacer con un lote que ya se pagó. El agente
    terminaba apretando «Procesar pago» una por una, hasta trescientas veces.

    Y hay dos caminos que asientan un pago: el botón de a una y este cierre.
    Los dos tienen que hacer EXACTAMENTE el mismo trabajo, porque lo que se
    pierde cuando se separan no se nota — el aviso al cliente, o el cupo.

LA APLICACION NO PAGA

    Todas estas órdenes ya se pagaron en el banco venezolano. Esto asienta el
    registro. Por eso ningún test de acá mira saldos: el saldo del cliente se
    debitó cuando creó el envío.
"""
import asyncio
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

# Los ayudantes viven en el archivo del flujo anterior: un lote con sus fotos
# adjudicadas es justo el punto de partida de todo lo que se prueba acá, y
# copiarlos los dejaría desincronizados en la primera corrección.
from test_comprobantes_del_lote import (                             # noqa: E402
    Jefe, _con_lector, _correr, _foto, _lote_con, _orden, _senales)

from services import comprobantes_del_lote as cmp                    # noqa: E402
from services import lotes_de_pago as lotes                          # noqa: E402
from services import registro_del_pago                               # noqa: E402
from conftest import usar_base                                       # noqa: E402

CUENTA_A = "01340219112191046516"
CUENTA_B = "01020121710106529080"


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test_cerrar"]
    usar_base(b)
    return b


@pytest.fixture(autouse=True)
def sin_avisos(monkeypatch):
    """El aviso al cliente sale por su propio camino y acá no se prueba.

    Se cuenta cuántos salieron, que es lo que sí importa: un cierre que asienta
    diez pagos y manda nueve avisos deja a alguien sin enterarse.
    """
    enviados = []

    async def _falso(**kwargs):
        enviados.append(kwargs)

    monkeypatch.setattr(registro_del_pago, "create_notification", _falso)
    return enviados


async def _con_dueno(base):
    """Le pone dueño a las órdenes sembradas.

    `_lote_con` las siembra con lo mínimo para armar el lote, y hasta ahora
    nadie miraba de quién eran. Asentar el pago sí: le avisa al cliente.
    """
    await base.transactions.update_many(
        {"user_id": {"$exists": False}}, {"$set": {"user_id": "u_cliente"}})


async def _lote_listo(base, monkeypatch, cuantas=2):
    """Un lote con `cuantas` órdenes, cada una con su comprobante adjudicado."""
    cuentas = [CUENTA_A, CUENTA_B][:cuantas]
    ordenes = [_orden(i, cuenta=c, monto="100.00") for i, c in enumerate(cuentas)]
    lote_id = await _lote_con(base, ordenes)
    await _con_dueno(base)
    _con_lector(monkeypatch, [_senales(cuentas=[c], montos=["100,00"])
                              for c in cuentas])
    # Cada foto de un color distinto A PROPOSITO: son imágenes distintas y el
    # sistema descarta las repetidas por su contenido. Con `_foto()` dos veces,
    # la segunda se saltea —bien— y el lote queda con una orden sin comprobante.
    await cmp.cargar(base, lote_id,
                     [_foto((30 + i * 40, 30, 30)) for i in range(len(cuentas))],
                     quien=Jefe())
    return lote_id


# ══════════════════════════════════════════════════════════════════════════
# 1. El cierre asienta los pagos
# ══════════════════════════════════════════════════════════════════════════

def test_CERRAR_DEJA_LAS_ORDENES_COMO_PAGADAS(base, monkeypatch):
    """Es lo que hace que salgan de «por procesar» y aparezcan en «Pagados»."""
    async def caso():
        lote_id = await _lote_listo(base, monkeypatch)

        resultado = await lotes.cerrar(base, lote_id, quien=Jefe())

        assert resultado["asentadas"] == 2
        async for tx in base.transactions.find({"type": "withdrawal"}):
            assert tx["status"] == "completed", tx["transaction_id"]
            assert tx["processed_by"] == Jefe().user_id
    _correr(caso())


def test_CERRAR_SACA_EL_LOTE_DE_LOS_ABIERTOS(base, monkeypatch):
    """Lo que pidió el dueño: que el área quede limpia para lo que entre."""
    async def caso():
        lote_id = await _lote_listo(base, monkeypatch)
        assert len(await lotes.abiertos(base)) == 1

        await lotes.cerrar(base, lote_id, quien=Jefe())

        assert await lotes.abiertos(base) == []
        cerrados = await lotes.cerrados(base)
        assert [l["lote_id"] for l in cerrados] == [lote_id]
        assert cerrados[0]["total"] == 2, (
            "el lote cerrado tiene que poder mirarse: adentro viven el archivo "
            "que se le mandó al banco y las fotos")
    _correr(caso())


def test_CERRAR_LE_AVISA_A_CADA_CLIENTE(base, monkeypatch, sin_avisos):
    """Un cierre que asienta dos pagos y manda un aviso deja a alguien sin
    enterarse de que le llegó la plata."""
    async def caso():
        lote_id = await _lote_listo(base, monkeypatch)
        await lotes.cerrar(base, lote_id, quien=Jefe())
        assert len(sin_avisos) == 2
        assert all(a["notification_type"] == "withdrawal_completed"
                   for a in sin_avisos)
    _correr(caso())


def test_CADA_PAGO_ASENTADO_DEJA_SU_LINEA_DE_AUDITORIA(base, monkeypatch):
    """`dinero.retiro_aprobado` estaba declarada y NO LA LLAMABA NADIE: armar un
    lote quedaba asentado y mandar la plata no."""
    async def caso():
        lote_id = await _lote_listo(base, monkeypatch)
        await lotes.cerrar(base, lote_id, quien=Jefe())

        lineas = await base.auditoria.count_documents(
            {"accion": "dinero.retiro_aprobado"})
        assert lineas == 2
        assert await base.auditoria.find_one({"accion": "dinero.lote_cerrado"})
    _correr(caso())


def test_UN_LOTE_CERRADO_NO_SE_CIERRA_DOS_VECES(base, monkeypatch):
    """La segunda vez volvería a avisarle al cliente y a consumirle el cupo."""
    async def caso():
        lote_id = await _lote_listo(base, monkeypatch)
        await lotes.cerrar(base, lote_id, quien=Jefe())
        with pytest.raises(ValueError):
            await lotes.cerrar(base, lote_id, quien=Jefe())
    _correr(caso())


def test_UNA_ORDEN_QUE_YA_SE_ASENTO_NO_SE_ASIENTA_DE_NUEVO(base, monkeypatch, sin_avisos):
    """Alguien pudo apretar «Procesar pago» de a una mientras el lote seguía
    abierto. El lote cierra igual —el resultado es el mismo— pero esa orden no
    vuelve a avisar ni a consumir cupo."""
    async def caso():
        lote_id = await _lote_listo(base, monkeypatch)
        # Como si el botón de a una la hubiera asentado antes.
        await base.transactions.update_one(
            {"transaction_id": "tx_0000"}, {"$set": {"status": "completed"}})

        resultado = await lotes.cerrar(base, lote_id, quien=Jefe())

        assert resultado["asentadas"] == 1
        assert len(resultado["ya_estaban"]) == 1
        assert len(sin_avisos) == 1, "al que ya estaba no se le avisa de nuevo"
    _correr(caso())


# ══════════════════════════════════════════════════════════════════════════
# 2. No cierra con preguntas abiertas adentro
# ══════════════════════════════════════════════════════════════════════════

def test_NO_CIERRA_SI_UNA_ORDEN_NO_TIENE_COMPROBANTE(base, monkeypatch):
    """Si el cierre las dejara pasar, el lote desaparecería de la pantalla con
    la pregunta adentro y nadie la volvería a ver."""
    async def caso():
        ordenes = [_orden(0, cuenta=CUENTA_A), _orden(1, cuenta=CUENTA_B)]
        lote_id = await _lote_con(base, ordenes)
        await _con_dueno(base)
        _con_lector(monkeypatch, [_senales(cuentas=[CUENTA_A], montos=["100,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        with pytest.raises(ValueError) as e:
            await lotes.cerrar(base, lote_id, quien=Jefe())
        assert "#000001" in str(e.value), "tiene que decir CUAL falta"

        tx = await base.transactions.find_one({"transaction_id": "tx_0000"})
        assert tx["status"] == "pending", (
            "si el cierre no procede, no asienta nada: a medias sería peor")
    _correr(caso())


def test_NO_CIERRA_SI_EL_MONTO_DE_LA_FOTO_NO_ES_EL_DE_LA_ORDEN(base, monkeypatch):
    """Lo que se decidió: esas las mira una persona. Asentarlo sería dar por
    pagado un importe que nadie comparó."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0, cuenta=CUENTA_A, monto="100.00")])
        await _con_dueno(base)
        _con_lector(monkeypatch, [_senales(cuentas=[CUENTA_A], montos=["999,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        with pytest.raises(ValueError):
            await lotes.cerrar(base, lote_id, quien=Jefe())
    _correr(caso())


def test_NO_CIERRA_UN_LOTE_CON_UNA_ORDEN_QUE_NO_SABE_ASENTAR(base, monkeypatch):
    """BTC→VES entra en un lote pero vive en otra colección y se asienta por
    otra ruta. Antes que hacerlo mal en silencio, se niega y la nombra."""
    async def caso():
        lote_id = await _lote_listo(base, monkeypatch, cuantas=1)
        await base[lotes.COLECCION].update_one(
            {"lote_id": lote_id},
            {"$set": {"ordenes.0.flujo": "btc_ves"}})

        with pytest.raises(ValueError) as e:
            await lotes.cerrar(base, lote_id, quien=Jefe())
        assert "su tarjeta" in str(e.value), "tiene que decir qué hacer"
    _correr(caso())


# ══════════════════════════════════════════════════════════════════════════
# 3. La orden que no se pagó vuelve a la cola
# ══════════════════════════════════════════════════════════════════════════

def test_DEVOLVER_UNA_ORDEN_LA_SACA_DEL_LOTE_Y_LA_DEJA_PENDIENTE(base, monkeypatch):
    """Es la salida de la orden que el banco rechazó: sin ella el lote no se
    podía cerrar nunca, esperando un comprobante que no iba a llegar."""
    async def caso():
        ordenes = [_orden(0, cuenta=CUENTA_A), _orden(1, cuenta=CUENTA_B)]
        lote_id = await _lote_con(base, ordenes)
        await _con_dueno(base)
        _con_lector(monkeypatch, [_senales(cuentas=[CUENTA_A], montos=["100,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        await lotes.devolver_una(base, lote_id, "tx_0001",
                                 "el banco la rechazó", quien=Jefe())

        tx = await base.transactions.find_one({"transaction_id": "tx_0001"})
        assert tx["estado_admin"] == "pendiente"
        assert tx["lote_id"] is None
        assert tx["status"] == "pending", "vuelve a la cola, no queda pagada"

        vista = await cmp.listar(base, lote_id)
        assert [o["orden_id"] for o in vista["ordenes"]] == ["tx_0000"]
    _correr(caso())


def test_DEVUELTA_LA_QUE_FALTABA_EL_LOTE_YA_CIERRA(base, monkeypatch):
    """El camino completo: lo que no se pagó sale, y el resto se asienta."""
    async def caso():
        ordenes = [_orden(0, cuenta=CUENTA_A), _orden(1, cuenta=CUENTA_B)]
        lote_id = await _lote_con(base, ordenes)
        await _con_dueno(base)
        _con_lector(monkeypatch, [_senales(cuentas=[CUENTA_A], montos=["100,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        await lotes.devolver_una(base, lote_id, "tx_0001", "cuenta cerrada",
                                 quien=Jefe())
        resultado = await lotes.cerrar(base, lote_id, quien=Jefe())

        assert resultado["asentadas"] == 1
        assert await lotes.abiertos(base) == []
    _correr(caso())


def test_DEVOLVER_SIN_MOTIVO_NO_SE_PUEDE(base, monkeypatch):
    """Devolver una orden es decir «esta se vuelve a pagar». Si resulta que sí
    se había pagado, se paga dos veces: el motivo obliga a pensarlo."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0, cuenta=CUENTA_A)])
        await _con_dueno(base)

        for vacio in ("", "   ", "no"):
            with pytest.raises(ValueError):
                await lotes.devolver_una(base, lote_id, "tx_0000", vacio,
                                         quien=Jefe())

        tx = await base.transactions.find_one({"transaction_id": "tx_0000"})
        assert tx["estado_admin"] == lotes.EN_LOTE, "sigue en el lote"
    _correr(caso())


def test_NO_SE_DEVUELVE_UNA_ORDEN_QUE_TIENE_COMPROBANTE(base, monkeypatch):
    """Tiene la prueba de que se pagó. Devolverla la haría pagar dos veces.

    Si la foto está mal, primero se descarta la foto —y eso deja su propia
    línea— y recién entonces se puede devolver la orden.
    """
    async def caso():
        lote_id = await _lote_listo(base, monkeypatch, cuantas=1)

        with pytest.raises(ValueError) as e:
            await lotes.devolver_una(base, lote_id, "tx_0000", "me confundí",
                                     quien=Jefe())
        assert "descartalo primero" in str(e.value)

        tx = await base.transactions.find_one({"transaction_id": "tx_0000"})
        assert tx["estado_admin"] == lotes.EN_LOTE
    _correr(caso())


def test_DEVOLVER_QUEDA_EN_LA_AUDITORIA(base, monkeypatch):
    """Cambia lo que el cliente va a ver de su envío: tiene que asentarse."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0, cuenta=CUENTA_A)])
        await _con_dueno(base)
        await lotes.devolver_una(base, lote_id, "tx_0000",
                                 "el banco la rechazó", quien=Jefe())

        linea = await base.auditoria.find_one(
            {"accion": "dinero.lote_orden_devuelta"})
        assert linea is not None
        assert linea["detalle"]["motivo"] == "el banco la rechazó"
    _correr(caso())


# ══════════════════════════════════════════════════════════════════════════
# 4. El registro de un pago, que ahora comparten los dos caminos
# ══════════════════════════════════════════════════════════════════════════

def test_ASENTAR_DOS_VECES_LA_MISMA_ORDEN_SOLO_CUENTA_UNA(base, monkeypatch, sin_avisos):
    """Dos agentes con la misma orden abierta. La condición va DENTRO de la
    escritura: la base decide quién llegó primero y el segundo se entera porque
    no modificó nada. Sin eso caben dos avisos y dos consumos de cupo."""
    async def caso():
        await base.transactions.insert_one({
            "transaction_id": "tx_solo", "type": "withdrawal",
            "status": "pending", "user_id": "u1", "display_id": "#000900"})
        tx = await base.transactions.find_one({"transaction_id": "tx_solo"})

        primera = await registro_del_pago.registrar(base, tx, quien=Jefe())
        segunda = await registro_del_pago.registrar(base, tx, quien=Jefe())

        assert primera is True
        assert segunda is False, "la segunda no asienta nada"
        assert len(sin_avisos) == 1
        assert await base.auditoria.count_documents(
            {"accion": "dinero.retiro_aprobado"}) == 1
    _correr(caso())


def test_ASENTAR_NO_PISA_LOS_COMPROBANTES_QUE_YA_TENIA(base, monkeypatch):
    """En el camino del lote las fotos ya se colgaron de la orden cuando se
    adjudicaron. Pisarlas con una lista vacía borraría la prueba del pago."""
    async def caso():
        await base.transactions.insert_one({
            "transaction_id": "tx_conf", "type": "withdrawal",
            "status": "pending", "user_id": "u1",
            "proof_images": ["data:image/png;base64,YQ=="]})
        tx = await base.transactions.find_one({"transaction_id": "tx_conf"})

        await registro_del_pago.registrar(base, tx, quien=Jefe())

        guardada = await base.transactions.find_one({"transaction_id": "tx_conf"})
        assert guardada["proof_images"] == ["data:image/png;base64,YQ=="]
    _correr(caso())
