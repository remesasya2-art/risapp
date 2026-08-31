"""
El unico modulo del sistema de envios que mueve plata.

CONTEXTO
    RIS App cobra un solo servicio, en dos partidas: la INICIAL al verificar el
    comprobante de despacho —calculada con el peso que midio el transportista de
    origen, una medicion ajena— y el AJUSTE al repesar con balanza propia en
    Pacaraima.

LA REGLA QUE ORDENA TODO EL ARCHIVO
    Que una partida quede impaga NO es un error: es un estado del negocio. Cuando
    se emite el cobro inicial el paquete ya esta viajando y no depende de
    nosotros, asi que quedarse sin saldo no puede cancelar nada ni devolver un
    402. La partida queda pendiente y la unica palanca de cobro real —que el
    paquete no salga de Pacaraima— se ejerce en otro lado.

QUE SE CUBRE
    1. El debito es atomico: dos peticiones simultaneas no sobregiran.
    2. Saldo justo: se puede pagar exactamente lo que hay.
    3. Sin saldo: queda pendiente, no revienta y no devuelve 402.
    4. Si falla marcar la partida DESPUES de debitar, se devuelve el saldo.
    5. Doble clic: se cobra una sola vez.
    6. Se cobra con la tarifa CONGELADA, nunca con la vigente.
    7. El libro registra el movimiento, y que el libro falle no rompe el cobro.

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

TARIFA_NUEVA = {**TARIFA, "version_id": "tar_2026_09_a",
                "escalones_peso": [{**e, "precio": str(Decimal(e["precio"]) * 3)}
                                   for e in TARIFA["escalones_peso"]]}

ENVIO = {
    "envio_id": "env_aaa111", "display_id": "E000001", "user_id": "usr_ana",
    "estado": "en_transito_origen",
    "paquete": {
        "declarado": {"peso_kg": "2.30", "largo_cm": "40", "ancho_cm": "30",
                      "alto_cm": "20", "valor_declarado": "180.00"},
        "bultos": 1,
    },
    "cotizacion": {"tarifa_version": "tar_2026_08_a", "fecha": "2026-08-30",
                   "total_estimado_ris": "132.00", "moneda": "RIS"},
    "cobros": {"inicial": None, "ajuste": None,
               "reembolsado_ris": "0.00", "total_cobrado_ris": "0.00"},
}


class _Usuario:
    user_id = "usr_ana"


def db_completa(saldo="500.00", envio=None, tarifas_envio=None):
    import copy
    base = _Db(
        envios=[copy.deepcopy(envio or ENVIO)],
        tarifas_envio=copy.deepcopy(tarifas_envio or [TARIFA]),
        users=[{"user_id": "usr_ana", "email": "ana@example.com",
                "balance_ris": Decimal128(Decimal(saldo))}],
        ledger=[], idempotency_keys=[],
    )
    usar_base(base)
    idem._idem_indexes_ready = True
    ledger._indexes_ready = True
    return base


def saldo_de(base) -> Decimal:
    return _num(base.users.filas[0]["balance_ris"])


def envio_de(base) -> dict:
    return base.envios.filas[0]


# ─── 1. El cobro inicial ──────────────────────────────────────────────────

def test_el_cobro_inicial_se_calcula_con_el_peso_del_comprobante():
    """Una medición ajena, hecha por alguien sin ningún interés en que sea baja,
    y disponible antes de que el paquete cruce nada."""
    base = db_completa()
    r = corre(cobros.emitir_inicial(envio_de(base), "2.65", "40", "30", "20",
                                    db=base, ahora=AHORA))
    esperado = tarifas.cotizar_servicio(TARIFA, "2.65", "40", "30", "20",
                                        valor_declarado="180.00", bultos=1,
                                        fecha="2026-08-30")["total"]
    assert Decimal(r["monto_ris"]) == esperado
    assert r["estado"] == "pagado"
    assert saldo_de(base) == Decimal("500.00") - esperado


def test_se_cobra_con_la_tarifa_congelada_y_no_con_la_vigente():
    """Lo que impide cobrarle a alguien un aumento posterior a lo que aceptó."""
    # La MAS NUEVA primero: si el codigo tomara "la primera que encuentre" en
    # vez de la congelada, este test no lo veria con el orden al reves.
    base = db_completa(tarifas_envio=[TARIFA_NUEVA, TARIFA])
    r = corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                    db=base, ahora=AHORA))
    con_la_vieja = tarifas.cotizar_servicio(TARIFA, "2.30", "40", "30", "20",
                                            valor_declarado="180.00", bultos=1,
                                            fecha="2026-08-30")["total"]
    assert Decimal(r["monto_ris"]) == con_la_vieja
    assert envio_de(base)["cobros"]["inicial"]["detalle"]["tarifa_version"] == \
        "tar_2026_08_a"


def test_sin_la_version_congelada_no_se_cobra():
    """Cobrar sin saber con qué precio se cotizó es arriesgarse a cobrar precios
    que el usuario no aceptó."""
    sin_version = {**ENVIO, "cotizacion": {"total_estimado_ris": "132.00"}}
    base = db_completa(envio=sin_version)
    with pytest.raises(cobros.CobroImposible) as e:
        corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                    db=base, ahora=AHORA))
    assert e.value.http == 409
    assert "con qué versión de tarifa" in e.value.mensaje
    assert saldo_de(base) == Decimal("500.00")


def test_si_la_version_congelada_ya_no_existe_no_se_inventa_otra():
    base = db_completa(tarifas_envio=[TARIFA_NUEVA])
    with pytest.raises(cobros.CobroImposible) as e:
        corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                    db=base, ahora=AHORA))
    assert e.value.http == 409
    assert saldo_de(base) == Decimal("500.00")


def test_el_cobro_queda_registrado_en_el_envio_con_su_base():
    base = db_completa()
    corre(cobros.emitir_inicial(envio_de(base), "2.65", "40", "30", "20",
                                db=base, ahora=AHORA))
    partida = envio_de(base)["cobros"]["inicial"]
    assert partida["estado"] == "pagado"
    assert partida["base"] == "comprobante"
    assert Decimal(partida["peso_base_kg"]) == Decimal("2.65")
    assert partida["pagado_at"] == AHORA


# ─── 2. Saldo ─────────────────────────────────────────────────────────────

def test_saldo_justo_alcanza():
    """El borde exacto: el `$gte` tiene que dejar pasar la igualdad."""
    base = db_completa(saldo="132.00")
    r = corre(cobros.cobrar(envio_de(base), "inicial", "132.00", db=base, ahora=AHORA))
    assert r["estado"] == "pagado"
    assert saldo_de(base) == Decimal("0.00")
    assert Decimal(r["saldo_restante"]) == Decimal("0.00")


def test_un_centavo_de_menos_deja_la_partida_pendiente():
    base = db_completa(saldo="131.99")
    r = corre(cobros.cobrar(envio_de(base), "inicial", "132.00", db=base, ahora=AHORA))
    assert r["estado"] == "pendiente" and r["motivo"] == "saldo"
    assert saldo_de(base) == Decimal("131.99")     # no se tocó


def test_sin_saldo_no_es_un_error_ni_un_402():
    """Cuando se emite el cobro inicial el paquete ya está viajando: quedarse sin
    saldo no puede cancelar nada. La única palanca real —que no salga de
    Pacaraima— se ejerce en otro lado."""
    base = db_completa(saldo="0.00")
    r = corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                    db=base, ahora=AHORA))
    assert r["estado"] == "pendiente"
    partida = envio_de(base)["cobros"]["inicial"]
    assert partida["estado"] == "pendiente"
    assert Decimal(partida["monto_ris"]) > 0
    assert estados.partidas_impagas(envio_de(base)) == ["inicial"]


def test_la_partida_pendiente_se_puede_saldar_despues():
    base = db_completa(saldo="0.00")
    corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                db=base, ahora=AHORA))
    base.users.filas[0]["balance_ris"] = Decimal128(Decimal("200.00"))

    r = corre(cobros.pagar_pendiente(envio_de(base), "inicial", db=base, ahora=AHORA))
    assert r["estado"] == "pagado"
    assert estados.partidas_impagas(envio_de(base)) == []
    assert saldo_de(base) == Decimal("200.00") - Decimal("132.00")


def test_saldar_dos_veces_no_cobra_dos_veces():
    base = db_completa()
    corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                db=base, ahora=AHORA))
    saldo = saldo_de(base)
    r = corre(cobros.pagar_pendiente(envio_de(base), "inicial", db=base, ahora=AHORA))
    assert r["estado"] == "pagado"
    assert saldo_de(base) == saldo


def test_saldar_algo_que_no_existe_es_404():
    base = db_completa()
    with pytest.raises(cobros.CobroImposible) as e:
        corre(cobros.pagar_pendiente(envio_de(base), "ajuste", db=base, ahora=AHORA))
    assert e.value.http == 404


# ─── 3. El débito es atómico ──────────────────────────────────────────────

def test_dos_cobros_simultaneos_no_sobregiran():
    """Leer el saldo y después restar es una carrera con la plata de alguien. El
    `find_one_and_update` condicional es lo único que lo impide."""
    base = db_completa(saldo="150.00")
    envio_b = {**ENVIO, "envio_id": "env_bbb222", "display_id": "E000002"}
    import copy
    base.envios.filas.append(copy.deepcopy(envio_b))

    base.envios.CEDER = 1          # que las dos tareas se intercalen de verdad
    base.users.CEDER = 1

    async def dos():
        return await asyncio.gather(
            cobros.cobrar(base.envios.filas[0], "inicial", "132.00", db=base,
                          ahora=AHORA),
            cobros.cobrar(base.envios.filas[1], "inicial", "132.00", db=base,
                          ahora=AHORA),
        )
    a, b = corre(dos())

    pagados = [x for x in (a, b) if x["estado"] == "pagado"]
    assert len(pagados) == 1, "los dos cobros no pueden salir de 150 RIS"
    assert saldo_de(base) == Decimal("18.00")
    assert saldo_de(base) >= 0


def test_el_saldo_nunca_queda_negativo():
    base = db_completa(saldo="10.00")
    for _ in range(5):
        envio = envio_de(base)
        envio["cobros"]["inicial"] = None
        corre(cobros.cobrar(envio, "inicial", "50.00", db=base, ahora=AHORA))
    assert saldo_de(base) == Decimal("10.00")


# ─── 4. El rollback ───────────────────────────────────────────────────────

def test_si_falla_marcar_la_partida_despues_de_debitar_se_devuelve_el_saldo():
    """Es el patrón de compensación que `/reais/send` ya usa cuando el
    beneficiario no existe. No se inventó uno nuevo."""
    base = db_completa()
    original = cobros._marcar_pagada

    async def no_marca(*a, **k):
        return None
    cobros._marcar_pagada = no_marca
    try:
        with pytest.raises(cobros.CobroImposible) as e:
            corre(cobros.cobrar(envio_de(base), "inicial", "132.00",
                                db=base, ahora=AHORA))
    finally:
        cobros._marcar_pagada = original

    assert e.value.http == 503
    assert "no fue afectado" in e.value.mensaje
    assert saldo_de(base) == Decimal("500.00")     # devuelto
    assert envio_de(base)["cobros"]["inicial"]["estado"] == "pendiente"


def test_si_falla_emitir_la_partida_no_se_debita_nada():
    """La partida se registra ANTES de tocar el saldo: si se debita y después no
    se puede escribir que se debitó, el usuario pagó y el envío no lo sabe."""
    base = db_completa()

    async def revienta(*a, **k):
        raise RuntimeError("caída al emitir")
    base.envios.find_one_and_update = revienta

    with pytest.raises(cobros.CobroImposible):
        corre(cobros.cobrar(envio_de(base), "inicial", "132.00", db=base, ahora=AHORA))
    assert saldo_de(base) == Decimal("500.00")


def test_si_el_debito_falla_la_partida_queda_pendiente_y_no_se_pierde():
    base = db_completa()

    async def revienta(*a, **k):
        raise RuntimeError("mongo caído")
    base.users.find_one_and_update = revienta

    r = corre(cobros.cobrar(envio_de(base), "inicial", "132.00", db=base, ahora=AHORA))
    assert r["estado"] == "pendiente" and r["motivo"] == "error"
    assert envio_de(base)["cobros"]["inicial"]["estado"] == "pendiente"


# ─── 5. Idempotencia ──────────────────────────────────────────────────────

def test_un_doble_clic_cobra_una_sola_vez():
    base = db_completa()
    a = corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                    db=base, ahora=AHORA, idempotency_key="k1"))
    b = corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                    db=base, ahora=AHORA, idempotency_key="k1"))
    assert a["monto_ris"] == b["monto_ris"]
    assert saldo_de(base) == Decimal("500.00") - Decimal(a["monto_ris"])
    assert len(base.ledger.filas) == 1


def test_una_partida_ya_emitida_no_se_reemite():
    """Reemitirla es cobrar dos veces lo mismo."""
    base = db_completa()
    corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                db=base, ahora=AHORA))
    saldo = saldo_de(base)
    r = corre(cobros.emitir_inicial(envio_de(base), "9.00", "40", "30", "20",
                                    db=base, ahora=AHORA))
    assert r["estado"] == "pagado"
    assert saldo_de(base) == saldo


def test_la_clave_de_idempotencia_incluye_el_envio_y_la_partida():
    """Con una acción fija, una clave reusada entre dos envíos devuelve el
    resultado del primero y el segundo nunca se cobra. Acá costaría plata."""
    a = cobros.accion_idempotencia("env_aaa111", "inicial")
    b = cobros.accion_idempotencia("env_bbb222", "inicial")
    c = cobros.accion_idempotencia("env_aaa111", "ajuste")
    assert len({a, b, c}) == 3


def test_la_misma_clave_en_dos_envios_cobra_los_dos():
    base = db_completa(saldo="500.00")
    import copy
    base.envios.filas.append(copy.deepcopy(
        {**ENVIO, "envio_id": "env_bbb222", "display_id": "E000002"}))

    a = corre(cobros.cobrar(base.envios.filas[0], "inicial", "50.00", db=base,
                            ahora=AHORA, idempotency_key="K"))
    b = corre(cobros.cobrar(base.envios.filas[1], "inicial", "70.00", db=base,
                            ahora=AHORA, idempotency_key="K"))
    assert a["estado"] == b["estado"] == "pagado"
    assert Decimal(b["monto_ris"]) == Decimal("70.00")
    assert saldo_de(base) == Decimal("380.00")


# ─── 6. El libro ──────────────────────────────────────────────────────────

def test_el_cobro_deja_su_asiento_en_el_libro():
    base = db_completa()
    r = corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                    db=base, ahora=AHORA))
    asiento = base.ledger.filas[0]
    assert asiento["movement_type"] == cobros.MOVIMIENTO_COBRO
    assert asiento["direction"] == "debit"
    assert Decimal(str(asiento["amount"])) == Decimal(r["monto_ris"])
    assert asiento["reference"] == {"kind": "envio", "id": "env_aaa111"}
    assert asiento["display_id"] == "E000001"
    assert asiento["metadata"]["partida"] == "inicial"
    assert asiento["metadata"]["tarifa_version"] == "tar_2026_08_a"


def test_que_el_libro_falle_no_rompe_el_cobro():
    """El libro es un registro, no la fuente de verdad del saldo."""
    base = db_completa()

    async def revienta(*a, **k):
        raise RuntimeError("libro caído")
    base.ledger.insert_one = revienta

    r = corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                    db=base, ahora=AHORA))
    assert r["estado"] == "pagado" and r["entry_id"] is None
    assert envio_de(base)["cobros"]["inicial"]["estado"] == "pagado"


def test_no_se_asienta_nada_cuando_la_partida_queda_pendiente():
    """Un asiento sin movimiento de saldo es una línea de libro que miente."""
    base = db_completa(saldo="0.00")
    corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                db=base, ahora=AHORA))
    assert base.ledger.filas == []


# ─── 7. Lo que no se cobra ────────────────────────────────────────────────

@pytest.mark.parametrize("monto", ["0", "0.00", "-5", "-0.01"])
def test_un_cobro_de_cero_o_negativo_no_se_emite(monto):
    """Si no hay nada que cobrar, la partida no existe. Emitirla en cero deja un
    envío con una deuda de cero que bloquea la salida de Pacaraima."""
    base = db_completa()
    with pytest.raises(cobros.CobroImposible) as e:
        corre(cobros.cobrar(envio_de(base), "inicial", monto, db=base, ahora=AHORA))
    assert e.value.http == 500
    assert envio_de(base)["cobros"]["inicial"] is None


def test_una_partida_desconocida_no_se_cobra():
    base = db_completa()
    with pytest.raises(cobros.CobroImposible):
        corre(cobros.cobrar(envio_de(base), "propina", "10.00", db=base, ahora=AHORA))


def test_el_envio_de_otro_usuario_no_existe():
    base = db_completa()

    class _Otro:
        user_id = "usr_otro"

    with pytest.raises(cobros.CobroImposible) as e:
        corre(cobros.envio_del_usuario(_Otro(), "env_aaa111", db=base))
    with pytest.raises(cobros.CobroImposible) as e2:
        corre(cobros.envio_del_usuario(_Usuario(), "env_no_existe", db=base))
    assert e.value.http == e2.value.http == 404
    assert e.value.mensaje == e2.value.mensaje


def test_el_modulo_no_menciona_ninguna_marca():
    fuente = open(os.path.join(_BACKEND, "services", "envios_cobros.py"),
                  encoding="utf-8").read().lower()
    for marca in ("mrw", "correios", "zoom", "tealca", "domesa"):
        assert marca not in fuente


# ─── 8. Lo que encontro la verificacion por mutacion ──────────────────────

def test_dos_pagos_simultaneos_de_la_misma_partida_debitan_una_sola_vez():
    """EL DEFECTO. El débito es atómico contra el SALDO, no contra la deuda: dos
    peticiones simultáneas de pago de la misma partida ven las dos `pendiente`,
    las dos encuentran saldo suficiente, y las dos debitan. El usuario paga dos
    veces lo mismo y solo una queda marcada.

    Lo que lo impide es reservar la partida —`pendiente` a `pagando`— antes de
    tocar el saldo."""
    base = db_completa(saldo="500.00")
    corre(cobros.cobrar(envio_de(base), "inicial", "132.00", db=base, ahora=AHORA))
    # Se la deja pendiente a mano, como si no hubiera habido saldo al emitirla.
    envio_de(base)["cobros"]["inicial"]["estado"] = "pendiente"
    envio_de(base)["cobros"]["inicial"]["pagado_at"] = None
    base.users.filas[0]["balance_ris"] = Decimal128(Decimal("500.00"))
    base.ledger.filas.clear()          # se cuentan los asientos de los dos pagos
    base.envios.CEDER = 1              # que las dos tareas se intercalen de verdad
    base.users.CEDER = 1

    async def dos():
        return await asyncio.gather(
            cobros.pagar_pendiente(envio_de(base), "inicial", db=base, ahora=AHORA),
            cobros.pagar_pendiente(envio_de(base), "inicial", db=base, ahora=AHORA),
        )
    a, b = corre(dos())

    # Lo que importa: UN solo débito. Las dos respuestas son válidas —la que
    # pierde contesta con lo que diga la base, que es "pagado" si el ganador ya
    # marcó, o "pendiente / en curso" si todavía no— pero ninguna es un error, y
    # el saldo se movió una sola vez.
    assert saldo_de(base) == Decimal("500.00") - Decimal("132.00")
    assert envio_de(base)["cobros"]["inicial"]["estado"] == "pagado"
    assert {a["estado"], b["estado"]} <= {"pagado", "pendiente"}
    assert len(base.ledger.filas) == 1


def test_una_partida_no_queda_trabada_si_no_hay_saldo():
    """La reserva es de milisegundos. Si queda en `pagando`, la deuda no figura
    como pendiente ni está pagada: el paquete no sale de Pacaraima y ninguna ruta
    la destraba."""
    base = db_completa(saldo="0.00")
    corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                db=base, ahora=AHORA))
    r = corre(cobros.pagar_pendiente(envio_de(base), "inicial", db=base, ahora=AHORA))
    assert r["estado"] == "pendiente"
    assert envio_de(base)["cobros"]["inicial"]["estado"] == "pendiente"
    assert estados.partidas_impagas(envio_de(base)) == ["inicial"]


def test_tampoco_queda_trabada_si_falla_el_debito():
    base = db_completa(saldo="0.00")
    corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                db=base, ahora=AHORA))

    async def revienta(*a, **k):
        raise RuntimeError("mongo caído")
    base.users.find_one_and_update = revienta

    corre(cobros.pagar_pendiente(envio_de(base), "inicial", db=base, ahora=AHORA))
    assert envio_de(base)["cobros"]["inicial"]["estado"] == "pendiente"


def test_ni_cuando_hay_que_devolver_el_saldo():
    base = db_completa(saldo="0.00")
    corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                db=base, ahora=AHORA))
    base.users.filas[0]["balance_ris"] = Decimal128(Decimal("500.00"))
    original = cobros._marcar_pagada

    async def no_marca(*a, **k):
        return None
    cobros._marcar_pagada = no_marca
    try:
        with pytest.raises(cobros.CobroImposible):
            corre(cobros.pagar_pendiente(envio_de(base), "inicial",
                                         db=base, ahora=AHORA))
    finally:
        cobros._marcar_pagada = original

    assert saldo_de(base) == Decimal("500.00")
    assert envio_de(base)["cobros"]["inicial"]["estado"] == "pendiente"


def test_el_total_cobrado_acumula_las_partidas():
    """Es el precio final del servicio, y es lo que se lee para saber si el envío
    está al día. Un total que no acumula deja una deuda invisible."""
    base = db_completa(saldo="500.00")
    corre(cobros.cobrar(envio_de(base), "inicial", "132.00", db=base, ahora=AHORA))
    assert Decimal(envio_de(base)["cobros"]["total_cobrado_ris"]) == Decimal("132.00")

    corre(cobros.cobrar(envio_de(base), "ajuste", "6.70", db=base, ahora=AHORA))
    assert Decimal(envio_de(base)["cobros"]["total_cobrado_ris"]) == Decimal("138.70")
    assert saldo_de(base) == Decimal("500.00") - Decimal("138.70")


def test_la_guardia_del_documento_frena_una_reemision_aunque_el_dict_este_rancio():
    """Dos capas: el chequeo sobre el envío que se recibió, y el filtro del
    update. La segunda existe para el caso en que el dict venga de una lectura
    anterior a la emisión — que es exactamente lo que ve la segunda petición de
    un doble clic."""
    base = db_completa()
    import copy
    rancio = copy.deepcopy(envio_de(base))          # sin la partida todavía
    corre(cobros.cobrar(envio_de(base), "inicial", "132.00", db=base, ahora=AHORA))
    saldo = saldo_de(base)

    r = corre(cobros.cobrar(rancio, "inicial", "999.00", db=base, ahora=AHORA))
    assert Decimal(r["monto_ris"]) == Decimal("132.00")
    assert saldo_de(base) == saldo


# ─── 9. Lo que encontro la revision adversarial ───────────────────────────

def test_una_reserva_abandonada_sin_debito_vuelve_a_pendiente():
    """Si el proceso muere entre la reserva y el débito, la partida queda en
    `pagando` para siempre: no figura pendiente, no está pagada, y el paquete no
    sale de Pacaraima. Ninguna ruta la destrabaría."""
    base = db_completa(saldo="0.00")
    corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                db=base, ahora=AHORA))
    partida = envio_de(base)["cobros"]["inicial"]
    partida["estado"] = "pagando"
    partida["intento_id"] = "int_muerto"
    partida["reservado_at"] = AHORA - timedelta(hours=1)
    base.users.filas[0]["balance_ris"] = Decimal128(Decimal("500.00"))

    r = corre(cobros.pagar_pendiente(envio_de(base), "inicial", db=base,
                                     ahora=AHORA))
    assert r["estado"] == "pagado"
    assert saldo_de(base) == Decimal("500.00") - Decimal("132.00")


def test_una_reserva_abandonada_con_debito_hecho_se_cierra_sin_cobrar_de_nuevo():
    """El libro se escribe ANTES de marcar justamente para esto: un asiento con
    ese `intento_id` dice que la plata ya salió, y entonces lo correcto es
    terminar de marcar la partida, no volver a debitar."""
    base = db_completa(saldo="368.00")
    corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                db=base, ahora=AHORA))
    # Se simula el estado justo después del débito y antes del marcado.
    partida = envio_de(base)["cobros"]["inicial"]
    partida["estado"] = "pagando"
    partida["intento_id"] = "int_yadebitado"
    partida["reservado_at"] = AHORA - timedelta(hours=1)
    base.ledger.filas.append({"entry_id": "le_x", "amount": 132.00,
                              "metadata": {"intento_id": "int_yadebitado"}})
    saldo = saldo_de(base)

    r = corre(cobros.pagar_pendiente(envio_de(base), "inicial", db=base, ahora=AHORA))
    assert saldo_de(base) == saldo, "no se puede volver a debitar lo ya debitado"
    assert envio_de(base)["cobros"]["inicial"]["estado"] == "pagado"
    assert r["estado"] in ("pagado", "pendiente")


def test_una_reserva_reciente_no_se_pisa():
    """La reserva vive milisegundos: pisarla porque sí es exactamente el doble
    cobro que la reserva existe para impedir."""
    base = db_completa()
    corre(cobros.cobrar(envio_de(base), "inicial", "132.00", db=base, ahora=AHORA))
    partida = envio_de(base)["cobros"]["inicial"]
    partida["estado"] = "pagando"
    partida["reservado_at"] = AHORA
    saldo = saldo_de(base)

    r = corre(cobros.pagar_pendiente(envio_de(base), "inicial", db=base, ahora=AHORA))
    assert r["estado"] == "pendiente" and r["motivo"] == "en_curso"
    assert saldo_de(base) == saldo


def test_si_el_marcado_ya_se_habia_aplicado_no_se_devuelve_el_saldo():
    """Una excepción de red no significa "la escritura no ocurrió": significa "no
    sé si ocurrió". Devolver el saldo sobre una partida que quedó pagada regala
    el traslado y libera Pacaraima."""
    base = db_completa()
    original = cobros._marcar_pagada

    async def marca_y_miente(base_, envio_id, partida, intento, importe, ahora):
        await original(base_, envio_id, partida, intento, importe, ahora)
        return None                      # la escritura se aplicó, la respuesta se perdió
    cobros._marcar_pagada = marca_y_miente
    try:
        r = corre(cobros.cobrar(envio_de(base), "inicial", "132.00",
                                db=base, ahora=AHORA))
    finally:
        cobros._marcar_pagada = original

    assert r["estado"] == "pagado"
    assert saldo_de(base) == Decimal("500.00") - Decimal("132.00")
    assert envio_de(base)["cobros"]["inicial"]["estado"] == "pagado"


def test_un_marcado_que_no_matchea_no_se_toma_por_exito():
    """`update_one` que no matchea NO lanza. Tratarlo como éxito dejaba el débito
    hecho, la partida pendiente y la respuesta diciendo `pagado`: el siguiente
    intento cobraba de nuevo."""
    base = db_completa()
    original = cobros._marcar_pagada

    async def no_matchea(*a, **k):
        return None
    cobros._marcar_pagada = no_matchea
    try:
        with pytest.raises(cobros.CobroImposible):
            corre(cobros.cobrar(envio_de(base), "inicial", "132.00",
                                db=base, ahora=AHORA))
    finally:
        cobros._marcar_pagada = original
    assert saldo_de(base) == Decimal("500.00")


def test_el_total_no_depende_de_quien_leyo_primero():
    """Se cobra el ajuste, se paga después la inicial desde una pantalla que leyó
    el envío antes, y el total decía 132,00 cuando el saldo había bajado 138,70.
    El campo que dice si el envío está al día no puede depender de eso."""
    import copy
    base = db_completa(saldo="0.00")
    corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                db=base, ahora=AHORA))
    rancio = copy.deepcopy(envio_de(base))       # leído antes del ajuste
    base.users.filas[0]["balance_ris"] = Decimal128(Decimal("500.00"))
    corre(cobros.cobrar(envio_de(base), "ajuste", "6.70", db=base, ahora=AHORA))

    corre(cobros.pagar_pendiente(rancio, "inicial", db=base, ahora=AHORA))
    assert Decimal(envio_de(base)["cobros"]["total_cobrado_ris"]) == Decimal("138.70")
    assert saldo_de(base) == Decimal("500.00") - Decimal("138.70")


def test_se_cobra_el_monto_persistido_y_no_el_del_dict_que_llega():
    """Un dict del llamador puede venir de una lectura anterior, y el módulo
    trata los dicts rancios como entrada esperada."""
    import copy
    base = db_completa(saldo="0.00")
    corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                db=base, ahora=AHORA))
    mentiroso = copy.deepcopy(envio_de(base))
    mentiroso["cobros"]["inicial"]["monto_ris"] = "1.00"
    base.users.filas[0]["balance_ris"] = Decimal128(Decimal("500.00"))

    corre(cobros.pagar_pendiente(mentiroso, "inicial", db=base, ahora=AHORA))
    assert saldo_de(base) == Decimal("500.00") - Decimal("132.00")


@pytest.mark.parametrize("estado", ["cancelado", "siniestrado", "devuelto"])
def test_no_se_cobra_sobre_un_envio_terminado(estado):
    """`cancelado` es, por definición, "cancelado antes de que hubiera nada que
    cobrar"; `siniestrado` abre indemnización. Un reproceso de comprobantes
    atrasados le cobraba el traslado a paquetes que nunca se trasladaron."""
    base = db_completa(envio={**ENVIO, "estado": estado})
    with pytest.raises(cobros.CobroImposible) as e:
        corre(cobros.emitir_inicial(envio_de(base), "2.30", "40", "30", "20",
                                    db=base, ahora=AHORA))
    assert e.value.http == 409
    assert saldo_de(base) == Decimal("500.00")


def test_no_se_puede_pagar_una_partida_inventada():
    """Cualquier clave con forma de dict dentro de `cobros` era cobrable desde la
    ruta: `/cobros/reembolso/pagar` debitaba el monto de una DEVOLUCIÓN."""
    envio = {**ENVIO, "cobros": {**ENVIO["cobros"],
                                 "reembolso": {"monto_ris": "80.00",
                                               "estado": "pendiente"}}}
    base = db_completa(envio=envio)
    with pytest.raises(cobros.CobroImposible) as e:
        corre(cobros.pagar_pendiente(envio_de(base), "reembolso", db=base, ahora=AHORA))
    assert e.value.http == 404
    assert saldo_de(base) == Decimal("500.00")


@pytest.mark.parametrize("monto", ["Infinity", "1e999", "no es un número", None])
def test_una_partida_con_un_monto_ilegible_da_un_motivo_y_no_un_503_en_bucle(monto):
    envio = {**ENVIO, "cobros": {**ENVIO["cobros"],
                                 "inicial": {"monto_ris": monto,
                                             "estado": "pendiente"}}}
    base = db_completa(envio=envio)
    with pytest.raises(cobros.CobroImposible) as e:
        corre(cobros.pagar_pendiente(envio_de(base), "inicial", db=base, ahora=AHORA))
    assert e.value.http == 409 and "legible" in e.value.mensaje


def test_una_partida_escrita_a_medias_no_bloquea_el_envio_sin_salida():
    """Un `{}` figuraba impago para `partidas_impagas`, emitirlo devolvía 503 en
    bucle y pagarlo devolvía 404: el envío quedaba bloqueado sin ninguna vía."""
    envio = {**ENVIO, "cobros": {**ENVIO["cobros"], "inicial": {}}}
    base = db_completa(envio=envio)
    with pytest.raises(cobros.CobroImposible) as e:
        corre(cobros.pagar_pendiente(envio_de(base), "inicial", db=base, ahora=AHORA))
    assert e.value.http == 409 and "legible" in e.value.mensaje


def test_el_estado_interno_de_la_reserva_no_sale_a_la_pantalla():
    """Hacia afuera hay dos estados y solo dos."""
    base = db_completa()
    corre(cobros.cobrar(envio_de(base), "inicial", "132.00", db=base, ahora=AHORA))
    envio_de(base)["cobros"]["inicial"]["estado"] = "pagando"
    envio_de(base)["cobros"]["inicial"]["reservado_at"] = AHORA
    r = corre(cobros.cobrar(envio_de(base), "inicial", "132.00", db=base, ahora=AHORA))
    assert r["estado"] in ("pagado", "pendiente")


def test_los_tipos_de_movimiento_no_chocan_con_los_de_remesas():
    """`pago_envio` y `refund_envio` ya significan el envío de una REMESA en esta
    aplicación. Una consulta del libro por `movement_type` mezclaría dos
    negocios."""
    assert cobros.MOVIMIENTO_COBRO not in ("pago_envio", "envio_ves", "envio_reais")
    assert cobros.MOVIMIENTO_REEMBOLSO not in ("refund_envio", "refund_envio_ves")
    for archivo in ("routes/admin.py", "routes/transactions.py"):
        fuente = open(os.path.join(_BACKEND, archivo), encoding="utf-8").read()
        assert cobros.MOVIMIENTO_COBRO not in fuente
        assert cobros.MOVIMIENTO_REEMBOLSO not in fuente


# ─── 10. Devolver ─────────────────────────────────────────────────────────

def test_se_puede_devolver_cuando_la_balanza_propia_da_menos():
    """Sin esto, el cobro inicial sería un anticipo que solo sube — que es
    exactamente lo que el diseño del ajuste dice que no puede pasar."""
    base = db_completa(saldo="368.00")
    r = corre(cobros.devolver(envio_de(base), "6.70", db=base, ahora=AHORA))
    assert r["estado"] == "acreditado"
    assert saldo_de(base) == Decimal("374.70")
    assert Decimal(envio_de(base)["cobros"]["reembolsado_ris"]) == Decimal("6.70")


def test_una_devolucion_no_se_acredita_dos_veces():
    base = db_completa(saldo="368.00")
    corre(cobros.devolver(envio_de(base), "6.70", db=base, ahora=AHORA))
    corre(cobros.devolver(envio_de(base), "6.70", db=base, ahora=AHORA))
    assert saldo_de(base) == Decimal("374.70")


def test_la_devolucion_deja_su_asiento():
    base = db_completa(saldo="368.00")
    corre(cobros.devolver(envio_de(base), "6.70", db=base, ahora=AHORA))
    asiento = base.ledger.filas[-1]
    assert asiento["movement_type"] == cobros.MOVIMIENTO_REEMBOLSO
    assert asiento["direction"] == "credit"


def test_una_devolucion_de_cero_no_se_emite():
    base = db_completa(saldo="368.00")
    with pytest.raises(cobros.CobroImposible):
        corre(cobros.devolver(envio_de(base), "0", db=base, ahora=AHORA))
    assert saldo_de(base) == Decimal("368.00")
