"""
Las fotos en un almacen de objetos, y la migracion que las mueve sin perderlas.

QUE SE CUBRE
    1. Sin variables de entorno, todo sigue igual: los bytes van a Mongo.
    2. Con el almacen prendido, los bytes NO quedan en Mongo y la ficha dice
       donde estan.
    3. Si el almacen no contesta al subir, el archivo se guarda igual en Mongo.
       Un servicio nuestro caido no puede impedir que el usuario despache.
    4. Leer despacha por ficha, no por interruptor global: en una misma base
       conviven fotos en Mongo y fotos en el almacen.
    5. Lo que vuelve distinto de lo que se guardo NO se sirve. De esa foto sale
       el peso con el que se cobra.
    6. La migracion escribe, RELEE, COMPARA y recien despues borra de Mongo. Si
       cualquiera de los tres pasos falla, el ejemplar de Mongo se queda.
    7. Un endpoint en http desactiva el almacen: la firma viajaria en claro.
    8. `estado()` no devuelve la clave ni el secreto por ninguna via.

El doble de S3 es deliberadamente antipatico: puede fallar al escribir, fallar al
leer, devolver bytes distintos, devolver de mas y quedarse mudo. Un doble que
siempre funciona prueba el camino feliz y nada mas.
"""
import asyncio
import hashlib
import importlib.util
import io
import os
import sys
import threading
import types

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from conftest import usar_base                                        # noqa: E402


# --- doble de Mongo ---------------------------------------------------------

def _proyectar(doc, proyeccion):
    import copy
    if not proyeccion:
        return copy.deepcopy(doc)
    incluir = [k for k, v in proyeccion.items() if v and k != "_id"]
    if incluir:
        return copy.deepcopy({k: v for k, v in doc.items() if k in incluir})
    excluir = [k for k, v in proyeccion.items() if not v]
    return copy.deepcopy({k: v for k, v in doc.items() if k not in excluir})


class _Resultado:
    def __init__(self, n):
        self.matched_count = n
        self.modified_count = n


class _Coleccion:
    def __init__(self, filas=None):
        self.filas = filas if filas is not None else []
        self.rota = False
        self.ultimo_limite = "sin listar"

    def _match(self, d, filtro):
        for k, v in (filtro or {}).items():
            actual = d.get(k)
            if isinstance(v, dict) and "$exists" in v:
                if (k in d) != bool(v["$exists"]):
                    return False
            elif isinstance(v, dict) and "$ne" in v:
                if actual == v["$ne"]:
                    return False
            elif actual != v:
                return False
        return True

    class _Cursor:
        def __init__(self, filas, coleccion):
            self.filas = filas
            self.coleccion = coleccion

        async def to_list(self, n):
            self.coleccion.ultimo_limite = n
            return list(self.filas)[:n] if n else list(self.filas)

    def find(self, filtro=None, proyeccion=None):
        return self._Cursor([_proyectar(d, proyeccion)
                             for d in self.filas if self._match(d, filtro)], self)

    async def find_one(self, filtro, proyeccion=None):
        for d in self.filas:
            if self._match(d, filtro):
                return _proyectar(d, proyeccion)
        return None

    async def count_documents(self, filtro):
        return sum(1 for d in self.filas if self._match(d, filtro))

    async def insert_one(self, doc):
        if self.rota:
            raise RuntimeError("mongo caído")
        self.filas.append(dict(doc))

    async def update_one(self, filtro, cambio, upsert=False):
        for d in self.filas:
            if self._match(d, filtro):
                for clave, valor in (cambio.get("$set") or {}).items():
                    d[clave] = valor
                for clave in (cambio.get("$unset") or {}):
                    d.pop(clave, None)
                return _Resultado(1)
        return _Resultado(0)


class _Db:
    def __init__(self):
        self._c = {}

    def __getattr__(self, nombre):
        return self._c.setdefault(nombre, _Coleccion([]))

    def __getitem__(self, nombre):
        return self._c.setdefault(nombre, _Coleccion([]))


# --- doble de S3 ------------------------------------------------------------

