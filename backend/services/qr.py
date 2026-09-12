"""
services/qr.py — Un código QR dibujado con celdas de tabla, para que se VEA en el correo.

POR QUE NO ES UNA IMAGEN

    Es la parte contraintuitiva. Un QR es una imagen, y la forma obvia sería
    mandarlo como imagen. No funciona:

        <img src="data:image/png;base64,...">   Gmail NO lo muestra. Ni en la
                                                web, ni en iOS, ni en Android.
                                                Outlook tampoco.
        <img src="https://...">                 Gmail sí, pero Outlook de
                                                escritorio arranca bloqueando
                                                las imágenes.

    En los dos casos, a una parte de la gente el comprobante le llega con un
    recuadro vacío donde tenía que estar su código. Y un comprobante al que le
    falta justo eso es peor que uno que nunca lo tuvo: parece roto.

    Dibujado con celdas de tabla se ve en los tres lados sin que nadie toque
    nada, porque no es una imagen: es la misma tabla con la que está armado el
    resto del correo.

LAS CUATRO COSAS QUE HAY QUE HACER BIEN, Y QUE SE DESCUBRIERON ROMPIENDOLAS

    1. FUSIONAR LOS TRAMOS CON `colspan`. Dibujar una celda por módulo es lo
       obvio y sale mal: cada fila termina con una cantidad distinta de celdas
       si se fusionan sólo con anchos, y el navegador arma las columnas
       contando celdas. La rejilla queda torcida y no se lee.

       Se fusionan los tramos del mismo color con `colspan`, y la PRIMERA fila
       es una hilera de celdas de alto cero que fija las columnas de una vez.

    2. LA ZONA DE SILENCIO. Sin el marco blanco alrededor no lo lee NINGUN
       lector, por perfecta que esté la rejilla. Se hace con relleno y fondo
       blanco, que no cuesta ni un byte de tabla.

    3. MATAR EL ALTO DE LINEA. `font-size:0` y `line-height:0`, más
       `mso-line-height-rule:exactly` para Outlook. Sin eso, cada fila se
       estira al alto de una línea de texto y los módulos salen rectangulares.

    4. EL ANCHO FIJO. Si la columna puede encogerse, en una pantalla angosta
       el navegador le saca el ancho que le falta al resto y el código deja de
       leerse. Se le pone `width` en la etiqueta, no sólo en el estilo.

QUE SE PUEDE METER ADENTRO

    Poco. Con corrección M: 42 bytes entran en un código de 29x29, 62 en uno
    de 33x33, 84 en uno de 37x37. Cada salto de tamaño son cuatro módulos más
    de lado, y a mayor tamaño, menos aguanta que el correo se achique en un
    teléfono: el ancho del talón es fijo, así que más módulos son menos
    píxeles para cada uno.

    Por eso lo que va adentro se elige con cuidado y se mide. Ver
    `services/comprobante.py`.
"""
import logging

logger = logging.getLogger(__name__)

# Cuánto mide un módulo, medido y no elegido. Se fotografió el comprobante
# ENTERO con Chromium y se leyó con un lector de verdad, achicando la página, y
# cada medición se repitió TRES VECES —la primera vuelta dio fallos sueltos que
# al repetirlos no volvieron a aparecer: eran del lector, no del código—.
#
#   3 px → 136 px de lado.  Lee hasta el 80 %. Al 70 % se cae, las tres veces.
#   4 px → 180 px de lado.  Lee hasta el 65 %.
#   5 px → 225 px de lado.  Lee hasta el 50 %.
#
# Se toma 4, que es lo que pidió el dueño del proyecto: el código más chico que
# igual se lee donde se va a leer. El 65 % importa porque es justo donde cae un
# correo de 600 px ajustado al ancho de un teléfono; 3 px, que no llega ahí, se
# quedaría sin leer en el caso más común de todos.
PX_POR_MODULO = 4

# Cuántos módulos de blanco alrededor. Cuatro es lo que pide la norma.
#
# Se probó con tres y con dos, para ver si se podía ahorrar ancho, y el
# resultado fue peor que inútil: iba y venía sin orden —tres se leía al 40 % y
# no al 50 %—, que es la firma del redondeo, no de una mejora. Con cuatro sale
# limpio en las cuatro escalas. Se deja lo que pide la norma.
MODULOS_DE_SILENCIO = 4


