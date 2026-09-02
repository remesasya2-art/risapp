"""
tests/test_envios_admin_origenes.py — Las rutas del panel de orígenes.

Corren contra mongomock y no contra un doble escrito a mano, porque lo que hay
que verificar es semántica de Mongo de verdad: que cargar el mismo CEP dos veces
CORRIJA en vez de duplicar, y que la vista previa del CSV no deje NADA escrito.
Un doble solo falla donde su autor pensó que podía fallar, y las dos cosas que
importan acá son exactamente las que un doble da por buenas.

La que más importa es la de la vista previa. Un CSV de orígenes cambia la clave
con la que se busca el precio de un tramo entero: si «previsualizar» escribiera,
la persona se enteraría de que puso la UF equivocada en doscientas ciudades
DESPUÉS de habérselas guardado.
"""

import asyncio
import importlib.util
import os
import sys
import types

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="mongomock-motor no está instalado: es de test y no va en producción",
)


def _preparar():
    """Carga `routes.envios_admin` por ruta directa, sin arrastrar el proyecto."""
    if "routes" not in sys.modules:
        paquete = types.ModuleType("routes")
        paquete.__path__ = [os.path.join(_BACKEND, "routes")]
        sys.modules["routes"] = paquete

    if "routes.dependencies" not in sys.modules:
        deps = types.ModuleType("routes.dependencies")
        for nombre in ("get_current_user", "get_admin_user", "get_crm_user",
                       "get_super_admin", "get_verified_user"):
            setattr(deps, nombre, (lambda n: (lambda: None))(nombre))
        sys.modules["routes.dependencies"] = deps

    if "services" not in sys.modules:
        paquete = types.ModuleType("services")
        paquete.__path__ = [os.path.join(_BACKEND, "services")]
        sys.modules["services"] = paquete
    for nombre in ("money", "envios_tarifas", "envios_policy", "referencias",
                   "envios_catalogo", "envios_config", "envios_retiro",
                   "envios_origenes", "envios_tarifa_editor"):
        completo = f"services.{nombre}"
        if completo not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                completo, os.path.join(_BACKEND, "services", f"{nombre}.py"))
            modulo = importlib.util.module_from_spec(spec)
            sys.modules[completo] = modulo
            spec.loader.exec_module(modulo)

    if "routes.envios_admin" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "routes.envios_admin", os.path.join(_BACKEND, "routes", "envios_admin.py"))
        modulo = importlib.util.module_from_spec(spec)
        sys.modules["routes.envios_admin"] = modulo
        spec.loader.exec_module(modulo)
    return sys.modules["routes.envios_admin"]


ra = _preparar()
from fastapi import HTTPException                                    # noqa: E402


def corre(coro):
    return asyncio.run(coro)


class _Admin:
    user_id = "usr_super"
    email = "super@risappbr.com"


class _Archivo:
    """El UploadFile reducido a lo único que la ruta usa."""

    def __init__(self, texto):
        self._bytes = texto.encode("utf-8")

    async def read(self):
        return self._bytes


BASE = {}


@pytest.fixture(autouse=True)
def base_limpia():
    from conftest import usar_base
    base = mongomock_motor.AsyncMongoMockClient()["risapp_test"]
    usar_base(base)
    BASE["db"] = base
    yield base


CSV_BUENO = (
    "cep,ciudad,uf\n"
    "01310-100,São Paulo,SP\n"
    "30130-010,Belo Horizonte,MG\n"
)


# ─── El alta rápida: agregar un CEP no puede exigir armar un CSV ──────────

def test_se_agrega_una_ciudad_sola():
    salida = corre(ra.crear_origen(
        ra.OrigenNuevo(cep="01310-100", ciudad="São Paulo", uf="SP"), _Admin()))
    assert salida["ok"] and salida["ya_existia"] is False
    assert salida["valor"]["cep"] == "01310100"
    assert salida["valor"]["cep_legible"] == "01310-100"


def test_cargar_la_misma_ciudad_dos_veces_la_corrige_y_no_duplica():
    """Es lo que permite volver a cargar un CEP mal tipeado sin borrar nada."""
    corre(ra.crear_origen(ra.OrigenNuevo(cep="01310100", ciudad="Sao Paulo", uf="MG"), _Admin()))
    segunda = corre(ra.crear_origen(
        ra.OrigenNuevo(cep="01310-100", ciudad="São Paulo", uf="SP"), _Admin()))
    assert segunda["ya_existia"] is True

    listado = corre(ra.listar_origenes(_Admin()))
    assert len(listado["origenes"]) == 1
    assert listado["origenes"][0]["uf"] == "SP"


