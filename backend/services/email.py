"""
services/email.py — Los correos de la cuenta: registro, contraseña, invitación.

Arma el texto y se lo pasa a `services/correo.py`, que es la única puerta por
la que sale un correo. Antes cada una de estas cuatro funciones llamaba a
Resend por su cuenta, con su propio remitente y su propio `try`, y la llamada
—que espera— frenaba al servidor entero mientras el correo viajaba.

Estos cuatro se mandan ESPERANDO la respuesta. No son cortesía: si el código
de verificación no sale, quien se está registrando no puede terminar, y la
pantalla necesita saberlo para decírselo.
"""
import logging

from config import FRONTEND_URL
from services import correo, registro

logger = logging.getLogger(__name__)


def _cuerpo(titulo: str, adentro: str) -> str:
    """El envoltorio común. Antes estaba copiado cuatro veces."""
    return f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #6366f1;">{titulo}</h2>
            {adentro}
        </div>
    """


def _destacado(texto: str, *, espaciado: str = "2px", tamano: str = "24px") -> str:
    """El recuadro violeta donde va el código o la contraseña temporal."""
    return f"""
            <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; padding: 20px; text-align: center; border-radius: 10px; margin: 20px 0;">
                <span style="font-size: {tamano}; font-weight: bold; letter-spacing: {espaciado};">{texto}</span>
            </div>
    """


async def send_verification_email(email: str, code: str, name: str) -> bool:
    """El código de verificación del registro."""
    salio = await correo.enviar(
        email, f"Tu código de verificación: {code}",
        _cuerpo("Verifica tu correo electrónico", f"""
            <p>Hola {name},</p>
            <p>Tu código de verificación es:</p>
            {_destacado(code, espaciado="8px", tamano="32px")}
            <p>Este código expira en 10 minutos.</p>
            <p style="color: #666; font-size: 12px;">Si no solicitaste este código, ignora este mensaje.</p>
        """),
        que_es="correo de verificación")
    if salio:
        logger.info("Correo de verificación enviado a %s", registro.correo(email))
    return salio


async def send_password_reset_email(email: str, temp_password: str) -> bool:
    """La contraseña temporal para recuperar el acceso."""
    salio = await correo.enviar(
        email, "Restablecimiento de Contraseña",
        _cuerpo("Restablecimiento de Contraseña", f"""
            <p>Has solicitado restablecer tu contraseña.</p>
            <p>Tu contraseña temporal es:</p>
            {_destacado(temp_password)}
            <p>Usa esta contraseña temporal para iniciar sesión. Deberás cambiarla en tu primer acceso.</p>
            <p>Esta contraseña expira en 1 hora.</p>
            <p style="color: #666; font-size: 12px;">Si no solicitaste este cambio, ignora este mensaje y tu contraseña actual seguirá funcionando.</p>
        """),
        que_es="correo de reseteo")
    if salio:
        logger.info("Correo de reseteo enviado a %s", registro.correo(email))
    return salio


async def send_admin_password_reset_email(email: str, temp_password: str,
                                          admin_name: str) -> bool:
    """El reseteo que arranca un administrador."""
    salio = await correo.enviar(
        email, "Tu contraseña ha sido restablecida",
        _cuerpo("Tu contraseña ha sido restablecida", f"""
            <p>Un administrador ({admin_name}) ha restablecido tu contraseña.</p>
            <p>Tu nueva contraseña temporal es:</p>
            {_destacado(temp_password)}
            <p><strong>IMPORTANTE:</strong> Deberás cambiar esta contraseña en tu primer inicio de sesión.</p>
            <p style="color: #666; font-size: 12px;">Si no esperabas este cambio, contacta al soporte inmediatamente.</p>
        """),
        que_es="correo de reseteo (admin)")
    if salio:
        logger.info("Correo de reseteo (admin) enviado a %s", registro.correo(email))
    return salio


async def send_staff_invitation_email(email: str, nombre: str, cargo: str,
                                      token: str) -> bool:
    """Invitación de primer acceso para el personal dado de alta en RRHH.

    El token viaja SOLO acá: en la base queda su hash. Por eso este correo
    no se loguea con el link adentro —el log lo lee mucha más gente que la
    casilla del destinatario.
    """
    enlace = f"{FRONTEND_URL.rstrip('/')}/personal/activar?token={token}"

    salio = await correo.enviar(
        email, "Activa tu acceso a RIS App",
        _cuerpo("Activa tu acceso", f"""
            <p>Hola {nombre},</p>
            <p>Se creó tu perfil de <strong>{cargo}</strong> en RIS App.
               Para entrar por primera vez tenés que configurar tu contraseña
               y activar la verificación en dos pasos.</p>
            <div style="text-align: center; margin: 28px 0;">
                <a href="{enlace}" style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; padding: 14px 32px; border-radius: 10px; text-decoration: none; font-weight: bold; display: inline-block;">Configurar mi acceso</a>
            </div>
            <p>Si el botón no funciona, copiá este enlace en tu navegador:</p>
            <p style="word-break: break-all; color: #6366f1; font-size: 12px;">{enlace}</p>
            <p><strong>El enlace vence en 72 horas y se puede usar una sola vez.</strong>
               Si vence, pedile a tu administrador que te lo reenvíe.</p>
            <p style="color: #666; font-size: 12px;">Si no esperabas este correo,
               no lo uses y avisá a tu administrador: alguien creó un perfil a tu nombre.</p>
        """),
        que_es="invitación de personal")
    if salio:
        logger.info("Invitación de personal enviada a %s", registro.correo(email))
    return salio
