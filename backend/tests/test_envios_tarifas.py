"""
El motor de precios del traslado transfronterizo: lo que decide cuanto se cobra.

CONTEXTO
    Una misma caja "pesa" distinto en cada tramo porque cada transportista cubica
    con su divisor y aplica —o no— un umbral por debajo del cual ignora el
    volumetrico. De esos tres numeros, solo el propio decide un cobro. Si el
    calculo se corre un escalon, se cobra de mas o de menos en todos los envios a
    la vez y nadie lo nota hasta el cierre del mes.

QUE SE CUBRE
    1. El umbral de cubado por sus DOS lados: justo debajo no aplica, justo
       encima si.
    2. Los tres divisores sobre la MISMA caja: dan tres pesos distintos, y esta
       bien que asi sea.
    3. Los bordes de escalon: 3,00 y 3,01 kg caen en escalones distintos.
    4. Divisor 0 o negativo no rompe ni inventa un peso: se cae al peso real.
    5. Entradas basura (None, texto, vacio) no revientan.
    6. El precio del servicio NO depende de la zona ni del destino: la funcion ni
       siquiera los recibe, y el mismo paquete cuesta lo mismo siempre.
    7. La tabla de escalones se valida antes de publicar: huecos, solapamientos,
       tablas no monotonas y precios en cero.
    8. Descuentos por cantidad, recargo de temporada, tarifa minima y el modo
       peso_o_volumen, que cobra la mayor de las dos tablas y NUNCA la suma.

Los modulos son puros —no tocan red ni Mongo— asi que se cargan por ruta directa
para no arrastrar services/__init__.py, que importa twilio y otras dependencias.
"""
import importlib.util
import os
import sys
import types
from decimal import Decimal

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _cargar(nombre):
    """Carga services/<nombre>.py sin ejecutar services/__init__.py."""
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


# ─── Reglas de ejemplo. Ningun nombre de empresa: solo codigos. ───────────

REGLA_CON_UMBRAL = {"divisor": 6000, "escalon_kg": "0.5", "minimo_kg": "0.3",
                    "umbral_cubado_kg": "5"}
REGLA_SIN_UMBRAL = {"divisor": 5000, "escalon_kg": "0.5", "minimo_kg": "1.0",
                    "umbral_cubado_kg": None}
REGLA_PROPIA = {"divisor": 5000, "escalon_kg": "0.5", "minimo_kg": "1.0",
                "umbral_cubado_kg": None}

TARIFA = {
    "version_id": "tar_test",
    "moneda": "RIS",
    "modo_tarifa": "peso",
    "regla_peso": REGLA_PROPIA,
    "escalones_peso": [
        {"desde_kg": "0.00", "hasta_kg": "1.00", "precio": "45.00"},
        {"desde_kg": "1.01", "hasta_kg": "3.00", "precio": "78.00"},
        {"desde_kg": "3.01", "hasta_kg": "5.00", "precio": "110.00"},
        {"desde_kg": "5.01", "hasta_kg": "10.00", "precio": "185.00"},
    ],
    "adicional_por_kg": "17.50",
    "tarifa_minima": "45.00",
    "margen": {"tipo": "porcentual", "valor": "0.20"},
}


# ─── 1. El umbral de cubado, por sus dos lados ────────────────────────────

def test_umbral_no_alcanzado_ignora_el_cubado():
    """Caja de 40x30x20 = 24.000 cm3 / 6000 = 4 kg de cubado, bajo el umbral de 5.
    Pesa 2 kg reales, asi que se factura por los 2 kg."""
    pf = tarifas.peso_facturable(2, 40, 30, 20, REGLA_CON_UMBRAL)
    assert pf == Decimal("2.000")


def test_umbral_superado_aplica_el_cubado():
    """La misma regla con una caja de 50x40x20 = 40.000 / 6000 = 6,667 kg.
    Supera el umbral de 5, asi que manda el cubado y no los 2 kg reales."""
    pf = tarifas.peso_facturable(2, 50, 40, 20, REGLA_CON_UMBRAL)
    assert pf == Decimal("7.000")   # 6,667 redondeado hacia arriba al escalon de 0,5


def test_umbral_none_aplica_siempre_el_cubado():
    """Sin umbral, un cubado de 4,8 kg le gana a 2 kg reales aunque sea chico."""
    pf = tarifas.peso_facturable(2, 40, 30, 20, REGLA_SIN_UMBRAL)  # 24000/5000 = 4,8
    assert pf == Decimal("5.000")