def test_una_uf_inventada_se_rechaza_al_dar_de_alta():
    """MUTACIÓN: aceptar cualquier cosa de dos letras deja pasar esto. Y 'XX' es
    una ciudad que nunca va a encontrar su matriz."""
    with pytest.raises(HTTPException) as e:
        corre(ra.crear_origen(
            ra.OrigenNuevo(cep="01310100", ciudad="São Paulo", uf="XX"), _Admin()))
    assert e.value.status_code == 400
    assert "UF" in e.value.detail


def test_desactivar_una_ciudad_la_saca_del_formulario_y_la_deja_en_el_panel():
    corre(ra.crear_origen(ra.OrigenNuevo(cep="01310100", ciudad="São Paulo", uf="SP"), _Admin()))
    corre(ra.editar_origen("01310-100", ra.OrigenEditado(activo=False), _Admin()))

    from services import envios_origenes
    del_usuario, _ = corre(envios_origenes.listar(db=BASE["db"]))
    assert del_usuario == []
    del_panel = corre(ra.listar_origenes(_Admin()))
    assert len(del_panel["origenes"]) == 1
    assert del_panel["origenes"][0]["activo"] is False


def test_editar_un_cep_que_no_existe_es_un_404():
    with pytest.raises(HTTPException) as e:
        corre(ra.editar_origen("99999999", ra.OrigenEditado(ciudad="Nada"), _Admin()))
    assert e.value.status_code == 404


# ─── El CSV: la vista previa NO escribe ───────────────────────────────────

def test_la_vista_previa_del_csv_no_escribe_nada():
    """LA MÁS IMPORTANTE DEL ARCHIVO.

    Si previsualizar escribiera, la persona se enteraría de que puso la UF
    equivocada en doscientas ciudades después de habérselas guardado.

    MUTACIÓN: sacar el `if not confirmar: return` hace que esto se ponga en rojo.
    """
    plan = corre(ra.importar_origenes(_Archivo(CSV_BUENO), False, _Admin()))
    assert plan["confirmado"] is False
    assert plan["nuevas"] == 2 and plan["actualiza"] == 0
    # Y la base sigue vacía.
    assert corre(ra.listar_origenes(_Admin()))["origenes"] == []


def test_confirmar_escribe_lo_que_la_vista_previa_anuncio():
    plan = corre(ra.importar_origenes(_Archivo(CSV_BUENO), False, _Admin()))
    hecho = corre(ra.importar_origenes(_Archivo(CSV_BUENO), True, _Admin()))
    assert hecho["confirmado"] is True
    assert (hecho["nuevas"], hecho["actualiza"]) == (plan["nuevas"], plan["actualiza"])
    assert len(corre(ra.listar_origenes(_Admin()))["origenes"]) == 2


def test_la_segunda_importacion_actualiza_en_vez_de_duplicar():
    """El usuario reportó que no sabía si el CSV actualiza o duplica. Actualiza,
    y este test lo deja escrito."""
    corre(ra.importar_origenes(_Archivo(CSV_BUENO), True, _Admin()))
    plan = corre(ra.importar_origenes(_Archivo(CSV_BUENO), False, _Admin()))
    assert plan["nuevas"] == 0 and plan["actualiza"] == 2
    corre(ra.importar_origenes(_Archivo(CSV_BUENO), True, _Admin()))
    assert len(corre(ra.listar_origenes(_Admin()))["origenes"]) == 2


def test_una_fila_mala_no_frena_a_las_demas_y_dice_su_linea():
    csv_mixto = (
        "cep,ciudad,uf\n"
        "01310-100,São Paulo,SP\n"
        "123,Rota,SP\n"
        "40010-000,Salvador,XX\n"
        "30130-010,Belo Horizonte,MG\n"
    )
    plan = corre(ra.importar_origenes(_Archivo(csv_mixto), False, _Admin()))
    assert plan["nuevas"] == 2
    assert plan["total_rechazadas"] == 2
    assert [r["fila"] for r in plan["rechazadas"]] == [3, 4]


