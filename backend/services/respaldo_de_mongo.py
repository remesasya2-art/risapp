"""
El respaldo de la base de la aplicación, y la prueba de que se puede leer.

POR QUE EXISTE

    Mongo está alojado en Railway, que no respalda la base por su cuenta.
    Sin esto, la única copia de cada cuenta, cada envío y cada línea del
    libro es la que está en ese servidor. Un respaldo que se baja y se guarda
    afuera es la diferencia entre un mal día y el fin de la operación.

QUE SE EXPORTA

    Las colecciones que hay que conservar (`COLECCIONES_QUE_SE_CONSERVAN`):
    las cuentas, las verificaciones, los envíos y las órdenes, los cobros por
    PIX y tarjeta, los libros (RIS, cripto, bancos), los saldos y lotes
    cripto, la configuración, la lista negra, los beneficiarios, las cuentas
    bancarias, los transportistas y agencias, la mesa de ayuda, los avisos de
    pago ya procesados y los libros de auditoría. NO se exportan las
    sesiones, los códigos de un solo uso ni las cosas que se regeneran solas
    (tasas del BCV, notificaciones, contadores).

    El formato es una línea JSON por documento (JSON Lines), en el JSON
    extendido de Mongo (`bson.json_util`, forma canónica): las fechas, los
    Decimal128, los binarios cifrados del cofre y los ObjectId se conservan
    con su tipo, y `mongoimport` lo lee tal cual. La primera línea es la
    cabecera; la última, el cierre, con la cantidad de documentos y el
    SHA-256 de todo lo anterior.

EL RESPALDO ES SENSIBLE

    Lleva los datos personales de cada cliente y los documentos del cofre
    (cifrados, pero ahí). Se guarda donde se guardaría la base misma, y se
    baja sólo un super administrador. La aplicación asienta en la auditoría
    quién lo bajó y cuándo.

LA FIRMA Y LA COMPROBACION

    Con la variable `LLAVE_DE_RESPALDO` (o, si no está, la del núcleo,
    `NUCLEO_SECRETO_LLAVE_DE_RESPALDO`) el archivo se firma con HMAC-SHA256.
    `comprobar` verifica el hash del cierre, la firma, la cantidad de
    documentos y que cada línea se pueda leer. Un respaldo que no se probó
    es una esperanza; la pantalla tiene el botón para probarlo.

LA FIRMA VA SOBRE LA HUELLA, Y VIAJA ADENTRO DEL ARCHIVO

    La primera versión firmaba el contenido entero y mostraba la firma en la
    pantalla, en un texto que desaparecía al moverse. El dueño del proyecto
    creó cuatro respaldos y no llegó a guardar ninguna firma. Y comprobarlos
    exigía SUBIR el archivo entero: con 70 MB, desde una conexión de casa,
    el pedido moría por tiempo en Cloudflare antes de llegar.

    Ahora la firma es HMAC-SHA256 sobre la HUELLA (el SHA-256 del contenido),
    que vale lo mismo —un SHA-256 no se falsifica— y se puede verificar con
    sólo la huella en la mano. Y va escrita en la última línea del archivo,
    `{"tipo":"firma",...}`, después del cierre: el archivo se basta solo, y
    no hay nada que copiar. La huella registrada en la base sigue siendo la
    del contenido SIN esa última línea, que es lo que se firmó.

    Así el navegador puede hacer la lectura pesada —cada línea, el hash del
    cierre, la cuenta de documentos— y mandarle al servidor sólo la huella y
    la firma (`comprobar_huella`). Las firmas del esquema anterior, sobre el
    contenido entero, se siguen aceptando cuando se comprueba con el archivo
    (`comprobar`), para que los cuatro respaldos de septiembre de 2026 no
    queden huérfanos.
"""
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from bson import json_util

logger = logging.getLogger(__name__)

VERSION = 1
TIPO = "respaldo_risapp"
COLECCION_DEL_REGISTRO = "respaldos"

COLECCIONES_QUE_SE_CONSERVAN = (
    "users", "verifications", "kyc_audit_log", "beneficiaries", "blacklist",
    "transactions", "gestor_transactions", "btc_remesas", "btc_ves_wallets",
    "gestor_pix_payments", "card_payments", "processed_webhooks", "admin_payment_records",
    "ledger", "bank_ledger", "gateway_fee_ledger", "usdt_ledger", "usdt_balance", "usdt_lots", "usdt_operations", "crypto_deposits",
    "bank_accounts", "transportistas", "agencias", "origenes_brasil", "matrices_referencia", "codigos_de_cambio",
    "config", "app_settings", "settings", "policies", "accounting_rates", "exchange_rates", "rate_history",
    "soporte_casos", "soporte_mensajes", "soporte_pedidos", "quick_replies", "support_requests",
    "auditoria", "audit_log", "accounting_audit_log", "btc_config_audit", "admin_access_log", "centro_gestion_log",
    "colaboradores_retiro", "ratings", "cpf_tomados", "invitaciones_personal",
)

