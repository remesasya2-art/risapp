"""
tests/test_contratos_del_personal.py — El personal se da de alta, se cambia y
se da de baja sólo por Recursos Humanos, y lo que el panel ve del personal
sale por un contrato. Ver routes/recursos_humanos.py y models/panel_personal.py.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")


def ya(c):
    return asyncio.run(c)


# ══════════════════════════════════════════════════════════════════════════
# 1. El camino viejo de alta de administradores no vuelve
# ══════════════════════════════════════════════════════════════════════════

def _rutas_de_la_app():
    """(método, camino) de todo lo que atiende la aplicación de verdad."""
    from _lote_c_comun import sin_webpush
    sin_webpush()
    import server
    return {(m, r.path) for r in server.app.routes for m in (getattr(r, "methods", None) or ())}


def test_EL_ALTA_CAMBIO_Y_BAJA_DE_ADMINISTRADORES_ES_SOLO_DE_RRHH():
    """`POST`, `PUT` y `DELETE /admin/sub-admins` se saltaban las reglas del
    personal: promovían a un cliente con saldo, no marcaban la cuenta como
    personal —y así el candado de la plata no la frenaba— y no dejaban
    rastro en el libro. Se sacaron; ver el bloque que las reemplaza en
    `admin_routes.py`. El alta, el cambio de permisos y la baja son de RRHH."""
    rutas = _rutas_de_la_app()
    volvieron = sorted(f"{m} {c}" for m, c in rutas
                       if "sub-admins" in c and m in ("POST", "PUT", "PATCH", "DELETE"))
    assert not volvieron, f"volvió el camino viejo de alta de administradores: {volvieron}"
    # Y la lectura se queda, igual que las puertas de RRHH: si el filtro de
    # arriba dejara de encontrar rutas, este test no probaría nada.
    assert ("GET", "/api/admin/sub-admins") in rutas
    for m, c in (("POST", "/api/admin/rrhh"), ("PUT", "/api/admin/rrhh/{user_id}/permisos"),
                 ("DELETE", "/api/admin/rrhh/{user_id}")):
        assert (m, c) in rutas, f"falta {m} {c}: RRHH es el único camino y tiene que estar"
