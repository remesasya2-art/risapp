"""
routes/envios_admin.py — El panel de configuración del módulo de envíos.

QUE SE ADMINISTRA ACA
    Todo lo que un día puede querer cambiarse sin abrir el repositorio: los
    transportistas y sus reglas, sus agencias, y los bloques de operación,
    contenido y punto de origen. Los precios del servicio propio tienen su propia
    pantalla, con simulador y versionado, y llegan en el PR siguiente.

    Lo que NO se administra: la mecánica. Cómo se calcula un peso volumétrico,
    qué transiciones de estado son válidas, cómo se debita un saldo. Eso es
    lógica, cambia con un cambio de diseño y pertenece al repositorio con sus
    tests.

QUIEN ESCRIBE
    Solo el super administrador. El operador lee lo que necesita para trabajar y
    no puede cambiar a dónde va la plata — es la separación que hace que cargar
    el monto de un flete y cambiar la cuenta que lo recibe sean dos permisos
    distintos (§4.6).

NADA SE BORRA, TODO SE DESACTIVA
    Transportistas, agencias, colaboradores. El historial de envíos apunta a esas
    filas: borrar una es dejar envíos viejos apuntando al vacío, y el día que
    alguien abra uno para responder un reclamo, no va a haber a qué mirar.
"""

import csv
import io
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Literal, Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException,
                     UploadFile)
from fastapi.responses import Response
from pydantic import BaseModel, Field

from database import db
from routes.dependencies import (get_admin_user, get_crm_user,
                                 get_super_admin)
from models.user import User
from models.envios_config import (Transportista, Agencia, CuentaBancaria,
                                  Colaborador, ConfigPuntoOrigen, ESQUEMAS)
from models.envios_tarifa import TarifaEnvio, TarifaBorrador, CajaDePrueba
from services import (envios_catalogo, envios_comprobante, envios_config,
                      envios_operacion, envios_origenes, envios_rentabilidad,
                      envios_retiro, envios_tarifa_editor)
from services.envios_archivos import (MIGRACION_LOTE_MAX,
                                      MIGRACION_LOTE_POR_DEFECTO)
from services.envios_catalogo import invalidar_cache
from services.envios_tarifas import validar_tarifa

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/envios", tags=["envios-admin"])


# Lo que NUNCA sale de una ficha de la nomina hacia un log. El CPF y el telefono
# existen para la autorizacion ante el transportista y se quedan del lado
# interno: el log de auditoria lo lee mas gente de la que puede editar la nomina,
# y una copia del documento ahi es una copia del dato sensible en un lugar con
# menos control que el original.
async def _ya_esta_en_la_nomina(ficha: dict) -> bool:
    """Misma persona: el mismo CPF, o el mismo nombre si no hay CPF cargado."""
    cpf = (ficha.get("cpf") or "").strip()
    filtro = {"cpf": cpf} if cpf else {"nombre": ficha.get("nombre")}
    try:
        return await db.colaboradores_retiro.find_one(filtro, {"_id": 1}) is not None
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo chequear duplicados en la nómina: {e}")
        return False


def _sin_datos_personales(ficha: dict) -> dict:
    return {k: v for k, v in (ficha or {}).items() if k not in ("cpf", "telefono")}


def _error(errores: list[str]) -> HTTPException:
    return HTTPException(status_code=400, detail=" ".join(errores))


# ─── La portada: qué falta para poder operar ──────────────────────────────

@router.get("/estado")
async def estado_del_modulo(admin: User = Depends(get_super_admin)):
    """El checklist de puesta en marcha, en el orden en que hay que cargarlo.

    `GET /envios/limites` contesta `disponible: false` y **no dice por qué**: el
    diagnóstico de configuración es interno. Esta es la otra mitad, del lado de
    adentro, para que la primera señal de que falta cargar algo no sea una
    cotización que falla en la cara de un usuario.
    """
    from services import envios_puesta_en_marcha
    try:
        return await envios_puesta_en_marcha.estado()
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: no se pudo armar el estado del módulo: {e}")
        raise HTTPException(
            503, "No se pudo leer el estado del módulo. Probá de nuevo.")


# ─── Bloques de configuración ─────────────────────────────────────────────

@router.get("/config")
async def listar_bloques(admin: User = Depends(get_super_admin)):
    """Qué bloques existen y cuáles ya tienen valor. Es la portada del panel."""
    salida = {}
    for bloque in ESQUEMAS:
        salida[bloque] = await envios_config.leer(bloque) or {}
    return {"bloques": salida, "disponibles": sorted(ESQUEMAS)}


@router.get("/config/{bloque}")
async def leer_bloque(bloque: str, admin: User = Depends(get_super_admin)):
    if bloque not in ESQUEMAS:
        raise HTTPException(404, f"Bloque de configuración desconocido: {bloque}")
    return await envios_config.leer(bloque) or {}


@router.put("/config/{bloque}")
async def guardar_bloque(bloque: str, datos: dict,
                         admin: User = Depends(get_super_admin)):
    """Valida, guarda, audita e invalida el caché. En ese orden.

    Devuelve el valor EFECTIVO, no el que llegó: la pantalla lo muestra tal cual
    y así el admin ve lo que quedó guardado, con sus defaults, en vez de lo que
    él tipeó.
    """
    validado, errores = await envios_config.guardar(
        bloque, datos, admin, invalidar=invalidar_cache)
    if errores:
        raise _error(errores)
    return {"ok": True, "bloque": bloque, "valor": validado}


# ─── Transportistas ───────────────────────────────────────────────────────

@router.get("/transportistas")
async def listar_transportistas(admin: User = Depends(get_crm_user)):
    """El operador también lee: necesita saber a quién le está entregando."""
    filas = await db.transportistas.find({}, {"_id": 0}).sort("orden", 1).to_list(None)
    return {"transportistas": [_sin_cuenta(t) for t in filas]}


def _sin_cuenta(t: dict) -> dict:
    """La cuenta bancaria no viaja en un listado. Se ve al abrir la ficha, y
    enmascarada: un listado se comparte en pantalla mucho más seguido."""
    salida = dict(t)
    cuenta = salida.get("cuenta_bancaria")
    if cuenta:
        salida["cuenta_bancaria"] = {"banco": cuenta.get("banco"),
                                     "numero": "****" + str(cuenta.get("numero", ""))[-4:]}
    return salida


@router.post("/transportistas")
async def crear_transportista(datos: Transportista,
                              admin: User = Depends(get_super_admin)):
    if datos.rol != "venezuela" and datos.cuenta_bancaria is not None:
        raise HTTPException(
            400, "Solo el transportista de Venezuela cobra flete: los de Brasil los "
                 "paga el usuario directamente en el mostrador.")
    if await db.transportistas.find_one({"codigo": datos.codigo}):
        raise HTTPException(409, f"Ya existe un transportista con el código {datos.codigo}.")

    doc = datos.model_dump()
    doc["transportista_id"] = f"trp_{uuid.uuid4().hex[:12]}"
    doc["creado_at"] = datetime.now(timezone.utc)
    await db.transportistas.insert_one(dict(doc))
    await envios_config.auditar("transportistas", {}, doc, admin, accion="crear")
    invalidar_cache()
    return {"ok": True, "transportista_id": doc["transportista_id"]}


