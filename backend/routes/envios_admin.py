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
from models.envios_config import (Transportista, Agencia, CuentaBancaria,
                                  Colaborador, ConfigPuntoOrigen, ESQUEMAS)
from models.envios_tarifa import TarifaEnvio, TarifaBorrador, CajaDePrueba
from services import envios_config, envios_retiro, envios_tarifa_editor
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
