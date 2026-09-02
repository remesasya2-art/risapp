"""
El panel del operador: lo que pasa con el paquete.

CONTEXTO
    Cinco momentos en que alguien del equipo toca un envio: avisar que llego a la
    agencia de Pacaraima, retirarlo del mostrador por LOTE, repesarlo con balanza
    propia, sacarlo hacia Santa Elena, y entregarlo con guia.

EL REPESAJE ES EL UNICO MOMENTO EN QUE EL PRECIO SE CIERRA
    Hasta ahi todo fue estimado: la cotizacion sobre lo declarado y el cobro
    inicial sobre lo que midio el transportista de origen. El ajuste tiene TRES
    ramas —cobrar, devolver, nada— porque un ajuste que solo sube no es un
    ajuste, es un recargo.

LA UNICA PALANCA DE COBRO ES LA POSESION FISICA
    El paquete no sale de Pacaraima con una partida impaga. Lo contrario tambien:
    mientras viaja por Brasil una deuda no frena nada, porque el paquete no
    depende de nosotros.

QUE SE CUBRE
    1. La cola se agrupa por el nombre CONGELADO, no por quien este de turno hoy.
    2. Un codigo desconocido no aborta el lote.
    3. Las tres ramas del ajuste.
    4. Un paquete con deuda no sale de Pacaraima.
    5. Dos operadores sobre el mismo paquete: gana uno.

Los modulos se cargan por ruta directa para no arrastrar services/__init__.py.
"""
import asyncio
import importlib.util
import io
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from conftest import usar_base                                        # noqa: E402


def _proyectar(doc, proyeccion):
    """Copia PROFUNDA, como hace la base de verdad.

    Con una copia superficial, el bloque `cobros` es el mismo objeto en la base y
    en el dict del llamador, así que un dict nunca puede quedar rancio — y los
    defectos que dependen justamente de leer datos viejos se vuelven invisibles
    para toda la suite.
    """
    import copy
    if not proyeccion:
        return copy.deepcopy(doc)
    incluir = [k for k, v in proyeccion.items() if v and k != "_id"]
    if incluir:
        return copy.deepcopy({k: v for k, v in doc.items() if k in incluir})
    excluir = [k for k, v in proyeccion.items() if not v]
    return copy.deepcopy({k: v for k, v in doc.items() if k not in excluir})


def _camino(doc, clave):
    actual = doc
    for parte in str(clave).split("."):
        if not isinstance(actual, dict):
            return None
        actual = actual.get(parte)
    return actual


def _num(valor):
    """Compara como Mongo: los tipos numéricos se comparan entre sí."""
    if isinstance(valor, Decimal128):
        return valor.to_decimal()
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))
    return valor


def _fijar(doc, clave, valor):
    partes = str(clave).split(".")
    actual = doc
    for parte in partes[:-1]:
        actual = actual.setdefault(parte, {})
    actual[partes[-1]] = valor


class _Resultado:
    def __init__(self, n):
        self.matched_count = n
        self.modified_count = n


class _Coleccion:
    UNICOS = ()
    # Cuantas veces `find_one_and_update` cede el control antes de escribir. Sin
    # esto, ninguna operacion del doble suspende y `asyncio.gather` corre una
    # tarea entera y despues la otra: un test de concurrencia que no intercala no
    # prueba concurrencia, y pasa contra el codigo SIN la reserva.
    CEDER = 0

    def __init__(self, filas=None):
        self.filas = filas if filas is not None else []

    def _match(self, d, filtro):
        for k, v in (filtro or {}).items():
            actual = _camino(d, k)
            if isinstance(v, dict) and "$ne" in v:
                if actual == v["$ne"]:
                    return False
            elif isinstance(v, dict) and "$gte" in v:
                a, b = _num(actual), _num(v["$gte"])
                if a is None or not isinstance(a, Decimal) or a < b:
                    return False
            elif actual != v:
                return False
        return True

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
        for clave in self.UNICOS:
            if doc.get(clave) is not None and any(
                    d.get(clave) == doc.get(clave) for d in self.filas):
                raise RuntimeError(f"E11000 duplicate key: {clave}")
        self.filas.append(dict(doc))

    def _aplicar(self, d, cambio):
        for clave, valor in (cambio.get("$set") or {}).items():
            _fijar(d, clave, valor)
        for clave, valor in (cambio.get("$inc") or {}).items():
            actual = _num(_camino(d, clave)) or Decimal("0")
            _fijar(d, clave, Decimal128(actual + _num(valor)))

    async def update_one(self, filtro, cambio, upsert=False):
        for d in self.filas:
            if self._match(d, filtro):
                self._aplicar(d, cambio)
                return _Resultado(1)
        if upsert:
            nuevo = {k: v for k, v in (filtro or {}).items()
                     if not isinstance(v, dict)}
            self.filas.append(nuevo)
            self._aplicar(nuevo, cambio)
            return _Resultado(1)
        # Como motor: un update que no matchea NO lanza, devuelve matched_count 0.
        return _Resultado(0)

    async def find_one_and_update(self, filtro, cambio, upsert=False,
                                  return_document=True):
        for _ in range(self.CEDER):
            await asyncio.sleep(0)
        for d in self.filas:
            if self._match(d, filtro):
                antes = dict(d)
                self._aplicar(d, cambio)
                return dict(d) if return_document else antes
        if upsert:
            nuevo = {k: v for k, v in (filtro or {}).items()
                     if not isinstance(v, dict)}
            self.filas.append(nuevo)
            self._aplicar(nuevo, cambio)
            return dict(nuevo)
        return None

    async def delete_one(self, filtro):
        for i, d in enumerate(self.filas):
            if self._match(d, filtro):
                del self.filas[i]
                return


class _ColeccionUnica(_Coleccion):
    UNICOS = ()

    async def insert_one(self, doc):
        if any(all(d.get(k) == doc.get(k) for k in ("user_id", "action", "key"))
               for d in self.filas):
            raise RuntimeError("E11000 duplicate key")
        self.filas.append(dict(doc))


class _Db:
    def __init__(self, **colecciones):
        # La clase correcta TAMBIEN para las colecciones declaradas de entrada:
        # con `_Coleccion` plana, `claim_idempotency` nunca detecta una clave
        # repetida y los tests de doble clic pasan por otra guardia.
        self._c = {k: (_ColeccionUnica if k == "idempotency_keys" else _Coleccion)(v)
                   for k, v in colecciones.items()}

    def _nueva(self, nombre):
        clase = _ColeccionUnica if nombre == "idempotency_keys" else _Coleccion
        return self._c.setdefault(nombre, clase([]))

    def __getattr__(self, nombre):
        return self._nueva(nombre)

    def __getitem__(self, nombre):
        return self._nueva(nombre)


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
estados = _cargar("envios_estados")
idem = _cargar("idempotency")
ledger = _cargar("ledger")
cobros = _cargar("envios_cobros")
_cargar("envios_eventos")
archivos = _cargar("envios_archivos")
comp = _cargar("envios_comprobante")
op = _cargar("envios_operacion")


