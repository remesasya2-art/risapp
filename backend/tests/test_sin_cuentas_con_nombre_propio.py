"""
tests/test_sin_cuentas_con_nombre_propio.py — Ninguna cuenta protegida por su
nombre.

QUE PASABA

    La cuenta del super administrador estaba protegida en tres lugares
    comparando contra su DIRECCION DE CORREO, escrita en el código:

        frontend/src/pages/Profile.jsx:26
            return email === '<el correo del dueño>';

        backend/routes/admin.py:589   (cambiar el rol de un usuario)
        backend/routes/admin.py:631   (promover a agente de soporte)

    El del frontend era el grave. El frontend se compila y se sirve al
    navegador: ese correo viajaba —y se leía— en el bundle de CADA visitante
    del sitio. Le decía a cualquiera exactamente qué cuenta atacar para
    quedarse con la aplicación. Se comprobó que estaba en el JS publicado.

    Las tres se reemplazaron por el ROL, que significa lo mismo y además
    cubre a cualquier otro super administrador que exista mañana — con el
    correo a mano, ése quedaba desprotegido.

POR QUE UN TEST Y NO SOLO EL ARREGLO

    Escribir un correo concreto en un `if` es la forma más natural de
    resolver "protegé esta cuenta". Va a volver a pasar. Esto lo frena en
    CI, incluido en un archivo de test, que es de donde salieron seis de las
    nueve apariciones.
"""
import os
import pathlib
import re

import pytest

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

# Se revisa el código FUENTE. `dist/` es la salida compilada: si el fuente
# está limpio, sale limpia sola, y revisarla haría fallar el test por un
# bundle viejo que nadie regeneró.
CARPETAS = ["backend", "frontend/src"]
EXTENSIONES = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yml", ".yaml"}
SALTEAR = {"node_modules", ".git", "__pycache__", "dist", "build", ".venv", "venv"}

# Dominios que sólo aparecen como ejemplo en un formulario: dicen la FORMA del
# dato que se pide, no una dirección a la que escribirle. Los dos primeros son
# los reservados por la RFC 2606; los otros son los que ya usa esta aplicación
# en sus campos.
DOMINIOS_DE_EJEMPLO = ("@example.com", "@example.org",
                       "@ejemplo.com", "@dominio.com", "@empresa.com",
                       "@correo.com")

CORREO = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Dominios que SI pueden aparecer: los de la empresa —para textos, remitentes
# y datos de prueba— y los de ejemplo reservados por la RFC 2606.
PERMITIDOS = (
    "@risappbr.com", "@risapp.com",
    "@example.com", "@example.org", "@test.com",
    "@correo.com", "@b.com", "@d.com", "@x.x",
)

# Proveedores de correo personal. Una dirección de estos en el código es la
# cuenta real de una persona.
PERSONALES = ("@gmail.", "@hotmail.", "@outlook.", "@yahoo.", "@icloud.",
              "@live.", "@protonmail.", "@proton.me")

# Vacío, y así tiene que quedarse.
#
# Acá estuvo el contacto de la empresa mientras estaba escrito a mano en el pie
# de página y en cinco párrafos de la página legal. Ya no hay ninguno: el único
# canal de atención es el centro de ayuda de la aplicación, y no existe forma
# de publicar una dirección — no quedó ni una constante ni una variable de
# entorno que lo permita.
#
# Si alguien necesita agregar una entrada acá, la pregunta correcta es por qué
# la plataforma volvería a publicar una dirección de correo.
PUBLICADOS_A_PROPOSITO = set()


def _archivos():
    for carpeta in CARPETAS:
        base = _RAIZ / carpeta
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix not in EXTENSIONES:
                continue
            if any(parte in SALTEAR for parte in p.parts):
                continue
            yield p


def test_ninguna_direccion_de_correo_personal_en_el_codigo():
    """Una cuenta real escrita en un `if` es un blanco publicado.

    Peor en el frontend, que se le sirve entero a cualquiera que entre al
    sitio: ahí no hay 'está en el backend, no se ve'.
    """
    hallazgos = []
    for archivo in _archivos():
        try:
            texto = archivo.read_text(encoding="utf-8", errors="ignore")
        except Exception:                                # pragma: no cover
            continue
        for n, linea in enumerate(texto.splitlines(), 1):
            for correo in CORREO.findall(linea):
                bajo = correo.lower()
                if bajo in PUBLICADOS_A_PROPOSITO:
                    continue
                if any(bajo.endswith(d) for d in PERMITIDOS):
                    continue
                if any(p in bajo for p in PERSONALES):
                    hallazgos.append(
                        f"{archivo.relative_to(_RAIZ)}:{n}  {correo}")

    assert not hallazgos, (
        "Hay direcciones de correo personales escritas en el código:\n  "
        + "\n  ".join(hallazgos)
        + "\n\nProteger una cuenta por su nombre la PUBLICA, y en el frontend "
          "el bundle se le sirve a cada visitante del sitio. Usá el rol "
          "(`role == 'super_admin'`), que significa lo mismo y además cubre a "
          "cualquier otro super administrador que exista mañana.")


