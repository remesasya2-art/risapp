"""
tests/test_jurisdicciones_bloqueadas.py — Dónde NO se puede recargar en cripto.

QUE PROTEGE

    El proveedor de pagos en cripto no presta servicio a residentes ni
    ciudadanos de Estados Unidos, la Unión Europea y el Reino Unido. Si
    aceptáramos una recarga desde ahí, el incumplimiento es NUESTRO.

    El guardia es `assert_payment_allowed(request, declared_not_restricted)` y
    tiene DOS capas, por una razón que conviene no perder:

      * La IP dice desde dónde se conecta el usuario, NO su nacionalidad. Un
        ciudadano estadounidense conectado desde Brasil pasa el filtro de IP.
      * Por eso además se le exige una declaración explícita. Y por eso una IP
        desconocida NO se bloquea: bloquear por no saber dejaría afuera a
        usuarios legítimos, y la declaración más el KYC son el respaldo.

    Lo que este archivo agrega, y que no existía: que el guardia CORRA, y que
    corra ANTES de crear el cobro. Que la función exista y nadie la llame es
    la forma más común de que un control de cumplimiento no exista.

    El orden se comprueba por comportamiento, no leyendo el código fuente: se
    manda un pedido desde una jurisdicción bloqueada Y con una moneda inválida.
    Si el guardia va primero, la respuesta es 403 por jurisdicción; si alguien
    lo moviera más abajo, sería 400 por la moneda. Una prueba que mirara el
    orden de las líneas se rompería con cualquier refactor inocente.
"""
import asyncio
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from fastapi import HTTPException                                   # noqa: E402
from starlette.requests import Request as PedidoReal                # noqa: E402

from services.geo_restrictions import (                             # noqa: E402
    RESTRICTED_COUNTRIES, assert_payment_allowed, get_ip_country, is_restricted_ip,
)


def pedido(pais=None):
    cabeceras = [(b"user-agent", b"test")]
    if pais is not None:
        cabeceras.append((b"cf-ipcountry", pais.encode()))
    return PedidoReal({
        "type": "http", "method": "POST", "path": "/credits/deposit",
        "query_string": b"", "headers": cabeceras, "client": ("1.2.3.4", 0),
    })


def corre(coro):
    return asyncio.run(coro)


# ─── La lista ─────────────────────────────────────────────────────────────

def test_la_lista_son_los_29_paises_del_tos():
    """EE.UU. + Reino Unido + los 27 de la Unión Europea."""
    assert len(RESTRICTED_COUNTRIES) == 29
    for pais in ("US", "GB", "DE", "FR", "ES", "IT", "NL", "PT", "IE"):
        assert pais in RESTRICTED_COUNTRIES, f"falta {pais}"
    for pais in ("BR", "VE", "AR", "CO", "MX"):
        assert pais not in RESTRICTED_COUNTRIES, f"{pais} no debería estar bloqueado"


# ─── El guardia ───────────────────────────────────────────────────────────

def test_desde_una_jurisdiccion_bloqueada_no_se_puede_ni_declarando():
    """La declaración no habilita una IP bloqueada: son dos condiciones, no
    una alternativa."""
    for pais in ("US", "GB", "DE"):
        with pytest.raises(HTTPException) as e:
            assert_payment_allowed(pedido(pais), declared_not_restricted=True)
        assert e.value.status_code == 403
        assert pais in e.value.detail


def test_desde_una_jurisdiccion_libre_hace_falta_la_declaracion():
    with pytest.raises(HTTPException) as e:
        assert_payment_allowed(pedido("BR"), declared_not_restricted=False)
    assert e.value.status_code == 400


def test_la_declaracion_no_viene_marcada_por_defecto():
    """Sin el argumento, el guardia frena. Un valor por omisión permisivo
    convertiría un olvido del llamador en una recarga aceptada."""
    with pytest.raises(HTTPException):
        assert_payment_allowed(pedido("BR"))


def test_desde_una_jurisdiccion_libre_y_declarando_pasa():
    assert_payment_allowed(pedido("BR"), declared_not_restricted=True)


def test_una_ip_desconocida_no_se_bloquea_pero_sigue_necesitando_la_declaracion():
    """Cloudflare manda 'XX' o 'T1' cuando no sabe. No bloqueamos por no
    saber: la declaración y el KYC son el respaldo."""
    for desconocido in (None, "XX", "T1"):
        assert get_ip_country(pedido(desconocido)) is None
        assert is_restricted_ip(pedido(desconocido)) is False
        assert_payment_allowed(pedido(desconocido), declared_not_restricted=True)
        with pytest.raises(HTTPException) as e:
            assert_payment_allowed(pedido(desconocido), declared_not_restricted=False)
        assert e.value.status_code == 400


def test_el_pais_se_lee_sin_importar_mayusculas_ni_espacios():
    assert get_ip_country(pedido(" us ")) == "US"
    assert is_restricted_ip(pedido(" us ")) is True


# ─── Que el guardia esté enchufado, y primero ─────────────────────────────

def test_la_recarga_en_cripto_llama_al_guardia_antes_que_a_nada():
    """El control de jurisdicción corre ANTES de validar la moneda.

    Si alguien lo moviera más abajo, este pedido —jurisdicción bloqueada Y
    moneda inexistente— devolvería 400 en vez de 403, y la prueba avisa.
    """
    from routes.credits import DepositRequest, create_deposit

    datos = DepositRequest(currency="moneda-que-no-existe", amount=1,
                           declared_not_restricted=True)
    with pytest.raises(HTTPException) as e:
        corre(create_deposit(datos, pedido("US"), current_user=None))

    assert e.value.status_code == 403, (
        "la recarga en cripto validó la moneda antes que la jurisdicción")


def test_sin_la_declaracion_tampoco_se_llega_a_crear_el_cobro():
    from routes.credits import DepositRequest, create_deposit

    datos = DepositRequest(currency="usdt", amount=1000,
                           declared_not_restricted=False)
    with pytest.raises(HTTPException) as e:
        corre(create_deposit(datos, pedido("BR"), current_user=None))
    assert e.value.status_code == 400
