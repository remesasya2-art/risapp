"""
tests/test_lotes_de_pago.py — Que dos agentes no se lleven la misma orden.

LO QUE SE VIGILA, POR ORDEN DE DAÑO

    1. Que una orden no pueda entrar en dos lotes. Si entra, se paga dos veces,
       y esa plata hay que ir a buscarla.
    2. Que cancelar un lote no suelte una orden que ya está en otro. Mismo
       daño, por el camino contrario.
    3. Que el archivo guardado NO se vuelva a generar. Entre que se bajó y
       ahora pudo cambiar la tasa: el segundo archivo no sería el que la
       persona ya pegó en el banco, y los comprobantes no cuadrarían.
    4. Que lo que no se pudo tomar se diga. Un lote de diez cuando se pidieron
       once es un pago que no se hace y que nadie nota.
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

from conftest import ensenarle_decimal128_a_mongomock, usar_base    # noqa: E402
ensenarle_decimal128_a_mongomock()

from services import lotes_de_pago as lotes                         # noqa: E402
from services.money import to_decimal128                            # noqa: E402

BDV = "0102"


class Jefe:
    user_id = "s_jefe"
    name = "Dirección"
    email = "jefe@ejemplo.com"
    role = "super_admin"


class Otro:
    user_id = "s_otro"
    name = "Otro operador"
    email = "otro@ejemplo.com"
    role = "super_admin"


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test_lotes"]
    usar_base(b)
    return b


def _correr(corrutina):
    return asyncio.run(corrutina)


def _orden(i=0, cuenta="01340219112191046516", monto="100.00", flujo="ris_ves"):
    return {
        "orden_id": f"tx_{i:04d}", "flujo": flujo, "display_id": f"#{i:06d}",
        "destino": {"valor": to_decimal128(monto), "unidad": "VES"},
        "beneficiario": {"nombre": f"BENEFICIARIO {i}", "documento": "V-12345678",
                         "cuenta": cuenta, "bank": "Banesco",
                         "tipo_pago": "transferencia"},
    }


async def _sembrar(base, cuantas=3):
    ordenes = [_orden(i) for i in range(cuantas)]
    for o in ordenes:
        await base.transactions.insert_one({
            "transaction_id": o["orden_id"], "type": "withdrawal",
            "status": "pending", "created_at": datetime.now(timezone.utc),
        })
    return ordenes


# ══════════════════════════════════════════════════════════════════════════
# 1. El reclamo, que es lo único que impide pagar dos veces
# ══════════════════════════════════════════════════════════════════════════

def test_UNA_ORDEN_NO_PUEDE_ENTRAR_EN_DOS_LOTES(base):
    """Si entra en dos, se paga dos veces. Es el daño más caro de este módulo."""
    async def caso():
        ordenes = await _sembrar(base, 2)
        primero = await lotes.armar(base, ordenes, banco_pagador=BDV, quien=Jefe())
        assert primero["total"] == 2

        # El segundo agente pide las mismas más una libre.
        libre = _orden(9)
        await base.transactions.insert_one({
            "transaction_id": libre["orden_id"], "type": "withdrawal",
            "status": "pending"})
        segundo = await lotes.armar(base, ordenes + [libre], banco_pagador=BDV,
                                    quien=Otro())
        assert segundo["total"] == 1, "se llevó órdenes que ya estaban en otro lote"
        assert len(segundo["no_se_pudieron_tomar"]) == 2
        assert "#000000" in segundo["no_se_pudieron_tomar"]
    _correr(caso())


def test_SI_NO_SE_PUDO_TOMAR_NINGUNA_NO_SE_ARMA_UN_LOTE_VACIO(base):
    async def caso():
        ordenes = await _sembrar(base, 2)
        await lotes.armar(base, ordenes, banco_pagador=BDV, quien=Jefe())
        with pytest.raises(ValueError, match="Ninguna"):
            await lotes.armar(base, ordenes, banco_pagador=BDV, quien=Otro())
        assert await base[lotes.COLECCION].count_documents({}) == 1
    _correr(caso())


def test_LO_QUE_NO_SE_PUDO_TOMAR_VUELVE_NOMBRADO(base):
    """Un lote de diez cuando se pidieron once es un pago que no se hace y que
    nadie nota hasta que el cliente reclama."""
    async def caso():
        ordenes = await _sembrar(base, 3)
        await lotes.armar(base, [ordenes[0]], banco_pagador=BDV, quien=Jefe())
        segundo = await lotes.armar(base, ordenes, banco_pagador=BDV, quien=Otro())
        assert segundo["no_se_pudieron_tomar"] == ["#000000"], segundo
        assert segundo["total"] == 2
    _correr(caso())


def test_una_orden_que_no_existe_no_rompe_el_lote(base):
    async def caso():
        ordenes = await _sembrar(base, 1)
        lote = await lotes.armar(base, ordenes + [_orden(99)], banco_pagador=BDV,
                                 quien=Jefe())
        assert lote["total"] == 1
        assert lote["no_se_pudieron_tomar"] == ["#000099"]
    _correr(caso())


# ══════════════════════════════════════════════════════════════════════════
# 2. Las órdenes salen de la cola, pero el cliente no ve nada
# ══════════════════════════════════════════════════════════════════════════

def test_LA_ORDEN_QUEDA_MARCADA_PERO_SU_ESTADO_PARA_EL_CLIENTE_NO_CAMBIA(base):
    """`estado_admin` es del panel; `status` es lo que ve quien hizo la orden.
    Para el cliente la orden sigue en proceso hasta que se paga de verdad."""
    async def caso():
        ordenes = await _sembrar(base, 1)
        lote = await lotes.armar(base, ordenes, banco_pagador=BDV, quien=Jefe())
        doc = await base.transactions.find_one({"transaction_id": "tx_0000"})
        assert doc["estado_admin"] == lotes.EN_LOTE
        assert doc["lote_id"] == lote["lote_id"]
        assert doc["status"] == "pending", "le cambió el estado al cliente"
    _correr(caso())


# ══════════════════════════════════════════════════════════════════════════
# 3. Cancelar
# ══════════════════════════════════════════════════════════════════════════

def test_cancelar_devuelve_las_ordenes_a_la_cola(base):
    async def caso():
        ordenes = await _sembrar(base, 2)
        lote = await lotes.armar(base, ordenes, banco_pagador=BDV, quien=Jefe())
        r = await lotes.cancelar(base, lote["lote_id"], quien=Jefe())
        assert r["devueltas"] == 2
        doc = await base.transactions.find_one({"transaction_id": "tx_0000"})
        assert doc["estado_admin"] == "pendiente" and doc["lote_id"] is None
        # Y ahora sí se pueden volver a tomar.
        otro = await lotes.armar(base, ordenes, banco_pagador=BDV, quien=Otro())
        assert otro["total"] == 2
    _correr(caso())


def test_CANCELAR_UN_LOTE_NO_SUELTA_UNA_ORDEN_QUE_YA_ESTA_EN_OTRO(base):
    """El `lote_id` en el filtro no es adorno: sin él, cancelar un lote viejo
    soltaría una orden que ya entró en otro, y esa se pagaría dos veces o
    ninguna."""
    async def caso():
        ordenes = await _sembrar(base, 1)
        primero = await lotes.armar(base, ordenes, banco_pagador=BDV, quien=Jefe())
        await lotes.cancelar(base, primero["lote_id"], quien=Jefe())
        segundo = await lotes.armar(base, ordenes, banco_pagador=BDV, quien=Otro())

        # Se cancela el PRIMERO otra vez (por ejemplo, desde una pestaña vieja).
        await base[lotes.COLECCION].update_one(
            {"lote_id": primero["lote_id"]}, {"$set": {"estado": lotes.ABIERTO}})
        r = await lotes.cancelar(base, primero["lote_id"], quien=Jefe())

        assert r["devueltas"] == 0, "soltó una orden que era de otro lote"
        doc = await base.transactions.find_one({"transaction_id": "tx_0000"})
        assert doc["lote_id"] == segundo["lote_id"], "la orden perdió su lote"
    _correr(caso())


def test_un_lote_ya_cancelado_no_se_puede_cancelar_de_nuevo(base):
    async def caso():
        ordenes = await _sembrar(base, 1)
        lote = await lotes.armar(base, ordenes, banco_pagador=BDV, quien=Jefe())
        await lotes.cancelar(base, lote["lote_id"], quien=Jefe())
        with pytest.raises(ValueError, match="cerrado o cancelado"):
            await lotes.cancelar(base, lote["lote_id"], quien=Jefe())
    _correr(caso())


# ══════════════════════════════════════════════════════════════════════════
# 4. El archivo guardado
# ══════════════════════════════════════════════════════════════════════════

def test_EL_ARCHIVO_SE_GUARDA_Y_NO_SE_VUELVE_A_GENERAR(base):
    """Lo que se pagó es lo que decía el papel.

    Entre que el agente baja el archivo y vuelve con los comprobantes pueden
    pasar horas, y en el medio puede cambiar la tasa o corregirse una cuenta.
    Si el archivo se regenerara, el segundo no sería el que la persona pegó en
    el banco.
    """
    async def caso():
        ordenes = await _sembrar(base, 1)
        lote = await lotes.armar(base, ordenes, banco_pagador=BDV, quien=Jefe())
        original = lote["texto"]
        assert "01340219112191046516" in original

        # Cambia el mundo: otra cuenta para el mismo beneficiario.
        await base.transactions.update_one(
            {"transaction_id": "tx_0000"},
            {"$set": {"beneficiary_data.account_number": "01020000000000000000"}})

        guardado = await lotes.archivo(base, lote["lote_id"])
        assert guardado["texto"] == original, "el archivo se volvió a generar"
    _correr(caso())


def test_el_archivo_de_un_lote_que_no_existe_avisa(base):
    async def caso():
        with pytest.raises(ValueError, match="no existe"):
            await lotes.archivo(base, "lote_inventado")
    _correr(caso())


def test_LA_FOTO_DE_CADA_ORDEN_QUEDA_EN_EL_LOTE(base):
    """Sirve para lo mismo que el texto: si mañana cambia la tasa, esto sigue
    diciendo qué se mandó a pagar."""
    async def caso():
        ordenes = await _sembrar(base, 1)
        lote = await lotes.armar(base, ordenes, banco_pagador=BDV, quien=Jefe())
        foto = lote["ordenes"][0]
        assert foto["orden_id"] == "tx_0000"
        assert foto["beneficiario"]["cuenta"] == "01340219112191046516"
    _correr(caso())


# ══════════════════════════════════════════════════════════════════════════
# 5. Los límites y el rastro
# ══════════════════════════════════════════════════════════════════════════

def test_un_banco_pagador_que_no_existe_se_rechaza(base):
    async def caso():
        ordenes = await _sembrar(base, 1)
        with pytest.raises(ValueError, match="no está en la lista"):
            await lotes.armar(base, ordenes, banco_pagador="9999", quien=Jefe())
        # Y no dejó ninguna orden reservada a medias.
        doc = await base.transactions.find_one({"transaction_id": "tx_0000"})
        assert doc.get("estado_admin") in (None, "pendiente"), doc
    _correr(caso())


def test_no_se_arma_un_lote_sin_ordenes(base):
    async def caso():
        with pytest.raises(ValueError, match="No hay órdenes"):
            await lotes.armar(base, [], banco_pagador=BDV, quien=Jefe())
    _correr(caso())


def test_el_lote_no_pasa_del_maximo(base):
    async def caso():
        muchas = [_orden(i) for i in range(lotes.MAXIMO + 20)]
        for o in muchas:
            await base.transactions.insert_one({
                "transaction_id": o["orden_id"], "type": "withdrawal",
                "status": "pending"})
        lote = await lotes.armar(base, muchas, banco_pagador=BDV, quien=Jefe())
        assert lote["total"] == lotes.MAXIMO
    _correr(caso())


def test_ARMAR_Y_CANCELAR_DEJAN_RASTRO_EN_LA_AUDITORIA(base):
    """Ninguna de las dos mueve plata, pero las dos deciden qué se va a pagar y
    quién lo decidió — y eso, meses después, es la pregunta."""
    async def caso():
        ordenes = await _sembrar(base, 1)
        lote = await lotes.armar(base, ordenes, banco_pagador=BDV, quien=Jefe())
        await lotes.cancelar(base, lote["lote_id"], quien=Otro())

        acciones = [d["accion"] async for d in base.auditoria.find({})]
        assert "dinero.lote_armado" in acciones, acciones
        assert "dinero.lote_cancelado" in acciones, acciones

        armado = await base.auditoria.find_one({"accion": "dinero.lote_armado"})
        assert armado["actor"]["user_id"] == "s_jefe"
        assert armado["objetivo"]["id"] == lote["lote_id"]
        assert armado["objetivo"]["tipo"] == "lote"
    _correr(caso())


def test_los_lotes_abiertos_se_pueden_listar(base):
    """Sus órdenes salieron de la cola: si no hubiera dónde mirarlas, para el
    operador simplemente desaparecieron."""
    async def caso():
        ordenes = await _sembrar(base, 2)
        lote = await lotes.armar(base, ordenes, banco_pagador=BDV, quien=Jefe())
        abiertos = await lotes.abiertos(base)
        assert len(abiertos) == 1
        assert abiertos[0]["lote_id"] == lote["lote_id"]
        assert abiertos[0]["total"] == 2
        # La lista no arrastra el archivo entero de cada lote.
        assert "texto" not in abiertos[0]

        await lotes.cancelar(base, lote["lote_id"], quien=Jefe())
        assert await lotes.abiertos(base) == []
    _correr(caso())
