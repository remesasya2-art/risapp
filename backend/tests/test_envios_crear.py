"""
Confirmar una cotizacion. El boton que NO cobra.

CONTEXTO
    En el diseno original confirmar era cobrar. Ya no: el usuario paga el tramo 1
    directamente al transportista de origen, y RIS App recien cobra cuando puede
    verificar contra una medicion ajena —el peso del comprobante de despacho—.

    Eso cambia el manejo del error de raiz. Antes, sin saldo, no habia envio y un
    402 era correcto. Ahora el paquete existe y esta viajando: quedarse sin saldo
    no cancela nada, solo deja una partida pendiente.

QUE SE CUBRE
    1. Crear NO debita, no toca saldos y no escribe en el ledger.
    2. Las dos aceptaciones son DOS: falta cualquiera y no hay envio.
    3. Doble clic: un solo envio, misma respuesta.
    4. Cotizacion vencida: 409.
    5. Un envio de otro usuario: el mismo 404 que uno que no existe.
    6. El tracking_token es opaco y nunca secuencial.
    7. Los limites se revalidan, porque pueden haber cambiado desde la cotizacion.

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


def _proyectar(doc, proyeccion):
    if not proyeccion:
        return dict(doc)
    incluir = [k for k, v in proyeccion.items() if v and k != "_id"]
    if incluir:
        return {k: v for k, v in doc.items() if k in incluir}
    excluir = [k for k, v in proyeccion.items() if not v]
    return {k: v for k, v in doc.items() if k not in excluir}


def _camino(doc, clave):
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
        for k, v in (filtro or {}).items():
            actual = _camino(d, k)
            if isinstance(v, dict) and "$gte" in v:
                if actual is None or actual < v["$gte"]:
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

    UNICOS = ()

    async def insert_one(self, doc):
        for clave in self.UNICOS:
            if doc.get(clave) is None:
                continue
            if any(d.get(clave) == doc.get(clave) for d in self.filas):
                raise RuntimeError(f"E11000 duplicate key: {clave}")
        self.filas.append(dict(doc))

    async def delete_one(self, filtro):
        for i, d in enumerate(self.filas):
            if self._match(d, filtro):
                del self.filas[i]
                return
        return

    async def update_one(self, filtro, cambio, upsert=False):
        for d in self.filas:
            if self._match(d, filtro):
                d.update(cambio.get("$set") or {})
                for k, v in (cambio.get("$inc") or {}).items():
                    d[k] = (d.get(k) or 0) + v
                return
        if upsert:
            self.filas.append({**filtro, **(cambio.get("$set") or {})})

    async def find_one_and_update(self, filtro, cambio, upsert=False,
                                  return_document=True):
        for d in self.filas:
            if self._match(d, filtro):
                antes = dict(d)
                d.update(cambio.get("$set") or {})
                for k, v in (cambio.get("$inc") or {}).items():
                    d[k] = (d.get(k) or 0) + v
                # `return_document` se respeta: un cambio a False haria que
                # `_numerar` reciba el documento viejo y reasigne numero y token,
                # y un doble que siempre devuelve el nuevo no lo detecta.
                return dict(d) if return_document else antes
        if upsert:
            nuevo = {k: v for k, v in (filtro or {}).items()
                     if not isinstance(v, dict)}
            nuevo.update(cambio.get("$set") or {})
            for k, v in (cambio.get("$inc") or {}).items():
                nuevo[k] = v
            self.filas.append(nuevo)
            return dict(nuevo)
        return None


class _ColeccionUnica(_Coleccion):
    """Una colección con índice único, como la de idempotencia.

    El doble tiene que modelarlo: `claim_idempotency` reconoce una clave repetida
    justamente porque el `insert_one` falla. Sin la unicidad, un fake deja pasar
    dos reclamos de la misma clave y el test de doble clic verifica nada.
    """
    CLAVES = ("user_id", "action", "key")

    async def insert_one(self, doc):
        if any(all(d.get(k) == doc.get(k) for k in self.CLAVES) for d in self.filas):
            raise RuntimeError("E11000 duplicate key")
        self.filas.append(dict(doc))


class _Db:
    def __init__(self, **colecciones):
        self._c = {k: _Coleccion(v) for k, v in colecciones.items()}

    def _nueva(self, nombre):
        clase = _ColeccionUnica if nombre == "idempotency_keys" else _Coleccion
        coleccion = self._c.setdefault(nombre, clase([]))
        # Los unicos que declara services/envios_indices, para que el doble no
        # deje pasar un duplicado que la base real rechazaria.
        if nombre == "envios":
            coleccion.UNICOS = ("envio_id", "display_id", "tracking_token")
        elif nombre == "envios_eventos":
            coleccion.UNICOS = ("evento_id",)
        return coleccion

    def __getattr__(self, nombre):
        return self._nueva(nombre)

    def __getitem__(self, nombre):
        return self._nueva(nombre)


# `services/idempotency.py` usa el `db` global del modulo `database`. Se apunta
# el proxy del conftest a la base de cada test, para poder verificar la
# idempotencia de verdad en vez de saltearla: es la mitad de este PR.
from conftest import usar_base                                       # noqa: E402


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
_cargar("envios_estados")
_cargar("envios_eventos")
idem = _cargar("idempotency")
crear_mod = _cargar("envios_crear")
from models.envios_cotizacion import (PedidoDeCotizacion,        # noqa: E402
                                      PedidoDeCreacion, Declaracion)


def corre(coro):
    return asyncio.run(coro)


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
          "regla_peso": {"divisor": 6000, "escalon_kg": "0.5", "minimo_kg": "0.3"},
          "limites": {"peso_max_kg": 30, "lado_max_cm": 100, "suma_lados_max_cm": 200,
                      "largo_min_cm": 11, "ancho_min_cm": 6, "alto_min_cm": "0.4"}}
TRP_VE = {"transportista_id": "trp_ve1", "codigo": "TRP-3Q9X", "rol": "venezuela",
          "activo": True, "orden": 1, "nombre": "Empresa de Destino",
          "regla_peso": {"divisor": 4000, "escalon_kg": "1", "minimo_kg": "1"},
          "limites": {"peso_max_kg": 70, "lado_max_cm": 120}}

AGENCIA = {"transportista_id": "trp_ve1", "codigo": "agc_001", "nombre": "Centro",
           "estado": "Miranda", "ciudad": "Caracas", "activa": True, "zona": "zona_a"}

PUNTO = {"setting_id": "envios_punto_origen",
         "nombre": "AC Pacaraima", "cep": "69355000", "ciudad": "Pacaraima", "uf": "RR",
         "modalidad": "caixa_postal", "caixa_postal": "123", "direccion": None,
         "razon_social": "RIS App LTDA",
         "plantilla_direccion": ret.PLANTILLA_POR_DEFECTO,
         "retirador_activo_id": "col_aaaa1111"}

CONTENIDO = {"setting_id": "envios_contenido", "prohibidos": ["armas"],
             "terminos_version": "envios-v1",
             "texto_estimado": "Texto que edita el panel.",
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

ACEPTA_TODO = {"contenido_aceptado": True, "estimado_aceptado": True}


def pedido(**cambios) -> dict:
    datos = {k: (dict(v) if isinstance(v, dict) else v) for k, v in PEDIDO.items()}
    for clave, valor in cambios.items():
        if isinstance(valor, dict) and isinstance(datos.get(clave), dict):
            datos[clave] = {**datos[clave], **valor}
        else:
            datos[clave] = valor
    return PedidoDeCotizacion(**datos).model_dump()


def db_completa(**cambios):
    # copy.deepcopy y no dict(): `dict()` es superficial, así que un test que
    # tocaba `limites["peso_max_kg"]` le cambiaba el límite a los otros dieciséis.
    # Es el bug de fixture compartido, y en una suite de dinero es peor que en
    # otras: un test que contamina a otro hace que un fallo real parezca ruido.
    import copy
    base = dict(
        transportistas=copy.deepcopy([TRP_BR, TRP_VE]),
        agencias=copy.deepcopy([AGENCIA]),
        tarifas_envio=copy.deepcopy([TARIFA]),
        matrices_referencia=[],
        app_settings=copy.deepcopy([PUNTO, CONTENIDO, OPERACION]),
        colaboradores_retiro=copy.deepcopy([MARIA]),
        envios=[], envios_eventos=[], counters=[],
        users=[{"user_id": "usr_ana", "email": "ana@example.com",
                "balance_ris": 500.0}],
    )
    base.update(cambios)
    return _Db(**base)


@pytest.fixture(autouse=True)
def base_del_test():
    """Cada test corre contra su propia base, tambien para la idempotencia: una
    clave que sobrevive de un test al siguiente lo hace pasar (o fallar) por el
    motivo equivocado."""
    usar_base(db_completa())
    idem._idem_indexes_ready = True
    yield


def cotizado(base=None, **cambios):
    """Un envío recién cotizado, hecho con el cotizador de verdad."""
    base = base or db_completa()
    corre(cot.cotizar(_Usuario(), pedido(**cambios), db=base, ahora=AHORA))
    return base, base.envios.filas[0]["envio_id"]


# ─── 1. Crear no mueve plata ──────────────────────────────────────────────

def test_confirmar_no_debita_ni_un_centavo():
    """El botón que en cualquier otra app de este rubro sacaría plata. El usuario
    paga el tramo 1 directamente al transportista de origen; RIS App recién cobra
    contra el comprobante."""
    base, envio_id = cotizado()
    saldo_antes = base.users.filas[0]["balance_ris"]

    r = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))

    assert base.users.filas[0]["balance_ris"] == saldo_antes
    assert r["cobrado_ahora_ris"] == "0.00"
    for coleccion in ("ledger", "ris_entries", "transactions", "withdrawals"):
        assert base._c.get(coleccion) is None or base._c[coleccion].filas == []


def test_confirmar_sin_saldo_funciona_igual():
    """Quedarse sin saldo no puede cancelar nada: el paquete todavía no existe
    pero el compromiso sí, y el único lugar donde la falta de saldo detiene algo
    es la salida de Pacaraima."""
    base, envio_id = cotizado(
        db_completa(users=[{"user_id": "usr_ana", "balance_ris": 0.0}]))
    r = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))
    assert r["success"] is True
    assert base.envios.filas[0]["estado"] == "esperando_postagem"


def test_el_modulo_no_importa_nada_que_mueva_plata():
    """La forma más barata de que siga siendo cierto dentro de un año."""
    fuente = open(os.path.join(_BACKEND, "services", "envios_crear.py"),
                  encoding="utf-8").read()
    # Se leen las líneas de CODIGO, sin comentarios: un comentario que explica
    # por qué este módulo no toca plata no puede contar como si la tocara.
    codigo = "\n".join(l for l in fuente.split("\n")
                       if not l.lstrip().startswith("#"))
    for prohibido in ("record_ris_entry", "balance_ris", "ledger", "to_decimal128",
                      "debitar", "acreditar", "withdrawal"):
        assert prohibido not in codigo


# ─── 2. Las dos aceptaciones son dos ──────────────────────────────────────

@pytest.mark.parametrize("declaracion,falta", [
    ({"contenido_aceptado": False, "estimado_aceptado": True}, "prohibidos"),
    ({"contenido_aceptado": True, "estimado_aceptado": False}, "estimado"),
    ({"contenido_aceptado": False, "estimado_aceptado": False}, "prohibidos"),
    ({}, "prohibidos"),
])
def test_falta_cualquiera_de_las_dos_y_no_hay_envio(declaracion, falta):
    """Juntarlas en un solo checkbox esconde la del precio detrás de la del
    contenido, que es justo lo que no se quiere el día que haya que defender el
    cobro de un ajuste."""
    base, envio_id = cotizado()
    with pytest.raises(crear_mod.NoSePuedeCrear) as e:
        corre(crear_mod.crear(_Usuario(), envio_id, declaracion, db=base, ahora=AHORA))
    assert e.value.http == 400 and falta in e.value.mensaje
    assert base.envios.filas[0]["estado"] == "cotizado"


def test_un_valor_que_no_es_true_no_cuenta_como_aceptacion():
    """"si", 1 y "true" no son un checkbox tildado: son un cliente mandando
    cualquier cosa. La aceptación es un hecho jurídico, no una sugerencia."""
    base, envio_id = cotizado()
    for valor in ("si", 1, "true", "on"):
        with pytest.raises(crear_mod.NoSePuedeCrear):
            corre(crear_mod.crear(
                _Usuario(), envio_id,
                {"contenido_aceptado": valor, "estimado_aceptado": valor},
                db=base, ahora=AHORA))


def test_el_modelo_exige_las_dos_y_no_las_da_por_defecto():
    """Una petición que se olvida el campo tiene que fallar, no pasar como "no
    aceptó"."""
    with pytest.raises(Exception):
        Declaracion(contenido_aceptado=True)
    assert Declaracion(contenido_aceptado=True,
                       estimado_aceptado=False).estimado_aceptado is False


