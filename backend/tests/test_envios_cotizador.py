"""
La cotizacion: un precio, dos orientaciones, y ni un centavo movido.

CONTEXTO
    RIS App cobra UN solo servicio: retirar el paquete en Pacaraima, repesarlo y
    llevarlo hasta la oficina del transportista en Santa Elena. Los dos tramos
    de transporte —Brasil hasta la frontera, Venezuela desde Santa Elena— los
    contrata y los paga el usuario por su cuenta.

EL RIESGO QUE ORGANIZA ESTE ARCHIVO
    Que el usuario crea que pagando en RIS App ya cubrio el envio entero. No se
    arregla con soporte: se arregla en la forma de la respuesta. Por eso hay
    tests que verifican que NINGUNA referencia entra en el total, que el aviso
    esta siempre, y que el bloque de lo que se paga adentro esta separado del de
    lo que se paga afuera.

QUE SE CUBRE
    1. El precio del servicio sale de la MISMA funcion que el simulador.
    2. Ninguna referencia entra en el total, ni sumada ni promediada.
    3. Las referencias ausentes no rompen la cotizacion.
    4. El nombre del retirador queda congelado aunque la nomina cambie.
    5. La version de tarifa queda congelada aunque se publique un aumento.
    6. Cotizar no escribe un solo movimiento de plata.
    7. Los limites se validan en el formulario, no en el mostrador.
    8. Una cotizacion vencida se reconoce como vencida.

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
_cargar("envios_config")
ret = _cargar("envios_retiro")
cot = _cargar("envios_cotizador")
from models.envios_cotizacion import PedidoDeCotizacion               # noqa: E402


def corre(coro):
    return asyncio.run(coro)


def _proyectar(doc, proyeccion):
    if not proyeccion:
        return dict(doc)
    incluir = [k for k, v in proyeccion.items() if v and k != "_id"]
    if incluir:
        return {k: v for k, v in doc.items() if k in incluir}
    excluir = [k for k, v in proyeccion.items() if not v]
    return {k: v for k, v in doc.items() if k not in excluir}


def _camino(doc, clave):
    """`"cotizacion.huella"` resuelve como en Mongo. El doble tiene que modelar
    lo que hace la base: sin esto, una consulta con notación de punto no matchea
    nunca y el test "pasa" contra un código que en producción se comporta al
    revés."""
    actual = doc
    for parte in str(clave).split("."):
        if not isinstance(actual, dict):
            return None
        actual = actual.get(parte)
    return actual


class _Coleccion:
    def __init__(self, filas=None):
        self.filas = filas if filas is not None else []

    def _match(self, d, filtro):
        return all(_camino(d, k) == v for k, v in (filtro or {}).items())

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
                             for d in self.filas if self._match(d, filtro)])

    async def find_one(self, filtro, proyeccion=None):
        for d in self.filas:
            if self._match(d, filtro):
                return _proyectar(d, proyeccion)
        return None

    async def insert_one(self, doc):
        self.filas.append(dict(doc))


class _Db:
    def __init__(self, **colecciones):
        self._c = {k: _Coleccion(v) for k, v in colecciones.items()}

    def __getattr__(self, nombre):
        return self._c.setdefault(nombre, _Coleccion([]))


class _Usuario:
    user_id = "usr_ana"
    email = "ana@example.com"


AHORA = datetime.now(timezone.utc)
_AYER = AHORA - timedelta(days=1)

REGLA = {"divisor": 5000, "escalon_kg": "0.5", "minimo_kg": "1.0"}

TARIFA = {
    "version_id": "tar_2026_08_a", "vigente_desde": _AYER, "vigente_hasta": None,
    "moneda": "RIS", "modo_tarifa": "peso", "regla_peso": REGLA,
    "escalones_peso": [
        {"desde_kg": "0.00", "hasta_kg": "1.00", "precio": "45.00"},
        {"desde_kg": "1.01", "hasta_kg": "3.00", "precio": "78.00"},
        {"desde_kg": "3.01", "hasta_kg": "5.00", "precio": "110.00"},
        {"desde_kg": "5.01", "hasta_kg": "10.00", "precio": "185.00"},
    ],
    "adicional_por_kg": "17.50", "tarifa_minima": "45.00",
    "margen": {"tipo": "porcentual", "valor": "0.20"},
    "limites_propios": {"valor_declarado_max": "3000"},
}

TRP_BR = {"transportista_id": "trp_br1", "codigo": "TRP-7K2M", "rol": "brasil",
          "activo": True, "orden": 1, "nombre": "Empresa de Origen",
          "regla_peso": {"divisor": 6000, "escalon_kg": "0.5", "minimo_kg": "0.3",
                         "umbral_cubado_kg": "5"},
          "limites": {"peso_max_kg": 30, "lado_max_cm": 100, "suma_lados_max_cm": 200,
                      "largo_min_cm": 11, "ancho_min_cm": 6, "alto_min_cm": "0.4"}}
TRP_VE = {"transportista_id": "trp_ve1", "codigo": "TRP-3Q9X", "rol": "venezuela",
          "activo": True, "orden": 1, "nombre": "Empresa de Destino",
          "regla_peso": {"divisor": 4000, "escalon_kg": "1", "minimo_kg": "1"},
          "limites": {"peso_max_kg": 70, "lado_max_cm": 120}}

AGENCIA = {"transportista_id": "trp_ve1", "codigo": "agc_001", "nombre": "Centro",
           "estado": "Miranda", "ciudad": "Caracas", "activa": True, "zona": "zona_a"}

MATRIZ = [
    {"transportista_id": "trp_br1", "clave": "SP", "hasta_kg": "10",
     "precio": "62.40", "moneda": "BRL", "actualizada_at": AHORA - timedelta(days=2)},
    {"transportista_id": "trp_ve1", "clave": "zona_a", "hasta_kg": "10",
     "precio": "310.00", "moneda": "VES", "actualizada_at": AHORA - timedelta(days=3)},
]

PUNTO = {"setting_id": "envios_punto_origen",
         "nombre": "AC Pacaraima", "cep": "69355000", "ciudad": "Pacaraima", "uf": "RR",
         "modalidad": "caixa_postal", "caixa_postal": "123", "direccion": None,
         "razon_social": "RIS App LTDA",
         "plantilla_direccion": ret.PLANTILLA_POR_DEFECTO,
         "retirador_activo_id": "col_aaaa1111"}

CONTENIDO = {"setting_id": "envios_contenido", "prohibidos": ["armas"],
             "terminos_version": "v3", "texto_estimado": "Texto que edita el panel.",
             "descripcion_min_caracteres": 10}

OPERACION = {"setting_id": "envios_operacion", "ttl_cotizacion_horas": 48,
             "banda_variacion_pct": "0.12"}

MARIA = {"colaborador_id": "col_aaaa1111", "nombre": "María Gómez",
         "cpf": "111.222.333-44", "telefono": "+55 95 99999-0000", "activo": True,
         "creado_at": AHORA - timedelta(days=30),
         "autorizado_desde": AHORA - timedelta(days=30), "autorizado_hasta": None}

PEDIDO = {
    "origen": {"cep": "01310-100", "ciudad": "São Paulo", "uf": "SP"},
    "destino": {"agencia_codigo": "agc_001", "transportista_id": "trp_ve1",
                "codigo_postal": "1071",
                "destinatario": {"nombre": "Ana Pérez", "documento": "V-12345678",
                                 "telefono": "+58 412 1234567"}},
    "paquete": {"peso_kg": "2.30", "largo_cm": "40", "ancho_cm": "30", "alto_cm": "20",
                "contenido_descripcion": "Ropa y artículos de higiene personal",
                "valor_declarado_brl": "180.00"},
    "modalidad_flete": "destino",
}


def pedido(**cambios) -> dict:
    """El pedido validado por el modelo, que es como llega desde la ruta."""
    datos = {k: (dict(v) if isinstance(v, dict) else v) for k, v in PEDIDO.items()}
    for clave, valor in cambios.items():
        if isinstance(valor, dict) and isinstance(datos.get(clave), dict):
            datos[clave] = {**datos[clave], **valor}
        else:
            datos[clave] = valor
    return PedidoDeCotizacion(**datos).model_dump()


def db_completa(**cambios):
    base = dict(
        transportistas=[dict(TRP_BR), dict(TRP_VE)],
        agencias=[dict(AGENCIA)],
        tarifas_envio=[dict(TARIFA)],
        matrices_referencia=[dict(m) for m in MATRIZ],
        app_settings=[dict(PUNTO), dict(CONTENIDO), dict(OPERACION)],
        colaboradores_retiro=[dict(MARIA)],
        envios=[],
    )
    base.update(cambios)
    return _Db(**base)


# ─── 1. El precio del servicio ────────────────────────────────────────────

def test_cotizar_devuelve_el_precio_del_servicio_y_lo_llama_por_su_nombre():
    r = corre(cot.cotizar(_Usuario(), pedido(), db=db_completa(), ahora=AHORA))
    assert r["a_pagar_en_risapp"]["concepto"] == cot.CONCEPTO
    assert Decimal(r["a_pagar_en_risapp"]["total_estimado_ris"]) > 0
    assert r["moneda"] == "RIS"


def test_el_precio_es_el_mismo_que_da_el_simulador_del_panel():
    """No una función parecida: la misma. Si algún día dan distinto hay un bug, y
    este es el test que lo detecta."""
    r = corre(cot.cotizar(_Usuario(), pedido(), db=db_completa(), ahora=AHORA))
    directo = tarifas.cotizar_servicio(TARIFA, "2.30", "40", "30", "20",
                                       valor_declarado="180.00", bultos=1,
                                       fecha=AHORA.date())
    assert Decimal(r["a_pagar_en_risapp"]["total_estimado_ris"]) == directo["total"]


def test_se_muestran_el_peso_real_y_el_facturable_por_separado():
    """Evita el ticket "pesa 2 kg, ¿por qué me cobran 5?"."""
    r = corre(cot.cotizar(_Usuario(), pedido(), db=db_completa(), ahora=AHORA))
    assert Decimal(r["peso_real_kg"]) == Decimal("2.300")
    assert Decimal(r["peso_facturable"]["propio"]["kg"]) >= Decimal(r["peso_real_kg"])
    assert r["peso_facturable"]["propio"]["volumetrico_kg"]


def test_cada_transportista_factura_un_peso_distinto_y_se_ve():
    """Evita el "¿por qué en un lado pesa 2,30 y en otro 5?". Esconderlo no hace
    que la diferencia no exista: cada uno tiene su divisor y su umbral."""
    r = corre(cot.cotizar(_Usuario(), pedido(), db=db_completa(), ahora=AHORA))
    por_codigo = {p["codigo"]: p["kg"] for p in r["peso_facturable"]["por_transportista"]}
    assert set(por_codigo) == {"TRP-7K2M", "TRP-3Q9X"}
    assert por_codigo["TRP-7K2M"] != por_codigo["TRP-3Q9X"]


# ─── 2. Ninguna referencia entra en el total ──────────────────────────────

def test_ninguna_referencia_entra_en_el_total():
    """LA INVARIANTE. Son dos contratos distintos, con dos empresas distintas, en
    dos monedas distintas. Un número que los sume parece un total y no lo es, y
    ese número terminaría algún día al lado del que RIS App sí cobra."""
    r = corre(cot.cotizar(_Usuario(), pedido(), db=db_completa(), ahora=AHORA))

    total = Decimal(r["a_pagar_en_risapp"]["total_estimado_ris"])
    montos = [Decimal(x["monto"]) for x in r["referencias"] if x["monto"] is not None]
    assert montos, "el escenario tiene que tener referencias con monto para probar algo"

    sin_referencias = tarifas.cotizar_servicio(
        TARIFA, "2.30", "40", "30", "20", valor_declarado="180.00",
        bultos=1, fecha=AHORA.date())["total"]
    assert total == sin_referencias
    for monto in montos:
        assert total != sin_referencias + monto
    assert total != sin_referencias + sum(montos)


def test_las_referencias_van_en_otro_bloque_y_con_su_etiqueta():
    """Separar lo que se paga adentro de lo que se paga afuera, con palabras y no
    con un color, es lo que evita el peor malentendido posible."""
    r = corre(cot.cotizar(_Usuario(), pedido(), db=db_completa(), ahora=AHORA))
    assert "referencias" not in r["a_pagar_en_risapp"]
    por_rol = {x["rol"]: x for x in r["referencias"]}
    assert "pagar al despachar en Brasil" in por_rol["brasil"]["etiqueta"]
    assert "dentro de Venezuela" in por_rol["venezuela"]["etiqueta"]


def test_las_referencias_no_se_guardan_como_si_fueran_un_precio():
    base = db_completa()
    corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
    guardadas = base.envios.filas[0]["cotizacion"]["referencias"]
    assert guardadas and all("fuente" in x for x in guardadas)
    # Se guardan por CÓDIGO. El nombre comercial no entra al documento del envío.
    assert all("nombre" not in x for x in guardadas)


# ─── 3. Lo que falta no puede romper ──────────────────────────────────────

def test_sin_ninguna_matriz_la_cotizacion_se_completa_igual():
    """El precio que RIS App cobra no depende de ninguna orientación."""
    r = corre(cot.cotizar(_Usuario(), pedido(),
                          db=db_completa(matrices_referencia=[]), ahora=AHORA))
    assert Decimal(r["a_pagar_en_risapp"]["total_estimado_ris"]) > 0
    assert all(x["monto"] is None for x in r["referencias"])
    assert all(x["detalle"] for x in r["referencias"])


def test_sin_uf_de_origen_la_referencia_de_brasil_dice_por_que():
    r = corre(cot.cotizar(_Usuario(), pedido(origen={"uf": None}),
                          db=db_completa(), ahora=AHORA))
    brasil = [x for x in r["referencias"] if x["rol"] == "brasil"][0]
    assert brasil["monto"] is None and brasil["fuente"] == "sin_clave"
    assert Decimal(r["a_pagar_en_risapp"]["total_estimado_ris"]) > 0


def test_una_agencia_sin_zona_no_impide_cotizar():
    sin_zona = {**AGENCIA, "zona": None}
    r = corre(cot.cotizar(_Usuario(), pedido(), db=db_completa(agencias=[sin_zona]),
                          ahora=AHORA))
    venezuela = [x for x in r["referencias"] if x["rol"] == "venezuela"][0]
    assert venezuela["monto"] is None
    assert Decimal(r["a_pagar_en_risapp"]["total_estimado_ris"]) > 0


# ─── 4. El aviso, siempre ─────────────────────────────────────────────────

def test_el_aviso_esta_en_toda_respuesta():
    """No es opcional, no es un tooltip y no es una nota al pie en gris claro."""
    r = corre(cot.cotizar(_Usuario(), pedido(), db=db_completa(), ahora=AHORA))
    assert r["aviso_estimado"] == CONTENIDO["texto_estimado"]
    assert r["es_estimado"] is True


def test_sin_texto_configurado_el_aviso_no_desaparece():
    """Un aviso que falta cuando el panel está a medio cargar es exactamente
    cuando más falta hace."""
    sin_texto = {k: v for k, v in CONTENIDO.items() if k != "texto_estimado"}
    r = corre(cot.cotizar(_Usuario(), pedido(),
                          db=db_completa(app_settings=[dict(PUNTO), sin_texto,
                                                       dict(OPERACION)]),
                          ahora=AHORA))
    assert "un solo servicio" in r["aviso_estimado"]
    assert "aparte" in r["aviso_estimado"]


# ─── 5. Lo que se congela ─────────────────────────────────────────────────

def test_el_nombre_del_retirador_queda_congelado_aunque_cambie_la_nomina():
    """Cambiar la nómina no puede cambiar la etiqueta de una caja que ya está
    viajando: el mostrador compara esa etiqueta contra un documento."""
    base = db_completa()
    corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
    congelado = base.envios.filas[0]["destino_brasil"]["retirador_nombre"]
    assert congelado == "María Gómez"

    base.colaboradores_retiro.filas[0]["activo"] = False       # se va de licencia
    assert base.envios.filas[0]["destino_brasil"]["retirador_nombre"] == "María Gómez"
    assert "María Gómez" in base.envios.filas[0]["destino_brasil"]["texto_copiable"]


def test_la_version_de_tarifa_queda_congelada():
    """Lo que impide cobrarle a alguien un aumento posterior a lo que aceptó."""
    base = db_completa()
    corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
    assert base.envios.filas[0]["cotizacion"]["tarifa_version"] == "tar_2026_08_a"


def test_la_agencia_se_congela_con_su_nombre():
    """Si la sucursal cierra y sale del catálogo, el envío tiene que poder seguir
    diciendo a dónde iba."""
    base = db_completa()
    corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
    destino = base.envios.filas[0]["destino"]
    assert destino["agencia_codigo"] == "agc_001"
    assert destino["agencia_nombre"] == "Centro"
    assert destino["zona_tarifa"] == "zona_a"


# ─── 6. Cotizar no mueve plata ────────────────────────────────────────────

def test_cotizar_no_escribe_un_solo_movimiento_de_plata():
    """Cotizar es gratis, y no es una promesa comercial: es una propiedad del
    código. El envío nace sin cobros y sin tocar ningún saldo."""
    base = db_completa()
    corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))

    for coleccion in ("ledger", "transactions", "ris_entries", "withdrawals", "users"):
        assert base._c.get(coleccion) is None or base._c[coleccion].filas == []

    cobros = base.envios.filas[0]["cobros"]
    assert cobros["inicial"] is None and cobros["ajuste"] is None
    assert cobros["total_cobrado_ris"] == "0.00"


def test_el_envio_nace_cotizado_y_estimado():
    base = db_completa()
    r = corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
    guardado = base.envios.filas[0]
    assert guardado["estado"] == "cotizado" == r["estado"]
    assert guardado["cotizacion"]["es_estimado"] is True
    assert guardado["cotizacion"]["total_final_ris"] is None
    assert guardado["user_id"] == "usr_ana"


def test_el_modulo_no_importa_nada_que_mueva_plata():
    """La forma más barata de que siga siendo cierto dentro de un año."""
    ruta = os.path.join(_BACKEND, "services", "envios_cotizador.py")
    fuente = open(ruta, encoding="utf-8").read()
    for prohibido in ("record_ris_entry", "balance_ris", "withdrawal",
                      "debitar", "acreditar"):
        assert prohibido not in fuente


# ─── 7. Los límites, en el formulario ─────────────────────────────────────

def test_una_caja_fuera_de_limites_se_rechaza_al_cotizar():
    """Se rechaza acá y no en el mostrador de Pacaraima con el paquete en la
    mano: ahí ya se pagó el tramo 1 y no hay vuelta atrás."""
    with pytest.raises(cot.NoSePuedeCotizar) as e:
        corre(cot.cotizar(_Usuario(), pedido(paquete={"peso_kg": "45"}),
                          db=db_completa(), ahora=AHORA))
    assert "30" in e.value.mensaje and e.value.http == 400


def test_el_limite_que_manda_es_el_del_transportista_mas_estricto():
    with pytest.raises(cot.NoSePuedeCotizar) as e:
        corre(cot.cotizar(_Usuario(), pedido(paquete={"largo_cm": "110"}),
                          db=db_completa(), ahora=AHORA))
    assert "100" in e.value.mensaje          # el de 100, no el de 120


def test_una_descripcion_de_tres_letras_no_pasa():
    with pytest.raises(cot.NoSePuedeCotizar) as e:
        corre(cot.cotizar(_Usuario(),
                          pedido(paquete={"contenido_descripcion": "ropa"}),
                          db=db_completa(), ahora=AHORA))
    assert "aduana" in e.value.mensaje


def test_el_error_del_usuario_llega_antes_que_el_de_configuracion():
    """Al revés, alguien con una caja de 80 kg recibe "el servicio no está
    disponible" y escribe a soporte, cuando el problema era su caja."""
    with pytest.raises(cot.NoSePuedeCotizar) as e:
        corre(cot.cotizar(_Usuario(), pedido(paquete={"contenido_descripcion": "x"}),
                          db=db_completa(tarifas_envio=[], transportistas=[]),
                          ahora=AHORA))
    assert e.value.http == 400 and "aduana" in e.value.mensaje


