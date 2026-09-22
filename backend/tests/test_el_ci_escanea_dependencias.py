"""
tests/test_el_ci_escanea_dependencias.py — CI escanea las dependencias del
backend y del frontend en cada pull request, y lo hace sin agregar trabajos.

POR QUE HAY UN TEST PARA UN ARCHIVO DE CI

    El escaneo no frena nada (arranca en modo aviso, a propósito: hay
    advertencias conocidas anotadas en el dossier). Un paso que no frena es
    un paso que alguien puede borrar «para acelerar CI» sin que nada se
    queje. Este test es lo que se queja.
"""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")

_FLUJO = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows" / "lint.yml"


def flujo():
    return yaml.safe_load(_FLUJO.read_text(encoding="utf-8"))


def pasos(trabajo):
    return flujo()["jobs"][trabajo]["steps"]


def paso_que_corre(trabajo, texto):
    return next((p for p in pasos(trabajo) if texto in str(p.get("run", ""))), None)


def test_EL_BACKEND_SE_ESCANEA_CON_PIP_AUDIT_SOBRE_LO_QUE_SE_DESPLIEGA():
    p = paso_que_corre("tests", "pip-audit -r requirements.txt")
    assert p is not None, "falta el paso de pip-audit en el trabajo de la suite"
    assert "--no-deps" in p["run"], "sin --no-deps audita una resolución nueva, no la que se despliega"
    assert p.get("working-directory") == "backend"


def test_EL_FRONTEND_SE_ESCANEA_CON_NPM_AUDIT_SIN_LAS_HERRAMIENTAS_DE_DESARROLLO():
    p = paso_que_corre("frontend", "npm audit")
    assert p is not None, "falta el paso de npm audit en el trabajo del frontend"
    assert "--omit=dev" in p["run"] and "--audit-level=high" in p["run"]


@pytest.mark.parametrize("trabajo,texto", [("tests", "pip-audit"), ("frontend", "npm audit")])
def test_los_escaneos_avisan_sin_frenar_por_ahora(trabajo, texto):
    """Decisión escrita en el flujo: hay advertencias conocidas (dossier,
    sección 11) y bloquear hoy congelaría las fusiones por lo que ya se sabe.
    Cuando la lista quede limpia, este test cambia junto con el flujo."""
    p = paso_que_corre(trabajo, texto)
    assert p.get("continue-on-error") is True
    assert p["name"].startswith("[INFO]")


def test_NO_SE_AGREGO_NINGUN_TRABAJO_DE_CI():
    """Cada trabajo habla con GitHub, y la cuenta del proyecto ya llegó al
    tope de peticiones por hora. Los escaneos van en los trabajos que ya
    existen."""
    assert set(flujo()["jobs"]) == {"lint", "tests", "frontend"}
