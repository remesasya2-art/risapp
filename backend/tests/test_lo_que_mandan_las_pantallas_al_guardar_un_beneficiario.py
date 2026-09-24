"""
tests/test_lo_que_mandan_las_pantallas_al_guardar_un_beneficiario.py — Cada
pantalla que guarda un beneficiario manda los campos con el nombre que el
servidor espera.

QUE PASO

    La pantalla de Bitcoin mandaba `cedula` y `phone`. El servidor pide
    `id_document` y `phone_number`: contestaba que faltaba la cédula y no
    guardaba nada. Nunca. Y no había forma de verlo desde un solo lado: el
    servidor tenía sus tests, la pantalla estaba bien escrita, y cada uno le
    decía a la misma cosa con un nombre distinto.

COMO SE PRUEBA

    Se lee el código de las pantallas, se sacan las claves del objeto que
    mandan a `POST /beneficiaries`, y se comparan con el modelo del pedido
    (`BeneficiaryCreate`): tienen que estar las obligatorias y no puede haber
    ninguna que el servidor no conozca —una clave desconocida se ignora en
    silencio, y el dato se pierde—.
"""
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_PANTALLAS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages"

# (pantalla, cómo se llama la variable que se manda)
QUIEN_GUARDA = [
    ("Send.jsx", "datos"),
    ("BTCLightning.jsx", "payload"),
]


def _cierre(texto, abre):
    """La posición de la llave que cierra la que abre en `abre`."""
    nivel = 0
    for i in range(abre, len(texto)):
        if texto[i] == "{":
            nivel += 1
        elif texto[i] == "}":
            nivel -= 1
            if nivel == 0:
                return i
    raise AssertionError("llaves sin cerrar")    # pragma: no cover


def _partes(cuerpo):
    """Separa por comas de primer nivel."""
    partes, nivel, actual = [], 0, ""
    for c in cuerpo:
        if c in "{([":
            nivel += 1
        elif c in "})]":
            nivel -= 1
        if c == "," and nivel == 0:
            partes.append(actual)
            actual = ""
        else:
            actual += c
    return [p.strip() for p in partes + [actual] if p.strip()]


def _claves(cuerpo):
    """Las claves de un objeto de JavaScript, incluidas las abreviadas
    (`{ bank }`) y las de un `...(cond ? { a } : { b })` —se juntan las de
    las dos ramas—."""
    claves = set()
    for parte in _partes(cuerpo):
        if parte.startswith("..."):
            i = 0
            while (i := parte.find("{", i)) != -1:
                fin = _cierre(parte, i)
                claves |= _claves(parte[i + 1:fin])
                i = fin + 1
        else:
            claves.add(parte.split(":")[0].strip())
    return claves


def _lo_que_manda(pantalla, variable):
    texto = (_PANTALLAS / pantalla).read_text(encoding="utf-8")
    objetos = [m.end() - 1 for m in re.finditer(rf"\b{variable}\s*=\s*{{", texto)]
    assert objetos, f"no encontré `{variable} = {{` en {pantalla}"
    return [_claves(texto[a + 1:_cierre(texto, a)]) for a in objetos]


@pytest.mark.parametrize("pantalla,variable", QUIEN_GUARDA)
def test_CADA_PANTALLA_MANDA_LOS_CAMPOS_CON_EL_NOMBRE_QUE_EL_SERVIDOR_ESPERA(pantalla, variable):
    from models.requests import BeneficiaryCreate
    conocidos = set(BeneficiaryCreate.model_fields)
    obligatorios = {c for c, f in BeneficiaryCreate.model_fields.items() if f.is_required()}
    for claves in _lo_que_manda(pantalla, variable):
        assert obligatorios <= claves, f"{pantalla} no manda {sorted(obligatorios - claves)}: el servidor no guarda nada"
        assert claves <= conocidos, f"{pantalla} manda {sorted(claves - conocidos)}, que el servidor no conoce: se pierde"


def test_NO_HAY_OTRA_PANTALLA_QUE_GUARDE_BENEFICIARIOS_SIN_ESTE_CONTROL():
    """Si una pantalla nueva empieza a guardar beneficiarios, tiene que entrar
    en la lista de arriba: si no, este control no la mira."""
    quienes = {p.name for p in _PANTALLAS.rglob("*.jsx")
               if re.search(r"api\.post\(\s*['\"]/beneficiaries['\"]", p.read_text(encoding="utf-8"))}
    assert quienes == {p for p, _ in QUIEN_GUARDA}
