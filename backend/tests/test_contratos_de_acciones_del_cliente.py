"""
tests/test_contratos_de_acciones_del_cliente.py — Las acciones del cliente
sobre encomiendas, beneficiarios y soporte salen por un contrato, y ningún
contrato se come un campo que su ruta devuelve.

Segunda tanda (la primera, lo que mueve plata, en
`test_contratos_de_acciones_de_dinero.py`).

La que más importa es la cotización de encomiendas, que alguna vez le mandó al
cliente el margen de ganancia. La sección 2 arma la respuesta REAL de la
cotización y la pasa por el contrato: tiene que salir entera, y lo que se le
agregue de más —el margen, el desglose— no tiene que salir.
"""
import ast
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

_BACKEND = Path(__file__).resolve().parents[1]

# (archivo de la ruta, método, camino, contrato, dónde se arma la respuesta)
# El último es (archivo, funciones): las rutas de encomiendas devuelven lo que
# arma un servicio, y las claves se leen de ahí.
RUTAS = [
    ("routes/envios.py", "POST", "/cotizar", "MiCotizacionDeEncomienda",
     ("services/envios_cotizador.py", ("_payload",))),
    ("routes/envios.py", "POST", "/crear", "MiEncomiendaCreada",
     ("services/envios_crear.py", ("_resultado",))),
    ("routes/envios.py", "POST", "/{envio_id}/cobros/{partida}/pagar", "MiCobroDeEncomienda",
     ("services/envios_cobros.py", ("_resultado", "_pendiente"))),
    ("routes/envios.py", "POST", "/{envio_id}/comprobante", "MiComprobanteDeEncomienda",
     ("services/envios_comprobante.py", ("_resultado",))),
    ("routes/transactions.py", "POST", "/beneficiaries", "MiBeneficiarioCreado", None),
    ("routes/transactions.py", "POST", "/beneficiaries/br", "MiBeneficiarioCreado", None),
    ("routes/transactions.py", "DELETE", "/beneficiaries/{beneficiary_id}", "MiBeneficiarioEliminado", None),
    ("routes/soporte.py", "POST", "/soporte/casos", "MiCasoAbierto", None),
    ("routes/soporte.py", "POST", "/soporte/casos/{caso_id}/mensajes", "MiRespuestaEnviada", None),
    ("routes/soporte.py", "POST", "/soporte/casos/{caso_id}/calificar", "MiCasoActualizado", None),
    ("routes/soporte.py", "POST", "/soporte/casos/{caso_id}/cerrar", "MiCasoActualizado", None),
]
_IDS = [f"{m} {c}" for _, m, c, _, _ in RUTAS]


def _ruta(archivo, metodo, camino):
    import importlib
    router = importlib.import_module(archivo[:-3].replace("/", ".")).router
    (r,) = [r for r in router.routes
            if r.path == (router.prefix or "") + camino and metodo in r.methods]
    return r


# ══════════════════════════════════════════════════════════════════════════
# 1. Cada ruta tiene su contrato, y el contrato no se come nada
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("archivo,metodo,camino,modelo,fuente", RUTAS, ids=_IDS)
def test_CADA_ACCION_TIENE_SU_CONTRATO(archivo, metodo, camino, modelo, fuente):
    ruta = _ruta(archivo, metodo, camino)
    assert ruta.response_model is not None and ruta.response_model.__name__ == modelo
    assert ruta.response_model_exclude_unset is True, "lo que la ruta no pone no tiene que salir como null"


def _de(d):
    return {k.value for k in d.keys if isinstance(k, ast.Constant)}


def _claves_de_las_funciones(archivo, nombres):
    """Las claves de primer nivel del diccionario que devuelven esas funciones."""
    arbol = ast.parse((_BACKEND / archivo).read_text(encoding="utf-8"))
    claves = set()
    encontradas = set()
    for f in ast.walk(arbol):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name in nombres:
            encontradas.add(f.name)
            for r in ast.walk(f):
                if isinstance(r, ast.Return) and isinstance(r.value, ast.Dict):
                    claves |= _de(r.value)
    assert encontradas == set(nombres), f"no encontré {set(nombres) - encontradas} en {archivo}"
    return claves


def _claves_de_la_ruta(archivo, metodo, camino):
    arbol = ast.parse((_BACKEND / archivo).read_text(encoding="utf-8"))
    for f in ast.walk(arbol):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                isinstance(d, ast.Call) and getattr(d.func, "attr", "") == metodo.lower()
                and d.args and isinstance(d.args[0], ast.Constant) and d.args[0].value == camino
                for d in f.decorator_list):
            return {k for r in ast.walk(f) if isinstance(r, ast.Return) and isinstance(r.value, ast.Dict)
                    for k in _de(r.value)}
    raise AssertionError(f"no encontré {metodo} {camino} en {archivo}")    # pragma: no cover


def _claves(archivo, metodo, camino, fuente):
    return _claves_de_las_funciones(*fuente) if fuente else _claves_de_la_ruta(archivo, metodo, camino)


