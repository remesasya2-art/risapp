"""
tests/test_permisos_se_aplican.py — Que marcar un permiso sirva para algo.

LO QUE SE MIDIO ANTES DE ESCRIBIR ESTO

    Sobre la aplicación armada: 209 rutas de administración exigían ROL, y las
    comprobaciones de permiso existían sólo dentro de `admin_routes.py`. Las
    otras 67 —KYC, envíos, soporte, listas negras, la lista completa de
    usuarios— no miraban permisos.

    Y de las veinte comprobaciones que sí había en `admin_routes.py`, NUEVE
    estaban en rutas duplicadas que FastAPI nunca atendía.

    Las once que quedaban tampoco servían, por esto:

        if role == 'admin':
            admin_only = ['admins.create', 'admins.edit']
            return permission not in admin_only

    A un `admin` se le daba por concedido cualquier permiso menos dos, SIN
    MIRAR SU LISTA. Y `admin` es el rol con el que Recursos Humanos da de alta
    al personal.

    O sea que marcar permisos era decorativo de punta a punta.

LOS DOS TESTS QUE IMPORTAN

    `test_ninguna_ruta_de_admin_quedo_sin_permiso` recorre la aplicación de
    verdad y falla si alguna ruta que pasa por `get_admin_user` o
    `get_crm_user` no está declarada. Es lo que impide que la tabla se quede
    atrás cuando alguien agrega una ruta: no hay que acordarse de nada.

    `test_una_ruta_sin_mapear_se_niega` congela la decisión de fallar CERRADO.
    Un mapa incompleto que deja pasar es el agujero que esto tapa, y no avisa;
    uno que frena se nota el primer día.
"""
import asyncio
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from conftest import usar_base                                      # noqa: E402,F401

from fastapi import HTTPException                                   # noqa: E402
from starlette.requests import Request as PedidoReal                # noqa: E402

from models.user import User                                        # noqa: E402
from routes import dependencies as deps                             # noqa: E402
from services import permisos                                       # noqa: E402


GUARDS_CON_PERMISO = {"get_admin_user", "get_crm_user"}


@pytest.fixture(scope="module")
def rutas_de_admin():
    """(método, camino) de cada ruta que pasa por los dos guards."""
    try:
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")

    salida = []
    for ruta in app.routes:
        nombres = set()

        def caminar(ds):
            for d in ds or []:
                c = getattr(d, "call", None)
                if c is not None and getattr(c, "__name__", "") in GUARDS_CON_PERMISO:
                    nombres.add(c.__name__)
                caminar(getattr(d, "dependencies", None))

        caminar(getattr(getattr(ruta, "dependant", None), "dependencies", None))
        if not nombres:
            continue
        for metodo in sorted(getattr(ruta, "methods", []) or []):
            if metodo in ("HEAD", "OPTIONS"):
                continue
            salida.append((metodo, ruta.path,
                           getattr(getattr(ruta, "endpoint", None), "__name__", "?")))
    return salida


def pedido(metodo, camino):
    """Un Request con la ruta ya resuelta, como llega a la dependencia."""
    class _Ruta:
        path = camino
    r = PedidoReal({"type": "http", "method": metodo, "path": camino,
                    "query_string": b"", "headers": [], "client": ("1.1.1.1", 0)})
    r.scope["route"] = _Ruta()
    return r


def usuario(rol="admin", permisos_=()):
    return User(user_id="u_1", email="quien@risapp.com", name="Quien",
                role=rol, permissions=list(permisos_))


def corre(coro):
    return asyncio.run(coro)


# ══════════════════════════════════════════════════════════════════════════
# La tabla no se puede quedar atrás
# ══════════════════════════════════════════════════════════════════════════

def test_ninguna_ruta_de_admin_quedo_sin_permiso(rutas_de_admin):
    """El test que hace que esto no se degrade solo.

    Recorre la aplicación de verdad. Si alguien agrega una ruta con el guard
    de siempre y se olvida de la tabla, acá se pone rojo y el mensaje dice
    qué línea escribir.
    """
    sin_mapear = [(m, p, ep) for m, p, ep in rutas_de_admin
                  if permisos.permiso_de(m, p) is None]

    assert not sin_mapear, (
        "Rutas de administración sin permiso declarado. En producción se van "
        "a NEGAR (se falla cerrado a propósito). Agregalas a MAPA en "
        "services/permisos.py:\n\n" +
        "\n".join(f'    ("{m}", "{p}"): "",   # {ep}' for m, p, ep in sin_mapear))


