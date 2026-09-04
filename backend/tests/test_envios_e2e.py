"""
El circuito completo, contra la APLICACION DE VERDAD.

POR QUE ESTE ARCHIVO EXISTE
    Todos los demas tests del modulo corren contra dobles de Mongo escritos a
    mano en este mismo repositorio. Son buenos dobles —entienden proyecciones,
    `$ne`, `$inc` con Decimal128, indices unicos, y hasta ceden el control para
    que `asyncio.gather` intercale de verdad— pero son mios, y un doble solo
    falla donde su autor penso que podia fallar.

    Hay una clase entera de defecto que NINGUNO de ellos puede ver, porque vive
    afuera de la funcion que prueban:

      - Dos rutas que se pisan por el orden en que se declararon.
      - Un `Decimal128` que sale de la base y el encoder de FastAPI no sabe
        serializar. Un solo campo asi tumba una respuesta entera.
      - Un modelo Pydantic que rechaza el cuerpo que la pantalla manda.
      - Un `multipart/form-data` mal armado.
      - Una dependencia que no es la que uno cree que es —este proyecto tiene
        `routes/dependencies.py` DUPLICADO entero, y Python usa la segunda copia
        en silencio.
      - Un `$push` sobre un documento donde el campo no existe todavia.

    Acá se levanta la aplicacion FastAPI de verdad, con su ruteo, su inyeccion
    de dependencias, su validacion y su serializacion, contra una base con
    semantica de Mongo real (mongomock). Lo unico que se sustituye es la
    autenticacion, que es lo correcto sustituir: la sesion no es lo que se esta
    probando, y el rol si —porque de el dependen cuatro rutas que mueven plata.

QUE RECORRE
    Los nueve pasos del MERGE.md, en orden y sobre el mismo envio: configurar el
    modulo entero por sus propias rutas de panel, cotizar, confirmar, cargar el
    comprobante, verificarlo (aca se cobra), marcar disponible, retirar por lote,
    repesar, despachar y entregar. Mas el seguimiento publico, que se revisa
    campo por campo buscando datos personales.
"""
import asyncio
import importlib.util
import io
import os
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

# Este archivo es un RECORRIDO: cada test continúa el envío que dejó el
# anterior. `tests/conftest.py` mira esta bandera y devuelve sus tests al orden
# de definición aunque la corrida esté aleatorizada.
ORDEN_IMPORTA = True

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

mongomock_motor = pytest.importorskip(
    "mongomock_motor",
    reason="El E2E necesita una base con semántica de Mongo real.")


def _enseñarle_decimal128_a_mongomock():
    """MongoDB trata `Decimal128` como un número. Mongomock no.

    NO es un problema del producto, y por eso se arregla acá y no allá. El saldo
    se guarda como `Decimal128` —así lo guarda el resto de la app— y el débito
    atómico hace dos cosas con él que el servidor de verdad resuelve sin
    pestañear:

        {"balance_ris": {"$gte": Decimal128(monto)}}     comparar
        {"$inc": {"balance_ris": Decimal128(-monto)}}    sumar

    Mongomock levanta "'>=' not supported" en la primera y "unsupported operand
    type(s) for +" en la segunda. Sin esto el guard del débito falla SIEMPRE, y
    el E2E daría por bueno un mundo donde ningún cobro se puede pagar — que es
    peor que no probarlo.

    Se le enseña al TIPO, no a mongomock: `bson.Decimal128` es Python puro, y
    darle aritmética y orden es exactamente lo que hace el servidor. Sale una
    línea por operación en vez de tres parches contra los internos de una
    librería de tests.

    Y que quede escrito, porque es lo que este archivo vino a hacer visible:
    **el cobro del módulo depende de que la base sume y ordene `Decimal128`.**
    Es un requisito real sobre MongoDB, y no había un solo test que lo dijera.
    """
    from decimal import Decimal
    from bson.decimal128 import Decimal128

    def valor(x):
        if isinstance(x, Decimal128):
            return x.to_decimal()
        if isinstance(x, float):
            return Decimal(str(x))
        if isinstance(x, (int, Decimal)):
            return Decimal(x)
        return None

    def binaria(nombre, operacion, invertida=False):
        def metodo(self, otro):
            a, b = valor(self), valor(otro)
            if a is None or b is None:
                return NotImplemented
            resultado = operacion(b, a) if invertida else operacion(a, b)
            return (Decimal128(resultado) if isinstance(resultado, Decimal)
                    else resultado)
        metodo.__name__ = nombre
        return metodo

    # Se aplica UNA vez. pytest importa todos los módulos de test en la
    # colección, así que sin esta guarda una segunda importación anidaría
    # lambdas sobre `_get_compare_type`.
    if getattr(Decimal128, "_ris_app_parchado", False):
        return
    Decimal128._ris_app_parchado = True

    import operator as op
    for nombre, fn in (("__add__", op.add), ("__sub__", op.sub),
                       ("__mul__", op.mul), ("__truediv__", op.truediv),
                       ("__lt__", op.lt), ("__le__", op.le),
                       ("__gt__", op.gt), ("__ge__", op.ge)):
        setattr(Decimal128, nombre, binaria(nombre, fn))
    for nombre, fn in (("__radd__", op.add), ("__rsub__", op.sub),
                       ("__rmul__", op.mul)):
        setattr(Decimal128, nombre, binaria(nombre, fn, invertida=True))

    # Y el orden de tipos: `Decimal128` es un número y va en el mismo grupo, que
    # es lo que hace que el type bracketing de Mongo no lo descarte contra un int.
    import mongomock.filtering as filtrado
    original_tipo = filtrado._get_compare_type
    filtrado._get_compare_type = (
        lambda val: 10 if isinstance(val, Decimal128) else original_tipo(val))

    # LO QUE ESTE PARCHE NO HACE, a propósito: `__eq__`. El que trae `bson`
    # compara la representación binaria, así que `Decimal128("2.00")` no es
    # igual a `Decimal128("2.0")` aunque ahora `<=` y `>=` digan que sí. MongoDB
    # resuelve las dos numéricamente. Se deja como está porque ninguna query del
    # módulo hace `$eq` ni `$in` sobre un monto —el débito compara con `$gte` y
    # suma con `$inc`, y todo lo demás pasa por `services/money.py`, que
    # convierte a `Decimal` antes de tocar nada—. Si alguien escribe esa query,
    # que la escriba con este comentario a la vista: acá el E2E daría verde
    # sobre un comportamiento que producción no tiene.


_enseñarle_decimal128_a_mongomock()


# ─── La base: una de verdad, no un doble mío ──────────────────────────────

def _base_nueva():
    return mongomock_motor.AsyncMongoMockClient()["ris_app_e2e"]


DB = _base_nueva()


def _exigir_dependencias_de_verdad(deps, envios, envios_admin):
    """Que las rutas cuelguen de ESTAS dependencias, y no de otro objeto.

    La comprobación que importa no es que `deps` sea real —lo acabo de ejecutar
    yo desde el archivo, no puede no serlo— sino que los módulos de rutas hayan
    quedado atados a él. Si el swap de `sys.modules` se rompe, las rutas se atan
    a un doble que devuelve `None`, ninguna ruta falla —las deja pasar a todas—
    y los tests de rol de este archivo seguirían en verde diciendo que un
    `agent` no puede cobrar cuando en realidad nadie miró el rol.
    """
    for modulo in (envios, envios_admin):
        for nombre in ("get_current_user", "get_admin_user", "get_crm_user",
                       "get_super_admin", "get_verified_user"):
            atada = getattr(modulo, nombre, None)
            if atada is None:
                continue          # no todas las rutas usan las cinco
            assert atada is getattr(deps, nombre), (
                f"{modulo.__name__} usa un {nombre} que no es el de "
                "routes/dependencies.py. Algún otro test dejó un doble en "
                "sys.modules y este archivo estaría probando contra roles que "
                "nadie comprueba.")


