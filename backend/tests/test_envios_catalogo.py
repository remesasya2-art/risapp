"""
Las dos rutas de lectura del modulo, y la estructura que crean los indices.

CONTEXTO
    Antes de que el usuario tipee un peso, la pantalla necesita dos cosas: a
    donde puede mandar, y que caja le van a aceptar. Ninguna de las dos mueve
    plata, pero la segunda es la que evita el bug del PR #40 un escalon mas
    arriba: la pantalla anunciaba un techo que el servidor no validaba, porque el
    numero vivia en dos lados y solo uno mandaba.

QUE SE CUBRE
    1. Un sistema recien instalado —sin transportistas, sin tarifa— responde
       "no disponible" con la lista de lo que falta. NO rompe, y sobre todo no
       devuelve limites vacios, que la pantalla leeria como "sin restricciones".
    2. Los limites son la interseccion de los transportistas activos, y cada uno
       viene con el CODIGO de quien lo impone.
    3. El catalogo trae las agencias activas de los transportistas de destino, y
       ahi los nombres comerciales SI viajan: son datos que el usuario tiene que
       leer para elegir.
    4. El cache tiene TTL e invalidacion explicita. Es el bug clasico del panel:
       el super administrador guarda una agencia y no aparece.
    5. Los indices crean estructura y NUNCA datos: ningun seed con una empresa de
       ejemplo, que es como un nombre real termina en el repositorio.

Los modulos se cargan por ruta directa para no arrastrar services/__init__.py,
que importa twilio, ni database.py, que abre un cliente de Mongo.
"""
import asyncio
import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


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
_cargar("referencias")
cat = _cargar("envios_catalogo")
idx = _cargar("envios_indices")


def corre(coro):
    return asyncio.run(coro)


# ─── Un Mongo de mentira ──────────────────────────────────────────────────

class _Cursor:
    def __init__(self, filas):
        self._filas = list(filas)

    def sort(self, campo, direccion=1):
        self._filas.sort(key=lambda d: str(d.get(campo, "")), reverse=direccion < 0)
        return self

    async def to_list(self, _n):
        return list(self._filas)


def _proyectar(doc, proyeccion):
    """Aplica la proyección como lo haría Mongo. Sin esto, un campo que la
    consulta no pide igual llega al código bajo prueba, y un olvido en la
    proyección pasa los tests y falla en producción — que es exactamente lo que
    pasó con `limites` en referencias.py."""
    if not proyeccion or not isinstance(doc, dict):
        return doc
    incluidos = [k for k, v in proyeccion.items() if v and k != "_id"]
    if incluidos:
        return {k: v for k, v in doc.items() if k in incluidos}
    excluidos = [k for k, v in proyeccion.items() if not v]
    return {k: v for k, v in doc.items() if k not in excluidos}


class _Coleccion:
    def __init__(self, filas, rompe=False):
        self.filas = filas
        self.rompe = rompe
        self.indices = []

    def _coincide(self, doc, filtro):
        for k, v in filtro.items():
            if isinstance(v, dict) and "$gte" in v:
                if not (float(doc.get(k, 0)) >= float(v["$gte"])):
                    return False
            elif doc.get(k) != v:
                return False
        return True

    def find(self, filtro, proyeccion=None):
        if self.rompe:
            raise RuntimeError("la base no responde")
        return _Cursor([_proyectar(d, proyeccion)
                        for d in self.filas if self._coincide(d, filtro)])

    async def find_one(self, filtro, proyeccion=None, sort=None):
        if self.rompe:
            raise RuntimeError("la base no responde")
        c = [_proyectar(d, proyeccion) for d in self.filas if self._coincide(d, filtro)]
        if sort:
            campo, direccion = sort[0]
            c.sort(key=lambda d: str(d.get(campo, "")), reverse=direccion < 0)
        return c[0] if c else None

    async def create_index(self, claves, **opciones):
        if self.rompe:
            raise RuntimeError("no se pudo crear")
        self.indices.append((claves, opciones))