def test_una_agencia_que_no_recibe_paquetes_se_rechaza():
    cerrada = {**AGENCIA, "activa": False}
    with pytest.raises(cot.NoSePuedeCotizar) as e:
        corre(cot.cotizar(_Usuario(), pedido(), db=db_completa(agencias=[cerrada]),
                          ahora=AHORA))
    assert "otra de la lista" in e.value.mensaje


def test_el_activo_de_la_agencia_se_lee_en_python():
    """`{"activa": True}` no matchea un 1, y este proyecto ya se comió ese bug."""
    con_uno = {**AGENCIA, "activa": 1}
    r = corre(cot.cotizar(_Usuario(), pedido(), db=db_completa(agencias=[con_uno]),
                          ahora=AHORA))
    assert r["envio_id"].startswith("env_")


# ─── 8. Sin configuración no se cotiza, pero no se rompe ──────────────────

def test_sin_tarifa_publicada_no_se_cotiza_y_no_se_filtra_el_diagnostico():
    """Explicarle a un anónimo qué le falta al panel no le sirve a nadie."""
    with pytest.raises(cot.NoSePuedeCotizar) as e:
        corre(cot.cotizar(_Usuario(), pedido(), db=db_completa(tarifas_envio=[]),
                          ahora=AHORA))
    assert e.value.http == 503
    assert "escalones" not in e.value.mensaje and "divisor" not in e.value.mensaje