def test_ninguna_autorizacion_decide_por_correo():
    """Comparar un correo dentro de un `if` es la forma en que esto entra.

    Se busca el patrón, no una dirección: una cuenta protegida por su nombre
    es frágil aunque el nombre sea de la empresa. Si mañana esa persona
    cambia de correo, el guard deja de proteger a nadie y nada avisa.
    """
    sospechosas = re.compile(
        r"""(email|correo|mail)\s*(==|===|!=|!==)\s*['"][^'"]+@""",
        re.IGNORECASE)

    hallazgos = []
    for archivo in _archivos():
        if archivo.name.startswith("test_"):
            # En un test, comparar contra un correo fijo es lo normal: es el
            # dato que el test acaba de sembrar.
            continue
        try:
            texto = archivo.read_text(encoding="utf-8", errors="ignore")
        except Exception:                                # pragma: no cover
            continue
        for n, linea in enumerate(texto.splitlines(), 1):
            if sospechosas.search(linea):
                hallazgos.append(
                    f"{archivo.relative_to(_RAIZ)}:{n}  {linea.strip()[:100]}")

    assert not hallazgos, (
        "Hay decisiones tomadas comparando contra un correo escrito en el "
        "código:\n  " + "\n  ".join(hallazgos)
        + "\n\nDecidí por rol o por permiso, no por identidad.")


def test_ninguna_direccion_escrita_a_mano_en_el_frontend():
    """En el frontend no va NINGUNA dirección literal, sea del dominio o no.

    POR QUE ES MAS ESTRICTO QUE EL DE ARRIBA

        El de arriba busca casillas personales en todo el proyecto. Éste no
        mira de quién es la dirección: en el frontend no puede haber ninguna,
        ni siquiera una del dominio propio.

        El motivo es el medio, no el dueño. Este código se compila y se le
        sirve al navegador de cada visitante: cualquier dirección que se
        escriba acá queda publicada para siempre, y cambiarla exige un
        despliegue. La política vigente es que el único canal de atención es
        el centro de ayuda de la aplicación: no va ninguna.

    LO UNICO QUE SE PERMITE

        Los textos de ejemplo de los formularios: "tu@correo.com" en el campo
        de recuperar la contraseña no es un canal de contacto, es la forma del
        dato que se pide.

        Se los reconoce por el DOMINIO y no por la palabra `placeholder` en la
        línea. Buscar la palabra fallaba con los que se declaran aparte —en
        RecursosHumanos.jsx los campos son tuplas `[nombre, etiqueta,
        ejemplo]` y el `placeholder` se arma después—, y una exención que
        depende de cómo se escribió la línea deja pasar la que se escribió
        distinto.
    """
    frontend = _RAIZ / "frontend" / "src"
    if not frontend.exists():                            # pragma: no cover
        pytest.skip("no está el frontend en este árbol")

    hallazgos = []
    for archivo in frontend.rglob("*"):
        if not archivo.is_file() or archivo.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
            continue
        if any(parte in SALTEAR for parte in archivo.parts):
            continue
        for n, linea in enumerate(archivo.read_text(encoding="utf-8",
                                                    errors="ignore").splitlines(), 1):
            for correo in CORREO.findall(linea):
                if any(correo.lower().endswith(d) for d in DOMINIOS_DE_EJEMPLO):
                    continue
                hallazgos.append(f"{archivo.relative_to(_RAIZ)}:{n}  {correo}")

    assert not hallazgos, (
        "Hay direcciones de correo escritas a mano en el frontend:\n  "
        + "\n  ".join(hallazgos)
        + "\n\nEste código se le sirve al navegador de cada visitante: lo que "
          "se escriba acá queda publicado y sólo se cambia desplegando. El "
          "único canal de atención es el centro de ayuda: enlazá a /support.")
