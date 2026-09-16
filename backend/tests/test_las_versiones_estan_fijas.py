"""
tests/test_las_versiones_estan_fijas.py — Que un despliegue no dependa de la
suerte.

EL DESPLIEGUE QUE SE CAYO SIN QUE NADIE TOCARA NADA

    Railway murió compilando el frontend, así:

        npm error 404 Not Found - GET .../@types/node/-/node-26.6.0.tgz

    No había cambiado nada de este lado. Lo que pasó es que el repositorio NO
    TENIA candado de versiones, así que cada instalación volvía a resolver
    contra lo último que hubiera publicado npm ese minuto. Y una dependencia
    lejana pedía `"@types/node": "*"` — literalmente «la más nueva que haya».

    La cadena, seguida hasta el final:

        expo → react-native → metro → jest-worker → jest-util → @jest/types
                                                                └─ "*"

    `expo` estaba declarado como dependencia y NO SE IMPORTABA EN NINGUN LADO.
    Sacarlo bajó la instalación de 408 paquetes a 165, se llevó `@types/node`
    entero, y dejó CERO dependencias con la versión suelta.

POR QUE HACE FALTA UN TEST Y NO ALCANZA CON HABERLO ARREGLADO

    El candado sólo sirve si TODOS lo respetan, y es muy fácil deshacerlo sin
    darse cuenta:

        `npm install` en vez de `npm ci` vuelve a resolver y REESCRIBE el
        candado en silencio. El despliegue sigue andando —hasta el día que no—,
        y nadie relaciona la caída con el cambio de una palabra hecho meses
        antes.

        Agregar una dependencia al `package.json` y no regenerar el candado
        deja los dos peleados. `npm ci` falla, pero recién en CI y con un
        mensaje que no dice qué hacer.

    Por eso este archivo mira las dos cosas: que el candado esté, y que quien
    instala lo use.
"""
import json
import os
import pathlib
import re

import pytest

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

PAQUETE = _RAIZ / "frontend" / "package.json"
CANDADO = _RAIZ / "frontend" / "package-lock.json"
NIXPACKS = _RAIZ / "nixpacks.toml"
CI = _RAIZ / ".github" / "workflows" / "lint.yml"

# Los lugares que instalan el frontend de verdad: el despliegue y CI. Si uno de
# los dos usa `npm install`, el candado deja de mandar donde más importa.
QUIENES_INSTALAN = (
    ("nixpacks.toml", NIXPACKS),
    (".github/workflows/lint.yml", CI),
)


def test_el_candado_de_versiones_esta_en_el_repositorio():
    """Sin él, cada despliegue resuelve contra lo que npm tenga ese minuto."""
    assert CANDADO.exists(), (
        "desapareció frontend/package-lock.json. Sin candado, dos despliegues "
        "del mismo commit pueden instalar versiones distintas, y una caída del "
        "registro de npm tumba el despliegue sin que nadie haya tocado nada.")


def test_el_candado_y_el_package_json_dicen_lo_mismo():
    """Peleados, `npm ci` falla — pero recién en CI, y sin decir qué hacer.

    Pasa al agregar una dependencia a mano y no regenerar el candado.
    """
    paquete = json.loads(PAQUETE.read_text(encoding="utf-8"))
    candado = json.loads(CANDADO.read_text(encoding="utf-8"))
    raiz = (candado.get("packages") or {}).get("", {})

    for cual in ("dependencies", "devDependencies"):
        assert (paquete.get(cual) or {}) == (raiz.get(cual) or {}), (
            f"`{cual}` del package.json no coincide con el candado. "
            "Corré `npm install` en frontend/ y sumá el package-lock.json al "
            "mismo commit.")


@pytest.mark.parametrize("nombre,archivo", QUIENES_INSTALAN)
def test_quien_instala_el_frontend_respeta_el_candado(nombre, archivo):
    """`npm install` reescribe el candado en silencio; `npm ci` lo obedece."""
    texto = archivo.read_text(encoding="utf-8")
    # Sólo las líneas que EJECUTAN, no los comentarios: este repositorio
    # explica en los comentarios de qué se salió, y nombrar `npm install` para
    # contar la historia no es volver a usarlo.
    ejecuta = [l for l in texto.splitlines()
               if "npm " in l and not l.lstrip().startswith("#")]
    # Sin pedir que la línea diga «frontend». La primera versión lo pedía, y
    # por eso no veía la de CI: ahí el directorio va en `working-directory:`,
    # en OTRA línea. CI podía volver a `npm install` y los seis tests seguían
    # en verde. Lo agarró la mutación.
    #
    # Estos dos archivos no instalan ninguna otra cosa con npm, así que
    # cualquier `npm install` que aparezca acá es éste.
    culpables = [l.strip() for l in ejecuta
                 if re.search(r"\bnpm (install|i)\b", l)]
    assert not culpables, (
        f"{nombre} instala el frontend con `npm install`, que vuelve a "
        "resolver las versiones y reescribe el candado. Tiene que ser "
        f"`npm ci`.\n  " + "\n  ".join(culpables))


def test_no_vuelve_la_bandera_que_tapaba_el_conflicto():
    """`--legacy-peer-deps` existía por `expo`. Sin `expo` no hace falta.

    Si reaparece es que volvió un conflicto de pares, y taparlo con la bandera
    es justo lo que dejó el problema escondido la vez pasada.
    """
    for nombre, archivo in QUIENES_INSTALAN:
        ejecuta = [l for l in archivo.read_text(encoding="utf-8").splitlines()
                   if "npm " in l and not l.lstrip().startswith("#")]
        conbandera = [l.strip() for l in ejecuta if "--legacy-peer-deps" in l]
        assert not conbandera, (
            f"{nombre} volvió a usar `--legacy-peer-deps`:\n  "
            + "\n  ".join(conbandera))


def test_no_vuelve_expo_como_dependencia():
    """No se importa en ningún lado y arrastra media biblioteca.

    El script `npm run expo` se conserva —lo puede estar llamando el hospedaje—
    y sigue andando: corre `expo-shim.cjs`, que sólo lanza Vite.
    """
    paquete = json.loads(PAQUETE.read_text(encoding="utf-8"))
    for cual in ("dependencies", "devDependencies"):
        assert "expo" not in (paquete.get(cual) or {}), (
            f"volvió `expo` a {cual}. No se importa en ningún archivo del "
            "frontend, y arrastra react-native y metro, que son los que piden "
            "versiones sueltas.")
