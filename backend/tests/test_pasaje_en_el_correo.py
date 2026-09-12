"""
tests/test_pasaje_en_el_correo.py — El comprobante lleno con la operación.

LO QUE PASABA

    El correo del movimiento de dinero decía «Tu retiro de 4.500,00 VES ha
    sido procesado» y nada más. Ni el número, ni la fecha, ni la tasa, ni a
    quién. Para reclamar en un banco eso no sirve: hay que entrar a la
    aplicación a buscar el número, y quien reclama desde un mostrador no tiene
    cómo.

    Ahora el correo lleva el comprobante con forma de pasaje. Los datos NO
    viajan en el aviso: viaja un identificador y la operación se lee de la
    base, en un solo lugar. Meter los ocho campos en los trece
    `create_notification` que mueven dinero es la forma que produjo las cinco
    maneras distintas de avisarle al equipo que hubo que desarmar.

LA GUARDA QUE MAS IMPORTA

    `test_ningun_aviso_de_dinero_con_operacion_se_queda_sin_comprobante`
    recorre los archivos de rutas y comprueba que cada `create_notification`
    de una clase que mueve plata mande un identificador. Es la que se va a
    poner roja el día que alguien agregue un movimiento nuevo y se olvide.
"""
import ast
import asyncio
import os
import pathlib
import re
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from datetime import datetime, timezone                # noqa: E402

from conftest import usar_base                         # noqa: E402
from services import avisos_por_correo, comprobante, correo, pasaje  # noqa: E402
from services.money import to_decimal128               # noqa: E402


def corre(coro):
    return asyncio.run(coro)


CUANDO = datetime(2026, 9, 11, 21, 40, tzinfo=timezone.utc)


def base_nueva():
    base = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(base)
    return base


async def con_un_retiro(base, **cambios):
    """Un retiro como lo escribe la aplicación.

    La plata va en `Decimal128` —con `to_decimal128`, igual que el producto—.
    Un test que escribe `4500.0` a secas pasa con el comprobante roto, porque
    `mongomock` sólo conserva el `Decimal128` si el test lo insertó así.
    """
    doc = {
        "transaction_id": "tx-1", "display_id": "RIS-8827194",
        "user_id": "u-1", "type": "withdrawal", "status": "completed",
        "amount_input": to_decimal128("250.00"),
        "amount_output": to_decimal128("4500.00"),
        "currency_input": "RIS", "currency_output": "VES",
        "rate": to_decimal128("18.00"), "created_at": CUANDO,
        "beneficiary_data": {
            "full_name": "María G.", "bank_name": "Banesco",
            "account_number": "01340000001234567890",
            "document": "V-12345678", "payment_type": "transferencia",
            # Esto NO puede salir en el correo, y por eso está acá:
            "notas_internas": "cliente marcado para revisión",
        },
    }
    doc.update(cambios)
    await base.transactions.insert_one(doc)
    return doc


# ──────────────────────────────────────────────────────────────────────────
#  El pasaje de un movimiento de dinero
# ──────────────────────────────────────────────────────────────────────────

def test_el_pasaje_lleva_el_numero_el_monto_y_la_fecha():
    async def caso():
        base = base_nueva()
        await con_un_retiro(base)
        return await pasaje.de_la_operacion("tx-1", titulo="Tu retiro se completó")

    html = corre(caso())
    assert html
    for esperado in ("RIS-8827194", "4.500,00 VES", "250,00 RIS", "18,00",
                     "11 SEP 2026", "COMPLETADO", "Tu retiro se completó"):
        assert html.find(esperado) != -1, esperado


def test_la_plata_sale_con_punto_de_miles_y_no_como_la_guarda_la_base():
    """`4500.00` es como se guarda; `4.500,00` es como se lee. Y el camino
    entre los dos pasa por `Decimal`, nunca por `float`."""
    async def caso():
        base = base_nueva()
        await con_un_retiro(base, amount_output=to_decimal128("1234567.89"))
        return await pasaje.de_la_operacion("tx-1", titulo="x")

    html = corre(caso())
    assert html.find("1.234.567,89 VES") != -1
    assert html.find("1234567.89") == -1