def test_las_dos_aceptaciones_quedan_registradas_con_su_version_de_terminos():
    """Es lo que se lee el día que haya que defender el cobro de un ajuste."""
    base, envio_id = cotizado()
    corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA,
                          ip="200.1.2.3"))
    dec = base.envios.filas[0]["declaracion"]
    assert dec["contenido_aceptado"] is True and dec["estimado_aceptado"] is True
    assert dec["terminos_version"] == "envios-v1"
    assert dec["at"] == AHORA and dec["ip"] == "200.1.2.3"


# ─── 3. Doble clic ────────────────────────────────────────────────────────

def test_un_doble_clic_confirma_una_sola_vez():
    base, envio_id = cotizado()
    primera = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base,
                                    ahora=AHORA, idempotency_key="k-1"))
    segunda = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base,
                                    ahora=AHORA, idempotency_key="k-1"))
    assert primera == segunda
    assert primera["display_id"] == segunda["display_id"]
    assert len([e for e in base.envios_eventos.filas
                if e["a_estado"] == "esperando_postagem"]) == 1


def test_confirmar_dos_veces_sin_clave_no_duplica_la_numeracion():
    """La idempotencia degrada con gracia y puede no estar. La guardia atómica
    sobre el estado tiene que sostener igual: `display_id` es único."""
    base, envio_id = cotizado()
    primera = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base,
                                    ahora=AHORA))
    segunda = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base,
                                    ahora=AHORA))
    assert primera["display_id"] == segunda["display_id"]
    assert primera["tracking_token"] == segunda["tracking_token"]
    assert base.counters.filas[0]["seq"] == 1


