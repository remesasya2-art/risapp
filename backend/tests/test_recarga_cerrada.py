"""
tests/test_recarga_cerrada.py — No se custodia dinero: se cierra la recarga.

POR QUE EXISTE ESTE ARCHIVO

    La empresa no puede custodiar dinero de terceros ni ofrecer recarga. El
    estado al que va la aplicación es «no entra saldo nuevo»; el por qué está
    en `services/recarga_abierta.py` y en `docs/politica-pld-ft.md`.

LAS CUATRO COSAS QUE ESTE ARCHIVO NO DEJA QUE SE ROMPAN

    1. QUE CERRAR LA RECARGA NO DEJE LA APP SIN FORMA DE ENVIAR.

       Es lo más importante. «Gastar en Venezuela» y «Gastar en Brasil» EXIGEN
       saldo cargado. Cerrar la carga con el pago al final apagado deja la
       aplicación muerta: no se puede cargar, y sin carga no se puede gastar.
       Y no lo diría ninguna pantalla — simplemente nada funcionaría.

       El panel lo rechaza, con el motivo, ANTES de escribir nada.

    2. QUE SE CIERREN LAS CUATRO PUERTAS Y NO TRES.

       PIX, la cotización de la tarjeta, el cobro con tarjeta, y la
       transferencia en bolívares. Una que se olvide es la recarga abierta por
       un costado.

    3. QUE GASTAR EL SALDO SIGA FUNCIONANDO.

       Quien ya tiene saldo lo sigue usando. Cerrarle también la salida sería
       atraparle la plata, que es lo que `services/personal.py` llama peor que
       la regla que se quiso cumplir.

    4. QUE NO SE CONFUNDA CARGAR SALDO CON PAGAR UN ENVIO.

       `/recharge/ves` y `/enviar-reais/comprobante` reciben las dos una
       transferencia en bolívares con su comprobante. La primera carga saldo
       —se cierra—; la segunda paga un envío —sigue abierta—. Ponerle la
       guarda a la segunda mataría el corredor a Brasil.
"""
import asyncio
import os
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))

_REPO = _BACKEND.parent

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from fastapi import HTTPException                             # noqa: E402

from conftest import usar_base                                # noqa: E402
from services import configuracion as cfg                     # noqa: E402
from services import pago_al_final as paf                     # noqa: E402
from services import recarga_abierta as ra                    # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def poner(base, clave, valor):
    normalizado, error = cfg.normalizar(clave, valor)
    assert error is None, f"el panel rechazaría {valor}: {error}"
    corre(cfg.escribir(base, clave, normalizado))


# ══════════════════════════════════════════════════════════════════════════
# 1. El estado de fábrica
# ══════════════════════════════════════════════════════════════════════════

def test_DE_FABRICA_LA_RECARGA_SIGUE_ABIERTA(base):
    """El despliegue no puede ser el que apague la recarga: en ese mismo
    instante los envíos —que exigen saldo— se quedarían sin financiarse.

    El estado al que se va es cerrada, pero se llega con dos clics del panel,
    en orden, no fusionando."""
    assert corre(ra.esta_abierta(base)) is True


def test_cerrada_frena_con_503(base):
    poner(base, paf.CLAVE, 1)          # primero el seguro, si no no deja
    poner(base, ra.CLAVE, ra.CERRADA)
    with pytest.raises(HTTPException) as e:
        corre(ra.exigir_abierta(base))
    assert e.value.status_code == 503


def test_el_mensaje_nombra_la_via_que_SI_funciona(base):
    """Sin eso, «no disponible» lo manda a soporte a preguntar qué hacer."""
    assert "al final" in ra.SIN_RECARGA
    assert "envi" in ra.SIN_RECARGA.lower()


# ══════════════════════════════════════════════════════════════════════════
# 2. El seguro: no dejar la aplicación sin forma de enviar
# ══════════════════════════════════════════════════════════════════════════

def test_NO_SE_PUEDE_CERRAR_LA_RECARGA_CON_EL_PAGO_AL_FINAL_APAGADO(base):
    """El test más importante del archivo.

    Con los dos apagados no se puede cargar saldo, y sin saldo no se puede
    enviar: la aplicación queda sin ninguna forma de mover plata. Ninguna
    pantalla lo diría.
    """
    queda = {ra.CLAVE: ra.CERRADA, "pago_al_final": 0}
    motivo = corre(cfg.revisar_las_parejas(base, queda))
    assert motivo is not None, (
        "el panel deja cerrar la recarga sin pago al final: la aplicación "
        "queda sin ninguna forma de enviar")
    assert "nadie podría enviar" in motivo