def _preparar():
    """Levanta la aplicación real. Se hace una sola vez por sesión de tests."""
    # `database.db` tiene que apuntar a la base falsa ANTES de que nada lo
    # importe: media docena de módulos hacen `from database import db` al
    # importarse y capturan el objeto en ese momento.
    from conftest import usar_base
    usar_base(DB)

    if "pywebpush" not in sys.modules:                        # pragma: no cover
        stub = types.ModuleType("pywebpush")
        stub.WebPushException = type("WebPushException", (Exception,), {})
        stub.webpush = lambda *a, **k: None
        sys.modules["pywebpush"] = stub

    # El paquete `routes` vacío: `routes/__init__.py` importa la aplicación
    # entera, incluido Google Drive, que en este entorno no compila. Se cargan
    # los tres módulos de rutas por su path, con las dependencias REALES.
    if "routes" not in sys.modules:
        paquete = types.ModuleType("routes")
        paquete.__path__ = [os.path.join(_BACKEND, "routes")]
        sys.modules["routes"] = paquete

    # ─────────────────────────────────────────────────────────────────────
    # Y ACA VA LA PARTE QUE NO ES OBVIA, que es la que este archivo aprendió
    # de sí mismo.
    #
    # `sys.modules` es uno solo para toda la corrida de pytest. Otros tests del
    # módulo —nómina, transportistas— registran un `routes.dependencies` FALSO,
    # donde `get_super_admin` y las otras cuatro son `lambda: None`, y cargan
    # `routes.envios_admin` contra él. Todos guardan con `if not in sys.modules`,
    # así que gana el que importa primero, y por orden alfabético ese no soy yo.
    #
    # Corriendo `pytest tests/test_envios_e2e.py` pasaba entero. Corriendo la
    # suite completa, este archivo recibía las dependencias de mentira: los roles
    # dejaban de comprobarse y `admin` llegaba como `None` a las rutas. Es
    # EXACTAMENTE el defecto que este archivo vino a cazar —una dependencia que
    # no es la que uno cree—, encontrado adentro del cazador.
    #
    # Por eso se cargan los módulos con `sys.modules` puesto en su estado real
    # durante la carga, y se restaura lo que hubiera después: mi app se queda con
    # los objetos de verdad, los otros archivos con los suyos, y ninguno de los
    # dos depende de quién importó primero.
    NOMBRES = ("routes.dependencies", "routes.envios", "routes.envios_admin")
    guardado = {n: sys.modules.get(n) for n in NOMBRES}
    for nombre in NOMBRES:
        sys.modules.pop(nombre, None)

    def cargar(nombre):
        completo = f"routes.{nombre}"
        spec = importlib.util.spec_from_file_location(
            completo, os.path.join(_BACKEND, "routes", f"{nombre}.py"))
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[completo] = modulo
        setattr(sys.modules["routes"], nombre, modulo)
        spec.loader.exec_module(modulo)
        return modulo

    try:
        deps = cargar("dependencies")
        envios = cargar("envios")
        envios_admin = cargar("envios_admin")
    finally:
        # Simétrico en las dos ramas. `from routes import envios_admin` resuelve
        # por ATRIBUTO del paquete antes que por `sys.modules`, así que restaurar
        # solo el diccionario deja el paquete apuntando a mis módulos cuando este
        # archivo cargó primero — el mismo agujero, un nivel más arriba.
        for nombre, modulo in guardado.items():
            corto = nombre.split(".", 1)[1]
            if modulo is None:
                sys.modules.pop(nombre, None)
                if hasattr(sys.modules["routes"], corto):
                    delattr(sys.modules["routes"], corto)
            else:
                sys.modules[nombre] = modulo
                setattr(sys.modules["routes"], corto, modulo)

    # Y que quede comprobado, no confiado: si mañana alguien vuelve a compartir
    # el módulo, esto falla acá y no dentro de un test de negocio.
    _exigir_dependencias_de_verdad(deps, envios, envios_admin)

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(envios.router, prefix="/api")
    app.include_router(envios_admin.router, prefix="/api")

    # Lo único sustituido es QUIEN SOS, y nada más.
    #
    # `get_current_user` y solo esa. Las otras cuatro —verified, crm, admin,
    # super_admin— cuelgan de ella con `Depends`, así que FastAPI resuelve la
    # sustitución también adentro de ellas y las comprobaciones de rol REALES
    # siguen corriendo.
    #
    # Sustituirlas todas, que fue lo primero que hice, anula justamente lo que
    # este archivo quiere probar: con eso un rol `agent` emitía el cobro inicial
    # y el test lo daba por bueno.
    from models.user import User
    actual = {"user": None}

    def _quien():
        if actual["user"] is None:
            from fastapi import HTTPException
            raise HTTPException(401, "sin sesión")
        return actual["user"]

    app.dependency_overrides[deps.get_current_user] = _quien
    return app, actual, User


APP, ACTUAL, User = _preparar()

from fastapi.testclient import TestClient                             # noqa: E402

CLIENTE = TestClient(APP)

AHORA = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _apuntar_la_base_a_la_mia():
    """`database.db` es un proxy global, y lo apunta el ULTIMO fixture que corrió.

    Este archivo lo apunta una vez al importarse, que alcanza para correrlo solo
    y no alcanza para nada más: cualquier otro test del módulo que instale su
    doble deja el proxy mirando ahí, y estos tests siguen contra una base que no
    es la suya. Corriendo el archivo solo pasaba; en la suite completa fallaba
    entero — la peor forma de fallar, porque el que rompe no es el que se ve roto.
    """
    from conftest import usar_base
    usar_base(DB)

    # El caché del catálogo es un dict de módulo, compartido por toda la
    # corrida. Hoy las rutas del panel lo invalidan solas después de cada
    # escritura, así que esto no arregla nada — y por eso mismo va: para que
    # este archivo no dependa de que sigan haciéndolo.
    from services import envios_catalogo
    envios_catalogo.invalidar_cache()

    # Y el almacén de fotos, en Mongo. Si la máquina que corre los tests tiene
    # credenciales de R2 en el entorno, el módulo escribiría las fotos de prueba
    # en un bucket de verdad.
    guardadas = {k: os.environ.pop(k) for k in list(os.environ)
                 if k.startswith("ENVIOS_R2_")}

    # Y la sesión arranca vacía: los dos tests del seguimiento público dejan
    # `ACTUAL["user"]` en None a propósito, y hoy el siguiente funciona solo
    # porque llama a `como(...)` antes de tocar nada. Eso es suerte, no diseño.
    ACTUAL["user"] = None
    try:
        yield
    finally:
        os.environ.update(guardadas)


def como(rol: str, user_id: str = None, verificacion: str = "verified",
         permisos=None):
    """Quién manda la petición. El rol importa: cuatro rutas lo miran.

    `verificacion` importa en otras cinco: las del usuario cuelgan de
    `get_verified_user`, no de `get_current_user`, y sin KYC el formulario de
    envío es carga de datos de terceros abierta a cualquiera.

    `permisos` llega con TODO el catálogo por defecto. Este archivo prueba la
    operación de envíos y la separación de ROLES, no el reparto de permisos
    —eso tiene su propio archivo—, así que darle la lista completa deja los
    treinta y cuatro casos midiendo lo que vinieron a medir. Pasar una lista
    corta acá alcanza para probar lo contrario.
    """
    from services.permisos import CATALOGO
    ACTUAL["user"] = User(
        user_id=user_id or f"usr_{rol}",
        email=f"{rol}@risappbr.com",
        name="Persona De Prueba",
        role=rol,
        permissions=sorted(CATALOGO) if permisos is None else list(permisos),
        verification_status=verificacion,
    )
    return ACTUAL["user"]


def corre(coro):
    return asyncio.run(coro)


# ─── Datos de arranque ────────────────────────────────────────────────────

def _jpeg(color=(200, 30, 30)):
    """Un JPEG de verdad: el módulo mira los BYTES, no la extensión."""
    from PIL import Image
    imagen = Image.new("RGB", (32, 24), color)
    salida = io.BytesIO()
    imagen.save(salida, format="JPEG")
    return salida.getvalue()


TARIFA = {
    "modo_tarifa": "peso", "moneda": "RIS",
    "regla_peso": {"divisor": 5000, "escalon_kg": "0.5", "minimo_kg": "1.0",
                   "umbral_cubado_kg": None},
    "escalones_peso": [
        {"desde_kg": "0.00", "hasta_kg": "1.00", "precio": "45.00"},
        {"desde_kg": "1.00", "hasta_kg": "3.00", "precio": "78.00"},
        {"desde_kg": "3.00", "hasta_kg": "5.00", "precio": "112.00"},
        {"desde_kg": "5.00", "hasta_kg": "10.00", "precio": "186.00"},
        # Una banda fina arriba de todo, para que exista una diferencia de
        # repesaje CHICA pero real (1.00, contra una tolerancia de 2.00). Sin
        # ella, la rama «sin_ajuste» solo se podía probar con diferencia CERO,
        # que es cierta para cualquier tolerancia —incluida una tolerancia de
        # cero, que es exactamente el defecto que esa rama tuvo—.
        {"desde_kg": "10.00", "hasta_kg": "10.50", "precio": "187.00"},
    ],
    "adicional_por_kg": "9.50", "adicional_por_m3": None, "tarifa_minima": "35.00",
    "escalones_volumen": [],
    "margen": {"tipo": "porcentual", "valor": "0"},
    "sobrecargos": [], "descuentos_cantidad": [], "recargos_temporada": [],
    "redondeo_final": {"decimales": 2, "multiplo": None},
    "limites_propios": {"peso_max_kg": "30", "lado_max_cm": "100",
                        "suma_lados_max_cm": "200", "valor_declarado_max": "5000"},
    "prohibidos": ["Armas y municiones", "Líquidos inflamables"],
}


PUNTO_ORIGEN = {
    "nombre": "Agencia Centro", "cep": "69355000", "ciudad": "Pacaraima", "uf": "RR",
    "modalidad": "caixa_postal", "caixa_postal": "123", "direccion": None,
    "razon_social": "RIS App LTDA",
    "plantilla_direccion": ("{razon_social}\nA/C {retirador_nombre}\n{linea_agencia}\n"
                           "{ciudad} - {uf}\nCEP {cep}"),
}

CONTENIDO = {
    "prohibidos": ["Armas y municiones", "Líquidos inflamables", "Dinero en efectivo"],
    "terminos_version": "2026-08-a",
    "texto_estimado": ("El precio que ves es un estimado sobre lo que declaraste. "
                       "Se confirma al repesar en Pacaraima con balanza propia."),
    "descripcion_min_caracteres": 10,
}

