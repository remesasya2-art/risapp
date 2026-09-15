"""
tests/test_comprobantes_del_lote.py — Que ninguna foto termine en la orden equivocada.

LO QUE SE VIGILA, POR ORDEN DE DAÑO

    1. Que el MONTO no adjudique nunca. Dos personas que cobran lo mismo el
       mismo día es normal: si el monto alcanzara para elegir, las dos fotos
       se repartirían al azar y cada expediente quedaría con la prueba del
       pago de otro.
    2. Que ante la duda no se elija. Dos órdenes que encajan con una foto, o
       dos fotos que encajan con una orden: ninguna se adjudica sola.
    3. Que mover una foto la SAQUE de donde estaba. Sin eso, cada corrección
       deja una foto de más colgada de una orden ajena.
    4. Que sin lector no se rompa nada: todo queda para asignar a mano, que es
       exactamente como se trabajaba antes.
"""
import asyncio
import base64
import io
import os
import sys
from datetime import datetime, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import ensenarle_decimal128_a_mongomock, usar_base     # noqa: E402
ensenarle_decimal128_a_mongomock()

from services import comprobantes_del_lote as cmp                    # noqa: E402
from services import lector_de_comprobantes as lector                # noqa: E402
from services import lotes_de_pago as lotes                          # noqa: E402
from services.money import to_decimal128                             # noqa: E402

BDV = "0102"


class Jefe:
    user_id = "s_jefe"
    name = "Dirección"
    email = "jefe@ejemplo.com"
    role = "super_admin"


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test_comprobantes"]
    usar_base(b)
    return b


def _correr(corrutina):
    return asyncio.run(corrutina)


def _foto(color=(30, 30, 30)) -> str:
    """Una imagen de verdad, chiquita. El validador le mira los BYTES."""
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def _senales(cuentas=(), telefonos=(), cedulas=(), montos=(), texto=""):
    """Lo que devolvería el lector para una foto. Se arma a mano: acá no se
    prueba el lector, se prueba la adjudicación."""
    return {"cuentas": list(cuentas), "telefonos": list(telefonos),
            "cedulas": list(cedulas), "montos": list(montos),
            "referencias": [], "texto": lector.sin_adornos(texto)}


def _orden(i=0, cuenta="01340219112191046516", monto="100.00",
           nombre=None, telefono="04141234567", cedula="V-12345678"):
    return {
        "orden_id": f"tx_{i:04d}", "flujo": "ris_ves", "display_id": f"#{i:06d}",
        "monto": to_decimal128(monto), "unidad": "VES",
        "beneficiario": {"nombre": nombre or f"BENEFICIARIO NUMERO {i}",
                         "documento": cedula, "cuenta": cuenta,
                         "telefono": telefono, "tipo_pago": "transferencia"},
    }


async def _lote_con(base, ordenes):
    """Un lote abierto con estas órdenes, ya reservadas."""
    for o in ordenes:
        await base.transactions.insert_one({
            "transaction_id": o["orden_id"], "type": "withdrawal",
            "status": "pending", "created_at": datetime.now(timezone.utc)})
    armado = await lotes.armar(
        base, [dict(o, destino={"valor": o["monto"], "unidad": "VES"})
               for o in ordenes],
        banco_pagador=BDV, quien=Jefe())
    return armado["lote_id"]


def _con_lector(monkeypatch, senales_por_foto):
    """Reemplaza al lector por una lista fija. Una entrada por foto, en orden."""
    pendientes = list(senales_por_foto)

    def _falso(_datos):
        return pendientes.pop(0)

    monkeypatch.setattr(cmp.lector, "leer", _falso)


# ══════════════════════════════════════════════════════════════════════════
# 1. El monto no adjudica. Nunca.
# ══════════════════════════════════════════════════════════════════════════

def test_EL_MONTO_SOLO_NO_ADJUDICA_AUNQUE_SEA_UNICO():
    """Dos personas cobran distinto y la foto sólo muestra un monto.

    Aunque el monto identifique sin ambigüedad a una de las dos, no alcanza:
    lo que se lee de una foto puede ser la comisión, el saldo o el límite
    diario, y el número correcto en el renglón equivocado adjudica mal.
    """
    ordenes = [_orden(0, monto="100.00"), _orden(1, cuenta="01020000000000000001",
                                                 monto="200.00")]
    fotos = [_senales(montos=["100,00"])]
    assert cmp.adjudicar(fotos, ordenes)[0]["estado"] == cmp.SIN_ADJUDICAR


def test_LA_CEDULA_SOLA_TAMPOCO_ADJUDICA():
    """Una misma persona puede tener dos órdenes en el mismo lote."""
    ordenes = [_orden(0, cedula="V-9111222")]
    fotos = [_senales(cedulas=["9111222"], montos=["100,00"])]
    assert cmp.adjudicar(fotos, ordenes)[0]["estado"] == cmp.SIN_ADJUDICAR


def test_LA_CUENTA_SOLA_SI_ADJUDICA_PORQUE_ES_UNICA():
    ordenes = [_orden(0, cuenta="01340219112191046516", monto="100.00")]
    fotos = [_senales(cuentas=["01340219112191046516"], montos=["100,00"])]
    fallo = cmp.adjudicar(fotos, ordenes)[0]
    assert fallo["estado"] == cmp.SEGURO
    assert fallo["orden_id"] == "tx_0000"


