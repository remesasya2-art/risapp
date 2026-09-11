"""
tests/test_qr_del_comprobante.py — Que el código del talón se pueda leer.

POR QUE ESTE ARCHIVO NO DECODIFICA UN QR

    Lo obvio sería dibujar el código, fotografiarlo y leerlo con un lector.
    Eso se hizo —con Chromium y con OpenCV, y de ahí salieron los tamaños que
    están anotados en `services/qr.py`—, pero no puede vivir acá: un navegador
    y una librería de visión no son dependencias de test de este repositorio,
    y un test que se saltea cuando no están es un test que no existe.

    Lo que sí vive acá es la cadena que sostiene esa medición:

      1. `qrcode` arma la rejilla. Es la librería que ya usa el segundo factor
         en producción, y de que un QR válido sea válido se encarga ella.
      2. ESTE archivo comprueba que el HTML dibuje EXACTAMENTE esa rejilla.

    El punto 2 es el que puede romperse en silencio, y es el que tiene el test
    más importante de acá: `test_el_dibujo_es_fiel_a_la_rejilla` vuelve a armar
    la matriz leyendo el HTML generado y la compara con la original. Un error
    de fusión de tramos —el que ya pasó, y el que deja el código torcido— no
    cambia ni el tamaño ni la cantidad de filas: cambia dónde cae cada módulo.
    No hay forma de verlo sin volver a leer el dibujo.
"""
import os
import re
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from services import comprobante as comp             # noqa: E402
from services import qr                              # noqa: E402

CARGA = ("RISAPP\nRIS-8827194\nRetiro a bolívares\n"
         "4.500,00 Bs\n11/09/2026 21:40\nCOMPLETADO")


# ──────────────────────────────────────────────────────────────────────────
#  El lector: vuelve a armar la rejilla leyendo el HTML.
# ──────────────────────────────────────────────────────────────────────────

def aparece(aguja: str, html: str) -> bool:
    """Si `aguja` está en `html`, pero comparando NUMEROS.

    Escrito como `assert aguja in html`, pytest explica el fallo volcando el
    HTML entero —setenta y ocho mil caracteres— y tarda tanto que en el
    servidor de integración no parece un test rojo: parece un test colgado.
    Se descubrió rompiendo estas guardas a propósito: detectaban la falla y no
    llegaban a decirlo.
    """
    return html.find(aguja) != -1


def solo_los_modulos(html: str) -> str:
    """La tabla de ADENTRO, la de los módulos.

    El recuadro blanco de afuera es una celda con color de fondo igual que un
    módulo claro, y contarla como un módulo más corre la rejilla entera. Y sus
    filas envuelven a las de adentro, así que buscar `<tr>` sobre el HTML
    completo devuelve cada fila dos veces.
    """
    return html.split('table-layout:fixed;">', 1)[1].split("</table>", 1)[0]


def celdas_de_modulo(html: str):
    return re.findall(r"<td[^>]*bgcolor=[^>]*>", solo_los_modulos(html))


def releer(html: str, oscuro: str = "#111827"):
    """La matriz que dibuja este HTML, según el HTML y no según quien lo armó.

    De cada fila saca los tramos con su `colspan` y su color, expandiéndolos de
    vuelta a un módulo por celda. Si el dibujo y la rejilla no coinciden, se ve
    acá.
    """
    filas = []
    for fila in re.findall(r"<tr[^>]*>(.*?)</tr>", solo_los_modulos(html), re.S):
        modulos = []
        for celda in re.findall(r"<td[^>]*>", fila):
            # La hilera que fija las columnas no pinta nada, y ésa es la
            # diferencia que sirve. Descartarla por su `height:0` no funciona:
            # TODAS las celdas llevan `line-height:0`, que contiene ese texto.
            # Escrito así, el lector salteaba el dibujo entero y devolvía vacío.
            if "bgcolor=" not in celda:
                continue
            cuantos = int((re.search(r'colspan="(\d+)"', celda) or [0, 1])[1])
            color = (re.search(r'bgcolor="([^"]+)"', celda) or [0, ""])[1]
            modulos.extend([color.lower() == oscuro.lower()] * cuantos)
        if modulos:
            filas.append(modulos)
    return filas


