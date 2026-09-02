"""
La portada del panel: que le falta al modulo para poder operar.

POR QUE HAY UNA PANTALLA PARA ESTO
    `/envios/limites` contesta `disponible: false` y no dice por que — el
    diagnostico de configuracion es interno. Sin esta pantalla, la unica forma de
    saber que falta cargar es leer el codigo, y la primera senal es una
    cotizacion que falla en la cara de un usuario.

LO QUE MAS IMPORTA QUE SE PRUEBE
    Que "no esta cargado" y "no lo pude leer" NO se confundan. `leer` devuelve
    None por las dos razones, y una pantalla que las funde le dice "carga el
    punto de origen" a alguien durante un corte de base. Esa persona lo carga de
    memoria y pisa la plantilla y la Caixa Postal reales, que si estaban.
"""
import asyncio
import copy
import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from conftest import usar_base                                        # noqa: E402


class _Cursor:
    def __init__(self, filas):
        self.filas = filas

    def sort(self, campo, direccion=1):
        self.filas.sort(key=lambda d: str(d.get(campo, "")), reverse=direccion < 0)
        return self

    async def to_list(self, n):
        return list(self.filas)[:n] if n else list(self.filas)


class _Coleccion:
    def __init__(self, filas=None):
        self.filas = filas if filas is not None else []
        self.rota = False

    def _match(self, d, filtro):
        for k, v in (filtro or {}).items():
            actual = d.get(k)
            if isinstance(v, dict) and "$in" in v:
                if actual not in v["$in"]:
                    return False
            elif actual != v:
                return False
        return True

    def _proyectar(self, d, proyeccion):
        if not proyeccion:
            return copy.deepcopy(d)
        incluir = [k for k, v in proyeccion.items() if v and k != "_id"]
        if incluir:
            return copy.deepcopy({k: v for k, v in d.items() if k in incluir})
        excluir = [k for k, v in proyeccion.items() if not v]
        return copy.deepcopy({k: v for k, v in d.items() if k not in excluir})

    def find(self, filtro=None, proyeccion=None):
        if self.rota:
            raise RuntimeError("motor caído")
        return _Cursor([self._proyectar(d, proyeccion)
                        for d in self.filas if self._match(d, filtro)])

    async def find_one(self, filtro, proyeccion=None):
        if self.rota:
            raise RuntimeError("motor caído")
        for d in self.filas:
            if self._match(d, filtro):
                return self._proyectar(d, proyeccion)
        return None

    async def count_documents(self, filtro):
        if self.rota:
            raise RuntimeError("motor caído")
        return sum(1 for d in self.filas if self._match(d, filtro))


class _Db:
    def __init__(self, **colecciones):
        self._c = {k: _Coleccion(v) for k, v in colecciones.items()}

    def _nueva(self, nombre):
        return self._c.setdefault(nombre, _Coleccion([]))

    def __getattr__(self, nombre):
        return self._nueva(nombre)

    def __getitem__(self, nombre):
        return self._nueva(nombre)


