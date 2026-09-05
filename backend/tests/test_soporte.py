"""
tests/test_soporte.py — Las reglas de la mesa de ayuda.

QUE SOSTIENEN

    El modelo viejo era UN chat por usuario, para siempre. Estos tests fijan
    lo que el modelo de casos tiene que cumplir para que eso no vuelva:

      · Un caso cerrado se queda cerrado. Para hablar de otra cosa se abre uno
        nuevo, que es exactamente lo que el chat único no permitía.
      · Un caso resuelto se REABRE si el cliente escribe. Es la diferencia
        entre «resuelto» y «cerrado», y sin ella el asesor no puede dar por
        terminado sin arriesgarse a dejar a alguien sin respuesta.
      · Al cliente le contesta uno solo: el que tomó el caso.
      · Un pedido a otra área lo contesta quien puede resolverlo, no cualquiera.
      · La bandeja se ordena por lo que hay que hacer primero, no por lo más
        reciente.
"""
from datetime import datetime, timedelta, timezone

import pytest

from services import soporte


AHORA = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def _caso(**campos):
    base = {
        "caso_id": "caso_1",
        "estado": soporte.ABIERTO,
        "prioridad": "normal",
        "asignado_a": None,
        "creado_en": AHORA,
        "primera_respuesta_en": None,
        "escalado": False,
    }
    base.update(campos)
    return base


# ══════════════════════════════════════════════════════════════════════════
# Los estados
# ══════════════════════════════════════════════════════════════════════════

def test_un_caso_cerrado_no_vuelve():
    """Cerrado es el final, y es a propósito.

    En el chat viejo el cliente escribía y el hilo se reabría encima de una
    consulta de hace tres meses. Acá, para hablar de otra cosa se abre un caso
    nuevo: así el historial de cada consulta queda entero y separado.
    """
    for destino in soporte.ESTADOS:
        assert not soporte.puede_pasar(soporte.CERRADO, destino), (
            f"Se pudo pasar de cerrado a {destino}.")


def test_un_caso_resuelto_se_puede_reabrir():
    """Si no se pudiera, «resuelto» sería «cerrado» con otro nombre.

    El asesor tiene que poder dar por terminado sin miedo: si el cliente no
    quedó conforme, vuelve al mismo caso en vez de empezar de cero.
    """
    assert soporte.puede_pasar(soporte.RESUELTO, soporte.EN_CURSO)


@pytest.mark.parametrize("desde, hasta", [
    (soporte.ABIERTO, soporte.EN_CURSO),
    (soporte.EN_CURSO, soporte.ESPERANDO_CLIENTE),
    (soporte.ESPERANDO_CLIENTE, soporte.EN_CURSO),
    (soporte.EN_CURSO, soporte.CERRADO),
])
def test_las_transiciones_del_dia_a_dia_estan_permitidas(desde, hasta):
    assert soporte.puede_pasar(desde, hasta)


def test_un_estado_no_pasa_a_si_mismo():
    """Tomar dos veces el mismo caso no puede contar como un cambio.

    Si contara, cada doble clic dejaría una línea en la historia del caso y el
    asesor que la lee después no distinguiría lo que pasó de lo que se repitió.
    """
    for estado in soporte.ESTADOS:
        assert not soporte.puede_pasar(estado, estado)


# ══════════════════════════════════════════════════════════════════════════
# Quién contesta
# ══════════════════════════════════════════════════════════════════════════

def test_al_cliente_le_contesta_el_que_tomo_el_caso():
    """Dos asesores respondiendo lo mismo es peor que uno tardando un poco.

    El cliente recibe dos versiones y no sabe cuál vale.
    """
    caso = _caso(estado=soporte.EN_CURSO, asignado_a="ana",
                 asignado_a_nombre="Ana")
    assert soporte.problema_para_responder(caso, "ana") is None
    problema = soporte.problema_para_responder(caso, "beto")
    assert problema and "Ana" in problema


