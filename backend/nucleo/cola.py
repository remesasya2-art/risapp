"""
La bandeja de salida y la cola de trabajos del núcleo.

DOS TABLAS, UN PROBLEMA

    Un banco vive de «pasó X, entonces hay que hacer Y»: entró un pago,
    entonces avisar al titular; cerró el día, entonces armar el informe.
    Lo difícil no es hacer Y: es garantizar que Y se haga UNA vez, aunque
    el proceso se muera en el medio, y que nunca se haga si X en realidad
    no pasó.

    La bandeja de salida (`eventos`) resuelve la segunda mitad: el evento se
    escribe en LA MISMA transacción que el asiento. Si el asiento no entró,
    el evento tampoco. Si entró, el evento está ahí aunque el proceso se
    caiga un milisegundo después, y el despachador lo va a encontrar.

    La cola (`trabajos`) resuelve la primera: cada trabajo tiene una clave
    única, se toma con un turno de tiempo, se reintenta con espera creciente
    y, si sigue fallando, va a la cola de muertos donde una persona lo ve.

POR QUE EN LA MISMA BASE Y NO EN REDIS O EN UNA COLA EXTERNA

    Porque la garantía de arriba —evento y asiento juntos o ninguno— sólo
    existe si están en la misma transacción, y una transacción no cruza a
    otro sistema. Una cola externa se puede agregar después, DETRAS de esta
    tabla, sin perder la garantía. Al revés no se puede.

LOS TURNOS, Y POR QUE NO `SELECT ... FOR UPDATE SKIP LOCKED`

    Tomar un trabajo es un UPDATE condicional: «pasalo a en_curso si sigue
    como lo vi». Si otro trabajador lo tomó primero, el UPDATE toca cero
    filas y se prueba con el siguiente. Es lo mismo que hace `find_one_and_
    update` en el webhook de Mercado Pago, y funciona igual en Postgres y
    en el SQLite de los tests. `SKIP LOCKED` sería más elegante en Postgres
    y no existe en SQLite: dos caminos para probar, uno solo para correr.

    El turno dura `DURACION_DEL_TURNO`. Si el proceso muere con un trabajo
    tomado, nadie lo libera: vence solo, y el siguiente trabajador lo
    retoma. Por eso el manejador tiene que ser idempotente: puede correr
    dos veces si la primera murió justo antes de marcar «hecho».

LA ESPERA CRECIENTE

    5, 10, 20, 40, 80 segundos, con tope, y un poco de azar arriba. El azar
    está para que diez trabajos que fallaron juntos por lo mismo (un
    proveedor caído) no vuelvan a pegar todos en el mismo segundo.

LO QUE NO HAY

    Prioridades, colas con nombre, programación a futuro más allá del
    reintento. Cuando hagan falta se agregan como columnas; hoy serían
    código que nadie usa.
"""
import json
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select

from nucleo.esquema import eventos, trabajos

PENDIENTE, EN_CURSO, HECHO, MUERTO = "pendiente", "en_curso", "hecho", "muerto"
ESTADOS = (PENDIENTE, EN_CURSO, HECHO, MUERTO)

