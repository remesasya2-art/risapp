"""
Los limites del formulario de envios: la interseccion, y los minimos que se olvidan.

CONTEXTO
    Los limites de un paquete no son una constante: son la interseccion de los
    transportistas habilitados, y gana el mas estricto. Escribirlos a mano en la
    pantalla es exactamente el bug que arreglo el PR #40 con los montos, un
    escalon mas arriba: la app anunciaba un techo que el servidor no validaba.

    Y hay minimos, no solo maximos. Es el error facil de omitir: se valida que la
    caja no sea demasiado grande y nadie valida que no sea demasiado chica. Un
    sobre por debajo del minimo cotiza bien, se paga, y despues no se despacha —
    con la plata ya debitada y el paquete en la calle.

QUE SE CUBRE
    1. La interseccion toma el MENOR de los maximos y el MAYOR de los minimos.
    2. Un transportista que no declara un limite no lo restringe.
    3. Habilitar una empresa mas estricta ajusta los limites solos, sin tocar
       codigo.
    4. Los minimos de 11 x 6 x 0,4 cm se validan de verdad.
    5. La suma de lados, por arriba y por abajo.
    6. Los mensajes nombran al transportista por su CODIGO, nunca por su marca.
    7. Entradas basura (None, texto, cero, negativos) devuelven mensaje y no
       lanzan — mismo criterio que services/limits.py.
    8. La lista de prohibidos del codigo es una semilla, no la fuente de verdad.

El modulo es puro —no toca red ni Mongo— asi que se carga por ruta directa para
no arrastrar services/__init__.py, que importa twilio y otras dependencias.
"""
import importlib.util
import os
import sys
import types
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
policy = _cargar("envios_policy")


# ─── Transportistas de ejemplo. Solo codigos, ningun nombre. ──────────────

TRP_BR = {
    "codigo": "TRP-7K2M", "rol": "brasil", "activo": True,
    "limites": {"peso_max_kg": 30, "lado_max_cm": 100, "suma_lados_max_cm": 200,
                "largo_min_cm": 11, "ancho_min_cm": 6, "alto_min_cm": "0.4",
                "suma_lados_min_cm": "17.4"},
}
TRP_VE = {
    "codigo": "TRP-3Q9X", "rol": "venezuela", "activo": True,
    "limites": {"peso_max_kg": 70, "lado_max_cm": 120, "suma_lados_max_cm": 250},
}
TRP_ESTRICTO = {
    "codigo": "TRP-1A1A", "rol": "venezuela", "activo": True,
    "limites": {"peso_max_kg": 20, "lado_max_cm": 80},
}
LIMITES_PROPIOS = {"valor_declarado_max": 3000}


# ─── 1. La interseccion ───────────────────────────────────────────────────

def test_la_interseccion_toma_el_maximo_mas_chico():
    lim = policy.limites_efectivos([TRP_BR, TRP_VE])
    assert lim["peso_max_kg"] == Decimal("30")
    assert lim["lado_max_cm"] == Decimal("100")
    assert lim["suma_lados_max_cm"] == Decimal("200")


def test_la_interseccion_toma_el_minimo_mas_grande():
    otro = {"codigo": "TRP-2B2B", "activo": True, "limites": {"largo_min_cm": 15}}
    lim = policy.limites_efectivos([TRP_BR, otro])
    assert lim["largo_min_cm"] == Decimal("15")
    assert lim["ancho_min_cm"] == Decimal("6")


def test_un_transportista_sin_limite_declarado_no_restringe():
    """Si nadie declara peso maximo, no hay peso maximo. Inventar un techo que
    despues nadie puede explicar es peor que no tenerlo."""
    lim = policy.limites_efectivos([{"codigo": "TRP-0000", "activo": True, "limites": {}}])
    assert "peso_max_kg" not in lim
    assert policy.limites_efectivos([]) == {}
    assert policy.limites_efectivos(None) == {}