def test_el_super_administrador_puede_destrabar():
    caso = _caso(estado=soporte.EN_CURSO, asignado_a="ana", asignado_a_nombre="Ana")
    assert soporte.problema_para_responder(caso, "jefe", es_super_admin=True) is None


def test_hay_que_tomar_el_caso_antes_de_responder():
    """Sin dueño, nadie es responsable de que la respuesta salga."""
    problema = soporte.problema_para_responder(_caso(), "ana")
    assert problema and "tomá" in problema.lower()


def test_no_se_responde_un_caso_cerrado():
    caso = _caso(estado=soporte.CERRADO, asignado_a="ana")
    assert soporte.problema_para_responder(caso, "ana") is not None


# ══════════════════════════════════════════════════════════════════════════
# La calificación
# ══════════════════════════════════════════════════════════════════════════

def test_se_califica_cada_caso_y_una_sola_vez():
    """Antes la calificación colgaba del USUARIO.

    Se calificaba una vez en la vida y todas las consultas siguientes quedaban
    sin medir, porque la marca quedaba puesta en el único documento que había.
    """
    cerrado = _caso(estado=soporte.CERRADO)
    assert soporte.problema_para_calificar(cerrado) is None

    ya = _caso(estado=soporte.CERRADO, calificacion={"estrellas": 5})
    assert soporte.problema_para_calificar(ya) is not None


def test_no_se_califica_un_caso_todavia_abierto():
    problema = soporte.problema_para_calificar(_caso(estado=soporte.EN_CURSO))
    assert problema and "cerrado" in problema.lower()


# ══════════════════════════════════════════════════════════════════════════
# El semáforo y el orden de la bandeja
# ══════════════════════════════════════════════════════════════════════════

def test_el_semaforo_avisa_antes_de_que_sea_tarde():
    """Amarillo a la mitad del compromiso, no cuando ya se pasó.

    Un semáforo que sólo se enciende cuando el plazo venció no evita nada:
    informa de un incumplimiento en vez de prevenirlo.
    """
    caso = _caso(prioridad="alta")  # 60 minutos de compromiso
    assert soporte.semaforo(caso, AHORA + timedelta(minutes=10)) == "verde"
    assert soporte.semaforo(caso, AHORA + timedelta(minutes=35)) == "amarillo"
    assert soporte.semaforo(caso, AHORA + timedelta(minutes=61)) == "rojo"


def test_el_semaforo_se_apaga_cuando_ya_se_respondio():
    """Mide lo que falta contestar, no lo que tarda un caso en resolverse.

    Un caso complejo puede llevar días sin que nadie haya hecho nada mal.
    """
    caso = _caso(primera_respuesta_en=AHORA)
    assert soporte.semaforo(caso, AHORA + timedelta(days=3)) is None
    assert soporte.minutos_esperando(caso, AHORA + timedelta(days=3)) is None


def test_una_fecha_sin_zona_no_rompe_la_lista():
    """Mongo devuelve fechas sin zona horaria.

    Compararlas con una que sí la tiene lanza TypeError, y eso tiraría abajo
    la bandeja entera por un documento viejo.
    """
    caso = _caso(creado_en=datetime(2026, 9, 5, 12, 0))
    assert soporte.minutos_esperando(caso, AHORA + timedelta(minutes=30)) == 30


def test_la_bandeja_pone_primero_lo_que_hay_que_hacer_ahora():
    """El orden ES la herramienta.

    Un asesor que entra a trabajar tiene que ver arriba lo urgente, no lo más
    reciente. Manda el escalamiento, después lo que nadie tomó, después la
    prioridad.
    """
    escalado = _caso(caso_id="escalado", escalado=True, estado=soporte.EN_CURSO,
                     prioridad="baja")
    sin_tomar = _caso(caso_id="sin_tomar", estado=soporte.ABIERTO, prioridad="normal")
    urgente_en_curso = _caso(caso_id="urgente", estado=soporte.EN_CURSO,
                             prioridad="urgente")
    resuelto = _caso(caso_id="resuelto", estado=soporte.RESUELTO, prioridad="urgente")

    orden = [c["caso_id"] for c in sorted(
        [resuelto, urgente_en_curso, sin_tomar, escalado],
        key=lambda c: soporte.clave_de_orden(c, AHORA))]
    assert orden == ["escalado", "sin_tomar", "urgente", "resuelto"]