def test_el_lector_de_arriba_reconoce_un_dibujo_torcido():
    """La guarda de la guarda.

    `releer` es el test más importante del archivo, así que hay que probar que
    sirve para algo. Se le da un dibujo al que le sacamos un módulo de un tramo
    —el error de fusión exacto que se quiere atrapar— y tiene que notarlo.
    """
    html = qr.tabla(CARGA)
    bien = releer(html)
    torcido = releer(re.sub(r'colspan="(\d+)"',
                            lambda m: f'colspan="{max(1, int(m.group(1)) - 1)}"',
                            html, count=1))
    assert bien != torcido


# ──────────────────────────────────────────────────────────────────────────
#  El dibujo
# ──────────────────────────────────────────────────────────────────────────

def test_el_dibujo_es_fiel_a_la_rejilla():
    assert releer(qr.tabla(CARGA)) == qr.matriz(CARGA)


def test_todas_las_filas_declaran_la_misma_cantidad_de_columnas():
    """El navegador arma las columnas contando celdas.

    Una fila con menos columnas que las otras le corre la rejilla, y el código
    deja de leerse sin que el HTML parezca roto.
    """
    anchos = {len(f) for f in releer(qr.tabla(CARGA))}
    assert len(anchos) == 1
    assert anchos.pop() == len(qr.matriz(CARGA))


def test_la_primera_hilera_fija_las_columnas():
    """Sin ella cada fila reparte el ancho a su manera. Ver `services/qr.py`."""
    html = qr.tabla(CARGA)
    lado = len(qr.matriz(CARGA))
    # Por lo que no tiene, no por su alto: buscarla por `height:0` encuentra
    # todas, porque cada celda del dibujo lleva `line-height:0`.
    hileras = [f for f in re.findall(r"<tr[^>]*>(.*?)</tr>",
                                     solo_los_modulos(html), re.S)
               if "bgcolor=" not in f]
    assert len(hileras) == 1
    assert hileras[0].count("<td") == lado
    # y va PRIMERA: si va después, las columnas ya quedaron repartidas
    assert solo_los_modulos(html).index(hileras[0]) < 60


def test_el_blanco_de_alrededor_esta():
    """Sin zona de silencio no lo lee ningún lector, por perfecta que esté."""
    html = qr.tabla(CARGA, px=4)
    assert aparece(f"padding:{4 * qr.MODULOS_DE_SILENCIO}px", html)


def test_el_alto_de_linea_esta_muerto_en_cada_modulo():
    """Sin esto cada fila se estira al alto de una línea y salen rectángulos."""
    for celda in celdas_de_modulo(qr.tabla(CARGA)):
        assert "font-size:0" in celda
        assert "line-height:0" in celda
        assert "mso-line-height-rule:exactly" in celda


def test_el_ancho_va_en_la_etiqueta_y_no_solo_en_el_estilo():
    """Un ancho sólo en el estilo lo descartan varios programas de correo, y
    ahí la columna se encoge y el código se deforma."""
    for celda in celdas_de_modulo(qr.tabla(CARGA)):
        assert re.search(r'width="\d+"', celda), celda


def test_no_pide_ni_una_imagen_de_afuera():
    """Una imagen de afuera la bloquea Outlook de arranque, y entonces al
    código le faltan pedazos. El espaciador va incrustado."""
    html = qr.tabla(CARGA)
    assert not aparece("http", html)
    afuera = [s for s in re.findall(r'src="([^"]*)"', html)
              if not s.startswith("data:image/gif;base64,")]
    assert afuera == []


def test_el_tamano_del_modulo_hace_efecto_de_verdad():
    """La constante decía 4 y era inmovible: estaba escrita como valor por
    omisión de un parámetro, o sea evaluada una sola vez al importar. Quien la
    cambiara para medir otro tamaño seguía obteniendo el de antes."""
    antes = qr.PX_POR_MODULO
    try:
        qr.PX_POR_MODULO = 7
        assert aparece('height="7"', qr.tabla(CARGA))
        assert qr.medida(CARGA)[1] == qr.medida(CARGA)[0] * 7 + 7 * qr.MODULOS_DE_SILENCIO * 2
    finally:
        qr.PX_POR_MODULO = antes


def test_medida_dice_lo_que_mide_el_dibujo():
    lado, px_total = qr.medida(CARGA)
    assert lado == len(qr.matriz(CARGA))
    assert aparece(f'width="{px_total}"', qr.tabla(CARGA))