class _Db:
    def __init__(self, **colecciones):
        self._c = {k: _Coleccion(v) for k, v in colecciones.items()}

    def __getattr__(self, nombre):
        return self._c.setdefault(nombre, _Coleccion([]))

    def __getitem__(self, nombre):
        return self._c.setdefault(nombre, _Coleccion([]))


# ─── Datos. Solo códigos en las reglas; los nombres los carga el panel. ───

TRP_BR = {"transportista_id": "trp_br1", "codigo": "TRP-7K2M", "rol": "brasil",
          "activo": True, "orden": 1, "nombre": "Empresa de Origen",
          "limites": {"peso_max_kg": 30, "lado_max_cm": 100, "suma_lados_max_cm": 200,
                      "largo_min_cm": 11, "ancho_min_cm": 6, "alto_min_cm": "0.4"}}
TRP_VE = {"transportista_id": "trp_ve1", "codigo": "TRP-3Q9X", "rol": "venezuela",
          "activo": True, "orden": 1, "nombre": "Empresa de Destino",
          "limites": {"peso_max_kg": 70, "lado_max_cm": 120}}

AGENCIAS = [
    {"transportista_id": "trp_ve1", "codigo": "agc_001", "nombre": "Centro",
     "estado": "Miranda", "ciudad": "Caracas", "activa": True, "zona": "zona_a"},
    {"transportista_id": "trp_ve1", "codigo": "agc_002", "nombre": "Este",
     "estado": "Anzoátegui", "ciudad": "Barcelona", "activa": True, "zona": "zona_b"},
    {"transportista_id": "trp_ve1", "codigo": "agc_009", "nombre": "Cerrada",
     "estado": "Zulia", "ciudad": "Maracaibo", "activa": False, "zona": "zona_c"},
]

_AYER = datetime.now(timezone.utc) - timedelta(days=1)
_EL_MES_QUE_VIENE = datetime.now(timezone.utc) + timedelta(days=30)

TARIFA = {"version_id": "tar_2026_09_a", "vigente_hasta": None,
          "vigente_desde": _AYER, "moneda": "RIS",
          "regla_peso": {"divisor": 5000, "escalon_kg": "0.5", "minimo_kg": "1.0"},
          "escalones_peso": [{"desde_kg": "0", "hasta_kg": "1", "precio": "45"}],
          "limites_propios": {"valor_declarado_max": 3000}}


def db_completa():
    return _Db(transportistas=[TRP_BR, TRP_VE], agencias=list(AGENCIAS),
               tarifas_envio=[TARIFA])


@pytest.fixture(autouse=True)
def _sin_cache():
    cat.invalidar_cache()
    yield
    cat.invalidar_cache()


# ─── 1. El sistema recién instalado ───────────────────────────────────────

def test_sin_nada_configurado_responde_no_disponible_y_no_rompe():
    """Es el estado normal de un módulo recién instalado, no una falla."""
    r = corre(cat.limites(db=_Db()))
    assert r["disponible"] is False
    assert len(r["faltantes"]) == 3          # rol brasil, rol venezuela, tarifa
    assert r["tarifa_version"] is None


def test_sin_configurar_los_limites_van_vacios_pero_disponible_dice_que_no():
    """El peligro es que la pantalla lea un dict de límites vacío como "no hay
    restricciones" y deje cotizar cualquier cosa. Por eso mira `disponible`."""
    r = corre(cat.limites(db=_Db()))
    assert all(v is None for v in r["limites"].values())
    assert r["disponible"] is False


def test_con_un_solo_rol_cargado_sigue_sin_estar_disponible():
    r = corre(cat.limites(db=_Db(transportistas=[TRP_BR], tarifas_envio=[TARIFA])))
    assert r["disponible"] is False
    assert any("Venezuela" in f for f in r["faltantes"])