def test_la_tabla_no_declara_rutas_que_ya_no_existen(rutas_de_admin):
    """Al revés: una entrada que sobra es una pista falsa.

    Quien la lea va a creer que esa función está protegida y va a buscarla
    donde no está.
    """
    vivas = {(m, p) for m, p, _ in rutas_de_admin}
    fantasmas = sorted(k for k in permisos.MAPA if k not in vivas)

    assert not fantasmas, (
        "MAPA declara rutas que la aplicación ya no tiene:\n  " +
        "\n  ".join(f"{m} {p}" for m, p in fantasmas))


def test_todo_permiso_del_catalogo_gobierna_alguna_ruta():
    """Un permiso que se puede otorgar y no hace nada es peor que no ofrecerlo.

    Quien lo marca en Recursos Humanos cree que repartió trabajo. Así se
    fueron seis del catálogo viejo: `dashboard.view`, `users.edit`,
    `admins.create`, `admins.edit`, `withdrawals.view` y
    `withdrawals.process`.
    """
    usados = set(permisos.MAPA.values())
    de_adorno = sorted(set(permisos.CATALOGO) - usados)

    assert not de_adorno, (
        "Estos permisos se ofrecen en la pantalla de RRHH y no habilitan "
        "ninguna ruta:\n  " + "\n  ".join(de_adorno))


def test_todo_permiso_usado_esta_en_el_catalogo():
    """Al revés: uno que la tabla exige y el catálogo no ofrece es una puerta
    que nadie puede abrir, ni siquiera queriendo."""
    huerfanos = sorted(set(permisos.MAPA.values()) - set(permisos.CATALOGO))

    assert not huerfanos, (
        "MAPA exige permisos que no se pueden otorgar desde RRHH:\n  " +
        "\n  ".join(huerfanos))


# ══════════════════════════════════════════════════════════════════════════
# Cómo se comporta
# ══════════════════════════════════════════════════════════════════════════

def test_sin_el_permiso_no_pasa():
    with pytest.raises(HTTPException) as e:
        corre(deps.get_admin_user(pedido("GET", "/api/admin/users"),
                                  usuario("admin", [])))
    assert e.value.status_code == 403


def test_con_el_permiso_pasa():
    u = corre(deps.get_admin_user(pedido("GET", "/api/admin/users"),
                                  usuario("admin", ["users.view"])))
    assert u.user_id == "u_1"


def test_un_permiso_no_habilita_el_de_al_lado():
    """`users.view` no puede alcanzar para ajustar un saldo."""
    with pytest.raises(HTTPException) as e:
        corre(deps.get_admin_user(pedido("PUT", "/api/admin/users/{user_id}/balance"),
                                  usuario("admin", ["users.view"])))
    assert e.value.status_code == 403


def test_ver_no_alcanza_para_aprobar_un_kyc():
    corre(deps.get_crm_user(pedido("GET", "/api/admin/kyc/list"),
                            usuario("agent", ["kyc.view"])))
    with pytest.raises(HTTPException):
        corre(deps.get_crm_user(
            pedido("POST", "/api/admin/kyc/{verification_id}/approve"),
            usuario("agent", ["kyc.view"])))


def test_el_mensaje_dice_QUE_permiso_falta():
    """Sin esto, el colaborador ve un 403 pelado y quien administra no sabe
    qué tildar en la pantalla de RRHH."""
    with pytest.raises(HTTPException) as e:
        corre(deps.get_admin_user(
            pedido("POST", "/api/admin/recharges/approve"),
            usuario("admin", [])))
    assert "Aprobar recargas" in e.value.detail


def test_el_super_administrador_no_necesita_permisos():
    """Los permisos existen para repartir trabajo; él es de quien se reparte."""
    u = corre(deps.get_admin_user(
        pedido("PUT", "/api/admin/users/{user_id}/balance"),
        usuario("super_admin", [])))
    assert u.role == "super_admin"


