import os
import logging
import mercadopago
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class MercadoPagoService:
    """Service for Mercado Pago PIX payments"""
    
    def __init__(self):
        self.access_token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
        self.public_key = os.getenv('MERCADOPAGO_PUBLIC_KEY')
        
        if self.access_token:
            self.sdk = mercadopago.SDK(self.access_token)
            logger.info("Mercado Pago SDK initialized")
        else:
            self.sdk = None
            logger.warning("Mercado Pago access token not found")
    
    def create_pix_payment(
        self,
        amount: float,
        description: str,
        payer_email: str,
        payer_first_name: str,
        payer_last_name: str,
        payer_cpf: str,
        external_reference: str
    ) -> Optional[Dict[str, Any]]:
        """
        Create a PIX payment
        
        Args:
            amount: Amount in BRL
            description: Payment description
            payer_email: Payer's email
            payer_first_name: Payer's first name
            payer_last_name: Payer's last name
            payer_cpf: Payer's CPF (Brazilian tax ID)
            external_reference: External reference ID (transaction_id)
            
        Returns:
            Payment response with QR code data or None if failed
        """
        if not self.sdk:
            logger.error("Mercado Pago SDK not initialized")
            return None
        
        try:
            # Set expiration to 30 minutes from now
            expiration = datetime.utcnow() + timedelta(minutes=30)
            
            payment_data = {
                "transaction_amount": float(amount),
                "description": description,
                "payment_method_id": "pix",
                "payer": {
                    "email": payer_email,
                    "first_name": payer_first_name,
                    "last_name": payer_last_name,
                    "identification": {
                        "type": "CPF",
                        "number": payer_cpf.replace(".", "").replace("-", "")
                    }
                },
                "external_reference": external_reference,
                "date_of_expiration": expiration.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
            }
            
            logger.info(f"Creating PIX payment: {amount} BRL for {payer_email}")
            
            payment_response = self.sdk.payment().create(payment_data)
            response = payment_response.get("response", {})
            status_code = payment_response.get("status")
            
            if status_code == 201:
                # Payment created successfully
                payment_id = response.get("id")
                pix_data = response.get("point_of_interaction", {}).get("transaction_data", {})
                
                result = {
                    "success": True,
                    "payment_id": payment_id,
                    "status": response.get("status"),
                    "status_detail": response.get("status_detail"),
                    "qr_code": pix_data.get("qr_code"),
                    "qr_code_base64": pix_data.get("qr_code_base64"),
                    "ticket_url": pix_data.get("ticket_url"),
                    "expiration": expiration.isoformat(),
                    "amount": amount
                }
                
                logger.info(f"PIX payment created: {payment_id}")
                return result
            else:
                logger.error(f"Failed to create PIX payment: {response}")
                return {
                    "success": False,
                    "error": response.get("message", "Error creating payment"),
                    "cause": response.get("cause", [])
                }
                
        except Exception as e:
            logger.error(f"Error creating PIX payment: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_payment_status(self, payment_id: int) -> Optional[Dict[str, Any]]:
        """
        Get payment status
        
        Args:
            payment_id: Mercado Pago payment ID
            
        Returns:
            Payment status data
        """
        if not self.sdk:
            logger.error("Mercado Pago SDK not initialized")
            return None
        
        try:
            payment_response = self.sdk.payment().get(payment_id)
            response = payment_response.get("response", {})
            
            return {
                "payment_id": response.get("id"),
                "status": response.get("status"),
                "status_detail": response.get("status_detail"),
                "amount": response.get("transaction_amount"),
                "external_reference": response.get("external_reference"),
                "date_approved": response.get("date_approved"),
                "date_created": response.get("date_created")
            }
            
        except Exception as e:
            logger.error(f"Error getting payment status: {e}")
            return None
    
    def search_payment_by_reference(self, external_reference: str) -> Optional[Dict[str, Any]]:
        """
        Search payment by external reference
        
        Args:
            external_reference: External reference ID
            
        Returns:
            Payment data if found
        """
        if not self.sdk:
            logger.error("Mercado Pago SDK not initialized")
            return None
        
        try:
            filters = {
                "external_reference": external_reference
            }
            
            search_response = self.sdk.payment().search(filters)
            results = search_response.get("response", {}).get("results", [])
            
            if results:
                return results[0]
            return None
            
        except Exception as e:
            logger.error(f"Error searching payment: {e}")
            return None


# Global instance
mercadopago_service = MercadoPagoService()
