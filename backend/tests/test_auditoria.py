"""
tests/test_auditoria.py — El libro de auditoría.

POR QUE ESTE ARCHIVO EXISTE

    De las 96 rutas de administración que escriben en la base, sólo cuatro
    dejaban rastro. Otorgar permisos —darle a alguien el poder de mover
    plata— no quedaba registrado en ningún lado, mientras que mover la plata
    sí. Este libro cierra eso.

    Un libro de auditoría tiene una propiedad rara: si falla, falla en
    silencio y nadie se entera hasta que hace falta buscar algo y no está.
    Por eso lo que más se prueba acá no es que escriba, sino que escriba
    COMPLETO, que no rompa la operación que audita, y que una acción mal
    escrita se vea ahora y no dentro de un año.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)

from conftest import usar_base                                      # noqa: E402
from services import auditoria                                      # noqa: E402


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture
def base():
    b = mongomock_motor.AsyncMongoMockClient()["ris_test"]
    usar_base(b)
    return b


class _Pedido:
    """Un request de mentira, con las cabeceras que pone el proxy de Railway."""
    def __init__(self, ip="200.1.2.3", pais="VE", detras_de_proxy=True):
        self.headers = {"user-agent": "Mozilla/5.0 prueba"}
        if detras_de_proxy:
            self.headers["x-forwarded-for"] = f"{ip}, 10.0.0.1"
        self.headers["cf-ipcountry"] = pais
        self.client = type("C", (), {"host": "10.0.0.9"})()


ADMIN = {"user_id": "usr_super", "email": "super@risappbr.com",
         "name": "Julio", "role": "super_admin"}


# ══════════════════════════════════════════════════════════════════════════
# 1. Que la línea quede COMPLETA
# ══════════════════════════════════════════════════════════════════════════

def test_la_linea_guarda_todo_lo_que_hace_falta_para_investigar(base):
    async def caso():
        await auditoria.registrar(
            base, "personal.permisos", quien=ADMIN, request=_Pedido(),
            objetivo_tipo="usuario", objetivo_id="usr_ana",
            objetivo_desc="ana@ejemplo.com",
            antes={"permisos": ["users.view"]},
            despues={"permisos": ["users.view", "users.edit"]},
            detalle={"motivo": "pasa a atención al cliente"})

        linea = await base.auditoria.find_one({})
        # Quién
        assert linea["actor"]["email"] == "super@risappbr.com"
        assert linea["actor"]["nombre"] == "Julio"
        assert linea["actor"]["rol"] == "super_admin"
        # Qué
        assert linea["accion"] == "personal.permisos"
        assert linea["categoria"] == auditoria.Cat.PERSONAL
        assert linea["etiqueta"] == "Cambio de permisos"
        # Sobre quién
        assert linea["objetivo"] == {"tipo": "usuario", "id": "usr_ana",
                                     "descripcion": "ana@ejemplo.com"}
        # Antes y después
        assert linea["antes"] == {"permisos": ["users.view"]}
        assert linea["despues"] == {"permisos": ["users.view", "users.edit"]}
        # Desde dónde
        assert linea["origen"]["ip"] == "200.1.2.3", \
            "tomó la IP del proxy en vez de la del cliente"
        assert linea["origen"]["pais"] == "VE"
        assert "Mozilla" in linea["origen"]["navegador"]
        # Cuándo, en las dos horas
        assert isinstance(linea["cuando"], datetime)
        assert linea["cuando_caracas"].endswith("-04:00"), \
            linea["cuando_caracas"]
    corre(caso())


def test_EL_NOMBRE_Y_EL_CORREO_QUEDAN_GUARDADOS_no_solo_el_id(base):
    """Dentro de un año ese usuario puede no existir.

    Una línea que sólo guarda `actor.user_id` deja de decir quién fue en
    cuanto la cuenta se borra, que es justo cuando hace falta leerla.
    """
    async def caso():
        await auditoria.registrar(base, "personal.alta", quien=ADMIN,
                                  objetivo_tipo="usuario", objetivo_id="x")
        await base.users.delete_many({})          # el actor ya no existe
        linea = await base.auditoria.find_one({})
        assert linea["actor"]["email"] == "super@risappbr.com"
        assert linea["actor"]["nombre"] == "Julio"
    corre(caso())


def test_sin_request_el_origen_queda_en_nulo_no_inventado(base):
    async def caso():
        await auditoria.registrar(base, "personal.alta", quien=ADMIN)
        linea = await base.auditoria.find_one({})
        assert linea["origen"] == {"ip": None, "pais": None, "navegador": None}
    corre(caso())


def test_sin_proxy_toma_la_ip_del_cliente(base):
    async def caso():
        await auditoria.registrar(base, "personal.alta", quien=ADMIN,
                                  request=_Pedido(detras_de_proxy=False))
        linea = await base.auditoria.find_one({})
        assert linea["origen"]["ip"] == "10.0.0.9"
    corre(caso())


# ══════════════════════════════════════════════════════════════════════════
# 2. Que no rompa nada, y que los errores se vean temprano
# ══════════════════════════════════════════════════════════════════════════

def test_UNA_ACCION_MAL_ESCRITA_REVIENTA_AHORA(base):
    """Y a propósito.

    Una acción no declarada se guardaría igual y después NADIE la encuentra al
    filtrar por categoría. Mejor que explote en los tests que descubrirlo
    dentro de un año, buscando.
    """
    async def caso():
        with pytest.raises(auditoria.AccionDesconocida, match="no declarada"):
            await auditoria.registrar(base, "permisos.cambiados", quien=ADMIN)
        assert await base.auditoria.count_documents({}) == 0
    corre(caso())


def test_SI_EL_LIBRO_FALLA_LA_OPERACION_NO_SE_CAE(base):
    """Un libro que puede tumbar un KYC es un libro que alguien va a sacar."""
    async def caso():
        class _Rota:
            def __init__(s, real):
                s._real = real

            def __getattr__(s, n):
                return getattr(s._real, n)

            async def insert_one(s, *a, **k):
                raise RuntimeError("la base no responde")

        class _Base:
            def __init__(s, real):
                s._real = real

            def __getattr__(s, n):
                return getattr(s._real, n)

            def __getitem__(s, n):
                real = s._real[n]
                return _Rota(real) if n == auditoria.COLECCION else real

        # No levanta, y devuelve None para que el llamador sepa que se perdió.
        assert await auditoria.registrar(
            _Base(base), "personal.alta", quien=ADMIN) is None
    corre(caso())


def test_el_catalogo_no_tiene_acciones_sin_categoria_ni_etiqueta():
    for accion, valor in auditoria.ACCIONES.items():
        categoria, etiqueta = valor
        assert categoria and etiqueta, accion
        assert "." in accion, f"{accion}: se espera 'categoria.hecho'"


# ══════════════════════════════════════════════════════════════════════════
# 3. Que se pueda leer, que es donde fallaban los cuatro libros anteriores
# ══════════════════════════════════════════════════════════════════════════

async def _tres_lineas(base):
    await auditoria.registrar(base, "personal.alta", quien=ADMIN,
                              objetivo_tipo="usuario", objetivo_id="usr_ana")
    await auditoria.registrar(base, "kyc.aprobado", quien=ADMIN,
                              objetivo_tipo="usuario", objetivo_id="usr_ana")
    await auditoria.registrar(base, "dinero.ajuste_manual",
                              quien={"user_id": "usr_otro", "email": "o@x.com"},
                              objetivo_tipo="usuario", objetivo_id="usr_beto")


def test_se_puede_filtrar_por_categoria_por_actor_y_por_objetivo(base):
    async def caso():
        await _tres_lineas(base)

        r = await auditoria.buscar(base, categoria=auditoria.Cat.KYC)
        assert [x["accion"] for x in r["lineas"]] == ["kyc.aprobado"]

        r = await auditoria.buscar(base, actor_id="usr_otro")
        assert r["total"] == 1

        r = await auditoria.buscar(base, objetivo_id="usr_ana")
        assert r["total"] == 2

        r = await auditoria.buscar(base, accion="personal.alta")
        assert r["total"] == 1
    corre(caso())


def test_lo_mas_nuevo_va_primero(base):
    async def caso():
        ahora = datetime.now(timezone.utc)
        for i, cuando in enumerate([ahora - timedelta(days=2), ahora]):
            await base.auditoria.insert_one({
                "_id": f"l{i}", "accion": "personal.alta",
                "categoria": "personal", "cuando": cuando})
        r = await auditoria.buscar(base)
        assert r["lineas"][0]["cuando"] > r["lineas"][1]["cuando"]
    corre(caso())


def test_el_limite_no_se_puede_desbordar(base):
    async def caso():
        r = await auditoria.buscar(base, limite=99999)
        assert r["limite"] == 500
        r = await auditoria.buscar(base, limite=0)
        assert r["limite"] == 1
    corre(caso())


def test_EL_LIBRO_NO_OFRECE_NINGUNA_FORMA_DE_EDITAR_NI_BORRAR():
    """Se escribe y se lee. Nada más.

    Si mañana alguien agrega un `borrar()` o un `corregir()`, este test lo
    frena: en un libro de auditoría, poder editar una línea es poder tapar lo
    que pasó.
    """
    import ast
    import pathlib
    fuente = pathlib.Path(_BACKEND, "services/auditoria.py").read_text()
    arbol = ast.parse(fuente)
    publicas = {n.name for n in arbol.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not n.name.startswith("_")}
    assert publicas == {"registrar", "asegurar_indices", "buscar"}, publicas

    # Y que ninguna toque la colección para modificar.
    prohibido = ("update_one", "update_many", "delete_one", "delete_many",
                 "replace_one", "find_one_and_update", "drop")
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Attribute) and nodo.attr in prohibido:
            pytest.fail(f"services/auditoria.py usa {nodo.attr} "
                        f"(línea {nodo.lineno}): el libro no se modifica")


def test_LA_FECHA_QUE_SALE_DEL_LIBRO_NUNCA_ES_AMBIGUA(base):
    """Mongo devuelve las fechas sin zona: se guardan en UTC y vuelven naive.

    Emitirlas así deja un `2026-09-03T22:09:14` que quien lo lea puede tomar
    por hora local — cuatro horas de diferencia en una investigación. `buscar`
    les vuelve a poner el UTC que siempre tuvieron.
    """
    async def caso():
        await auditoria.registrar(base, "personal.alta", quien=ADMIN)

        crudo = await base.auditoria.find_one({})
        assert crudo["cuando"].tzinfo is None, \
            "cambió el comportamiento de Mongo: revisar este test"

        r = await auditoria.buscar(base)
        assert r["lineas"][0]["cuando"].endswith("+00:00"), \
            r["lineas"][0]["cuando"]
        # Y la de Caracas sigue estando, para leer sin hacer la cuenta.
        assert r["lineas"][0]["cuando_caracas"].endswith("-04:00")
    corre(caso())
