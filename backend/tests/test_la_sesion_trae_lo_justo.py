"""
tests/test_la_sesion_trae_lo_justo.py — La consulta que más corre de todas.

DE DONDE SALE

    De la revisión de capacidad para dos mil usuarios activos, punto 5.

    La comprobación de sesión hace DOS lecturas por cada pedido autenticado, y
    los pedidos los generan los relojes del panel y de la campana. Con dos mil
    personas con la aplicación abierta son unos 67 pedidos por segundo: 134
    documentos por segundo cruzando la red hacia Mongo.

    Las dos consultas venían SIN proyección: traían el documento entero de la
    sesión y el documento entero del usuario. La regla del proyecto —lista de
    lo permitido en todo lo que ve el usuario— acá faltaba.

LO QUE SE VIGILA, Y POR QUE EN ESE ORDEN

    Una proyección de MAS es lento. Una de MENOS es un campo que llega vacío y
    una pantalla que se rompe lejos de acá, sin nada que apunte a esta línea.
    Por eso el primer test es el que comprueba que no falte ninguno.
"""
import ast
import asyncio
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción")

from conftest import usar_base                              # noqa: E402
from models.user import User                                # noqa: E402
from routes import dependencies as deps                     # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
# 1. La comprobación de sesión trae lo justo
# ══════════════════════════════════════════════════════════════════════════

class _PedidoFalso:
    """Lo mínimo que `get_current_user` mira de un pedido."""

    def __init__(self, token):
        self.cookies = {"session_token": token}
        self.headers = {}


def _un_valor_para(campo, anotacion):
    """Un valor distinto del que traería por omisión, para cada tipo."""
    texto = str(anotacion)
    if "bool" in texto:
        return True
    if "float" in texto or "int" in texto:
        return 7.0
    if "datetime" in texto:
        return datetime(2026, 1, 2, tzinfo=timezone.utc)
    if "List" in texto or "list" in texto:
        return ["algo"]
    if "dict" in texto:
        return {"algo": 1}
    return f"valor-de-{campo}"


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test_peso"]
    usar_base(b)
    return b


def _sembrar(base, extra=None):
    """Un usuario con TODOS los campos del modelo puestos, y su sesión."""
    doc = {c: _un_valor_para(c, a.annotation) for c, a in User.model_fields.items()}
    doc["user_id"] = "u1"
    doc["is_deleted"] = False
    doc["is_banned"] = False
    doc.update(extra or {})
    asyncio.run(base.users.insert_one(dict(doc)))
    asyncio.run(base.user_sessions.insert_one(
        {"session_token": "t1", "user_id": "u1",
         "expires_at": datetime.now(timezone.utc) + timedelta(days=1)}))
    return doc


def test_NO_SE_PIERDE_NI_UN_CAMPO_DEL_MODELO(base):
    """EL TEST QUE IMPORTA. Una proyección de más es lento; una de menos es un
    campo que llega vacío y una pantalla que se rompe lejos de acá.

    Se siembra un usuario con los 41 campos puestos y se comprueba que los 41
    vuelvan. Si alguien le agrega un campo al modelo y la lista no lo acompaña,
    esto se pone en rojo solo.
    """
    puesto = _sembrar(base)
    usuario = asyncio.run(deps.get_current_user(_PedidoFalso("t1")))

    def igual(a, b):
        # Sin zona horaria: el driver devuelve las fechas SIN `tzinfo` (el
        # cliente no se crea con `tz_aware`) y mongomock hace lo mismo. Eso no
        # es lo que este test vigila.
        if isinstance(a, datetime) and isinstance(b, datetime):
            return a.replace(tzinfo=None) == b.replace(tzinfo=None)
        return a == b

    faltan = [c for c in User.model_fields if not igual(getattr(usuario, c), puesto[c])]
    assert not faltan, f"la consulta no trajo: {faltan}"


def test_LA_LISTA_SE_ARMA_SOLA_A_PARTIR_DEL_MODELO():
    """Escrita a mano se desincroniza el día que alguien agrega un campo, y el
    defecto aparece lejos de acá. Derivada, no hay nada que recordar."""
    del_modelo = set(User.model_fields)
    pedidos = {c for c, v in deps.DEL_USUARIO.items() if v == 1}
    assert del_modelo <= pedidos, f"no se piden: {del_modelo - pedidos}"


def test_NO_SE_PIDE_NADA_QUE_NO_HAGA_FALTA():
    """La otra mitad: que la lista no se convierta de a poco en «traelo todo»."""
    permitidos = set(User.model_fields) | {"is_banned"}
    de_mas = {c for c, v in deps.DEL_USUARIO.items() if v == 1} - permitidos
    assert not de_mas, f"se piden campos que nadie usa: {de_mas}"
    assert deps.DEL_USUARIO.get("_id") == 0, "el _id vuelve a venir"


def test_DE_LA_SESION_SOLO_SE_PIDEN_DOS_COSAS():
    assert {c for c, v in deps.DE_LA_SESION.items() if v == 1} == {"user_id",
                                                                   "expires_at"}


def test_UNA_CUENTA_SUSPENDIDA_SIGUE_SIN_PODER_ENTRAR(base):
    """`is_banned` NO está en el modelo, así que una lista derivada sólo del
    modelo lo dejaría afuera — y entonces la comprobación miraría un campo que
    nunca llega, y toda cuenta suspendida entraría."""
    from fastapi import HTTPException

    _sembrar(base, {"is_banned": True})
    with pytest.raises(HTTPException) as e:
        asyncio.run(deps.get_current_user(_PedidoFalso("t1")))
    assert e.value.status_code == 403


def test_UNA_CUENTA_BORRADA_SIGUE_SIN_PODER_ENTRAR(base):
    from fastapi import HTTPException

    _sembrar(base, {"is_deleted": True})
    with pytest.raises(HTTPException) as e:
        asyncio.run(deps.get_current_user(_PedidoFalso("t1")))
    assert e.value.status_code == 401


def test_LA_PROYECCION_LLEGA_DE_VERDAD_A_LA_CONSULTA(base, monkeypatch):
    """Definir la lista y no pasarla deja el test de arriba en verde y la
    consulta trayendo el documento entero igual."""
    vistas = []

    class _Coleccion:
        def __init__(self, real):
            self._real = real

        async def find_one(self, filtro, proyeccion=None, *a, **k):
            vistas.append(proyeccion)
            return await self._real.find_one(filtro, proyeccion, *a, **k)

    class _Base:
        """Un envoltorio de la base entera.

        No alcanza con pegarle a `base.users.find_one`: en motor, `base.users`
        arma un envoltorio NUEVO en cada acceso, así que el espía se pierde
        antes de que nadie lo llame.
        """
        def __init__(self, real):
            self._real = real

        def __getattr__(self, nombre):
            return _Coleccion(getattr(self._real, nombre))

    _sembrar(base)
    monkeypatch.setattr(deps, "db", _Base(base))
    asyncio.run(deps.get_current_user(_PedidoFalso("t1")))

    assert len(vistas) == 2, f"se esperaban dos consultas, hubo {len(vistas)}"
    assert vistas[0] == deps.DE_LA_SESION, (
        "la consulta de la sesión no lleva la lista de lo permitido")
    assert vistas[1] == deps.DEL_USUARIO, (
        "la consulta del usuario no lleva la lista de lo permitido")
