"""
El panel de configuracion: validar, auditar e invalidar. En ese orden.

CONTEXTO
    Un panel que escribe JSON libre en Mongo es una bomba de tiempo: un typo en
    una clave rompe la cotizacion en produccion y nadie sabe quien lo hizo. Y
    encima esta el bug clasico de todo panel: el super administrador cambia un
    valor, guarda, y no pasa nada hasta que el proceso reinicie.

QUE SE CUBRE
    1. Cada bloque valida contra su esquema, y el error dice QUE CAMPO esta mal.
    2. Un campo de mas se rechaza: casi siempre es un typo en el nombre de otro.
    3. La coma decimal se rechaza en vez de adivinarse.
    4. Guardar audita el cambio con quien, cuando y que cambio -- y solo lo que
       cambio, no el documento entero.
    5. Los datos sensibles salen ENMASCARADOS del log: la auditoria la lee mas
       gente de la que puede editar una cuenta bancaria.
    6. Guardar invalida el cache. Sin eso, el que guardo cree que no se guardo.

Los modulos se cargan por ruta directa para no arrastrar services/__init__.py.
"""
import asyncio
import importlib.util
import os
import re
import sys
import types

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)


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


cfg = _cargar("envios_config")
from models.envios_config import (  # noqa: E402
    Transportista, Agencia, CuentaBancaria, ConfigOperacion, ESQUEMAS,
)


def corre(coro):
    return asyncio.run(coro)


class _Coleccion:
    def __init__(self, filas=None):
        self.filas = filas or []

    async def find_one(self, filtro, _proj=None, sort=None):
        for d in self.filas:
            if all(d.get(k) == v for k, v in filtro.items()):
                return {k: v for k, v in d.items() if k != "_id"}
        return None

    async def update_one(self, filtro, cambio, upsert=False):
        for d in self.filas:
            if all(d.get(k) == v for k, v in filtro.items()):
                d.update(cambio["$set"])
                return
        if upsert:
            self.filas.append({**filtro, **cambio["$set"]})

    async def insert_one(self, doc):
        self.filas.append(doc)


class _Db:
    def __init__(self):
        self._c = {}

    def __getattr__(self, nombre):
        return self._c.setdefault(nombre, _Coleccion())


class _Admin:
    user_id = "usr_admin"
    email = "admin@risappbr.com"
    name = "Julio"


# ─── 1. Validación ────────────────────────────────────────────────────────

def test_un_bloque_valido_pasa():
    validado, errores = cfg.validar("operacion", {"tolerancia_ajuste_ris": "3.00"})
    assert errores == []
    assert validado["tolerancia_ajuste_ris"] == "3.00"
    assert validado["ttl_cotizacion_horas"] == 48      # el default viaja completo


def test_un_bloque_desconocido_no_se_puede_guardar():
    """Agregar un bloque es agregar su esquema. Si no, cualquier typo en la ruta
    crea una configuración fantasma que nadie lee."""
    validado, errores = cfg.validar("inventado", {"lo": "que sea"})
    assert validado is None and "desconocido" in errores[0]


def test_el_error_dice_que_campo_esta_mal():
    """"Input should be a valid integer" no le dice a nadie qué arreglar."""
    _, errores = cfg.validar("operacion", {"ttl_cotizacion_horas": "muchas"})
    assert any("ttl_cotizacion_horas" in e for e in errores)


def test_un_campo_de_mas_se_rechaza():
    """Casi siempre es un typo en el nombre de otro: "tolerancia_ajuste" en vez
    de "tolerancia_ajuste_ris" guardaría un campo que nadie lee mientras el
    verdadero conserva el valor viejo."""
    _, errores = cfg.validar("operacion", {"tolerancia_ajuste": "3.00"})
    assert errores and "tolerancia_ajuste" in errores[0]


@pytest.mark.parametrize("valor", ["3,00", "", "abc", "Infinity"])
def test_los_numeros_mal_escritos_se_rechazan(valor):
    """La coma se rechaza en vez de convertirse: "1,5" puede ser uno y medio o
    mil quinientos según quién lo escriba, y adivinar mal en un precio es peor
    que pedir que lo escriban con punto."""
    _, errores = cfg.validar("operacion", {"tolerancia_ajuste_ris": valor})
    assert errores


