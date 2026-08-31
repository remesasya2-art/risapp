"""
Las rutas de la nomina de retiro, probadas de verdad.

POR QUE ESTE ARCHIVO EXISTE
    Hasta que se escribio, las rutas del panel se verificaban leyendo el texto
    fuente: que digan `get_super_admin`, que llamen a `invalidar_cache`. Eso
    atrapa un olvido, no un comportamiento. Los tres defectos mas caros de este
    PR —la nomina cruda con el CPF de todos saliendo por el GET, la edicion
    parcial que reactivaba a alguien dado de baja, y el alta duplicada— vivian
    los tres en estas funciones y ninguno era visible desde afuera.

COMO SE CARGA
    `routes/envios_admin.py` importa `routes.dependencies`, y `routes/__init__.py`
    arrastra el proyecto entero. Se arma un paquete `routes` vacio y se carga el
    modulo por ruta directa, igual que los tests de servicios hacen con
    `services/__init__.py`.
"""
import asyncio
import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)


class _Resultado:
    def __init__(self, n=1):
        self.matched_count = n
        self.modified_count = n
        self.inserted_id = "x"


def _proyectar(doc, proyeccion):
    if not proyeccion:
        return dict(doc)
    incluir = [k for k, v in proyeccion.items() if v and k != "_id"]
    if incluir:
        return {k: v for k, v in doc.items() if k in incluir}
    excluir = [k for k, v in proyeccion.items() if not v]
    return {k: v for k, v in doc.items() if k not in excluir}


class _Coleccion:
    def __init__(self, filas=None):
        self.filas = filas if filas is not None else []

    def _match(self, d, filtro):
        return all(d.get(k) == v for k, v in filtro.items())

    class _Cursor:
        def __init__(self, filas):
            self.filas = filas

        def sort(self, campo, direccion=1):
            self.filas.sort(key=lambda d: str(d.get(campo, "")), reverse=direccion < 0)
            return self

        async def to_list(self, n):
            return list(self.filas)[:n] if n else list(self.filas)

    def find(self, filtro=None, proyeccion=None):
        return self._Cursor([_proyectar(d, proyeccion)
                             for d in self.filas if self._match(d, filtro or {})])

    async def find_one(self, filtro, proyeccion=None):
        for d in self.filas:
            if self._match(d, filtro):
                return _proyectar(d, proyeccion)
        return None

    async def insert_one(self, doc):
        self.filas.append(dict(doc))
        return _Resultado()

    async def update_one(self, filtro, cambio, upsert=False):
        for d in self.filas:
            if self._match(d, filtro):
                d.update(cambio.get("$set") or {})
                return _Resultado()
        if upsert:
            self.filas.append({**filtro, **(cambio.get("$set") or {})})
        return _Resultado(0)


class _Db:
    def __init__(self, **colecciones):
        self._c = {k: _Coleccion(v) for k, v in colecciones.items()}

    def __getattr__(self, nombre):
        return self._c.setdefault(nombre, _Coleccion([]))


DB = _Db()


def _preparar():
    """El paquete `routes` vacío y las dependencias stubbeadas."""
    if "routes" not in sys.modules:
        paquete = types.ModuleType("routes")
        paquete.__path__ = [os.path.join(_BACKEND, "routes")]
        sys.modules["routes"] = paquete

    from conftest import usar_base
    usar_base(DB)

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
                   "envios_tarifa_editor"):
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
ret = sys.modules["services.envios_retiro"]
from fastapi import HTTPException                                    # noqa: E402
from models.envios_config import Colaborador                         # noqa: E402


def corre(coro):
    return asyncio.run(coro)


AHORA = datetime.now(timezone.utc)


class _Admin:
    user_id = "usr_super"
    email = "super@risappbr.com"


MARIA = {"colaborador_id": "col_aaaa1111", "nombre": "María Gómez",
         "cpf": "111.222.333-44", "telefono": "+55 95 99999-0000",
         "activo": True, "notas": "Autorización firmada el 2026-01-10",
         "autorizado_desde": AHORA - timedelta(days=30), "autorizado_hasta": None,
         "creado_at": AHORA - timedelta(days=30), "creado_por": "usr_super"}

