"""
tests/test_sin_socios_ni_gestores.py — Que el área eliminada no vuelva sola.

QUE SE ELIMINO

    Había dos roles con pantalla propia: `socio`, que refería usuarios y
    cobraba comisiones, y `socio_gestor`, que procesaba envíos de terceros y
    guardaba plata de sus clientes en un saldo aparte.

    Los dos se fueron. Ahora cada usuario recibe su código de referido al
    registrarse —eso ya pasaba para todos— y no hay rol, ni panel, ni tabla de
    ganancias.

    De paso se fue código que NUNCA CORRIO: `services/referrals.py` calculaba
    el bono de referido y no lo llamaba ningún lugar de la aplicación. Había un
    archivo de tests entero verificando una función muerta. Y adentro tenía un
    defecto anotado en `services/kyc_quota.py`: buscaba las recargas con estado
    `completed` cuando el valor real es `approved`, así que su contador daba
    cero siempre.

LA GUARDA QUE MAS IMPORTA NO ES LA DE ARRIBA

    Es `test_la_recarga_por_pix_de_todos_sigue_en_pie`.

    El archivo `routes/gestor_pix.py` se llama así pero NO es de los gestores:
    ahí vive la recarga por PIX de todos los usuarios y el webhook de Mercado
    Pago por donde se acreditan los pagos con PIX y con tarjeta. Borrarlo por
    el nombre —que es lo que invita a hacer— deja a la aplicación sin cobros.

    Este test existe para que quien lea «gestor» en el nombre y vaya a
    borrarlo, se encuentre con un rojo que se lo explica.
"""
import ast
import os
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(_BACKEND))

# Los nombres que no pueden volver. Se buscan como CADENAS, que es como se
# escriben los roles en este proyecto.
ROLES_MUERTOS = ("socio", "socio_gestor")

# Dónde se busca. Los tests quedan afuera a propósito: `test_borrado_total`
# usa un usuario con rol `socio_gestor` como dato de prueba, para comprobar
# que el borrado total sigue limpiando el saldo de terceros de una cuenta
# vieja. Eso tiene que seguir ahí.
CARPETAS = ("routes", "services", "models")


def archivos_de_produccion():
    for carpeta in CARPETAS:
        for ruta in sorted((_BACKEND / carpeta).rglob("*.py")):
            if "__pycache__" in ruta.parts:
                continue
            yield ruta


def cadenas_de(ruta: pathlib.Path):
    """Las cadenas literales del archivo, sin comentarios ni docstrings.

    Se lee el ARBOL y no el texto: los comentarios que EXPLICAN que el área se
    eliminó nombran los roles, naturalmente, y con una búsqueda de texto esos
    comentarios pondrían la guarda en rojo contra el código correcto.
    """
    arbol = ast.parse(ruta.read_text(), filename=str(ruta))
    docstrings = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(nodo, clean=False)
            if doc:
                docstrings.add(doc)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            if nodo.value not in docstrings:
                yield nodo.lineno, nodo.value


def test_ningun_rol_de_socio_quedo_vivo_en_el_codigo():
    culpables = []
    for ruta in archivos_de_produccion():
        for linea, texto in cadenas_de(ruta):
            if texto in ROLES_MUERTOS:
                culpables.append(f"{ruta.relative_to(_BACKEND)}:{linea}")
    assert culpables == [], (
        "Volvió un rol de socio. Se eliminaron los dos: " + ", ".join(culpables))


def test_esta_guarda_distingue_el_rol_del_comentario_que_lo_explica():
    """La guarda de la guarda.

    Tiene que ver el rol usado de verdad y NO verlo cuando sólo se lo nombra
    en el texto que explica por qué se fue.
    """
    import tempfile
    vivo = 'if user["role"] == "socio":\n    pass\n'
    explicado = '"""El rol socio se eliminó, y socio_gestor también."""\n'

    with tempfile.TemporaryDirectory() as d:
        a = pathlib.Path(d) / "vivo.py"; a.write_text(vivo)
        b = pathlib.Path(d) / "explicado.py"; b.write_text(explicado)
        assert any(t in ROLES_MUERTOS for _, t in cadenas_de(a))
        assert not any(t in ROLES_MUERTOS for _, t in cadenas_de(b))


def hay_ruta(sufijo: str) -> bool:
    """Si existe una ruta que termina así.

    Por el sufijo y no por el camino entero: el router va montado bajo `/api`,
    y escribir el prefijo en cada test lo ata a una decisión de montaje que no
    es lo que se quiere probar.
    """
    from routes import api_router
    return any(r.path.endswith(sufijo) for r in api_router.routes)


def test_no_quedan_modulos_ni_rutas_del_area_borrada():
    for nombre in ("routes/partner.py", "routes/gestor.py",
                   "services/referrals.py"):
        assert not (_BACKEND / nombre).exists(), f"volvió {nombre}"

    for muerta in ("/partner/dashboard", "/partner/referral-link",
                   "/gestor/dashboard", "/gestor/process-transaction",
                   "/admin/partners", "/admin/gestors"):
        assert not hay_ruta(muerta), f"volvió la ruta {muerta}"


def test_la_recarga_por_pix_de_todos_sigue_en_pie():
    """EL ARCHIVO SE LLAMA `gestor_pix` Y NO ES DE LOS GESTORES.

    Ahí vive la recarga por PIX de todos los usuarios y el webhook de Mercado
    Pago. Si alguien lo borra por el nombre, nadie puede recargar ni le entra
    un pago. Este rojo es para evitarlo.
    """
    assert (_BACKEND / "routes" / "gestor_pix.py").exists(), (
        "Se borró routes/gestor_pix.py. NO es de los gestores: es la recarga "
        "por PIX de todos los usuarios y el webhook de Mercado Pago.")

    for viva in ("/gestor/pix/create", "/gestor/pix/pending",
                 "/gestor/pix/status/{payment_id}", "/webhook/mercadopago"):
        assert hay_ruta(viva), f"se perdió {viva}, que la usa todo el mundo"


def test_cada_usuario_tiene_su_ruta_para_el_codigo_de_referido():
    """Lo único que se conserva del área: el código, ahora para todos y sin
    rol de por medio."""
    assert hay_ruta("/referidos/mi-codigo")