def test_una_clave_quemada_por_un_error_no_bloquea_el_reintento():
    """La idempotencia se reclama DESPUÉS de validar. Reclamarla antes convierte
    un 400 por un checkbox sin tildar en una clave que devuelve el mismo error
    para siempre."""
    base, envio_id = cotizado()
    with pytest.raises(crear_mod.NoSePuedeCrear):
        corre(crear_mod.crear(_Usuario(), envio_id,
                              {"contenido_aceptado": True, "estimado_aceptado": False},
                              db=base, ahora=AHORA, idempotency_key="k-2"))
    r = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base,
                              ahora=AHORA, idempotency_key="k-2"))
    assert r["success"] is True


def test_un_envio_ya_confirmado_devuelve_lo_mismo_en_vez_de_un_error():
    """Un reintento de red no puede parecer un fallo cuando salió bien."""
    base, envio_id = cotizado()
    primera = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base,
                                    ahora=AHORA, idempotency_key="k-3"))
    segunda = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base,
                                    ahora=AHORA, idempotency_key="otra"))
    assert segunda["envio_id"] == primera["envio_id"]
    assert segunda["estado"] == "esperando_postagem"


# ─── 4. La cotización tiene que estar viva y ser suya ─────────────────────

def test_una_cotizacion_vencida_no_se_confirma():
    """Confirmar dentro de seis meses un precio de hoy es cobrarle al usuario un
    número que ya no existe."""
    base, envio_id = cotizado()
    with pytest.raises(crear_mod.NoSePuedeCrear) as e:
        corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base,
                              ahora=AHORA + timedelta(hours=49)))
    assert e.value.http == 409 and "venció" in e.value.mensaje