# ─── 2. Tres divisores, la misma caja ─────────────────────────────────────

def test_la_misma_caja_pesa_distinto_en_cada_transportista():
    """No existe "el" peso facturable: existe uno por transportista.
    50x40x30 = 60.000 cm3."""
    caja = (50, 40, 30)
    con_6000 = tarifas.peso_volumetrico(*caja, 6000)
    con_5000 = tarifas.peso_volumetrico(*caja, 5000)
    con_4000 = tarifas.peso_volumetrico(*caja, 4000)
    assert (con_6000, con_5000, con_4000) == (Decimal("10.000"), Decimal("12.000"),
                                              Decimal("15.000"))
    assert con_6000 < con_5000 < con_4000


def test_divisor_cero_o_negativo_no_inventa_un_peso():
    """Una configuracion incompleta no puede transformarse en un cobro.
    Sin divisor valido no hay cubado, y manda el peso real."""
    assert tarifas.peso_volumetrico(50, 40, 30, 0) == Decimal("0")
    assert tarifas.peso_volumetrico(50, 40, 30, -1) == Decimal("0")
    regla = {"divisor": 0, "escalon_kg": "0.5", "minimo_kg": "1.0"}
    assert tarifas.peso_facturable(3, 50, 40, 30, regla) == Decimal("3.000")


def test_minimo_facturable_manda_sobre_un_paquete_liviano():
    """Un sobre de 200 g igual ocupa un viaje y un tramite."""
    assert tarifas.peso_facturable("0.2", 15, 10, 2, REGLA_SIN_UMBRAL) == Decimal("1.000")


def test_escalon_cero_no_redondea_pero_respeta_el_minimo():
    regla = {"divisor": 5000, "escalon_kg": 0, "minimo_kg": "1.0"}
    assert tarifas.peso_facturable("2.37", 10, 10, 10, regla) == Decimal("2.370")


@pytest.mark.parametrize("basura", [None, "", "abc", [], {}])
def test_entradas_basura_no_revientan(basura):
    """to_decimal es tolerante a proposito: devuelve 0 en vez de lanzar."""
    assert tarifas.peso_volumetrico(basura, basura, basura, 5000) == Decimal("0")
    assert tarifas.peso_facturable(basura, basura, basura, basura, REGLA_SIN_UMBRAL) \
        == Decimal("1.000")


def test_peso_negativo_se_trata_como_cero():
    """Sin minimo que lo tape: un peso negativo no puede convertirse en un
    facturable negativo, que restaria plata en la suma del lote."""
    sin_minimo = {"divisor": 0, "escalon_kg": 0, "minimo_kg": 0}
    assert tarifas.peso_facturable(-5, 0, 0, 0, sin_minimo) == Decimal("0.000")


# ─── 3. Los bordes del escalon ────────────────────────────────────────────

@pytest.mark.parametrize("peso,esperado", [
    ("0.50", "45.00"), ("1.00", "45.00"),
    ("1.01", "78.00"), ("3.00", "78.00"),
    ("3.01", "110.00"), ("5.00", "110.00"),
    ("5.01", "185.00"), ("10.00", "185.00"),
])
def test_cada_peso_cae_en_su_escalon(peso, esperado):
    assert tarifas.precio_por_escalon(peso, TARIFA["escalones_peso"], "17.50") \
        == Decimal(esperado)


def test_sobre_el_ultimo_escalon_se_cobra_el_adicional():
    """12 kg = el escalon de 10 (185) + 2 kg a 17,50."""
    assert tarifas.precio_por_escalon(12, TARIFA["escalones_peso"], "17.50") \
        == Decimal("220.00")


def test_tabla_vacia_devuelve_cero_sin_romper():
    assert tarifas.precio_por_escalon(5, [], "17.50") == Decimal("0")
    assert tarifas.precio_por_escalon(5, None, None) == Decimal("0")


def test_la_forma_vieja_de_la_tabla_sigue_cotizando_igual():
    """Antes del panel las filas tenian solo hasta_kg y cada una arrancaba donde
    terminaba la anterior. Una tarifa cargada asi no puede cambiar de precio."""
    vieja = [{"hasta_kg": 1, "precio": "45.00"}, {"hasta_kg": 3, "precio": "78.00"},
             {"hasta_kg": 5, "precio": "110.00"}, {"hasta_kg": 10, "precio": "185.00"}]
    for peso in ("0.5", "1", "2.5", "3", "4", "10", "12"):
        assert tarifas.precio_por_escalon(peso, vieja, "17.50") == \
               tarifas.precio_por_escalon(peso, TARIFA["escalones_peso"], "17.50")