VARIABLES_DE_LA_LLAVE = ("LLAVE_DE_RESPALDO", "NUCLEO_SECRETO_LLAVE_DE_RESPALDO")


def _llave() -> Optional[str]:
    for v in VARIABLES_DE_LA_LLAVE:
        valor = (os.environ.get(v) or "").strip()
        if valor:
            return valor
    return None


def hay_llave() -> bool:
    return _llave() is not None


def _linea(obj) -> str:
    return json_util.dumps(obj, json_options=json_util.CANONICAL_JSON_OPTIONS, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _hmac(llave: str, texto: str) -> str:
    return hmac.new(llave.encode("utf-8"), texto.encode("utf-8"), hashlib.sha256).hexdigest()


def firmar_huella(huella: str) -> Optional[str]:
    """La firma de un respaldo: HMAC-SHA256 de su huella. Ver el encabezado."""
    llave = _llave()
    if not llave:
        return None
    return _hmac(llave, huella)


def firmar(contenido: str) -> Optional[str]:
    return firmar_huella(_hash(contenido))


def _firma_verifica(firma: str, huella: str, contenido: Optional[str] = None) -> Optional[bool]:
    """None sin llave. Acepta el esquema actual (sobre la huella) y, si hay
    contenido, el anterior (sobre el contenido entero)."""
    llave = _llave()
    if not llave:
        return None
    if hmac.compare_digest(_hmac(llave, huella), firma):
        return True
    return contenido is not None and hmac.compare_digest(_hmac(llave, contenido), firma)


def linea_de_firma(huella: str, firma: Optional[str], documentos: int) -> str:
    return _linea({"tipo": "firma", "hash": huella, "firma": firma, "documentos": documentos})


def partir(archivo: str) -> tuple:
    """(contenido firmado, firma de la última línea o None). Un archivo sin
    línea de firma —los del esquema anterior— vuelve entero y sin firma."""
    recortado = archivo[:-1] if archivo.endswith("\n") else archivo
    corte = recortado.rfind("\n")
    ultima = recortado[corte + 1:]
    if ultima.startswith('{"documentos"') or ultima.startswith('{"firma"') or '"tipo":"firma"' in ultima:
        try:
            datos = json_util.loads(ultima)
        except Exception:
            return archivo, None
        if datos.get("tipo") == "firma":
            return recortado[:corte + 1], datos.get("firma") or None
    return archivo, None


async def exportar(db, *, actor: str, ahora: Optional[datetime] = None) -> tuple:
    """(contenido, firma o None, resumen). Todo en memoria: la base de hoy
    entra de sobra; el día que no entre, esto pasa a ser un flujo."""
    ahora = ahora or datetime.now(timezone.utc)
    lineas = [_linea({"tipo": TIPO, "version": VERSION, "momento": ahora.isoformat(), "actor": actor,
                      "colecciones": list(COLECCIONES_QUE_SE_CONSERVAN)})]
    por_coleccion = {}
    for nombre in COLECCIONES_QUE_SE_CONSERVAN:
        cuantos = 0
        async for doc in db[nombre].find({}):
            lineas.append(_linea({"coleccion": nombre, "doc": doc}))
            cuantos += 1
        por_coleccion[nombre] = cuantos
    cuerpo = "\n".join(lineas) + "\n"
    total = sum(por_coleccion.values())
    contenido = cuerpo + _linea({"tipo": "fin", "documentos": total, "hash": _hash(cuerpo)}) + "\n"
    firma = firmar(contenido)
    resumen = {"documentos": total, "colecciones": {k: v for k, v in por_coleccion.items() if v},
               "bytes": len(contenido.encode("utf-8")), "hash": _hash(contenido), "firmado": firma is not None}
    return contenido, firma, resumen


async def crear(db, *, quien, request=None, ahora: Optional[datetime] = None) -> dict:
    """Exporta, registra y asienta en la auditoría. Devuelve el contenido
    para que quien lo pidió lo guarde afuera; la base sólo guarda el
    registro."""
    from services import auditoria
    ahora = ahora or datetime.now(timezone.utc)
    actor = getattr(quien, "user_id", None) or (quien or {}).get("user_id") or "sistema"
    contenido, firma, resumen = await exportar(db, actor=actor, ahora=ahora)
    registro = {"momento": ahora, "actor": actor, "documentos": resumen["documentos"], "colecciones": resumen["colecciones"],
                "bytes": resumen["bytes"], "hash": resumen["hash"], "firmado": resumen["firmado"],
                # Los registros anteriores a septiembre de 2026 no tienen este campo:
                # su firma es sobre el contenido entero y no se puede juzgar por la huella.
                "esquema_de_firma": "huella",
                "comprobado_en": None, "comprobacion": None}
    r = await db[COLECCION_DEL_REGISTRO].insert_one(dict(registro))
    await auditoria.registrar(db, "respaldo.creado", quien=quien, request=request, objetivo_tipo="respaldo",
                              objetivo_id=resumen["hash"][:16], detalle={"documentos": resumen["documentos"], "bytes": resumen["bytes"],
                                                                        "firmado": resumen["firmado"]})
    archivo = contenido + linea_de_firma(resumen["hash"], firma, resumen["documentos"])
    return {"id": str(r.inserted_id), **_para_mostrar(registro), "contenido": archivo, "firma": firma}


def comprobar(contenido: str, firma: Optional[str] = None) -> dict:
    """Lo que un auditor haría con el archivo en la mano. Si el archivo trae
    la línea de firma y no se pasa otra, se usa ésa."""
    contenido, firma_del_archivo = partir(contenido)
    firma = firma or firma_del_archivo
    salida = {"ok": False, "hash_ok": False, "firma": "sin_firma", "documentos": 0, "colecciones": {}, "motivo": None}
    lineas = contenido.split("\n")
    if lineas and lineas[-1] == "":
        lineas.pop()
    if len(lineas) < 2:
        salida["motivo"] = "el archivo no tiene cabecera y cierre"
        return salida
    try:
        cabecera, cierre = json_util.loads(lineas[0]), json_util.loads(lineas[-1])
    except Exception:
        salida["motivo"] = "la cabecera o el cierre no son JSON"
        return salida
    if cabecera.get("tipo") != TIPO or cierre.get("tipo") != "fin":
        salida["motivo"] = "no es un respaldo de la aplicación"
        return salida
    cuerpo = "\n".join(lineas[:-1]) + "\n"
    salida["hash_ok"] = _hash(cuerpo) == cierre.get("hash")
    if not salida["hash_ok"]:
        salida["motivo"] = "el hash del cierre no coincide con el contenido: el archivo fue alterado o está incompleto"
        return salida
    if firma:
        verifica = _firma_verifica(firma, _hash(contenido), contenido)
        if verifica is None:
            salida["firma"] = "sin_llave"
        else:
            salida["firma"] = "ok" if verifica else "invalida"
            if salida["firma"] == "invalida":
                salida["motivo"] = "la firma no es la de la llave de respaldo"
                return salida
    for i, l in enumerate(lineas[1:-1], start=2):
        try:
            fila = json_util.loads(l)
            nombre = fila["coleccion"]
            fila["doc"]
        except Exception:
            salida["motivo"] = f"la línea {i} no se puede leer"
            return salida
        salida["colecciones"][nombre] = salida["colecciones"].get(nombre, 0) + 1
        salida["documentos"] += 1
    if salida["documentos"] != cierre.get("documentos"):
        salida["motivo"] = f"el cierre dice {cierre.get('documentos')} documentos y hay {salida['documentos']}"
        return salida
    salida["ok"] = True
    return salida


async def comprobar_y_anotar(db, contenido: str, firma: Optional[str], *, quien, request=None,
                             ahora: Optional[datetime] = None) -> dict:
    from services import auditoria
    ahora = ahora or datetime.now(timezone.utc)
    resultado = comprobar(contenido, firma)
    h = _hash(partir(contenido)[0])
    conocido = await db[COLECCION_DEL_REGISTRO].find_one({"hash": h})
    if conocido is not None:
        await db[COLECCION_DEL_REGISTRO].update_one({"_id": conocido["_id"]}, {"$set": {"comprobado_en": ahora, "comprobacion": resultado}})
    await auditoria.registrar(db, "respaldo.comprobado", quien=quien, request=request, objetivo_tipo="respaldo", objetivo_id=h[:16],
                              detalle={"ok": resultado["ok"], "firma": resultado["firma"], "documentos": resultado["documentos"],
                                       "registrado": conocido is not None, "motivo": resultado["motivo"]}, exito=resultado["ok"])
    return {**resultado, "hash": h, "registrado": conocido is not None}


async def comprobar_huella(db, *, huella: str, documentos: int, hash_de_cierre_ok: bool, lineas_ok: bool,
                           colecciones: Optional[dict] = None, firma: Optional[str] = None, motivo_del_navegador: Optional[str] = None,
                           quien, request=None, ahora: Optional[datetime] = None) -> dict:
    """La comprobación cuando la lectura pesada la hizo el navegador y acá
    llegan sólo la huella, la cuenta y lo que encontró. El servidor pone lo
    que el navegador no puede: la firma (necesita la llave) y si esa huella
    es la de un respaldo que esta base registró.

    Lo que informa el navegador se guarda diciendo que lo informó él: es una
    comprobación que el super administrador se hace a sí mismo, no una
    frontera de seguridad."""
    from services import auditoria
    ahora = ahora or datetime.now(timezone.utc)
    huella = (huella or "").strip().lower()
    salida = {"ok": False, "hash_ok": bool(hash_de_cierre_ok), "firma": "sin_firma", "documentos": int(documentos),
              "colecciones": dict(colecciones or {}), "motivo": None, "hash": huella, "registrado": False, "en": "navegador"}
    conocido = await db[COLECCION_DEL_REGISTRO].find_one({"hash": huella})
    salida["registrado"] = conocido is not None
    if firma:
        verifica = _firma_verifica(firma, huella)
        if verifica is None:
            salida["firma"] = "sin_llave"
        elif verifica:
            salida["firma"] = "ok"
        elif conocido is not None and conocido.get("firmado") and conocido.get("esquema_de_firma") != "huella":
            # Un respaldo del esquema anterior: su firma es sobre el contenido
            # entero, que acá no está. No se puede juzgar sin el archivo, y se
            # dice así en vez de llamarla inválida.
            salida["firma"] = "no_verificable_por_la_huella"
        else:
            salida["firma"] = "invalida"
    if not hash_de_cierre_ok:
        salida["motivo"] = motivo_del_navegador or "el hash del cierre no coincide con el contenido: el archivo fue alterado o está incompleto"
    elif not lineas_ok:
        salida["motivo"] = motivo_del_navegador or "alguna línea no se puede leer"
    elif conocido is None:
        # Antes que la firma: una huella que esta base no registró es un
        # archivo de otra base o alterado, y eso explica también que la firma
        # no cierre.
        salida["motivo"] = "esa huella no figura entre los respaldos registrados en esta base"
    elif salida["firma"] == "invalida":
        salida["motivo"] = "la firma no es la de la llave de respaldo"
    elif conocido.get("documentos") != int(documentos):
        salida["motivo"] = f"el registro dice {conocido.get('documentos')} documentos y el archivo tiene {documentos}"
    else:
        salida["ok"] = True
    if conocido is not None:
        await db[COLECCION_DEL_REGISTRO].update_one({"_id": conocido["_id"]}, {"$set": {"comprobado_en": ahora, "comprobacion": salida}})
    await auditoria.registrar(db, "respaldo.comprobado", quien=quien, request=request, objetivo_tipo="respaldo", objetivo_id=huella[:16],
                              detalle={"ok": salida["ok"], "firma": salida["firma"], "documentos": salida["documentos"],
                                       "registrado": salida["registrado"], "motivo": salida["motivo"], "en": "navegador"}, exito=salida["ok"])
    return salida


def _para_mostrar(r: dict) -> dict:
    return {"momento": r["momento"].isoformat() if hasattr(r["momento"], "isoformat") else r["momento"], "actor": r["actor"],
            "documentos": r["documentos"], "colecciones": r["colecciones"], "bytes": r["bytes"], "hash": r["hash"],
            "firmado": bool(r.get("firmado")),
            "comprobado_en": r["comprobado_en"].isoformat() if hasattr(r.get("comprobado_en"), "isoformat") else r.get("comprobado_en"),
            "comprobacion": r.get("comprobacion")}


async def listar(db, limite: int = 30) -> list:
    salida = []
    async for r in db[COLECCION_DEL_REGISTRO].find({}).sort("momento", -1).limit(limite):
        salida.append({"id": str(r["_id"]), **_para_mostrar(r)})
    return salida