def test_habilitar_una_empresa_mas_estricta_ajusta_los_limites_solo():
    """Es la razon de ser de este modulo: el dia que entre un transportista mas
    restrictivo, el formulario se ajusta sin tocar una linea de codigo."""
    antes = policy.limites_efectivos([TRP_BR, TRP_VE])
    despues = policy.limites_efectivos([TRP_BR, TRP_VE, TRP_ESTRICTO])
    assert antes["peso_max_kg"] == Decimal("30")
    assert despues["peso_max_kg"] == Decimal("20")
    assert despues["lado_max_cm"] == Decimal("80")


def test_los_limites_propios_entran_en_la_interseccion():
    lim = policy.limites_efectivos([TRP_BR], LIMITES_PROPIOS)
    assert lim["valor_declarado_max"] == Decimal("3000")


def test_quien_impone_el_limite_devuelve_el_codigo_y_no_una_marca():
    quien = policy.quien_impone([TRP_BR, TRP_VE], "lado_max_cm")
    assert quien == "TRP-7K2M"
    assert policy.quien_impone([TRP_BR, TRP_VE, TRP_ESTRICTO], "peso_max_kg") == "TRP-1A1A"
    assert policy.quien_impone([], "peso_max_kg") is None


# ─── 2. La validacion del paquete ─────────────────────────────────────────

LIM = policy.limites_efectivos([TRP_BR, TRP_VE], LIMITES_PROPIOS)


def test_un_paquete_normal_pasa():
    assert policy.validar_paquete(5, 40, 30, 20, 200, LIM) is None


def test_el_borde_exacto_pasa():
    """30 kg justos y 100 cm justos se aceptan: el limite es inclusivo."""
    assert policy.validar_paquete(30, 100, 50, 50, 0, LIM) is None


def test_un_kilo_de_mas_se_rechaza():
    msg = policy.validar_paquete("30.01", 40, 30, 20, 0, LIM)
    assert msg and "30 kg" in msg


def test_un_lado_de_mas_se_rechaza_diciendo_cuanto_mide():
    msg = policy.validar_paquete(5, 101, 30, 20, 0, LIM)
    assert msg and "100" in msg and "101" in msg


def test_la_suma_de_lados_se_valida_aunque_ningun_lado_se_pase():
    """80 + 70 + 60 = 210: ningun lado supera los 100, pero la suma supera 200."""
    msg = policy.validar_paquete(5, 80, 70, 60, 0, LIM)
    assert msg and "suma" in msg.lower()


@pytest.mark.parametrize("largo,ancho,alto,pista", [
    (10, 8, 5, "largo"),
    (12, 5, 5, "ancho"),
    ("12", "7", "0.3", "alto"),
])
def test_los_minimos_se_validan_de_verdad(largo, ancho, alto, pista):
    """11 x 6 x 0,4 cm. Debajo de eso el paquete no se despacha, y si el
    formulario lo deja cotizar el usuario paga por un envio imposible."""
    msg = policy.validar_paquete(1, largo, ancho, alto, 0, LIM)
    assert msg and pista in msg


def test_el_minimo_exacto_pasa():
    assert policy.validar_paquete(1, 11, 6, "0.4", 0, LIM) is None


def test_el_valor_declarado_tiene_techo():
    msg = policy.validar_paquete(5, 40, 30, 20, 5000, LIM)
    assert msg and "3000" in msg.replace(".", "")


def test_el_valor_declarado_no_puede_ser_negativo():
    assert policy.validar_paquete(5, 40, 30, 20, -1, LIM) is not None


@pytest.mark.parametrize("basura", [None, "", "abc", 0, -3, []])
def test_entradas_basura_devuelven_mensaje_y_no_lanzan(basura):
    msg = policy.validar_paquete(basura, 40, 30, 20, 0, LIM)
    assert isinstance(msg, str) and "mayor a 0" in msg
    msg = policy.validar_paquete(5, basura, 30, 20, 0, LIM)
    assert isinstance(msg, str) and "mayor a 0" in msg


