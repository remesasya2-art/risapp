"""
tests/test_cotizacion_a_medias.py — La cotización que quedó sin confirmar.

EL CASO, TAL COMO PASO

    El usuario cotizó un envío, salió de la aplicación sin confirmar, y volvió
    cinco minutos después. Se encontró con un aviso que decía «esta cotización
    todavía no está confirmada», un botón «Actualizar» que no cambiaba nada, y
    un botón «Cotizar de nuevo» — que es volver a tipear el paquete entero.

    No era un error de lectura ni un envío roto: la cotización estaba viva y le
    quedaban 48 horas. El backend la podía confirmar perfectamente
    —`POST /envios/crear` recibe un `envio_id`— pero la pantalla de detalle no
    ofrecía por dónde.

    «Actualizar» tampoco estaba roto: releía el envío y el envío seguía igual.
    Desde afuera se lee como que la pantalla no responde.

POR QUE ESTE TEST ES SOBRE EL FUENTE DE LA PANTALLA

    El agujero no estaba en el backend —ahí todo funcionaba— sino en que la
    pantalla no usaba lo que el backend ofrecía. Un test de backend no lo
    hubiera visto nunca: los de `test_envios_crear.py` pasaban en verde
    mientras el usuario no tenía cómo confirmar.

    Se revisa entonces lo que la pantalla efectivamente hace: que llame a
    confirmar, que mande las dos aceptaciones y la versión de términos, y que
    no las dé por tildadas.
"""
import os
import pathlib
import re

import pytest

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))
_PANTALLA = _RAIZ / "frontend" / "src" / "pages" / "EnvioDetalle.jsx"


@pytest.fixture(scope="module")
def fuente():
    if not _PANTALLA.exists():                               # pragma: no cover
        pytest.skip("no está el frontend en este árbol")
    return _PANTALLA.read_text(encoding="utf-8")


def test_la_pantalla_de_detalle_puede_confirmar(fuente):
    """Lo que faltaba: que exista la llamada.

    Antes la única salida de una cotización a medias era `/envios/nuevo`, o sea
    empezar de cero.
    """
    assert "'/envios/crear'" in fuente, (
        "La pantalla de detalle no confirma. Una cotización vigente que quedó a "
        "medias sólo se puede abandonar y volver a cargar entera.")


def test_confirmar_manda_las_dos_aceptaciones_y_la_version(fuente):
    """`envios_crear` exige las tres cosas. Si falta una, el usuario aprieta el
    botón y se come un 400 que no puede arreglar."""
    for campo in ("contenido_aceptado", "estimado_aceptado", "terminos_version"):
        assert campo in fuente, f"la confirmación no manda {campo}"


def test_las_aceptaciones_no_vienen_tildadas(fuente):
    """Son el registro que se lee el día que haya que defender un ajuste de
    precio. Tildarlas por defecto —o heredarlas de cuando cotizó— sería anotar
    una aceptación que nadie dio en este momento.

    Se mira que los dos estados nazcan en `false`, y que lo que se manda sean
    esos estados y no dos literales `true`. Lo segundo importa igual: un
    formulario que envía `contenido_aceptado: true` fijo registra una
    aceptación aunque la casilla esté vacía, y el registro es justamente lo que
    después hay que poder mostrar.
    """
    for cual in ("contenido", "estimado"):
        assert re.search(rf"\[{cual}, set\w+\] = useState\(false\)", fuente), (
            f"la aceptación «{cual}» no arranca sin tildar")

    for campo, estado in (("contenido_aceptado", "contenido"),
                          ("estimado_aceptado", "estimado")):
        assert re.search(rf"{campo}:\s*{estado}\b", fuente), (
            f"«{campo}» no manda el estado real de la casilla")


def test_el_boton_no_se_puede_apretar_sin_las_dos(fuente):
    """El backend igual lo frena, pero un botón que se puede apretar para
    recibir un error es una trampa: el usuario no sabe qué le falta."""
    assert "disabled={!contenido || !estimado}" in fuente, (
        "el botón de confirmar no exige las dos aceptaciones antes de habilitarse")


def test_una_cotizacion_vencida_no_ofrece_confirmar(fuente):
    """Confirmar un precio vencido es cobrarle al usuario un número que ya no
    existe. El backend lo rechaza con 409; la pantalla no puede ofrecerlo y
    esperar el error.
    """
    assert "vencida" in fuente, "la pantalla no distingue una cotización vencida"
    assert re.search(r"new Date\(envio\.vence_at\)\s*<=\s*new Date\(\)", fuente), (
        "el vencimiento no se compara contra la hora actual, así que una "
        "cotización vencida sigue ofreciendo el botón")


def test_el_vencimiento_se_recalcula_en_cada_render(fuente):
    """Que apretar «Actualizar» sirva para algo.

    Si el vencimiento se calculara una sola vez —en un `useState` inicial o un
    `useMemo` sin dependencias— una cotización que vence con la pantalla
    abierta seguiría ofreciendo el botón hasta recargar entera. Y «Actualizar»
    volvería a no hacer nada visible, que es de donde vino todo esto.
    """
    m = re.search(r"const vencida = ([^;]+);", fuente)
    assert m, "no se encontró el cálculo del vencimiento"
    assert "useState" not in m.group(1) and "useMemo" not in m.group(1), (
        "el vencimiento quedó congelado en el primer render")


def test_la_etiqueta_sigue_sin_mostrarse_antes_de_confirmar(fuente):
    """La regla que ya estaba, y que este cambio no puede aflojar.

    El texto para rotular la caja no se muestra en `cotizado`: alguien lo copió,
    fue a despachar, no confirmó nunca, y a las 48 horas la cotización se borró
    por TTL — la caja llegó a Pacaraima sin ningún envío que la reclame.
    """
    m = re.search(r"const ANTES_DE_DESPACHAR = \[([^\]]*)\]", fuente)
    assert m, "no se encontró la lista de estados que muestran la etiqueta"
    assert "cotizado" not in m.group(1), (
        "la etiqueta volvió a mostrarse antes de confirmar")
