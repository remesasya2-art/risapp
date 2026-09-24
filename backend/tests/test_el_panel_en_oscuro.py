"""El panel de administración en modo oscuro.

Estos tests leen el código del frontend, como los demás de la apariencia. Cada
uno vigila un tropiezo que apareció al convertir el panel, no una idea de cómo
debería ser.
"""
import re
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _leer(*partes):
    return _SRC.joinpath(*partes).read_text(encoding="utf-8")


def test_EL_TEXTO_QUE_NO_DICE_SU_COLOR_ES_CLARO_EN_OSCURO():
    """Los títulos de Recursos Humanos, Auditoría y Errores no tienen color
    propio: heredaban el negro de la página y en oscuro no se veían."""
    css = _leer("index.css")
    assert ':root[data-tema="oscuro"] .con-tema { color: var(--en-oscuro-texto); }' in css
    # Sólo en oscuro: en claro lo heredado tiene que seguir siendo lo de
    # siempre, o cambia cada pantalla marcada.
    for m in re.finditer(r"([^{}]*)\{[^{}]*(?<![-\w])color:\s*var\(--en-oscuro-texto\)", css):
        assert 'data-tema="oscuro"' in m.group(1), m.group(1).strip()


def test_EL_PANEL_TIENE_EL_SOL_Y_LA_LUNA():
    panel = _leer("pages", "AdminPanel.jsx")
    assert "<SelectorDeApariencia cuadrado />" in panel
    selector = _leer("components", "tema", "SelectorDeApariencia.jsx")
    assert "export default function SelectorDeApariencia({ cuadrado = false })" in selector


# Componentes del panel que reciben un color como DATO (la barra de «Uso», las
# cifras de Seguridad financiera). Con `color=` se leían como íconos, y la
# herramienta que pasó los íconos a `style` les movió el dato a un estilo que
# nadie lee: la barra de «Uso» salió violeta en vez de celeste, en claro.
_CON_TONO = {
    ("components", "admin", "Uso.jsx"): "Barra",
    ("components", "admin", "SeguridadFinanciera.jsx"): "Cifra",
    ("components", "admin", "BtcAdminConfig.jsx"): "Stat",
    ("components", "admin", "CreditsAdminPanel.jsx"): "SummaryPill",
    ("components", "admin", "ComprobantesDelLote.jsx"): "ConMotivo",
}


def test_LOS_QUE_RECIBEN_UN_COLOR_COMO_DATO_LO_LLAMAN_TONO():
    for partes, nombre in _CON_TONO.items():
        texto = _leer(*partes)
        definicion = re.search(rf"function {nombre}\(\{{([^}}]*)\}}\)", texto)
        assert definicion and "tono: color" in definicion.group(1), (nombre, "definición")
        usos = 0
        for m in re.finditer(rf"<{nombre}\b", texto):
            etiqueta = texto[m.start():texto.index("/>", m.start())]
            assert "style={{ color" not in etiqueta and not re.search(r"\scolor=", etiqueta), (
                f"{nombre} recibe el color por un lugar que no lee:\n{etiqueta}")
            usos += "tono=" in etiqueta
        assert usos, f"ningún {nombre} recibe su tono"


def test_LA_TRANSPARENCIA_SE_ESCRIBE_CON_COLOR_MIX():
    """Sumarle dos cifras a una variable da un color inválido. Que nadie lo haga
    lo vigila `test_NADIE_LE_PEGA_TEXTO_A_UN_COLOR_DE_LA_PALETA`; esto vigila
    que la alternativa siga funcionando con variables."""
    fuente = _leer("tema", "conAlfa.js")
    assert "return `color-mix(in srgb, ${color} ${porcentaje}%, transparent)`;" in fuente
    usan = [f for f in (_SRC / "components" / "admin").rglob("*.jsx")
            if "conAlfa(" in f.read_text(encoding="utf-8")]
    assert len(usan) >= 5, usan