# ─── 4. El precio del servicio no depende del destino ─────────────────────

def test_el_precio_del_servicio_no_depende_de_la_zona():
    """La firma de cotizar_servicio no recibe zona, destino ni transportista.
    Este test existe para que se rompa el dia que alguien intente agregarselos:
    el servicio termina siempre en el mismo mostrador de Santa Elena."""
    import inspect
    parametros = set(inspect.signature(tarifas.cotizar_servicio).parameters)
    assert not (parametros & {"zona", "zona_destino", "destino", "estado",
                              "transportista", "transportista_id", "agencia"})


def test_la_cotizacion_no_acepta_ni_ignora_un_destino():
    """Pasarle un destino tiene que ser un error de programacion visible, no un
    parametro que se ignora en silencio y le hace creer a quien lo escribio que
    el precio cambia con la zona."""
    with pytest.raises(TypeError):
        tarifas.cotizar_servicio(TARIFA, 4, 40, 30, 20, zona_destino="ZONA-A")


# ─── 5. La cotizacion completa ────────────────────────────────────────────

def test_desglose_de_una_caja_tipica():
    """4 kg reales, 40x30x20 = 24.000/5000 = 4,8 de cubado -> 5,0 facturables.
    Escalon de 5 kg = 110,00; margen 20 % = 22,00; total 132,00."""
    r = tarifas.cotizar_servicio(TARIFA, 4, 40, 30, 20)
    assert r["peso_volumetrico_kg"] == Decimal("4.800")
    assert r["peso_facturable_kg"] == Decimal("5.000")
    assert r["base"] == Decimal("110.00")
    assert r["margen"] == Decimal("22.00")
    assert r["total"] == Decimal("132.00")
    assert r["moneda"] == "RIS"


def test_el_margen_se_aplica_sobre_el_subtotal_con_sobrecargos():
    tarifa = dict(TARIFA, sobrecargos=[
        {"codigo": "sobredimension", "tipo": "fijo", "valor": "35.00", "activo": True,
         "condicion": {"suma_lados_cm_mayor_a": 80}},
    ])
    r = tarifas.cotizar_servicio(tarifa, 4, 40, 30, 20)   # suma 90 > 80
    assert r["total_sobrecargos"] == Decimal("35.00")
    assert r["subtotal"] == Decimal("145.00")
    assert r["margen"] == Decimal("29.00")
    assert r["total"] == Decimal("174.00")


def test_un_sobrecargo_con_condicion_que_no_se_cumple_no_se_cobra():
    tarifa = dict(TARIFA, sobrecargos=[
        {"codigo": "valor_declarado", "tipo": "porcentual", "valor": "0.02",
         "activo": True, "condicion": {"valor_declarado_mayor_a": 500}},
    ])
    sin = tarifas.cotizar_servicio(tarifa, 4, 40, 30, 20, valor_declarado=100)
    con = tarifas.cotizar_servicio(tarifa, 4, 40, 30, 20, valor_declarado=1000)
    assert sin["total_sobrecargos"] == Decimal("0.00")
    assert con["total_sobrecargos"] == Decimal("2.20")   # 2 % de 110


def test_un_sobrecargo_desactivado_no_se_cobra():
    tarifa = dict(TARIFA, sobrecargos=[
        {"codigo": "x", "tipo": "fijo", "valor": "35.00", "activo": False},
    ])
    assert tarifas.cotizar_servicio(tarifa, 4, 40, 30, 20)["total_sobrecargos"] \
        == Decimal("0.00")


def test_una_condicion_desconocida_no_activa_el_sobrecargo_ni_rompe():
    """Un typo en el panel no puede transformarse en un cobro sorpresa."""
    tarifa = dict(TARIFA, sobrecargos=[
        {"codigo": "x", "tipo": "fijo", "valor": "999.00", "activo": True,
         "condicion": {"clave_que_no_existe": 1}},
    ])
    assert tarifas.cotizar_servicio(tarifa, 4, 40, 30, 20)["total_sobrecargos"] \
        == Decimal("0.00")


