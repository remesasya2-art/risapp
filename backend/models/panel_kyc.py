"""
models/panel_kyc.py — Lo que el panel ve de las verificaciones de identidad:
la lista, el detalle de una y su historia.

La lista y el detalle ya arman la verificación campo por campo
(`routes/kyc_admin._serialize_verification`). El contrato fija esos campos.

LA HISTORIA SALIA ENTERA

    `/kyc/{id}/history` devolvía cada línea del libro de auditoría tal cual
    está en la base, con el correo y el identificador de quien revisó y el del
    cliente. La pantalla muestra qué se hizo, quién (por su nombre), cuándo y
    el detalle. El contrato deja eso.

UNA VERIFICACION PARA LA LISTA Y EL DETALLE, A PROPOSITO

    La ventana del detalle arranca con la fila de la lista y le encima la
    respuesta del detalle: el riesgo y la coincidencia con la lista negra
    vienen SOLO de la lista. Si fueran dos contratos, el día que uno pierda
    un campo la ventana lo pierde sin que el otro se entere. La lista no trae
    las fotos (trae si las hay) y el detalle sí: con `exclude_unset`, lo que
    una ruta no pone no sale.

Un test (`tests/test_contratos_del_panel.py`) recorre las tres rutas con una
verificación de ejemplo y compara con lo que la pantalla lee.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar


def _simple(nombre, campos, **extra):
    return create_model(nombre, **{c: (Escalar, None) for c in campos}, **extra)


VerificacionQueVeElPanel = _simple("VerificacionQueVeElPanel", (
    "verification_id", "user_id", "full_name", "email",
    "document_type", "document_type_label", "document_number", "cpf_number", "cpf_discrepa", "phone_number",
    "status", "submitted_at", "processed_at", "processed_by", "processed_by_name",
    "rejection_reason", "rejection_code", "admin_note",
    # Las fotos, sólo en el detalle.
    "id_document_image", "id_document_image_back", "cpf_image", "selfie_image",
    # Si las hay, sólo en la lista: para que cargue rápido.
    "has_id_document", "has_id_document_back", "has_cpf", "has_selfie",
    # Lo que la lista agrega: el riesgo y la lista negra.
    "blacklist_match", "risk_level", "risk_suggested"))

ConteoDeVerificaciones = _simple("ConteoDeVerificaciones", ("pending", "approved", "rejected", "total"))


class ListaDeVerificaciones(BaseModel):
    counts: Optional[ConteoDeVerificaciones] = None
    items: List[VerificacionQueVeElPanel] = []


# El cliente de la verificación, con la proyección que ya usa la ruta.
ClienteDeLaVerificacion = _simple("ClienteDeLaVerificacion", (
    "user_id", "email", "full_name", "phone_number", "role", "balance_ris", "created_at", "verification_status"))


class DetalleDeVerificacion(BaseModel):
    verification: Optional[VerificacionQueVeElPanel] = None
    user: Optional[ClienteDeLaVerificacion] = None


# Lo que cada acción anota en `details`: aprobar (la lista de lo revisado),
# marcar el riesgo, rechazar (el motivo), y cambiar la nota (antes y después).
DetalleDeLaAuditoria = _simple("DetalleDeLaAuditoria", (
    "level", "reason_code", "reason_label", "reason_text", "final_reason",
    "previous_value", "new_value", "previous_length", "new_length"),
    checklist=(Optional[Dict[str, Escalar]], None))

LineaDeLaHistoria = _simple("LineaDeLaHistoria", (
    "audit_id", "verification_id", "action", "admin_name", "created_at"),
    details=(Optional[DetalleDeLaAuditoria], None))


class HistoriaDeLaVerificacion(BaseModel):
    verification_id: Escalar = None
    history: List[LineaDeLaHistoria] = []