@router.patch("/transportistas/{transportista_id}")
async def editar_transportista(transportista_id: str, datos: dict,
                               admin: User = Depends(get_super_admin)):
    """Edita todo menos el código y la cuenta bancaria.

    El **código no cambia nunca**: los envíos viejos, los logs y los tests lo
    referencian, y renombrarlo rompe la trazabilidad hacia atrás sin avisar. La
    **cuenta bancaria tiene su propia ruta** porque necesita confirmación tipeada
    y aviso al equipo.
    """
    actual = await db.transportistas.find_one({"transportista_id": transportista_id},
                                              {"_id": 0})
    if not actual:
        raise HTTPException(404, "Transportista no encontrado")

    # Cambiar el rol de venezuela a brasil deja la cuenta bancaria viva colgando
    # de un transportista que no cobra flete, y encima invisible: el panel solo
    # muestra la sección de cuenta en el rol venezuela. Es la misma regla que
    # `crear_transportista` ya aplica al alta.
    if (datos.get("rol") and datos["rol"] != actual.get("rol")
            and actual.get("cuenta_bancaria")):
        raise HTTPException(
            400, "Ese transportista tiene una cuenta bancaria cargada: solo el de "
                 "Venezuela cobra flete. Si de verdad cambió de rol, dalo de baja y "
                 "cargá uno nuevo — su historial de envíos apunta a esta ficha.")

    for prohibido in ("codigo", "transportista_id", "cuenta_bancaria"):
        if prohibido in datos:
            raise HTTPException(
                400, f"El campo {prohibido} no se edita por acá." +
                     (" El código de un transportista no cambia nunca: los envíos "
                      "viejos lo referencian." if prohibido == "codigo" else
                      " La cuenta bancaria tiene su propia ruta." if
                      prohibido == "cuenta_bancaria" else ""))

    # Solo los campos que el esquema conoce. Quedarse con todo menos tres claves
    # dejaba pasar `cuentas_anteriores` —que `cambiar_cuenta` agrega con $push— y
    # como el modelo es `extra="forbid"`, la ficha quedaba inservible a partir del
    # PRIMER cambio de cuenta: cualquier edición posterior devolvía 400. Es el
    # mismo criterio que ya usa `designar_retirador`, por la misma razón.
    fusionado = {k: v for k, v in {**actual, **datos}.items()
                 if k in Transportista.model_fields}
    fusionado.pop("transportista_id", None)
    fusionado.pop("creado_at", None)
    fusionado.pop("cuenta_bancaria", None)

    # Una plantilla de rastreo YA GUARDADA que no tiene `{codigo}` no puede
    # bloquear la edición de otra cosa. Como acá se valida la ficha ENTERA
    # —hace falta: es un merge y el modelo es la única fuente de verdad—, sin
    # esto cambiarle el nombre a un transportista devolvía un 400 hablando del
    # rastreo, un campo que la persona no tocó. Y encima es la misma pantalla
    # donde se corrige un límite mal cargado: el mensaje llegaba en el peor
    # momento posible, hablando de otra cosa.
    #
    # Se saca de la validación, se guarda TAL CUAL estaba —no se pisa ni se
    # borra— y se devuelve un aviso. La plantilla rota sigue rota y sigue
    # visible; lo que deja de hacer es tomar de rehén al resto de la ficha.
    #
    # Editarla SÍ la valida: en cuanto `plantilla_rastreo` viene en `datos`,
    # esta excepción no aplica y el validador manda.
    heredada = (fusionado.get("plantilla_rastreo") or "").strip()
    rastreo_viejo_invalido = ("plantilla_rastreo" not in datos
                              and heredada and "{codigo}" not in heredada)
    if rastreo_viejo_invalido:
        fusionado["plantilla_rastreo"] = None

    try:
        validado = Transportista(**fusionado).model_dump()
    except Exception as e:
        raise _error(envios_config._legible(e))

    avisos = []
    if rastreo_viejo_invalido:
        validado["plantilla_rastreo"] = actual.get("plantilla_rastreo")
        avisos.append(
            "La plantilla de rastreo de esta ficha no incluye {codigo}, así que el "
            "enlace lleva a la portada del transportista en vez de al paquete. Se "
            "guardó tal cual estaba: corregila cuando puedas, o dejala vacía si esa "
            "empresa no tiene enlace directo.")

    validado.pop("cuenta_bancaria", None)      # no se toca desde acá
    await db.transportistas.update_one({"transportista_id": transportista_id},
                                       {"$set": validado})
    await envios_config.auditar("transportistas", actual, validado, admin)
    invalidar_cache()
    return {"ok": True, "valor": _sin_cuenta(validado), "avisos": avisos}


class CambioDeCuenta(BaseModel):
    """La confirmación es tipeada, no copiada: un pegado repite el mismo error."""
    cuenta: CuentaBancaria
    confirmacion_numero: str
    motivo: str = ""