def test_del_beneficiario_salen_los_ultimos_cuatro_y_nada_mas():
    """Un correo se reenvía, se imprime y queda en una casilla que no siempre
    es la de quien opera."""
    async def caso():
        base = base_nueva()
        await con_un_retiro(base)
        return await pasaje.de_la_operacion("tx-1", titulo="x")

    html = corre(caso())
    assert html.find("••••7890") != -1
    assert html.find("••••5678") != -1
    for prohibido in ("01340000001234567890", "V-12345678",
                      "cliente marcado para revisión"):
        assert html.find(prohibido) == -1, prohibido


def test_la_proyeccion_es_una_lista_de_lo_permitido():
    """Con una lista de lo PROHIBIDO, cada campo nuevo de una operación entra
    solo al correo el día que alguien lo agregue."""
    valores = set(pasaje.DE_LA_OPERACION.values()) | set(pasaje.DEL_ENVIO.values())
    assert valores == {0, 1}
    for proyeccion in (pasaje.DE_LA_OPERACION, pasaje.DEL_ENVIO):
        # `_id: 0` es la única exclusión, y es la que Mongo obliga a escribir.
        assert [k for k, v in proyeccion.items() if v == 0] == ["_id"]


def test_la_proyeccion_no_pide_ni_una_credencial():
    """Mirando la PROYECCION y no el HTML.

    Mirando el correo, pedir el token del seguimiento no rompe nada: se trae y
    no se dibuja. Pero el link de seguimiento es una credencial —quien lo
    tiene ve el envío, y no caduca—, y si está en la proyección se filtra el
    día que alguien agregue un campo al comprobante sin mirar de dónde sale.
    No se pide, y así no hay ese día.
    """
    SOSPECHOSAS = ("token", "secret", "password", "clave", "key", "hash",
                   "pin", "otp", "cvv")
    for nombre, proyeccion in (("operación", pasaje.DE_LA_OPERACION),
                               ("envío", pasaje.DEL_ENVIO)):
        for campo in proyeccion:
            bajo = campo.lower()
            assert not any(p in bajo for p in SOSPECHOSAS), (nombre, campo)


def test_no_hay_ni_una_consulta_sin_lista_de_lo_permitido():
    """Toda lectura de este módulo va con proyección, SIN excepción.

    La guarda de más arriba mira las dos listas de lo permitido. No alcanza:
    apareció una segunda consulta al mismo envío, esta vez sin proyección
    ninguna —`find_one({"envio_id": envio_id})` a secas—, que traía el
    documento entero con el token adentro y dejaba las dos listas impecables.
    La guarda de las listas pasaba, y el token salía igual.

    Así que lo que se vigila es la FORMA de la consulta: si lee, lleva lista.
    """
    import ast
    import inspect
    from services import pasaje as modulo

    fuente = inspect.getsource(modulo)
    sin_lista = []
    for nodo in ast.walk(ast.parse(fuente)):
        if not isinstance(nodo, ast.Call):
            continue
        if getattr(nodo.func, "attr", None) not in ("find_one", "find",
                                                    "find_one_and_update",
                                                    "aggregate"):
            continue
        # La proyección va como segundo argumento posicional, o como
        # `projection=`. Sin ninguno de los dos, Mongo devuelve TODO.
        tiene = (len(nodo.args) >= 2
                 or any(k.arg == "projection" for k in nodo.keywords))
        if not tiene:
            sin_lista.append((nodo.lineno, ast.unparse(nodo)[:90]))
    assert sin_lista == [], sin_lista


def test_esta_guarda_reconoce_la_consulta_sin_lista_que_aparecio():
    """La guarda de la guarda, con la línea exacta."""
    import ast
    fuente = 'crudo = await base.envios.find_one({"envio_id": envio_id})'
    llamada = next(n for n in ast.walk(ast.parse(fuente)) if isinstance(n, ast.Call))
    assert len(llamada.args) == 1 and not llamada.keywords
    # y la que sí lleva lista no se confunde con ella
    buena = 'await base.envios.find_one({"envio_id": envio_id}, DEL_ENVIO)'
    otra = next(n for n in ast.walk(ast.parse(buena)) if isinstance(n, ast.Call))
    assert len(otra.args) == 2


