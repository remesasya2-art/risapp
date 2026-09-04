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
import textwrap
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
    """Un request de mentira, con las cabeceras que pone el proxy de Railway.

    LA CADENA VA AL REVES DE LO QUE PARECE

        `X-Forwarded-For` se arma por acumulación: cada proxy le agrega AL FINAL
        la IP de quien le habló. Detrás de un solo proxy la cabecera que llega
        trae un valor, y lo escribió el proxy. Si trae dos, el primero lo puso
        el cliente — y es justamente el que no hay que creerle.

        Esta clase armaba antes `f"{ip}, 10.0.0.1"` y el test esperaba que se
        guardara `ip`, o sea el valor del cliente. Con eso, cualquiera que
        mandara `X-Forwarded-For: 200.1.2.3` a mano ensuciaba el libro de
        auditoría con una IP inventada, que es el único dato del libro que se
        mira cuando hace falta encontrar a alguien.

        Ahora `ip` es lo que agrega el proxy —el último valor, el confiable— y
        `dice_venir_de` es lo que el cliente escribió adelante para hacerse
        pasar por otro.
    """
    def __init__(self, ip="200.1.2.3", pais="VE", detras_de_proxy=True,
                 dice_venir_de=None):
        self.headers = {"user-agent": "Mozilla/5.0 prueba"}
        if detras_de_proxy:
            self.headers["x-forwarded-for"] = (
                f"{dice_venir_de}, {ip}" if dice_venir_de else ip)
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
            "no tomó la IP que escribió el proxy"
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


def test_UNA_IP_ESCRITA_A_MANO_NO_ENTRA_EN_EL_LIBRO(base):
    """El libro de auditoría es el lugar donde MENOS puede entrar un dato que
    eligió quien está siendo auditado.

    El pedido llega con `X-Forwarded-For: 1.2.3.4, 200.1.2.3`. El «1.2.3.4» lo
    escribió el cliente para hacerse pasar por otro; el «200.1.2.3» se lo agregó
    el proxy y es el único de los dos que no se puede falsear desde afuera.
    """
    async def caso():
        await auditoria.registrar(
            base, "personal.alta", quien=ADMIN,
            request=_Pedido(ip="200.1.2.3", dice_venir_de="1.2.3.4"),
            objetivo_tipo="usuario", objetivo_id="x")
        linea = await base.auditoria.find_one({})
        assert linea["origen"]["ip"] == "200.1.2.3", \
            "guardó la IP que eligió quien hizo el pedido"
    corre(caso())


def test_lo_que_escribe_cloudflare_le_gana_a_lo_que_diga_el_cliente(base):
    """`CF-Connecting-IP` la pone Cloudflare PISANDO cualquier valor que venga
    del cliente. Es la más confiable de las tres, así que va primero."""
    async def caso():
        pedido = _Pedido(ip="200.1.2.3", dice_venir_de="1.2.3.4")
        pedido.headers["cf-connecting-ip"] = "190.8.8.8"
        await auditoria.registrar(base, "personal.alta", quien=ADMIN,
                                  request=pedido,
                                  objetivo_tipo="usuario", objetivo_id="x")
        linea = await base.auditoria.find_one({})
        assert linea["origen"]["ip"] == "190.8.8.8"
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


# ══════════════════════════════════════════════════════════════════════════
# 4. Que las acciones sensibles estén REALMENTE enganchadas
# ══════════════════════════════════════════════════════════════════════════
#
# Los tests de arriba prueban que el libro funciona. Estos prueban que alguien
# lo LLAMA — que es donde falla de verdad una auditoría: el módulo perfecto que
# nadie invoca. Se mira el árbol de sintaxis de cada handler, porque ejercitar
# los diez caminos por HTTP necesitaría media base de datos montada, y lo que
# hay que garantizar es más simple: que la llamada esté ahí.

import ast                                                          # noqa: E402
import pathlib                                                      # noqa: E402

# (archivo, función, acción que tiene que asentar)
ENGANCHES = [
    ("routes/admin.py", "decide_verification", "kyc.aprobado"),
    ("routes/admin.py", "decide_verification", "kyc.rechazado"),
    ("routes/admin.py", "suspend_user", "usuario.suspendido"),
    ("routes/admin.py", "suspend_user", "usuario.reactivado"),
    ("routes/admin.py", "update_rates", "config.tasa"),
    ("admin_routes.py", "approve_recharge", "dinero.recarga_aprobada"),
    ("admin_routes.py", "approve_recharge", "dinero.recarga_rechazada"),
    ("admin_routes.py", "update_user_balance", "dinero.ajuste_manual"),
]


def _nodo(archivo, funcion):
    src = pathlib.Path(_BACKEND, archivo).read_text()
    for n in ast.parse(src).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and n.name == funcion:
            return n
    return None


