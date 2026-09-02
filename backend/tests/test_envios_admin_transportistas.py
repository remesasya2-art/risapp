"""
Las rutas de transportistas y agencias, probadas de verdad.

QUE SE CUBRE, Y POR QUE ESTAS COSAS
    1. **Una ficha sigue siendo editable despues de cambiar la cuenta bancaria.**
       `cambiar_cuenta` agrega `cuentas_anteriores` con un $push, y el modelo es
       `extra="forbid"`: la edicion parcial fusionaba con el documento entero y
       devolvia 400 para siempre a partir del PRIMER cambio de cuenta. Con un
       mensaje de Pydantic que no significa nada para quien lo lee.
    2. **El rol no se cambia con una cuenta cargada.** Pasar de venezuela a
       brasil dejaba una cuenta bancaria viva colgando de alguien que no cobra
       flete, e invisible: el panel solo muestra esa seccion en el rol venezuela.
    3. **Una agencia se puede corregir.** Sin esta ruta, marcar como punto de
       entrega una agencia ya cargada solo se podia hacer reimportando un CSV —y
       un CSV que no trae una columna la borra en todas las filas.
    4. **Solo una agencia es el punto de entrega.** Dos es un envio que no sabe a
       donde va.

El arnes es el mismo de test_envios_admin_nomina: paquete `routes` vacio y carga
por ruta directa, para no arrastrar el proyecto entero.
"""
import asyncio
import importlib.util
import os
import sys
import types
from datetime import datetime, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)


class _Resultado:
    def __init__(self, n=1):
        self.matched_count = n
        self.modified_count = n


def _proyectar(doc, proyeccion):
    import copy
    if not proyeccion:
        return copy.deepcopy(doc)
    incluir = [k for k, v in proyeccion.items() if v and k != "_id"]
    if incluir:
        return copy.deepcopy({k: v for k, v in doc.items() if k in incluir})
    excluir = [k for k, v in proyeccion.items() if not v]
    return copy.deepcopy({k: v for k, v in doc.items() if k not in excluir})


class _Coleccion:
    def __init__(self, filas=None):
        self.filas = filas if filas is not None else []

    def _match(self, d, filtro):
        return all(d.get(k) == v for k, v in (filtro or {}).items())

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
        self.filas.append(dict(doc))
        return _Resultado()

    async def update_one(self, filtro, cambio, upsert=False):
        for d in self.filas:
            if self._match(d, filtro):
                d.update(cambio.get("$set") or {})
                for clave, valor in (cambio.get("$push") or {}).items():
                    d.setdefault(clave, []).append(valor)
                return _Resultado()
        return _Resultado(0)

    async def update_many(self, filtro, cambio):
        n = 0
        for d in self.filas:
            if self._match(d, filtro):
                d.update(cambio.get("$set") or {})
                n += 1
        return _Resultado(n)


class _Db:
    def __init__(self):
        self._c = {}

    def __getattr__(self, nombre):
        return self._c.setdefault(nombre, _Coleccion([]))


DB = _Db()


def _preparar():
    if "routes" not in sys.modules:
        paquete = types.ModuleType("routes")
        paquete.__path__ = [os.path.join(_BACKEND, "routes")]
        sys.modules["routes"] = paquete

    from conftest import usar_base
    usar_base(DB)

    if "routes.dependencies" not in sys.modules:
        deps = types.ModuleType("routes.dependencies")
        for nombre in ("get_current_user", "get_admin_user", "get_crm_user",
                       "get_super_admin", "get_verified_user"):
            setattr(deps, nombre, (lambda n: (lambda: None))(nombre))
        sys.modules["routes.dependencies"] = deps

    if "services" not in sys.modules:
        paquete = types.ModuleType("services")
        paquete.__path__ = [os.path.join(_BACKEND, "services")]
        sys.modules["services"] = paquete
    for nombre in ("money", "envios_tarifas", "envios_policy", "referencias",
                   "envios_catalogo", "envios_config", "envios_retiro",
                   "envios_tarifa_editor"):
        completo = f"services.{nombre}"
        if completo not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                completo, os.path.join(_BACKEND, "services", f"{nombre}.py"))
            modulo = importlib.util.module_from_spec(spec)
            sys.modules[completo] = modulo
            spec.loader.exec_module(modulo)

    if "routes.envios_admin" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "routes.envios_admin", os.path.join(_BACKEND, "routes", "envios_admin.py"))
        modulo = importlib.util.module_from_spec(spec)
        sys.modules["routes.envios_admin"] = modulo
        spec.loader.exec_module(modulo)
    return sys.modules["routes.envios_admin"]


