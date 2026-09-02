"""
tests/test_envios_origenes.py — El catalogo de ciudades de Brasil y su cola.

Lo que se vigila aca es una sola cosa, dicha de varias maneras: **la UF es la
clave con la que se busca un precio**, y un error de dos letras trae el precio
de otro estado sin que nadie lo note. Por eso la lista es cerrada, por eso el
CEP se normaliza antes de guardarse, y por eso nada entra al catalogo solo.

Las funciones que tocan la base se prueban contra mongomock, no contra un doble
escrito a mano: lo que hay que verificar es el `$inc` sobre un indice unico —que
el segundo pedido incremente en vez de duplicar— y eso es exactamente la
semantica de Mongo que un doble no reproduce salvo que su autor la haya pensado.
"""

import asyncio

import pytest

from services import envios_origenes as origenes

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)


def corre(coro):
    return asyncio.run(coro)


def base_limpia():
    return mongomock_motor.AsyncMongoMockClient()["risapp_test"]


# ─── El CEP: una sola forma adentro ───────────────────────────────────────

@pytest.mark.parametrize("crudo,esperado", [
    ("01310-100", "01310100"),
    ("01310100", "01310100"),
    (" 01310 100 ", "01310100"),
    ("01310.100", "01310100"),
])
def test_el_cep_se_guarda_sin_guion_venga_como_venga(crudo, esperado):
    """Las cuatro formas son el mismo CEP, y el indice unico solo lo sabe si
    llegan iguales. Sin normalizar, el mismo CSV subido con y sin guion deja dos
    ciudades donde hay una."""
    assert origenes.normalizar_cep(crudo) == esperado


@pytest.mark.parametrize("basura", ["", None, "1310100", "013101000", "abcdefgh", "01310-10a"])
def test_lo_que_no_es_un_cep_no_pasa_por_un_cep(basura):
    assert origenes.normalizar_cep(basura) is None


def test_el_cep_se_muestra_con_guion():
    assert origenes.formatear_cep("01310100") == "01310-100"


# ─── La UF: lista cerrada ─────────────────────────────────────────────────

def test_son_exactamente_las_27():
    assert len(origenes.UF_BRASIL) == 27
    assert len(set(origenes.UF_BRASIL)) == 27


@pytest.mark.parametrize("crudo,esperado", [("sp", "SP"), (" mg ", "MG"), ("RJ", "RJ")])
def test_la_uf_se_normaliza_a_mayusculas(crudo, esperado):
    assert origenes.normalizar_uf(crudo) == esperado


@pytest.mark.parametrize("invalida", ["XX", "ZZ", "S", "SPP", "", None, "  "])
def test_una_uf_que_no_existe_se_rechaza(invalida):
    """MUTACION: aceptar cualquier cosa de dos letras pone esto en rojo. Y no es
    una validacion cosmetica: 'XX' guardado como UF es una ciudad que nunca va a
    encontrar su matriz, y el bloque de referencia queda mudo sin decir por que."""
    assert origenes.normalizar_uf(invalida) is None


# ─── La validacion, que es una sola para las tres vias de carga ───────────

def test_una_fila_valida_sale_normalizada():
    fila, errores = origenes.validar("01310-100", "  São Paulo  ", "sp")
    assert not errores
    assert fila == {"cep": "01310100", "ciudad": "São Paulo", "uf": "SP"}


def test_los_errores_se_juntan_y_dicen_cual_es_cada_uno():
    """Tres campos mal tienen que devolver tres motivos, no el primero. Quien
    corrige un CSV de doscientas filas necesita la lista entera de una."""
    fila, errores = origenes.validar("123", "", "XX")
    assert fila is None
    assert len(errores) == 3


# ─── El catalogo ──────────────────────────────────────────────────────────

def test_guardar_dos_veces_el_mismo_cep_corrige_y_no_duplica():
    """El CSV se tiene que poder volver a subir corregido sin limpiar nada antes."""
    base = base_limpia()

    async def caso():
        fila, _ = origenes.validar("01310100", "Sao Paulo", "SP")
        await origenes.guardar(fila, db=base)
        # La misma ciudad, con la UF corregida y el CEP escrito con guion.
        fila2, _ = origenes.validar("01310-100", "São Paulo", "MG")
        await origenes.guardar(fila2, db=base)
        return await origenes.listar(db=base)

    lista, ok = corre(caso())
    assert ok
    assert len(lista) == 1
    assert lista[0]["uf"] == "MG"
    assert lista[0]["ciudad"] == "São Paulo"
    assert lista[0]["cep_legible"] == "01310-100"


def test_un_origen_desactivado_sale_del_formulario_pero_no_se_borra():
    """Nada se borra en el modulo. Desactivar lo saca del catalogo del usuario y
    lo deja visible para el panel, que es lo que permite volver a prenderlo."""
    base = base_limpia()

    async def caso():
        fila, _ = origenes.validar("01310100", "São Paulo", "SP")
        await origenes.guardar({**fila, "activo": False}, db=base)
        del_usuario, _ = await origenes.listar(db=base)
        del_panel, _ = await origenes.listar(db=base, solo_activos=False)
        return del_usuario, del_panel

    del_usuario, del_panel = corre(caso())
    assert del_usuario == []
    assert len(del_panel) == 1 and del_panel[0]["activo"] is False