# ══════════════════════════════════════════════════════════════════════════
# Los pedidos a otra área
# ══════════════════════════════════════════════════════════════════════════

def test_un_pedido_sin_detalle_es_una_interrupcion():
    """«Miren esto» obliga a la otra área a volver a preguntar.

    Y mientras tanto el cliente espera.
    """
    assert soporte.problema_para_pedir("verificaciones", "revisen") is not None
    assert soporte.problema_para_pedir(
        "verificaciones", "El cliente dice que subió el DNI ayer y sigue pendiente") is None


def test_un_pedido_va_a_un_area_de_la_lista():
    assert soporte.problema_para_pedir("inventada", "un detalle bien largo acá") is not None


def test_el_pedido_lo_contesta_quien_puede_resolverlo():
    """Si no, un asesor de soporte «respondería» un pedido a Finanzas y el caso
    seguiría con una respuesta que nadie con la facultad de darla revisó.
    """
    pedido = {"area": "finanzas", "estado": soporte.PEDIDO_PENDIENTE}
    assert soporte.problema_para_responder_pedido(pedido, ["saldos.ajustar"]) is None

    problema = soporte.problema_para_responder_pedido(pedido, ["support.respond"])
    assert problema and "Finanzas" in problema


def test_el_super_administrador_puede_contestar_cualquier_pedido():
    pedido = {"area": "finanzas", "estado": soporte.PEDIDO_PENDIENTE}
    assert soporte.problema_para_responder_pedido(pedido, [], es_super_admin=True) is None


def test_un_pedido_ya_respondido_no_se_responde_dos_veces():
    pedido = {"area": "finanzas", "estado": soporte.PEDIDO_RESPONDIDO}
    assert soporte.problema_para_responder_pedido(
        pedido, ["saldos.ajustar"]) is not None


# ══════════════════════════════════════════════════════════════════════════
# Las áreas, atadas a los permisos que ya existen
# ══════════════════════════════════════════════════════════════════════════

def test_cada_area_apunta_a_un_permiso_que_existe():
    """No se inventa un organigrama nuevo.

    Un área cuyo permiso no esté en el catálogo no tendría a nadie que pueda
    contestarle: los pedidos entrarían y no los vería nadie.
    """
    from services.permisos import CATALOGO
    for clave, (nombre, permiso) in soporte.AREAS.items():
        assert permiso in CATALOGO, (
            f"El área «{clave}» pide «{permiso}», que no está en el catálogo.")
        assert nombre


def test_cada_motivo_del_cliente_encamina_a_un_area_real():
    for motivo in soporte.MOTIVOS:
        assert soporte.area_valida(soporte.area_del_motivo(motivo))


# ══════════════════════════════════════════════════════════════════════════
# El asunto y el número
# ══════════════════════════════════════════════════════════════════════════

def test_el_asunto_se_arma_solo_y_corta_en_palabra_entera():
    """En un chat nadie escribe un asunto, y un campo que la gente saltea es
    un campo vacío en la lista del asesor."""
    largo = "Quería consultar por el envío que hice ayer a Venezuela y todavía no llegó"
    asunto = soporte.asunto_desde(largo, largo=40)
    assert asunto.endswith("…") and len(asunto) <= 41
    assert not asunto[:-1].endswith(" ")
    # No corta una palabra por la mitad.
    assert largo.startswith(asunto[:-1])


def test_un_mensaje_vacio_no_deja_el_asunto_vacio():
    assert soporte.asunto_desde("   ")


def test_el_numero_se_puede_dictar_por_telefono():
    assert soporte.numero_legible(123) == "S-000123"
    assert soporte.numero_legible(1) == "S-000001"
