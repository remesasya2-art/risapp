"""
services/envios_retiro.py — A nombre de quien y a donde despacha el usuario.

QUE PROBLEMA RESUELVE
    El usuario despacha su paquete a una agencia de Pacaraima. Esa caja tiene que
    llegar rotulada de forma que el equipo pueda retirarla en el mostrador: con
    la razon social, con el nombre de la persona autorizada, y con la direccion
    exacta de la agencia. Este modulo arma ese bloque y lo devuelve como texto
    para copiar.

SE CONGELA EN EL ENVIO, NO SE LEE EN VIVO
    Es la diferencia con la cuenta bancaria del transportista (§4.6), que
    deliberadamente NO se congela. Son dos casos opuestos y conviene tener claro
    por que:

      - La CUENTA BANCARIA se lee en vivo porque el transportista la puede
        cambiar sin avisar, y pagarle a una cuenta congelada es plata perdida.
      - El BLOQUE DE DESPACHO se congela porque ya esta impreso en una etiqueta
        pegada a una caja que esta viajando. Cambiar la nomina hoy no puede
        cambiar el nombre de un paquete que ya salio, porque el mostrador va a
        comparar la etiqueta contra un documento y no contra la base de datos.

    Por eso la cola de retiro se agrupa POR ESE NOMBRE: quien viaja a Pacaraima
    necesita saber cuales puede reclamar de verdad.

SI NO HAY NADIE DE TURNO, NO SE ROMPE
    Cae al nombre de la empresa sola y avisa. Un problema interno de nomina no
    puede dejar a un usuario sin poder despachar; y una razon social sin A/C
    igual se retira, solo que el mostrador no sabe a quien llamar.

LA PLANTILLA NO SE RENDERIZA CON str.format
    Ver `_render`. La plantilla la escribe el super administrador y el valor
    `razon_social` viene de la base: con `.format` una plantilla que dijera
    `{razon_social.__class__.__mro__}` devuelve objetos internos de Python, y un
    `{` suelto tira KeyError adentro de la funcion que arma la cotizacion. Se
    reemplazan tokens de una lista blanca y se acabo.
"""

import logging
import re
import uuid
from datetime import datetime, time, timedelta, timezone

from services.referencias import _activo as activo_de

logger = logging.getLogger(__name__)

SETTING_PUNTO_ORIGEN = "envios_punto_origen"

# La nomina son unidades: dos o tres activos, mas los historicos que nunca se
# borran. El tope existe para que la consulta no crezca sola, y es holgado a
# proposito — si el designado cayera fuera de la ventana, TODAS las cotizaciones
# nuevas se rotularian con un suplente y el unico indicio seria un warning.
_NOMINA_MAX = 1000


def _orden(colaborador: dict) -> tuple:
    """El desempate, para que quien sale rotulado no dependa de Mongo.

    `find({})` sin `sort` devuelve el orden natural, que no esta garantizado y
    cambia cuando un documento se reescribe. Dos cotizaciones del mismo dia
    podian congelarse con nombres distintos sin que nadie tocara nada — y como la
    cola de retiro se agrupa POR ESE NOMBRE, el que viaja a Pacaraima podia
    reclamar la mitad de las cajas y tener que volver con otra persona.
    """
    creado = _fecha(colaborador.get("creado_at"))[0]
    return (creado is None, creado or datetime.min.replace(tzinfo=timezone.utc),
            str(colaborador.get("colaborador_id") or ""))

# Los unicos tokens que la plantilla puede usar. Uno que no este aca se deja tal
# cual en el texto, a la vista: que se vea "{telefono}" en la vista previa es
# como el super administrador se entera de que ese dato no existe. Borrarlo en
# silencio produciria una direccion incompleta que parece completa.
TOKENS = ("razon_social", "retirador_nombre", "linea_agencia", "agencia",
          "caixa_postal", "direccion", "ciudad", "uf", "cep")

