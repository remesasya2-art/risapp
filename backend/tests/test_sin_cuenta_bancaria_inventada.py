"""
tests/test_sin_cuenta_bancaria_inventada.py — `/ves-payment-info` no vuelve.

Era una ruta pública, sin sesión, que devolvía el documento entero de
`settings` con `{"_id": 0}`. Ningún código escribía ese documento, así que lo
que salía siempre era el relleno escrito en el código: una cuenta de un banco
real, un titular «RISAPP C.A.» y un RIF «J-00000000-0». Parecía una cuenta
de verdad para transferir, y ninguna pantalla la pedía.

Se borró. Si hace falta publicar los datos de pago, que salgan de la
configuración del panel y no de un relleno en el código.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_LA_RUTA_YA_NO_EXISTE():
    from routes.misc import router
    assert not [r for r in router.routes if getattr(r, "path", "").endswith("ves-payment-info")]


def test_NINGUN_ARCHIVO_DEL_BACKEND_TIENE_LA_CUENTA_DE_RELLENO():
    raiz = Path(__file__).resolve().parents[1]
    con_relleno = [p.relative_to(raiz).as_posix() for p in raiz.rglob("*.py")
                   if not p.relative_to(raiz).as_posix().startswith(("tests/", "venv/"))
                   and "0134-0000-00-0000000000" in p.read_text(encoding="utf-8", errors="ignore")]
    assert not con_relleno, con_relleno