def test_TELEFONO_Y_CEDULA_JUNTOS_ADJUDICAN():
    """Es el caso del pago móvil: los dos bancos muestran los dos enteros."""
    ordenes = [_orden(0, telefono="04264672100", cedula="V-26138745",
                      monto="10.00")]
    fotos = [_senales(telefonos=["04264672100"], cedulas=["26138745"],
                      montos=["10,00"])]
    assert cmp.adjudicar(fotos, ordenes)[0]["estado"] == cmp.SEGURO


def test_EL_TELEFONO_SOLO_NO_ADJUDICA():
    ordenes = [_orden(0, telefono="04264672100")]
    fotos = [_senales(telefonos=["04264672100"], montos=["100,00"])]
    assert cmp.adjudicar(fotos, ordenes)[0]["estado"] == cmp.SIN_ADJUDICAR


def test_NOMBRE_Y_FINAL_DE_CUENTA_ADJUDICAN_EL_CASO_DEL_BDV():
    """El BDV tapa la cuenta: deja el nombre y los últimos cuatro dígitos."""
    ordenes = [_orden(0, cuenta="01020121710106529080", monto="51932.50",
                      nombre="MARIA MAGDALENA MUNOZ MELENDEZ")]
    fotos = [_senales(montos=["51.932,50"],
                      texto="Beneficiario MARIA MAGDALENA MUÑOZ MELENDEZ "
                            "Cuenta 0102****9080")]
    fallo = cmp.adjudicar(fotos, ordenes)[0]
    assert fallo["estado"] == cmp.SEGURO, fallo["motivo"]


def test_EL_FINAL_DE_CUENTA_SOLO_NO_ADJUDICA():
    """Diez mil combinaciones posibles: en un lote de once se repiten."""
    ordenes = [_orden(0, cuenta="01020121710106529080",
                      nombre="MARIA MAGDALENA MUNOZ MELENDEZ")]
    fotos = [_senales(montos=["100,00"], texto="Cuenta 0102****9080")]
    assert cmp.adjudicar(fotos, ordenes)[0]["estado"] == cmp.SIN_ADJUDICAR


def test_UN_APELLIDO_SUELTO_NO_ALCANZA_PARA_DAR_EL_NOMBRE_POR_ENCONTRADO():
    """En un lote con dos RODRIGUEZ, una sola palabra adjudicaría al azar."""
    ordenes = [_orden(0, cuenta="01020121710106529080",
                      nombre="CARLOS RODRIGUEZ")]
    fotos = [_senales(montos=["100,00"], texto="RODRIGUEZ 0102****9080")]
    assert cmp.adjudicar(fotos, ordenes)[0]["estado"] == cmp.SIN_ADJUDICAR


def test_LAS_TILDES_Y_LA_ENE_NO_IMPIDEN_QUE_EL_NOMBRE_COINCIDA():
    """El lector devuelve MUNOZ donde el panel guarda MUÑOZ."""
    ordenes = [_orden(0, cuenta="01020121710106529080", monto="10.00",
                      nombre="MARÍA MUÑOZ MELÉNDEZ")]
    fotos = [_senales(montos=["10,00"],
                      texto="MARIA MUNOZ MELENDEZ 0102****9080")]
    assert cmp.adjudicar(fotos, ordenes)[0]["estado"] == cmp.SEGURO


# ══════════════════════════════════════════════════════════════════════════
# 2. Ante la duda, no se elige
# ══════════════════════════════════════════════════════════════════════════

def test_SI_DOS_ORDENES_ENCAJAN_CON_LA_FOTO_NO_SE_ELIGE_NINGUNA():
    """Una persona con dos órdenes al mismo beneficiario. Pasa de verdad."""
    ordenes = [_orden(0, cuenta="01340219112191046516", monto="100.00"),
               _orden(1, cuenta="01340219112191046516", monto="100.00")]
    fotos = [_senales(cuentas=["01340219112191046516"], montos=["100,00"])]
    fallo = cmp.adjudicar(fotos, ordenes)[0]
    assert fallo["estado"] == cmp.AMBIGUO
    assert fallo["orden_id"] is None
    assert sorted(fallo["candidatas"]) == ["tx_0000", "tx_0001"]


def test_SI_DOS_FOTOS_ENCAJAN_CON_LA_MISMA_ORDEN_NO_SE_ADJUDICA_NINGUNA():
    """Puede ser un pago hecho dos veces o la misma captura subida dos veces.
    Las dos se resuelven mirando, ninguna eligiendo al azar."""
    ordenes = [_orden(0, cuenta="01340219112191046516", monto="100.00")]
    fotos = [_senales(cuentas=["01340219112191046516"], montos=["100,00"]),
             _senales(cuentas=["01340219112191046516"], montos=["100,00"])]
    fallos = cmp.adjudicar(fotos, ordenes)
    assert [f["estado"] for f in fallos] == [cmp.REPETIDO, cmp.REPETIDO]
    assert all(f["orden_id"] is None for f in fallos)
    assert all(f["candidatas"] == ["tx_0000"] for f in fallos)


