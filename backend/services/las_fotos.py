"""Las fotos que viven adentro de una transacción, y por qué no hay que leerlas.

DONDE ESTAN

    El comprobante de una recarga y los del pago de un retiro se guardan
    INLINE, como data URL en base64, adentro del documento de `transactions`.
    Una foto de celular de 500 KB pesa unos 667 KB así guardada, y un retiro
    completado lleva una LISTA de fotos, no una.

QUE PASABA

    Veintiuna consultas a `transactions` no llevaban proyección, así que se
    traían las fotos aunque no las usaran. La peor era la de exportar:

        db.transactions.find({}, {"_id": 0, "proof_image": 0}).to_list(10000)

    Medido corriéndolo, con cincuenta filas de una foto en singular y dos en
    plural: 64 MB en memoria para escribir NUEVE columnas de un Excel. Al tope
    de la ruta —diez mil filas— serían unos 12 GB. El proceso de Railway tiene
    bastante menos: esa exportación lo mata mucho antes de terminar, y se
    lleva puesta la app para todos mientras se reinicia.

POR QUE LA PROYECCION QUE HABIA NO ALCANZABA

    Era una lista de lo PROHIBIDO, y nombraba `proof_image`, el campo viejo.
    Después se agregó `proof_images` —en plural, una lista— y nadie se acordó
    de agregarlo ahí. Es exactamente la forma de fallar contra la que avisa la
    regla del proyecto: una lista de lo prohibido deja pasar cada campo nuevo
    hasta que alguien se acuerde.

COMO SE EVITA QUE VUELVA A PASAR

    Los campos pesados se nombran UNA vez, acá. Una pantalla que los quiera
    fuera usa `SIN_LAS_FOTOS`, no una lista escrita a mano; y hay un test que
    recorre el código y exige que toda consulta de LISTA a `transactions`
    lleve proyección, y que si es de lo prohibido, las excluya a TODAS.

    O sea que agregar un campo de fotos nuevo a esta tupla pone en rojo cada
    lugar que se olvidó de sacarlo. Antes, agregarlo no avisaba en ningún lado.

POR QUE `find_one` QUEDA AFUERA DE LA REGLA

    Buscar UNA transacción por su id es, casi siempre, la pantalla de detalle:
    ahí la foto es justo lo que se viene a ver. Traer una foto cuando se pidió
    una transacción no es el problema; traer mil cuando se pidió una lista, sí.
"""
LAS_FOTOS = ("proof_image", "proof_images", "comprobante_pago")

# Para las pantallas que pasan el documento entero a la vista y no se puede
# saber desde acá qué campos les hacen falta. Es una lista de lo prohibido, y
# se tolera SOLO porque el test la obliga a nombrarlas todas.
SIN_LAS_FOTOS = {campo: 0 for campo in LAS_FOTOS}


def sin_las_fotos(**extra) -> dict:
    """`SIN_LAS_FOTOS` más lo que se quiera sacar además (`_id`, por ejemplo)."""
    proyeccion = dict(SIN_LAS_FOTOS)
    proyeccion.update(extra)
    return proyeccion


def solo(*campos: str) -> dict:
    """Lista de lo PERMITIDO: sólo estos campos, y sin `_id`.

    Es la forma preferida. `sin_las_fotos()` existe para los pocos lugares
    donde el documento se pasa entero a la pantalla.
    """
    proyeccion = {"_id": 0}
    proyeccion.update({campo: 1 for campo in campos})
    return proyeccion


async def cuales_tienen_foto(base, filtro: dict) -> set:
    """Los `transaction_id` que tienen comprobante, SIN traerse ninguna foto.

    El reporte de procesados imprime una columna que dice «sí» o «no». Para
    escribir esa palabra se traía el documento entero de cada fila, fotos
    incluidas: megabytes para dos letras. Es el problema que
    `services/reportes.py` ya documenta en su encabezado, punto 1.

    Acá la pregunta la contesta la base: el `$size` de la lista y la
    existencia del campo viejo se evalúan del lado del servidor y lo que
    vuelve es un booleano por fila.
    """
    etapas = [
        {"$match": filtro},
        {"$project": {
            "_id": 0,
            "transaction_id": 1,
            "tiene": {"$or": [
                {"$gt": [{"$size": {"$ifNull": ["$proof_images", []]}}, 0]},
                {"$ne": [{"$ifNull": ["$proof_image", None]}, None]},
            ]},
        }},
    ]
    con_foto = set()
    async for fila in base.transactions.aggregate(etapas):
        if fila.get("tiene"):
            con_foto.add(fila.get("transaction_id"))
    return con_foto
