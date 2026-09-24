"""El historial usa el color sólo donde significa algo.

La lista llevaba cuatro manchas de color por fila —la flecha, el monto, la
pastilla del estado y la del comprobante—, y cada envío salía en rojo. El
dueño la describió como «un arbolito de navidad». El problema no era sólo de
gusto: con todo en color, el pedido vencido no se distinguía del aprobado.

Estos tests leen el código de las filas, como los demás tests del frontend de
este repositorio, y vigilan las cuatro decisiones que lo arreglaron.
"""
import re
from pathlib import Path

_DASH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "dashboard"
_FILA = _DASH / "TransactionItem.jsx"
_CRIPTO = _DASH / "CryptoHistoryItem.jsx"


def _texto(p):
    return p.read_text(encoding="utf-8")


def _conjunto(texto):
    m = re.search(r"const TERMINADOS_BIEN = new Set\(\[([^\]]*)\]\)", texto)
    assert m, "no encuentro TERMINADOS_BIEN"
    return set(re.findall(r"'(\w+)'", m.group(1)))


def test_MANDAR_PLATA_NO_SE_PINTA_DE_ROJO():
    texto = _texto(_FILA)
    linea = next(l for l in texto.splitlines() if "const amountColor" in l)
    lo_que_sale = linea.split("?", 1)[1].split(":", 1)[0]
    assert "texto" in lo_que_sale and "error" not in lo_que_sale and "#E53E3E" not in lo_que_sale, (
        "el monto de un envío vuelve a tener color: el rojo se lee como un error")


def test_LA_FLECHA_NO_LLEVA_COLOR():
    texto = _texto(_FILA)
    for nombre in ("iconBg", "iconColor"):
        linea = next(l for l in texto.splitlines() if f"const {nombre} =" in l)
        assert "isWithdrawal" not in linea, (
            f"{nombre} vuelve a cambiar de color según el sentido: la flecha ya lo dice")


def test_LA_FILA_DEL_HISTORIAL_NO_USA_LA_PASTILLA():
    """La pastilla sigue existiendo para el panel de administración."""
    texto = _texto(_FILA)
    cuerpo = texto[texto.index("export default function TransactionItem"):]
    assert "<StatusBadge" not in cuerpo
    assert "<EstadoEnTexto status={txStatus} />" in cuerpo
    assert "export function StatusBadge" in texto, "el panel la importa"


def test_LO_QUE_SALIO_BIEN_VA_EN_GRIS_Y_LO_DEMAS_EN_COLOR():
    texto = _texto(_FILA)
    estado = texto[texto.index("function EstadoEnTexto"):texto.index("const ENLACE_DE_FILA")]
    assert "color: bien ? 'var(--en-oscuro-texto-2" in estado and ": cfg.fg," in estado
    compacta = next(l for l in texto.splitlines() if "{statusCfg.label}</span>" in l)
    assert "TERMINADOS_BIEN.has(txStatus) ? 'var(--en-oscuro-texto-2" in compacta, (
        "la lista del inicio volvió a pintar de verde cada aprobado")


def test_CADA_ESTADO_VERDE_ESTA_ENTRE_LOS_TERMINADOS_BIEN():
    """Un estado verde que falte en el conjunto sale en texto verde entero, y
    uno que sobre esconde en gris algo que pedía atención."""
    for archivo, campo in ((_FILA, "fg"), (_CRIPTO, "color")):
        texto = _texto(archivo)
        verdes = set(re.findall(
            r"^\s*(\w+):\s*\{[^\n]*\b" + campo + r": 'var\(--en-oscuro-exito,", texto, re.M))
        assert verdes, archivo.name
        assert verdes == _conjunto(texto), (archivo.name, verdes ^ _conjunto(texto))


def test_LAS_ACCIONES_SON_ENLACES_Y_NO_PASTILLAS():
    texto = _texto(_FILA)
    cuerpo = texto[texto.index("{/* Abajo: el estado"):]
    for testid in ("retomar-", "view-voucher-"):
        i = cuerpo.index(f"data-testid={{`{testid}")
        trozo = cuerpo[i:i + 120]
        assert "style={ENLACE_DE_FILA}" in trozo, testid
    enlace = texto[texto.index("const ENLACE_DE_FILA"):texto.index("function formatShort")]
    assert "background: 'none'" in enlace


def test_LA_FILA_CRIPTO_TAMPOCO_USA_PASTILLA():
    texto = _texto(_CRIPTO)
    assert "backgroundColor: statusInfo.bg" not in texto
    assert "TERMINADOS_BIEN.has(item.status) ? 'var(--en-oscuro-texto-2" in texto