def test_si_el_codigo_no_se_puede_armar_el_correo_sale_igual(monkeypatch):
    """Un correo que no llega porque no se pudo dibujar un cuadradito es mucho
    peor que uno sin cuadradito."""
    def explota(texto):
        raise RuntimeError("se cayó la librería")
    monkeypatch.setattr(qr, "matriz", explota)
    assert qr.tabla(CARGA) == ""


# ──────────────────────────────────────────────────────────────────────────
#  El marco
# ──────────────────────────────────────────────────────────────────────────

def test_el_marco_ovalado_no_toca_los_modulos():
    """Redondear los módulos obliga a darle una celda a cada uno, y eso rompe
    la fusión por tramos que es lo único que hace que la rejilla salga derecha.
    El marco va en el recuadro blanco de afuera."""
    html = qr.tabla(CARGA, radio=14, borde="#F5A623")
    assert html.count("border-radius") == 1
    assert html.count("border:1px solid") == 1
    for celda in celdas_de_modulo(html):
        assert "border-radius" not in celda
    # y redondear no cambió ni un módulo
    assert releer(html) == qr.matriz(CARGA)


def test_sin_marco_no_aparece_ni_el_radio_ni_la_linea():
    html = qr.tabla(CARGA)
    assert not aparece("border-radius", html)
    assert not aparece("border:1px", html)


# ──────────────────────────────────────────────────────────────────────────
#  Lo que va adentro del código
# ──────────────────────────────────────────────────────────────────────────

from datetime import datetime, timezone              # noqa: E402

CUANDO = datetime(2026, 9, 11, 21, 40, tzinfo=timezone.utc)


def test_la_carga_lleva_las_seis_lineas_que_se_pidieron():
    carga = comp.carga_del_qr(referencia="RIS-8827194", tipo="Retiro a bolívares",
                              monto="4.500,00 Bs", cuando=CUANDO, estado="Completado")
    assert carga.split("\n") == ["RISAPP", "RIS-8827194", "Retiro a bolívares",
                                 "4.500,00 Bs", "11/09/2026 21:40", "COMPLETADO"]


def test_un_estado_de_varias_palabras_que_entra_llega_entero():
    """Resumirlo a la primera palabra es el plan B, no el plan A. «En
    Pacaraima» resumido a «EN» no dice nada, y entra completo de sobra."""
    carga = comp.carga_del_qr(referencia="RIS-000123", tipo="Paquete",
                              cuando=CUANDO, estado="En Pacaraima")
    assert "EN PACARAIMA" in carga


def test_lo_que_falta_no_deja_una_linea_vacia():
    """Un paquete no tiene monto. Una línea en blanco adentro del código gasta
    bytes del tope y no dice nada."""
    carga = comp.carga_del_qr(referencia="RIS-000123", tipo="Envío de paquete",
                              cuando=CUANDO, estado="En Pacaraima")
    assert "" not in carga.split("\n")


def test_la_carga_no_lleva_nada_de_la_otra_persona():
    """Lo que hay adentro del código NO SE VE. Quien reenvía el comprobante
    decide sobre los campos escritos; sobre esto no puede decidir porque no
    sabe que está ahí."""
    carga = comp.carga_del_qr(referencia="RIS-8827194", tipo="Retiro a bolívares",
                              monto="4.500,00 Bs", cuando=CUANDO, estado="Completado")
    for prohibido in ("María", "V-12345678", "01340000001234567890", "http", "@"):
        assert prohibido not in carga


LARGOS = [
    "Recarga con transferencia VES",
    "Envío de dinero a Venezuela en bolívares soberanos",
    "Retiro a cuenta bancaria en bolívares con tasa preferencial",
    "Pago de paquetería internacional Pacaraima Santa Elena",
]


@pytest.mark.parametrize("tipo", LARGOS)
def test_una_descripcion_larga_acorta_el_tipo_y_no_el_numero(tipo):
    """El número, el monto y la fecha son lo que se mira en un reclamo."""
    carga = comp.carga_del_qr(referencia="RIS-9930571", tipo=tipo,
                              monto="1.200,00 VES", cuando=CUANDO, estado="Rechazada")
    assert len(carga.encode("utf-8")) <= comp.TOPE_DEL_QR
    for imprescindible in ("RISAPP", "RIS-9930571", "1.200,00 VES",
                           "11/09/2026 21:40", "RECHAZADA"):
        assert imprescindible in carga


