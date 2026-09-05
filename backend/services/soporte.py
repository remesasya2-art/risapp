"""
services/soporte.py — Las reglas de la mesa de ayuda.

QUE HABIA ANTES, Y POR QUE NO ALCANZABA

    Un solo chat por usuario, para siempre. `support_chats` tenía UN documento
    por persona, con `status` y `last_message`. Eso quiere decir:

      · Una consulta de septiembre sobre un envío y otra de noviembre sobre el
        KYC eran la MISMA conversación. Cerrar la primera cerraba el hilo, y
        cuando el cliente volvía a escribir se reabría encima de lo viejo.
      · El asesor que entraba a un caso leía todo el historial de la persona
        mezclado, sin saber dónde empezaba lo que tenía que resolver.
      · No se podía medir nada por consulta: ni cuánto tardó la primera
        respuesta, ni cuántas veces volvió el mismo problema.
      · La calificación era del USUARIO, no del caso: se calificaba una vez y
        nunca más, porque `rated` quedaba puesto en el único documento.
      · No había forma de pasarle un caso a otro asesor con contexto, de
        pedirle algo a otra área, ni de escribir una nota que el cliente no
        vea. Sólo «tomar» y «soltar».

    Acá vive el modelo nuevo: un CASO por consulta, con su número, su estado,
    su dueño y su historia. Y las cuatro cosas que un asesor necesita de
    verdad para no quedar solo con el problema: nota interna, transferencia,
    pedido a otra área y escalamiento.

POR QUE UN SERVICIO Y NO TODO EN LAS RUTAS

    Las transiciones de estado son la parte que se rompe en silencio. «Cerrar
    un caso ya cerrado», «transferir uno que no es tuyo», «responder a uno
    resuelto»: si cada ruta decide por su cuenta, cada una decide distinto y
    la que se olvida no avisa. Están todas acá, en funciones que se prueban
    sin base de datos.
"""
import re
import uuid
from datetime import datetime, timezone


# ─── Los estados ──────────────────────────────────────────────────────────
#
# Cinco, y cada uno contesta una pregunta distinta de quien mira la lista:
#
#   abierto            nadie lo tomó todavía  → hay que tomarlo
#   en_curso           alguien lo está atendiendo
#   esperando_cliente  la pelota la tiene el cliente → no cuenta contra el
#                      tiempo de respuesta del equipo
#   resuelto           el asesor cree que terminó, el cliente todavía puede
#                      responder y reabrirlo sin abrir un caso nuevo
#   cerrado            terminado. Sólo desde acá se califica.

ABIERTO = "abierto"
EN_CURSO = "en_curso"
ESPERANDO_CLIENTE = "esperando_cliente"
RESUELTO = "resuelto"
CERRADO = "cerrado"

ESTADOS = (ABIERTO, EN_CURSO, ESPERANDO_CLIENTE, RESUELTO, CERRADO)

# Los que siguen vivos para el equipo. `resuelto` está adentro a propósito: el
# cliente puede volver a escribir y el caso tiene que reaparecer en la lista.
ABIERTOS = (ABIERTO, EN_CURSO, ESPERANDO_CLIENTE, RESUELTO)

# De dónde se puede pasar a dónde. Lo que no está acá, no se puede.
#
# ESTA TABLA DESCRIBE TODO LO QUE EL SISTEMA HACE, no sólo el menú que ve el
# asesor. Es la distinción que se me pasó al escribirla: `tomar`, `soltar`,
# `responder` y `transferir` también mueven el estado, y lo hacían a saltos que
# esta tabla declaraba imposibles. Nadie fallaba —esas rutas no la consultan—,
# pero la tabla mentía: quien la leyera para razonar sobre el ciclo de vida, o
# la pantalla, que arma el menú de estados a partir de ella, sacaba
# conclusiones falsas. Hay un test que recorre las cuatro operaciones y falla
# si alguna vuelve a dejar el caso fuera de acá.
TRANSICIONES = {
    ABIERTO: (EN_CURSO, RESUELTO, CERRADO),
    EN_CURSO: (ESPERANDO_CLIENTE, RESUELTO, CERRADO, ABIERTO),
    # A `abierto` se vuelve soltando el caso o transfiriéndolo a un área sin
    # elegir a nadie: es «devolver a la bandeja», y pasa desde cualquier estado
    # vivo.
    ESPERANDO_CLIENTE: (EN_CURSO, RESUELTO, CERRADO, ABIERTO),
    # Resuelto vuelve a en_curso si el cliente escribe: es la reapertura, y es
    # automática. Nadie tiene que acordarse de hacerla a mano. Y vuelve a
    # esperando_cliente si el asesor le agrega algo después de haberlo dado por
    # resuelto.
    RESUELTO: (EN_CURSO, ESPERANDO_CLIENTE, CERRADO, ABIERTO),
    # Cerrado es el final. Para volver a hablar se abre un caso nuevo, que es
    # justamente lo que el modelo viejo no permitía.
    CERRADO: (),
}


