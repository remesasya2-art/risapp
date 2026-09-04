"""
tests/test_imagen_recibida.py — Que no se GUARDE lo que no se puede abrir.

LA OTRA MITAD DEL MISMO AGUJERO

    `test_url_de_archivo.py` prueba que la pantalla no abra un valor peligroso.
    Esto prueba que no entre. Las dos hacen falta, y por motivos distintos:

      * el filtro del navegador es lo único que protege de lo que YA está
        guardado, que entró antes de que existiera esta validación;
      * esta validación es lo único que impide que el campo siga siendo texto
        libre para quien arma el pedido a mano, sin pasar por la pantalla.

    Confiar en una sola de las dos es confiar en que nadie llame a la API
    directamente, o en que nadie olvide el filtro en la próxima pantalla.

QUE CAMPOS SON

    Los tres documentos del KYC, el comprobante de una recarga en VES y los
    comprobantes de un retiro. Todos llegan como texto adentro del JSON, y todos
    los abre después un administrador.
"""
import os
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from services.imagen_recibida import (                              # noqa: E402
    TOPE_BYTES, ImagenInvalida, es_imagen_aceptable, limpiar_imagen,
    limpiar_imagen_opcional, limpiar_lista)


# ══════════════════════════════════════════════════════════════════════════
# 1. Lo que no puede entrar
# ══════════════════════════════════════════════════════════════════════════

PELIGROSOS = [
    "javascript:alert(1)",
    "JavaScript:fetch('/api/admin/users')",
    "  javascript:alert(1)",
    "java\tscript:alert(1)",
    "java\nscript:alert(1)",
    "java\x00script:alert(1)",
    "vbscript:msgbox(1)",
    "data:text/html,<script>alert(1)</script>",
    "data:text/html;base64,PHNjcmlwdD4=",
    "data:image/svg+xml;base64,PHN2Zz48c2NyaXB0Lz48L3N2Zz4=",
    "data:image/svg+xml,<svg onload=alert(1)>",
    "file:///etc/passwd",
    "//otro-sitio.example/a.png",
]


@pytest.mark.parametrize("valor", PELIGROSOS)
def test_NADA_QUE_PUEDA_EJECUTARSE_SE_GUARDA(valor):
    with pytest.raises(ImagenInvalida):
        limpiar_imagen(valor)
    assert es_imagen_aceptable(valor) is False


def test_el_mensaje_del_rechazo_le_dice_al_usuario_que_hacer():
    """Quien manda esto de verdad casi siempre es alguien probando. Pero el
    mismo mensaje lo puede ver alguien con una foto rara, y «400 Bad Request»
    no le dice a nadie que vuelva a sacar la foto."""
    with pytest.raises(ImagenInvalida) as e:
        limpiar_imagen("javascript:alert(1)", campo="El documento")
    assert "El documento" in str(e.value)
    assert "de nuevo" in str(e.value).lower()


@pytest.mark.parametrize("valor", [None, 12, [], {}, True, b"bytes"])
def test_lo_que_ni_siquiera_es_texto_no_entra(valor):
    with pytest.raises(ImagenInvalida):
        limpiar_imagen(valor)


def test_UNA_FOTO_ENORME_NO_ENTRA():
    """Un `data:` viaja adentro del documento de Mongo. Sin tope, lo que se
    rompe no es la subida: es la lectura de esa colección, para todos, desde el
    momento en que un documento pasa los 16 MB."""
    gigante = "data:image/png;base64," + ("A" * (TOPE_BYTES + 1))
    with pytest.raises(ImagenInvalida, match="pesa demasiado"):
        limpiar_imagen(gigante)