def test_un_campo_nuevo_de_la_operacion_no_entra_solo_al_correo():
    """La prueba de que la lista de lo permitido hace su trabajo."""
    async def caso():
        base = base_nueva()
        await con_un_retiro(base, motivo_de_fraude="coincide con lista negra")
        return await pasaje.de_la_operacion("tx-1", titulo="x")

    assert corre(caso()).find("lista negra") == -1


def test_una_remesa_con_bitcoin_se_encuentra_por_su_numero_de_remesa():
    """Las remesas con Bitcoin no tienen `transaction_id`: su operación se
    busca por `remesa_id`. Buscando sólo por uno, la mitad de los avisos de
    cripto se quedaban sin comprobante."""
    async def caso():
        base = base_nueva()
        await con_un_retiro(base, transaction_id=None, remesa_id="rem-77",
                            display_id=None)
        return await pasaje.de_la_operacion("rem-77", titulo="x")

    html = corre(caso())
    assert html
    assert html.find("rem-77") != -1


def test_si_la_operacion_no_esta_no_hay_pasaje_y_no_se_cae():
    async def caso():
        base_nueva()
        return await pasaje.de_la_operacion("no-existe", titulo="x")

    assert corre(caso()) is None


def test_sin_identificador_no_hay_pasaje():
    assert corre(pasaje.de_la_operacion("", titulo="x")) is None
    assert corre(pasaje.de_la_operacion(None, titulo="x")) is None


def test_si_la_base_se_cae_el_correo_sale_igual(monkeypatch):
    """Esto corre adentro del camino del correo, que corre adentro del camino
    de un aviso. Ninguno de los tres puede levantar."""
    class Explota:
        async def find_one(self, *a, **k):
            raise RuntimeError("se cayó Mongo")

    class BaseRota:
        transactions = Explota()
        envios = Explota()

    monkeypatch.setattr(pasaje, "_base", lambda db=None: _devolver(BaseRota()))
    assert corre(pasaje.de_la_operacion("tx-1", titulo="x")) is None
    assert corre(pasaje.del_envio("env-1", titulo="x")) is None


async def _devolver(valor):
    return valor


def test_un_estado_que_no_esta_en_la_tabla_no_deja_el_sello_en_blanco():
    """Un estado nuevo no puede dejar el pasaje sin sello: se muestra tal como
    vino, que dice menos pero dice algo."""
    async def caso():
        base = base_nueva()
        await con_un_retiro(base, status="algo_nuevo")
        return await pasaje.de_la_operacion("tx-1", titulo="x")

    assert corre(caso()).find("ALGO_NUEVO") != -1


def test_una_clase_de_operacion_nueva_no_se_queda_sin_comprobante():
    """Cae en el nombre genérico. Al revés —sin comprobante— el día que
    alguien agregue una clase de movimiento sus correos perderían el pasaje
    en silencio."""
    async def caso():
        base = base_nueva()
        await con_un_retiro(base, type="algo_que_no_existia")
        return await pasaje.de_la_operacion("tx-1", titulo="x")

    html = corre(caso())
    assert html.find(pasaje.GENERICO.upper()) != -1


# ──────────────────────────────────────────────────────────────────────────
#  El pasaje de un paquete
# ──────────────────────────────────────────────────────────────────────────

def test_el_pasaje_del_paquete_lleva_la_ruta_de_verdad():
    async def caso():
        base = base_nueva()
        await base.envios.insert_one({
            "envio_id": "env-1", "display_id": "RIS-000123",
            "estado": "recibido_pacaraima", "created_at": CUANDO,
            "peso_facturable": to_decimal128("7.40"), "moneda": "RIS",
            "origen": {"ciudad": "Pacaraima"},
            "destino": {"ciudad": "Santa Elena", "estado_ve": "Bolívar"},
            # Nada de esto puede salir:
            "tracking_token": "a" * 40,
            "user_id": "u-1",
        })
        return await pasaje.del_envio("env-1", titulo="Ya tenemos tu paquete")

    html = corre(caso())
    assert html
    for esperado in ("RIS-000123", "PAC", "SAN", "Santa Elena, Bolívar",
                     "7,40 kg", "Ya tenemos tu paquete"):
        assert html.find(esperado) != -1, esperado
    # el enlace de seguimiento es una credencial y no viaja en algo que se reenvía
    assert html.find("a" * 40) == -1