def test_una_cotizacion_que_quedo_a_medias_se_confirma_despues():
    """EL CASO REAL: el usuario cotizó, se fue, y volvió cinco minutos después.

    Pasó de verdad. Cotizar y confirmar vivían los dos en la misma pantalla, y
    si el usuario la cerraba antes de confirmar, el envío quedaba en `cotizado`
    y VIGENTE por 48 horas, pero la pantalla de detalle no ofrecía ninguna
    forma de confirmarlo: sólo «Cotizar de nuevo», que es volver a tipear todo.

    Este test fija que confirmar más tarde funciona, con lo único que la
    pantalla de detalle tiene a mano: el `envio_id` y las dos aceptaciones. Sin
    nada de la sesión anterior, porque esa sesión ya no existe.
    """
    base, envio_id = cotizado()

    r = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base,
                              ahora=AHORA + timedelta(minutes=5)))

    assert r.get("envio_id") == envio_id
    doc = base.envios.filas[0]
    assert doc["estado"] == "esperando_postagem"
    assert doc.get("display_id"), "quedó confirmado sin número de envío"


def test_confirmar_tarde_exige_las_aceptaciones_otra_vez():
    """No se heredan de la sesión en que se cotizó.

    Son el registro que se lee el día que haya que defender un ajuste de
    precio. Darlas por hechas porque «ya las aceptó cuando cotizó» sería anotar
    una aceptación que nadie dio en este momento — y la sesión donde
    supuestamente la dio terminó hace dos días.
    """
    base, envio_id = cotizado()

    with pytest.raises(crear_mod.NoSePuedeCrear) as e:
        corre(crear_mod.crear(_Usuario(), envio_id, {}, db=base,
                              ahora=AHORA + timedelta(minutes=5)))

    assert "aceptar" in e.value.mensaje
    assert base.envios.filas[0]["estado"] == "cotizado"


def test_el_envio_de_otro_usuario_no_existe():
    """El mismo 404 para "no existe" y para "es de otro": distinguirlos convierte
    la ruta en un oráculo que confirma qué identificadores existen."""
    base, envio_id = cotizado()

    class _Otro:
        user_id = "usr_otro"

    with pytest.raises(crear_mod.NoSePuedeCrear) as e:
        corre(crear_mod.crear(_Otro(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))
    assert e.value.http == 404

    with pytest.raises(crear_mod.NoSePuedeCrear) as e2:
        corre(crear_mod.crear(_Usuario(), "env_no_existe", ACEPTA_TODO, db=base,
                              ahora=AHORA))
    assert e2.value.http == 404 and e2.value.mensaje == e.value.mensaje


def test_un_envio_que_ya_avanzo_no_se_puede_confirmar():
    base, envio_id = cotizado()
    base.envios.filas[0]["estado"] = "recibido_pacaraima"
    with pytest.raises(crear_mod.NoSePuedeCrear) as e:
        corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))
    assert e.value.http == 409


# ─── 5. Numeración y token ────────────────────────────────────────────────

def test_el_token_de_seguimiento_no_es_secuencial():
    """Con un número correlativo, cualquiera que reciba un link puede sumarle uno
    y ver el paquete de otra persona: a dónde va, a nombre de quién y con qué
    teléfono."""
    tokens = [crear_mod.nuevo_tracking_token() for _ in range(500)]
    assert len(set(tokens)) == 500
    assert all(len(t) == 32 for t in tokens)          # 128 bits

    # Lo que realmente distingue "aleatorio" de "correlativo": con un contador,
    # los 500 valores caben en un rango de 500. Acá tienen que estar repartidos
    # por todo el espacio.
    numeros = sorted(int(t, 16) for t in tokens)
    espacio = 16 ** 32
    assert numeros[-1] - numeros[0] > espacio // 2
    saltos = [b - a for a, b in zip(numeros, numeros[1:])]
    assert min(saltos) > 1


def test_la_numeracion_visible_es_correlativa_y_atomica():
    base = db_completa()
    numeros = [corre(crear_mod.siguiente_display_id(base)) for _ in range(3)]
    assert numeros == ["E000001", "E000002", "E000003"]


def test_si_el_contador_falla_el_envio_se_crea_igual():
    """Un envío sin `display_id` es incómodo de nombrar por teléfono; un envío que
    no se creó porque un contador falló es un usuario que no puede despachar."""
    base, envio_id = cotizado()

    async def revienta(*a, **k):
        raise RuntimeError("contador caído")
    base.counters.find_one_and_update = revienta

    r = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))
    assert r["success"] is True and r["display_id"] is None
    assert r["tracking_token"]


# ─── 6. La bitácora ───────────────────────────────────────────────────────

