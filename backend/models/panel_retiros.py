"""
models/panel_retiros.py — Lo que el panel ve de la cola de pagos.

Cada fila la arma `services/retiros.cola` campo por campo, salvo una cosa: el
beneficiario (`beneficiary_data`) iba ENTERO, tal como se guardó con la
operación. Y lo que se guarda con la operación depende de qué camino la creó:
el envío por Bitcoin, por ejemplo, copiaba el documento del beneficiario
completo (ver `models/movimientos.beneficiario_para_la_orden`).

El beneficiario sale recortado por la MISMA lista que usa el historial del
cliente (`LO_QUE_VE_DEL_BENEFICIARIO`): nombre, documento, banco, cuenta,
teléfono, llave PIX. Es todo lo que la cola muestra para pagar.

Un test (`tests/test_contratos_del_panel.py`) compara la respuesta de la ruta
con lo que arma el servicio: tiene que ser lo mismo, menos lo que sobra del
beneficiario.
"""
from typing import List, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar
from models.movimientos import BeneficiarioDeLaOperacion


def _simple(nombre, campos, **extra):
    return create_model(nombre, **{c: (Escalar, None) for c in campos}, **extra)


# Cuánto hace que espera, y en qué color se pinta.
Antiguedad = _simple("Antiguedad", ("horas", "nivel"))

RetiroEnLaCola = _simple("RetiroEnLaCola", (
    "transaction_id", "display_id", "posicion", "user_id", "user_name", "user_email",
    "amount_input", "currency_input", "amount_output", "currency_output", "rate", "status",
    "payment_type", "is_gestor_transaction", "client_name", "created_at", "completed_at",
    "rejection_reason", "proof_image", "comprobantes", "processed_by", "paid_from_bank",
    "assigned_to", "assigned_to_name", "falta_beneficiario", "falta_destino"),
    beneficiary_data=(Optional[BeneficiarioDeLaOperacion], None),
    proof_images=(List[Escalar], []),
    pending_images=(List[Escalar], []),
    antiguedad=(Optional[Antiguedad], None))

PlataPorMoneda = _simple("PlataPorMoneda", ("moneda", "total", "ordenes"))

ContadoresDeLaCola = _simple("ContadoresDeLaCola", (
    "total", "pendientes", "pagados", "rechazados", "sin_beneficiario"),
    por_moneda=(List[PlataPorMoneda], []),
    por_origen=(List[PlataPorMoneda], []),
    mas_vieja=(Optional[Antiguedad], None))


class ColaDeRetiros(BaseModel):
    withdrawals: List[RetiroEnLaCola] = []
    total: Escalar = None
    limite: Escalar = None
    saltear: Escalar = None
    hay_mas: Escalar = None
    estado: Escalar = None
    busqueda: Escalar = None
    moneda: Escalar = None
    counters: Optional[ContadoresDeLaCola] = None


RetirosPendientes = List[RetiroEnLaCola]