def test_con_todo_cargado_esta_disponible():
    r = corre(cat.limites(db=db_completa()))
    assert r["disponible"] is True
    assert r["faltantes"] == []
    assert r["tarifa_version"] == "tar_2026_09_a"


# ─── 2. Los límites son la intersección ───────────────────────────────────

def test_los_limites_son_la_interseccion_de_los_activos():
    r = corre(cat.limites(db=db_completa()))
    assert r["limites"]["peso_max_kg"] == 30.0       # el más estricto de los dos
    assert r["limites"]["lado_max_cm"] == 100.0
    assert r["limites"]["largo_min_cm"] == 11.0      # los mínimos también viajan


def test_cada_limite_dice_quien_lo_impone_por_su_codigo():
    """"El transportista TRP-7K2M no despacha más de 100 cm de lado" es una regla
    que soporte puede verificar; "no se despacha más de 100 cm" no."""
    r = corre(cat.limites(db=db_completa()))
    assert r["impuesto_por"]["lado_max_cm"] == "TRP-7K2M"
    assert r["impuesto_por"]["valor_declarado_max"] == "propio"


def test_los_limites_propios_de_la_tarifa_entran_en_la_interseccion():
    r = corre(cat.limites(db=db_completa()))
    assert r["limites"]["valor_declarado_max"] == 3000.0


def test_los_limites_salen_como_numeros_json_y_no_como_decimal():
    r = corre(cat.limites(db=db_completa()))
    for v in r["limites"].values():
        assert v is None or isinstance(v, float)
        assert not isinstance(v, Decimal)


def test_la_lista_de_prohibidos_y_la_version_de_terminos_viajan():
    r = corre(cat.limites(db=db_completa()))
    assert any("industrial" in p for p in r["prohibidos"])
    assert r["terminos_version"]


def test_una_tarifa_con_su_propia_lista_de_prohibidos_le_gana_a_la_semilla():
    """La lista que se aplica vive en la configuración, no en el código."""
    tarifa = dict(TARIFA, prohibidos=["solo esto"])
    r = corre(cat.limites(db=_Db(transportistas=[TRP_BR, TRP_VE],
                                 agencias=list(AGENCIAS), tarifas_envio=[tarifa])))
    assert r["prohibidos"] == ["solo esto"]


# ─── 3. El catálogo ───────────────────────────────────────────────────────

def test_el_catalogo_trae_los_transportistas_de_destino_con_sus_agencias():
    c = corre(cat.catalogo(db=db_completa()))
    assert c["disponible"] is True
    assert [t["codigo"] for t in c["transportistas"]] == ["TRP-3Q9X"]
    assert [a["codigo"] for a in c["transportistas"][0]["agencias"]] == ["agc_002", "agc_001"]


def test_las_agencias_desactivadas_no_aparecen():
    c = corre(cat.catalogo(db=db_completa()))
    codigos = [a["codigo"] for a in c["transportistas"][0]["agencias"]]
    assert "agc_009" not in codigos


def test_en_el_catalogo_los_nombres_comerciales_SI_viajan():
    """La regla es que el nombre no viva en el código, no que sea secreto: el
    usuario tiene que leerlo para elegir a dónde manda."""
    c = corre(cat.catalogo(db=db_completa()))
    assert c["transportistas"][0]["nombre"] == "Empresa de Destino"
    assert c["transportistas"][0]["agencias"][0]["nombre"]


def test_un_transportista_sin_agencias_no_alcanza_para_estar_disponible():
    """Un desplegable vacío es peor que un cartel que dice que no se puede."""
    c = corre(cat.catalogo(db=_Db(transportistas=[TRP_BR, TRP_VE], agencias=[])))
    assert c["disponible"] is False


def test_sin_transportistas_de_destino_el_catalogo_no_rompe():
    c = corre(cat.catalogo(db=_Db()))
    assert c["transportistas"] == [] and c["disponible"] is False
    assert c["degradado"] is False      # vacío por configuración, no por falla


# ─── 4. El caché y su bug clásico ─────────────────────────────────────────