def test_LA_LLAVE_COINCIDE_Y_EL_MONTO_NO_SE_PROPONE_PERO_SE_MARCA():
    """Se pagó de menos, o de más, o se leyó mal. Lo mira una persona."""
    ordenes = [_orden(0, cuenta="01340219112191046516", monto="100.00")]
    fotos = [_senales(cuentas=["01340219112191046516"], montos=["999,00"])]
    fallo = cmp.adjudicar(fotos, ordenes)[0]
    assert fallo["estado"] == cmp.REVISAR
    assert fallo["orden_id"] == "tx_0000", "se pierde la propuesta"
    assert "monto" in fallo["motivo"]


def test_EL_PUNTO_DE_MILES_DE_LA_FOTO_NO_ROMPE_LA_COMPARACION():
    """El banco escribe 114.552,10 y el archivo del lote escribe 114552,10."""
    ordenes = [_orden(0, cuenta="01340046600463065183", monto="114552.10")]
    fotos = [_senales(cuentas=["01340046600463065183"], montos=["114.552,10"])]
    assert cmp.adjudicar(fotos, ordenes)[0]["estado"] == cmp.SEGURO


def test_UN_MONTO_DIEZ_VECES_MAYOR_NO_SE_CONFUNDE_CON_EL_CORRECTO():
    """Comparar sin separadores no puede borrar la diferencia entre 3.460,00
    y 34.600,00: son 346000 y 3460000, y no se parecen."""
    ordenes = [_orden(0, cuenta="01340046600463065183", monto="3460.00")]
    fotos = [_senales(cuentas=["01340046600463065183"], montos=["34.600,00"])]
    assert cmp.adjudicar(fotos, ordenes)[0]["estado"] == cmp.REVISAR


def test_UNA_FOTO_QUE_NO_SE_PUDO_LEER_QUEDA_SIN_ADJUDICAR():
    ordenes = [_orden(0)]
    assert cmp.adjudicar([lector.vacio()], ordenes)[0]["estado"] == cmp.SIN_ADJUDICAR


def test_UNA_ORDEN_SIN_CUENTA_NO_ADJUDICA_POR_CUENTA_VACIA():
    """Si el vacío coincidiera con el vacío, cualquier foto sería suya."""
    ordenes = [_orden(0, cuenta="", telefono="", cedula="", nombre="")]
    fotos = [_senales(montos=["100,00"])]
    assert cmp.adjudicar(fotos, ordenes)[0]["estado"] == cmp.SIN_ADJUDICAR


def test_UNA_ORDEN_SIN_CUENTA_NO_ADJUDICA_POR_EL_NOMBRE_SOLO():
    """El caso que obliga a que el final de cuenta lleve su propia guarda.

    Sin cuenta, el «final de cuenta» es la cadena vacía — y la cadena vacía
    está adentro de CUALQUIER texto. Si no se preguntara antes si la orden
    tiene cuenta, esta foto se adjudicaría con sólo nombrar al beneficiario, y
    una orden sin cuenta es justamente la que nadie pagó todavía.
    """
    ordenes = [_orden(0, cuenta="", telefono="", cedula="",
                      nombre="MARIA MAGDALENA MUNOZ")]
    fotos = [_senales(montos=["100,00"], texto="Pago a MARIA MAGDALENA MUNOZ")]
    assert cmp.adjudicar(fotos, ordenes)[0]["estado"] == cmp.SIN_ADJUDICAR


def test_LAS_PALABRAS_CORTAS_DEL_NOMBRE_NO_CUENTAN():
    """«DE» y «LA» están en medio nombre venezolano: si contaran, dos de esas
    partículas alcanzarían para dar el nombre por encontrado, y el nombre es
    la mitad de la llave que adjudica las transferencias del BDV.
    """
    ordenes = [_orden(0, cuenta="01020121710106529080",
                      nombre="JOSE DE LA CRUZ PEREZ")]
    fotos = [_senales(montos=["100,00"],
                      texto="Transferencia a ANA DE LA ROSA 0102****9080")]
    assert cmp.adjudicar(fotos, ordenes)[0]["estado"] == cmp.SIN_ADJUDICAR


def test_UNA_COMA_EN_EL_NOMBRE_GUARDADO_NO_IMPIDE_QUE_COINCIDA():
    """El panel guarda «PÉREZ, ANA» tal como lo escribió quien lo cargó.

    Sin sacar la puntuación, la palabra a buscar sería «PEREZ,» con la coma
    pegada, y eso no aparece en ninguna foto. Y «ANA» no la reemplaza: tiene
    tres letras y las palabras cortas no cuentan. O sea que al beneficiario
    correcto lo dejaría sin adjudicar un signo.
    """
    ordenes = [_orden(0, cuenta="01020121710106529080", monto="10.00",
                      nombre="PÉREZ, ANA")]
    fotos = [_senales(montos=["10,00"],
                      texto="Beneficiario ANA PEREZ 0102****9080")]
    assert cmp.adjudicar(fotos, ordenes)[0]["estado"] == cmp.SEGURO