def test_los_sobrecargos_porcentuales_no_se_calculan_entre_si():
    """Dos porcentuales del 10 % suman 20 % de la base, no 21 %."""
    tarifa = dict(TARIFA, margen={}, sobrecargos=[
        {"codigo": "a", "tipo": "porcentual", "valor": "0.10", "activo": True},
        {"codigo": "b", "tipo": "porcentual", "valor": "0.10", "activo": True},
    ])
    r = tarifas.cotizar_servicio(tarifa, 4, 40, 30, 20)
    assert r["total_sobrecargos"] == Decimal("22.00")
    assert r["total"] == Decimal("132.00")


def test_la_tarifa_minima_es_un_piso_absoluto():
    tarifa = dict(TARIFA, tarifa_minima="200.00", margen={})
    r = tarifas.cotizar_servicio(tarifa, "0.2", 15, 10, 2)
    assert r["total"] == Decimal("200.00")
    assert r["aplico_tarifa_minima"] is True


def test_descuento_por_cantidad_toma_el_tramo_mas_alto_y_no_los_suma():
    dtos = [{"desde_bultos": 3, "descuento": "0.05"},
            {"desde_bultos": 6, "descuento": "0.10"}]
    assert tarifas.descuento_por_cantidad(dtos, 1) == Decimal("0")
    assert tarifas.descuento_por_cantidad(dtos, 3) == Decimal("0.05")
    assert tarifas.descuento_por_cantidad(dtos, 7) == Decimal("0.10")
    assert tarifas.descuento_por_cantidad(dtos, None) == Decimal("0")


def test_el_descuento_se_aplica_sobre_el_total_con_margen():
    tarifa = dict(TARIFA, descuentos_cantidad=[{"desde_bultos": 3, "descuento": "0.10"}])
    r = tarifas.cotizar_servicio(tarifa, 4, 40, 30, 20, bultos=4)
    assert r["descuento_cantidad"] == Decimal("13.20")   # 10 % de 132
    assert r["total"] == Decimal("118.80")


def test_recargo_de_temporada_solo_dentro_de_sus_fechas():
    recargos = [{"nombre": "Diciembre", "desde": "2026-12-01", "hasta": "2026-12-31",
                 "multiplicador": "1.15", "activo": True}]
    assert tarifas.multiplicador_temporada(recargos, "2026-11-30") == Decimal("1")
    assert tarifas.multiplicador_temporada(recargos, "2026-12-01") == Decimal("1.15")
    assert tarifas.multiplicador_temporada(recargos, "2026-12-31") == Decimal("1.15")
    assert tarifas.multiplicador_temporada(recargos, "2027-01-01") == Decimal("1")
    assert tarifas.multiplicador_temporada(recargos, None) == Decimal("1")


def test_temporadas_solapadas_gana_la_que_empezo_mas_tarde():
    """La decision mas reciente manda, no la mas cara: si ganara siempre el
    multiplicador mayor, una promocion programada encima de un recargo vigente
    seria letra muerta."""
    recargos = [{"desde": "2026-12-01", "hasta": "2026-12-31", "multiplicador": "1.30"},
                {"desde": "2026-12-20", "hasta": "2027-01-05", "multiplicador": "1.15"}]
    assert tarifas.multiplicador_temporada(recargos, "2026-12-25") == Decimal("1.15")
    assert tarifas.multiplicador_temporada(recargos, "2026-12-10") == Decimal("1.30")


def test_una_temporada_baja_se_aplica_de_verdad():
    """Un multiplicador menor a 1 es una promocion configurada. Ignorarla es
    cobrarle al usuario mas de lo que el panel dice que se le cobra."""
    baja = [{"desde": "2026-02-01", "hasta": "2026-03-31", "multiplicador": "0.85"}]
    assert tarifas.multiplicador_temporada(baja, "2026-02-15") == Decimal("0.85")
    r = tarifas.cotizar_servicio(dict(TARIFA, recargos_temporada=baja),
                                 4, 40, 30, 20, fecha="2026-02-15")
    assert r["total"] == Decimal("112.20")   # 132,00 x 0,85


def test_modo_peso_o_volumen_cobra_la_mayor_y_nunca_la_suma():
    """Un bulto liviano que ocupa medio vehiculo: 100x80x60 = 0,48 m3, 2 kg."""
    tarifa = dict(TARIFA, modo_tarifa="peso_o_volumen", margen={}, escalones_volumen=[
        {"desde_kg": "0.00", "hasta_kg": "0.20", "precio": "90.00"},
        {"desde_kg": "0.21", "hasta_kg": "0.50", "precio": "260.00"},
    ])
    r = tarifas.cotizar_servicio(tarifa, 2, 100, 80, 60)
    assert r["base_volumen"] == Decimal("260.00")
    # Sin la proteccion contra el doble conteo, el cubado de 96 kg haria que la
    # tabla de peso cobrara 1.690 y el "mayor de los dos" fuera siempre el peso.
    assert r["peso_facturable_kg"] == Decimal("2.000")
    assert r["total"] == Decimal("260.00")


