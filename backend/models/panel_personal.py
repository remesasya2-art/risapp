"""
models/panel_personal.py — Lo que el panel ve del personal: la lista y el
legajo de Recursos Humanos, el libro de auditoría, el catálogo de permisos y
la lista de administradores.

CASI TODO YA SE ARMABA CAMPO POR CAMPO

    La ficha de cada persona sale de `_ficha` y `_acceso`
    (`routes/recursos_humanos.py`), que nunca traen la contraseña, la semilla
    del segundo factor ni las fotos de documentos. El contrato fija esos
    campos: el día que alguien le agregue «un dato más» a la ficha, no sale
    solo. Lo que no tenía ningún recorte es la línea del libro de auditoría,
    que salía tal cual se guarda; el contrato fija su forma.

EL LIBRO SE MUESTRA CON LA IP Y EL NAVEGADOR, A PROPOSITO

    Es para lo que existe: cuando algo pasó, saber desde dónde. Lo lee sólo
    el super administrador (`get_super_admin`), y la pantalla lo muestra
    (`LibroAuditoria.jsx`). Lo que el libro NUNCA guarda —el token de una
    invitación— se queda afuera antes de escribirse (`_invitar`), no acá.

`antes`, `despues` y `detalle` quedan libres

    Cada acción anota lo suyo: los permisos de antes y de después (una lista),
    los campos del legajo que cambiaron, el motivo de una baja. Fijarlos acá
    sería repetir el catálogo de acciones entero; el contrato fija la línea,
    y lo que cada acción anota es de la acción.

Un test (`tests/test_contratos_del_personal.py`) compara lo que leen las
pantallas de RRHH y del libro con cada contrato, y recorre las rutas.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar
from models.panel_usuarios import UsuarioQueVeElPanel


def _simple(nombre, campos, **extra):
    return create_model(nombre, **{c: (Escalar, None) for c in campos}, **extra)


# ── La ficha de una persona ───────────────────────────────────────────────

# Los mismos campos que `recursos_humanos.CAMPOS_DEL_LEGAJO`; un test compara
# las dos listas para que no se separen.
LegajoDelPersonal = _simple("LegajoDelPersonal", (
    "nombre_completo", "documento", "telefono", "cargo", "area", "fecha_ingreso", "notas"))

EstadoDeLaInvitacion = _simple("EstadoDeLaInvitacion", ("estado", "expira_en", "usada_en"))

AccesoDelPersonal = _simple("AccesoDelPersonal", ("clave_configurada", "correo_verificado", "dos_pasos"),
                            invitacion=(Optional[EstadoDeLaInvitacion], None))

FichaDelPersonal = _simple("FichaDelPersonal", ("user_id", "email", "nombre", "rol", "activo", "alta", "baja"),
                           permisos=(List[Escalar], []),
                           legajo=(Optional[LegajoDelPersonal], None),
                           acceso=(Optional[AccesoDelPersonal], None))


class ListaDelPersonal(BaseModel):
    personal: List[FichaDelPersonal] = []
    total: Escalar = None


# ── El libro de auditoría ─────────────────────────────────────────────────

ActorDeLaLinea = _simple("ActorDeLaLinea", ("user_id", "email", "nombre", "rol"))
ObjetivoDeLaLinea = _simple("ObjetivoDeLaLinea", ("tipo", "id", "descripcion"))
OrigenDeLaLinea = _simple("OrigenDeLaLinea", ("ip", "pais", "navegador"))

LineaDelLibro = _simple("LineaDelLibro", ("accion", "categoria", "etiqueta", "exito", "cuando", "cuando_caracas"),
                        actor=(Optional[ActorDeLaLinea], None),
                        objetivo=(Optional[ObjetivoDeLaLinea], None),
                        origen=(Optional[OrigenDeLaLinea], None),
                        antes=(Optional[Any], None),
                        despues=(Optional[Any], None),
                        detalle=(Optional[Any], None))


class LegajoCompleto(BaseModel):
    ficha: Optional[FichaDelPersonal] = None
    historial: List[LineaDelLibro] = []


class LibroDeAuditoria(BaseModel):
    lineas: List[LineaDelLibro] = []
    total: Escalar = None
    limite: Escalar = None
    saltar: Escalar = None


AccionAuditable = _simple("AccionAuditable", ("accion", "categoria", "etiqueta"))


class AccionesAuditables(BaseModel):
    acciones: List[AccionAuditable] = []


# ── El catálogo de permisos ───────────────────────────────────────────────

# Un diccionario de permiso → nombre legible (`services/permisos.CATALOGO`).
CatalogoDePermisos = Dict[str, Escalar]


class PermisosQueSePuedenDar(BaseModel):
    permisos: CatalogoDePermisos = {}


# ── Lo que contesta cada acción de RRHH ───────────────────────────────────

# La invitación de primer acceso: si se emitió, si el correo salió, y cuánto
# dura. Cuando no hace falta —la persona ya tenía con qué entrar—, el motivo.
InvitacionEmitida = _simple("InvitacionEmitida", ("emitida", "correo_enviado", "vence_en_horas", "motivo"))

AltaDelPersonal = _simple("AltaDelPersonal", ("mensaje", "user_id", "convertido_desde_usuario"),
                          acceso=(Optional[InvitacionEmitida], None))
InvitacionReenviada = _simple("InvitacionReenviada", ("mensaje",), acceso=(Optional[InvitacionEmitida], None))
PermisosCambiados = _simple("PermisosCambiados", ("mensaje",), permisos=(List[Escalar], []))
LegajoCambiado = _simple("LegajoCambiado", ("mensaje",), cambios=(Optional[LegajoDelPersonal], None))
SesionesCerradas = _simple("SesionesCerradas", ("mensaje", "sesiones_cerradas"))

# ── La lista de administradores ───────────────────────────────────────────

# La misma forma que la lista de usuarios del panel: sale de la misma
# proyección (`perfil.LO_QUE_VE_EL_PANEL`) y se arma con la misma función.
Administradores = List[UsuarioQueVeElPanel]