def test_sin_bloque_de_despacho_no_se_da_un_precio_que_no_se_puede_usar():
    """Cotizar sin dirección de despacho es darle un precio a alguien que después
    no puede despachar."""
    with pytest.raises(cot.NoSePuedeCotizar) as e:
        corre(cot.cotizar(_Usuario(), pedido(),
                          db=db_completa(app_settings=[dict(CONTENIDO), dict(OPERACION)]),
                          ahora=AHORA))
    assert e.value.http == 503


def test_si_no_se_puede_guardar_no_se_devuelve_una_cotizacion_fantasma():
    base = db_completa()

    async def revienta(*a, **k):
        raise RuntimeError("mongo caído")
    base.envios.insert_one = revienta

    with pytest.raises(cot.NoSePuedeCotizar) as e:
        corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
    assert e.value.http == 503


# ─── 9. Vencimiento ───────────────────────────────────────────────────────

def test_la_cotizacion_vence_con_el_ttl_configurado():
    base = db_completa()
    corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
    vence = base.envios.filas[0]["cotizacion"]["vence_at"]
    assert vence == AHORA + timedelta(hours=48)


@pytest.mark.parametrize("ttl", [0, -3, "muchas", None, 5000])
def test_un_ttl_absurdo_no_deja_toda_cotizacion_vencida_al_nacer(ttl):
    operacion = {**OPERACION, "ttl_cotizacion_horas": ttl}
    base = db_completa(app_settings=[dict(PUNTO), dict(CONTENIDO), operacion])
    corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
    assert not cot.esta_vencida(base.envios.filas[0], ahora=AHORA)


