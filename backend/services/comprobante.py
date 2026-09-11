"""
services/comprobante.py — El comprobante que va en el correo, con forma de pasaje.

QUE ES Y POR QUE ASI

    Un correo que dice «tu retiro fue procesado» y nada más obliga a entrar a
    la aplicación para saber cuánto, cuándo y con qué referencia. Lo que la
    persona necesita cuando reclama —en un banco, en un mostrador, o con
    nosotros— es un comprobante: el número, el monto y la fecha, juntos.

    Tiene forma de pasaje de avión porque es la forma que todo el mundo ya sabe
    leer: de dónde sale, a dónde va, cuándo, y un talón con el número que hay
    que guardar. Nadie necesita que le expliquen un boarding pass.

EL DORADO ES EL DE LA APLICACION

    `#F5A623`, `#D4920A` y `#B8860B`, los tres que declara
    `frontend/tailwind.config.js`. No se inventa un dorado parecido: un correo
    que se parece pero no es igual se lee como de otra empresa, que es justo lo
    que hace dudar de si el correo es de verdad.

HTML DE CORREO, QUE NO ES HTML DE PANTALLA

    Los programas de correo tienen quince años de retraso. `flex` y `grid` no
    andan en Outlook, los estilos de una hoja aparte se descartan, y los
    bordes redondeados se pierden en algunos.

    Por eso esto está armado con TABLAS anidadas y con los estilos escritos en
    cada etiqueta. No es descuido: es lo único que se ve igual en todos lados.
    Y por eso el talón va al COSTADO con anchos fijos —420 + 180— y no con
    columnas que se reacomodan: reacomodarse es lo que ninguno hace igual.

LAS BARRAS DEL TALON SON DECORACION, Y EL NUMERO ESTA ESCRITO

    No es un código de barras que se pueda escanear, y por eso el número va
    escrito abajo, legible. Un código que parece escaneable y no lo es hace
    que alguien lo intente en un mostrador y se quede sin su comprobante.

QUE NO VA EN EL COMPROBANTE

    Ni el documento completo del beneficiario, ni el número de cuenta entero.
    Un correo se reenvía, se imprime y queda en una casilla que no siempre es
    la de quien opera. Van los últimos cuatro dígitos, que alcanzan para
    reconocer la operación y no para usarla.
"""
from datetime import datetime, timezone

# Los tres dorados de `frontend/tailwind.config.js`.
ORO = "#F5A623"
ORO_MEDIO = "#D4920A"
ORO_OSCURO = "#B8860B"

TINTA = "#111827"
GRIS = "#6b7280"
TENUE = "#9ca3af"
LINEA = "#e5e7eb"
FONDO = "#f4f4f5"
CREMA = "#fffbeb"


def ultimos4(valor) -> str:
    """Los últimos cuatro, para reconocer sin exponer."""
    texto = "".join(ch for ch in str(valor or "") if ch.isalnum())
    return f"••••{texto[-4:]}" if len(texto) > 4 else (texto or "")


def _fecha(cuando) -> str:
    if not isinstance(cuando, datetime):
        return ""
    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=timezone.utc)
    return cuando.strftime("%d %b %Y · %H:%M").upper()


def _barras(semilla: str) -> str:
    """La tira decorativa del talón, armada con celdas de tabla.

    Con celdas y no con un dibujo ni una imagen: un `<img>` lo bloquean casi
    todos los programas de correo hasta que la persona toca «mostrar
    imágenes», y entonces el talón llega vacío.
    """
    if not semilla:
        semilla = "RISAPP"
    celdas = []
    for i, ch in enumerate(semilla * 3):
        if len(celdas) >= 34:
            break
        ancho = 1 + (ord(ch) + i) % 3
        color = TINTA if (ord(ch) + i) % 3 else "transparent"
        celdas.append(f'<td width="{ancho * 2}" bgcolor="{color}" '
                      f'style="width:{ancho * 2}px;height:34px;font-size:0;">&nbsp;</td>'
                      f'<td width="2" style="width:2px;font-size:0;">&nbsp;</td>')
    return ("<table cellpadding=\"0\" cellspacing=\"0\" role=\"presentation\">"
            f"<tr>{''.join(celdas)}</tr></table>")


def _campo(etiqueta: str, valor: str, ancho: str = "") -> str:
    """Uno de los recuadritos en mayúsculas del pasaje (tipo PUERTA / ASIENTO)."""
    return f"""
              <td {ancho} valign="top" style="padding:0 14px 0 0;">
                <div style="color:{TENUE};font-size:9px;letter-spacing:1.4px;
                            text-transform:uppercase;font-family:Arial,sans-serif;">{etiqueta}</div>
                <div style="color:{TINTA};font-size:15px;font-weight:700;padding-top:3px;
                            font-family:Arial,sans-serif;">{valor}</div>
              </td>"""


def _fila(etiqueta: str, valor: str) -> str:
    return f"""
                <tr>
                  <td style="padding:6px 0;color:{GRIS};font-size:12px;">{etiqueta}</td>
                  <td align="right" style="padding:6px 0;color:{TINTA};font-size:12px;font-weight:700;">{valor}</td>
                </tr>"""


