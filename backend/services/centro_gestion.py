"""
centro_gestion.py - Servicio de registro administrativo para CentroGestionCont-Byte

Registra cada transaccion ejecutada en RisApp en la coleccion 'centro_gestion_log'
para consulta y auditoria por parte de centrogestioncont-byte.

Tipos de eventos registrados:
  - retiro_ves       : Retiro VES solicitado por usuario
    - recarga_pix      : Recarga via PIX (Mercado Pago)
      - recarga_ves      : Recarga en bolivares
        - pago_tarjeta     : Pago con tarjeta via Mercado Pago
          - remesa_btc       : Remesa via Bitcoin Lightning
            - retiro_aprobado  : Retiro procesado/aprobado por adminbrl
              - retiro_rechazado : Retiro rechazado por adminbrl
              """
import logging
from datetime import datetime, timezone
from typing import Optional

from database import db

logger = logging.getLogger(__name__)


async def registrar_evento(
      tipo: str,
      transaction_id: str,
      user_id: str,
      user_email: Optional[str] = None,
      user_name: Optional[str] = None,
      amount_input: Optional[float] = None,
      amount_output: Optional[float] = None,
      currency_input: Optional[str] = None,
      currency_output: Optional[str] = None,
      status: Optional[str] = None,
      metadata: Optional[dict] = None
):
      """
          Registra un evento de transaccion en el log administrativo de CentroGestion.
              Fire-and-forget: no lanza excepcion si falla, solo loguea el error.
                  """
      try:
                doc = {
                              "tipo": tipo,
                              "transaction_id": transaction_id,
                              "user_id": user_id,
                              "user_email": user_email,
                              "user_name": user_name,
                              "amount_input": amount_input,
                              "amount_output": amount_output,
                              "currency_input": currency_input,
                              "currency_output": currency_output,
                              "status": status or "pending",
                              "metadata": metadata or {},
                              "registrado_en": datetime.now(timezone.utc),
                              "origen": "risappbr"
                }
                await db.centro_gestion_log.insert_one(doc)
                logger.info(f"[CentroGestion] Evento registrado: {tipo} | tx={transaction_id} | user={user_id}")
except Exception as e:
        logger.error(f"[CentroGestion] Error al registrar evento {tipo}: {e}")