def test_una_cotizacion_pasada_su_fecha_esta_vencida():
    envio = {"cotizacion": {"vence_at": AHORA - timedelta(minutes=1)}}
    assert cot.esta_vencida(envio, ahora=AHORA) is True


@pytest.mark.parametrize("vence", [None, "", "el jueves", 12345, {"a": 1}])
def test_una_fecha_de_vencimiento_ilegible_cuenta_como_vencida(vence):
    """El error caro es confirmar dentro de seis meses un precio de hoy."""
    assert cot.esta_vencida({"cotizacion": {"vence_at": vence}}, ahora=AHORA) is True


def test_la_banda_de_variacion_sale_en_porcentaje():
    r = corre(cot.cotizar(_Usuario(), pedido(), db=db_completa(), ahora=AHORA))
    assert r["banda_variacion_pct"] == "12"


# ─── 10. El bloque de despacho que ve el usuario ──────────────────────────

def test_al_usuario_le_llega_la_direccion_lista_para_copiar():
    r = corre(cot.cotizar(_Usuario(), pedido(), db=db_completa(), ahora=AHORA))
    assert r["retiro"]["texto_copiable"].startswith("RIS App LTDA\nA/C María Gómez")
    assert r["retiro"]["cep"] == "69355-000"


def test_al_usuario_no_le_llegan_los_datos_internos_del_retirador():
    r = corre(cot.cotizar(_Usuario(), pedido(), db=db_completa(), ahora=AHORA))
    plano = repr(r)
    assert MARIA["cpf"] not in plano and MARIA["telefono"] not in plano
    assert "retirador_id" not in r["retiro"]
    assert "retirador_motivo" not in r["retiro"]