def test_sin_envio_no_hay_pasaje():
    async def caso():
        base_nueva()
        return await pasaje.del_envio("no-existe", titulo="x")

    assert corre(caso()) is None


# ──────────────────────────────────────────────────────────────────────────
#  El enganche con el aviso
# ──────────────────────────────────────────────────────────────────────────

def test_el_aviso_de_dinero_manda_el_comprobante_y_no_un_parrafo(monkeypatch):
    salidas = []
    monkeypatch.setattr(correo, "en_segundo_plano",
                        lambda *a, **k: salidas.append(a))

    async def caso():
        base = base_nueva()
        await base.users.insert_one({"user_id": "u-1", "email": "ana@example.com"})
        await con_un_retiro(base)
        return await avisos_por_correo.acompanar(
            "u-1", "Tu retiro se completó", "Enviamos el dinero.",
            "withdrawal_completed", {"transaction_id": "tx-1"})

    assert corre(caso()) is True
    cuerpo = salidas[0][2]
    assert cuerpo.find("RIS-8827194") != -1
    assert cuerpo.find("4.500,00 VES") != -1
    # y el código para escanear está adentro
    assert cuerpo.find("Escaneá para ver los datos") != -1


def test_sin_numero_de_operacion_el_correo_sale_igual_como_parrafo(monkeypatch):
    """Un movimiento de dinero sin aviso es mucho peor que un aviso sin
    pasaje. El PIX, la tarjeta y el bono de referido no tienen operación en
    `transactions` y caen acá a propósito."""
    salidas = []
    monkeypatch.setattr(correo, "en_segundo_plano",
                        lambda *a, **k: salidas.append(a))

    async def caso():
        base = base_nueva()
        await base.users.insert_one({"user_id": "u-1", "email": "ana@example.com"})
        return await avisos_por_correo.acompanar(
            "u-1", "Recibimos tu pago por PIX", "Ya está en tu saldo.",
            "pix_received", {"payment_id": "pay-9"})

    assert corre(caso()) is True
    cuerpo = salidas[0][2]
    assert cuerpo.find("Recibimos tu pago por PIX") != -1
    assert cuerpo.find("Escaneá para ver los datos") == -1
    # pero con la MISMA identidad: la banda dorada y RISAPP. Antes éste salía
    # como un `<h2>` violeta sobre blanco, y al lado del pasaje dorado no
    # parecía el mismo remitente.
    assert cuerpo.find("RISAPP") != -1
    assert cuerpo.find(comprobante.ORO) != -1


def test_los_dos_correos_se_parecen_entre_si():
    """El que lleva comprobante y el que no tienen que salir de la misma
    empresa. Un correo de plata que no se parece al anterior se mira con
    desconfianza, o se borra."""
    con = comprobante.armar(titulo="Tu retiro se completó", tipo="Retiro",
                            referencia="RIS-1", cuando=CUANDO)
    sin = comprobante.nota(titulo="Recibimos tu pago por PIX")
    for igual in ("RISAPP", comprobante.ORO, comprobante.FONDO,
                  'width="600"', "border-radius:14px",
                  "no respondas a este correo"):
        assert con.find(igual) != -1 and sin.find(igual) != -1, igual


def test_si_el_pasaje_se_cae_el_correo_sale_igual(monkeypatch):
    salidas = []
    monkeypatch.setattr(correo, "en_segundo_plano",
                        lambda *a, **k: salidas.append(a))

    async def explota(*a, **k):
        raise RuntimeError("se cayó el pasaje")
    monkeypatch.setattr(pasaje, "para_el_aviso", explota)

    async def caso():
        base = base_nueva()
        await base.users.insert_one({"user_id": "u-1", "email": "ana@example.com"})
        return await avisos_por_correo.acompanar(
            "u-1", "Tu retiro se completó", "Enviamos el dinero.",
            "withdrawal_completed", {"transaction_id": "tx-1"})

    assert corre(caso()) is True
    assert salidas, "el correo tenía que salir igual"


