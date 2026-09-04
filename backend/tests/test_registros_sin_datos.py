"""
tests/test_registros_sin_datos.py — Lo que queda escrito en los registros.

POR QUE ESTO ES UN PROBLEMA DE SEGURIDAD Y NO DE PROLIJIDAD

    Un registro no es un archivo privado. Los de esta aplicación los ve
    cualquiera que entre al panel del proveedor de hosting, se copian a
    servicios de terceros para poder buscarlos, se guardan mucho más tiempo que
    los datos que describen, y sobreviven a cualquier borrado que hagamos en la
    base. Todo lo que se escribe ahí sale del perímetro que controlamos.

    Y esta aplicación mueve remesas de venezolanos en Brasil. Un volcado de
    registros con correos, teléfonos y documentos no es «una filtración de
    datos»: es una lista de personas de una comunidad concreta, con cuánto manda
    cada una y a quién. Sirve para extorsionar y sirve para perseguir.

QUE HABIA

    35 puntos que interpolaban datos personales o cuerpos enteros de pedidos de
    terceros. Los dos peores:

      * `logger.info(f"webhook recibido: {payload}")` — el cuerpo entero que
        manda el proveedor de pagos. Hoy son campos inocuos; el día que
        agreguen el nombre del pagador entra al registro sin que nadie lo haya
        decidido.
      * Cuando el libro de auditoría fallaba al escribir, se registraba LA
        LINEA ENTERA, con el antes y el después del cambio. El documento más
        sensible del sistema, copiado al lugar menos protegido, justo en el
        momento en que algo ya había salido mal.

QUE SE PRUEBA

    Que las funciones de enmascarado hagan lo que dicen, y —lo que más importa—
    que el código no vuelva a escribir datos crudos. El último bloque recorre
    TODOS los `logger.*` de la aplicación.
"""
import ast
import os
import re
import sys

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from services import registro                                       # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
# 1. El enmascarado
# ══════════════════════════════════════════════════════════════════════════

def test_de_un_correo_queda_lo_justo_para_reconocerlo():
    """Dos letras y el dominio: alcanza para que soporte coteje con la persona
    que tiene enfrente, y no alcanza para armar una lista de nadie."""
    assert registro.correo("juan.perez@proveedor.test") == "ju***@proveedor.test"
    assert "juan.perez" not in registro.correo("juan.perez@proveedor.test")


def test_UN_CORREO_CORTO_TAMPOCO_SE_ESCRIBE_ENTERO():
    """El caso que se escapa cuando se enmascara «todo menos los primeros dos»:
    un nombre de dos letras quedaría entero."""
    enmascarado = registro.correo("jp@proveedor.test")
    assert enmascarado.startswith("j***"), enmascarado
    assert "jp@" not in enmascarado


@pytest.mark.parametrize("valor, esperado", [
    ("", "(sin correo)"),
    (None, "(sin correo)"),
    ("   ", "(sin correo)"),
    ("no-es-un-correo", "(correo ilegible)"),
])
def test_lo_que_no_es_un_correo_se_dice_y_no_se_copia(valor, esperado):
    assert registro.correo(valor) == esperado


def test_el_dominio_se_conserva_porque_es_para_lo_que_sirve():
    """La razón real por la que esto se registra es diagnosticar entregas de
    correo. Sin el dominio, la línea no sirve para nada y alguien la va a
    volver a poner entera."""
    assert registro.correo("x@dominio-raro.test").endswith("@dominio-raro.test")


def test_de_un_telefono_quedan_cuatro_digitos():
    assert registro.ultimos("+55 11 98765-4321") == "...4321"
    assert "98765" not in registro.ultimos("+55 11 98765-4321")


@pytest.mark.parametrize("valor", ["", None, "abc", "12"])
def test_un_telefono_corto_o_vacio_no_se_filtra_entero(valor):
    salida = registro.ultimos(valor)
    assert salida in ("(vacío)", "...")


# ══════════════════════════════════════════════════════════════════════════
# 2. El cuerpo que manda un tercero
# ══════════════════════════════════════════════════════════════════════════

def test_DEL_CUERPO_AJENO_SOLO_SALE_LO_QUE_SE_PIDIO():
    """La inversión que importa: en vez de tapar lo que se conoce, se copia sólo
    lo que se pidió. Lo que el proveedor agregue mañana no entra solo."""
    cuerpo = {"type": "payment", "id": "123",
              "payer": {"email": "quien@proveedor.test", "name": "Juan Pérez"},
              "card": {"number": "4111111111111111"}}
    salida = registro.resumen(cuerpo, ["type", "id"])
    assert "type=payment" in salida and "id=123" in salida
    assert "quien@proveedor.test" not in salida
    assert "Juan" not in salida
    assert "4111" not in salida