def _cargar(nombre):
    if "services" not in sys.modules:
        paquete = types.ModuleType("services")
        paquete.__path__ = [os.path.join(_BACKEND, "services")]
        sys.modules["services"] = paquete
    completo = f"services.{nombre}"
    if completo in sys.modules:
        return sys.modules[completo]
    ruta = os.path.join(_BACKEND, "services", f"{nombre}.py")
    spec = importlib.util.spec_from_file_location(completo, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[completo] = modulo
    spec.loader.exec_module(modulo)
    return modulo


_cargar("money")
_cargar("envios_tarifas")
_cargar("envios_policy")
_cargar("envios_catalogo")
_cargar("envios_retiro")
_cargar("envios_config")
puesta = _cargar("envios_puesta_en_marcha")


def corre(coro):
    return asyncio.run(coro)


AHORA = datetime.now(timezone.utc)

PUNTO_ORIGEN = {
    "setting_id": "envios_punto_origen",
    "nombre": "Agencia Centro", "cep": "69350000", "ciudad": "Pacaraima", "uf": "RR",
    "modalidad": "caixa_postal", "caixa_postal": "123", "direccion": None,
    "razon_social": "RIS App LTDA",
    "plantilla_direccion": "{razon_social}\n{retirador_nombre}\n{agencia_linea}",
    "retirador_activo_id": "col_1",
}
CONTENIDO = {"setting_id": "envios_contenido", "prohibidos": ["armas", "líquidos"],
             "terminos_version": "2026-08-a", "texto_estimado": "x" * 40,
             "descripcion_min_caracteres": 10}
OPERACION = {"setting_id": "envios_operacion", "tolerancia_ajuste_ris": "2.00",
             "dias_guarda": 30, "ttl_cotizacion_horas": 48}

TRP_BR = {"transportista_id": "t_br", "codigo": "TRP-BR1", "rol": "brasil",
          "activo": True}
TRP_VE = {"transportista_id": "t_ve", "codigo": "TRP-VE1", "rol": "venezuela",
          "activo": True}

AGENCIA = {"transportista_id": "t_ve", "codigo": "001", "nombre": "Santa Elena",
           "estado": "Bolívar", "ciudad": "Santa Elena", "activa": True,
           "es_punto_entrega": True}

COLABORADOR = {"colaborador_id": "col_1", "nombre": "Ana Pérez", "activo": True,
               "autorizado_desde": None, "autorizado_hasta": None}

TARIFA = {
    "version_id": "tar_2026_08_a", "moneda": "RIS",
    "vigente_desde": AHORA - timedelta(days=1), "vigente_hasta": None,
    "regla_peso": {"divisor": 5000, "escalon_kg": "0.5", "minimo_kg": "1.0"},
    "escalones_peso": [{"desde_kg": "0.00", "hasta_kg": "1.00", "precio": "45.00"}],
}


def _base(**cambios):
    filas = {
        "app_settings": [copy.deepcopy(PUNTO_ORIGEN), copy.deepcopy(CONTENIDO),
                         copy.deepcopy(OPERACION)],
        "transportistas": [copy.deepcopy(TRP_BR), copy.deepcopy(TRP_VE)],
        "agencias": [copy.deepcopy(AGENCIA)],
        "colaboradores_retiro": [copy.deepcopy(COLABORADOR)],
        "tarifas_envio": [copy.deepcopy(TARIFA)],
    }
    filas.update(cambios)
    return usar_base(_Db(**filas))


@pytest.fixture(autouse=True)
def _sin_cache():
    """El catálogo cachea la tarifa vigente. Sin limpiarlo, el primer test le
    impone su respuesta a todos los demás."""
    from services import envios_catalogo
    envios_catalogo.invalidar_cache()
    yield
    envios_catalogo.invalidar_cache()


# --- todo vacío -------------------------------------------------------------

def test_un_modulo_recien_instalado_dice_los_siete_pasos():
    _base(app_settings=[], transportistas=[], agencias=[],
          colaboradores_retiro=[], tarifas_envio=[])
    salida = corre(puesta.estado())
    assert salida["puede_operar"] is False
    assert [p["clave"] for p in salida["pasos"]] == list(puesta.ORDEN)
    assert all(p["estado"] == puesta.FALTA for p in salida["pasos"])
    assert salida["siguiente"] == "punto_origen"
    assert salida["faltan"] == 7


def test_con_todo_cargado_puede_operar():
    _base()
    salida = corre(puesta.estado())
    assert salida["puede_operar"] is True, [p for p in salida["pasos"]
                                            if p["estado"] != puesta.LISTO]
    assert salida["siguiente"] is None
    assert salida["hay_lecturas_fallidas"] is False


# --- la distinción que importa ---------------------------------------------

def test_una_base_caida_no_dice_que_falta_cargar():
    """El defecto que esta pantalla NO puede tener.

    `leer` devuelve None si el bloque no está cargado Y si Mongo no contestó. Si
    la pantalla las funde, durante un corte le dice "cargá el punto de origen" a
    alguien que lo tiene cargado — y esa persona lo carga de memoria y pisa la
    plantilla y la Caixa Postal reales.
    """
    base = _base()
    base.app_settings.rota = True
    salida = corre(puesta.estado())

    # Los TRES bloques que salen de app_settings, no solo el primero: cada uno
    # tiene su rama y una sola cubierta deja las otras dos sin red.
    for clave in ("punto_origen", "contenido", "operacion"):
        paso = next(p for p in salida["pasos"] if p["clave"] == clave)
        assert paso["estado"] == puesta.ILEGIBLE, clave
        assert "no se pudo leer" in paso["detalle"].lower(), clave
        assert "cargá" not in paso["detalle"].lower(), clave
        assert "no lo cargues de nuevo" in paso["detalle"].lower(), clave
    assert "pisarías" in salida["pasos"][0]["detalle"]


def test_durante_un_corte_no_se_afirma_que_puede_operar():
    """"No sé" no es "sí". Con lecturas fallidas la respuesta honesta es que no
    se puede afirmar nada, no que está todo bien."""
    base = _base()
    base.transportistas.rota = True
    salida = corre(puesta.estado())
    assert salida["puede_operar"] is False
    assert salida["hay_lecturas_fallidas"] is True


def test_una_lectura_fallida_no_cuenta_como_paso_que_falta():
    base = _base()
    base.colaboradores_retiro.rota = True
    salida = corre(puesta.estado())
    nomina = next(p for p in salida["pasos"] if p["clave"] == "nomina")
    assert nomina["estado"] == puesta.ILEGIBLE
    # `siguiente` apunta a lo que hay que CARGAR. Mandar a alguien a cargar algo
    # que no se pudo leer es exactamente el error de arriba.
    assert salida["siguiente"] != "nomina"


# --- cada paso --------------------------------------------------------------

def test_falta_un_transportista_de_cada_rol():
    _base(transportistas=[copy.deepcopy(TRP_BR)])
    paso = next(p for p in corre(puesta.estado())["pasos"]
                if p["clave"] == "transportistas")
    assert paso["estado"] == puesta.FALTA
    # Dice el que falta y NO el que está. Nombrar los dos manda a alguien a
    # revisar un transportista que ya cargó bien.
    assert "ninguno con rol Venezuela" in paso["detalle"]
    assert "ninguno con rol Brasil" not in paso["detalle"]
    assert paso["brasil"] == 1 and paso["venezuela"] == 0


def test_un_transportista_inactivo_no_cuenta():
    _base(transportistas=[copy.deepcopy(TRP_BR),
                          {**copy.deepcopy(TRP_VE), "activo": False}])
    paso = next(p for p in corre(puesta.estado())["pasos"]
                if p["clave"] == "transportistas")
    assert paso["estado"] == puesta.FALTA


def test_agencias_sin_punto_de_entrega_no_alcanzan():
    """Es la falta más fácil de no ver: hay doscientas agencias cargadas y el
    traslado sigue sin saber dónde termina."""
    _base(agencias=[{**copy.deepcopy(AGENCIA), "es_punto_entrega": False}])
    paso = next(p for p in corre(puesta.estado())["pasos"] if p["clave"] == "agencias")
    assert paso["estado"] == puesta.FALTA
    assert "punto de entrega" in paso["detalle"]
    assert paso["total"] == 1 and paso["punto_entrega"] == 0


def test_varias_agencias_marcadas_como_punto_de_entrega_tampoco_alcanzan():
    """EXACTAMENTE una, no "al menos una".

    En producción quedaron 250 marcadas —un CSV con la columna en verdadero en
    todas las filas— y este paso seguía en verde. El verde es peor que el rojo:
    dice que el paso está resuelto cuando el operador no tiene una respuesta a
    "dónde termina el traslado".

    Mutación: volver la condición a `if not entrega` deja este caso en LISTO y
    este test se pone en rojo.
    """
    _base(agencias=[{**copy.deepcopy(AGENCIA), "codigo": "001",
                     "es_punto_entrega": True},
                    {**copy.deepcopy(AGENCIA), "codigo": "014",
                     "es_punto_entrega": True}])
    paso = next(p for p in corre(puesta.estado())["pasos"] if p["clave"] == "agencias")
    assert paso["estado"] == puesta.FALTA
    assert paso["punto_entrega"] == 2
    # Y le dice a la persona cómo salir del estado inválido, que es guardar la
    # correcta desde el panel: eso desmarca las demás.
    assert "una" in paso["detalle"]


def test_una_sola_marcada_deja_el_paso_listo():
    """El borde de arriba del test anterior: con una, y solo una, se puede operar."""
    _base(agencias=[{**copy.deepcopy(AGENCIA), "es_punto_entrega": True}])
    paso = next(p for p in corre(puesta.estado())["pasos"] if p["clave"] == "agencias")
    assert paso["estado"] == puesta.LISTO
    assert paso["punto_entrega"] == 1


def test_si_no_se_pueden_contar_las_agencias_no_se_dice_que_no_hay():
    """Cero agencias y "no pude contar" mandan a lugares distintos: el primero a
    cargar un CSV, el segundo a esperar. Confundirlos hace que alguien reimporte
    doscientas filas encima de las que ya estaban."""
    base = _base()
    base.agencias.rota = True
    paso = next(p for p in corre(puesta.estado())["pasos"] if p["clave"] == "agencias")
    assert paso["estado"] == puesta.ILEGIBLE
    assert "no se pudieron contar" in paso["detalle"].lower()


def test_el_de_turno_apunta_a_alguien_que_ya_no_esta_vigente():
    """El caso que se ve en producción y no en una instalación nueva: hay nómina
    viva, hay alguien designado, y el designado venció. La cotización rotularía a
    nombre de una persona que el mostrador ya no acepta."""
    vencido = {**copy.deepcopy(COLABORADOR),
               "autorizado_hasta": (AHORA - timedelta(days=10)).date().isoformat()}
    otro = {**copy.deepcopy(COLABORADOR), "colaborador_id": "col_2",
            "nombre": "Beto Ruiz"}
    _base(colaboradores_retiro=[vencido, otro])   # el turno sigue en col_1
    paso = next(p for p in corre(puesta.estado())["pasos"] if p["clave"] == "nomina")
    assert paso["estado"] == puesta.FALTA
    assert paso["vigentes"] == 1
    assert "de turno" in paso["detalle"]


def test_sin_transportista_venezolano_las_agencias_mandan_al_paso_anterior():
    _base(transportistas=[copy.deepcopy(TRP_BR)], agencias=[])
    paso = next(p for p in corre(puesta.estado())["pasos"] if p["clave"] == "agencias")
    assert paso["estado"] == puesta.FALTA
    assert "Primero" in paso["detalle"]


def test_nomina_con_gente_pero_sin_nadie_de_turno():
    _base(app_settings=[{**copy.deepcopy(PUNTO_ORIGEN), "retirador_activo_id": None},
                        copy.deepcopy(CONTENIDO), copy.deepcopy(OPERACION)])
    paso = next(p for p in corre(puesta.estado())["pasos"] if p["clave"] == "nomina")
    assert paso["estado"] == puesta.FALTA
    assert "de turno" in paso["detalle"]
    assert paso["vigentes"] == 1


def test_el_de_turno_tiene_que_seguir_vigente():
    """Designado en marzo, autorización vencida en junio. La cotización de julio
    rotularía a nombre de alguien que el mostrador ya no acepta."""
    vencido = {**copy.deepcopy(COLABORADOR),
               "autorizado_hasta": (AHORA - timedelta(days=10)).date().isoformat()}
    _base(colaboradores_retiro=[vencido])
    paso = next(p for p in corre(puesta.estado())["pasos"] if p["clave"] == "nomina")
    assert paso["estado"] == puesta.FALTA
    assert paso["vigentes"] == 0


def test_una_fecha_ilegible_deja_al_colaborador_afuera():
    raro = {**copy.deepcopy(COLABORADOR), "autorizado_hasta": "31/12/2026"}
    _base(colaboradores_retiro=[raro])
    paso = next(p for p in corre(puesta.estado())["pasos"] if p["clave"] == "nomina")
    assert paso["estado"] == puesta.FALTA


def test_sin_tarifa_publicada():
    _base(tarifas_envio=[])
    paso = next(p for p in corre(puesta.estado())["pasos"] if p["clave"] == "tarifa")
    assert paso["estado"] == puesta.FALTA
    assert "publicada" in paso["detalle"]


def test_una_tarifa_programada_todavia_no_rige():
    futura = {**copy.deepcopy(TARIFA), "vigente_desde": AHORA + timedelta(days=5)}
    _base(tarifas_envio=[futura])
    paso = next(p for p in corre(puesta.estado())["pasos"] if p["clave"] == "tarifa")
    assert paso["estado"] == puesta.FALTA


def test_la_tarifa_no_repite_lo_que_ya_dice_el_paso_de_transportistas():
    """Un solo problema tiene que verse una sola vez. Repetido, el admin cree que
    tiene dos y arregla uno."""
    sin_tabla = {**copy.deepcopy(TARIFA), "escalones_peso": []}
    _base(transportistas=[], tarifas_envio=[sin_tabla])
    salida = corre(puesta.estado())
    tarifa = next(p for p in salida["pasos"] if p["clave"] == "tarifa")
    assert "transportista" not in tarifa["detalle"].lower()
    assert "escalones" in tarifa["detalle"]


def test_el_bloque_de_operacion_explica_por_que_hay_que_cargarlo():
    """Es el único que parece opcional y no lo es: sin él no hay tolerancia, y
    sin tolerancia todo repesaje ajusta el precio."""
    _base(app_settings=[copy.deepcopy(PUNTO_ORIGEN), copy.deepcopy(CONTENIDO)])
    paso = next(p for p in corre(puesta.estado())["pasos"] if p["clave"] == "operacion")
    assert paso["estado"] == puesta.FALTA
    assert "tolerancia" in paso["detalle"]


# --- forma de la respuesta --------------------------------------------------

def test_cada_paso_dice_a_donde_ir():
    _base()
    for paso in corre(puesta.estado())["pasos"]:
        assert paso["donde"], paso["clave"]
        assert paso["titulo"]
        assert paso["estado"] in (puesta.LISTO, puesta.FALTA, puesta.ILEGIBLE)


def test_la_portada_no_escribe_nada():
    """Es una pantalla de diagnóstico. Si además arreglara cosas, abrirla para
    entender un problema se lo cambiaría a uno abajo de los pies."""
    import ast
    arbol = ast.parse(open(os.path.join(_BACKEND, "services",
                                        "envios_puesta_en_marcha.py"),
                           encoding="utf-8").read())
    escrituras = {"insert_one", "insert_many", "update_one", "update_many",
                  "replace_one", "delete_one", "delete_many",
                  "find_one_and_update", "guardar", "auditar"}
    usadas = {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
    assert not (usadas & escrituras), sorted(usadas & escrituras)
