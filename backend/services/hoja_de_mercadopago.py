"""
La hoja de pagos de Mercado Pago: qué avisó, cuándo, y en qué terminó.

POR QUE ESTO EXISTE

    El 20 de septiembre de 2026 un cliente pagó con PIX y su envío no avanzó.
    Al investigarlo apareció que NO HABIA DONDE MIRAR: de todo lo que Mercado
    Pago nos avisa, no se guardaba nada. La única huella era el registro del
    servidor, que se rota, que nadie abre a las tres de la mañana, y que no se
    puede filtrar por fecha ni buscar por referencia.

    Averiguar si Mercado Pago había llamado costó leer código. Eso es lo que
    esta hoja arregla.

SE ESCRIBE SIEMPRE, Y ESO ES TODO EL PUNTO

    Cada aviso queda anotado, TERMINE COMO TERMINE: acreditado, rechazado por
    monto, no encontrado, lo que sea. Una hoja que sólo guarda los que salen
    bien no sirve para investigar — que es exactamente para lo que se la
    necesita.

    Por eso se escribe al principio del receptor y se completa al final, en
    vez de escribirse una sola vez cuando ya se sabe el resultado: si algo
    revienta en el medio, la fila igual queda, con el desenlace en blanco. Una
    fila a medias es una pista; una fila que no existe no es nada.

DESPUES DE LA FIRMA, NO ANTES

    Lo que no pasa la comprobación de firma no viene de Mercado Pago: viene de
    cualquiera que conozca la dirección. Guardarlo sería dejar que un
    desconocido escriba en nuestra hoja.

    Esos intentos igual quedan en el registro del servidor, con su 401.

POR LISTA DE LO PERMITIDO, COMO TODO

    El cuerpo que manda Mercado Pago trae datos del pagador. Guardarlo entero
    sería meter datos personales en una tabla que el equipo mira todos los
    días, sin que nadie lo haya decidido. Se guardan los campos que hacen
    falta para conciliar y nada más.
"""
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

COLECCION = "avisos_de_mercadopago"

# En qué terminó el aviso. Lo que ve el operador en la hoja.
ACREDITADO = "acreditado"
SIN_ACREDITAR = "sin_acreditar"
IGNORADO = "ignorado"          # no era un aviso de pago, o era repetido
SIN_TERMINAR = "sin_terminar"  # algo reventó en el medio: es una pista

COMO_TERMINO = {
    ACREDITADO: "Se acreditó",
    SIN_ACREDITAR: "NO se acreditó",
    IGNORADO: "No hacía falta hacer nada",
    SIN_TERMINAR: "Quedó a medias",
}


async def anotar_que_llego(db, *, mp_payment_id, tipo_de_evento) -> str:
    """Deja la fila apenas llega el aviso. Devuelve su identificador.

    NO LEVANTA NUNCA. Esto es un registro, no una operación: que no se pueda
    anotar no puede impedir que un pago se acredite. Sería cambiar un problema
    de papeles por uno de plata.
    """
    anotacion = f"mpa_{uuid.uuid4().hex[:12]}"
    try:
        await db[COLECCION].insert_one({
            "anotacion_id": anotacion,
            "mp_payment_id": str(mp_payment_id) if mp_payment_id else None,
            "tipo_de_evento": tipo_de_evento,
            "llego_a_las": datetime.now(timezone.utc),
            "como_termino": SIN_TERMINAR,
        })
    except Exception as e:                                    # pragma: no cover
        logger.error("No se pudo anotar el aviso de Mercado Pago %s: %s",
                     mp_payment_id, e)
        return ""
    return anotacion


async def anotar_como_termino(db, anotacion: str, *, como: str,
                              referencia=None, monto=None, estado_en_mp=None,
                              motivo=None, transaction_id=None) -> None:
    """Completa la fila con el desenlace. Tampoco levanta nunca."""
    if not anotacion:
        return
    campos = {"como_termino": como, "termino_a_las": datetime.now(timezone.utc)}
    # Sólo lo que de verdad hay: un `None` guardado tapa el dato de una
    # anotación anterior si esto se llamara dos veces.
    if referencia is not None:
        campos["referencia"] = referencia
    if monto is not None:
        campos["monto"] = float(monto)
    if estado_en_mp is not None:
        campos["estado_en_mp"] = estado_en_mp
    if motivo is not None:
        campos["motivo"] = motivo
    if transaction_id is not None:
        campos["transaction_id"] = transaction_id
    try:
        await db[COLECCION].update_one({"anotacion_id": anotacion},
                                       {"$set": campos})
    except Exception as e:                                    # pragma: no cover
        logger.error("No se pudo cerrar la anotación %s: %s", anotacion, e)


# Lo que ve el operador. Por lista de lo permitido: el documento puede crecer
# y lo nuevo no sale solo.
LO_QUE_SE_MUESTRA = {
    "_id": 0,
    "anotacion_id": 1,
    "mp_payment_id": 1,
    "referencia": 1,
    "transaction_id": 1,
    "tipo_de_evento": 1,
    "llego_a_las": 1,
    "termino_a_las": 1,
    "como_termino": 1,
    "motivo": 1,
    "monto": 1,
    "estado_en_mp": 1,
}


async def buscar(db, *, desde=None, hasta=None, texto=None, como_termino=None,
                 pagina: int = 1, por_pagina: int = 50) -> dict:
    """Las filas de la hoja, filtradas.

    EL TEXTO BUSCA POR LOS TRES IDENTIFICADORES

        Quien viene a buscar algo tiene UNO de los tres en la mano: el de
        Mercado Pago si lo sacó de su panel, nuestra referencia si lo sacó del
        cobro, o el de la operación si lo sacó del historial del cliente.
        Obligarlo a saber cuál de los tres es sería obligarlo a saber cómo
        está hecho esto por dentro.

        Se busca por el valor exacto y no por parecido: son identificadores,
        no nombres. Una búsqueda por parecido sobre una tabla que crece con
        cada pago es una consulta que un día tarda diez segundos.
    """
    filtro = {}
    if desde or hasta:
        rango = {}
        if desde:
            rango["$gte"] = desde
        if hasta:
            rango["$lte"] = hasta
        filtro["llego_a_las"] = rango
    if como_termino:
        filtro["como_termino"] = como_termino
    if texto:
        limpio = str(texto).strip()
        filtro["$or"] = [
            {"mp_payment_id": limpio},
            {"referencia": limpio},
            {"transaction_id": limpio},
        ]

    pagina = max(1, int(pagina or 1))
    por_pagina = min(200, max(1, int(por_pagina or 50)))
    total = await db[COLECCION].count_documents(filtro)
    filas = await db[COLECCION].find(filtro, LO_QUE_SE_MUESTRA).sort(
        "llego_a_las", -1).skip((pagina - 1) * por_pagina).limit(
        por_pagina).to_list(por_pagina)
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina,
            "filas": filas}
