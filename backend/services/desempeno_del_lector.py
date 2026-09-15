"""
services/desempeno_del_lector.py — Qué tan bien viene adjudicando el lector.

PARA QUE SIRVE ESTE NUMERO

    El lector mira cada foto de comprobante y trata de decir de qué orden es.
    Hasta acá nadie sabía con qué frecuencia acertaba, con qué frecuencia se
    abstenía, y —lo más importante— con qué frecuencia se EQUIVOCABA.

    Tres cosas dependen de saberlo:

    1.  ENTERARSE CUANDO SE ROMPE. Ya pasó: el lector estuvo caído en
        producción y nadie se dio cuenta hasta que el agente venía asignando
        cada foto a mano y lo mencionó al pasar. `sin_lector` en este informe
        es exactamente ese síntoma, contado.

    2.  SABER SI UN CAMBIO LO MEJORA. Las reglas de emparejamiento están en
        `comprobantes_del_lote.py` y se pueden afinar. Sin un número antes y
        después, afinarlas es adivinar.

    3.  DECIDIR SI DARLE MAS TRABAJO. Hoy cerrar un lote exige que una persona
        haya mirado todo. `corregidas` es el número que dice si alguna vez se
        le puede confiar el cierre de las que emparejó limpio: si de cien
        «seguras» hubo que corregir cinco, la respuesta es no, y conviene
        saberlo por un número y no por un pago mal asentado.

SOLO SE MIRAN LOS LOTES CERRADOS, Y ES LA DECISION QUE HACE HONESTO EL NUMERO

    En un lote abierto las fotos todavía no las revisó nadie. Contarlas sería
    darle por buena al lector cada foto recién subida sólo porque aún no llegó
    la persona que la iba a corregir — el número saldría alto el día de la
    carga y bajaría solo con los días.

    Cerrar un lote, en cambio, exige que TODAS sus órdenes estén resueltas
    (ver `lotes_de_pago.cerrar`). O sea que en un lote cerrado alguien ya pasó
    por cada foto: ahí «nadie la corrigió» quiere decir «estaba bien», que es
    lo único que se puede afirmar.

QUE CUENTA COMO ERROR, Y POR QUE ALCANZA CON COMPARAR LA ORDEN

    Una foto la corrigió una persona si terminó en un lugar distinto del que
    eligió el lector. Eso cubre las tres formas de corregirla, sin una regla
    por cada una:

        se movió a otra orden   ->  `orden_id` es otra
        se soltó                ->  `orden_id` quedó en None
        se descartó             ->  `orden_id` quedó en None

    Y la tercera es correcta aunque suene dura. Descartar una foto que el
    lector dio por segura es decir que esa prueba no servía; y como una orden
    con comprobante colgado NO se puede devolver a la cola sin descartar antes
    la foto (ver `lotes_de_pago.devolver_una`), el descarte es el camino
    obligado también cuando el banco rechazó el pago. En los dos casos el
    lote no se habría podido cerrar solo, que es justo lo que este número mide.

LO QUE SE DEJA AFUERA DEL DENOMINADOR, PARA QUE NO MIENTA

    `sin_lector`  El lector no estaba. Eso no es el lector fallando, es el
                  lector ausente. Mezclarlo hunde el porcentaje sin que nadie
                  haya hecho nada mal. Se cuenta APARTE, porque es la señal de
                  que algo se rompió.

    `de_antes`    Fotos subidas antes de que existiera `estado_del_lector`.
                  No hay forma de saber qué dijo la máquina. Se cuentan y se
                  dicen: fingir que el informe las incluye sería peor que
                  admitir que no.
"""
import logging
from datetime import datetime, timezone

from services import comprobantes_del_lote as cmp
from services import lotes_de_pago

logger = logging.getLogger(__name__)

# Cuántas fotos entran en el informe. Doscientas son varias semanas de trabajo
# en este volumen: suficientes para que un porcentaje signifique algo, y pocas
# como para que un cambio en las reglas se note a los pocos días en vez de
# quedar diluido en el promedio de todo el año.
VENTANA = 200

# Tope de lotes que se leen para juntar esas fotos. Sin tope, el día que haya
# mil lotes cerrados esta consulta los traería todos para mostrar un renglón.
LOTES_A_LO_SUMO = 60