PUNTO = {"setting_id": "envios_punto_origen",
         "nombre": "AC Pacaraima", "cep": "69355000", "ciudad": "Pacaraima", "uf": "RR",
         "modalidad": "caixa_postal", "caixa_postal": "123", "direccion": None,
         "razon_social": "RIS App LTDA",
         "plantilla_direccion": ret.PLANTILLA_POR_DEFECTO,
         "retirador_activo_id": "col_aaaa1111"}


@pytest.fixture(autouse=True)
def base_limpia():
    from conftest import usar_base
    usar_base(DB)
    DB._c.clear()
    DB._c["colaboradores_retiro"] = _Coleccion([dict(MARIA)])
    DB._c["app_settings"] = _Coleccion([dict(PUNTO)])
    DB._c["centro_gestion_log"] = _Coleccion([])
    yield


# ─── 1. Los datos personales no salen ─────────────────────────────────────

def test_el_listado_no_le_da_el_cpf_de_la_nomina_al_operador():
    """EL DEFECTO P0. `get_crm_user` admite `agent`, `admin` y `super_admin`. El
    operador necesita saber a qué nombre están rotulados los paquetes para saber
    cuáles puede reclamar; no necesita el documento de sus compañeros. Es la
    misma decisión que `listar_transportistas`, que también recorta."""
    r = corre(ra.ver_retiro(admin=_Admin()))
    assert r["nomina"][0]["nombre"] == "María Gómez"
    assert "cpf" not in r["nomina"][0]
    assert "telefono" not in r["nomina"][0]
    assert MARIA["cpf"] not in repr(r)


def test_la_nomina_se_pide_sin_los_campos_personales():
    """La primera de las dos capas. Se comprueba aparte de la otra a propósito:
    con las dos puestas, sacar cualquiera de las dos deja la respuesta igual de
    limpia, así que un test sobre la salida no distingue una capa de dos. El día
    que alguien toque una, la otra sostiene y este test avisa."""
    proyecciones = []
    original = DB.colaboradores_retiro.find

    def espiar(filtro=None, proyeccion=None):
        proyecciones.append(proyeccion)
        return original(filtro, proyeccion)
    DB.colaboradores_retiro.find = espiar

    corre(ra.ver_retiro(admin=_Admin()))
    assert proyecciones and proyecciones[0].get("cpf") == 0
    assert proyecciones[0].get("telefono") == 0


def test_el_filtro_de_datos_personales_saca_las_dos_claves():
    """La segunda capa, probada sola contra un documento que sí las trae."""
    limpio = ra._sin_datos_personales(dict(MARIA))
    assert "cpf" not in limpio and "telefono" not in limpio
    assert limpio["nombre"] == "María Gómez"
    assert limpio["colaborador_id"] == "col_aaaa1111"


def test_si_la_proyeccion_dejara_de_recortar_el_filtro_sostiene():
    """Lo que hace que las dos capas sean dos y no una escrita dos veces. Se
    simula el día en que alguien toque la proyección —o el driver la ignore— y se
    verifica que la respuesta siga sin el CPF."""
    DB.colaboradores_retiro.find = lambda filtro=None, proyeccion=None: \
        _Coleccion._Cursor([dict(d) for d in DB.colaboradores_retiro.filas])

    r = corre(ra.ver_retiro(admin=_Admin()))
    assert "cpf" not in r["nomina"][0]
    assert MARIA["cpf"] not in repr(r)


def test_el_listado_no_baja_el_bloque_de_configuracion_crudo():
    """`GET /config/{bloque}` lo sirve y pide super_admin. El mismo documento con
    dos niveles de autorización según por dónde se pida es la clase de
    inconsistencia que después se cita como precedente."""
    r = corre(ra.ver_retiro(admin=_Admin()))
    assert "punto_origen" not in r
    assert r["vista_previa"]["destinatario"] == "RIS App LTDA - A/C María Gómez"