@pytest.mark.parametrize("tipo", LARGOS)
def test_el_codigo_no_crece_mas_alla_de_lo_que_entra_en_el_talon(tipo):
    """37x37 es el más grande que cabe en el talón al tamaño de módulo que se
    lee. El que sigue entraría en ancho y ya no se leería."""
    carga = comp.carga_del_qr(referencia="RIS-9930571", tipo=tipo,
                              monto="1.200,00 VES", cuando=CUANDO, estado="Rechazada")
    assert len(qr.matriz(carga)) <= 37


EXTREMOS = [
    dict(referencia="RIS-9930571", tipo="Pago", monto="1.234.567.890,00 VES",
         cuando=CUANDO, estado="Esperando confirmación del transportista"),
    dict(referencia="RIS-0000000000000123456", tipo="Envío",
         monto="999.999,00 Bs", cuando=CUANDO, estado="Rechazado por el banco"),
    dict(referencia="RIS-9930571", tipo="", monto="1.200,00 VES",
         cuando=CUANDO, estado="Devuelto al remitente por dirección incompleta"),
]


# Los tres de arriba entran en cuanto se resume el estado, así que no llegan a
# los últimos escalones de la cascada. Éstos sí, y hacen falta: sin ellos se le
# podía sacar el último escalón al código y ningún test se daba cuenta.
#
#   sale_el_tipo   el tipo tiene que irse del todo para que entre.
#   sale_el_estado ni sin el tipo entra: también se va el estado.
#   se_corta       ni pelado entra, porque el número y el monto son enormes.
HASTA_EL_FONDO = [
    ("sale_el_tipo", dict(
        referencia="RIS-0000000000000123456", tipo="Pago",
        monto="1.234.567.890,00 VES", cuando=CUANDO,
        estado="Imposibilitado de procesar")),
    ("sale_el_estado", dict(
        referencia="RIS-0000000000000123456", tipo="Pago",
        monto="1.234.567.890,00 VES", cuando=CUANDO,
        estado="Internacionalizado sin respuesta")),
    ("se_corta", dict(
        referencia="RIS-" + "0" * 60, tipo="Pago",
        monto="1.234.567.890.123.456,00 VES", cuando=CUANDO,
        estado="Rechazado")),
]


def test_el_tipo_no_se_acorta_mas_de_lo_necesario():
    """La cascada toma el PRIMER intento que entra, y por eso el tipo pierde
    de a cuatro letras y no de golpe. Un tipo mutilado sin motivo —«Reca» en
    vez de «Recarga con transferencia»— no lo nota nadie mirando el código,
    porque el código igual se lee: sólo dice menos."""
    carga = comp.carga_del_qr(referencia="RIS-9930571",
                              tipo="Recarga con transferencia VES",
                              monto="1.200,00 VES", cuando=CUANDO,
                              estado="Rechazada")
    tipo = carga.split("\n")[2]
    assert tipo.startswith("Recarga con transferencia")
    # y si el paso hubiera sido mas grande, esto quedaria mas corto
    assert len(tipo) >= len("Recarga con transferencia")


@pytest.mark.parametrize("caso,datos", HASTA_EL_FONDO, ids=[c for c, _ in HASTA_EL_FONDO])
def test_la_cascada_baja_hasta_donde_haga_falta(caso, datos):
    carga = comp.carga_del_qr(**datos)
    assert len(carga.encode("utf-8")) <= comp.TOPE_DEL_QR
    assert len(qr.matriz(carga)) <= 37
    if caso == "sale_el_tipo":
        # se fue el tipo, pero el estado resumido sigue
        assert "PAGO" not in carga.upper()
        assert "IMPOSIBILITADO" in carga
    if caso == "sale_el_estado":
        assert "INTERNACIONALIZADO" not in carga
    if caso == "se_corta":
        # se corta acá, donde se ve, y no en el dibujo
        assert carga.startswith("RISAPP")