@pytest.mark.parametrize("archivo,metodo,camino,modelo,fuente", RUTAS, ids=_IDS)
def test_EL_CONTRATO_NO_SE_COME_NINGUN_CAMPO_QUE_LA_ACCION_DEVUELVE(archivo, metodo, camino, modelo, fuente):
    ruta = _ruta(archivo, metodo, camino)
    faltan = _claves(archivo, metodo, camino, fuente) - set(ruta.response_model.model_fields)
    assert not faltan, f"{camino} devuelve {sorted(faltan)} y su contrato no los tiene: la pantalla los perdería"


def test_LA_LECTURA_DEL_CODIGO_ENCUENTRA_CLAVES():
    """Sin esto, el de arriba pasaría igual si la lectura dejara de encontrar
    diccionarios: cero claves de cero es verde y no prueba nada."""
    vacias = [c for a, m, c, _, f in RUTAS if not _claves(a, m, c, f)]
    assert vacias == [], vacias


# ══════════════════════════════════════════════════════════════════════════
# 2. La cotización de encomiendas, de punta a punta
# ══════════════════════════════════════════════════════════════════════════

def _cotizacion_real():
    """La respuesta que arma `envios_cotizador._payload`, con datos de ejemplo.
    Es la función de verdad: si mañana devuelve una clave nueva, la pasa por el
    contrato y el test de abajo se entera."""
    from services import envios_cotizador
    envio = {
        "envio_id": "env_1", "estado": "cotizado", "modalidad_flete": "origen",
        "paquete": {"pf_declarado": {"propio": "3.00", "TRP-7K2M": "3.50"}},
        # Lo que la cotización GUARDA y no tiene que mostrar: el desglose.
        "cotizacion": {"moneda": "RIS", "total_estimado_ris": "120.00",
                       "vence_at": "2026-09-25T00:00:00Z", "terminos_version": "v3",
                       "margen_ris": "20.00", "subtotal_ris": "100.00"},
    }
    servicio = {"peso_real_kg": "2.8", "peso_facturable_kg": "3.00", "peso_volumetrico_kg": "2.50"}
    referencias = [{"codigo": "TRP-7K2M", "rol": "brasil", "monto": "45.00", "moneda": "BRL",
                    "fuente": "matriz", "desactualizada": False}]
    despacho = {"destinatario": "RISApp LTDA", "ciudad": "Pacaraima", "uf": "RR", "cep": "69345-000"}
    return envios_cotizador._payload(envio, servicio, referencias, despacho,
                                     {"contenido": {}, "operacion": {}},
                                     {"peso_max_kg": 30, "largo_min_cm": 10})


def _por_el_contrato(respuesta):
    from fastapi.encoders import jsonable_encoder
    from models.acciones_del_cliente import MiCotizacionDeEncomienda
    return jsonable_encoder(MiCotizacionDeEncomienda.model_validate(respuesta).model_dump(exclude_unset=True))


def test_LA_COTIZACION_REAL_PASA_ENTERA_POR_EL_CONTRATO():
    """Nada de lo que la pantalla recibe hoy se pierde en el camino, tampoco lo
    anidado: el peso por transportista, las referencias, el retiro, los límites."""
    from fastapi.encoders import jsonable_encoder
    real = _cotizacion_real()
    assert _por_el_contrato(real) == jsonable_encoder(real)


def test_EL_MARGEN_Y_EL_DESGLOSE_NO_SALEN_AUNQUE_ALGUIEN_LOS_AGREGUE():
    real = _cotizacion_real()
    real["margen_ris"] = "20.00"
    real["desglose"] = {"servicio_ris": "80.00", "sobrecargos_ris": "20.00"}
    real["a_pagar_en_risapp"]["subtotal_ris"] = "100.00"
    real["a_pagar_en_risapp"]["margen_ris"] = "20.00"
    real["referencias"][0]["costo_interno"] = "30.00"
    real["retiro"]["telefono_del_operador"] = "+55 95 0000-0000"
    real["limites"]["limite_secreto"] = "1"
    salida = str(_por_el_contrato(real))
    for de_mas in ("margen_ris", "desglose", "subtotal_ris", "costo_interno",
                   "telefono_del_operador", "limite_secreto"):
        assert de_mas not in salida, f"la cotización dejó salir «{de_mas}»"
    assert "120.00" in salida, "el total sí tiene que salir"


def test_LOS_LIMITES_SALEN_DE_LA_MISMA_LISTA_QUE_LA_REGLA():
    """Una clave de límite nueva en la regla tiene que llegar a la pantalla sin
    que nadie se acuerde de agregarla al contrato."""
    from models.acciones_del_cliente import LimitesDeLaCotizacion
    from services.envios_policy import _MAXIMOS, _MINIMOS
    assert set(LimitesDeLaCotizacion.model_fields) == set(_MAXIMOS) | set(_MINIMOS)
