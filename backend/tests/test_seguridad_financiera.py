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


# Cuántas preguntas contesta la pantalla. Se nombra una vez para que agregar
# una tarjeta obligue a mirar los tests que cuentan, en vez de que un `4` suelto
# quede mal en tres lugares distintos.
CUANTAS_TARJETAS = 5


def test_el_resumen_de_una_pantalla_sin_datos_no_afirma_nada():
    """Antes de que conteste la primera consulta, todas las preguntas están sin
    responder. Ninguna puede nacer en verde."""
    estados = js("m.resumen(null).map(t => t.estado)")
    assert estados == ["desconocido"] * CUANTAS_TARJETAS
    assert js("m.resumen(undefined).map(t => t.estado)") == \
        ["desconocido"] * CUANTAS_TARJETAS


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
    """Encadenado con `resumen`: todas las preguntas sin responder tienen que
    dar un dictamen que no afirme nada."""
    assert js("m.dictamen(m.resumen(null)).estado") == "sin_verificar"
    assert js("m.dictamen(m.resumen(null)).noVerificados") == CUANTAS_TARJETAS


# ══════════════════════════════════════════════════════════════════════════
# C-06 — El cofre de los documentos
# ══════════════════════════════════════════════════════════════════════════
#
# Esta tarjeta existe por una promesa que estaba escrita y no era cierta:
# `services/cofre.py` y `docs/la-llave-del-cofre.md` dicen que la huella de la
# llave «se puede mirar en el panel», y no se podía. Sin eso, el procedimiento
# de cotejar la llave que está corriendo contra la anotada en papel exigía
# entrar al servidor por consola — o sea, no se hacía.

def _cofre(valor):
    return json.dumps({"cofre": {"estado": "ok", "valor": valor}})


def tarjeta_cofre(datos):
    return js(f"m.resumen({datos}).find(t => t.clave === 'cofre')")


def test_LA_HUELLA_SE_MUESTRA_EN_LA_TARJETA():
    """Es para lo que existe: cotejarla de un vistazo contra la que está
    anotada, sin entrar al servidor y sin sacar la llave de ningún lado."""
    t = tarjeta_cofre(_cofre({"modo": "cifrando", "ok": True, "huella": "cd3ffe4d"}))
    assert t["cifra"] == "cd3ffe4d"
    assert "huella" in t["unidad"]


def test_el_cofre_prendido_y_verificado_esta_bien():
    t = tarjeta_cofre(_cofre({"modo": "cifrando", "ok": True, "huella": "cd3ffe4d"}))
    assert t["estado"] == "bien"


def test_EL_COFRE_PRENDIDO_QUE_NO_ABRE_ES_ROJO():
    """Es el único estado urgente de esta tarjeta: significa que hay documentos
    guardados que no se van a poder leer."""
    t = tarjeta_cofre(_cofre({"modo": "cifrando", "ok": False, "huella": "aaaa1111",
                              "detalle": "LA LLAVE NO ES LA CORRECTA"}))
    assert t["estado"] == "mal"
    assert "LA LLAVE NO ES LA CORRECTA" in t["detalle"]


def test_el_texto_del_servidor_llega_tal_cual_a_la_pantalla():
    """El servidor distingue «no llego a la base» de «la llave está mal», y esa
    diferencia importa más que el color: una dice que no toques nada, la otra
    que cambies la llave. Si la pantalla lo reemplazara por un mensaje genérico,
    esa distinción se perdería justo cuando hace falta."""
    t = tarjeta_cofre(_cofre({
        "modo": "cifrando", "ok": False, "huella": "aaaa1111",
        "detalle": "No se pudo hablar con la base... no la cambies."}))
    assert "no la cambies" in t["detalle"]


def test_EL_COFRE_APAGADO_NO_ES_UNA_EXCEPCION():
    """La decisión más discutible de la tarjeta, así que queda fijada.

    Guardar los documentos en claro es una postura declarada, no un control que
    falló. Pintarla de ámbar dejaría el dictamen general en «con observaciones»
    para siempre, y un ámbar permanente enseña a ignorar el ámbar — que es lo
    que no se quiere el día que aparezca uno de verdad.

    Va en neutro, y el TEXTO lo dice sin vueltas: ahí es donde se informa.
    """
    t = tarjeta_cofre(_cofre({"modo": "apagado", "ok": True, "huella": "(sin llave)"}))
    assert t["estado"] == "neutro"
    assert "sin cifrar" in t["detalle"]

    dictamen = js(f"m.dictamen(m.resumen({_cofre({'modo': 'apagado', 'ok': True})}))")
    assert dictamen["excepciones"] == 0
    assert dictamen["observaciones"] == 0


@pytest.mark.parametrize("respuesta", [
    '{"cofre": {"estado": "error", "error": "500"}}',
    '{"cofre": {"estado": "ok"}}',              # sin `valor`
    '{"cofre": null}',
    '{}',
])
def test_si_no_se_pudo_consultar_no_se_afirma_nada(respuesta):
    """La regla de todo este archivo, aplicada a la tarjeta nueva: no saber no
    es estar bien."""
    t = tarjeta_cofre(respuesta)
    assert t["estado"] == "desconocido"
    assert t["cifra"] is None


def test_la_consulta_del_cofre_esta_declarada():
    """Sin la entrada en CONSULTAS la tarjeta nunca recibiría datos y se
    quedaría en «desconocido» para siempre, que se lee como un error del
    servidor y no como una tarjeta que nadie conectó."""
    rutas = js("m.CONSULTAS.map(c => c.clave)")
    assert "cofre" in rutas