_TOKEN = re.compile(r"\{([a-z_]{1,40})\}")

PLANTILLA_POR_DEFECTO = ("{razon_social}\n"
                         "A/C {retirador_nombre}\n"
                         "{linea_agencia}\n"
                         "{ciudad} - {uf}\n"
                         "CEP {cep}")


async def _db(db=None):
    if db is not None:
        return db
    from database import db as real
    return real


def _texto(valor) -> str:
    return "" if valor is None else str(valor).strip()


# "A/C" o "a/c" al final de una linea, con o sin coma o guion delante, cuando el
# nombre que iba despues no existe. Se saca el rotulo, no la linea: la linea
# suele traer tambien la razon social.
_AC_COLGADO = re.compile(r"[\s,;\-–—]*\ba/?c\.?\s*$", re.IGNORECASE)


def _render(plantilla: str, valores: dict) -> str:
    """La plantilla con sus tokens reemplazados. Nunca lanza.

    NO usa str.format, a proposito. `.format` sobre una plantilla editable desde
    el panel permite `{razon_social.__class__.__mro__[1].__subclasses__}` —el
    camino clasico para leer internals de Python desde un string de
    configuracion— y ademas convierte una llave suelta en un KeyError adentro de
    la cotizacion. Acá se reemplaza contra una lista blanca y lo demas queda como
    texto literal.
    """
    def uno(m):
        clave = m.group(1)
        if clave not in TOKENS:
            return m.group(0)          # se deja visible: es un aviso, no un dato
        return _texto(valores.get(clave))

    try:
        texto = _TOKEN.sub(uno, plantilla or "")
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo renderizar la dirección de despacho: {e}")
        return ""
    # Una linea que quedo vacia porque su unico token no tenia valor no es una
    # linea: es un renglon en blanco en el medio de una direccion, y el mostrador
    # lo lee como un dato faltante. Y un "A/C" sin nombre detras es peor que
    # nada, asi que se limpia el rotulo — pero SOLO el rotulo: borrar la linea
    # entera, que fue el primer intento, se llevaba puesta la razon social cuando
    # la plantilla las ponia juntas, y dejaba la caja sin nada contra que
    # comparar en el mostrador.
    limpias = []
    for linea in texto.split("\n"):
        linea = _AC_COLGADO.sub("", linea.rstrip())
        if linea.strip():
            limpias.append(linea)
    return "\n".join(limpias)


def linea_agencia(punto: dict) -> str:
    """La linea que ubica el paquete dentro de la agencia.

    Depende de la modalidad porque no son intercambiables: una Caixa Postal tiene
    numero y una Posta Restante no, y poner "Caixa Postal" sin numero manda al
    usuario a un casillero que no existe.
    """
    punto = punto or {}
    agencia = _texto(punto.get("nombre"))
    modalidad = _texto(punto.get("modalidad")) or "caixa_postal"

    if modalidad == "caixa_postal":
        caja = _texto(punto.get("caixa_postal"))
        cabeza = f"Caixa Postal {caja}" if caja else "Caixa Postal"
    elif modalidad == "posta_restante":
        cabeza = "Posta Restante"
    else:
        cabeza = _texto(punto.get("direccion"))

    return " - ".join([p for p in (cabeza, agencia) if p])


