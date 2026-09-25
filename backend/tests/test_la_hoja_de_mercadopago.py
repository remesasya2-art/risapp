"""
tests/test_la_hoja_de_mercadopago.py — Qué nos avisó Mercado Pago.

POR QUE EXISTE ESTE ARCHIVO

    El 20 de septiembre de 2026 un cliente pagó con PIX y su envío no avanzó.
    Averiguar si Mercado Pago había llamado costó leer código: de todo lo que
    nos avisa, NO SE GUARDABA NADA. La única huella era el registro del
    servidor, que se rota, que nadie abre a las tres de la mañana, y que no se
    puede filtrar por fecha ni buscar por referencia.

    El historial está en `docs/incidentes/`.

LO QUE ESTE ARCHIVO NO DEJA QUE SE ROMPA

    1. Que la fila quede SIEMPRE, termine como termine el aviso. Una hoja que
       sólo guarda los que salen bien no sirve para investigar — que es para
       lo único que se la necesita.
    2. Que se pueda buscar por cualquiera de los tres identificadores.
    3. Que el filtro de fecha y hora funcione.
    4. Que anotar no pueda frenar un pago. Es un registro, no una operación.
    5. Que no salga nada que no tenga que salir.
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

from conftest import usar_base                                # noqa: E402
from services import hoja_de_mercadopago as hoja              # noqa: E402


def corre(coro):
    return asyncio.run(coro)


def ahora():
    return datetime.now(timezone.utc)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def una_fila(base, **kw):
    anotacion = corre(hoja.anotar_que_llego(
        base, mp_payment_id=kw.pop("mp_payment_id", 123),
        tipo_de_evento=kw.pop("tipo_de_evento", "payment.updated")))
    if kw:
        corre(hoja.anotar_como_termino(base, anotacion, **kw))
    return anotacion


def filas(base, **kw):
    return corre(hoja.buscar(base, **kw))["filas"]


# ══════════════════════════════════════════════════════════════════════════
# 1. LA FILA QUEDA SIEMPRE. Es todo el punto.
# ══════════════════════════════════════════════════════════════════════════

def test_UN_AVISO_QUE_NO_ENCUENTRA_EL_COBRO_DEJA_FILA(base):
    """El caso del incidente.

    Ese aviso llegó, no encontró nada y se fue. Sin fila, no había forma de
    saber siquiera que Mercado Pago había llamado.
    """
    una_fila(base, mp_payment_id=999, como=hoja.SIN_ACREDITAR,
             motivo="No coincide con ningún cobro nuestro.")
    encontradas = filas(base)
    assert len(encontradas) == 1
    assert encontradas[0]["como_termino"] == hoja.SIN_ACREDITAR
    assert "coincide" in encontradas[0]["motivo"]


def test_un_aviso_que_SI_se_acredito_tambien(base):
    """Si sólo quedaran los que fallan, no habría con qué comparar."""
    una_fila(base, como=hoja.ACREDITADO, monto=100.0)
    assert filas(base)[0]["como_termino"] == hoja.ACREDITADO


def test_UNA_FILA_A_MEDIAS_ES_UNA_PISTA(base):
    """Si algo revienta entre que llega el aviso y que se decide qué hacer, la
    fila queda con el desenlace en blanco. Eso dice «acá pasó algo raro», que
    es infinitamente más de lo que decía no tener nada."""
    una_fila(base)     # se anota que llegó y no se cierra
    fila = filas(base)[0]
    assert fila["como_termino"] == hoja.SIN_TERMINAR
    assert fila["llego_a_las"] is not None
    assert fila.get("termino_a_las") is None


def test_cada_desenlace_tiene_nombre_en_castellano():
    """La hoja la lee quien atiende el chat, no quien escribió esto."""
    for clave, texto in hoja.COMO_TERMINO.items():
        assert texto and texto[0].isupper()
    assert set(hoja.COMO_TERMINO) == {
        hoja.ACREDITADO, hoja.SIN_ACREDITAR, hoja.IGNORADO, hoja.SIN_TERMINAR}


# ══════════════════════════════════════════════════════════════════════════
# 2. La lupa: buscar por cualquiera de los tres identificadores
# ══════════════════════════════════════════════════════════════════════════

def test_SE_BUSCA_POR_EL_DE_MERCADO_PAGO(base):
    """El que quien busca saca del panel de Mercado Pago."""
    una_fila(base, mp_payment_id=111, como=hoja.ACREDITADO)
    una_fila(base, mp_payment_id=222, como=hoja.ACREDITADO)
    assert len(filas(base, texto="111")) == 1


def test_se_busca_por_NUESTRA_referencia(base):
    """El que sale del cobro: `venv_...`, `brl_...`, `gpix_...`."""
    una_fila(base, como=hoja.ACREDITADO, referencia="venv_abc123")
    una_fila(base, como=hoja.ACREDITADO, referencia="venv_otra")
    assert len(filas(base, texto="venv_abc123")) == 1


def test_se_busca_por_el_de_LA_OPERACION(base):
    """El que sale del historial del cliente. Quien busca tiene UNO de los
    tres en la mano; obligarlo a saber cuál es obligarlo a saber cómo está
    hecho esto por dentro."""
    una_fila(base, como=hoja.ACREDITADO, transaction_id="tx_999")
    assert len(filas(base, texto="tx_999")) == 1


def test_se_busca_por_el_VALOR_EXACTO(base):
    """Son identificadores, no nombres. Una búsqueda por parecido sobre una
    tabla que crece con cada pago es una consulta que un día tarda diez
    segundos."""
    una_fila(base, como=hoja.ACREDITADO, referencia="venv_abc123")
    assert filas(base, texto="venv_abc") == []


def test_buscar_algo_que_no_esta_no_rompe(base):
    una_fila(base, como=hoja.ACREDITADO)
    assert filas(base, texto="no_existe") == []


# ══════════════════════════════════════════════════════════════════════════
# 3. El filtro de fecha y hora
# ══════════════════════════════════════════════════════════════════════════

def test_FILTRA_POR_FECHA_Y_HORA(base):
    """«El cliente dice que pagó anoche» es el modo en que llega el 90 % de
    estas consultas."""
    vieja = una_fila(base, mp_payment_id=1, como=hoja.ACREDITADO)
    corre(base[hoja.COLECCION].update_one(
        {"anotacion_id": vieja},
        {"$set": {"llego_a_las": ahora() - timedelta(days=3)}}))
    una_fila(base, mp_payment_id=2, como=hoja.ACREDITADO)

    recientes = filas(base, desde=ahora() - timedelta(hours=1))
    assert len(recientes) == 1
    assert recientes[0]["mp_payment_id"] == "2"


def test_filtra_hasta_una_fecha(base):
    reciente = una_fila(base, mp_payment_id=1, como=hoja.ACREDITADO)
    assert filas(base, hasta=ahora() - timedelta(days=1)) == []
    assert len(filas(base, hasta=ahora() + timedelta(minutes=1))) == 1


def test_se_puede_filtrar_por_COMO_TERMINO(base):
    """«Mostrame los que no se acreditaron» es la consulta que encuentra los
    problemas antes de que el cliente reclame."""
    una_fila(base, mp_payment_id=1, como=hoja.ACREDITADO)
    una_fila(base, mp_payment_id=2, como=hoja.SIN_ACREDITAR)
    sin = filas(base, como_termino=hoja.SIN_ACREDITAR)
    assert len(sin) == 1 and sin[0]["mp_payment_id"] == "2"


def test_LO_MAS_NUEVO_VA_PRIMERO(base):
    """Quien abre la hoja viene por lo de recién, no por lo del mes pasado."""
    vieja = una_fila(base, mp_payment_id=1, como=hoja.ACREDITADO)
    corre(base[hoja.COLECCION].update_one(
        {"anotacion_id": vieja},
        {"$set": {"llego_a_las": ahora() - timedelta(days=2)}}))
    una_fila(base, mp_payment_id=2, como=hoja.ACREDITADO)
    assert [f["mp_payment_id"] for f in filas(base)] == ["2", "1"]


def test_se_pagina(base):
    for i in range(5):
        una_fila(base, mp_payment_id=i, como=hoja.ACREDITADO)
    r = corre(hoja.buscar(base, pagina=1, por_pagina=2))
    assert r["total"] == 5 and len(r["filas"]) == 2


def test_no_se_puede_pedir_una_pagina_gigante(base):
    """Una consulta sin techo es la que tumba la base el día que la tabla
    tiene un millón de filas."""
    for i in range(3):
        una_fila(base, mp_payment_id=i, como=hoja.ACREDITADO)
    assert corre(hoja.buscar(base, por_pagina=99999))["por_pagina"] <= 200


# ══════════════════════════════════════════════════════════════════════════
# 4. Anotar no puede frenar un pago
# ══════════════════════════════════════════════════════════════════════════

def test_SI_NO_SE_PUEDE_ANOTAR_EL_PAGO_SIGUE(base, monkeypatch):
    """Esto es un registro, no una operación. Que no se pueda anotar sería
    cambiar un problema de papeles por uno de plata."""
    class BaseRota:
        def __getitem__(self, _):
            raise RuntimeError("la base no contesta")

    assert corre(hoja.anotar_que_llego(
        BaseRota(), mp_payment_id=1, tipo_de_evento="payment")) == ""


def test_cerrar_una_anotacion_que_no_existe_no_rompe(base):
    corre(hoja.anotar_como_termino(base, "", como=hoja.ACREDITADO))
    corre(hoja.anotar_como_termino(base, "mpa_fantasma", como=hoja.ACREDITADO))


def test_cerrar_NO_PISA_lo_que_ya_estaba(base):
    """Un `None` guardado tapa el dato de una anotación anterior."""
    a = una_fila(base, como=hoja.SIN_ACREDITAR, referencia="venv_1", monto=50.0)
    corre(hoja.anotar_como_termino(base, a, como=hoja.ACREDITADO))
    fila = filas(base)[0]
    assert fila["referencia"] == "venv_1", "se borró la referencia al cerrar"
    assert fila["monto"] == 50.0


# ══════════════════════════════════════════════════════════════════════════
# 5. Lo que NO sale
# ══════════════════════════════════════════════════════════════════════════

def test_NO_SALE_NADA_QUE_NO_ESTE_DECLARADO(base):
    """El cuerpo que manda Mercado Pago trae datos del pagador. Sale por lista
    de lo permitido justamente para que un campo nuevo no se cuele a una
    pantalla que el equipo mira todos los días."""
    a = una_fila(base, como=hoja.ACREDITADO)
    corre(base[hoja.COLECCION].update_one(
        {"anotacion_id": a},
        {"$set": {"correo_del_pagador": "alguien@ejemplo.com",
                  "mp_response": {"payer": {"email": "otro@ejemplo.com"}}}}))
    plano = str(filas(base))
    assert "alguien@ejemplo.com" not in plano
    assert "mp_response" not in plano


def test_el_contrato_de_la_ruta_es_por_lista_de_lo_permitido():
    fuente = (_BACKEND / "routes" / "admin" / "reportes.py").read_text(encoding="utf-8")
    assert "response_model=LaHojaDeMercadoPago" in fuente


# ══════════════════════════════════════════════════════════════════════════
# 6. Que el receptor la alimente de verdad
# ══════════════════════════════════════════════════════════════════════════

def _cuerpo_del_receptor():
    fuente = (_BACKEND / "routes" / "gestor_pix.py").read_text(encoding="utf-8")
    i = fuente.index("async def mercadopago_webhook(")
    c = fuente[i:]
    return c[:c.find("\n@")] if "\n@" in c else c


def test_LA_HOJA_SE_ABRE_APENAS_LLEGA_EL_AVISO():
    """Antes de cualquier comprobación. Si se anotara al final, los avisos que
    revientan en el medio no dejarían fila — y son justo los que hay que
    investigar."""
    cuerpo = _cuerpo_del_receptor()
    i = cuerpo.index("anotar_que_llego")
    for despues in ("gestor_pix_payments.find_one", "get_payment_status",
                    "amount_mismatch"):
        assert i < cuerpo.index(despues), (
            f"la hoja se abre después de «{despues}»: lo que falle antes no "
            f"deja rastro")


def test_TODAS_LAS_SALIDAS_CIERRAN_SU_FILA():
    """Una salida que no cierra deja una fila «a medias» que no lo está: quien
    la mire va a buscar un problema que no existe."""
    cuerpo = _cuerpo_del_receptor()
    assert cuerpo.count("await _cerrar(") == 8, (
        f"hay {cuerpo.count('await _cerrar(')} cierres: alguna salida dejó de "
        f"anotar en qué terminó")


def test_la_hoja_se_escribe_DESPUES_de_comprobar_la_firma():
    """Lo que no pasa la firma no viene de Mercado Pago: viene de cualquiera
    que conozca la dirección. Guardarlo sería dejar que un desconocido escriba
    en nuestra hoja."""
    cuerpo = _cuerpo_del_receptor()
    assert cuerpo.index("invalid_signature") < cuerpo.index("anotar_que_llego")


# ══════════════════════════════════════════════════════════════════════════
# 7. Que se pueda llegar a la hoja
# ══════════════════════════════════════════════════════════════════════════
#
#   Una pantalla que nadie puede abrir es una pantalla que no existe. En este
#   panel eso ya pasó y por eso hay un test —`test_el_menu_del_panel.py`— que
#   exige que toda sección esté en algún grupo. Acá se comprueba lo otro: que
#   la sección exista, que el componente esté importado y que haya algo que lo
#   dibuje.

_PANEL = _BACKEND.parent / "frontend" / "src" / "pages" / "AdminPanel.jsx"


def test_LA_HOJA_SE_PUEDE_ABRIR_DESDE_EL_PANEL():
    panel = _PANEL.read_text(encoding="utf-8")
    assert "key: 'hoja_mp'" in panel, "la sección no está en el catálogo"
    assert "import HojaDeMercadoPago from" in panel, "falta importar la pantalla"
    assert "<HojaDeMercadoPago />" in panel, "nada dibuja la pantalla"
    assert "activeTab === 'hoja_mp'" in panel, (
        "la pantalla está importada pero ninguna condición la muestra")


def test_la_hoja_esta_en_OPERACION():
    """Donde se pidió. No en Contabilidad: no se abre para cuadrar el mes, se
    abre cuando un cobro de hoy no apareció."""
    panel = _PANEL.read_text(encoding="utf-8")
    i = panel.index("key: 'g_operacion'")
    grupo = panel[i:panel.index("key: 'g_clientes'")]
    assert "'hoja_mp'" in grupo


def test_LA_VE_UN_ADMINISTRADOR_Y_NO_SOLO_EL_SUPER():
    """La puerta del panel tiene que decir lo mismo que la del backend
    (`get_admin_user`). Si acá se marcara `superAdminOnly`, quien atiende no
    la vería aunque el servidor se la deje abrir."""
    panel = _PANEL.read_text(encoding="utf-8")
    i = panel.index("key: 'hoja_mp'")
    ficha = panel[i:panel.index("\n", i)]
    assert "superAdminOnly" not in ficha

    ruta = (_BACKEND / "routes" / "admin" / "reportes.py").read_text(encoding="utf-8")
    j = ruta.index('@router.get("/hoja-mercadopago"')
    cuerpo = ruta[j:ruta.index('"""', ruta.index('"""', j) + 3)]
    assert "Depends(get_admin_user)" in cuerpo