def test_el_aviso_de_un_paquete_manda_el_pasaje_del_paquete(monkeypatch):
    salidas = []
    monkeypatch.setattr(correo, "en_segundo_plano",
                        lambda *a, **k: salidas.append(a))

    async def caso():
        base = base_nueva()
        await base.users.insert_one({"user_id": "u-1", "email": "ana@example.com"})
        await base.envios.insert_one({
            "envio_id": "env-1", "display_id": "RIS-000123",
            "estado": "recibido_pacaraima", "created_at": CUANDO,
            "origen": {"ciudad": "Pacaraima"},
            "destino": {"ciudad": "Santa Elena"}})
        return await avisos_por_correo.acompanar(
            "u-1", "Ya tenemos tu paquete", "Lo retiramos del mostrador.",
            "envio", {"envio_id": "env-1", "display_id": "RIS-000123"})

    assert corre(caso()) is True
    assert salidas[0][2].find("RIS-000123") != -1


# ──────────────────────────────────────────────────────────────────────────
#  La guarda que recorre el repositorio
# ──────────────────────────────────────────────────────────────────────────

# Las clases de aviso que mueven plata Y tienen operación en `transactions`.
#
# Las otras cuatro —`pix_received`, `card_received`, `credit_deposit`,
# `partner_bonus`— viven en otras colecciones y salen como párrafo. Si algún
# día se les arma un comprobante, se agregan acá y el test pide el número.
CON_OPERACION = {
    "withdrawal_pending", "withdrawal_completed", "withdrawal_rejected",
    "recharge_approved", "recharge_rejected",
    "crypto_send_paid", "crypto_send_refunded", "crypto_send_awaiting_topup",
    "crypto_send_underpaid_review",
    "btc_enviado", "btc_remesa_enviada", "btc_payment",
}

IDENTIFICADORES = ("transaction_id", "remesa_id", "tx_id", "display_id",
                   "envio_id")


def avisos_del_repositorio():
    """Cada `create_notification` de una clase que mueve plata, con lo que le
    pasa en `data`. Se lee el ARBOL y no el texto: un `data=` en un comentario
    o en una cadena no cuenta, y con una expresión regular sí contaría."""
    carpeta = pathlib.Path(_BACKEND)
    for archivo in sorted(carpeta.glob("routes/*.py")) + sorted(carpeta.glob("services/*.py")):
        arbol = ast.parse(archivo.read_text(), filename=str(archivo))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            nombre = getattr(nodo.func, "id", None) or getattr(nodo.func, "attr", None)
            if nombre != "create_notification":
                continue
            claves = {k.arg: k.value for k in nodo.keywords if k.arg}
            tipo = claves.get("notification_type")
            if not (isinstance(tipo, ast.Constant) and tipo.value in CON_OPERACION):
                continue
            texto = ast.unparse(claves["data"]) if "data" in claves else ""
            yield archivo.relative_to(carpeta), nodo.lineno, tipo.value, texto


def test_ningun_aviso_de_dinero_con_operacion_se_queda_sin_comprobante():
    """La guarda que se pone roja el día que alguien agregue un movimiento
    nuevo y se olvide de mandar el número: su correo saldría como párrafo, y
    nadie lo notaría hasta que un usuario pida su comprobante."""
    sin = [(str(a), l, t) for a, l, t, data in avisos_del_repositorio()
           if not any(i in data for i in IDENTIFICADORES)]
    assert sin == [], (
        "estos avisos de dinero no mandan el número de la operación, así que "
        f"su correo sale sin comprobante: {sin}")


def test_la_guarda_de_arriba_encuentra_los_avisos_que_persigue():
    """Una guarda que no encuentra nada pasa siempre. Ya pasó en este
    repositorio: dos guardas redundantes se tapaban entre sí y ninguna estaba
    probada de verdad."""
    encontrados = list(avisos_del_repositorio())
    assert len(encontrados) >= 12, encontrados
    assert len({t for _, _, t, _ in encontrados}) >= 8


def test_la_guarda_de_arriba_reconoce_un_aviso_sin_numero():
    """Y que sepa distinguir. Se le da a mano un aviso sin identificador."""
    fuente = '''
create_notification(user_id=x, title="t", message="m",
                    notification_type="withdrawal_completed",
                    data={"otra_cosa": 1})
'''
    arbol = ast.parse(fuente)
    llamada = next(n for n in ast.walk(arbol) if isinstance(n, ast.Call)
                   and getattr(n.func, "id", None) == "create_notification")
    data = ast.unparse(next(k.value for k in llamada.keywords if k.arg == "data"))
    assert not any(i in data for i in IDENTIFICADORES)
