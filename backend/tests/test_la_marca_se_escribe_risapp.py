"""La marca se escribe «RISApp»: todo junto, RIS en mayúsculas y App con A.

El repositorio la tenía escrita de siete maneras —«RIS App», «RisApp», «RIS
APP», «RISAPP»…— y el cliente veía una en el correo, otra en el título de la
pestaña y otra en el marco legal. El dueño pidió unificarla.

Lo que NO se busca acá son los nombres internos que nadie ve y que romperían
algo si cambiaran: la base de datos (`ris_app`), el caché del navegador
(`ris-app-v2`), los dominios y las variables de entorno (`RISAPP_...`).
"""
import re
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[2]

# Donde vive lo que el cliente o el equipo ven: pantallas, correos, avisos,
# PDF, planillas, políticas y el manifiesto de la app instalada.
_DONDE = [
    _RAIZ / "frontend" / "src",
    _RAIZ / "frontend" / "public",
    _RAIZ / "frontend" / "index.html",
    _RAIZ / "backend",
]
_EXTENSIONES = {".py", ".js", ".jsx", ".json", ".html", ".md"}

# Las grafías viejas. «RISAPP» sólo cuenta suelta: pegada a otra cosa
# (`RISAPP_TEST_BASE_URL`) es el nombre de una variable, no la marca.
_VIEJAS = re.compile(r"RIS App|RIS APP|RisApp|(?<![A-Z_])RISAPP(?![A-Z_])")


def _archivos():
    for lugar in _DONDE:
        candidatos = [lugar] if lugar.is_file() else lugar.rglob("*")
        for f in candidatos:
            if (f.is_file() and f.suffix in _EXTENSIONES
                    and "node_modules" not in f.parts and f.name != Path(__file__).name):
                yield f


def test_LO_QUE_SE_VE_DICE_RISAPP():
    malos = []
    for f in _archivos():
        for n, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            # La cita del titular falso que alguna vez se inventó: se nombra
            # para que nadie lo vuelva a escribir.
            if "«RISAPP C.A.»" in linea:
                continue
            if _VIEJAS.search(linea):
                malos.append(f"{f.relative_to(_RAIZ)}:{n}: {linea.strip()[:90]}")
    assert not malos, "La marca se escribe «RISApp»:\n  " + "\n  ".join(malos)


def test_LA_APP_INSTALADA_SE_LLAMA_RISAPP():
    """El nombre que queda debajo del ícono en el teléfono."""
    manifiesto = (_RAIZ / "frontend" / "public" / "manifest.json").read_text(encoding="utf-8")
    assert '"name": "RISApp"' in manifiesto and '"short_name": "RISApp"' in manifiesto
    indice = (_RAIZ / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'content="RISApp"' in indice


def test_EL_QR_DEL_COMPROBANTE_EMPIEZA_CON_LA_MARCA():
    fuente = (_RAIZ / "backend" / "services" / "comprobante.py").read_text(encoding="utf-8")
    assert '"RISApp", referencia' in fuente
