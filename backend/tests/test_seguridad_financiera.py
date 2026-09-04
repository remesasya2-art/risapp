"""
tests/test_seguridad_financiera.py — El área que dice si la plata está.

QUE PROTEGE, Y POR QUE ESTOS TRES GRUPOS

    La pantalla de Seguridad financiera no calcula nada del dinero: pregunta a
    cinco rutas que ya existían y traduce las respuestas a cuatro veredictos.
    Todo lo que puede salir mal está en esa traducción, y en la unión entre las
    dos puntas.

    1. LA LOGICA, CORRIENDOLA DE VERDAD
       `frontend/src/utils/seguridadFinanciera.js` no tiene React ni red: son
       funciones puras, y acá se ejecutan con node. No se lee el archivo
       buscando texto —eso comprueba que algo está escrito, no que funcione—.

    2. LA UNION CON EL BACKEND
       Las cinco rutas que la pantalla consulta tienen que EXISTIR en la
       aplicación armada y tienen que ser de super administrador. Si mañana
       alguien renombra `/admin/ledger/pozo`, la pantalla se queda en gris
       diciendo «no se pudo comprobar» y nadie se entera de por qué: el
       veredicto en gris es correcto, y por eso mismo no alarma.

    3. LA PUERTA
       La pestaña es sólo del super administrador en las dos puntas. Una
       pantalla que resume el estado del dinero de la empresa no es algo que se
       reparta.

LA REGLA QUE MAS SE PRUEBA ACA

    NO SABER NO ES ESTAR BIEN.

    Si una consulta falla, el veredicto es «no se pudo comprobar» y nunca
    verde. Es la trampa clásica de un tablero: el `catch` no toca la tarjeta y
    la tarjeta se queda con el color de antes. Hay cuatro pruebas sobre esto
    porque es lo único de esta pantalla que puede hacer daño de verdad:
    alguien la mira, la ve verde, y se va tranquilo.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_RAIZ = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

from conftest import usar_base                                      # noqa: E402,F401

MODULO = os.path.join(_RAIZ, "frontend", "src", "utils", "seguridadFinanciera.js")
PANTALLA = os.path.join(_RAIZ, "frontend", "src", "components", "admin",
                        "SeguridadFinanciera.jsx")
PANEL = os.path.join(_RAIZ, "frontend", "src", "pages", "AdminPanel.jsx")

# Las cinco consultas de la pantalla, tal como las declara CONSULTAS.
RUTAS = [
    ("GET", "/api/admin/ledger/pozo"),
    ("GET", "/api/admin/ledger/reconciliacion"),
    ("GET", "/api/admin/ledger/integridad"),
    ("GET", "/api/admin/rrhh"),
    ("GET", "/api/admin/rrhh/auditoria/libro"),
]


# ─── Grupo 1: la lógica, corriendo ────────────────────────────────────────

_node = shutil.which("node")


def js(expresion):
    """Evalúa una expresión contra el módulo y devuelve el resultado."""
    if not _node:
        pytest.skip("node no está instalado: la lógica de la pantalla no se puede correr")
    codigo = (
        f"import * as m from {json.dumps('file://' + MODULO)};\n"
        f"console.log(JSON.stringify(({expresion})));\n"
    )
    r = subprocess.run([_node, "--input-type=module", "-e", codigo],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        pytest.fail(f"node falló evaluando «{expresion}»:\n{r.stderr}")
    return json.loads(r.stdout)


def persona(**campos):
    base = {"user_id": "u", "email": "a@b.com", "nombre": "Alguien",
            "rol": "admin", "permisos": [], "acceso": {}}
    base.update(campos)
    return json.dumps(base)


def test_el_super_administrador_aparece_aunque_no_tenga_permisos_marcados():
    """EL CASO QUE ESTA PRUEBA EXISTE PARA ATAJAR.

    En su ficha, el super administrador suele tener `permisos: []` — no le
    hacen falta, `services/permisos.py` le devuelve `true` antes de mirar la
    lista. Una pantalla que se guiara sólo por ese arreglo informaría que
    nadie puede ajustar saldos, en una aplicación donde él puede ajustar
    todos. Un listado de llaves que omite al que tiene todas es peor que no
    listar nada.
    """
    llaves = js(f"m.llavesDe({persona(rol='super_admin', permisos=[])})")
    assert llaves["mueveDinero"] is True
    assert llaves["porSerSuperAdmin"] is True
    assert sorted(llaves["dinero"]) == ["envios.dinero", "recharges.approve", "saldos.ajustar"]


def test_un_admin_sin_permisos_de_dinero_no_tiene_llaves():
    llaves = js(f"m.llavesDe({persona(permisos=['users.view', 'kyc.approve'])})")
    assert llaves["mueveDinero"] is False
    assert llaves["mueveLaTasa"] is False
    assert llaves["dinero"] == []


def test_cada_permiso_de_dinero_cuenta_por_si_solo():
    for permiso in ("saldos.ajustar", "recharges.approve", "envios.dinero"):
        llaves = js(f"m.llavesDe({persona(permisos=[permiso])})")
        assert llaves["mueveDinero"] is True, f"{permiso} no contó como llave"
        assert llaves["dinero"] == [permiso]


def test_la_tasa_va_aparte_y_no_se_cuenta_como_mover_dinero():
    """Cambiar la tasa no mueve un saldo, pero cambia lo que todos pagan.
    Mezclarlo haría que «mueve dinero» dejara de significar algo preciso."""
    llaves = js(f"m.llavesDe({persona(permisos=['settings.edit'])})")
    assert llaves["mueveDinero"] is False
    assert llaves["mueveLaTasa"] is True


def test_los_que_tienen_llaves_salen_antes_que_los_que_solo_tocan_la_tasa():
    personal = json.dumps([
        {"email": "tasa@b.com", "rol": "admin", "permisos": ["settings.edit"],
         "acceso": {"dos_pasos": True, "clave_configurada": True}},
        {"email": "plata@b.com", "rol": "admin", "permisos": ["saldos.ajustar"],
         "acceso": {"dos_pasos": True, "clave_configurada": True}},
        {"email": "nadie@b.com", "rol": "agent", "permisos": ["users.view"],
         "acceso": {"dos_pasos": True, "clave_configurada": True}},
    ])
    orden = js(f"m.llaverosDelDinero({personal}).map(f => f.persona.email)")
    assert orden == ["plata@b.com", "tasa@b.com"], (
        "quien mueve dinero tiene que quedar arriba, y quien no tiene llaves afuera")


def test_el_acceso_a_medio_terminar_sube_en_la_lista():
    """Lo que hay que mirar queda arriba sin que nadie ordene la tabla."""
    personal = json.dumps([
        {"email": "listo@b.com", "rol": "admin", "permisos": ["saldos.ajustar"],
         "acceso": {"dos_pasos": True, "clave_configurada": True}},
        {"email": "amedias@b.com", "rol": "admin", "permisos": ["saldos.ajustar"],
         "acceso": {"dos_pasos": False, "clave_configurada": True}},
    ])
    orden = js(f"m.llaverosDelDinero({personal}).map(f => f.persona.email)")
    assert orden == ["amedias@b.com", "listo@b.com"]


def test_los_tres_estados_del_acceso():
    assert js(f"m.estadoDelAcceso({persona(acceso={'dos_pasos': True, 'clave_configurada': True})})") == "listo"
    assert js(f"m.estadoDelAcceso({persona(acceso={'dos_pasos': False, 'clave_configurada': True})})") == "sin_dos_pasos"
    assert js(f"m.estadoDelAcceso({persona(acceso={'dos_pasos': False, 'clave_configurada': False})})") == "sin_activar"


# ─── No saber no es estar bien ────────────────────────────────────────────

def test_una_consulta_caida_no_da_verde():
    assert js("m.veredicto({estado: 'error', error: 'timeout'}, () => true)") == "desconocido"
    assert js("m.veredicto(null, () => true)") == "desconocido"
    assert js("m.veredicto(undefined, () => true)") == "desconocido"


def test_una_respuesta_con_la_forma_cambiada_tampoco_da_verde():
    """Si el servidor devuelve algo que la pantalla no sabe leer, lo honesto
    es decir que no se pudo comprobar, no asumir que está bien."""
    roto = "m.veredicto({estado: 'ok', valor: null}, (v) => v.cubre === true)"
    assert js(roto) == "desconocido"


def test_el_veredicto_solo_es_verde_con_el_valor_exacto():
    """`cubre` tiene que ser `true`, no cualquier cosa que parezca verdadera.
    Un `"false"` de texto es truthy en JavaScript."""
    assert js("m.veredicto({estado: 'ok', valor: {cubre: true}}, (v) => v.cubre === true)") == "bien"
    assert js("m.veredicto({estado: 'ok', valor: {cubre: false}}, (v) => v.cubre === true)") == "mal"
    assert js("m.veredicto({estado: 'ok', valor: {cubre: 'false'}}, (v) => v.cubre === true)") == "mal"
    assert js("m.veredicto({estado: 'ok', valor: {}}, (v) => v.cubre === true)") == "mal"


def test_el_resumen_de_una_pantalla_sin_datos_no_afirma_nada():
    """Antes de que conteste la primera consulta, las cuatro preguntas están
    sin responder. Ninguna puede nacer en verde."""
    estados = js("m.resumen(null).map(t => t.estado)")
    assert estados == ["desconocido"] * 4
    assert js("m.resumen(undefined).map(t => t.estado)") == ["desconocido"] * 4


def test_el_resumen_traduce_cada_respuesta():
    datos = json.dumps({
        "pozo": {"estado": "ok", "valor": {"cubre": True, "diferencia": "10.00", "moneda": "BRL"}},
        "reconciliacion": {"estado": "ok", "valor": {"cuadra": False, "descuadres_totales": 3}},
        "integridad": {"estado": "error", "error": "500"},
        "personal": {"estado": "ok", "valor": {"personal": [
            {"email": "a@b.com", "rol": "admin", "permisos": ["saldos.ajustar"],
             "acceso": {"dos_pasos": True, "clave_configurada": True}}]}},
    })
    tarjetas = js(f"m.resumen({datos})")
    por_clave = {t["clave"]: t for t in tarjetas}
    assert por_clave["pozo"]["estado"] == "bien"
    assert por_clave["reconciliacion"]["estado"] == "mal"
    assert por_clave["reconciliacion"]["cifra"] == "3"
    assert por_clave["integridad"]["estado"] == "desconocido"
    assert por_clave["integridad"]["cifra"] is None
    assert por_clave["llaves"]["estado"] == "neutro"
    assert por_clave["llaves"]["cifra"] == "1"


def test_el_resumen_exige_el_valor_exacto_y_no_algo_parecido():
    """En JavaScript `"false"` es truthy, y `0` es falsy. Si el resumen mirara
    `v.cubre` a secas en vez de `v.cubre === true`, un pozo que no cubre
    —informado como texto por cualquier razón— saldría en verde. Es el error
    más barato de cometer y el más caro de tener."""
    for valor, esperado in [(True, "bien"), (False, "mal"), ("false", "mal"),
                            ("", "mal"), (1, "mal"), (None, "mal")]:
        datos = json.dumps({"pozo": {"estado": "ok", "valor": {"cubre": valor}}})
        tarjetas = js(f"m.resumen({datos})")
        pozo = [t for t in tarjetas if t["clave"] == "pozo"][0]
        assert pozo["estado"] == esperado, f"con cubre={valor!r} dio {pozo['estado']}"


def test_el_resumen_exige_el_valor_exacto_tambien_en_las_otras_dos():
    for clave, campo in [("reconciliacion", "cuadra"), ("integridad", "sano")]:
        for valor, esperado in [(True, "bien"), ("true", "mal"), (1, "mal")]:
            datos = json.dumps({clave: {"estado": "ok", "valor": {campo: valor}}})
            tarjetas = js(f"m.resumen({datos})")
            t = [x for x in tarjetas if x["clave"] == clave][0]
            assert t["estado"] == esperado, f"{clave} con {campo}={valor!r} dio {t['estado']}"


def test_las_llaves_pasan_a_ambar_cuando_alguien_no_termino_de_asegurarse():
    datos = json.dumps({"personal": {"estado": "ok", "valor": {"personal": [
        {"email": "a@b.com", "rol": "admin", "permisos": ["saldos.ajustar"],
         "acceso": {"dos_pasos": False, "clave_configurada": True}}]}}})
    tarjetas = js(f"m.resumen({datos})")
    assert [t for t in tarjetas if t["clave"] == "llaves"][0]["estado"] == "atencion"


def test_las_llaves_nunca_dan_verde():
    """«Hay cinco personas que pueden mover plata» no es una buena noticia ni
    una mala: es un recuento. Pintarlo de verde sería decir que está bien, y
    eso no lo decide una pantalla."""
    datos = json.dumps({"personal": {"estado": "ok", "valor": {"personal": [
        {"email": "a@b.com", "rol": "super_admin", "permisos": [],
         "acceso": {"dos_pasos": True, "clave_configurada": True}}]}}})
    tarjetas = js(f"m.resumen({datos})")
    assert [t for t in tarjetas if t["clave"] == "llaves"][0]["estado"] == "neutro"


# ─── El dictamen general del encabezado ───────────────────────────────────

def _tarjetas(*estados):
    return json.dumps([{"clave": f"c{i}", "estado": e} for i, e in enumerate(estados)])


def test_el_dictamen_nunca_dice_conforme_si_algo_quedo_sin_verificar():
    """LA REGLA DE SIEMPRE, APLICADA AL LUGAR MAS VISIBLE.

    El encabezado es lo primero que se lee y lo único que alguien recuerda. Si
    dijera «conforme» con un control caído, la pantalla estaría afirmando
    exactamente lo que no pudo comprobar. En un informe de control interno eso
    tiene nombre: limitación al alcance.
    """
    assert js(f"m.dictamen({_tarjetas('bien', 'bien', 'bien', 'desconocido')}).estado") == "sin_verificar"
    assert js(f"m.dictamen({_tarjetas('bien', 'neutro', 'desconocido')}).estado") == "sin_verificar"


def test_una_excepcion_pesa_mas_que_todo_lo_demas():
    assert js(f"m.dictamen({_tarjetas('mal', 'bien', 'bien', 'bien')}).estado") == "excepcion"
    assert js(f"m.dictamen({_tarjetas('mal', 'desconocido')}).estado") == "excepcion"
    assert js(f"m.dictamen({_tarjetas('mal', 'atencion')}).estado") == "excepcion"


def test_no_verificado_pesa_mas_que_una_observacion():
    """Una observación es algo que se sabe y se mira. Un control sin verificar
    es algo de lo que no se sabe nada, y eso es peor."""
    assert js(f"m.dictamen({_tarjetas('atencion', 'desconocido')}).estado") == "sin_verificar"


def test_solo_es_conforme_cuando_todo_lo_es():
    assert js(f"m.dictamen({_tarjetas('bien', 'bien', 'bien', 'neutro')}).estado") == "conforme"
    assert js(f"m.dictamen({_tarjetas('bien', 'bien', 'atencion')}).estado") == "observaciones"


def test_sin_tarjetas_no_hay_dictamen_favorable():
    """Antes de la primera ejecución no hay nada comprobado. Un encabezado que
    naciera en «conforme» sería la peor versión del error que este archivo
    persigue."""
    for entrada in ("[]", "null", "undefined"):
        assert js(f"m.dictamen({entrada}).estado") == "sin_verificar"


def test_el_dictamen_cuenta_cada_categoria():
    d = js(f"m.dictamen({_tarjetas('mal', 'mal', 'desconocido', 'atencion', 'bien', 'neutro')})")
    assert d["excepciones"] == 2
    assert d["noVerificados"] == 1
    assert d["observaciones"] == 1
    assert d["conformes"] == 2
    assert d["total"] == 6


def test_el_dictamen_del_resumen_sin_datos_es_alcance_limitado():
    """Encadenado con `resumen`: las cuatro preguntas sin responder tienen que
    dar un dictamen que no afirme nada."""
    assert js("m.dictamen(m.resumen(null)).estado") == "sin_verificar"
    assert js("m.dictamen(m.resumen(null)).noVerificados") == 4


def test_no_verificado_no_se_puede_etiquetar_como_aprobado():
    """LA SIMPLIFICACION QUE ALGUIEN HARIA DE BUENA FE.

    Cambiar «No verificado» por «Sin novedad» parece una mejora de redacción y
    es un cambio de significado: convierte una limitación al alcance en un
    visto bueno. Por eso las palabras viven en el módulo y no en la pantalla.
    """
    etiquetas = js("m.DICTAMEN_ETIQUETA")
    sin_verificar = etiquetas["desconocido"].lower()

    assert sin_verificar != etiquetas["bien"].lower()
    assert sin_verificar != etiquetas["neutro"].lower()
    for palabra in ("conforme", "novedad", "correcto", "ok", "bien"):
        assert palabra not in sin_verificar, (
            f"«{etiquetas['desconocido']}» se lee como aprobación")


def test_cada_estado_tiene_su_propia_palabra():
    """Dos estados con la misma etiqueta es un estado que desaparece."""
    for mapa in ("m.DICTAMEN_ETIQUETA", "m.DICTAMEN_GENERAL_ETIQUETA"):
        etiquetas = js(mapa)
        assert len(set(etiquetas.values())) == len(etiquetas), (
            f"{mapa} repite alguna etiqueta: {etiquetas}")


def test_hay_una_palabra_para_cada_estado_que_el_resumen_puede_devolver():
    """Si `resumen` devolviera un estado sin etiqueta, la pantalla caería al
    genérico y mostraría «No verificado» sobre un control que sí se verificó."""
    estados = set(js("m.resumen(null).map(t => t.estado)"))
    estados |= {"bien", "mal", "atencion", "neutro", "desconocido"}
    etiquetas = js("m.DICTAMEN_ETIQUETA")
    faltan = sorted(estados - set(etiquetas))
    assert not faltan, f"estados sin etiqueta: {faltan}"

    generales = js("m.DICTAMEN_GENERAL_ETIQUETA")
    posibles = {"conforme", "observaciones", "sin_verificar", "excepcion"}
    assert posibles <= set(generales), sorted(posibles - set(generales))


# ─── Grupo 2: la unión con el backend ─────────────────────────────────────

@pytest.fixture(scope="module")
def rutas_de_la_app():
    try:
        from server import app
    except Exception as e:                                # pragma: no cover
        pytest.skip(f"no se pudo armar la app: {type(e).__name__}: {e}")
    return app.routes


def _ruta(rutas, metodo, camino):
    for r in rutas:
        if getattr(r, "path", None) == camino and metodo in (getattr(r, "methods", None) or ()):
            return r
    return None


def test_las_cinco_consultas_de_la_pantalla_existen(rutas_de_la_app):
    """Si alguien renombra una, la pantalla se queda en gris diciendo «no se
    pudo comprobar». El veredicto sería correcto y justamente por eso nadie
    iría a mirar: un gris no alarma."""
    faltan = [f"{m} {c}" for m, c in RUTAS if _ruta(rutas_de_la_app, m, c) is None]
    assert not faltan, "la pantalla consulta rutas que la aplicación no tiene:\n  " + "\n  ".join(faltan)


def test_las_cinco_son_de_super_administrador(rutas_de_la_app):
    from routes.dependencies import get_super_admin

    def exige_super(dependant):
        if any(d.call is get_super_admin for d in dependant.dependencies):
            return True
        return any(exige_super(d) for d in dependant.dependencies)

    sueltas = []
    for metodo, camino in RUTAS:
        ruta = _ruta(rutas_de_la_app, metodo, camino)
        if ruta is None:
            continue                      # ya lo dice la prueba de arriba
        if not exige_super(ruta.dependant):
            sueltas.append(f"{metodo} {camino}")

    assert not sueltas, (
        "estas rutas del área de Seguridad financiera no exigen super "
        "administrador:\n  " + "\n  ".join(sueltas))


def test_la_pantalla_no_consulta_ninguna_otra_ruta():
    """Lo que la pantalla pide tiene que ser exactamente lo que estas pruebas
    comprueban. Una consulta agregada a mano en el componente —salteando
    CONSULTAS— quedaría sin verificar."""
    fuente = open(PANTALLA, encoding="utf-8").read()
    assert "api.get" in fuente, "la pantalla dejó de consultar: revisá esta prueba"
    # Una sola llamada, y va sobre la lista declarada.
    assert fuente.count("api.get") == 1
    assert "CONSULTAS.map" in fuente


def test_la_pantalla_solo_lee():
    """No cambia ningún saldo ni corrige ningún asiento, y eso no es una
    promesa del comentario: no hay forma de escribir desde acá."""
    fuente = open(PANTALLA, encoding="utf-8").read()
    for verbo in ("api.post", "api.put", "api.patch", "api.delete"):
        assert verbo not in fuente, f"la pantalla de Seguridad financiera usa {verbo}"


# ─── Grupo 3: la puerta ───────────────────────────────────────────────────

def test_la_pestana_es_solo_del_super_administrador():
    """En las dos puntas: la pestaña no se dibuja, y el contenido tampoco. El
    backend igual la frenaría, pero una pestaña que un agente ve y que le
    devuelve cinco errores es una pestaña que no debería estar."""
    panel = open(PANEL, encoding="utf-8").read()
    declaracion = [l for l in panel.splitlines() if "key: 'seguridad'" in l]
    assert len(declaracion) == 1, "la pestaña tiene que declararse una sola vez"
    assert "superAdminOnly: true" in declaracion[0]
    assert "activeTab === 'seguridad' && user?.role === 'super_admin'" in panel
