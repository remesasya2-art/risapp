"""
models/panel_usuarios.py — Lo que el panel ve de un cliente: la lista de
usuarios, el detalle y la ficha completa.

POR QUE SE GENERA DE LA PROYECCION

    El usuario que ve el panel sale de la base con `perfil.LO_QUE_VE_EL_PANEL`,
    una lista de lo permitido. El contrato se genera de ESA lista y no de una
    copia escrita acá: dos listas se separan —ya pasó con las cinco puertas de
    entrada— y la que se queda atrás se come en silencio el campo nuevo que
    alguien sumó a la otra.

LO QUE LA FICHA DEVOLVIA ENTERO

    `/users/{id}/complete` devolvía la verificación entera del cliente —con las
    tres fotos otra vez, que ya iban en el perfil, y todo lo que el equipo le
    anota— y cada beneficiario entero. El panel lee de la verificación cuatro
    datos para completar los que falten en el perfil (CPF, teléfono, documento,
    estado), y de cada beneficiario el nombre, el banco y la cuenta. El
    contrato deja lo que el panel usa y lo que identifica a cada cosa.

Un test (`tests/test_contratos_del_panel.py`) arma cada respuesta con datos de
ejemplo, la pasa por su contrato y comprueba que el panel recibe lo mismo.
"""
from typing import List, Optional, Union

from pydantic import BaseModel, create_model

from models.cuenta import MiBeneficiario, MiBeneficiarioEnBrasil
from models.escalar import Escalar
from models.movimientos import BeneficiarioDeLaOperacion
from services.estado_de_la_cuenta import LOS_ESTADOS
from services.perfil import LO_PERMITIDO_AL_PANEL


def _simple(nombre, campos, **extra):
    return create_model(nombre, **{c: (Escalar, None) for c in campos}, **extra)


# `estado` no está en la base: lo calcula la ruta (activa, suspendida, vetada,
# borrada) para que la tabla y el resumen digan lo mismo.
UsuarioQueVeElPanel = _simple("UsuarioQueVeElPanel", sorted(LO_PERMITIDO_AL_PANEL | {"estado"}))

ResumenDeCuentas = _simple("ResumenDeCuentas", (*LOS_ESTADOS, "total"))


class ListaDeUsuariosDelPanel(BaseModel):
    users: List[UsuarioQueVeElPanel] = []
    resumen: Optional[ResumenDeCuentas] = None


MovimientoDelDetalle = _simple("MovimientoDelDetalle", (
    "transaction_id", "display_id", "type", "status", "amount_input", "amount_output", "created_at"))


class DetalleDeUsuario(BaseModel):
    user: Optional[UsuarioQueVeElPanel] = None
    transactions: List[MovimientoDelDetalle] = []


# ── La ficha completa ─────────────────────────────────────────────────────

# El perfil, más las tres fotos de su verificación: el panel las muestra al
# lado de los datos para comparar.
PerfilDeLaFicha = create_model(
    "PerfilDeLaFicha", __base__=UsuarioQueVeElPanel,
    **{c: (Escalar, None) for c in ("id_document_image", "cpf_image", "selfie_image")})

# De la verificación, lo que el panel lee para completar el perfil y lo que
# la identifica. Sin las fotos —ya van en el perfil— ni lo que anota el equipo.
KycDeLaFicha = _simple("KycDeLaFicha", (
    "verification_id", "status", "full_name", "document_type", "document_number",
    "cpf_number", "phone_number", "submitted_at", "processed_at", "rejection_reason"))

EstadisticasDeLaFicha = _simple("EstadisticasDeLaFicha", (
    "total_recharged_ris", "total_withdrawn_ris", "total_ves_sent", "total_transactions"))

RecargaDeLaFicha = _simple("RecargaDeLaFicha", (
    "transaction_id", "display_id", "status", "amount_ris", "amount_brl", "created_at", "completed_at"))

# `beneficiary` es el beneficiario guardado con la operación: un documento,
# recortado por la misma lista que usa el historial. En operaciones muy viejas
# puede ser sólo el nombre escrito.
RetiroDeLaFicha = _simple("RetiroDeLaFicha", (
    "transaction_id", "display_id", "status", "amount_ris", "amount_ves", "created_at", "completed_at"),
    beneficiary=(Optional[Union[BeneficiarioDeLaOperacion, str]], None))

# Un beneficiario de Venezuela o de Brasil: los campos de los dos contratos
# que ya ve el cliente, más el país.
BeneficiarioDeLaFicha = _simple("BeneficiarioDeLaFicha", sorted(
    set(MiBeneficiario.model_fields) | set(MiBeneficiarioEnBrasil.model_fields) | {"pais"}))


class FichaCompletaDelUsuario(BaseModel):
    profile: Optional[PerfilDeLaFicha] = None
    kyc: Optional[KycDeLaFicha] = None
    stats: Optional[EstadisticasDeLaFicha] = None
    recharges: List[RecargaDeLaFicha] = []
    withdrawals: List[RetiroDeLaFicha] = []
    beneficiaries: List[BeneficiarioDeLaFicha] = []