OPERACION = {
    "tolerancia_ajuste_ris": "2.00", "ttl_cotizacion_horas": 48,
    "ttl_espera_postagem_dias": 30, "plazo_pago_pendiente_dias": 7,
    "dias_guarda": 30, "alertas_guarda_dias": [7, 15, 25],
    "banda_variacion_pct": "0.15",
}

TRP_BRASIL = {
    "codigo": "TRP-BR1", "nombre": "Transporte del Norte", "rol": "brasil",
    "activo": True, "orden": 1, "moneda": "BRL",
    "regla_peso": {"divisor": 6000, "escalon_kg": "0.5", "minimo_kg": "0.3",
                   "umbral_cubado_kg": None},
    "limites": {"peso_max_kg": "30", "lado_max_cm": "100", "suma_lados_max_cm": "200",
                "largo_min_cm": None, "ancho_min_cm": None, "alto_min_cm": None,
                "suma_lados_min_cm": None, "valor_declarado_max": None},
    "plantilla_rastreo": None, "fuente_referencia": None, "notas": None,
    "cuenta_bancaria": None,
}

TRP_VENEZUELA = {**TRP_BRASIL, "codigo": "TRP-VE1", "nombre": "Encomiendas del Sur",
                 "rol": "venezuela", "orden": 2, "moneda": "USD",
                 "regla_peso": {"divisor": 5000, "escalon_kg": "1", "minimo_kg": "1",
                                "umbral_cubado_kg": None}}

AGENCIA = {"codigo": "001", "nombre": "Santa Elena Centro", "estado": "Bolívar",
           "ciudad": "Santa Elena", "direccion": "Av. Perimetral",
           "zona": "GranSabana", "codigo_postal": None, "activa": True,
           "es_punto_entrega": True}

# Las matrices de referencia, cargadas a mano desde el panel —que es como se
# cargan de verdad: no hay contrato ni API con ningún transportista—.
#
# El precio del tramo venezolano está puesto EXACTAMENTE igual al total que
# cobra RIS App (112.00) y no por casualidad: es el único valor con el que
# «la referencia no entra en el total» se puede probar de verdad. Con cualquier
# otro número, un sistema que sumara la referencia daría un total distinto por
# accidente y el test pasaría sin haber mirado nada.
REFERENCIAS = (("br", "SP", "120.00", "BRL"),
               ("ve", "GranSabana", "112.00", "USD"))

COLABORADOR = {"nombre": "Ana Pérez", "cpf": "111.222.333-44",
               "telefono": "+55 95 99999-0000", "activo": True,
               "autorizado_desde": None, "autorizado_hasta": None, "notas": ""}

ESTADO = {}          # lo que va quedando del recorrido


def _saldo(user_id="usr_user", monto="500.00"):
    from bson.decimal128 import Decimal128
    from decimal import Decimal
    corre(DB.users.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "balance_ris": Decimal128(Decimal(monto)),
                  "email": "cliente@risappbr.com", "role": "user",
                  "verification_status": "verified"}},
        upsert=True))


def _saldo_de(user_id="usr_user"):
    from decimal import Decimal
    doc = corre(DB.users.find_one({"user_id": user_id})) or {}
    bruto = doc.get("balance_ris")
    return bruto.to_decimal() if hasattr(bruto, "to_decimal") else Decimal(str(bruto or 0))


def _todas_las_claves(dato, camino=""):
    """Todas las claves del árbol, no solo las de arriba."""
    salida = []
    if isinstance(dato, dict):
        for clave, valor in dato.items():
            salida.append(f"{camino}{clave}")
            salida += _todas_las_claves(valor, f"{camino}{clave}.")
    elif isinstance(dato, (list, tuple)):
        for elemento in dato:
            salida += _todas_las_claves(elemento, camino)
    return salida


def _ok(respuesta, esperado=200):
    assert respuesta.status_code == esperado, (
        f"{respuesta.request.method} {respuesta.request.url.path} → "
        f"{respuesta.status_code}: {respuesta.text[:400]}")
    if not respuesta.content:
        return None
    if "json" not in (respuesta.headers.get("content-type") or ""):
        return respuesta.content          # una foto, por ejemplo
    return respuesta.json()


# ─── Paso 1: configurar el módulo entero, por sus propias rutas ───────────

def test_01_el_modulo_arranca_diciendo_que_no_esta_disponible():
    """Un sistema recién instalado no es un error: contesta `disponible: false`.

    Y **no dice por qué**: el diagnóstico de configuración es interno.
    """
    como("user")
    datos = _ok(CLIENTE.get("/api/envios/limites"))
    assert datos["disponible"] is False
    assert datos["prohibidos"], "la lista de prohibidos no puede ir vacía en el fallback"
    # El detalle es interno. Afuera va un solo mensaje, no las frases del panel.
    assert len(datos["faltantes"]) == 1
    assert "transportista" not in " ".join(datos["faltantes"]).lower()


def test_02_el_panel_dice_que_falta_y_en_que_orden():
    como("super_admin")
    estado = _ok(CLIENTE.get("/api/admin/envios/estado"))
    assert estado["puede_operar"] is False
    assert estado["siguiente"] == "punto_origen"
    assert [p["clave"] for p in estado["pasos"]][0] == "punto_origen"


def test_03_se_configura_todo_desde_el_panel():
    """Los siete pasos del MERGE.md, por las rutas de verdad."""
    como("super_admin")

    _ok(CLIENTE.put("/api/admin/envios/config/punto_origen", json=PUNTO_ORIGEN))
    _ok(CLIENTE.put("/api/admin/envios/config/contenido", json=CONTENIDO))
    _ok(CLIENTE.put("/api/admin/envios/config/operacion", json=OPERACION))

    br = _ok(CLIENTE.post("/api/admin/envios/transportistas", json=TRP_BRASIL))
    ve = _ok(CLIENTE.post("/api/admin/envios/transportistas", json=TRP_VENEZUELA))
    ESTADO["trp_br"] = br["transportista_id"]
    ESTADO["trp_ve"] = ve["transportista_id"]

    _ok(CLIENTE.post(f"/api/admin/envios/transportistas/{ESTADO['trp_ve']}/agencias",
                     json=AGENCIA))

    for lado, clave, precio, moneda in REFERENCIAS:
        _ok(CLIENTE.post("/api/admin/envios/envios/observado/aprobar", json={
            "transportista_id": ESTADO[f"trp_{lado}"], "clave": clave,
            "hasta_kg": "30", "precio": precio, "moneda": moneda}))

    colaborador = _ok(CLIENTE.post("/api/admin/envios/retiro/colaboradores",
                                   json=COLABORADOR))
    ESTADO["colaborador"] = colaborador["valor"]["colaborador_id"]
    turno = _ok(CLIENTE.put("/api/admin/envios/retiro/turno",
                            json={"colaborador_id": ESTADO["colaborador"]}))
    assert turno["de_turno"] == "Ana Pérez"
    assert "Ana Pérez" in turno["vista_previa"]["texto_copiable"]

    _ok(CLIENTE.put("/api/admin/envios/tarifas/borrador", json=TARIFA))
    publicada = _ok(CLIENTE.post("/api/admin/envios/tarifas/publicar",
                                 json={"nota": "Primera versión de precios."}))
    ESTADO["tarifa"] = publicada["version_id"]


def test_04_ahora_el_modulo_esta_disponible():
    como("super_admin")
    estado = _ok(CLIENTE.get("/api/admin/envios/estado"))
    assert estado["puede_operar"] is True, [
        p for p in estado["pasos"] if p["estado"] != "listo"]

    como("user")
    limites = _ok(CLIENTE.get("/api/envios/limites"))
    assert limites["disponible"] is True
    assert limites["tarifa_version"] == ESTADO["tarifa"]
    assert limites["descripcion_min_caracteres"] == 10


# ─── Paso 2: el usuario cotiza y confirma ─────────────────────────────────

PEDIDO = {
    "origen": {"cep": "01310100", "ciudad": "São Paulo", "uf": "SP"},
    "destino": {
        "transportista_id": None, "agencia_codigo": "001", "codigo_postal": None,
        "destinatario": {"nombre": "Luisa Marín", "documento": "V-12345678",
                         "telefono": "+58 414 1234567"},
    },
    "paquete": {"peso_kg": "2.30", "largo_cm": "40", "ancho_cm": "30", "alto_cm": "20",
                "contenido_descripcion": "Ropa de bebé y dos pares de zapatillas",
                "valor_declarado_brl": "180.00"},
    "modalidad_flete": "destino",
}