def test_el_motivo_dice_QUE_HACER_y_no_solo_que_no(base):
    """Un rechazo que no dice el orden correcto obliga a adivinar."""
    motivo = corre(cfg.revisar_las_parejas(
        base, {ra.CLAVE: ra.CERRADA, "pago_al_final": 0}))
    assert "Prendé primero" in motivo


def test_con_el_pago_al_final_prendido_SI_se_puede_cerrar(base):
    motivo = corre(cfg.revisar_las_parejas(
        base, {ra.CLAVE: ra.CERRADA, "pago_al_final": 1}))
    assert motivo is None


def test_el_seguro_mira_COMO_QUEDARIA_y_no_lo_que_se_mando(base):
    """La pantalla puede mandar un solo campo.

    Si ya está guardado «pago al final = 0» y alguien manda sólo «recarga =
    0», comprobar únicamente lo enviado dejaría pasar el caso. Es la misma
    lección que la pareja de mínimo y máximo de PIX, escrita en esa función.
    """
    poner(base, paf.CLAVE, 0)
    motivo = corre(cfg.revisar_las_parejas(base, {ra.CLAVE: ra.CERRADA}))
    assert motivo is not None, (
        "el seguro miró sólo lo enviado y no cómo quedaría todo")


def test_el_seguro_corre_ANTES_de_escribir_nada(base):
    """Escribir uno y después rechazar el otro dejaría la configuración a
    medio camino, que es peor que rechazar las dos cosas."""
    fuente = (_BACKEND / "services" / "configuracion.py").read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("async def revisar_las_parejas("):]
    cuerpo = cuerpo[:cuerpo.index("\nasync def ")]
    assert "motivo_si_deja_la_app_sin_salida" in cuerpo
    # Y la función entera es de sólo lectura: no escribe.
    for prohibido in ("escribir(", "update_one", "insert_one"):
        assert prohibido not in cuerpo, (
            f"`revisar_las_parejas` escribe («{prohibido}»): tiene que sólo mirar")


# ══════════════════════════════════════════════════════════════════════════
# 3. Las cuatro puertas, y las que NO se cierran
# ══════════════════════════════════════════════════════════════════════════

PUERTAS = (
    ("routes/gestor_pix.py", "create_pix_payment"),          # PIX
    ("routes/payments_card.py", "quote_card_payment"),       # cotizar tarjeta
    ("routes/payments_card.py", "process_card_payment"),     # cobrar tarjeta
    ("routes/transactions.py", "recharge_ves"),              # bolívares
)


def _cuerpo(archivo, funcion):
    fuente = (_BACKEND / archivo).read_text(encoding="utf-8")
    i = fuente.index(f"async def {funcion}(")
    resto = fuente[i:]
    fin = resto.find("\n@router")
    return resto if fin < 0 else resto[:fin]


@pytest.mark.parametrize("archivo, funcion", PUERTAS)
def test_cada_puerta_de_recarga_pregunta_por_la_guarda(archivo, funcion):
    """Una que se olvide es la recarga abierta por un costado."""
    cuerpo = _cuerpo(archivo, funcion)
    assert "recarga_abierta.exigir_abierta" in cuerpo, (
        f"{archivo}:{funcion} no pregunta: con la recarga cerrada, esta ruta "
        f"sigue cargando saldo.")


@pytest.mark.parametrize("archivo, funcion", PUERTAS)
def test_la_guarda_va_ANTES_de_cobrarle_nada_a_nadie(archivo, funcion):
    """Preguntar tarde deja al usuario completando un formulario de tarjeta o
    mirando un QR para algo que se va a rechazar."""
    cuerpo = _cuerpo(archivo, funcion)
    i = cuerpo.index("recarga_abierta.exigir_abierta")
    # Lo que no puede pasar ANTES: pedirle un cobro a la pasarela, o escribir
    # el pedido en la base. La primera versión de este test buscaba
    # `create_pix_payment(`, que es el nombre de la propia función — coincidía
    # con su `def` y comparaba la guarda contra la línea 1.
    for despues in ("mercadopago_service.", "asyncio.to_thread",
                    "httpx.AsyncClient", "insert_one"):
        if despues in cuerpo:
            assert i < cuerpo.index(despues), (
                f"la guarda corre después de «{despues}»: el usuario completa "
                f"todo para algo que se va a rechazar")


# ── Lo que NO se cierra ──────────────────────────────────────────────────

