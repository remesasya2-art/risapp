"""
El seguimiento publico y los avisos.

EL RIESGO QUE ORGANIZA ESTE ARCHIVO
    El link de seguimiento se comparte por WhatsApp: al destinatario, a la
    familia, al grupo. Va a terminar en manos que no son la del usuario, y hay
    que disenarlo asumiendo eso desde el principio y no despues del primer
    incidente.

    Por eso el test central toma un envio COMPLETO —con nombre, documento,
    telefono, direccion y montos— arma el payload publico y busca cada uno de
    esos datos adentro. Es la unica forma de que esto siga siendo cierto dentro
    de un ano: una clave nueva en el documento del envio no puede aparecer sola
    en la respuesta publica.

QUE SE CUBRE
    1. El payload publico no lleva un solo dato personal.
    2. Un token inexistente y uno mal formado dan la misma respuesta.
    3. La linea de tiempo sale en orden y recortada.
    4. No se avisa por cada movimiento interno.
    5. Un aviso que falla no deshace el movimiento que lo produjo.
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
        # Con NOTACION DE PUNTO, como la base de verdad: `{"destino.ciudad": 1}`
        # trae ese campo y no el bloque entero. Un doble que solo entiende claves
        # de primer nivel deja pasar una proyeccion que en produccion recorta, y
        # al reves — que es peor: hace fallar un test que en produccion pasa.
        salida = {}
        for clave in incluir:
            partes = clave.split(".")
            actual, destino = doc, salida
            for parte in partes[:-1]:
                if not isinstance(actual, dict) or parte not in actual:
                    actual = None
                    break
                actual = actual[parte]
                destino = destino.setdefault(parte, {})
            if actual is None or not isinstance(actual, dict):
                continue
            if partes[-1] in actual:
                destino[partes[-1]] = copy.deepcopy(actual[partes[-1]])
        return salida
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
            if isinstance(v, dict) and "$gte" in v:
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
seg = _cargar("envios_seguimiento")


def corre(coro):
    return asyncio.run(coro)


AHORA = datetime.now(timezone.utc)

TOKEN = "9f2c" + "a" * 28

# Un envio COMPLETO, con todo lo sensible adentro. El test central busca cada uno
# de estos valores en el payload publico; un fixture pobre haria pasar cualquier
# implementacion.
SENSIBLES = {
    "nombre": "Ana Pérez González",
    "documento": "V-12345678",
    "telefono": "+58 412 1234567",
    "email": "ana@example.com",
    "cep": "01310100",
    "direccion": "Caixa Postal 123",
    "retirador": "María Gómez",
    "monto": "132.00",
    "user_id": "usr_ana",
    "envio_id": "env_aaa111",
    "codigo_objeto": "AA123456789BR",
}

ENVIO = {
    "envio_id": "env_aaa111", "display_id": "E000123", "user_id": "usr_ana",
    "estado": "en_transito_int", "tracking_token": TOKEN,
    "created_at": AHORA - timedelta(days=5),
    "origen": {"cep": "01310100", "ciudad": "São Paulo", "uf": "SP",
               "codigo_objeto": "AA123456789BR"},
    "destino_brasil": {"retirador_nombre": "María Gómez",
                       "texto_copiable": "RIS App LTDA\nA/C María Gómez\n"
                                         "Caixa Postal 123"},
    "destino": {
        "ciudad": "Caracas", "estado_ve": "Miranda", "agencia_nombre": "Centro",
        "destinatario": {"nombre": "Ana Pérez González", "documento": "V-12345678",
                         "telefono": "+58 412 1234567"},
    },
    "paquete": {"declarado": {"peso_kg": "2.30"},
                "contenido_descripcion": "Ropa y artículos de higiene"},
    "cotizacion": {"total_estimado_ris": "132.00", "tarifa_version": "tar_x"},
    "cobros": {"inicial": {"monto_ris": "132.00", "estado": "pagado"}},
    "entrega": {"guia": "GUIA-99887"},
}

EVENTOS = [
    {"envio_id": "env_aaa111", "a_estado": "esperando_postagem",
     "created_at": AHORA - timedelta(days=5), "detalle": {"terminos_version": "v1"}},
    {"envio_id": "env_aaa111", "a_estado": "en_transito_origen",
     "created_at": AHORA - timedelta(days=4),
     "detalle": {"codigo_objeto": "AA123456789BR"}},
    {"envio_id": "env_aaa111", "a_estado": "recibido_pacaraima",
     "created_at": AHORA - timedelta(days=1),
     "detalle": {"lote_retiro_id": "lot_x"}},
    {"envio_id": "env_aaa111", "a_estado": "en_transito_int",
     "created_at": AHORA, "detalle": {"monto_ris": "132.00"}},
]


def db_completa(envio=None, eventos=None):
    import copy
    base = _Db(
        envios=copy.deepcopy([envio or ENVIO]),
        envios_eventos=copy.deepcopy(eventos if eventos is not None else EVENTOS),
        notifications=[], users=[{"user_id": "usr_ana", "email": "ana@example.com"}],
    )
    usar_base(base)
    return base


# ─── 1. El payload público no lleva nada personal ─────────────────────────

def test_el_seguimiento_no_filtra_un_solo_dato_personal():
    """EL TEST CENTRAL. El link se comparte por WhatsApp y va a terminar en manos
    que no son la del usuario."""
    base = db_completa()
    r = corre(seg.seguir(TOKEN, db=base))
    plano = repr(r)
    for nombre, valor in SENSIBLES.items():
        if nombre in ("monto",):
            assert valor not in plano, f"se filtró el {nombre}"
        else:
            assert valor not in plano, f"se filtró el {nombre}: {valor}"


def test_el_seguimiento_no_lleva_el_token_de_vuelta():
    """Devolverlo lo pone en cualquier captura de pantalla del seguimiento."""
    base = db_completa()
    assert TOKEN not in repr(corre(seg.seguir(TOKEN, db=base)))


def test_el_seguimiento_contesta_lo_que_la_pantalla_pregunta():
    base = db_completa()
    r = corre(seg.seguir(TOKEN, db=base))
    assert r["display_id"] == "E000123"
    assert r["estado"] == "en_transito_int"
    assert "oficina del transportista" in r["estado_detalle"]
    assert r["destino"] == {"ciudad": "Caracas", "estado": "Miranda"}
    assert r["guia_transportista"] == "GUIA-99887"


def test_la_proyeccion_es_una_lista_blanca():
    """Con una exclusión, cada campo nuevo del envío entra solo a la respuesta
    pública el día que alguien lo agregue."""
    base = db_completa()
    proyecciones = []
    original = base.envios.find_one

    async def espiar(filtro, proyeccion=None):
        proyecciones.append(proyeccion)
        return await original(filtro, proyeccion)
    base.envios.find_one = espiar

    corre(seg.seguir(TOKEN, db=base))
    proyeccion = proyecciones[0]
    incluidos = {k: v for k, v in proyeccion.items() if k != "_id"}
    assert incluidos, "una proyección sin campos incluidos es una exclusión"
    assert all(v == 1 for v in incluidos.values())
    # Y los campos sensibles no están en la lista, ni siquiera anidados.
    assert not any(k.startswith(("destino.destinatario", "paquete", "cobros",
                                "cotizacion", "destino_brasil", "origen"))
                   for k in incluidos)


def test_un_campo_nuevo_en_el_envio_no_aparece_solo_en_el_seguimiento():
    envio = {**ENVIO, "notas_internas": "el usuario llamó tres veces",
             "margen_real_ris": "22.00"}
    base = db_completa(envio=envio)
    plano = repr(corre(seg.seguir(TOKEN, db=base)))
    assert "llamó tres veces" not in plano and "22.00" not in plano


# ─── 2. El token es una credencial ────────────────────────────────────────

@pytest.mark.parametrize("token", ["", "corto", "no-alfanumerico!" * 3,
                                   "z" * 200, None, "9f2c" + "a" * 28 + "x"])
def test_un_token_invalido_da_la_misma_respuesta_que_uno_inexistente(token):
    """Distinguirlos convierte la ruta en un oráculo para adivinar tokens."""
    base = db_completa()
    assert corre(seg.seguir(token, db=base)) is None


def test_un_token_con_forma_imposible_ni_llega_a_la_base():
    """Un token es una credencial de 128 bits en hexadecimal. Mandar a la base
    cualquier cosa que llegue por la URL es abrirle una consulta a quien quiera,
    sobre una ruta pública y sin sesión."""
    base = db_completa()
    consultas = []
    original = base.envios.find_one

    async def espiar(filtro, proyeccion=None):
        consultas.append(filtro)
        return await original(filtro, proyeccion)
    base.envios.find_one = espiar

    for malo in ("", "x", "z" * 500, "../../etc", "' or 1=1", None):
        assert corre(seg.seguir(malo, db=base)) is None
    assert consultas == [], "ninguno de esos tendría que haber llegado a la base"


def test_un_token_que_no_existe_no_dice_nada():
    base = db_completa()
    assert corre(seg.seguir("b" * 32, db=base)) is None


def test_si_la_base_falla_el_seguimiento_no_revienta():
    base = db_completa()
    base.envios.find_one = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    assert corre(seg.seguir(TOKEN, db=base)) is None


# ─── 3. La línea de tiempo ────────────────────────────────────────────────

def test_la_linea_de_tiempo_sale_en_orden():
    base = db_completa()
    r = corre(seg.seguir(TOKEN, db=base))
    assert [e["estado"] for e in r["timeline"]] == [
        "esperando_postagem", "en_transito_origen", "recibido_pacaraima",
        "en_transito_int"]
    fechas = [e["at"] for e in r["timeline"]]
    assert fechas == sorted(fechas)


def test_la_linea_de_tiempo_no_lleva_el_detalle_interno():
    """Cada evento tiene códigos de objeto, montos y quién lo movió."""
    base = db_completa()
    r = corre(seg.seguir(TOKEN, db=base))
    plano = repr(r["timeline"])
    assert "AA123456789BR" not in plano
    assert "lot_x" not in plano and "132.00" not in plano
    assert all(set(e) == {"estado", "titulo", "detalle", "at"} for e in r["timeline"])


def test_cada_estado_publico_se_dice_con_palabras():
    """"recibido_pacaraima" no le dice nada a nadie."""
    for estado, (titulo, detalle) in seg.PUBLICO.items():
        assert titulo and titulo[0].isupper()
        assert "_" not in titulo


def test_todos_los_estados_del_sistema_tienen_texto_publico():
    """Un estado sin texto se muestra como "En proceso", que es peor que nada
    cuando el paquete está retenido."""
    estados = _cargar("envios_estados").ESTADOS
    faltan = set(estados) - set(seg.PUBLICO)
    assert faltan == set()


# ─── 4. Los avisos ────────────────────────────────────────────────────────

def test_no_se_avisa_por_cada_movimiento_interno():
    """Un aviso por cada movimiento entrena al usuario a ignorarlos, y después el
    único que importaba —tenés un cobro pendiente— llega a alguien que ya no los
    lee."""
    assert seg.se_avisa("pago_pendiente") is True
    assert seg.se_avisa("entregado_transportista") is True
    assert seg.se_avisa("repesado") is False
    assert seg.se_avisa("cotizado") is False

    # Y `avisar` respeta esa decisión: no alcanza con que la función lo diga.
    base = db_completa()
    assert corre(seg.avisar(ENVIO, "repesado", db=base)) is None
    assert corre(seg.avisar(ENVIO, "cotizado", db=base)) is None
    assert base.notifications.filas == []


def test_el_aviso_no_lleva_el_token_de_seguimiento():
    """Un aviso se reenvía y se captura de pantalla. El link de seguimiento es una
    credencial y vive detrás de la sesión."""
    base = db_completa()
    corre(seg.avisar(ENVIO, "en_transito_int", db=base))
    assert TOKEN not in repr(base.notifications.filas)


def test_el_aviso_dice_de_que_envio_habla():
    base = db_completa()
    corre(seg.avisar(ENVIO, "pago_pendiente", db=base))
    aviso = base.notifications.filas[0]
    assert "E000123" in aviso["message"]
    assert aviso["user_id"] == "usr_ana"
    assert "cobro pendiente" in aviso["message"]


def test_un_aviso_que_falla_no_deshace_nada():
    """El paquete ya está donde está, y un aviso que falla no lo devuelve."""
    base = db_completa()
    base.notifications.insert_one = lambda *a, **k: (
        _ for _ in ()).throw(RuntimeError("caído"))
    assert corre(seg.avisar(ENVIO, "en_transito_int", db=base)) is None


def test_un_envio_sin_usuario_no_rompe_el_aviso():
    base = db_completa()
    assert corre(seg.avisar({"display_id": "E1"}, "en_transito_int", db=base)) is None


def test_el_operador_avisa_al_mover_el_paquete():
    """El aviso va al final del movimiento, no en una tarea aparte que alguien se
    olvide de disparar."""
    fuente = open(os.path.join(_BACKEND, "services", "envios_operacion.py"),
                  encoding="utf-8").read()
    cuerpo = fuente[fuente.index("async def _mover("):]
    assert "envios_seguimiento.avisar" in cuerpo


def test_el_modulo_no_menciona_ninguna_marca():
    fuente = open(os.path.join(_BACKEND, "services", "envios_seguimiento.py"),
                  encoding="utf-8").read().lower()
    for marca in ("mrw", "correios", "zoom", "tealca", "domesa"):
        assert marca not in fuente