def _vigente(colaborador: dict, ahora: datetime) -> bool:
    """Activo Y con la autorización vigente hoy.

    Las dos condiciones, no una: un colaborador activo con la autorización
    vencida no puede retirar nada, y enterarse de eso en el mostrador es
    enterarse con el paquete adentro.

    ACA SE FALLA CERRADO, al revés que en el resto del módulo. Una fecha de
    vencimiento presente pero ilegible —`"31/12/2025"` tipeado a mano, un epoch
    que dejó un script— NO es "sin vencimiento": es un dato que no se pudo leer,
    y leerlo como permiso ilimitado es el único error de este archivo que termina
    con una caja retenida en el mostrador. Ausente sí es sin vencimiento;
    ilegible no.
    """
    if not colaborador or not activo_de(colaborador):
        return False

    desde, desde_legible = _fecha(colaborador.get("autorizado_desde"))
    hasta, hasta_legible = _fecha(colaborador.get("autorizado_hasta"))
    if not desde_legible or not hasta_legible:
        logger.warning(
            f"envios: {colaborador.get('colaborador_id')} tiene una fecha de autorización "
            f"que no se puede leer; se lo trata como no vigente")
        return False

    if desde is not None and desde > ahora:
        return False
    if hasta is not None and _fin_del_dia(hasta) < ahora:
        return False
    return True


def _fin_del_dia(momento: datetime) -> datetime:
    """"Autorizado hasta el 31/12" incluye el 31 entero.

    El formulario manda una fecha sin hora y Pydantic la convierte en medianoche.
    Cortando en ese instante se pierde el último día completo: con la ficha
    diciendo "hasta el 31", el colaborador dejaba de poder retirar a las 20 h del
    30, hora de Roraima. Una fecha sin hora es un día, no un instante.
    """
    if (momento.hour, momento.minute, momento.second, momento.microsecond) != (0, 0, 0, 0):
        return momento
    return datetime.combine(momento.date(), time.max, tzinfo=momento.tzinfo)


def _fecha(valor) -> tuple[datetime | None, bool]:
    """(fecha, se_pudo_leer). Ausente se lee bien y vale None."""
    if valor is None or valor == "":
        return None, True
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
        except ValueError:
            return None, False
    if not isinstance(valor, datetime):
        return None, False
    return (valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor), True


async def retirador_de_turno(punto: dict, db=None, ahora=None) -> tuple[dict | None, str]:
    """(colaborador, por qué). Nunca lanza y nunca deja la cotización sin salida.

    El motivo importa tanto como el colaborador, porque es lo que le dice al
    super administrador qué arreglar:
        designado          el que está marcado de turno, y puede retirar
        suplente           el designado no sirve hoy; se usó otro de la nómina
        sin_nomina         no hay ningún colaborador vigente
        sin_designar       hay nómina pero nadie marcado; se usó el primero
        error              la base no respondió
    """
    ahora = ahora or datetime.now(timezone.utc)
    try:
        base = await _db(db)
        filas = await base.colaboradores_retiro.find({}, {"_id": 0}).to_list(_NOMINA_MAX)
    except Exception as e:
        logger.warning(f"envios: no se pudo leer la nómina de retiro: {e}")
        return None, "error"

    # El filtro va en Python, no en la query: `{"activo": True}` no matchea un 1
    # ni un "true", y las fechas guardadas como texto nunca matchean un $lte.
    vigentes = sorted((c for c in (filas or []) if _vigente(c, ahora)), key=_orden)
    if not vigentes:
        return None, "sin_nomina"

    designado_id = _texto((punto or {}).get("retirador_activo_id"))
    if designado_id:
        for c in vigentes:
            if _texto(c.get("colaborador_id")) == designado_id:
                return c, "designado"
        # Está designado alguien que hoy no puede retirar: de licencia, dado de
        # baja o con la autorización vencida. Se sigue operando con otro, pero el
        # motivo tiene que llegar al panel.
        logger.warning(
            f"envios: el retirador designado {designado_id} no está vigente; "
            f"se usa un suplente de la nómina")
        return vigentes[0], "suplente"

    return vigentes[0], "sin_designar"


