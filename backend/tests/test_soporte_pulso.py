"""
tests/test_soporte_pulso.py — Lo que las pantallas de soporte hacen y no se
puede probar con node: cómo preguntan y qué llegan a mostrar.

LOS DEFECTOS QUE ESTE ARCHIVO SOSTIENE CERRADOS

    1. La bandeja del asesor no se refrescaba sola. El reloj que la volvía a
       pedir vivía DENTRO del efecto del caso elegido, así que el asesor que
       miraba la lista sin abrir ningún caso no veía entrar uno nuevo hasta
       que abría alguno o recargaba la pantalla. Es la pantalla principal de
       la mesa de ayuda y el defecto no se ve: la lista simplemente no cambia.

    2. Se preguntaba con la pestaña oculta. Cada asesor con la mesa abierta en
       una solapa que no mira le pegaba al servidor cada seis segundos todo el
       día, y son muchos asesores.

    Las dos cosas las resuelve `frontend/src/hooks/usePulso.js`, y las dos se
    vuelven a romper con un retoque distraído en los efectos. Por eso se miran
    desde acá y no de memoria.
"""
import os
import pathlib
import re

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))
_FUENTE = _RAIZ / "frontend" / "src"
_PULSO = _FUENTE / "hooks" / "usePulso.js"

# Las dos pantallas que preguntan cada tanto: la del asesor y la del cliente
# —que es la misma pieza en el botón flotante y en la sección de Soporte—.
_PANTALLAS = (
    _FUENTE / "components" / "admin" / "MesaDeAyuda.jsx",
    _FUENTE / "components" / "soporte" / "CasosDelCliente.jsx",
)

_BLOQUE = re.compile(r"/\*.*?\*/", re.S)
_LINEA = re.compile(r"(?<![:\w])//[^\n]*")


def _sin_comentarios(ruta):
    """El código, sin los comentarios.

    Los archivos que arreglaron esto EXPLICAN el defecto en su encabezado y
    nombran `setInterval` para hacerlo: un test que buscara la cadena a secas
    fallaría por la documentación del propio arreglo.
    """
    return _LINEA.sub("", _BLOQUE.sub("", ruta.read_text(encoding="utf-8")))


def test_el_pulso_no_pregunta_con_la_pestana_oculta():
    codigo = _sin_comentarios(_PULSO)
    assert "document.hidden" in codigo, (
        "usePulso tiene que dejar de preguntar cuando nadie mira la pestaña")
    assert "visibilitychange" in codigo, (
        "y tiene que volver a preguntar EN EL ACTO al volver a la pestaña; "
        "si no, se siente colgada hasta el próximo ciclo")


def test_las_pantallas_de_soporte_no_arman_su_propio_reloj():
    """Ningún `setInterval` suelto: si no, se pierden las dos protecciones."""
    culpables = []
    for ruta in _PANTALLAS:
        if "setInterval" in _sin_comentarios(ruta):
            culpables.append(ruta.relative_to(_RAIZ).as_posix())
    assert not culpables, (
        "estas pantallas arman su propio reloj en vez de usar `usePulso`, así "
        "que vuelven a preguntar con la pestaña oculta: " + ", ".join(culpables))


def test_la_bandeja_del_asesor_se_refresca_sin_caso_abierto():
    """El pulso de la lista no puede depender de que haya un caso elegido."""
    codigo = _sin_comentarios(_PANTALLAS[0])
    pulsos = re.findall(r"usePulso\(([^\n]*)\)", codigo)
    de_la_lista = [p for p in pulsos if "traerCasos" in p]
    assert de_la_lista, "la bandeja no tiene su propio pulso"
    for p in de_la_lista:
        assert "elegido" not in p, (
            "el pulso de la bandeja mira el caso elegido: sin ninguno abierto "
            "se apaga, y el asesor deja de ver entrar los casos nuevos")


def test_cada_pantalla_descarta_las_respuestas_viejas():
    """Saltar de un caso a otro no puede dejar la conversación del anterior.

    Es el peor error posible acá porque no se nota: el asesor lee la charla de
    un cliente bajo el nombre de otro y le contesta cualquier cosa.
    """
    for ruta in _PANTALLAS:
        codigo = _sin_comentarios(ruta)
        assert re.search(r"turno\.current\s*\+=\s*1", codigo), (
            f"{ruta.name} no numera sus pedidos: la respuesta lenta de un caso "
            "puede pisar la del caso que el usuario ya abrió después")
        # Numerarlos y no mirar el número sería lo mismo que no numerarlos.
        assert re.search(r"if\s*\(\s*turno\.current\s*===\s*mio\s*\)\s*setDetalle",
                         codigo), (
            f"{ruta.name} numera los pedidos pero guarda la respuesta igual: "
            "el número tiene que decidir si se guarda o se tira")


def test_los_pedidos_a_mi_area_tienen_donde_contestarse():
    """El circuito del pedido tiene dos puntas y las dos tienen que existir.

    El asesor puede pedirle algo a Finanzas o a Verificaciones sin soltar el
    caso. Del otro lado, el pedido llegaba como un aviso y nada más: quien
    tenía que contestarlo no tenía dónde. La ruta estaba, la pantalla no, y
    eso no se ve mirando el backend: los tests del circuito pasaban enteros
    mientras el encargado del área no podía hacer nada.
    """
    codigo = _sin_comentarios(_PANTALLAS[0])
    assert "/admin/soporte/pedidos" in codigo, (
        "la consola no pide los pedidos de su área: el encargado no se entera")
    assert re.search(r"/admin/soporte/pedidos/\$\{[^}]+\}/responder", codigo), (
        "la consola muestra los pedidos pero no los contesta: el circuito "
        "queda abierto y el cliente esperando algo que nadie puede cerrar")