def test_redondeo_final_a_multiplo():
    tarifa = dict(TARIFA, redondeo_final={"decimales": 2, "multiplo": "5"})
    r = tarifas.cotizar_servicio(tarifa, 4, 40, 30, 20)   # 132,00
    assert r["total"] == Decimal("130.00")


# ─── 6. La tabla se valida antes de publicar ──────────────────────────────

def test_una_tabla_sana_no_tiene_errores():
    assert tarifas.validar_escalones(TARIFA["escalones_peso"], "17.50") == []


def test_se_detecta_el_hueco():
    con_hueco = [{"desde_kg": "0.00", "hasta_kg": "3.00", "precio": "78.00"},
                 {"desde_kg": "3.50", "hasta_kg": "5.00", "precio": "110.00"}]
    errores = tarifas.validar_escalones(con_hueco)
    assert any("hueco" in e for e in errores)


def test_se_detecta_el_solapamiento():
    solapada = [{"desde_kg": "0.00", "hasta_kg": "3.00", "precio": "78.00"},
                {"desde_kg": "2.00", "hasta_kg": "5.00", "precio": "110.00"}]
    errores = tarifas.validar_escalones(solapada)
    assert any("solapan" in e for e in errores)


def test_se_detecta_la_tabla_no_monotona():
    """Si el escalon de 5 kg sale mas barato que el de 3, alguien va a declarar
    de mas para pagar menos."""
    invertida = [{"desde_kg": "0.00", "hasta_kg": "3.00", "precio": "110.00"},
                 {"desde_kg": "3.01", "hasta_kg": "5.00", "precio": "78.00"}]
    errores = tarifas.validar_escalones(invertida)
    assert any("más barato" in e for e in errores)


def test_se_detectan_precios_en_cero_o_negativos():
    mala = [{"desde_kg": "0.00", "hasta_kg": "3.00", "precio": "0"}]
    assert any("mayor a 0" in e for e in tarifas.validar_escalones(mala))


def test_se_detecta_que_la_tabla_no_arranca_en_cero():
    tarde = [{"desde_kg": "2.00", "hasta_kg": "5.00", "precio": "110.00"}]
    assert any("por debajo de eso" in e for e in tarifas.validar_escalones(tarde))


def test_tabla_vacia_es_un_error_de_publicacion():
    assert tarifas.validar_escalones([]) != []
    assert tarifas.validar_escalones(None) != []


def test_sin_adicional_por_kg_todo_lo_que_excede_viaja_gratis():
    assert any("gratis" in e for e in
               tarifas.validar_escalones(TARIFA["escalones_peso"], "0"))


def test_se_devuelven_todos_los_errores_juntos():
    """El que carga la tabla quiere ver de una vez todo lo que hay que arreglar."""
    mala = [{"desde_kg": "0.00", "hasta_kg": "3.00", "precio": "110.00"},
            {"desde_kg": "4.00", "hasta_kg": "5.00", "precio": "0"}]
    assert len(tarifas.validar_escalones(mala)) >= 3


def test_el_redondeo_no_puede_bajar_del_piso():
    """Un multiplo mal cargado redondea 45 hacia 0. El piso gana: es el numero
    que se prometio que nadie baja de ahi."""
    tarifa = dict(TARIFA, tarifa_minima="45.00", margen={},
                  redondeo_final={"decimales": 2, "multiplo": "300"})
    r = tarifas.cotizar_servicio(tarifa, "0.2", 15, 10, 2)
    assert r["total"] == Decimal("45.00")
    # ...y esa configuracion no deberia haberse podido publicar.
    assert any("múltiplo" in e for e in tarifas.validar_tarifa(tarifa))


def test_la_bandera_de_tarifa_minima_no_se_prende_de_mas():
    """Un envio que ya paga mas que el piso no puede reportar que lo aplico."""
    r = tarifas.cotizar_servicio(dict(TARIFA, tarifa_minima="45.00"), 4, 40, 30, 20)
    assert r["total"] == Decimal("132.00")
    assert r["aplico_tarifa_minima"] is False


# ─── 7. Configuracion mal cargada: nunca puede cobrar de mas ──────────────