def test_el_cpf_no_llega_al_log_de_auditoria():
    """`centro_gestion_log` no es un log interno: se sirve entero a un sistema
    externo. Un CPF que entre ahí sale de la aplicación."""
    ficha = Colaborador(nombre="José Ferreira", cpf="555.666.777-88",
                        telefono="+55 95 98888-0000")
    corre(ra.crear_colaborador(ficha, admin=_Admin()))
    plano = repr(DB.centro_gestion_log.filas)
    assert "555.666.777-88" not in plano
    assert "98888" not in plano


# ─── 2. Editar es fusionar, no reemplazar ─────────────────────────────────

def test_editar_sin_mandar_el_cpf_no_lo_borra():
    """El panel no muestra el CPF —por la misma razón de privacidad que motiva
    todo esto— así que no lo reenvía. Un reemplazo total lo borraba en silencio."""
    corre(ra.editar_colaborador("col_aaaa1111",
                                Colaborador.model_construct(nombre="María Gomes"),
                                admin=_Admin()))
    guardado = DB.colaboradores_retiro.filas[0]
    assert guardado["nombre"] == "María Gomes"
    assert guardado["cpf"] == "111.222.333-44"


def test_editar_a_alguien_dado_de_baja_no_lo_reactiva():
    """`activo` tiene default True: editarle el teléfono a alguien dado de baja
    lo reactivaba, y su nombre volvía a salir rotulado en cajas que ya no está
    autorizado a retirar."""
    DB.colaboradores_retiro.filas[0]["activo"] = False
    corre(ra.editar_colaborador("col_aaaa1111",
                                Colaborador.model_construct(telefono="+55 95 90000-1111"),
                                admin=_Admin()))
    assert DB.colaboradores_retiro.filas[0]["activo"] is False


def test_editar_no_borra_la_fecha_de_vencimiento():
    """Si mañana lo reactivan, una autorización que estaba vencida habría quedado
    convertida en ilimitada."""
    vence = AHORA + timedelta(days=10)
    DB.colaboradores_retiro.filas[0]["autorizado_hasta"] = vence
    corre(ra.editar_colaborador("col_aaaa1111",
                                Colaborador.model_construct(notas="al día"),
                                admin=_Admin()))
    assert DB.colaboradores_retiro.filas[0]["autorizado_hasta"] == vence


def test_editar_conserva_la_identidad_y_el_alta():
    corre(ra.editar_colaborador("col_aaaa1111",
                                Colaborador.model_construct(nombre="María Gómez"),
                                admin=_Admin()))
    guardado = DB.colaboradores_retiro.filas[0]
    assert guardado["colaborador_id"] == "col_aaaa1111"
    assert guardado["creado_por"] == "usr_super"


def test_la_auditoria_de_una_edicion_no_inventa_bajas():
    """El log decía que la ficha perdía su identificador y su autor, cuando en la
    base seguían intactos — y es justo lo que la auditoría existe para contestar."""
    corre(ra.editar_colaborador("col_aaaa1111",
                                Colaborador.model_construct(nombre="María Gomes"),
                                admin=_Admin()))
    cambios = DB.centro_gestion_log.filas[-1]
    plano = repr(cambios)
    for metadato in ("colaborador_id", "creado_at", "creado_por"):
        assert metadato not in plano


def test_editar_a_alguien_que_no_esta_en_la_nomina_es_404():
    with pytest.raises(HTTPException) as e:
        corre(ra.editar_colaborador("col_no_existe",
                                    Colaborador.model_construct(nombre="Nadie Nadie"),
                                    admin=_Admin()))
    assert e.value.status_code == 404


# ─── 3. Alta ──────────────────────────────────────────────────────────────

def test_no_se_puede_dar_de_alta_dos_veces_a_la_misma_persona():
    """Se da de baja la ficha que se ve seleccionada, la otra queda vigente, y
    meses después sale rotulada como suplente: el mostrador recibe una caja a
    nombre de alguien que la nómina ya dio de baja."""
    otra_vez = Colaborador(nombre="María Gómez", cpf="111.222.333-44")
    with pytest.raises(HTTPException) as e:
        corre(ra.crear_colaborador(otra_vez, admin=_Admin()))
    assert e.value.status_code == 409
    assert len(DB.colaboradores_retiro.filas) == 1


