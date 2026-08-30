"""
Lo que el usuario ve de sus propios envios: la lista y el detalle.

LA DIFERENCIA CON EL SEGUIMIENTO PUBLICO
    Los dos modulos muestran el mismo envio y conviene tener clara la diferencia.
    El seguimiento es un link que se reenvia; esto esta detras de la sesion y le
    pertenece a quien lo pide, asi que aca SI van los datos que el usuario cargo.

    Lo que no sale ni aca: los diagnosticos internos, el margen, el desglose del
    calculo y el `retirador_id`. Nada de eso es del usuario.

QUE SE CUBRE
    1. Un envio ajeno no existe, y da el mismo 404 que uno inexistente.
    2. La lista dice lo primero que el usuario quiere saber: si hay algo que
       pagar.
    3. El detalle trae la direccion CONGELADA, no la vigente.
    4. Ninguna respuesta lleva el margen ni el desglose del calculo.
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
seg = _cargar("envios_seguimiento")
con = _cargar("envios_consulta")


def corre(coro):
    return asyncio.run(coro)


AHORA = datetime.now(timezone.utc)


class _Usuario:
    user_id = "usr_ana"


def envio(i=1, **cambios):
    import copy
    doc = {
        "envio_id": f"env_{i:03d}", "display_id": f"E{i:06d}", "user_id": "usr_ana",
        "estado": "en_transito_int", "tracking_token": "a" * 32,
        "created_at": AHORA - timedelta(days=i),
        "modalidad_flete": "destino",
        "destino_brasil": {"retirador_nombre": "María Gómez",
                           "retirador_id": "col_aaaa1111",
                           "retirador_motivo": "designado",
                           "texto_copiable": "RIS App LTDA\nA/C María Gómez"},
        "destino": {"ciudad": "Caracas", "estado_ve": "Miranda",
                    "agencia_nombre": "Centro",
                    "destinatario": {"nombre": "Ana Pérez", "documento": "V-1",
                                     "telefono": "+58 412"}},
        "paquete": {"declarado": {"peso_kg": "2.30"}, "verificado": None,
                    "contenido_descripcion": "Ropa"},
        "cotizacion": {"total_estimado_ris": "132.00", "total_final_ris": None,
                       "es_estimado": True, "moneda": "RIS",
                       "margen_ris": "22.00", "tarifa_version": "tar_x",
                       "referencias": [{"codigo": "TRP-7K2M", "monto": "62.40"}]},
        "cobros": {"inicial": {"monto_ris": "132.00", "estado": "pagado",
                               "detalle": {"tarifa_version": "tar_x"}},
                   "ajuste": None, "total_cobrado_ris": "132.00"},
        "origen": {"codigo_objeto": "AA123456789BR",
                   "comprobante_asset_id": "ast_x",
                   "posteado_at": AHORA - timedelta(days=2)},
    }
    doc = copy.deepcopy(doc)
    for clave, valor in cambios.items():
        if isinstance(valor, dict) and valor and isinstance(doc.get(clave), dict):
            doc[clave].update(valor)
        else:
            doc[clave] = valor
    return doc


def db_completa(envios=None, eventos=None):
    import copy
    base = _Db(
        envios=copy.deepcopy(envios if envios is not None else [envio()]),
        envios_eventos=copy.deepcopy(eventos or [
            {"envio_id": "env_001", "a_estado": "esperando_postagem",
             "created_at": AHORA - timedelta(days=3), "detalle": {"x": 1}},
            {"envio_id": "env_001", "a_estado": "en_transito_int",
             "created_at": AHORA, "detalle": {"monto_ris": "132.00"}},
        ]),
    )
    usar_base(base)
    return base


# ─── 1. Lo ajeno no existe ────────────────────────────────────────────────

def test_un_envio_ajeno_da_el_mismo_404_que_uno_inexistente():
    base = db_completa()

    class _Otro:
        user_id = "usr_otro"

    assert corre(con.detalle(_Otro(), "env_001", db=base)) is None
    assert corre(con.detalle(_Usuario(), "env_no_existe", db=base)) is None


def test_la_lista_solo_trae_los_envios_del_usuario():
    ajeno = envio(2)
    ajeno["user_id"] = "usr_otro"
    base = db_completa(envios=[envio(1), ajeno])
    r = corre(con.listar(_Usuario(), db=base))
    assert [e["envio_id"] for e in r["envios"]] == ["env_001"]


# ─── 2. La lista contesta lo primero que se pregunta ──────────────────────

def test_la_lista_dice_si_hay_algo_que_pagar():
    """Es lo primero que el usuario quiere saber al abrir la pantalla, y la regla
    de qué cuenta como impago vive en el backend."""
    con_deuda = envio(2, cobros={"inicial": {"monto_ris": "132.00",
                                             "estado": "pendiente"},
                                 "ajuste": {"monto_ris": "6.70",
                                            "estado": "pendiente"}})
    base = db_completa(envios=[envio(1), con_deuda])
    r = corre(con.listar(_Usuario(), db=base))
    por_id = {e["envio_id"]: e for e in r["envios"]}
    assert por_id["env_001"]["hay_algo_que_pagar"] is False
    assert por_id["env_001"]["a_pagar_ris"] is None
    assert por_id["env_002"]["hay_algo_que_pagar"] is True
    assert Decimal(por_id["env_002"]["a_pagar_ris"]) == Decimal("138.70")


def test_la_lista_sale_del_mas_nuevo_al_mas_viejo():
    base = db_completa(envios=[envio(3), envio(1), envio(2)])
    r = corre(con.listar(_Usuario(), db=base))
    assert [e["display_id"] for e in r["envios"]] == ["E000001", "E000002", "E000003"]


def test_la_lista_pagina_sin_contar_la_coleccion_entera():
    """Se pide uno más de los que se muestran: es la forma barata de saber si hay
    página siguiente."""
    base = db_completa(envios=[envio(i) for i in range(1, 8)])
    primera = corre(con.listar(_Usuario(), por_pagina=3, db=base))
    assert len(primera["envios"]) == 3 and primera["hay_mas"] is True
    tercera = corre(con.listar(_Usuario(), pagina=3, por_pagina=3, db=base))
    assert len(tercera["envios"]) == 1 and tercera["hay_mas"] is False


def test_la_pagina_no_se_puede_pedir_gigante():
    """`por_pagina` llega por la URL. Sin tope, cualquiera pide cien mil envíos
    por request contra una colección que crece — y el `to_list` de abajo es
    `pagina * por_pagina`, así que también se puede pedir la página un millón."""
    base = db_completa(envios=[envio(i) for i in range(1, 30)])
    pedidos = []
    original = base.envios.find

    def espiar(filtro=None, proyeccion=None):
        cursor = original(filtro, proyeccion)
        to_list_original = cursor.to_list

        async def contar(n):
            pedidos.append(n)
            return await to_list_original(n)
        cursor.to_list = contar
        return cursor
    base.envios.find = espiar

    r = corre(con.listar(_Usuario(), por_pagina=10000, db=base))
    assert len(r["envios"]) <= con.POR_PAGINA_MAX
    assert pedidos[0] <= con.POR_PAGINA_MAX + 1, (
        f"se le pidieron {pedidos[0]} documentos a la base")


def test_si_la_base_falla_la_lista_no_revienta():
    base = db_completa()
    base.envios.find = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    r = corre(con.listar(_Usuario(), db=base))
    assert r["envios"] == [] and r["degradado"] is True


def test_el_total_que_se_muestra_es_el_final_cuando_ya_se_cerro():
    cerrado = envio(1, cotizacion={"es_estimado": False,
                                   "total_final_ris": "138.70"})
    base = db_completa(envios=[cerrado])
    r = corre(con.listar(_Usuario(), db=base))
    assert r["envios"][0]["total_ris"] == "138.70"
    assert r["envios"][0]["es_estimado"] is False


# ─── 3. El detalle ────────────────────────────────────────────────────────

def test_el_detalle_trae_la_direccion_congelada_sin_los_datos_internos():
    base = db_completa()
    r = corre(con.detalle(_Usuario(), "env_001", db=base))
    assert "María Gómez" in r["retiro"]["texto_copiable"]
    assert "retirador_id" not in r["retiro"]
    assert "retirador_motivo" not in r["retiro"]
    assert "col_aaaa1111" not in repr(r)


def test_el_detalle_dice_que_se_cobro_y_si_esta_pago():
    base = db_completa()
    r = corre(con.detalle(_Usuario(), "env_001", db=base))
    assert r["cobros"] == [{"partida": "inicial",
                            "concepto": "Servicio de traslado",
                            "monto_ris": "132.00", "estado": "pagado",
                            "pagado_at": None}]


def test_el_detalle_muestra_la_devolucion_cuando_la_hubo():
    con_devolucion = envio(1, cobros={"devolucion": {"monto_ris": "6.70",
                                                     "estado": "acreditado"}})
    base = db_completa(envios=[con_devolucion])
    r = corre(con.detalle(_Usuario(), "env_001", db=base))
    partidas = {c["partida"] for c in r["cobros"]}
    assert "devolucion" in partidas


def test_el_detalle_no_muestra_el_margen_ni_el_desglose_del_calculo():
    """Al usuario le importa qué le cobraron y por qué en una línea. El margen y
    el multiplicador de temporada, sueltos, invitan a discutir el precio de una
    tabla que ya aceptó."""
    base = db_completa()
    plano = repr(corre(con.detalle(_Usuario(), "env_001", db=base)))
    assert "margen" not in plano
    assert "22.00" not in plano
    assert "tarifa_version" not in plano


def test_el_detalle_no_muestra_las_referencias_como_si_fueran_un_precio():
    base = db_completa()
    plano = repr(corre(con.detalle(_Usuario(), "env_001", db=base)))
    assert "62.40" not in plano


def test_el_detalle_trae_la_linea_de_tiempo_en_orden():
    base = db_completa()
    r = corre(con.detalle(_Usuario(), "env_001", db=base))
    assert [e["estado"] for e in r["timeline"]] == ["esperando_postagem",
                                                    "en_transito_int"]
    assert all("monto_ris" not in repr(e) for e in r["timeline"])


def test_el_detalle_trae_el_token_para_compartir():
    """Acá sí: está detrás de la sesión y es del usuario. Lo que no puede es
    viajar en un aviso, que se reenvía."""
    base = db_completa()
    r = corre(con.detalle(_Usuario(), "env_001", db=base))
    assert r["tracking_token"] == "a" * 32


def test_el_detalle_dice_si_ya_se_cargo_el_comprobante():
    base = db_completa()
    r = corre(con.detalle(_Usuario(), "env_001", db=base))
    assert r["comprobante"]["codigo_objeto"] == "AA123456789BR"
    assert r["comprobante"]["verificado_at"] is None

    sin_comprobante = envio(1, origen={})
    sin_comprobante["origen"] = {}
    base2 = db_completa(envios=[sin_comprobante])
    assert corre(con.detalle(_Usuario(), "env_001", db=base2))["comprobante"] is None


# ─── 4. Las rutas se resuelven en el orden correcto ───────────────────────

def test_las_rutas_fijas_se_declaran_antes_que_la_comodin():
    """`GET /envios/{envio_id}` matchearía `/envios/limites` si se declarara
    antes. FastAPI resuelve por orden de declaración, y este es el error que se
    descubre cuando una ruta que funcionaba deja de funcionar."""
    fuente = open(os.path.join(_BACKEND, "routes", "envios.py"),
                  encoding="utf-8").read()
    comodin = fuente.index('@router.get("/{envio_id}")')
    for fija in ('@router.get("/limites")', '@router.get("/catalogo")',
                 '@router.get("/seguimiento/{token}")'):
        assert fuente.index(fija) < comodin, fija


@pytest.mark.parametrize("pagina,por_pagina", [
    (1_000_000, 50), (10 ** 12, 20), ("muchas", "todas"), (None, None), (-5, -5),
])
def test_ni_la_pagina_ni_el_tamano_pueden_pedirle_de_todo_a_la_base(pagina, por_pagina):
    """Los dos llegan por la URL. Con `to_list(pagina * por_pagina + 1)`, una
    página de un millón le pide cincuenta millones de documentos a la base."""
    base = db_completa(envios=[envio(i) for i in range(1, 5)])
    pedidos = []
    original = base.envios.find

    def espiar(filtro=None, proyeccion=None):
        cursor = original(filtro, proyeccion)
        to_list_original = cursor.to_list

        async def contar(n):
            pedidos.append(n)
            return await to_list_original(n)
        cursor.to_list = contar
        return cursor
    base.envios.find = espiar

    r = corre(con.listar(_Usuario(), pagina=pagina, por_pagina=por_pagina, db=base))
    assert r["degradado"] is False
    assert pedidos[0] <= con.PAGINA_MAX * con.POR_PAGINA_MAX + 1


def test_un_documento_roto_no_se_lleva_puesta_la_lista_entera():
    """`_fila` corría fuera del try. Con un envío a medio migrar —`destinatario`
    como texto en vez de dict— la lista entera del usuario devolvía un 500."""
    roto = envio(2)
    # `cobros` viaja entero en la proyección, así que un valor con otra forma
    # llega hasta `partidas_impagas`. (Un `destinatario` roto no sirve para este
    # test: la proyección con notación de punto ya lo descarta antes.)
    roto["cobros"] = "esto no es un dict"
    base = db_completa(envios=[envio(1), roto])
    r = corre(con.listar(_Usuario(), db=base))
    assert [e["envio_id"] for e in r["envios"]] == ["env_001"]
    assert r["degradado"] is False


def test_un_documento_roto_tampoco_rompe_el_detalle():
    roto = envio(1)
    roto["cobros"] = "esto no es un dict"
    base = db_completa(envios=[roto])
    assert corre(con.detalle(_Usuario(), "env_001", db=base)) is None


# ─── El detalle no lleva datos internos ───────────────────────────────────

def test_el_detalle_no_le_da_al_usuario_quien_peso_su_paquete():
    """`repesar` escribe `verificado_por` —el user_id del OPERADOR— adentro de
    `paquete.verificado`, y el detalle devolvía el bloque entero.

    No lo renderizaba ninguna pantalla, que es la peor forma de filtrar un dato:
    la que nadie ve, y que aparece el día que alguien mira el JSON. El resto del
    módulo usa listas blancas por esta misma razón.
    """
    doc = envio(1)
    doc["paquete"]["verificado"] = {
        "peso_kg": "3.10", "largo_cm": "41", "ancho_cm": "30", "alto_cm": "21",
        "verificado_por": "usr_operador_secreto",
        "verificado_at": AHORA, "tarifa_version": "tar_2026_08_a",
    }
    base = db_completa(envios=[doc])
    salida = corre(con.detalle(_Usuario(), "env_001", db=base))

    verificado = salida["paquete"]["verificado"]
    assert verificado["peso_kg"] == "3.10"
    assert "verificado_por" not in verificado
    assert "usr_operador_secreto" not in repr(salida)


def test_el_detalle_sin_repesaje_no_inventa_un_bloque_vacio():
    base = db_completa()
    salida = corre(con.detalle(_Usuario(), "env_001", db=base))
    assert salida["paquete"]["verificado"] is None
