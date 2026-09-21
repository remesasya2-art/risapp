"""
tests/test_la_pantalla_se_entera_del_pago.py — El cliente paga, y la pantalla
lo dice.

QUE PASABA

    El aviso de Mercado Pago llegaba bien y el servidor acreditaba bien —la
    hoja de Pagos de Mercado Pago lo mostraba—. Pero la pantalla del QR del
    envío NO PREGUNTABA NUNCA si el pago había entrado: mostraba el código y
    se quedaba ahí. El cliente pagaba, miraba, y no pasaba nada. Con la
    recarga sí pasaba, porque `Recharge.jsx` pregunta cada pocos segundos;
    cuando el envío pasó a pagarse al final, la pantalla del QR se escribió
    sin la pregunta. Lo reportó el dueño del proyecto el 21 de septiembre de
    2026, con la hoja en la mano.

LO QUE ESTE ARCHIVO NO DEJA QUE SE ROMPA

    1. Que el servidor conteste «pagado» por un cobro de ENVIO —no sólo de
       recarga— cuando el receptor lo acreditó. Es la ruta que las pantallas
       van a preguntar.
    2. Que las dos pantallas con QR de envío pregunten, con el mismo hook.
    3. Que al recibir «pagado» muestren la pantalla verde, y que el QR se
       vaya: un QR pagable al lado de «pago recibido» invita a pagar dos veces.
    4. Que la pregunta pare cuando el servidor da un desenlace: un pago
       confirmado no se sigue preguntando cada cinco segundos hasta que el
       cliente cierre la pestaña.
"""
import asyncio
import os
import pathlib
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))
_SRC = _BACKEND.parent / "frontend" / "src"

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base                                # noqa: E402
from models.user import User                                  # noqa: E402
from routes import gestor_pix                                 # noqa: E402
from services import pago_al_final as paf                     # noqa: E402

ANA = User(user_id="u_ana", email="ana@ejemplo.com", name="Ana", role="user",
           verification_status="verified")


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_pantalla_pago"]
    usar_base(b)
    return b


def _cobro_de_envio(base, status, **extra):
    ahora = datetime.now(timezone.utc)
    corre(base.gestor_pix_payments.insert_one({
        "payment_id": "venv_abc123", "gestor_id": ANA.user_id,
        "proposito": paf.PROPOSITO, "metodo": "pix", "transaction_id": "tx_1",
        "amount_ris": 100.0, "amount_brl": 100.0, "amount_ves": 11000.0,
        "status": status, "created_at": ahora,
        "expires_at": ahora + timedelta(minutes=7), **extra,
    }))


# ══════════════════════════════════════════════════════════════════════════
# 1. El servidor contesta «pagado» por un cobro de envío
# ══════════════════════════════════════════════════════════════════════════

def test_UN_COBRO_DE_ENVIO_PAGADO_SE_CONTESTA_COMO_PAGADO(base):
    """Es exactamente lo que escribe `pago_al_final.confirmar` cuando el
    receptor acredita: `status: paid` en el cobro. La pantalla pregunta por
    esta ruta y tiene que oír «paid»."""
    _cobro_de_envio(base, "paid", paid_at=datetime.now(timezone.utc))
    r = corre(gestor_pix.get_pix_status("venv_abc123", current_user=ANA))
    assert r["status"] == "paid"


def test_mientras_no_se_pago_contesta_pendiente(base):
    _cobro_de_envio(base, "pending")
    r = corre(gestor_pix.get_pix_status("venv_abc123", current_user=ANA))
    assert r["status"] == "pending"


def test_el_cobro_de_OTRA_persona_no_se_ve(base):
    """La pantalla pregunta con el identificador del cobro; nadie puede
    preguntar por el cobro de otro aunque lo adivine."""
    from fastapi import HTTPException
    _cobro_de_envio(base, "paid")
    otro = User(user_id="u_otro", email="otro@ejemplo.com", name="Otro", role="user")
    with pytest.raises(HTTPException) as e:
        corre(gestor_pix.get_pix_status("venv_abc123", current_user=otro))
    assert e.value.status_code == 404


# ══════════════════════════════════════════════════════════════════════════
# 2. Las dos pantallas preguntan, con el mismo hook
# ══════════════════════════════════════════════════════════════════════════

HOOK = _SRC / "hooks" / "useEsperarElPago.js"
PANTALLAS = {
    "Send.jsx": _SRC / "pages" / "Send.jsx",
    "RetomarPago.jsx": _SRC / "pages" / "RetomarPago.jsx",
}


