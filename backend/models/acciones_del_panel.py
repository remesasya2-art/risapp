"""
models/acciones_del_panel.py — Lo que contestan las acciones del panel sobre
los clientes: cambiar un rol, suspender, vetar, borrar, ajustar un saldo,
reiniciar una contraseña, y decidir una verificación o un retiro.

Primera tanda de los contratos del panel. Las del cliente ya están todas (ver
`models/acciones_de_dinero.py` para el porqué completo).

POR QUE EL PANEL TAMBIEN

    Lo que el panel ve no lo ve el cliente, pero lo ve el personal, y el
    personal tiene permisos distintos: quien atiende no es quien administra la
    seguridad. Ya pasó una vez: la lista de usuarios le mostraba a quien tenía
    el permiso de atención al cliente la semilla del segundo factor de todos,
    la del dueño incluida (ver `services/perfil.py`). Con eso no se ve de más:
    se puede entrar como otro.

    Estas acciones contestan poco —un mensaje, un sí, un número—, pero leen el
    documento del cliente para decidir. El contrato es para el día que alguien
    conteste con ese documento.

Un test (`tests/test_contratos_del_panel.py`) compara las claves que devuelve
cada ruta, leídas del código, con su contrato.
"""
from typing import List

from pydantic import create_model

from models.escalar import Escalar


def _simple(nombre, campos):
    return create_model(nombre, **{c: (Escalar, None) for c in campos})


# ── Sobre la cuenta ───────────────────────────────────────────────────────

AccionDelPanel = _simple("AccionDelPanel", ("success", "message"))
RolCambiado = _simple("RolCambiado", ("message", "new_role"))
AgenteAsignado = _simple("AgenteAsignado", ("success", "role"))
ClaveReiniciada = _simple("ClaveReiniciada", ("message", "sesiones_cerradas"))
CuentaVetada = _simple("CuentaVetada", ("success", "message", "scope"))
SaldoAjustado = _simple("SaldoAjustado", ("message", "balance_after"))

# ── Verificación de identidad (KYC) ───────────────────────────────────────

RiesgoMarcado = _simple("RiesgoMarcado", ("success", "risk_level"))
VerificacionRechazada = _simple("VerificacionRechazada", ("success", "message", "reason"))
NotaGuardada = _simple("NotaGuardada", ("success", "note"))

# Los dos catálogos fijos del KYC. Salen de listas escritas en el código;
# el contrato es el mismo que tendrían si un día se leyeran de la base.
TipoDeDocumento = _simple("TipoDeDocumento", ("code", "label", "requires_back"))
MotivoDeRechazo = _simple("MotivoDeRechazo", ("code", "label"))
TiposDeDocumento = List[TipoDeDocumento]
MotivosDeRechazo = List[MotivoDeRechazo]