def test_el_mismo_cep_dos_veces_en_el_archivo_se_avisa():
    """Son dos ciudades distintas para el mismo código postal, y cuál queda no lo
    puede decidir el orden de las filas."""
    csv_repetido = (
        "cep,ciudad,uf\n"
        "01310-100,São Paulo,SP\n"
        "01310100,Otra Ciudad,MG\n"
    )
    plan = corre(ra.importar_origenes(_Archivo(csv_repetido), False, _Admin()))
    assert plan["nuevas"] == 1
    assert plan["total_rechazadas"] == 1
    assert "ya aparece" in plan["rechazadas"][0]["motivo"]


def test_un_csv_que_no_es_utf8_lo_dice_en_vez_de_romperse():
    class _Latin:
        async def read(self):
            return "cep,ciudad,uf\n01310100,S\xe3o Paulo,SP\n".encode("latin-1")

    with pytest.raises(HTTPException) as e:
        corre(ra.importar_origenes(_Latin(), False, _Admin()))
    assert e.value.status_code == 400
    assert "UTF-8" in e.value.detail


# ─── La cola de propuestos ────────────────────────────────────────────────

def test_aprobar_un_propuesto_lo_pasa_al_catalogo():
    from services import envios_origenes
    corre(envios_origenes.registrar_propuesto("40010-000", "Salvador", "BA",
                                              db=BASE["db"]))
    salida = corre(ra.resolver_origen_propuesto(
        "40010000", ra.PropuestoResuelto(estado="aprobado"), _Admin()))
    assert salida["valor"]["uf"] == "BA"

    listado = corre(ra.listar_origenes(_Admin()))
    assert [o["ciudad"] for o in listado["origenes"]] == ["Salvador"]
    # Y sale de la cola de pendientes, sin borrarse.
    assert listado["propuestos"] == []


def test_al_aprobar_se_puede_corregir_lo_que_el_usuario_declaro():
    """Aprobar a ciegas lo que alguien tipeó sería exactamente el autocompletado
    que este módulo no hace."""
    from services import envios_origenes
    corre(envios_origenes.registrar_propuesto("40010000", "salvadr", "SP",
                                              db=BASE["db"]))
    salida = corre(ra.resolver_origen_propuesto(
        "40010000", ra.PropuestoResuelto(estado="aprobado", ciudad="Salvador", uf="BA"),
        _Admin()))
    assert salida["valor"] == {"cep": "40010000", "ciudad": "Salvador", "uf": "BA",
                               "activo": True}


def test_un_propuesto_sin_uf_no_entra_al_catalogo_a_medias():
    """La UF es opcional en el formulario del usuario, así que puede faltar. Eso
    no es un error suyo: es lo que esta pantalla viene a completar, y aprobarlo
    sin UF dejaría una ciudad que nunca encuentra su matriz."""
    from services import envios_origenes
    corre(envios_origenes.registrar_propuesto("40010000", "Salvador", None,
                                              db=BASE["db"]))
    with pytest.raises(HTTPException) as e:
        corre(ra.resolver_origen_propuesto(
            "40010000", ra.PropuestoResuelto(estado="aprobado"), _Admin()))
    assert e.value.status_code == 400
    assert corre(ra.listar_origenes(_Admin()))["origenes"] == []


def test_descartar_no_lo_borra_ni_lo_mete_al_catalogo():
    from services import envios_origenes
    corre(envios_origenes.registrar_propuesto("40010000", "Salvador", "BA",
                                              db=BASE["db"]))
    corre(ra.resolver_origen_propuesto(
        "40010000", ra.PropuestoResuelto(estado="descartado",
                                         motivo="Fuera del área"), _Admin()))
    listado = corre(ra.listar_origenes(_Admin()))
    assert listado["origenes"] == []
    assert listado["propuestos"] == []
    descartados, _ = corre(envios_origenes.listar_propuestos(
        db=BASE["db"], estado="descartado"))
    assert descartados[0]["motivo"] == "Fuera del área"


def test_resolver_un_cep_que_no_esta_en_la_cola_es_un_404():
    with pytest.raises(HTTPException) as e:
        corre(ra.resolver_origen_propuesto(
            "99999999", ra.PropuestoResuelto(estado="aprobado"), _Admin()))
    assert e.value.status_code == 404


# ─── La columna «Matriz» ──────────────────────────────────────────────────