def test_una_clave_pedida_que_trae_un_objeto_no_se_vuelca():
    """Pedir `payer` no puede significar volcar todo lo que haya adentro."""
    salida = registro.resumen({"payer": {"email": "x@y.test"}}, ["payer"])
    assert "x@y.test" not in salida
    assert "dict" in salida


def test_un_valor_larguisimo_se_corta():
    salida = registro.resumen({"nota": "x" * 5000}, ["nota"])
    assert len(salida) < 500


@pytest.mark.parametrize("basura", [None, "texto", 42, [1, 2, 3]])
def test_si_el_cuerpo_no_es_un_diccionario_no_se_cae(basura):
    assert isinstance(registro.resumen(basura, ["x"]), str)


# ══════════════════════════════════════════════════════════════════════════
# 3. Tapar un documento entero conservando su forma
# ══════════════════════════════════════════════════════════════════════════

def test_LA_LINEA_DE_AUDITORIA_SE_REGISTRA_SIN_SU_CONTENIDO():
    """Se conserva la FORMA —que es lo que sirve para entender por qué falló— y
    se tapa el contenido, que no tiene por qué salir de la base."""
    linea = {
        "accion": "kyc.aprobado",
        "actor": {"user_id": "u1", "email": "admin@interno.test", "rol": "super_admin"},
        "objetivo": {"tipo": "usuario", "id": "u2"},
        "antes": {"cpf_image": "data:image/jpeg;base64,AAAA", "estado": "pendiente"},
        "despues": {"estado": "aprobado"},
    }
    limpio = registro.sin_datos(linea)
    texto = str(limpio)

    # La forma sobrevive: se sigue viendo qué acción, sobre quién y qué cambió.
    assert limpio["accion"] == "kyc.aprobado"
    assert limpio["actor"]["user_id"] == "u1"
    assert limpio["antes"]["estado"] == "pendiente"
    assert limpio["despues"]["estado"] == "aprobado"

    # El contenido, no.
    assert "admin@interno.test" not in texto
    assert "base64" not in texto


def test_se_tapa_por_parecido_de_nombre_no_por_lista_exacta():
    """`id_document_image_back` tiene que caer igual que `id_document_image`.
    Una lista de nombres exactos deja pasar el campo siguiente que alguien
    agregue."""
    limpio = registro.sin_datos({
        "id_document_image_back": "x", "selfie_image_url": "y",
        "user_phone_number": "z", "beneficiario_nombre": "w"})
    assert all(v == "(tapado)" for v in limpio.values()), limpio


def test_una_estructura_muy_profunda_no_cuelga():
    hondo = {}
    actual = hondo
    for _ in range(50):
        actual["mas"] = {}
        actual = actual["mas"]
    actual["email"] = "x@y.test"
    texto = str(registro.sin_datos(hondo))
    assert "x@y.test" not in texto


def test_una_lista_larga_no_se_copia_entera():
    limpio = registro.sin_datos({"items": [{"email": f"{i}@y.test"} for i in range(500)]})
    assert len(limpio["items"]) <= 10


def test_un_texto_enorme_se_corta_y_se_dice_cuanto():
    limpio = registro.sin_datos({"nota": "x" * 900})
    assert "(+780)" in limpio["nota"]


# ══════════════════════════════════════════════════════════════════════════
# 4. Que no vuelvan a escribirse datos crudos — acá es donde esto regresa
# ══════════════════════════════════════════════════════════════════════════

# Lo que no puede aparecer INTERPOLADO en un `logger.*`. Se busca en el nombre
# de lo que se interpola, no en el texto fijo: `logger.info("mandando el mail")`
# no filtra nada, `logger.info(f"...{email}")` sí.
CRUDOS = re.compile(
    r"(?<![\w.])("
    # `payload` y `body` SOLOS: el cuerpo entero de un tercero. `payload.estado`
    # no cae acá —es un campo elegido a mano— pero `payload.email` sí, por la
    # regla del correo de abajo.
    r"payload(?!\.)|body(?!\.)|"
    r"\w*\.email|\w*\[.email.\]|\bemail\b|"
    r"\w*\.phone\w*|\bphone_number\b|\btelefono\b|\bcelular\b|"
    r"\bcpf\w*|\bdocument_number\b|\bcedula\b|\w*id_document\w*|"
    r"\bselfie\w*|\bproof_image\b|\bvoucher_image\b|"
    r"\w*password\w*|\w*secret\w*|\w*_token\b|\bapi_key\b|"
    # Un nombre sí; un identificador interno no. `beneficiary_id` es
    # pseudónimo —no dice quién es nadie fuera de nuestra base— y prohibirlo
    # obligaría a enmascarar justo el dato que sirve para investigar.
    r"\bfull_name\b|\bclient_name\b|\bbeneficiar(?!\w*_id\b)\w*"
    r")(?![\w])", re.I)