def corre(coro):
    return asyncio.run(coro)


AHORA = datetime.now(timezone.utc)

TARIFA = {
    "version_id": "tar_2026_08_a", "moneda": "RIS", "modo_tarifa": "peso",
    "regla_peso": {"divisor": 5000, "escalon_kg": "0.5", "minimo_kg": "1.0"},
    "escalones_peso": [
        {"desde_kg": "0.00", "hasta_kg": "1.00", "precio": "45.00"},
        {"desde_kg": "1.01", "hasta_kg": "3.00", "precio": "78.00"},
        {"desde_kg": "3.01", "hasta_kg": "5.00", "precio": "110.00"},
        {"desde_kg": "5.01", "hasta_kg": "10.00", "precio": "185.00"},
    ],
    "adicional_por_kg": "17.50", "tarifa_minima": "45.00",
    "margen": {"tipo": "porcentual", "valor": "0.20"},
}

OPERACION = {"setting_id": "envios_operacion", "tolerancia_ajuste_ris": "2.00",
             "dias_guarda": 30}


def envio_base(**cambios):
    import copy
    envio = {
        "envio_id": "env_aaa111", "display_id": "E000001", "user_id": "usr_ana",
        "estado": "en_transito_origen",
        "created_at": AHORA - timedelta(days=3),
        "modalidad_flete": "destino",
        "destino_brasil": {"retirador_nombre": "María Gómez"},
        "destino": {"agencia_nombre": "Centro", "estado_ve": "Miranda"},
        "paquete": {
            "declarado": {"peso_kg": "2.30", "largo_cm": "40", "ancho_cm": "30",
                          "alto_cm": "20", "valor_declarado": "180.00"},
            "bultos": 1, "verificado": None,
        },
        "cotizacion": {"tarifa_version": "tar_2026_08_a", "fecha": "2026-08-30",
                       "total_estimado_ris": "132.00", "moneda": "RIS",
                       "es_estimado": True, "total_final_ris": None},
        "origen": {"codigo_objeto": "AA123456789BR"},
        "cobros": {"inicial": {"monto_ris": "132.00", "estado": "pagado",
                               "peso_base_kg": "2.30"},
                   "ajuste": None, "reembolsado_ris": "0.00",
                   "total_cobrado_ris": "132.00"},
    }
    envio = copy.deepcopy(envio)
    for clave, valor in cambios.items():
        # Un dict VACIO reemplaza, no fusiona: `destino_brasil={}` en un test
        # tiene que dejar el bloque vacio, que es justo el caso que se prueba.
        if isinstance(valor, dict) and valor and isinstance(envio.get(clave), dict):
            envio[clave].update(valor)
        else:
            envio[clave] = valor
    return envio


class _Operador:
    user_id = "usr_operador"


def _jpeg(ancho=16, alto=12):
    from PIL import Image
    imagen = Image.new("RGB", (ancho, alto), (30, 120, 200))
    salida = io.BytesIO()
    imagen.save(salida, format="JPEG")
    return salida.getvalue()


def db_completa(saldo="500.00", envios=None):
    import copy
    base = _Db(
        envios=copy.deepcopy(envios if envios is not None else [envio_base()]),
        tarifas_envio=copy.deepcopy([TARIFA]),
        app_settings=copy.deepcopy([OPERACION]),
        users=[{"user_id": "usr_ana", "balance_ris": Decimal128(Decimal(saldo))}],
        ledger=[], idempotency_keys=[], envios_eventos=[], envios_lotes=[],
        envios_archivos=[],
    )
    usar_base(base)
    idem._idem_indexes_ready = True
    ledger._indexes_ready = True
    return base


def envio_de(base, i=0) -> dict:
    return base.envios.filas[i]


def saldo_de(base) -> Decimal:
    return _num(base.users.filas[0]["balance_ris"])


# ─── 1. La cola ───────────────────────────────────────────────────────────

def test_la_cola_se_agrupa_por_el_nombre_rotulado_en_la_caja():
    """En el mostrador comparan la etiqueta contra un documento. Quien va
    necesita saber cuáles puede reclamar él."""
    otro = envio_base(envio_id="env_bbb222", display_id="E000002",
                      estado="disponible_retiro",
                      destino_brasil={"retirador_nombre": "José Ferreira"})
    mio = envio_base(estado="disponible_retiro")
    base = db_completa(envios=[mio, otro])

    r = corre(op.cola("disponible_retiro", db=base, ahora=AHORA))
    nombres = [g["retirador_nombre"] for g in r["grupos"]]
    assert nombres == ["José Ferreira", "María Gómez"]
    assert r["total"] == 2 and all(g["cuantos"] == 1 for g in r["grupos"])


def test_un_envio_sin_nombre_no_desaparece_de_la_cola():
    """Cae en su propio grupo. Desaparecer de la cola es un paquete que nadie va
    a buscar."""
    sin_nombre = envio_base(estado="disponible_retiro", destino_brasil={})
    base = db_completa(envios=[sin_nombre])
    r = corre(op.cola("disponible_retiro", db=base, ahora=AHORA))
    assert r["grupos"][0]["retirador_nombre"] == "Sin nombre en la etiqueta"


def test_la_cola_dice_cuales_pueden_salir():
    """El operador tiene que saberlo antes de cargar la camioneta, no después."""
    con_deuda = envio_base(estado="disponible_retiro", envio_id="env_ccc333",
                           cobros={"inicial": {"monto_ris": "132.00",
                                               "estado": "pendiente"},
                                   "ajuste": None})
    base = db_completa(envios=[envio_base(estado="disponible_retiro"), con_deuda])
    r = corre(op.cola("disponible_retiro", db=base, ahora=AHORA))
    filas = [e for g in r["grupos"] for e in g["envios"]]
    por_id = {f["envio_id"]: f for f in filas}
    assert por_id["env_aaa111"]["puede_salir"] is True
    assert por_id["env_ccc333"]["puede_salir"] is False
    assert por_id["env_ccc333"]["partidas_impagas"] == ["inicial"]