async def bloque_de_despacho(db=None, ahora=None) -> dict:
    """A dónde y a nombre de quién despacha el usuario. Nunca lanza.

    Es lo que se congela en el envío al cotizar. Devuelve siempre las mismas
    claves; cuando no se puede armar, `disponible` es False y `faltantes` dice
    qué le falta al panel — sin eso, la pantalla mostraría una dirección a medias
    y alguien despacharía una caja a la nada.
    """
    ahora = ahora or datetime.now(timezone.utc)
    punto, faltantes = await _punto_origen(db=db)
    if faltantes:
        return {"disponible": False, "faltantes": faltantes}

    colaborador, motivo = await retirador_de_turno(punto, db=db, ahora=ahora)
    if motivo == "error":
        # NO se congela un bloque sin nombre por un corte de base. La regla de
        # "un problema interno no puede dejar al usuario sin despachar" es sobre
        # la nómina VACÍA, que es un estado real y estable; un failover de dos
        # segundos es otra cosa, y congelarlo deja una caja rotulada sin A/C para
        # siempre, indistinguible en la cola de un `sin_nomina` legítimo.
        return {"disponible": False,
                "faltantes": ["No se pudo leer la nómina de retiro. Reintentá en un momento."]}

    razon_social = _texto(punto.get("razon_social"))
    nombre = _texto((colaborador or {}).get("nombre"))

    valores = {
        "razon_social": razon_social,
        "retirador_nombre": nombre,
        "linea_agencia": linea_agencia(punto),
        "agencia": _texto(punto.get("nombre")),
        "caixa_postal": _texto(punto.get("caixa_postal")),
        "direccion": _texto(punto.get("direccion")),
        "ciudad": _texto(punto.get("ciudad")),
        "uf": _texto(punto.get("uf")),
        "cep": _cep_legible(punto.get("cep")),
    }
    plantilla = _texto(punto.get("plantilla_direccion")) or PLANTILLA_POR_DEFECTO

    return {
        "disponible": True,
        "faltantes": [],
        "retirador_id": _texto((colaborador or {}).get("colaborador_id")) or None,
        "retirador_nombre": nombre or None,
        "retirador_motivo": motivo,
        "destinatario": f"{razon_social} - A/C {nombre}" if nombre else razon_social,
        "razon_social": razon_social,
        "agencia": valores["agencia"],
        "linea_agencia": valores["linea_agencia"],
        "modalidad": _texto(punto.get("modalidad")) or "caixa_postal",
        "caixa_postal": valores["caixa_postal"] or None,
        "ciudad": valores["ciudad"],
        "uf": valores["uf"],
        "cep": valores["cep"],
        "texto_copiable": _render(plantilla, valores),
        "congelado_at": ahora,
    }


def _cep_legible(valor) -> str:
    """El CEP como se escribe en un sobre: 69355-000.

    Se guarda sin guion —el esquema lo normaliza para poder compararlo— pero lo
    que se copia en una etiqueta se lee mejor con el guion, y el mostrador está
    acostumbrado a esa forma.
    """
    limpio = _texto(valor).replace("-", "")
    return f"{limpio[:5]}-{limpio[5:]}" if len(limpio) == 8 and limpio.isdigit() else _texto(valor)


async def _punto_origen(db=None) -> tuple[dict, list[str]]:
    try:
        base = await _db(db)
        doc = await base.app_settings.find_one({"setting_id": SETTING_PUNTO_ORIGEN},
                                               {"_id": 0}) or {}
    except Exception as e:
        logger.warning(f"envios: no se pudo leer el punto de origen: {e}")
        return {}, ["No se pudo leer la configuración del punto de origen."]

    punto = doc.get("valor") if isinstance(doc.get("valor"), dict) else doc
    faltantes = []
    if not _texto(punto.get("razon_social")):
        faltantes.append("Falta la razón social a nombre de la que se rotulan los paquetes.")
    if not _texto(punto.get("nombre")):
        faltantes.append("Falta la agencia de Pacaraima a la que despacha el usuario.")
    if not _texto(punto.get("cep")):
        faltantes.append("Falta el CEP de la agencia de destino en Brasil.")
    return punto, faltantes


def nuevo_colaborador_id() -> str:
    return f"col_{uuid.uuid4().hex[:8]}"
