"""
tests/test_cripto_apagada.py — La vía cripto se apaga sin atrapar la plata de nadie.

POR QUE EXISTE ESTE ARCHIVO

    La empresa apagó la vía cripto —saldos en USDT y USDC, y remesas por BTC
    Lightning— porque mantener el activo de un tercero y transferirlo al
    exterior cae, en la lectura natural, bajo la autorización previa que el
    Banco Central de Brasil exige a una PSAV, y esa autorización no está. El
    detalle está en `docs/politica-pld-ft.md`, sección 1.

    El apagado es por configuración y no por borrado: el día que llegue la
    licencia se vuelve a prender desde el panel, sin desplegar.

LAS CUATRO COSAS QUE ESTE ARCHIVO NO DEJA QUE SE ROMPAN

    1. QUE EL ESTADO DE APAGADO NO ATRAPE PLATA.

       El estado 1 —el de fábrica— cierra la entrada y DEJA ABIERTA LA SALIDA.
       Si alguien «simplifica» los tres estados a un prendido/apagado, quien
       tenga saldo queda mirando un número que no puede sacar. La regla ya está
       escrita en `services/personal.py`: atrapar la plata de alguien para
       cumplir una regla interna es peor que la regla.

    2. QUE LOS WEBHOOKS NO SE CIERREN.

       Alguien pudo pagar en la blockchain minutos antes del apagado. Esa plata
       ya salió de su billetera y no vuelve. Un webhook cerrado dejaría el pago
       hecho y el saldo sin acreditar. Hay un test que recorre los tres
       receptores y exige que NINGUNO pregunte por la guarda.

    3. QUE `use_balance=False` NO PASE POR SALIDA.

       `POST /api/withdraw-crypto` se llama «withdraw», pero con
       `use_balance=False` genera un pago cripto NUEVO: es entrada disfrazada
       de salida. Quien le ponga una sola guarda mirando el nombre de la ruta
       deja abierta justo la mitad que crea custodia nueva.

    4. QUE LA PANTALLA Y EL SERVIDOR NO SE SEPAREN.

       El estado viaja por `/api/limits`, que la pantalla ya consulta. Si se
       dejara de publicar, el frontend dibujaría botones que el servidor
       rechaza.
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

from fastapi import HTTPException                            # noqa: E402

from conftest import usar_base                               # noqa: E402
from services import configuracion as cfg                    # noqa: E402
from services import cripto_abierta as ca                    # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def poner(base, valor):
    """Deja el ajuste en un estado, pasando por la misma validación que el panel."""
    normalizado, error = cfg.normalizar(ca.CLAVE, valor)
    assert error is None, f"el panel rechazaría {valor}: {error}"
    corre(cfg.escribir(base, ca.CLAVE, normalizado))


# ══════════════════════════════════════════════════════════════════════════
# 1. El estado de fábrica: entrada cerrada, salida abierta
# ══════════════════════════════════════════════════════════════════════════

def test_DE_FABRICA_NO_ENTRAN_DEPOSITOS(base):
    """Sin nada guardado tiene que valer el estado 1. Es lo que apura: que no
    nazca custodia nueva desde el minuto del despliegue."""
    assert corre(cfg.leer(base, ca.CLAVE)) == ca.SOLO_SALIDA
    assert corre(ca.acepta_depositos(base)) is False


def test_DE_FABRICA_LA_PLATA_PUEDE_SALIR(base):
    """El test más importante del archivo.

    Si esto se pone rojo, el apagado le atrapó la plata a alguien: tiene saldo
    y no tiene por dónde sacarlo."""
    assert corre(ca.acepta_envios(base)) is True


def test_DE_FABRICA_LAS_PANTALLAS_SE_SIGUEN_VIENDO(base):
    """Corolario del anterior, y se olvida: una salida abierta sin pantalla que
    la dibuje es una salida que nadie encuentra."""
    assert corre(ca.se_le_muestra(base)) is True


# ══════════════════════════════════════════════════════════════════════════
# 2. Los tres estados, uno por uno
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("estado, deposito, envio, visible", [
    (ca.ABIERTA,     True,  True,  True),
    (ca.SOLO_SALIDA, False, True,  True),
    (ca.CERRADA,     False, False, False),
])
def test_cada_estado_permite_lo_que_dice(base, estado, deposito, envio, visible):
    poner(base, estado)
    assert corre(ca.acepta_depositos(base)) is deposito
    assert corre(ca.acepta_envios(base)) is envio
    assert corre(ca.se_le_muestra(base)) is visible


def test_NO_EXISTE_EL_ESTADO_QUE_ATRAPA_PLATA(base):
    """La razón de ser de que sea UN número y no dos interruptores.

    Se recorren los tres estados y se exige que NINGUNO acepte depósitos
    teniendo la salida cerrada. Con dos interruptores esa combinación se
    configura con un clic; acá no se puede ni escribir."""
    for estado in (ca.CERRADA, ca.SOLO_SALIDA, ca.ABIERTA):
        poner(base, estado)
        entra = corre(ca.acepta_depositos(base))
        sale = corre(ca.acepta_envios(base))
        assert not (entra and not sale), (
            f"el estado {estado} deja entrar plata y no deja sacarla")


def test_el_panel_rechaza_un_estado_que_no_existe(base):
    """El catálogo tiene mínimo 0 y máximo 2. Un 3 escrito de más no puede
    quedar guardado: `_estado` lo compararía con `>= SOLO_SALIDA` y lo trataría
    como abierto sin que nadie lo haya decidido."""
    for fuera in (-1, 3, 99):
        _, error = cfg.normalizar(ca.CLAVE, fuera)
        assert error is not None, f"{fuera} se guardó y no debería"


# ══════════════════════════════════════════════════════════════════════════
# 3. Las guardas que frenan las rutas
# ══════════════════════════════════════════════════════════════════════════

def test_exigir_deposito_frena_con_503_y_no_con_403(base):
    """503 y no 403: no es que esta cuenta no tenga permiso, es que el servicio
    no está dando eso. Un 403 le haría pensar al usuario que hizo algo mal."""
    with pytest.raises(HTTPException) as e:
        corre(ca.exigir_deposito(base))
    assert e.value.status_code == 503


def test_exigir_deposito_le_dice_por_donde_si(base):
    """El mensaje no puede ser sólo «no disponible»: decir qué SI se puede es
    la diferencia entre un usuario que sigue y uno que se va.

    CUAL ES LA VIA YA NO SE ESCRIBE ACA.

        Este test exigía la palabra «PIX», porque la frase estaba escrita fija
        y decía «podés recargar tu saldo con PIX». Esa frase quedó mintiendo
        el día que la carga de saldo se pudo cerrar.

        Ahora la salida la calcula `services/la_via_que_funciona.py` mirando la
        configuración, así que lo que se comprueba es que el mensaje NOMBRE
        una salida — no cuál, que depende de lo que esté prendido.
    """
    with pytest.raises(HTTPException) as e:
        corre(ca.exigir_deposito(base))
    assert "no están disponibles" in e.value.detail
    assert "Podés" in e.value.detail, (
        "el mensaje quedó en «no disponible» sin decir qué hacer")


def test_CON_LA_CARGA_CERRADA_LA_CRIPTO_NO_MANDA_A_RECARGAR(base):
    """El otro texto que quedó mintiendo, por el mismo motivo y a la vez."""
    from services import pago_al_final, recarga_abierta
    from services import configuracion as cfg

    async def poner_ajuste(clave, valor):
        normalizado, error = cfg.normalizar(clave, valor)
        assert error is None
        await cfg.escribir(base, clave, normalizado)

    # En este orden, que es el que el panel obliga.
    corre(poner_ajuste(pago_al_final.CLAVE, 1))
    corre(poner_ajuste(recarga_abierta.CLAVE, recarga_abierta.CERRADA))

    with pytest.raises(HTTPException) as e:
        corre(ca.exigir_deposito(base))
    assert "recarg" not in e.value.detail.lower(), (
        f"con la carga de saldo cerrada, la vía cripto sigue mandando a "
        f"recargar: «{e.value.detail}»")
    assert "al final" in e.value.detail, (
        "tenía que ofrecer el pago al final, que es la vía que quedó abierta")


def test_exigir_envio_NO_frena_en_el_estado_de_fabrica(base):
    """No tiene que levantar nada: en 1 la plata sale."""
    corre(ca.exigir_envio(base))


def test_exigir_envio_frena_con_la_via_cerrada(base):
    poner(base, ca.CERRADA)
    with pytest.raises(HTTPException) as e:
        corre(ca.exigir_envio(base))
    assert e.value.status_code == 503


# ══════════════════════════════════════════════════════════════════════════
# 4. Lo que la guarda NO toca, y que si se toca se pierde plata
# ══════════════════════════════════════════════════════════════════════════

# Los tres receptores que acreditan. Ninguno puede preguntar por la guarda:
# el pago ya ocurrió en la blockchain y no se puede devolver.
RECEPTORES = (
    ("routes/credits.py", "nowpayments_webhook"),
    ("routes/transactions.py", "webhook_crypto_send"),
    ("routes/btc_lightning.py", "webhook_blink"),
)


def _cuerpo_de(archivo, funcion):
    """El texto de una función, desde su `def` hasta el próximo `def` o
    decorador de la misma columna."""
    texto = (_BACKEND / archivo).read_text(encoding="utf-8")
    lineas = texto.splitlines()
    inicio = None
    for i, linea in enumerate(lineas):
        if linea.startswith(f"async def {funcion}(") or linea.startswith(f"def {funcion}("):
            inicio = i
            break
    assert inicio is not None, (
        f"no encontré {funcion} en {archivo}. Si se renombró, actualizá "
        f"RECEPTORES: este test es lo único que impide que el receptor "
        f"empiece a preguntar por la guarda.")
    for j in range(inicio + 1, len(lineas)):
        if lineas[j].startswith("@") or lineas[j].startswith("def ") \
                or lineas[j].startswith("async def "):
            return "\n".join(lineas[inicio:j])
    return "\n".join(lineas[inicio:])


@pytest.mark.parametrize("archivo, funcion", RECEPTORES)
def test_NINGUN_WEBHOOK_PREGUNTA_POR_LA_GUARDA(archivo, funcion):
    """Si esto se pone rojo, alguien le puso la guarda a un receptor de pagos.

    Lo que pasa entonces: un usuario paga en la blockchain, el aviso llega, la
    guarda lo rechaza, y el saldo nunca se acredita. La plata salió de su
    billetera y se quedó acá. No hay forma de deshacerlo.

    No abre nada dejarlos libres: la ruta que CREA el pago sí tiene la guarda,
    así que un webhook sólo puede terminar de acreditar algo que ya existía.
    """
    cuerpo = _cuerpo_de(archivo, funcion)
    for prohibido in ("exigir_deposito", "exigir_envio", "acepta_depositos",
                      "acepta_envios"):
        assert prohibido not in cuerpo, (
            f"{archivo}:{funcion} pregunta por «{prohibido}». Un receptor de "
            f"pagos cerrado pierde la plata de quien ya pagó.")


def test_el_envio_con_saldo_y_el_envio_con_pago_nuevo_NO_llevan_la_misma_guarda():
    """`POST /api/withdraw-crypto` es dos cosas según `use_balance`.

    Con `use_balance=True` gasta saldo que ya existe: es salida, y en el estado
    de apagado tiene que funcionar. Con `use_balance=False` genera un pago
    cripto nuevo por NOWPayments: es ENTRADA, aunque la ruta se llame
    «withdraw».

    Este test exige que la entrada esté atada a `use_balance`. Sin eso, la
    mitad que crea custodia nueva queda abierta con la vía apagada, que es
    exactamente lo que el apagado venía a evitar.
    """
    cuerpo = _cuerpo_de("routes/transactions.py", "create_crypto_withdrawal")
    assert "exigir_envio" in cuerpo, "falta la guarda de salida"
    assert "if not request.use_balance:" in cuerpo, (
        "la guarda de entrada no está atada a `use_balance`: o se le exige a "
        "los dos caminos —y entonces el saldo no puede salir— o a ninguno.")
    # El orden importa: la de entrada va DESPUES y colgada del `if`.
    assert cuerpo.index("exigir_envio") < cuerpo.index("if not request.use_balance:")


# ══════════════════════════════════════════════════════════════════════════
# 5. La pantalla lee lo mismo que hace cumplir el servidor
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("estado", [ca.CERRADA, ca.SOLO_SALIDA, ca.ABIERTA])
def test_lo_que_se_publica_coincide_con_lo_que_se_hace_cumplir(base, estado):
    """El servidor y la pantalla no pueden discrepar. Se compara campo por
    campo lo que viaja contra lo que las guardas deciden."""
    poner(base, estado)
    publicado = ca.para_el_frontend(estado)
    assert publicado["deposito"] == corre(ca.acepta_depositos(base))
    assert publicado["envio"] == corre(ca.acepta_envios(base))
    assert publicado["visible"] == corre(ca.se_le_muestra(base))


def test_limits_publica_el_estado_de_la_via(base):
    """`/api/limits` es la ruta que la pantalla ya consulta. El estado viaja
    ahí y no en una ruta nueva, para que no haya un momento en que la pantalla
    sepa una cosa y el servidor otra."""
    from services.limits import limits_payload
    payload = corre(limits_payload(base))
    assert "cripto" in payload, (
        "`/api/limits` dejó de publicar el estado de la vía cripto: el "
        "frontend va a dibujar botones que el servidor rechaza.")
    assert payload["cripto"]["deposito"] is False
    assert payload["cripto"]["envio"] is True


# ══════════════════════════════════════════════════════════════════════════
# 6. Que la regla viva en un solo lugar
# ══════════════════════════════════════════════════════════════════════════

# Las rutas que crean custodia o la gastan, y el archivo donde viven.
PUERTAS = (
    ("routes/credits.py", "create_deposit", "exigir_deposito"),
    ("routes/credits_admin.py", "manual_credit", "exigir_deposito"),
    ("routes/btc_lightning.py", "generar_invoice", "exigir_deposito"),
    ("routes/transactions.py", "create_crypto_withdrawal", "exigir_envio"),
)


@pytest.mark.parametrize("archivo, funcion, guarda", PUERTAS)
def test_cada_puerta_pregunta_por_la_guarda(archivo, funcion, guarda):
    """Una puerta que se olvida de preguntar es la vía abierta por un costado.

    `manual_credit` está en la lista a propósito: que la llame un super
    administrador no vuelve legal la custodia que crea.
    """
    cuerpo = _cuerpo_de(archivo, funcion)
    assert guarda in cuerpo, (
        f"{archivo}:{funcion} no pregunta por `{guarda}`: con la vía apagada, "
        f"esta ruta sigue funcionando.")


def test_la_condicion_no_esta_copiada_en_las_rutas():
    """Nadie compara el número a mano.

    La lección es del segundo factor: la condición vivía copiada en dos puertas
    de ingreso, y la copia de una dejaba afuera al cliente. Ver
    `services/personal.pide_dos_pasos`. Acá se pregunta por una función; el
    número sólo se compara dentro de `cripto_abierta.py`.
    """
    for archivo, _, _ in PUERTAS:
        texto = (_BACKEND / archivo).read_text(encoding="utf-8")
        for copia in ('== 2', '>= 1', 'cripto_abierta.ABIERTA',
                      'cripto_abierta.SOLO_SALIDA'):
            assert f'{ca.CLAVE}") {copia}' not in texto, (
                f"{archivo} compara el estado a mano. Preguntale a la guarda.")


# ══════════════════════════════════════════════════════════════════════════
# 7. Que la pantalla no ofrezca lo que el servidor rechaza
# ══════════════════════════════════════════════════════════════════════════
#
# ESTE BLOQUE EXISTE POR UN ERROR QUE COMETI Y QUE LOS TESTS NO VIERON.
#
#   La primera versión de `PuertaCripto` miraba una sola cosa —«¿se ve la
#   cripto?»— para las tres pantallas. Los 25 tests de arriba pasaban, porque
#   ninguno sabía del frontend.
#
#   Corriendo la app apareció: en el estado de apagado, `/credits/deposit` y
#   `/btc-lightning` se abrían igual. Las dos son ENTRADA, así que el usuario
#   completaba la pantalla entera y recién al final se comía un 503.
#
#   Lo que esto vigila es la correspondencia: cada pantalla del frontend tiene
#   que estar detrás de la puerta del MISMO tipo que la guarda que su ruta del
#   backend tiene puesta. Es la misma idea que
#   `test_el_api_le_manda_a_la_pantalla_todos_los_campos_que_lee`: dos lados
#   que se tienen que poner de acuerdo y nada que avise cuando dejan de estarlo.

_APP_JSX = _REPO / "frontend" / "src" / "App.jsx"

# La pantalla, y de qué tipo tiene que ser su puerta.
PANTALLAS = (
    ("SendCrypto", "envio"),          # gasta saldo que ya existe
    ("CreditsDeposit", "deposito"),   # mete cripto
    ("BTCLightning", "deposito"),     # genera factura para que entre cripto
)


@pytest.mark.parametrize("pantalla, tipo", PANTALLAS)
def test_cada_pantalla_esta_detras_de_la_puerta_de_su_tipo(pantalla, tipo):
    texto = _APP_JSX.read_text(encoding="utf-8")
    esperado = f'<PuertaCripto tipo="{tipo}"><{pantalla} /></PuertaCripto>'
    assert esperado in texto, (
        f"{pantalla} no está detrás de `PuertaCripto tipo=\"{tipo}\"`. "
        f"Si es de entrada y queda detrás de la de salida, en el estado de "
        f"apagado la pantalla abre y el servidor la rechaza al final con 503.")


def test_la_puerta_exige_que_le_digan_el_tipo():
    """Un tipo por omisión sería el que alguien se olvida de poner en la
    pantalla siguiente, y el olvido no se ve —la pantalla abre— hasta que un
    usuario se come el 503."""
    puerta = (_REPO / "frontend" / "src" / "components" / "PuertaCripto.jsx") \
        .read_text(encoding="utf-8")
    assert "throw new Error" in puerta, (
        "`PuertaCripto` dejó de exigir el tipo: una pantalla sin tipo va a "
        "abrirse cuando no corresponde, y nadie se va a enterar.")


def test_el_menu_y_la_puerta_de_lightning_miran_LO_MISMO():
    """BTC Lightning está en el menú del panel del cliente y su pantalla está
    detrás de la puerta de entrada. Si el menú mirara otra cosa, mostraría un
    enlace que devuelve a la portada."""
    dashboard = (_REPO / "frontend" / "src" / "pages" / "Dashboard.jsx") \
        .read_text(encoding="utf-8")
    assert "if (cripto.deposito) {" in dashboard, (
        "el menú del cliente dejó de mirar `cripto.deposito` para Lightning: "
        "va a ofrecer un enlace que rebota.")


def test_la_portada_publica_no_ofrece_lo_que_no_se_puede_hacer():
    """La portada la ve quien NO tiene cuenta, así que no puede tener saldo
    cripto que sacar. Mira `deposito`: ofrecerle depositar en una vía que sólo
    acepta retiros es prometerle algo que el servidor le va a negar después de
    que se registre."""
    landing = (_REPO / "frontend" / "src" / "pages" / "Landing.jsx") \
        .read_text(encoding="utf-8")
    assert "deposito: ofreceCripto" in landing, (
        "la portada dejó de mirar `deposito`: vuelve a vender la vía cripto "
        "con la vía apagada.")
    assert "ofreceCripto || !f.cripto" in landing, (
        "las tarjetas de cripto de la portada ya no se filtran.")
