"""Lo que te queda a vos en cada operación, y la firma de los pedidos salientes.

QUE PASABA

    La ganancia estaba metida en la tasa y NO QUEDABA ESCRITA EN NINGUN LADO:
    la operación guardaba la tasa que vio el cliente y nada más. Se puede
    calcular después con un informe, pero lo que no se registra hoy no se
    recupera nunca, y el día que haya un proveedor con qué comparar la
    historia anterior no existiría.

LO QUE SE PRUEBA

    1. Que la comisión salga de las DOS tasas de la operación y no de un
       porcentaje nominal, en aritmética exacta.
    2. Que de fábrica esto no haga NADA: ni anote, ni rechace.
    3. Que prendido y sin tasa de costo, la operación NO se procese.
    4. Que el cliente no vea ni el costo ni la comisión.
    5. Que la firma saliente y la verificación entrante cierren, que la marca
       de tiempo vieja se rechace y que una firma torcida no levante.
"""
import asyncio
import os
import sys
from decimal import Decimal

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base, ensenarle_decimal128_a_mongomock   # noqa: E402
from services import comisiones, configuracion, firma              # noqa: E402
from services.money import to_decimal128                           # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    ensenarle_decimal128_a_mongomock()
    b = mongomock_motor.AsyncMongoMockClient()["ris_comisiones"]
    usar_base(b)
    yield b


async def _prender(base, costo="260.00"):
    await configuracion.escribir(base, "comision_registrar", 1)
    if costo is not None:
        await configuracion.escribir(base, "costo_ris_to_ves", configuracion.normalizar("costo_ris_to_ves", costo)[0])


# ══════════════════════════════════════════════════════════════════════════
# 1. La cuenta
# ══════════════════════════════════════════════════════════════════════════

def test_la_comision_sale_de_las_dos_tasas_y_no_de_un_porcentaje():
    """El cliente pone 100 a una tasa de 250; a vos conseguir esos bolívares
    te sale a 260. Los 25.000 VES te costaron 96,15 RIS: quedan 3,85."""
    c = comisiones.calcular(monto_cliente="100", tasa_cliente="250",
                            tasa_costo="260")
    assert c == Decimal("3.85"), c


def test_LOS_DOS_DECIMALES_DE_LA_TASA_MUEVEN_LA_COMISION():
    """La limitación del módulo, fijada acá para que no se descubra tarde.

    El catálogo de configuración guarda la plata con DOS decimales, y la tasa
    de costo va ahí. Con una tasa cercana a uno —el precio de un dólar cripto
    en reales, por ejemplo— el segundo decimal vale casi dos décimas de por
    ciento, y sobre un margen del uno por ciento eso es un error enorme.

    Lo descubrió este test: se escribió esperando 9,02 (la cuenta con la tasa
    exacta 1,0091) y dio 9,90, porque la tasa se redondeó a 1,01. No es un
    defecto del cálculo: es el alcance de hoy, y queda escrito.

    Para las tasas que la aplicación tiene hoy —bolívares por real, números
    grandes— dos decimales sobran. El día que aparezca una tasa cercana a uno,
    el catálogo necesita un tipo con más decimales y ESTE TEST SE PONE ROJO.
    """
    con_redondeo = comisiones.calcular(monto_cliente="1000", tasa_cliente="1",
                                       tasa_costo="1.0091")
    assert con_redondeo == Decimal("9.90"), con_redondeo
    # Y una tasa grande, que es el caso real de hoy: el tercer decimal no
    # cambia nada porque no hay tercer decimal que perder.
    grande = comisiones.calcular(monto_cliente="100", tasa_cliente="250.00",
                                 tasa_costo="260.004")
    assert grande == Decimal("3.85"), grande


def test_sin_los_numeros_no_se_inventa_una_comision():
    for caso in [
        {"monto_cliente": "0", "tasa_cliente": "250", "tasa_costo": "260"},
        {"monto_cliente": "100", "tasa_cliente": "0", "tasa_costo": "260"},
        {"monto_cliente": "100", "tasa_cliente": "250", "tasa_costo": "0"},
        {"monto_cliente": "100", "tasa_cliente": "250", "tasa_costo": "-1"},
        {"monto_cliente": "abc", "tasa_cliente": "250", "tasa_costo": "260"},
        {"monto_cliente": None, "tasa_cliente": "250", "tasa_costo": "260"},
    ]:
        assert comisiones.calcular(**caso) is None, caso


