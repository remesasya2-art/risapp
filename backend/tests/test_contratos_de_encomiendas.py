"""
tests/test_contratos_de_encomiendas.py — Lo que el panel ve de las encomiendas
sale por un contrato, y ningún contrato se come un campo que su servicio arma.
Ver models/panel_encomiendas.py.

DOS GUARDAS, Y HACEN FALTA LAS DOS

    La primera (acá) lee del código las claves que arma cada función —también
    las de las listas que el circuito de prueba deja vacías, como el historial o
    las observaciones de precios— y exige que estén en el contrato de su ruta.

    La segunda está al final del circuito de punta a punta
    (`test_envios_e2e.test_42_las_lecturas_del_panel_salen_enteras_por_su_contrato`):
    con los datos de verdad del recorrido, cada lectura del panel contesta lo
    mismo que su función llamada a mano. La lectura del código no ve lo que se
    arma con `{**otro}`; la comparación sí.
"""
import ast
import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ris_test")

_BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _rutas():
    from routes.envios_admin import router
    return [r for r in router.routes if hasattr(r, "methods")]


def test_CADA_RUTA_DEL_PANEL_DE_ENCOMIENDAS_TIENE_SU_CONTRATO():
    rutas = _rutas()
    assert len(rutas) >= 45, "el router cambió de forma: este test no está mirando lo que dice mirar"
    sin = [f"{sorted(r.methods)} {r.path}" for r in rutas
           if "/foto/" not in r.path and (r.response_model is None or not r.response_model_exclude_unset)]
    assert not sin, f"rutas del panel de encomiendas sin contrato: {sin}"


def test_LA_FOTO_SIGUE_SIN_CONTRATO_PORQUE_ES_UNA_IMAGEN():
    (foto,) = [r for r in _rutas() if "/foto/" in r.path]
    assert foto.response_model is None


def _campos(modelo, vistos=None):
    """Los campos de un modelo y de todos los que cuelgan de él."""
    from typing import get_args
    from pydantic import BaseModel
    vistos = vistos if vistos is not None else set()
    campos = set(modelo.model_fields)
    for campo in modelo.model_fields.values():
        pendientes = [campo.annotation]
        while pendientes:
            t = pendientes.pop()
            if isinstance(t, type) and issubclass(t, BaseModel) and t not in vistos:
                vistos.add(t)
                campos |= _campos(t, vistos)
            pendientes.extend(get_args(t))
    return campos


def _claves_devueltas(archivo, funcion):
    """Las claves de cada `return {...}` de la función, sin las `**otro`."""
    arbol = ast.parse((_BACKEND / archivo).read_text("utf-8"))
    (f,) = [n for n in ast.walk(arbol)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == funcion]
    claves = set()
    for n in ast.walk(f):
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict):
            claves |= {k.value for k in n.value.keys if isinstance(k, ast.Constant)}
    return claves


# (archivo, función que arma, contrato que la recibe)
QUIEN_ARMA_QUE = [
    ("services/envios_puesta_en_marcha.py", "estado", "EstadoDelModulo"),
    ("services/envios_puesta_en_marcha.py", "_paso", "PasoDeLaPuestaEnMarcha"),
    ("services/envios_operacion.py", "cola", "ColaDeEnvios"),
    ("services/envios_operacion.py", "_fila_de_cola", "EnvioEnLaCola"),
    ("services/envios_operacion.py", "ticket", "TicketDelEnvio"),
    ("services/envios_operacion.py", "marcar_disponible", "AccionSobreUnEnvio"),
    ("services/envios_operacion.py", "retirar_lote", "LoteRetirado"),
    ("services/envios_operacion.py", "despachar", "AccionSobreUnEnvio"),
    ("services/envios_operacion.py", "entregar", "AccionSobreUnEnvio"),
    ("services/envios_operacion.py", "desviar", "AccionSobreUnEnvio"),
    ("services/envios_operacion.py", "cargar_flete", "AccionSobreUnEnvio"),
    ("services/envios_operacion.py", "acreditar_flete", "AccionSobreUnEnvio"),
    ("services/envios_comprobante.py", "verificar", "AccionSobreUnEnvio"),
    ("services/envios_comprobante.py", "_cobro_de", "CobroDelEnvio"),
    ("services/envios_entrega_final.py", "registrar", "AccionSobreUnEnvio"),
    ("services/envios_entrega_final.py", "historial", "HistorialDeEnvios"),
    ("services/envios_entrega_final.py", "_fila", "EnvioDelHistorial"),
    ("services/envios_rentabilidad.py", "por_lote", "Viaje"),
    ("services/envios_rentabilidad.py", "_resumen", "Observacion"),
    ("services/envios_retiro.py", "bloque_de_despacho", "VistaPreviaDelRetiro"),
]