def test_el_hook_pregunta_por_LA_MISMA_RUTA_que_la_recarga():
    """Si preguntara por otra, un cambio en el receptor podría dejar bien la
    recarga y rota la pantalla del envío sin que nadie lo note."""
    hook = HOOK.read_text(encoding="utf-8")
    recarga = (_SRC / "pages" / "Recharge.jsx").read_text(encoding="utf-8")
    # La LLAMADA, no el nombre: el encabezado del hook menciona la ruta en
    # prosa, y con «está en el archivo» una mutación que cambiara la ruta de
    # la llamada pasaba en verde por el comentario. Pasó.
    assert "api.get(`/gestor/pix/status/${paymentId}`)" in hook
    assert "api.get(`/gestor/pix/status/${pixData.payment_id}`)" in recarga


@pytest.mark.parametrize("nombre", sorted(PANTALLAS))
def test_CADA_PANTALLA_CON_QR_DE_ENVIO_PREGUNTA(nombre):
    fuente = PANTALLAS[nombre].read_text(encoding="utf-8")
    assert "useEsperarElPago(" in fuente, (
        f"{nombre} dejó de preguntar si el pago entró: el cliente paga y la "
        f"pantalla se queda igual")


@pytest.mark.parametrize("nombre", sorted(PANTALLAS))
def test_cada_pantalla_muestra_LA_MISMA_pantalla_verde(nombre):
    fuente = PANTALLAS[nombre].read_text(encoding="utf-8")
    # `\s` después del nombre: con «<PagoRecibido» a secas, un componente
    # llamado `<PagoRecibidoX` pasaba por el bueno. Pasó.
    assert re.search(r"<PagoRecibido\s", fuente), (
        f"{nombre} no muestra «pago recibido» cuando entra el pago")
    assert "import PagoRecibido from" in fuente


def test_el_hook_entiende_las_tres_formas_de_decir_pagado():
    """La ruta contesta `paid`; el receptor de tarjeta y el de la recarga han
    dicho `approved` y `completed`. `Recharge.jsx` acepta las tres, y esto
    también, para que un cambio en una no deje a la otra sorda."""
    hook = HOOK.read_text(encoding="utf-8")
    for forma in ("'paid'", "'approved'", "'completed'"):
        assert forma in hook, f"el hook no reconoce {forma} como pagado"


# ══════════════════════════════════════════════════════════════════════════
# 3. Con «pagado», el QR se va
# ══════════════════════════════════════════════════════════════════════════

def test_EN_SEND_EL_QR_SOLO_SE_MUESTRA_MIENTRAS_SE_ESPERA():
    """Un QR pagable al lado de «¡Pago recibido!» es una invitación a pagar
    dos veces. El bloque del QR tiene que estar condicionado a ESPERANDO."""
    fuente = PANTALLAS["Send.jsx"].read_text(encoding="utf-8")
    i = fuente.index('data-testid="cobro-pix"')
    linea_de_arriba = fuente[fuente.rfind("\n", 0, fuente.rfind("\n", 0, i))+1:i]
    assert "espera.estado === ESPERANDO" in linea_de_arriba, (
        "el QR de Send.jsx se sigue mostrando después de que el pago entró")


def test_EN_RETOMAR_EL_QR_SOLO_SE_MUESTRA_MIENTRAS_SE_ESPERA():
    fuente = PANTALLAS["RetomarPago.jsx"].read_text(encoding="utf-8")
    assert "espera.estado !== PAGADO && pago.se_puede_pagar ?" in fuente, (
        "el QR de RetomarPago.jsx se sigue mostrando después de que el pago entró")


def test_la_pantalla_verde_dice_el_numero_y_que_sigue():
    """Lo que va a decir si escribe a soporte, y qué pasa ahora. «Ya está en
    camino» sin decir qué sigue deja a la persona mirando la pantalla."""
    verde = (_SRC / "components" / "flujo" / "PagoRecibido.jsx").read_text(encoding="utf-8")
    assert "¡Pago recibido!" in verde
    assert "Nº {numero}" in verde
    assert "te avisamos" in verde


# ══════════════════════════════════════════════════════════════════════════
# 4. La pregunta para cuando hay desenlace
# ══════════════════════════════════════════════════════════════════════════

def test_LA_PREGUNTA_PARA_CUANDO_EL_SERVIDOR_DA_UN_DESENLACE():
    """Sin esto, un pago confirmado se sigue preguntando cada cinco segundos
    hasta que el cliente cierre la pestaña — y si la deja abierta, toda la
    tarde."""
    hook = HOOK.read_text(encoding="utf-8")
    assert "if (parado || como !== ESPERANDO) return;" in hook