def test_el_catalogo_se_cachea():
    base = db_completa()
    primero = corre(cat.catalogo(db=base))
    base.agencias.filas.append({"transportista_id": "trp_ve1", "codigo": "agc_003",
                                "nombre": "Nueva", "estado": "Lara", "ciudad": "Barquisimeto",
                                "activa": True})
    segundo = corre(cat.catalogo(db=base))
    assert segundo == primero          # todavía el cacheado


def test_invalidar_el_cache_hace_aparecer_lo_que_el_panel_acaba_de_guardar():
    """El bug clásico de todo panel: el super administrador agrega una agencia,
    guarda, y no aparece hasta que el proceso reinicie."""
    base = db_completa()
    corre(cat.catalogo(db=base))
    base.agencias.filas.append({"transportista_id": "trp_ve1", "codigo": "agc_003",
                                "nombre": "Nueva", "estado": "Lara", "ciudad": "Barquisimeto",
                                "activa": True})
    cat.invalidar_cache()
    c = corre(cat.catalogo(db=base))
    assert "agc_003" in [a["codigo"] for a in c["transportistas"][0]["agencias"]]


def test_se_puede_pedir_sin_cache():
    base = db_completa()
    corre(cat.catalogo(db=base))
    base.agencias.filas.append({"transportista_id": "trp_ve1", "codigo": "agc_003",
                                "nombre": "Nueva", "estado": "Lara", "ciudad": "Barquisimeto",
                                "activa": True})
    c = corre(cat.catalogo(db=base, usar_cache=False))
    assert "agc_003" in [a["codigo"] for a in c["transportistas"][0]["agencias"]]


def test_los_limites_NO_se_cachean():
    """Cambian con cada alta de transportista y con cada tarifa nueva, y son lo
    que decide si el formulario deja pasar una caja. Un límite viejo cotiza algo
    que después no se puede despachar."""
    base = db_completa()
    corre(cat.limites(db=base))
    base.transportistas.filas.append({"transportista_id": "trp_ve2", "codigo": "TRP-1A1A",
                                      "rol": "venezuela", "activo": True, "orden": 2,
                                      "limites": {"peso_max_kg": 20}})
    r = corre(cat.limites(db=base))
    assert r["limites"]["peso_max_kg"] == 20.0


# ─── 5. Los índices: estructura, nunca datos ──────────────────────────────

# Los índices que, si faltan, duelen. Escritos a mano contra el código, no
# derivados de él: `creados == len(INDICES)` se cumple con cualquier lista, y
# borrar cuatro índices no rompía un solo test.
INDICES_QUE_NO_PUEDEN_FALTAR = {
    ("envios", (("estado", 1), ("created_at", -1))),      # la cola del operador
    ("envios", (("user_id", 1), ("created_at", -1))),     # "mis envíos"
    ("envios_eventos", (("envio_id", 1), ("created_at", 1))),
    ("agencias", (("transportista_id", 1), ("codigo", 1))),
    ("tarifas_envio", (("vigente_desde", -1),)),
    ("matrices_referencia", (("transportista_id", 1), ("clave", 1), ("hasta_kg", 1))),
}


def _normalizar(claves):
    return tuple(tuple(c) for c in claves) if isinstance(claves, list) else claves


def test_estan_los_indices_que_no_pueden_faltar():
    """Sin el de la cola, el panel escanea la colección entera en cada refresh."""
    declarados = {(c, _normalizar(k)) for c, k, _ in idx.INDICES}
    faltan = INDICES_QUE_NO_PUEDEN_FALTAR - declarados
    assert not faltan, f"faltan índices: {faltan}"


