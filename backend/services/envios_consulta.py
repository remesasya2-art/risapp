"""
services/envios_consulta.py — Lo que el usuario ve de sus propios envios.

DOS PANTALLAS
    La LISTA, que contesta "en que anda cada uno". El DETALLE, que contesta "que
    pasa con este" — con su linea de tiempo, su deuda si la tiene, y la direccion
    a la que tiene que despachar.

ACA SI VAN LOS DATOS DEL USUARIO
    Es la diferencia con el seguimiento publico, y conviene tenerla clara porque
    los dos modulos muestran el mismo envio. El seguimiento es un link que se
    reenvia; esto esta detras de la sesion y le pertenece a quien lo pide. Le
    mostramos el nombre del destinatario porque es el que el escribio.

    Lo que NO sale ni aca: los diagnosticos internos, el margen, lo que cobra
    cada transportista de referencia como si fuera un precio, y el
    `retirador_id`. Nada de eso es del usuario.
"""

import logging

from services.envios_estados import partidas_impagas
from services.money import to_decimal

logger = logging.getLogger(__name__)

POR_PAGINA = 20
POR_PAGINA_MAX = 50

# Con 50 por pagina son 5.000 envios: mas que los que va a tener nadie.
PAGINA_MAX = 100

# Los campos que la LISTA necesita. Lista blanca, por lo mismo que el
# seguimiento: un campo nuevo del envio no puede aparecer solo en una respuesta.
_PROYECCION_LISTA = {
    "_id": 0, "envio_id": 1, "display_id": 1, "estado": 1, "created_at": 1,
    "destino.ciudad": 1, "destino.estado_ve": 1, "destino.agencia_nombre": 1,
    "destino.destinatario.nombre": 1, "cotizacion.total_estimado_ris": 1,
    "cotizacion.total_final_ris": 1, "cotizacion.es_estimado": 1,
    "cotizacion.moneda": 1, "cotizacion.vence_at": 1, "cobros": 1,
    "origen.codigo_objeto": 1, "origen.guarda_vence_at": 1,
}


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


async def listar(usuario, *, pagina: int = 1, por_pagina: int = POR_PAGINA,
                 estado: str = None, db=None) -> dict:
    """Los envíos del usuario, del más nuevo al más viejo. Nunca lanza."""
    user_id = getattr(usuario, "user_id", None)
    try:
        pagina = max(1, int(pagina or 1))
        por_pagina = max(1, min(int(por_pagina or POR_PAGINA), POR_PAGINA_MAX))
    except (TypeError, ValueError):
        pagina, por_pagina = 1, POR_PAGINA
    # Y un tope a la PAGINA. Los dos llegan por la URL, y con `to_list(pagina *
    # por_pagina + 1)` una pagina de un millon le pide cincuenta millones de
    # documentos a la base. Nadie tiene mil paginas de envios; el que las pida
    # esta probando otra cosa.
    pagina = min(pagina, PAGINA_MAX)
    filtro = {"user_id": user_id}
    if estado:
        filtro["estado"] = str(estado)[:40]

    try:
        base = await _db(db)
        # Se pide UNO MÁS de los que se muestran: es la forma barata de saber si
        # hay página siguiente sin contar la colección entera en cada request.
        filas = await base.envios.find(filtro, _PROYECCION_LISTA) \
            .sort("created_at", -1).to_list(pagina * por_pagina + 1)
    except Exception as e:
        logger.warning(f"envios: no se pudo listar los envíos de {user_id}: {e}")
        return {"envios": [], "pagina": pagina, "hay_mas": False, "degradado": True}

    desde = (pagina - 1) * por_pagina
    ventana = (filas or [])[desde:desde + por_pagina]
    # Cada fila se arma por separado: un documento a medio migrar —con
    # `destino.destinatario` como texto, por ejemplo— no puede llevarse puesta la
    # lista entera del usuario.
    return {
        "envios": [f for f in (_fila_segura(e) for e in ventana) if f],
        "pagina": pagina,
        "hay_mas": len(filas or []) > desde + por_pagina,
        "degradado": False,
    }


def _fila_segura(envio: dict):
    try:
        return _fila(envio)
    except Exception as e:
        logger.warning(
            f"envios: no se pudo mostrar {envio.get('envio_id')} en la lista: {e}")
        return None


def _fila(envio: dict) -> dict:
    cot = envio.get("cotizacion") or {}
    impagas = partidas_impagas(envio)
    return {
        "envio_id": envio.get("envio_id"),
        "display_id": envio.get("display_id"),
        "estado": envio.get("estado"),
        "creado_at": envio.get("created_at"),
        "destino": {
            "ciudad": (envio.get("destino") or {}).get("ciudad"),
            "estado": (envio.get("destino") or {}).get("estado_ve"),
            "agencia": (envio.get("destino") or {}).get("agencia_nombre"),
            "destinatario": ((envio.get("destino") or {}).get("destinatario")
                             or {}).get("nombre"),
        },
        "es_estimado": bool(cot.get("es_estimado", True)),
        "total_ris": cot.get("total_final_ris") or cot.get("total_estimado_ris"),
        "moneda": cot.get("moneda") or "RIS",
        "codigo_objeto": (envio.get("origen") or {}).get("codigo_objeto"),
        # Lo primero que el usuario quiere saber cuando abre la lista: si hay
        # algo que hacer. Se calcula acá y no en la pantalla, porque la regla de
        # qué cuenta como impago vive en el backend.
        "hay_algo_que_pagar": bool(impagas),
        "a_pagar_ris": str(_deuda(envio)) if impagas else None,
        "vence_at": cot.get("vence_at"),
    }


