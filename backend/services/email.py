"""
Email notification service via Resend
"""
import logging
import resend
from config import RESEND_API_KEY, FROM_EMAIL, FRONTEND_URL

logger = logging.getLogger(__name__)

resend.api_key = RESEND_API_KEY

async def send_verification_email(email: str, code: str, name: str) -> bool:
    """Send email verification code"""
    if not RESEND_API_KEY:
        logger.warning("Email not configured - missing Resend API key")
        return False
    
    try:
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #6366f1;">Verifica tu correo electrónico</h2>
            <p>Hola {name},</p>
            <p>Tu código de verificación es:</p>
            <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; padding: 20px; text-align: center; border-radius: 10px; margin: 20px 0;">
                <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px;">{code}</span>
            </div>
            <p>Este código expira en 10 minutos.</p>
            <p style="color: #666; font-size: 12px;">Si no solicitaste este código, ignora este mensaje.</p>
        </div>
        """
        
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": email,
            "subject": f"Tu código de verificación: {code}",
            "html": html_content
        })
        
        logger.info(f"Verification email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"Error sending verification email: {e}")
        return False

async def send_password_reset_email(email: str, temp_password: str) -> bool:
    """Send password reset email with temporary password"""
    if not RESEND_API_KEY:
        logger.warning("Email not configured - missing Resend API key")
        return False
    
    try:
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #6366f1;">Restablecimiento de Contraseña</h2>
            <p>Has solicitado restablecer tu contraseña.</p>
            <p>Tu contraseña temporal es:</p>
            <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; padding: 20px; text-align: center; border-radius: 10px; margin: 20px 0;">
                <span style="font-size: 24px; font-weight: bold; letter-spacing: 2px;">{temp_password}</span>
            </div>
            <p>Usa esta contraseña temporal para iniciar sesión. Deberás cambiarla en tu primer acceso.</p>
            <p>Esta contraseña expira en 1 hora.</p>
            <p style="color: #666; font-size: 12px;">Si no solicitaste este cambio, ignora este mensaje y tu contraseña actual seguirá funcionando.</p>
        </div>
        """
        
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": email,
            "subject": "Restablecimiento de Contraseña",
            "html": html_content
        })
        
        logger.info(f"Password reset email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"Error sending password reset email: {e}")
        return False

async def send_admin_password_reset_email(email: str, temp_password: str, admin_name: str) -> bool:
    """Send password reset email initiated by admin"""
    if not RESEND_API_KEY:
        logger.warning("Email not configured - missing Resend API key")
        return False
    
    try:
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #6366f1;">Tu contraseña ha sido restablecida</h2>
            <p>Un administrador ({admin_name}) ha restablecido tu contraseña.</p>
            <p>Tu nueva contraseña temporal es:</p>
            <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; padding: 20px; text-align: center; border-radius: 10px; margin: 20px 0;">
                <span style="font-size: 24px; font-weight: bold; letter-spacing: 2px;">{temp_password}</span>
            </div>
            <p><strong>IMPORTANTE:</strong> Deberás cambiar esta contraseña en tu primer inicio de sesión.</p>
            <p style="color: #666; font-size: 12px;">Si no esperabas este cambio, contacta al soporte inmediatamente.</p>
        </div>
        """
        
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": email,
            "subject": "Tu contraseña ha sido restablecida",
            "html": html_content
        })
        
        logger.info(f"Admin password reset email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"Error sending admin password reset email: {e}")
        return False