# Cada excepción es una decisión escrita, no una lista de perdones. Si mañana
# una de estas cambia de contenido, la razón deja de valer.
CRUDOS_ACEPTADOS = {
    # `to_email` es el destinatario que ACABA de fallar; sin él la línea no
    # sirve para nada, y ya va enmascarado por `registro.correo()`.
    ("services/email.py", "correo"),
}


def _es_llamada_a_logger(nodo):
    if not (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)):
        return False
    if nodo.func.attr not in ("info", "debug", "warning", "error",
                              "exception", "critical"):
        return False
    base = nodo.func.value
    return isinstance(base, ast.Name) and base.id in ("logger", "log", "logging")


def _interpolado(nodo, texto):
    """Lo que se mete DENTRO del mensaje: el f-string y los argumentos de %."""
    partes = []
    primero = nodo.args[0]
    if isinstance(primero, ast.JoinedStr):
        partes += [ast.get_source_segment(texto, v.value) or ""
                   for v in primero.values if isinstance(v, ast.FormattedValue)]
    partes += [ast.get_source_segment(texto, a) or "" for a in nodo.args[1:]]
    return " ".join(partes)


def _archivos():
    for carpeta in ("routes", "services", "utils"):
        raiz = os.path.join(_BACKEND, carpeta)
        if not os.path.isdir(raiz):
            continue
        for archivo in sorted(os.listdir(raiz)):
            if archivo.endswith(".py"):
                yield f"{carpeta}/{archivo}", os.path.join(raiz, archivo)


def test_NINGUN_REGISTRO_ESCRIBE_UN_DATO_PERSONAL_CRUDO():
    """El barrido que impide que esto vuelva.

    No enumera los 35 puntos que había: recorre TODOS los `logger.*` y mira qué
    se interpola. Un registro nuevo con un correo adentro lo pone en rojo el día
    que se escribe, y para pasarlo hay que enmascararlo o justificarlo.
    """
    crudos = []
    for rel, ruta in _archivos():
        texto = open(ruta, encoding="utf-8").read()
        try:
            arbol = ast.parse(texto)
        except SyntaxError:                               # pragma: no cover
            continue
        for nodo in ast.walk(arbol):
            if not _es_llamada_a_logger(nodo) or not nodo.args:
                continue
            dentro = _interpolado(nodo, texto)
            if not dentro:
                continue
            # Ya pasó por el enmascarador: es exactamente lo que se pide.
            if "registro." in dentro:
                continue
            m = CRUDOS.search(dentro)
            if not m:
                continue
            if (rel, m.group(0).lower()) in CRUDOS_ACEPTADOS:
                continue
            crudos.append(f"{rel}:{nodo.lineno}  «{m.group(0)}» en: {dentro.strip()[:70]}")

    assert not crudos, (
        "estos registros escriben un dato personal o un cuerpo ajeno sin "
        "enmascarar. Los registros salen de nuestro perímetro y no vuelven.\n"
        "Usá services/registro.py (correo / ultimos / resumen / sin_datos), o "
        "registrá el `user_id`, que no dice nada fuera de la base:\n  "
        + "\n  ".join(crudos))


def test_el_barrido_mira_de_verdad():
    """Si no encuentra ningún `logger.*` con interpolación, pasa sin haber
    mirado nada. Es la forma en que un test de barrido miente."""
    vistos = 0
    for _, ruta in _archivos():
        texto = open(ruta, encoding="utf-8").read()
        try:
            arbol = ast.parse(texto)
        except SyntaxError:                               # pragma: no cover
            continue
        for nodo in ast.walk(arbol):
            if _es_llamada_a_logger(nodo) and nodo.args and _interpolado(nodo, texto):
                vistos += 1
    assert vistos > 150, f"el barrido sólo vio {vistos} registros con interpolación"


def test_los_dos_peores_quedaron_arreglados():
    """Se nombran porque eran los que motivaron todo esto, y porque un barrido
    genérico no cuenta la historia de por qué existe."""
    auditoria = open(os.path.join(_BACKEND, "services", "auditoria.py"),
                     encoding="utf-8").read()
    assert "Línea completa: %s" not in auditoria, \
        "el libro de auditoría vuelve a registrarse entero cuando falla"
    assert "registro.sin_datos" in auditoria

    for archivo in ("routes/gestor_pix.py", "routes/credits.py"):
        fuente = open(os.path.join(_BACKEND, archivo), encoding="utf-8").read()
        assert "registro.resumen" in fuente, f"{archivo} vuelca el cuerpo entero"
