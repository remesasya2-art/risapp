"""
tests/test_pendientes_por_seccion.py — Por dónde hay que empezar.

QUE SOSTIENE ESTE ARCHIVO

    El panel tiene veintitrés secciones y sólo el Resumen decía algo. Para
    saber si había un KYC sin revisar o una orden sin procesar había que
    ENTRAR A CADA PESTAÑA. Quien entra no sabe por dónde empezar, y lo que no
    se mira no se hace.

LAS DOS COSAS QUE SE PRUEBAN, Y LA SEGUNDA ES LA QUE IMPORTA

    1. Que los números sean los de verdad. Los cuatro del Resumen se
       calculaban descargando listas enteras y midiendo su largo en el
       navegador: «Usuarios totales» mentía pasados los 1000 y «Recargas
       pendientes» pasadas las 100, en silencio y sin forma de auditarlo.

    2. QUE CADA NUMERO SE VEA SOLO DESDE LA SECCION QUE SE PUEDE ABRIR.
       Un contador es información: «hay 14 retiros pendientes» le dice a quien
       no puede verlos cuánto dinero está esperando salir. El criterio es el
       mismo que la puerta de cada sección, y por el mismo motivo.
"""
import asyncio
import logging
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import usar_base                     # noqa: E402
from models.user import User                       # noqa: E402
from services import pendientes                    # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


def quien(rol="admin", *permisos):
    return User(user_id="u_1", email="quien@ejemplo.com", name="Quien",
                role=rol, permissions=list(permisos))


JEFA = quien("super_admin")


@pytest.fixture
def con_trabajo(base):
    """Una tarde cualquiera: algo esperando en cada sección."""
    corre(base.transactions.insert_many([
        # Dos retiros esperando, y uno ya pagado que NO cuenta.
        {"transaction_id": "t1", "type": "withdrawal", "status": "pending"},
        {"transaction_id": "t2", "type": "withdrawal", "status": "pending"},
        {"transaction_id": "t3", "type": "withdrawal", "status": "completed"},
        # Uno pendiente pero escondido del panel: tampoco cuenta.
        {"transaction_id": "t4", "type": "withdrawal", "status": "pending",
         "hidden_from_admin": True},
        # Una recarga VES esperando.
        {"transaction_id": "t5", "type": "recharge_ves", "status": "pending"},
        # Una diferencia de pago.
        {"transaction_id": "t6", "type": "crypto_send", "status": "underpaid_review"},
    ]))
    corre(base.btc_remesas.insert_many([
        {"remesa_id": "b1", "estado": "pagado"},
        {"remesa_id": "b2", "estado": "revision_manual"},
        {"remesa_id": "b3", "estado": "enviado"},
    ]))
    corre(base.verifications.insert_many([
        {"verification_id": "v1", "status": "pending"},
        {"verification_id": "v2", "status": "approved"},
    ]))
    corre(base.soporte_casos.insert_many([
        {"caso_id": "c1", "estado": "abierto"},
        {"caso_id": "c2", "estado": "en_curso"},
        {"caso_id": "c3", "estado": "cerrado"},
    ]))
    corre(base.envios.insert_many([
        {"envio_id": "e1", "estado": "disponible_retiro"},
        {"envio_id": "e2", "estado": "entregado_transportista"},
    ]))
    corre(base.crypto_deposits.insert_many([
        {"order_id": "d1", "status": "pending"},
        {"order_id": "d2", "status": "finished"},
    ]))
    return base


# ─── Que los números sean los de verdad ───────────────────────────────────

def test_cuenta_lo_que_espera_en_cada_seccion(con_trabajo):
    n = corre(pendientes.contar_para(JEFA))

    assert n["withdrawals"] == 2, "Sólo los pendientes, y no los escondidos."
    assert n["recharges"] == 1
    assert n["diferencias"] == 1
    assert n["kyc"] == 1
    assert n["support"] == 2, "`cerrado` no espera a nadie."
    assert n["operacion"] == 1
    assert n["credits"] == 1
    assert n["btc"] == 2, "Pagada y en revisión manual: las dos esperan."


def test_ordenes_por_procesar_junta_los_tres_flujos(con_trabajo):
    """La bandeja unificada junta retiros, Bitcoin y recargas, así que el
    número también. Un contador que cuente menos que la lista que abre es
    peor que ninguno."""
    n = corre(pendientes.contar_para(JEFA))
    assert n["ordenes"] == 2 + 1 + 1, (
        "2 retiros + 1 remesa de Bitcoin pagada + 1 recarga VES.")


def test_sin_trabajo_los_numeros_son_cero(base):
    n = corre(pendientes.contar_para(JEFA))
    assert set(n) == {"ordenes", "diferencias", "withdrawals", "recharges",
                      "btc", "credits", "kyc", "support", "operacion"}
    assert all(v == 0 for v in n.values())