INTENTOS_MAXIMOS = 6            # un intento y cinco reintentos; el séptimo no existe
DURACION_DEL_TURNO = 60         # segundos que un trabajador tiene el trabajo antes de que otro lo retome
ESPERA_BASE = 5                 # segundos antes del primer reintento
ESPERA_TOPE = 600               # nunca más de diez minutos entre reintentos
AZAR_MAXIMO = 0.25              # hasta un cuarto más, para desparramar


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _json(carga: dict) -> str:
    """Canónico: claves ordenadas, sin espacios. La misma carga, el mismo texto."""
    return json.dumps(carga or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def espera_antes_del_reintento(intentos_fallidos: int, azar: Optional[float] = None) -> float:
    """Segundos hasta el próximo intento después de `intentos_fallidos`
    fallos. Crece al doble por fallo, con tope, más hasta un cuarto de azar."""
    if intentos_fallidos < 1:
        raise ValueError("La espera se calcula después de al menos un fallo.")
    base = min(ESPERA_BASE * (2 ** (intentos_fallidos - 1)), ESPERA_TOPE)
    azar = random.random() if azar is None else azar
    return base * (1 + AZAR_MAXIMO * azar)


# ─── la bandeja de salida ─────────────────────────────────────────────────

async def anotar_evento(sesion, *, tipo: str, clave: str, carga: dict) -> Optional[int]:
    """Deja un evento en la bandeja, dentro de la transacción de `sesion`.
    Idempotente por (tipo, clave): si ya está, devuelve el que había."""
    ya = (await sesion.execute(
        select(eventos.c.id).where(eventos.c.tipo == tipo, eventos.c.clave == clave))).scalar_one_or_none()
    if ya is not None:
        return ya
    r = await sesion.execute(eventos.insert().values(tipo=tipo, clave=clave, carga=_json(carga)))
    return r.inserted_primary_key[0]


async def despachar_eventos(sesion, suscripciones: dict, *, ahora: Optional[datetime] = None,
                            limite: int = 100) -> int:
    """Convierte los eventos sin publicar en trabajos, según `suscripciones`
    ({tipo_de_evento: (tipo_de_trabajo, …)}), y los marca publicados. Todo
    en una transacción: si un trabajo no se pudo encolar, el evento sigue
    sin publicar y la próxima vuelta lo vuelve a intentar.

    Un evento sin suscriptores se publica igual: queda como registro de que
    pasó, que es la mitad de su valor."""
    ahora = ahora or ahora_utc()
    pendientes = (await sesion.execute(
        select(eventos).where(eventos.c.publicado.is_(None)).order_by(eventos.c.id).limit(limite))).all()
    publicados = 0
    for e in pendientes:
        # «Marcalo publicado si sigue sin publicar»: si otro despachador se
        # lo llevó entre el SELECT y acá, toca cero filas y se lo dejamos.
        r = await sesion.execute(eventos.update()
                                 .where(eventos.c.id == e.id, eventos.c.publicado.is_(None))
                                 .values(publicado=ahora))
        if r.rowcount != 1:
            continue
        carga = json.loads(e.carga)
        for tipo_de_trabajo in suscripciones.get(e.tipo, ()):
            await encolar(sesion, tipo=tipo_de_trabajo, clave=f"{e.tipo}:{e.clave}", carga=carga,
                          origen_evento=e.id, ahora=ahora)
        publicados += 1
    return publicados


# ─── la cola ──────────────────────────────────────────────────────────────

async def encolar(sesion, *, tipo: str, clave: str, carga: dict, ahora: Optional[datetime] = None,
                  origen_evento: Optional[int] = None, max_intentos: int = INTENTOS_MAXIMOS) -> dict:
    """Deja un trabajo pendiente. Idempotente por (tipo, clave): el mismo
    trabajo pedido dos veces es uno, y se devuelve `nuevo=False`."""
    ahora = ahora or ahora_utc()
    ya = (await sesion.execute(
        select(trabajos.c.id).where(trabajos.c.tipo == tipo, trabajos.c.clave == clave))).scalar_one_or_none()
    if ya is not None:
        return {"id": ya, "nuevo": False}
    r = await sesion.execute(trabajos.insert().values(
        tipo=tipo, clave=clave, carga=_json(carga), estado=PENDIENTE, intentos=0,
        max_intentos=max_intentos, proximo_intento=ahora, origen_evento=origen_evento))
    return {"id": r.inserted_primary_key[0], "nuevo": True}


async def tomar(sesion, *, trabajador: str, ahora: Optional[datetime] = None) -> Optional[dict]:
    """El próximo trabajo que se pueda tomar, ya tomado por `trabajador`, o
    None. Se puede tomar lo pendiente cuyo momento llegó y lo en curso cuyo
    turno venció (el trabajador anterior murió con él en la mano)."""
    ahora = ahora or ahora_utc()
    candidato = (await sesion.execute(
        select(trabajos)
        .where(((trabajos.c.estado == PENDIENTE) & (trabajos.c.proximo_intento <= ahora))
               | ((trabajos.c.estado == EN_CURSO) & (trabajos.c.tomado_hasta < ahora)))
        .order_by(trabajos.c.proximo_intento, trabajos.c.id).limit(1))).first()
    if candidato is None:
        return None
    r = await sesion.execute(trabajos.update()
                             .where(trabajos.c.id == candidato.id, trabajos.c.estado == candidato.estado,
                                    trabajos.c.intentos == candidato.intentos)
                             .values(estado=EN_CURSO, tomado_por=trabajador,
                                     tomado_hasta=ahora + timedelta(seconds=DURACION_DEL_TURNO),
                                     intentos=trabajos.c.intentos + 1))
    if r.rowcount != 1:
        return None                          # otro se lo llevó; la próxima vuelta sigue
    return {"id": candidato.id, "tipo": candidato.tipo, "clave": candidato.clave,
            "carga": json.loads(candidato.carga), "intentos": candidato.intentos + 1,
            "max_intentos": candidato.max_intentos}


async def terminar(sesion, trabajo_id: int, *, trabajador: str, resultado: Optional[str] = None,
                   ahora: Optional[datetime] = None) -> bool:
    """Marca hecho. Sólo si el trabajo sigue siendo de `trabajador`: si el
    turno venció y otro lo retomó, el resultado del primero no pisa nada."""
    ahora = ahora or ahora_utc()
    r = await sesion.execute(trabajos.update()
                             .where(trabajos.c.id == trabajo_id, trabajos.c.estado == EN_CURSO,
                                    trabajos.c.tomado_por == trabajador)
                             .values(estado=HECHO, terminado=ahora, tomado_hasta=None,
                                     resultado=(resultado or None), ultimo_error=None))
    return r.rowcount == 1


async def fallar(sesion, trabajo_id: int, *, trabajador: str, error: str,
                 ahora: Optional[datetime] = None, azar: Optional[float] = None) -> dict:
    """Un intento falló. Vuelve a pendiente con espera creciente, o a muerto
    si ya no quedan intentos. Devuelve {estado, proximo_intento}."""
    ahora = ahora or ahora_utc()
    fila = (await sesion.execute(select(trabajos).where(trabajos.c.id == trabajo_id))).first()
    if fila is None or fila.estado != EN_CURSO or fila.tomado_por != trabajador:
        return {"estado": fila.estado if fila else None, "proximo_intento": None, "ajeno": True}
    error = (error or "")[:2000]
    if fila.intentos >= fila.max_intentos:
        await sesion.execute(trabajos.update().where(trabajos.c.id == trabajo_id)
                             .values(estado=MUERTO, terminado=ahora, tomado_hasta=None, ultimo_error=error))
        return {"estado": MUERTO, "proximo_intento": None}
    proximo = ahora + timedelta(seconds=espera_antes_del_reintento(fila.intentos, azar))
    await sesion.execute(trabajos.update().where(trabajos.c.id == trabajo_id)
                         .values(estado=PENDIENTE, proximo_intento=proximo, tomado_hasta=None,
                                 ultimo_error=error))
    return {"estado": PENDIENTE, "proximo_intento": proximo.isoformat()}


async def matar(sesion, trabajo_id: int, *, trabajador: str, error: str,
                ahora: Optional[datetime] = None) -> bool:
    """Directo a muerto, sin reintentos. Para lo que reintentar no arregla:
    un tipo de trabajo que no tiene manejador."""
    ahora = ahora or ahora_utc()
    r = await sesion.execute(trabajos.update()
                             .where(trabajos.c.id == trabajo_id, trabajos.c.estado == EN_CURSO,
                                    trabajos.c.tomado_por == trabajador)
                             .values(estado=MUERTO, terminado=ahora, tomado_hasta=None,
                                     ultimo_error=(error or "")[:2000]))
    return r.rowcount == 1


async def reintentar(sesion, trabajo_id: int, *, ahora: Optional[datetime] = None) -> bool:
    """Un muerto vuelve a la cola, con los intentos en cero. Lo pide una
    persona desde el panel; el último error queda para que se sepa por qué
    murió."""
    ahora = ahora or ahora_utc()
    r = await sesion.execute(trabajos.update()
                             .where(trabajos.c.id == trabajo_id, trabajos.c.estado == MUERTO)
                             .values(estado=PENDIENTE, intentos=0, proximo_intento=ahora,
                                     tomado_por=None, tomado_hasta=None, terminado=None))
    return r.rowcount == 1


# ─── para mirar ───────────────────────────────────────────────────────────

async def resumen(sesion) -> dict:
    filas = (await sesion.execute(
        select(trabajos.c.estado, func.count()).group_by(trabajos.c.estado))).all()
    salida = {e: 0 for e in ESTADOS}
    for estado, cuantos in filas:
        salida[estado] = int(cuantos)
    salida["eventos_sin_publicar"] = int((await sesion.execute(
        select(func.count()).select_from(eventos).where(eventos.c.publicado.is_(None)))).scalar_one())
    salida["eventos"] = int((await sesion.execute(select(func.count()).select_from(eventos))).scalar_one())
    return salida


async def listar_trabajos(sesion, *, limite: int = 50) -> list:
    filas = (await sesion.execute(select(trabajos).order_by(trabajos.c.id.desc()).limit(limite))).all()
    return [{"id": f.id, "tipo": f.tipo, "clave": f.clave, "carga": json.loads(f.carga), "estado": f.estado,
             "intentos": f.intentos, "max_intentos": f.max_intentos,
             "proximo_intento": _iso(f.proximo_intento), "tomado_por": f.tomado_por,
             "tomado_hasta": _iso(f.tomado_hasta), "ultimo_error": f.ultimo_error, "resultado": f.resultado,
             "origen_evento": f.origen_evento, "creado": _iso(f.creado), "terminado": _iso(f.terminado)}
            for f in filas]


async def listar_eventos(sesion, *, limite: int = 50) -> list:
    filas = (await sesion.execute(select(eventos).order_by(eventos.c.id.desc()).limit(limite))).all()
    return [{"id": f.id, "tipo": f.tipo, "clave": f.clave, "carga": json.loads(f.carga),
             "creado": _iso(f.creado), "publicado": _iso(f.publicado)} for f in filas]