def test_los_indices_se_crean_con_sus_opciones():
    """El fake registra qué se pidió: sin esto, borrar los `unique` de la llamada
    a create_index no rompía nada."""
    base = _Db()
    corre(idx.ensure_envios_indexes(db=base))
    pedidos = {(c, _normalizar(k)): o for c in idx.COLECCIONES
               for k, o in base[c].indices}
    assert pedidos[("envios", "envio_id")].get("unique") is True
    assert pedidos[("envios", "tracking_token")].get("unique") is True
    assert pedidos[("agencias", (("transportista_id", 1), ("codigo", 1)))].get("unique") is True
    # Y los que no son únicos no se crearon como únicos por descuido.
    assert not pedidos[("envios", (("estado", 1), ("created_at", -1)))].get("unique")


def test_se_crean_todos_los_indices_declarados():
    base = _Db()
    r = corre(idx.ensure_envios_indexes(db=base))
    assert r["creados"] == len(idx.INDICES)
    assert r["fallidos"] == [] and r["timeout"] is False


def test_los_indices_apuntan_a_las_colecciones_declaradas():
    """Si alguien agrega un índice sobre una colección que no está en la lista,
    esa colección existe sin que nadie lo haya decidido."""
    for coleccion, _, _ in idx.INDICES:
        assert coleccion in idx.COLECCIONES, coleccion


def test_las_unicidades_que_importan_estan():
    """El display_id y el tracking_token duplicados son dos bugs distintos y los
    dos son caros: uno confunde a soporte, el otro filtra envíos ajenos."""
    unicos = {(c, k) for c, k, o in idx.INDICES
              if o.get("unique") and isinstance(k, str)}
    assert ("envios", "envio_id") in unicos
    assert ("envios", "display_id") in unicos
    assert ("envios", "tracking_token") in unicos


def test_todo_unico_sobre_un_campo_suelto_es_sparse():
    """Un único sin sparse trata la ausencia del campo como un valor: el segundo
    documento que no lo tiene choca con el primero. Importa el día que un campo
    se asigne en un segundo paso."""
    for coleccion, claves, opciones in idx.INDICES:
        if opciones.get("unique") and isinstance(claves, str):
            assert opciones.get("sparse"), f"{coleccion}/{claves} es único y no sparse"


def test_el_codigo_de_agencia_es_unico_por_transportista_y_no_global():
    """Dos empresas distintas pueden llamar "001" a su sucursal central. Un único
    global le impide al panel guardar la segunda, con un E11000 que solo aparece
    como warning en el arranque."""
    for coleccion, claves, opciones in idx.INDICES:
        if coleccion == "agencias" and opciones.get("unique"):
            assert claves == [("transportista_id", 1), ("codigo", 1)]


def test_un_indice_que_falla_no_tumba_el_arranque():
    """Un índice único sobre datos que ya violan la unicidad falla acá. Es
    información valiosa, no una razón para no levantar la aplicación."""
    class _Roto(_Db):
        def __getitem__(self, nombre):
            c = super().__getitem__(nombre)
            c.rompe = True
            return c

    r = corre(idx.ensure_envios_indexes(db=_Roto()))
    assert r["creados"] == 0
    assert len(r["fallidos"]) == len(idx.INDICES)
    assert all(f["coleccion"] and f["error"] for f in r["fallidos"])


def test_no_hay_ningun_seed_de_datos():
    """Un seed con una empresa de ejemplo es exactamente como un nombre real
    termina en el repositorio y después no sale más."""
    fuente = open(os.path.join(_BACKEND, "services", "envios_indices.py"),
                  encoding="utf-8").read()
    for sospechoso in ("insert_one", "insert_many", "update_one", "upsert"):
        assert sospechoso not in fuente, f"el módulo de índices escribe datos: {sospechoso}"


def test_el_modulo_de_indices_no_menciona_ninguna_marca():
    fuente = open(os.path.join(_BACKEND, "services", "envios_indices.py"),
                  encoding="utf-8").read().lower()
    for marca in ("mrw", "correios", "zoom", "tealca"):
        assert marca not in fuente


# ─── 6. Lo que la revisión encontró ───────────────────────────────────────

