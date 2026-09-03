"""
Recursos Humanos — el legajo del personal y la única puerta de alta.

QUE CAMBIA RESPECTO DE LO QUE HABIA

    Antes, el personal se creaba desde la pantalla de usuarios con
    `POST /admin/sub-admins`, y esa ruta hacía dos cosas peligrosas:

      - Si el correo ya existía, PROMOVÍA esa cuenta a `admin` sin más. Un
        usuario cualquiera, con su saldo y sus transacciones, pasaba a ser
        personal de un plumazo.
      - Si no existía, creaba un usuario con `verification_status: "verified"`
        puesto a mano —una cuenta dada por verificada que nunca pasó por KYC—
        y sin contraseña, así que en la práctica no podía entrar.

    Y ninguna de las dos dejaba rastro en ningún libro.

    Acá el alta es explícita, deja legajo, deja línea de auditoría, y no
    inventa una verificación que nadie hizo.

LAS REGLAS

    1. Sólo el super administrador entra a esta sección. Ni un `admin` con
       todos los permisos: el alta de personal no es un permiso que se delega.
    2. No se da de alta a alguien con saldo. Su plata quedaría encerrada,
       porque el personal no puede hacer transacciones. Se rechaza y se avisa
       que la retire primero.
    3. Todo movimiento —alta, baja, cambio de permisos, cambio de legajo—
       queda asentado en el libro de auditoría con fecha, hora, quién, sobre
       quién, y qué había antes.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from database import db
from models.user import User
from routes.dependencies import get_super_admin
from services import auditoria, invitaciones, personal
from services.email import send_staff_invitation_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/rrhh", tags=["Recursos Humanos"])

# Los campos del legajo que se pueden editar. Se declara para que agregar uno
# sea una decisión y no un descuido: cualquier otra clave que llegue en el
# cuerpo se ignora.
CAMPOS_DEL_LEGAJO = (
    "nombre_completo", "documento", "telefono", "cargo", "area",
    "fecha_ingreso", "notas",
)


class AltaDePersonal(BaseModel):
    email: EmailStr
    nombre_completo: str = Field(..., min_length=2, max_length=120)
    cargo: str = Field(..., min_length=2, max_length=80)
    area: str = Field(..., min_length=2, max_length=80)
    documento: Optional[str] = Field(None, max_length=40)
    telefono: Optional[str] = Field(None, max_length=40)
    fecha_ingreso: Optional[str] = None
    notas: Optional[str] = Field(None, max_length=1000)
    permisos: List[str] = Field(default_factory=list)


class CambioDePermisos(BaseModel):
    permisos: List[str]
    motivo: Optional[str] = Field(None, max_length=300)


class CambioDeLegajo(BaseModel):
    nombre_completo: Optional[str] = Field(None, min_length=2, max_length=120)
    cargo: Optional[str] = Field(None, min_length=2, max_length=80)
    area: Optional[str] = Field(None, min_length=2, max_length=80)
    documento: Optional[str] = Field(None, max_length=40)
    telefono: Optional[str] = Field(None, max_length=40)
    fecha_ingreso: Optional[str] = None
    notas: Optional[str] = Field(None, max_length=1000)


class Baja(BaseModel):
    motivo: str = Field(..., min_length=3, max_length=300)


def _permisos_validos(pedidos: List[str]) -> List[str]:
    """Sólo los permisos del catálogo. Uno inventado se rechaza en vez de
    guardarse: un permiso que no existe nunca se cumple, y quien lo cargó
    cree que sí."""
    from admin_routes import ADMIN_PERMISSIONS
    desconocidos = [p for p in pedidos if p not in ADMIN_PERMISSIONS]
    if desconocidos:
        raise HTTPException(
            status_code=400,
            detail=f"Permisos que no existen: {', '.join(desconocidos)}")
    # Sin repetidos y en orden, para que el 'antes/después' del libro se
    # pueda comparar de un vistazo.
    return sorted(set(pedidos))


def _legajo_de(doc: dict) -> dict:
    return {c: (doc.get("legajo") or {}).get(c) for c in CAMPOS_DEL_LEGAJO}


def _acceso(doc: dict, invitacion: Optional[dict]) -> dict:
    """Cómo está el acceso de esta persona: clave, dos pasos, invitación.

    Es lo que hay que poder mirar de un vistazo para saber si alguien con
    permisos de administración todavía no terminó de asegurar su cuenta.
    """
    return {
        "clave_configurada": bool(doc.get("password_set") and doc.get("password_hash")),
        "correo_verificado": bool(doc.get("email_verified")),
        "dos_pasos": bool(doc.get("two_factor_enabled")),
        "invitacion": invitacion or {"estado": invitaciones.SIN_INVITACION,
                                     "expira_en": None, "usada_en": None},
    }


def _ficha(doc: dict) -> dict:
    """Lo que se muestra en la lista. Nunca las imágenes de documentos."""
    return {
        "user_id": doc.get("user_id"),
        "email": doc.get("email"),
        "nombre": doc.get("name"),
        "rol": doc.get("role"),
        "activo": bool(doc.get("is_active", True)),
        "permisos": sorted(doc.get("permissions") or []),
        "legajo": _legajo_de(doc),
        "alta": (doc.get("legajo") or {}).get("dado_de_alta_en"),
        "baja": (doc.get("legajo") or {}).get("dado_de_baja_en"),
    }


async def _invitar(doc: dict, admin: User, request: Request,
                   motivo: str) -> dict:
    """Emite la invitación de primer acceso y la manda por correo.

    Devuelve qué pasó, para que la respuesta del alta le diga al super
    administrador si el correo salió o no. Si Resend está caído, el alta NO
    se cae: la persona queda creada y la invitación se reenvía después.
    """
    token = await invitaciones.emitir(
        db, user_id=doc["user_id"], email=doc["email"],
        emitida_por=admin.user_id)

    enviado = await send_staff_invitation_email(
        doc["email"], doc.get("name") or doc["email"],
        (doc.get("legajo") or {}).get("cargo") or "colaborador", token)

    # El token no entra al libro. Una línea de auditoría con la llave adentro
    # convierte al libro —que mucha gente puede leer— en la propia llave.
    await auditoria.registrar(
        db, "personal.invitacion", quien=admin, request=request,
        objetivo_tipo="usuario", objetivo_id=doc["user_id"],
        objetivo_desc=doc["email"],
        despues={"invitacion": "emitida",
                 "vence_en_horas": invitaciones.HORAS_DE_VIDA},
        detalle={"motivo": motivo, "correo_enviado": enviado},
        exito=enviado)

    if not enviado:
        logger.error(
            "INVITACION SIN ENVIAR: %s quedó dada de alta pero el correo de "
            "activación no salió. Reenviala desde RRHH.", doc["email"])

    return {"emitida": True, "correo_enviado": enviado,
            "vence_en_horas": invitaciones.HORAS_DE_VIDA}


def _puede_entrar_ya(doc: dict) -> bool:
    """Si esta cuenta ya tiene con qué entrar por su cuenta.

    Un usuario que existía y se convirtió en personal ya tiene contraseña y
    correo verificado: no necesita invitación, y mandarle una sería darle una
    segunda llave por correo sin motivo. Una cuenta nueva no tiene ninguna de
    las dos cosas.
    """
    return bool(doc.get("password_set") and doc.get("password_hash")
                and doc.get("email_verified"))


# ─── Catálogo ─────────────────────────────────────────────────────────────

@router.get("/permisos")
async def catalogo_de_permisos(admin: User = Depends(get_super_admin)):
    """Los permisos que se pueden otorgar, con su nombre legible."""
    from admin_routes import ADMIN_PERMISSIONS
    return {"permisos": ADMIN_PERMISSIONS}


# ─── Legajos ──────────────────────────────────────────────────────────────

@router.get("")
async def listar_personal(incluir_bajas: bool = False,
                          admin: User = Depends(get_super_admin)):
    filtro = {personal.CAMPO: True}
    if not incluir_bajas:
        filtro["is_active"] = {"$ne": False}
    cursor = db.users.find(filtro).sort("email", 1)
    docs = [d async for d in cursor]
    estados = await invitaciones.estado_de_varios(
        db, [d.get("user_id") for d in docs if d.get("user_id")])
    fichas = [{**_ficha(d), "acceso": _acceso(d, estados.get(d.get("user_id")))}
              for d in docs]
    return {"personal": fichas, "total": len(fichas)}


@router.get("/{user_id}")
async def ver_legajo(user_id: str, admin: User = Depends(get_super_admin)):
    doc = await db.users.find_one({"user_id": user_id, personal.CAMPO: True})
    if not doc:
        raise HTTPException(status_code=404, detail="No es personal de la empresa")
    acceso = _acceso(doc, await invitaciones.estado(db, user_id))
    historial = await auditoria.buscar(db, objetivo_id=user_id, limite=100)
    return {"ficha": {**_ficha(doc), "acceso": acceso},
            "historial": historial["lineas"]}


@router.post("")
async def dar_de_alta(datos: AltaDePersonal, request: Request,
                      admin: User = Depends(get_super_admin)):
    """Da de alta a una persona como personal de la empresa.

    Si el correo ya tiene cuenta de usuario, se la convierte — pero sólo si
    NO tiene saldo, porque el personal no puede hacer transacciones y esa
    plata quedaría encerrada.
    """
    permisos = _permisos_validos(datos.permisos)
    email = datos.email.lower().strip()
    ahora = datetime.now(timezone.utc)

    existente = await db.users.find_one({"email": email})

    if existente and personal.es_personal(existente):
        raise HTTPException(status_code=409,
                            detail=f"{email} ya es personal de la empresa")

    if existente:
        atascado = await personal.saldo_en_cero(db, existente["user_id"])
        if atascado:
            raise HTTPException(
                status_code=409,
                detail=(f"{email} tiene {atascado}. El personal no puede hacer "
                        f"transacciones, así que ese saldo quedaría encerrado: "
                        f"que lo retire antes del alta."))

    legajo = {c: getattr(datos, c, None) for c in CAMPOS_DEL_LEGAJO}
    legajo["nombre_completo"] = datos.nombre_completo
    legajo["dado_de_alta_en"] = ahora
    legajo["dado_de_alta_por"] = admin.user_id

    campos = {
        personal.CAMPO: True,
        "role": personal.ROL_PERSONAL,
        "permissions": permisos,
        "legajo": legajo,
        "is_active": True,
        "name": datos.nombre_completo,
        "updated_at": ahora,
    }

    if existente:
        antes = {"rol": existente.get("role"),
                 "permisos": sorted(existente.get("permissions") or []),
                 "es_personal": False}
        await db.users.update_one({"user_id": existente["user_id"]},
                                  {"$set": campos})
        user_id = existente["user_id"]
        convertido = True
    else:
        # Cuenta nueva. NO se marca como verificada: dar por hecha una
        # verificación que nadie hizo es exactamente lo que hacía la ruta
        # vieja. Si esta persona además necesita operar como usuario, que se
        # registre y verifique por su cuenta — con otro correo, porque éste
        # ya no puede transaccionar.
        import uuid
        user_id = f"emp_{uuid.uuid4().hex[:12]}"
        antes = None
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": datos.nombre_completo,
            "role": personal.ROL_PERSONAL,
            "permissions": permisos,
            personal.CAMPO: True,
            "legajo": legajo,
            "is_active": True,
            "verification_status": "unverified",
            "created_at": ahora,
        })
        convertido = False

    await auditoria.registrar(
        db, "personal.alta", quien=admin, request=request,
        objetivo_tipo="usuario", objetivo_id=user_id, objetivo_desc=email,
        antes=antes,
        despues={"rol": personal.ROL_PERSONAL, "permisos": permisos,
                 "es_personal": True, "legajo": legajo},
        detalle={"convertido_desde_usuario": convertido,
                 "cargo": datos.cargo, "area": datos.area})

    # La llave. Sin esto la cuenta nueva nace sin contraseña y sin correo
    # verificado, o sea que su dueño no puede entrar por ninguna puerta: el
    # login frena en `email_verified`, y el "olvidé mi contraseña" también.
    recien = await db.users.find_one({"user_id": user_id})
    if _puede_entrar_ya(recien or {}):
        acceso = {"emitida": False, "correo_enviado": False,
                  "motivo": "ya tenía contraseña y correo verificado"}
    else:
        acceso = await _invitar(recien or {}, admin, request, motivo="alta")

    return {"mensaje": f"{email} dado de alta como personal",
            "user_id": user_id, "convertido_desde_usuario": convertido,
            "acceso": acceso}


@router.post("/{user_id}/reenviar-invitacion")
async def reenviar_invitacion(user_id: str, request: Request,
                              admin: User = Depends(get_super_admin)):
    """Vuelve a mandar el correo de primer acceso.

    Emitir una invitación nueva ANULA la anterior, así que reenviar por un
    correo perdido no deja dos links vivos. Se niega si la persona ya
    configuró su clave: ahí el camino es "olvidé mi contraseña", que exige
    conocer la cuenta y no crea una llave nueva desde el panel.
    """
    doc = await db.users.find_one({"user_id": user_id, personal.CAMPO: True})
    if not doc:
        raise HTTPException(status_code=404, detail="No es personal de la empresa")
    if not doc.get("is_active", True):
        raise HTTPException(
            status_code=409,
            detail="Esta persona está dada de baja. Reactivala antes de invitarla.")
    if _puede_entrar_ya(doc):
        raise HTTPException(
            status_code=409,
            detail=("Esta persona ya tiene su acceso configurado. Si lo perdió, "
                    "que use 'olvidé mi contraseña' desde el login."))

    acceso = await _invitar(doc, admin, request, motivo="reenvío")
    return {"mensaje": f"Invitación reenviada a {doc['email']}", "acceso": acceso}


@router.put("/{user_id}/permisos")
async def cambiar_permisos(user_id: str, datos: CambioDePermisos,
                           request: Request,
                           admin: User = Depends(get_super_admin)):
    permisos = _permisos_validos(datos.permisos)
    doc = await db.users.find_one({"user_id": user_id, personal.CAMPO: True})
    if not doc:
        raise HTTPException(status_code=404, detail="No es personal de la empresa")

    antes = sorted(doc.get("permissions") or [])
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"permissions": permisos,
                  "updated_at": datetime.now(timezone.utc)}})

    await auditoria.registrar(
        db, "personal.permisos", quien=admin, request=request,
        objetivo_tipo="usuario", objetivo_id=user_id,
        objetivo_desc=doc.get("email"),
        antes={"permisos": antes}, despues={"permisos": permisos},
        detalle={"motivo": datos.motivo,
                 "agregados": sorted(set(permisos) - set(antes)),
                 "quitados": sorted(set(antes) - set(permisos))})

    return {"mensaje": "Permisos actualizados", "permisos": permisos}


@router.put("/{user_id}/legajo")
async def cambiar_legajo(user_id: str, datos: CambioDeLegajo, request: Request,
                         admin: User = Depends(get_super_admin)):
    doc = await db.users.find_one({"user_id": user_id, personal.CAMPO: True})
    if not doc:
        raise HTTPException(status_code=404, detail="No es personal de la empresa")

    cambios = {k: v for k, v in datos.model_dump().items() if v is not None}
    if not cambios:
        raise HTTPException(status_code=400, detail="Nada que cambiar")

    antes = _legajo_de(doc)
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {**{f"legajo.{k}": v for k, v in cambios.items()},
                  "updated_at": datetime.now(timezone.utc)}})

    await auditoria.registrar(
        db, "personal.datos", quien=admin, request=request,
        objetivo_tipo="usuario", objetivo_id=user_id,
        objetivo_desc=doc.get("email"),
        antes={k: antes.get(k) for k in cambios}, despues=cambios)

    return {"mensaje": "Legajo actualizado", "cambios": cambios}


@router.delete("/{user_id}")
async def dar_de_baja(user_id: str, datos: Baja, request: Request,
                      admin: User = Depends(get_super_admin)):
    """Baja: se le quitan los permisos, se desactiva y se cierran sus sesiones.

    No se borra el usuario. Borrarlo dejaría sin sentido cada línea del libro
    de auditoría que lo menciona, que es justo lo que hay que poder leer
    después de una baja.
    """
    doc = await db.users.find_one({"user_id": user_id, personal.CAMPO: True})
    if not doc:
        raise HTTPException(status_code=404, detail="No es personal de la empresa")
    if doc.get("role") == "super_admin":
        raise HTTPException(
            status_code=400,
            detail="No se puede dar de baja al super administrador desde acá.")

    ahora = datetime.now(timezone.utc)
    antes = {"rol": doc.get("role"),
             "permisos": sorted(doc.get("permissions") or []),
             "activo": bool(doc.get("is_active", True))}

    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"permissions": [], "role": "user", "is_active": False,
                  "legajo.dado_de_baja_en": ahora,
                  "legajo.dado_de_baja_por": admin.user_id,
                  "legajo.motivo_de_baja": datos.motivo,
                  "updated_at": ahora}})
    cerradas = await db.user_sessions.delete_many({"user_id": user_id})

    await auditoria.registrar(
        db, "personal.baja", quien=admin, request=request,
        objetivo_tipo="usuario", objetivo_id=user_id,
        objetivo_desc=doc.get("email"),
        antes=antes,
        despues={"rol": "user", "permisos": [], "activo": False},
        detalle={"motivo": datos.motivo,
                 "sesiones_cerradas": cerradas.deleted_count})

    return {"mensaje": "Persona dada de baja",
            "sesiones_cerradas": cerradas.deleted_count}


# ─── El libro ─────────────────────────────────────────────────────────────

@router.get("/auditoria/libro")
async def libro_de_auditoria(
    categoria: Optional[str] = None,
    accion: Optional[str] = None,
    actor_id: Optional[str] = None,
    objetivo_id: Optional[str] = None,
    limite: int = 100,
    saltar: int = 0,
    admin: User = Depends(get_super_admin),
):
    """El libro completo, filtrable. Sólo lectura: acá no se modifica nada."""
    return await auditoria.buscar(
        db, categoria=categoria, accion=accion, actor_id=actor_id,
        objetivo_id=objetivo_id, limite=limite, saltar=saltar)


@router.get("/auditoria/acciones")
async def acciones_auditables(admin: User = Depends(get_super_admin)):
    """El catálogo de acciones, para armar los filtros del panel."""
    return {"acciones": [
        {"accion": a, "categoria": c, "etiqueta": e}
        for a, (c, e) in sorted(auditoria.ACCIONES.items())]}