def test_la_modalidad_de_flete_se_guarda_y_no_cambia_ni_un_centavo():
    """El flete no se cobra al cotizar, ni al crear, ni nunca dentro del envío."""
    con_destino = corre(cot.cotizar(_Usuario(), pedido(modalidad_flete="destino"),
                                    db=db_completa(), ahora=AHORA))
    con_prepago = corre(cot.cotizar(_Usuario(), pedido(modalidad_flete="prepago"),
                                    db=db_completa(), ahora=AHORA))
    assert con_destino["modalidad_flete"] == "destino"
    assert con_prepago["modalidad_flete"] == "prepago"
    assert (con_destino["a_pagar_en_risapp"]["total_estimado_ris"]
            == con_prepago["a_pagar_en_risapp"]["total_estimado_ris"])


def test_el_modulo_no_menciona_ninguna_marca():
    ruta = os.path.join(_BACKEND, "services", "envios_cotizador.py")
    fuente = open(ruta, encoding="utf-8").read().lower()
    for marca in ("mrw", "correios", "zoom", "tealca", "domesa"):
        assert marca not in fuente


# ─── 11. Lo que encontro la revision adversarial ──────────────────────────

def test_lo_que_escribe_el_cotizador_es_lo_que_lee_el_que_cobra():
    """EL DEFECTO P0, y el test que impide que vuelva.

    El cotizador guardaba las medidas anidadas y `envios_estados` las leía
    planas. Ninguna de las dos partes estaba mal por sí sola; lo que estaba mal
    era que fueran dos. El resultado: 176,75 en pantalla y 132,00 cobrado, con el
    mismo peso, las mismas medidas y la misma versión de tarifa.

    Este test no comprueba una función: comprueba que el documento que escribe un
    PR lo sabe leer el otro. Es el único que puede fallar cuando alguien renombra
    un campo con la mejor intención.
    """
    estados = _cargar("envios_estados")
    con_seguro = {
        **TARIFA,
        "sobrecargos": [{"codigo": "seguro", "nombre": "Seguro", "tipo": "porcentual",
                         "valor": "0.03", "activo": True,
                         "condicion": {"valor_declarado_mayor_a": "100"}}],
    }
    base = db_completa(tarifas_envio=[con_seguro])
    r = corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
    guardado = base.envios.filas[0]

    # El mismo paquete que se declaró, cobrado contra el comprobante.
    cobro = estados.cobro_inicial(guardado, con_seguro, "2.30", "40", "30", "20")

    assert cobro["monto"] == Decimal(r["a_pagar_en_risapp"]["total_estimado_ris"])
    assert [s["codigo"] for s in cobro["desglose"]["cotizacion"]["sobrecargos"]] \
        == [s["codigo"] for s in r["a_pagar_en_risapp"]["sobrecargos"]]
    # Y el desglose que ve el usuario no dice "declarado: 0 kg".
    declarado = cobro["desglose"]["declarado"]
    assert declarado["peso_kg"] == Decimal("2.30")
    assert declarado["largo_cm"] == Decimal("40")


