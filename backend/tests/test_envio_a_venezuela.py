"""
tests/test_envio_a_venezuela.py — Las cuentas de «Enviar a Venezuela».

QUE PROTEGE

    Esta pantalla le dice a alguien cuánto va a recibir su familia. Si esa cifra
    está mal no es un error de interfaz: es una promesa incumplida que se
    descubre del otro lado de la frontera, cuando ya no se puede hacer nada.

    La lógica vive en `frontend/src/utils/envioAVenezuela.js`, sin React y sin
    red, y acá se EJECUTA con node. No se lee el archivo buscando texto: eso
    comprueba que algo está escrito, no que funcione.

LAS DOS REGLAS QUE MAS SE PRUEBAN

    1. LO QUE SE MUESTRA ES LO QUE VA A PASAR.
       El servidor calcula `round(ris * tasa, 2)` sobre el RIS que recibe. Así
       que cuando alguien escribe el monto en bolívares, la pantalla no puede
       repetirle el número que tipeó: tiene que mostrarle el que sale del RIS
       redondeado que se va a enviar de verdad.

    2. SIN TASA NO SE INVENTA UNA.
       `RateContext` arranca con `ris_to_ves: 110` para que ninguna pantalla se
       rompa mientras carga. Si `/rate` falla ese 110 se queda ahí, y hasta
       ahora esta pantalla lo mostraba y convertía con él. Una conversión
       inventada en la pantalla que mueve dinero es peor que ninguna.
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

MODULO = os.path.join(_RAIZ, "frontend", "src", "utils", "envioAVenezuela.js")
PANTALLA = os.path.join(_RAIZ, "frontend", "src", "pages", "Send.jsx")
CONTEXTO = os.path.join(_RAIZ, "frontend", "src", "contexts", "RateContext.jsx")

_node = shutil.which("node")


def js(expresion):
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


# ─── Regla 1: lo que se muestra es lo que va a pasar ──────────────────────

def test_escribiendo_en_ris_la_cuenta_es_directa():
    ris = js("m.risAEnviar({risEscrito: '100', tasa: 165, tasaDisponible: true})")
    assert ris == 100
    assert js("m.vesARecibir({ris: 100, tasa: 165, tasaDisponible: true})") == 16500


def test_escribiendo_en_bolivares_el_ris_se_redondea_a_lo_que_el_saldo_admite():
    """10.000 VES a 165 son 60,606060… RIS. El saldo lleva dos decimales."""
    ris = js("m.risAEnviar({vesEscrito: '10000', tasa: 165, tasaDisponible: true})")
    assert ris == 60.61


def test_LOS_BOLIVARES_QUE_SE_MUESTRAN_SALEN_DEL_RIS_NO_DE_LO_TIPEADO():
    """LA REGLA CENTRAL DE ESTE ARCHIVO.

    Quien escribe «10.000 VES» va a recibir 10.000,65, porque el servidor
    calcula sobre los 60,61 RIS que efectivamente se envían. Mostrar «10.000»
    sería repetirle su propio número en vez de decirle lo que va a pasar.

    La diferencia es de céntimos. Lo que importa no es el monto: es que la
    pantalla no puede afirmar una cifra que el servidor no va a producir.
    """
    ris = js("m.risAEnviar({vesEscrito: '10000', tasa: 165, tasaDisponible: true})")
    ves = js(f"m.vesARecibir({{ris: {ris}, tasa: 165, tasaDisponible: true}})")
    assert ves == 10000.65
    assert ves != 10000, "la pantalla está repitiendo lo tipeado en vez de calcular"


def test_la_ida_y_la_vuelta_cierran_para_muchos_montos():
    """Para cualquier monto, los bolívares mostrados tienen que ser exactamente
    `round(ris * tasa, 2)`: la misma cuenta que hace el servidor."""
    guion = """
      (() => {
        const casos = [];
        for (const tasa of [110, 165.5, 233.77, 1.05]) {
          for (const ves of [100, 1000, 9999.99, 250000, 7]) {
            const ris = m.risAEnviar({vesEscrito: String(ves), tasa, tasaDisponible: true});
            const mostrado = m.vesARecibir({ris, tasa, tasaDisponible: true});
            const servidor = Math.round((ris * tasa + Number.EPSILON) * 100) / 100;
            casos.push({tasa, ves, ris, mostrado, servidor, cierra: mostrado === servidor});
          }
        }
        return casos.filter(c => !c.cierra);
      })()
    """
    fallan = js(guion)
    assert fallan == [], f"la pantalla mostraría algo distinto de lo que calcula el servidor: {fallan}"


def test_el_ris_nunca_lleva_mas_de_dos_decimales():
    """La comprobación NO es `r * 100 === Math.round(r * 100)`.

    En coma flotante `0.14 * 100` da 14.000000000000002, así que esa forma de
    preguntarlo falla para valores que están perfectamente redondeados. Se
    compara contra una tolerancia, que es la única manera honesta de preguntar
    «¿tiene dos decimales?» sobre un float.
    """
    guion = """
      [110, 165.5, 233.77, 7.13].flatMap(tasa =>
        [1, 33, 999.99, 123456].map(ves => {
          const r = m.risAEnviar({vesEscrito: String(ves), tasa, tasaDisponible: true});
          const ok = Math.abs(r * 100 - Math.round(r * 100)) < 1e-9;
          return {tasa, ves, r, ok};
        })).filter(x => !x.ok)
    """
    assert js(guion) == []


# ─── Regla 2: sin tasa no se inventa una ──────────────────────────────────

def test_sin_tasa_no_se_convierte():
    """`null`, y no cero: un cero se leería como «no recibe nada», que es una
    afirmación distinta de «no lo sabemos»."""
    assert js("m.risAEnviar({risEscrito: '100', tasa: 110, tasaDisponible: false})") is None
    assert js("m.vesARecibir({ris: 100, tasa: 110, tasaDisponible: false})") is None


def test_sin_tasa_no_se_puede_continuar():
    v = js("m.validarMonto({ris: 100, saldo: 1000, tasaDisponible: false, escribioAlgo: true})")
    assert v["ok"] is False
    assert v["motivo"] == "sin_tasa"


def test_una_tasa_en_cero_o_negativa_tampoco_convierte():
    for tasa in ("0", "-5", "null"):
        assert js(f"m.risAEnviar({{risEscrito: '100', tasa: {tasa}, tasaDisponible: true}})") is None


# ─── El motivo, no sólo el sí o el no ─────────────────────────────────────

def test_cada_negativa_trae_su_motivo():
    """Una pantalla que sólo sabe que «no se puede» tiene que inventar el
    mensaje, y termina diciendo «saldo insuficiente» a quien no escribió nada."""
    casos = [
        ("{ris: null, saldo: 100, tasaDisponible: true, escribioAlgo: false}", "vacio"),
        ("{ris: 0, saldo: 100, tasaDisponible: true, escribioAlgo: true}", "no_positivo"),
        ("{ris: -3, saldo: 100, tasaDisponible: true, escribioAlgo: true}", "no_positivo"),
        ("{ris: 500, saldo: 100, tasaDisponible: true, escribioAlgo: true}", "excede_saldo"),
        ("{ris: 10, saldo: 0, tasaDisponible: true, escribioAlgo: true}", "sin_saldo"),
    ]
    for entrada, esperado in casos:
        v = js(f"m.validarMonto({entrada})")
        assert v["ok"] is False, entrada
        assert v["motivo"] == esperado, f"{entrada} dio {v['motivo']}"


def test_el_monto_justo_del_saldo_se_puede_enviar():
    v = js("m.validarMonto({ris: 100, saldo: 100, tasaDisponible: true, escribioAlgo: true})")
    assert v["ok"] is True


def test_hay_mensaje_para_todos_los_motivos():
    """Un motivo sin mensaje deja la pantalla muda justo cuando tiene que
    explicar por qué no la deja seguir."""
    motivos = js("Object.values(m.MOTIVO)")
    mensajes = js("m.MENSAJE_DEL_MOTIVO")
    faltan = sorted(set(motivos) - set(mensajes))
    assert not faltan, f"motivos sin mensaje: {faltan}"
    assert all(str(v).strip() for v in mensajes.values())


# ─── La tasa que se mueve mientras el usuario decide ──────────────────────

def test_se_avisa_cuando_la_tasa_cambio():
    d = js("m.tasaSeMovio({tasaAlCotizar: 165, tasaAhora: 170})")
    assert d["antes"] == 165 and d["ahora"] == 170 and d["mejora"] is True

    d = js("m.tasaSeMovio({tasaAlCotizar: 165, tasaAhora: 160})")
    assert d["mejora"] is False


def test_no_se_avisa_de_un_cambio_que_no_hubo():
    assert js("m.tasaSeMovio({tasaAlCotizar: 165, tasaAhora: 165})") is None
    assert js("m.tasaSeMovio({tasaAlCotizar: null, tasaAhora: 165})") is None
    assert js("m.tasaSeMovio({tasaAlCotizar: 165, tasaAhora: 0})") is None


# ─── Los pasos ────────────────────────────────────────────────────────────

def test_no_se_puede_saltar_a_un_paso_sin_sus_datos():
    assert js("m.ultimoPasoAlcanzable({montoOk: false})") == 1
    assert js("m.ultimoPasoAlcanzable({montoOk: true})") == 2
    assert js("m.ultimoPasoAlcanzable({montoOk: true, metodo: 'pago_movil'})") == 3
    assert js("m.ultimoPasoAlcanzable({montoOk: true, metodo: 'pago_movil', beneficiario: {}})") == 4


def test_los_cuatro_pasos_tienen_nombre():
    """«2 de 4» no informa nada. El nombre del paso sí."""
    pasos = js("m.PASOS")
    assert [p["numero"] for p in pasos] == [1, 2, 3, 4]
    assert all(p["titulo"].strip() for p in pasos)
    assert len({p["titulo"] for p in pasos}) == 4


# ─── Cómo se muestran los datos del beneficiario ──────────────────────────

def test_el_banco_de_pago_movil_muestra_nombre_y_codigo():
    """Pago Móvil guarda SOLO el código. Mostrar «0134» a quien eligió
    «Banesco» lo obliga a recordar un número para reconocer al suyo."""
    catalogo = json.dumps([{"code": "0134", "name": "Banesco"}])
    b = json.dumps({"bank": "0134", "bank_code": "0134"})
    assert js(f"m.nombreDelBanco({b}, {catalogo})") == "Banesco · 0134"


def test_el_banco_de_transferencia_tambien():
    catalogo = json.dumps([{"code": "0102", "name": "Banco de Venezuela"}])
    b = json.dumps({"bank": "Banco de Venezuela", "bank_code": "0102"})
    assert js(f"m.nombreDelBanco({b}, {catalogo})") == "Banco de Venezuela · 0102"


def test_un_banco_que_no_esta_en_el_catalogo_no_desaparece():
    """Si el catálogo cambia, el beneficiario guardado tiene que seguir
    mostrando algo: lo que se guardó."""
    b = json.dumps({"bank": "Banco Viejo", "bank_code": "9999"})
    assert js(f"m.nombreDelBanco({b}, [])") == "Banco Viejo · 9999"
    assert js("m.nombreDelBanco({}, [])") == "—"


def test_la_cuenta_se_abrevia_en_la_lista():
    assert js("m.cuentaAbreviada('01340123456789012345')") == "••••2345"
    assert js("m.cuentaAbreviada('')") == "—"


def test_el_telefono_se_agrupa_para_poder_leerlo():
    assert js("m.telefonoLegible('04141234567')") == "0414 123 4567"
    assert js("m.telefonoLegible('123')") == "123"


# ─── La unión con la pantalla ─────────────────────────────────────────────

def test_la_pantalla_envia_el_ris_calculado_y_no_lo_tipeado():
    """El `POST /withdraw` lleva `amount: ris` —el número redondeado que la
    pantalla mostró— y no el texto crudo del campo. Si mandara lo tipeado, el
    servidor calcularía sobre otro monto que el que se le prometió al usuario."""
    fuente = open(PANTALLA, encoding="utf-8").read()
    assert "amount: ris," in fuente
    assert "parseFloat(amount)" not in fuente


def test_la_pantalla_lee_el_indicador_de_tasa_disponible():
    fuente = open(PANTALLA, encoding="utf-8").read()
    assert "tasaDisponible" in fuente
    contexto = open(CONTEXTO, encoding="utf-8").read()
    assert "tasaDisponible" in contexto, (
        "RateContext dejó de publicar el indicador: la pantalla volvería a "
        "convertir con la tasa por defecto de 110 cuando /rate falle.")


def test_el_contexto_no_enciende_el_indicador_sin_respuesta_del_servidor():
    """El indicador se pone en true SOLO con una respuesta que trae tasa."""
    contexto = open(CONTEXTO, encoding="utf-8").read()
    assert "setTasaDisponible(Boolean(response.data?.ris_to_ves))" in contexto
    # Y no hay ningún otro lugar que lo encienda.
    assert contexto.count("setTasaDisponible(") == 1