def test_sin_limites_cargados_no_se_valida_nada_pero_tampoco_rompe():
    """Antes de que el panel tenga transportistas, validar_paquete no puede
    reventar: la que avisa que falta configurar es configuracion_incompleta()."""
    assert policy.validar_paquete(500, 300, 300, 300, 99999, {}) is None
    assert policy.validar_paquete(5, 40, 30, 20, 0, None) is None


# ─── 3. El payload que consume la pantalla ────────────────────────────────

def test_limites_payload_no_esconde_las_claves_ausentes():
    """Un limite que no existe viaja como null para que la pantalla sepa que ahi
    no hay nada que mostrar, en vez de tener que adivinarlo."""
    payload = policy.limites_payload(policy.limites_efectivos([TRP_VE]))
    assert payload["peso_max_kg"] == 70.0
    assert payload["largo_min_cm"] is None
    assert set(payload) == set(policy._MAXIMOS + policy._MINIMOS)


# ─── 4. Contenido ─────────────────────────────────────────────────────────

def test_la_descripcion_corta_se_rechaza():
    assert policy.validar_descripcion("ropa") is not None
    assert policy.validar_descripcion("   ") is not None
    assert policy.validar_descripcion(None) is not None
    assert policy.validar_descripcion("Dos pares de zapatillas") is None


def test_la_maquinaria_industrial_esta_en_la_lista_por_defecto():
    assert any("industrial" in c for c in policy.CATEGORIAS_PROHIBIDAS_POR_DEFECTO)


def test_la_lista_de_prohibidos_del_codigo_es_solo_una_semilla():
    """La lista que se aplica vive en la configuracion: cambia con un criterio de
    aduana y no puede depender de un deploy. Este modulo no la usa para decidir
    nada —solo la ofrece para poblar la configuracion la primera vez—, y este
    test se rompe el dia que alguien la convierta en la fuente de verdad."""
    fuente = open(os.path.join(_BACKEND, "services", "envios_policy.py"),
                  encoding="utf-8").read()
    usos = fuente.count("CATEGORIAS_PROHIBIDAS_POR_DEFECTO")
    assert usos == 1, "la semilla se está usando para validar; la lista real vive en la config"


def test_la_version_de_terminos_esta_declarada_y_es_versionable():
    """Los envios viejos apuntan a la version que el usuario acepto de verdad,
    asi que tiene que ser un identificador y no un booleano ni una fecha suelta."""
    assert isinstance(policy.TERMINOS_VERSION, str)
    assert policy.TERMINOS_VERSION.startswith("envios-")


# ─── 5. Avisos de configuracion incompleta ────────────────────────────────

TARIFA_OK = {"escalones_peso": [{"desde_kg": "0", "hasta_kg": "1", "precio": "45"}],
             "regla_peso": {"divisor": 5000, "escalon_kg": "0.5", "minimo_kg": "1.0"}}


def test_sistema_bien_configurado_no_tiene_avisos():
    assert policy.configuracion_incompleta([TRP_BR, TRP_VE], TARIFA_OK) == []


def test_falta_un_rol_o_la_tarifa():
    assert policy.configuracion_incompleta([TRP_BR], TARIFA_OK) != []
    assert policy.configuracion_incompleta([TRP_VE], TARIFA_OK) != []
    assert policy.configuracion_incompleta([TRP_BR, TRP_VE], None) != []
    assert policy.configuracion_incompleta([TRP_BR, TRP_VE], {"escalones_peso": []}) != []


def test_un_transportista_desactivado_no_cuenta():
    inactivo = dict(TRP_VE, activo=False)
    assert policy.configuracion_incompleta([TRP_BR, inactivo], TARIFA_OK) != []


def test_sin_nada_cargado_avisa_todo_junto():
    """Los tres roles que faltan y la tarifa, de una vez: el panel lo muestra en
    su portada, y la primera senal de que falta cargar algo no puede ser una
    cotizacion que devuelve 500 en la cara de un usuario."""
    assert len(policy.configuracion_incompleta([], None)) == 3