def test_los_limites_llegan_de_verdad_con_el_sistema_configurado():
    """El test que faltaba, y por cuyo hueco pasó el bug: la proyección de
    referencias.py no traía `limites`, así que la ruta devolvía todo en null con
    `disponible: true` — exactamente lo que este módulo existe para impedir."""
    r = corre(cat.limites(db=db_completa()))
    assert r["disponible"] is True
    assert r["limites"]["peso_max_kg"] == 30.0
    assert r["limites"]["lado_max_cm"] == 100.0
    assert any(v is not None for v in r["limites"].values())


def test_el_catalogo_trae_el_nombre_de_verdad():
    """Mismo hueco, otra cara: la proyección que sirve para las referencias no
    sirve para el catálogo, porque saca el nombre a propósito."""
    c = corre(cat.catalogo(db=db_completa()))
    assert c["transportistas"][0]["nombre"] == "Empresa de Destino"


@pytest.mark.parametrize("activa", [True, 1, "true", "si"])
def test_una_agencia_activa_de_cualquier_forma_aparece(activa):
    """`{"activa": True}` en Mongo no matchea un 1 ni un "true": una agencia dada
    de alta desde el panel desaparecía del formulario sin un solo log."""
    agencias = [dict(AGENCIAS[0], activa=activa)]
    c = corre(cat.catalogo(db=_Db(transportistas=[TRP_BR, TRP_VE], agencias=agencias)))
    assert c["transportistas"][0]["agencias"]


@pytest.mark.parametrize("activa", [False, 0, "false", "no", ""])
def test_y_una_dada_de_baja_de_cualquier_forma_no(activa):
    agencias = [dict(AGENCIAS[0], activa=activa)]
    c = corre(cat.catalogo(db=_Db(transportistas=[TRP_BR, TRP_VE], agencias=agencias)))
    assert c["transportistas"][0]["agencias"] == []


def test_un_resultado_degradado_no_se_cachea():
    """Un hipo de la base de cinco segundos dejaría "no disponible" pegado cinco
    minutos para todo el mundo, mucho después de que la base se recuperó."""
    base = db_completa()
    base.agencias.rompe = True
    primero = corre(cat.catalogo(db=base))
    assert primero["degradado"] is True and primero["disponible"] is False

    base.agencias.rompe = False
    segundo = corre(cat.catalogo(db=base))
    assert segundo["degradado"] is False
    assert segundo["transportistas"][0]["agencias"]


def test_una_tarifa_programada_para_el_mes_que_viene_no_rige_hoy():
    """`vigente_desde` existe para poder dejar un aumento programado. Sin
    compararlo contra hoy, ese aumento rige desde que se guarda: el super
    administrador cree que programó algo y en realidad lo publicó."""
    futura = dict(TARIFA, version_id="tar_futura", vigente_desde=_EL_MES_QUE_VIENE)
    base = _Db(transportistas=[TRP_BR, TRP_VE], agencias=list(AGENCIAS),
               tarifas_envio=[TARIFA, futura])
    assert corre(cat.tarifa_vigente(db=base))["version_id"] == "tar_2026_09_a"


def test_una_version_sin_fecha_de_inicio_es_un_borrador_y_no_rige():
    borrador = {"version_id": "tar_borrador", "vigente_hasta": None,
                "escalones_peso": [{"desde_kg": "0", "hasta_kg": "1", "precio": "45"}]}
    base = _Db(transportistas=[TRP_BR, TRP_VE], tarifas_envio=[borrador])
    assert corre(cat.tarifa_vigente(db=base)) is None
    assert corre(cat.limites(db=base))["disponible"] is False


@pytest.mark.parametrize("valor", [float("inf"), float("-inf"), float("nan"), "Infinity"])
def test_un_limite_no_finito_no_revienta_la_serializacion(valor):
    """float('inf') pasa el try/except de la ruta y explota DESPUÉS, cuando
    starlette serializa con allow_nan=False: un 500 sin traza útil. Un dato roto
    es "no hay límite declarado"."""
    trp = dict(TRP_VE, limites={"peso_max_kg": valor})
    r = corre(cat.limites(db=_Db(transportistas=[TRP_BR, trp], tarifas_envio=[TARIFA])))
    import json
    json.dumps(r)          # esto es lo que hace starlette, y no puede lanzar
    assert r["limites"]["peso_max_kg"] in (None, 30.0)