def test_05_cotizar_no_mueve_un_centavo_y_separa_lo_que_cobra_ris_app():
    como("user")
    _saldo("usr_user", "500.00")
    antes = _saldo_de()

    pedido = {**PEDIDO}
    pedido["destino"] = {**PEDIDO["destino"], "transportista_id": ESTADO["trp_ve"]}
    datos = _ok(CLIENTE.post("/api/envios/cotizar", json=pedido))

    assert _saldo_de() == antes, "cotizar movió saldo"
    ESTADO["envio_id"] = datos["envio_id"]
    ESTADO["terminos"] = datos["terminos_version"]
    ESTADO["total_estimado"] = datos["a_pagar_en_risapp"]["total_estimado_ris"]

    # LA REGLA QUE MAS IMPORTA: lo que cobra RIS App va en su bloque, y las
    # referencias en otro. Ninguna referencia entra en el total.
    #
    # Y se prueba como EXCLUSION DE LA SUMA, no comparando números. La versión
    # anterior de este test decía `monto != total` con las dos referencias en
    # `None` —porque nadie había cargado las matrices—, así que el cuerpo del
    # `if` no se ejecutaba nunca y la regla central del módulo era texto muerto.
    from decimal import Decimal
    bloque = datos["a_pagar_en_risapp"]
    total = Decimal(bloque["total_estimado_ris"])
    assert total == Decimal(bloque["subtotal_ris"]) + Decimal(bloque["margen_ris"]), (
        "el total lleva algo que no es el servicio de RIS App")

    assert len(datos["referencias"]) == 2, "faltó alguna referencia"
    for r in datos["referencias"]:
        assert r["facturable"] is False
        assert r["monto"] is not None, (
            f"la referencia {r} salió sin monto: sin eso, la regla no se prueba")
    # El tramo venezolano vale 112.00, que es el total exacto. Un sistema que lo
    # sumara daría 224.00 acá.
    assert total == Decimal("112.00")
    assert datos["es_estimado"] is True
    assert datos["aviso_estimado"], "el aviso del estimado va siempre, sin condición"
    assert datos["retiro"]["texto_copiable"].startswith("RIS App LTDA")
    assert "Ana Pérez" in datos["retiro"]["texto_copiable"]

    # Y la respuesta serializa: un Decimal128 suelto acá tumba la ruta entera.
    assert isinstance(datos["a_pagar_en_risapp"]["total_estimado_ris"], str)


def test_06_confirmar_tampoco_cobra():
    como("user")
    antes = _saldo_de()
    datos = _ok(CLIENTE.post("/api/envios/crear", json={
        "envio_id": ESTADO["envio_id"],
        "declaracion": {"contenido_aceptado": True, "estimado_aceptado": True,
                        "terminos_version": ESTADO["terminos"]},
        "idempotency_key": "e2e-crear-1",
    }))
    assert _saldo_de() == antes, "confirmar movió saldo"
    assert datos["estado"] == "esperando_postagem"
    assert datos["display_id"]
    ESTADO["display_id"] = datos["display_id"]


def test_07_el_doble_clic_en_confirmar_no_crea_dos_envios():
    como("user")
    otra = CLIENTE.post("/api/envios/crear", json={
        "envio_id": ESTADO["envio_id"],
        "declaracion": {"contenido_aceptado": True, "estimado_aceptado": True,
                        "terminos_version": ESTADO["terminos"]},
        "idempotency_key": "e2e-crear-1",
    })
    assert otra.status_code == 200
    assert otra.json()["display_id"] == ESTADO["display_id"]
    assert corre(DB.envios.count_documents({"user_id": "usr_user"})) == 1


# ─── Paso 3: el comprobante ───────────────────────────────────────────────

def test_08_cargar_el_comprobante_no_cobra():
    como("user")
    antes = _saldo_de()
    ayer = (AHORA - timedelta(days=1)).date().isoformat()
    respuesta = CLIENTE.post(
        f"/api/envios/{ESTADO['envio_id']}/comprobante",
        data={"codigo_objeto": "AA123456789BR", "posteado_at": ayer},
        files={"foto": ("comprobante.jpg", _jpeg(), "image/jpeg")})
    _ok(respuesta)
    assert _saldo_de() == antes, "cargar el comprobante movió saldo"

    detalle = _ok(CLIENTE.get(f"/api/envios/{ESTADO['envio_id']}"))
    assert detalle["estado"] == "en_transito_origen"
    assert detalle["comprobante"]["codigo_objeto"] == "AA123456789BR"
    ESTADO["asset"] = detalle["comprobante"]["foto_asset_id"]


def test_09_la_foto_es_del_dueño_del_envio_y_de_nadie_mas():
    como("user")
    _ok(CLIENTE.get(f"/api/envios/{ESTADO['envio_id']}/foto/{ESTADO['asset']}"))
    como("user", "usr_otro")
    ajena = CLIENTE.get(f"/api/envios/{ESTADO['envio_id']}/foto/{ESTADO['asset']}")
    assert ajena.status_code == 404


# ─── Paso 4: el operador verifica, y AHI se cobra ─────────────────────────

def test_10_un_agente_no_puede_emitir_el_cobro():
    """`verificar` mueve saldo real: pide `get_admin_user`, no `get_crm_user`."""
    como("agent")
    rechazado = CLIENTE.post(
        f"/api/admin/envios/envios/{ESTADO['envio_id']}/comprobante/verificar",
        json={"peso_kg": "2.30", "largo_cm": "40", "ancho_cm": "30", "alto_cm": "20"})
    assert rechazado.status_code == 403


def test_11_verificar_emite_el_cobro_inicial():
    como("admin")
    antes = _saldo_de("usr_user")
    datos = _ok(CLIENTE.post(
        f"/api/admin/envios/envios/{ESTADO['envio_id']}/comprobante/verificar",
        json={"peso_kg": "2.30", "largo_cm": "40", "ancho_cm": "30", "alto_cm": "20",
              "idempotency_key": "e2e-verificar-1"}))
    assert datos["cobro"]["estado"] == "pagado"
    from decimal import Decimal
    cobrado = Decimal(datos["cobro"]["monto_ris"])
    # El NUMERO, no «algo positivo»: se verificó el mismo peso y las mismas
    # medidas que se cotizaron, así que el cobro tiene que ser el estimado y no
    # un parecido. Un `> 0` deja pasar que se cobre por peso real en vez de
    # cubado (78.00 en lugar de 112.00), o que el margen se aplique dos veces.
    assert cobrado == Decimal(ESTADO["total_estimado"]) == Decimal("112.00")
    assert _saldo_de("usr_user") == antes - cobrado
    ESTADO["cobro_inicial"] = cobrado


def test_12_verificar_dos_veces_no_cobra_dos_veces():
    como("admin")
    antes = _saldo_de("usr_user")
    datos = _ok(CLIENTE.post(
        f"/api/admin/envios/envios/{ESTADO['envio_id']}/comprobante/verificar",
        json={"peso_kg": "9.99", "largo_cm": "40", "ancho_cm": "30", "alto_cm": "20"}))
    assert datos["ya_verificado"] is True
    assert _saldo_de("usr_user") == antes


# ─── Paso 5: el paquete llega y se retira ─────────────────────────────────

def test_13_marcar_disponible_arranca_el_reloj_de_guarda():
    como("agent")     # el operador SI puede mover paquetes
    datos = _ok(CLIENTE.post(
        f"/api/admin/envios/envios/{ESTADO['envio_id']}/disponible", json={}))
    assert datos["guarda_vence_at"], "no arrancó el reloj de guarda"

    cola = _ok(CLIENTE.get("/api/admin/envios/envios/cola",
                           params={"estado": "disponible_retiro"}))
    assert cola["total"] == 1
    # Agrupada por el nombre CONGELADO en el envío, no por quién esté de turno.
    assert cola["grupos"][0]["retirador_nombre"] == "Ana Pérez"
    fila = cola["grupos"][0]["envios"][0]
    assert fila["codigo_objeto"] == "AA123456789BR"
    assert fila["puede_salir"] is True


def test_14_el_retiro_por_lote_no_se_frena_por_un_codigo_desconocido():
    como("agent")
    datos = _ok(CLIENTE.post("/api/admin/envios/envios/retiro-lote", json={
        "codigos": ["AA123456789BR", "ZZ000000000ZZ"], "nota": "viaje del martes"}))
    assert datos["cuantos"] == 1
    assert datos["cuantos_rechazados"] == 1
    # Y el rechazo trae con qué hacer algo, no solo un slug.
    rechazado = datos["rechazados"][0]
    assert rechazado["codigo"] == "ZZ000000000ZZ"
    assert rechazado.get("motivo")
    ESTADO["lote"] = datos["lote_id"]


# ─── Paso 6: el repesaje y sus tres ramas ────────────────────────────────

def test_15_un_agente_no_puede_repesar():
    """La rama «devolver» ACREDITA saldo real: `get_admin_user`, no `get_crm_user`."""
    como("agent")
    rechazado = CLIENTE.post(
        f"/api/admin/envios/envios/{ESTADO['envio_id']}/repesar",
        json={"peso_kg": "2.30", "largo_cm": "40", "ancho_cm": "30", "alto_cm": "20"})
    assert rechazado.status_code == 403


def test_16_repesar_con_el_mismo_peso_no_ajusta_nada():
    """Rama A: la diferencia no llega a la tolerancia, así que no se toca nada.

    Generar un cobro de treinta centavos cuesta más en soporte que lo que recauda.
    """
    como("admin")
    antes = _saldo_de("usr_user")
    datos = _ok(CLIENTE.post(
        f"/api/admin/envios/envios/{ESTADO['envio_id']}/repesar",
        json={"peso_kg": "2.30", "largo_cm": "40", "ancho_cm": "30", "alto_cm": "20",
              "idempotency_key": "e2e-repesar-1"}))
    assert datos["rama"] == "sin_ajuste"
    assert datos["puede_salir"] is True
    assert _saldo_de("usr_user") == antes
    assert datos["estado"] == "repesado"