def armar(*, titulo: str, detalle: str = "", tipo: str = "COMPROBANTE",
          desde: str = "", desde_pie: str = "", hasta: str = "", hasta_pie: str = "",
          monto: str = "", campos=(), filas=(), referencia: str = "",
          cuando=None, estado: str = "", color_estado: str = ORO_OSCURO) -> str:
    """El pasaje entero.

    `campos` son los recuadritos en mayúsculas de arriba —lo que en un pasaje
    serían PUERTA y ASIENTO—; `filas` es el detalle fino de abajo. Lo que no
    aplica a un movimiento no se pasa: una fila que dice «—» ocupa lo mismo
    que una con información y no dice nada.
    """
    campos_html = "".join(_campo(e, v) for e, v in campos if v not in (None, "", "—"))
    filas_html = "".join(_fila(e, v) for e, v in filas if v not in (None, "", "—"))
    sello = f"""<span style="display:inline-block;padding:3px 11px;border-radius:999px;
                   background:{color_estado}1f;color:{color_estado};font-size:11px;
                   font-weight:700;letter-spacing:.5px;">{estado.upper()}</span>""" if estado else ""

    ruta = f"""
          <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
                 style="padding:4px 0 18px 0;">
            <tr>
              <td valign="middle" style="color:{TINTA};font-size:26px;font-weight:800;
                                         letter-spacing:1px;">{desde}</td>
              <td valign="middle" align="center" width="76" style="width:76px;color:{ORO_MEDIO};
                          font-size:17px;">&#9992;</td>
              <td valign="middle" align="right" style="color:{TINTA};font-size:26px;
                          font-weight:800;letter-spacing:1px;">{hasta}</td>
            </tr>
            <tr>
              <td style="color:{TENUE};font-size:11px;padding-top:2px;">{desde_pie}</td>
              <td></td>
              <td align="right" style="color:{TENUE};font-size:11px;padding-top:2px;">{hasta_pie}</td>
            </tr>
          </table>""" if desde or hasta else ""

    return f"""
<table width="100%" cellpadding="0" cellspacing="0" role="presentation"
       style="background:{FONDO};padding:26px 10px;font-family:Arial,Helvetica,sans-serif;">
  <tr>
    <td align="center">
      <table width="600" cellpadding="0" cellspacing="0" role="presentation"
             style="max-width:600px;width:100%;background:#ffffff;border-radius:14px;
                    overflow:hidden;border:1px solid {LINEA};">

        <!-- La banda dorada, como la cabecera de un pasaje -->
        <tr>
          <td colspan="2" style="background:{ORO};padding:14px 22px;">
            <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
              <tr>
                <td style="color:#3b2c05;font-size:16px;font-weight:800;letter-spacing:2px;">RIS APP</td>
                <td align="right" style="color:#4a3806;font-size:10px;font-weight:700;
                                         letter-spacing:2px;">{tipo.upper()}</td>
              </tr>
            </table>
          </td>
        </tr>

        <tr>
          <!-- ── El cuerpo del pasaje ──────────────────────────────── -->
          <td width="420" valign="top" style="width:420px;padding:20px 22px 18px 22px;">

            <div style="color:{TINTA};font-size:19px;font-weight:700;">{titulo}</div>
            {f'<div style="color:{GRIS};font-size:13px;padding-top:5px;line-height:1.5;">{detalle}</div>' if detalle else ''}
            {f'<div style="padding-top:10px;">{sello}</div>' if sello else ''}
            {ruta}

            {f'''<table width="100%" cellpadding="0" cellspacing="0" role="presentation"
                    style="border-top:1px solid {LINEA};padding-top:14px;">
              <tr>{campos_html}</tr>
            </table>''' if campos_html else ''}

            {f'''<table width="100%" cellpadding="0" cellspacing="0" role="presentation"
                    style="padding-top:14px;">{filas_html}
            </table>''' if filas_html else ''}
          </td>

          <!-- ── El talón, separado por la perforación ─────────────── -->
          <td width="180" valign="top"
              style="width:180px;background:{CREMA};border-left:2px dashed {ORO_MEDIO};
                     padding:20px 18px 18px 18px;">
            <div style="color:{ORO_OSCURO};font-size:9px;letter-spacing:1.6px;
                        text-transform:uppercase;font-weight:700;">Comprobante</div>
            <div style="color:{TINTA};font-size:15px;font-weight:800;padding-top:5px;
                        font-family:'Courier New',Courier,monospace;letter-spacing:1px;
                        word-break:break-all;">{referencia or '—'}</div>

            {f'''<div style="color:{TENUE};font-size:9px;letter-spacing:1.4px;
                        text-transform:uppercase;padding-top:16px;">Monto</div>
            <div style="color:{TINTA};font-size:17px;font-weight:800;padding-top:2px;">{monto}</div>''' if monto else ''}

            <div style="color:{TENUE};font-size:9px;letter-spacing:1.4px;
                        text-transform:uppercase;padding-top:16px;">Fecha</div>
            <div style="color:{TINTA};font-size:11px;font-weight:700;padding-top:2px;">{_fecha(cuando) or '—'}</div>

            <div style="padding-top:18px;">{_barras(referencia)}</div>
            <div style="color:{TENUE};font-size:9px;padding-top:6px;letter-spacing:1px;
                        font-family:'Courier New',Courier,monospace;">{referencia or ''}</div>
          </td>
        </tr>

        <!-- El pie -->
        <tr>
          <td colspan="2" style="background:#fafafa;border-top:1px solid {LINEA};padding:14px 22px;">
            <div style="color:{GRIS};font-size:11px;line-height:1.6;">
              Guardá el número del comprobante: es el que te vamos a pedir si hacés un
              reclamo. Este es un aviso automático de RIS App; no respondas a este correo.
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
"""