def test_buscar_uf_devuelve_la_del_catalogo_y_no_la_que_venga_de_afuera():
    """Es la razon de ser del catalogo: la UF tipeada a mano puede estar mal."""
    base = base_limpia()

    async def caso():
        fila, _ = origenes.validar("01310100", "São Paulo", "SP")
        await origenes.guardar(fila, db=base)
        return (await origenes.buscar_uf("01310-100", db=base),
                await origenes.buscar_uf("99999999", db=base))

    encontrada, ausente = corre(caso())
    assert encontrada == "SP"
    assert ausente is None


def test_un_origen_desactivado_no_resuelve_su_uf():
    """Desactivarlo tiene que sacarlo de la resolucion tambien, no solo de la
    lista: si no, sigue trayendo precios de una ciudad que se dio de baja."""
    base = base_limpia()

    async def caso():
        fila, _ = origenes.validar("01310100", "São Paulo", "SP")
        await origenes.guardar({**fila, "activo": False}, db=base)
        return await origenes.buscar_uf("01310100", db=base)

    assert corre(caso()) is None


def test_si_la_base_no_contesta_no_se_dice_que_el_catalogo_esta_vacio():
    """Cero origenes y «no pude leer» mandan a lugares distintos: el primero a
    cargar el primer CEP, el segundo a esperar. Confundirlos hace que alguien
    reimporte un CSV encima de datos que si estaban."""
    class _Rota:
        def __getattr__(self, _):
            raise RuntimeError("la base no contesta")

    lista, ok = corre(origenes.listar(db=_Rota()))
    assert lista == [] and ok is False


# ─── La cola de propuestos ────────────────────────────────────────────────

def test_el_segundo_pedido_del_mismo_cep_incrementa_y_no_duplica():
    """Sin esto la cola se llena de la misma ciudad y el orden por `pedidos`
    —que es lo que dice cual cargar primero— no significa nada.

    MUTACION: cambiar el `$inc` por un insert deja dos filas y esto se pone en
    rojo.
    """
    base = base_limpia()

    async def caso():
        for _ in range(3):
            await origenes.registrar_propuesto("30130-010", "Belo Horizonte", "MG", db=base)
        return await origenes.listar_propuestos(db=base)

    cola, ok = corre(caso())
    assert ok
    assert len(cola) == 1
    assert cola[0]["pedidos"] == 3


def test_la_cola_viene_del_mas_pedido_al_menos_pedido():
    """Siete personas pidiendo el mismo CEP vale mas que una, y una cola sin
    ordenar obliga a leerla entera para descubrirlo."""
    base = base_limpia()

    async def caso():
        await origenes.registrar_propuesto("30130010", "Belo Horizonte", "MG", db=base)
        for _ in range(4):
            await origenes.registrar_propuesto("40010000", "Salvador", "BA", db=base)
        return await origenes.listar_propuestos(db=base)

    cola, _ = corre(caso())
    assert [c["ciudad"] for c in cola] == ["Salvador", "Belo Horizonte"]


def test_la_cola_no_guarda_un_solo_dato_personal():
    """Para decidir si una ciudad entra al catalogo no hace falta saber de quien
    era el paquete. Este test mira el documento CRUDO, no la proyeccion: lo que
    importa es que el dato no este guardado, no que no se muestre."""
    base = base_limpia()

    async def caso():
        await origenes.registrar_propuesto("30130010", "Belo Horizonte", "MG", db=base)
        return await base.origenes_propuestos.find_one({"cep": "30130010"})

    crudo = corre(caso())
    prohibidos = {"user_id", "usuario", "email", "envio_id", "cpf", "telefono",
                  "nombre", "destinatario"}
    assert not (set(crudo) & prohibidos), f"la cola guarda datos personales: {crudo}"


def test_anotar_un_propuesto_nunca_lanza_aunque_la_base_falle():
    """Corre adentro de una cotizacion. Que no se pueda anotar una sugerencia no
    puede tumbar el precio que el usuario esta esperando.

    MUTACION: sacar el try/except de `registrar_propuesto` hace que esto lance.
    """
    class _Rota:
        def __getattr__(self, _):
            raise RuntimeError("la base no contesta")

    assert corre(origenes.registrar_propuesto("01310100", "X", "SP", db=_Rota())) is False


def test_un_cep_invalido_no_ensucia_la_cola():
    base = base_limpia()

    async def caso():
        await origenes.registrar_propuesto("123", "Ciudad", "SP", db=base)
        return await origenes.listar_propuestos(db=base)

    cola, _ = corre(caso())
    assert cola == []


def test_resolver_un_propuesto_lo_marca_y_no_lo_borra():
    """El descarte es informacion: sin la fila, la misma ciudad vuelve a la cola
    en la proxima cotizacion y alguien la evalua de cero sin saber que ya se
    decidio que no."""
    base = base_limpia()

    async def caso():
        await origenes.registrar_propuesto("30130010", "Belo Horizonte", "MG", db=base)
        movio = await origenes.resolver_propuesto(
            "30130010", "descartado", "Fuera del área de retiro", db=base)
        pendientes, _ = await origenes.listar_propuestos(db=base)
        descartados, _ = await origenes.listar_propuestos(db=base, estado="descartado")
        return movio, pendientes, descartados

    movio, pendientes, descartados = corre(caso())
    assert movio is True
    assert pendientes == []
    assert len(descartados) == 1
    assert descartados[0]["motivo"] == "Fuera del área de retiro"