def test_los_avisos_de_guarda_van_en_orden():
    _, errores = cfg.validar("operacion", {"alertas_guarda_dias": [25, 7]})
    assert errores
    _, sin_errores = cfg.validar("operacion", {"alertas_guarda_dias": [7, 15, 25]})
    assert sin_errores == []


def test_la_lista_de_prohibidos_no_puede_quedar_vacia():
    """Una lista vacía se lee literalmente como "no hay nada prohibido"."""
    for lista in ([], ["", "  "]):
        _, errores = cfg.validar("contenido", {
            "prohibidos": lista, "terminos_version": "envios-v1",
            "texto_estimado": "x" * 30})
        assert errores


def test_el_cep_del_punto_de_origen_tiene_ocho_digitos():
    base = {"nombre": "Agencia", "razon_social": "RIS App LTDA",
            "plantilla_direccion": "x" * 20}
    _, errores = cfg.validar("punto_origen", {**base, "cep": "1234"})
    assert errores
    validado, sin_errores = cfg.validar("punto_origen", {**base, "cep": "69355-000"})
    assert sin_errores == [] and validado["cep"] == "69355000"


# ─── 2. Los esquemas de catálogo ──────────────────────────────────────────

def test_el_codigo_de_transportista_tiene_forma_de_codigo():
    for malo in ("trp-7k2m", "TRP 7K2M", "TR", "TRP_7K2M"):
        with pytest.raises(Exception):
            Transportista(codigo=malo, nombre="Empresa", rol="venezuela",
                          regla_peso={"divisor": 5000})
    assert Transportista(codigo="TRP-7K2M", nombre="Empresa", rol="venezuela",
                         regla_peso={"divisor": 5000}).codigo == "TRP-7K2M"


def test_el_rol_solo_puede_ser_brasil_o_venezuela():
    """RIS App no es una fila de esta tabla: el tramo propio nunca se terceriza."""
    for malo in ("propio", "risapp", "origen", "destino"):
        with pytest.raises(Exception):
            Transportista(codigo="TRP-1111", nombre="Empresa", rol=malo,
                          regla_peso={"divisor": 5000})


def test_un_divisor_en_cero_se_rechaza_en_el_panel():
    """Abajo, el motor lo tolera y se cae al peso real —cobrar de menos ante un
    dato roto—. Acá se rechaza: es el momento en que hay una persona mirando."""
    with pytest.raises(Exception):
        Transportista(codigo="TRP-1111", nombre="Empresa", rol="brasil",
                      regla_peso={"divisor": 0})


def test_los_limites_son_todos_opcionales():
    """Lo que no se declara, no restringe: inventar un techo que después nadie
    puede explicar es peor que no tenerlo."""
    t = Transportista(codigo="TRP-1111", nombre="Empresa", rol="brasil",
                      regla_peso={"divisor": 5000})
    assert t.limites.peso_max_kg is None


def test_el_numero_de_cuenta_solo_acepta_digitos():
    with pytest.raises(Exception):
        CuentaBancaria(banco="Banco", numero="01AB2345", titular="Empresa",
                       documento="J-123456")
    c = CuentaBancaria(banco="Banco", numero="0102-1234-5678", titular="Empresa",
                       documento="J-123456")
    assert c.numero == "010212345678"


def test_una_agencia_pide_estado_y_ciudad():
    with pytest.raises(Exception):
        Agencia(codigo="001", nombre="Centro", estado="", ciudad="Caracas")


# ─── 3. Auditoría ─────────────────────────────────────────────────────────

def test_se_audita_solo_lo_que_cambio():
    """Guardar el documento entero dos veces hace que el log crezca y que nadie
    lo lea. Guardar lo que cambió lo vuelve útil: se abre y se ve la línea."""
    d = cfg.diferencias({"a": 1, "b": 2}, {"a": 1, "b": 3})
    assert d == {"b": {"antes": 2, "despues": 3}}


def test_los_metadatos_de_guardado_no_ensucian_el_log():
    d = cfg.diferencias({"a": 1, "actualizado_at": "ayer"},
                        {"a": 1, "actualizado_at": "hoy", "actualizado_por": "x"})
    assert d == {}