ra = _preparar()
from fastapi import HTTPException                                    # noqa: E402
from models.envios_config import CuentaBancaria                      # noqa: E402


def corre(coro):
    return asyncio.run(coro)


AHORA = datetime.now(timezone.utc)


class _Admin:
    user_id = "usr_super"
    email = "super@risappbr.com"


TRP_VE = {
    "transportista_id": "trp_ve", "codigo": "TRP-VE1", "nombre": "Empresa de destino",
    "rol": "venezuela", "activo": True, "orden": 2, "moneda": "USD",
    "regla_peso": {"divisor": 5000, "escalon_kg": "1", "minimo_kg": "1",
                   "umbral_cubado_kg": None},
    "limites": {"peso_max_kg": "30", "lado_max_cm": None, "suma_lados_max_cm": None,
                "largo_min_cm": None, "ancho_min_cm": None, "alto_min_cm": None,
                "suma_lados_min_cm": None, "valor_declarado_max": None},
    "plantilla_rastreo": None, "fuente_referencia": None, "notas": None,
    "cuenta_bancaria": None, "creado_at": AHORA,
}

AGENCIA = {"transportista_id": "trp_ve", "codigo": "001", "nombre": "Santa Elena",
           "estado": "Bolívar", "ciudad": "Santa Elena", "direccion": "Av. Perimetral",
           "zona": "centro", "codigo_postal": None, "activa": True,
           "es_punto_entrega": False, "creada_at": AHORA}


@pytest.fixture(autouse=True)
def base_limpia():
    import copy
    from conftest import usar_base
    usar_base(DB)
    DB._c.clear()
    DB._c["transportistas"] = _Coleccion([copy.deepcopy(TRP_VE)])
    DB._c["agencias"] = _Coleccion([copy.deepcopy(AGENCIA)])
    DB._c["centro_gestion_log"] = _Coleccion([])
    DB._c["app_settings"] = _Coleccion([])
    yield


CUENTA = {"banco": "Banco de Venezuela", "tipo_cuenta": "corriente",
          "numero": "01021234567890123456", "titular": "Empresa de destino CA",
          "documento": "J-12345678-9"}


def _cambiar_cuenta():
    return corre(ra.cambiar_cuenta("trp_ve", ra.CambioDeCuenta(
        cuenta=CuentaBancaria(**CUENTA), confirmacion_numero=CUENTA["numero"],
        motivo="alta inicial"), _Admin()))


# ─── 1. La ficha sigue viva después de cambiar la cuenta ──────────────────

def test_editar_un_transportista_despues_de_cambiarle_la_cuenta():
    """EL DEFECTO. `cambiar_cuenta` hace $push a `cuentas_anteriores`; el modelo
    es `extra="forbid"` y la edición parcial fusionaba con el documento ENTERO.
    A partir del primer cambio de cuenta, corregir el nombre o el divisor
    devolvía 400 con un mensaje de Pydantic que no dice nada."""
    _cambiar_cuenta()
    _cambiar_cuenta()          # el segundo es el que llena `cuentas_anteriores`
    fila = DB.transportistas.filas[0]
    assert fila.get("cuentas_anteriores"), "el arnés no reprodujo el $push"

    salida = corre(ra.editar_transportista("trp_ve", {"nombre": "Otro nombre"}, _Admin()))
    assert salida["ok"] is True
    assert DB.transportistas.filas[0]["nombre"] == "Otro nombre"
    # Y la cuenta vigente no se tocó: tiene su propia ruta, con confirmación.
    assert DB.transportistas.filas[0]["cuenta_bancaria"]["numero"] == CUENTA["numero"]


def test_editar_no_borra_el_historial_de_cuentas():
    """Queda para poder contestar «¿a qué cuenta le pagó este usuario en marzo?»."""
    _cambiar_cuenta()
    _cambiar_cuenta()
    antes = len(DB.transportistas.filas[0]["cuentas_anteriores"])
    corre(ra.editar_transportista("trp_ve", {"orden": 5}, _Admin()))
    assert len(DB.transportistas.filas[0]["cuentas_anteriores"]) == antes