@router.put("/transportistas/{transportista_id}/cuenta")
async def cambiar_cuenta(transportista_id: str, cambio: CambioDeCuenta,
                         admin: User = Depends(get_super_admin)):
    """Cambia la cuenta que recibe los fletes. El campo más sensible del panel.

    Quien pueda editar esto puede redirigir todos los fletes del sistema, y no es
    un precio que se corrige mañana: es plata que sale y no vuelve. Cuatro
    resguardos (§4.6), y ninguno es caro:

      1. Solo el super administrador, nunca el operador.
      2. Confirmación tipeando el número de nuevo. Es la única validación que
         atrapa el dígito cambiado, porque un pegado repite el mismo error.
      3. Se avisa al equipo, con la cuenta vieja y la nueva enmascaradas.
      4. Se VERSIONA, no se pisa: la anterior queda consultable para poder
         responder "¿a qué cuenta le pagó este usuario en marzo?".

    Lo que NO se hace es congelar la cuenta dentro de cada envío. El
    transportista puede cambiarla sin avisar, y una copia congelada pagaría a una
    cuenta muerta: el destino es siempre la vigente.
    """
    t = await db.transportistas.find_one({"transportista_id": transportista_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Transportista no encontrado")
    if t.get("rol") != "venezuela":
        raise HTTPException(
            400, "Solo el transportista de Venezuela cobra flete a través de RIS App.")

    numero = cambio.cuenta.numero
    tipeado = cambio.confirmacion_numero.replace("-", "").replace(" ", "")
    if tipeado != numero:
        raise HTTPException(
            400, "El número de confirmación no coincide. Escribilo de nuevo a mano, "
                 "sin copiar y pegar: es la única forma de detectar un dígito cambiado.")

    anterior = t.get("cuenta_bancaria") or {}
    nueva = cambio.cuenta.model_dump()
    nueva["version_id"] = f"cta_{uuid.uuid4().hex[:10]}"
    nueva["vigente_desde"] = datetime.now(timezone.utc)
    nueva["cargada_por"] = admin.user_id

    await db.transportistas.update_one(
        {"transportista_id": transportista_id},
        {"$set": {"cuenta_bancaria": nueva},
         "$push": {"cuentas_anteriores": {**anterior,
                                          "reemplazada_at": datetime.now(timezone.utc)}}
         if anterior else {}},
    )
    await envios_config.auditar(
        "cuenta_bancaria", {"cuenta_bancaria": anterior}, {"cuenta_bancaria": nueva},
        admin, accion="cambiar_cuenta")

    # El aviso al equipo va por los canales que ya existen. Si el cambio no lo
    # hizo alguien del equipo, hay que enterarse en minutos y no en el cierre.
    try:
        from services.notifications import create_notification
        await create_notification(
            user_id=admin.user_id,
            title="Cambió la cuenta bancaria de un transportista",
            message=(f"{t.get('codigo')}: de ****{str(anterior.get('numero', ''))[-4:]} "
                     f"a ****{numero[-4:]}. Lo hizo {admin.email}."),
            notification_type="alerta",
        )
    except Exception as e:                                    # pragma: no cover
        logger.warning(f"envios: no se pudo avisar el cambio de cuenta: {e}")

    invalidar_cache()
    return {"ok": True, "version_id": nueva["version_id"],
            "numero": "****" + numero[-4:]}


# ─── Agencias ─────────────────────────────────────────────────────────────

@router.get("/transportistas/{transportista_id}/agencias")
async def listar_agencias(transportista_id: str, admin: User = Depends(get_crm_user)):
    filas = await db.agencias.find({"transportista_id": transportista_id},
                                   {"_id": 0}).sort("estado", 1).to_list(None)
    return {"agencias": filas}


@router.post("/transportistas/{transportista_id}/agencias")
async def crear_agencia(transportista_id: str, datos: Agencia,
                        admin: User = Depends(get_super_admin)):
    if not await db.transportistas.find_one({"transportista_id": transportista_id}):
        raise HTTPException(404, "Transportista no encontrado")
    if await db.agencias.find_one({"transportista_id": transportista_id,
                                   "codigo": datos.codigo}):
        raise HTTPException(409, f"Ese transportista ya tiene una agencia {datos.codigo}.")

    if datos.es_punto_entrega:
        await _liberar_punto_entrega(transportista_id)

    doc = datos.model_dump()
    doc["transportista_id"] = transportista_id
    doc["creada_at"] = datetime.now(timezone.utc)
    await db.agencias.insert_one(dict(doc))
    await envios_config.auditar("agencias", {}, doc, admin, accion="crear")
    invalidar_cache()
    return {"ok": True, "codigo": datos.codigo}


async def _liberar_punto_entrega(transportista_id: str) -> None:
    """Dos puntos de entrega es un envío que no sabe a dónde va.

    Se resuelve moviendo la marca en vez de rechazando el alta: el que marca una
    agencia nueva como punto de entrega está diciendo justamente que quiere
    cambiarla, y hacerle desmarcar la anterior primero es una fricción que no
    protege de nada.

    Libera TODAS, incluida la que se está guardando, porque quien llama escribe
    su agencia DESPUES de esto y esa escritura la vuelve a marcar. Que la limpie
    y la reponga en vez de excluirla es lo que hace que esto sirva también de
    REPARACION: una base donde un CSV dejó varias marcadas se arregla guardando
    la correcta, aunque esa ya viniera marcada.
    """
    await db.agencias.update_many(
        {"transportista_id": transportista_id, "es_punto_entrega": True},
        {"$set": {"es_punto_entrega": False}})


@router.patch("/transportistas/{transportista_id}/agencias/{codigo}")
async def editar_agencia(transportista_id: str, codigo: str, datos: dict,
                         admin: User = Depends(get_super_admin)):
    """Corrige una agencia. **No borra: se desactiva con `activa: false`.**

    Sin esta ruta, una agencia cargada sin marcar como punto de entrega solo se
    podía arreglar reimportando un CSV — y un CSV que no trae una columna la
    borra en todas las filas. Alguien que instala el módulo una sola vez no tiene
    por qué descubrir eso.

    El **código no se edita**: es la identidad de la fila dentro de la empresa y
    lo que el CSV usa para no duplicar.
    """
    actual = await db.agencias.find_one(
        {"transportista_id": transportista_id, "codigo": codigo}, {"_id": 0})
    if not actual:
        raise HTTPException(404, "Esa agencia no existe.")
    if "codigo" in datos and datos["codigo"] != codigo:
        raise HTTPException(
            400, "El código de una agencia no se cambia: es cómo la identifica el CSV "
                 "y cómo la referencian los envíos viejos.")

    fusionado = {k: v for k, v in {**actual, **datos}.items()
                 if k in Agencia.model_fields}
    try:
        validada = Agencia(**fusionado).model_dump()
    except Exception as e:
        raise _error(envios_config._legible(e))

    # Solo una puede ser el punto de entrega: dos es un envío que no sabe a dónde
    # va. Se liberan las demás ANTES de marcar esta.
    #
    # Se libera SIEMPRE que el resultado quede marcado, no solo cuando la agencia
    # venia sin marcar. Guardar una que ya estaba marcada tiene que limpiar a las
    # otras: es el unico camino para reparar una base donde un CSV dejo varias, y
    # con la condicion vieja ese guardado no hacia nada.
    if validada["es_punto_entrega"]:
        await _liberar_punto_entrega(transportista_id)

    await db.agencias.update_one(
        {"transportista_id": transportista_id, "codigo": codigo}, {"$set": validada})
    await envios_config.auditar("agencias", actual, validada, admin)
    invalidar_cache()
    return {"ok": True, "valor": {**validada, "transportista_id": transportista_id}}


@router.post("/transportistas/{transportista_id}/agencias/csv")
async def importar_agencias(transportista_id: str, archivo: UploadFile = File(...),
                            admin: User = Depends(get_super_admin)):
    """Importa agencias desde un CSV. Una fila mala no aborta la importación.

    Es la diferencia entre un CSV de doscientas agencias que entra con tres
    rechazadas y un CSV que no entra nunca porque la fila 87 tiene el estado en
    blanco. El informe dice cuáles fallaron y por qué, y esa lista es lo que la
    persona corrige y vuelve a subir.

    LA EXCEPCION A ESA REGLA es `es_punto_entrega` en más de una fila, y se
    rechaza el ARCHIVO ENTERO antes de escribir nada. No es una fila mala entre
    doscientas buenas: es un archivo que da una instrucción contradictoria sobre
    una marca que por definición es única, y no hay forma de elegir por la
    persona cuál de las 250 quiso. Importar "casi todo" dejaría la base en el
    estado exacto que este arreglo viene a impedir — que es como se marcaron 250
    en producción con el semáforo en verde.
    """
    if not await db.transportistas.find_one({"transportista_id": transportista_id}):
        raise HTTPException(404, "Transportista no encontrado")

    try:
        crudo = (await archivo.read()).decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "El archivo no está en UTF-8. Guardalo de nuevo como CSV UTF-8.")

    # Se materializan las filas ANTES de escribir para poder contar los puntos de
    # entrega sobre el archivo completo. Un CSV de agencias son cientos de filas,
    # no millones: entra en memoria sin drama.
    limpias = []
    for numero, fila in enumerate(csv.DictReader(io.StringIO(crudo)), start=2):
        limpia = {k.strip(): (v.strip() if isinstance(v, str) else v)
                  for k, v in fila.items() if k}
        for booleano in ("activa", "es_punto_entrega"):
            if booleano in limpia:
                limpia[booleano] = str(limpia[booleano]).strip().lower() in (
                    "1", "true", "si", "sí", "x")
        limpias.append((numero, limpia))

    marcadas = [n for n, f in limpias if f.get("es_punto_entrega")]
    if len(marcadas) > 1:
        muestra = ", ".join(str(n) for n in marcadas[:10])
        y_mas = f" y {len(marcadas) - 10} más" if len(marcadas) > 10 else ""
        raise HTTPException(
            400,
            f"El archivo marca {len(marcadas)} filas como punto de entrega y solo puede "
            f"haber una: es la única oficina donde RIS App deja los paquetes. Están en "
            f"las líneas {muestra}{y_mas}. No se importó nada. Dejá la columna "
            f"`es_punto_entrega` en verdadero en una sola fila —o vacía en todas, y "
            f"marcala después desde el panel— y volvé a subirlo.")

    creadas, actualizadas, rechazadas = 0, 0, []
    for numero, limpia in limpias:
        try:
            validada = Agencia(**limpia).model_dump()
        except Exception as e:
            rechazadas.append({"fila": numero, "motivo": "; ".join(envios_config._legible(e))})
            continue

        # Como mucho una fila llega marcada: lo garantiza el chequeo de arriba.
        if validada["es_punto_entrega"]:
            await _liberar_punto_entrega(transportista_id)

        existente = await db.agencias.find_one(
            {"transportista_id": transportista_id, "codigo": validada["codigo"]}, {"_id": 0})
        validada["transportista_id"] = transportista_id
        if existente:
            await db.agencias.update_one(
                {"transportista_id": transportista_id, "codigo": validada["codigo"]},
                {"$set": validada})
            actualizadas += 1
        else:
            validada["creada_at"] = datetime.now(timezone.utc)
            await db.agencias.insert_one(dict(validada))
            creadas += 1

    await envios_config.auditar(
        "agencias", {}, {"importacion": {"creadas": creadas, "actualizadas": actualizadas,
                                         "rechazadas": len(rechazadas)}},
        admin, accion="importar_csv")
    invalidar_cache()
    return {"creadas": creadas, "actualizadas": actualizadas,
            "rechazadas": rechazadas, "total_rechazadas": len(rechazadas)}


# ─── Orígenes de Brasil ───────────────────────────────────────────────────
#
# La UF de origen es la CLAVE con la que se busca el precio del tramo brasileño.
# Cargarla desde acá, una vez por ciudad y mirando lo que se carga, es lo que
# evita que la tipee cada usuario en un campo de dos letras al lado del CEP.


class OrigenNuevo(BaseModel):
    """El alta rápida de una ciudad. Tres campos y nada más."""
    model_config = {"extra": "forbid"}
    cep: str = Field(min_length=8, max_length=9)
    ciudad: str = Field(min_length=2, max_length=80)
    uf: str = Field(min_length=2, max_length=2)
    activo: bool = True


class OrigenEditado(BaseModel):
    """Lo que se puede corregir de una ciudad ya cargada. El CEP no: es su
    identidad, y cambiarlo sería dar de alta otra."""
    model_config = {"extra": "forbid"}
    ciudad: Optional[str] = Field(default=None, min_length=2, max_length=80)
    uf: Optional[str] = Field(default=None, min_length=2, max_length=2)
    activo: Optional[bool] = None


class PropuestoResuelto(BaseModel):
    model_config = {"extra": "forbid"}
    estado: Literal["aprobado", "descartado"]
    motivo: Optional[str] = Field(default=None, max_length=300)
    # Solo al aprobar: permite corregir lo que el usuario declaró antes de que
    # entre al catálogo. Aprobar a ciegas lo que alguien tipeó sería exactamente
    # el autocompletado que este módulo no hace.
    ciudad: Optional[str] = Field(default=None, min_length=2, max_length=80)
    uf: Optional[str] = Field(default=None, min_length=2, max_length=2)


async def _uf_con_matriz() -> tuple[set, bool]:
    """Las UF que tienen precios cargados, para la columna «Matriz».

    Un origen sin matriz cotiza igual, pero su bloque de referencia queda mudo
    —y hoy eso pasa sin que nadie se entere—. Decirlo en la misma tabla donde se
    cargan los orígenes es lo que convierte ese silencio en una tarea visible.
    """
    from services.referencias import claves_cargadas, transportistas_activos
    brasileños = await transportistas_activos("brasil")
    claves, ok = set(), True
    for t in brasileños:
        propias, ok_propias = await claves_cargadas(t.get("transportista_id"))
        claves |= propias
        ok = ok and ok_propias
    return claves, ok


@router.get("/origenes")
async def listar_origenes(admin: User = Depends(get_super_admin)):
    """El catálogo, la cobertura de matriz y la cola de propuestos, en una sola
    lectura: es una sola pantalla y pedirla en tres llamadas es pintarla en tres
    pasos."""
    catalogo, ok = await envios_origenes.listar(db=None, solo_activos=False)
    if not ok:
        raise HTTPException(
            503, "No se pudo leer el catálogo de orígenes. No cargues nada encima "
                 "hasta que vuelva: un catálogo que no se puede leer no es un "
                 "catálogo vacío.")
    con_matriz, ok_matriz = await _uf_con_matriz()
    propuestos, _ok_cola = await envios_origenes.listar_propuestos()
    return {
        "origenes": [{**o, "tiene_matriz": (o["uf"] in con_matriz) if ok_matriz else None}
                     for o in catalogo],
        "uf_disponibles": list(envios_origenes.UF_BRASIL),
        # `None` en `tiene_matriz` es «no lo pude averiguar», y la pantalla tiene
        # que mostrarlo distinto de «no tiene»: mandar a cargar precios que ya
        # están es peor que no avisar.
        "matriz_legible": ok_matriz,
        "propuestos": propuestos,
    }


@router.post("/origenes")
async def crear_origen(datos: OrigenNuevo, admin: User = Depends(get_super_admin)):
    """Alta de UNA ciudad. Es el camino corto: agregar un CEP no puede exigir
    armar un CSV entero."""
    fila, errores = envios_origenes.validar(datos.cep, datos.ciudad, datos.uf)
    if errores:
        raise _error(errores)
    anterior = await db.origenes_brasil.find_one({"cep": fila["cep"]}, {"_id": 0})
    guardado = await envios_origenes.guardar(
        {**fila, "activo": datos.activo}, admin=admin)
    await envios_config.auditar("origenes", anterior or {}, guardado, admin,
                                accion="editar" if anterior else "crear")
    invalidar_cache()
    return {"ok": True, "valor": {**guardado,
                                  "cep_legible": envios_origenes.formatear_cep(guardado["cep"])},
            "ya_existia": bool(anterior)}


@router.patch("/origenes/{cep}")
async def editar_origen(cep: str, datos: OrigenEditado,
                        admin: User = Depends(get_super_admin)):
    """Corrige una ciudad. **No borra: se desactiva con `activo: false`.**"""
    limpio = envios_origenes.normalizar_cep(cep)
    actual = await db.origenes_brasil.find_one({"cep": limpio}, {"_id": 0}) if limpio else None
    if not actual:
        raise HTTPException(404, "Ese CEP no está en el catálogo.")

    fila, errores = envios_origenes.validar(
        limpio,
        datos.ciudad if datos.ciudad is not None else actual.get("ciudad"),
        datos.uf if datos.uf is not None else actual.get("uf"))
    if errores:
        raise _error(errores)
    activo = datos.activo if datos.activo is not None else actual.get("activo", True)
    guardado = await envios_origenes.guardar({**fila, "activo": activo}, admin=admin)
    await envios_config.auditar("origenes", actual, guardado, admin)
    invalidar_cache()
    return {"ok": True, "valor": {**guardado,
                                  "cep_legible": envios_origenes.formatear_cep(guardado["cep"])}}


@router.post("/origenes/csv")
async def importar_origenes(archivo: UploadFile = File(...),
                            confirmar: bool = Form(False),
                            admin: User = Depends(get_super_admin)):
    """Importa ciudades desde un CSV de `cep,ciudad,uf`.

    **La vista previa es obligatoria y es este mismo endpoint sin `confirmar`.**
    Contesta cuántas filas son nuevas, cuántas actualizan una que ya está y
    cuántas se rechazan con su motivo y su número de línea — y NO escribe nada.
    Recién con `confirmar` se guarda.

    Son dos viajes y no uno a propósito: un CSV de orígenes cambia la clave con
    la que se busca el precio de un tramo, y «lo subí y ya está» es cómo se
    entera alguien de que puso la UF equivocada en doscientas ciudades. Ver el
    plan antes cuesta un clic.

    Una fila mala no frena a las demás: se listan aparte, con su línea, y esa
    lista es lo que la persona corrige y vuelve a subir.
    """
    try:
        crudo = (await archivo.read()).decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "El archivo no está en UTF-8. Guardalo de nuevo como CSV UTF-8.")

    nuevas, actualiza, rechazadas = [], [], []
    vistos = set()
    for numero, fila in enumerate(csv.DictReader(io.StringIO(crudo)), start=2):
        limpia = {(k or "").strip().lower(): (v.strip() if isinstance(v, str) else v)
                  for k, v in fila.items() if k}
        validada, errores = envios_origenes.validar(
            limpia.get("cep"), limpia.get("ciudad"), limpia.get("uf"))
        if errores:
            rechazadas.append({"fila": numero, "motivo": "; ".join(errores)})
            continue
        # El mismo CEP dos veces DENTRO del archivo: se avisa en vez de dejar que
        # la última gane en silencio. Son dos ciudades distintas para el mismo
        # código postal, y cuál queda no lo puede decidir el orden de las filas.
        if validada["cep"] in vistos:
            rechazadas.append({
                "fila": numero,
                "motivo": f"El CEP {envios_origenes.formatear_cep(validada['cep'])} ya aparece "
                          f"antes en este mismo archivo."})
            continue
        vistos.add(validada["cep"])
        existente = await db.origenes_brasil.find_one({"cep": validada["cep"]}, {"_id": 0})
        destino = actualiza if existente else nuevas
        destino.append({**validada,
                        "cep_legible": envios_origenes.formatear_cep(validada["cep"]),
                        **({"antes": {"ciudad": existente.get("ciudad"),
                                      "uf": existente.get("uf")}} if existente else {})})

    plan = {
        "nuevas": len(nuevas), "actualiza": len(actualiza),
        "rechazadas": rechazadas, "total_rechazadas": len(rechazadas),
        # La muestra alcanza para revisar sin volver ilegible la respuesta de un
        # CSV de miles de filas.
        "muestra_nuevas": nuevas[:20], "muestra_actualiza": actualiza[:20],
    }
    if not confirmar:
        return {"ok": True, "confirmado": False, **plan}

    for fila in nuevas + actualiza:
        await envios_origenes.guardar(
            {k: fila[k] for k in ("cep", "ciudad", "uf")}, admin=admin)
    await envios_config.auditar(
        "origenes", {}, {"importacion": {"nuevas": len(nuevas),
                                         "actualizadas": len(actualiza),
                                         "rechazadas": len(rechazadas)}},
        admin, accion="importar")
    invalidar_cache()
    return {"ok": True, "confirmado": True, **plan}


