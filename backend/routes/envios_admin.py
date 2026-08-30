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

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from database import db
from routes.dependencies import get_super_admin, get_crm_user
from models.user import User
from models.envios_config import Transportista, Agencia, CuentaBancaria, ESQUEMAS
from models.envios_tarifa import TarifaEnvio, TarifaBorrador, CajaDePrueba
from services import envios_config, envios_tarifa_editor
from services.envios_catalogo import invalidar_cache
from services.envios_tarifas import validar_tarifa

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/envios", tags=["envios-admin"])


def _error(errores: list[str]) -> HTTPException:
    return HTTPException(status_code=400, detail=" ".join(errores))


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

    for prohibido in ("codigo", "transportista_id", "cuenta_bancaria"):
        if prohibido in datos:
            raise HTTPException(
                400, f"El campo {prohibido} no se edita por acá." +
                     (" El código de un transportista no cambia nunca: los envíos "
                      "viejos lo referencian." if prohibido == "codigo" else
                      " La cuenta bancaria tiene su propia ruta." if
                      prohibido == "cuenta_bancaria" else ""))

    fusionado = {**actual, **datos}
    fusionado.pop("transportista_id", None)
    fusionado.pop("creado_at", None)
    fusionado.pop("cuenta_bancaria", None)
    try:
        validado = Transportista(**fusionado).model_dump()
    except Exception as e:
        raise _error(envios_config._legible(e))

    validado.pop("cuenta_bancaria", None)      # no se toca desde acá
    await db.transportistas.update_one({"transportista_id": transportista_id},
                                       {"$set": validado})
    await envios_config.auditar("transportistas", actual, validado, admin)
    invalidar_cache()
    return {"ok": True, "valor": _sin_cuenta(validado)}


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
    """
    await db.agencias.update_many(
        {"transportista_id": transportista_id, "es_punto_entrega": True},
        {"$set": {"es_punto_entrega": False}})


@router.post("/transportistas/{transportista_id}/agencias/csv")
async def importar_agencias(transportista_id: str, archivo: UploadFile = File(...),
                            admin: User = Depends(get_super_admin)):
    """Importa agencias desde un CSV. Una fila mala no aborta la importación.

    Es la diferencia entre un CSV de doscientas agencias que entra con tres
    rechazadas y un CSV que no entra nunca porque la fila 87 tiene el estado en
    blanco. El informe dice cuáles fallaron y por qué, y esa lista es lo que la
    persona corrige y vuelve a subir.
    """
    if not await db.transportistas.find_one({"transportista_id": transportista_id}):
        raise HTTPException(404, "Transportista no encontrado")

    try:
        crudo = (await archivo.read()).decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "El archivo no está en UTF-8. Guardalo de nuevo como CSV UTF-8.")

    creadas, actualizadas, rechazadas = 0, 0, []
    for numero, fila in enumerate(csv.DictReader(io.StringIO(crudo)), start=2):
        limpia = {k.strip(): (v.strip() if isinstance(v, str) else v)
                  for k, v in fila.items() if k}
        for booleano in ("activa", "es_punto_entrega"):
            if booleano in limpia:
                limpia[booleano] = str(limpia[booleano]).strip().lower() in (
                    "1", "true", "si", "sí", "x")
        try:
            validada = Agencia(**limpia).model_dump()
        except Exception as e:
            rechazadas.append({"fila": numero, "motivo": "; ".join(envios_config._legible(e))})
            continue

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