@pytest.mark.parametrize("apagado", [False, 0, "", "false", "no", None])
def test_un_sobrecargo_apagado_de_cualquier_forma_no_se_cobra(apagado):
    """Del panel un checkbox puede llegar como False, 0, "" o el string "false"
    segun como se serialice. Todas esas formas apagan la fila: comparar con
    `is False` dejaba pasar el string y se cobraban 999 pesos de la nada."""
    tarifa = dict(TARIFA, sobrecargos=[
        {"codigo": "x", "tipo": "fijo", "valor": "999.00", "activo": apagado},
    ])
    assert tarifas.cotizar_servicio(tarifa, 4, 40, 30, 20)["total_sobrecargos"] \
        == Decimal("0.00")


def test_un_sobrecargo_sin_la_clave_activo_se_cobra():
    """La ausencia del campo significa activo; solo un valor falso lo apaga."""
    tarifa = dict(TARIFA, sobrecargos=[{"codigo": "x", "tipo": "fijo", "valor": "10.00"}])
    assert tarifas.cotizar_servicio(tarifa, 4, 40, 30, 20)["total_sobrecargos"] \
        == Decimal("10.00")


def test_el_orden_de_las_filas_no_cambia_el_precio():
    """La misma tabla guardada en otro orden tiene que cotizar igual: el orden
    de un array en Mongo no es una garantia en la que se pueda confiar."""
    desordenada = [TARIFA["escalones_peso"][i] for i in (2, 0, 3, 1)]
    for peso in ("0.5", "1", "2", "3", "4", "7", "12"):
        assert tarifas.precio_por_escalon(peso, desordenada, "17.50") == \
               tarifas.precio_por_escalon(peso, TARIFA["escalones_peso"], "17.50")


def test_la_forma_vieja_desordenada_tambien_cotiza_igual():
    vieja = [{"hasta_kg": 5, "precio": "110.00"}, {"hasta_kg": 1, "precio": "45.00"},
             {"hasta_kg": 10, "precio": "185.00"}, {"hasta_kg": 3, "precio": "78.00"}]
    assert tarifas.precio_por_escalon("0.5", vieja, "17.50") == Decimal("45.00")
    assert tarifas.precio_por_escalon(2, vieja, "17.50") == Decimal("78.00")


def test_una_fila_sin_hasta_no_se_lleva_puestos_los_escalones_siguientes():
    """Valiendo 0, esa fila se colaba primera y un paquete de 4 kg terminaba
    pagando el escalon de 10. Se descarta, y la validacion la reporta."""
    con_fila_rota = [{"desde_kg": "0.00", "hasta_kg": "1.00", "precio": "45.00"},
                     {"desde_kg": "1.01", "hasta_kg": "3.00", "precio": "78.00"},
                     {"desde_kg": "3.01", "precio": "110.00"},
                     {"desde_kg": "5.01", "hasta_kg": "10.00", "precio": "185.00"}]
    assert tarifas.precio_por_escalon(4, con_fila_rota, "17.50") == Decimal("78.00")
    assert any("hasta" in e for e in tarifas.validar_escalones(con_fila_rota))


def test_dos_escalones_que_empiezan_igual_no_dependen_del_orden():
    a = [{"hasta_kg": 3, "precio": "78.00"}, {"desde_kg": 0, "hasta_kg": 1, "precio": "45.00"}]
    b = list(reversed(a))
    assert tarifas.precio_por_escalon("0.5", a, 0) == tarifas.precio_por_escalon("0.5", b, 0)


def test_adicional_por_kg_en_cero_es_un_valor_y_no_una_ausencia():
    """Quien puso 0 a proposito ("el excedente no se cobra aparte") no puede
    terminar cobrando el numero de una version anterior de la tarifa."""
    tarifa = {"escalones_peso": TARIFA["escalones_peso"], "adicional_por_kg": 0,
              "regla_peso": {"divisor": 0, "escalon_kg": "0.5", "minimo_kg": "1.0"},
              "servicio_traslado": {"adicional_por_kg": "17.50"}}
    assert tarifas.cotizar_servicio(tarifa, 12, 10, 10, 10)["base"] == Decimal("185.00")


def test_un_descuento_sin_desde_bultos_no_se_le_aplica_a_todos():
    assert tarifas.descuento_por_cantidad([{"descuento": "0.50"}], 1) == Decimal("0")