def _cuerpo(archivo, funcion):
    n = _nodo(archivo, funcion)
    return ast.unparse(n) if n is not None else None


def _registros_vivos(fn):
    """Las llamadas a `auditoria.registrar` que de verdad se pueden ejecutar.

    Comprobar que el TEXTO de la llamada está no alcanza: envolverla en un
    `if False:` la deja escrita y muerta, y el test seguiría en verde. Acá se
    descarta toda llamada cuyo camino pase por una condición constante falsa.
    """
    padres = {}
    for padre in ast.walk(fn):
        for hijo in ast.iter_child_nodes(padre):
            padres[hijo] = padre

    def muerta(nodo):
        while nodo in padres:
            padre = padres[nodo]
            if isinstance(padre, ast.If) and nodo in padre.body:
                prueba = padre.test
                if isinstance(prueba, ast.Constant) and not prueba.value:
                    return True
            nodo = padre
        return False

    vivas = []
    for nodo in ast.walk(fn):
        if not isinstance(nodo, ast.Call):
            continue
        f = nodo.func
        if isinstance(f, ast.Attribute) and f.attr == "registrar" \
                and isinstance(f.value, ast.Name) and f.value.id == "auditoria" \
                and not muerta(nodo):
            vivas.append(nodo)
    return vivas


@pytest.mark.parametrize("archivo, funcion, accion", ENGANCHES)
def test_la_accion_sensible_deja_rastro(archivo, funcion, accion):
    fn = _nodo(archivo, funcion)
    assert fn is not None, f"no existe {archivo}:{funcion}"

    vivas = _registros_vivos(fn)
    assert vivas, (
        f"{archivo}:{funcion} no asienta nada en el libro que se pueda "
        f"ejecutar. Una acción sensible sin rastro es la razón por la que "
        f"este libro existe.")

    texto = "\n".join(ast.unparse(v) for v in vivas)
    assert f"'{accion}'" in texto or f'"{accion}"' in texto, (
        f"{archivo}:{funcion} no asienta la acción {accion!r} por ningún "
        f"camino alcanzable.")


@pytest.mark.parametrize("archivo, funcion, accion", ENGANCHES)
def test_la_accion_enganchada_esta_declarada(archivo, funcion, accion):
    """Un enganche a una acción que no existe reventaría recién en producción."""
    assert accion in auditoria.ACCIONES, (
        f"{archivo}:{funcion} asienta {accion!r}, que no está en ACCIONES. "
        f"`registrar` levanta AccionDesconocida: esto explotaría en el "
        f"momento de aprobar un KYC, no acá.")


def test_EL_CAMBIO_DE_TASA_GUARDA_EL_VALOR_ANTERIOR():
    """"Se cambió la tasa" sin decir de cuánto a cuánto no sirve de nada.

    Y para tenerlo hay que LEER antes de escribir: después del update, el
    valor viejo ya no está.
    """
    cuerpo = _cuerpo("routes/admin.py", "update_rates")
    assert "antes_de_la_tasa" in cuerpo
    posicion_lectura = cuerpo.index("antes_de_la_tasa")
    posicion_escritura = cuerpo.index("rates.update_one")
    assert posicion_lectura < posicion_escritura, (
        "lee la tasa vieja DESPUÉS de pisarla: el 'antes' del libro sería "
        "igual al 'después'")


def test_LA_GUARDA_DE_ENGANCHES_DISTINGUE_UNA_LLAMADA_MUERTA():
    """Y ésta es la prueba de que lo distingue.

    La primera versión de esta guarda buscaba el texto `auditoria.registrar`
    en el cuerpo de la función. Dos mutaciones sobrevivieron: envolver la
    llamada en `if False:` la deja escrita y sin ejecutar, y el test seguía
    en verde. Un test que no separa una llamada viva de una desactivada no
    prueba nada.
    """
    viva = ast.parse(textwrap.dedent("""
        async def f():
            await auditoria.registrar(db, "kyc.aprobado")
    """)).body[0]
    assert len(_registros_vivos(viva)) == 1

    muerta = ast.parse(textwrap.dedent("""
        async def f():
            if False:
                await auditoria.registrar(db, "kyc.aprobado")
    """)).body[0]
    assert _registros_vivos(muerta) == []

    # Una condición de verdad NO la mata: puede no ejecutarse en una corrida,
    # pero el camino existe.
    condicional = ast.parse(textwrap.dedent("""
        async def f(aprobado):
            if aprobado:
                await auditoria.registrar(db, "kyc.aprobado")
    """)).body[0]
    assert len(_registros_vivos(condicional)) == 1

    # Y el `else` de un `if False:` sí se ejecuta.
    en_el_else = ast.parse(textwrap.dedent("""
        async def f():
            if False:
                pass
            else:
                await auditoria.registrar(db, "kyc.aprobado")
    """)).body[0]
    assert len(_registros_vivos(en_el_else)) == 1
