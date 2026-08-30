"""
Que dejo cada viaje, y que precio se vio de verdad.

DOS PREGUNTAS CON LOS MISMOS DATOS
    Cuanto dejo un viaje a Pacaraima, y cuanto cobra de verdad cada tramo que el
    usuario paga por su cuenta.

LA REGLA DURA
    NINGUNA sugerencia se escribe sola. Se propone y alguien aprueba. Un job que
    corrige precios solo es un job que un dia mueve un numero por una muestra
    rara, y nadie se entera hasta que un usuario pregunta por que le dijimos que
    iba a pagar el doble.

QUE SE CUBRE
    1. Lo pendiente no se suma a lo cobrado.
    2. Sin el costo del viaje no hay resultado, y se dice que falta.
    3. Pocas muestras o mucha dispersion no son un precio: se marcan.
    4. `observaciones()` no escribe una sola fila.
    5. Lo observado no toca lo que RIS App factura.
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
rent = _cargar("envios_rentabilidad")


def corre(coro):
    return asyncio.run(coro)


AHORA = datetime.now(timezone.utc)


class _Admin:
    user_id = "usr_super"


def envio_del_lote(i, *, cobrado="132.00", estado_cobro="pagado", peso="2.30",
                   lote="lot_x", uf="SP", pagado_brl=None, zona="zona_a",
                   flete=None, creado_hace=1):
    return {
        "envio_id": f"env_{i:03d}", "display_id": f"E{i:06d}",
        "user_id": "usr_ana", "estado": "en_transito_int",
        "created_at": AHORA - timedelta(days=creado_hace),
        "origen": {"lote_retiro_id": lote, "uf": uf,
                   "monto_pagado_brl": pagado_brl},
        "destino": {"zona_tarifa": zona},
        "flete": {"monto_acordado_ris": flete} if flete else {},
        "paquete": {"declarado": {"peso_kg": peso},
                    "verificado": {"peso_kg": peso}},
        "cobros": {"inicial": {"monto_ris": cobrado, "estado": estado_cobro},
                   "ajuste": None},
    }


def db_completa(envios=None, lotes=None):
    import copy
    base = _Db(
        envios=copy.deepcopy(envios if envios is not None else []),
        envios_lotes=copy.deepcopy(lotes if lotes is not None else [
            {"lote_id": "lot_x", "retirado_por": "usr_operador",
             "created_at": AHORA - timedelta(days=1), "cuantos": 0}]),
        matrices_referencia=[], centro_gestion_log=[],
    )
    usar_base(base)
    return base


# ─── 1. Rentabilidad por viaje ────────────────────────────────────────────

def test_el_viaje_suma_lo_que_se_cobro_por_sus_paquetes():
    base = db_completa(envios=[envio_del_lote(1), envio_del_lote(2, cobrado="185.00")])
    r = corre(rent.por_lote("lot_x", db=base))
    assert r["cuantos"] == 2
    assert Decimal(r["cobrado_ris"]) == Decimal("317.00")


def test_lo_pendiente_no_se_suma_a_lo_cobrado():
    """Sumarlo daría un viaje rentable con plata que todavía no entró, que es la
    forma clásica de creerse rentable seis meses seguidos."""
    base = db_completa(envios=[
        envio_del_lote(1),
        envio_del_lote(2, cobrado="185.00", estado_cobro="pendiente")])
    r = corre(rent.por_lote("lot_x", db=base))
    assert Decimal(r["cobrado_ris"]) == Decimal("132.00")
    assert Decimal(r["pendiente_ris"]) == Decimal("185.00")


def test_una_devolucion_resta_de_lo_cobrado():
    envio = envio_del_lote(1)
    envio["cobros"]["devolucion"] = {"monto_ris": "12.00", "estado": "acreditado"}
    base = db_completa(envios=[envio])
    r = corre(rent.por_lote("lot_x", db=base))
    assert Decimal(r["cobrado_ris"]) == Decimal("120.00")


def test_sin_el_costo_no_hay_resultado_y_se_dice():
    """Estimarlo sería inventar justamente la parte que hace que el resultado sea
    un resultado."""
    base = db_completa(envios=[envio_del_lote(1)])
    r = corre(rent.por_lote("lot_x", db=base))
    assert r["resultado_ris"] is None
    assert r["falta_el_costo"] is True
    assert r["costo_por_kg_ris"] is None


def test_con_el_costo_cargado_sale_el_resultado_y_el_costo_por_kilo():
    base = db_completa(envios=[envio_del_lote(1, peso="4.00"),
                               envio_del_lote(2, peso="6.00")])
    r = corre(rent.cargar_costo(_Admin(), "lot_x", "80.00", db=base, ahora=AHORA))
    assert Decimal(r["resultado_ris"]) == Decimal("264.00") - Decimal("80.00")
    assert Decimal(r["peso_total_kg"]) == Decimal("10.00")
    assert Decimal(r["costo_por_kg_ris"]) == Decimal("8.00")
    assert r["falta_el_costo"] is False


def test_un_costo_ilegible_se_rechaza():
    base = db_completa(envios=[envio_del_lote(1)])
    for malo in ("", "gratis", "0", "-50", None):
        with pytest.raises(rent.RentabilidadRechazada):
            corre(rent.cargar_costo(_Admin(), "lot_x", malo, db=base, ahora=AHORA))


def test_un_viaje_que_no_existe_es_404():
    base = db_completa()
    with pytest.raises(rent.RentabilidadRechazada) as e:
        corre(rent.por_lote("lot_no_existe", db=base))
    assert e.value.http == 404


def test_un_viaje_sin_paquetes_no_revienta():
    base = db_completa(envios=[])
    r = corre(rent.por_lote("lot_x", db=base))
    assert r["cuantos"] == 0 and Decimal(r["cobrado_ris"]) == 0


# ─── 2. Los precios observados ────────────────────────────────────────────

def test_se_observa_lo_que_el_usuario_pago_en_el_mostrador_de_origen():
    base = db_completa(envios=[
        envio_del_lote(i, pagado_brl=p, peso="2.00")
        for i, p in enumerate(["60.00", "62.00", "64.00", "58.00"], start=1)])
    obs = corre(rent.observaciones(db=base, ahora=AHORA))
    brasil = [o for o in obs if o["rol"] == "brasil"]
    assert len(brasil) == 1
    assert brasil[0]["clave"] == "SP" and brasil[0]["muestras"] == 4
    assert Decimal(brasil[0]["promedio"]) == Decimal("61.00")
    assert brasil[0]["confiable"] is True


def test_se_observa_lo_que_pidio_el_transportista_de_destino():
    base = db_completa(envios=[
        envio_del_lote(i, flete=f, peso="2.00")
        for i, f in enumerate(["300.00", "310.00", "305.00", "295.00"], start=1)])
    obs = corre(rent.observaciones(db=base, ahora=AHORA))
    ve = [o for o in obs if o["rol"] == "venezuela"]
    assert len(ve) == 1 and ve[0]["clave"] == "zona_a"
    assert Decimal(ve[0]["promedio"]) == Decimal("302.50")


def test_pocas_muestras_no_son_un_precio():
    """Una sugerencia con dos observaciones no es un precio: es ruido."""
    base = db_completa(envios=[envio_del_lote(1, pagado_brl="60.00"),
                               envio_del_lote(2, pagado_brl="62.00")])
    obs = corre(rent.observaciones(db=base, ahora=AHORA))
    assert obs[0]["confiable"] is False
    assert "2 observaciones" in obs[0]["por_que_no"]


def test_mucha_dispersion_tampoco():
    base = db_completa(envios=[
        envio_del_lote(i, pagado_brl=p, peso="2.00")
        for i, p in enumerate(["20.00", "200.00", "45.00", "180.00"], start=1)])
    obs = corre(rent.observaciones(db=base, ahora=AHORA))
    assert obs[0]["confiable"] is False
    assert "varían" in obs[0]["por_que_no"]
    # Y el promedio se muestra igual, con el mínimo y el máximo al lado.
    assert Decimal(obs[0]["minimo"]) == Decimal("20.00")
    assert Decimal(obs[0]["maximo"]) == Decimal("200.00")


def test_se_agrupa_por_franja_de_peso_y_no_por_peso_exacto():
    """Un promedio de precios de paquetes de 1 kg y de 9 kg no es el precio de
    ninguno de los dos."""
    base = db_completa(envios=[
        envio_del_lote(1, pagado_brl="30.00", peso="0.80"),
        envio_del_lote(2, pagado_brl="32.00", peso="0.90"),
        envio_del_lote(3, pagado_brl="90.00", peso="8.00"),
        envio_del_lote(4, pagado_brl="95.00", peso="9.00")])
    obs = corre(rent.observaciones(db=base, ahora=AHORA))
    por_franja = {o["hasta_kg"]: o for o in obs}
    assert set(por_franja) == {"1", "10"}
    assert Decimal(por_franja["1"]["promedio"]) == Decimal("31.00")
    assert Decimal(por_franja["10"]["promedio"]) == Decimal("92.50")


def test_un_monto_en_cero_o_ilegible_no_entra_al_promedio():
    """Un cero inventado baja el precio observado de un tramo, que es el número
    que después se le muestra a otro usuario como orientación."""
    base = db_completa(envios=[
        envio_del_lote(1, pagado_brl="60.00"), envio_del_lote(2, pagado_brl="0"),
        envio_del_lote(3, pagado_brl=""), envio_del_lote(4, pagado_brl="gratis"),
        envio_del_lote(5, pagado_brl="62.00")])
    obs = corre(rent.observaciones(db=base, ahora=AHORA))
    assert obs[0]["muestras"] == 2
    assert Decimal(obs[0]["promedio"]) == Decimal("61.00")


def test_se_usa_el_peso_verificado_y_no_el_declarado():
    """El verificado salió de nuestra balanza. Usar el declarado cuando existe el
    verificado metería en la muestra un peso que nadie confirmó."""
    envio = envio_del_lote(1, pagado_brl="60.00")
    envio["paquete"]["declarado"]["peso_kg"] = "0.50"
    envio["paquete"]["verificado"]["peso_kg"] = "8.00"
    base = db_completa(envios=[envio])
    obs = corre(rent.observaciones(db=base, ahora=AHORA))
    assert obs[0]["hasta_kg"] == "10"


def test_lo_viejo_no_entra():
    base = db_completa(envios=[
        envio_del_lote(1, pagado_brl="60.00", creado_hace=200),
        envio_del_lote(2, pagado_brl="62.00", creado_hace=2)])
    obs = corre(rent.observaciones(db=base, ahora=AHORA, dias=90))
    assert obs[0]["muestras"] == 1


def test_observar_no_escribe_una_sola_fila():
    """LA REGLA DURA. Un job que corrige precios solo es un job que un día mueve
    un número por una muestra rara."""
    base = db_completa(envios=[envio_del_lote(i, pagado_brl="60.00")
                               for i in range(1, 8)])
    corre(rent.observaciones(db=base, ahora=AHORA))
    assert base.matrices_referencia.filas == []


def test_si_la_base_falla_no_se_inventan_observaciones():
    base = db_completa()
    base.envios.find = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    assert corre(rent.observaciones(db=base, ahora=AHORA)) == []


# ─── 3. Aprobar es lo único que escribe ───────────────────────────────────

def test_aprobar_deja_la_fila_marcada_como_observada():
    """Es lo que después permite distinguir un precio que vimos de uno que
    alguien tipeó."""
    base = db_completa()
    r = corre(rent.aprobar(_Admin(), transportista_id="trp_br1", clave="SP",
                           hasta_kg="3", precio="61.00", moneda="BRL",
                           db=base, ahora=AHORA))
    fila = base.matrices_referencia.filas[0]
    assert fila["origen"] == "observado"
    assert fila["aprobada_por"] == "usr_super"
    assert Decimal(fila["precio"]) == Decimal("61.00")
    assert r["ok"] is True


def test_aprobar_dos_veces_actualiza_la_misma_fila():
    base = db_completa()
    for precio in ("61.00", "64.00"):
        corre(rent.aprobar(_Admin(), transportista_id="trp_br1", clave="SP",
                           hasta_kg="3", precio=precio, db=base, ahora=AHORA))
    assert len(base.matrices_referencia.filas) == 1
    assert Decimal(base.matrices_referencia.filas[0]["precio"]) == Decimal("64.00")


@pytest.mark.parametrize("cambio", [
    {"precio": "0"}, {"precio": "gratis"}, {"hasta_kg": ""}, {"clave": "  "},
])
def test_aprobar_algo_incompleto_no_escribe(cambio):
    base = db_completa()
    datos = {"transportista_id": "trp_br1", "clave": "SP", "hasta_kg": "3",
             "precio": "61.00"}
    datos.update(cambio)
    with pytest.raises(rent.RentabilidadRechazada):
        corre(rent.aprobar(_Admin(), db=base, ahora=AHORA, **datos))
    assert base.matrices_referencia.filas == []


def test_aprobar_queda_auditado():
    base = db_completa()
    corre(rent.aprobar(_Admin(), transportista_id="trp_br1", clave="SP",
                       hasta_kg="3", precio="61.00", db=base, ahora=AHORA))
    assert base.centro_gestion_log.filas, "aprobar un precio tiene que quedar registrado"


def test_lo_observado_no_toca_lo_que_ris_app_factura():
    """Son los dos tramos que el usuario paga por su cuenta. La tarifa propia se
    edita en su consola y no sale de acá."""
    fuente = open(os.path.join(_BACKEND, "services", "envios_rentabilidad.py"),
                  encoding="utf-8").read()
    codigo = "\n".join(l for l in fuente.split("\n")
                       if not l.lstrip().startswith("#"))
    for prohibido in ("tarifas_envio", "escalones_peso", "balance_ris",
                      "record_ris_entry", "cotizar_servicio"):
        assert prohibido not in codigo


def test_el_modulo_no_menciona_ninguna_marca():
    fuente = open(os.path.join(_BACKEND, "services", "envios_rentabilidad.py"),
                  encoding="utf-8").read().lower()
    for marca in ("mrw", "correios", "zoom", "tealca", "domesa"):
        assert marca not in fuente


def test_el_tope_de_peso_se_escribe_siempre_igual():
    """"10" y "10.0" son claves distintas y el índice de la matriz no es único:
    dejaban dos filas para el mismo tope, y el precio viejo se quedaba ahí
    esperando a ganar un desempate."""
    base = db_completa()
    for tope in ("10", "10.0", "10.00", " 10 "):
        corre(rent.aprobar(_Admin(), transportista_id="trp_br1", clave="SP",
                           hasta_kg=tope, precio="61.00", db=base, ahora=AHORA))
    assert len(base.matrices_referencia.filas) == 1
    assert base.matrices_referencia.filas[0]["hasta_kg"] == "10"


def test_un_tope_con_decimales_de_verdad_se_conserva():
    base = db_completa()
    corre(rent.aprobar(_Admin(), transportista_id="trp_br1", clave="SP",
                       hasta_kg="0.5", precio="30.00", db=base, ahora=AHORA))
    assert base.matrices_referencia.filas[0]["hasta_kg"] == "0.5"


def test_el_barrido_de_observaciones_tiene_indice():
    """Sin índice es un COLLSCAN con sort en memoria, y Mongo aborta el sort al
    pasar los 32 MB: la pantalla empieza a decir "sin observaciones" con un
    200 OK y nadie sabe que la consulta explotó."""
    indices = _cargar("envios_indices").INDICES
    assert any(c == "envios" and k == [("created_at", -1)] for c, k, _ in indices)