# Sólo estos campos. No es adorno: `comprobantes` guardaba las fotos enteras
# en base64 hasta hace poco, y todavía puede haberlas en los lotes viejos.
# Traerlas para contar renglones serían decenas de megas por consulta.
LO_QUE_HACE_FALTA = {
    "_id": 0,
    "lote_id": 1,
    "numero": 1,
    "cerrado_en": 1,
    "comprobantes.estado_del_lector": 1,
    "comprobantes.orden_del_lector": 1,
    "comprobantes.orden_id": 1,
    "comprobantes.subido_en": 1,
}


def _cuando(foto: dict) -> float:
    """La fecha de subida como NUMERO, para poder ordenar sin sorpresas.

    POR QUE UN NUMERO Y NO LA FECHA

        La primera versión devolvía la fecha, y para las fotos sin fecha un
        respaldo: `datetime(1970, 1, 1, tzinfo=utc)`. Parecía inofensivo y no
        lo era.

        El driver devuelve las fechas SIN zona horaria —`AsyncIOMotorClient`
        se crea sin `tz_aware`, y `mongomock` hace lo mismo—, así que todas las
        fotos llegaban sin zona y el respaldo con zona. Comparar una con otra
        en un `sort` levanta TypeError, y acá ese error lo atrapa el `except`
        de `medir`: el informe entero salía VACIO, en silencio, porque a una
        sola foto le faltaba la fecha.

        Un número no tiene ese problema. Es la diferencia entre protegerse de
        la mezcla y hacer que la mezcla no exista.
    """
    valor = foto.get("subido_en")
    if not isinstance(valor, datetime):
        return 0.0
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.timestamp()


def _la_corrigio_una_persona(foto: dict) -> bool:
    """Si terminó en un lugar distinto del que eligió el lector."""
    return foto.get("orden_id") != foto.get("orden_del_lector")


async def medir(db) -> dict:
    """El informe. Nunca levanta: es un número en una pantalla, no un pago."""
    try:
        return await _medir(db)
    except Exception as e:                                # pragma: no cover
        # Una pantalla de pagos no se cae porque un contador no sepa contar.
        # Queda el motivo en el registro y el informe sale vacío, que la
        # pantalla ya sabe no mostrar.
        logger.warning("desempeno_del_lector: no se pudo medir: %s", e)
        return _vacio()


def _vacio() -> dict:
    return {"ventana": VENTANA, "lotes": 0, "miradas": 0, "resueltas": 0,
            "corregidas": 0, "avisadas": 0, "no_pudo": 0, "sin_lector": 0,
            "de_antes": 0, "desde": None, "hasta": None}


async def _medir(db) -> dict:
    cursor = db[lotes_de_pago.COLECCION].find(
        {"estado": lotes_de_pago.CERRADO}, LO_QUE_HACE_FALTA
    ).sort("cerrado_en", -1).limit(LOTES_A_LO_SUMO)

    lotes = 0
    juzgadas, sin_lector, de_antes = [], 0, 0
    async for lote in cursor:
        lotes += 1
        for foto in lote.get("comprobantes") or []:
            veredicto = foto.get("estado_del_lector")
            if not veredicto:
                de_antes += 1
            elif veredicto == cmp.SIN_LECTOR:
                sin_lector += 1
            else:
                juzgadas.append(foto)

    # La ventana se aplica a las que el lector SI juzgó. Si se aplicara antes
    # de separar, una semana con el lector caído llenaría las doscientas de
    # `sin_lector` y el informe quedaría en blanco justo cuando hay algo que
    # mirar.
    juzgadas.sort(key=_cuando, reverse=True)
    juzgadas = juzgadas[:VENTANA]

    resueltas = [f for f in juzgadas if f["estado_del_lector"] == cmp.SEGURO]
    avisadas = sum(1 for f in juzgadas if f["estado_del_lector"] == cmp.REVISAR)

    informe = _vacio()
    informe.update({
        "lotes": lotes,
        "miradas": len(juzgadas),
        "resueltas": len(resueltas),
        "corregidas": sum(1 for f in resueltas if _la_corrigio_una_persona(f)),
        # `revisar` NO es un error: el lector encontró al beneficiario y avisó
        # que el monto no coincide. Es el lector trabajando bien, y por eso va
        # en su propio renglón y no sumado a lo que no pudo.
        "avisadas": avisadas,
        "no_pudo": len(juzgadas) - len(resueltas) - avisadas,
        "sin_lector": sin_lector,
        "de_antes": de_antes,
    })
    if juzgadas:
        # Las fechas salen crudas, como vinieron: `_cuando` devuelve un número
        # para ordenar, no algo que una pantalla pueda mostrar.
        informe["desde"] = juzgadas[-1].get("subido_en")
        informe["hasta"] = juzgadas[0].get("subido_en")
    return informe