def test_el_codigo_y_la_cuenta_siguen_sin_editarse_por_esta_ruta():
    for campo in ("codigo", "cuenta_bancaria", "transportista_id"):
        with pytest.raises(HTTPException) as e:
            corre(ra.editar_transportista("trp_ve", {campo: "x"}, _Admin()))
        assert e.value.status_code == 400


# ─── 2. El rol no se cambia con una cuenta cargada ────────────────────────

def test_no_se_cambia_el_rol_con_una_cuenta_bancaria_viva():
    """Pasar a Brasil deja una cuenta bancaria colgando de alguien que no cobra
    flete, y encima invisible: el panel solo muestra esa sección en Venezuela."""
    _cambiar_cuenta()
    with pytest.raises(HTTPException) as e:
        corre(ra.editar_transportista("trp_ve", {"rol": "brasil"}, _Admin()))
    assert e.value.status_code == 400
    assert "cuenta bancaria" in e.value.detail
    assert DB.transportistas.filas[0]["rol"] == "venezuela"


def test_sin_cuenta_cargada_el_rol_se_puede_corregir():
    """Un rol mal elegido al alta tiene que poder arreglarse: es el error más
    fácil de cometer en el formulario, y todavía no hay nada colgando de él."""
    salida = corre(ra.editar_transportista("trp_ve", {"rol": "brasil"}, _Admin()))
    assert salida["ok"] is True
    assert DB.transportistas.filas[0]["rol"] == "brasil"


# ─── 3. Una agencia se puede corregir ─────────────────────────────────────

def test_marcar_el_punto_de_entrega_de_una_agencia_que_ya_existe():
    """Sin esta ruta, el único camino era reimportar un CSV — y un CSV que no
    trae una columna la borra en todas las filas."""
    salida = corre(ra.editar_agencia("trp_ve", "001", {"es_punto_entrega": True},
                                     _Admin()))
    assert salida["ok"] is True
    assert DB.agencias.filas[0]["es_punto_entrega"] is True
    # Y no se llevó puesto nada de lo que no se mandó.
    assert DB.agencias.filas[0]["zona"] == "centro"
    assert DB.agencias.filas[0]["direccion"] == "Av. Perimetral"


def test_marcar_una_libera_la_anterior():
    """Dos puntos de entrega es un envío que no sabe a dónde va."""
    import copy
    DB._c["agencias"].filas.append({**copy.deepcopy(AGENCIA), "codigo": "014",
                                    "nombre": "Puerto Ordaz"})
    corre(ra.editar_agencia("trp_ve", "001", {"es_punto_entrega": True}, _Admin()))
    corre(ra.editar_agencia("trp_ve", "014", {"es_punto_entrega": True}, _Admin()))
    marcadas = [a for a in DB.agencias.filas if a["es_punto_entrega"]]
    assert [a["codigo"] for a in marcadas] == ["014"]


def test_desactivar_una_agencia_no_la_borra():
    corre(ra.editar_agencia("trp_ve", "001", {"activa": False}, _Admin()))
    assert len(DB.agencias.filas) == 1
    assert DB.agencias.filas[0]["activa"] is False


def test_el_codigo_de_una_agencia_no_se_cambia():
    """Es cómo la identifica el CSV y cómo la referencian los envíos viejos."""
    with pytest.raises(HTTPException) as e:
        corre(ra.editar_agencia("trp_ve", "001", {"codigo": "002"}, _Admin()))
    assert e.value.status_code == 400


def test_mandar_el_mismo_codigo_no_molesta():
    """El formulario reenvía la fila entera; rechazar el código igual a sí mismo
    sería rechazar el caso normal."""
    salida = corre(ra.editar_agencia("trp_ve", "001",
                                     {"codigo": "001", "ciudad": "Santa Elena de Uairén"},
                                     _Admin()))
    assert salida["ok"] is True
    assert DB.agencias.filas[0]["ciudad"] == "Santa Elena de Uairén"