def test_el_recargo_de_temporada_cotizado_es_el_que_se_cobra():
    """La fecha del cálculo es la de la COTIZACIÓN, no la del mostrador. Sin
    congelarla, un recargo cotizado no se cobraba —y uno que empezó después se
    cobraba sin que el usuario lo hubiera aceptado."""
    estados = _cargar("envios_estados")
    en_diciembre = datetime(2026, 12, 20, tzinfo=timezone.utc)
    con_temporada = {**TARIFA, "vigente_desde": en_diciembre - timedelta(days=90),
                     "recargos_temporada": [
                         {"nombre": "temporada alta", "desde": "2026-12-01",
                          "hasta": "2026-12-31", "multiplicador": "1.30",
                          "activo": True}]}
    base = db_completa(tarifas_envio=[con_temporada])
    r = corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=en_diciembre))

    # Se cobra en enero, ya fuera de la temporada.
    cobro = estados.cobro_inicial(base.envios.filas[0], con_temporada,
                                  "2.30", "40", "30", "20")
    assert cobro["desglose"]["cotizacion"]["multiplicador_temporada"] == Decimal("1.30")
    assert cobro["monto"] == Decimal(r["a_pagar_en_risapp"]["total_estimado_ris"])


def test_si_no_se_pudo_leer_un_rol_del_catalogo_no_se_cotiza():
    """Un rol que falla llegaba como lista vacía y la intersección de límites se
    calculaba solo con el otro: una caja de 110 cm que el transportista de origen
    rechaza a los 100 pasaba a cotizar bien. El usuario paga el tramo 1 y la caja
    se rechaza en el mostrador."""
    base = db_completa()
    original = base.transportistas.find

    def a_medias(filtro=None, proyeccion=None):
        if (filtro or {}).get("rol") == "brasil":
            raise RuntimeError("failover")
        return original(filtro, proyeccion)
    base.transportistas.find = a_medias

    with pytest.raises(cot.NoSePuedeCotizar) as e:
        corre(cot.cotizar(_Usuario(), pedido(paquete={"largo_cm": "110"}),
                          db=base, ahora=AHORA))
    assert e.value.http == 503


def test_un_transportista_de_destino_dado_de_baja_no_se_puede_elegir():
    """`/catalogo` no lo ofrece, pero no ofrecerlo no es lo mismo que
    rechazarlo: la ruta acepta cualquier id que el cliente mande. Y sus límites
    ya no entran en la intersección, así que cotizaría más permisivo."""
    de_baja = {**TRP_VE, "activo": False}
    with pytest.raises(cot.NoSePuedeCotizar) as e:
        corre(cot.cotizar(_Usuario(), pedido(),
                          db=db_completa(transportistas=[dict(TRP_BR), de_baja]),
                          ahora=AHORA))
    assert "no está disponible" in e.value.mensaje


def test_no_se_puede_mandar_un_paquete_a_venezuela_por_un_transportista_de_brasil():
    agencia_br = {**AGENCIA, "transportista_id": "trp_br1"}
    with pytest.raises(cot.NoSePuedeCotizar) as e:
        corre(cot.cotizar(_Usuario(),
                          pedido(destino={"transportista_id": "trp_br1"}),
                          db=db_completa(agencias=[agencia_br]), ahora=AHORA))
    assert "de la lista" in e.value.mensaje


