"""
models/movimientos.py — Lo que el cliente ve de sus operaciones: la lista del
historial y el detalle de una.

DOS CAPAS

    La consulta ya traía de la base sólo lo permitido (`LO_QUE_VE_EL_CLIENTE`,
    que se mudó acá desde `routes/transactions.py`). El contrato de salida
    (`MovimientoQueVeElCliente`) es la segunda capa, y se GENERA de esa misma
    lista: dos listas de los mismos campos escritas a mano terminan distintas,
    y cuando pasa el campo se pierde en silencio.

    Lo que la lista de la consulta no podía cortar era lo de ADENTRO de un
    campo permitido: `beneficiary_data` sale entero. Y en los envíos por
    Bitcoin ese bloque era una copia del documento completo del beneficiario
    (`routes/btc_lightning.py`), con `user_id`, `beneficiary_id`, `created_at`
    y cualquier campo que se le agregue mañana a los beneficiarios. Ahora hay
    una lista de lo permitido también para ese bloque.
"""
from typing import List, Optional

from pydantic import BaseModel, create_model

from models.escalar import Escalar
from services.las_fotos import LAS_FOTOS


# LO QUE EL CLIENTE VE DE SU PROPIA OPERACION, POR LISTA DE LO PERMITIDO
#
#   Acá había `{"_id": 0}`, que es una lista de lo PROHIBIDO con un solo
#   elemento: saca el identificador interno de Mongo y deja pasar todo lo
#   demás. Y al documento de una orden le escribe el panel mientras la
#   procesa: quién la tomó, en qué lote iba, desde cuál de nuestras cuentas
#   se pagó.
#
#   Lo que se filtraba, comprobado corriendo las dos rutas contra una orden
#   que pasó por un lote: `assigned_to`, `assigned_to_name`, `assigned_at`,
#   `estado_admin`, `lote_id`, `processed_by`, `paid_from_bank` y
#   `hidden_from_admin`.
#
#   El peor de todos es `assigned_to_name`. Se llena con
#   `full_name or name or email` —en `routes/admin.py` y en
#   `services/lotes_de_pago.py`, las dos con la misma última alternativa—, así
#   que un agente que no tenga el nombre cargado le deja SU DIRECCION DE
#   CORREO escrita en la orden del cliente. Cerrar el lote no la borra: queda
#   ahí para siempre, y de ahí viajaba al navegador del cliente.
#
#   POR QUE LISTA DE LO PERMITIDO Y NO UNA DE LO PROHIBIDO
#
#       Una de lo prohibido deja pasar cada campo nuevo hasta que alguien se
#       acuerde de agregarlo, y acordarse depende de que ese alguien sepa que
#       la lista existe. Al panel se le agregan campos seguido; a esta lista,
#       casi nunca.
#
#   COMO SE AGREGA UN CAMPO NUEVO
#
#       Se agrega ACA. Si falta, la pantalla del cliente NO da error: muestra
#       un espacio vacío, que es el peor modo de fallar que tiene esto —nadie
#       se enteraría hasta que un cliente pregunte—. Por eso
#       `tests/test_el_historial_no_lleva_el_panel.py` lee las pantallas del
#       cliente y falla si alguna muestra un campo que no esté en esta lista.
#
#   LOS NOMBRES REPETIDOS EN ESPAÑOL NO SON DESCUIDO
#
#       `tipo`, `estado`, `beneficiario_data` y `beneficiario` existen porque
#       los envíos por Bitcoin se guardan con esos nombres
#       (`routes/btc_lightning.py`) y la misma pantalla los lee de las dos
#       formas. Sacarlos deja el historial de esos envíos en blanco.
LO_QUE_VE_EL_CLIENTE = {
    "_id": 0,
    # Para identificar la operación
    "transaction_id": 1, "display_id": 1,
    # Qué fue y cómo va
    "type": 1, "tipo": 1, "subtipo": 1, "status": 1, "estado": 1,
    # Cuándo
    "created_at": 1, "completed_at": 1,
    # Cuánto
    "amount_input": 1, "amount_output": 1, "amount_ris": 1, "amount_ves": 1,
    "amount": 1, "usd_cliente": 1, "ves_recibe": 1, "currency_input": 1,
    # `currency_output` faltaba, y el historial le ponía «VES» a mano a lo que
    # recibe el beneficiario: una orden a Brasil mostraba «40,00 VES» donde
    # eran 40 reales. La pantalla no podía arreglarlo sola porque el dato no
    # le llegaba.
    "currency_output": 1,
    # A quién
    "beneficiary_data": 1, "beneficiario_data": 1, "beneficiario": 1,
    # El comprobante del pago, que es lo que el cliente viene a buscar
    "proof_image": 1, "proof_images": 1, "comprobante_pago": 1,
    "voucher_url": 1,
}


