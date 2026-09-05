"""
tests/test_cotizacion_btc.py — Sin cotización no se cobra.

LA DECISION QUE ESTE ARCHIVO SOSTIENE

    Es del operador, y está escrita con sus palabras: «mejor que falle por
    error de cálculo en la tasa; asumir representa perder o ganar dinero y
    quiero ser lo más justo posible».

QUE HABIA ANTES

    Dos números escritos a mano en el camino que cobra:

      · `_btc_price_cache` arrancaba en 58 500 USD. Si el primer pedido al
        proveedor de precio fallaba, se cobraba con esa cifra. Con el bitcoin
        cerca de 79 000, el cliente pagaba un 36 % de más en bitcoin.

      · `_get_tasa_ves()` devolvía 680.0 cuando faltaba la configuración. Si
        la real fuera 270, a cada beneficiario se le prometían dos veces y
        media los bolívares que corresponden, y la diferencia la pone el
        operador.

    Los dos fallan hacia un lado distinto, y ninguno de los dos hacía ruido:
    la remesa se emitía, el cliente pagaba, y el número estaba mal.

POR QUE UN TEST Y NO UN COMENTARIO

    Un valor por defecto se agrega para «que no se rompa mientras carga», con
    la mejor intención, y no rompe nada — por eso vuelve. Lo único que lo
    frena es que algo se ponga en rojo cuando aparece.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from fastapi import HTTPException  # noqa: E402

from routes import btc_lightning as btc  # noqa: E402


def _recien():
    return datetime.now(timezone.utc) - timedelta(minutes=5)


def corre(coro):
    """Este repositorio no usa pytest-asyncio: corre las corrutinas a mano.

    Se sigue la convención que ya está en el resto de los tests. Traer una
    dependencia nueva para escribir `async def test_` es cambiarle las reglas
    a la suite entera por comodidad de un archivo.
    """
    return asyncio.run(coro)


class _Config:
    """La colección `config`, con lo justo para estas preguntas."""

    def __init__(self, doc):
        self._doc = doc

    async def find_one(self, _filtro):
        return self._doc


class _Base:
    def __init__(self, doc=None):
        self.config = _Config(doc)


@pytest.fixture(autouse=True)
def _caché_limpio():
    """Cada test arranca sin precio guardado.

    El caché es de módulo: sin esto, un test que guarda un precio se lo deja
    puesto al siguiente y los resultados dependen del orden. Es la clase de
    test que enseña a desconfiar de la suite y no del código.
    """
    previo = dict(btc._btc_price_cache)
    btc._btc_price_cache["price"] = None
    btc._btc_price_cache["updated_at"] = None
    yield
    btc._btc_price_cache.update(previo)


# ══════════════════════════════════════════════════════════════════════════
# La tasa
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("doc, porque", [
    (None, "no hay configuración"),
    ({"valor": None, "updated_at": _recien()}, "está guardada en nulo"),
    ({"valor": 0, "updated_at": _recien()}, "es cero, y con cero el beneficiario recibe nada"),
    ({"valor": -5, "updated_at": _recien()}, "es negativa"),
    ({"valor": "ochenta", "updated_at": _recien()}, "no es un número"),
])
def test_la_tasa_es_none_cuando_no_se_puede_confiar(monkeypatch, doc, porque):
    monkeypatch.setattr(btc, "db", _Base(doc))
    assert corre(btc._get_tasa_ves()) is None, (
        f"La tasa {porque} y aun así se devolvió un número. Cualquier número "
        "que salga de acá se usa para cobrarle a una persona.")


def test_la_tasa_configurada_se_devuelve_tal_cual(monkeypatch):
    monkeypatch.setattr(btc, "db", _Base({"valor": 268.4, "updated_at": _recien()}))
    assert corre(btc._get_tasa_ves()) == 268.4


# ══════════════════════════════════════════════════════════════════════════
# El precio
# ══════════════════════════════════════════════════════════════════════════

def _proveedor_caido(monkeypatch):
    class _Cliente:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def get(self, *_a, **_k):
            raise OSError("el proveedor no contesta")

    monkeypatch.setattr(btc.httpx, "AsyncClient", lambda **_k: _Cliente())


def test_sin_proveedor_y_sin_precio_guardado_no_hay_precio(monkeypatch):
    _proveedor_caido(monkeypatch)
    assert corre(btc._get_btc_price()) is None


def test_un_precio_dentro_del_limite_sirve_cuando_el_proveedor_no_contesta(monkeypatch):
    """No se castiga un tropiezo del proveedor: adentro del límite, sirve.

    Las dos edades se calculan A PARTIR de `EDAD_MAXIMA_DEL_PRECIO` y no con
    minutos escritos a mano. Ya pasó: el límite bajó de diez minutos a treinta
    segundos y este test, que tenía «dos minutos» escrito, se puso rojo por el
    cambio de política y no por un error. Un test que hay que editar cada vez
    que se ajusta un número termina editado sin pensar.
    """
    _proveedor_caido(monkeypatch)
    btc._btc_price_cache["price"] = 79679.78
    btc._btc_price_cache["updated_at"] = (
        datetime.now(timezone.utc) - btc.EDAD_MAXIMA_DEL_PRECIO / 2)
    assert corre(btc._get_btc_price()) == 79679.78


def test_un_precio_viejo_no_sirve_para_cobrar(monkeypatch):
    """El bitcoin se mueve. Cobrar con la cifra de hace horas es cobrar mal."""
    _proveedor_caido(monkeypatch)
    btc._btc_price_cache["price"] = 58500.0
    btc._btc_price_cache["updated_at"] = (
        datetime.now(timezone.utc) - btc.EDAD_MAXIMA_DEL_PRECIO - timedelta(seconds=1))
    assert corre(btc._get_btc_price()) is None


def test_el_cache_no_arranca_con_un_precio_escrito_a_mano():
    """La regresión exacta: el caché arrancaba en 58 500.

    Se mira el archivo y no la variable, porque la variable la deja limpia el
    fixture de este mismo archivo. Lo que hay que impedir es que alguien
    vuelva a escribir un número en la línea que lo declara.
    """
    fuente = open(btc.__file__, encoding="utf-8").read()
    linea = next(l for l in fuente.splitlines() if l.startswith("_btc_price_cache"))
    assert '"price": None' in linea, (
        f"El caché del precio arranca con un valor: {linea.strip()}\n"
        "Si el proveedor falla en el primer pedido, ese número se usa para "
        "cobrar una remesa real y nadie se entera.")


# ══════════════════════════════════════════════════════════════════════════
# El camino que mueve la plata
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("precio, tasa, falta", [
    (None, 268.4, "el precio"),
    (79679.78, None, "la tasa"),
    (None, None, "las dos"),
])
def test_sin_cotizacion_completa_el_cobro_no_se_emite(monkeypatch, precio, tasa, falta):
    async def _precio():
        return precio

    async def _tasa():
        return tasa

    monkeypatch.setattr(btc, "_get_btc_price", _precio)
    monkeypatch.setattr(btc, "_get_tasa_ves", _tasa)

    with pytest.raises(HTTPException) as e:
        corre(btc._cotizacion_o_error())
    assert e.value.status_code == 503, f"Falta {falta} y no se cortó con 503."
    # El mensaje lo lee una persona que está por mandar plata: tiene que decir
    # qué pasó y qué hacer, no un código.
    assert "tasa estimada" in e.value.detail and "de nuevo" in e.value.detail


def test_con_cotizacion_completa_devuelve_las_dos_cifras(monkeypatch):
    async def _precio():
        return 79679.78

    async def _tasa():
        return 268.4

    monkeypatch.setattr(btc, "_get_btc_price", _precio)
    monkeypatch.setattr(btc, "_get_tasa_ves", _tasa)
    assert corre(btc._cotizacion_o_error()) == (79679.78, 268.4)


def test_generar_invoice_usa_la_cotizacion_que_corta():
    """Que el camino del cobro pase por el guardián, y no alrededor.

    Sin esto, alguien puede agregar mañana otra ruta que cobre llamando a
    `_get_btc_price()` directo, y los tests de arriba seguirían verdes.
    """
    fuente = open(btc.__file__, encoding="utf-8").read()
    cuerpo = fuente[fuente.index('@router.post("/generar-invoice"'):]
    cuerpo = cuerpo[:cuerpo.index("\n@router.")] if "\n@router." in cuerpo else cuerpo

    assert "_cotizacion_o_error()" in cuerpo, (
        "El camino que emite el cobro dejó de usar `_cotizacion_o_error()`.")
    assert "_get_btc_price()" not in cuerpo and "_get_tasa_ves()" not in cuerpo, (
        "El camino que emite el cobro está leyendo el precio o la tasa por su "
        "cuenta. Esas funciones pueden devolver None, y ese None terminaría "
        "multiplicando el monto que paga una persona.")


def test_el_endpoint_publico_dice_que_no_hay_en_vez_de_inventar(monkeypatch):
    async def _nada():
        return None

    monkeypatch.setattr(btc, "_get_btc_price", _nada)
    monkeypatch.setattr(btc, "_get_tasa_ves", _nada)
    # El endpoint también lee la fecha de la tasa, así que necesita una base.
    monkeypatch.setattr(btc, "db", _Base(None))

    r = corre(btc.get_precio_btc())
    assert r["precio_btc"] is None and r["tasa_btc_ves"] is None
    assert r["tasa_actualizada_en"] is None
    assert r["disponible"] is False, (
        "La pantalla decide con `disponible` si puede convertir. Sin ese "
        "campo en falso, muestra una conversión que no tiene respaldo.")


# ══════════════════════════════════════════════════════════════════════════
# La antigüedad de la tasa
# ══════════════════════════════════════════════════════════════════════════
#
# El precio de Bitcoin se pide en vivo en cada consulta, así que no envejece.
# La tasa USDI → VES sí: se escribe A MANO desde el panel. El raspador del BCV
# —que sí corre solo— escribe `bcv_rates`, otra colección, que nadie conecta
# con esta clave. Se comprobó leyendo el planificador.
#
# O sea que el modo de fallar más probable no es que la tasa falte: es que
# nadie la toque durante semanas y el sistema siga prometiendo bolívares con
# la de hace un mes. Eso es exactamente asumir.

def test_una_tasa_vieja_no_sirve_para_prometer_bolivares(monkeypatch):
    vieja = datetime.now(timezone.utc) - btc.EDAD_MAXIMA_DE_LA_TASA - timedelta(hours=1)
    monkeypatch.setattr(btc, "db", _Base({"valor": 268.4, "updated_at": vieja}))
    assert corre(btc._get_tasa_ves()) is None, (
        "Se cotizó con una tasa más vieja que el límite. El valor sigue ahí "
        "porque nadie lo borró, no porque siga siendo cierto.")


def test_una_tasa_de_hoy_sirve(monkeypatch):
    monkeypatch.setattr(btc, "db", _Base({
        "valor": 268.4,
        "updated_at": datetime.now(timezone.utc) - timedelta(hours=3),
    }))
    assert corre(btc._get_tasa_ves()) == 268.4


def test_una_fecha_sin_zona_horaria_no_hace_estallar_el_calculo(monkeypatch):
    """Mongo puede devolver la fecha sin zona: restarla así explota.

    `TypeError: can't subtract offset-naive and offset-aware datetimes`. No
    sería un número mal calculado sino un 500 en el camino del cobro, que es
    otra forma de romper el envío.
    """
    monkeypatch.setattr(btc, "db", _Base({
        "valor": 268.4,
        "updated_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1),
    }))
    assert corre(btc._get_tasa_ves()) == 268.4


def test_una_tasa_sin_fecha_se_acepta_una_vez_y_se_grita(monkeypatch, caplog):
    """La concesión, y por qué existe.

    Las tasas guardadas antes de que se sellara la hora no la tienen. Cortar
    ahí dejaría los envíos parados en el momento de desplegar esto, por un dato
    viejo y no por una tasa mala. Se acepta y se registra un error: con que el
    operador vuelva a guardarla desde el panel, queda sellada.

    Si esto se convierte en la puerta de siempre —alguien escribe la tasa sin
    fecha— el registro lo va a estar diciendo en cada consulta.
    """
    import logging
    monkeypatch.setattr(btc, "db", _Base({"valor": 268.4}))
    with caplog.at_level(logging.ERROR):
        assert corre(btc._get_tasa_ves()) == 268.4
    assert any("fecha de actualización" in m for m in caplog.messages), (
        "Se aceptó una tasa sin fecha y no quedó registrado. Una concesión "
        "silenciosa es indistinguible de un olvido.")


def test_el_endpoint_publico_muestra_desde_cuando_es_la_tasa(monkeypatch):
    """Un control que corta sin decir desde cuándo obliga a adivinar."""
    cuando = datetime.now(timezone.utc) - timedelta(hours=2)
    monkeypatch.setattr(btc, "db", _Base({"valor": 268.4, "updated_at": cuando}))

    async def _precio():
        return 79679.78

    monkeypatch.setattr(btc, "_get_btc_price", _precio)
    r = corre(btc.get_precio_btc())
    assert r["tasa_actualizada_en"] == cuando
    assert r["disponible"] is True


def test_el_limite_del_precio_es_de_segundos_y_no_de_minutos():
    """La decisión del operador, escrita donde se rompe si alguien la afloja.

    «El bitcoin es muy volátil»: el precio guardado vale medio minuto. El
    número puede ajustarse —treinta segundos no es sagrado— pero volver a los
    diez minutos sería deshacer la decisión, y eso tiene que costar cambiar un
    test a propósito y no editar una constante de paso.
    """
    assert btc.EDAD_MAXIMA_DEL_PRECIO <= timedelta(minutes=1), (
        f"El precio guardado vale {btc.EDAD_MAXIMA_DEL_PRECIO}. Se fijó en "
        "medio minuto porque el bitcoin se mueve y cobrar con una cifra vieja "
        "es cobrar mal, para un lado o para el otro.")
    assert btc.EDAD_MAXIMA_DEL_PRECIO >= timedelta(seconds=15), (
        "Menos de quince segundos es menos que el intervalo con que la "
        "pantalla consulta: sería no tolerar ni un tropiezo del proveedor.")