def test_la_zona_de_una_agencia_no_se_usa_para_cotizar_a_otra_empresa():
    """Las zonas son de cada transportista. Buscar "zona_a" en la matriz de otra
    empresa devuelve el precio de una zona que para ella significa otra cosa, y
    el usuario ve al lado una orientación de una empresa que no contrató."""
    otro = {**TRP_VE, "transportista_id": "trp_ve2", "codigo": "TRP-8B4L"}
    matriz = MATRIZ + [{"transportista_id": "trp_ve2", "clave": "zona_a",
                        "hasta_kg": "10", "precio": "980.00", "moneda": "VES",
                        "actualizada_at": AHORA}]
    r = corre(cot.cotizar(
        _Usuario(), pedido(),
        db=db_completa(transportistas=[dict(TRP_BR), dict(TRP_VE), otro],
                       matrices_referencia=matriz),
        ahora=AHORA))
    venezolanas = [x for x in r["referencias"] if x["rol"] == "venezuela"]
    assert [x["codigo"] for x in venezolanas] == ["TRP-3Q9X"]
    assert "980.00" not in repr(r)


def test_cada_referencia_lleva_puesto_que_no_es_facturable():
    """No es decoración: es lo que hace que un `sum()` distraído sea un test que
    falla en vez de un cobro de más."""
    base = db_completa()
    r = corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
    assert all(x["facturable"] is False for x in r["referencias"])
    guardadas = base.envios.filas[0]["cotizacion"]["referencias"]
    assert all(x["facturable"] is False for x in guardadas)


def test_el_nombre_comercial_no_sale_por_la_cotizacion():
    """La proyección de referencias.py excluye `nombre` a propósito, para que no
    viaje a un log. Volver a pedirlo acá sería deshacer esa decisión de un lado
    sin enterarse del otro: el nombre lo pone la pantalla desde /catalogo."""
    r = corre(cot.cotizar(_Usuario(), pedido(), db=db_completa(), ahora=AHORA))
    assert all("nombre" not in x for x in r["referencias"])
    assert "Empresa de Destino" not in repr(r)


def test_los_terminos_se_congelan_aunque_el_bloque_de_contenido_no_se_lea():
    """Un envío sin registro de qué términos aceptó el usuario es un envío que no
    se puede defender."""
    base = db_completa()

    async def revienta(*a, **k):
        raise RuntimeError("timeout")
    base.app_settings.find_one = revienta

    with pytest.raises(cot.NoSePuedeCotizar):
        corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))

    # Y con el bloque simplemente no cargado, se congela la versión del código.
    base2 = db_completa(app_settings=[dict(PUNTO), dict(OPERACION)])
    corre(cot.cotizar(_Usuario(), pedido(), db=base2, ahora=AHORA))
    congelada = base2.envios.filas[0]["cotizacion"]["terminos_version"]
    assert congelada and congelada != "None"


def test_una_banda_de_variacion_en_cero_es_una_decision_y_se_respeta():
    """Un 0 cargado a propósito es "el precio no varía". Tragárselo con el
    fallback es la misma clase de bug que un `or` sobre un cero."""
    operacion = {**OPERACION, "banda_variacion_pct": "0"}
    r = corre(cot.cotizar(_Usuario(), pedido(),
                          db=db_completa(app_settings=[dict(PUNTO), dict(CONTENIDO),
                                                       operacion]),
                          ahora=AHORA))
    assert r["banda_variacion_pct"] == "0"


def test_el_minimo_de_descripcion_lo_pone_el_panel():
    """Es un criterio de aduana, no una constante de ingeniería."""
    exigente = {**CONTENIDO, "descripcion_min_caracteres": 60}
    with pytest.raises(cot.NoSePuedeCotizar) as e:
        corre(cot.cotizar(_Usuario(), pedido(),
                          db=db_completa(app_settings=[dict(PUNTO), exigente,
                                                       dict(OPERACION)]),
                          ahora=AHORA))
    assert "60 caracteres" in e.value.mensaje


def test_un_doble_clic_no_crea_dos_envios():
    """Cotizar escribe el nombre, el documento y el teléfono de una persona en
    Venezuela. Un doble clic dejaba un envío huérfano ensuciando la cola del
    panel, con esos datos adentro."""
    base = db_completa()
    primera = corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
    segunda = corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
    assert primera["envio_id"] == segunda["envio_id"]
    assert len(base.envios.filas) == 1


def test_cambiar_el_paquete_si_es_una_cotizacion_nueva():
    base = db_completa()
    primera = corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
    otra = corre(cot.cotizar(_Usuario(), pedido(paquete={"peso_kg": "4.10"}),
                             db=base, ahora=AHORA))
    assert primera["envio_id"] != otra["envio_id"]
    assert len(base.envios.filas) == 2


def test_una_cotizacion_vencida_no_se_reutiliza():
    base = db_completa()
    primera = corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
    despues = corre(cot.cotizar(_Usuario(), pedido(), db=base,
                                ahora=AHORA + timedelta(hours=49)))
    assert primera["envio_id"] != despues["envio_id"]


