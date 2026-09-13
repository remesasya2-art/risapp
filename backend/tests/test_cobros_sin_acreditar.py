"""
tests/test_cobros_sin_acreditar.py — Que el informe no mienta en ninguna dirección.

QUE SE VIGILA ACA

    Un informe sobre dinero tiene dos formas de hacer daño, y las dos importan
    igual:

      · Decir que no hay nada cuando hay alguien esperando su plata. Nadie
        vuelve a mirar una pantalla que siempre está vacía.
      · Llenarse de filas que no son plata perdida. Un informe con ruido se
        deja de leer igual de rápido, y encima manda a revisar cuentas sanas.

    De ahí que la mitad de estos tests comprueben que algo NO aparece.

Y LA PIEZA QUE NINGUN TEST DEBERIA DEJAR PASAR

    En PIX hay dos identificadores para el mismo pago: el interno (`gpix_...`),
    que es el que el libro mayor anota, y el de Mercado Pago, que es el único
    por el que Mercado Pago sabe contestar. Confundirlos da un informe que anda,
    no falla, no avisa, y está siempre vacío.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import ensenarle_decimal128_a_mongomock, usar_base    # noqa: E402
ensenarle_decimal128_a_mongomock()

from services import cobros_sin_acreditar                           # noqa: E402
from services.money import to_decimal128                            # noqa: E402

@pytest.fixture
def base():
    cliente = mongomock_motor.AsyncMongoMockClient()
    db = cliente["risapp_test_cobros"]
    usar_base(db)
    return db


def _correr(corrutina):
    return asyncio.run(corrutina)


# ─── Los dobles: un Mercado Pago que contesta lo que el test quiera ────────

class MercadoPagoDeMentira:
    """Contesta por identificador, y anota TODO lo que se le preguntó.

    Lo que se le preguntó es la mitad de lo que hay que comprobar: que el filtro
    contra el libro funcione se demuestra viendo que por esos pagos NO preguntó.
    """

    def __init__(self, respuestas, revientan=()):
        self.respuestas = respuestas
        self.revientan = set(revientan)
        self.preguntas = []

    async def __call__(self, id_de_pago):
        self.preguntas.append(id_de_pago)
        if id_de_pago in self.revientan:
            raise RuntimeError("la API de Mercado Pago no contestó")
        return self.respuestas.get(id_de_pago)


def _aprobado(monto="100.00", cuando="2026-09-01T10:00:00.000-04:00"):
    return {"status": "approved", "amount": float(monto), "date_approved": cuando,
            "status_detail": "accredited"}


def _rechazado():
    return {"status": "rejected", "amount": 100.0, "status_detail": "cc_rejected"}


# ─── Los datos ────────────────────────────────────────────────────────────

def _hace(dias):
    return datetime.now(timezone.utc) - timedelta(days=dias)


async def _pix(db, payment_id, mp_id, *, status="pending", dias=1,
               monto="100.00", cliente="Ana", decimal128=True):
    # El dinero se escribe como Decimal128 —como lo escribe la app en todo lo
    # demás— salvo cuando el test quiere probar a propósito el caso viejo de
    # float. Un test que escribe `100.0` a secas pasa con el producto roto.
    monto_guardado = to_decimal128(monto) if decimal128 else float(monto)
    await db.gestor_pix_payments.insert_one({
        "payment_id": payment_id,
        "mp_payment_id": mp_id,
        "client_name": cliente,
        "amount_ris": monto_guardado,
        "amount_brl": monto_guardado,
        "status": status,
        "created_at": _hace(dias),
        "gestor_id": "u_gestor",
        "gestor_name": "Gestor",
    })


async def _tarjeta(db, payment_id, *, status="approved", dias=1,
                   monto="250.00", cobrado=None, usuario="u_1"):
    """Una tarjeta. `monto` es el saldo que se acredita; `cobrado`, lo que se le
    cobró de verdad.

    Los dos son DISTINTOS a propósito, y en producción siempre lo son: lo que se
    le cobra al cliente es el saldo más la comisión de la pasarela. Cuando el
    test los ponía iguales, leer el campo equivocado daba el mismo número y la
    mutación sobrevivía.
    """
    await db.card_payments.insert_one({
        "payment_id": payment_id,
        "user_id": usuario,
        "amount_ris": to_decimal128(monto),
        "total_charged_brl": to_decimal128(cobrado if cobrado is not None else monto),
        "status": status,
        "status_detail": "accredited",
        "created_at": _hace(dias),
    })


async def _linea_del_libro(db, clase, referencia):
    await db.ledger.insert_one({
        "entry_id": f"le_{clase}_{referencia}",
        "book": "RIS",
        "reference": {"kind": clase, "id": referencia},
        "signed_amount": 100.0,
    })


# ─── Que mongomock esté mirando de verdad ─────────────────────────────────

def test_mongomock_conserva_el_decimal128_que_escriben_estos_tests(base):
    """La autocomprobación de siempre: si mongomock devolviera un float, todos
    los tests de plata de este archivo pasarían con el producto roto."""
    async def caso():
        await _pix(base, "gpix_1", "mp_1")
        doc = await base.gestor_pix_payments.find_one({"payment_id": "gpix_1"})
        from bson.decimal128 import Decimal128
        assert isinstance(doc["amount_brl"], Decimal128), (
            "mongomock devolvió %r: este archivo no está probando nada de lo "
            "que cree probar" % type(doc["amount_brl"]))
    _correr(caso())


# ─── El caso que da sentido a todo el módulo ──────────────────────────────

def test_un_pago_aprobado_sin_linea_en_el_libro_aparece_con_su_monto(base):
    async def caso():
        await _pix(base, "gpix_1", "mp_1", status="expired", monto="150.00")
        mp = MercadoPagoDeMentira({"mp_1": _aprobado("150.00")})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert r["cuantos"] == 1, r
        assert r["total_brl"] == "150.00"
        fila = r["cobros"][0]
        assert fila["pago"] == "gpix_1"
        assert fila["pago_en_mercadopago"] == "mp_1"
        assert fila["cliente"] == "Ana"
        assert fila["estado_en_la_app"] == "expired"
        assert fila["monto_en_mercadopago"] == "150.00"
        assert fila["monto_en_la_app"] == "150.00"
    _correr(caso())


def test_a_mercadopago_se_le_pregunta_por_SU_identificador_y_no_por_el_interno(base):
    """El del libro es el interno; el único que Mercado Pago conoce es el suyo.

    Preguntar por el interno no falla ni avisa: Mercado Pago contesta que no
    existe y el informe queda vacío para siempre.
    """
    async def caso():
        await _pix(base, "gpix_1", "mp_1")
        mp = MercadoPagoDeMentira({"mp_1": _aprobado()})
        await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert mp.preguntas == ["mp_1"], (
            "se le preguntó a Mercado Pago por %r" % mp.preguntas)
    _correr(caso())


# ─── Lo que NO tiene que aparecer ─────────────────────────────────────────

def test_un_pago_con_linea_en_el_libro_no_aparece_ni_se_consulta(base):
    """El libro es el juez, y además el filtro: preguntarle a Mercado Pago por
    un pago que el libro ya registra es una llamada de red al vacío."""
    async def caso():
        await _pix(base, "gpix_1", "mp_1")
        await _linea_del_libro(base, "pix_payment", "gpix_1")
        mp = MercadoPagoDeMentira({"mp_1": _aprobado()})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert r["cuantos"] == 0, r["cobros"]
        assert r["candidatos"] == 0
        assert mp.preguntas == [], mp.preguntas
    _correr(caso())


def test_la_linea_del_libro_tiene_que_ser_DE_ESE_pago(base):
    """Una línea que apunta a otro pago no acredita éste. Comparar sólo la clase
    —«hay líneas de pix_payment»— daría por cobrado todo lo que existe."""
    async def caso():
        await _pix(base, "gpix_1", "mp_1")
        await _linea_del_libro(base, "pix_payment", "gpix_OTRO")
        mp = MercadoPagoDeMentira({"mp_1": _aprobado()})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert r["cuantos"] == 1, r
    _correr(caso())


def test_la_linea_del_libro_tiene_que_ser_DEL_MISMO_MEDIO(base):
    """PIX y tarjeta pueden compartir identificador sin ser el mismo pago: uno
    lo pone Mercado Pago y el otro lo pone esta app."""
    async def caso():
        await _pix(base, "mismo_id", "mp_1")
        await _linea_del_libro(base, "card_payment", "mismo_id")
        mp = MercadoPagoDeMentira({"mp_1": _aprobado()})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert r["cuantos"] == 1, r
    _correr(caso())


def test_un_pago_que_mercadopago_rechazo_no_aparece(base):
    async def caso():
        await _pix(base, "gpix_1", "mp_1")
        mp = MercadoPagoDeMentira({"mp_1": _rechazado()})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert r["cuantos"] == 0, r["cobros"]
        assert r["sin_respuesta"] == 0
    _correr(caso())


def test_un_pago_sin_identificador_de_mercadopago_no_se_mira(base):
    """Si Mercado Pago nunca creó el pago, no hay plata que preguntar: el código
    QR no existió."""
    async def caso():
        await _pix(base, "gpix_1", None)
        await _pix(base, "gpix_2", "")
        mp = MercadoPagoDeMentira({})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert r["candidatos"] == 0, r
        assert mp.preguntas == []
    _correr(caso())


def test_lo_que_quedo_fuera_de_la_ventana_no_se_mira(base):
    async def caso():
        await _pix(base, "gpix_viejo", "mp_viejo", dias=40)
        await _pix(base, "gpix_nuevo", "mp_nuevo", dias=2)
        mp = MercadoPagoDeMentira({"mp_viejo": _aprobado(), "mp_nuevo": _aprobado()})
        r = await cobros_sin_acreditar.revisar(base, dias=30, preguntar=mp)
        assert mp.preguntas == ["mp_nuevo"], mp.preguntas
        assert r["cuantos"] == 1
    _correr(caso())


# ─── No saber no es estar bien ────────────────────────────────────────────

def test_si_mercadopago_no_contesta_no_se_cuenta_como_no_pagado(base):
    """`get_payment_status` devuelve `None` tanto si el pago no existe como si
    la consulta falló. Contar eso como «no se pagó» convierte una credencial
    vencida en una pantalla tranquilizadora."""
    async def caso():
        await _pix(base, "gpix_1", "mp_1")
        mp = MercadoPagoDeMentira({"mp_1": None})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert r["sin_respuesta"] == 1, r
        assert r["cuantos"] == 0
    _correr(caso())


def test_una_respuesta_sin_estado_tampoco_es_una_respuesta(base):
    async def caso():
        await _pix(base, "gpix_1", "mp_1")
        mp = MercadoPagoDeMentira({"mp_1": {"amount": 100.0}})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert r["sin_respuesta"] == 1, r
    _correr(caso())


def test_una_consulta_que_revienta_no_se_lleva_el_informe_entero(base):
    async def caso():
        await _pix(base, "gpix_1", "mp_malo", dias=3)
        await _pix(base, "gpix_2", "mp_bueno", dias=2, monto="70.00")
        mp = MercadoPagoDeMentira({"mp_bueno": _aprobado("70.00")},
                                  revientan=["mp_malo"])
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert r["sin_respuesta"] == 1, r
        assert r["cuantos"] == 1, r["cobros"]
        assert r["total_brl"] == "70.00"
    _correr(caso())


# ─── Los límites, y que se cuenten en voz alta ────────────────────────────

def test_el_tope_recorta_y_dice_cuantos_quedaron_sin_mirar(base):
    """Un recorte silencioso se lee igual que «no hay nada», y son cosas
    opuestas."""
    async def caso():
        for i in range(5):
            await _pix(base, f"gpix_{i}", f"mp_{i}", dias=10 - i)
        mp = MercadoPagoDeMentira({f"mp_{i}": _aprobado() for i in range(5)})
        r = await cobros_sin_acreditar.revisar(base, tope=2, preguntar=mp)
        assert r["candidatos"] == 5, r
        assert r["mirados"] == 2, r
        assert r["sin_mirar"] == 3, r
        assert len(mp.preguntas) == 2
    _correr(caso())


def test_lo_mas_viejo_se_mira_primero(base):
    """Un cobro sin acreditar sólo empeora con el tiempo, porque es alguien
    esperando. Si el tope recorta, lo que se sacrifica es lo más reciente."""
    async def caso():
        await _pix(base, "gpix_nuevo", "mp_nuevo", dias=1)
        await _pix(base, "gpix_viejo", "mp_viejo", dias=20)
        await _pix(base, "gpix_medio", "mp_medio", dias=10)
        mp = MercadoPagoDeMentira({})
        await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert mp.preguntas == ["mp_viejo", "mp_medio", "mp_nuevo"], mp.preguntas
    _correr(caso())


def test_los_limites_se_acotan_aunque_los_pidan_enormes(base):
    async def caso():
        mp = MercadoPagoDeMentira({})
        r = await cobros_sin_acreditar.revisar(base, dias=99999, tope=99999,
                                               preguntar=mp)
        assert r["dias"] == cobros_sin_acreditar.DIAS_MAXIMO, r["dias"]
        assert r["tope"] == cobros_sin_acreditar.TOPE_MAXIMO, r["tope"]
    _correr(caso())


def test_un_limite_que_no_es_un_numero_no_tumba_la_consulta(base):
    async def caso():
        mp = MercadoPagoDeMentira({})
        r = await cobros_sin_acreditar.revisar(base, dias="muchos", tope=None,
                                               preguntar=mp)
        assert r["dias"] == cobros_sin_acreditar.DIAS_POR_DEFECTO
        assert r["tope"] == cobros_sin_acreditar.TOPE_POR_DEFECTO
    _correr(caso())


# ─── Las dos listas ──────────────────────────────────────────────────────

def test_lo_que_la_app_ya_da_por_cobrado_va_en_la_otra_lista(base):
    """Mismo síntoma, problema distinto: ahí el cliente tiene su saldo y lo que
    falta es el asiento. Sumarlo al total de «plata que se debe» sería mandar a
    acreditar dos veces."""
    async def caso():
        await _pix(base, "gpix_deuda", "mp_deuda", status="pending",
                   monto="10.00", dias=3)
        await _pix(base, "gpix_asiento", "mp_asiento", status="paid",
                   monto="20.00", dias=2)
        mp = MercadoPagoDeMentira({"mp_deuda": _aprobado("10.00"),
                                   "mp_asiento": _aprobado("20.00")})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert [f["pago"] for f in r["cobros"]] == ["gpix_deuda"], r["cobros"]
        assert r["total_brl"] == "10.00"
        assert [f["pago"] for f in r["descuadres"]] == ["gpix_asiento"]
        assert r["cuantos_descuadres"] == 1
        assert r["total_descuadres_brl"] == "20.00"
    _correr(caso())


def test_una_tarjeta_aprobada_y_sin_asentar_es_un_descuadre_no_una_deuda(base):
    async def caso():
        await _tarjeta(base, "mp_card_1", status="approved",
                       monto="250.00", cobrado="262.50")
        mp = MercadoPagoDeMentira({"mp_card_1": _aprobado("262.50")})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert r["cuantos"] == 0, r["cobros"]
        assert r["cuantos_descuadres"] == 1, r
        fila = r["descuadres"][0]
        assert fila["medio"] == "Tarjeta"
        assert fila["cliente"] == "u_1"
        # Lo que se le COBRO, no el saldo que se le iba a acreditar. En la
        # tarjeta son dos números distintos —la comisión de la pasarela va en el
        # medio— y el que importa acá es el que salió de su cuenta.
        assert fila["monto_en_la_app"] == "262.50", fila
        assert fila["monto_en_mercadopago"] == "262.50", fila
    _correr(caso())


def test_las_dos_colecciones_se_miran_en_la_misma_pasada(base):
    async def caso():
        await _pix(base, "gpix_1", "mp_pix", status="expired", monto="30.00", dias=5)
        await _tarjeta(base, "mp_card", status="in_process", monto="40.00", dias=4)
        mp = MercadoPagoDeMentira({"mp_pix": _aprobado("30.00"),
                                   "mp_card": _aprobado("40.00")})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert r["cuantos"] == 2, r["cobros"]
        assert {f["medio"] for f in r["cobros"]} == {"PIX", "Tarjeta"}
        assert r["total_brl"] == "70.00"
    _correr(caso())


# ─── El dinero ───────────────────────────────────────────────────────────

def test_el_total_suma_en_decimal_y_no_arrastra_el_ruido_del_float(base):
    """Tres veces 0,10 en float da 0,30000000000000004. El total de un informe
    de plata no puede tener esa cola."""
    async def caso():
        for i in range(3):
            await _pix(base, f"gpix_{i}", f"mp_{i}", monto="0.10", dias=5 - i)
        mp = MercadoPagoDeMentira({f"mp_{i}": _aprobado("0.10") for i in range(3)})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert r["total_brl"] == "0.30", r["total_brl"]
    _correr(caso())


def test_los_montos_salen_en_texto_que_se_puede_volver_a_convertir(base):
    """En el borde de la API el dinero va en texto para que no lo toque un float
    en el camino, pero en el texto canónico: «4500.00», no «4.500,00». El de la
    gente lo pone el navegador, y no se puede volver a leer como número."""
    async def caso():
        await _pix(base, "gpix_1", "mp_1", monto="4500.00")
        mp = MercadoPagoDeMentira({"mp_1": _aprobado("4500.00")})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        for texto in (r["total_brl"], r["cobros"][0]["monto_en_mercadopago"],
                      r["cobros"][0]["monto_en_la_app"]):
            assert texto == "4500.00", texto
            assert Decimal(texto) == Decimal("4500.00")
    _correr(caso())


def test_un_monto_viejo_guardado_como_float_se_lee_igual(base):
    """Los pagos de antes de la conversión a Decimal128 tienen el monto en
    float. Si esta consulta reventara con ellos, justamente los más viejos
    —los que más falta hace revisar— no se podrían mirar."""
    async def caso():
        await _pix(base, "gpix_1", "mp_1", monto="99.90", decimal128=False)
        mp = MercadoPagoDeMentira({"mp_1": _aprobado("99.90")})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert r["cobros"][0]["monto_en_la_app"] == "99.90", r["cobros"]
    _correr(caso())


def test_los_dos_montos_se_muestran_por_separado(base):
    """El de Mercado Pago es lo que salió de la cuenta del cliente; el nuestro,
    lo que la app creía cobrar. Si no coinciden, eso también hay que verlo, y
    mostrar uno solo es esconder la diferencia."""
    async def caso():
        await _pix(base, "gpix_1", "mp_1", monto="100.00")
        mp = MercadoPagoDeMentira({"mp_1": _aprobado("120.00")})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        fila = r["cobros"][0]
        assert fila["monto_en_mercadopago"] == "120.00"
        assert fila["monto_en_la_app"] == "100.00"
        assert r["total_brl"] == "120.00", (
            "el total tiene que sumar lo que el cliente pagó de verdad")
    _correr(caso())


# ─── La fecha ────────────────────────────────────────────────────────────

def test_la_fecha_sale_con_zona_horaria(base):
    """El cliente de Mongo de esta app no es `tz_aware`: lo que vuelve de la
    base son fechas sin zona. Mandarlas así hace que el navegador las lea como
    hora local y muestre un horario que nunca existió."""
    async def caso():
        await base.gestor_pix_payments.insert_one({
            "payment_id": "gpix_1", "mp_payment_id": "mp_1",
            "client_name": "Ana", "amount_brl": to_decimal128("10.00"),
            "status": "pending",
            # Sin zona, como vuelve de la base de verdad.
            "created_at": datetime.utcnow() - timedelta(days=1),
        })
        mp = MercadoPagoDeMentira({"mp_1": _aprobado("10.00")})
        r = await cobros_sin_acreditar.revisar(base, preguntar=mp)
        assert r["cuantos"] == 1, r
        cuando = r["cobros"][0]["cuando"]
        assert cuando.endswith("+00:00"), cuando
    _correr(caso())