def puede_pasar(desde, hasta):
    """¿Es válido este cambio de estado?"""
    if desde == hasta:
        return False
    return hasta in TRANSICIONES.get(desde, ())


# ─── Las prioridades ──────────────────────────────────────────────────────

PRIORIDADES = ("baja", "normal", "alta", "urgente")

# Minutos que el equipo se da para la PRIMERA respuesta, por prioridad. No es
# una promesa al cliente: es el semáforo de la lista del asesor, para que el
# caso que lleva tres horas sin contestar no quede debajo del que entró recién.
COMPROMISO_MINUTOS = {
    "urgente": 15,
    "alta": 60,
    "normal": 240,
    "baja": 480,
}


# ─── Las áreas ────────────────────────────────────────────────────────────
#
# NO SE INVENTA UN ORGANIGRAMA NUEVO.
#
# Cada área se identifica por el permiso que ya gobierna su trabajo en
# `services/permisos.py`. Así, «quién puede atender un pedido de Verificaciones»
# no es una lista aparte que alguien tiene que mantener sincronizada: es quien
# tiene `kyc.approve`, que es exactamente quien puede resolverlo.
#
# El legajo de RRHH ya guarda `area` como texto libre; se usa para MOSTRAR a
# qué área pertenece cada asesor, no para decidir permisos.

AREAS = {
    "soporte": ("Soporte", "support.respond"),
    "verificaciones": ("Verificaciones (KYC)", "kyc.approve"),
    "recargas": ("Recargas", "recharges.approve"),
    "envios": ("Envíos", "envios.operar"),
    "finanzas": ("Finanzas y saldos", "saldos.ajustar"),
    "configuracion": ("Configuración y tasas", "settings.edit"),
}


def area_valida(clave):
    return clave in AREAS


def nombre_de_area(clave):
    return AREAS.get(clave, (clave or "—", None))[0]


def permiso_de_area(clave):
    return AREAS.get(clave, (None, None))[1]


# ─── Quién es el autor de un mensaje ──────────────────────────────────────

CLIENTE = "cliente"
ASESOR = "asesor"
SISTEMA = "sistema"


# ─── El número del caso ───────────────────────────────────────────────────

def numero_legible(secuencia):
    """`S-000123`. Corto, se dicta por teléfono y se busca.

    El `caso_id` con hexadecimal existe igual, pero nadie le lee un uuid a un
    cliente por teléfono. El número es para las personas.
    """
    return f"S-{int(secuencia):06d}"


def nuevo_id():
    return f"caso_{uuid.uuid4().hex[:12]}"


# ─── El asunto ────────────────────────────────────────────────────────────

_ESPACIOS = re.compile(r"\s+")


def asunto_desde(texto, largo=70):
    """El asunto que se arma solo con la primera línea de lo que escribió.

    Se le pide al cliente que elija un motivo, pero no que redacte un asunto:
    en un chat nadie lo hace, y un campo que la gente saltea es un campo que
    después está vacío en la lista del asesor.
    """
    limpio = _ESPACIOS.sub(" ", (texto or "").strip())
    if not limpio:
        return "Consulta sin texto"
    if len(limpio) <= largo:
        return limpio
    # Se corta en la última palabra entera: «Quería consultar por el env…» se
    # lee; «Quería consultar por el envi» parece un error de tipeo.
    recorte = limpio[:largo].rsplit(" ", 1)[0]
    return (recorte or limpio[:largo]) + "…"


# ─── Los motivos que elige el cliente ─────────────────────────────────────
#
# Sirven para dos cosas: encaminar el caso al área correcta desde el primer
# mensaje, y que el asesor sepa qué va a leer antes de abrirlo.

MOTIVOS = {
    "envio": ("Un envío de dinero", "soporte"),
    "recarga": ("Una recarga", "recargas"),
    "verificacion": ("Mi verificación de identidad", "verificaciones"),
    "paquete": ("Un paquete", "envios"),
    "cuenta": ("Mi cuenta o mi acceso", "soporte"),
    "otro": ("Otra cosa", "soporte"),
}