def test_confirmar_deja_su_linea_en_la_bitacora():
    base, envio_id = cotizado()
    corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))
    evento = base.envios_eventos.filas[0]
    assert evento["de_estado"] == "cotizado"
    assert evento["a_estado"] == "esperando_postagem"
    assert evento["actor_type"] == "user" and evento["actor_id"] == "usr_ana"
    assert evento["envio_id"] == envio_id


def test_una_bitacora_que_falla_no_deshace_la_confirmacion():
    """Si el paquete pasó a esperando_postagem y la bitácora falla, el paquete
    SIGUE en esperando_postagem. Tirar un error ahí le diría al usuario que su
    confirmación no se guardó cuando sí se guardó."""
    base, envio_id = cotizado()

    async def revienta(*a, **k):
        raise RuntimeError("bitácora caída")
    base.envios_eventos.insert_one = revienta

    r = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))
    assert r["success"] is True
    assert base.envios.filas[0]["estado"] == "esperando_postagem"


# ─── 7. Los límites se revalidan ──────────────────────────────────────────

def test_si_los_limites_se_endurecieron_no_se_confirma():
    """Entre cotizar y confirmar pueden haber cambiado. Despachar algo que el
    mostrador va a rechazar es peor que un 409 acá."""
    base, envio_id = cotizado()
    base.transportistas.filas[0]["limites"]["peso_max_kg"] = 1
    with pytest.raises(crear_mod.NoSePuedeCrear) as e:
        corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))
    assert e.value.http == 409 and "cambiaron" in e.value.mensaje


def test_un_catalogo_incompleto_al_confirmar_no_bloquea_al_usuario():
    """El paquete ya fue validado al cotizar contra la intersección completa.
    Bloquear acá por un fallo nuestro le impide despachar a alguien que hizo todo
    bien — que es distinto de cotizar, donde todavía no hay nada comprometido."""
    base, envio_id = cotizado()
    original = base.transportistas.find

    def a_medias(filtro=None, proyeccion=None):
        if (filtro or {}).get("rol") == "brasil":
            raise RuntimeError("failover")
        return original(filtro, proyeccion)
    base.transportistas.find = a_medias

    r = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))
    assert r["success"] is True


# ─── 8. Lo que se le entrega al usuario ───────────────────────────────────

def test_se_entrega_la_direccion_congelada_y_no_la_vigente():
    """Entre cotizar y confirmar pueden haber cambiado el turno de la nómina, y
    la etiqueta tiene que decir lo mismo que dijo cuando el usuario la leyó."""
    base, envio_id = cotizado()
    base.colaboradores_retiro.filas[0]["activo"] = False       # cambia el turno
    r = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))
    assert "María Gómez" in r["retiro"]["texto_copiable"]


def test_al_usuario_no_le_llegan_los_datos_internos_del_retirador():
    base, envio_id = cotizado()
    r = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))
    assert "retirador_id" not in r["retiro"]
    assert "retirador_motivo" not in r["retiro"]
    assert MARIA["cpf"] not in repr(r)


def test_se_dice_que_no_se_cobro_nada_y_cual_es_el_proximo_paso():
    base, envio_id = cotizado()
    r = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))
    assert r["cobrado_ahora_ris"] == "0.00"
    assert "comprobante" in r["proximo_paso"]
    assert Decimal(r["total_estimado_ris"]) > 0
    assert r["es_estimado"] is True


def test_el_modulo_no_menciona_ninguna_marca():
    for archivo in ("envios_crear.py", "envios_eventos.py"):
        fuente = open(os.path.join(_BACKEND, "services", archivo),
                      encoding="utf-8").read().lower()
        for marca in ("mrw", "correios", "zoom", "tealca", "domesa"):
            assert marca not in fuente, archivo


# ─── 9. Las carreras ──────────────────────────────────────────────────────

def test_dos_confirmaciones_simultaneas_confirman_una_sola_vez():
    """La guardia va EN EL FILTRO del update, no solo en el chequeo de arriba.
    Entre que se lee el envío y que se escribe, otra petición pudo confirmarlo:
    sin el estado en el filtro, la segunda pisa la primera y se lleva puesto el
    `display_id` y el token que ya se le habían entregado al usuario.

    Se simula con una lectura RANCIA, que es exactamente lo que ve la segunda
    petición de un doble clic: el documento como estaba antes del primer update.
    """
    base, envio_id = cotizado()
    primera = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base,
                                    ahora=AHORA))

    rancio = dict(base.envios.filas[0])
    rancio["estado"] = "cotizado"
    rancio.pop("display_id", None)
    rancio.pop("tracking_token", None)

    original = base.envios.find_one

    async def lectura_rancia(filtro, proyeccion=None):
        base.envios.find_one = original          # solo la primera lectura
        return dict(rancio)
    base.envios.find_one = lectura_rancia

    despues = AHORA + timedelta(minutes=5)
    segunda = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base,
                                    ahora=despues))

    assert segunda["display_id"] == primera["display_id"]
    assert segunda["tracking_token"] == primera["tracking_token"]
    assert base.counters.filas[0]["seq"] == 1

    # Y lo que más importa: la segunda no pisa el registro de la primera. El
    # momento en que el usuario aceptó las condiciones es lo que se lee el día
    # que haya que defender un cobro; reescribirlo con la hora de un reintento de
    # red lo vuelve inservible, y sin la guardia en el filtro eso pasa en
    # silencio.
    guardado = base.envios.filas[0]
    assert guardado["confirmado_at"] == AHORA
    assert guardado["declaracion"]["at"] == AHORA
    assert len(base.envios_eventos.filas) == 1