NO_SE_CIERRAN = (
    # Gastar el saldo que ya está. Cerrarlo sería atrapar la plata de alguien.
    ("routes/transactions.py", "create_withdrawal"),
    ("routes/transactions.py", "create_reais_send"),
    # Pagar un envío en bolívares NO es cargar saldo, aunque las dos reciban
    # una transferencia con comprobante.
    ("routes/transactions.py", "comprobante_del_envio_reais"),
    ("routes/transactions.py", "cotizar_envio_reais"),
    # Y el envío que se paga con PIX al final.
    ("routes/transactions.py", "cotizar_envio_ves"),
)


@pytest.mark.parametrize("archivo, funcion", NO_SE_CIERRAN)
def test_ESTAS_NO_llevan_la_guarda_de_la_recarga(archivo, funcion):
    """Si alguna la lleva, o se atrapó el saldo de alguien, o se mató el
    corredor a Brasil."""
    cuerpo = _cuerpo(archivo, funcion)
    assert "recarga_abierta" not in cuerpo, (
        f"{archivo}:{funcion} pregunta por la guarda de la recarga, y no es "
        f"una recarga: o gasta saldo que ya está, o paga un envío.")


def test_el_webhook_de_pagos_NO_pregunta_por_la_guarda():
    """La misma lección que la vía cripto: alguien pudo pagar minutos antes
    del apagado. Esa plata ya salió de su cuenta y hay que acreditarla.

    No abre nada, porque la ruta que CREA el cobro sí está cerrada.
    """
    cuerpo = _cuerpo("routes/gestor_pix.py", "mercadopago_webhook")
    assert "recarga_abierta" not in cuerpo, (
        "el receptor de pagos pregunta por la guarda: un PIX pagado justo "
        "antes del apagado quedaría cobrado y sin acreditar.")


# ══════════════════════════════════════════════════════════════════════════
#
# 4. QUE NINGUNA PANTALLA OFREZCA LO QUE EL SERVIDOR VA A NEGAR
#
#   Esto existe por lo que pasó con la vía cripto y está contado en
#   `test_cripto_apagada.py`: las guardas del backend estaban completas, los
#   tests en verde, y corriendo la aplicación aparecieron dos pantallas que se
#   abrían igual. Ningún test sabía del frontend.
#
#   Acá el riesgo es el mismo y más repartido: son SEIS lugares distintos que
#   llevan a `/recharge` —la tarjeta de saldo, el menú del panel, el panel sin
#   movimientos, el historial vacío, los primeros pasos y la pantalla de
#   envío—. Seis condiciones escritas a mano son cinco que alguien actualiza.
#
#   Este bloque no lleva una lista de las seis: RECORRE el frontend. Una
#   pantalla nueva con un botón de recargar sin la condición rompe el test sin
#   que nadie se acuerde de venir a anotarla acá.
#
# ══════════════════════════════════════════════════════════════════════════

_SRC = _REPO / "frontend" / "src"

# Las formas en que el frontend lleva a la pantalla de recarga.
LLEVAN_A_RECARGA = ('to="/recharge"', "navigate('/recharge')",
                    "ruta: '/recharge'", "path: '/recharge'")

# Lo que no se mira, y por qué:
#   App.jsx             es la puerta misma (`<PuertaRecarga>`), no un botón.
#   Recharge*.jsx       ya están detrás de la puerta; navegar entre ellas está
#                       bien porque a la primera no se llega con la recarga
#                       cerrada.
SE_SALTEAN = ("App.jsx", "Recharge.jsx", "RechargeVES.jsx")

# CUANTO SE ACEPTA QUE HAYA ENTRE LA CONDICION Y EL ENLACE, y por qué tan poco.
#
#   La primera versión de este guardián miraba OCHO LINEAS para arriba, en
#   bruto. Rompiendo a propósito la condición de `BalanceCard` —cambiando
#   `{recarga.abierta ? (` por `{true ? (`— los 27 tests siguieron en verde:
#   ocho líneas más arriba, la rejilla de la tarjeta menciona `recarga.abierta`
#   para decidir si va a una o a dos columnas, y el guardián se conformaba con
#   esa. O sea que el botón quedaba suelto y nadie se enteraba.
#
#   Ahora se cuentan LINEAS DE CODIGO —los comentarios no gastan ventana— y son
#   TRES. Hoy la distancia más larga es la de `Send.jsx`, que tiene tres. Si
#   alguna pantalla nueva necesita más, la que se cambia es la pantalla: una
#   condición a cinco líneas del botón que controla es una condición que el
#   próximo que lea el archivo no va a ver.
VENTANA = 3