def test_el_numero_de_cuenta_sale_enmascarado():
    """La auditoría la lee más gente de la que puede editar una cuenta bancaria:
    un número completo ahí es el mismo dato en un lugar con menos control."""
    antes = {"cuenta_bancaria": {"banco": "X", "numero": "01021234567890",
                                 "documento": "J-12345678"}}
    despues = {"cuenta_bancaria": {"banco": "X", "numero": "01029999888877",
                                   "documento": "J-12345678"}}
    d = cfg.diferencias(antes, despues)
    texto = str(d)
    assert "01021234567890" not in texto and "01029999888877" not in texto
    assert "****7890" in texto and "****8877" in texto


def test_el_enmascarado_llega_hasta_lo_anidado():
    hondo = {"a": {"b": [{"numero": "12345678"}]}}
    assert "12345678" not in str(cfg.enmascarar(hondo))
    assert "****5678" in str(cfg.enmascarar(hondo))


def test_guardar_escribe_una_linea_de_auditoria():
    base = _Db()
    corre(cfg.guardar("operacion", {"tolerancia_ajuste_ris": "5.00"}, _Admin(), db=base))
    log = base.centro_gestion_log.filas
    assert len(log) == 1
    assert log[0]["tipo"] == "envios_config"
    assert log[0]["user_id"] == "usr_admin"
    assert log[0]["metadata"]["bloque"] == "operacion"
    assert log[0]["metadata"]["cambios"]["tolerancia_ajuste_ris"]["despues"] == "5.00"


def test_guardar_sin_cambiar_nada_no_ensucia_el_log():
    base = _Db()
    datos = {"tolerancia_ajuste_ris": "5.00"}
    corre(cfg.guardar("operacion", datos, _Admin(), db=base))
    corre(cfg.guardar("operacion", datos, _Admin(), db=base))
    assert len(base.centro_gestion_log.filas) == 1


def test_un_guardado_invalido_no_escribe_ni_audita():
    base = _Db()
    validado, errores = corre(cfg.guardar("operacion", {"ttl_cotizacion_horas": -5},
                                          _Admin(), db=base))
    assert validado is None
    # El error tiene que venir de la VALIDACIÓN y decir qué campo está mal, no de
    # un reventón más abajo: "No se pudo guardar" no le sirve a nadie para
    # arreglar nada, y significa que el dato inválido llegó hasta la escritura.
    assert any("ttl_cotizacion_horas" in e for e in errores), errores
    assert base.app_settings.filas == []
    assert base.centro_gestion_log.filas == []


# ─── 4. El caché ──────────────────────────────────────────────────────────

def test_guardar_invalida_el_cache():
    """El bug clásico: el super administrador cambia un valor, guarda, y no pasa
    nada hasta que el proceso reinicie."""
    llamadas = []
    base = _Db()
    corre(cfg.guardar("operacion", {"tolerancia_ajuste_ris": "5.00"}, _Admin(),
                      db=base, invalidar=lambda: llamadas.append(1)))
    assert llamadas == [1]


def test_un_guardado_rechazado_no_invalida_nada():
    llamadas = []
    base = _Db()
    corre(cfg.guardar("operacion", {"ttl_cotizacion_horas": -5}, _Admin(),
                      db=base, invalidar=lambda: llamadas.append(1)))
    assert llamadas == []


def test_leer_devuelve_lo_guardado():
    base = _Db()
    corre(cfg.guardar("operacion", {"tolerancia_ajuste_ris": "7.50"}, _Admin(), db=base))
    leido = corre(cfg.leer("operacion", db=base))
    assert leido["tolerancia_ajuste_ris"] == "7.50"
    assert leido["actualizado_por"] == "usr_admin"


def test_leer_un_bloque_que_no_existe_devuelve_none():
    assert corre(cfg.leer("operacion", db=_Db())) is None


# ─── 5. Todos los bloques declarados son usables ──────────────────────────

def test_todo_esquema_declarado_valida_su_propio_default():
    """Un bloque cuyo default no valida es un bloque que nadie puede guardar sin
    llenar todo a mano la primera vez."""
    for bloque, modelo in ESQUEMAS.items():
        campos_requeridos = [n for n, f in modelo.model_fields.items() if f.is_required()]
        if campos_requeridos:
            continue                      # ese bloque exige datos, y está bien
        validado, errores = cfg.validar(bloque, {})
        assert errores == [], f"{bloque}: {errores}"


