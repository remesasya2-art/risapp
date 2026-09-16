"""
Qué tan bien viene adjudicando el lector, contado de forma que no adule.

POR QUE ESTE ARCHIVO EXISTE

    El lector estuvo roto en producción y nadie se enteró hasta que el agente
    venía asignando cada foto a mano y lo mencionó al pasar. No había ningún
    número que lo dijera.

    Pero un contador mal hecho es peor que ninguno, porque se le cree. Este
    archivo vigila las cuatro formas que tiene de mentir:

    1.  CONTAR LOTES ABIERTOS. Sus fotos todavía no las revisó nadie. Contarlas
        le da por buena al lector cada foto recién subida sólo porque aún no
        llegó quien la iba a corregir.

    2.  PERDER LOS ERRORES. Cuando el lector daba una foto por segura y estaba
        mal, la persona la soltaba y el estado pasaba a `sin_adjudicar` — el
        MISMO que cuando el lector no supo decidir. El peor error quedaba
        anotado como una abstención honesta. Por eso existen
        `estado_del_lector` y `orden_del_lector`, y por eso la mitad de este
        archivo comprueba que nadie los pise.

    3.  MEZCLAR EL LECTOR AUSENTE CON EL LECTOR FALLANDO. Las fotos subidas sin
        lector no son errores de nadie; en el denominador hunden el porcentaje
        sin que haya pasado nada malo.

    4.  FINGIR QUE CUENTA LAS VIEJAS. Las fotos anteriores a este cambio no
        tienen veredicto guardado. Se dicen aparte en vez de esconderlas.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

# Los ayudantes viven en el archivo de los comprobantes: un lote con sus fotos
# es el punto de partida de todo esto, y copiarlos los dejaría desincronizados
# en la primera corrección.
from test_comprobantes_del_lote import (                             # noqa: E402
    Jefe, _con_lector, _correr, _foto, _lote_con, _orden, _senales)

from conftest import usar_base                                       # noqa: E402
from services import comprobantes_del_lote as cmp                    # noqa: E402
from services import desempeno_del_lector as desempeno               # noqa: E402
from services import lotes_de_pago as lotes                          # noqa: E402
from services import registro_del_pago                               # noqa: E402

CUENTA_A = "01340219112191046516"
CUENTA_B = "01020121710106529080"

AHORA = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test_desempeno"]
    usar_base(b)
    return b


@pytest.fixture(autouse=True)
def sin_avisos(monkeypatch):
    """Cerrar un lote le avisa al cliente. Ese camino se prueba en su archivo."""
    async def _falso(**kwargs):
        return None

    monkeypatch.setattr(registro_del_pago, "create_notification", _falso)


# ─── Un lote cerrado armado a mano ────────────────────────────────────────
#
# Para las reglas del conteo se siembra el documento directo: el camino
# completo —cargar, corregir, cerrar— tiene su propio test al final, y pasar
# por él en cada caso haría un archivo lento que prueba veinte veces lo mismo.

def _foto_de(veredicto, eligio=None, quedo="MISMO", hace_minutos=0):
    """Una foto ya procesada. `quedo="MISMO"` = nadie la tocó."""
    return {
        "comprobante_id": f"cmp_{veredicto}_{hace_minutos}",
        "estado_del_lector": veredicto,
        "orden_del_lector": eligio,
        "orden_id": eligio if quedo == "MISMO" else quedo,
        "subido_en": AHORA - timedelta(minutes=hace_minutos),
    }


def _foto_vieja(hace_minutos=0):
    """Una de antes de este cambio: sin veredicto guardado."""
    return {"comprobante_id": f"cmp_vieja_{hace_minutos}",
            "orden_id": "tx_0000",
            "subido_en": AHORA - timedelta(minutes=hace_minutos)}


async def _sembrar_lote(base, fotos, *, estado=None, numero="L-00001",
                        hace_minutos=0):
    await base[lotes.COLECCION].insert_one({
        "lote_id": f"lote_{numero}",
        "numero": numero,
        "estado": estado or lotes.CERRADO,
        "cerrado_en": AHORA - timedelta(minutes=hace_minutos),
        "ordenes": [],
        "comprobantes": fotos,
    })


def _medir(base, fotos=None, **kw):
    async def hacerlo():
        if fotos is not None:
            await _sembrar_lote(base, fotos, **kw)
        return await desempeno.medir(base)
    return _correr(hacerlo())


# ══════════════════════════════════════════════════════════════════════════
# 1. Que nadie pise lo que dijo el lector. Es lo que hace posible el número.
# ══════════════════════════════════════════════════════════════════════════

async def _lote_con_una_segura(base, monkeypatch):
    """Un lote abierto con una foto que el lector adjudicó con seguridad."""
    ordenes = [_orden(0, cuenta=CUENTA_A, monto="100.00"),
               _orden(1, cuenta=CUENTA_B, monto="200.00")]
    lote_id = await _lote_con(base, ordenes)
    await base.transactions.update_many(
        {"user_id": {"$exists": False}}, {"$set": {"user_id": "u_cliente"}})
    _con_lector(monkeypatch, [_senales(cuentas=[CUENTA_A], montos=["100,00"])])
    salida = await cmp.cargar(base, lote_id, [_foto((30, 30, 30))], quien=Jefe())
    assert salida["comprobantes"][0]["estado"] == cmp.SEGURO
    return lote_id, salida["comprobantes"][0]["comprobante_id"]


async def _la_foto(base, lote_id):
    lote = await base[lotes.COLECCION].find_one({"lote_id": lote_id})
    return lote["comprobantes"][0]


def test_mover_la_foto_a_otra_orden_no_pisa_lo_que_dijo_el_lector(base, monkeypatch):
    """El error del lector tiene que quedar visible después de corregirlo.

    Antes de esto, corregirlo lo borraba: `estado` pasaba a `a_mano` y no
    quedaba rastro de que el lector se había declarado seguro.
    """
    async def hacerlo():
        lote_id, foto_id = await _lote_con_una_segura(base, monkeypatch)
        await cmp.asignar(base, lote_id, foto_id, "tx_0001", quien=Jefe())
        return await _la_foto(base, lote_id)

    foto = _correr(hacerlo())
    assert foto["estado"] == cmp.A_MANO, "el estado sí cambia: así quedó"
    assert foto["estado_del_lector"] == cmp.SEGURO, "lo que dijo el lector se pisó"
    assert foto["orden_del_lector"] == "tx_0000", "la orden que eligió se pisó"


def test_soltar_la_foto_no_pisa_lo_que_dijo_el_lector(base, monkeypatch):
    """El caso que borraba la evidencia: soltarla deja `sin_adjudicar`.

    Que es el mismo estado que «el lector no supo». Sin `estado_del_lector`,
    este error se cuenta como una abstención.
    """
    async def hacerlo():
        lote_id, foto_id = await _lote_con_una_segura(base, monkeypatch)
        await cmp.asignar(base, lote_id, foto_id, None, quien=Jefe())
        return await _la_foto(base, lote_id)

    foto = _correr(hacerlo())
    assert foto["estado"] == cmp.SIN_ADJUDICAR
    assert foto["estado_del_lector"] == cmp.SEGURO
    assert foto["orden_del_lector"] == "tx_0000"


def test_descartar_la_foto_no_pisa_lo_que_dijo_el_lector(base, monkeypatch):
    async def hacerlo():
        lote_id, foto_id = await _lote_con_una_segura(base, monkeypatch)
        await cmp.descartar(base, lote_id, foto_id, "foto repetida", quien=Jefe())
        return await _la_foto(base, lote_id)

    foto = _correr(hacerlo())
    assert foto["estado"] == cmp.DESCARTADO
    assert foto["estado_del_lector"] == cmp.SEGURO
    assert foto["orden_del_lector"] == "tx_0000"


# ══════════════════════════════════════════════════════════════════════════
# 2. Que el informe cuente lo que dice contar.
# ══════════════════════════════════════════════════════════════════════════

def test_una_foto_que_nadie_toco_cuenta_como_resuelta(base):
    r = _medir(base, [_foto_de(cmp.SEGURO, "tx_0000")])
    assert (r["miradas"], r["resueltas"], r["corregidas"]) == (1, 1, 0)


def test_una_foto_que_movieron_a_otra_orden_cuenta_como_corregida(base):
    r = _medir(base, [_foto_de(cmp.SEGURO, "tx_0000", quedo="tx_0009")])
    assert (r["resueltas"], r["corregidas"]) == (1, 1)


def test_una_foto_que_soltaron_cuenta_como_corregida(base):
    r = _medir(base, [_foto_de(cmp.SEGURO, "tx_0000", quedo=None)])
    assert (r["resueltas"], r["corregidas"]) == (1, 1)


def test_avisar_que_el_monto_no_coincide_no_cuenta_como_error(base):
    """`revisar` es el lector trabajando bien: encontró a la persona y avisó.

    Contarlo como fallo castigaría justo la parte que evita asentar un pago
    por un importe que nadie comparó.
    """
    r = _medir(base, [_foto_de(cmp.REVISAR, "tx_0000")])
    assert r["avisadas"] == 1
    assert (r["resueltas"], r["corregidas"], r["no_pudo"]) == (0, 0, 0)


@pytest.mark.parametrize("veredicto",
                         [cmp.AMBIGUO, cmp.REPETIDO, cmp.SIN_ADJUDICAR])
def test_lo_que_el_lector_no_pudo_decidir_va_a_su_renglon(base, veredicto):
    r = _medir(base, [_foto_de(veredicto, None)])
    assert r["no_pudo"] == 1
    assert (r["resueltas"], r["avisadas"]) == (0, 0)


def test_los_tres_renglones_suman_exactamente_las_miradas(base):
    """Si dejan de sumar, hay un veredicto que el informe no sabe dónde poner."""
    r = _medir(base, [
        _foto_de(cmp.SEGURO, "tx_0000", hace_minutos=1),
        _foto_de(cmp.REVISAR, "tx_0001", hace_minutos=2),
        _foto_de(cmp.AMBIGUO, None, hace_minutos=3),
        _foto_de(cmp.SIN_ADJUDICAR, None, hace_minutos=4),
    ])
    assert r["resueltas"] + r["avisadas"] + r["no_pudo"] == r["miradas"] == 4


# ══════════════════════════════════════════════════════════════════════════
# 3. Lo que queda afuera del denominador, que es donde un contador miente.
# ══════════════════════════════════════════════════════════════════════════

def test_un_lote_abierto_no_entra_en_el_informe(base):
    """Sus fotos no las revisó nadie todavía.

    Contarlas le daría por buena al lector cada foto recién subida sólo porque
    aún no llegó la persona que la iba a corregir, y el número saldría alto el
    día de la carga para bajar solo con los días.
    """
    r = _medir(base, [_foto_de(cmp.SEGURO, "tx_0000")], estado=lotes.ABIERTO)
    assert r["miradas"] == 0
    assert r["lotes"] == 0


def test_un_lote_cancelado_tampoco_entra(base):
    """Un lote cancelado se abandonó: nadie terminó de mirar sus fotos."""
    r = _medir(base, [_foto_de(cmp.SEGURO, "tx_0000")], estado=lotes.CANCELADO)
    assert r["miradas"] == 0


def test_las_fotos_subidas_sin_lector_no_hunden_el_porcentaje(base):
    """El lector ausente no es el lector fallando. Van contadas aparte."""
    r = _medir(base, [_foto_de(cmp.SEGURO, "tx_0000", hace_minutos=1),
                      _foto_de(cmp.SIN_LECTOR, None, hace_minutos=2),
                      _foto_de(cmp.SIN_LECTOR, None, hace_minutos=3)])
    assert r["miradas"] == 1, "las de sin_lector entraron al denominador"
    assert r["resueltas"] == 1
    assert r["sin_lector"] == 2, "y tienen que quedar contadas: es la señal"


def test_las_fotos_anteriores_a_este_cambio_se_cuentan_aparte(base):
    """No tienen veredicto guardado. Esconderlas sería peor que admitirlo."""
    r = _medir(base, [_foto_de(cmp.SEGURO, "tx_0000", hace_minutos=1),
                      _foto_vieja(hace_minutos=2), _foto_vieja(hace_minutos=3)])
    assert r["miradas"] == 1
    assert r["de_antes"] == 2


# ══════════════════════════════════════════════════════════════════════════
# 4. La ventana.
# ══════════════════════════════════════════════════════════════════════════

def test_la_ventana_deja_afuera_las_mas_viejas(base, monkeypatch):
    monkeypatch.setattr(desempeno, "VENTANA", 3)
    r = _medir(base, [_foto_de(cmp.SEGURO, f"tx_{i}", hace_minutos=i)
                      for i in range(10)])
    assert r["miradas"] == 3


def test_la_ventana_no_la_llenan_las_de_sin_lector(base, monkeypatch):
    """Una semana con el lector caído dejaría el informe en blanco.

    Justo cuando hay algo que mirar: si las de `sin_lector` gastaran los
    lugares de la ventana, las que el lector sí juzgó quedarían afuera.
    """
    monkeypatch.setattr(desempeno, "VENTANA", 2)
    fotos = [_foto_de(cmp.SIN_LECTOR, None, hace_minutos=i) for i in range(20)]
    fotos += [_foto_de(cmp.SEGURO, f"tx_{i}", hace_minutos=100 + i)
              for i in range(2)]
    r = _medir(base, fotos)
    assert r["miradas"] == 2, "las de sin_lector gastaron lugares de la ventana"
    assert r["sin_lector"] == 20


def test_se_miran_los_lotes_mas_nuevos_primero(base, monkeypatch):
    """Con el tope de lotes puesto, los que se leen son los últimos."""
    monkeypatch.setattr(desempeno, "LOTES_A_LO_SUMO", 1)

    async def hacerlo():
        await _sembrar_lote(base, [_foto_de(cmp.SEGURO, "tx_0000")],
                            numero="L-VIEJO", hace_minutos=5000)
        await _sembrar_lote(base, [_foto_de(cmp.AMBIGUO, None)],
                            numero="L-NUEVO", hace_minutos=1)
        return await desempeno.medir(base)

    r = _correr(hacerlo())
    assert (r["lotes"], r["no_pudo"], r["resueltas"]) == (1, 1, 0)


# ══════════════════════════════════════════════════════════════════════════
# 5. Que no rompa nada. Es un número en una pantalla, no un pago.
# ══════════════════════════════════════════════════════════════════════════

def test_sin_lotes_cerrados_el_informe_sale_vacio(base):
    r = _medir(base)
    assert (r["miradas"], r["lotes"], r["desde"]) == (0, 0, None)


def test_una_foto_sin_fecha_no_vacia_el_informe(base):
    """El defecto que destapó la mutación, y que estuvo escrito y en verde.

    El respaldo para una foto sin fecha era una fecha CON zona horaria, y todas
    las demás llegan SIN zona —el driver las devuelve así—. Compararlas en el
    ordenamiento levanta TypeError, y acá ese error lo atrapa el `except` de
    `medir`: el informe entero salía vacío, en silencio, porque a una sola foto
    le faltaba la fecha.
    """
    sin_fecha = _foto_de(cmp.SEGURO, "tx_0000", hace_minutos=1)
    del sin_fecha["subido_en"]
    r = _medir(base, [sin_fecha, _foto_de(cmp.SEGURO, "tx_0001", hace_minutos=2)])
    assert r["miradas"] == 2, "una foto sin fecha vació el informe entero"
    assert r["resueltas"] == 2


def test_la_foto_sin_fecha_queda_ultima_y_no_primera(base, monkeypatch):
    """Sin fecha no puede ganarle a una foto de hoy por el lugar en la ventana."""
    monkeypatch.setattr(desempeno, "VENTANA", 1)
    sin_fecha = _foto_de(cmp.AMBIGUO, None, hace_minutos=1)
    del sin_fecha["subido_en"]
    r = _medir(base, [sin_fecha, _foto_de(cmp.SEGURO, "tx_0001", hace_minutos=2)])
    assert (r["miradas"], r["resueltas"]) == (1, 1)


def test_si_la_consulta_falla_el_informe_sale_vacio_y_no_revienta():
    class BaseRota:
        def __getitem__(self, _nombre):
            raise RuntimeError("la base no contesta")

    r = _correr(desempeno.medir(BaseRota()))
    assert r["miradas"] == 0, "un contador roto no puede tumbar la pantalla"


# ══════════════════════════════════════════════════════════════════════════
# 6. El camino completo, por las funciones de verdad.
# ══════════════════════════════════════════════════════════════════════════

def test_el_camino_completo_desde_la_carga_hasta_el_informe(base, monkeypatch):
    """Cargar dos fotos, corregir una, cerrar el lote y medir.

    Los tests de arriba siembran el documento a mano para probar una regla por
    vez. Éste no: pasa por `cargar`, `asignar` y `cerrar` de verdad, que es lo
    único que demuestra que el veredicto del lector llega entero hasta el
    informe atravesando todo lo que una persona le hace en el medio.
    """
    async def hacerlo():
        ordenes = [_orden(0, cuenta=CUENTA_A, monto="100.00"),
                   _orden(1, cuenta=CUENTA_B, monto="100.00")]
        lote_id = await _lote_con(base, ordenes)
        await base.transactions.update_many(
            {"user_id": {"$exists": False}}, {"$set": {"user_id": "u_cliente"}})
        # La primera la adjudica bien; la segunda el lector la manda a la
        # orden EQUIVOCADA, que es el caso que hay que poder contar.
        _con_lector(monkeypatch, [
            _senales(cuentas=[CUENTA_A], montos=["100,00"]),
            _senales(cuentas=[CUENTA_A], montos=["100,00"]),
        ])
        salida = await cmp.cargar(
            base, lote_id, [_foto((30, 30, 30)), _foto((120, 60, 60))],
            quien=Jefe())
        # Las dos encajan con la misma orden: el lector no adjudica ninguna.
        # Una persona las reparte.
        for foto, orden in zip(salida["comprobantes"], ("tx_0000", "tx_0001")):
            await cmp.asignar(base, lote_id, foto["comprobante_id"], orden,
                              quien=Jefe())
        await lotes.cerrar(base, lote_id, quien=Jefe())
        return await desempeno.medir(base)

    r = _correr(hacerlo())
    assert r["lotes"] == 1
    assert r["miradas"] == 2
    # El lector no adjudicó ninguna: las dos encajaban con la misma orden.
    assert r["no_pudo"] == 2
    assert (r["resueltas"], r["corregidas"]) == (0, 0)