def matriz(texto: str):
    """La rejilla de módulos: una lista de filas, `True` donde va oscuro.

    Usa `qrcode`, que YA está en `requirements.txt` y ya se usa en producción
    para el código del segundo factor. No hace falta Pillow: `get_matrix()` no
    pasa por ahí.
    """
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M

    codigo = qrcode.QRCode(error_correction=ERROR_CORRECT_M, border=0)
    codigo.add_data(texto)
    # `fit=True` elige el tamaño más chico que alcance. Escribirlo a mano sería
    # elegir mal el día que el dato crezca un carácter.
    codigo.make(fit=True)
    return codigo.get_matrix()


def _fila(modulos, px: int, oscuro: str, claro: str) -> str:
    """Una fila, con los tramos del mismo color fusionados. Ver el punto 1."""
    celdas = []
    arranque = 0
    for i in range(1, len(modulos) + 1):
        if i < len(modulos) and modulos[i] == modulos[arranque]:
            continue
        cuantos = i - arranque
        ancho = cuantos * px
        color = oscuro if modulos[arranque] else claro
        celdas.append(
            f'<td colspan="{cuantos}" width="{ancho}" height="{px}" bgcolor="{color}"'
            f' style="width:{ancho}px;height:{px}px;background-color:{color};'
            f'font-size:0;line-height:0;padding:0;mso-line-height-rule:exactly;">'
            f'<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"'
            f' width="{ancho}" height="{px}" alt="" style="display:block;border:0;"></td>')
        arranque = i
    return f'<tr style="height:{px}px;">{"".join(celdas)}</tr>'


def tabla(texto: str, *, px: int | None = None,
          oscuro: str = "#111827", claro: str = "#ffffff",
          radio: int = 0, borde: str = "") -> str:
    """El QR entero, listo para pegar en el correo. Devuelve "" si algo falla.

    Devuelve vacío y no levanta: el comprobante sale igual sin el código, y un
    correo que no llega porque no se pudo dibujar un cuadradito es mucho peor
    que uno sin cuadradito.

    `px=None` y no `px=PX_POR_MODULO`: un valor por omisión se evalúa UNA VEZ,
    al importar el módulo, y queda congelado. Escrito de la forma obvia, quien
    cambia `PX_POR_MODULO` para medir otro tamaño sigue obteniendo el de antes
    y no se entera. Pasó al medir esto, y la tabla de resultados salió mintiendo.

    `radio` y `borde` son el marco: esquinas redondeadas y una línea alrededor.
    Van en el recuadro blanco de AFUERA, nunca en los módulos. Redondear los
    módulos uno por uno obligaría a darle una celda a cada uno, y eso es
    exactamente lo que rompe la rejilla (ver el punto 1 de arriba). Outlook
    ignora las esquinas redondeadas y las muestra rectas, que es la peor cosa
    que puede pasar: un marco cuadrado.

    """
    if px is None:
        px = PX_POR_MODULO
    try:
        m = matriz(texto)
    except Exception as e:                                    # pragma: no cover
        logger.warning("no se pudo armar el QR: %s: %s", type(e).__name__, e)
        return ""

    lado = len(m)
    silencio = MODULOS_DE_SILENCIO * px
    ancho = lado * px

    # La hilera de alto cero que fija las columnas. Ver el punto 1.
    fijar = "".join(f'<td width="{px}" style="width:{px}px;height:0;'
                    f'font-size:0;line-height:0;padding:0;"></td>' for _ in range(lado))

    filas = "".join(_fila(fila, px, oscuro, claro) for fila in m)

    total = ancho + silencio * 2
    # El marco va en la celda y NO en la tabla: la tabla de afuera lleva
    # `border-collapse`, y con eso varios programas de correo se comen el
    # redondeo y la línea. En la celda sobreviven.
    marco = (f'border-radius:{radio}px;' if radio else "") + \
            (f'border:1px solid {borde};' if borde else "")

    return (
        f'<table cellpadding="0" cellspacing="0" border="0" role="presentation"'
        f' width="{total}"'
        f' style="width:{total}px;border-collapse:collapse;'
        f'border-spacing:0;">'
        f'<tr><td width="{total}" align="center" bgcolor="{claro}"'
        f' style="padding:{silencio}px;background-color:{claro};'
        f'font-size:0;line-height:0;{marco}">'
        f'<table cellpadding="0" cellspacing="0" border="0" role="presentation"'
        f' width="{ancho}" style="width:{ancho}px;border-collapse:collapse;'
        f'border-spacing:0;table-layout:fixed;">'
        f'<tr style="height:0;">{fijar}</tr>{filas}</table>'
        f'</td></tr></table>')


def medida(texto: str, px: int | None = None) -> tuple:
    """(módulos por lado, píxeles de lado con la zona blanca). Para decidir."""
    if px is None:
        px = PX_POR_MODULO
    lado = len(matriz(texto))
    return lado, lado * px + MODULOS_DE_SILENCIO * px * 2
