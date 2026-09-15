"""
services/comprobantes_del_lote.py — Una sola carga de fotos para todo el lote.

QUE RESUELVE

    El agente paga once órdenes en la banca en línea y vuelve con once
    capturas en el teléfono. Antes tenía que abrir orden por orden, buscar
    cuál de las once fotos era la de ésa, y subirla. Once veces. Y la única
    forma de saber cuál era cuál era leyendo el monto en la foto, que es
    justo el dato que se repite cuando dos personas cobran lo mismo.

    Acá se sueltan las once juntas y el sistema dice de quién es cada una.

COMO SE DECIDE DE QUIEN ES UNA FOTO

    No por el monto. El monto NUNCA identifica: dos beneficiarios que cobran
    lo mismo el mismo día es normal, no raro. El monto sirve para lo otro —
    para confirmar que la foto que se adjudicó por otra vía dice la cifra que
    corresponde.

    Lo que identifica es lo que es único de cada beneficiario, y está en
    `LLAVES`. Cada entrada es una COMBINACION que alcanza por sí sola:

      · la cuenta de 20 dígitos — única, y sale entera en las
        transferencias de Banesco;
      · el teléfono junto con la cédula — los dos salen enteros en los
        comprobantes de pago móvil de los dos bancos;
      · el nombre junto con los últimos cuatro dígitos de la cuenta — es el
        caso de las transferencias del BDV, que tapan la cuenta y dejan ver
        sólo el final.

    Una sola señal floja no adjudica. La cédula sola no, porque una misma
    persona puede tener dos órdenes en el mismo lote. El nombre solo tampoco.

SI HAY LA MAS MINIMA DUDA, NO SE ADJUDICA

    Dos órdenes que encajan con la misma foto: ninguna. Dos fotos que encajan
    con la misma orden: ninguna. La llave encaja pero el monto no: se propone
    y se marca en amarillo, y la confirma una persona.

    Es a propósito, y es la regla más importante del módulo. Adjudicar mal
    deja el comprobante de un pago colgado de la orden de otro cliente, que
    es un documento falso en un expediente — y en un negocio de remesas eso
    no es un detalle de comodidad. Dejar una foto sin adjudicar sólo cuesta
    un clic.

LO QUE ESTO NO HACE

    No aprueba nada, no acredita nada y no cierra el lote. Colgar la foto y
    dar la orden por pagada son dos decisiones distintas, y la segunda la
    toma una persona mirando la primera.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from services import (archivo_de_pagos, auditoria, imagen_recibida,
                      lector_de_comprobantes as lector, lotes_de_pago)

logger = logging.getLogger(__name__)

# Cuántas fotos entran en una carga. El lote tiene un techo de 300 órdenes;
# esto lo acompaña con holgura para el caso de dos capturas de una misma
# operación, sin dejar que una carpeta entera del teléfono entre por error.
MAXIMO_POR_CARGA = 60


def _cuantas_a_la_vez() -> int:
    """Cuántas fotos se leen en paralelo. Uno menos que los procesadores.

    `tesseract` es un programa aparte y cada lectura usa un procesador entero
    (ver `_un_solo_hilo_por_lectura` en el lector). Dejar uno libre no es
    prudencia de manual: la primera versión leía cuatro a la vez en una
    máquina de cuatro, y mientras leía, el resto de la aplicación —el panel,
    la app del cliente— no contestaba.
    """
    import os
    return max(1, min(4, (os.cpu_count() or 2) - 1))


# Las combinaciones de señales que alcanzan para decir «esta foto es de esta
# orden». Ver el encabezado: cada una es única por sí misma, y el monto no
# está en ninguna a propósito.
LLAVES = (
    ("cuenta",),
    ("telefono", "cedula"),
    ("nombre", "cuenta_final"),
)

# Cómo termina cada foto.
SEGURO = "seguro"              # llave y monto coinciden: se adjudica
REVISAR = "revisar"            # la llave coincide, el monto no
AMBIGUO = "ambiguo"            # encaja con más de una orden
REPETIDO = "repetido"          # más de una foto encaja con la misma orden
SIN_ADJUDICAR = "sin_adjudicar"  # no encaja con ninguna
SIN_LECTOR = "sin_lector"      # no hay lector en el servidor
A_MANO = "a_mano"              # lo adjudicó una persona
DESCARTADO = "descartado"      # una persona dijo que esta foto no va

# Los estados en los que la foto quedó colgada de una orden. No se usa para
# DECIDIR si colgarla —eso lo dice el `orden_id`, ver `_colgar_de_las_ordenes`—
# sino para que la pantalla sepa cuáles pintar en verde.
ADJUDICADOS = (SEGURO, REVISAR, A_MANO)

# Con cuáles alcanza para asentar el pago sin que nadie mire la foto.
#
# POR QUE «REVISAR» NO ESTA ACA, AUNQUE LA FOTO ESTE COLGADA DE LA ORDEN
#
#     `REVISAR` quiere decir que el beneficiario coincide pero EL MONTO NO: la
#     foto es de esa persona y el importe no es el de la orden. Puede ser un
#     cobro por otra cifra, un pago parcial, o una orden mal cargada.
#
#     Asentar eso solo sería dar por pagado un importe que nadie comparó. Va a
#     la lista de lo que mira una persona, que es lo que se decidió.
#
#     Por eso son dos listas y no una: `ADJUDICADOS` dice de quién es la foto,
#     esta dice si alcanza para registrar. Juntarlas fue la primera idea y
#     mezclaba dos preguntas distintas.
LISTOS_PARA_REGISTRAR = (SEGURO, A_MANO)

# Cuántas letras tiene que tener una palabra del nombre para que cuente. Con
# menos, «DE» y «LA» harían coincidir a cualquiera con cualquiera.
LETRAS_DE_UNA_PALABRA = 4

# El motivo con el que se descarta una foto. Un mínimo para que «x» o «no» no
# pasen por explicación, y un tope para que la pantalla no reviente.
LETRAS_DEL_MOTIVO = 4
LARGO_DEL_MOTIVO = 200

# Cuántas palabras del nombre tienen que aparecer para dar el nombre por
# encontrado. Dos, porque un apellido solo se repite: en un lote con dos
# «RODRIGUEZ» distintos, una sola palabra adjudicaría al azar.
PALABRAS_QUE_HACEN_FALTA = 2


def _digitos(valor) -> str:
    return lector.solo_digitos(valor)


def _palabras_del_nombre(nombre) -> list:
    return [p for p in lector.sin_adornos(nombre).split()
            if len(p) >= LETRAS_DE_UNA_PALABRA]


def senales_de_la_orden(orden: dict) -> dict:
    """Los datos de la orden con los que se compara, ya normalizados."""
    b = orden.get("beneficiario") or {}
    cuenta = _digitos(b.get("cuenta"))
    return {
        "cuenta": cuenta if len(cuenta) == archivo_de_pagos.LARGO_DE_CUENTA else "",
        # Los últimos cuatro son lo único que muestra el BDV en una
        # transferencia. Solos no alcanzan —hay diez mil combinaciones y un
        # lote puede tener dos— así que van siempre con el nombre.
        "cuenta_final": cuenta[-4:] if len(cuenta) >= 4 else "",
        "telefono": _digitos(b.get("telefono")),
        "cedula": _digitos(b.get("documento")),
        "nombre": _palabras_del_nombre(b.get("nombre")),
        "monto": _digitos(archivo_de_pagos.monto(orden.get("monto") or 0)),
    }


def _coincide(senal: str, orden: dict, foto: dict) -> bool:
    """¿Esta señal de la orden aparece en la foto?

    Las tres primeras buscan en una LISTA de candidatos, y un dato vacío no
    está en ninguna lista: no hace falta preguntar antes si la orden lo tiene.
    La cuarta busca adentro de un TEXTO, y ahí el vacío está en todas partes
    —«"" in "cualquier cosa"» es verdadero—, así que esa sí lleva su guarda.

    Es una diferencia de una línea entre dos casos que se leen igual, y es el
    tipo de cosa que alguien «simplifica» dentro de seis meses.
    """
    if senal == "cuenta":
        return orden["cuenta"] in foto["cuentas"]
    if senal == "telefono":
        return orden["telefono"] in foto["telefonos"]
    if senal == "cedula":
        return orden["cedula"] in foto["cedulas"]
    if senal == "cuenta_final":
        # El BDV la escribe como «0102****4324»: los asteriscos se fueron al
        # sacar los separadores, así que se busca el final entre los dígitos
        # sueltos del texto, no entre las cuentas de 20.
        return bool(orden["cuenta_final"]) and orden["cuenta_final"] in foto["texto_digitos"]
    if senal == "nombre":
        encontradas = sum(1 for p in orden["nombre"] if p in foto["texto"])
        return encontradas >= min(PALABRAS_QUE_HACEN_FALTA, len(orden["nombre"] or [" "]))
    return False


def llaves_que_encajan(orden: dict, foto: dict) -> list:
    """Qué combinaciones identificatorias se cumplen enteras. Vacío = no encaja."""
    return [llave for llave in LLAVES
            if all(_coincide(s, orden, foto) for s in llave)]


def _preparar(senales: dict) -> dict:
    """Las señales de la foto, más los dígitos sueltos del texto."""
    listo = dict(senales)
    listo["texto_digitos"] = "".join(
        c if c.isdigit() else " " for c in senales.get("texto", ""))
    return listo


def adjudicar(fotos: list, ordenes: list) -> list:
    """De quién es cada foto. Función pura: no toca la base ni lee imágenes.

    `fotos` son las señales que devolvió el lector, una por foto. `ordenes`
    son las del lote. Devuelve, en el mismo orden que `fotos`, qué se decidió.
    """
    de_las_ordenes = [(o, senales_de_la_orden(o)) for o in ordenes]

    fallos = []
    for senales in fotos:
        foto = _preparar(senales)
        encajan = [(o, s) for o, s in de_las_ordenes if llaves_que_encajan(s, foto)]
        if len(encajan) > 1:
            # Más de una orden con la misma llave. Puede pasar de verdad: una
            # persona con dos órdenes al mismo beneficiario. No se elige.
            fallos.append({"orden_id": None, "estado": AMBIGUO,
                           "candidatas": [o.get("orden_id") for o, _ in encajan],
                           "motivo": f"La foto encaja con {len(encajan)} órdenes del lote."})
        elif not encajan:
            fallos.append({"orden_id": None, "estado": SIN_ADJUDICAR,
                           "candidatas": [],
                           "motivo": "No se encontró en la foto ningún dato de "
                                     "las órdenes de este lote."})
        else:
            orden, suya = encajan[0]
            monto_ok = bool(suya["monto"]) and suya["monto"] in [
                _digitos(m) for m in foto["montos"]]
            fallos.append({
                "orden_id": orden.get("orden_id"),
                "estado": SEGURO if monto_ok else REVISAR,
                "candidatas": [orden.get("orden_id")],
                "motivo": "" if monto_ok else (
                    "Los datos del beneficiario coinciden, pero el monto de la "
                    "orden no aparece en la foto."),
            })

    return _marcar_los_repetidos(fallos)


def _marcar_los_repetidos(fallos: list) -> list:
    """Dos fotos para la misma orden: ninguna se adjudica.

    Puede ser un pago hecho dos veces, la misma captura subida dos veces, o
    una adjudicación equivocada. Las tres se resuelven mirando, y ninguna se
    resuelve eligiendo una al azar.
    """
    cuantas = {}
    for f in fallos:
        if f["orden_id"]:
            cuantas[f["orden_id"]] = cuantas.get(f["orden_id"], 0) + 1
    for f in fallos:
        if f["orden_id"] and cuantas[f["orden_id"]] > 1:
            f["candidatas"] = [f["orden_id"]]
            f["orden_id"] = None
            f["estado"] = REPETIDO
            f["motivo"] = ("Hay más de una foto para esta misma orden. "
                           "Mirá cuál corresponde y asignala a mano.")
    return fallos


async def _leer_todas(imagenes: list) -> list:
    """Las señales de cada foto, leídas de a varias a la vez.

    El lector es un programa aparte y bloquea el hilo: va en un hilo propio
    para que el resto de la aplicación siga contestando mientras once fotos
    se leen. Si no hay lector, se devuelve vacío para todas y quien llama lo
    convierte en adjudicación manual.
    """
    import base64

    permiso = asyncio.Semaphore(_cuantas_a_la_vez())

    async def _una(imagen):
        crudos = base64.b64decode(imagen.split(",", 1)[1])
        async with permiso:
            return await asyncio.to_thread(lector.leer, crudos)

    try:
        return await asyncio.gather(*[_una(i) for i in imagenes])
    except lector.SinLector as e:
        logger.warning("comprobantes_del_lote: no hay lector en el servidor (%s)", e)
        return None


async def cargar(db, lote_id: str, imagenes: list, *, quien=None, request=None) -> dict:
    """Sube varias fotos de una vez y las reparte entre las órdenes del lote."""
    if not imagenes:
        raise ValueError("No llegó ninguna foto")
    if len(imagenes) > MAXIMO_POR_CARGA:
        raise ValueError(
            f"Son demasiadas fotos de una vez (el tope es {MAXIMO_POR_CARGA}). "
            "Subilas en dos tandas.")

    lote = await db[lotes_de_pago.COLECCION].find_one({"lote_id": lote_id})
    if not lote:
        raise ValueError("Ese lote no existe")
    if lote.get("estado") != lotes_de_pago.ABIERTO:
        raise ValueError("Ese lote ya está cerrado o cancelado")

    # Las fotos se miran por dentro y se les sacan los metadatos ANTES de
    # guardarlas. Una captura del teléfono del agente lleva el modelo y a
    # veces las coordenadas, y eso queda en la base para siempre.
    limpias = [imagen_recibida.limpiar_foto_del_chat(i, campo="El comprobante")
               for i in imagenes]

    ordenes = lote.get("ordenes") or []
    leidas = await _leer_todas(limpias)
    if leidas is None:
        # El renglón NO repite por qué falló el lector. Este texto decía «el
        # servidor no tiene el lector instalado», que era una conjetura —la
        # primera vez que falló de verdad, el lector estaba y lo que faltaba
        # era una pieza del sistema— y salía repetido en cada foto: doce
        # renglones diciendo doce veces lo mismo, y encima equivocado.
        #
        # El motivo real lo da `lector.por_que_no_hay_lector()` una sola vez,
        # arriba de la pantalla. Acá va lo único que le importa a este renglón:
        # que a esta foto hay que darle dueño a mano.
        fallos = [{"orden_id": None, "estado": SIN_LECTOR, "candidatas": [],
                   "motivo": "El lector no pudo leer esta foto. El motivo "
                             "está arriba."} for _ in limpias]
        leidas = [lector.vacio() for _ in limpias]
    else:
        fallos = adjudicar(leidas, ordenes)

    ahora = datetime.now(timezone.utc)
    comprobantes = []
    for imagen, senales, fallo in zip(limpias, leidas, fallos):
        comprobantes.append({
            "comprobante_id": f"cmp_{uuid.uuid4().hex[:12]}",
            "imagen": imagen,
            "subido_en": ahora,
            "subido_por": getattr(quien, "user_id", None),
            # Lo que se leyó se guarda. Cuando una adjudicación salga mal, la
            # pregunta va a ser «¿qué decía la foto?», y sin esto hay que
            # volver a pasarle el lector para saberlo.
            "leido": {k: v for k, v in senales.items() if k != "texto"},
            "orden_id": fallo["orden_id"],
            "estado": fallo["estado"],
            "motivo": fallo["motivo"],
            "candidatas": fallo["candidatas"],
        })

    await db[lotes_de_pago.COLECCION].update_one(
        {"lote_id": lote_id},
        {"$push": {"comprobantes": {"$each": comprobantes}}})

    await _colgar_de_las_ordenes(db, lote, comprobantes)

    resumen = _resumen(comprobantes)
    await auditoria.registrar(
        db, "dinero.lote_comprobantes", quien=quien, request=request,
        objetivo_tipo="lote", objetivo_id=lote_id,
        objetivo_desc=f"{lote.get('numero')}: {len(comprobantes)} comprobante(s)",
        detalle={"resumen": resumen,
                 "adjudicados": [c["orden_id"] for c in comprobantes if c["orden_id"]]})

    logger.info("lote %s: %s comprobante(s) cargados, %s", lote.get("numero"),
                len(comprobantes), resumen)
    return {"lote_id": lote_id, "resumen": resumen,
            "comprobantes": [_para_la_pantalla(c, ordenes) for c in comprobantes]}


def _resumen(comprobantes: list) -> dict:
    cuenta = {}
    for c in comprobantes:
        cuenta[c["estado"]] = cuenta.get(c["estado"], 0) + 1
    return cuenta


def _para_la_pantalla(comprobante: dict, ordenes: list) -> dict:
    """Lo que ve el operador. Sin la imagen: la pide aparte si la quiere ver.

    Una respuesta con once fotos en base64 adentro pesa decenas de megas y
    tarda, y la pantalla necesita la TABLA para poder empezar a trabajar.
    """
    por_id = {o.get("orden_id"): o for o in ordenes}
    orden = por_id.get(comprobante.get("orden_id")) or {}
    return {
        "comprobante_id": comprobante["comprobante_id"],
        "estado": comprobante["estado"],
        "motivo": comprobante["motivo"],
        "orden_id": comprobante.get("orden_id"),
        "display_id": orden.get("display_id"),
        "beneficiario": (orden.get("beneficiario") or {}).get("nombre"),
        "monto": orden.get("monto"),
        "candidatas": comprobante.get("candidatas") or [],
        "leido": comprobante.get("leido") or {},
    }


async def _colgar_de_las_ordenes(db, lote: dict, comprobantes: list):
    """Le agrega a cada orden la foto que le tocó.

    Se agrega a `proof_images`, que es donde ya viven los comprobantes de un
    pago: así la foto se ve desde la orden igual que siempre, sin que ninguna
    pantalla vieja tenga que aprender un campo nuevo.

    Sólo las adjudicadas. Una foto ambigua o sin dueño no se cuelga de
    ninguna orden — se queda en el lote hasta que alguien decida.
    """
    por_id = {o.get("orden_id"): o for o in lote.get("ordenes") or []}
    for c in comprobantes:
        # Alcanza con mirar si tiene orden. Preguntar ADEMAS por el estado
        # sería una segunda guarda que dice lo mismo —ambigua, repetida, sin
        # dueño y sin lector dejan todas `orden_id` en None—, y dos guardas
        # que se tapan entre sí no dejan probada ninguna de las dos. Ya pasó
        # en este repositorio.
        if not c.get("orden_id"):
            continue
        orden = por_id.get(c["orden_id"])
        if not orden:
            continue
        await _agregar_imagen(db, orden, c["imagen"])


async def _agregar_imagen(db, orden: dict, imagen: str) -> bool:
    coleccion, filtro = lotes_de_pago._coleccion_y_filtro(
        db, orden.get("flujo"), orden.get("orden_id"))
    if coleccion is None:
        return False
    resultado = await coleccion.update_one(
        filtro, {"$push": {"proof_images": imagen}})
    return getattr(resultado, "modified_count", 0) == 1


async def _quitar_imagen(db, orden: dict, imagen: str) -> bool:
    coleccion, filtro = lotes_de_pago._coleccion_y_filtro(
        db, orden.get("flujo"), orden.get("orden_id"))
    if coleccion is None:
        return False
    resultado = await coleccion.update_one(
        filtro, {"$pull": {"proof_images": imagen}})
    return getattr(resultado, "modified_count", 0) == 1


async def asignar(db, lote_id: str, comprobante_id: str, orden_id, *,
                  quien=None, request=None) -> dict:
    """Cambia a mano de quién es una foto. `orden_id` en `None` la deja suelta.

    Mover una foto SACA la anterior de la orden que la tenía. Sin eso, cada
    corrección dejaría una foto de más colgada de una orden ajena, que es
    justo el documento equivocado en el expediente equivocado que este módulo
    trata de evitar.
    """
    lote = await db[lotes_de_pago.COLECCION].find_one({"lote_id": lote_id})
    if not lote:
        raise ValueError("Ese lote no existe")
    if lote.get("estado") != lotes_de_pago.ABIERTO:
        raise ValueError("Ese lote ya está cerrado o cancelado")

    comprobantes = lote.get("comprobantes") or []
    actual = next((c for c in comprobantes
                   if c.get("comprobante_id") == comprobante_id), None)
    if not actual:
        raise ValueError("Esa foto no es de este lote")

    ordenes = lote.get("ordenes") or []
    por_id = {o.get("orden_id"): o for o in ordenes}
    if orden_id is not None and orden_id not in por_id:
        raise ValueError("Esa orden no es de este lote")

    if orden_id and any(c.get("orden_id") == orden_id and
                        c.get("comprobante_id") != comprobante_id
                        for c in comprobantes):
        raise ValueError(
            "Esa orden ya tiene una foto asignada. Soltá la otra primero.")

    if actual.get("orden_id") and por_id.get(actual["orden_id"]):
        await _quitar_imagen(db, por_id[actual["orden_id"]], actual["imagen"])
    if orden_id:
        await _agregar_imagen(db, por_id[orden_id], actual["imagen"])

    estado = A_MANO if orden_id else SIN_ADJUDICAR
    motivo = "" if orden_id else "La soltó el operador."
    await db[lotes_de_pago.COLECCION].update_one(
        {"lote_id": lote_id, "comprobantes.comprobante_id": comprobante_id},
        {"$set": {"comprobantes.$.orden_id": orden_id,
                  "comprobantes.$.estado": estado,
                  "comprobantes.$.motivo": motivo,
                  "comprobantes.$.asignado_por": getattr(quien, "user_id", None),
                  "comprobantes.$.asignado_en": datetime.now(timezone.utc)}})

    await auditoria.registrar(
        db, "dinero.lote_comprobante_asignado", quien=quien, request=request,
        objetivo_tipo="lote", objetivo_id=lote_id,
        objetivo_desc=f"{lote.get('numero')}: foto {comprobante_id} → "
                      f"{orden_id or 'sin orden'}",
        detalle={"comprobante_id": comprobante_id,
                 "antes": actual.get("orden_id"), "ahora": orden_id})

    actualizado = dict(actual, orden_id=orden_id, estado=estado, motivo=motivo)
    return _para_la_pantalla(actualizado, ordenes)


async def descartar(db, lote_id: str, comprobante_id: str, motivo: str, *,
                    quien=None, request=None) -> dict:
    """Saca una foto de la pantalla, con el motivo escrito.

    PARA QUE HACE FALTA

        Una foto puede no ser de nadie: un comprobante errado, un cobro que no
        corresponde, o la misma captura subida dos veces porque el lector no
        andaba y el agente reintentó. Hasta ahora no había salida: se quedaba
        en la lista para siempre y el lote no terminaba de resolverse nunca.

    POR QUE SE BORRAN LOS BYTES DE LA FOTO Y NO EL RENGLON

        El renglón queda —con quién la descartó, cuándo y por qué—, porque en
        una pantalla de pagos lo que se saca tiene que poder explicarse después.

        Lo que sí se borra es la imagen. Las fotos viven adentro del documento
        del lote, y un documento de MongoDB no puede pasar de 16 MB: cada foto
        que se queda sin usar le come lugar a las que faltan. Borrar el renglón
        entero escondería el descarte; guardar la imagen de algo que ya se dijo
        que no va, ocupa por nada.

    POR QUE EL MOTIVO ES OBLIGATORIO

        Descartar un comprobante es decir «este pago no está probado por esta
        foto». Sin motivo escrito, el que mire dentro de seis meses no puede
        distinguir un duplicado de un cobro indebido.
    """
    motivo = " ".join(str(motivo or "").split())
    if len(motivo) < LETRAS_DEL_MOTIVO:
        raise ValueError(
            f"Escribí por qué se descarta esta foto (al menos "
            f"{LETRAS_DEL_MOTIVO} letras): duplicada, comprobante errado, "
            "cobro que no corresponde…")
    motivo = motivo[:LARGO_DEL_MOTIVO]

    lote = await db[lotes_de_pago.COLECCION].find_one({"lote_id": lote_id})
    if not lote:
        raise ValueError("Ese lote no existe")
    if lote.get("estado") != lotes_de_pago.ABIERTO:
        raise ValueError("Ese lote ya está cerrado o cancelado")

    comprobantes = lote.get("comprobantes") or []
    actual = next((c for c in comprobantes
                   if c.get("comprobante_id") == comprobante_id), None)
    if not actual:
        raise ValueError("Esa foto no es de este lote")
    if actual.get("estado") == DESCARTADO:
        raise ValueError("Esa foto ya estaba descartada")

    # Si estaba colgada de una orden, se despega: dejarla sería dar por probado
    # un pago con una foto que acaba de decirse que no sirve.
    por_id = {o.get("orden_id"): o for o in lote.get("ordenes") or []}
    if actual.get("orden_id") and por_id.get(actual["orden_id"]):
        await _quitar_imagen(db, por_id[actual["orden_id"]], actual["imagen"])

    await db[lotes_de_pago.COLECCION].update_one(
        {"lote_id": lote_id, "comprobantes.comprobante_id": comprobante_id},
        {"$set": {"comprobantes.$.estado": DESCARTADO,
                  "comprobantes.$.orden_id": None,
                  "comprobantes.$.motivo": motivo,
                  "comprobantes.$.imagen": "",
                  "comprobantes.$.descartado_por": getattr(quien, "user_id", None),
                  "comprobantes.$.descartado_en": datetime.now(timezone.utc)}})

    await auditoria.registrar(
        db, "dinero.lote_comprobante_descartado", quien=quien, request=request,
        objetivo_tipo="lote", objetivo_id=lote_id,
        objetivo_desc=f"{lote.get('numero')}: foto {comprobante_id} descartada",
        detalle={"comprobante_id": comprobante_id,
                 "estaba_en": actual.get("orden_id"), "motivo": motivo})

    return {"comprobante_id": comprobante_id, "estado": DESCARTADO,
            "motivo": motivo}


async def listar(db, lote_id: str) -> dict:
    """Las fotos de un lote y las órdenes a las que se pueden asignar."""
    lote = await db[lotes_de_pago.COLECCION].find_one(
        {"lote_id": lote_id},
        # Sin `comprobantes.imagen`: son megas por foto y la tabla no las usa.
        {"_id": 0, "lote_id": 1, "numero": 1, "estado": 1, "ordenes": 1,
         "comprobantes.comprobante_id": 1, "comprobantes.estado": 1,
         "comprobantes.motivo": 1, "comprobantes.orden_id": 1,
         "comprobantes.candidatas": 1, "comprobantes.leido": 1})
    if not lote:
        raise ValueError("Ese lote no existe")
    ordenes = lote.get("ordenes") or []
    por_que_no = lector.por_que_no_hay_lector()

    # Las descartadas no vuelven a la pantalla. Es el punto de descartarlas: el
    # agente dijo que esa foto no va, y verla de nuevo en cada recarga es
    # trabajo que ya hizo. Quedan contadas —y enteras en la auditoría— porque
    # esconder cuántas se sacaron sería otra cosa.
    todas = lote.get("comprobantes") or []
    vivas = [c for c in todas if c.get("estado") != DESCARTADO]
    comprobantes = [_para_la_pantalla(c, ordenes) for c in vivas]

    # De qué orden es cada foto y en qué estado quedó. La pantalla necesita las
    # dos cosas juntas para separar «listas para registrar» de «las mira una
    # persona», y sin esto tendría que cruzarlas a mano y repetir la regla.
    estado_por_orden = {c["orden_id"]: c["estado"]
                        for c in comprobantes if c["orden_id"]}
    return {
        "lote_id": lote["lote_id"],
        "numero": lote.get("numero"),
        "estado": lote.get("estado"),
        # El motivo va junto al sí/no. Cuando falla, «no está instalado» era
        # una conjetura: podía ser eso, o que estuviera en otro lado, o que le
        # faltara el idioma. Lo lee un super administrador, no un cliente.
        "hay_lector": not por_que_no,
        "por_que_no_hay_lector": por_que_no,
        "idiomas_del_lector": lector.idiomas_instalados() if not por_que_no else [],
        "comprobantes": comprobantes,
        "descartadas": len(todas) - len(vivas),
        "ordenes": [{"orden_id": o.get("orden_id"),
                     "display_id": o.get("display_id"),
                     "beneficiario": (o.get("beneficiario") or {}).get("nombre"),
                     "monto": o.get("monto"),
                     "tiene_comprobante": o.get("orden_id") in estado_por_orden,
                     "estado_comprobante": estado_por_orden.get(o.get("orden_id")),
                     # La regla de qué alcanza para registrar vive acá, al lado
                     # de los estados, y no en la pantalla. Si mañana aparece un
                     # estado nuevo, se agrega en un solo lugar; repartida, la
                     # pantalla lo daría por bueno sin que nadie se entere.
                     "listo_para_registrar": estado_por_orden.get(o.get("orden_id"))
                     in LISTOS_PARA_REGISTRAR}
                    for o in ordenes],
        "resumen": _resumen(vivas),
    }


async def imagen(db, lote_id: str, comprobante_id: str) -> str:
    """La foto, para mirarla. Se pide de a una y sólo cuando se abre."""
    lote = await db[lotes_de_pago.COLECCION].find_one(
        {"lote_id": lote_id}, {"_id": 0, "comprobantes": 1})
    if not lote:
        raise ValueError("Ese lote no existe")
    for c in lote.get("comprobantes") or []:
        if c.get("comprobante_id") == comprobante_id:
            return c.get("imagen") or ""
    raise ValueError("Esa foto no es de este lote")
