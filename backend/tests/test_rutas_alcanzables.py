"""
tests/test_rutas_alcanzables.py — Que ninguna ruta quede tapada por otra.

POR QUE ESTE ARCHIVO EXISTE

    FastAPI resuelve las rutas POR ORDEN DE REGISTRO, no por especificidad. Si
    `/transactions/{transaction_id}` se registra antes que
    `/transactions/export`, un GET a `/transactions/export` lo atiende el
    primero, con `transaction_id="export"`. El segundo endpoint existe, está
    escrito, tiene tests si alguien se los escribe — y no se ejecuta jamás.

    Pasó dos veces en este repositorio, las dos con "exportar transacciones":
    la del usuario (`routes.misc.export_transactions`, tapada por
    `routes.transactions.get_transaction`) y la del panel
    (`admin_routes.export_transactions`, tapada por `get_transaction_detail`).
    Ninguna de las dos tiraba error: devolvían un 404 de "transacción no
    encontrada", que manda a buscar el problema en la base.

    No se arregla mirando: el orden depende de la posición de la función en su
    archivo Y del orden de `include_router` en routes/__init__.py, que son dos
    lugares distintos y ninguno de los dos lo dice. Por eso es un test.
"""
import os
import re
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from conftest import usar_base                                      # noqa: E402,F401


@pytest.fixture(scope="module")
def rutas():
    """(método, path, endpoint) de la app, en orden de registro."""
    try:
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    salida = []
    for ruta in app.routes:
        for metodo in sorted(getattr(ruta, "methods", []) or []):
            salida.append((metodo, ruta.path, getattr(ruta, "endpoint", None)))
    return salida


def _patron(path):
    """`/a/{id}/b` -> regex que matchea `/a/lo-que-sea/b`."""
    escapado = re.escape(path).replace(r"\{", "{").replace(r"\}", "}")
    return re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", escapado) + "$")


def _nombre(f):
    return f"{getattr(f, '__module__', '?')}.{getattr(f, '__name__', '?')}"


def test_ninguna_ruta_literal_queda_tapada_por_una_con_parametro(rutas):
    tapadas = []
    for i, (metodo, path, f) in enumerate(rutas):
        if "{" in path:
            continue
        for metodo_previo, path_previo, f_previo in rutas[:i]:
            if metodo_previo != metodo or "{" not in path_previo:
                continue
            if _patron(path_previo).match(path):
                tapadas.append(
                    f"{metodo} {path}\n"
                    f"      la tapa   : {path_previo}\n"
                    f"      debería   : {_nombre(f)}\n"
                    f"      atiende   : {_nombre(f_previo)}")
                break
    assert not tapadas, (
        "Hay rutas literales que no se alcanzan nunca. La ruta con parámetro "
        "se registró antes y se las come.\n\n  " + "\n\n  ".join(tapadas) +
        "\n\nSe arregla registrando la literal ANTES: subiéndola dentro de su "
        "archivo, o adelantando su include_router en routes/__init__.py.")


def test_ninguna_ruta_se_registra_dos_veces(rutas):
    import collections
    veces = collections.Counter((m, p) for m, p, _ in rutas)
    quienes = collections.defaultdict(list)
    for m, p, f in rutas:
        quienes[(m, p)].append(_nombre(f))

    repetidas = sorted(k for k, n in veces.items() if n > 1)
    # Las nueve del panel de admin son deuda conocida: `admin_routes` repite
    # handlers que ya viven en `routes/`, y los suyos quedan muertos. Se
    # anotan una por una para que este test siga sirviendo, y para que cuando
    # se limpien haya que venir acá a sacarlas de la lista.
    CONOCIDAS = {
        ("GET", "/api/admin/dashboard"),
        ("GET", "/api/admin/support/chat/{user_id}"),
        ("GET", "/api/admin/support/chats"),
        ("GET", "/api/admin/users"),
        ("GET", "/api/admin/users/{user_id}"),
        ("GET", "/api/admin/verifications/pending"),
        ("POST", "/api/admin/support/close"),
        ("POST", "/api/admin/support/respond"),
        ("POST", "/api/admin/verifications/decide"),
    }
    nuevas = [k for k in repetidas if k not in CONOCIDAS]
    assert not nuevas, (
        "Rutas registradas más de una vez; sólo atiende la primera:\n  " +
        "\n  ".join(f"{m} {p} -> {quienes[(m, p)]}" for m, p in nuevas))

    ya_no = sorted(CONOCIDAS - set(repetidas))
    assert not ya_no, (
        "Estas rutas ya no están duplicadas: sacalas de CONOCIDAS para que el "
        "test vuelva a atajarlas si reaparecen.\n  " +
        "\n  ".join(f"{m} {p}" for m, p in ya_no))