def test_una_confirmacion_todavia_en_vuelo_no_se_duplica():
    """La clave está reclamada pero la operación no terminó: no hay resultado que
    devolver todavía. Contestar un 200 vacío ahí le diría al usuario que su envío
    está confirmado cuando puede no estarlo."""
    base, envio_id = cotizado()
    corre(idem.claim_idempotency("usr_ana",
                                 crear_mod.accion_idempotencia(envio_id),
                                 "k-vuelo"))

    with pytest.raises(crear_mod.NoSePuedeCrear) as e:
        corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base,
                              ahora=AHORA, idempotency_key="k-vuelo"))
    assert e.value.http == 409 and "procesando" in e.value.mensaje
    assert base.envios.filas[0]["estado"] == "cotizado"


def test_la_bitacora_avisa_cuando_no_pudo_escribir():
    """Devolver un evento_id que no existe convierte un fallo en un éxito
    aparente. El que llama tiene que poder saberlo aunque hoy no lo mire."""
    eventos = _cargar("envios_eventos")
    base = db_completa()

    async def revienta(*a, **k):
        raise RuntimeError("caída")
    base.envios_eventos.insert_one = revienta

    assert corre(eventos.registrar({"envio_id": "env_x"}, "a", "b", "system",
                                   db=base)) is None

    base2 = db_completa()
    assert corre(eventos.registrar({"envio_id": "env_x"}, "a", "b", "system",
                                   db=base2)).startswith("eve_")


def test_el_historial_de_un_envio_sale_en_orden():
    base, envio_id = cotizado()
    corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))
    eventos = _cargar("envios_eventos")
    filas = corre(eventos.historial(envio_id, db=base))
    assert [f["a_estado"] for f in filas] == ["esperando_postagem"]


# ─── 10. Lo que encontro la revision adversarial ──────────────────────────

def test_la_misma_clave_para_dos_envios_no_devuelve_el_envio_equivocado():
    """EL DEFECTO P0. La clave se reclama por (user_id, accion, key), y con una
    accion fija dos envios distintos colisionan: el segundo devuelve el resultado
    del primero —otro envio_id, otro display_id, otro token— con un 200.

    No hace falta un cliente malicioso: alcanza un `useRef(uuid())` creado al
    montar la app. Y el daño no queda ahí. El segundo envío se queda en
    `cotizado`, el TTL lo borra a las 48 h, y el usuario —que recibió un 200—
    despacha esa caja y después carga el comprobante contra el display_id que le
    dieron, que es el del PRIMER envío. Ahí sí se mueve plata mal: el cobro
    inicial de uno se calcula con el peso del despacho del otro.
    """
    base, primero = cotizado()
    corre(cot.cotizar(_Usuario(), pedido(paquete={"peso_kg": "4.10"}),
                      db=base, ahora=AHORA))
    segundo = base.envios.filas[1]["envio_id"]
    assert primero != segundo

    a = corre(crear_mod.crear(_Usuario(), primero, ACEPTA_TODO, db=base,
                              ahora=AHORA, idempotency_key="K"))
    b = corre(crear_mod.crear(_Usuario(), segundo, ACEPTA_TODO, db=base,
                              ahora=AHORA, idempotency_key="K"))

    assert b["envio_id"] == segundo
    assert b["display_id"] != a["display_id"]
    assert b["tracking_token"] != a["tracking_token"]
    estados = {e["envio_id"]: e["estado"] for e in base.envios.filas}
    assert estados[primero] == estados[segundo] == "esperando_postagem"


def test_un_fallo_de_mongo_no_quema_la_clave_para_siempre():
    """El 503 invita a reintentar y un cliente bien hecho reintenta con la misma
    clave. Sin liberarla, la operación nunca ocurrió pero la clave queda en
    `processing` para siempre —no hay TTL en `idempotency_keys`— y el reintento
    devuelve 409 hasta que el envío vence."""
    base, envio_id = cotizado()
    original = base.envios.find_one_and_update

    async def revienta(*a, **k):
        base.envios.find_one_and_update = original     # solo el primer intento
        raise RuntimeError("timeout")
    base.envios.find_one_and_update = revienta

    with pytest.raises(crear_mod.NoSePuedeCrear) as e:
        corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base,
                              ahora=AHORA, idempotency_key="K2"))
    assert e.value.http == 503
    assert base.envios.filas[0]["estado"] == "cotizado"

    r = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base,
                              ahora=AHORA, idempotency_key="K2"))
    assert r["success"] is True


def test_el_segundo_clic_nunca_devuelve_un_envio_sin_numero():
    """La transición y la numeración son dos escrituras. Entre una y otra hay una
    ventana en la que el documento ya está confirmado y todavía no tiene número:
    el segundo clic salía por ahí y devolvía `display_id: null` con
    `success: true`, y la pantalla se quedaba sin número ni link de seguimiento."""
    base, envio_id = cotizado()
    # Se simula justo esa ventana: confirmado, sin numerar.
    base.envios.filas[0]["estado"] = "esperando_postagem"

    r = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))
    assert r["display_id"] and r["tracking_token"]
    assert base.envios.filas[0]["display_id"] == r["display_id"]