def test_UNA_CUENTA_DE_LARGO_EQUIVOCADO_NO_CUENTA_COMO_LLAVE():
    """Diecinueve dígitos es una cuenta mal cargada, no una cuenta."""
    ordenes = [_orden(0, cuenta="0134021911219104651", monto="100.00")]
    fotos = [_senales(cuentas=["0134021911219104651"], montos=["100,00"])]
    assert cmp.adjudicar(fotos, ordenes)[0]["estado"] == cmp.SIN_ADJUDICAR


# ══════════════════════════════════════════════════════════════════════════
# 3. La carga entera, contra la base
# ══════════════════════════════════════════════════════════════════════════

def test_UNA_SOLA_CARGA_REPARTE_LAS_FOTOS_ENTRE_LAS_ORDENES(base, monkeypatch):
    """Es la razón de ser del módulo: once fotos de una vez, cada una a la suya."""
    async def caso():
        ordenes = [_orden(0, cuenta="01340219112191046516", monto="100.00"),
                   _orden(1, cuenta="01020121710106529080", monto="200.00")]
        lote_id = await _lote_con(base, ordenes)
        _con_lector(monkeypatch, [
            _senales(cuentas=["01020121710106529080"], montos=["200,00"]),
            _senales(cuentas=["01340219112191046516"], montos=["100,00"])])

        salida = await cmp.cargar(base, lote_id, [_foto(), _foto((60, 60, 60))],
                                  quien=Jefe())
        assert salida["resumen"] == {cmp.SEGURO: 2}
        # La primera foto es la de la SEGUNDA orden: el orden en que se suben
        # no tiene por qué ser el orden del archivo.
        assert [c["orden_id"] for c in salida["comprobantes"]] == ["tx_0001", "tx_0000"]

        for oid in ("tx_0000", "tx_0001"):
            tx = await base.transactions.find_one({"transaction_id": oid})
            assert len(tx.get("proof_images") or []) == 1, f"{oid} se quedó sin foto"
    _correr(caso())


def test_LO_QUE_NO_SE_ADJUDICO_NO_SE_CUELGA_DE_NINGUNA_ORDEN(base, monkeypatch):
    async def caso():
        ordenes = [_orden(0, cuenta="01340219112191046516", monto="100.00")]
        lote_id = await _lote_con(base, ordenes)
        _con_lector(monkeypatch, [_senales(montos=["100,00"])])

        salida = await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())
        assert salida["resumen"] == {cmp.SIN_ADJUDICAR: 1}
        tx = await base.transactions.find_one({"transaction_id": "tx_0000"})
        assert not tx.get("proof_images"), "colgó una foto que no era de nadie"
    _correr(caso())


def test_LA_QUE_SE_MARCO_PARA_REVISAR_SI_SE_CUELGA(base, monkeypatch):
    """Se propone y se cuelga, porque el beneficiario coincide. Lo que falta
    es que alguien mire el monto, y para eso tiene que poder verla en la orden."""
    async def caso():
        ordenes = [_orden(0, cuenta="01340219112191046516", monto="100.00")]
        lote_id = await _lote_con(base, ordenes)
        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["999,00"])])

        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())
        tx = await base.transactions.find_one({"transaction_id": "tx_0000"})
        assert len(tx.get("proof_images") or []) == 1
    _correr(caso())


def test_SIN_LECTOR_NO_SE_ROMPE_NADA_Y_TODO_QUEDA_PARA_ASIGNAR(base, monkeypatch):
    """`tesseract` es un programa del sistema y puede no estar en el servidor."""
    async def caso():
        ordenes = [_orden(0, cuenta="01340219112191046516", monto="100.00")]
        lote_id = await _lote_con(base, ordenes)

        def _no_hay(_datos):
            raise lector.SinLector("no está instalado")
        monkeypatch.setattr(cmp.lector, "leer", _no_hay)

        salida = await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())
        assert salida["resumen"] == {cmp.SIN_LECTOR: 1}
        assert salida["comprobantes"][0]["orden_id"] is None
        tx = await base.transactions.find_one({"transaction_id": "tx_0000"})
        assert not tx.get("proof_images")
    _correr(caso())


def test_NO_SE_PUEDEN_CARGAR_FOTOS_EN_UN_LOTE_CANCELADO(base, monkeypatch):
    async def caso():
        ordenes = [_orden(0)]
        lote_id = await _lote_con(base, ordenes)
        await lotes.cancelar(base, lote_id, quien=Jefe())
        _con_lector(monkeypatch, [_senales()])
        with pytest.raises(ValueError, match="cerrado o cancelado"):
            await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())
    _correr(caso())


def test_UNA_CARGA_DEMASIADO_GRANDE_SE_RECHAZA_ENTERA(base):
    async def caso():
        lote_id = await _lote_con(base, [_orden(0)])
        with pytest.raises(ValueError, match="demasiadas"):
            await cmp.cargar(base, lote_id,
                             [_foto()] * (cmp.MAXIMO_POR_CARGA + 1), quien=Jefe())
    _correr(caso())


def test_UNA_FOTO_QUE_NO_ES_UNA_FOTO_NO_ENTRA(base):
    """El validador mira los BYTES, no la etiqueta."""
    from services.imagen_recibida import ImagenInvalida

    async def caso():
        lote_id = await _lote_con(base, [_orden(0)])
        mentira = "data:image/png;base64," + base64.b64encode(b"no soy un png").decode()
        with pytest.raises(ImagenInvalida):
            await cmp.cargar(base, lote_id, [mentira], quien=Jefe())
    _correr(caso())