def test_17_el_precio_deja_de_ser_un_estimado():
    como("user")
    detalle = _ok(CLIENTE.get(f"/api/envios/{ESTADO['envio_id']}"))
    assert detalle["es_estimado"] is False
    assert detalle["total_ris"] == str(ESTADO["cobro_inicial"])

    # El bloque `verificado` sale CON las medidas y SIN el user_id del operador.
    # El positivo va primero a propósito: `_medidas` devuelve None cuando el
    # bloque no está, y un `"verificado_por" not in (x or {})` es trivialmente
    # cierto contra None — o sea, pasaría igual si la pantalla perdiera las
    # medidas enteras.
    verificado = detalle["paquete"]["verificado"]
    assert verificado["peso_kg"] == "2.30"
    assert verificado["largo_cm"] == "40"
    assert "verificado_por" not in verificado


# ─── Paso 7: sale de Pacaraima ───────────────────────────────────────────

def test_18_despachar_y_entregar():
    como("agent")
    salida = _ok(CLIENTE.post(
        f"/api/admin/envios/envios/{ESTADO['envio_id']}/despachar"))
    assert salida["estado"] == "en_transito_int"

    entrega = CLIENTE.post(
        f"/api/admin/envios/envios/{ESTADO['envio_id']}/entregar",
        data={"guia": "GUIA-99887766"},
        files={"foto": ("remito.jpg", _jpeg((20, 120, 60)), "image/jpeg")})
    _ok(entrega)
    assert entrega.json()["estado"] == "entregado_transportista"


# ─── Paso 8: el seguimiento público ──────────────────────────────────────

def test_19_el_seguimiento_publico_no_lleva_un_solo_dato_personal():
    como("user")
    detalle = _ok(CLIENTE.get(f"/api/envios/{ESTADO['envio_id']}"))
    token = detalle["tracking_token"]

    ACTUAL["user"] = None      # sin sesión: es una página pública
    datos = _ok(CLIENTE.get(f"/api/envios/seguimiento/{token}"))

    crudo = str(datos)
    for dato in ("Luisa Marín", "V-12345678", "+58 414", "usr_user",
                 "AA123456789BR", ESTADO["envio_id"]):
        assert dato not in crudo, f"el seguimiento público filtra {dato!r}"

    # Ningún monto, EN NINGUN NIVEL. Mirar solo las claves de primer nivel deja
    # pasar un `total_ris` adentro de `destino`, que es como se filtran las
    # cosas de verdad: nadie agrega una clave llamada `cobros`.
    plata = [c for c in _todas_las_claves(datos)
             if any(t in c.lower() for t in
                    ("total", "monto", "cobro", "precio", "saldo", "deuda", "pag"))]
    assert not plata, f"el seguimiento público lleva plata: {plata}"

    # Y el positivo, que es lo que evita que todo lo de arriba pase por vacío:
    # una página de seguimiento en blanco no filtra nada y no sirve para nada.
    assert datos["display_id"] == ESTADO["display_id"]
    assert datos["estado_titulo"]
    assert datos["guia_transportista"] == "GUIA-99887766"
    assert datos["timeline"], "el seguimiento quedó sin línea de tiempo"
    assert datos["destino"]["ciudad"] == "Santa Elena"


def test_20_un_token_inventado_y_uno_mal_escrito_se_contestan_igual():
    """Distinguirlos convierte la ruta en un oráculo para adivinar tokens."""
    ACTUAL["user"] = None
    inexistente = CLIENTE.get(f"/api/envios/seguimiento/{'b' * 32}")
    malformado = CLIENTE.get("/api/envios/seguimiento/nada")
    assert inexistente.status_code == malformado.status_code == 404
    assert inexistente.json() == malformado.json()


# ─── Paso 9: las otras dos ramas del repesaje, y la partida impaga ────────
#
# Los tests 01–20 recorren un envío que sale bien: pesa lo que dijo, tiene con
# qué pagar, y sale de Pacaraima. Los que siguen recorren los tres finales que
# el otro no toca, y que son los que mueven plata de verdad:
#
#   cobrar          — pesó más. Se debita la diferencia.
#   devolver        — pesó menos. Se le ACREDITA la diferencia.
#   pago_pendiente  — pesó más y no tiene saldo. El paquete no sale.
#
# Cada uno con su envío y su usuario, porque el estado del anterior es terminal.


def _color_de(marca: str):
    from hashlib import sha256
    crudo = sha256(marca.encode()).digest()
    return (crudo[0], crudo[1], crudo[2])


def _envio_hasta_repesar(usuario: str, *, saldo: str, peso: str, codigo: str,
                         marca: str, hasta: str = "mostrador") -> str:
    """Un envío nuevo, por las rutas de verdad, hasta el mostrador de Pacaraima.

    Repite los pasos 2 a 5 sin sus aserciones: acá lo que se prueba es lo que
    viene DESPUES, y llegar hasta ahí a mano en cada test escondería el test
    adentro de su preparación.
    """
    _saldo(usuario, saldo)

    como("user", usuario)
    pedido = {**PEDIDO}
    pedido["destino"] = {**PEDIDO["destino"], "transportista_id": ESTADO["trp_ve"]}
    pedido["paquete"] = {**PEDIDO["paquete"], "peso_kg": peso}
    envio_id = _ok(CLIENTE.post("/api/envios/cotizar", json=pedido))["envio_id"]

    _ok(CLIENTE.post("/api/envios/crear", json={
        "envio_id": envio_id,
        "declaracion": {"contenido_aceptado": True, "estimado_aceptado": True,
                        "terminos_version": ESTADO["terminos"]},
        "idempotency_key": f"e2e-crear-{marca}"}))

    # Un JPEG distinto por envío: el módulo avisa cuando una foto ya se usó en
    # otro envío, y reusar la misma acá llenaría el log de una alarma falsa
    # justo donde esa alarma tiene que significar algo.
    ayer = (AHORA - timedelta(days=1)).date().isoformat()
    _ok(CLIENTE.post(
        f"/api/envios/{envio_id}/comprobante",
        data={"codigo_objeto": codigo, "posteado_at": ayer},
        files={"foto": ("comprobante.jpg", _jpeg(_color_de(marca)), "image/jpeg")}))

    como("admin")
    _ok(CLIENTE.post(f"/api/admin/envios/envios/{envio_id}/comprobante/verificar",
                     json={"peso_kg": peso, "largo_cm": "40", "ancho_cm": "30",
                           "alto_cm": "20",
                           "idempotency_key": f"e2e-verificar-{marca}"}))

    como("agent")
    _ok(CLIENTE.post(f"/api/admin/envios/envios/{envio_id}/disponible", json={}))
    if hasta == "disponible":
        return envio_id
    _ok(CLIENTE.post("/api/admin/envios/envios/retiro-lote",
                     json={"codigos": [codigo], "nota": f"lote {marca}"}))
    return envio_id


def test_21_repesar_pesando_mas_cobra_la_diferencia_y_el_paquete_sigue():
    """Rama B: pesó más de lo declarado. Se debita la diferencia, y sale igual.

    Lo que importa acá no es que cobre, es CUANTO: el ajuste se calcula contra
    el cobro inicial ya emitido, no contra cero. Cobrar el total de nuevo es el
    defecto obvio de esta rama y ningún doble lo distingue, porque el número que
    sale de un doble lo elegí yo.
    """
    from decimal import Decimal
    envio_id = _envio_hasta_repesar("usr_pesa_mas", saldo="500.00", peso="2.30",
                                    codigo="BB111111111BR", marca="mas")
    inicial = Decimal(((corre(DB.envios.find_one({"envio_id": envio_id})) or {})
                       .get("cobros") or {}).get("inicial", {}).get("monto_ris"))

    como("admin")
    antes = _saldo_de("usr_pesa_mas")
    datos = _ok(CLIENTE.post(
        f"/api/admin/envios/envios/{envio_id}/repesar",
        json={"peso_kg": "9.00", "largo_cm": "40", "ancho_cm": "30", "alto_cm": "20",
              "idempotency_key": "e2e-repesar-mas"}))

    assert datos["rama"] == "cobrar"
    diferencia = Decimal(datos["diferencia_ris"])
    assert diferencia > 0
    # La diferencia es contra lo ya cobrado, no el total otra vez.
    assert diferencia == Decimal(datos["total_final_ris"]) - inicial
    assert datos["cobro"]["estado"] == "pagado"
    assert _saldo_de("usr_pesa_mas") == antes - diferencia

    # Y con la diferencia pagada el paquete sale: no queda frenado por haber
    # pesado más.
    assert datos["partidas_impagas"] == []
    assert datos["puede_salir"] is True
    assert datos["estado"] == "repesado"
    _ok(CLIENTE.post(f"/api/admin/envios/envios/{envio_id}/despachar"))