# ─── 6. Las reglas de la ruta, probadas sin levantar FastAPI ──────────────
#
# Las rutas son delgadas a propósito: leen, llaman y escriben. Lo que sí tiene
# reglas propias —qué no se puede editar, cómo se confirma un cambio de cuenta,
# qué hace un CSV con una fila mala— se prueba acá contra las funciones y los
# modelos, sin necesidad de un cliente HTTP ni de Mongo.

def _fuente_ruta():
    return open(os.path.join(_BACKEND, "routes", "envios_admin.py"), encoding="utf-8").read()


# Las escrituras que hace el OPERADOR y no el super administrador. Son las
# operativas —tocar un paquete que está viajando— y no las de configuración: el
# que verifica un comprobante en el mostrador no tiene por qué poder cambiar los
# precios ni la cuenta que recibe los fletes.
#
# Escrita a mano y verificada contra el archivo, para que agregar una ruta
# operativa sea una decisión y no un descuido.
ESCRITURAS_DEL_OPERADOR = (
    "verificar_comprobante",
    # La operacion: mover paquetes que el operador tiene en la mano.
    "marcar_disponible", "retirar_lote", "repesar", "despachar", "entregar",
)


def test_solo_el_super_administrador_escribe_la_configuracion():
    """El operador lee lo que necesita para trabajar y toca los paquetes que
    tiene en la mano. Que cargar el monto de un flete y cambiar la cuenta que lo
    recibe sean dos permisos distintos es lo que impide que una sola persona haga
    las dos cosas."""
    fuente = _fuente_ruta()
    escrituras = re.findall(
        r"@router\.(?:post|put|patch)\([^)]*\)\s*\nasync def (\w+)", fuente)
    for funcion in escrituras:
        cabecera = _cabecera_de(fuente, funcion)
        if funcion in ESCRITURAS_DEL_OPERADOR:
            assert "get_crm_user" in cabecera, funcion
            assert "get_super_admin" not in cabecera, funcion
        else:
            assert "get_super_admin" in cabecera, f"escritura sin super admin: {funcion}"


def test_las_escrituras_del_operador_estan_declaradas_y_existen():
    """Una lista blanca que nombra funciones borradas protege tanto como una
    lista vacía."""
    fuente = _fuente_ruta()
    escrituras = set(re.findall(
        r"@router\.(?:post|put|patch)\([^)]*\)\s*\nasync def (\w+)", fuente))
    assert set(ESCRITURAS_DEL_OPERADOR) <= escrituras


def _cabecera_de(fuente: str, funcion: str) -> str:
    inicio = fuente.index(f"async def {funcion}(")
    resto = fuente[inicio:]
    return resto[:resto.index("):") + 2] if "):" in resto[:600] else resto[:600]


def test_las_lecturas_las_puede_hacer_el_operador():
    fuente = _fuente_ruta()
    assert "get_crm_user" in fuente


def test_el_codigo_de_un_transportista_no_se_edita():
    """Los envíos viejos, los logs y los tests lo referencian: renombrarlo rompe
    la trazabilidad hacia atrás sin avisar."""
    fuente = _fuente_ruta()
    assert 'for prohibido in ("codigo", "transportista_id", "cuenta_bancaria")' in fuente


def test_la_cuenta_bancaria_tiene_su_propia_ruta_con_confirmacion():
    fuente = _fuente_ruta()
    assert "confirmacion_numero" in fuente
    assert "sin copiar y pegar" in fuente
    # Y versiona en vez de pisar.
    assert "cuentas_anteriores" in fuente and "version_id" in fuente


def test_la_ruta_de_la_cuenta_no_congela_nada_en_los_envios():
    """El transportista puede cambiarla sin avisar: una copia congelada dentro de
    un envío pagaría a una cuenta muerta. El destino es siempre la vigente."""
    fuente = _fuente_ruta()
    assert "db.envios" not in fuente


def test_ninguna_ruta_borra_nada():
    """Nada se borra, todo se desactiva: el historial de envíos apunta a esas
    filas, y borrar una deja envíos viejos apuntando al vacío."""
    fuente = _fuente_ruta()
    assert "@router.delete" not in fuente
    for borrado in ("delete_one", "delete_many", "drop("):
        assert borrado not in fuente