def test_dice_que_origenes_quedan_sin_precio_cargado():
    """Un origen sin matriz cotiza igual, pero su bloque de referencia queda
    mudo — y hoy eso pasa sin que nadie se entere."""
    corre(ra.crear_origen(ra.OrigenNuevo(cep="01310100", ciudad="São Paulo", uf="SP"), _Admin()))
    corre(ra.crear_origen(ra.OrigenNuevo(cep="30130010", ciudad="Belo Horizonte", uf="MG"),
                          _Admin()))

    async def con_matriz():
        base = BASE["db"]
        await base.transportistas.insert_one(
            {"transportista_id": "trp_br", "codigo": "TRP-BRL", "rol": "brasil",
             "activo": True, "nombre": "Origen"})
        await base.matrices_referencia.insert_one(
            {"transportista_id": "trp_br", "clave": "SP", "hasta_kg": "30",
             "precio": "100.00"})
        return await ra.listar_origenes(_Admin())

    listado = corre(con_matriz())
    por_uf = {o["uf"]: o["tiene_matriz"] for o in listado["origenes"]}
    assert por_uf == {"SP": True, "MG": False}
    assert listado["matriz_legible"] is True


# ─── Matrices de referencia ───────────────────────────────────────────────

async def _un_transportista(rol="brasil", tid="trp_br", codigo="TRP-BRL"):
    await BASE["db"].transportistas.insert_one(
        {"transportista_id": tid, "codigo": codigo, "rol": rol, "activo": True,
         "nombre": "Empresa"})


def test_una_fila_manual_queda_marcada_como_manual_y_no_como_observada():
    """Son dos niveles de confianza distintos y la pantalla no los puede
    confundir: `observado` es un precio que vimos operando, `manual` uno que
    alguien tipeó.

    MUTACIÓN: volver `origen` a la constante "observado" pone esto en rojo.
    """
    async def caso():
        await _un_transportista()
        await ra.cargar_fila_de_matriz(
            ra.FilaDeMatriz(transportista_id="trp_br", clave="SP", hasta_kg="30",
                            precio="120.00", moneda="BRL"), _Admin())
        return await ra.listar_matrices(_Admin())

    salida = corre(caso())
    assert len(salida["filas"]) == 1
    assert salida["filas"][0]["origen"] == "manual"


def test_cargar_el_mismo_tope_escrito_distinto_no_deja_dos_filas():
    """«30» y «30.0» son el mismo tope. Sin la normalización de `aprobar` quedan
    dos filas y el precio viejo espera a ganar un desempate."""
    async def caso():
        await _un_transportista()
        for tope, precio in (("30", "120.00"), ("30.0", "150.00")):
            await ra.cargar_fila_de_matriz(
                ra.FilaDeMatriz(transportista_id="trp_br", clave="SP",
                                hasta_kg=tope, precio=precio), _Admin())
        return await ra.listar_matrices(_Admin())

    salida = corre(caso())
    assert len(salida["filas"]) == 1
    assert salida["filas"][0]["precio"] == "150.00"


def test_la_pantalla_dice_que_claves_faltan():
    """«Tenés 4 orígenes en UF sin precio» es el aviso que evita el bloque mudo."""
    async def caso():
        await _un_transportista()
        await ra.crear_origen(ra.OrigenNuevo(cep="01310100", ciudad="São Paulo",
                                             uf="SP"), _Admin())
        await ra.crear_origen(ra.OrigenNuevo(cep="30130010", ciudad="Belo Horizonte",
                                             uf="MG"), _Admin())
        await ra.cargar_fila_de_matriz(
            ra.FilaDeMatriz(transportista_id="trp_br", clave="SP", hasta_kg="30",
                            precio="120.00"), _Admin())
        return await ra.listar_matrices(_Admin())

    cobertura = corre(caso())["cobertura"]
    brasil = next(t for t in cobertura["transportistas"] if t["rol"] == "brasil")
    assert brasil["necesarias"] == ["MG", "SP"]
    assert brasil["faltan"] == ["MG"]


def test_una_fila_recien_cargada_no_se_muestra_vieja():
    async def caso():
        await _un_transportista()
        await ra.cargar_fila_de_matriz(
            ra.FilaDeMatriz(transportista_id="trp_br", clave="SP", hasta_kg="30",
                            precio="120.00"), _Admin())
        return await ra.listar_matrices(_Admin())

    assert corre(caso())["filas"][0]["desactualizada"] is False


def test_una_fila_sin_fecha_cuenta_como_vieja():
    """Por diseño: una matriz que no dice cuándo se cargó no puede presentarse
    como fresca. Está anotado en el encargo porque sorprende."""
    async def caso():
        await _un_transportista()
        await BASE["db"].matrices_referencia.insert_one(
            {"transportista_id": "trp_br", "clave": "SP", "hasta_kg": "30",
             "precio": "120.00", "origen": "manual"})
        return await ra.listar_matrices(_Admin())

    assert corre(caso())["filas"][0]["desactualizada"] is True


