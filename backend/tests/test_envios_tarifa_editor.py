"""
La consola de precios: borrador, simulador y publicacion.

CONTEXTO
    Es la pantalla mas importante del panel porque define el unico ingreso del
    modulo. Y es la mas peligrosa: publicar una tabla con un hueco, o un margen
    tipeado como 20 en vez de 0.20, cobra mal TODOS los envios hasta que alguien
    mire una factura.

QUE SE CUBRE
    1. Borrador y version son cosas distintas: el borrador se pisa, la version
       jamas se modifica.
    2. Copy-forward: si no hay borrador, se arranca copiando la vigente, sin sus
       campos de identidad. El que sube un precio no vuelve a tipear todo.
    3. El simulador usa la MISMA funcion que la cotizacion. Un simulador que
       miente es peor que no tener simulador, porque da confianza para publicar.
    4. La comparacion contra la vigente, con la variacion en porcentaje: es lo
       que evita publicar un 40 % creyendo que es un 4 %.
    5. Publicar valida, exige nota, cierra la anterior y consume el borrador.
    6. Una tabla con huecos, solapada, no monotona o con porcentajes mal escritos
       NO se puede publicar.

Los modulos se cargan por ruta directa para no arrastrar services/__init__.py.
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


_cargar("money")
tarifas = _cargar("envios_tarifas")
_cargar("envios_policy")
_cargar("referencias")
_cargar("envios_catalogo")
ed = _cargar("envios_tarifa_editor")
from models.envios_tarifa import (TarifaEnvio, TarifaBorrador,  # noqa: E402
                                  CajaDePrueba)


def corre(coro):
    return asyncio.run(coro)


def _proyectar(doc, proyeccion):
    """El doble respeta las proyecciones. No es adorno: un fake que las ignora
    escondio en PR D un endpoint que devolvia todos los limites en null."""
    if not proyeccion:
        return dict(doc)
    incluir = [k for k, v in proyeccion.items() if v and k != "_id"]
    if incluir:
        return {k: v for k, v in doc.items() if k in incluir}
    excluir = [k for k, v in proyeccion.items() if not v]
    return {k: v for k, v in doc.items() if k not in excluir}


class _Resultado:
    def __init__(self, n):
        self.deleted_count = n
        self.modified_count = n


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

    def find(self, filtro, proyeccion=None):
        return self._Cursor([_proyectar(d, proyeccion)
                             for d in self.filas if self._match(d, filtro)])

    async def find_one(self, filtro, proyeccion=None, sort=None):
        c = [d for d in self.filas if self._match(d, filtro)]
        if sort:
            campo, direccion = sort[0]
            c.sort(key=lambda d: str(d.get(campo, "")), reverse=direccion < 0)
        return _proyectar(c[0], proyeccion) if c else None

    async def update_one(self, filtro, cambio, upsert=False):
        for d in self.filas:
            if self._match(d, filtro):
                d.update(cambio["$set"])
                return _Resultado(1)
        if upsert:
            self.filas.append({**filtro, **cambio["$set"]})
        return _Resultado(0)

    async def update_many(self, filtro, cambio):
        n = 0
        for d in self.filas:
            if self._match(d, filtro):
                d.update(cambio["$set"])
                n += 1
        return _Resultado(n)

    async def replace_one(self, filtro, doc, upsert=False):
        for i, d in enumerate(self.filas):
            if self._match(d, filtro):
                self.filas[i] = dict(doc)     # REEMPLAZA: nada del anterior sobrevive
                return _Resultado(1)
        if upsert:
            self.filas.append(dict(doc))
        return _Resultado(0)

    async def insert_one(self, doc):
        self.filas.append(doc)

    async def delete_one(self, filtro):
        quedan = [d for d in self.filas if not self._match(d, filtro)]
        borradas = len(self.filas) - len(quedan)
        self.filas[:] = quedan
        return _Resultado(min(borradas, 1))


class _Db:
    def __init__(self):
        self._c = {}

    def __getattr__(self, nombre):
        return self._c.setdefault(nombre, _Coleccion())


class _Admin:
    user_id = "usr_admin"
    email = "admin@risappbr.com"


_AYER = datetime.now(timezone.utc) - timedelta(days=1)

TARIFA = {
    "modo_tarifa": "peso", "moneda": "RIS",
    "regla_peso": {"divisor": 5000, "escalon_kg": "0.5", "minimo_kg": "1.0",
                   "umbral_cubado_kg": None},
    "escalones_peso": [
        {"desde_kg": "0.00", "hasta_kg": "1.00", "precio": "45.00"},
        {"desde_kg": "1.01", "hasta_kg": "3.00", "precio": "78.00"},
        {"desde_kg": "3.01", "hasta_kg": "5.00", "precio": "110.00"},
        {"desde_kg": "5.01", "hasta_kg": "10.00", "precio": "185.00"},
    ],
    "adicional_por_kg": "17.50",
    "tarifa_minima": "45.00",
    "margen": {"tipo": "porcentual", "valor": "0.20"},
    "sobrecargos": [], "descuentos_cantidad": [], "recargos_temporada": [],
    "redondeo_final": {"decimales": 2, "multiplo": None},
    "limites_propios": {}, "escalones_volumen": [], "prohibidos": [],
}

CAJA = {"peso_kg": "4", "largo_cm": "40", "ancho_cm": "30", "alto_cm": "20",
        "valor_declarado": "0", "bultos": 1}


def db_con_vigente():
    base = _Db()
    base.tarifas_envio.filas.append({
        **TARIFA, "version_id": "tar_vieja", "vigente_desde": _AYER,
        "vigente_hasta": None, "nota": "la primera", "creada_at": _AYER})
    return base


# ─── 1. Borrador ──────────────────────────────────────────────────────────

def test_sin_borrador_ni_vigente_se_arranca_vacio():
    borrador, origen = corre(ed.borrador_o_copia(db=_Db()))
    assert borrador == {} and origen == "vacio"


def test_sin_borrador_se_copia_la_vigente_sin_su_identidad():
    """Copy-forward: el que entra a subir un precio no tiene que volver a tipear
    los sobrecargos, los descuentos ni los límites. Pero la copia NO se lleva el
    version_id ni las fechas: eso la volvería la misma versión, editada."""
    borrador, origen = corre(ed.borrador_o_copia(db=db_con_vigente()))
    assert origen == "copia_de_vigente"
    assert borrador["escalones_peso"] == TARIFA["escalones_peso"]
    for identidad in ("version_id", "vigente_desde", "vigente_hasta", "nota", "creada_at"):
        assert identidad not in borrador


def test_el_borrador_se_pisa_y_no_afecta_a_nadie():
    base = db_con_vigente()
    # La primera escritura trae una clave que la segunda NO tiene: con un $set
    # sobrevive, y como publicar congela el documento entero, esa basura entra a
    # una versión inmutable. Las dos escrituras del test viejo tenían el mismo
    # juego de claves, así que no podían detectarlo.
    corre(ed.guardar_borrador({**TARIFA, "tarifa_minima": "60.00",
                               "sobrecargos": [{"codigo": "seguro"}]}, _Admin(), db=base))
    corre(ed.guardar_borrador({**TARIFA, "tarifa_minima": "70.00"}, _Admin(), db=base))
    assert corre(ed.leer_borrador(db=base)).get("sobrecargos") == []
    borrador, origen = corre(ed.borrador_o_copia(db=base))
    assert origen == "borrador" and borrador["tarifa_minima"] == "70.00"
    # La vigente no se movió.
    assert corre(ed.vigente(db=base))["tarifa_minima"] == "45.00"


def test_el_borrador_se_guarda_aunque_este_a_medio_cargar():
    """Validar acá sería impedirle a alguien guardar una tabla incompleta y
    volver mañana. Lo que se valida es publicar.

    Pasa por TarifaBorrador, que es el modelo que usa la ruta: probar solo el
    servicio dejaba verde un comportamiento que la API no tenía. La ruta pedía
    TarifaEnvio, que exige la tabla completa, así que guardar una tabla a medio
    cargar era un 422 — el escenario exacto que este test dice cubrir.
    """
    base = _Db()
    medio = TarifaBorrador(escalones_peso=[]).como_borrador()
    corre(ed.guardar_borrador(medio, _Admin(), db=base))
    assert corre(ed.leer_borrador(db=base))["escalones_peso"] == []
    assert corre(ed.leer_borrador(db=base))["adicional_por_kg"] is None


# ─── 2. El simulador ──────────────────────────────────────────────────────

def test_el_simulador_usa_la_misma_funcion_que_la_cotizacion():
    """No una parecida: la misma. Un simulador que miente es peor que no tener
    simulador, porque da confianza para publicar."""
    del_editor = ed.simular(TARIFA, CAJA)
    de_la_cotizacion = tarifas.cotizar_servicio(
        TARIFA, CAJA["peso_kg"], CAJA["largo_cm"], CAJA["ancho_cm"], CAJA["alto_cm"],
        valor_declarado="0", bultos=1)
    assert del_editor == de_la_cotizacion
    assert del_editor["total"] == Decimal("132.00")


def test_el_simulador_no_lanza_con_una_tarifa_rota():
    """Es una pantalla, no un cobro: mostrar el error es útil, reventar no.

    La entrada tiene que ser una que REALMENTE lance. Una tabla vacía cotiza 0
    por el camino feliz, así que el test viejo —que además aceptaba None o 0,
    o sea las dos ramas— pasaba con el try/except borrado.
    """
    rota = {**TARIFA, "redondeo_final": {"decimales": 2, "multiplo": "1E-30"}}
    with pytest.raises(Exception):
        tarifas.cotizar_servicio(rota, CAJA["peso_kg"], CAJA["largo_cm"],
                                 CAJA["ancho_cm"], CAJA["alto_cm"])
    r = ed.simular(rota, CAJA)
    assert r["total"] is None and r["error"]


def test_la_comparacion_muestra_la_variacion_en_porcentaje():
    """Es lo que evita publicar un aumento del 40 % creyendo que era del 4 %."""
    caro = {**TARIFA, "escalones_peso": [
        {**e, "precio": str(Decimal(e["precio"]) * Decimal("1.4"))}
        for e in TARIFA["escalones_peso"]]}
    filas = ed.comparar(caro, TARIFA, [CAJA])
    assert Decimal(filas[0]["variacion_pct"]) == Decimal("40.00")


def test_la_comparacion_muestra_el_cero_en_vez_de_esconderlo():
    """Que el número esté y sea cero es información; que no esté, no."""
    filas = ed.comparar(TARIFA, TARIFA, [CAJA])
    assert filas[0]["variacion_pct"] == "0.00"


def test_sin_vigente_la_comparacion_no_inventa_una_variacion():
    filas = ed.comparar(TARIFA, None, [CAJA])
    assert filas[0]["variacion_pct"] is None
    assert filas[0]["nuevo"]["total"] == Decimal("132.00")


def test_las_cajas_guardadas_se_recotizan_todas():
    cajas = [CAJA, {**CAJA, "peso_kg": "0.5"}, {**CAJA, "peso_kg": "12"}]
    filas = ed.comparar(TARIFA, TARIFA, cajas)
    assert len(filas) == 3
    assert [f["nuevo"]["total"] for f in filas] == [
        Decimal("132.00"), Decimal("132.00"), Decimal("264.00")]


# ─── 3. Publicar ──────────────────────────────────────────────────────────

def test_publicar_crea_una_version_y_cierra_la_anterior():
    base = db_con_vigente()
    version, errores = corre(ed.publicar(dict(TARIFA), "Aumento de combustible",
                                         _Admin(), db=base))
    assert errores == []
    assert version["version_id"].startswith("tar_")
    assert version["nota"] == "Aumento de combustible"

    abiertas = [t for t in base.tarifas_envio.filas if t["vigente_hasta"] is None]
    assert len(abiertas) == 1 and abiertas[0]["version_id"] == version["version_id"]


def test_publicar_no_modifica_la_version_anterior_mas_que_para_cerrarla():
    """Regla de oro: una versión nunca se modifica. Los envíos en vuelo siguen
    apuntando a la suya."""
    base = db_con_vigente()
    antes = dict(base.tarifas_envio.filas[0])
    corre(ed.publicar(dict(TARIFA), "otra", _Admin(), db=base))
    despues = base.tarifas_envio.filas[0]
    assert despues["version_id"] == antes["version_id"]
    assert despues["escalones_peso"] == antes["escalones_peso"]
    assert despues["vigente_hasta"] is not None      # lo único que cambió


def test_publicar_exige_la_nota():
    """Es lo que alguien va a leer dentro de seis meses para entender por qué un
    envío de marzo costó lo que costó."""
    for vacia in ("", "   ", None):
        _, errores = corre(ed.publicar(dict(TARIFA), vacia, _Admin(), db=_Db()))
        assert any("nota" in e for e in errores)


def test_publicar_consume_el_borrador():
    """Dejarlo vivo hace que el próximo que entre crea que tiene cambios sin
    publicar cuando ya los publicó."""
    base = db_con_vigente()
    corre(ed.guardar_borrador(dict(TARIFA), _Admin(), db=base))
    corre(ed.publicar(dict(TARIFA), "va", _Admin(), db=base))
    assert corre(ed.leer_borrador(db=base)) is None


def test_una_version_no_puede_empezar_a_regir_en_el_pasado():
    ayer = datetime.now(timezone.utc) - timedelta(days=2)
    _, errores = corre(ed.publicar(dict(TARIFA), "retroactiva", _Admin(),
                                   db=_Db(), vigente_desde=ayer))
    assert any("pasado" in e for e in errores)


def test_se_puede_programar_un_aumento_para_mas_adelante():
    """Y hasta que llegue esa fecha, la vigente sigue siendo la vieja."""
    base = db_con_vigente()
    dentro_de_un_mes = datetime.now(timezone.utc) + timedelta(days=30)
    version, errores = corre(ed.publicar(dict(TARIFA), "aumento programado", _Admin(),
                                         db=base, vigente_desde=dentro_de_un_mes))
    assert errores == []
    assert corre(ed.vigente(db=base))["version_id"] == "tar_vieja"


# ─── 4. Lo que bloquea publicar ───────────────────────────────────────────

def test_una_tabla_con_un_hueco_no_se_publica():
    """Un paquete que cae en el hueco no tiene precio y la cotización devuelve
    cualquier cosa."""
    con_hueco = {**TARIFA, "escalones_peso": [
        {"desde_kg": "0.00", "hasta_kg": "3.00", "precio": "78.00"},
        {"desde_kg": "3.50", "hasta_kg": "5.00", "precio": "110.00"}]}
    _, errores = corre(ed.publicar(con_hueco, "va", _Admin(), db=_Db()))
    assert any("hueco" in e for e in errores)


def test_una_tabla_no_monotona_no_se_publica():
    """Si el escalón de 5 kg sale más barato que el de 3, alguien va a declarar
    de más para pagar menos."""
    invertida = {**TARIFA, "escalones_peso": [
        {"desde_kg": "0.00", "hasta_kg": "3.00", "precio": "110.00"},
        {"desde_kg": "3.01", "hasta_kg": "5.00", "precio": "78.00"}]}
    _, errores = corre(ed.publicar(invertida, "va", _Admin(), db=_Db()))
    assert any("más barato" in e for e in errores)


def test_un_margen_escrito_como_entero_no_se_publica():
    """20 en vez de 0.20 multiplica el precio por veintiuno."""
    mala = {**TARIFA, "margen": {"tipo": "porcentual", "valor": "20"}}
    _, errores = corre(ed.publicar(mala, "va", _Admin(), db=_Db()))
    assert any("fracción" in e for e in errores)


def test_una_publicacion_rechazada_no_toca_nada():
    base = db_con_vigente()
    con_hueco = {**TARIFA, "escalones_peso": [
        {"desde_kg": "0.00", "hasta_kg": "3.00", "precio": "78.00"},
        {"desde_kg": "3.50", "hasta_kg": "5.00", "precio": "110.00"}]}
    corre(ed.publicar(con_hueco, "va", _Admin(), db=base))
    assert len(base.tarifas_envio.filas) == 1
    assert base.tarifas_envio.filas[0]["vigente_hasta"] is None


# ─── 5. El esquema del editor ─────────────────────────────────────────────

def test_el_esquema_no_acepta_una_zona():
    """El servicio termina siempre en el mismo mostrador: su precio es una
    función de una sola variable. Si este modelo pide una zona, algo se rompió en
    el negocio antes que en el código."""
    with pytest.raises(Exception):
        TarifaEnvio(regla_peso={"divisor": 5000}, adicional_por_kg="17.50",
                    escalones_peso=[{"desde_kg": "0", "hasta_kg": "1", "precio": "45"}],
                    zona_destino="zona_a")


def test_el_esquema_rechaza_la_coma_decimal_en_un_precio():
    with pytest.raises(Exception):
        TarifaEnvio(regla_peso={"divisor": 5000}, adicional_por_kg="17,50",
                    escalones_peso=[{"desde_kg": "0", "hasta_kg": "1", "precio": "45"}])


def test_el_esquema_exige_al_menos_un_escalon():
    with pytest.raises(Exception):
        TarifaEnvio(regla_peso={"divisor": 5000}, adicional_por_kg="17.50",
                    escalones_peso=[])


def test_una_caja_de_prueba_no_puede_pesar_cero():
    with pytest.raises(Exception):
        CajaDePrueba(peso_kg="0", largo_cm="10", ancho_cm="10", alto_cm="10")


# ─── 5. Lo que encontro la revision adversarial ───────────────────────────
#
# Cada test de aca abajo nacio de un defecto concreto que la suite anterior
# dejaba pasar en verde. El comentario dice cual, porque dentro de un ano el
# valor del test es entender por que existe.

def test_una_fecha_sin_zona_horaria_no_revienta_al_publicar():
    """Un <input type="datetime-local"> manda "2026-10-01T00:00:00", sin Z y sin
    offset. Pydantic lo parsea naive, y compararlo contra un aware era un
    TypeError sin capturar: un 500 en el botón de programar un aumento."""
    base = db_con_vigente()
    naive = (datetime.now(timezone.utc) + timedelta(days=30)).replace(tzinfo=None)
    version, errores = corre(ed.publicar(dict(TARIFA), "aumento de octubre", _Admin(),
                                         db=base, vigente_desde=naive))
    assert errores == []
    assert version["vigente_desde"].tzinfo is not None


def test_se_le_perdona_al_cliente_el_reloj_corrido():
    """El formulario manda la hora que ve el navegador. Entre el skew y la
    latencia llega unos segundos en el pasado, y rechazarlo es un 400 que nadie
    entiende. Un aumento fechado ayer sí se rechaza: eso no es reloj corrido."""
    base = db_con_vigente()
    _, errores = corre(ed.publicar(dict(TARIFA), "ahora", _Admin(), db=base,
                                   vigente_desde=datetime.now(timezone.utc)
                                   - timedelta(seconds=5)))
    assert errores == []

    _, errores = corre(ed.publicar(dict(TARIFA), "ayer", _Admin(), db=base,
                                   vigente_desde=_AYER))
    assert errores and "pasado" in errores[0]


def test_el_simulador_ve_los_recargos_de_temporada():
    """El defecto más caro de todos: sin fecha, `multiplicador_temporada`
    devuelve 1 y la pantalla que existe para no publicar un 40 % creyendo que es
    un 4 % mostraba 0 % para un aumento del 50 %."""
    navidad = {**TARIFA, "recargos_temporada": [
        {"nombre": "temporada alta", "desde": "2026-12-01", "hasta": "2026-12-31",
         "multiplicador": "1.5", "activo": True}]}
    en_diciembre = ed.comparar(navidad, TARIFA, [CAJA], fecha="2026-12-10")
    assert Decimal(en_diciembre[0]["variacion_pct"]) == Decimal("50.00")

    en_marzo = ed.comparar(navidad, TARIFA, [CAJA], fecha="2026-03-10")
    assert Decimal(en_marzo[0]["variacion_pct"]) == Decimal("0.00")


def test_no_se_publica_lo_que_hay_en_mongo_sin_volver_a_validarlo():
    """Publicar toma el borrador CRUDO de la base, y de la base puede venir
    cualquier cosa: un "NaN" que escribió una versión vieja, un número en
    notación científica. Sin re-validar el esquema, `validar_tarifa` levantaba
    InvalidOperation al comparar y la ruta devolvía un 500."""
    base = db_con_vigente()
    base.app_settings.filas.append({"setting_id": ed.SETTING_BORRADOR,
                                    **TARIFA, "tarifa_minima": "NaN"})
    borrador, origen = corre(ed.borrador_o_copia(db=base))
    assert origen == "borrador"
    version, errores = corre(ed.publicar(borrador, "lo que sea", _Admin(), db=base))
    assert version is None
    assert any("tarifa_minima" in e for e in errores)


def test_un_multiplo_de_redondeo_absurdo_no_llega_a_cobrar():
    """1E-30 es finito y está entre 0 y 10000, así que pasaba el modelo y
    `validar_tarifa`. Después hacía estallar CADA cotización con InvalidOperation,
    ya publicada."""
    base = db_con_vigente()
    rota = {**TARIFA, "redondeo_final": {"decimales": 2, "multiplo": "1E-30"}}
    version, errores = corre(ed.publicar(rota, "redondeo", _Admin(), db=base))
    assert version is None and errores


def test_una_correccion_reemplaza_al_aumento_programado_en_vez_de_encolarse():
    """EL DEFECTO P0. Se programa un aumento para dentro de un mes, se descubre
    que estaba mal y se publica la corrección. Cerrando "las que no tienen
    vigente_hasta", la programada equivocada seguía viva: el precio equivocado
    empezaba a cobrar solo el mes siguiente, sin que nadie hubiera publicado
    nada en el medio."""
    base = db_con_vigente()
    dentro_de_un_mes = datetime.now(timezone.utc) + timedelta(days=30)
    mala, _ = corre(ed.publicar({**TARIFA, "tarifa_minima": "600.00"},
                                "aumento mal tipeado", _Admin(), db=base,
                                vigente_desde=dentro_de_un_mes))
    buena, errores = corre(ed.publicar({**TARIFA, "tarifa_minima": "60.00"},
                                       "corrección del aumento", _Admin(), db=base,
                                       vigente_desde=dentro_de_un_mes))
    assert errores == []

    anulada = [t for t in base.tarifas_envio.filas
               if t["version_id"] == mala["version_id"]][0]
    assert anulada["anulada"] is True

    en_dos_meses = datetime.now(timezone.utc) + timedelta(days=60)
    rige = corre(ed.vigente(db=base, ahora=en_dos_meses))
    assert rige["version_id"] == buena["version_id"]
    assert rige["tarifa_minima"] == "60.00"


def test_nunca_hay_dos_versiones_rigiendo_al_mismo_tiempo():
    """Con un aumento programado en el medio, publicar algo urgente dejaba la
    vieja abierta hasta la fecha de la programada: dos documentos cumplían la
    condición de vigencia a la vez."""
    base = db_con_vigente()
    corre(ed.publicar({**TARIFA, "tarifa_minima": "600.00"}, "programado",
                      _Admin(), db=base,
                      vigente_desde=datetime.now(timezone.utc) + timedelta(days=30)))
    urgente, _ = corre(ed.publicar({**TARIFA, "tarifa_minima": "48.00"},
                                   "corrección urgente", _Admin(), db=base))

    for dias in (0, 1, 15, 31, 45, 90):
        momento = datetime.now(timezone.utc) + timedelta(days=dias, seconds=1)
        vigentes = [t for t in base.tarifas_envio.filas
                    if not t.get("anulada")
                    and ed._aware(t["vigente_desde"]) <= momento
                    and (t["vigente_hasta"] is None
                         or ed._aware(t["vigente_hasta"]) > momento)]
        assert len(vigentes) == 1, f"a los {dias} días rigen {len(vigentes)}"
        assert vigentes[0]["version_id"] == urgente["version_id"]


def test_ninguna_version_queda_con_la_ventana_al_reves():
    base = db_con_vigente()
    corre(ed.publicar({**TARIFA, "tarifa_minima": "600.00"}, "programado", _Admin(),
                      db=base, vigente_desde=datetime.now(timezone.utc) + timedelta(days=30)))
    corre(ed.publicar({**TARIFA, "tarifa_minima": "48.00"}, "urgente", _Admin(), db=base))
    for t in base.tarifas_envio.filas:
        if t.get("vigente_hasta") is not None:
            assert ed._aware(t["vigente_hasta"]) > ed._aware(t["vigente_desde"]), t


def test_si_falla_cerrar_la_anterior_el_modulo_no_se_queda_sin_tarifa():
    """Se inserta primero y se cierra después. Al revés, un fallo del insert
    dejaba la vigente ya cerrada y CERO versiones rigiendo: todos los usuarios
    veían "el servicio no está disponible", y no hay ninguna ruta que reabra una
    versión desde el panel."""
    base = db_con_vigente()

    async def revienta(*a, **k):
        raise RuntimeError("failover de mongo")
    base.tarifas_envio.update_one = revienta

    version, errores = corre(ed.publicar({**TARIFA, "tarifa_minima": "70.00"},
                                         "aumento", _Admin(), db=base))
    assert errores == []
    assert corre(ed.vigente(db=base))["version_id"] == version["version_id"]


def test_un_doble_clic_en_publicar_no_crea_dos_versiones():
    base = db_con_vigente()
    corre(ed.guardar_borrador({**TARIFA, "tarifa_minima": "70.00"}, _Admin(), db=base))
    borrador = corre(ed.leer_borrador(db=base))
    marca = borrador["actualizado_at"]

    primera, e1 = corre(ed.publicar(dict(borrador), "aumento", _Admin(), db=base,
                                    marca_borrador=marca))
    segunda, e2 = corre(ed.publicar(dict(borrador), "aumento", _Admin(), db=base,
                                    marca_borrador=marca))
    assert primera is not None and e1 == []
    assert segunda is None and "cambió mientras publicabas" in e2[0]
    assert len(base.tarifas_envio.filas) == 2       # la vieja y una sola nueva


def test_publicar_una_tarifa_explicita_no_se_lleva_el_borrador_de_otro():
    """El delete_one era incondicional: alguien con la tabla del mes que viene a
    medio cargar la perdía, sin aviso, sin auditoría y sin deshacer."""
    base = db_con_vigente()
    corre(ed.guardar_borrador({**TARIFA, "tarifa_minima": "99.00"}, _Admin(), db=base))
    corre(ed.publicar(dict(TARIFA), "republicación", _Admin(), db=base,
                      consumir_borrador=False))
    assert corre(ed.leer_borrador(db=base))["tarifa_minima"] == "99.00"


def test_un_fallo_de_lectura_no_se_confunde_con_no_tener_borrador():
    """Si un timeout devolviera None, la pantalla diría "no tenés cambios sin
    publicar", el administrador los volvería a cargar y al publicar el delete_one
    se llevaría el borrador real que sí estaba."""
    base = db_con_vigente()

    async def revienta(*a, **k):
        raise RuntimeError("timeout")
    base.app_settings.find_one = revienta

    with pytest.raises(ed.BaseInaccesible):
        corre(ed.leer_borrador(db=base))
    borrador, origen = corre(ed.borrador_o_copia(db=base))
    assert origen == "error" and borrador == {}


def test_el_copy_forward_de_una_version_con_la_forma_vieja_se_puede_guardar():
    """La forma anidada (`servicio_traslado.escalones`) todavía la acepta el
    motor. Copiarla verbatim producía un borrador que el esquema rechaza por
    partida doble, o sea que el copy-forward no servía justo para las versiones
    más viejas."""
    base = _Db()
    base.tarifas_envio.filas.append({
        "version_id": "tar_vieja", "vigente_desde": _AYER, "vigente_hasta": None,
        "modo_tarifa": "peso", "regla_peso": TARIFA["regla_peso"],
        "servicio_traslado": {"escalones": TARIFA["escalones_peso"],
                              "adicional_por_kg": "2.00"},
    })
    borrador, origen = corre(ed.borrador_o_copia(db=base))
    assert origen == "copia_de_vigente"
    assert "servicio_traslado" not in borrador
    assert borrador["escalones_peso"] == TARIFA["escalones_peso"]
    TarifaBorrador(**borrador)      # el esquema lo acepta: se puede seguir editando


def test_el_dinero_no_sale_de_la_api_como_float():
    """Misma regla que models/envios_tarifa: un Decimal que FastAPI convierte a
    float es el ruido binario volviendo a entrar por la ventana de salida."""
    payload = ed.serializable({"total": Decimal("132.00"),
                               "filas": [{"precio": Decimal("0.1")}]})
    assert payload == {"total": "132.00", "filas": [{"precio": "0.1"}]}


def test_un_decimal128_en_la_base_no_tumba_la_consola_de_precios():
    """Es como services/money.py guarda dinero en Mongo, y el encoder de FastAPI
    no lo sabe serializar: un solo campo así devolvía un 500."""
    class _Decimal128:
        def __init__(self, v): self.v = v
        def __str__(self): return self.v
    _Decimal128.__name__ = "Decimal128"

    import json
    payload = ed.serializable({"tarifa_minima": _Decimal128("45.00")})
    assert json.dumps(payload) == '{"tarifa_minima": "45.00"}'


def test_el_historial_marca_las_versiones_que_nunca_rigieron():
    base = db_con_vigente()
    # La MISMA fecha las dos veces: es lo que hace el panel, donde se elige un día
    # del calendario y no un "dentro de 30 días" que cambia entre un clic y otro.
    el_primero = (datetime.now(timezone.utc) + timedelta(days=30)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    mala, _ = corre(ed.publicar({**TARIFA, "tarifa_minima": "600.00"}, "mal tipeado",
                                _Admin(), db=base, vigente_desde=el_primero))
    corre(ed.publicar({**TARIFA, "tarifa_minima": "60.00"}, "corregido", _Admin(),
                      db=base, vigente_desde=el_primero))
    fila = [f for f in corre(ed.historial(db=base))
            if f["version_id"] == mala["version_id"]][0]
    assert fila["anulada"] is True and fila["nota"] == "mal tipeado"


def test_el_borrador_admite_todos_los_campos_de_una_version():
    """Sin esto, un campo nuevo en TarifaEnvio quedaría fuera del borrador y la
    pantalla no lo podría guardar hasta que alguien se acordara de agregarlo."""
    faltan = set(TarifaEnvio.model_fields) - set(TarifaBorrador.model_fields)
    assert faltan == set()


def test_lo_que_devuelve_el_get_se_puede_volver_a_guardar():
    """El GET devolvía el borrador con `actualizado_por` y `actualizado_at`, y el
    modelo de guardado tiene extra="forbid": el segundo guardado de la vida del
    editor era un 422, y el primero no, así que nadie lo asociaba."""
    base = _Db()
    corre(ed.guardar_borrador(TarifaBorrador(**TARIFA).como_borrador(), _Admin(), db=base))
    devuelto = corre(ed.leer_borrador(db=base))
    assert "actualizado_at" in devuelto
    de_vuelta = TarifaBorrador(**devuelto).como_borrador()      # no lanza
    assert "actualizado_at" not in de_vuelta


def test_un_precio_en_notacion_cientifica_se_rechaza_aunque_este_en_rango():
    """"4.5E+1" son 45, un valor perfectamente válido, y por eso pasaba todos los
    rangos. El problema no es el valor: es que en una planilla de precios nadie
    escribe así, y lo que sí llega en esa forma —un 1E-30 de múltiplo de
    redondeo— hace estallar cada cotización ya publicada. Los precios se escriben
    con todos sus dígitos."""
    with pytest.raises(Exception) as e:
        TarifaEnvio(**{**TARIFA, "tarifa_minima": "4.5E+1"})
    assert "cientifica" in str(e.value)
    assert TarifaEnvio(**{**TARIFA, "tarifa_minima": "45"}).tarifa_minima == "45"