# ══════════════════════════════════════════════════════════════════════════
# 2. De fábrica no hace nada
# ══════════════════════════════════════════════════════════════════════════

def test_de_fabrica_no_anota_nada_y_no_rechaza_nada(base):
    """Lo más importante del cambio: desplegarlo no cambia el comportamiento
    de la aplicación. Una guarda cerrada que se despliega prendida frena la
    plata de todo el mundo en el minuto cero."""
    async def cuerpo():
        assert await comisiones.esta_prendida(base) is False
        campos = await comisiones.campos_de(
            base, via="ris_to_ves", monto_cliente="100", tasa_cliente="250")
        assert campos == {}
    corre(cuerpo())


def test_de_fabrica_ni_siquiera_mira_la_tasa_de_costo(base):
    """Apagado, una tasa de costo sin cargar no puede molestar a nadie."""
    async def cuerpo():
        await configuracion.escribir(base, "costo_ris_to_ves", configuracion.normalizar("costo_ris_to_ves", "0")[0])
        assert await comisiones.campos_de(
            base, via="ris_to_ves", monto_cliente="100",
            tasa_cliente="250") == {}
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 3. Prendido: cerrado por omisión
# ══════════════════════════════════════════════════════════════════════════

def test_prendido_guarda_las_dos_tasas_y_la_comision(base):
    async def cuerpo():
        await _prender(base, costo="260.00")
        campos = await comisiones.campos_de(
            base, via="ris_to_ves", monto_cliente="100", tasa_cliente="250")
        assert set(campos) == {"tasa_cliente", "tasa_costo", "comision",
                               "proveedor_ref"}
        assert campos["comision"].to_decimal() == Decimal("3.85")
        assert campos["tasa_costo"].to_decimal() == Decimal("260.00")
        assert campos["proveedor_ref"] is None, "el hueco del proveedor va vacío"
    corre(cuerpo())


def test_prendido_y_SIN_tasa_de_costo_la_operacion_no_se_procesa(base):
    """Cerrado por omisión, igual que la tasa de cambio. Una operación cuyo
    costo nadie conoce es una cuya ganancia nadie va a poder calcular."""
    async def cuerpo():
        await _prender(base, costo=None)
        with pytest.raises(comisiones.FaltaLaTasaDeCosto):
            await comisiones.campos_de(base, via="ris_to_ves",
                                       monto_cliente="100", tasa_cliente="250")
    corre(cuerpo())


def test_una_tasa_de_costo_en_cero_es_NO_CARGADA_y_no_gratis(base):
    async def cuerpo():
        await _prender(base, costo="0")
        assert await comisiones.tasa_de_costo(base, "ris_to_ves") is None
        with pytest.raises(comisiones.FaltaLaTasaDeCosto):
            await comisiones.campos_de(base, via="ris_to_ves",
                                       monto_cliente="100", tasa_cliente="250")
    corre(cuerpo())


def test_una_via_sin_tasa_de_costo_declarada_tambien_frena(base):
    """El catálogo `COSTO_DE_LA_VIA` es la lista de lo permitido. Una vía que
    no está no se procesa en silencio con comisión cero: se rechaza."""
    async def cuerpo():
        await _prender(base)
        assert await comisiones.tasa_de_costo(base, "inventada") is None
        with pytest.raises(comisiones.FaltaLaTasaDeCosto):
            await comisiones.campos_de(base, via="inventada",
                                       monto_cliente="100", tasa_cliente="250")
    corre(cuerpo())


# ══════════════════════════════════════════════════════════════════════════
# 4. El cliente no ve tu costo
# ══════════════════════════════════════════════════════════════════════════

def test_el_cliente_NO_ve_el_costo_ni_la_comision():
    """Es lo que da gratis la lista de lo permitido, y por eso se fija acá:
    con una lista de lo prohibido, cada campo nuevo se filtra hasta que
    alguien se acuerde de agregarlo."""
    from routes.transactions import LO_QUE_VE_EL_CLIENTE
    for campo in ("tasa_costo", "comision", "proveedor_ref"):
        assert campo not in LO_QUE_VE_EL_CLIENTE, campo
    # Y que de verdad sea una lista de lo PERMITIDO y no de lo prohibido.
    assert all(v == 1 for k, v in LO_QUE_VE_EL_CLIENTE.items() if k != "_id")


