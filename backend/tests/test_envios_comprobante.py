"""
El comprobante: el usuario avisa que despacho, el operador verifica.

CONTEXTO
    No hay API de rastreo. Sin contrato con el transportista de origen, el
    sistema no tiene forma de enterarse solo de que un paquete se despacho: el
    unico que lo sabe es el usuario, que tiene el comprobante en la mano.

CARGAR NO ES VERIFICAR, Y ES POR PLATA
    El cobro inicial se calcula con el PESO QUE FIGURA EN EL COMPROBANTE. Si ese
    numero lo tipeara el usuario y se cobrara sin mirar, cualquiera escribiria
    0,1 kg. Por eso son dos pasos: el usuario carga (no se cobra nada) y el
    operador verifica mirando la foto (ahi se emite el cobro).

QUE SE CUBRE
    1. Cargar no mueve un centavo; verificar si.
    2. El tipo del archivo se mira en los BYTES, no en el nombre ni en el
       content-type: los dos los elige quien sube.
    3. El EXIF se borra: una foto de telefono lleva las coordenadas de donde se
       saco, y el comprobante de un envio no tiene por que registrar la casa de
       nadie.
    4. Un codigo de objeto no puede estar en dos envios: serian dos cobros sobre
       un solo despacho.
    5. Una foto no se puede leer desde otro envio.

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

ENVIO = {
    "envio_id": "env_aaa111", "display_id": "E000001", "user_id": "usr_ana",
    "estado": "esperando_postagem",
    "paquete": {
        "declarado": {"peso_kg": "2.30", "largo_cm": "40", "ancho_cm": "30",
                      "alto_cm": "20", "valor_declarado": "180.00"},
        "bultos": 1,
    },
    "cotizacion": {"tarifa_version": "tar_2026_08_a", "fecha": "2026-08-30",
                   "total_estimado_ris": "132.00", "moneda": "RIS"},
    "cobros": {"inicial": None, "ajuste": None,
               "reembolsado_ris": "0.00", "total_cobrado_ris": "0.00"},
    "origen": {},
}


class _Usuario:
    user_id = "usr_ana"


class _Operador:
    user_id = "usr_operador"


# Un JPEG de verdad y con EXIF adentro: es lo unico que prueba que el EXIF se
# borra. Un jpg falso de tres bytes no tiene nada que borrar, y un test sobre eso
# pasaria con la limpieza desconectada.
def _jpeg(ancho=16, alto=12, color=(200, 30, 30)):
    from PIL import Image
    imagen = Image.new("RGB", (ancho, alto), color)
    salida = io.BytesIO()
    exif = Image.Exif()
    exif[0x010F] = "ACME Phone"          # Make
    exif[0x0110] = "Modelo X"            # Model
    imagen.save(salida, format="JPEG", exif=exif)
    return salida.getvalue()


def db_completa(saldo="500.00", envio=None):
    import copy
    base = _Db(
        envios=[copy.deepcopy(envio or ENVIO)],
        tarifas_envio=copy.deepcopy([TARIFA]),
        users=[{"user_id": "usr_ana", "balance_ris": Decimal128(Decimal(saldo))}],
        ledger=[], idempotency_keys=[], envios_eventos=[], envios_archivos=[],
    )
    usar_base(base)
    idem._idem_indexes_ready = True
    ledger._indexes_ready = True
    return base


def envio_de(base) -> dict:
    return base.envios.filas[0]


def saldo_de(base) -> Decimal:
    return _num(base.users.filas[0]["balance_ris"])


CODIGO = "AA123456789BR"


# RELATIVA al reloj, no fija. Con "2026-08-29" escrito a mano y un limite de
# sesenta dias hacia atras, toda la suite de este archivo empezaba a fallar el
# 28 de octubre de 2026 — y el fallo no habria dicho "el test tiene una fecha
# vieja", habria dicho "el comprobante tiene mas de 60 dias".
AYER = (AHORA - timedelta(days=1)).date().isoformat()
ANTEAYER = (AHORA - timedelta(days=2)).date().isoformat()


def cargar(base, **cambios):
    datos = {"codigo_objeto": CODIGO, "posteado_at": AYER, "foto": _jpeg()}
    datos.update(cambios)
    return corre(comp.cargar(_Usuario(), "env_aaa111", db=base, ahora=AHORA, **datos))


# ─── 1. Cargar no cobra ───────────────────────────────────────────────────

def test_cargar_el_comprobante_no_mueve_un_centavo():
    """El peso todavía no lo miró nadie de este lado. Cobrar acá sería cobrar
    contra un número que tipeó el usuario."""
    base = db_completa()
    r = cargar(base)
    assert r["ok"] is True
    assert saldo_de(base) == Decimal("500.00")
    assert envio_de(base)["cobros"]["inicial"] is None
    assert base.ledger.filas == []


def test_cargar_mueve_el_envio_y_deja_su_linea_en_la_bitacora():
    base = db_completa()
    cargar(base)
    assert envio_de(base)["estado"] == "en_transito_origen"
    evento = base.envios_eventos.filas[-1]
    assert evento["a_estado"] == "en_transito_origen"
    assert evento["actor_type"] == "user"
    assert evento["detalle"]["codigo_objeto"] == CODIGO


def test_el_comprobante_queda_guardado_con_su_foto():
    base = db_completa()
    cargar(base)
    origen = envio_de(base)["origen"]
    assert origen["codigo_objeto"] == CODIGO
    assert origen["comprobante_asset_id"].startswith("ast_")
    assert origen["verificado"] is None
    ficha = base.envios_archivos.filas[0]
    assert ficha["clase"] == "comprobante" and ficha["content_type"] == "image/jpeg"


def test_cargar_dos_veces_no_rompe():
    """Un reintento de red no puede parecer un fallo cuando salió bien."""
    base = db_completa()
    primera = cargar(base)
    segunda = cargar(base)
    assert primera["codigo_objeto"] == segunda["codigo_objeto"]
    assert len(base.envios_archivos.filas) == 1


# ─── 2. El código de objeto ───────────────────────────────────────────────

@pytest.mark.parametrize("bruto,esperado", [
    ("AA123456789BR", "AA123456789BR"),
    ("aa123456789br", "AA123456789BR"),
    ("AA 1234 5678 9BR", "AA123456789BR"),      # como está impreso
    (" AA-123456789-BR ", "AA123456789BR"),
])
def test_el_codigo_se_normaliza_como_viene_del_comprobante(bruto, esperado):
    """La gente lo copia tal como está impreso. Rechazar eso es rechazar el dato
    correcto por su formato de presentación."""
    assert comp.normalizar_codigo(bruto) == esperado


@pytest.mark.parametrize("malo", [
    "", "123456789", "AAA123456789BR", "AA12345678BR", "AA123456789B",
    "AA1234567890BR", None, "el que me dieron",
])
def test_un_codigo_con_otra_forma_se_rechaza(malo):
    with pytest.raises(comp.ComprobanteRechazado):
        comp.normalizar_codigo(malo)


def test_el_mismo_codigo_no_puede_estar_en_dos_envios():
    """Dos envíos con el mismo comprobante son dos cobros sobre un solo
    despacho, y el segundo se descubre en el mostrador."""
    import copy
    base = db_completa()
    otro = copy.deepcopy(ENVIO)
    otro["envio_id"] = "env_bbb222"
    otro["origen"] = {"codigo_objeto": CODIGO}
    base.envios.filas.append(otro)

    with pytest.raises(comp.ComprobanteRechazado) as e:
        cargar(base)
    assert e.value.http == 409
    assert envio_de(base)["estado"] == "esperando_postagem"


def test_el_indice_del_codigo_es_unico():
    indices = _cargar("envios_indices").INDICES
    for coleccion, claves, opciones in indices:
        if coleccion == "envios" and claves == "origen.codigo_objeto":
            assert opciones.get("unique") is True
            return
    raise AssertionError("falta el índice del código de objeto")


# ─── 3. La fecha ──────────────────────────────────────────────────────────

def test_una_fecha_futura_se_rechaza():
    base = db_completa()
    futura = (AHORA + timedelta(days=5)).date().isoformat()
    with pytest.raises(comp.ComprobanteRechazado) as e:
        cargar(base, posteado_at=futura)
    assert "futuro" in e.value.mensaje


def test_se_tolera_un_dia_hacia_adelante():
    """El usuario puede estar en otro huso y despachar a la noche."""
    base = db_completa()
    r = cargar(base, posteado_at=(AHORA + timedelta(hours=10)).isoformat())
    assert r["ok"] is True


def test_una_fecha_demasiado_vieja_se_rechaza():
    base = db_completa()
    vieja = (AHORA - timedelta(days=200)).date().isoformat()
    with pytest.raises(comp.ComprobanteRechazado) as e:
        cargar(base, posteado_at=vieja)
    assert "días" in e.value.mensaje


def test_una_fecha_ilegible_se_rechaza_con_un_motivo():
    base = db_completa()
    with pytest.raises(comp.ComprobanteRechazado) as e:
        cargar(base, posteado_at="el jueves pasado")
    assert "AAAA-MM-DD" in e.value.mensaje


# ─── 4. El archivo ────────────────────────────────────────────────────────

def test_el_tipo_se_mira_en_los_bytes_y_no_en_el_nombre():
    """Un ejecutable renombrado a .jpg pasa cualquier chequeo de nombre y ninguno
    de firma. El content-type y la extensión los elige quien sube el archivo."""
    assert archivos.tipo_real(b"MZ\x90\x00ejecutable") is None
    assert archivos.tipo_real(b"<?php system($_GET[0]); ?>") is None
    assert archivos.tipo_real(_jpeg())[0] == "image/jpeg"
    assert archivos.tipo_real(b"%PDF-1.4 algo")[0] == "application/pdf"


def test_un_archivo_que_no_es_una_foto_no_se_guarda():
    base = db_completa()
    with pytest.raises(archivos.ArchivoRechazado) as e:
        cargar(base, foto=b"MZ\x90\x00ejecutable")
    assert "No reconocemos" in e.value.mensaje
    assert base.envios_archivos.filas == []
    assert envio_de(base)["estado"] == "esperando_postagem"


def test_un_archivo_demasiado_grande_se_rechaza_con_su_tamano():
    base = db_completa()
    gigante = _jpeg() + b"\x00" * (archivos.TAMANO_MAX_BYTES + 1)
    with pytest.raises(archivos.ArchivoRechazado) as e:
        cargar(base, foto=gigante)
    assert e.value.http == 413 and "MB" in e.value.mensaje


def test_el_exif_se_borra():
    """Una foto de teléfono lleva las coordenadas de dónde se sacó. El
    comprobante de un envío no tiene por qué registrar la casa de nadie, y una
    vez guardado ya no se puede deshacer."""
    from PIL import Image
    original = _jpeg()
    assert Image.open(io.BytesIO(original)).getexif(), "el fixture tiene que traer EXIF"

    base = db_completa()
    cargar(base, foto=original)
    guardada = base.envios_archivos.filas[0]["contenido"]
    assert not Image.open(io.BytesIO(guardada)).getexif()
    assert base.envios_archivos.filas[0]["exif_removido"] is True


def test_la_imagen_sigue_siendo_la_misma_despues_de_limpiarla():
    """Borrar los metadatos no puede borrar la foto."""
    from PIL import Image
    original = _jpeg(ancho=20, alto=10, color=(10, 200, 40))
    limpia = archivos.sin_exif(original, "image/jpeg")
    a, b = Image.open(io.BytesIO(original)), Image.open(io.BytesIO(limpia))
    assert a.size == b.size
    assert a.convert('RGB').tobytes()[:60] == b.convert('RGB').tobytes()[:60]


def test_un_pdf_se_acepta_y_no_se_toca():
    base = db_completa()
    pdf = b"%PDF-1.4\n" + b"x" * 200
    cargar(base, foto=pdf)
    ficha = base.envios_archivos.filas[0]
    assert ficha["content_type"] == "application/pdf"
    assert bytes(ficha["contenido"]) == pdf


def test_el_mismo_archivo_en_otro_envio_se_marca_pero_no_frena():
    """Dos fotos idénticas pueden ser un reintento legítimo. No se rechaza
    automáticamente, pero el operador tiene que verlo antes de verificar."""
    import copy
    base = db_completa()
    otro = copy.deepcopy(ENVIO)
    otro["envio_id"] = "env_bbb222"
    base.envios.filas.append(otro)
    foto = _jpeg()
    corre(comp.cargar(_Usuario(), "env_bbb222", codigo_objeto="ZZ987654321BR",
                      posteado_at=ANTEAYER, foto=foto, db=base, ahora=AHORA))

    cargar(base, foto=foto)
    assert envio_de(base)["origen"]["foto_repetida_en"] == "env_bbb222"
    assert envio_de(base)["estado"] == "en_transito_origen"


def test_al_usuario_no_se_le_dice_en_que_otro_envio_estaba_la_foto():
    """Decirle "esta foto ya está en env_xxx" le confirma qué identificadores
    existen, y no le sirve para nada."""
    import copy
    base = db_completa()
    otro = copy.deepcopy(ENVIO)
    otro["envio_id"] = "env_bbb222"
    base.envios.filas.append(otro)
    foto = _jpeg()
    corre(comp.cargar(_Usuario(), "env_bbb222", codigo_objeto="ZZ987654321BR",
                      posteado_at=ANTEAYER, foto=foto, db=base, ahora=AHORA))
    r = cargar(base, foto=foto)
    assert "env_bbb222" not in repr(r)


# ─── 5. Verificar es lo que cobra ─────────────────────────────────────────

def test_verificar_emite_el_cobro_inicial_con_el_peso_que_leyo_el_operador():
    base = db_completa()
    cargar(base)
    r = corre(comp.verificar(_Operador(), "env_aaa111", peso_kg="2.65",
                             largo_cm="40", ancho_cm="30", alto_cm="20",
                             db=base, ahora=AHORA))
    esperado = tarifas.cotizar_servicio(TARIFA, "2.65", "40", "30", "20",
                                        valor_declarado="180.00", bultos=1,
                                        fecha="2026-08-30")["total"]
    assert r["cobro"]["estado"] == "pagado"
    assert Decimal(r["cobro"]["monto_ris"]) == esperado
    assert saldo_de(base) == Decimal("500.00") - esperado


def test_el_peso_que_cobra_es_el_del_operador_y_no_el_que_declaro_el_usuario():
    """Es toda la razón por la que verificar existe."""
    base = db_completa()
    cargar(base)
    corre(comp.verificar(_Operador(), "env_aaa111", peso_kg="8.00",
                         largo_cm="40", ancho_cm="30", alto_cm="20",
                         db=base, ahora=AHORA))
    con_lo_declarado = tarifas.cotizar_servicio(
        TARIFA, "2.30", "40", "30", "20", valor_declarado="180.00", bultos=1,
        fecha="2026-08-30")["total"]
    cobrado = Decimal(envio_de(base)["cobros"]["inicial"]["monto_ris"])
    assert cobrado > con_lo_declarado


def test_verificar_dos_veces_cobra_una_sola_vez():
    base = db_completa()
    cargar(base)
    corre(comp.verificar(_Operador(), "env_aaa111", peso_kg="2.65", largo_cm="40",
                         ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    saldo = saldo_de(base)
    r = corre(comp.verificar(_Operador(), "env_aaa111", peso_kg="9.00", largo_cm="40",
                             ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    assert r["ya_verificado"] is True
    assert saldo_de(base) == saldo


def test_no_se_verifica_un_envio_sin_comprobante():
    base = db_completa()
    with pytest.raises(comp.ComprobanteRechazado) as e:
        corre(comp.verificar(_Operador(), "env_aaa111", peso_kg="2.65", largo_cm="40",
                             ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    assert e.value.http == 409
    assert saldo_de(base) == Decimal("500.00")


def test_sin_saldo_la_verificacion_igual_avanza():
    """El paquete ya está viajando: quedarse sin saldo no cancela nada."""
    base = db_completa(saldo="0.00")
    cargar(base)
    r = corre(comp.verificar(_Operador(), "env_aaa111", peso_kg="2.65", largo_cm="40",
                             ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    assert r["cobro"]["estado"] == "pendiente"
    assert envio_de(base)["origen"]["verificado"]["por"] == "usr_operador"


def test_la_verificacion_queda_registrada_con_quien_la_hizo():
    base = db_completa()
    cargar(base)
    corre(comp.verificar(_Operador(), "env_aaa111", peso_kg="2.65", largo_cm="40",
                         ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    v = envio_de(base)["origen"]["verificado"]
    assert v["por"] == "usr_operador" and v["at"] == AHORA
    assert v["peso_kg"] == "2.65"


# ─── 6. Lo que no se puede hacer ──────────────────────────────────────────

def test_no_se_carga_el_comprobante_de_un_envio_ajeno():
    base = db_completa()

    class _Otro:
        user_id = "usr_otro"

    with pytest.raises(comp.ComprobanteRechazado) as e:
        corre(comp.cargar(_Otro(), "env_aaa111", codigo_objeto=CODIGO,
                          posteado_at=AYER, foto=_jpeg(), db=base,
                          ahora=AHORA))
    assert e.value.http == 404


def test_no_se_carga_sobre_un_envio_que_todavia_no_se_confirmo():
    base = db_completa(envio={**ENVIO, "estado": "cotizado"})
    with pytest.raises(comp.ComprobanteRechazado) as e:
        cargar(base)
    assert e.value.http == 409


def test_una_foto_no_se_puede_leer_desde_otro_envio():
    """Un identificador de archivo suelto no puede ser una llave: es lo que
    convierte una galería privada en una pública."""
    import copy
    base = db_completa()
    cargar(base)
    asset = envio_de(base)["origen"]["comprobante_asset_id"]
    assert corre(archivos.leer(asset, envio_id="env_aaa111", db=base)) is not None
    assert corre(archivos.leer(asset, envio_id="env_bbb222", db=base)) is None


def test_el_modulo_no_menciona_ninguna_marca():
    for archivo in ("envios_comprobante.py", "envios_archivos.py"):
        fuente = open(os.path.join(_BACKEND, "services", archivo),
                      encoding="utf-8").read().lower()
        for marca in ("mrw", "correios", "zoom", "tealca", "domesa"):
            assert marca not in fuente, archivo


def test_el_modulo_de_carga_no_importa_nada_que_cobre():
    """Cargar y cobrar son dos pasos y viven en dos funciones. La forma más
    barata de que siga siendo cierto es que el camino de carga no pueda ni
    nombrar al que cobra."""
    fuente = open(os.path.join(_BACKEND, "services", "envios_comprobante.py"),
                  encoding="utf-8").read()
    codigo = "\n".join(l for l in fuente.split("\n")
                       if not l.lstrip().startswith("#"))
    cuerpo_cargar = codigo[codigo.index("async def cargar("):
                           codigo.index("async def verificar(")]
    for prohibido in ("envios_cobros", "emitir_inicial", "balance_ris"):
        assert prohibido not in cuerpo_cargar


def test_verificar_dos_veces_no_pisa_lo_que_leyo_el_primero():
    """Lo que el operador leyó en el papel es lo que justifica el monto cobrado.
    Reescribirlo con un segundo intento deja el cobro sin nada que lo explique."""
    base = db_completa()
    cargar(base)
    corre(comp.verificar(_Operador(), "env_aaa111", peso_kg="2.65", largo_cm="40",
                         ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))

    class _Otro:
        user_id = "usr_otro_operador"

    corre(comp.verificar(_Otro(), "env_aaa111", peso_kg="9.00", largo_cm="40",
                         ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    v = envio_de(base)["origen"]["verificado"]
    assert v["peso_kg"] == "2.65" and v["por"] == "usr_operador"


def test_el_estado_se_chequea_antes_y_tambien_en_el_filtro():
    """Dos capas. La de arriba da el mensaje bueno; la del filtro es la que
    sostiene cuando el documento cambió entre la lectura y la escritura."""
    base = db_completa(envio={**ENVIO, "estado": "recibido_pacaraima"})
    with pytest.raises(comp.ComprobanteRechazado) as e:
        cargar(base)
    assert "no está esperando el comprobante" in e.value.mensaje

    # Y con una lectura rancia, que es lo que ve la segunda petición de un doble
    # clic: el chequeo de arriba pasa y lo que frena es el filtro.
    base2 = db_completa()
    rancio = dict(envio_de(base2))
    envio_de(base2)["estado"] = "recibido_pacaraima"
    original = base2.envios.find_one

    async def lectura_rancia(filtro, proyeccion=None):
        base2.envios.find_one = original
        return dict(rancio)
    base2.envios.find_one = lectura_rancia

    with pytest.raises(comp.ComprobanteRechazado) as e2:
        cargar(base2)
    assert e2.value.http == 409


def test_una_lectura_rancia_no_deja_verificar_dos_veces():
    """La guardia de arriba mira el documento que se leyó; la del filtro mira el
    que está. Entre los dos hay una ventana, y es la que ve la segunda petición
    de un doble clic."""
    base = db_completa()
    cargar(base)
    import copy
    # deepcopy: con una copia superficial el bloque `origen` es el MISMO objeto y
    # la "lectura rancia" se entera de la verificación, o sea que no es rancia.
    rancio = copy.deepcopy(envio_de(base))   # sin verificar todavía
    corre(comp.verificar(_Operador(), "env_aaa111", peso_kg="2.65", largo_cm="40",
                         ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    saldo = saldo_de(base)

    original = base.envios.find_one

    async def lectura_rancia(filtro, proyeccion=None):
        base.envios.find_one = original
        return dict(rancio)
    base.envios.find_one = lectura_rancia

    r = corre(comp.verificar(_Operador(), "env_aaa111", peso_kg="9.00", largo_cm="40",
                             ancho_cm="30", alto_cm="20", db=base, ahora=AHORA))
    assert r["ya_verificado"] is True
    assert envio_de(base)["origen"]["verificado"]["peso_kg"] == "2.65"
    assert saldo_de(base) == saldo


def test_ninguna_fecha_de_despacho_esta_escrita_a_mano():
    """Una fecha de despacho fija contra un reloj real es una bomba: la suite
    empieza a fallar sola un día, y el fallo no dice "el test tiene una fecha
    vieja", dice "el comprobante tiene más de 60 días".

    La fecha de la COTIZACIÓN sí puede ser fija, y tiene que serlo: está congelada
    en el envío y es lo que hace reproducible el monto que se cobra.
    """
    import re as _re
    fuente = open(__file__, encoding="utf-8").read()
    codigo = "\n".join(l for l in fuente.split("\n")
                       if not l.lstrip().startswith("#"))
    fijas = _re.findall(r'posteado_at\s*[=:]\s*"20\d\d-\d\d-\d\d"', codigo)
    assert fijas == [], f"fechas de despacho fijas: {fijas}"


def test_una_fecha_de_despacho_de_hace_dos_meses_ya_no_entra():
    """El límite es real y este test lo fija: si alguien lo sube a 365, esto
    falla y hay que decidirlo, no descubrirlo."""
    base = db_completa()
    vieja = (AHORA - timedelta(days=comp.DIAS_ATRAS_MAX + 1)).date().isoformat()
    with pytest.raises(comp.ComprobanteRechazado):
        cargar(base, posteado_at=vieja)
    justo = (AHORA - timedelta(days=comp.DIAS_ATRAS_MAX - 1)).date().isoformat()
    assert cargar(base, posteado_at=justo)["ok"] is True


def test_la_deteccion_de_foto_repetida_no_depende_del_orden_de_mongo():
    """`guardar` INSERTA antes de consultar, así que si la base devolvía primero
    el documento recién insertado la marca se perdía en silencio. Depender del
    orden natural para una señal de fraude es no tener la señal."""
    base = db_completa()
    base.envios_archivos.filas.extend([
        {"asset_id": "ast_viejo", "sha256": "abc", "envio_id": "env_otro"},
        {"asset_id": "ast_nuevo", "sha256": "abc", "envio_id": "env_aaa111"},
    ])
    # Se fuerza el peor orden: el propio primero, que es el que hacía perder la
    # marca.
    base.envios_archivos.filas.reverse()
    assert corre(archivos.ya_usado("abc", "env_aaa111", db=base)) == "env_otro"


def test_dos_cargas_simultaneas_del_mismo_codigo_dan_un_motivo_y_no_un_503():
    """El índice de `origen.codigo_objeto` es único, así que la segunda carga
    termina en un E11000. Responder 503 le dice al usuario "reintentá" sobre algo
    que nunca va a funcionar."""
    base = db_completa()
    original = base.envios.find_one_and_update

    async def choca(*a, **k):
        base.envios.find_one_and_update = original
        raise RuntimeError("E11000 duplicate key error collection: envios")
    base.envios.find_one_and_update = choca

    with pytest.raises(comp.ComprobanteRechazado) as e:
        cargar(base)
    assert e.value.http == 409
    assert "otro envío" in e.value.mensaje