def test_el_alta_estampa_identidad_y_autor():
    r = corre(ra.crear_colaborador(Colaborador(nombre="José Ferreira"), admin=_Admin()))
    assert r["valor"]["colaborador_id"].startswith("col_")
    assert r["valor"]["creado_por"] == "usr_super"


def test_un_nombre_sin_apellido_no_entra_en_la_nomina():
    """Es el nombre que va rotulado en la caja y el que el mostrador compara
    contra el documento."""
    with pytest.raises(Exception):
        Colaborador(nombre="María")


# ─── 4. Designar de turno ─────────────────────────────────────────────────

def test_designar_a_alguien_no_vigente_se_rechaza():
    DB.colaboradores_retiro.filas[0]["activo"] = False
    with pytest.raises(HTTPException) as e:
        corre(ra.designar_retirador(ra.Designacion(colaborador_id="col_aaaa1111"),
                                    admin=_Admin()))
    assert e.value.status_code == 400


def test_designar_devuelve_la_vista_previa_ya_renderizada():
    """Una plantilla se edita a ciegas si no se ve el resultado, y una dirección
    mal armada no se descubre en el panel: se descubre cuando una caja llega a
    una agencia que no la esperaba."""
    r = corre(ra.designar_retirador(ra.Designacion(colaborador_id="col_aaaa1111"),
                                    admin=_Admin()))
    assert r["de_turno"] == "María Gómez"
    assert r["vista_previa"]["texto_copiable"].startswith("RIS App LTDA\nA/C María Gómez")


def test_una_clave_desconocida_en_el_bloque_guardado_no_bloquea_designar():
    """Quedarse con "todo menos tres claves" dejaba pasar cualquier otra que
    existiera en el documento, y como el esquema es `extra="forbid"`, designar a
    alguien pasaba a devolver 400 para siempre sin ninguna pista."""
    DB.app_settings.filas[0]["telefono_agencia"] = "+55 95 3000-0000"
    r = corre(ra.designar_retirador(ra.Designacion(colaborador_id="col_aaaa1111"),
                                    admin=_Admin()))
    assert r["de_turno"] == "María Gómez"


def test_un_corte_de_base_no_manda_a_recargar_el_punto_de_origen():
    """Mandar a "cargá primero el punto de origen" durante un corte hace que
    alguien lo recargue de memoria y pise la plantilla y la Caixa Postal
    reales."""
    async def revienta(*a, **k):
        raise RuntimeError("timeout")
    DB.app_settings.find_one = revienta

    with pytest.raises(HTTPException) as e:
        corre(ra.designar_retirador(ra.Designacion(colaborador_id="col_aaaa1111"),
                                    admin=_Admin()))
    assert e.value.status_code == 503
    assert "no lo vuelvas a cargar" in e.value.detail


# ─── 5. La plantilla se valida cuando hay alguien mirando ─────────────────

@pytest.mark.parametrize("plantilla", [
    "{Razon_Social}\n{ciudad}",           # mayúscula: no matchea, queda literal
    "{ retirador_nombre }\n{ciudad}",     # espacios: tampoco, y esquiva la limpieza
    "{razon_social}\n{telefono}",         # dato que no existe
])
def test_una_plantilla_con_un_token_que_no_existe_se_rechaza_al_guardar(plantilla):
    """Guardar es el único momento en que hay alguien mirando. Después ese texto
    es el que el usuario copia y pega sobre la caja."""
    from services import envios_config as cfg
    bloque = {k: v for k, v in PUNTO.items() if k != "setting_id"}
    _, errores = cfg.validar("punto_origen", {**bloque, "plantilla_direccion": plantilla})
    assert errores and any("no existen" in e for e in errores)


def test_la_plantilla_valida_se_guarda_sin_ruido():
    from services import envios_config as cfg
    validado, errores = cfg.validar("punto_origen", {k: v for k, v in PUNTO.items()
                                                     if k != "setting_id"})
    assert errores == []
    assert validado["retirador_activo_id"] == "col_aaaa1111"