def test_una_agencia_dada_de_baja_frena_la_confirmacion():
    """El panel da de baja la agencia de Caracas, el usuario confirma, paga el
    tramo 1 de su bolsillo, y la caja llega a Pacaraima con destino a un mostrador
    que ya no recibe. Es el caso que la revalidación existe para prevenir."""
    base, envio_id = cotizado()
    base.agencias.filas[0]["activa"] = False
    with pytest.raises(crear_mod.NoSePuedeCrear) as e:
        corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))
    assert e.value.http == 409 and "recibiendo" in e.value.mensaje


def test_un_transportista_de_destino_dado_de_baja_frena_la_confirmacion():
    """Y este es el peor de los dos: `limites_efectivos` descarta las fichas
    inactivas, así que dar de baja un transportista SACABA sus límites de la
    intersección — la revalidación se volvía más laxa justo cuando algo se había
    roto."""
    base, envio_id = cotizado()
    base.transportistas.filas[1]["activo"] = False
    with pytest.raises(crear_mod.NoSePuedeCrear) as e:
        corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base, ahora=AHORA))
    assert e.value.http == 409 and "disponible" in e.value.mensaje


@pytest.mark.parametrize("valor", ["on", "true", "yes", "t", "1", 1, 1.0])
def test_el_modelo_no_acepta_un_checkbox_improvisado(valor):
    """Pydantic coacciona "on", "true", "yes" y 1 a True. Un checkbox tildado
    manda `true`; cualquier otra cosa es un cliente improvisando, y esto es lo
    que se lee el día que haya que defender un cobro."""
    with pytest.raises(Exception):
        Declaracion(contenido_aceptado=valor, estimado_aceptado=True)
    assert Declaracion(contenido_aceptado=True,
                       estimado_aceptado=True).contenido_aceptado is True


def test_si_la_pantalla_mostro_otros_terminos_no_se_confirma():
    """El usuario aceptó un texto distinto del que el envío dice que aceptó, y
    "aceptaste las condiciones" deja de sostenerse justo cuando hace falta."""
    base, envio_id = cotizado()
    with pytest.raises(crear_mod.NoSePuedeCrear) as e:
        corre(crear_mod.crear(_Usuario(), envio_id,
                              {**ACEPTA_TODO, "terminos_version": "envios-v9"},
                              db=base, ahora=AHORA))
    assert e.value.http == 409 and "condiciones cambiaron" in e.value.mensaje

    r = corre(crear_mod.crear(_Usuario(), envio_id,
                              {**ACEPTA_TODO, "terminos_version": "envios-v1"},
                              db=base, ahora=AHORA))
    assert r["success"] is True


def test_el_identificador_de_evento_no_se_recorta():
    """Con el índice único, una colisión no produce una fila duplicada: produce
    un E11000 que se atrapa y se convierte en None. O sea, una línea de bitácora
    que se pierde en silencio, en la colección que existe para poder contestar
    qué pasó."""
    eventos = _cargar("envios_eventos")
    base = db_completa()
    corre(eventos.registrar({"envio_id": "env_x"}, "a", "b", "system", db=base))
    evento_id = base.envios_eventos.filas[0]["evento_id"]
    assert len(evento_id) == len("eve_") + 32


def test_la_ip_que_se_guarda_es_la_del_usuario_y_no_la_del_proxy():
    """Detrás del edge, `request.client.host` es la misma para todos. El campo
    existe únicamente para el argumento legal que motiva la doble aceptación: una
    IP idéntica para todo el mundo no distingue a nadie.

    ESTE TEST PEDIA EL PRIMER VALOR DE X-FORWARDED-FOR, Y ESO ERA EL BUG

        Con la cabecera «200.1.2.3, 10.0.0.1» esperaba «200.1.2.3». Pero esa
        cabecera se arma por acumulación: cada proxy le AGREGA al final la IP de
        quien le habló. El primer valor no es el cliente, es lo que el cliente
        escribió. Cuando la cadena trae dos valores y adelante hay un solo proxy,
        el primero lo puso el cliente a mano.

        Ahora se lee de derecha a izquierda y el bueno es «10.0.0.1», que lo
        escribió el proxy y no se puede falsear desde afuera.

    Se prueba la FUNCIÓN, no el texto del archivo: un grep del nombre del helper
    pasa igual si adentro se sigue leyendo `request.client`."""
    ip_real = _funcion_de_ruta("_ip_real")

    class _Pedido:
        headers = {"x-forwarded-for": "200.1.2.3, 10.0.0.1"}

        class client:
            host = "10.0.0.7"          # el edge

    assert ip_real(_Pedido()) == "10.0.0.1"

    class _Directo:
        headers = {}

        class client:
            host = "190.9.9.9"

    assert ip_real(_Directo()) == "190.9.9.9"