@pytest.mark.parametrize("datos", EXTREMOS)
def test_cuando_acortar_el_tipo_no_alcanza_el_tipo_se_va_del_todo(datos):
    """Acortar el tipo se rinde cuando le quedan cuatro letras, y ahí el bucle
    salía con el tope sin cumplir: el código saltaba de tamaño, no entraba en
    el talón y no se leía, sin que nada lo dijera. Se vio rompiéndolo a
    propósito —y de paso el bucle se colgaba para siempre—."""
    carga = comp.carga_del_qr(**datos)
    assert len(carga.encode("utf-8")) <= comp.TOPE_DEL_QR
    assert len(qr.matriz(carga)) <= 37
    # lo que no se negocia sigue ahí
    for imprescindible in ("RISAPP", datos["referencia"], datos["monto"]):
        assert imprescindible in carga


@pytest.mark.parametrize("datos", EXTREMOS)
def test_aunque_no_entre_la_frase_entera_sigue_diciendo_que_paso(datos):
    """Lo que se pidió del estado es saber si salió bien o mal. La primera
    palabra lo dice —RECHAZADO, DEVUELTO, ESPERANDO— y la frase entera es la
    explicación, que no es para lo que sirve un código."""
    carga = comp.carga_del_qr(**datos)
    assert datos["estado"].split()[0].upper() in carga


def test_el_tope_esta_medido_y_no_elegido():
    """84 bytes es exactamente lo último que entra en 37x37 con corrección M.
    Si alguien lo sube, el código salta de tamaño y deja de leerse."""
    # Minúsculas y no mayúsculas: con puras mayúsculas `qrcode` usa un modo
    # más compacto que no es el que corresponde a una carga con acentos, y el
    # test mediría un código que nunca vamos a dibujar.
    assert len(qr.matriz("a" * comp.TOPE_DEL_QR)) == 37
    assert len(qr.matriz("a" * (comp.TOPE_DEL_QR + 1))) > 37


# ──────────────────────────────────────────────────────────────────────────
#  El código dentro del comprobante
# ──────────────────────────────────────────────────────────────────────────

def armar_uno(**cambios):
    datos = dict(titulo="Tu retiro fue completado", tipo="Retiro a bolívares",
                 monto="4.500,00 Bs", referencia="RIS-8827194", cuando=CUANDO,
                 estado="Completado")
    datos.update(cambios)
    return comp.armar(**datos)


def test_el_comprobante_mete_el_codigo_en_el_talon():
    carga = comp.carga_del_qr(referencia="RIS-8827194", tipo="Retiro a bolívares",
                              monto="4.500,00 Bs", cuando=CUANDO, estado="Completado")
    html = armar_uno(carga_qr=carga)
    assert aparece("Escaneá para ver los datos", html)
    # y el dibujo que quedó adentro del talón es el de esa carga
    assert releer(html) == qr.matriz(carga)


def test_sin_carga_no_hay_codigo_ni_el_renglon_que_lo_explica():
    """Un comprobante sin código sale igual. Lo que no puede salir es el
    renglón que dice «escaneá» al lado de un hueco."""
    html = armar_uno()
    assert not aparece("Escaneá para ver los datos", html)
    assert not aparece("data:image/gif", html)


def test_el_codigo_del_comprobante_lleva_el_marco_ovalado():
    """Contando, y no preguntando si aparece.

    Preguntando «¿aparece border-radius:14px?» el test pasaba igual con el
    código sin marco: el pasaje ya lleva las esquinas redondeadas en su propia
    tarjeta, así que la respuesta era sí por el motivo equivocado. Se vio
    sacándole el marco al código a propósito: ningún test se quejó.
    """
    carga = comp.carga_del_qr(referencia="RIS-8827194", cuando=CUANDO)
    assert armar_uno().count("border-radius:14px") == 1            # la tarjeta
    assert armar_uno(carga_qr=carga).count("border-radius:14px") == 2


def test_el_talon_le_deja_al_codigo_el_ancho_que_necesita():
    """El código mide 180 px y el talón 220. Si alguien angosta el talón, el
    código no se encoge: se sale, o le arrebata el ancho al resto."""
    carga = comp.carga_del_qr(referencia="RIS-8827194", tipo="Retiro a bolívares",
                              monto="4.500,00 Bs", cuando=CUANDO, estado="Completado")
    _, mide = qr.medida(carga)
    html = armar_uno(carga_qr=carga)
    talon = int(re.search(r'<td width="(\d+)" valign="top"\s*\n\s*style="width:\1px;'
                          r'background:#fffbeb', html).group(1))
    relleno = 16 + 18
    assert mide + relleno <= talon
