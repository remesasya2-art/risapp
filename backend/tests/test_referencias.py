"""
Las orientaciones de los transportistas: numeros que se muestran y no se cobran.

CONTEXTO
    El usuario contrata y paga por su cuenta los dos tramos de los extremos: el
    transportista brasileño que lleva el paquete hasta Pacaraima y el venezolano
    que lo lleva desde Santa Elena. RIS App igual le muestra un aproximado de cada
    uno, porque sin eso no puede decidir si le conviene mandar el paquete.

    Esos numeros son ORIENTACION. No se facturan, no se concilian y jamas entran
    en el total que RIS App cobra. Y como no se cobran, que falten no puede
    romper nada: el precio propio no depende de ellos.

QUE SE CUBRE
    1. Una clave sin fila en la matriz devuelve monto None y un motivo, sin lanzar.
    2. Un paquete mas pesado que la ultima franja cargada tampoco rompe.
    3. La base caida tampoco: la cotizacion se completa igual sin NINGUNA de las
       dos referencias.
    4. Toda referencia sale marcada facturable=False, incluidas las que no tienen
       dato. Es lo que hace que un sum() distraido en la ruta sea un test que
       falla y no un cobro indebido.
    5. El peso se convierte al facturable DE CADA TRANSPORTISTA antes de buscar
       en su matriz: la misma caja cae en franjas distintas segun el divisor.
    6. Una matriz que nadie refresco en un mes se marca desactualizada.
    7. Ningun nombre de empresa: los transportistas se nombran por su codigo.

La base se inyecta: no hace falta Mongo para probar esto. El fake de abajo imita
lo justo de motor —find().sort().to_list() y find_one(sort=...)— y nada mas.
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
ref = _cargar("referencias")


def corre(coro):
    return asyncio.run(coro)


# ─── Un Mongo de mentira, con lo justo ────────────────────────────────────

class _Cursor:
    def __init__(self, filas):
        self._filas = list(filas)

    def sort(self, campo, direccion=1):
        self._filas.sort(key=lambda d: d.get(campo, 0), reverse=direccion < 0)
        return self

    async def to_list(self, _n):
        return list(self._filas)


def _proyectar(doc, proyeccion):
    """Aplica la proyección como lo haría Mongo. El fake TIENE que hacerlo: sin
    esto, un campo que la consulta no pide igual llega al código bajo prueba, y
    un olvido en la proyección pasa los tests y falla en producción."""
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
        candidatos = [d for d in self.filas if self._coincide(d, filtro)]
        if sort:
            campo, direccion = sort[0]
            candidatos.sort(key=lambda d: d.get(campo, 0), reverse=direccion < 0)
        return candidatos[0] if candidatos else None


class _Db:
    def __init__(self, transportistas, matrices, rompe=False):
        self.transportistas = _Coleccion(transportistas, rompe)
        self.matrices_referencia = _Coleccion(matrices, rompe)


# ─── Datos de prueba. Solo códigos, ningún nombre. ────────────────────────

TRP_BR = {"transportista_id": "trp_br1", "codigo": "TRP-7K2M", "rol": "brasil",
          "activo": True, "orden": 1, "moneda": "BRL",
          "regla_peso": {"divisor": 6000, "escalon_kg": "1", "minimo_kg": "0.3",
                         "umbral_cubado_kg": "5"},
          "limites": {"peso_max_kg": 30, "lado_max_cm": 100}}
TRP_VE1 = {"transportista_id": "trp_ve1", "codigo": "TRP-3Q9X", "rol": "venezuela",
           "activo": True, "orden": 1, "moneda": "USD",
           "regla_peso": {"divisor": 5000, "escalon_kg": "0.5", "minimo_kg": "1"}}
TRP_VE2 = {"transportista_id": "trp_ve2", "codigo": "TRP-8H4L", "rol": "venezuela",
           "activo": True, "orden": 2, "moneda": "USD",
           "regla_peso": {"divisor": 4000, "escalon_kg": "0.5", "minimo_kg": "1"}}
TRP_BAJA = {"transportista_id": "trp_ve9", "codigo": "TRP-0000", "rol": "venezuela",
            "activo": False, "orden": 3}

# Relativas a hoy: con fechas fijas, la suite empieza a fallar sola el día que
# la "reciente" cumple un mes, y el que la vea va a creer que rompió algo.
_AHORA = datetime.now(timezone.utc)
RECIENTE = (_AHORA - timedelta(days=2)).isoformat().replace("+00:00", "Z")
VIEJA = (_AHORA - timedelta(days=200)).isoformat().replace("+00:00", "Z")

MATRICES = [
    {"transportista_id": "trp_br1", "clave": "SP", "hasta_kg": 5, "precio": "62.00",
     "moneda": "BRL", "actualizada_at": RECIENTE, "origen": "job"},
    {"transportista_id": "trp_br1", "clave": "SP", "hasta_kg": 10, "precio": "94.00",
     "moneda": "BRL", "actualizada_at": RECIENTE, "origen": "job"},
    {"transportista_id": "trp_ve1", "clave": "ZONA-A", "hasta_kg": 5, "precio": "18.00",
     "moneda": "USD", "actualizada_at": VIEJA, "origen": "manual"},
    {"transportista_id": "trp_ve2", "clave": "ZONA-A", "hasta_kg": 5, "precio": "15.00",
     "moneda": "USD", "actualizada_at": RECIENTE, "origen": "manual"},
    {"transportista_id": "trp_ve2", "clave": "ZONA-A", "hasta_kg": 10, "precio": "23.00",
     "moneda": "USD", "actualizada_at": RECIENTE, "origen": "manual"},
]

TODOS = [TRP_BR, TRP_VE1, TRP_VE2, TRP_BAJA]


def db_normal():
    return _Db(TODOS, MATRICES)


# ─── 1. Catálogo ──────────────────────────────────────────────────────────

def test_solo_los_activos_y_en_el_orden_del_panel():
    ves = corre(ref.transportistas_activos("venezuela", db=db_normal()))
    assert [t["codigo"] for t in ves] == ["TRP-3Q9X", "TRP-8H4L"]


@pytest.mark.parametrize("rol", ["brazil", "", None, "BRASIL", "propio"])
def test_un_rol_desconocido_devuelve_vacio_y_no_lanza(rol):
    """Si mañana alguien escribe "brazil" en una ruta, el usuario tiene que ver
    una cotización sin esa orientación, no un 500."""
    assert corre(ref.transportistas_activos(rol, db=db_normal())) == []


def test_ris_app_no_es_un_transportista():
    """El tramo propio nunca sale de esta tabla: no es una elección, es el
    servicio que se vende."""
    assert set(ref.ROLES) == {"brasil", "venezuela"}


def test_la_base_caida_devuelve_vacio_y_no_lanza():
    caida = _Db(TODOS, MATRICES, rompe=True)
    assert corre(ref.transportistas_activos("brasil", db=caida)) == []


# ─── 2. Una referencia ────────────────────────────────────────────────────

def test_una_referencia_con_dato():
    r = corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20, db=db_normal()))
    assert r["monto"] == Decimal("62.00")
    assert r["moneda"] == "BRL"
    assert r["fuente"] == "matriz"
    assert r["codigo"] == "TRP-7K2M"
    assert r["facturable"] is False


def test_cada_transportista_busca_con_SU_peso_facturable():
    """La misma caja: 40x30x20 = 24.000 cm3. Con divisor 6000 y umbral 5 kg el
    cubado es 4 y no aplica, así que pesa 2. Con divisor 4000 da 6 kg y cae en
    otra franja. Buscar en la matriz con el peso real daría la franja equivocada,
    así que no alcanza con mirar el peso: hay que mirar el PRECIO que salió."""
    br = corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20, db=db_normal()))
    ve = corre(ref.cotizar_referencia(TRP_VE2, "ZONA-A", 2, 40, 30, 20, db=db_normal()))
    assert br["peso_facturable_kg"] == Decimal("2.000")
    assert ve["peso_facturable_kg"] == Decimal("6.000")
    # Con el peso real (2 kg) habría caído en la franja de 5 y cobrado 15,00.
    assert ve["hasta_kg"] == Decimal("10")
    assert ve["monto"] == Decimal("23.00")


def test_la_franja_que_se_toma_es_la_mas_chica_que_alcanza():
    """7 kg no entran en la franja de 5: tiene que caer en la de 10, no al revés."""
    r = corre(ref.cotizar_referencia(TRP_BR, "SP", 7, 10, 10, 10, db=db_normal()))
    assert r["hasta_kg"] == Decimal("10")
    assert r["monto"] == Decimal("94.00")


# ─── 3. Lo que falta no rompe nada ────────────────────────────────────────

def test_una_clave_sin_fila_devuelve_null_con_su_motivo():
    r = corre(ref.cotizar_referencia(TRP_BR, "AM", 2, 40, 30, 20, db=db_normal()))
    assert r["monto"] is None
    assert r["fuente"] == "sin_dato"
    assert r["facturable"] is False


def test_un_paquete_mas_pesado_que_la_tabla_tampoco_rompe():
    """Nadie cargó una franja de 40 kg. Eso es "no sé", no un error."""
    r = corre(ref.cotizar_referencia(TRP_BR, "SP", 40, 10, 10, 10, db=db_normal()))
    assert r["monto"] is None and r["fuente"] == "sin_dato"
    assert r["peso_facturable_kg"] == Decimal("40.000")


@pytest.mark.parametrize("clave", [None, "", 0])
def test_sin_clave_no_se_va_a_buscar_nada(clave):
    r = corre(ref.cotizar_referencia(TRP_BR, clave, 2, 40, 30, 20, db=db_normal()))
    assert r["monto"] is None and r["fuente"] == "sin_clave"


def test_la_base_caida_devuelve_una_referencia_sin_dato():
    caida = _Db(TODOS, MATRICES, rompe=True)
    r = corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20, db=caida))
    assert r["monto"] is None and r["fuente"] == "error"


def test_un_transportista_sin_ficha_no_lanza():
    for t in ({}, None):
        r = corre(ref.cotizar_referencia(t, "SP", 2, 40, 30, 20, db=db_normal()))
        assert r["monto"] is None
        assert r["codigo"] == "?"


# ─── 4. Las dos referencias juntas ────────────────────────────────────────

def test_se_devuelven_todas_las_orientaciones_de_los_dos_roles():
    refs = corre(ref.referencias_para("SP", "ZONA-A", 2, 40, 30, 20, db=db_normal()))
    assert [r["codigo"] for r in refs] == ["TRP-7K2M", "TRP-3Q9X", "TRP-8H4L"]
    assert ref.resumen(refs)["completo"] is True


def test_la_cotizacion_se_completa_igual_sin_ninguna_referencia():
    """Es LA regla del módulo: el precio que RIS App cobra no depende de estos
    números. Con la base caída la cotización sigue, y la lista lo DICE."""
    caida = _Db(TODOS, MATRICES, rompe=True)
    refs = corre(ref.referencias_para("SP", "ZONA-A", 2, 40, 30, 20, db=caida))
    assert [r["fuente"] for r in refs] == ["catalogo_no_disponible"] * 2
    assert all(r["monto"] is None for r in refs)
    assert ref.resumen(refs)["hay_problemas"] is True
    assert ref.resumen(refs)["completo"] is False


def test_base_caida_no_se_confunde_con_panel_vacio():
    """"No hay transportistas configurados" lo arregla el super administrador;
    "Mongo no contestó", no. Desde afuera se parecen y no son lo mismo."""
    vacio = _Db([], [])
    refs = corre(ref.referencias_para("SP", "ZONA-A", 2, 40, 30, 20, db=vacio))
    assert refs == []
    assert ref.resumen(refs)["hay_problemas"] is False

    # Y con catálogo pero sin matrices, una entrada por transportista, sin monto.
    sin_matrices = _Db(TODOS, [])
    refs = corre(ref.referencias_para("SP", "ZONA-A", 2, 40, 30, 20, db=sin_matrices))
    assert len(refs) == 3
    assert all(r["monto"] is None for r in refs)
    assert all(r["fuente"] == "sin_dato" for r in refs)


def test_una_referencia_rota_no_se_lleva_puestas_a_las_otras():
    solo_br = _Db(TODOS, [m for m in MATRICES if m["transportista_id"] == "trp_br1"])
    refs = corre(ref.referencias_para("SP", "ZONA-A", 2, 40, 30, 20, db=solo_br))
    con_dato = [r for r in refs if r["monto"] is not None]
    assert len(con_dato) == 1 and con_dato[0]["codigo"] == "TRP-7K2M"
    r = ref.resumen(refs)
    assert r["total_transportistas"] == 3 and r["con_dato"] == 1 and r["sin_dato"] == 2
    assert r["completo"] is False and r["hay_problemas"] is False


# ─── 5. Ninguna referencia se factura ─────────────────────────────────────

def test_absolutamente_toda_referencia_sale_marcada_como_no_facturable():
    """Incluidas las que no tienen dato. Es lo que hace que sumar esto al total
    sea un test que falla y no un cobro indebido en producción."""
    escenarios = [db_normal(), _Db(TODOS, []), _Db(TODOS, MATRICES, rompe=False)]
    for base in escenarios:
        for r in corre(ref.referencias_para("SP", "ZONA-A", 2, 40, 30, 20, db=base)):
            assert r["facturable"] is False
    for clave in ("AM", "", None):
        r = corre(ref.cotizar_referencia(TRP_BR, clave, 2, 40, 30, 20, db=db_normal()))
        assert r["facturable"] is False


def test_el_resumen_no_suma_montos():
    """Sumarlos daría un número que parece un total y no lo es: son dos contratos
    con dos empresas distintas, en dos monedas distintas. Y ese número terminaría
    algún día al lado del que RIS App sí cobra.

    Se comprueba el conjunto EXACTO de claves y que ningún valor sea un monto —en
    Decimal o en float—, porque "no hay una clave que se llame total" lo esquiva
    cualquiera que la llame `orientacion_estimada`."""
    refs = corre(ref.referencias_para("SP", "ZONA-A", 2, 40, 30, 20, db=db_normal()))
    r = ref.resumen(refs)
    assert set(r) == {"total_transportistas", "con_dato", "sin_dato",
                      "hay_desactualizadas", "hay_problemas", "monedas", "completo"}
    for clave, valor in r.items():
        assert isinstance(valor, (int, bool, list)), f"{clave} parece un monto: {valor!r}"
        assert not isinstance(valor, (Decimal, float))


def test_las_monedas_conviven_sin_convertirse():
    refs = corre(ref.referencias_para("SP", "ZONA-A", 2, 40, 30, 20, db=db_normal()))
    monedas = {r["moneda"] for r in refs if r["monto"] is not None}
    assert monedas == {"BRL", "USD"}
    assert ref.resumen(refs)["monedas"] == ["BRL", "USD"]


def test_el_monto_es_decimal_y_nunca_float():
    """Un float es lo que haría que un sum() distraído en la ruta funcione en
    silencio, que es exactamente lo que services/money.py existe para evitar."""
    for r in corre(ref.referencias_para("SP", "ZONA-A", 2, 40, 30, 20, db=db_normal())):
        assert isinstance(r["monto"], Decimal)
        assert not isinstance(r["monto"], float)


# ─── 6. Frescura ──────────────────────────────────────────────────────────

def test_una_matriz_vieja_se_marca_desactualizada():
    vieja = corre(ref.cotizar_referencia(TRP_VE1, "ZONA-A", 2, 40, 30, 20, db=db_normal()))
    fresca = corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20, db=db_normal()))
    assert vieja["desactualizada"] is True
    assert fresca["desactualizada"] is False


def test_una_fila_sin_fecha_se_considera_vieja():
    """Una matriz que no dice cuándo se cargó no puede presentarse como fresca."""
    sin_fecha = _Db(TODOS, [{"transportista_id": "trp_br1", "clave": "SP",
                             "hasta_kg": 5, "precio": "62.00", "moneda": "BRL"}])
    r = corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20, db=sin_fecha))
    assert r["desactualizada"] is True


def test_una_fecha_ilegible_tambien():
    rara = _Db(TODOS, [{"transportista_id": "trp_br1", "clave": "SP", "hasta_kg": 5,
                        "precio": "62.00", "actualizada_at": "el martes pasado"}])
    r = corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20, db=rara))
    assert r["desactualizada"] is True


def test_el_umbral_de_frescura_es_configurable():
    r = corre(ref.cotizar_referencia(TRP_VE1, "ZONA-A", 2, 40, 30, 20,
                                     db=db_normal(), dias_frescura=100000))
    assert r["desactualizada"] is False


def test_el_resumen_avisa_si_alguna_esta_vieja():
    refs = corre(ref.referencias_para("SP", "ZONA-A", 2, 40, 30, 20, db=db_normal()))
    assert ref.resumen(refs)["hay_desactualizadas"] is True


# ─── 7. Ningún nombre de empresa ──────────────────────────────────────────

def test_el_modulo_no_menciona_ninguna_marca():
    fuente = open(os.path.join(_BACKEND, "services", "referencias.py"),
                  encoding="utf-8").read().lower()
    for marca in ("mrw", "correios", "zoom", "tealca", "domesa", "serviex"):
        assert marca not in fuente, f"aparece {marca} en el código"


def test_a_los_transportistas_se_los_nombra_por_codigo():
    assert ref.codigo_de(TRP_BR) == "TRP-7K2M"
    assert ref.codigo_de({"transportista_id": "trp_x"}) == "trp_x"
    assert ref.codigo_de({}) == "?"
    assert ref.codigo_de(None) == "?"


def test_un_rol_desconocido_ni_siquiera_toca_la_base():
    """Devolver vacío porque la consulta no encontró nada y devolverlo porque el
    rol no existe se parecen desde afuera, pero no son lo mismo: el primero es un
    viaje a Mongo por cada cotización, con un typo que nadie ve en los logs."""
    class _Espia(_Db):
        def __init__(self):
            super().__init__(TODOS, MATRICES)
            self.consultas = 0
            find_real = self.transportistas.find

            def find(filtro, proj=None):
                self.consultas += 1
                return find_real(filtro, proj)

            self.transportistas.find = find

    espia = _Espia()
    assert corre(ref.transportistas_activos("brazil", db=espia)) == []
    assert espia.consultas == 0
    assert corre(ref.transportistas_activos("brasil", db=espia)) != []
    assert espia.consultas == 1


# ─── 8. Los tipos que Mongo guarda de verdad ──────────────────────────────
#
# Mongo compara tipos con "type bracketing": un hasta_kg guardado como string
# nunca matchea un $gte numérico, y un Decimal128 no es >= el double que sale de
# float(Decimal(...)). Filtrar en la consulta hacía que estos casos devolvieran
# "sin dato" en producción con los tests en verde. Por eso el módulo trae las
# filas de esa clave y elige en Python, con to_decimal, que sabe leer las cuatro
# formas. Estos tests fijan esa decisión.

from bson.decimal128 import Decimal128   # noqa: E402


@pytest.mark.parametrize("tope,precio", [
    (5, "62.00"),                       # int
    (5.0, "62.00"),                     # double
    ("5", "62.00"),                     # string, como lo deja una importación CSV
    (Decimal128("5"), Decimal128("62.00")),   # lo que escribe services/money.py
])
def test_la_franja_se_encuentra_sea_cual_sea_el_tipo_guardado(tope, precio):
    base = _Db(TODOS, [{"transportista_id": "trp_br1", "clave": "SP",
                        "hasta_kg": tope, "precio": precio,
                        "moneda": "BRL", "actualizada_at": RECIENTE}])
    r = corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20, db=base))
    assert r["fuente"] == "matriz"
    assert r["monto"] == Decimal("62.00")


def test_el_borde_exacto_no_se_pierde_por_el_redondeo_del_float():
    """float(Decimal("2.1")) es 2.1000000000000000888…, así que preguntarle a
    Mongo por >= ese double deja afuera la franja de 2,1 guardada como decimal."""
    base = _Db(TODOS, [{"transportista_id": "trp_ve1", "clave": "ZONA-A",
                        "hasta_kg": Decimal128("2.5"), "precio": "18.00",
                        "actualizada_at": RECIENTE}])
    r = corre(ref.cotizar_referencia(TRP_VE1, "ZONA-A", "2.3", 10, 10, 10, db=base))
    assert r["peso_facturable_kg"] == Decimal("2.500")
    assert r["fuente"] == "matriz"


@pytest.mark.parametrize("activo", [True, 1, "true", "si"])
def test_un_transportista_activo_de_cualquier_forma_aparece(activo):
    """{"activo": True} en la consulta no matchea un 1 ni un "true": el panel que
    serializa el checkbox como número hacía desaparecer al transportista de las
    orientaciones sin un solo log."""
    t = dict(TRP_BR, activo=activo)
    assert corre(ref.transportistas_activos("brasil", db=_Db([t], MATRICES))) != []


@pytest.mark.parametrize("activo", [False, 0, "false", "no", ""])
def test_y_uno_dado_de_baja_de_cualquier_forma_no(activo):
    t = dict(TRP_BR, activo=activo)
    assert corre(ref.transportistas_activos("brasil", db=_Db([t], MATRICES))) == []


# ─── 9. Datos malos que no pueden pasar por buenos ────────────────────────

@pytest.mark.parametrize("precio", [None, "", "gratis", "62,00", 0, "0", -5])
def test_un_precio_ilegible_no_se_muestra_como_cero(precio):
    """"R$ 0,00" es un tramo aparentemente gratis, indistinguible de un precio
    real. Un precio que no se puede leer es "no sé", no "sale cero"."""
    base = _Db(TODOS, [{"transportista_id": "trp_br1", "clave": "SP", "hasta_kg": 5,
                        "precio": precio, "actualizada_at": RECIENTE}])
    r = corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20, db=base))
    assert r["monto"] is None
    assert r["fuente"] == "precio_invalido"
    assert ref.resumen([r])["completo"] is False


def test_dos_franjas_con_el_mismo_tope_desempatan_por_la_mas_reciente():
    """Sin desempate, el precio depende del orden en que Mongo devuelva las filas
    — que no está garantizado y cambia con el tiempo."""
    base = _Db(TODOS, [
        {"transportista_id": "trp_br1", "clave": "SP", "hasta_kg": 5,
         "precio": "999.00", "actualizada_at": VIEJA},
        {"transportista_id": "trp_br1", "clave": "SP", "hasta_kg": 5,
         "precio": "62.00", "actualizada_at": RECIENTE},
    ])
    for _ in range(2):
        r = corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20, db=base))
        assert r["monto"] == Decimal("62.00")
    base.matrices_referencia.filas.reverse()
    assert corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20,
                                        db=base))["monto"] == Decimal("62.00")


@pytest.mark.parametrize("basura", [1756500000, 1756500000.0, [], {}, object()])
def test_una_fecha_de_un_tipo_raro_no_hace_lanzar(basura):
    """Un job que guarda epoch en vez de ISO reventaba la referencia entera
    adentro de la función que promete no lanzar."""
    base = _Db(TODOS, [{"transportista_id": "trp_br1", "clave": "SP", "hasta_kg": 5,
                        "precio": "62.00", "actualizada_at": basura}])
    r = corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20, db=base))
    assert r["monto"] == Decimal("62.00")
    assert r["desactualizada"] is True


def test_una_fila_que_no_es_un_documento_se_ignora():
    """Mongo no debería devolver esto nunca; el módulo igual no se cae, porque la
    selección de franja es la única parte que un día podría recibir filas de otra
    fuente —un CSV a medio importar, por ejemplo—."""
    buena = {"transportista_id": "trp_br1", "clave": "SP", "hasta_kg": 5,
             "precio": "62.00", "actualizada_at": RECIENTE}
    elegida = ref._elegir_franja(["no soy un dict", None, 42, buena], Decimal("2"))
    assert elegida is buena
    assert ref._elegir_franja(["basura"], Decimal("2")) is None
    assert ref._elegir_franja(None, Decimal("2")) is None


# ─── 10. Ni romper ni colgar ──────────────────────────────────────────────

def test_una_base_lenta_no_cuelga_la_cotizacion():
    """Una base degradada casi nunca falla: tarda. Sin tope de tiempo la
    cotización se queda esperando para siempre por un número que ni se cobra."""
    class _Lenta(_Db):
        def __init__(self):
            super().__init__(TODOS, MATRICES)
            find_real = self.transportistas.find

            def find(filtro, proj=None):
                cursor = find_real(filtro, proj)
                to_list_real = cursor.to_list

                async def to_list(n):
                    await asyncio.sleep(5)
                    return await to_list_real(n)

                cursor.to_list = to_list
                return cursor

            self.transportistas.find = find

    refs = corre(ref.referencias_para("SP", "ZONA-A", 2, 40, 30, 20,
                                      db=_Lenta(), timeout_s=0.05))
    assert [r["fuente"] for r in refs] == ["timeout", "timeout"]
    assert all(r["facturable"] is False for r in refs)


def test_las_consultas_de_un_rol_van_en_paralelo():
    """Cinco lecturas de 200 ms en serie le agregan un segundo a la cotización."""
    class _Lenta(_Db):
        def __init__(self):
            super().__init__(TODOS, MATRICES)
            find_real = self.matrices_referencia.find

            def find(filtro, proj=None):
                cursor = find_real(filtro, proj)
                to_list_real = cursor.to_list

                async def to_list(n):
                    await asyncio.sleep(0.05)
                    return await to_list_real(n)

                cursor.to_list = to_list
                return cursor

            self.matrices_referencia.find = find

    import time
    inicio = time.monotonic()
    refs = corre(ref.referencias_para("SP", "ZONA-A", 2, 40, 30, 20, db=_Lenta()))
    transcurrido = time.monotonic() - inicio
    assert len(refs) == 3
    # En serie serían 3 x 50 ms; en paralelo, dos tandas de 50 ms.
    assert transcurrido < 0.14, f"tardó {transcurrido:.3f}s: parecen consultas en serie"


def test_un_import_roto_de_la_base_tampoco_rompe_la_cotizacion():
    """Sin db inyectado el módulo importa el real. Ese import también puede
    fallar, y estaba fuera del try."""
    import builtins
    real = builtins.__import__

    def falla(nombre, *a, **k):
        if nombre == "database":
            raise ImportError("no hay base configurada")
        return real(nombre, *a, **k)

    builtins.__import__ = falla
    try:
        assert corre(ref.transportistas_activos("brasil")) == []
        r = corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20))
        assert r["fuente"] == "error" and r["monto"] is None
        refs = corre(ref.referencias_para("SP", "ZONA-A", 2, 40, 30, 20))
        assert [r["fuente"] for r in refs] == ["catalogo_no_disponible"] * 2
    finally:
        builtins.__import__ = real


# ─── 11. La forma del payload ─────────────────────────────────────────────

def test_todas_las_salidas_tienen_exactamente_las_mismas_claves():
    """Un consumidor que lea r["desactualizada"] en la referencia que no tuvo
    dato no puede llevarse un KeyError."""
    casos = [
        corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20, db=db_normal())),
        corre(ref.cotizar_referencia(TRP_BR, "AM", 2, 40, 30, 20, db=db_normal())),
        corre(ref.cotizar_referencia(TRP_BR, None, 2, 40, 30, 20, db=db_normal())),
        corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20,
                                     db=_Db(TODOS, MATRICES, rompe=True))),
    ]
    casos += corre(ref.referencias_para("SP", "ZONA-A", 2, 40, 30, 20,
                                        db=_Db(TODOS, MATRICES, rompe=True)))
    esperadas = set(ref._FORMA)
    for c in casos:
        assert set(c) == esperadas, f"{c['fuente']} tiene otra forma"
        assert c["fuente"] in ref.MOTIVOS


def test_el_payload_no_arrastra_el_id_de_mongo():
    """Un ObjectId rompe la serialización de la respuesta."""
    for r in corre(ref.referencias_para("SP", "ZONA-A", 2, 40, 30, 20, db=db_normal())):
        assert "_id" not in r


def test_la_referencia_dice_de_donde_salio_el_dato():
    """Manual o del job: es la diferencia entre un número que alguien revisó y
    uno que salió de un parseo."""
    r = corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20, db=db_normal()))
    assert r["origen_dato"] == "job"
    assert r["rol"] == "brasil"
    sin_origen = _Db(TODOS, [{"transportista_id": "trp_br1", "clave": "SP", "hasta_kg": 5,
                              "precio": "62.00", "actualizada_at": RECIENTE}])
    assert corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20,
                                        db=sin_origen))["origen_dato"] == "manual"


def test_la_moneda_de_la_fila_le_gana_a_la_de_la_ficha():
    sin_moneda = _Db(TODOS, [{"transportista_id": "trp_br1", "clave": "SP", "hasta_kg": 5,
                              "precio": "62.00", "actualizada_at": RECIENTE}])
    r = corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20, db=sin_moneda))
    assert r["moneda"] == "BRL"          # cae a la de la ficha


# ─── 12. El nombre de la empresa no sale de la base ───────────────────────

def test_el_nombre_comercial_nunca_sale_del_modulo():
    """No alcanza con que el código no mencione marcas: el nombre está en la
    ficha, y basta un fallback "por si el código está vacío" para que empiece a
    viajar en los logs y en el payload."""
    assert "nombre" not in ref._PROYECCION_TRANSPORTISTA
    ficha = {"transportista_id": "trp_x", "nombre": "Empresa Real S.A."}
    assert ref.codigo_de(ficha) == "trp_x"
    assert ref.codigo_de({"nombre": "Empresa Real S.A."}) == "?"
    r = corre(ref.cotizar_referencia(dict(TRP_BR, nombre="Empresa Real S.A."),
                                     "SP", 2, 40, 30, 20, db=db_normal()))
    assert "Empresa Real" not in str(r)


def test_ninguna_referencia_puede_salir_marcada_como_facturable():
    """El candado está al final de _referencia() y pisa cualquier valor que le
    llegue. Es la última línea de defensa entre una orientación y un cobro."""
    r = ref._referencia(TRP_BR, "SP", monto=Decimal("62.00"), facturable=True,
                        fuente="matriz")
    assert r["facturable"] is False


def test_una_fecha_naive_se_interpreta_como_utc():
    """Motor devuelve datetimes naive porque database.py crea el cliente sin
    tz_aware. Interpretarlos como hora local daría hasta 12 horas de error."""
    naive = datetime.utcnow() - timedelta(days=1)
    base = _Db(TODOS, [{"transportista_id": "trp_br1", "clave": "SP", "hasta_kg": 5,
                        "precio": "62.00", "actualizada_at": naive}])
    r = corre(ref.cotizar_referencia(TRP_BR, "SP", 2, 40, 30, 20, db=base))
    assert r["desactualizada"] is False


def test_la_ficha_trae_los_limites_aunque_este_modulo_no_los_use():
    """Los usa envios_policy para la intersección. Sin ellos, la pantalla recibe
    todos los límites en null y los lee como "sin restricciones" — el bug del
    PR #40 entrando por la puerta de atrás. Este test existe porque el fake
    original ignoraba las proyecciones y no lo veía."""
    activos = corre(ref.transportistas_activos("brasil", db=db_normal()))
    assert activos and activos[0].get("limites"), "la proyección se comió los límites"
    assert activos[0]["limites"]["peso_max_kg"] == 30


def test_la_proyeccion_sigue_sin_traer_el_nombre():
    ficha = dict(TRP_BR, nombre="Empresa Real S.A.")
    activos = corre(ref.transportistas_activos("brasil", db=_Db([ficha], MATRICES)))
    assert "nombre" not in activos[0]