# Las rutas que cambian algo que el catálogo o los límites leen. Escritas a mano
# porque contar decoradores es una heurística: hay escrituras que NO tienen que
# invalidar nada —guardar un borrador de tarifa no afecta a ningún usuario— y
# confundir las dos cosas hace que el test moleste sin proteger.
RUTAS_QUE_INVALIDAN = (
    "crear_transportista", "editar_transportista", "cambiar_cuenta",
    "crear_agencia", "importar_agencias", "publicar_tarifa",
    # Esta no la llama directo: se la pasa al servicio como `invalidar=`, que es
    # lo que verifica test_el_guardado_de_configuracion_pasa_la_invalidacion.
    "guardar_bloque",
    # Escribe el bloque punto_origen por el mismo camino auditado.
    "designar_retirador",
)

# Las operativas no invalidan cache de configuracion: no tocan nada que el
# catalogo o los limites lean.

RUTAS_QUE_NO_TOCAN_LO_QUE_SE_LEE = (
    "guardar_borrador_tarifa", "simular_tarifa",
    # La nómina no la lee ninguna pantalla cacheada.
    "crear_colaborador", "editar_colaborador",
    # Las operativas mueven paquetes y emiten cobros; no cambian ninguna
    # configuracion que el catalogo o los limites lean.
    "verificar_comprobante", "marcar_disponible", "retirar_lote", "repesar",
    "despachar", "entregar",
)


def _cuerpo_de(fuente: str, funcion: str) -> str:
    """El cuerpo de la función, SIN comentarios.

    Sin sacarlos, un comentario que explica por qué esta ruta NO llama a
    `invalidar_cache()` cuenta como si la llamara. Un test que lee código fuente
    tiene que leer código, no prosa."""
    inicio = fuente.index(f"async def {funcion}(")
    resto = fuente[inicio:]
    fin = resto.find("\n@router.", 1)
    cuerpo = resto if fin < 0 else resto[:fin]
    return "\n".join(l for l in cuerpo.split("\n") if not l.lstrip().startswith("#"))


def test_toda_escritura_que_importa_invalida_el_cache():
    """Si una sola se olvida, el panel guarda y la pantalla sigue mostrando lo
    viejo — y el que guardó cree que no se guardó."""
    fuente = _fuente_ruta()
    for funcion in RUTAS_QUE_INVALIDAN:
        assert "invalidar_cache" in _cuerpo_de(fuente, funcion), funcion


def test_ninguna_escritura_queda_fuera_de_las_dos_listas():
    """La guardia que hace que las listas de arriba no se queden viejas.

    Escritas a mano son una lista blanca: la ruta de escritura que agregue el PR
    siguiente no está en ninguna de las dos, no invalida nada, y el test pasa en
    verde igual. Este barrido obliga a decidir: o invalida, o se declara que no
    hace falta. Las dos cosas son respuestas válidas; olvidarse no.
    """
    fuente = _fuente_ruta()
    escrituras = set(re.findall(
        r"@router\.(?:post|put|patch)\([^)]*\)\s*\nasync def (\w+)", fuente))
    declaradas = set(RUTAS_QUE_INVALIDAN) | set(RUTAS_QUE_NO_TOCAN_LO_QUE_SE_LEE)
    sin_declarar = escrituras - declaradas
    assert sin_declarar == set(), (
        f"Estas rutas de escritura no están en ninguna lista: {sorted(sin_declarar)}. "
        f"Agregalas a RUTAS_QUE_INVALIDAN o, si de verdad no tocan nada que se lea, "
        f"a RUTAS_QUE_NO_TOCAN_LO_QUE_SE_LEE.")
    # Y las declaradas tienen que existir: una lista que nombra funciones
    # borradas protege tanto como una lista vacía.
    assert declaradas <= escrituras, sorted(declaradas - escrituras)


def test_guardar_un_borrador_no_invalida_nada():
    """Un borrador no lo lee ninguna cotización: invalidar ahí sería tirar el
    caché de todos cada vez que alguien tipea un número en el editor."""
    fuente = _fuente_ruta()
    for funcion in RUTAS_QUE_NO_TOCAN_LO_QUE_SE_LEE:
        assert "invalidar_cache" not in _cuerpo_de(fuente, funcion), funcion


def test_el_guardado_de_configuracion_pasa_la_invalidacion_al_servicio():
    assert "invalidar=invalidar_cache" in _fuente_ruta()


def test_el_panel_no_menciona_ninguna_marca():
    fuente = _fuente_ruta().lower()
    for marca in ("mrw", "correios", "zoom", "tealca"):
        assert marca not in fuente