def test_LO_QUE_SE_LEYO_QUEDA_GUARDADO(base, monkeypatch):
    """Cuando una adjudicación salga mal, la pregunta va a ser qué decía la foto."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0, cuenta="01340219112191046516")])
        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["100,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        lote = await base[lotes.COLECCION].find_one({"lote_id": lote_id})
        leido = lote["comprobantes"][0]["leido"]
        assert leido["cuentas"] == ["01340219112191046516"]
        assert "texto" not in leido, "el texto entero engorda el documento sin uso"
    _correr(caso())


def test_LA_CARGA_QUEDA_EN_LA_AUDITORIA(base, monkeypatch):
    async def caso():
        lote_id = await _lote_con(base, [_orden(0, cuenta="01340219112191046516")])
        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["100,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        fila = await base.auditoria.find_one({"accion": "dinero.lote_comprobantes"})
        assert fila is not None
        assert fila["objetivo"]["id"] == lote_id
    _correr(caso())


# ══════════════════════════════════════════════════════════════════════════
# 4. Asignar a mano
# ══════════════════════════════════════════════════════════════════════════

def test_MOVER_UNA_FOTO_LA_SACA_DE_LA_ORDEN_ANTERIOR(base, monkeypatch):
    """Sin esto, cada corrección deja una foto de más en un expediente ajeno."""
    async def caso():
        ordenes = [_orden(0, cuenta="01340219112191046516", monto="100.00"),
                   _orden(1, cuenta="01020121710106529080", monto="200.00")]
        lote_id = await _lote_con(base, ordenes)
        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["100,00"])])
        salida = await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())
        cid = salida["comprobantes"][0]["comprobante_id"]

        await cmp.asignar(base, lote_id, cid, "tx_0001", quien=Jefe())

        vieja = await base.transactions.find_one({"transaction_id": "tx_0000"})
        nueva = await base.transactions.find_one({"transaction_id": "tx_0001"})
        assert not vieja.get("proof_images"), "la foto quedó también en la vieja"
        assert len(nueva.get("proof_images") or []) == 1
    _correr(caso())


def test_SOLTAR_UNA_FOTO_LA_SACA_Y_NO_LA_PONE_EN_NINGUNA(base, monkeypatch):
    async def caso():
        lote_id = await _lote_con(base, [_orden(0, cuenta="01340219112191046516")])
        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["100,00"])])
        salida = await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())
        cid = salida["comprobantes"][0]["comprobante_id"]

        devuelto = await cmp.asignar(base, lote_id, cid, None, quien=Jefe())
        assert devuelto["estado"] == cmp.SIN_ADJUDICAR
        tx = await base.transactions.find_one({"transaction_id": "tx_0000"})
        assert not tx.get("proof_images")
    _correr(caso())


def test_NO_SE_PUEDE_ASIGNAR_A_UNA_ORDEN_QUE_NO_ES_DEL_LOTE(base, monkeypatch):
    async def caso():
        lote_id = await _lote_con(base, [_orden(0)])
        _con_lector(monkeypatch, [_senales()])
        salida = await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())
        cid = salida["comprobantes"][0]["comprobante_id"]
        with pytest.raises(ValueError, match="no es de este lote"):
            await cmp.asignar(base, lote_id, cid, "tx_9999", quien=Jefe())
    _correr(caso())


def test_NO_SE_PUEDEN_PONER_DOS_FOTOS_EN_LA_MISMA_ORDEN_A_MANO(base, monkeypatch):
    """La segunda taparía a la primera sin que nadie lo note."""
    async def caso():
        ordenes = [_orden(0, cuenta="01340219112191046516", monto="100.00"),
                   _orden(1, cuenta="01020121710106529080", monto="200.00")]
        lote_id = await _lote_con(base, ordenes)
        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["100,00"]),
            _senales(cuentas=["01020121710106529080"], montos=["200,00"])])
        salida = await cmp.cargar(base, lote_id, [_foto(), _foto((60, 60, 60))],
                                  quien=Jefe())
        segunda = salida["comprobantes"][1]["comprobante_id"]

        with pytest.raises(ValueError, match="ya tiene una foto"):
            await cmp.asignar(base, lote_id, segunda, "tx_0000", quien=Jefe())
    _correr(caso())


def test_ASIGNAR_A_MANO_QUEDA_EN_LA_AUDITORIA(base, monkeypatch):
    """Quién decidió que esta foto es de esta orden es la pregunta de un banco."""
    async def caso():
        ordenes = [_orden(0, cuenta="01340219112191046516", monto="100.00"),
                   _orden(1, cuenta="01020121710106529080", monto="200.00")]
        lote_id = await _lote_con(base, ordenes)
        _con_lector(monkeypatch, [_senales()])
        salida = await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())
        cid = salida["comprobantes"][0]["comprobante_id"]

        await cmp.asignar(base, lote_id, cid, "tx_0001", quien=Jefe())
        fila = await base.auditoria.find_one(
            {"accion": "dinero.lote_comprobante_asignado"})
        assert fila is not None
        assert fila["detalle"]["ahora"] == "tx_0001"
    _correr(caso())


# ══════════════════════════════════════════════════════════════════════════
# 5. La tabla que ve el operador
# ══════════════════════════════════════════════════════════════════════════

def test_LA_TABLA_NO_TRAE_LAS_IMAGENES(base, monkeypatch):
    """Once fotos en base64 son decenas de megas, y la tabla no las usa."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0, cuenta="01340219112191046516")])
        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["100,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        tabla = await cmp.listar(base, lote_id)
        assert tabla["comprobantes"][0]["orden_id"] == "tx_0000"
        assert "imagen" not in tabla["comprobantes"][0]
        # Y la foto se puede pedir aparte.
        assert (await cmp.imagen(
            base, lote_id, tabla["comprobantes"][0]["comprobante_id"])
        ).startswith("data:image/")
    _correr(caso())


def test_LA_TABLA_DICE_QUE_ORDENES_SIGUEN_SIN_FOTO(base, monkeypatch):
    """Es lo que el operador mira para saber si terminó."""
    async def caso():
        ordenes = [_orden(0, cuenta="01340219112191046516", monto="100.00"),
                   _orden(1, cuenta="01020121710106529080", monto="200.00")]
        lote_id = await _lote_con(base, ordenes)
        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["100,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        tabla = await cmp.listar(base, lote_id)
        con_foto = {o["orden_id"]: o["tiene_comprobante"] for o in tabla["ordenes"]}
        assert con_foto == {"tx_0000": True, "tx_0001": False}
    _correr(caso())


# ══════════════════════════════════════════════════════════════════════════
# 9. Separar lo que ya está de lo que mira una persona, y sacar lo que no va
#
# La pantalla era UNA tabla con todo mezclado: lo resuelto, lo dudoso y lo que
# no es de nadie, junto y del mismo tamaño. Con dieciséis fotos, las dos que
# había que mirar quedaban enterradas.
#
# Y no había forma de sacar una foto: un comprobante errado, un cobro que no
# corresponde o la misma captura subida dos veces se quedaban en la lista para
# siempre, y el lote no terminaba de resolverse nunca.
# ══════════════════════════════════════════════════════════════════════════

def test_UNA_ORDEN_CON_EL_MONTO_DISTINTO_NO_ESTA_LISTA_PARA_REGISTRAR(base, monkeypatch):
    """`revisar` quiere decir que el beneficiario coincide y el importe NO.

    Asentarlo solo sería dar por pagada una cifra que nadie comparó. Es lo que
    se decidió: esa la mira una persona.
    """
    async def caso():
        lote_id = await _lote_con(base, [_orden(0, cuenta="01340219112191046516",
                                                monto="100.00")])
        # La cuenta da, el monto no: 999,00 contra los 100,00 de la orden.
        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["999,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        orden = (await cmp.listar(base, lote_id))["ordenes"][0]
        assert orden["tiene_comprobante"] is True, "la foto SI es de esa orden"
        assert orden["estado_comprobante"] == cmp.REVISAR
        assert orden["listo_para_registrar"] is False, (
            "el monto no coincide: no se registra sin que alguien mire")
    _correr(caso())


def test_UNA_ORDEN_CON_TODO_COINCIDIENDO_SI_ESTA_LISTA(base, monkeypatch):
    """El otro lado de la guarda. Sin esto, «no está lista» podría ser siempre
    y el test de arriba pasaría sin probar nada."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0, cuenta="01340219112191046516",
                                                monto="100.00")])
        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["100,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        orden = (await cmp.listar(base, lote_id))["ordenes"][0]
        assert orden["estado_comprobante"] == cmp.SEGURO
        assert orden["listo_para_registrar"] is True
    _correr(caso())


def test_UNA_ORDEN_SIN_FOTO_NO_ESTA_LISTA(base, monkeypatch):
    """Sin comprobante no hay nada que registrar, y tiene que decirlo."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0), _orden(1, cuenta="01020121710106529080")])
        _con_lector(monkeypatch, [_senales(cuentas=["01340219112191046516"],
                                           montos=["100,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        listas = {o["orden_id"]: o["listo_para_registrar"]
                  for o in (await cmp.listar(base, lote_id))["ordenes"]}
        assert listas == {"tx_0000": True, "tx_0001": False}
    _correr(caso())


def test_DESCARTAR_SACA_LA_FOTO_DE_LA_PANTALLA(base, monkeypatch):
    """Es el punto de descartarla: no volver a verla en cada recarga."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0)])
        _con_lector(monkeypatch, [_senales(cuentas=["00000000000000000000"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        antes = await cmp.listar(base, lote_id)
        assert len(antes["comprobantes"]) == 1
        cid = antes["comprobantes"][0]["comprobante_id"]

        await cmp.descartar(base, lote_id, cid, "repetida", quien=Jefe())

        despues = await cmp.listar(base, lote_id)
        assert despues["comprobantes"] == []
        assert despues["descartadas"] == 1, (
            "se sacan de la lista, pero cuántas se sacaron no se esconde")
    _correr(caso())


def test_DESCARTAR_BORRA_LOS_BYTES_PERO_DEJA_EL_RENGLON(base, monkeypatch):
    """Las fotos viven adentro del documento del lote y MongoDB no pasa de
    16 MB: una foto que ya se dijo que no va, ocupa por nada.

    El renglón queda —quién, cuándo y por qué—, porque en una pantalla de pagos
    lo que se saca tiene que poder explicarse después.
    """
    async def caso():
        lote_id = await _lote_con(base, [_orden(0)])
        _con_lector(monkeypatch, [_senales(cuentas=["00000000000000000000"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())
        cid = (await cmp.listar(base, lote_id))["comprobantes"][0]["comprobante_id"]

        await cmp.descartar(base, lote_id, cid, "comprobante errado", quien=Jefe())

        lote = await base[lotes.COLECCION].find_one({"lote_id": lote_id})
        guardado = lote["comprobantes"][0]
        assert guardado["imagen"] == "", "los bytes se van"
        assert guardado["estado"] == cmp.DESCARTADO
        assert guardado["motivo"] == "comprobante errado", "el porqué queda"
        assert guardado["descartado_por"] == Jefe().user_id
    _correr(caso())


def test_DESCARTAR_DESPEGA_LA_FOTO_DE_LA_ORDEN(base, monkeypatch):
    """Dejarla colgada sería dar por probado un pago con una foto que acaba de
    decirse que no sirve."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0, cuenta="01340219112191046516")])
        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["100,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        tx = await base.transactions.find_one({"transaction_id": "tx_0000"})
        assert len(tx.get("proof_images") or []) == 1

        cid = (await cmp.listar(base, lote_id))["comprobantes"][0]["comprobante_id"]
        await cmp.descartar(base, lote_id, cid, "no corresponde", quien=Jefe())

        tx = await base.transactions.find_one({"transaction_id": "tx_0000"})
        assert (tx.get("proof_images") or []) == []
        orden = (await cmp.listar(base, lote_id))["ordenes"][0]
        assert orden["tiene_comprobante"] is False
    _correr(caso())


def test_DESCARTAR_SIN_MOTIVO_NO_SE_PUEDE(base, monkeypatch):
    """Sin motivo escrito, el que mire dentro de seis meses no puede
    distinguir un duplicado de un cobro indebido."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0)])
        _con_lector(monkeypatch, [_senales(cuentas=["00000000000000000000"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())
        cid = (await cmp.listar(base, lote_id))["comprobantes"][0]["comprobante_id"]

        for vacio in ("", "   ", "no"):
            with pytest.raises(ValueError):
                await cmp.descartar(base, lote_id, cid, vacio, quien=Jefe())

        assert len((await cmp.listar(base, lote_id))["comprobantes"]) == 1, (
            "si el motivo no sirve, la foto no se toca")
    _correr(caso())


def test_DESCARTAR_QUEDA_EN_LA_AUDITORIA(base, monkeypatch):
    """Sacar un comprobante es sacar la prueba de un pago. Tiene que asentarse."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0)])
        _con_lector(monkeypatch, [_senales(cuentas=["00000000000000000000"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())
        cid = (await cmp.listar(base, lote_id))["comprobantes"][0]["comprobante_id"]

        await cmp.descartar(base, lote_id, cid, "cobro que no corresponde", quien=Jefe())

        linea = await base.auditoria.find_one(
            {"accion": "dinero.lote_comprobante_descartado"})
        assert linea is not None
        assert linea["detalle"]["motivo"] == "cobro que no corresponde"
    _correr(caso())


def test_UNA_FOTO_DESCARTADA_NO_SE_DESCARTA_DOS_VECES(base, monkeypatch):
    """La segunda vez sobreescribiría el motivo de la primera con otro."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0)])
        _con_lector(monkeypatch, [_senales(cuentas=["00000000000000000000"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())
        cid = (await cmp.listar(base, lote_id))["comprobantes"][0]["comprobante_id"]

        await cmp.descartar(base, lote_id, cid, "la primera vez", quien=Jefe())
        with pytest.raises(ValueError):
            await cmp.descartar(base, lote_id, cid, "la segunda vez", quien=Jefe())

        lote = await base[lotes.COLECCION].find_one({"lote_id": lote_id})
        assert lote["comprobantes"][0]["motivo"] == "la primera vez"
    _correr(caso())


# ══════════════════════════════════════════════════════════════════════════
# 10. La foto no vive adentro del lote
#
# Se guardaba en base64 en el documento del lote. Un documento de MongoDB no
# puede pasar de 16 MB, y con capturas de teléfono de medio mega entran unas
# veinticuatro — un lote admite trescientas órdenes. Al pasarse, el `$push`
# falla y el agente pierde la tanda entera.
#
# `services/envios_archivos.py` ya resolvía esto para las fotos de los envíos,
# por el mismo motivo y escrito en su encabezado.
# ══════════════════════════════════════════════════════════════════════════

def test_EL_LOTE_GUARDA_LA_REFERENCIA_Y_NO_LOS_BYTES(base, monkeypatch):
    """Es todo el punto del cambio: el documento del lote se queda chico."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0, cuenta="01340219112191046516")])
        _con_lector(monkeypatch, [_senales(cuentas=["01340219112191046516"],
                                           montos=["100,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        lote = await base[lotes.COLECCION].find_one({"lote_id": lote_id})
        guardado = lote["comprobantes"][0]
        assert guardado.get("asset_id"), "tiene que quedar la referencia"
        assert not guardado.get("imagen"), (
            "los bytes NO van adentro del lote: es lo que rompía el tope de 16 MB")

        ficha = await base.envios_archivos.find_one(
            {"asset_id": guardado["asset_id"]})
        assert ficha is not None, "y tienen que estar en el almacén"
        assert ficha["clase"] == "comprobante_lote"
        assert ficha["dueno_id"] == lote_id
    _correr(caso())


def test_LA_FOTO_SE_SIGUE_PUDIENDO_MIRAR(base, monkeypatch):
    """Guardarla afuera no sirve si después no se puede abrir."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0, cuenta="01340219112191046516")])
        _con_lector(monkeypatch, [_senales(cuentas=["01340219112191046516"],
                                           montos=["100,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())
        cid = (await cmp.listar(base, lote_id))["comprobantes"][0]["comprobante_id"]

        assert (await cmp.imagen(base, lote_id, cid)).startswith("data:image/")
    _correr(caso())


def test_UNA_FOTO_DE_UN_LOTE_VIEJO_SE_SIGUE_LEYENDO(base, monkeypatch):
    """Los lotes que ya existen tienen los bytes adentro, en `imagen`.

    Migrarlos de golpe es lo que deja un lote sin sus comprobantes si algo sale
    mal a mitad de camino. Se leen de los dos lados y no hay apuro.
    """
    async def caso():
        lote_id = await _lote_con(base, [_orden(0)])
        vieja = _foto()
        await base[lotes.COLECCION].update_one(
            {"lote_id": lote_id},
            {"$push": {"comprobantes": {
                "comprobante_id": "cmp_vieja", "imagen": vieja,
                "estado": cmp.SIN_ADJUDICAR, "motivo": "", "orden_id": None,
                "candidatas": [], "leido": {}}}})

        assert await cmp.imagen(base, lote_id, "cmp_vieja") == vieja
    _correr(caso())


def test_LA_FOTO_SE_CUELGA_IGUAL_DE_LA_ORDEN(base, monkeypatch):
    """`proof_images` sigue siendo el campo de siempre: ninguna pantalla vieja
    tiene que aprender el almacén."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0, cuenta="01340219112191046516")])
        _con_lector(monkeypatch, [_senales(cuentas=["01340219112191046516"],
                                           montos=["100,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        tx = await base.transactions.find_one({"transaction_id": "tx_0000"})
        assert len(tx.get("proof_images") or []) == 1
        assert tx["proof_images"][0].startswith("data:image/")
    _correr(caso())


def test_LA_MISMA_FOTO_DOS_VECES_NO_ENTRA_DOS_VECES(base, monkeypatch):
    """Lo que pasó de verdad: el lector no andaba, el agente reintentó, y
    quedaron doce fotos para cuatro órdenes.

    Se compara el CONTENIDO. El nombre del archivo no dice nada.
    """
    async def caso():
        lote_id = await _lote_con(base, [_orden(0, cuenta="01340219112191046516")])
        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["100,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        # La misma tanda otra vez, como el reintento del agente.
        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["100,00"])])
        resultado = await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        assert resultado["repetidas"] == 1
        assert len((await cmp.listar(base, lote_id))["comprobantes"]) == 1, (
            "una sola foto, no dos")
    _correr(caso())


def test_DOS_FOTOS_DISTINTAS_SI_ENTRAN_LAS_DOS(base, monkeypatch):
    """El otro lado de la guarda. Sin esto, «se descarta» podría ser siempre."""
    async def caso():
        ordenes = [_orden(0, cuenta="01340219112191046516"),
                   _orden(1, cuenta="01020121710106529080")]
        lote_id = await _lote_con(base, ordenes)
        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["100,00"]),
            _senales(cuentas=["01020121710106529080"], montos=["100,00"])])

        resultado = await cmp.cargar(
            base, lote_id, [_foto((10, 10, 10)), _foto((200, 200, 200))],
            quien=Jefe())

        assert resultado["repetidas"] == 0
        assert len((await cmp.listar(base, lote_id))["comprobantes"]) == 2
    _correr(caso())


def test_UNA_FOTO_DESCARTADA_SE_PUEDE_VOLVER_A_SUBIR(base, monkeypatch):
    """Descartarla fue decir «esta no va». Si el agente se equivocó al
    descartarla, tiene que poder subirla de nuevo — si no, la huella la
    dejaría afuera para siempre."""
    async def caso():
        lote_id = await _lote_con(base, [_orden(0, cuenta="01340219112191046516")])
        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["100,00"])])
        await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())
        cid = (await cmp.listar(base, lote_id))["comprobantes"][0]["comprobante_id"]
        await cmp.descartar(base, lote_id, cid, "me confundí", quien=Jefe())

        _con_lector(monkeypatch, [
            _senales(cuentas=["01340219112191046516"], montos=["100,00"])])
        resultado = await cmp.cargar(base, lote_id, [_foto()], quien=Jefe())

        assert resultado["repetidas"] == 0
        assert len((await cmp.listar(base, lote_id))["comprobantes"]) == 1
    _correr(caso())