def test_22_repesar_pesando_menos_le_devuelve_la_diferencia():
    """Rama C: pesó menos. Se ACREDITA. Un ajuste que solo sube es un recargo.

    Y se revisa lo que ve el usuario, no solo el saldo: la devolución llegó a
    mostrarse como una deuda con botón de «Pagar» — el mismo número, con el
    signo al revés, es la peor forma de tener razón.
    """
    from decimal import Decimal
    envio_id = _envio_hasta_repesar("usr_pesa_menos", saldo="500.00", peso="9.00",
                                    codigo="CC222222222BR", marca="menos")

    como("admin")
    antes = _saldo_de("usr_pesa_menos")
    datos = _ok(CLIENTE.post(
        f"/api/admin/envios/envios/{envio_id}/repesar",
        json={"peso_kg": "2.30", "largo_cm": "40", "ancho_cm": "30", "alto_cm": "20",
              "idempotency_key": "e2e-repesar-menos"}))

    assert datos["rama"] == "devolver"
    devuelto = Decimal(datos["diferencia_ris"]).copy_abs()
    assert devuelto > 0
    assert datos["devolucion"] is not None
    assert _saldo_de("usr_pesa_menos") == antes + devuelto
    assert datos["puede_salir"] is True

    # Del lado del usuario: la devolución se lee como devolución, no como deuda.
    como("user", "usr_pesa_menos")
    detalle = _ok(CLIENTE.get(f"/api/envios/{envio_id}"))
    assert detalle["es_estimado"] is False
    lineas = {c["partida"]: c for c in (detalle.get("cobros") or [])}
    assert "devolucion" in lineas, "la devolución no aparece en el detalle"
    assert lineas["devolucion"]["estado"] == "acreditado"
    assert "ajuste" not in lineas, "la devolución se listó como partida a pagar"
    assert not [c for c in lineas.values() if c["estado"] == "pendiente"]
    ESTADO["envio_devuelto"] = envio_id


def test_23_sin_saldo_el_paquete_no_sale_de_pacaraima():
    """La única palanca de cobro real del negocio: la posesión física.

    Que la partida quede impaga NO es un error —el paquete ya viajó y no
    dependía de nosotros—, así que la ruta contesta 200. Lo que no pasa es que
    salga.
    """
    from decimal import Decimal
    envio_id = _envio_hasta_repesar("usr_sin_saldo", saldo="500.00", peso="2.30",
                                    codigo="DD333333333BR", marca="pobre")
    _saldo("usr_sin_saldo", "0.00")          # se le fue el saldo entre medio

    como("admin")
    datos = _ok(CLIENTE.post(
        f"/api/admin/envios/envios/{envio_id}/repesar",
        json={"peso_kg": "9.00", "largo_cm": "40", "ancho_cm": "30", "alto_cm": "20",
              "idempotency_key": "e2e-repesar-pobre"}))

    assert datos["rama"] == "cobrar"
    assert datos["cobro"]["estado"] == "pendiente"
    assert datos["cobro"]["motivo"] == "saldo"
    assert _saldo_de("usr_sin_saldo") == Decimal("0.00"), "debitó sin saldo"

    # El estado lo ESCRIBE el repesaje, no lo sugiere.
    assert datos["estado"] == "pago_pendiente"
    assert datos["puede_salir"] is False
    assert "ajuste" in datos["partidas_impagas"]

    # Y despachar se rechaza, venga de donde venga la llamada.
    frenado = CLIENTE.post(f"/api/admin/envios/envios/{envio_id}/despachar")
    assert frenado.status_code == 409
    assert corre(DB.envios.find_one({"envio_id": envio_id}))["estado"] == "pago_pendiente"
    ESTADO["envio_pobre"] = envio_id


def test_24_pagar_sin_saldo_contesta_200_con_el_motivo_y_no_un_error():
    """Un 402 acá manda a la pantalla a mostrar un cartel rojo de fallo.

    No falló nada: falta plata. La pantalla necesita poder decir «te faltan X»
    con el número en la mano, y para eso el cuerpo tiene que llegar.
    """
    from decimal import Decimal
    como("user", "usr_sin_saldo")
    datos = _ok(CLIENTE.post(
        f"/api/envios/{ESTADO['envio_pobre']}/cobros/ajuste/pagar"))

    assert datos["estado"] == "pendiente"
    assert datos["motivo"] == "saldo"
    assert Decimal(datos["monto_ris"]) > 0, "sin el monto no hay «te faltan X»"
    assert _saldo_de("usr_sin_saldo") == Decimal("0.00")


def test_25_la_partida_ajena_no_se_paga_ni_se_mira():
    """El envío se busca por dueño, no solo por id."""
    como("user", "usr_otro")
    ajeno = CLIENTE.post(f"/api/envios/{ESTADO['envio_pobre']}/cobros/ajuste/pagar")
    assert ajeno.status_code == 404


def test_26_con_saldo_se_salda_la_partida_y_el_paquete_sale():
    from decimal import Decimal
    _saldo("usr_sin_saldo", "300.00")
    como("user", "usr_sin_saldo")
    antes = _saldo_de("usr_sin_saldo")

    datos = _ok(CLIENTE.post(
        f"/api/envios/{ESTADO['envio_pobre']}/cobros/ajuste/pagar"))
    assert datos["estado"] == "pagado"
    pagado = Decimal(datos["monto_ris"])
    assert _saldo_de("usr_sin_saldo") == antes - pagado

    # Pagar dos veces no cobra dos veces: la guardia es el estado de la partida.
    otra = _ok(CLIENTE.post(
        f"/api/envios/{ESTADO['envio_pobre']}/cobros/ajuste/pagar"))
    assert otra["estado"] == "pagado"
    assert _saldo_de("usr_sin_saldo") == antes - pagado

    # Y recién ahora sale de Pacaraima.
    como("agent")
    salida = _ok(CLIENTE.post(
        f"/api/admin/envios/envios/{ESTADO['envio_pobre']}/despachar"))
    assert salida["estado"] == "en_transito_int"


# ─── Paso 10: las puertas. Quién NO puede hacer qué ──────────────────────
#
# Los tests 10 y 15 prueban una mitad del par —un `agent` no cobra ni repesa—.
# Acá va la otra, y el KYC, que no lo prueba nadie en todo el repositorio: hay
# un test que revisa los decoradores leyendo el TEXTO del archivo, y eso no
# ejecuta el grafo de dependencias. Este archivo es el único lugar donde ese
# grafo corre de verdad, así que es el único que puede decir algo.


def test_27_sin_kyc_no_se_cotiza_ni_se_crea_ni_se_carga_un_comprobante():
    """El formulario pide nombre, documento y teléfono de UN TERCERO.

    Sin KYC eso es carga de datos de otra persona abierta a cualquiera que se
    registre con un mail. Cambiar `get_verified_user` por `get_current_user` en
    `routes/envios.py` no rompía un solo test del repositorio.
    """
    como("user", "usr_sin_kyc", verificacion="pending")

    pedido = {**PEDIDO}
    pedido["destino"] = {**PEDIDO["destino"], "transportista_id": ESTADO["trp_ve"]}
    assert CLIENTE.post("/api/envios/cotizar", json=pedido).status_code == 403
    assert CLIENTE.post("/api/envios/crear", json={
        "envio_id": ESTADO["envio_id"],
        "declaracion": {"contenido_aceptado": True, "estimado_aceptado": True,
                        "terminos_version": ESTADO["terminos"]}}).status_code == 403
    ayer = (AHORA - timedelta(days=1)).date().isoformat()
    subir = CLIENTE.post(
        f"/api/envios/{ESTADO['envio_id']}/comprobante",
        data={"codigo_objeto": "XX999999999BR", "posteado_at": ayer},
        files={"foto": ("comprobante.jpg", _jpeg(), "image/jpeg")})
    assert subir.status_code == 403
    assert CLIENTE.post(
        f"/api/envios/{ESTADO['envio_id']}/cobros/ajuste/pagar").status_code == 403

    # LEER lo propio, en cambio, no pide KYC y está bien que no lo pida: sin
    # KYC no se pudo crear nada, así que la lista está vacía. Lo que se cierra
    # es escribir datos de un tercero, no mirar los de uno.
    _ok(CLIENTE.get("/api/envios"))

    # Y con el KYC hecho, la misma persona cotiza: lo que se rechaza es el
    # estado de la verificación, no la ruta.
    como("user", "usr_sin_kyc")
    _ok(CLIENTE.post("/api/envios/cotizar", json=pedido))


def test_28_un_usuario_comun_no_ve_la_cola_del_operador():
    """La otra mitad del par de roles: `get_crm_user` contra un `user`.

    La cola lleva nombres, documentos y teléfonos de destinatarios de TODOS los
    envíos. Es la lista de datos personales más grande del módulo.
    """
    como("user")
    assert CLIENTE.get("/api/admin/envios/envios/cola").status_code == 403
    assert CLIENTE.get("/api/admin/envios/estado").status_code == 403


def test_29_un_admin_que_no_es_super_no_publica_tarifas_ni_mueve_el_origen():
    """Publicar una tarifa cambia lo que se le cobra a todo el mundo."""
    como("admin")
    assert CLIENTE.post("/api/admin/envios/tarifas/publicar",
                        json={"nota": "por las mías"}).status_code == 403
    assert CLIENTE.put("/api/admin/envios/config/punto_origen",
                       json=PUNTO_ORIGEN).status_code == 403
    assert CLIENTE.post("/api/admin/envios/transportistas",
                        json=TRP_BRASIL).status_code == 403