def test_numeros_absurdos_no_revientan_la_cotizacion():
    """Un 1e40 pegado en un campo tiene que dar un numero manejable o cero, no
    un InvalidOperation con un 500 en la cara del usuario."""
    assert tarifas.peso_facturable(10 ** 30, 10, 10, 10, REGLA_SIN_UMBRAL) >= Decimal("0")
    assert tarifas.peso_volumetrico("1e15", "1e15", "1e15", 5000) == Decimal("0")
    r = tarifas.cotizar_servicio(TARIFA, "1e40", "1e40", "1e40", "1e40")
    assert r["total"] >= Decimal("0")


def test_decimales_de_redondeo_no_numericos_no_rompen():
    tarifa = dict(TARIFA, redondeo_final={"decimales": "dos"})
    assert tarifas.cotizar_servicio(tarifa, 4, 40, 30, 20)["total"] == Decimal("132.00")


# ─── 8. Margen fijo y sobrecargo por kg ───────────────────────────────────

def test_margen_fijo():
    tarifa = dict(TARIFA, margen={"tipo": "fijo", "valor": "30.00"})
    assert tarifas.cotizar_servicio(tarifa, 4, 40, 30, 20)["total"] == Decimal("140.00")


def test_sobrecargo_por_kg_usa_el_peso_facturable():
    tarifa = dict(TARIFA, margen={}, sobrecargos=[
        {"codigo": "manipuleo", "tipo": "por_kg", "valor": "3.00", "activo": True}])
    r = tarifas.cotizar_servicio(tarifa, 4, 40, 30, 20)      # 5,0 kg facturables
    assert r["total_sobrecargos"] == Decimal("15.00")


# ─── 9. validar_tarifa: el porcentaje mal tipeado ─────────────────────────

def test_una_tarifa_sana_se_puede_publicar():
    assert tarifas.validar_tarifa(TARIFA) == []


def test_un_margen_escrito_como_entero_se_rechaza():
    """20 en vez de 0.20 multiplica el precio por veintiuno. Sin esta validacion
    se publica sin que nada chille y se cobra hasta que alguien mire una factura."""
    mala = dict(TARIFA, margen={"tipo": "porcentual", "valor": "20"})
    assert any("fracción" in e for e in tarifas.validar_tarifa(mala))
    assert tarifas.cotizar_servicio(mala, 4, 40, 30, 20)["total"] > Decimal("2000")


def test_un_sobrecargo_porcentual_desmedido_se_rechaza():
    mala = dict(TARIFA, sobrecargos=[
        {"codigo": "x", "tipo": "porcentual", "valor": "2", "activo": True}])
    assert any("fracción" in e for e in tarifas.validar_tarifa(mala))


def test_una_condicion_que_el_sistema_no_sabe_evaluar_se_rechaza():
    """Si no se avisa acá, el sobrecargo queda cargado, visible en el panel, y
    no se cobra nunca: se descubre recién al cerrar el mes."""
    mala = dict(TARIFA, sobrecargos=[
        {"codigo": "x", "tipo": "fijo", "valor": "10", "activo": True,
         "condicion": {"clave_que_no_existe": 1}}])
    assert any("no sabe" in e for e in tarifas.validar_tarifa(mala))


def test_un_descuento_fuera_de_rango_se_rechaza():
    mala = dict(TARIFA, descuentos_cantidad=[{"desde_bultos": 3, "descuento": "50"}])
    assert any("fracción" in e for e in tarifas.validar_tarifa(mala))


def test_una_temporada_desmedida_o_al_reves_se_rechaza():
    assert any("multiplicador" in e for e in tarifas.validar_tarifa(
        dict(TARIFA, recargos_temporada=[{"nombre": "T", "multiplicador": "15"}])))
    assert any("antes de empezar" in e for e in tarifas.validar_tarifa(
        dict(TARIFA, recargos_temporada=[{"nombre": "T", "multiplicador": "1.1",
                                          "desde": "2026-12-31", "hasta": "2026-12-01"}])))


def test_una_tarifa_sin_divisor_volumetrico_se_rechaza():
    """Sin divisor, un bulto grande y liviano cotiza como si pesara dos kilos."""
    mala = dict(TARIFA, regla_peso={"divisor": 0, "escalon_kg": "0.5", "minimo_kg": "1.0"})
    assert any("divisor" in e for e in tarifas.validar_tarifa(mala))


