"""
tests/test_el_ci_prueba_con_mongo_de_verdad.py — CI corre contra un Mongo con
réplicas cada archivo de tests que sabe hacerlo.

POR QUE HAY UN TEST PARA UN ARCHIVO DE CI

    Un archivo de tests que usa `tests/_mongo_de_verdad.py` y no está en el
    paso de CI corre sólo sobre mongomock, sin transacciones, y da verde sin
    haber probado lo que vino a probar. Nada se queja: por eso este test.
"""
import pathlib
import re

import pytest

yaml = pytest.importorskip("yaml")

_RAIZ = pathlib.Path(__file__).resolve().parents[2]
_FLUJO = _RAIZ / ".github" / "workflows" / "lint.yml"


def _paso():
    pasos = yaml.safe_load(_FLUJO.read_text(encoding="utf-8"))["jobs"]["tests"]["steps"]
    return next((p for p in pasos if "RIS_MONGO_DE_VERDAD" in str(p.get("env", ""))), None)


def _los_que_saben():
    # La línea del import, al principio de la línea: este mismo archivo tiene
    # el texto adentro de una cadena y no es uno de los que saben.
    return sorted(p.name for p in (_RAIZ / "backend" / "tests").glob("test_*.py")
                  if re.search(r"^from _mongo_de_verdad import", p.read_text(encoding="utf-8"), re.M))


def test_EL_PASO_LEVANTA_UN_MONGO_CON_REPLICAS_Y_FRENA():
    p = _paso()
    assert p is not None, "falta el paso que corre los tests contra un Mongo con réplicas"
    assert "replicaSet=rs0" in p["env"]["RIS_MONGO_DE_VERDAD"]
    assert "--replSet rs0" in p["run"] and "rs.initiate" in p["run"], "sin réplicas no hay transacciones"
    assert not p.get("continue-on-error"), "tiene que frenar: es el único lugar donde se prueban las transacciones"


def test_CADA_ARCHIVO_QUE_SABE_CORRER_CONTRA_MONGO_CORRE_AHI():
    saben = _los_que_saben()
    assert "test_motor_contable.py" in saben, saben
    faltan = [n for n in saben if f"tests/{n}" not in _paso()["run"]]
    assert not faltan, f"estos archivos saben correr contra un Mongo de verdad y CI no los corre ahí: {faltan}"