@router.post("/origenes/propuestos/{cep}")
async def resolver_origen_propuesto(cep: str, datos: PropuestoResuelto,
                                    admin: User = Depends(get_super_admin)):
    """Aprueba una ciudad de la cola —y ahí entra al catálogo— o la descarta.

    **Nada entra solo.** Es la misma regla que rige para los precios observados
    y por el mismo motivo: un catálogo que se autocompleta es un catálogo donde
    un error de tipeo se vuelve permanente sin que nadie lo mire.
    """
    limpio = envios_origenes.normalizar_cep(cep)
    propuesto = await db.origenes_propuestos.find_one({"cep": limpio}, {"_id": 0}) if limpio else None
    if not propuesto:
        raise HTTPException(404, "Ese CEP no está en la cola.")

    creado = None
    if datos.estado == "aprobado":
        fila, errores = envios_origenes.validar(
            limpio,
            datos.ciudad or propuesto.get("ciudad"),
            datos.uf or propuesto.get("uf"))
        if errores:
            # Lo que declaró el usuario puede estar incompleto —la UF es
            # opcional en el formulario— y eso no es un error suyo: es lo que
            # esta pantalla viene a completar.
            raise _error(errores + [
                "Completá la ciudad y la UF acá antes de aprobar: es lo que va a "
                "quedar en el catálogo."])
        creado = await envios_origenes.guardar(fila, admin=admin)
        invalidar_cache()

    await envios_origenes.resolver_propuesto(limpio, datos.estado, datos.motivo)
    await envios_config.auditar("origenes_propuestos", propuesto,
                                {"estado": datos.estado, "motivo": datos.motivo,
                                 "catalogo": creado},
                                admin, accion=datos.estado)
    return {"ok": True, "estado": datos.estado, "valor": creado}


# ─── Tarifas: la consola de precios ───────────────────────────────────────

@router.get("/tarifas")
async def listar_tarifas(admin: User = Depends(get_super_admin)):
    """El historial con sus notas, y qué hay en el borrador."""
    borrador, origen = await envios_tarifa_editor.borrador_o_copia()
    if origen == "error":
        raise HTTPException(
            503, "No se pudo leer el borrador. No edites hasta que vuelva: lo que "
                 "guardes ahora puede pisar lo que ya había.")
    # Todo pasa por `serializable`: en esta colección puede haber Decimal128
    # —es como services/money.py guarda dinero— y el encoder de FastAPI no sabe
    # serializarlo. Un solo campo así tumbaba la consola de precios entera.
    return envios_tarifa_editor.serializable({
        "vigente": await envios_tarifa_editor.vigente(),
        "borrador": borrador,
        "origen_borrador": origen,
        "historial": await envios_tarifa_editor.historial(),
    })


@router.put("/tarifas/borrador")
async def guardar_borrador_tarifa(datos: TarifaBorrador,
                                  admin: User = Depends(get_super_admin)):
    """Guarda el borrador. No publica nada y no valida la coherencia de la tabla.

    Recibe `TarifaBorrador` y no `TarifaEnvio`: guardar tiene que poder hacerse
    con la tabla a medio cargar —alguien carga cuatro escalones un martes y
    vuelve el jueves— y con el mismo objeto que devolvió el GET, metadatos
    incluidos. Lo que se valida es publicar, que es cuando el número empieza a
    cobrarse. Igual se devuelven las advertencias, para que la pantalla las
    muestre mientras se edita.
    """
    limpio = datos.como_borrador()
    guardado = await envios_tarifa_editor.guardar_borrador(limpio, admin)
    return envios_tarifa_editor.serializable({
        "ok": True, "borrador": guardado,
        "advertencias": validar_tarifa(limpio),
    })