def test_editar_una_agencia_que_no_existe_es_404():
    with pytest.raises(HTTPException) as e:
        corre(ra.editar_agencia("trp_ve", "999", {"activa": False}, _Admin()))
    assert e.value.status_code == 404


def test_una_agencia_invalida_se_rechaza_con_el_campo():
    with pytest.raises(HTTPException) as e:
        corre(ra.editar_agencia("trp_ve", "001", {"estado": ""}, _Admin()))
    assert e.value.status_code == 400
    assert "estado" in e.value.detail.lower()


def test_los_metadatos_de_la_fila_no_entran_al_modelo():
    """`creada_at` y `transportista_id` viven en el documento y no en `Agencia`,
    que es `extra="forbid"`: fusionar sin filtrar los volvía un 400."""
    salida = corre(ra.editar_agencia("trp_ve", "001", {"nombre": "Santa Elena Centro"},
                                     _Admin()))
    assert salida["valor"]["transportista_id"] == "trp_ve"
    assert "creada_at" not in salida["valor"]
    assert DB.agencias.filas[0]["creada_at"] == AGENCIA["creada_at"]


# ─── La marca de punto de entrega es UNA, y se puede reparar ──────────────
#
# En produccion quedaron 250 agencias marcadas: un CSV con la columna en
# verdadero en todas las filas. El semaforo de puesta en marcha lo daba por
# bueno —exigia "al menos una"— y el panel no tenia forma de arreglarlo.

def test_guardar_la_correcta_desmarca_a_las_demas_aunque_ya_estuviera_marcada():
    """El camino de REPARACION de una base que ya quedo con varias marcadas.

    Antes se liberaba solo `if es_punto_entrega and not actual.es_punto_entrega`:
    con las dos ya marcadas, guardar la buena no desmarcaba a la otra y no habia
    forma de salir del estado invalido desde el panel. Es la mutacion de esta
    guarda: restaurar esa condicion vuelve a dejar ['001', '014'].
    """
    import copy
    DB._c["agencias"].filas.append({**copy.deepcopy(AGENCIA), "codigo": "014",
                                    "nombre": "Puerto Ordaz", "es_punto_entrega": True})
    DB.agencias.filas[0]["es_punto_entrega"] = True

    corre(ra.editar_agencia("trp_ve", "014", {"es_punto_entrega": True}, _Admin()))

    marcadas = [a["codigo"] for a in DB.agencias.filas if a["es_punto_entrega"]]
    assert marcadas == ["014"]


def test_un_csv_que_marca_dos_puntos_de_entrega_no_escribe_nada():
    """El archivo entero se rechaza, no la fila: es una instruccion contradictoria
    sobre una marca unica, y no hay forma de elegir por la persona cual quiso.

    Importar "casi todo" dejaria exactamente el estado que esto viene a impedir.
    """
    csv_malo = (
        "codigo,nombre,estado,ciudad,es_punto_entrega\n"
        "010,Uno,Bolívar,Santa Elena,true\n"
        "011,Dos,Bolívar,Tumeremo,true\n"
    )
    with pytest.raises(HTTPException) as e:
        corre(ra.importar_agencias("trp_ve", _Archivo(csv_malo), _Admin()))
    assert e.value.status_code == 400
    assert "2 filas" in e.value.detail
    # Y NADA se escribio: sigue estando solo la agencia del fixture.
    assert [a["codigo"] for a in DB.agencias.filas] == ["001"]


def test_un_csv_que_marca_una_sola_libera_a_las_anteriores():
    """La otra mitad: el CSV valido tiene que dejar la marca donde dice, y sola."""
    DB.agencias.filas[0]["es_punto_entrega"] = True
    csv_bueno = (
        "codigo,nombre,estado,ciudad,es_punto_entrega\n"
        "010,Uno,Bolívar,Santa Elena,true\n"
        "011,Dos,Bolívar,Tumeremo,false\n"
    )
    corre(ra.importar_agencias("trp_ve", _Archivo(csv_bueno), _Admin()))
    marcadas = [a["codigo"] for a in DB.agencias.filas if a["es_punto_entrega"]]
    assert marcadas == ["010"]


class _Archivo:
    """El UploadFile que espera la ruta, reducido a lo unico que usa: read()."""

    def __init__(self, texto: str):
        self._bytes = texto.encode("utf-8")

    async def read(self):
        return self._bytes