def test_UNA_IP_ESCRITA_A_MANO_NO_QUEDA_ASENTADA_EN_EL_ENVIO():
    """El caso del atacante, escrito tal cual llega al servidor.

    Quien manda `X-Forwarded-For: 1.2.3.4` no borra nada: el proxy le agrega su
    IP real AL FINAL. Lo que la aplicación ve es «1.2.3.4, 200.5.5.5» y lo que
    tiene que dejar asentado es 200.5.5.5. Guardar la otra convierte el único
    dato con el que se puede rastrear un envío en un campo de texto libre.
    """
    ip_real = _funcion_de_ruta("_ip_real")

    class _Falseado:
        headers = {"x-forwarded-for": "1.2.3.4, 200.5.5.5"}

        class client:
            host = "10.0.0.7"

    assert ip_real(_Falseado()) == "200.5.5.5", \
        "asentó la IP que eligió quien hizo el pedido"


def test_lo_que_escribe_cloudflare_le_gana_a_lo_que_diga_el_cliente():
    """`CF-Connecting-IP` la pone Cloudflare PISANDO lo que venga del cliente:
    es la única de las tres que no se puede tocar desde afuera, así que gana."""
    ip_real = _funcion_de_ruta("_ip_real")

    class _ConCF:
        headers = {"cf-connecting-ip": "200.7.7.7",
                   "x-forwarded-for": "1.2.3.4, 10.0.0.1"}

        class client:
            host = "10.0.0.7"

    assert ip_real(_ConCF()) == "200.7.7.7"


def test_el_criterio_de_ip_es_el_mismo_que_el_del_resto_de_la_app():
    """ESTE TEST DEFENDIA EL BUG, Y VALE LA PENA DEJARLO ESCRITO

        Ataba `_ip_real` al TEXTO de `get_real_client_ip`: leía el archivo de
        `security_2fa.py` y exigía que ahí adentro apareciera `split(",")[0]`.
        La intención era buena —que los dos criterios no se separaran— pero el
        efecto fue que arreglar la resolución de IP ponía el test en rojo. Un
        test que se pone en rojo cuando se cierra un agujero es un test que
        empuja a no cerrarlo.

        Se compara por COMPORTAMIENTO, sobre los mismos pedidos. Es lo que
        importaba desde el principio: que la IP con la que se frena a alguien y
        la que se asienta en el envío sean la misma, sin importar cómo esté
        escrita cada una.
    """
    ip_real = _funcion_de_ruta("_ip_real")
    from services.ip_cliente import ip_del_cliente

    casos = ["200.1.2.3, 10.0.0.1", "  8.8.8.8  ", "1.1.1.1,2.2.2.2,3.3.3.3",
             "", "1.2.3.4, , 10.0.0.1"]
    for cadena in casos:
        class _P:
            headers = {"x-forwarded-for": cadena}

            class client:
                host = "10.0.0.7"
        assert ip_real(_P()) == ip_del_cliente(_P()), cadena

    # Y el criterio explícito, para que este test diga CUAL es y no sólo que los
    # dos coinciden: con un proxy de confianza adelante, el último de la cadena.
    class _Cadena:
        headers = {"x-forwarded-for": "1.1.1.1,2.2.2.2,3.3.3.3"}

        class client:
            host = "10.0.0.7"

    assert ip_real(_Cadena()) == "3.3.3.3"


def _funcion_de_ruta(nombre):
    """Carga `routes/envios.py` aislado, con el paquete `routes` vacío."""
    import importlib.util
    if "routes" not in sys.modules:
        paquete = types.ModuleType("routes")
        paquete.__path__ = [os.path.join(_BACKEND, "routes")]
        sys.modules["routes"] = paquete
    if "routes.dependencies" not in sys.modules:
        deps = types.ModuleType("routes.dependencies")
        for dep in ("get_current_user", "get_verified_user"):
            setattr(deps, dep, (lambda: None))
        sys.modules["routes.dependencies"] = deps
    if "routes.envios" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "routes.envios", os.path.join(_BACKEND, "routes", "envios.py"))
        modulo = importlib.util.module_from_spec(spec)
        sys.modules["routes.envios"] = modulo
        spec.loader.exec_module(modulo)
    return getattr(sys.modules["routes.envios"], nombre)


def test_la_relectura_de_limites_no_se_queda_con_el_worker():
    """Con un failover, tres lecturas en serie y sin cota son tres veces el
    server-selection timeout reteniendo un worker. Se mide el TIEMPO y no solo el
    resultado: sin el tope la confirmación igual sale bien, solo que treinta
    segundos después, y un test que mira nada más el resultado no lo ve."""
    import time
    base, envio_id = cotizado()

    def cuelga(*a, **k):
        class _C:
            def sort(self, *a, **k):
                return self

            async def to_list(self, n):
                await asyncio.sleep(5)
        return _C()
    base.transportistas.find = cuelga

    crear_mod.TIMEOUT_RELECTURA_S = 0.2
    try:
        arranco = time.monotonic()
        r = corre(crear_mod.crear(_Usuario(), envio_id, ACEPTA_TODO, db=base,
                                  ahora=AHORA))
        tardo = time.monotonic() - arranco
    finally:
        crear_mod.TIMEOUT_RELECTURA_S = 6.0

    # No bloquea al usuario: el paquete ya se validó al cotizar y el fallo es
    # nuestro. Pero tampoco se queda esperando.
    assert r["success"] is True
    assert tardo < 2, f"la confirmación tardó {tardo:.1f}s: no hay tope"
