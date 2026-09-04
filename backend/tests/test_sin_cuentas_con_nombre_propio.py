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

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

# Se revisa el código FUENTE. `dist/` es la salida compilada: si el fuente
# está limpio, sale limpia sola, y revisarla haría fallar el test por un
# bundle viejo que nadie regeneró.
CARPETAS = ["backend", "frontend/src"]
EXTENSIONES = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yml", ".yaml"}
SALTEAR = {"node_modules", ".git", "__pycache__", "dist", "build", ".venv", "venv"}

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

# Direcciones que están en el código A PROPOSITO porque se publican: el
# contacto de la empresa en el pie de página y en la página legal. Publicar el
# correo de contacto es lo correcto —una plataforma que maneja plata ajena
# tiene que decir cómo se la contacta— y es lo contrario de proteger una
# cuenta por su nombre.
#
# La lista es explícita para que agregar una sea una decisión visible en la
# revisión, y no algo que entra sin que nadie lo mire.
PUBLICADOS_A_PROPOSITO = {
    "saipha.servicios.digitais@gmail.com",   # contacto de SAIPHA SERVICIOS DIGITAIS
}


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