def test_los_dos_ajustes_estan_en_el_catalogo_del_panel():
    """Configurar no puede requerir editar código. Y al estar en el catálogo,
    la pantalla los dibuja sola: no hace falta tocar el frontend."""
    for clave in (comisiones.AJUSTE_PRENDIDA, "costo_ris_to_ves"):
        assert clave in configuracion.AJUSTES, clave
    assert configuracion.AJUSTES[comisiones.AJUSTE_PRENDIDA].defecto == 0, \
        "tiene que venir apagado de fábrica"


def test_cada_via_apunta_a_un_ajuste_que_existe():
    """Una vía que apunta a un ajuste inexistente no cobra nada y no avisa."""
    for via, clave in comisiones.COSTO_DE_LA_VIA.items():
        assert clave in configuracion.AJUSTES, (via, clave)


# ══════════════════════════════════════════════════════════════════════════
# 5. La firma
# ══════════════════════════════════════════════════════════════════════════

SECRETO = "una-clave-compartida-de-prueba"
CUERPO = b'{"monto":"100.00","destino":"X"}'


def test_lo_que_se_firma_se_verifica():
    cabeceras = firma.firmar(SECRETO, CUERPO, marca=1_800_000_000)
    assert firma.verificar(SECRETO, CUERPO, cabeceras[firma.CABECERA],
                           ahora=1_800_000_000) is True


def test_con_otra_clave_no_valida():
    cabeceras = firma.firmar(SECRETO, CUERPO, marca=1_800_000_000)
    assert firma.verificar("otra-clave", CUERPO, cabeceras[firma.CABECERA],
                           ahora=1_800_000_000) is False


def test_si_el_cuerpo_cambia_un_byte_no_valida():
    """El motivo de firmar el cuerpo EXACTO y no el diccionario: volver a
    serializarlo con las claves en otro orden da otra firma."""
    cabeceras = firma.firmar(SECRETO, CUERPO, marca=1_800_000_000)
    assert firma.verificar(SECRETO, CUERPO + b" ", cabeceras[firma.CABECERA],
                           ahora=1_800_000_000) is False


@pytest.mark.parametrize("desfase", [301, -301, 100_000])
def test_una_firma_vieja_o_del_futuro_se_rechaza(desfase):
    """Sin ventana, quien capture un pedido lo repite mañana y vale igual.
    Y del futuro también: con el reloj adelantado se fabrica una que dura."""
    cabeceras = firma.firmar(SECRETO, CUERPO, marca=1_800_000_000)
    assert firma.verificar(SECRETO, CUERPO, cabeceras[firma.CABECERA],
                           ahora=1_800_000_000 + desfase) is False


@pytest.mark.parametrize("desfase", [0, 299, -299])
def test_dentro_de_la_ventana_sigue_valiendo(desfase):
    cabeceras = firma.firmar(SECRETO, CUERPO, marca=1_800_000_000)
    assert firma.verificar(SECRETO, CUERPO, cabeceras[firma.CABECERA],
                           ahora=1_800_000_000 + desfase) is True


@pytest.mark.parametrize("cabecera", [
    "", None, "cualquier cosa", "ts=,v1=", "ts=hola,v1=abc",
    "v1=abc", "ts=1800000000", "ts=1800000000,v1=",
])
def test_una_cabecera_torcida_devuelve_False_y_no_levanta(cabecera):
    """Un verificador que levanta con una entrada rara se tumba desde afuera."""
    assert firma.verificar(SECRETO, CUERPO, cabecera, ahora=1_800_000_000) is False


def test_la_firma_no_se_compara_con_el_igual():
    """Comparar secretos con `==` corta en la primera letra distinta: tarda
    distinto según cuánto acertaste, y eso alcanza para adivinarla byte a
    byte. Es la guarda más fácil de perder en un refactor."""
    import pathlib
    fuente = pathlib.Path(_BACKEND, "services", "firma.py").read_text(encoding="utf-8")
    assert "compare_digest" in fuente
    assert "esperada == firma" not in fuente