def test_el_cache_expira_solo():
    """El TTL es la red por si alguien agrega una escritura y se olvida de
    invalidar. Sin este test, un TTL que no expira nunca pasa desapercibido."""
    base = db_completa()
    corre(cat.catalogo(db=base))
    base.agencias.filas.append({"transportista_id": "trp_ve1", "codigo": "agc_003",
                                "nombre": "Nueva", "estado": "Lara",
                                "ciudad": "Barquisimeto", "activa": True})
    # Se envejece la entrada en vez de esperar cinco minutos.
    clave, (vence, valor) = "catalogo", cat._cache["catalogo"]
    cat._cache[clave] = (vence - cat.TTL_CATALOGO_S - 1, valor)
    c = corre(cat.catalogo(db=base))
    assert "agc_003" in [a["codigo"] for a in c["transportistas"][0]["agencias"]]


def test_los_indices_se_rinden_por_tiempo_en_vez_de_colgar_el_arranque():
    """Con Mongo inalcanzable, cada create_index espera su propio timeout de
    treinta segundos: veinte índices en serie son diez minutos de arranque
    colgado, healthcheck caído y crash-loop en Railway."""
    class _Lenta(_Db):
        def __getitem__(self, nombre):
            c = super().__getitem__(nombre)
            original = c.create_index

            async def lenta(claves, **opciones):
                await asyncio.sleep(5)
                return await original(claves, **opciones)

            c.create_index = lenta
            return c

    r = corre(idx.ensure_envios_indexes(db=_Lenta(), timeout_s=0.05))
    assert r["timeout"] is True
    assert r["creados"] == 0


def test_el_detalle_de_lo_que_falta_no_sale_por_la_ruta_publica():
    """El diagnóstico interno incluye frases como "la tarifa no tiene divisor
    volumétrico, los bultos grandes cotizarían solo por su peso real": explicarle
    a un anónimo cómo pagar de menos no le sirve a nadie."""
    import importlib.util as _iu
    ruta = os.path.join(_BACKEND, "routes", "envios.py")
    fuente = open(ruta, encoding="utf-8").read()
    assert "_sin_detalle" in fuente

    # La función de saneo, aislada: no hace falta levantar FastAPI para probarla.
    ns = {}
    inicio = fuente.index("_MENSAJE_NO_DISPONIBLE = (")
    fin = fuente.index("@router.get")
    exec(fuente[inicio:fin], ns)
    sin_divisor = {"version_id": "tar_x", "vigente_hasta": None,
                   "vigente_desde": _AYER,
                   "escalones_peso": [{"desde_kg": "0", "hasta_kg": "1", "precio": "45"}],
                   "regla_peso": {"escalon_kg": "0.5"}}
    base = _Db(transportistas=[TRP_BR, TRP_VE], tarifas_envio=[sin_divisor])
    interno = corre(cat.limites(db=base))
    assert any("divisor" in f for f in interno["faltantes"])      # adentro sí
    publico = ns["_sin_detalle"](interno)
    assert not any("divisor" in f for f in publico["faltantes"])  # afuera no
    assert publico["disponible"] is False
    assert len(publico["faltantes"]) == 1


@pytest.mark.parametrize("valor,esperado", [
    (float("inf"), None), (float("-inf"), None), (float("nan"), None),
    ("abc", None), (None, None), (30, 30.0), (Decimal("0.4"), 0.4),
])
def test_el_saneo_para_json_es_la_ultima_barrera(valor, esperado):
    """La intersección ya descarta lo no comparable, pero este saneo es lo último
    antes de que starlette serialice con allow_nan=False — donde un ValueError
    ocurre DESPUÉS de que el handler retornó y ningún try/except lo atrapa."""
    assert cat._json_seguro({"peso_max_kg": valor})["peso_max_kg"] == esperado