class Simulacion(BaseModel):
    # El tope no es una opinión de producto: cada caja son dos cotizaciones
    # Decimal síncronas dentro del event loop, y una lista sin cota bloquea el
    # worker entero, no solo esta request.
    cajas: list[CajaDePrueba] = Field(default_factory=list, max_length=50)
    tarifa: TarifaEnvio | None = None      # si no viene, se usa el borrador
    fecha: date | None = None              # para ver una temporada sin esperarla


@router.post("/tarifas/simular")
async def simular_tarifa(datos: Simulacion, admin: User = Depends(get_super_admin)):
    """Cotiza las cajas contra el borrador y contra la vigente, lado a lado.

    Es lo que evita publicar un aumento del 40 % creyendo que era del 4 %. La
    fecha es opcional y por defecto es hoy: sin ella los recargos de temporada
    valen 1 y un aumento de temporada del 50 % se vería como 0 %.
    """
    if datos.tarifa is not None:
        borrador = datos.tarifa.model_dump()
    else:
        borrador, origen = await envios_tarifa_editor.borrador_o_copia()
        if origen == "error":
            raise HTTPException(503, "No se pudo leer el borrador.")

    return envios_tarifa_editor.serializable({
        "comparacion": envios_tarifa_editor.comparar(
            borrador, await envios_tarifa_editor.vigente(),
            [c.model_dump() for c in datos.cajas], fecha=datos.fecha),
        "bloqueos": validar_tarifa(borrador),
        "fecha_simulada": (datos.fecha or date.today()).isoformat(),
    })


class Publicacion(BaseModel):
    nota: str = Field(min_length=1, max_length=500)
    vigente_desde: datetime | None = None
    tarifa: TarifaEnvio | None = None


@router.post("/tarifas/publicar")
async def publicar_tarifa(datos: Publicacion, admin: User = Depends(get_super_admin)):
    """Crea la versión nueva y reordena las ventanas. **Nunca edita una existente.**

    Pide una nota de qué cambió y por qué. No es burocracia: es lo que alguien va
    a leer dentro de seis meses para entender por qué un envío de marzo costó lo
    que costó.
    """
    if datos.tarifa is not None:
        # Vino la tarifa entera: el borrador guardado no tiene nada que ver con
        # esta publicación y no se toca. Consumirlo acá borraba, sin aviso y sin
        # deshacer, el trabajo a medio cargar de quien estuviera editando.
        borrador, consumir, marca = datos.tarifa.model_dump(), False, None
    else:
        borrador, origen = await envios_tarifa_editor.borrador_o_copia()
        if origen == "error":
            raise HTTPException(
                503, "No se pudo leer el borrador. Publicar ahora podría pisarlo.")
        if origen == "vacio":
            raise HTTPException(400, "No hay borrador ni versión vigente que publicar.")
        if origen == "copia_de_vigente":
            raise HTTPException(
                400, "No hay cambios que publicar: el borrador es una copia idéntica de "
                     "la versión vigente. Editá algo primero.")
        consumir, marca = True, borrador.get("actualizado_at")

    version, errores = await envios_tarifa_editor.publicar(
        borrador, datos.nota, admin, vigente_desde=datos.vigente_desde,
        consumir_borrador=consumir, marca_borrador=marca)
    if errores:
        raise _error(errores)

    # La clave es `version_publicada` y no `version_id` porque envios_config
    # descarta `version_id` de las diferencias —es metadato del guardado, no un
    # cambio— y el asiento quedaba con la nota y sin forma de atarla a la versión
    # que un envío de marzo tiene congelada, que es justo lo que la auditoría
    # existe para poder contestar.
    await envios_config.auditar(
        "tarifas", {}, {"version_publicada": version["version_id"], "nota": version["nota"],
                        "vigente_desde": version["vigente_desde"].isoformat()},
        admin, accion="publicar")
    invalidar_cache()
    return {"ok": True, "version_id": version["version_id"],
            "vigente_desde": version["vigente_desde"].isoformat()}


# ─── Nómina de retiro: a nombre de quién se rotulan los paquetes ──────────
#
# Escritura solo del super administrador; lectura tambien para el operador. Es la
# misma separacion que el panel ya usa para las tasas: el que viaja a Pacaraima
# necesita ver a que nombre estan rotulados los paquetes para saber cuales puede
# reclamar, pero no tiene por que poder cambiar ese nombre.

@router.get("/retiro")
async def ver_retiro(admin: User = Depends(get_crm_user)):
    """La nómina, quién está de turno y la vista previa del bloque de despacho.

    La vista previa se renderiza con la misma función que usa la cotización. Una
    plantilla se edita a ciegas si no se ve el resultado, y una dirección mal
    armada no se descubre en el panel: se descubre cuando una caja llega a una
    agencia que no la esperaba.

    **La nómina sale sin CPF ni teléfono.** El operador necesita saber a qué
    nombre están rotulados los paquetes para saber cuáles puede reclamar; no
    necesita el documento de sus compañeros. Es la misma decisión que
    `listar_transportistas`, que también es `get_crm_user` y también recorta —
    un listado se comparte en pantalla mucho más seguido de lo que se cree.

    El bloque `punto_origen` completo tampoco baja acá: `GET /config/{bloque}` lo
    sirve y pide `get_super_admin`. El mismo documento con dos niveles de
    autorización según por dónde se pida es la clase de inconsistencia que
    después se cita como precedente.
    """
    try:
        nomina = await db.colaboradores_retiro.find(
            {}, {"_id": 0, "cpf": 0, "telefono": 0}).to_list(envios_retiro._NOMINA_MAX)
    except Exception as e:
        logger.warning(f"envios: no se pudo leer la nómina: {e}")
        nomina = []
    return {
        # Cinturón y tirantes: la proyección ya los excluye, y el filtro atrapa el
        # día que alguien la toque. Es un dato personal de un empleado.
        "nomina": [_sin_datos_personales(c) for c in nomina],
        "vista_previa": await envios_retiro.bloque_de_despacho(),
    }


@router.post("/retiro/colaboradores")
async def crear_colaborador(datos: Colaborador, admin: User = Depends(get_super_admin)):
    """Da de alta a alguien autorizado a retirar en la agencia de Pacaraima."""
    validado = datos.model_dump()

    # Sin esto, un doble clic en Guardar o un reintento del cliente crean dos
    # fichas de la misma persona. Se da de baja la que se ve seleccionada, la otra
    # queda vigente, y meses después sale rotulada como suplente: el mostrador
    # recibe una caja a nombre de alguien que la nómina ya dio de baja.
    if await _ya_esta_en_la_nomina(validado):
        raise HTTPException(
            409, "Esa persona ya está en la nómina. Editá su ficha en vez de darla de "
                 "alta otra vez: dos fichas de la misma persona se desactivan por "
                 "separado y una queda viva sin que nadie la vea.")

    validado["colaborador_id"] = envios_retiro.nuevo_colaborador_id()
    validado["creado_at"] = datetime.now(timezone.utc)
    validado["creado_por"] = admin.user_id
    await db.colaboradores_retiro.insert_one(dict(validado))
    await envios_config.auditar("nomina_retiro", {}, _sin_datos_personales(validado),
                                admin, accion="alta_colaborador")
    # No invalida el caché: la nómina no la lee ninguna pantalla cacheada. Llamar
    # a invalidar_cache() acá sería tirar el catálogo de todos para nada, y —peor—
    # dejar escrito que existe una dependencia que no existe.
    return {"ok": True, "valor": validado}


@router.put("/retiro/colaboradores/{colaborador_id}")
async def editar_colaborador(colaborador_id: str, datos: Colaborador,
                             admin: User = Depends(get_super_admin)):
    """Edita una ficha. **No borra: se desactiva con `activo: false`.**

    El envío que ya se cotizó guarda el nombre congelado, así que dar de baja a
    alguien no rompe nada viejo — pero su ficha tiene que seguir existiendo para
    poder contestar quién retiró el paquete de marzo.
    """
    actual = await db.colaboradores_retiro.find_one({"colaborador_id": colaborador_id},
                                                    {"_id": 0})
    if not actual:
        raise HTTPException(404, "Ese colaborador no está en la nómina.")

    # Se FUSIONA con lo actual, igual que editar_transportista, y por dos razones
    # que se descubren tarde. Una: el panel no muestra el CPF —por la misma razón
    # de privacidad que motiva todo esto— así que no lo reenvía, y un reemplazo
    # total lo borraba en silencio. Dos: `activo` tiene default True, así que
    # editarle el teléfono a alguien dado de baja lo REACTIVABA, y su nombre
    # volvía a salir rotulado en cajas que ya no está autorizado a retirar.
    fusionado = {**actual, **datos.model_dump(exclude_unset=True)}
    for metadato in ("colaborador_id", "creado_at", "creado_por"):
        fusionado.pop(metadato, None)
    try:
        validado = Colaborador(**fusionado).model_dump()
    except Exception as e:
        raise _error(envios_config._legible(e))

    await db.colaboradores_retiro.update_one({"colaborador_id": colaborador_id},
                                             {"$set": validado})
    await envios_config.auditar("nomina_retiro", _sin_datos_personales(actual),
                                _sin_datos_personales(validado), admin)
    return {"ok": True, "valor": {**validado, "colaborador_id": colaborador_id}}