# ─── La plantilla de rastreo tiene que rastrear ───────────────────────────

def test_una_plantilla_de_rastreo_sin_codigo_se_rechaza():
    """Sin `{codigo}` la URL apunta a la portada: el usuario hace clic, cae en la
    home de una empresa que no conoce y cree que perdio el paquete.

    Mutacion: sacar la guarda deja pasar la URL y este test se pone en rojo.
    """
    with pytest.raises(HTTPException) as e:
        corre(ra.editar_transportista(
            "trp_ve", {"plantilla_rastreo": "https://rastreo.example/consulta"},
            _Admin()))
    assert e.value.status_code == 400
    assert "{codigo}" in e.value.detail


def test_una_plantilla_de_rastreo_vacia_es_valida():
    """A proposito: hay transportistas cuyo rastreo es un formulario que se
    completa a mano y no tienen enlace directo. Obligarlos a inventar uno seria
    obligarlos a cargar un enlace que no rastrea."""
    for vacia in (None, "", "   "):
        salida = corre(ra.editar_transportista(
            "trp_ve", {"plantilla_rastreo": vacia}, _Admin()))
        assert not (salida["valor"].get("plantilla_rastreo") or "").strip()


def test_una_plantilla_de_rastreo_con_codigo_se_acepta():
    salida = corre(ra.editar_transportista(
        "trp_ve", {"plantilla_rastreo": "https://rastreo.example/g/{codigo}"},
        _Admin()))
    assert salida["valor"]["plantilla_rastreo"].endswith("{codigo}")


# ─── Una plantilla rota no toma de rehen al resto de la ficha ─────────────

def test_una_plantilla_vieja_rota_no_bloquea_editar_otro_campo():
    """La ficha entera se valida —hace falta, es un merge— pero una plantilla
    YA GUARDADA sin `{codigo}` no puede tomar de rehen al resto.

    Sin esto, cambiarle el nombre a un transportista devolvia un 400 hablando
    del rastreo, un campo que la persona no toco. Y es la misma pantalla donde
    se corrige un limite mal cargado: el mensaje llegaba en el peor momento
    posible, hablando de otra cosa.
    """
    DB.transportistas.filas[0]["plantilla_rastreo"] = "https://rastreo.example/consulta"

    salida = corre(ra.editar_transportista(
        "trp_ve", {"nombre": "Otro nombre"}, _Admin()))

    assert salida["valor"]["nombre"] == "Otro nombre"
    # Y la plantilla rota se guardo TAL CUAL: no se pisa ni se borra.
    assert salida["valor"]["plantilla_rastreo"] == "https://rastreo.example/consulta"
    # Pero no se guarda en silencio: se avisa.
    assert salida["avisos"] and "{codigo}" in salida["avisos"][0]


def test_editar_la_plantilla_rota_si_la_valida():
    """La excepcion es SOLO para la heredada. En cuanto se toca el campo, el
    validador manda: si no, la puerta quedaria abierta para siempre.

    MUTACION: sacar el `"plantilla_rastreo" not in datos` de la condicion deja
    pasar esto y el test se pone en rojo.
    """
    DB.transportistas.filas[0]["plantilla_rastreo"] = "https://rastreo.example/consulta"

    with pytest.raises(HTTPException) as e:
        corre(ra.editar_transportista(
            "trp_ve", {"plantilla_rastreo": "https://otra.example/tambien-sin-token"},
            _Admin()))
    assert e.value.status_code == 400
    assert "{codigo}" in e.value.detail


def test_arreglar_la_plantilla_rota_se_puede_y_no_deja_aviso():
    DB.transportistas.filas[0]["plantilla_rastreo"] = "https://rastreo.example/consulta"

    salida = corre(ra.editar_transportista(
        "trp_ve", {"plantilla_rastreo": "https://rastreo.example/g/{codigo}"},
        _Admin()))
    assert salida["valor"]["plantilla_rastreo"].endswith("{codigo}")
    assert salida["avisos"] == []


def test_una_ficha_sana_no_arrastra_ningun_aviso():
    salida = corre(ra.editar_transportista("trp_ve", {"nombre": "Sano"}, _Admin()))
    assert salida["avisos"] == []