def test_la_vista_previa_del_csv_de_matrices_no_escribe():
    csv_matriz = ("clave,hasta_kg,precio,moneda\n"
                  "SP,30,120.00,BRL\n"
                  "MG,30,140.00,BRL\n")

    async def caso():
        await _un_transportista()
        plan = await ra.importar_matrices("trp_br", _Archivo(csv_matriz), False, _Admin())
        despues = await ra.listar_matrices(_Admin())
        return plan, despues

    plan, despues = corre(caso())
    assert plan["confirmado"] is False and plan["validas"] == 2
    assert despues["filas"] == []


def test_confirmar_el_csv_de_matrices_carga_las_filas_como_manuales():
    csv_matriz = ("clave,hasta_kg,precio,moneda\n"
                  "SP,30,120.00,BRL\n"
                  "MG,30,140.00,BRL\n")

    async def caso():
        await _un_transportista()
        hecho = await ra.importar_matrices("trp_br", _Archivo(csv_matriz), True, _Admin())
        return hecho, await ra.listar_matrices(_Admin())

    hecho, despues = corre(caso())
    assert hecho["guardadas"] == 2
    assert {f["clave"] for f in despues["filas"]} == {"SP", "MG"}
    assert {f["origen"] for f in despues["filas"]} == {"manual"}


def test_el_csv_de_matrices_de_un_transportista_que_no_existe_es_404():
    with pytest.raises(HTTPException) as e:
        corre(ra.importar_matrices("trp_nada", _Archivo("clave,hasta_kg,precio\n"),
                                   False, _Admin()))
    assert e.value.status_code == 404


# ---------------------------------------------------------------------------
# El header de multipart, que no se puede olvidar.
# ---------------------------------------------------------------------------

def test_toda_subida_de_archivo_manda_el_header_de_multipart():
    """Un `new FormData()` que se postea sin `Content-Type: multipart/form-data`
    NO llega al servidor.

    `utils/api.js` crea el cliente de axios con `Content-Type: application/json`
    fijo. Con ese default, axios ve el FormData y toma la rama

        return hasJSONContentType ? JSON.stringify(formDataToJSON(data)) : data

    o sea: lo serializa a JSON. El archivo se convierte en `{}`, el parser de
    multipart de FastAPI no ve un cuerpo, y `archivo: UploadFile = File(...)`
    contesta **«Field required»** — un error que no nombra ni al archivo ni al
    header y que manda a revisar el CSV, que no tiene nada malo.

    Paso en produccion con la subida de origenes y con la de matrices. Es
    invisible en revision —el codigo se lee perfecto— y ESLint no lo ve. Por eso
    esto se verifica sobre el fuente: es la unica forma de que no vuelva.

    (Poner el header sin boundary es correcto: axios detecta que falta el
    boundary, borra el header y deja que el navegador lo ponga bien.)
    """
    import re

    raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                        "frontend", "src"))
    if not os.path.isdir(raiz):                               # pragma: no cover
        pytest.skip("el frontend no esta en este arbol")

    sin_header = []
    for base, _, archivos in os.walk(raiz):
        for nombre in archivos:
            if not nombre.endswith((".jsx", ".js")):
                continue
            ruta = os.path.join(base, nombre)
            with open(ruta, encoding="utf-8") as f:
                fuente = f.read()
            for m in re.finditer(r"new FormData\(\)", fuente):
                # El post que usa ese FormData esta a unas pocas lineas: se mira
                # la ventana que va desde el `new FormData()` hasta el final de
                # la llamada a `api.post(...)` que le sigue.
                ventana = fuente[m.start():m.start() + 1200]
                post = re.search(r"api\.(post|put|patch)\(", ventana)
                if not post:
                    continue
                hasta = ventana[post.start():post.start() + 600]
                if "multipart/form-data" not in hasta:
                    linea = fuente[:m.start()].count("\n") + 1
                    sin_header.append(f"{os.path.relpath(ruta, raiz)}:{linea}")

    assert not sin_header, (
        "Estas subidas mandan un FormData sin `Content-Type: multipart/form-data`, "
        "asi que axios lo va a convertir a JSON y el archivo no va a llegar:\n  "
        + "\n  ".join(sin_header)
        + "\nAgregale el tercer argumento: "
        "{ headers: { 'Content-Type': 'multipart/form-data' } }"
    )
