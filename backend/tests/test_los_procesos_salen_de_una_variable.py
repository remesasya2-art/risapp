"""
tests/test_los_procesos_salen_de_una_variable.py — la cantidad de procesos
del servidor se configura con `WEB_WORKERS` en Railway, sin editar código.

POR QUE

    Railway le da prioridad a `railway.toml` sobre lo que se escriba en su
    panel. Con `--workers 2` escrito acá, subir o bajar la cantidad de
    procesos era un commit. Configurar nunca puede requerir editar código en
    GitHub: es regla de la casa.
"""
import pathlib
import re
import subprocess

_RAIZ = pathlib.Path(__file__).resolve().parents[2]
_ESPERADO = "--workers ${WEB_WORKERS:-1}"


def _comando_de(texto, clave):
    m = re.search(clave + r'\s*=\s*"([^"]+)"', texto)
    assert m, f"no se encontró {clave}"
    return m.group(1)


def comandos():
    return (_comando_de((_RAIZ / "railway.toml").read_text(encoding="utf-8"), "startCommand"),
            _comando_de((_RAIZ / "nixpacks.toml").read_text(encoding="utf-8"), "cmd"))


def test_LOS_DOS_COMANDOS_DE_ARRANQUE_LEEN_WEB_WORKERS_Y_SON_EL_MISMO():
    railway, nixpacks = comandos()
    assert _ESPERADO in railway and _ESPERADO in nixpacks
    assert railway == nixpacks, "railway.toml y nixpacks.toml tienen que arrancar igual"
    assert "--workers" not in railway.replace(_ESPERADO, ""), "un --workers fijo vuelve a exigir un commit para cambiarlo"


def test_SIN_LA_VARIABLE_ES_UN_PROCESO_Y_CON_ELLA_LOS_QUE_DIGA():
    """El comando lo interpreta el shell de Railway: se comprueba con un
    shell de verdad, no leyendo el texto."""
    railway, _ = comandos()
    pedazo = railway.split("--workers", 1)[1].strip()
    sin = subprocess.run(["sh", "-c", f"echo {pedazo}"], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    con = subprocess.run(["sh", "-c", f"echo {pedazo}"], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "WEB_WORKERS": "2"})
    assert sin.stdout.strip() == "1" and con.stdout.strip() == "2"