def test_una_tarifa_sin_divisor_volumetrico_es_configuracion_incompleta():
    """Sin divisor, un bulto grande y liviano cotiza como si pesara dos kilos."""
    sin_divisor = {"escalones_peso": TARIFA_OK["escalones_peso"],
                   "regla_peso": {"escalon_kg": "0.5", "minimo_kg": "1.0"}}
    assert any("divisor" in a for a in
               policy.configuracion_incompleta([TRP_BR, TRP_VE], sin_divisor))


# ─── 6. Regresiones de la revision ────────────────────────────────────────

def test_un_transportista_desactivado_no_restringe_el_formulario():
    """Un limite que sobrevive a la baja de la empresa que lo imponia es un
    limite que nadie puede explicar ni encontrar en el panel."""
    dado_de_baja = dict(TRP_ESTRICTO, activo=False)
    lim = policy.limites_efectivos([TRP_BR, TRP_VE, dado_de_baja])
    assert lim["peso_max_kg"] == Decimal("30")
    assert lim["lado_max_cm"] == Decimal("100")
    assert policy.quien_impone([TRP_BR, dado_de_baja], "peso_max_kg") == "TRP-7K2M"


@pytest.mark.parametrize("apagado", [False, 0, "", "false", "no"])
def test_desactivado_de_cualquier_forma_cuenta_como_desactivado(apagado):
    """bool("false") es True: si no se normaliza el string, un transportista
    dado de baja desde el panel sigue restringiendo."""
    baja = dict(TRP_ESTRICTO, activo=apagado)
    assert policy.limites_efectivos([TRP_BR, baja])["peso_max_kg"] == Decimal("30")


def test_un_transportista_sin_la_clave_activo_cuenta_como_activo():
    sin_flag = {"codigo": "TRP-9Z9Z", "limites": {"peso_max_kg": 10}}
    assert policy.limites_efectivos([TRP_BR, sin_flag])["peso_max_kg"] == Decimal("10")


def test_los_limites_pueden_venir_sin_convertir():
    """La firma invita a pasarle el dict del panel o los limites propios de la
    tarifa directo; comparar un Decimal contra el string "30" lanzaba TypeError."""
    crudos = {"peso_max_kg": "30", "lado_max_cm": "100"}
    assert policy.validar_paquete(5, 40, 30, 20, 0, crudos) is None
    assert policy.validar_paquete("30.5", 40, 30, 20, 0, crudos) is not None


def test_medidas_absurdas_se_rechazan_aunque_no_haya_nada_configurado():
    """Con el panel vacio no hay limites que validar, pero 1e40 kg no es un peso:
    dejarlo pasar es un 500 mas adelante en vez de un mensaje ahora."""
    assert policy.validar_paquete("1e40", 10, 10, 10, 0, {}) is not None
    assert policy.validar_paquete(5, "1e40", 10, 10, 0, {}) is not None
    assert policy.validar_paquete(5, 10, 10, 10, "1e40", {}) is not None


@pytest.mark.parametrize("roto", [float("nan"), float("inf"), "NaN", "Infinity", "abc"])
def test_un_limite_que_no_se_puede_comparar_no_tumba_la_interseccion(roto):
    """Comparar un Decimal NaN LANZA, a diferencia del float que devuelve False
    en silencio. Una ficha con un valor roto tumbaba la intersección entera, y
    con ella la ruta pública que la sirve."""
    malo = {"codigo": "TRP-XXXX", "activo": True, "limites": {"peso_max_kg": roto}}
    lim = policy.limites_efectivos([TRP_BR, malo])
    assert lim["peso_max_kg"] == Decimal("30")          # gana el que sí se puede leer
    assert policy.quien_impone([TRP_BR, malo], "peso_max_kg") == "TRP-7K2M"


def test_si_el_unico_limite_declarado_esta_roto_es_como_si_no_hubiera():
    malo = {"codigo": "TRP-XXXX", "activo": True, "limites": {"peso_max_kg": float("nan")}}
    assert "peso_max_kg" not in policy.limites_efectivos([malo])