# ══════════════════════════════════════════════════════════════════════════
# Los datos del beneficiario que se guardan con cada operación
# ══════════════════════════════════════════════════════════════════════════

# LISTA DE LO PERMITIDO: lo que los cuatro lugares que arman ese bloque en
# `routes/transactions.py` escriben, más los nombres viejos que el panel
# todavía lee de las órdenes antiguas (`cedula`, `phone`, `name`,
# `bank_name`, `document`). Son los datos de pago que el propio cliente cargó.
#
# Afuera, a propósito: `user_id`, `beneficiary_id` y `created_at`, que
# viajaban en los envíos por Bitcoin porque ese bloque era una copia del
# documento entero del beneficiario.
LO_QUE_VE_DEL_BENEFICIARIO = (
    "full_name", "name", "id_document", "cedula", "document", "cpf",
    "bank", "bank_code", "bank_name", "account_number", "account_type",
    "phone_number", "phone", "pix_key", "payment_type", "pais",
)


def beneficiario_para_la_orden(beneficiario) -> dict:
    """El beneficiario recortado a lo que se guarda con una operación.

    Se usa al GUARDAR (el envío por Bitcoin copiaba el documento entero), y
    el contrato de abajo corta lo mismo al MOSTRAR, para las órdenes viejas
    que ya se guardaron con la copia completa.
    """
    beneficiario = beneficiario if isinstance(beneficiario, dict) else {}
    return {k: beneficiario[k] for k in LO_QUE_VE_DEL_BENEFICIARIO if k in beneficiario}


BeneficiarioDeLaOperacion = create_model(
    "BeneficiarioDeLaOperacion",
    **{c: (Escalar, None) for c in LO_QUE_VE_DEL_BENEFICIARIO})


# ══════════════════════════════════════════════════════════════════════════
# El contrato, generado de la lista de la consulta
# ══════════════════════════════════════════════════════════════════════════

def _tipo_de(campo):
    if campo in ("beneficiary_data", "beneficiario_data"):
        return Optional[BeneficiarioDeLaOperacion]
    if campo == "proof_images":
        return Optional[List[Escalar]]
    return Escalar


MovimientoQueVeElCliente = create_model(
    "MovimientoQueVeElCliente",
    **{c: (_tipo_de(c), None) for c in LO_QUE_VE_EL_CLIENTE if c != "_id"})


# ══════════════════════════════════════════════════════════════════════════
# La lista del historial: todo lo del detalle MENOS las fotos
# ══════════════════════════════════════════════════════════════════════════
#
# Las fotos del comprobante se guardan adentro de la operación, en base64
# (ver `services/las_fotos.py`): unos 667 KB cada una, y un retiro completado
# lleva dos o más. La lista las mandaba todas para dibujar un ojito.
#
# Medido corriendo la ruta con diez operaciones con foto, que es la primera
# página del inicio: 10 MB cada vez que el cliente abre la app. Con
# `?limit=60`, 60 MB, y el tope no existía: cualquier cliente con sesión podía
# pedir su historial entero y hacer que el servidor lo cargara en memoria.
#
# Ahora la lista dice SI hay comprobante (`tiene_comprobante`) y las fotos se
# piden al tocar «Ver comprobante», por el detalle de esa sola operación.
#
# Se genera de la misma lista que el detalle, para que un campo nuevo que se
# agregue allá aparezca acá sin que nadie se acuerde. Lo único que se saca es
# lo que `LAS_FOTOS` nombra.
LO_QUE_VE_EN_LA_LISTA = {c: v for c, v in LO_QUE_VE_EL_CLIENTE.items() if c not in LAS_FOTOS}

MovimientoEnLaLista = create_model(
    "MovimientoEnLaLista",
    tiene_comprobante=(Optional[bool], None),
    **{c: (_tipo_de(c), None) for c in LO_QUE_VE_EN_LA_LISTA if c != "_id"})


class MisMovimientos(BaseModel):
    total: Escalar = None
    page: Escalar = None
    limit: Escalar = None
    pages: Escalar = None
    transactions: List[MovimientoEnLaLista] = []