class Designacion(BaseModel):
    colaborador_id: str = Field(min_length=1, max_length=40)


@router.put("/retiro/turno")
async def designar_retirador(datos: Designacion, admin: User = Depends(get_super_admin)):
    """Marca quién sale rotulado en las cotizaciones **nuevas**.

    No toca ni un envío existente, y eso es deliberado: cambiar la nómina no
    puede cambiar la etiqueta de una caja que ya está viajando, porque el
    mostrador va a comparar esa etiqueta contra un documento y no contra la base.
    """
    colaborador = await db.colaboradores_retiro.find_one(
        {"colaborador_id": datos.colaborador_id}, {"_id": 0})
    if not colaborador:
        raise HTTPException(404, "Ese colaborador no está en la nómina.")
    if not envios_retiro._vigente(colaborador, datetime.now(timezone.utc)):
        raise HTTPException(
            400, "Ese colaborador no está activo o su autorización no está vigente. "
                 "Actualizá su ficha antes de ponerlo de turno.")

    punto = await envios_config.leer("punto_origen")
    if not punto:
        # `leer` devuelve None tanto si no está cargado como si Mongo no
        # contestó, y las dos cosas no se responden igual: mandar a "cargá
        # primero el punto de origen" durante un corte hace que alguien lo
        # recargue de memoria y pise la plantilla y la Caixa Postal reales.
        _, se_pudo_leer = await envios_config.leer_con_estado("punto_origen")
        if not se_pudo_leer:
            raise HTTPException(
                503, "No se pudo leer el punto de origen. Reintentá en un momento — no "
                     "lo vuelvas a cargar, que lo pisarías.")
        raise HTTPException(
            400, "Cargá primero el punto de origen: sin la agencia y la razón social no "
                 "hay bloque de despacho que armar.")

    # Solo los campos que el esquema conoce. Quedarse con todo menos tres claves
    # dejaba pasar cualquier otra que existiera en el documento —una versión
    # anterior del esquema, una edición a mano— y como el modelo es
    # `extra="forbid"`, designar a alguien pasaba a devolver 400 para siempre.
    limpio = {k: v for k, v in punto.items() if k in ConfigPuntoOrigen.model_fields}
    limpio["retirador_activo_id"] = datos.colaborador_id
    valor, errores = await envios_config.guardar("punto_origen", limpio, admin,
                                                 invalidar=invalidar_cache)
    if errores:
        raise _error(errores)
    return {"ok": True, "de_turno": colaborador.get("nombre"),
            "vista_previa": await envios_retiro.bloque_de_despacho()}


# ─── Comprobantes: verificar es lo que emite el cobro inicial ─────────────

class Verificacion(BaseModel):
    """Lo que el operador LEE en la foto del comprobante.

    No es lo que el usuario tipeó: con eso, cualquiera escribiría 0,1 kg y el
    servicio se cobraría solo. La medición sigue siendo ajena —la hizo el
    transportista de origen— y acá alguien de este lado la confirma mirando el
    papel.
    """
    peso_kg: str = Field(min_length=1, max_length=20)
    largo_cm: str = Field(min_length=1, max_length=20)
    ancho_cm: str = Field(min_length=1, max_length=20)
    alto_cm: str = Field(min_length=1, max_length=20)
    idempotency_key: str = Field(default=None, max_length=100)


@router.post("/envios/{envio_id}/comprobante/verificar")
async def verificar_comprobante(envio_id: str, datos: Verificacion,
                                admin: User = Depends(get_admin_user)):
    """Confirma el comprobante y **emite el cobro inicial**.

    `get_admin_user` y no `get_crm_user`: esta ruta mueve saldo real, y el rol
    `agent` —soporte de chat— no tiene por qué poder emitir un cobro. Es la misma
    razón por la que el repesaje, que puede acreditarle plata a un usuario,
    tampoco lo acepta.

    Es una de las dos rutas del panel que hacen que se mueva saldo, y lo hace con el peso
    que el operador leyó en la foto. Si el cobro no se puede pagar, la partida
    queda pendiente y el envío sigue: el paquete ya está viajando.
    """
    try:
        return await envios_comprobante.verificar(
            admin, envio_id, peso_kg=datos.peso_kg, largo_cm=datos.largo_cm,
            ancho_cm=datos.ancho_cm, alto_cm=datos.alto_cm,
            idempotency_key=datos.idempotency_key)
    except envios_comprobante.ComprobanteRechazado as e:
        raise HTTPException(e.http, e.mensaje)
    except Exception as e:
        from services.envios_cobros import CobroImposible
        if isinstance(e, CobroImposible):
            raise HTTPException(e.http, e.mensaje)
        logger.error(f"envios: verificar comprobante falló: {e}")
        raise HTTPException(503, "No se pudo verificar. Reintentá en un momento.")


# ─── La operación: lo que pasa con el paquete ─────────────────────────────
#
# Todas son del OPERADOR (`get_crm_user`), no del super administrador. El que
# viaja a Pacaraima y pesa cajas no tiene por que poder cambiar los precios ni la
# cuenta que recibe los fletes, y el que fija los precios no necesita mover
# paquetes. Es la misma separacion que el panel ya usa para las tasas.

def _operacion(e: Exception):
    if isinstance(e, envios_operacion.OperacionRechazada):
        return HTTPException(e.http, e.mensaje)
    from services.envios_archivos import ArchivoRechazado
    from services.envios_cobros import CobroImposible
    if isinstance(e, (CobroImposible, ArchivoRechazado)):
        return HTTPException(e.http, e.mensaje)
    logger.error(f"envios: operación falló: {e}")
    return HTTPException(503, "No se pudo completar. Reintentá en un momento.")


@router.get("/envios/cola")
async def ver_cola(estado: str = "disponible_retiro",
                   admin: User = Depends(get_crm_user)):
    """La cola del operador, agrupada por el nombre rotulado en cada caja.

    El agrupamiento es lo que hace útil esta pantalla: en el mostrador comparan
    la etiqueta contra un documento, así que quien va necesita saber cuáles puede
    reclamar él. Agrupar por quien esté de turno hoy sería mandarlo a reclamar
    cajas que no puede.
    """
    return await envios_operacion.cola(estado)


class Disponible(BaseModel):
    dias_guarda: int = Field(default=None, ge=1, le=180)


@router.post("/envios/{envio_id}/disponible")
async def marcar_disponible(envio_id: str, datos: Disponible = None,
                            admin: User = Depends(get_crm_user)):
    """El paquete está en el mostrador. **Arranca el reloj de guarda.**

    Pasado el plazo la agencia lo devuelve al remitente, con el costo del retorno
    y un usuario que ya pagó. Es el parámetro operativo más caro del módulo.
    """
    try:
        return await envios_operacion.marcar_disponible(
            admin, envio_id, dias_guarda=(datos.dias_guarda if datos else None))
    except Exception as e:
        raise _operacion(e)


class Lote(BaseModel):
    # Por CODIGO DE OBJETO: es lo que esta impreso en la caja que el operador
    # tiene en la mano. Pedirle el envio_id seria pedirle que busque cada caja en
    # una pantalla, parado en un mostrador con treinta cajas.
    codigos: list[str] = Field(min_length=1, max_length=200)
    nota: str = Field(default="", max_length=300)


@router.post("/envios/retiro-lote")
async def retirar_lote(datos: Lote, admin: User = Depends(get_crm_user)):
    """Retira varios paquetes del mostrador de una vez.

    Un código desconocido **no aborta el lote**: vuelven en `rechazados` con el
    motivo. El operador está en un mostrador con treinta cajas y que una no se
    reconozca no puede hacerle perder las veintinueve que sí.
    """
    try:
        return await envios_operacion.retirar_lote(admin, datos.codigos,
                                                   nota=datos.nota)
    except Exception as e:
        raise _operacion(e)


class Repesaje(BaseModel):
    peso_kg: str = Field(min_length=1, max_length=20)
    largo_cm: str = Field(min_length=1, max_length=20)
    ancho_cm: str = Field(min_length=1, max_length=20)
    alto_cm: str = Field(min_length=1, max_length=20)
    idempotency_key: str = Field(default=None, max_length=100)


@router.post("/envios/{envio_id}/repesar")
async def repesar(envio_id: str, datos: Repesaje,
                  admin: User = Depends(get_admin_user)):
    """Pesa con balanza propia y cierra el precio. Las tres ramas del ajuste.

    `get_admin_user` y no `get_crm_user`: la rama "devolver" **acredita saldo
    real** con un monto derivado de las medidas que teclea quien llama. Un rol
    `agent` con esta ruta puede transferirse plata a sí mismo en dos pasos.

    Devuelve `puede_salir`, que es lo que el operador necesita saber antes de
    cargar la camioneta y no después.
    """
    try:
        return await envios_operacion.repesar(
            admin, envio_id, peso_kg=datos.peso_kg, largo_cm=datos.largo_cm,
            ancho_cm=datos.ancho_cm, alto_cm=datos.alto_cm,
            idempotency_key=datos.idempotency_key)
    except Exception as e:
        raise _operacion(e)