@pytest.mark.parametrize("archivo,funcion,modelo", QUIEN_ARMA_QUE, ids=[f for _, f, _ in QUIEN_ARMA_QUE])
def test_LO_QUE_ARMA_CADA_SERVICIO_ESTA_EN_SU_CONTRATO(archivo, funcion, modelo):
    from models import panel_encomiendas
    claves = _claves_devueltas(archivo, funcion)
    assert claves, f"no encontré qué devuelve {funcion}: sin claves este test no prueba nada"
    faltan = claves - _campos(getattr(panel_encomiendas, modelo))
    assert not faltan, f"{funcion} arma {sorted(faltan)} y el contrato {modelo} no los tiene"


def test_LO_QUE_ARMA_REPESAR_ESTA_EN_SU_CONTRATO():
    """`repesar` no devuelve un diccionario escrito en el `return`: arma
    `resultado = {...}` y le agrega el cobro o la devolución según la rama.
    Se leen las dos cosas."""
    from models.panel_encomiendas import AccionSobreUnEnvio
    arbol = ast.parse((_BACKEND / "services/envios_operacion.py").read_text("utf-8"))
    (f,) = [n for n in ast.walk(arbol) if isinstance(n, ast.AsyncFunctionDef) and n.name == "repesar"]
    claves = set()
    for n in ast.walk(f):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "resultado" and isinstance(n.value, ast.Dict):
            claves |= {k.value for k in n.value.keys if isinstance(k, ast.Constant)}
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Subscript) \
                and getattr(n.targets[0].value, "id", "") == "resultado":
            claves.add(n.targets[0].slice.value)
    assert {"rama", "cobro", "devolucion"} <= claves, f"la lectura no encontró lo que arma repesar: {claves}"
    faltan = claves - _campos(AccionSobreUnEnvio)
    assert not faltan, f"repesar arma {sorted(faltan)} y el contrato no los tiene"


def test_LO_QUE_ARMAN_LAS_RUTAS_ESTA_EN_SU_CONTRATO():
    """Las rutas que arman su respuesta ahí mismo, con un diccionario a la vista."""
    arbol = ast.parse((_BACKEND / "routes/envios_admin.py").read_text("utf-8"))
    por_funcion = {r.endpoint.__name__: r for r in _rutas()}
    revisadas, faltan = 0, []
    for f in arbol.body:
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) or f.name not in por_funcion:
            continue
        ruta = por_funcion[f.name]
        if ruta.response_model is None or not hasattr(ruta.response_model, "model_fields"):
            continue
        claves = _claves_devueltas("routes/envios_admin.py", f.name)
        if not claves:
            continue
        revisadas += 1
        sobra = claves - _campos(ruta.response_model)
        if sobra:
            faltan.append(f"{ruta.path}: {sorted(sobra)}")
    assert revisadas >= 20, f"sólo se revisaron {revisadas} rutas: la lectura se rompió"
    assert not faltan, "estas rutas devuelven campos que su contrato no tiene:\n" + "\n".join(faltan)


def test_LA_NOMINA_NO_TRAE_LOS_DATOS_PERSONALES_DE_QUIEN_RETIRA():
    """La nómina se lista sin CPF ni teléfono (`_sin_datos_personales`). El
    contrato los tiene porque al crear o editar se devuelve lo que se acaba de
    escribir; lo que los saca de la lista es la función, y eso se comprueba."""
    from routes import envios_admin
    limpio = envios_admin._sin_datos_personales({"colaborador_id": "c1", "nombre": "Ana", "cpf": "111",
                                                 "telefono": "+55 11"})
    assert "cpf" not in limpio and "telefono" not in limpio and limpio["nombre"] == "Ana"
