"""
tests/test_soporte_pantalla.py — Las reglas de pantalla de la mesa de ayuda.

POR QUE ESTAN ACA Y NO EN UN TEST DE JAVASCRIPT

    Este repositorio no tiene banco de pruebas de frontend. La lógica vive en
    `frontend/src/utils/soporte.js` —fuera del JSX— y se corre desde acá con
    node, igual que las de enviar a Venezuela, Brasil y el perfil.

QUE SOSTIENEN

    El asesor tiene ocho botones que a veces se pueden usar y a veces no. Esa
    tabla es la parte que se rompe en silencio: un botón que se ofrece cuando
    no corresponde manda al asesor contra un error del servidor; uno que se
    apaga de más le esconde una herramienta que sí tenía.

    Y sostienen que la pantalla ESPEJA al backend: si allá se agrega un estado
    o cambia una transición y acá no, el asesor ve opciones que van a fallar.
"""
import json
import os
from datetime import datetime, timezone
import pathlib
import subprocess

import pytest

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))
_MODULO = _RAIZ / "frontend" / "src" / "utils" / "soporte.js"


def _js(cuerpo):
    if not _MODULO.exists():
        pytest.fail(f"No está {_MODULO.relative_to(_RAIZ)}.")
    guion = f"import * as m from '{_MODULO}';\nconsole.log(JSON.stringify({cuerpo}));"
    r = subprocess.run(["node", "--input-type=module", "-e", guion],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        pytest.fail(f"El módulo no corre:\n{r.stderr[-1500:]}")
    return json.loads(r.stdout.strip())


def _acciones(caso, yo="ana", es_super=False):
    args = json.dumps({"caso": caso, "yo": yo, "esSuperAdmin": es_super})
    return _js(f"m.accionesDelAsesor({args})")


# ══════════════════════════════════════════════════════════════════════════
# La pantalla espeja al backend
# ══════════════════════════════════════════════════════════════════════════

def test_los_estados_son_los_mismos_de_los_dos_lados():
    """Si el backend agrega un estado y la pantalla no, el asesor ve un caso
    en un estado que no sabe nombrar; al revés, ofrece uno que va a fallar."""
    from services import soporte
    assert set(_js("Object.keys(m.ESTADOS)")) == set(soporte.ESTADOS)


def test_las_transiciones_son_las_mismas_de_los_dos_lados():
    from services import soporte
    for desde in soporte.ESTADOS:
        de_la_pantalla = set(_js(f"m.estadosPosibles({json.dumps(desde)})"))
        del_servidor = set(soporte.TRANSICIONES.get(desde, ()))
        assert de_la_pantalla == del_servidor, (
            f"Desde «{desde}» la pantalla ofrece {de_la_pantalla} y el servidor "
            f"acepta {del_servidor}.")


def test_cuando_se_da_por_terminado_es_lo_mismo_de_los_dos_lados():
    """La lista que habilita la calificación tiene que ser LA MISMA.

    Si acá sobrara un estado, la pantalla ofrece calificar y el servidor
    rechaza; si faltara, la atención termina sin ningún lugar donde opinar.
    """
    from services import soporte
    assert set(_js("m.TERMINADOS")) == set(soporte.TERMINADOS)


def test_la_espera_del_cliente_se_calcula_igual_de_los_dos_lados():
    """Es el dato que decide el orden de la bandeja y el que se muestra.

    Si la pantalla lo calculara distinto, el asesor vería una fila con «espera
    hace 5 min» arriba de otra con «espera hace 3 h» y el orden parecería
    arbitrario, que es peor que no mostrar nada.
    """
    from services import soporte
    ahora = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    milis = int(ahora.timestamp() * 1000)

    def _cuando(hora, minuto=0):
        return datetime(2026, 3, 1, hora, minuto, tzinfo=timezone.utc)

    casos = [
        # La pelota la tiene la casa: el cliente escribió hace 90 minutos.
        {"estado": "en_curso", "ultimo_mensaje_de": "cliente",
         "ultimo_mensaje_en": _cuando(10, 30)},
        # Ya contestamos: no hay espera que contar.
        {"estado": "en_curso", "ultimo_mensaje_de": "asesor",
         "ultimo_mensaje_en": _cuando(4)},
        # Cerrado: tampoco.
        {"estado": "cerrado", "ultimo_mensaje_de": "cliente",
         "ultimo_mensaje_en": _cuando(4)},
        # Sin fecha de último mensaje, se cuenta desde que se abrió.
        {"estado": "abierto", "ultimo_mensaje_de": "cliente",
         "ultimo_mensaje_en": None, "creado_en": _cuando(11, 45)},
        # Una fecha que no se entiende no puede romper la lista.
        {"estado": "abierto", "ultimo_mensaje_de": "cliente",
         "ultimo_mensaje_en": "no es una fecha"},
    ]

    def _para_js(caso):
        return {k: (v.isoformat() if isinstance(v, datetime) else v)
                for k, v in caso.items()}

    for caso in casos:
        de_la_pantalla = _js(f"m.minutosSinRespuesta({json.dumps(_para_js(caso))}, {milis})")
        del_servidor = soporte.minutos_sin_respuesta(dict(caso), ahora)
        assert de_la_pantalla == del_servidor, caso

    # Y el primero da lo que tiene que dar, no sólo «lo mismo de los dos lados».
    assert soporte.minutos_sin_respuesta(dict(casos[0]), ahora) == 90


def test_los_compromisos_de_tiempo_son_los_mismos():
    from services import soporte
    assert _js("m.COMPROMISO_MINUTOS") == soporte.COMPROMISO_MINUTOS


def test_el_cliente_y_el_asesor_no_leen_lo_mismo():
    """«Esperando al cliente» para el equipo es «te respondimos» para él.

    Decirle a un cliente que su caso está «esperando cliente» lo deja sin
    saber qué se espera de él.
    """
    assert _js("m.nombreDeEstado('esperando_cliente', 'asesor')") == 'Esperando al cliente'
    assert _js("m.nombreDeEstado('esperando_cliente', 'cliente')") == 'Te respondimos'


# ══════════════════════════════════════════════════════════════════════════
# Los botones del asesor
# ══════════════════════════════════════════════════════════════════════════

def test_sin_tomar_el_caso_no_se_le_responde_al_cliente():
    """Y el botón dice por qué está apagado, no queda gris y mudo."""
    acciones = _acciones({"estado": "abierto", "asignado_a": None})
    assert acciones["responder"]["puede"] is False
    assert "tomá" in acciones["responder"]["porque"].lower()
    assert acciones["tomar"]["puede"] is True


def test_no_se_le_responde_al_cliente_en_el_caso_de_otro():
    """Dos asesores contestando lo mismo le dan al cliente dos versiones."""
    caso = {"estado": "en_curso", "asignado_a": "beto", "asignado_a_nombre": "Beto"}
    acciones = _acciones(caso, yo="ana")
    assert acciones["responder"]["puede"] is False
    assert "Beto" in acciones["responder"]["porque"]


def test_la_nota_interna_se_puede_dejar_en_un_caso_ajeno():
    """Es contexto para el equipo, no una respuesta al cliente.

    Lo que se protege es que al cliente le hable una sola persona, no que
    nadie más pueda aportar lo que sabe.
    """
    caso = {"estado": "en_curso", "asignado_a": "beto", "asignado_a_nombre": "Beto"}
    acciones = _acciones(caso, yo="ana")
    assert acciones["notaInterna"]["puede"] is True
    assert acciones["responder"]["puede"] is False


def test_el_super_administrador_destraba():
    caso = {"estado": "en_curso", "asignado_a": "beto", "asignado_a_nombre": "Beto"}
    acciones = _acciones(caso, yo="jefe", es_super=True)
    assert acciones["responder"]["puede"] is True
    assert acciones["soltar"]["puede"] is True


def test_en_un_caso_cerrado_no_se_puede_nada():
    """Y cada botón lo dice, en vez de dejar ocho grises sin explicación."""
    acciones = _acciones({"estado": "cerrado", "asignado_a": "ana"})
    for nombre, accion in acciones.items():
        assert accion["puede"] is False, f"«{nombre}» seguía disponible en un caso cerrado."
        assert accion["porque"], f"«{nombre}» está apagado y no dice por qué."


def test_un_caso_ya_escalado_no_se_escala_dos_veces():
    caso = {"estado": "en_curso", "asignado_a": "ana", "escalado": True}
    acciones = _acciones(caso)
    assert acciones["escalar"]["puede"] is False
    assert "escalado" in acciones["escalar"]["porque"].lower()


def test_lo_que_esta_apagado_siempre_dice_por_que():
    """Un botón gris sin motivo es una pared. Ya pasó en el perfil."""
    for caso in ({"estado": "abierto", "asignado_a": None},
                 {"estado": "en_curso", "asignado_a": "beto", "asignado_a_nombre": "Beto"},
                 {"estado": "cerrado", "asignado_a": "ana"}):
        for nombre, accion in _acciones(caso).items():
            if not accion["puede"]:
                assert accion["porque"], (
                    f"«{nombre}» apagado y sin motivo, con el caso {caso}.")


# ══════════════════════════════════════════════════════════════════════════
# El semáforo
# ══════════════════════════════════════════════════════════════════════════

def test_el_semaforo_de_la_pantalla_da_lo_mismo_que_el_del_servidor():
    """Se recalcula en el navegador para que un caso se ponga en rojo solo,
    sin esperar al próximo refresco. Tiene que dar lo mismo."""
    creado = "2026-09-05T12:00:00.000Z"
    ahora = "2026-09-05T13:01:00.000Z"  # 61 minutos
    caso = json.dumps({"creado_en": creado, "prioridad": "alta",
                       "primera_respuesta_en": None, "estado": "abierto"})
    assert _js(f"m.semaforo({caso}, Date.parse('{ahora}'))") == "rojo"
    ahora_medio = "2026-09-05T12:35:00.000Z"
    assert _js(f"m.semaforo({caso}, Date.parse('{ahora_medio}'))") == "amarillo"


def test_el_semaforo_se_apaga_cuando_ya_se_respondio():
    caso = json.dumps({"creado_en": "2026-09-05T12:00:00.000Z", "prioridad": "alta",
                       "primera_respuesta_en": "2026-09-05T12:05:00.000Z",
                       "estado": "en_curso"})
    assert _js(f"m.semaforo({caso}, Date.parse('2026-09-08T12:00:00.000Z'))") is None


def test_una_fecha_que_no_se_entiende_no_rompe_la_lista():
    caso = json.dumps({"creado_en": "no es una fecha", "estado": "abierto"})
    assert _js(f"m.semaforo({caso})") is None


# ══════════════════════════════════════════════════════════════════════════
# Lo que escribe el asesor antes de mover el caso
# ══════════════════════════════════════════════════════════════════════════

def test_una_transferencia_sin_nota_no_sale():
    """Es el momento en que el contexto está en la cabeza de alguien.

    Si no se escribe ahí, se pierde, y el que recibe lee toda la conversación
    para adivinar qué se espera de él mientras el cliente espera.
    """
    assert _js("m.problemaDeLaTransferencia({ area: 'finanzas', nota: '' })")
    assert _js("m.problemaDeLaTransferencia({ area: '', nota: 'ya revisé el saldo' })")
    assert _js("m.problemaDeLaTransferencia({ area: 'finanzas', nota: 'ya revisé el saldo y no cuadra' })") is None


def test_un_pedido_sin_detalle_no_sale():
    assert _js("m.problemaDelPedido({ area: 'verificaciones', detalle: 'vean' })")
    assert _js("m.problemaDelPedido({ area: 'verificaciones', detalle: 'subió el DNI ayer y sigue pendiente' })") is None


def test_un_escalamiento_sin_motivo_no_sale():
    assert _js("m.problemaDelEscalamiento('')")
    assert _js("m.problemaDelEscalamiento('el cliente reclama una operación de hace 20 días')") is None


# ══════════════════════════════════════════════════════════════════════════
# El lado del cliente
# ══════════════════════════════════════════════════════════════════════════

def test_al_cliente_se_le_pide_motivo_y_texto():
    assert _js("m.problemaParaAbrirCaso({ motivo: '', mensaje: 'hola' })")
    assert _js("m.problemaParaAbrirCaso({ motivo: 'envio', mensaje: '  ' })")
    assert _js("m.problemaParaAbrirCaso({ motivo: 'envio', mensaje: 'no llegó' })") is None


def test_el_cliente_califica_un_caso_resuelto_sin_esperar_al_cierre():
    """La pantalla espeja a `TERMINADOS` del backend.

    Si acá pidiera «cerrado» y allá aceptara «resuelto», el cliente vería una
    atención terminada sin ningún lugar donde opinar, que es justo el caso más
    común: al asesor se le pide dejarlo en «resuelto».
    """
    assert _js("m.sePuedeCalificar({estado: 'resuelto'})") is True
    assert _js("m.sePuedeCalificar({estado: 'cerrado'})") is True
    assert _js("m.sePuedeCalificar({estado: 'en_curso'})") is False
    assert _js("m.sePuedeCalificar({estado: 'resuelto', calificacion: {estrellas: 3}})") is False


def test_el_cliente_puede_dar_por_terminada_su_consulta_hasta_que_este_cerrada():
    for estado in ("abierto", "en_curso", "esperando_cliente", "resuelto"):
        assert _js(f"m.sePuedeCerrarPorElCliente({{estado: '{estado}'}})") is True, estado
    assert _js("m.sePuedeCerrarPorElCliente({estado: 'cerrado'})") is False
    assert _js("m.sePuedeCerrarPorElCliente(null)") is False


def test_en_un_caso_cerrado_el_cliente_no_escribe_pero_califica():
    """Es lo que mantiene cada consulta con su historia.

    En el chat viejo el cliente escribía y reabría un hilo de hace tres meses.
    """
    cerrado = json.dumps({"estado": "cerrado", "calificacion": None})
    assert _js(f"m.sePuedeEscribir({cerrado})") is False
    assert _js(f"m.sePuedeCalificar({cerrado})") is True

    abierto = json.dumps({"estado": "en_curso", "calificacion": None})
    assert _js(f"m.sePuedeEscribir({abierto})") is True
    assert _js(f"m.sePuedeCalificar({abierto})") is False


def test_no_se_califica_dos_veces_el_mismo_caso():
    ya = json.dumps({"estado": "cerrado", "calificacion": {"estrellas": 4}})
    assert _js(f"m.sePuedeCalificar({ya})") is False


# ══════════════════════════════════════════════════════════════════════════
# Los pedidos que llegan a mi área
# ══════════════════════════════════════════════════════════════════════════

def test_un_pedido_no_se_contesta_con_un_visto():
    """La respuesta vuelve al caso como nota interna y alguien la va a leer.

    Un «ok» no le sirve al asesor que está con el cliente: después tiene que
    traducirle esa respuesta, y para eso necesita saber QUE pasó.
    """
    assert _js("m.problemaDeLaRespuestaAlPedido('')")
    assert _js("m.problemaDeLaRespuestaAlPedido('   ')")
    assert _js("m.problemaDeLaRespuestaAlPedido('ok')")
    assert _js("m.problemaDeLaRespuestaAlPedido('Le devolvimos el saldo, ya está acreditado')") is None


def test_una_respuesta_larguisima_se_frena_de_este_lado():
    """El servidor la corta en 2000; enterarse recién ahí es perder lo escrito."""
    assert _js("m.problemaDeLaRespuestaAlPedido('x'.repeat(2001))")
    assert _js("m.problemaDeLaRespuestaAlPedido('x'.repeat(2000))") is None