def test_una_version_ya_reemplazada_deja_de_regir_en_su_fecha():
    """Al publicar un aumento programado, la versión actual se cierra con la
    fecha FUTURA en que dejará de regir. Si la búsqueda pidiera solo las que
    tienen `vigente_hasta: None`, esa versión quedaría afuera desde el instante
    en que se programa el reemplazo, y el módulo se quedaría sin tarifa un mes
    antes de tiempo."""
    manana = datetime.now(timezone.utc) + timedelta(days=1)
    actual = dict(TARIFA, version_id="tar_actual", vigente_hasta=manana)
    futura = dict(TARIFA, version_id="tar_futura", vigente_desde=manana,
                  vigente_hasta=None)
    base = _Db(tarifas_envio=[actual, futura])

    # Hoy rige la que se está por reemplazar, no la programada.
    assert corre(cat.tarifa_vigente(db=base))["version_id"] == "tar_actual"
    # Y pasado mañana, la otra.
    pasado = datetime.now(timezone.utc) + timedelta(days=2)
    assert corre(cat.tarifa_vigente(db=base, ahora=pasado))["version_id"] == "tar_futura"


def test_sin_ninguna_version_vigente_hoy_no_se_inventa_una():
    ayer = datetime.now(timezone.utc) - timedelta(days=1)
    vencida = dict(TARIFA, version_id="tar_vencida", vigente_hasta=ayer)
    assert corre(cat.tarifa_vigente(db=_Db(tarifas_envio=[vencida]))) is None


# ─── La ventana de vigencia, despues de la revision adversarial ────────────

def test_una_version_anulada_nunca_llega_a_regir():
    """Se programa un aumento, se descubre que estaba mal y se publica la
    corrección. La equivocada queda anulada: existe en el historial, pero no
    cobra ni un envío. Sin este filtro, el precio equivocado empezaba a cobrar
    solo el mes siguiente sin que nadie hubiera publicado nada en el medio."""
    anulada = {**TARIFA, "version_id": "tar_mala", "vigente_desde": _AYER,
               "tarifa_minima": "600", "anulada": True}
    base = _Db(transportistas=[TRP_BR, TRP_VE], tarifas_envio=[TARIFA, anulada])
    assert corre(cat.tarifa_vigente(db=base))["version_id"] == TARIFA["version_id"]


def test_si_la_unica_version_esta_anulada_no_hay_tarifa():
    anulada = {**TARIFA, "anulada": True}
    base = _Db(transportistas=[TRP_BR, TRP_VE], tarifas_envio=[anulada])
    assert corre(cat.tarifa_vigente(db=base)) is None


def test_elegir_la_vigente_no_arrastra_las_tarifas_enteras():
    """`GET /envios/limites` es pública, no pide sesión, no está cacheada y no
    tiene rate limit. Traer doscientas tarifas COMPLETAS —con sus escalones,
    sobrecargos y temporadas— en cada request anónima es una amplificación de
    doscientos a uno contra el único endpoint que cualquiera puede martillar. La
    ventana se decide con las fechas; el documento entero se trae después, y solo
    el que ganó."""
    base = _Db(transportistas=[TRP_BR, TRP_VE], tarifas_envio=[TARIFA])
    proyecciones = []
    original = base.tarifas_envio.find

    def espiar(filtro, proyeccion=None):
        proyecciones.append(proyeccion)
        return original(filtro, proyeccion)
    base.tarifas_envio.find = espiar

    assert corre(cat.tarifa_vigente(db=base))["escalones_peso"] == TARIFA["escalones_peso"]
    assert proyecciones and "escalones_peso" not in (proyecciones[0] or {})
    assert (proyecciones[0] or {}).get("vigente_desde") == 1