def test_la_cola_dice_cuales_pueden_entregarse():
    """El otro candado, el del flete, contado ANTES y no despues de apretar.

    Paso en produccion: el operador lleno el numero de guia, adjunto la foto del
    remito, apreto «Registrar la entrega» y recien ahi le salto que el flete no
    estaba acreditado. Con el paquete en el mostrador y el cliente enfrente.

    El candado esta bien y no se toca —no se suelta un paquete contra una remesa
    que nadie de este lado vio llegar—; lo que faltaba era decirlo a tiempo.
    `puede_salir` ya se calculaba asi para el despacho por exactamente el mismo
    motivo.
    """
    prepago_pendiente = envio_base(estado="en_transito_int", envio_id="env_ccc333",
                                   modalidad_flete="prepago",
                                   flete={"estado": "pendiente"})
    prepago_ok = envio_base(estado="en_transito_int", envio_id="env_ddd444",
                            modalidad_flete="prepago",
                            flete={"estado": "acreditado"})
    base = db_completa(envios=[envio_base(estado="en_transito_int"),
                               prepago_pendiente, prepago_ok])
    r = corre(op.cola("en_transito_int", db=base, ahora=AHORA))
    por_id = {f["envio_id"]: f for g in r["grupos"] for f in g["envios"]}

    # Contra entrega: no hay remesa que esperar.
    assert por_id["env_aaa111"]["puede_entregar"] is True
    assert por_id["env_ccc333"]["puede_entregar"] is False
    assert por_id["env_ccc333"]["flete_estado"] == "pendiente"
    assert por_id["env_ddd444"]["puede_entregar"] is True

    # Y lo que la cola dice tiene que ser lo MISMO que la transicion hace: una
    # segunda version de la regla en la cola se despega de la de verdad y el
    # cartel termina mintiendo en la direccion peligrosa.
    with pytest.raises(op.OperacionRechazada):
        corre(op.entregar(_Operador(), "env_ccc333", guia="GUIA-1", db=base,
                          ahora=AHORA))


def test_si_la_cola_no_se_puede_leer_no_revienta():
    base = db_completa()
    base.envios.find = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    r = corre(op.cola("disponible_retiro", db=base, ahora=AHORA))
    assert r["grupos"] == [] and r["degradado"] is True


# ─── 2. El reloj de guarda ────────────────────────────────────────────────

def test_marcar_disponible_arranca_el_reloj_de_guarda():
    """Pasado el plazo la agencia lo devuelve al remitente, con el costo del
    retorno y un usuario que ya pagó."""
    base = db_completa()
    r = corre(op.marcar_disponible(_Operador(), "env_aaa111", db=base, ahora=AHORA))
    assert r["estado"] == "disponible_retiro"
    assert envio_de(base)["origen"]["guarda_vence_at"] == AHORA + timedelta(days=30)
    assert envio_de(base)["origen"]["dias_guarda"] == 30


def test_el_vencimiento_se_congela_y_no_se_mueve_al_cambiar_la_configuracion():
    """Cambiar los días de guarda no puede moverle el vencimiento a los paquetes
    que ya están esperando."""
    base = db_completa()
    corre(op.marcar_disponible(_Operador(), "env_aaa111", db=base, ahora=AHORA))
    vence = envio_de(base)["origen"]["guarda_vence_at"]
    base.app_settings.filas[0]["dias_guarda"] = 3
    assert envio_de(base)["origen"]["guarda_vence_at"] == vence


def test_la_cola_dice_cuantos_dias_de_guarda_quedan():
    base = db_completa()
    corre(op.marcar_disponible(_Operador(), "env_aaa111", db=base, ahora=AHORA))
    r = corre(op.cola("disponible_retiro", db=base,
                      ahora=AHORA + timedelta(days=25)))
    fila = r["grupos"][0]["envios"][0]
    assert fila["dias_de_guarda_restantes"] == 5


# ─── 3. El retiro por lote ────────────────────────────────────────────────

def test_un_codigo_desconocido_no_aborta_el_lote():
    """El operador está en un mostrador con treinta cajas: que una no se
    reconozca no puede hacerle perder las veintinueve que sí."""
    a = envio_base(estado="disponible_retiro")
    b = envio_base(envio_id="env_bbb222", display_id="E000002",
                   estado="disponible_retiro",
                   origen={"codigo_objeto": "ZZ987654321BR"})
    base = db_completa(envios=[a, b])

    r = corre(op.retirar_lote(_Operador(),
                              ["AA123456789BR", "XX000000000BR", "ZZ987654321BR"],
                              db=base, ahora=AHORA))
    assert r["cuantos"] == 2
    assert [x["motivo"] for x in r["rechazados"]] == ["desconocido"]
    assert all(e["estado"] == "recibido_pacaraima" for e in base.envios.filas)


def test_un_codigo_con_mal_formato_se_rechaza_sin_frenar_el_resto():
    base = db_completa(envios=[envio_base(estado="disponible_retiro")])
    r = corre(op.retirar_lote(_Operador(), ["AA123456789BR", "el de la caja azul"],
                              db=base, ahora=AHORA))
    assert r["cuantos"] == 1
    assert r["rechazados"][0]["motivo"] == "formato"


def test_un_paquete_en_otro_estado_se_rechaza_con_su_motivo():
    """Que el operador sepa POR QUÉ no se pudo retirar es la diferencia entre
    resolverlo en el mostrador y volver sin la caja."""
    base = db_completa(envios=[envio_base(estado="en_transito_origen")])
    r = corre(op.retirar_lote(_Operador(), ["AA123456789BR"], db=base, ahora=AHORA))
    assert r["cuantos"] == 0
    assert r["rechazados"][0]["motivo"] == "estado"
    assert r["rechazados"][0]["display_id"] == "E000001"


def test_el_lote_queda_registrado_con_lo_que_se_retiro():
    """Es lo que hace posible la vista de rentabilidad por viaje."""
    base = db_completa(envios=[envio_base(estado="disponible_retiro")])
    r = corre(op.retirar_lote(_Operador(), ["AA123456789BR"], db=base, ahora=AHORA,
                              nota="viaje del martes"))
    lote = base.envios_lotes.filas[0]
    assert lote["lote_id"] == r["lote_id"] and lote["cuantos"] == 1
    assert lote["nota"] == "viaje del martes"
    assert envio_de(base)["origen"]["lote_retiro_id"] == r["lote_id"]


def test_un_lote_vacio_se_rechaza():
    base = db_completa()
    with pytest.raises(op.OperacionRechazada):
        corre(op.retirar_lote(_Operador(), [], db=base, ahora=AHORA))


# ─── 4. El repesaje y las tres ramas ──────────────────────────────────────

def _listo_para_repesar(**cambios):
    return envio_base(estado="recibido_pacaraima", **cambios)