def test_30_los_limites_se_leen_sin_sesion():
    """La pantalla de cotizar es pública: el precio se ve antes de registrarse.

    Está escrito como decisión en `routes/envios.py`, y agregarle un `Depends`
    no rompía ningún test. Ahora sí.
    """
    ACTUAL["user"] = None
    datos = _ok(CLIENTE.get("/api/envios/limites"))
    assert datos["disponible"] is True
    # Pero sin diagnóstico de configuración: eso es interno.
    assert "pasos" not in datos and "puede_operar" not in datos


# ─── Paso 11: lo que quedaba de las ramas de plata ───────────────────────

def test_31_la_cola_agrupa_por_el_nombre_congelado_y_no_por_quien_este_de_turno():
    """La etiqueta de una caja que ya viaja no cambia porque cambie la nómina.

    El mostrador compara esa etiqueta contra un documento, no contra la base.

    Y esto NO se prueba con una sola persona en la nómina, ni con una sola caja
    en la cola: agrupar por el nombre congelado y agrupar por el que está de
    turno dan lo mismo mientras haya un solo nombre a la vista. Hacen falta dos
    cajas rotuladas a nombres DISTINTOS esperando al mismo tiempo — que es
    exactamente lo que pasa en el mostrador cuando alguien se va de viaje.
    """
    # Una caja rotulada a Ana, que se queda esperando en el mostrador.
    de_ana = _envio_hasta_repesar("usr_con_ana", saldo="500.00", peso="2.30",
                                  codigo="EE444444444BR", marca="ana",
                                  hasta="disponible")

    # Cambia el turno. La caja de Ana ya está rotulada y no se toca.
    como("super_admin")
    otro = _ok(CLIENTE.post("/api/admin/envios/retiro/colaboradores",
                            json={**COLABORADOR, "nombre": "Beto Suárez",
                                  "cpf": "555.666.777-88"}))["valor"]
    turno = _ok(CLIENTE.put("/api/admin/envios/retiro/turno",
                            json={"colaborador_id": otro["colaborador_id"]}))
    assert turno["de_turno"] == "Beto Suárez"

    # Y una caja nueva, rotulada a Beto.
    de_beto = _envio_hasta_repesar("usr_con_beto", saldo="500.00", peso="2.30",
                                   codigo="HH777777777BR", marca="beto",
                                   hasta="disponible")

    como("agent")
    cola = _ok(CLIENTE.get("/api/admin/envios/envios/cola",
                           params={"estado": "disponible_retiro"}))
    por_nombre = {g["retirador_nombre"]: g for g in cola["grupos"]}
    assert set(por_nombre) == {"Ana Pérez", "Beto Suárez"}, list(por_nombre)

    # Y cada caja bajo el nombre que lleva ESCRITO, no bajo el del turno.
    assert [e["codigo_objeto"] for e in por_nombre["Ana Pérez"]["envios"]] \
        == ["EE444444444BR"]
    assert [e["codigo_objeto"] for e in por_nombre["Beto Suárez"]["envios"]] \
        == ["HH777777777BR"]

    # Y el texto copiable del envío de Ana sigue diciendo Ana.
    como("user", "usr_con_ana")
    detalle = _ok(CLIENTE.get(f"/api/envios/{de_ana}"))
    assert "Ana Pérez" in detalle["retiro"]["texto_copiable"]
    assert "Beto" not in detalle["retiro"]["texto_copiable"]

    # Se vuelve a dejar a Ana de turno: los tests que siguen no son sobre esto.
    como("super_admin")
    _ok(CLIENTE.put("/api/admin/envios/retiro/turno",
                    json={"colaborador_id": ESTADO["colaborador"]}))
    ESTADO["envio_de_ana"] = de_ana
    ESTADO["envio_de_beto"] = de_beto


def test_32_una_diferencia_menor_a_la_tolerancia_no_emite_nada():
    """La rama «sin_ajuste» con una diferencia DE VERDAD, no con cero.

    Con diferencia cero, `|0| <= tolerancia` es cierto para cualquier
    tolerancia, incluida la tolerancia CERO —que es exactamente el defecto que
    esta rama tuvo: un cero explícito la hacía desaparecer y un envío quedaba
    frenado en Pacaraima por un peso con cincuenta—. Acá la diferencia es 1.00
    contra una tolerancia de 2.00: si la tolerancia se rompe, esto falla.
    """
    from decimal import Decimal
    envio_id = _envio_hasta_repesar("usr_apenas", saldo="500.00", peso="10.00",
                                    codigo="FF555555555BR", marca="apenas")
    inicial = Decimal(((corre(DB.envios.find_one({"envio_id": envio_id})) or {})
                       .get("cobros") or {}).get("inicial", {}).get("monto_ris"))
    assert inicial == Decimal("186.00")

    como("admin")
    antes = _saldo_de("usr_apenas")
    datos = _ok(CLIENTE.post(
        f"/api/admin/envios/envios/{envio_id}/repesar",
        json={"peso_kg": "10.40", "largo_cm": "40", "ancho_cm": "30",
              "alto_cm": "20", "idempotency_key": "e2e-repesar-apenas"}))

    # Pesó más y el precio de tabla subió 1.00 — y aun así no se emite nada.
    assert Decimal(datos["total_final_ris"]) == Decimal("187.00")
    assert Decimal(datos["diferencia_ris"]) == Decimal("1.00")
    assert datos["rama"] == "sin_ajuste"
    assert datos["cobro"] is None and datos["devolucion"] is None
    assert _saldo_de("usr_apenas") == antes
    assert datos["puede_salir"] is True


def test_33_la_devolucion_no_se_puede_cobrar_como_si_fuera_una_deuda():
    """`devolucion` es una partida REAL del documento, con un monto real.

    La ruta de pago recibe el nombre de la partida por la URL. Cuando aceptaba
    cualquiera, pagar `devolucion` DEBITABA el monto que se le acababa de
    acreditar al usuario: el peor resultado posible, con el signo al revés dos
    veces. El test que cubre esto usa una partida inventada; ésta existe.
    """
    from decimal import Decimal
    envio_id = ESTADO["envio_devuelto"]
    como("user", "usr_pesa_menos")
    antes = _saldo_de("usr_pesa_menos")

    rechazado = CLIENTE.post(f"/api/envios/{envio_id}/cobros/devolucion/pagar")
    assert rechazado.status_code in (400, 404), rechazado.text
    assert _saldo_de("usr_pesa_menos") == antes, "cobró una devolución"


def test_34_verificar_sin_saldo_deja_el_cobro_inicial_pendiente_y_el_paquete_viaja():
    """El paquete YA está en manos de Correios: no depende de nosotros.

    Por eso la falta de saldo no rechaza la verificación —el operador no puede
    deshacer un despacho que ya ocurrió— y la partida queda pendiente. La
    palanca se ejerce después, en Pacaraima, que es donde el paquete sí está en
    nuestras manos.
    """
    from decimal import Decimal
    _saldo("usr_pelado", "0.00")

    como("user", "usr_pelado")
    pedido = {**PEDIDO}
    pedido["destino"] = {**PEDIDO["destino"], "transportista_id": ESTADO["trp_ve"]}
    envio_id = _ok(CLIENTE.post("/api/envios/cotizar", json=pedido))["envio_id"]
    _ok(CLIENTE.post("/api/envios/crear", json={
        "envio_id": envio_id,
        "declaracion": {"contenido_aceptado": True, "estimado_aceptado": True,
                        "terminos_version": ESTADO["terminos"]},
        "idempotency_key": "e2e-crear-pelado"}))
    ayer = (AHORA - timedelta(days=1)).date().isoformat()
    _ok(CLIENTE.post(
        f"/api/envios/{envio_id}/comprobante",
        data={"codigo_objeto": "GG666666666BR", "posteado_at": ayer},
        files={"foto": ("comprobante.jpg", _jpeg(_color_de("pelado")), "image/jpeg")}))

    como("admin")
    datos = _ok(CLIENTE.post(
        f"/api/admin/envios/envios/{envio_id}/comprobante/verificar",
        json={"peso_kg": "2.30", "largo_cm": "40", "ancho_cm": "30",
              "alto_cm": "20", "idempotency_key": "e2e-verificar-pelado"}))

    assert datos["cobro"]["estado"] == "pendiente"
    assert datos["cobro"]["motivo"] == "saldo"
    assert Decimal(datos["cobro"]["monto_ris"]) == Decimal("112.00")
    assert _saldo_de("usr_pelado") == Decimal("0.00")

    # El envío SIGUE, porque el paquete sigue.
    como("user", "usr_pelado")
    detalle = _ok(CLIENTE.get(f"/api/envios/{envio_id}"))
    assert detalle["estado"] == "en_transito_origen"

    # Y en Pacaraima se frena: la deuda es del cobro INICIAL, no de un ajuste.
    como("agent")
    _ok(CLIENTE.post(f"/api/admin/envios/envios/{envio_id}/disponible", json={}))
    _ok(CLIENTE.post("/api/admin/envios/envios/retiro-lote",
                     json={"codigos": ["GG666666666BR"], "nota": "lote pelado"}))
    como("admin")
    repesado = _ok(CLIENTE.post(
        f"/api/admin/envios/envios/{envio_id}/repesar",
        json={"peso_kg": "2.30", "largo_cm": "40", "ancho_cm": "30",
              "alto_cm": "20", "idempotency_key": "e2e-repesar-pelado"}))
    assert repesado["rama"] == "sin_ajuste"
    assert "inicial" in repesado["partidas_impagas"]
    assert repesado["puede_salir"] is False
    assert CLIENTE.post(
        f"/api/admin/envios/envios/{envio_id}/despachar").status_code == 409