def test_en_modo_volumen_la_tabla_de_m3_tambien_se_valida():
    mala = dict(TARIFA, modo_tarifa="peso_o_volumen", escalones_volumen=[
        {"desde_kg": "0.00", "hasta_kg": "0.20", "precio": "90.00"},
        {"desde_kg": "0.50", "hasta_kg": "1.00", "precio": "260.00"}])
    errores = tarifas.validar_tarifa(mala)
    assert any("hueco" in e and "m³" in e for e in errores)


def test_la_tolerancia_de_hueco_es_de_un_centesimo_y_no_mas():
    """Un salto de 0,01 kg es como se cargan las tablas a mano (…3,00 / 3,01…) y
    no deja ningun peso sin precio. Uno de 0,10 si: con escalones de 0,05 kg,
    un paquete de 3,05 caeria en el vacio."""
    a_mano = [{"desde_kg": "0.00", "hasta_kg": "3.00", "precio": "78.00"},
              {"desde_kg": "3.01", "hasta_kg": "5.00", "precio": "110.00"}]
    assert tarifas.validar_escalones(a_mano) == []

    con_salto = [{"desde_kg": "0.00", "hasta_kg": "3.00", "precio": "78.00"},
                 {"desde_kg": "3.10", "hasta_kg": "5.00", "precio": "110.00"}]
    assert any("hueco" in e for e in tarifas.validar_escalones(con_salto))


# ─── Lo que encontro la revision adversarial de la consola de precios ──────

def test_un_minimo_facturable_absurdo_no_se_puede_publicar():
    """Es el mismo error de tipeo que el margen "20" en vez de "0.20", una celda
    mas a la derecha. Con minimo_kg = 1000 y una tabla que llega a 10 kg, una
    caja de 1 kg se cobra como si pesara una tonelada: 45 se vuelven 21.000. Ni
    el modelo ni el validador lo miraban, porque 1000 esta dentro del rango
    admitido — solo es absurdo CONTRA ESTA TABLA."""
    rota = {**TARIFA, "regla_peso": {**REGLA_PROPIA, "minimo_kg": "1000"}}
    errores = tarifas.validar_tarifa(rota)
    assert any("mínimo facturable" in e for e in errores)

    caro = tarifas.cotizar_servicio(rota, "1", "20", "20", "20")
    sano = tarifas.cotizar_servicio(TARIFA, "1", "20", "20", "20")
    assert caro["total"] > sano["total"] * 100     # el daño que el error evita


def test_un_escalon_de_redondeo_absurdo_tampoco():
    rota = {**TARIFA, "regla_peso": {**REGLA_PROPIA, "escalon_kg": "1000"}}
    assert any("escalón de redondeo" in e for e in tarifas.validar_tarifa(rota))


def test_una_regla_de_peso_normal_sigue_pasando():
    assert tarifas.validar_tarifa(TARIFA) == []


def test_el_volumen_sin_adicional_no_se_puede_publicar():
    """Mismo criterio que la tabla de kilos: sin adicional, todo lo que excede el
    ultimo escalon de m³ viaja gratis. En kilos se bloqueaba y en volumen no,
    porque un adicional ausente y uno en cero son indistinguibles desde adentro
    de validar_escalones."""
    con_volumen = {
        **TARIFA, "modo_tarifa": "peso_o_volumen",
        "escalones_volumen": [{"desde_kg": "0.00", "hasta_kg": "0.10", "precio": "50.00"}],
    }
    assert any("adicional_por_m3" in e for e in tarifas.validar_tarifa(con_volumen))
    # Con un adicional cargado, la misma tabla pasa.
    assert tarifas.validar_tarifa({**con_volumen, "adicional_por_m3": "120.00"}) == []


def test_un_no_finito_se_reporta_en_vez_de_reventar_el_validador():
    """`Decimal("NaN") < 0` no devuelve False: lanza InvalidOperation. El
    validador, que existe para que nada rompa mas adelante, rompia primero — y lo
    hacia dentro de la ruta que publica, o sea un 500."""
    for valor in ("NaN", "Infinity", float("nan"), float("inf")):
        errores = tarifas.validar_tarifa({**TARIFA, "tarifa_minima": valor})
        assert errores and all("finito" in e for e in errores)
        assert any("tarifa_minima" in e for e in errores)


def test_un_no_finito_escondido_en_un_escalon_tambien_se_ve():
    rota = {**TARIFA, "escalones_peso": [
        {**TARIFA["escalones_peso"][0], "precio": "NaN"}, *TARIFA["escalones_peso"][1:]]}
    errores = tarifas.validar_tarifa(rota)
    assert any("escalones_peso[0].precio" in e for e in errores)