@router.post("/envios/{envio_id}/despachar")
async def despachar(envio_id: str, admin: User = Depends(get_crm_user)):
    """El paquete sale hacia Santa Elena. **Solo con todo pago.**

    Es la única palanca de cobro real del negocio: la posesión física.
    """
    try:
        return await envios_operacion.despachar(admin, envio_id)
    except Exception as e:
        raise _operacion(e)


@router.post("/envios/{envio_id}/entregar")
async def entregar(envio_id: str, guia: str = Form(...),
                   foto: UploadFile = File(None),
                   admin: User = Depends(get_crm_user)):
    """Entregado en la oficina del transportista. El servicio terminó acá.

    La guía es obligatoria: sin ella, la única prueba de la entrega es la palabra
    del operador.
    """
    try:
        datos = None
        if foto is not None:
            from services.envios_archivos import TAMANO_MAX_BYTES
            datos = await foto.read(TAMANO_MAX_BYTES + 1)
        return await envios_operacion.entregar(admin, envio_id, guia=guia, foto=datos)
    except Exception as e:
        raise _operacion(e)


# ─── Rentabilidad y precios observados ────────────────────────────────────

def _rentabilidad(e: Exception):
    if isinstance(e, envios_rentabilidad.RentabilidadRechazada):
        return HTTPException(e.http, e.mensaje)
    logger.error(f"envios: rentabilidad falló: {e}")
    return HTTPException(503, "No se pudo calcular. Reintentá en un momento.")


@router.get("/envios/viajes/{lote_id}")
async def ver_viaje(lote_id: str, admin: User = Depends(get_crm_user)):
    """Qué dejó un viaje a Pacaraima: lo cobrado, lo pendiente y el resultado.

    Lo pendiente se muestra **aparte** y no se suma a lo cobrado: sumarlo daría
    un viaje rentable con plata que todavía no entró, que es la forma clásica de
    creerse rentable seis meses seguidos.
    """
    try:
        return await envios_rentabilidad.por_lote(lote_id)
    except Exception as e:
        raise _rentabilidad(e)


class CostoDelViaje(BaseModel):
    costo_ris: str = Field(min_length=1, max_length=20)


@router.put("/envios/viajes/{lote_id}/costo")
async def cargar_costo_viaje(lote_id: str, datos: CostoDelViaje,
                             admin: User = Depends(get_crm_user)):
    """Carga lo que costó el viaje: combustible, peajes y horas.

    Es el único número que no se deduce de ningún lado, y sin él la cuenta del
    viaje no significa nada. Estimarlo sería inventar justamente la parte que
    hace que el resultado sea un resultado.
    """
    try:
        return await envios_rentabilidad.cargar_costo(admin, lote_id, datos.costo_ris)
    except Exception as e:
        raise _rentabilidad(e)


@router.get("/envios/observado")
async def ver_observado(dias: int = 90, admin: User = Depends(get_super_admin)):
    """Lo que costó de verdad cada tramo, sacado de las operaciones.

    **No escribe nada.** Cada propuesta viaja con sus muestras y su dispersión, y
    con un `confiable` que dice si el módulo se animaría a usarla: una sugerencia
    con dos observaciones y una dispersión del 40 % no es un precio, es ruido.
    """
    return {"observaciones": await envios_rentabilidad.observaciones(dias=dias),
            "muestras_minimas": envios_rentabilidad.MUESTRAS_MINIMAS}


class Aprobacion(BaseModel):
    transportista_id: str = Field(min_length=1, max_length=60)
    clave: str = Field(min_length=1, max_length=40)
    hasta_kg: str = Field(min_length=1, max_length=20)
    precio: str = Field(min_length=1, max_length=20)
    moneda: str = Field(default=None, max_length=8)


@router.post("/envios/observado/aprobar")
async def aprobar_observado(datos: Aprobacion,
                            admin: User = Depends(get_super_admin)):
    """Lleva un valor observado a la matriz de referencia. **Nadie más escribe ahí.**

    Es una ruta aparte y no el final de la anterior a propósito: un job que
    corrige precios solo es un job que un día mueve un número por una muestra
    rara, y nadie se entera hasta que un usuario pregunta por qué le dijimos que
    iba a pagar el doble.
    """
    try:
        resultado = await envios_rentabilidad.aprobar(
            admin, transportista_id=datos.transportista_id, clave=datos.clave,
            hasta_kg=datos.hasta_kg, precio=datos.precio, moneda=datos.moneda)
    except Exception as e:
        raise _rentabilidad(e)
    invalidar_cache()
    return resultado


# ─── Matrices de referencia ───────────────────────────────────────────────
#
# La coleccion existe desde el principio y no cambia de forma. Lo que faltaba
# eran las ENTRADAS para escribirla: se diseño para alimentarse sola con los
# precios que la operacion observa, y en regimen funciona — pero al arrancar no
# funciona nunca, porque para observar un precio hay que haber despachado un
# paquete y para que alguien despache tiene que ver un precio.


class FilaDeMatriz(BaseModel):
    """Una fila cargada a mano. Misma forma que la aprobación de un observado."""
    model_config = {"extra": "forbid"}
    transportista_id: str = Field(min_length=1, max_length=60)
    clave: str = Field(min_length=1, max_length=40)
    hasta_kg: str = Field(min_length=1, max_length=20)
    precio: str = Field(min_length=1, max_length=20)
    moneda: Optional[str] = Field(default=None, max_length=8)


async def _claves_que_faltan() -> dict:
    """Qué claves tiene cargadas cada transportista, y cuáles se van a necesitar.

    Es lo que evita el bloque mudo. Del lado de Brasil las claves que hacen falta
    son las UF de los orígenes ACTIVOS; del lado de Venezuela, las zonas de las
    agencias activas. Decirlo acá, en la pantalla donde se cargan los precios, es
    lo que convierte «a este usuario no le apareció la referencia» en una tarea
    visible antes de que pase.
    """
    from services.referencias import claves_cargadas, transportistas_activos

    origenes, ok_origenes = await envios_origenes.listar()
    necesarias_brasil = sorted({o["uf"] for o in origenes if o.get("uf")})

    salida, legible = [], ok_origenes
    for rol in ("brasil", "venezuela"):
        for t in await transportistas_activos(rol):
            cargadas, ok = await claves_cargadas(t.get("transportista_id"))
            legible = legible and ok
            if rol == "brasil":
                necesarias = necesarias_brasil
            else:
                agencias, ok_ag = await envios_catalogo._agencias_de(
                    t.get("transportista_id"))
                legible = legible and ok_ag
                necesarias = sorted({a["zona"] for a in agencias if a.get("zona")})
            salida.append({
                "transportista_id": t.get("transportista_id"),
                "codigo": (t.get("codigo") or "?"),
                "rol": rol,
                "cargadas": sorted(cargadas),
                "necesarias": necesarias,
                "faltan": [c for c in necesarias if c not in cargadas],
            })
    return {"transportistas": salida, "legible": legible}


@router.get("/matrices")
async def listar_matrices(admin: User = Depends(get_super_admin)):
    """Las filas cargadas, con de dónde salió cada número y cuál está vieja.

    Las dos cosas que la pantalla tiene que decir sin que se las pidan:

      - **De dónde salió**: `observado` es un precio que vimos operando,
        `manual` uno que alguien tipeó. Son dos niveles de confianza distintos.
      - **Cuál está vieja**: a los `DIAS_FRESCURA` el usuario ve la advertencia
        de que la referencia puede haber cambiado. Verlo acá ANTES que allá es
        la diferencia entre corregirlo y enterarse por un reclamo.

    Y una fila SIN `actualizada_at` legible cuenta como vieja, por diseño: una
    matriz que no dice cuándo se cargó no puede presentarse como fresca.
    """
    from services.referencias import DIAS_FRESCURA, _esta_vieja
    try:
        filas = await db.matrices_referencia.find({}, {"_id": 0}).sort(
            [("transportista_id", 1), ("clave", 1), ("hasta_kg", 1)]).to_list(None)
    except Exception as e:
        logger.error(f"envios: no se pudieron leer las matrices: {e}")
        raise HTTPException(
            503, "No se pudieron leer las matrices. No cargues nada encima hasta que "
                 "vuelva: lo que guardes ahora puede pisar lo que ya había.")
    return {
        "filas": [{**f, "desactualizada": _esta_vieja(f.get("actualizada_at"),
                                                      DIAS_FRESCURA)}
                  for f in (filas or [])],
        "dias_frescura": DIAS_FRESCURA,
        "cobertura": await _claves_que_faltan(),
    }


@router.post("/matrices")
async def cargar_fila_de_matriz(datos: FilaDeMatriz,
                                admin: User = Depends(get_super_admin)):
    """Carga o corrige UNA fila. Agregar un precio no puede exigir un CSV.

    Entra por `envios_rentabilidad.aprobar` y no por una escritura propia: esa
    función normaliza `hasta_kg`, y el índice de la matriz no es único, así que
    "10" y "10.0" dejarían dos filas para el mismo tope con el precio viejo
    esperando a ganar un desempate. Se pasa `origen="manual"` para que la fila
    diga que la tipeó una persona.
    """
    try:
        resultado = await envios_rentabilidad.aprobar(
            admin, transportista_id=datos.transportista_id, clave=datos.clave,
            hasta_kg=datos.hasta_kg, precio=datos.precio, moneda=datos.moneda,
            origen="manual")
    except Exception as e:
        raise _rentabilidad(e)
    invalidar_cache()
    return resultado