def test_35_un_cep_fuera_del_catalogo_cotiza_igual_y_queda_propuesto():
    """Que la ciudad no este cargada NO bloquea a nadie.

    El catalogo arranca vacio y se llena de a poco: una pantalla que solo
    funcione con catalogo cargado seria una pantalla rota el primer dia. Se
    cotiza con la UF que declaro el usuario, y el CEP queda anotado para que
    alguien lo cargue.

    Y anotar eso no puede tumbar una cotizacion: es telemetria, no parte del
    calculo.
    """
    from decimal import Decimal

    como("user")
    _saldo("usr_user", "500.00")

    pedido = {**PEDIDO}
    pedido["destino"] = {**PEDIDO["destino"], "transportista_id": ESTADO["trp_ve"]}
    pedido["origen"] = {"cep": "88010001", "ciudad": "Florianópolis", "uf": "SC"}
    datos = _ok(CLIENTE.post("/api/envios/cotizar", json=pedido))

    # Cotizo de verdad: hay precio.
    assert Decimal(datos["a_pagar_en_risapp"]["total_estimado_ris"]) > 0

    como("super_admin")
    catalogo = _ok(CLIENTE.get("/api/admin/envios/origenes"))
    propuestos = {p["cep"]: p for p in catalogo["propuestos"]}
    assert "88010001" in propuestos, "el CEP no quedo en la cola"
    assert propuestos["88010001"]["ciudad"] == "Florianópolis"
    assert propuestos["88010001"]["pedidos"] >= 1
    # Y NO entro solo al catalogo.
    assert "88010001" not in {o["cep"] for o in catalogo["origenes"]}


def test_36_pedir_dos_veces_la_misma_ciudad_no_duplica_la_cola():
    """El indice unico hace que el segundo pedido incremente el contador. Sin
    eso la cola se llena de la misma ciudad y el orden por `pedidos` —que es lo
    que dice cual cargar primero— no significa nada."""
    como("super_admin")
    antes = {p["cep"]: p["pedidos"]
             for p in _ok(CLIENTE.get("/api/admin/envios/origenes"))["propuestos"]}

    como("user")
    pedido = {**PEDIDO}
    pedido["destino"] = {**PEDIDO["destino"], "transportista_id": ESTADO["trp_ve"]}
    pedido["origen"] = {"cep": "88010-001", "ciudad": "Florianópolis", "uf": "SC"}
    _ok(CLIENTE.post("/api/envios/cotizar", json=pedido))

    como("super_admin")
    cola = _ok(CLIENTE.get("/api/admin/envios/origenes"))["propuestos"]
    fila = next(p for p in cola if p["cep"] == "88010001")
    assert fila["pedidos"] == antes.get("88010001", 0) + 1
    assert len([p for p in cola if p["cep"] == "88010001"]) == 1


def test_37_la_uf_del_catalogo_le_gana_a_la_que_venga_tipeada():
    """Es la razon de ser del catalogo.

    Se carga São Paulo con su UF correcta y se cotiza declarando OTRA. La
    referencia del tramo brasileño tiene que salir por la clave del catalogo:
    una UF tipeada mal trae el precio de otro estado, la referencia sale, es
    plausible, y esta mal.
    """
    como("super_admin")
    _ok(CLIENTE.post("/api/admin/envios/origenes",
                     json={"cep": "01310100", "ciudad": "São Paulo", "uf": "SP"}))

    como("user")
    pedido = {**PEDIDO}
    pedido["destino"] = {**PEDIDO["destino"], "transportista_id": ESTADO["trp_ve"]}
    # El CEP es el de São Paulo pero la UF declarada dice Minas Gerais.
    pedido["origen"] = {"cep": "01310-100", "ciudad": "São Paulo", "uf": "MG"}
    datos = _ok(CLIENTE.post("/api/envios/cotizar", json=pedido))

    # La matriz de este e2e solo tiene cargada la clave "SP". Si mandara la UF
    # tipeada —"MG"— la referencia saldria sin dato; si manda la del catalogo,
    # sale con monto. Se verifica el EFECTO y no una clave interna, que no viaja
    # al usuario a proposito.
    brasil = next(r for r in datos["referencias"] if r["rol"] == "brasil")
    assert brasil["monto"] is not None, "mando la UF tipeada en vez de la del catalogo"
    assert brasil["fuente"] == "matriz"


def test_38_el_catalogo_de_origenes_le_llega_al_formulario():
    """Viajan dentro de `/envios/catalogo`, que el formulario ya pide. Y una
    ciudad recien cargada tiene que aparecer sin esperar el TTL del cache: si no,
    el que la cargo cree que no se guardo."""
    como("super_admin")
    _ok(CLIENTE.post("/api/admin/envios/origenes",
                     json={"cep": "30130010", "ciudad": "Belo Horizonte", "uf": "MG"}))

    como("user")
    catalogo = _ok(CLIENTE.get("/api/envios/catalogo"))
    por_cep = {o["cep"]: o for o in catalogo["origenes"]}
    assert "30130010" in por_cep, "la ciudad recien cargada no llego al formulario"
    assert por_cep["30130010"]["cep_legible"] == "30130-010"
    assert por_cep["30130010"]["uf"] == "MG"


def test_39_una_ciudad_desactivada_desaparece_del_formulario():
    como("super_admin")
    _ok(CLIENTE.patch("/api/admin/envios/origenes/30130010", json={"activo": False}))

    como("user")
    catalogo = _ok(CLIENTE.get("/api/envios/catalogo"))
    assert "30130010" not in {o["cep"] for o in catalogo["origenes"]}

    # Pero sigue en el panel, para poder volver a prenderla: nada se borra.
    como("super_admin")
    del_panel = _ok(CLIENTE.get("/api/admin/envios/origenes"))["origenes"]
    assert next(o for o in del_panel if o["cep"] == "30130010")["activo"] is False


def test_40_aprobar_un_propuesto_lo_deja_cotizando_por_su_clave():
    """El circuito entero de la cola: alguien pide una ciudad, el super
    administrador la aprueba corrigiendo lo que haga falta, y a partir de ahi esa
    ciudad resuelve su UF por el catalogo."""
    como("super_admin")
    _ok(CLIENTE.post("/api/admin/envios/origenes/propuestos/88010001",
                     json={"estado": "aprobado", "ciudad": "Florianópolis",
                           "uf": "SC"}))

    catalogo = _ok(CLIENTE.get("/api/admin/envios/origenes"))
    assert "88010001" in {o["cep"] for o in catalogo["origenes"]}
    assert "88010001" not in {p["cep"] for p in catalogo["propuestos"]}

    # Y a partir de ahora esa ciudad resuelve por el catalogo. Se le carga
    # precio a su UF y se cotiza declarando OTRA: si manda la del catalogo, la
    # referencia sale con monto.
    _ok(CLIENTE.post("/api/admin/envios/matrices",
                     json={"transportista_id": ESTADO["trp_br"], "clave": "SC",
                           "hasta_kg": "30", "precio": "99.00", "moneda": "BRL"}))

    como("user")
    pedido = {**PEDIDO}
    pedido["destino"] = {**PEDIDO["destino"], "transportista_id": ESTADO["trp_ve"]}
    pedido["origen"] = {"cep": "88010001", "ciudad": "Florianópolis", "uf": "RJ"}
    datos = _ok(CLIENTE.post("/api/envios/cotizar", json=pedido))
    brasil = next(r for r in datos["referencias"] if r["rol"] == "brasil")
    assert brasil["monto"] == "99.00", "no resolvio por la UF del catalogo"


def test_41_una_tarifa_con_dos_escalones_que_comparten_borde_se_puede_publicar():
    """El borde compartido es lo que fabrica el editor —prellena el `desde` con
    el `hasta` anterior— y por eso NO se rechaza: hacerlo volveria irrepublicable
    toda tarifa cargada desde el panel, la que esta viva incluida.

    Lo que si esta fijado es a que banda pertenece el peso del borde: la de
    ABAJO. Eso lo cubre test_envios_tarifas; aca se verifica que la publicacion
    no se frene.
    """
    como("super_admin")
    con_borde = {**TARIFA, "escalones_peso": [
        {"desde_kg": "0.00", "hasta_kg": "1.00", "precio": "45.00"},
        {"desde_kg": "1.00", "hasta_kg": "3.00", "precio": "78.00"},
        {"desde_kg": "3.00", "hasta_kg": "5.00", "precio": "112.00"},
        {"desde_kg": "5.00", "hasta_kg": "10.00", "precio": "186.00"},
        {"desde_kg": "10.00", "hasta_kg": "10.50", "precio": "187.00"},
    ]}
    _ok(CLIENTE.put("/api/admin/envios/tarifas/borrador", json=con_borde))
    _ok(CLIENTE.post("/api/admin/envios/tarifas/simular", json={}))
    _ok(CLIENTE.post("/api/admin/envios/tarifas/publicar",
                     json={"nota": "Escalones contiguos, como los escribe el editor."}))
