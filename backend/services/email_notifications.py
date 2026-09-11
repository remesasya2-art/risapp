"""
services/email_notifications.py — Los correos de seguridad y de movimiento.

Arma el texto y se lo pasa a `services/correo.py`, que es la única puerta por
la que sale un correo. Antes este archivo tenía SU PROPIO remitente
—`notificaciones@risapp.com`, un dominio que no es de la empresa— y su propia
llamada a Resend, la que frenaba al servidor mientras el correo viajaba.
"""
import logging
from datetime import datetime, timezone

from services import correo

logger = logging.getLogger(__name__)

APP_NAME = correo.APP

def get_email_template(title: str, content: str, footer_note: str = "") -> str:
    """Generate HTML email template"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f5;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f5; padding: 40px 20px;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                        <!-- Header -->
                        <tr>
                            <td style="background: linear-gradient(135deg, #7c3aed 0%, #6366f1 100%); padding: 30px; text-align: center;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 700;">{APP_NAME}</h1>
                            </td>
                        </tr>
                        <!-- Content -->
                        <tr>
                            <td style="padding: 40px 30px;">
                                <h2 style="color: #1f2937; margin: 0 0 20px 0; font-size: 20px; font-weight: 600;">{title}</h2>
                                <div style="color: #4b5563; font-size: 16px; line-height: 1.6;">
                                    {content}
                                </div>
                            </td>
                        </tr>
                        <!-- Footer -->
                        <tr>
                            <td style="background-color: #f9fafb; padding: 20px 30px; border-top: 1px solid #e5e7eb;">
                                <p style="color: #9ca3af; font-size: 12px; margin: 0; text-align: center;">
                                    {footer_note if footer_note else "Este es un mensaje automático de seguridad. Por favor no responda a este correo."}
                                </p>
                                <p style="color: #9ca3af; font-size: 12px; margin: 10px 0 0 0; text-align: center;">
                                    © {datetime.now().year} {APP_NAME}. Todos los derechos reservados.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

async def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """Manda uno y espera. Devuelve si salió."""
    return await correo.enviar(to_email, subject, html_content, que_es=subject)


def _cortesia(to_email: str, subject: str, html_content: str) -> None:
    """Lo manda sin hacer esperar a quien acaba de operar.

    «Entraste a tu cuenta» y «se movió tu saldo» son cortesía: el trabajo ya
    está hecho y el aviso ya quedó guardado dentro de la aplicación. Que
    Resend tarde un segundo no puede ser un segundo más de ruedita para quien
    acaba de iniciar sesión.
    """
    correo.en_segundo_plano(to_email, subject, html_content, que_es=subject)


# ============================================================================
# SECURITY NOTIFICATION FUNCTIONS
# ============================================================================

async def notify_login(email: str, user_name: str, ip_address: str = "Unknown", device: str = "Unknown"):
    """Notify user of new login"""
    timestamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    
    content = f"""
    <p>Hola <strong>{user_name}</strong>,</p>
    <p>Se ha detectado un nuevo inicio de sesión en tu cuenta:</p>
    <table style="background-color: #f3f4f6; border-radius: 8px; padding: 20px; margin: 20px 0; width: 100%;">
        <tr><td style="padding: 8px 0;"><strong>Fecha y hora:</strong></td><td>{timestamp}</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Dispositivo:</strong></td><td>{device}</td></tr>
    </table>
    <p style="color: #dc2626; font-weight: 500;">⚠️ Si no reconoces esta actividad, cambia tu contraseña inmediatamente.</p>
    """
    
    html = get_email_template("Nuevo inicio de sesión", content)
    _cortesia(email, f"🔐 {APP_NAME} - Nuevo inicio de sesión detectado", html)


async def notify_password_change(email: str, user_name: str):
    """Notify user of password change"""
    timestamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    
    content = f"""
    <p>Hola <strong>{user_name}</strong>,</p>
    <p>Tu contraseña ha sido cambiada exitosamente.</p>
    <table style="background-color: #f3f4f6; border-radius: 8px; padding: 20px; margin: 20px 0; width: 100%;">
        <tr><td style="padding: 8px 0;"><strong>Fecha y hora:</strong></td><td>{timestamp}</td></tr>
    </table>
    <p style="color: #dc2626; font-weight: 500;">⚠️ Si no realizaste este cambio, contacta a soporte inmediatamente.</p>
    """
    
    html = get_email_template("Contraseña actualizada", content)
    _cortesia(email, f"🔑 {APP_NAME} - Tu contraseña ha sido cambiada", html)


async def notify_recharge_success(email: str, user_name: str, amount: float, method: str, balance_type: str = "principal"):
    """Notify user of successful recharge"""
    timestamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    balance_name = "Saldo de Terceros" if balance_type == "terceros" else "Saldo Principal"
    
    content = f"""
    <p>Hola <strong>{user_name}</strong>,</p>
    <p>Tu recarga ha sido procesada exitosamente:</p>
    <table style="background-color: #dcfce7; border-radius: 8px; padding: 20px; margin: 20px 0; width: 100%;">
        <tr><td style="padding: 8px 0;"><strong>Monto:</strong></td><td style="color: #16a34a; font-weight: 700; font-size: 18px;">+R$ {amount:.2f}</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Método:</strong></td><td>{method}</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Destino:</strong></td><td>{balance_name}</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Fecha:</strong></td><td>{timestamp}</td></tr>
    </table>
    <p>¡Gracias por usar {APP_NAME}!</p>
    """
    
    html = get_email_template("Recarga exitosa", content)
    await send_email(email, f"✅ {APP_NAME} - Recarga de R$ {amount:.2f} completada", html)


async def notify_withdrawal_initiated(email: str, user_name: str, amount_ves: float, beneficiary: str, payment_type: str):
    """Notify user of withdrawal request initiated"""
    timestamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    
    content = f"""
    <p>Hola <strong>{user_name}</strong>,</p>
    <p>Tu solicitud de retiro ha sido registrada:</p>
    <table style="background-color: #fef3c7; border-radius: 8px; padding: 20px; margin: 20px 0; width: 100%;">
        <tr><td style="padding: 8px 0;"><strong>Monto:</strong></td><td style="font-weight: 700; font-size: 18px;">{amount_ves:.2f} VES</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Beneficiario:</strong></td><td>{beneficiary}</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Tipo:</strong></td><td>{payment_type}</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Fecha:</strong></td><td>{timestamp}</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Estado:</strong></td><td style="color: #d97706;">⏳ En proceso</td></tr>
    </table>
    <p>Te notificaremos cuando el retiro sea completado.</p>
    """
    
    html = get_email_template("Retiro en proceso", content)
    await send_email(email, f"⏳ {APP_NAME} - Retiro de {amount_ves:.2f} VES en proceso", html)


async def notify_withdrawal_completed(email: str, user_name: str, amount_ves: float, beneficiary: str, reference: str = ""):
    """Notify user of completed withdrawal"""
    timestamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    
    content = f"""
    <p>Hola <strong>{user_name}</strong>,</p>
    <p>¡Tu retiro ha sido completado exitosamente!</p>
    <table style="background-color: #dcfce7; border-radius: 8px; padding: 20px; margin: 20px 0; width: 100%;">
        <tr><td style="padding: 8px 0;"><strong>Monto:</strong></td><td style="color: #16a34a; font-weight: 700; font-size: 18px;">{amount_ves:.2f} VES</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Beneficiario:</strong></td><td>{beneficiary}</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Referencia:</strong></td><td>{reference if reference else "N/A"}</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Fecha:</strong></td><td>{timestamp}</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Estado:</strong></td><td style="color: #16a34a;">✅ Completado</td></tr>
    </table>
    <p>¡Gracias por usar {APP_NAME}!</p>
    """
    
    html = get_email_template("Retiro completado", content)
    await send_email(email, f"✅ {APP_NAME} - Retiro de {amount_ves:.2f} VES completado", html)


async def notify_pix_received(email: str, user_name: str, amount: float, client_name: str = "Cliente"):
    """Notify gestor of PIX payment received"""
    timestamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    
    content = f"""
    <p>Hola <strong>{user_name}</strong>,</p>
    <p>Has recibido un pago PIX:</p>
    <table style="background-color: #dcfce7; border-radius: 8px; padding: 20px; margin: 20px 0; width: 100%;">
        <tr><td style="padding: 8px 0;"><strong>Monto:</strong></td><td style="color: #16a34a; font-weight: 700; font-size: 18px;">+R$ {amount:.2f}</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Cliente:</strong></td><td>{client_name}</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Destino:</strong></td><td>Saldo de Terceros</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Fecha:</strong></td><td>{timestamp}</td></tr>
    </table>
    <p>El monto ya está disponible en tu saldo de terceros.</p>
    """
    
    html = get_email_template("Pago PIX recibido", content)
    _cortesia(email, f"💰 {APP_NAME} - Pago PIX de R$ {amount:.2f} recibido", html)


async def notify_transfer_sent(email: str, user_name: str, amount_ves: float, beneficiary: str, amount_ris: float):
    """Notify user of transfer sent to beneficiary"""
    timestamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    
    content = f"""
    <p>Hola <strong>{user_name}</strong>,</p>
    <p>Tu transferencia ha sido enviada:</p>
    <table style="background-color: #dbeafe; border-radius: 8px; padding: 20px; margin: 20px 0; width: 100%;">
        <tr><td style="padding: 8px 0;"><strong>Monto enviado:</strong></td><td style="font-weight: 700;">{amount_ves:.2f} VES</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Equivalente:</strong></td><td>R$ {amount_ris:.2f}</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Beneficiario:</strong></td><td>{beneficiary}</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Fecha:</strong></td><td>{timestamp}</td></tr>
    </table>
    <p>El beneficiario recibirá los fondos pronto.</p>
    """
    
    html = get_email_template("Transferencia enviada", content)
    await send_email(email, f"📤 {APP_NAME} - Transferencia de {amount_ves:.2f} VES enviada", html)


async def notify_suspicious_activity(email: str, user_name: str, activity: str):
    """Notify user of suspicious activity"""
    timestamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    
    content = f"""
    <p>Hola <strong>{user_name}</strong>,</p>
    <p style="color: #dc2626; font-weight: 600;">⚠️ Se ha detectado actividad sospechosa en tu cuenta:</p>
    <table style="background-color: #fee2e2; border-radius: 8px; padding: 20px; margin: 20px 0; width: 100%;">
        <tr><td style="padding: 8px 0;"><strong>Actividad:</strong></td><td>{activity}</td></tr>
        <tr><td style="padding: 8px 0;"><strong>Fecha:</strong></td><td>{timestamp}</td></tr>
    </table>
    <p style="color: #dc2626; font-weight: 500;">Si no reconoces esta actividad:</p>
    <ol style="color: #4b5563;">
        <li>Cambia tu contraseña inmediatamente</li>
        <li>Revisa tus transacciones recientes</li>
        <li>Contacta a soporte si es necesario</li>
    </ol>
    """
    
    html = get_email_template("Alerta de seguridad", content)
    await send_email(email, f"🚨 {APP_NAME} - Alerta de seguridad en tu cuenta", html)
