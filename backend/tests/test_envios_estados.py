"""
El ciclo de vida de un envio y el unico momento en que se mueve plata.

CONTEXTO
    Cotizar no cuesta nada. El precio se construye en DOS cobros, y cada uno se
    apoya en una medicion que no salio del usuario: el COBRO INICIAL contra el
    peso que registro el transportista de origen en el comprobante, y el AJUSTE
    contra la balanza propia en Pacaraima, que cobra la diferencia, la devuelve o
    no hace nada.

    Los estados dicen donde esta el paquete; la plata vive en el bloque `cobros`.
    Un cobro inicial impago no frena el paquete —ya esta viajando y no depende de
    nosotros—: lo que frena es la SALIDA de Pacaraima.

QUE SE CUBRE
    1. Toda transicion que no este en la tabla se rechaza, y ninguna sale de un
       estado terminal.
    2. Los actores se respetan: el usuario no puede marcar un envio como retirado
       en el mostrador, ni el sistema confirmar por el.
    3. Una partida impaga NO deja salir de Pacaraima, pero si se puede devolver,
       cancelar o retener: lo que se congela es el viaje, no la resolucion.
    4. El cobro inicial se calcula con el peso del COMPROBANTE, no con el
       declarado.
    5. Las tres ramas del ajuste contra ese cobro inicial, con sus bordes exactos
       de tolerancia -- incluida la que DEVUELVE, que es la que hace creible la
       palabra "inicial".
    6. Calcular con una tarifa distinta de la congelada es IMPOSIBLE: lanza.
    7. Confirmar el envio, postear, retirar y trasladar no mueven un centavo.

Los modulos son puros —no tocan red ni Mongo— asi que se cargan por ruta directa
para no arrastrar services/__init__.py, que importa twilio.
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
_cargar("envios_tarifas")
est = _cargar("envios_estados")


TARIFA = {
    "version_id": "tar_2026_09_a",
    "moneda": "RIS",
    "modo_tarifa": "peso",
    "regla_peso": {"divisor": 5000, "escalon_kg": "0.5", "minimo_kg": "1.0",
                   "umbral_cubado_kg": None},
    "escalones_peso": [
        {"desde_kg": "0.00", "hasta_kg": "1.00", "precio": "45.00"},
        {"desde_kg": "1.01", "hasta_kg": "3.00", "precio": "78.00"},
        {"desde_kg": "3.01", "hasta_kg": "5.00", "precio": "110.00"},
        {"desde_kg": "5.01", "hasta_kg": "10.00", "precio": "185.00"},
    ],
    "adicional_por_kg": "17.50",
    "margen": {"tipo": "porcentual", "valor": "0.20"},
}

# La tarifa que se publicó DESPUÉS de que el usuario pagó. Un 15 % más cara.
TARIFA_NUEVA = dict(TARIFA, version_id="tar_2026_10_a", escalones_peso=[
    {"desde_kg": "0.00", "hasta_kg": "1.00", "precio": "52.00"},
    {"desde_kg": "1.01", "hasta_kg": "3.00", "precio": "90.00"},
    {"desde_kg": "3.01", "hasta_kg": "5.00", "precio": "126.00"},
    {"desde_kg": "5.01", "hasta_kg": "10.00", "precio": "213.00"},
])


def envio(peso="2.30", largo=40, ancho=30, alto=20, cobrado="93.60",
          version="tar_2026_09_a", fecha="2026-09-01", bultos=1,
          peso_base="2.30", estado_inicial="pagado"):
    """Un envío con su cobro inicial ya emitido. 2,30 kg declarados, 40x30x20 ->
    cubado 4,8 -> 5,0 kg facturables -> escalón de 110,00 + 20 % = 132,00. El
    monto del cobro inicial se pasa a mano para poder mover cada rama."""
    return {
        "envio_id": "env_test",
        "paquete": {"peso_kg": peso, "largo_cm": largo, "ancho_cm": ancho,
                    "alto_cm": alto, "valor_declarado": 0, "bultos": bultos},
        "cotizacion": {"tarifa_version": version, "es_estimado": True,
                       "fecha": fecha, "peso_facturable_kg": "2.50"},
        "origen": {"codigo_objeto": "AA123456789BR"},
        "cobros": {"inicial": {"monto_ris": cobrado, "base": "comprobante",
                               "peso_base_kg": peso_base, "estado": estado_inicial}},
    }


# ─── 1. La tabla de transiciones ──────────────────────────────────────────

def test_el_camino_feliz_completo_es_valido():
    camino = [("cotizado", "esperando_postagem", "user"),
              ("esperando_postagem", "en_transito_origen", "user"),
              ("en_transito_origen", "disponible_retiro", "system"),
              ("disponible_retiro", "recibido_pacaraima", "admin"),
              ("recibido_pacaraima", "repesado", "admin"),
              ("repesado", "en_transito_int", "system"),
              ("en_transito_int", "entregado_transportista", "admin")]
    for desde, hacia, actor in camino:
        assert est.puede_transicionar(desde, hacia, actor) is None, f"{desde}->{hacia}"


@pytest.mark.parametrize("desde,hacia", [
    ("cotizado", "repesado"),            # saltarse el viaje entero
    ("cotizado", "en_transito_int"),     # cruzar sin que el paquete exista
    ("cotizado", "entregado_transportista"),
    ("recibido_pacaraima", "en_transito_int"),   # trasladar sin repesar
    ("disponible_retiro", "repesado"),   # repesar sin haberlo retirado
    ("en_transito_int", "repesado"),     # volver a pesar en el camino
])
def test_los_atajos_se_rechazan(desde, hacia):
    assert est.puede_transicionar(desde, hacia, "admin") is not None


def test_el_conjunto_de_actores_por_defecto_es_solo_el_operador():
    """Si el default se aflojara, el usuario podría declarar el peso de su propio
    paquete: recibido_pacaraima -> repesado no tiene entrada propia en ACTORES."""
    assert est.ACTOR_POR_DEFECTO == frozenset({"admin"})
    for actor in ("user", "system"):
        assert est.puede_transicionar("recibido_pacaraima", "repesado", actor) is not None


@pytest.mark.parametrize("desde,hacia,esperado", [
    ("cotizado", "esperando_postagem", {"user"}),
    ("disponible_retiro", "recibido_pacaraima", {"admin"}),
    ("esperando_postagem", "en_transito_origen", {"user"}),
    ("repesado", "pago_pendiente", {"system"}),
    ("recibido_pacaraima", "repesado", {"admin"}),
])
def test_el_conjunto_exacto_de_actores(desde, hacia, esperado):
    """El conjunto completo, no "este sí y este no": relajar un permiso sin que
    ningún test lo note es como se abren los agujeros de autorización."""
    assert set(est.actores_de(desde, hacia)) == esperado


def test_un_actor_inventado_se_rechaza():
    assert est.puede_transicionar("cotizado", "esperando_postagem", "root") is not None
    assert est.puede_transicionar("cotizado", "esperando_postagem", "") is not None


@pytest.mark.parametrize("terminal", sorted(est.TERMINALES))
def test_de_un_terminal_no_sale_nada(terminal):
    assert est.TRANSICIONES[terminal] == set()
    for hacia in est.TRANSICIONES:
        if hacia != terminal:
            msg = est.puede_transicionar(terminal, hacia, "admin")
            assert msg is not None and "terminal" in msg


def test_no_se_puede_transicionar_al_mismo_estado():
    assert est.puede_transicionar("repesado", "repesado", "admin") is not None


@pytest.mark.parametrize("estado", ["", None, "en_camino", "PAGADO", "entregado"])
def test_un_estado_inventado_se_rechaza_y_no_revienta(estado):
    assert est.puede_transicionar(estado, "repesado", "admin") is not None
    assert est.puede_transicionar("repesado", estado, "admin") is not None


def test_la_tabla_no_apunta_a_estados_que_no_existen():
    """Un destino mal tipeado en la tabla es un envío que no puede avanzar y
    nadie entiende por qué."""
    for desde, destinos in est.TRANSICIONES.items():
        assert desde in est.ESTADOS, desde
        for hacia in destinos:
            assert hacia in est.TRANSICIONES, f"{desde} -> {hacia}"


def test_todos_los_estados_estan_documentados():
    assert set(est.ESTADOS) == set(est.TRANSICIONES)


def test_todo_estado_no_terminal_tiene_salida():
    """Un estado sin salida que no está declarado terminal es una trampa: el
    envío entra y no vuelve a moverse nunca."""
    for estado, destinos in est.TRANSICIONES.items():
        if estado not in est.TERMINALES:
            assert destinos, f"{estado} no tiene salida y no es terminal"


# ─── 2. Los actores ───────────────────────────────────────────────────────

def test_el_usuario_no_puede_marcar_que_su_paquete_fue_retirado():
    """El retiro en el mostrador lo hace el equipo, con foto. Que lo declare el
    usuario sería dejarle mover el estado que dispara el traslado."""
    assert est.puede_transicionar("disponible_retiro", "recibido_pacaraima", "user") is not None
    assert est.puede_transicionar("disponible_retiro", "recibido_pacaraima", "admin") is None


def test_solo_el_usuario_avisa_que_desposto():
    """Sin API de rastreo, el comprobante de despacho solo puede venir de él."""
    assert est.puede_transicionar("esperando_postagem", "en_transito_origen", "user") is None
    assert est.puede_transicionar("esperando_postagem", "en_transito_origen", "admin") is not None


def test_el_sistema_no_confirma_por_el_usuario():
    """Confirmar no cuesta nada, pero es una aceptación de condiciones: la tiene
    que dar él."""
    assert est.puede_transicionar("cotizado", "esperando_postagem", "system") is not None
    assert est.puede_transicionar("cotizado", "esperando_postagem", "user") is None


def test_la_devolucion_por_guarda_vencida_la_dispara_el_sistema():
    assert est.puede_transicionar("disponible_retiro", "devuelto", "system") is None
    assert est.puede_transicionar("disponible_retiro", "devuelto", "user") is not None


def test_los_actores_declarados_apuntan_a_transiciones_que_existen():
    for (desde, hacia) in est.ACTORES:
        assert hacia in est.TRANSICIONES.get(desde, set()), f"{desde} -> {hacia}"


# ─── 3. La diferencia impaga congela el avance ────────────────────────────

def test_con_partida_impaga_el_paquete_no_sale_de_pacaraima():
    """Puede ser el cobro inicial o el ajuste: los dos frenan la salida, y es la
    única palanca de cobro que el negocio puede ejecutar de verdad."""
    msg = est.puede_transicionar("repesado", "en_transito_int", "system", partida_impaga=True)
    assert msg is not None and "salde" in msg
    assert est.puede_transicionar("pago_pendiente", "en_transito_int", "system",
                                 partida_impaga=True) is not None


def test_pero_si_se_puede_resolver_el_problema():
    """Lo que se congela es el viaje, no la salida: un paquete con deuda igual
    se puede devolver, cancelar o retener. Si no, queda encallado para siempre."""
    for hacia, actor in (("devuelto", "admin"), ("cancelado", "admin")):
        assert est.puede_transicionar("pago_pendiente", hacia, actor,
                                      partida_impaga=True) is None
    assert est.puede_transicionar("repesado", "retenido", "admin",
                                  partida_impaga=True) is None


def test_sin_deuda_avanza_normal():
    assert est.puede_transicionar("repesado", "en_transito_int", "system",
                                 partida_impaga=False) is None


# ─── 4. El efecto monetario: la invariante 1 ──────────────────────────────

# La lista COMPLETA y literal de las aristas que tocan el saldo. Está escrita a
# mano a propósito: derivarla de TRANSICIONES haría que agregar una transición
# que mueve plata pase inadvertida, que es exactamente lo que hay que impedir.
ARISTAS_CON_PLATA = {
    # El COBRO INICIAL no está acá y es correcto que no esté: no es una
    # transición. Se emite mientras el envío está en en_transito_origen, al
    # verificarse el comprobante, y el paquete sigue viajando pase lo que pase
    # con esa deuda.
    ("repesado", "en_transito_int"),            # el ajuste del repesaje
    ("pago_pendiente", "en_transito_int"),      # la diferencia saldada
    ("cotizado", "cancelado"), ("en_transito_origen", "cancelado"),
    ("esperando_postagem", "cancelado"), ("pago_pendiente", "cancelado"),
    ("disponible_retiro", "devuelto"), ("recibido_pacaraima", "devuelto"),
    ("repesado", "devuelto"), ("pago_pendiente", "devuelto"),
    ("retenido", "devuelto"),
    ("en_transito_origen", "siniestrado"), ("disponible_retiro", "siniestrado"),
    ("recibido_pacaraima", "siniestrado"), ("repesado", "siniestrado"),
    ("pago_pendiente", "siniestrado"), ("en_transito_int", "siniestrado"),
    ("retenido", "siniestrado"),
}


def test_el_saldo_se_mueve_solo_donde_dice_la_invariante():
    """Recorre la tabla ENTERA contra una lista escrita a mano. Es la forma de
    que agregar un débito nuevo por descuido rompa un test, en vez de
    descubrirse en el cierre del mes."""
    mueven = {(d, h) for d, destinos in est.TRANSICIONES.items() for h in destinos
              if est.mueve_saldo(d, h)}
    assert mueven == ARISTAS_CON_PLATA


@pytest.mark.parametrize("desde,hacia", [
    ("cotizado", "esperando_postagem"),             # confirmar no mueve saldo
    ("esperando_postagem", "en_transito_origen"),   # postear tampoco
    ("en_transito_origen", "disponible_retiro"),
    ("disponible_retiro", "recibido_pacaraima"),
    ("recibido_pacaraima", "repesado"),             # pesar tampoco: el cobro es al salir
    ("en_transito_int", "entregado_transportista"),
    ("retenido", "en_transito_int"),
])
def test_la_logistica_no_toca_la_plata(desde, hacia):
    assert est.efecto_monetario(desde, hacia) == "ninguno"


def test_los_transportistas_no_aparecen_en_ningun_efecto():
    """Ni el de Brasil ni el de Venezuela mueven el saldo: los paga el usuario."""
    assert est.efecto_monetario("esperando_postagem", "en_transito_origen") == "ninguno"
    assert est.efecto_monetario("en_transito_int", "entregado_transportista") == "ninguno"


def test_todo_camino_a_un_terminal_infeliz_devuelve_plata():
    for hacia in ("cancelado", "devuelto", "siniestrado"):
        for desde, destinos in est.TRANSICIONES.items():
            if hacia in destinos:
                assert est.efecto_monetario(desde, hacia) == "reembolso"


def test_preguntar_por_una_transicion_que_no_existe_es_un_error():
    """Contestar "ninguno" sobre un camino imposible da una falsa sensación de
    cobertura: un test puede recorrer pares inventados y concluir que todo bien."""
    for par in [("xxx", "devuelto"), ("entregado_transportista", "cancelado"),
                ("cancelado", "siniestrado"), ("cotizado", "repesado")]:
        with pytest.raises(ValueError):
            est.efecto_monetario(*par)


def test_todo_efecto_declarado_es_uno_de_los_conocidos():
    for (d, h) in est.EFECTOS:
        assert est.EFECTOS[(d, h)] in est.EFECTOS_POSIBLES
        assert h in est.TRANSICIONES.get(d, set()), f"{d} -> {h}"


# ─── 5. El ajuste del repesaje ────────────────────────────────────────────

def test_la_caja_que_pesa_lo_declarado_no_genera_ajuste():
    """2,30 kg y 40x30x20 -> 5,0 kg facturables -> 110 + 20 % = 132,00."""
    a = est.ajuste_por_repesaje(envio(cobrado="132.00"), TARIFA,
                                "2.30", 40, 30, 20)
    assert a["total_final"] == Decimal("132.00")
    assert a["diferencia"] == Decimal("0.00")
    assert a["rama"] == "sin_ajuste"


def test_rama_a_una_diferencia_chica_se_ignora():
    """Generar un cobro de un peso cuesta más en soporte de lo que recauda."""
    a = est.ajuste_por_repesaje(envio(cobrado="130.50"), TARIFA, "2.30", 40, 30, 20)
    assert a["diferencia"] == Decimal("1.50")
    assert a["rama"] == "sin_ajuste"


@pytest.mark.parametrize("cobrado,esperada", [("130.00", "2.00"), ("134.00", "-2.00")])
def test_el_borde_exacto_de_la_tolerancia_no_ajusta(cobrado, esperada):
    a = est.ajuste_por_repesaje(envio(cobrado=cobrado), TARIFA, "2.30", 40, 30, 20)
    assert a["diferencia"] == Decimal(esperada)
    assert a["rama"] == "sin_ajuste"


@pytest.mark.parametrize("cobrado,rama", [("129.99", "cobrar"), ("134.01", "devolver")])
def test_un_centavo_mas_alla_de_la_tolerancia_si_ajusta(cobrado, rama):
    assert est.ajuste_por_repesaje(envio(cobrado=cobrado), TARIFA,
                                   "2.30", 40, 30, 20)["rama"] == rama


def test_rama_b_el_paquete_peso_mas_de_lo_declarado():
    """Declaró 2,30 kg pero pesó 6 kg: sube dos escalones."""
    a = est.ajuste_por_repesaje(envio(cobrado="132.00"), TARIFA, 6, 40, 30, 20)
    assert a["total_final"] == Decimal("222.00")     # 185 + 20 %
    assert a["diferencia"] == Decimal("90.00")
    assert a["rama"] == "cobrar"


def test_rama_c_el_paquete_era_mas_chico_y_se_reembolsa():
    a = est.ajuste_por_repesaje(envio(cobrado="132.00"), TARIFA, "0.8", 15, 10, 8)
    assert a["total_final"] == Decimal("54.00")      # 45 + 20 %
    assert a["diferencia"] == Decimal("-78.00")
    assert a["rama"] == "devolver"


def test_el_ajuste_trae_el_desglose_completo_y_no_un_monto_suelto():
    """"Declaraste 2,30 kg y 40x30x20; al pesarlo dio 2,65 y 41x30x21." Un ajuste
    sin desglose es un reclamo garantizado."""
    e = envio(cobrado="132.00", peso_base="2.30")
    a = est.ajuste_por_repesaje(e, TARIFA, "2.65", 41, 30, 21)
    d = a["desglose"]
    assert d["comprobante"]["peso_kg"] == Decimal("2.30")
    assert d["comprobante"]["monto_ris"] == Decimal("132.00")
    assert d["verificado"]["peso_kg"] == Decimal("2.65")
    assert d["verificado"]["largo_cm"] == Decimal("41")
    assert d["verificado"]["peso_facturable_kg"] > 0
    assert d["codigo_objeto"] == "AA123456789BR"
    assert d["cotizacion_nueva"]["base"] > 0


def test_una_tolerancia_configurada_se_respeta():
    grande = est.ajuste_por_repesaje(envio(cobrado="120.00"), TARIFA, "2.30", 40, 30, 20,
                                     tolerancia="20.00")
    chica = est.ajuste_por_repesaje(envio(cobrado="120.00"), TARIFA, "2.30", 40, 30, 20,
                                    tolerancia="1.00")
    assert grande["rama"] == "sin_ajuste"
    assert chica["rama"] == "cobrar"
    assert grande["diferencia"] == chica["diferencia"] == Decimal("12.00")


# ─── 6. El bug más caro del módulo ────────────────────────────────────────

def test_recalcular_con_la_tarifa_vigente_es_imposible():
    """El escenario exacto de §4.3: el usuario cotizó el 1 de septiembre, pagó, y
    el 5 se publicó una tarifa 15 % más cara. Cobrarle esa suba disfrazada de
    ajuste por peso es el error más costoso del módulo, y es invisible: no falla
    ningún test obvio, no tira excepción, y aparece como una avalancha de
    reclamos. Acá tira excepción."""
    with pytest.raises(est.TarifaEquivocada) as e:
        est.ajuste_por_repesaje(envio(), TARIFA_NUEVA, "2.30", 40, 30, 20)
    assert "tar_2026_09_a" in str(e.value) and "tar_2026_10_a" in str(e.value)


def test_con_la_tarifa_congelada_el_aumento_posterior_no_lo_paga_el_usuario():
    """La misma caja, cotizada con la tarifa vieja: el ajuste es 0 aunque la
    lista haya subido un 15 %."""
    a = est.ajuste_por_repesaje(envio(cobrado="132.00"), TARIFA, "2.30", 40, 30, 20)
    assert a["diferencia"] == Decimal("0.00")
    assert a["tarifa_version"] == "tar_2026_09_a"


def test_un_envio_sin_version_congelada_no_se_recalcula():
    """Sin saber con qué precios se cotizó, cualquier recálculo es adivinar cuál
    era el trato. Se bloquea el repesaje de ese envío y lo mira una persona; la
    alternativa —recalcular con lo que haya— es cobrarle precios que no aceptó."""
    sin_version = envio(cobrado="132.00")
    sin_version["cotizacion"].pop("tarifa_version")
    with pytest.raises(est.EnvioIncompleto):
        est.ajuste_por_repesaje(sin_version, TARIFA, "2.30", 40, 30, 20)


def test_el_ajuste_no_dice_a_que_estado_va():
    """Tener dos funciones del módulo contestando "el próximo estado" es cómo un
    paquete termina viajando con la deuda encima: el que mira el saldo es
    estado_tras_ajuste(), y es el único que puede saberlo."""
    a = est.ajuste_por_repesaje(envio(cobrado="132.00"), TARIFA, 6, 40, 30, 20)
    assert "estado_siguiente" not in a
    assert a["rama"] == "cobrar"


# ─── 7. A dónde va el envío según el saldo ────────────────────────────────

def test_si_el_saldo_alcanza_el_paquete_sigue_viaje():
    a = est.ajuste_por_repesaje(envio(cobrado="132.00"), TARIFA, 6, 40, 30, 20)
    assert est.estado_tras_ajuste(a, "90.00") == "en_transito_int"
    assert est.estado_tras_ajuste(a, "1000") == "en_transito_int"


def test_si_no_alcanza_queda_en_pago_pendiente():
    a = est.ajuste_por_repesaje(envio(cobrado="132.00"), TARIFA, 6, 40, 30, 20)
    assert est.estado_tras_ajuste(a, "89.99") == "pago_pendiente"
    assert est.estado_tras_ajuste(a, 0) == "pago_pendiente"


def test_un_reembolso_nunca_deja_el_envio_pendiente():
    """Un envío al que hay que devolverle plata no puede quedar frenado por no
    tener saldo: es al revés."""
    a = est.ajuste_por_repesaje(envio(cobrado="132.00"), TARIFA, "0.8", 15, 10, 8)
    assert est.estado_tras_ajuste(a, 0) == "en_transito_int"


# ─── 8. Datos rotos: nunca un cero silencioso ─────────────────────────────
#
# Los ceros de consuelo son simétricos y feos en los dos sentidos: un cobrado
# ilegible hace que el usuario pague el envío dos veces, y un peso verificado en
# blanco le devuelve plata que nadie le debía. Las dos cosas pasan en silencio y
# ninguna se reclama, así que acá se lanza.

@pytest.mark.parametrize("cobrado", ["132,00", "R$ 132.00", "", "  ", "abc",
                                     None, [], {}, "0", "-5"])
def test_un_cobrado_ilegible_no_cobra_el_envio_dos_veces(cobrado):
    """Sin esta guarda, "132,00" con coma se lee como 0, la diferencia da el
    precio entero, y se le cobra el envío completo por segunda vez."""
    roto = envio()
    roto["cobros"]["inicial"]["monto_ris"] = cobrado
    with pytest.raises(est.EnvioIncompleto):
        est.ajuste_por_repesaje(roto, TARIFA, "2.30", 40, 30, 20)


def test_sin_bloque_de_cobros_tampoco_se_recalcula():
    roto = envio()
    roto.pop("cobros")
    with pytest.raises(est.EnvioIncompleto):
        est.ajuste_por_repesaje(roto, TARIFA, "2.30", 40, 30, 20)


@pytest.mark.parametrize("peso", ["6,5", "", "abc", None, 0, -5, "0", 5000])
def test_un_peso_verificado_invalido_no_genera_un_reembolso(peso):
    """Una balanza que devuelve 0, un campo en blanco o la coma decimal tipeada
    por el operador: los tres reembolsaban en silencio."""
    with pytest.raises(est.EnvioIncompleto):
        est.ajuste_por_repesaje(envio(cobrado="132.00"), TARIFA, peso, 40, 30, 20)


@pytest.mark.parametrize("indice", [0, 1, 2])
def test_una_medida_verificada_invalida_tampoco(indice):
    dims = [40, 30, 20]
    dims[indice] = 0
    with pytest.raises(est.EnvioIncompleto):
        est.ajuste_por_repesaje(envio(cobrado="132.00"), TARIFA, "2.30", *dims)


@pytest.mark.parametrize("tarifa", [None, {}, {"version_id": "tar_2026_09_a"},
                                    {"version_id": "tar_2026_09_a", "escalones_peso": []}])
def test_una_tarifa_vacia_no_reembolsa_todo_lo_pagado(tarifa):
    """Sin tabla de escalones el total da 0 y la diferencia es todo lo cobrado."""
    with pytest.raises((est.EnvioIncompleto, est.TarifaEquivocada)):
        est.ajuste_por_repesaje(envio(cobrado="132.00"), tarifa, "2.30", 40, 30, 20)


@pytest.mark.parametrize("tol", ["", "abc", -1, "-2"])
def test_una_tolerancia_invalida_se_rechaza(tol):
    """`None` es el default; basura no. Sin esto, tolerancia None daba 0 y una
    diferencia de cincuenta centavos generaba un cobro."""
    with pytest.raises(est.EnvioIncompleto):
        est.ajuste_por_repesaje(envio(cobrado="132.00"), TARIFA, "2.30", 40, 30, 20,
                                tolerancia=tol)


def test_tolerancia_none_usa_el_default():
    a = est.ajuste_por_repesaje(envio(cobrado="131.00"), TARIFA, "2.30", 40, 30, 20,
                                tolerancia=None)
    assert a["tolerancia"] == est.TOLERANCIA_POR_DEFECTO
    assert a["rama"] == "sin_ajuste"


def test_el_desglose_cierra_con_la_resta_que_ve_el_usuario():
    """Mostrar 130,00 y 132,00 con una diferencia de 2,01 es un ticket de soporte
    asegurado. Lo cobrado se redondea ANTES de restar, no después."""
    a = est.ajuste_por_repesaje(envio(cobrado="129.995"), TARIFA, "2.30", 40, 30, 20)
    assert a["total_final"] - a["cobrado_inicial"] == a["diferencia"]


# ─── 9. Lo que se congela, y por qué ──────────────────────────────────────

TARIFA_CON_TEMPORADA = dict(TARIFA, recargos_temporada=[
    {"nombre": "Diciembre", "desde": "2026-12-01", "hasta": "2026-12-31",
     "multiplicador": "1.30", "activo": True}])


def test_el_recargo_de_temporada_no_se_cuela_como_ajuste_por_peso():
    """El mismo bug de §4.3 pero SIN cambiar de versión: si el recálculo usara la
    fecha del mostrador, un paquete cotizado en septiembre y repesado en
    diciembre pagaría el 30 % de recargo navideño como si fuera peso."""
    e = envio(cobrado="132.00", fecha="2026-09-01")
    a = est.ajuste_por_repesaje(e, TARIFA_CON_TEMPORADA, "2.30", 40, 30, 20)
    assert a["total_final"] == Decimal("132.00")
    assert a["rama"] == "sin_ajuste"


def test_y_al_reves_tampoco_se_le_devuelve_de_mas():
    """Cotizado en diciembre con el recargo: al repesarlo en enero el recargo
    sigue valiendo, porque es el precio que él aceptó."""
    e = envio(cobrado="171.60", fecha="2026-12-20")
    a = est.ajuste_por_repesaje(e, TARIFA_CON_TEMPORADA, "2.30", 40, 30, 20)
    assert a["total_final"] == Decimal("171.60")
    assert a["rama"] == "sin_ajuste"


TARIFA_CON_DESCUENTO = dict(TARIFA, descuentos_cantidad=[
    {"desde_bultos": 3, "descuento": "0.10"}])


def test_el_descuento_por_cantidad_no_se_pierde_en_el_recalculo():
    """Cotizó 5 bultos con 10 % de descuento y pagó 118,80. Si el recálculo
    olvidara los bultos, aparecería un cargo de 13,20 salido de la nada."""
    e = envio(cobrado="118.80", bultos=5)
    a = est.ajuste_por_repesaje(e, TARIFA_CON_DESCUENTO, "2.30", 40, 30, 20)
    assert a["total_final"] == Decimal("118.80")
    assert a["rama"] == "sin_ajuste"


def test_los_parametros_comerciales_no_los_pone_quien_llama():
    """No hay forma de que una ruta distraída pase bultos o valor declarado
    distintos de los que el usuario aceptó: la firma no los acepta."""
    import inspect
    parametros = set(inspect.signature(est.ajuste_por_repesaje).parameters)
    assert not (parametros & {"bultos", "valor_declarado", "fecha"})


# ─── 10. El precio se cierra o el paquete no viaja ────────────────────────

def test_un_paquete_retenido_antes_de_pesarse_no_puede_salir_sin_repesar():
    """recibido_pacaraima -> retenido -> en_transito_int esquivaba el único punto
    de cobro del módulo: el envío viajaba con el precio todavía estimado."""
    assert est.puede_transicionar("retenido", "en_transito_int", "admin",
                                  precio_cerrado=False) is not None
    assert est.puede_transicionar("retenido", "repesado", "admin",
                                  precio_cerrado=False) is None
    assert est.puede_transicionar("retenido", "en_transito_int", "admin",
                                  precio_cerrado=True) is None


def test_la_deuda_impaga_tambien_bloquea_la_entrega_final():
    assert est.puede_transicionar("en_transito_int", "entregado_transportista", "admin",
                                  partida_impaga=True) is not None


def test_el_paquete_se_puede_perder_mientras_lo_tenemos_nosotros():
    """Es el único tramo donde el responsable somos nosotros. Sin la transición,
    un paquete roto en el depósito había que sacarlo como devuelto: mentir en el
    estado y cerrarle la puerta a la indemnización."""
    for desde in ("recibido_pacaraima", "repesado", "pago_pendiente"):
        assert est.puede_transicionar(desde, "siniestrado", "admin") is None
        assert est.efecto_monetario(desde, "siniestrado") == "reembolso"


def test_un_envio_con_deuda_igual_se_puede_retener_o_declarar_siniestrado():
    """Si aduana lo incauta mientras el usuario junta el saldo, el operador no
    puede quedar obligado a mentir en el estado."""
    for hacia in ("retenido", "siniestrado", "devuelto"):
        assert est.puede_transicionar("pago_pendiente", hacia, "admin",
                                      partida_impaga=True) is None


# ─── 11. El saldo, en el borde ────────────────────────────────────────────

def test_el_saldo_justo_alcanza():
    a = est.ajuste_por_repesaje(envio(cobrado="132.00"), TARIFA, 6, 40, 30, 20)
    assert a["diferencia"] == Decimal("90.00")
    assert est.estado_tras_ajuste(a, "90.00") == "en_transito_int"
    assert est.estado_tras_ajuste(a, "89.99") == "pago_pendiente"


@pytest.mark.parametrize("saldo", ["0", "10.00", "89.99"])
def test_cualquier_saldo_insuficiente_deja_el_envio_pendiente(saldo):
    a = est.ajuste_por_repesaje(envio(cobrado="132.00"), TARIFA, 6, 40, 30, 20)
    assert est.estado_tras_ajuste(a, saldo) == "pago_pendiente"


TARIFA_CON_SOBRECARGO = dict(TARIFA, sobrecargos=[
    {"codigo": "valor_declarado", "tipo": "porcentual", "valor": "0.02", "activo": True,
     "condicion": {"valor_declarado_mayor_a": 500}}])


def test_el_valor_declarado_tampoco_se_pierde_en_el_recalculo():
    """Cotizó con 1.000 declarados y pagó el sobrecargo del 2 %. Si el recálculo
    lo olvidara, el total bajaría y se le devolvería plata que sí correspondía
    cobrar — el mismo error que el descuento por cantidad, al revés."""
    e = envio(cobrado="134.64")          # 110 + 2,20 de sobrecargo, + 20 %
    e["paquete"]["valor_declarado"] = 1000
    a = est.ajuste_por_repesaje(e, TARIFA_CON_SOBRECARGO, "2.30", 40, 30, 20)
    assert a["total_final"] == Decimal("134.64")
    assert a["rama"] == "sin_ajuste"


def test_el_desglose_no_puede_mostrar_lo_verificado_como_declarado():
    """Es la mentira más fácil de cometer y la más difícil de ver: el usuario
    lee "declaraste 2,65 kg" cuando declaró 2,30, y el ajuste parece justo."""
    e = envio(peso="2.30", largo=40, ancho=30, alto=20, cobrado="132.00", peso_base="2.30")
    a = est.ajuste_por_repesaje(e, TARIFA, "6.10", 41, 31, 21)
    d = a["desglose"]
    assert d["comprobante"]["peso_kg"] == Decimal("2.30")
    assert d["verificado"]["peso_kg"] == Decimal("6.10")
    assert d["verificado"]["peso_facturable_kg"] == Decimal("6.500")
    assert d["comprobante"]["peso_kg"] != d["verificado"]["peso_kg"]


# ─── 12. El cobro inicial, contra el comprobante ──────────────────────────

def envio_sin_cobrar(**kw):
    """Un envío que despachó y todavía no tiene cobro inicial emitido."""
    e = envio(**kw)
    e["cobros"] = {}
    return e


def test_el_cobro_inicial_usa_el_peso_del_comprobante_y_no_el_declarado():
    """Es la razón de ser de este cobro: el comprobante trae el peso por el que
    un tercero YA le cobró al usuario, medido por alguien sin ningún interés en
    que sea bajo. Lo declarado es una estimación de buena fe; esto es un dato."""
    e = envio_sin_cobrar(peso="1.00", largo=10, ancho=10, alto=10)
    c = est.cobro_inicial(e, TARIFA, "6.00", 40, 30, 20)
    assert c["peso_base_kg"] == Decimal("6.000")
    assert c["base"] == "comprobante"
    assert c["monto"] == Decimal("222.00")          # escalón de 10 kg + 20 %
    # Con lo declarado habría salido el escalón de 1 kg: 45 + 20 % = 54,00.
    assert c["desglose"]["declarado"]["peso_kg"] == Decimal("1.00")


def test_el_cobro_inicial_muestra_lo_declarado_al_lado_de_lo_del_comprobante():
    """Sin esa comparación, el usuario no entiende por qué el número cambió."""
    d = est.cobro_inicial(envio_sin_cobrar(), TARIFA, "2.65", 41, 30, 21)["desglose"]
    assert d["declarado"]["peso_kg"] == Decimal("2.30")
    assert d["comprobante"]["peso_kg"] == Decimal("2.65")
    assert d["comprobante"]["peso_facturable_kg"] > 0


def test_el_cobro_inicial_tambien_usa_la_tarifa_congelada():
    with pytest.raises(est.TarifaEquivocada):
        est.cobro_inicial(envio_sin_cobrar(), TARIFA_NUEVA, "2.65", 41, 30, 21)


def test_el_cobro_inicial_respeta_los_parametros_comerciales_del_envio():
    """Los bultos y el valor declarado salen del envío, no de quien llama: son
    parte de lo que el usuario aceptó."""
    import inspect
    parametros = set(inspect.signature(est.cobro_inicial).parameters)
    assert not (parametros & {"bultos", "valor_declarado", "fecha", "zona"})

    tarifa = dict(TARIFA, descuentos_cantidad=[{"desde_bultos": 3, "descuento": "0.10"}])
    con_descuento = est.cobro_inicial(envio_sin_cobrar(bultos=5), tarifa, "2.30", 40, 30, 20)
    sin_descuento = est.cobro_inicial(envio_sin_cobrar(bultos=1), tarifa, "2.30", 40, 30, 20)
    assert con_descuento["monto"] < sin_descuento["monto"]


@pytest.mark.parametrize("peso", ["2,65", "", "abc", None, 0, -5, 5000])
def test_un_peso_de_comprobante_ilegible_no_emite_un_cobro_de_cero(peso):
    """El criterio opuesto al de envios_tarifas: acá hay un paquete despachado y
    un cobro real. Un dato ilegible es un envío roto, no una imprecisión."""
    with pytest.raises(est.EnvioIncompleto):
        est.cobro_inicial(envio_sin_cobrar(), TARIFA, peso, 40, 30, 20)


def test_el_cobro_inicial_no_depende_del_destino():
    import inspect
    parametros = set(inspect.signature(est.cobro_inicial).parameters)
    assert not (parametros & {"zona_destino", "destino", "estado_ve", "transportista"})


# ─── 13. El ajuste se calcula contra el cobro inicial ─────────────────────

def test_el_ajuste_compara_contra_el_cobro_inicial_y_no_contra_el_estimado():
    """Es el encadenamiento de los dos cobros: lo que se emitió contra el
    comprobante es lo que el ajuste tiene que corregir."""
    e = envio_sin_cobrar()
    c = est.cobro_inicial(e, TARIFA, "2.30", 40, 30, 20)
    e["cobros"] = {"inicial": {"monto_ris": c["monto"], "peso_base_kg": c["peso_base_kg"],
                               "estado": "pagado"}}
    a = est.ajuste_por_repesaje(e, TARIFA, "2.30", 40, 30, 20)
    assert a["cobrado_inicial"] == c["monto"]
    assert a["diferencia"] == Decimal("0.00")
    assert a["rama"] == "sin_ajuste"


def test_sin_cobro_inicial_el_ajuste_no_cobra_el_precio_entero_otra_vez():
    for cobros in ({}, {"inicial": {}}, {"inicial": {"monto_ris": None}},
                   {"inicial": {"monto_ris": "0"}}):
        e = envio()
        e["cobros"] = cobros
        with pytest.raises(est.EnvioIncompleto):
            est.ajuste_por_repesaje(e, TARIFA, "2.30", 40, 30, 20)


def test_la_rama_que_devuelve_es_la_que_hace_creible_la_palabra_inicial():
    """Si el sistema solo cobrara de más y nunca devolviera, el cobro inicial
    sería un anticipo disfrazado."""
    a = est.ajuste_por_repesaje(envio(cobrado="222.00"), TARIFA, "2.30", 40, 30, 20)
    assert a["rama"] == "devolver"
    assert a["diferencia"] < 0
    assert a["total_final"] == Decimal("132.00")
    assert est.estado_tras_ajuste(a, 0) == "en_transito_int"


# ─── 14. Las partidas: la deuda vive en el envío ──────────────────────────

def test_partidas_impagas_lee_del_envio_y_no_del_estado():
    e = envio(estado_inicial="pendiente")
    assert est.partidas_impagas(e) == ["inicial"]
    e["cobros"]["inicial"]["estado"] = "pagado"
    assert est.partidas_impagas(e) == []
    e["cobros"]["ajuste"] = {"monto_ris": "6.70", "estado": "pendiente"}
    assert est.partidas_impagas(e) == ["ajuste"]


def test_una_partida_sin_estado_cuenta_como_pendiente():
    """El que emite un cobro tiene que decir cómo quedó. Ante la duda, se debe."""
    e = envio()
    e["cobros"]["inicial"].pop("estado")
    assert est.partidas_impagas(e) == ["inicial"]


def test_un_envio_sin_cobros_no_debe_nada():
    assert est.partidas_impagas({}) == []
    assert est.partidas_impagas({"cobros": {}}) == []
    assert est.partidas_impagas(None) == []


def test_no_hay_una_tercera_partida_escondida():
    """Si alguien agrega un cobro nuevo, tiene que aparecer acá o no se va a
    contar como deuda en ningún lado."""
    assert est.PARTIDAS == ("inicial", "ajuste")


# ─── 15. El flete bloquea la entrega, no la salida ────────────────────────

def test_el_flete_impago_frena_la_entrega_pero_no_el_viaje():
    """El paquete sale de Pacaraima con el servicio pago; lo que espera por el
    flete es la entrega en el mostrador, con el paquete ya en Santa Elena."""
    assert est.puede_transicionar("repesado", "en_transito_int", "system",
                                  flete_impago=True) is None
    msg = est.puede_transicionar("en_transito_int", "entregado_transportista", "admin",
                                 flete_impago=True)
    assert msg is not None and "flete" in msg


def test_el_servicio_impago_tambien_frena_la_entrega():
    assert est.puede_transicionar("en_transito_int", "entregado_transportista", "admin",
                                  partida_impaga=True) is not None


def test_con_todo_pago_se_entrega():
    assert est.puede_transicionar("en_transito_int", "entregado_transportista", "admin") is None