def test_rama_cobrar_el_paquete_peso_mas():
    # 6 kg reales superan el cubado de la misma caja (24.000 / 5000 = 4,8), asi
    # que suben de escalon de verdad. Con 4,2 el cubado seguia mandando y la
    # diferencia daba cero: el test hubiera pasado por el motivo equivocado.
    base = db_completa(envios=[_listo_para_repesar()])
    r = corre(op.repesar(_Operador(), "env_aaa111", peso_kg="6.00", largo_cm="40",
                         ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    assert r["rama"] == "cobrar"
    assert Decimal(r["diferencia_ris"]) > 0
    assert r["cobro"]["estado"] == "pagado"
    assert saldo_de(base) == Decimal("500.00") - Decimal(r["diferencia_ris"])


def test_rama_devolver_el_paquete_peso_menos():
    """Un ajuste que solo sube no es un ajuste, es un recargo."""
    caro = _listo_para_repesar(
        cobros={"inicial": {"monto_ris": "185.00", "estado": "pagado",
                            "peso_base_kg": "6.00"},
                "ajuste": None, "total_cobrado_ris": "185.00",
                "reembolsado_ris": "0.00"})
    base = db_completa(envios=[caro])
    r = corre(op.repesar(_Operador(), "env_aaa111", peso_kg="2.30", largo_cm="40",
                         ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    assert r["rama"] == "devolver"
    assert r["devolucion"]["estado"] == "acreditado"
    assert saldo_de(base) > Decimal("500.00")


def test_rama_sin_ajuste_dentro_de_la_tolerancia():
    """Un cobro de doce centavos cuesta más en soporte que en plata."""
    base = db_completa(envios=[_listo_para_repesar()])
    r = corre(op.repesar(_Operador(), "env_aaa111", peso_kg="2.31", largo_cm="40",
                         ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    assert r["rama"] == "sin_ajuste"
    assert r["cobro"] is None and r["devolucion"] is None
    assert saldo_de(base) == Decimal("500.00")


def test_el_repesaje_cierra_el_precio():
    base = db_completa(envios=[_listo_para_repesar()])
    corre(op.repesar(_Operador(), "env_aaa111", peso_kg="2.30", largo_cm="40",
                     ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    cot = envio_de(base)["cotizacion"]
    assert cot["es_estimado"] is False
    assert Decimal(cot["total_final_ris"]) > 0
    verificado = envio_de(base)["paquete"]["verificado"]
    assert verificado["peso_kg"] == "2.30"
    assert verificado["verificado_por"] == "usr_operador"


def test_el_repesaje_usa_la_tarifa_congelada():
    nueva = {**TARIFA, "version_id": "tar_nueva",
             "escalones_peso": [{**e, "precio": str(Decimal(e["precio"]) * 5)}
                                for e in TARIFA["escalones_peso"]]}
    base = db_completa(envios=[_listo_para_repesar()])
    base.tarifas_envio.filas.insert(0, nueva)
    r = corre(op.repesar(_Operador(), "env_aaa111", peso_kg="2.30", largo_cm="40",
                         ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    assert r["rama"] == "sin_ajuste"      # con la tarifa x5 daría "cobrar"


def test_si_no_hay_saldo_el_ajuste_queda_pendiente_y_el_paquete_no_sale():
    base = db_completa(saldo="0.00", envios=[_listo_para_repesar()])
    r = corre(op.repesar(_Operador(), "env_aaa111", peso_kg="6.00", largo_cm="40",
                         ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    assert r["cobro"]["estado"] == "pendiente"
    assert r["puede_salir"] is False
    # El estado se ESCRIBE, no se sugiere: `pago_pendiente` existe para que el
    # usuario reciba el aviso de que su paquete espera un pago, y dejarlo como
    # sugerencia lo volvia un estado inalcanzable y ese aviso, codigo muerto.
    assert r["estado"] == "pago_pendiente"
    assert envio_de(base)["estado"] == "pago_pendiente"


# ─── 5. La salida de Pacaraima ────────────────────────────────────────────

def test_un_paquete_con_deuda_no_sale_de_pacaraima():
    """Es la única palanca de cobro real del negocio: la posesión física."""
    con_deuda = envio_base(estado="repesado",
                           cotizacion={"es_estimado": False},
                           cobros={"inicial": {"monto_ris": "132.00",
                                               "estado": "pendiente"},
                                   "ajuste": None})
    base = db_completa(envios=[con_deuda])
    with pytest.raises(op.OperacionRechazada) as e:
        corre(op.despachar(_Operador(), "env_aaa111", db=base, ahora=AHORA))
    assert e.value.http == 409
    assert envio_de(base)["estado"] == "repesado"


def test_con_todo_pago_el_paquete_sale():
    listo = envio_base(estado="repesado", cotizacion={"es_estimado": False})
    base = db_completa(envios=[listo])
    r = corre(op.despachar(_Operador(), "env_aaa111", db=base, ahora=AHORA))
    assert r["estado"] == "en_transito_int"


def test_un_paquete_sin_repesar_no_sale_aunque_no_deba_nada():
    """`recibido_pacaraima -> retenido -> en_transito_int` esquiva el ajuste. Sin
    la bandera, el paquete sale con el precio sin cerrar y nadie se entera."""
    sin_repesar = envio_base(estado="retenido")
    base = db_completa(envios=[sin_repesar])
    with pytest.raises(op.OperacionRechazada) as e:
        corre(op.despachar(_Operador(), "env_aaa111", db=base, ahora=AHORA))
    assert "repes" in e.value.mensaje.lower()


def test_las_invariantes_se_derivan_del_envio_y_no_las_pasa_la_ruta():
    """Dejarlas en manos de quien llama es dejar que una ruta nueva se olvide de
    una y saque un paquete de Pacaraima con la deuda encima."""
    fuente = open(os.path.join(_BACKEND, "services", "envios_operacion.py"),
                  encoding="utf-8").read()
    cuerpo = fuente[fuente.index("def _exigir_transicion("):]
    assert "partida_impaga=bool(impagas)" in cuerpo
    assert "precio_cerrado=not" in cuerpo


# ─── 6. La entrega ────────────────────────────────────────────────────────

def test_la_entrega_exige_guia():
    """Sin ella, la única prueba de la entrega es la palabra del operador."""
    base = db_completa(envios=[envio_base(estado="en_transito_int")])
    with pytest.raises(op.OperacionRechazada) as e:
        corre(op.entregar(_Operador(), "env_aaa111", guia="  ", db=base, ahora=AHORA))
    assert "guía" in e.value.mensaje
    assert envio_de(base)["estado"] == "en_transito_int"


def test_la_entrega_cierra_el_envio_con_su_guia_y_su_foto():
    base = db_completa(envios=[envio_base(estado="en_transito_int")])
    r = corre(op.entregar(_Operador(), "env_aaa111", guia="GUIA-99887",
                          foto=_jpeg(), db=base, ahora=AHORA))
    assert r["estado"] == "entregado_transportista"
    entrega = envio_de(base)["entrega"]
    assert entrega["guia"] == "GUIA-99887" and entrega["por"] == "usr_operador"
    assert base.envios_archivos.filas[0]["clase"] == "entrega"


def test_en_prepago_no_se_entrega_con_el_flete_sin_acreditar():
    """El paquete espera con el equipo, no se entrega en el mostrador."""
    prepago = envio_base(estado="en_transito_int", modalidad_flete="prepago",
                         flete={"estado": "pendiente"})
    base = db_completa(envios=[prepago])
    with pytest.raises(op.OperacionRechazada) as e:
        corre(op.entregar(_Operador(), "env_aaa111", guia="GUIA-1", db=base,
                          ahora=AHORA))
    assert "flete" in e.value.mensaje.lower()


def test_en_prepago_con_el_flete_acreditado_si_se_entrega():
    prepago = envio_base(estado="en_transito_int", modalidad_flete="prepago",
                         flete={"estado": "acreditado"})
    base = db_completa(envios=[prepago])
    r = corre(op.entregar(_Operador(), "env_aaa111", guia="GUIA-1", db=base,
                          ahora=AHORA))
    assert r["estado"] == "entregado_transportista"


# ─── 7. Dos operadores sobre el mismo paquete ─────────────────────────────

def test_dos_operadores_sobre_el_mismo_paquete_no_lo_mueven_dos_veces():
    """Con dos personas en un mostrador, esto no es hipotético."""
    import copy
    base = db_completa(envios=[envio_base(estado="disponible_retiro")])
    rancio = copy.deepcopy(envio_de(base))
    corre(op.retirar_lote(_Operador(), ["AA123456789BR"], db=base, ahora=AHORA))
    primer_lote = envio_de(base)["origen"]["lote_retiro_id"]

    original = base.envios.find_one

    async def lectura_rancia(filtro, proyeccion=None):
        base.envios.find_one = original
        return copy.deepcopy(rancio)
    base.envios.find_one = lectura_rancia

    r = corre(op.retirar_lote(_Operador(), ["AA123456789BR"], db=base, ahora=AHORA))
    assert r["cuantos"] == 0
    assert envio_de(base)["origen"]["lote_retiro_id"] == primer_lote


def test_cada_movimiento_deja_su_linea_en_la_bitacora():
    base = db_completa(envios=[envio_base(estado="disponible_retiro")])
    corre(op.retirar_lote(_Operador(), ["AA123456789BR"], db=base, ahora=AHORA))
    corre(op.repesar(_Operador(), "env_aaa111", peso_kg="2.30", largo_cm="40",
                     ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    corre(op.despachar(_Operador(), "env_aaa111", db=base, ahora=AHORA))
    estados = [e["a_estado"] for e in base.envios_eventos.filas]
    assert estados == ["recibido_pacaraima", "repesado", "en_transito_int"]
    assert all(e["actor_type"] == "admin" for e in base.envios_eventos.filas)
    assert all(e["actor_id"] == "usr_operador" for e in base.envios_eventos.filas)


def test_el_modulo_no_menciona_ninguna_marca():
    fuente = open(os.path.join(_BACKEND, "services", "envios_operacion.py"),
                  encoding="utf-8").read().lower()
    for marca in ("mrw", "correios", "zoom", "tealca", "domesa"):
        assert marca not in fuente


# ─── 8. Lo que encontro la revision adversarial ───────────────────────────

def test_si_el_cobro_del_ajuste_falla_el_paquete_no_sale_igual():
    """EL DEFECTO P0. El estado cambiaba ANTES de cobrar: si el cobro fallaba por
    un 503 pasajero, el reintento chocaba contra "el envío ya está en ese
    estado", ninguna otra ruta emite la partida `ajuste`, y el paquete salía de
    Pacaraima sin la diferencia cobrada."""
    cobros = _cargar("envios_cobros")
    base = db_completa(envios=[_listo_para_repesar()])
    original = cobros.cobrar

    async def revienta(*a, **k):
        cobros.cobrar = original
        raise cobros.CobroImposible("mongo caído", http=503)
    cobros.cobrar = revienta
    try:
        with pytest.raises(Exception):
            corre(op.repesar(_Operador(), "env_aaa111", peso_kg="6.00",
                             largo_cm="40", ancho_cm="30", alto_cm="20",
                             db=base, ahora=AHORA))
    finally:
        cobros.cobrar = original

    # El estado NO se movió, así que el reintento funciona.
    assert envio_de(base)["estado"] == "recibido_pacaraima"
    r = corre(op.repesar(_Operador(), "env_aaa111", peso_kg="6.00", largo_cm="40",
                         ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    assert r["cobro"]["estado"] == "pagado"
    assert envio_de(base)["estado"] == "repesado"     # listo para despachar
    assert r["puede_salir"] is True


def test_reintentar_un_repesaje_no_cobra_dos_veces():
    """Cobrar antes de mover es seguro porque `cobrar` es idempotente por
    partida: un reintento devuelve la que ya existe."""
    base = db_completa(envios=[_listo_para_repesar()])
    corre(op.repesar(_Operador(), "env_aaa111", peso_kg="6.00", largo_cm="40",
                     ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    saldo = saldo_de(base)
    envio_de(base)["estado"] = "recibido_pacaraima"      # como si nada se hubiera movido
    corre(op.repesar(_Operador(), "env_aaa111", peso_kg="6.00", largo_cm="40",
                     ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    assert saldo_de(base) == saldo


def test_sin_el_bloque_de_operacion_la_tolerancia_no_es_cero():
    """`to_decimal(None)` da 0 —es su contrato— y pasarlo tal cual entregaba una
    tolerancia EXPLÍCITA de cero: la rama "sin_ajuste" desaparecía y un envío
    podía quedar frenado en Pacaraima por un peso con cincuenta. Y pasaba en toda
    instalación nueva, porque el bloque no existe hasta que alguien lo guarda."""
    apenas = _listo_para_repesar(
        cobros={"inicial": {"monto_ris": "130.50", "estado": "pagado",
                            "peso_base_kg": "2.30"},
                "ajuste": None, "total_cobrado_ris": "130.50",
                "reembolsado_ris": "0.00"})
    base = db_completa(envios=[apenas])
    base.app_settings.filas.clear()          # panel recién instalado

    r = corre(op.repesar(_Operador(), "env_aaa111", peso_kg="2.30", largo_cm="40",
                         ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    assert r["rama"] == "sin_ajuste"
    assert envio_de(base)["cobros"]["ajuste"] is None
    assert saldo_de(base) == Decimal("500.00")


def test_sin_cobro_inicial_el_error_no_culpa_al_operador():
    """El error decía "revisá las medidas que cargaste", culpándolo de que nadie
    verificó el comprobante todavía. Y el operador volvía a tipear el peso
    indefinidamente."""
    sin_inicial = _listo_para_repesar(
        cobros={"inicial": None, "ajuste": None, "total_cobrado_ris": "0.00"})
    base = db_completa(envios=[sin_inicial])
    with pytest.raises(op.OperacionRechazada) as e:
        corre(op.repesar(_Operador(), "env_aaa111", peso_kg="2.30", largo_cm="40",
                         ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    assert e.value.http == 409
    assert "comprobante" in e.value.mensaje


def test_el_usuario_se_entera_de_que_su_paquete_espera_un_pago():
    """Es el único aviso que el propio módulo llama "el que importaba"."""
    base = db_completa(saldo="0.00", envios=[_listo_para_repesar()])
    corre(op.repesar(_Operador(), "env_aaa111", peso_kg="6.00", largo_cm="40",
                     ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    avisos = [n for n in base.notifications.filas
              if "espera un pago" in (n.get("title") or "")]
    assert avisos, "sin este aviso el usuario no sabe que su paquete está frenado"


def test_la_cola_avisa_cuando_hay_mas_de_los_que_muestra():
    """Truncar en silencio hace que quien viaja arme la lista con doscientos y
    deje el resto en el mostrador consumiendo días de guarda."""
    envios = [envio_base(envio_id=f"env_{i:03d}", display_id=f"E{i:06d}",
                         estado="disponible_retiro",
                         origen={"codigo_objeto": f"AA{i:09d}BR"})
              for i in range(1, 8)]
    base = db_completa(envios=envios)
    r = corre(op.cola("disponible_retiro", db=base, limite=5, ahora=AHORA))
    assert r["total"] == 5 and r["hay_mas"] is True

    completa = corre(op.cola("disponible_retiro", db=base, limite=50, ahora=AHORA))
    assert completa["total"] == 7 and completa["hay_mas"] is False


# ─── 9. Los caminos que no son el feliz ───────────────────────────────────

def test_un_paquete_devuelto_por_la_agencia_tiene_salida():
    """Sin esto, un paquete cuya guarda vencía y que la agencia devolvía al
    remitente se quedaba en `disponible_retiro` para siempre, y la cola lo
    mostraba con los días en negativo sin ninguna salida."""
    base = db_completa(envios=[envio_base(estado="disponible_retiro")])
    r = corre(op.desviar(_Operador(), "env_aaa111", "devuelto",
                         motivo="venció la guarda y la agencia lo devolvió",
                         db=base, ahora=AHORA))
    assert r["estado"] == "devuelto"
    assert envio_de(base)["desvio"]["por"] == "usr_operador"


@pytest.mark.parametrize("desde,hacia", [
    ("recibido_pacaraima", "retenido"),
    ("recibido_pacaraima", "siniestrado"),
    ("en_transito_int", "retenido"),
    ("disponible_retiro", "devuelto"),
])
def test_los_desvios_declarados_se_pueden_hacer(desde, hacia):
    base = db_completa(envios=[envio_base(estado=desde)])
    r = corre(op.desviar(_Operador(), "env_aaa111", hacia,
                         motivo="aduana observó el contenido", db=base, ahora=AHORA))
    assert r["estado"] == hacia


def test_un_desvio_exige_un_motivo_de_verdad():
    """Estos estados abren consecuencias —una indemnización, una devolución— y
    dentro de seis meses la única forma de entender por qué un paquete terminó
    así es lo que alguien escribió acá."""
    base = db_completa(envios=[envio_base(estado="recibido_pacaraima")])
    for malo in ("", "   ", "ok", "problema"):
        with pytest.raises(op.OperacionRechazada):
            corre(op.desviar(_Operador(), "env_aaa111", "retenido", motivo=malo,
                             db=base, ahora=AHORA))
    assert envio_de(base)["estado"] == "recibido_pacaraima"


def test_no_se_puede_desviar_a_cualquier_estado():
    base = db_completa(envios=[envio_base(estado="recibido_pacaraima")])
    with pytest.raises(op.OperacionRechazada):
        corre(op.desviar(_Operador(), "env_aaa111", "entregado_transportista",
                         motivo="quiero saltearme el repesaje", db=base, ahora=AHORA))


def test_un_desvio_invalido_para_ese_estado_se_rechaza():
    """Sigue pasando por la máquina de estados: no es una puerta trasera."""
    base = db_completa(envios=[envio_base(estado="entregado_transportista")])
    with pytest.raises(op.OperacionRechazada) as e:
        corre(op.desviar(_Operador(), "env_aaa111", "retenido",
                         motivo="me equivoqué de envío", db=base, ahora=AHORA))
    assert e.value.http == 409


def test_el_usuario_puede_cancelar_antes_de_despachar():
    base = db_completa(envios=[envio_base(estado="esperando_postagem")])

    class _Ana:
        user_id = "usr_ana"

    r = corre(op.cancelar(_Ana(), "env_aaa111", db=base, ahora=AHORA))
    assert r["estado"] == "cancelado"


def test_el_usuario_no_puede_cancelar_un_paquete_que_ya_esta_viajando():
    """Cancelarlo en una pantalla no lo trae de vuelta."""
    base = db_completa(envios=[envio_base(estado="recibido_pacaraima")])

    class _Ana:
        user_id = "usr_ana"

    with pytest.raises(op.OperacionRechazada) as e:
        corre(op.cancelar(_Ana(), "env_aaa111", db=base, ahora=AHORA))
    assert e.value.http == 409


def test_nadie_cancela_el_envio_de_otro():
    base = db_completa(envios=[envio_base(estado="esperando_postagem")])

    class _Otro:
        user_id = "usr_otro"

    with pytest.raises(op.OperacionRechazada) as e:
        corre(op.cancelar(_Otro(), "env_aaa111", db=base, ahora=AHORA))
    assert e.value.http == 404


# ─── 10. El flete del tramo final ─────────────────────────────────────────

def test_un_envio_prepago_se_puede_entregar_despues_de_acreditar_el_flete():
    """Nada escribía `flete.*`, así que un envío `prepago` no se podía entregar
    NUNCA: la validación lo bloqueaba y no existía la ruta que lo destrabara."""
    prepago = envio_base(estado="en_transito_int", modalidad_flete="prepago")
    base = db_completa(envios=[prepago])

    with pytest.raises(op.OperacionRechazada):
        corre(op.entregar(_Operador(), "env_aaa111", guia="GUIA-1", db=base,
                          ahora=AHORA))

    corre(op.cargar_flete(_Operador(), "env_aaa111", monto="310.00", db=base,
                          ahora=AHORA))
    corre(op.acreditar_flete(_Operador(), "env_aaa111", referencia="wd_123",
                             db=base, ahora=AHORA))
    r = corre(op.entregar(_Operador(), "env_aaa111", guia="GUIA-1", db=base,
                          ahora=AHORA))
    assert r["estado"] == "entregado_transportista"


def test_no_se_acredita_un_flete_que_nadie_cargo():
    base = db_completa(envios=[envio_base(estado="en_transito_int",
                                          modalidad_flete="prepago")])
    with pytest.raises(op.OperacionRechazada) as e:
        corre(op.acreditar_flete(_Operador(), "env_aaa111", db=base, ahora=AHORA))
    assert e.value.http == 409


def test_el_flete_queda_donde_lo_lee_la_rentabilidad():
    """Es la fuente de la mitad venezolana de los precios observados. Si el nombre
    del campo no coincide, esa mitad queda vacía para siempre y nadie se entera."""
    rent = _cargar("envios_rentabilidad")
    base = db_completa(envios=[envio_base(estado="en_transito_int",
                                          destino={"zona_tarifa": "zona_a"})])
    corre(op.cargar_flete(_Operador(), "env_aaa111", monto="310.00", db=base,
                          ahora=AHORA))
    obs = corre(rent.observaciones(db=base, ahora=AHORA))
    venezuela = [o for o in obs if o["rol"] == "venezuela"]
    assert venezuela and Decimal(venezuela[0]["promedio"]) == Decimal("310.00")


def test_un_monto_de_flete_ilegible_se_rechaza():
    base = db_completa(envios=[envio_base(estado="en_transito_int")])
    for malo in ("0", "", "gratis", "-10"):
        with pytest.raises(op.OperacionRechazada):
            corre(op.cargar_flete(_Operador(), "env_aaa111", monto=malo, db=base,
                                  ahora=AHORA))


def test_no_queda_ninguna_transicion_declarada_sin_forma_de_hacerla():
    """La máquina de estados declara treinta transiciones. Las que ninguna ruta
    implementa son paquetes que quedan atascados, y el costo se descubre con el
    paquete adentro."""
    estados = _cargar("envios_estados")
    # Lo que el módulo sabe mover: el camino feliz más los desvíos.
    implementadas = {
        ("cotizado", "esperando_postagem"), ("esperando_postagem", "en_transito_origen"),
        ("en_transito_origen", "disponible_retiro"),
        ("disponible_retiro", "recibido_pacaraima"),
        ("recibido_pacaraima", "repesado"), ("repesado", "pago_pendiente"),
        ("repesado", "en_transito_int"), ("pago_pendiente", "en_transito_int"),
        ("en_transito_int", "entregado_transportista"), ("retenido", "repesado"),
        ("retenido", "en_transito_int"),
    }
    for desde, hacia in ((d, h) for d, hs in estados.TRANSICIONES.items() for h in hs):
        if hacia in op.DESVIOS:
            continue          # la ruta de desvío las cubre todas
        assert (desde, hacia) in implementadas, f"{desde} -> {hacia} no la hace nadie"


def test_desviar_no_es_una_puerta_para_saltearse_el_repesaje():
    """`repesado` es una transición VÁLIDA desde `recibido_pacaraima`, así que la
    máquina de estados sola no la frena: lo que la frena es que `repesado` no
    está en la lista de desvíos. Sin esa lista, `desviar(..., "repesado")` movería
    el paquete sin calcular ni cobrar el ajuste."""
    base = db_completa(envios=[envio_base(estado="recibido_pacaraima")])
    with pytest.raises(op.OperacionRechazada) as e:
        corre(op.desviar(_Operador(), "env_aaa111", "repesado",
                         motivo="quiero saltearme el ajuste", db=base, ahora=AHORA))
    assert e.value.http == 400
    assert envio_de(base)["estado"] == "recibido_pacaraima"
    assert envio_de(base)["cotizacion"]["es_estimado"] is True


def test_la_cola_le_da_al_operador_la_foto_que_le_va_a_pedir_verificar():
    """Sin el asset en la cola, el paso de verificación es tipear un peso a
    ciegas: la única ruta que servía archivos exigía ser el dueño del envío."""
    con_comprobante = envio_base(
        estado="disponible_retiro",
        origen={"codigo_objeto": "AA123456789BR",
                "comprobante_asset_id": "ast_abc", "foto_repetida_en": "env_xxx"})
    base = db_completa(envios=[con_comprobante])
    r = corre(op.cola("disponible_retiro", db=base, ahora=AHORA))
    fila = r["grupos"][0]["envios"][0]
    assert fila["comprobante_asset_id"] == "ast_abc"
    assert fila["foto_repetida_en"] == "env_xxx"
    assert fila["comprobante_verificado"] is False


# ─── El ticket que se pega en la caja ─────────────────────────────────────

def _con_agencia(base, direccion="Av. Bolívar, local 4", nombre="Centro"):
    """La agencia VIVA en el catálogo, que es de donde sale la calle."""
    base.agencias.filas.append({
        "transportista_id": "trp_vzl", "codigo": "AG-01", "nombre": nombre,
        "direccion": direccion, "ciudad": "El Tigre", "estado": "Anzoátegui",
        "activa": True})
    base.transportistas.filas.append({
        "transportista_id": "trp_vzl", "nombre": "Transporte Zoom"})
    return base


def _envio_con_destino(**cambios):
    destino = {"agencia_nombre": "Centro", "agencia_codigo": "AG-01",
               "transportista_id": "trp_vzl", "estado_ve": "Anzoátegui",
               "ciudad": "El Tigre",
               "destinatario": {"nombre": "Ana Pérez", "documento": "V-12345678",
                                "telefono": "+58 412 5551234"}}
    return envio_base(estado="repesado", destino=destino, **cambios)


def test_el_ticket_trae_a_quien_se_le_entrega_y_donde():
    """Las dos cosas que alguien lee de parado con la caja en la mano."""
    base = _con_agencia(db_completa(envios=[_envio_con_destino()]))
    t = corre(op.ticket("env_aaa111", db=base))

    assert t["destinatario"]["nombre"] == "Ana Pérez"
    assert t["destinatario"]["documento"] == "V-12345678"
    assert t["destinatario"]["telefono"] == "+58 412 5551234"
    assert t["agencia"]["nombre"] == "Centro"
    assert t["agencia"]["direccion"] == "Av. Bolívar, local 4"
    assert t["agencia"]["transportista"] == "Transporte Zoom"


def test_la_direccion_del_ticket_se_lee_viva_y_no_congelada():
    """Es lo contrario de la etiqueta del tramo brasileño, y a propósito.

    Aquella tiene que decir lo mismo que leyó el usuario cuando despachó: es un
    compromiso con él. Esta se pega AHORA sobre una caja que sale AHORA, y tiene
    que decir dónde está la agencia HOY. Si la agencia se mudó y el ticket sale
    con la calle vieja, la caja va al lugar equivocado.

    MUTACION: leer `destino.agencia_direccion` del envío en vez de ir a
    `agencias` y este test se pone en rojo — el envío no tiene ese campo, así
    que el ticket saldría siempre sin calle.
    """
    base = _con_agencia(db_completa(envios=[_envio_con_destino()]),
                        direccion="La NUEVA, calle 5")
    t = corre(op.ticket("env_aaa111", db=base))
    assert t["agencia"]["direccion"] == "La NUEVA, calle 5"
    # Y el NOMBRE sí sale del envío, congelado: es con lo que el usuario eligió.
    assert t["agencia"]["nombre"] == "Centro"


def test_sin_agencia_en_el_catalogo_el_ticket_sale_igual():
    """Un ticket incompleto se completa a mano en el mostrador; un ticket que no
    se imprime frena la caja. La calle es lo único que se pierde."""
    base = db_completa(envios=[_envio_con_destino()])   # sin agencias cargadas
    t = corre(op.ticket("env_aaa111", db=base))
    assert t["agencia"]["direccion"] is None
    assert t["agencia"]["nombre"] == "Centro"
    assert t["destinatario"]["nombre"] == "Ana Pérez"


def test_si_el_catalogo_no_se_puede_leer_el_ticket_sale_igual():
    """Mongo caído no puede frenar una caja que ya está lista para viajar."""
    base = _con_agencia(db_completa(envios=[_envio_con_destino()]))

    class _Rota:
        async def find_one(self, *a, **k):
            raise RuntimeError("mongo caído")
    base._c["agencias"] = _Rota()

    t = corre(op.ticket("env_aaa111", db=base))
    assert t["agencia"]["direccion"] is None
    assert t["destinatario"]["nombre"] == "Ana Pérez"


def test_el_ticket_dice_si_hay_que_cobrarle_a_quien_recibe():
    """En `destino` lo cobra el transportista en el mostrador."""
    base = _con_agencia(db_completa(envios=[_envio_con_destino(
        modalidad_flete="destino")]))
    t = corre(op.ticket("env_aaa111", db=base))
    assert t["pago"]["modalidad"] == "destino"
    assert t["pago"]["cobrar_al_recibir"] is True


def test_en_prepago_el_ticket_dice_que_NO_se_cobra():
    """Ya se pagó por remesa. Cobrarle de nuevo a quien retira es cobrar dos
    veces el mismo tramo, y el que lo paga es alguien que ya pagó.

    MUTACION: que `cobrar_al_recibir` sea siempre True y este test se pone en
    rojo. Es el error caro de los dos: no cobrar cuando había que cobrar se
    arregla con una llamada; cobrar de más ya salió del bolsillo de alguien.
    """
    base = _con_agencia(db_completa(envios=[_envio_con_destino(
        modalidad_flete="prepago", flete={"estado": "acreditado",
                                          "monto_ris": "40.00"})]))
    t = corre(op.ticket("env_aaa111", db=base))
    assert t["pago"]["modalidad"] == "prepago"
    assert t["pago"]["cobrar_al_recibir"] is False
    assert t["pago"]["flete_estado"] == "acreditado"


def test_el_ticket_dice_cuando_la_caja_NO_puede_salir():
    """El papel se imprime antes de que la caja se cargue, así que tiene que
    poder decir «esta no sale». Un ticket que se ve igual con la partida impaga
    es un ticket que ayuda a despachar lo que no se puede despachar."""
    con_deuda = _envio_con_destino(
        cobros={"inicial": {"monto_ris": "132.00", "estado": "pendiente"},
                "ajuste": None})
    base = _con_agencia(db_completa(envios=[con_deuda]))
    t = corre(op.ticket("env_aaa111", db=base))
    assert t["puede_salir"] is False
    assert t["partidas_impagas"] == ["inicial"]


def test_el_ticket_dice_si_el_peso_es_de_la_balanza_o_lo_declarado():
    """Un peso sin origen en un papel que viaja es el que después nadie puede
    defender."""
    base = _con_agencia(db_completa(envios=[_envio_con_destino()]))
    t = corre(op.ticket("env_aaa111", db=base))
    assert t["paquete"]["peso_es_verificado"] is False
    assert t["paquete"]["peso_kg"] == "2.30"

    pesado = _envio_con_destino(envio_id="env_bbb222")
    pesado["paquete"]["verificado"] = {"peso_kg": "3.10"}
    base2 = _con_agencia(db_completa(envios=[pesado]))
    t2 = corre(op.ticket("env_bbb222", db=base2))
    assert t2["paquete"]["peso_es_verificado"] is True
    assert t2["paquete"]["peso_kg"] == "3.10"


def test_un_envio_que_no_existe_no_devuelve_un_ticket_en_blanco():
    with pytest.raises(op.OperacionRechazada) as e:
        corre(op.ticket("env_no_existe", db=db_completa()))
    assert e.value.http == 404


def test_el_ticket_nunca_mete_datos_de_una_persona_en_innerHTML():
    """El nombre de quien recibe y la direccion los escribio una persona.

    Meterlos en un `innerHTML` es dejar que un nombre con `<script>` corra en una
    ventana que se abre con la sesion del operador. En `ticket.js` el HTML es una
    cascara FIJA y los datos entran siempre por `textContent`, que no interpreta
    nada.

    Este test permite exactamente una asignacion a innerHTML —la de la cascara,
    que es una constante del modulo— y falla ante cualquier otra. Se verifica
    sobre el fuente porque el frontend no tiene runner de tests, y porque el dia
    que alguien agregue un renglon al ticket la salida facil es interpolarlo.
    """
    import re

    ruta = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..",
        "frontend", "src", "components", "admin", "envios", "ticket.js"))
    if not os.path.isfile(ruta):                              # pragma: no cover
        pytest.skip("el frontend no esta en este arbol")
    with open(ruta, encoding="utf-8") as f:
        fuente = f.read()

    asignaciones = re.findall(r"\.innerHTML\s*=\s*([^;\n]+)", fuente)
    assert asignaciones == ["CASCARA"], (
        "El ticket asigna a innerHTML algo que no es la cascara fija:\n  "
        + "\n  ".join(asignaciones)
        + "\nLos datos de una persona van por textContent (mira `poner`)."
    )
    # Y que no se cuele por la otra puerta.
    for prohibido in ("insertAdjacentHTML", "outerHTML", "document.writeln"):
        assert prohibido not in fuente, (
            f"`{prohibido}` interpreta HTML igual que innerHTML. Usa textContent.")