@router.post("/matrices/csv")
async def importar_matrices(transportista_id: str = Form(...),
                            archivo: UploadFile = File(...),
                            confirmar: bool = Form(False),
                            admin: User = Depends(get_super_admin)):
    """Importa filas desde un CSV de `clave,hasta_kg,precio,moneda`.

    **Misma vista previa obligatoria que la de orígenes**, y por el mismo motivo:
    estos números son los que se le muestran a un usuario como orientación de lo
    que va a pagar por fuera, y subir un archivo con la columna corrida es
    mostrarle el precio de otro tramo.
    """
    if not await db.transportistas.find_one({"transportista_id": transportista_id}):
        raise HTTPException(404, "Transportista no encontrado")
    try:
        crudo = (await archivo.read()).decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "El archivo no está en UTF-8. Guardalo de nuevo como CSV UTF-8.")

    validas, rechazadas = [], []
    for numero, fila in enumerate(csv.DictReader(io.StringIO(crudo)), start=2):
        limpia = {(k or "").strip().lower(): (v.strip() if isinstance(v, str) else v)
                  for k, v in fila.items() if k}
        try:
            candidata = FilaDeMatriz(transportista_id=transportista_id,
                                     clave=limpia.get("clave") or "",
                                     hasta_kg=limpia.get("hasta_kg") or "",
                                     precio=limpia.get("precio") or "",
                                     moneda=limpia.get("moneda") or None)
        except Exception as e:
            rechazadas.append({"fila": numero,
                               "motivo": "; ".join(envios_config._legible(e))})
            continue
        validas.append({"fila": numero, **candidata.model_dump()})

    plan = {"validas": len(validas), "rechazadas": rechazadas,
            "total_rechazadas": len(rechazadas), "muestra": validas[:20]}
    if not confirmar:
        return {"ok": True, "confirmado": False, **plan}

    guardadas = 0
    for fila in validas:
        try:
            await envios_rentabilidad.aprobar(
                admin, transportista_id=transportista_id, clave=fila["clave"],
                hasta_kg=fila["hasta_kg"], precio=fila["precio"],
                moneda=fila["moneda"], origen="manual")
            guardadas += 1
        except Exception as e:
            # Una fila rechazada por el validador de negocio —un precio en cero,
            # un tope ilegible— no aborta el resto: se suma a la misma lista que
            # la persona corrige y vuelve a subir.
            rechazadas.append({"fila": fila["fila"], "motivo": str(e)})
    invalidar_cache()
    await envios_config.auditar(
        "matrices_referencia", {},
        {"importacion": {"transportista_id": transportista_id, "guardadas": guardadas,
                         "rechazadas": len(rechazadas)}},
        admin, accion="importar")
    return {"ok": True, "confirmado": True, "guardadas": guardadas,
            "validas": len(validas), "rechazadas": rechazadas,
            "total_rechazadas": len(rechazadas)}


# ─── Los caminos que no son el feliz, y el flete del tramo final ──────────

class Desvio(BaseModel):
    # El motivo no es burocracia: estos estados abren consecuencias —una
    # indemnizacion, una devolucion, un reclamo— y dentro de seis meses la unica
    # forma de entender por que un paquete termino asi es lo que alguien
    # escribio aca.
    motivo: str = Field(min_length=10, max_length=500)


@router.post("/envios/{envio_id}/desviar/{hacia}")
async def desviar_envio(envio_id: str, hacia: str, datos: Desvio,
                        admin: User = Depends(get_admin_user)):
    """Lleva un envío a `retenido`, `devuelto`, `siniestrado` o `cancelado`.

    Sin esta ruta, la mitad de las transiciones que la máquina de estados declara
    no las implementaba nadie: un paquete cuya guarda vencía y que la agencia
    devolvía al remitente se quedaba en `disponible_retiro` para siempre.
    """
    try:
        return await envios_operacion.desviar(admin, envio_id, hacia,
                                              motivo=datos.motivo)
    except Exception as e:
        raise _operacion(e)


class Flete(BaseModel):
    monto_ris: str = Field(min_length=1, max_length=20)


@router.put("/envios/{envio_id}/flete")
async def cargar_flete(envio_id: str, datos: Flete,
                       admin: User = Depends(get_crm_user)):
    """Registra lo que el transportista de destino pidió por el tramo final.

    Lo carga el operador parado en el mostrador, porque hasta ese momento el
    precio no existe: nadie puede cotizarlo antes. **No es un cobro de RIS App**
    — es el número que el usuario tiene que enviar como remesa.
    """
    try:
        return await envios_operacion.cargar_flete(admin, envio_id,
                                                   monto=datos.monto_ris)
    except Exception as e:
        raise _operacion(e)


class AcreditacionFlete(BaseModel):
    referencia: str = Field(default="", max_length=80)


@router.post("/envios/{envio_id}/flete/acreditar")
async def acreditar_flete(envio_id: str, datos: AcreditacionFlete,
                          admin: User = Depends(get_admin_user)):
    """Marca que la remesa del usuario al transportista llegó.

    Es lo que destraba la entrega en modalidad prepago. Lo confirma una persona
    porque la remesa se ejecuta por fuera de este módulo y nadie de acá puede
    verla llegar. Sin esta ruta, un envío `prepago` no se podía entregar nunca.
    """
    try:
        return await envios_operacion.acreditar_flete(
            admin, envio_id, referencia=datos.referencia)
    except Exception as e:
        raise _operacion(e)


@router.get("/envios/{envio_id}/foto/{asset_id}")
async def ver_foto_admin(envio_id: str, asset_id: str,
                         admin: User = Depends(get_crm_user)):
    """La foto de un envío, para el operador.

    Sin esto, la ruta que le pide al operador "lo que LEE en la foto del
    comprobante" le pedía tipear un peso a ciegas: la única ruta que servía
    archivos exigía ser el dueño del envío.
    """
    from services import envios_archivos
    ficha = await envios_archivos.leer(asset_id, envio_id=envio_id)
    try:
        envios_archivos.exigir_bytes(ficha)
    except envios_archivos.ArchivoRechazado as e:
        raise HTTPException(e.http, e.mensaje)
    return Response(content=bytes(ficha["contenido"]),
                    media_type=ficha.get("content_type") or "image/jpeg",
                    headers={"Cache-Control": "private, max-age=300"})


# --- El almacén de las fotos ------------------------------------------------
#
# Tres rutas, y ninguna edita credenciales. Las credenciales viven en variables
# de entorno (ver services/envios_almacen.py): una clave con permiso de escritura
# sobre el bucket es la capacidad de reemplazar cualquier comprobante del
# historial, y eso no se edita desde una pantalla web ni se guarda en la misma
# base que el log de auditoría.
#
# Lo que el panel SÍ necesita es contestar tres preguntas: ¿está prendido?,
# ¿funciona?, ¿cuánto falta mover?


class Migracion(BaseModel):
    # Los topes salen del servicio, no de acá. Duplicarlos hace que subir el
    # máximo en `envios_archivos` deje la ruta rechazando 51 con un 422 y nadie
    # entienda por qué.
    limite: int = Field(default=MIGRACION_LOTE_POR_DEFECTO, ge=1,
                        le=MIGRACION_LOTE_MAX)


@router.get("/almacen")
async def estado_almacen(admin: User = Depends(get_super_admin)):
    """Dónde están los bytes hoy. Sin la clave ni el secreto, nunca."""
    from services import envios_almacen, envios_archivos
    try:
        return {**envios_almacen.estado(), **(await envios_archivos.conteo())}
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: no se pudo leer el estado del almacén: {e}")
        raise HTTPException(
            503, "No se pudo leer el estado del almacén. Probá de nuevo.")


@router.post("/almacen/probar")
async def probar_almacen(admin: User = Depends(get_super_admin)):
    """Escribe y lee un objeto minúsculo contra el bucket.

    Existe para que el super administrador descubra que la credencial está mal
    ANTES de migrar tres mil fotos, y no en el medio.
    """
    from services import envios_almacen
    try:
        return await envios_almacen.probar()
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: no se pudo probar el almacén: {e}")
        raise HTTPException(503, "No se pudo probar el almacén. Probá de nuevo.")


@router.post("/almacen/migrar")
async def migrar_almacen(datos: Migracion = None,
                         admin: User = Depends(get_super_admin)):
    """Mueve un lote de fotos de Mongo al almacén de objetos.

    Por lotes y reanudable: se llama de nuevo hasta que `en_mongo` llegue a cero.
    Cada archivo se escribe, se vuelve a leer y se compara antes de borrarlo de
    Mongo — nunca al revés.
    """
    from services import envios_archivos
    limite = datos.limite if datos else MIGRACION_LOTE_POR_DEFECTO
    try:
        return await envios_archivos.migrar_lote(limite=limite)
    except Exception as e:                                    # pragma: no cover
        logger.error(f"envios: la migración de archivos falló: {e}")
        raise HTTPException(
            503, "No se pudo migrar el lote. Probá de nuevo en un minuto.")