def _es_comentario(linea):
    t = linea.strip()
    return t.startswith(("//", "/*", "*", "{/*"))


def _enlaces_a_la_recarga():
    """Todos los lugares del frontend que llevan a cargar saldo, con la
    condición que los controla —o sin ella, que es lo que se busca."""
    encontrados = []
    for archivo in sorted(_SRC.rglob("*.jsx")) + sorted(_SRC.rglob("*.js")):
        if archivo.name in SE_SALTEAN:
            continue
        lineas = archivo.read_text(encoding="utf-8").splitlines()
        for n, linea in enumerate(lineas):
            if not any(f in linea for f in LLEVAN_A_RECARGA):
                continue
            tiene, gastadas = False, 0
            for m in range(n, -1, -1):
                if not lineas[m].strip() or _es_comentario(lineas[m]):
                    continue
                if "recarga.abierta" in lineas[m]:
                    tiene = True
                    break
                gastadas += 1
                if gastadas > VENTANA:
                    break
            encontrados.append(
                (archivo.relative_to(_REPO).as_posix(), n + 1, tiene))
    return encontrados


def test_SE_ENCONTRARON_los_enlaces_a_la_recarga():
    """El guardián de abajo recorre el repositorio buscando un puñado de formas
    escritas a mano. Si alguien cambia cómo se navega —otro componente, otra
    comilla— el recorrido devuelve cero y el test de abajo pasa vacío, que es
    la peor forma de pasar: verde y sin mirar nada.

    Seis es lo que hay hoy. Si baja, o el frontend perdió un botón, o este
    archivo dejó de encontrarlos.
    """
    enlaces = _enlaces_a_la_recarga()
    assert len(enlaces) >= 6, (
        f"sólo se encontraron {len(enlaces)} enlaces a la recarga y son seis: "
        f"el recorrido dejó de reconocer cómo navega el frontend, así que el "
        f"guardián de abajo no está mirando nada.")


def test_CADA_enlace_a_la_recarga_mira_si_esta_abierta():
    """Un botón que lleva a una pantalla que rebota a la portada.

    Peor que inútil: el usuario cree que hizo algo mal.
    """
    sin_condicion = [
        f"{archivo}:{linea}"
        for archivo, linea, tiene_condicion in _enlaces_a_la_recarga()
        if not tiene_condicion
    ]
    assert not sin_condicion, (
        "estos enlaces llevan a cargar saldo sin preguntar si se puede:\n  "
        + "\n  ".join(sin_condicion)
        + "\nCon la recarga cerrada la pantalla rebota y el usuario no sabe "
          "por qué.")


def test_la_puerta_deja_pasar_MIENTRAS_no_sabe():
    """Esconder de más le saca al usuario algo que hoy funciona; mostrar de más
    le da, en el peor caso, un mensaje claro del servidor. Es el mismo criterio
    con el que falla `esta_abierta` acá al lado, y tiene que ser el mismo en
    los dos lados o uno esconde lo que el otro acepta."""
    puerta = (_SRC / "components" / "PuertaRecarga.jsx").read_text(encoding="utf-8")
    assert "cargando" in puerta, (
        "`PuertaRecarga` dejó de mirar si todavía está cargando: va a rebotar "
        "al usuario durante el parpadeo de la consulta a `/limits`.")


def test_el_frontend_lo_saca_de_la_MISMA_ruta_que_lo_hace_cumplir():
    """Si el frontend lo leyera de otro lado —una variable de entorno, un
    segundo ajuste— habría dos verdades y un día no coincidirían."""
    hook = (_SRC / "hooks" / "useRecarga.js").read_text(encoding="utf-8")
    assert "'/limits'" in hook
    assert "recarga" in hook


def test_el_que_no_puede_pagar_su_encomienda_NO_queda_esperando_una_recarga():
    """`EnvioDetalle` decía «cuando la recarga se acredite, volvé acá y pagá».

    Con la carga de saldo cerrada eso es mentira: no hay ninguna recarga en
    camino y el paquete se queda parado en Pacaraima esperando algo que no va a
    pasar. La pantalla tiene que decir qué hacer DE VERDAD.
    """
    detalle = (_SRC / "pages" / "EnvioDetalle.jsx").read_text(encoding="utf-8")
    assert "sin-recarga-escribinos" in detalle, (
        "EnvioDetalle perdió el mensaje para cuando la recarga está cerrada: "
        "le dice al usuario que espere una recarga que nadie puede hacer.")