def test_los_usuarios_se_cuentan_en_la_base(base):
    """La mentira que se arregla acá.

    El Resumen medía el largo de la lista que trae `GET /admin/users`, que
    corta en 1000. Con 1200 usuarios seguía diciendo 1000 y nadie tenía cómo
    darse cuenta.
    """
    corre(base.users.insert_many(
        [{"user_id": f"u{i}", "role": "user"} for i in range(1200)]))

    assert corre(pendientes.total_de_usuarios()) == 1200


def test_una_cuenta_borrada_no_es_un_usuario(base):
    corre(base.users.insert_many([
        {"user_id": "u1", "role": "user"},
        {"user_id": "u2", "role": "user", "is_deleted": True},
    ]))
    assert corre(pendientes.total_de_usuarios()) == 1


# ─── Que cada número se vea sólo desde donde se puede trabajar ────────────

def test_un_agente_de_soporte_no_se_entera_de_los_retiros(con_trabajo):
    """Un contador es información. «Hay 2 retiros pendientes» le dice a quien
    no puede verlos cuánto dinero está esperando salir."""
    n = corre(pendientes.contar_para(quien("agent", "support.view")))

    assert set(n) == {"support"}, f"Recibió de más: {sorted(n)}"


def test_cada_permiso_abre_su_contador_y_ninguno_mas(con_trabajo):
    casos = [("kyc.view", "kyc"), ("support.view", "support"),
             ("envios.view", "operacion")]
    for permiso, clave in casos:
        n = corre(pendientes.contar_para(quien("admin", permiso)))
        assert set(n) == {clave}, (
            f"Con {permiso!r} se vieron {sorted(n)} en vez de sólo {clave!r}.")


def test_un_admin_sin_permisos_no_ve_ningun_contador(con_trabajo):
    assert corre(pendientes.contar_para(quien("admin"))) == {}


def test_un_cliente_no_ve_nada(con_trabajo):
    assert corre(pendientes.contar_para(quien("user"))) == {}


def test_el_super_administrador_ve_las_nueve(con_trabajo):
    """Entra siempre, sin que le marquen permisos: es quien destraba."""
    n = corre(pendientes.contar_para(quien("super_admin")))
    assert len(n) == 9


def test_las_secciones_de_plata_son_solo_del_super_administrador(con_trabajo):
    """Ni siquiera con todos los permisos del catálogo: esas secciones las
    guarda `get_super_admin` directamente, no un permiso."""
    from services import permisos
    todos = quien("admin", *permisos.CATALOGO)
    n = corre(pendientes.contar_para(todos))

    for clave in ("ordenes", "diferencias", "withdrawals", "recharges",
                  "btc", "credits"):
        assert clave not in n, (
            f"{clave!r} se mostró a un admin con todos los permisos, y esa "
            "sección la guarda el rol, no un permiso.")


# ─── Que contar no pueda tirar el panel ───────────────────────────────────

def test_si_una_consulta_falla_las_demas_siguen(con_trabajo, caplog, monkeypatch):
    """Es un adorno. Que no se puedan contar los KYC no puede dejar a nadie
    sin poder entrar a trabajar."""
    real = pendientes._contar

    async def _una_rota(coleccion, filtro):
        if coleccion == "verifications":
            raise RuntimeError("la base no contesta")
        return await real(coleccion, filtro)

    monkeypatch.setattr(pendientes, "_contar", _una_rota)
    with caplog.at_level(logging.WARNING):
        n = corre(pendientes.contar_para(JEFA))

    assert "kyc" not in n, "La sección rota tiene que quedar sin número."
    assert n["withdrawals"] == 2, "Las demás tienen que seguir contando."
    assert any("no se pudo contar" in m for m in caplog.messages)


# ─── La puerta de la ruta ─────────────────────────────────────────────────

def test_un_cliente_no_puede_pedir_los_pendientes(con_trabajo):
    """La ruta no pasa por los guardas con permiso —no tiene UN permiso: es un
    resumen de nueve secciones—, así que la puerta está adentro y se prueba."""
    from fastapi import HTTPException
    from routes import admin

    with pytest.raises(HTTPException) as e:
        corre(admin.get_pendientes(quien("user")))
    assert e.value.status_code == 403


def test_la_ruta_devuelve_los_contadores_y_los_usuarios(con_trabajo):
    from routes import admin
    corre(con_trabajo.users.insert_many(
        [{"user_id": f"u{i}", "role": "user"} for i in range(3)]))

    r = corre(admin.get_pendientes(JEFA))

    assert r["usuarios"] == 3
    assert r["pendientes"]["kyc"] == 1


def test_la_ruta_le_da_a_cada_uno_lo_suyo(con_trabajo):
    from routes import admin
    r = corre(admin.get_pendientes(quien("agent", "support.view")))
    assert set(r["pendientes"]) == {"support"}