def test_el_tope_se_mide_en_bytes_no_en_caracteres():
    """Un carácter no ASCII ocupa más de un byte, y lo que se guarda son bytes."""
    justo_pasado = "data:image/png;base64," + ("ñ" * (TOPE_BYTES // 2))
    assert len(justo_pasado) < TOPE_BYTES        # en caracteres entra
    with pytest.raises(ImagenInvalida, match="pesa demasiado"):
        limpiar_imagen(justo_pasado)             # en bytes no


# ══════════════════════════════════════════════════════════════════════════
# 2. Lo que sí tiene que entrar — una validación que rompe la app se saca
# ══════════════════════════════════════════════════════════════════════════

LEGITIMAS = [
    "data:image/jpeg;base64,/9j/4AAQSkZJRg==",
    "data:image/png;base64,iVBORw0KGgo=",
    "data:image/webp;base64,UklGRg==",
    "data:image/JPEG;base64,/9j/4AAQ",           # el navegador a veces manda mayúsculas
    "/api/static/uploads/comprobante.jpg",
    "/api/media/twilio/ACxxx/Media/MEzzz",
    "https://storage.example.com/kyc/abc.jpg",
]


@pytest.mark.parametrize("valor", LEGITIMAS)
def test_lo_que_manda_la_pantalla_de_verdad_entra(valor):
    assert limpiar_imagen(valor) == valor


def test_se_guarda_el_valor_TAL_CUAL_LLEGO():
    """Un base64 al que se le sacan caracteres deja de ser esa imagen. La
    limpieza es sólo para decidir; lo que se guarda es el original."""
    valor = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="
    assert limpiar_imagen(valor) is valor


def test_http_pelado_no_entra_aunque_el_navegador_lo_muestre():
    """El filtro del navegador acepta `http://` porque hay comprobantes viejos
    guardados así y hay que poder mirarlos. Lo que ENTRA desde ahora, no: la
    pantalla nunca manda uno, y en producción `http://` es contenido mixto que
    el navegador termina bloqueando."""
    with pytest.raises(ImagenInvalida):
        limpiar_imagen("http://storage.example.com/a.jpg")


# ══════════════════════════════════════════════════════════════════════════
# 3. Los opcionales y las listas
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("vacio", [None, "", "   ", "\t\n"])
def test_un_campo_opcional_vacio_es_un_vacio_legitimo(vacio):
    """El dorso del documento no va para un pasaporte, y el comprobante de una
    recarga puede subirse después. Vacío no es inválido."""
    assert limpiar_imagen_opcional(vacio) is None


def test_un_opcional_con_algo_peligroso_adentro_SI_levanta():
    with pytest.raises(ImagenInvalida):
        limpiar_imagen_opcional("javascript:alert(1)")


def test_UNA_LISTA_CON_UNA_MALA_NO_ENTRA_ENTERA():
    """Guardar tres de cuatro deja al operador mirando un juego incompleto sin
    saber que falta uno, que es peor que un error claro."""
    lista = ["data:image/png;base64,AAA",
             "data:image/png;base64,BBB",
             "javascript:alert(1)"]
    with pytest.raises(ImagenInvalida):
        limpiar_lista(lista)


def test_una_lista_buena_pasa_completa():
    lista = ["data:image/png;base64,AAA", "/api/static/x.jpg"]
    assert limpiar_lista(lista) == lista


def test_una_lista_vacia_o_ausente_no_molesta():
    assert limpiar_lista(None) is None
    assert limpiar_lista([]) == []


def test_algo_que_no_es_una_lista_no_pasa_por_error():
    with pytest.raises(ImagenInvalida):
        limpiar_lista("data:image/png;base64,AAA")


# ══════════════════════════════════════════════════════════════════════════
# 4. Que se USE — igual que del lado del navegador, acá vuelve el agujero
# ══════════════════════════════════════════════════════════════════════════

# Dónde entra una imagen hoy, y con qué se la valida. Si mañana aparece otra
# ruta que guarde una imagen sin validar, este test no la ve — por eso está
# también el barrido de abajo.
PUNTOS_DE_ENTRADA = [
    ("routes/misc.py", "limpiar_imagen"),           # los documentos del KYC
    ("routes/transactions.py", "limpiar_imagen_opcional"),   # recarga en VES
    ("routes/admin.py", "limpiar_lista"),           # comprobantes de un retiro
    ("routes/adminbrl_bridge.py", "limpiar_lista"),  # el puente con adminbrl
]


@pytest.mark.parametrize("archivo, funcion", PUNTOS_DE_ENTRADA)
def test_cada_punto_de_entrada_valida(archivo, funcion):
    fuente = open(os.path.join(_BACKEND, archivo), encoding="utf-8").read()
    assert funcion in fuente, f"{archivo} guarda una imagen sin llamar a {funcion}()"


def test_NINGUNA_RUTA_GUARDA_UNA_IMAGEN_SIN_VALIDARLA():
    """El barrido. Busca las asignaciones que meten un campo de imagen en un
    documento y pide que el valor venga de una variable ya validada o de una
    llamada al validador.

    Es tosco a propósito: prefiere pedir que se escriba la validación de más
    antes que dejar pasar un campo nuevo sin ella.
    """
    import re

    campos = ("proof_image", "proof_images", "voucher_image", "id_document_image",
              "cpf_image", "selfie_image", "comprobante_usuario")
    # `"campo": <algo>` donde <algo> viene del pedido sin pasar por el validador.
    patron = re.compile(
        r'"(' + "|".join(campos) + r')"\s*:\s*'
        r'(request\.[A-Za-z_.]+|data\.[A-Za-z_.]+|request\.get\([^)]*\))')

    sospechosos = []
    rutas = os.path.join(_BACKEND, "routes")
    for archivo in sorted(os.listdir(rutas)):
        if not archivo.endswith(".py"):
            continue
        texto = open(os.path.join(rutas, archivo), encoding="utf-8").read()
        for m in patron.finditer(texto):
            linea = texto.count("\n", 0, m.start()) + 1
            sospechosos.append(f"routes/{archivo}:{linea}  {m.group(0)[:70]}")

    assert not sospechosos, (
        "una ruta guarda un campo de imagen tomándolo del pedido sin validarlo.\n"
        "Pasalo por services/imagen_recibida.py:\n  " + "\n  ".join(sospechosos))