def test_el_rol_se_sigue_mirando_antes_que_el_permiso():
    """Un usuario común con la lista llena de permisos no entra igual.

    Si alguien le escribe permisos a mano a una cuenta de cliente, el rol
    tiene que seguir frenándola.
    """
    with pytest.raises(HTTPException) as e:
        corre(deps.get_admin_user(pedido("GET", "/api/admin/users"),
                                  usuario("user", sorted(permisos.CATALOGO))))
    assert e.value.status_code == 403
    assert "Admin" in e.value.detail


def test_un_agent_no_entra_por_la_puerta_de_admin():
    with pytest.raises(HTTPException) as e:
        corre(deps.get_admin_user(
            pedido("POST", "/api/admin/recharges/approve"),
            usuario("agent", sorted(permisos.CATALOGO))))
    assert e.value.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
# Fallar cerrado
# ══════════════════════════════════════════════════════════════════════════

def test_una_ruta_sin_mapear_se_niega(caplog):
    """LA decisión de este módulo.

    Si mañana alguien agrega `POST /api/admin/lo-que-sea` con el guard de
    siempre y se olvida de la tabla, esa ruta NO queda abierta al personal.

    Se comprueba POR QUE se negó, no sólo que se negó. Un 403 puede salir de
    dos lados —falta el permiso, o la ruta no está declarada— y confundirlos
    deja pasar una versión donde la rama de "sin declarar" nunca corre: el
    usuario de este test tiene TODOS los permisos, así que si el código no
    reconoce que la ruta está sin mapear, tendría que dejarlo entrar.
    """
    with caplog.at_level("ERROR"):
        with pytest.raises(HTTPException) as e:
            corre(deps.get_admin_user(
                pedido("POST", "/api/admin/una-ruta-que-nadie-declaro"),
                usuario("admin", sorted(permisos.CATALOGO))))

    assert e.value.status_code == 403
    assert "no tiene permiso asignado" in e.value.detail, (
        "se negó por el motivo equivocado: la ruta está sin declarar, no le "
        "falta un permiso")
    assert "SIN PERMISO DECLARADO" in caplog.text, (
        "no quedó el ERROR que nombra la ruta que hay que agregar a MAPA")
    assert "una-ruta-que-nadie-declaro" in caplog.text


def test_una_ruta_sin_mapear_no_frena_al_super_administrador():
    """Que un olvido en la tabla no deje la aplicación sin quien la opere."""
    u = corre(deps.get_admin_user(
        pedido("POST", "/api/admin/una-ruta-que-nadie-declaro"),
        usuario("super_admin", [])))
    assert u.role == "super_admin"


def test_sin_la_ruta_en_el_scope_igual_se_resuelve_por_el_camino():
    """Si `scope['route']` no estuviera, se compara el camino concreto contra
    las plantillas. Preferimos gastar una comparación antes que no saber qué
    ruta es y dejar pasar."""
    r = PedidoReal({"type": "http", "method": "POST",
                    "path": "/api/admin/kyc/ver_123/approve",
                    "query_string": b"", "headers": [], "client": ("1.1.1.1", 0)})

    with pytest.raises(HTTPException):
        corre(deps.get_crm_user(r, usuario("agent", ["kyc.view"])))
    corre(deps.get_crm_user(r, usuario("agent", ["kyc.approve"])))


# ══════════════════════════════════════════════════════════════════════════
# El que estaba roto de raíz
# ══════════════════════════════════════════════════════════════════════════

def test_un_admin_ya_no_recibe_todos_los_permisos_por_ser_admin():
    """El `has_permission` de admin_routes devolvía True para todo si el rol
    era `admin`, sin mirar la lista. Era la causa de fondo."""
    import admin_routes

    tiene_uno = admin_routes.has_permission(
        {"role": "admin", "permissions": ["kyc.view"]}, "kyc.view")
    tiene_otro = admin_routes.has_permission(
        {"role": "admin", "permissions": ["kyc.view"]}, "saldos.ajustar")

    assert tiene_uno is True
    assert tiene_otro is False, (
        "un `admin` sigue recibiendo permisos que nadie le otorgó")