def test_no_se_pueden_acumular_cotizaciones_sin_confirmar_para_siempre():
    """Sin cota, un bucle deja la colección del tamaño que se quiera, con datos
    personales de terceros adentro."""
    base = db_completa()
    for i in range(cot.COTIZACIONES_ABIERTAS_MAX):
        corre(cot.cotizar(_Usuario(), pedido(paquete={"peso_kg": f"{2 + i}.10"}),
                          db=base, ahora=AHORA))
    with pytest.raises(cot.NoSePuedeCotizar) as e:
        corre(cot.cotizar(_Usuario(), pedido(paquete={"peso_kg": "9.90"}),
                          db=base, ahora=AHORA))
    assert "sin confirmar" in e.value.mensaje
    assert len(base.envios.filas) == cot.COTIZACIONES_ABIERTAS_MAX


def test_las_cotizaciones_vencidas_no_cuentan_para_la_cota():
    base = db_completa()
    for i in range(cot.COTIZACIONES_ABIERTAS_MAX):
        corre(cot.cotizar(_Usuario(), pedido(paquete={"peso_kg": f"{2 + i}.10"}),
                          db=base, ahora=AHORA))
    r = corre(cot.cotizar(_Usuario(), pedido(paquete={"peso_kg": "9.90"}),
                          db=base, ahora=AHORA + timedelta(hours=49)))
    assert r["envio_id"]


def test_una_medida_absurdamente_larga_no_entra_en_la_base():
    """"2." seguido de dos millones de treses vale 2.33 y pasa todos los rangos.
    Cuatro campos así son 8 MB por documento."""
    with pytest.raises(Exception):
        pedido(paquete={"peso_kg": "2." + "3" * 2_000_000})


def test_el_cliente_no_puede_pedirse_un_descuento_por_cantidad():
    """El motor sabe aplicar un descuento por bultos y nada multiplica el precio
    por bultos: exponer el campo lo volvía una palanca de descuento del cliente,
    sin que nada verificara después cuántas cajas se despacharon."""
    with pytest.raises(Exception):
        pedido(paquete={"bultos": 100})

    con_descuento = {**TARIFA,
                     "descuentos_cantidad": [{"desde_bultos": 10, "descuento": "0.25"}]}
    base = db_completa(tarifas_envio=[con_descuento])
    r = corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
    sin_descuento = tarifas.cotizar_servicio(con_descuento, "2.30", "40", "30", "20",
                                             valor_declarado="180.00", bultos=1,
                                             fecha=AHORA.date())["total"]
    assert Decimal(r["a_pagar_en_risapp"]["total_estimado_ris"]) == sin_descuento
    assert base.envios.filas[0]["paquete"]["bultos"] == 1


def test_una_tarifa_sin_version_no_produce_un_envio_que_no_se_puede_cobrar():
    """Sin versión congelada, los dos cobros posteriores fallan PARA SIEMPRE."""
    sin_version = {k: v for k, v in TARIFA.items() if k != "version_id"}
    with pytest.raises(cot.NoSePuedeCotizar) as e:
        corre(cot.cotizar(_Usuario(), pedido(),
                          db=db_completa(tarifas_envio=[sin_version]), ahora=AHORA))
    assert e.value.http == 503


@pytest.mark.parametrize("coleccion,metodo", [
    ("app_settings", "find_one"),          # cuelga la lectura de configuración
    ("colaboradores_retiro", "find"),      # cuelga el bloque de despacho
])
def test_una_lectura_colgada_no_se_queda_con_el_worker(coleccion, metodo):
    """El cliente de Mongo del proyecto no fija socketTimeout, o sea que una
    lectura colgada —no caída: colgada— espera para siempre y se queda con un
    worker. Los DOS bloques en paralelo necesitan su tope, y por eso el test
    cuelga uno de cada uno: con el tope puesto en solo uno, el otro sigue
    esperando y este test lo dice."""
    base = db_completa()

    async def nunca(*a, **k):
        await asyncio.sleep(30)

    if metodo == "find":
        def cuelga(*a, **k):
            class _C:
                async def to_list(self, n):
                    await asyncio.sleep(30)
            return _C()
        setattr(getattr(base, coleccion), metodo, cuelga)
    else:
        setattr(getattr(base, coleccion), metodo, nunca)

    cot.TIMEOUT_ACCESORIOS_S = 0.2
    try:
        with pytest.raises(cot.NoSePuedeCotizar) as e:
            corre(cot.cotizar(_Usuario(), pedido(), db=base, ahora=AHORA))
        assert e.value.http == 503
    finally:
        cot.TIMEOUT_ACCESORIOS_S = 6.0


def test_los_indices_de_la_cotizacion_estan_declarados():
    indices = _cargar("envios_indices").INDICES
    claves = [(c, str(k)) for c, k, _ in indices]
    assert any(c == "envios" and "huella" in k for c, k in claves), \
        "sin índice, la deduplicación es un barrido de la colección entera"
    ttl = [o for c, k, o in indices
           if c == "envios" and k == "cotizacion.vence_at"]
    assert ttl and ttl[0].get("expireAfterSeconds") == 0
    # PARCIAL: un TTL a secas sobre vence_at borraría envíos reales.
    assert ttl[0]["partialFilterExpression"] == {"estado": "cotizado"}