class _CuerpoFalso:
    def __init__(self, datos, parcial=False):
        self._datos = datos
        self.cerrado = False
        self.pedido = "sin pedir"
        # Un `read(n)` puede devolver MENOS de n: es una lectura parcial, y es uno
        # de los dos casos que la verificación de hash existe para atrapar. Un
        # doble que siempre devuelve todo no puede producirlo.
        self._parcial = parcial

    def read(self, n=None):
        self.pedido = n
        datos = self._datos[:n] if n else self._datos
        return datos[:len(datos) // 2] if self._parcial else datos

    def close(self):
        self.cerrado = True


class _S3Falso:
    """Un bucket en memoria que se puede romper a voluntad."""

    def __init__(self):
        self.objetos = {}
        self.escrituras = 0
        self.lecturas = 0
        self.falla_al_escribir = False
        self.falla_al_leer = False
        self.escribe_pero_descarta = False
        self.devuelve_de_mas = False
        self.devuelve_parcial = False
        self.cuerpos = []
        # Dónde corrió cada llamada. boto3 es sincrónico: si alguna corre en el
        # hilo principal, está adentro del bucle de eventos.
        self.hilos = []

    def put_object(self, Bucket=None, Key=None, Body=None, ContentType=None):
        self.escrituras += 1
        self.hilos.append(threading.current_thread() is threading.main_thread())
        if self.falla_al_escribir:
            raise RuntimeError("503 del bucket")
        if self.escribe_pero_descarta:
            return {}
        self.objetos[(Bucket, Key)] = (bytes(Body), ContentType)
        return {}

    def get_object(self, Bucket=None, Key=None):
        self.lecturas += 1
        self.hilos.append(threading.current_thread() is threading.main_thread())
        if self.falla_al_leer:
            raise RuntimeError("timeout del bucket")
        if (Bucket, Key) not in self.objetos:
            raise RuntimeError("NoSuchKey")
        datos = self.objetos[(Bucket, Key)][0]
        if self.devuelve_de_mas:
            datos = b"x" * (9 * 1024 * 1024)
        cuerpo = _CuerpoFalso(datos, parcial=self.devuelve_parcial)
        self.cuerpos.append(cuerpo)
        return {"Body": cuerpo}


# --- carga de modulos -------------------------------------------------------

def _cargar(nombre):
    if "services" not in sys.modules:
        paquete = types.ModuleType("services")
        paquete.__path__ = [os.path.join(_BACKEND, "services")]
        sys.modules["services"] = paquete
    completo = f"services.{nombre}"
    if completo in sys.modules:
        modulo = sys.modules[completo]
    else:
        ruta = os.path.join(_BACKEND, "services", f"{nombre}.py")
        spec = importlib.util.spec_from_file_location(completo, ruta)
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[completo] = modulo
        spec.loader.exec_module(modulo)
    setattr(sys.modules["services"], nombre, modulo)
    return modulo


almacen = _cargar("envios_almacen")
archivos = _cargar("envios_archivos")


def corre(coro):
    return asyncio.run(coro)


ENDPOINT = "https://cuenta.r2.cloudflarestorage.com"
BUCKET = "risapp-envios"

VARIABLES = {
    almacen.VAR_ENDPOINT: ENDPOINT,
    almacen.VAR_BUCKET: BUCKET,
    almacen.VAR_ACCESS_KEY: "AKIAFALSA",
    almacen.VAR_SECRETO: "secreto-que-no-tiene-que-salir-nunca",
}


def _jpg(relleno=b"foto"):
    """Un JPEG que PIL no puede abrir: `sin_exif` devuelve los bytes tal cual.

    Es a propósito. Lo que se prueba acá es dónde van los bytes, no la limpieza
    del EXIF, y un JPEG real haría que el contenido guardado no fuera el que el
    test escribió — con lo cual las comparaciones dejarían de decir nada.
    """
    return b"\xff\xd8\xff" + relleno


@pytest.fixture
def base():
    return usar_base(_Db())


@pytest.fixture
def s3(monkeypatch):
    falso = _S3Falso()
    for nombre, valor in VARIABLES.items():
        monkeypatch.setenv(nombre, valor)
    monkeypatch.delenv(almacen.VAR_PREFIJO, raising=False)
    monkeypatch.setattr(almacen, "_construir_cliente",
                        lambda *a, **k: falso)
    almacen.olvidar_cliente()
    yield falso
    almacen.olvidar_cliente()


@pytest.fixture
def sin_almacen(monkeypatch):
    for nombre in almacen.OBLIGATORIAS + (almacen.VAR_PREFIJO,):
        monkeypatch.delenv(nombre, raising=False)
    almacen.olvidar_cliente()
    yield
    almacen.olvidar_cliente()


# --- 1. sin almacen, nada cambia --------------------------------------------

def test_sin_variables_los_bytes_van_a_mongo(base, sin_almacen):
    datos = _jpg()
    ficha = corre(archivos.guardar(datos, envio_id="env_1", user_id="u1",
                                   clase="comprobante"))
    assert ficha["almacen"] == "mongo"
    assert ficha["clave"] is None
    fila = base.envios_archivos.filas[0]
    assert fila["contenido"] == datos

    leida = corre(archivos.leer(ficha["asset_id"], envio_id="env_1"))
    assert leida["contenido"] == datos


def test_configurado_es_falso_si_falta_una_sola_variable(monkeypatch):
    for nombre, valor in VARIABLES.items():
        monkeypatch.setenv(nombre, valor)
    assert almacen.configurado() is True
    for nombre in almacen.OBLIGATORIAS:
        monkeypatch.delenv(nombre)
        assert almacen.configurado() is False, nombre
        assert nombre in almacen.faltantes()
        monkeypatch.setenv(nombre, VARIABLES[nombre])


# --- 2. con almacen, los bytes salen de Mongo -------------------------------

def test_con_almacen_los_bytes_no_quedan_en_mongo(base, s3):
    datos = _jpg()
    ficha = corre(archivos.guardar(datos, envio_id="env_1", user_id="u1",
                                   clase="comprobante"))
    assert ficha["almacen"] == "r2"
    assert ficha["clave"] == f"envios/env_1/{ficha['asset_id']}.jpg"

    fila = base.envios_archivos.filas[0]
    assert "contenido" not in fila, "la ficha en Mongo no puede llevar los bytes"
    assert s3.objetos[(BUCKET, ficha["clave"])][0] == datos
    assert s3.objetos[(BUCKET, ficha["clave"])][1] == "image/jpeg"


def test_leer_trae_los_bytes_del_almacen(base, s3):
    datos = _jpg(b"comprobante")
    ficha = corre(archivos.guardar(datos, envio_id="env_1", user_id="u1",
                                   clase="comprobante"))
    leida = corre(archivos.leer(ficha["asset_id"], envio_id="env_1"))
    assert leida["contenido"] == datos
    assert not leida.get("error")
    assert all(c.cerrado for c in s3.cuerpos), "el cuerpo del objeto queda abierto"


def test_el_prefijo_se_puede_cambiar(base, s3, monkeypatch):
    monkeypatch.setenv(almacen.VAR_PREFIJO, "fotos/prod")
    ficha = corre(archivos.guardar(_jpg(), envio_id="env_9", user_id="u1",
                                   clase="comprobante"))
    assert ficha["clave"].startswith("fotos/prod/env_9/")


def test_un_prefijo_con_salto_de_directorio_se_ignora(s3, monkeypatch):
    monkeypatch.setenv(almacen.VAR_PREFIJO, "../otro")
    assert almacen.prefijo() == almacen.PREFIJO_POR_DEFECTO


# --- 3. el almacen caido no impide despachar --------------------------------

def test_si_el_almacen_no_escribe_el_archivo_va_a_mongo(base, s3):
    s3.falla_al_escribir = True
    datos = _jpg()
    ficha = corre(archivos.guardar(datos, envio_id="env_1", user_id="u1",
                                   clase="comprobante"))
    assert ficha["almacen"] == "mongo"
    assert base.envios_archivos.filas[0]["contenido"] == datos
    leida = corre(archivos.leer(ficha["asset_id"], envio_id="env_1"))
    assert leida["contenido"] == datos


def test_el_objeto_se_escribe_antes_que_la_ficha(base, s3):
    """Si Mongo falla, queda un objeto huérfano — no una ficha que apunta a nada."""
    base.envios_archivos.rota = True
    with pytest.raises(archivos.ArchivoRechazado) as e:
        corre(archivos.guardar(_jpg(), envio_id="env_1", user_id="u1",
                               clase="comprobante"))
    assert e.value.http == 503
    assert s3.escrituras == 1, "el objeto tiene que haberse escrito primero"
    assert base.envios_archivos.filas == []


# --- 4. los dos almacenes conviven ------------------------------------------

def test_la_misma_base_sirve_fotos_de_los_dos_lados(base, s3, monkeypatch):
    en_almacen = corre(archivos.guardar(_jpg(b"nueva"), envio_id="env_1",
                                        user_id="u1", clase="comprobante"))
    for nombre in almacen.OBLIGATORIAS:
        monkeypatch.delenv(nombre)
    almacen.olvidar_cliente()
    en_mongo = corre(archivos.guardar(_jpg(b"vieja"), envio_id="env_2",
                                      user_id="u1", clase="comprobante"))
    assert en_mongo["almacen"] == "mongo"

    # Con el almacén apagado, la de Mongo se sirve igual.
    assert corre(archivos.leer(en_mongo["asset_id"], envio_id="env_2"))["contenido"] == _jpg(b"vieja")

    for nombre, valor in VARIABLES.items():
        monkeypatch.setenv(nombre, valor)
    almacen.olvidar_cliente()
    assert corre(archivos.leer(en_almacen["asset_id"], envio_id="env_1"))["contenido"] == _jpg(b"nueva")


# --- 5. lo que no se puede traer, y lo que no coincide ----------------------

def test_una_falla_de_lectura_no_es_un_404(base, s3):
    ficha = corre(archivos.guardar(_jpg(), envio_id="env_1", user_id="u1",
                                   clase="comprobante"))
    s3.falla_al_leer = True
    leida = corre(archivos.leer(ficha["asset_id"], envio_id="env_1"))
    assert leida is not None, "la ficha existe: no puede contestarse 'no existe'"
    assert leida.get("contenido") is None
    assert leida["error"] == "almacen"


def test_un_asset_inexistente_sigue_siendo_none(base, s3):
    assert corre(archivos.leer("ast_no_existe", envio_id="env_1")) is None


def test_bytes_que_no_coinciden_con_el_hash_no_se_sirven(base, s3):
    ficha = corre(archivos.guardar(_jpg(), envio_id="env_1", user_id="u1",
                                   clase="comprobante"))
    s3.objetos[(BUCKET, ficha["clave"])] = (_jpg(b"otra cosa"), "image/jpeg")
    leida = corre(archivos.leer(ficha["asset_id"], envio_id="env_1"))
    assert leida["error"] == "integridad"
    assert leida.get("contenido") is None


def test_el_objeto_se_pide_acotado_no_entero(base, s3):
    """El tamaño del objeto lo decide un servicio remoto, no nosotros.

    Chequear el largo DESPUÉS de leer no protege de nada: para cuando se puede
    medir, los bytes ya están en la memoria del proceso. Se pide un byte más que
    el tope, que es lo mínimo que alcanza para detectar el exceso.
    """
    ficha = corre(archivos.guardar(_jpg(), envio_id="env_1", user_id="u1",
                                   clase="comprobante"))
    corre(archivos.leer(ficha["asset_id"], envio_id="env_1"))
    assert s3.cuerpos[-1].pedido == archivos.TAMANO_MAX_BYTES + 1


def test_un_objeto_mas_grande_que_el_tope_no_se_sirve(base, s3):
    ficha = corre(archivos.guardar(_jpg(), envio_id="env_1", user_id="u1",
                                   clase="comprobante"))
    s3.devuelve_de_mas = True
    leida = corre(archivos.leer(ficha["asset_id"], envio_id="env_1"))
    # "grande", no "almacen": un objeto de 9 MB no se va a achicar por esperar un
    # minuto, y ese es el mensaje que decide qué se le dice a la persona.
    assert leida["error"] == "grande"


def test_una_foto_no_se_lee_desde_otro_envio(base, s3):
    ficha = corre(archivos.guardar(_jpg(), envio_id="env_1", user_id="u1",
                                   clase="comprobante"))
    assert corre(archivos.leer(ficha["asset_id"], envio_id="env_2")) is None


# --- 6. la migracion --------------------------------------------------------

def _tres_en_mongo(sin_variables=True):
    return [
        corre(archivos.guardar(_jpg(bytes(f"n{i}", "ascii")), envio_id=f"env_{i}",
                               user_id="u1", clase="comprobante"))
        for i in range(3)
    ]


def test_la_migracion_mueve_y_borra_de_mongo(base, monkeypatch):
    for nombre in almacen.OBLIGATORIAS:
        monkeypatch.delenv(nombre, raising=False)
    almacen.olvidar_cliente()
    fichas = _tres_en_mongo()
    assert all(f["almacen"] == "mongo" for f in fichas)

    falso = _S3Falso()
    for nombre, valor in VARIABLES.items():
        monkeypatch.setenv(nombre, valor)
    monkeypatch.setattr(almacen, "_construir_cliente", lambda *a, **k: falso)
    almacen.olvidar_cliente()

    salida = corre(archivos.migrar_lote(limite=50))
    assert salida["migrados"] == 3
    assert salida["fallidos"] == 0
    assert salida["en_mongo"] == 0
    assert salida["en_almacen"] == 3

    for f in fichas:
        fila = next(d for d in base.envios_archivos.filas
                    if d["asset_id"] == f["asset_id"])
        assert "contenido" not in fila
        assert fila["almacen"] == "r2"
        assert fila["migrado_at"] is not None
        # Y se sigue leyendo, que es lo único que le importa a quien la pide.
        assert corre(archivos.leer(f["asset_id"], envio_id=f["envio_id"]))[
            "contenido"] == falso.objetos[(BUCKET, fila["clave"])][0]
    almacen.olvidar_cliente()


def _preparar_migracion(monkeypatch, cantidad=1):
    for nombre in almacen.OBLIGATORIAS:
        monkeypatch.delenv(nombre, raising=False)
    almacen.olvidar_cliente()
    fichas = [corre(archivos.guardar(_jpg(bytes(f"n{i}", "ascii")),
                                     envio_id=f"env_{i}", user_id="u1",
                                     clase="comprobante"))
              for i in range(cantidad)]
    falso = _S3Falso()
    for nombre, valor in VARIABLES.items():
        monkeypatch.setenv(nombre, valor)
    monkeypatch.setattr(almacen, "_construir_cliente", lambda *a, **k: falso)
    almacen.olvidar_cliente()
    return fichas, falso


def test_si_la_escritura_falla_los_bytes_se_quedan_en_mongo(base, monkeypatch):
    fichas, falso = _preparar_migracion(monkeypatch)
    falso.falla_al_escribir = True
    salida = corre(archivos.migrar_lote())
    assert salida["migrados"] == 0
    assert salida["fallidos"] == 1
    assert base.envios_archivos.filas[0]["contenido"] is not None
    assert base.envios_archivos.filas[0]["almacen"] == "mongo"
    # El motivo tiene que ser el real. Si la escritura fallida se colara hasta la
    # relectura, el panel diría "lo que se leyó no es lo que se escribió" sobre
    # algo que nunca se escribió, y el admin iría a mirar el bucket en vez de la
    # credencial.
    assert "escribir" in salida["detalle"][0]
    assert falso.lecturas == 0, "no se relee lo que no se pudo escribir"
    almacen.olvidar_cliente()


def test_si_lo_que_vuelve_no_es_lo_que_se_escribio_no_se_borra(base, monkeypatch):
    """El bucket acepta la escritura y guarda otra cosa. Es el caso que justifica
    la relectura: sin ella, acá se borraba el único ejemplar que existía."""
    fichas, falso = _preparar_migracion(monkeypatch)
    falso.escribe_pero_descarta = True
    salida = corre(archivos.migrar_lote())
    assert salida["migrados"] == 0
    assert salida["fallidos"] == 1
    assert base.envios_archivos.filas[0]["contenido"] is not None
    assert base.envios_archivos.filas[0]["almacen"] == "mongo"
    almacen.olvidar_cliente()


def test_bytes_corruptos_en_mongo_no_se_migran(base, monkeypatch):
    fichas, falso = _preparar_migracion(monkeypatch)
    base.envios_archivos.filas[0]["contenido"] = _jpg(b"corrupto")
    salida = corre(archivos.migrar_lote())
    assert salida["sospechosos"] == 1
    assert salida["migrados"] == 0
    assert base.envios_archivos.filas[0]["contenido"] is not None
    assert falso.escrituras == 0, "no se sube un archivo que no coincide con su hash"
    almacen.olvidar_cliente()


def test_la_migracion_es_idempotente(base, monkeypatch):
    fichas, falso = _preparar_migracion(monkeypatch, cantidad=2)
    primera = corre(archivos.migrar_lote())
    segunda = corre(archivos.migrar_lote())
    assert primera["migrados"] == 2
    assert segunda["migrados"] == 0
    assert segunda["en_mongo"] == 0
    almacen.olvidar_cliente()


def test_el_lote_respeta_el_limite(base, monkeypatch):
    fichas, falso = _preparar_migracion(monkeypatch, cantidad=5)
    salida = corre(archivos.migrar_lote(limite=2))
    assert salida["migrados"] == 2
    assert salida["en_mongo"] == 3
    almacen.olvidar_cliente()


@pytest.mark.parametrize("pedido,esperado", [
    (10 ** 6, archivos.MIGRACION_LOTE_MAX),
    (0, archivos.MIGRACION_LOTE_POR_DEFECTO),
    (-5, 1),
    (None, archivos.MIGRACION_LOTE_POR_DEFECTO),
    ("muchos", archivos.MIGRACION_LOTE_POR_DEFECTO),
    (7, 7),
])
def test_el_limite_se_acota_antes_de_pedirle_nada_a_mongo(base, monkeypatch,
                                                          pedido, esperado):
    """Se comprueba CUÁNTO se le pidió a Mongo, no cuánto se migró.

    Con un lote de un archivo, `limite=1_000_000` y `limite=20` migran lo mismo:
    uno. La diferencia aparece el día que hay cincuenta mil, que es justo el día
    en que nadie está mirando este test.
    """
    _preparar_migracion(monkeypatch, cantidad=1)
    corre(archivos.migrar_lote(limite=pedido))
    assert base.envios_archivos.ultimo_limite == esperado
    almacen.olvidar_cliente()


def test_sin_almacen_la_migracion_no_hace_nada(base, sin_almacen):
    corre(archivos.guardar(_jpg(), envio_id="env_1", user_id="u1",
                           clase="comprobante"))
    salida = corre(archivos.migrar_lote())
    assert salida["activo"] is False
    assert salida["migrados"] == 0
    assert base.envios_archivos.filas[0]["contenido"] is not None


# --- 7. el endpoint tiene que ser https -------------------------------------

@pytest.mark.parametrize("endpoint", [
    "http://cuenta.r2.cloudflarestorage.com",
    "https://",
    "cuenta.r2.cloudflarestorage.com",
    "ftp://cuenta.r2.cloudflarestorage.com",
])
def test_un_endpoint_que_no_es_https_desactiva_el_almacen(monkeypatch, endpoint):
    for nombre, valor in VARIABLES.items():
        monkeypatch.setenv(nombre, valor)
    monkeypatch.setenv(almacen.VAR_ENDPOINT, endpoint)
    assert almacen.configurado() is False


def test_con_el_endpoint_en_http_los_bytes_van_a_mongo(base, s3, monkeypatch):
    monkeypatch.setenv(almacen.VAR_ENDPOINT, ENDPOINT.replace("https", "http"))
    ficha = corre(archivos.guardar(_jpg(), envio_id="env_1", user_id="u1",
                                   clase="comprobante"))
    assert ficha["almacen"] == "mongo"
    assert s3.escrituras == 0


# --- 8. el secreto no sale por ninguna via ----------------------------------

def test_estado_no_filtra_credenciales(s3):
    estado = almacen.estado()
    texto = repr(estado)
    assert VARIABLES[almacen.VAR_SECRETO] not in texto
    assert VARIABLES[almacen.VAR_ACCESS_KEY] not in texto
    assert estado["activo"] is True
    assert estado["bucket"] == BUCKET
    assert estado["endpoint_host"] == "cuenta.r2.cloudflarestorage.com"
    assert estado["credenciales_cargadas"] is True
    assert estado["variables_faltantes"] == []


def test_estado_sin_configurar_dice_que_falta(sin_almacen):
    estado = almacen.estado()
    assert estado["activo"] is False
    assert set(estado["variables_faltantes"]) == set(almacen.OBLIGATORIAS)


# --- el boton de probar -----------------------------------------------------

def test_probar_escribe_y_lee(s3):
    salida = corre(almacen.probar())
    assert salida["ok"] is True
    assert (BUCKET, f"envios/{almacen.CLAVE_DE_PRUEBA}") in s3.objetos


def test_probar_avisa_si_no_puede_escribir(s3):
    s3.falla_al_escribir = True
    assert corre(almacen.probar())["ok"] is False


def test_probar_avisa_si_escribe_pero_no_lee(s3):
    s3.falla_al_leer = True
    salida = corre(almacen.probar())
    assert salida["ok"] is False
    assert "lectura" in salida["detalle"]


def test_probar_sin_configurar_no_revienta(sin_almacen):
    salida = corre(almacen.probar())
    assert salida["ok"] is False
    assert salida["faltantes"]


# --- la clave -------------------------------------------------------------

@pytest.mark.parametrize("envio_id", ["../otro", "env/1", "", None, "a" * 80,
                                      ".oculto"])
def test_una_clave_con_componentes_raros_se_rechaza(s3, envio_id):
    with pytest.raises(ValueError):
        almacen.clave_de(envio_id, "ast_1", "jpg")


def test_un_envio_con_id_raro_no_bloquea_el_despacho(base, s3):
    """La clave la arma este sistema. Si no valida es un defecto nuestro, y el
    usuario no se puede quedar sin poder despachar por eso: va a Mongo."""
    ficha = corre(archivos.guardar(_jpg(), envio_id="env/1", user_id="u1",
                                   clase="comprobante"))
    assert ficha["almacen"] == "mongo"
    assert s3.escrituras == 0


def test_el_cliente_se_cachea_y_se_invalida_al_rotar(monkeypatch):
    construidos = []

    def _construir(endpoint, access_key, secreto):
        construidos.append(access_key)
        return _S3Falso()

    for nombre, valor in VARIABLES.items():
        monkeypatch.setenv(nombre, valor)
    monkeypatch.setattr(almacen, "_construir_cliente", _construir)
    almacen.olvidar_cliente()
    almacen._cliente()
    almacen._cliente()
    assert construidos == ["AKIAFALSA"]
    monkeypatch.setenv(almacen.VAR_ACCESS_KEY, "AKIAOTRA")
    almacen._cliente()
    assert construidos == ["AKIAFALSA", "AKIAOTRA"]
    almacen.olvidar_cliente()


def test_no_existe_ninguna_llamada_a_borrar():
    """El token de R2 se emite sin permiso de borrado, y este archivo es la
    garantía: si un día alguien agrega un `delete_object`, este test lo dice."""
    import ast as _ast
    arbol = _ast.parse(open(os.path.join(_BACKEND, "services", "envios_almacen.py"),
                            encoding="utf-8").read())
    prohibidos = {"delete_object", "delete_objects", "delete_bucket",
                  "put_bucket_lifecycle_configuration"}
    llamadas = {n.attr for n in _ast.walk(arbol) if isinstance(n, _ast.Attribute)}
    llamadas |= {n.value for n in _ast.walk(arbol)
                 if isinstance(n, _ast.Constant) and isinstance(n.value, str)
                 and n.value in prohibidos}
    assert not (llamadas & prohibidos), sorted(llamadas & prohibidos)


# --- 404 contra 503 ---------------------------------------------------------

def test_una_ficha_ausente_es_404(base, s3):
    with pytest.raises(archivos.ArchivoRechazado) as e:
        archivos.exigir_bytes(None)
    assert e.value.http == 404


def test_una_ficha_sin_bytes_y_sin_error_es_404(base, s3):
    with pytest.raises(archivos.ArchivoRechazado) as e:
        archivos.exigir_bytes({"asset_id": "ast_1"})
    assert e.value.http == 404


@pytest.mark.parametrize("motivo", ["almacen", "base"])
def test_una_falla_transitoria_es_503_y_dice_reintenta(base, s3, motivo):
    """No es 404. La foto está: lo que falló es traerla.

    Con 404, el operador va a pedirle al usuario que suba de nuevo un comprobante
    que ya subió, y el envío se frena por una caída que dura dos minutos.
    """
    with pytest.raises(archivos.ArchivoRechazado) as e:
        archivos.exigir_bytes({"asset_id": "ast_1", "error": motivo})
    assert e.value.http == 503
    assert "de nuevo" in e.value.mensaje


@pytest.mark.parametrize("motivo", ["integridad", "ausente", "grande"])
def test_una_falla_permanente_no_invita_a_reintentar(base, s3, motivo):
    """El módulo ya tiene escrita esta regla: responder 503 le dice a alguien
    "reintentá" sobre algo que nunca va a funcionar. Un objeto que no está no va
    a aparecer, y un hash que no coincide no se va a arreglar solo."""
    with pytest.raises(archivos.ArchivoRechazado) as e:
        archivos.exigir_bytes({"asset_id": "ast_1", "error": motivo})
    assert e.value.http == 410
    assert "de nuevo" not in e.value.mensaje
    assert "soporte" in e.value.mensaje


def test_una_ficha_con_bytes_pasa(base, s3):
    ficha = {"asset_id": "ast_1", "contenido": b"x"}
    assert archivos.exigir_bytes(ficha) is ficha


def test_las_dos_rutas_de_foto_contestan_igual():
    """Usuario y operador tienen que ver el mismo código. Si una de las dos se
    quedara con su propio `if`, una caída del almacén sería 503 para el usuario y
    404 para el operador — o al revés."""
    for archivo in ("routes/envios.py", "routes/envios_admin.py"):
        fuente = open(os.path.join(_BACKEND, archivo), encoding="utf-8").read()
        assert "envios_archivos.exigir_bytes(ficha)" in fuente, archivo
        assert 'raise HTTPException(404, "No encontramos esa foto.")' not in fuente, (
            f"{archivo} decide por su cuenta si es 404")


# --- lo que encontró la revisión adversarial --------------------------------

def _ficha_vieja(base, envio_id="env_viejo", datos=None):
    """Una ficha con el shape que escribía el módulo ANTES de este PR.

    Sin `almacen`, sin `clave`, sin `bucket`. Es el 100% de lo que existe el día
    del despliegue, y es exactamente lo que la migración viene a mover.
    """
    datos = datos if datos is not None else _jpg(b"vieja")
    base.envios_archivos.filas.append({
        "asset_id": "ast_" + "0" * 32, "envio_id": envio_id, "user_id": "u1",
        "clase": "comprobante", "content_type": "image/jpeg", "extension": "jpg",
        "bytes": len(datos), "sha256": hashlib.sha256(datos).hexdigest(),
        "exif_removido": False, "created_at": None, "contenido": datos,
    })
    return datos


def test_una_foto_anterior_al_campo_almacen_se_cuenta_y_se_migra(base, s3):
    """El defecto que hacía que la migración fuera un no-op sobre el histórico.

    Con el filtro `{"almacen": "mongo"}`, una ficha sin el campo no matcheaba:
    la migración movía cero, y el panel informaba `en_mongo: 0` — que se lee como
    "ya está". Un filtro que falla hacia "no queda nada pendiente" es peor que
    uno que falla a los gritos.
    """
    datos = _ficha_vieja(base)
    assert corre(archivos.conteo())["en_mongo"] == 1

    salida = corre(archivos.migrar_lote())
    assert salida["migrados"] == 1
    assert salida["en_mongo"] == 0
    fila = base.envios_archivos.filas[0]
    assert "contenido" not in fila
    assert s3.objetos[(BUCKET, fila["clave"])][0] == datos


def test_boto3_no_corre_en_el_bucle_de_eventos(base, s3):
    """La propiedad que el módulo declara como su razón de ser.

    Un `put_object` de 4 MB adentro del loop congela las cotizaciones, los cobros
    y la cola del operador por lo que tarde la red. Sin este test, sacar los dos
    saltos a un hilo dejaba la suite entera en verde.
    """
    ficha = corre(archivos.guardar(_jpg(), envio_id="env_1", user_id="u1",
                                   clase="comprobante"))
    corre(archivos.leer(ficha["asset_id"], envio_id="env_1"))
    assert s3.hilos, "no se llamó al bucket"
    assert not any(s3.hilos), "hay llamadas de boto3 en el hilo del bucle de eventos"


def test_una_caida_de_mongo_no_es_una_foto_que_no_existe(base, s3):
    """El agujero simétrico al que el PR cierra con el almacén.

    Si `leer` devuelve None cuando falla la consulta, la ruta contesta 404 y el
    operador va a buscar un comprobante que sí está cargado — y encima le pasa a
    las fotos NO migradas, que son las que no dependen del bucket.
    """
    class _Rota:
        async def find_one(self, *a, **k):
            raise RuntimeError("motor caído")

    class _BaseRota:
        envios_archivos = _Rota()

    ficha = corre(archivos.leer("ast_1", envio_id="env_1", db=_BaseRota()))
    assert ficha is not None
    assert ficha["error"] == "base"
    with pytest.raises(archivos.ArchivoRechazado) as e:
        archivos.exigir_bytes(ficha)
    assert e.value.http == 503


def test_la_ficha_guarda_el_bucket_y_lee_de_ese(base, s3, monkeypatch):
    """La ficha tiene que llevar la dirección COMPLETA, no la mitad de adentro.

    El bucket sale de una variable de entorno que alguien puede cambiar: se migra
    contra `-test`, se valida, se apunta al definitivo. Si la clave fuera lo
    único guardado, todo lo migrado quedaría ilegible — y los bytes de Mongo ya
    se borraron.
    """
    ficha = corre(archivos.guardar(_jpg(), envio_id="env_1", user_id="u1",
                                   clase="comprobante"))
    assert ficha["bucket"] == BUCKET
    monkeypatch.setenv(almacen.VAR_BUCKET, "risapp-envios-nuevo")
    leida = corre(archivos.leer(ficha["asset_id"], envio_id="env_1"))
    assert leida["contenido"] == _jpg(), "se leyó del bucket configurado, no del suyo"


def test_un_objeto_que_no_existe_se_distingue_de_una_caida(base, s3):
    ficha = corre(archivos.guardar(_jpg(), envio_id="env_1", user_id="u1",
                                   clase="comprobante"))
    s3.objetos.clear()

    class _NoSuchKey(RuntimeError):
        response = {"Error": {"Code": "NoSuchKey"}}

    def _explota(**k):
        raise _NoSuchKey("no está")

    s3.get_object = _explota
    leida = corre(archivos.leer(ficha["asset_id"], envio_id="env_1"))
    assert leida["error"] == "ausente"


def test_una_lectura_parcial_no_se_sirve(base, s3):
    """El otro caso que la verificación de hash existe para atrapar."""
    ficha = corre(archivos.guardar(_jpg(b"un comprobante largo"), envio_id="env_1",
                                   user_id="u1", clase="comprobante"))
    s3.devuelve_parcial = True
    leida = corre(archivos.leer(ficha["asset_id"], envio_id="env_1"))
    assert leida["error"] == "integridad"


def test_un_archivo_que_falla_siempre_no_traba_la_cola(base, monkeypatch):
    """Sin sacarlo de la cola, vuelve primero en TODOS los lotes.

    El admin clickea, ve `migrados: 0`; clickea otra vez, ve `migrados: 0`; y la
    migración no avanza nunca más sin entrar a Mongo a mano — que es justo lo que
    una migración "por lotes y reanudable" existe para evitar.
    """
    fichas, falso = _preparar_migracion(monkeypatch, cantidad=2)
    base.envios_archivos.filas[0]["contenido"] = _jpg(b"corrupto")

    primero = corre(archivos.migrar_lote(limite=1))
    assert primero["sospechosos"] == 1
    segundo = corre(archivos.migrar_lote(limite=1))
    assert segundo["migrados"] == 1, "el corrupto sigue tapando la cola"
    assert corre(archivos.conteo())["en_mongo"] == 0
    assert corre(archivos.conteo())["con_problema"] == 1
    almacen.olvidar_cliente()


def test_dos_lotes_a_la_vez_no_se_pisan(base, monkeypatch):
    """El `$exists` del filtro del update es lo que hace que el segundo no pise
    la clave que dejó el primero. Corriendo uno después del otro no se prueba."""
    fichas, falso = _preparar_migracion(monkeypatch, cantidad=4)

    async def _dos():
        return await asyncio.gather(archivos.migrar_lote(limite=4),
                                    archivos.migrar_lote(limite=4))

    a, b = corre(_dos())
    assert a["migrados"] + b["migrados"] == 4
    assert a["fallidos"] == b["fallidos"] == 0
    assert corre(archivos.conteo())["en_mongo"] == 0
    for fila in base.envios_archivos.filas:
        assert fila["almacen"] == "r2" and "contenido" not in fila
    almacen.olvidar_cliente()


def test_el_lote_se_corta_por_tiempo_y_lo_dice(base, monkeypatch):
    """Una petición de cinco minutos la corta el proxy, y el admin ve un error
    sobre trabajo que en realidad se hizo."""
    fichas, falso = _preparar_migracion(monkeypatch, cantidad=3)
    monkeypatch.setattr(archivos, "MIGRACION_SEGUNDOS_MAX", -1)
    salida = corre(archivos.migrar_lote(limite=3))
    assert salida["parcial"] is True
    assert salida["migrados"] == 0
    assert salida["en_mongo"] == 3, "no se perdió nada: sigue todo pendiente"
    almacen.olvidar_cliente()


def test_estado_no_revienta_con_un_endpoint_mal_escrito(monkeypatch):
    """Es la pantalla a la que entra el admin cuando la configuración está mal.
    Que devuelva un 500 ahí es dejarlo sin el único diagnóstico que tiene."""
    for nombre, valor in VARIABLES.items():
        monkeypatch.setenv(nombre, valor)
    monkeypatch.setenv(almacen.VAR_ENDPOINT, "https://[mal")
    estado = almacen.estado()
    assert estado["activo"] is False
    assert estado["endpoint_host"] is None


def test_leer_exige_el_envio(base, s3):
    """Antes tenía default `None`, y con `None` el filtro se relajaba solo."""
    ficha = corre(archivos.guardar(_jpg(), envio_id="env_1", user_id="u1",
                                   clase="comprobante"))
    with pytest.raises(TypeError):
        corre(archivos.leer(ficha["asset_id"]))
    assert corre(archivos.leer(ficha["asset_id"], envio_id="")) is None


def test_ya_estaba_no_cuenta_como_migrado(base, monkeypatch):
    """El contador que el admin usa para saber si avanzó no puede inflarse."""
    fichas, falso = _preparar_migracion(monkeypatch, cantidad=1)
    corre(archivos.migrar_lote())
    # Se vuelve a poner en la cola sin bytes: es el estado que deja una carrera.
    base.envios_archivos.filas[0]["almacen"] = "mongo"
    salida = corre(archivos.migrar_lote())
    assert salida["migrados"] == 0
    assert salida["ya_estaban"] == 1
    almacen.olvidar_cliente()


def test_un_contenido_de_tipo_raro_no_tumba_el_lote(base, monkeypatch):
    fichas, falso = _preparar_migracion(monkeypatch, cantidad=2)
    base.envios_archivos.filas[0]["contenido"] = object()
    salida = corre(archivos.migrar_lote())
    assert salida["fallidos"] == 1
    assert salida["migrados"] == 1, "el segundo se migró igual"
    almacen.olvidar_cliente()


def test_pil_tampoco_corre_en_el_bucle_de_eventos(base, s3, monkeypatch):
    """Decodificar y recodificar 8 MB con PIL es CPU pura, cientos de
    milisegundos, y adentro del bucle congela las cotizaciones y los cobros de
    todo el proceso. Es el mismo argumento que vale para boto3."""
    hilos = []
    original = archivos.sin_exif

    def _espia(datos, tipo):
        hilos.append(threading.current_thread() is threading.main_thread())
        return original(datos, tipo)

    monkeypatch.setattr(archivos, "sin_exif", _espia)
    corre(archivos.guardar(_jpg(), envio_id="env_1", user_id="u1",
                           clase="comprobante"))
    assert hilos == [False], "sin_exif corrió en el hilo del bucle de eventos"


def test_si_no_se_puede_contar_el_panel_dice_no_se_y_no_cero(base, s3):
    """"Cero pendientes" y "no pude contar" se leen igualísimo en una pantalla, y
    del primero se concluye que la migración terminó."""
    class _Rota:
        async def count_documents(self, *a, **k):
            raise RuntimeError("motor caído")

    class _BaseRota:
        envios_archivos = _Rota()

    salida = corre(archivos.conteo(db=_BaseRota()))
    assert salida == {"en_mongo": None, "en_almacen": None, "con_problema": None}


def test_una_excepcion_inesperada_no_se_lleva_puesto_el_lote(base, monkeypatch):
    """`_migrar_una` promete no lanzar. El día que deje de cumplirlo —un tipo
    nuevo en un campo, una librería que cambia— la excepción no puede tirar el
    lote entero y perder la cuenta de lo que sí se movió."""
    fichas, falso = _preparar_migracion(monkeypatch, cantidad=2)
    original = archivos._migrar_una
    primera = {"pasó": False}

    async def _rompe(base_, ficha, ahora):
        if not primera["pasó"]:
            primera["pasó"] = True
            raise RuntimeError("algo que nadie previó")
        return await original(base_, ficha, ahora)

    monkeypatch.setattr(archivos, "_migrar_una", _rompe)
    salida = corre(archivos.migrar_lote(limite=2))
    assert salida["fallidos"] == 1
    assert salida["migrados"] == 1, "el segundo archivo se migró igual"
    almacen.olvidar_cliente()