def test_la_pregunta_se_espacia_con_el_tiempo():
    """El mismo ritmo que la recarga, y por el mismo motivo: la gente paga en
    el primer minuto; el que a los diez minutos no pagó dejó la pantalla
    abierta."""
    hook = HOOK.read_text(encoding="utf-8")
    assert "{ hasta: 60, cada: 5000 }" in hook
    assert "{ cada: 30000 }" in hook


def test_una_consulta_que_falla_NO_es_un_pago_que_fallo():
    """Un tropiezo de red no puede dejar la pantalla en «vencido» ni en
    «pagado»: se vuelve a preguntar en la próxima vuelta."""
    hook = HOOK.read_text(encoding="utf-8")
    i = hook.index("} catch {")
    despues = hook[i:i + 400]
    assert "return ESPERANDO;" in despues
    assert "setEstado(" not in despues


# ══════════════════════════════════════════════════════════════════════════
# 5. La cotización con PIX devuelve la referencia del cobro
# ══════════════════════════════════════════════════════════════════════════
#
#   Fue el motivo exacto por el que «Enviar» no preguntaba: la referencia se
#   devolvía sólo con tarjeta, «porque con PIX el código ya lo identifica».
#   Para pagar sí; para PREGUNTAR si se pagó, no. Sin referencia, la pantalla
#   no tenía por qué preguntar. Se descubrió recorriendo el flujo entero en
#   el navegador, no leyendo el código.

class _MercadoPagoQueContesta:
    def create_pix_payment(self, **kw):
        return {"success": True, "payment_id": 1234567, "qr_code": "000201-codigo",
                "qr_code_base64": "AAAA"}


async def _cotizar_con_pix(base, monkeypatch):
    """La cotización de verdad contra mongomock, con un Mercado Pago que
    contesta. Mismo patrón que `test_tarjeta_paga_el_envio._cotizar`."""
    from routes import transactions
    from routes.transactions import CotizarEnvioVesRequest, cotizar_envio_ves
    from services import configuracion, tarjeta_del_envio
    monkeypatch.setattr(gestor_pix, "MP_AVAILABLE", True)
    monkeypatch.setattr(gestor_pix, "mercadopago_service", _MercadoPagoQueContesta())
    await configuracion.escribir(base, paf.CLAVE, 1)
    await base.rates.insert_one({"ris_to_ves": 110.0,
                                 "updated_at": datetime.now(timezone.utc)})
    await base.beneficiaries.insert_one({
        "beneficiary_id": "ben_1", "user_id": ANA.user_id, "full_name": "María Pérez",
        "id_document": "V123", "bank": "Banco", "bank_code": "0102",
        "payment_type": "pago_movil", "phone_number": "0414"})
    await base.users.insert_one({
        "user_id": ANA.user_id, "email": ANA.email, "name": "Ana",
        "cpf": "12345678909", "verification_status": "verified"})
    # Con `monkeypatch` y NO con `transactions.db = base` a secas: asignarlo
    # a secas deja el `db` de la ruta apuntando a la base de ESTE test para
    # el resto de la suite, y los archivos que corren después —por orden
    # alfabético, `test_recarga_ves.py` entre otros— leen una base ajena y
    # fallan sin que nada diga por qué. Pasó: ocho tests en rojo que solos
    # pasaban. Es la trampa del proxy que explica `conftest.py`.
    monkeypatch.setattr(transactions, "db", base)
    return await cotizar_envio_ves(
        CotizarEnvioVesRequest(amount=100.0, beneficiary_id="ben_1",
                               client_cpf="12345678909",
                               metodo=tarjeta_del_envio.POR_PIX),
        current_user=ANA)


def test_LA_COTIZACION_CON_PIX_DEVUELVE_LA_REFERENCIA_DEL_COBRO(base, monkeypatch):
    resp = corre(_cotizar_con_pix(base, monkeypatch))
    assert resp.get("metodo") == "pix"
    assert resp.get("payment_order_id"), (
        "la cotización con PIX no devuelve la referencia del cobro: la "
        "pantalla no tiene por qué preguntar si se pagó, y el cliente paga "
        "y no pasa nada")
    # Y es LA del cobro guardado, no cualquier cosa: es lo que la pantalla
    # le va a pasar a `/gestor/pix/status/{referencia}`.
    cobro = corre(base.gestor_pix_payments.find_one(
        {"payment_id": resp["payment_order_id"]}))
    assert cobro is not None
    assert cobro["gestor_id"] == ANA.user_id


def test_send_le_pasa_al_hook_LA_REFERENCIA_DEL_COBRO():
    """Y la pantalla la usa: sin esto, la referencia viaja y nadie la lee."""
    fuente = PANTALLAS["Send.jsx"].read_text(encoding="utf-8")
    assert "cobro.payment_order_id : null" in fuente