def _deuda(envio: dict):
    cobros = (envio or {}).get("cobros") or {}
    total = to_decimal(0)
    for partida in partidas_impagas(envio):
        total += to_decimal((cobros.get(partida) or {}).get("monto_ris"))
    return total


async def detalle(usuario, envio_id: str, db=None) -> dict | None:
    """Un envío del usuario, con su línea de tiempo. None si no es suyo.

    El mismo None para "no existe" y para "es de otro": distinguirlos convierte
    la ruta en un oráculo que confirma qué identificadores existen.
    """
    from services.envios_eventos import historial
    from services.envios_seguimiento import PUBLICO

    user_id = getattr(usuario, "user_id", None)
    try:
        base = await _db(db)
        envio = await base.envios.find_one(
            {"envio_id": envio_id, "user_id": user_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"envios: no se pudo leer {envio_id}: {e}")
        return None
    if not envio:
        return None

    try:
        return await _detalle(envio, base)
    except Exception as e:
        logger.warning(f"envios: no se pudo armar el detalle de {envio_id}: {e}")
        return None


async def _detalle(envio: dict, base) -> dict:
    from services.envios_eventos import historial
    from services.envios_seguimiento import PUBLICO

    envio_id = envio.get("envio_id")
    eventos = await historial(envio_id, db=base)
    cot = envio.get("cotizacion") or {}
    despacho = envio.get("destino_brasil") or {}
    origen = envio.get("origen") or {}

    return {
        **_fila(envio),
        "paquete": {
            "declarado": _medidas((envio.get("paquete") or {}).get("declarado")),
            # Lista blanca, igual que el resto del módulo. El bloque `verificado`
            # lleva `verificado_por` —el user_id del OPERADOR que pesó— y salía
            # entero al navegador del usuario. No lo renderizaba ninguna
            # pantalla, que es la peor forma de filtrar un dato: la que nadie ve.
            "verificado": _medidas((envio.get("paquete") or {}).get("verificado")),
            "contenido": (envio.get("paquete") or {}).get("contenido_descripcion"),
        },
        "modalidad_flete": envio.get("modalidad_flete"),
        # La dirección congelada: es la que el usuario tiene que usar, y tiene
        # que decir lo mismo que dijo cuando la leyó.
        "retiro": {k: v for k, v in despacho.items()
                   if k not in ("retirador_id", "retirador_motivo", "congelado_at")},
        "comprobante": {
            "codigo_objeto": origen.get("codigo_objeto"),
            "posteado_at": origen.get("posteado_at"),
            "foto_asset_id": origen.get("comprobante_asset_id"),
            "verificado_at": (origen.get("verificado") or {}).get("at"),
        } if origen.get("codigo_objeto") else None,
        "cobros": _cobros_visibles(envio),
        # La versión de términos congelada al cotizar.
        #
        # La pantalla de detalle la necesita para poder CONFIRMAR una cotización
        # que quedó a medias: `envios_crear` compara la versión que la pantalla
        # dice haber mostrado contra ésta, y si no coinciden frena. Sin el campo
        # acá, la única forma de confirmar desde el detalle sería no mandarla —
        # que es saltearse la comprobación, no cumplirla.
        "terminos_version": cot.get("terminos_version"),
        "tracking_token": envio.get("tracking_token"),
        "guia_transportista": (envio.get("entrega") or {}).get("guia"),
        "timeline": [
            {"estado": e.get("a_estado"),
             "titulo": PUBLICO.get(e.get("a_estado"), ("", ""))[0],
             "at": e.get("created_at")}
            for e in eventos or [] if e.get("a_estado") in PUBLICO
        ],
    }


_MEDIDAS = ("peso_kg", "largo_cm", "ancho_cm", "alto_cm", "valor_declarado")


def _medidas(bloque) -> dict | None:
    """Solo las medidas. Nada de quién las tomó ni cuándo."""
    if not isinstance(bloque, dict) or not bloque:
        return None
    return {k: bloque.get(k) for k in _MEDIDAS if bloque.get(k) is not None}


def _cobros_visibles(envio: dict) -> list[dict]:
    """Las partidas, con lo que el usuario necesita: cuánto y si está pago.

    NO sale el desglose interno del cálculo. Al usuario le importa qué le
    cobraron y por qué en una línea, no el margen ni el multiplicador de
    temporada — que además, mostrados sueltos, invitan a discutir el precio de
    una tabla que ya aceptó.
    """
    cobros = (envio or {}).get("cobros") or {}
    salida = []
    for partida in ("inicial", "ajuste"):
        doc = cobros.get(partida)
        if not isinstance(doc, dict) or not doc:
            continue
        salida.append({
            "partida": partida,
            "concepto": ("Servicio de traslado" if partida == "inicial"
                         else "Ajuste por el peso real"),
            "monto_ris": str(to_decimal(doc.get("monto_ris"))),
            "estado": "pagado" if doc.get("estado") == "pagado" else "pendiente",
            "pagado_at": doc.get("pagado_at"),
        })
    devolucion = cobros.get("devolucion")
    if isinstance(devolucion, dict) and devolucion:
        salida.append({
            "partida": "devolucion",
            "concepto": "Devolución por el peso real",
            "monto_ris": str(to_decimal(devolucion.get("monto_ris"))),
            "estado": "acreditado", "pagado_at": devolucion.get("acreditado_at"),
        })
    return salida