# ══════════════════════════════════════════════════════════════════════════
# 6. El enganche en el envío de verdad
# ══════════════════════════════════════════════════════════════════════════

async def _sembrar_un_envio(base):
    """Una cuenta con saldo, un beneficiario y una tasa. Lo mínimo para que
    `create_withdrawal` llegue hasta el final."""
    await base.users.insert_one({
        "user_id": "u_1", "email": "cliente@ejemplo.com", "name": "Cliente",
        "role": "user", "is_active": True, "verification_status": "verified",
        "balance_ris": to_decimal128("500.00")})
    await base.beneficiaries.insert_one({
        "beneficiary_id": "b_1", "user_id": "u_1", "full_name": "Destino",
        "bank": "BCO", "account_number": "123"})
    await base.rates.insert_one({"ris_to_ves": 250.0, "updated_at": 1})


def test_de_punta_a_punta_el_envio_guarda_la_comision(base):
    """El enganche de verdad, con la ruta del dinero entera. Sin esto se puede
    borrar la llamada de `routes/transactions.py` y todo sigue en verde."""
    from models.requests import WithdrawalRequest
    from models.user import User
    from routes import transactions as tx

    async def cuerpo():
        await _sembrar_un_envio(base)
        await _prender(base, costo="260.00")
        usuario = User(user_id="u_1", email="cliente@ejemplo.com",
                       name="Cliente", role="user",
                       verification_status="verified")
        await tx.create_withdrawal(
            WithdrawalRequest(amount=100.0, beneficiary_id="b_1",
                              idempotency_key="k-1"),
            current_user=usuario)
        guardada = await base.transactions.find_one({"user_id": "u_1"}, {"_id": 0})
        assert guardada["comision"].to_decimal() == Decimal("3.85")
        assert guardada["tasa_costo"].to_decimal() == Decimal("260.00")
        assert guardada["proveedor_ref"] is None
    corre(cuerpo())


def test_de_punta_a_punta_sin_tasa_de_costo_NO_se_debita_nada(base):
    """Lo que justifica que el cálculo vaya ANTES del débito: el rechazo deja
    el saldo intacto. Calculado después, habría que devolver plata ya movida."""
    from fastapi import HTTPException
    from models.requests import WithdrawalRequest
    from models.user import User
    from routes import transactions as tx

    async def cuerpo():
        await _sembrar_un_envio(base)
        await _prender(base, costo=None)
        usuario = User(user_id="u_1", email="cliente@ejemplo.com",
                       name="Cliente", role="user",
                       verification_status="verified")
        with pytest.raises(HTTPException) as e:
            await tx.create_withdrawal(
                WithdrawalRequest(amount=100.0, beneficiary_id="b_1",
                                  idempotency_key="k-2"),
                current_user=usuario)
        assert e.value.status_code == 503
        doc = await base.users.find_one({"user_id": "u_1"}, {"_id": 0, "balance_ris": 1})
        assert doc["balance_ris"].to_decimal() == Decimal("500.00"), "se debitó igual"
        assert await base.transactions.count_documents({}) == 0
    corre(cuerpo())


def test_no_se_puede_REFRESCAR_la_marca_y_reusar_la_firma():
    """El ataque que la ventana sola NO ataja, y por el que la marca de tiempo
    tiene que ir DENTRO de lo firmado.

    Quien capture un pedido tiene el cuerpo y la firma. Si la marca viajara
    sólo en la cabecera y no estuviera firmada, le bastaría con cambiarla por
    una fresca: la firma seguiría siendo válida, la ventana la vería nueva, y
    el pedido se podría repetir para siempre.

    Lo encontró una mutación: sacar la marca de la cadena firmada NO ponía
    ningún test en rojo, porque firmar y verificar usaban la misma función
    rota y se seguían dando la mano.
    """
    original = firma.firmar(SECRETO, CUERPO, marca=1_800_000_000)[firma.CABECERA]
    v1 = dict(p.split("=", 1) for p in original.split(","))["v1"]
    fresca = 1_800_000_000 + 10_000
    forjada = f"ts={fresca},v1={v1}"
    assert firma.verificar(SECRETO, CUERPO, forjada, ahora=fresca) is False