def area_del_motivo(motivo):
    """El área que arranca atendiendo, según lo que dijo el cliente.

    Es una sugerencia, no una condena: el asesor transfiere si no era.
    """
    return MOTIVOS.get(motivo, ("", "soporte"))[1]


def motivo_valido(motivo):
    return motivo in MOTIVOS


# ─── Lo que se puede hacer con un caso ────────────────────────────────────

def problema_para_responder(caso, quien_id, es_super_admin=False):
    """Por qué este asesor NO puede responder este caso. None si puede.

    La regla es una sola y protege al cliente de recibir dos respuestas
    distintas: responde quien lo tomó. Un super administrador pasa por encima
    —tiene que poder destrabar—, pero eso queda asentado igual.
    """
    if not caso:
        return "Ese caso no existe."
    if caso.get("estado") == CERRADO:
        return "El caso está cerrado. Si hay algo nuevo, se abre uno nuevo."
    asignado = caso.get("asignado_a")
    if not asignado:
        return "Tomá el caso antes de responder."
    if asignado != quien_id and not es_super_admin:
        return f"Lo está atendiendo {caso.get('asignado_a_nombre') or 'otro asesor'}."
    return None


def problema_para_transferir(caso, quien_id, es_super_admin=False):
    """Por qué NO se puede transferir. None si se puede."""
    if not caso:
        return "Ese caso no existe."
    if caso.get("estado") == CERRADO:
        return "Un caso cerrado no se transfiere."
    asignado = caso.get("asignado_a")
    if asignado and asignado != quien_id and not es_super_admin:
        return f"Lo está atendiendo {caso.get('asignado_a_nombre') or 'otro asesor'}."
    return None


def problema_para_cerrar(caso):
    if not caso:
        return "Ese caso no existe."
    if caso.get("estado") == CERRADO:
        return "Ya estaba cerrado."
    return None


# Cuando el trabajo ya está hecho. Los dos y no sólo `CERRADO`: al asesor se le
# dice —y con razón— que deje el caso en «resuelto» si puede faltar algo,
# porque cerrado no se reabre. Con la calificación atada a «cerrado», se le
# pedía la opinión al cliente justo en el estado que al asesor se le pide NO
# usar, y los casos resueltos quedaban sin medir.
TERMINADOS = (RESUELTO, CERRADO)


def problema_para_calificar(caso):
    """El cliente califica el CASO, y una sola vez.

    Antes la calificación colgaba del usuario: se calificaba una vez en la
    vida y todas las consultas siguientes quedaban sin medir.

    Calificar no cierra nada: el cliente puede calificar un caso resuelto y
    seguir escribiendo si algo faltaba —eso lo reabre— sin perder la opinión
    que ya dejó.
    """
    if not caso:
        return "No hay un caso para calificar."
    if caso.get("estado") not in TERMINADOS:
        return "Vas a poder calificar cuando el caso esté resuelto."
    if caso.get("calificacion"):
        return "Este caso ya lo calificaste."
    return None


# ─── El tiempo ────────────────────────────────────────────────────────────

def _aware(valor):
    """Una fecha comparable, o `None`.

    Mongo devuelve fechas sin zona y compararlas con una que sí la tiene lanza
    TypeError, que rompería la lista entera por un documento viejo. Lo mismo
    vale para cualquier otra cosa que haya quedado en ese campo —una cadena de
    una migración de hace años, un `0`—: no se adivina, se devuelve `None` y el
    caso queda sin semáforo en vez de tumbar la bandeja para todos.
    """
    if not isinstance(valor, datetime):
        return None
    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor


def minutos_esperando(caso, ahora=None):
    """Cuánto lleva el cliente esperando la PRIMERA respuesta.

    Si ya se le respondió, devuelve None: el semáforo es sobre lo que todavía
    no se contestó, no sobre lo que tarda un caso en resolverse. Un caso
    complejo puede llevar días sin que nadie haya hecho nada mal.
    """
    if caso.get("primera_respuesta_en"):
        return None
    if caso.get("estado") == CERRADO:
        return None
    creado = _aware(caso.get("creado_en"))
    if not creado:
        return None
    ahora = ahora or datetime.now(timezone.utc)
    return max(0, int((ahora - creado).total_seconds() // 60))


def semaforo(caso, ahora=None):
    """`verde` | `amarillo` | `rojo` | None, para ordenar la lista.

    Rojo es «pasó el compromiso». Amarillo es «va por más de la mitad»: es el
    que sirve, porque todavía se llega. Un semáforo que sólo avisa cuando ya
    es tarde no evita nada.
    """
    minutos = minutos_esperando(caso, ahora)
    if minutos is None:
        return None
    tope = COMPROMISO_MINUTOS.get(caso.get("prioridad") or "normal", 240)
    if minutos >= tope:
        return "rojo"
    if minutos >= tope / 2:
        return "amarillo"
    return "verde"


# ─── El orden de la lista ─────────────────────────────────────────────────

_PESO_ESTADO = {ABIERTO: 0, EN_CURSO: 1, ESPERANDO_CLIENTE: 2, RESUELTO: 3, CERRADO: 4}
_PESO_PRIORIDAD = {"urgente": 0, "alta": 1, "normal": 2, "baja": 3}


def minutos_sin_respuesta(caso, ahora=None):
    """Cuánto hace que el cliente escribió y nadie le contestó.

    `None` si la pelota no la tiene la casa: el último que habló fuimos
    nosotros, o el caso está cerrado. Es distinto de `minutos_esperando`, que
    mide sólo hasta la PRIMERA respuesta y se apaga para siempre después: una
    conversación de ida y vuelta puede tener al cliente esperando la quinta
    respuesta hace tres horas y ese dato no aparecía en ningún lado.
    """
    if caso.get("estado") == CERRADO:
        return None
    if caso.get("ultimo_mensaje_de") != CLIENTE:
        return None
    cuando = _aware(caso.get("ultimo_mensaje_en")) or _aware(caso.get("creado_en"))
    if not cuando:
        return None
    ahora = ahora or datetime.now(timezone.utc)
    return max(0, int((ahora - cuando).total_seconds() // 60))


def clave_de_orden(caso, ahora=None):
    """Con qué criterio se ordena la bandeja. Menor va primero.

    El orden ES la herramienta: un asesor que entra a trabajar tiene que ver
    arriba lo que hay que hacer ahora, no lo más reciente. Por eso manda el
    escalamiento, después lo que nadie tomó, después la prioridad, y recién al
    final el tiempo.

    EL TIEMPO QUE CUENTA ES EL QUE EL CLIENTE LLEVA ESPERANDO AHORA

        Acá estaba `minutos_esperando`, que devuelve `None` en cuanto el caso
        tuvo su primera respuesta —y está bien que lo haga, mide otra cosa—.
        Como desempate eso valía cero para TODO caso ya contestado, o sea la
        mayoría: dos casos con el mismo estado y la misma prioridad quedaban en
        el orden en que la base los hubiera devuelto, que no es ninguno.

        Primero va el que nunca recibió respuesta, y entre los demás el que
        hace más rato que escribió sin que nadie le conteste. Un caso donde ya
        contestamos no tiene nada pendiente del lado de la casa y baja.
    """
    nunca = minutos_esperando(caso, ahora)
    espera = minutos_sin_respuesta(caso, ahora)
    return (
        0 if caso.get("escalado") else 1,
        _PESO_ESTADO.get(caso.get("estado"), 9),
        _PESO_PRIORIDAD.get(caso.get("prioridad") or "normal", 2),
        0 if nunca is not None else 1,
        -(nunca if nunca is not None else (espera or 0)),
    )


# ─── Los pedidos a otra área ──────────────────────────────────────────────

PEDIDO_PENDIENTE = "pendiente"
PEDIDO_RESPONDIDO = "respondido"
PEDIDO_CANCELADO = "cancelado"


def problema_para_pedir(area, detalle):
    """Un pedido a otra área sin detalle es una interrupción, no un pedido."""
    if not area_valida(area):
        return "Elegí un área de la lista."
    if len((detalle or "").strip()) < 10:
        return "Contá qué necesitás, con lo suficiente para que lo puedan resolver sin volver a preguntarte."
    return None


def problema_para_responder_pedido(pedido, quien_permisos, es_super_admin=False):
    """Contesta el pedido quien puede resolverlo, no cualquiera.

    Si no fuera así, un asesor de soporte podría «responder» un pedido a
    Finanzas y el caso seguiría adelante con una respuesta que nadie con la
    facultad de darla revisó.
    """
    if not pedido:
        return "Ese pedido no existe."
    if pedido.get("estado") != PEDIDO_PENDIENTE:
        return "Ese pedido ya fue respondido o cancelado."
    if es_super_admin:
        return None
    requerido = permiso_de_area(pedido.get("area"))
    if requerido and requerido not in (quien_permisos or []):
        return f"Este pedido lo contesta {nombre_de_area(pedido.get('area'))}."
    return None
