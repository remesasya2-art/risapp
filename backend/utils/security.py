"""
Security utilities for password hashing and validation
"""
import asyncio
import bcrypt
import secrets
import string
import re

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════
# LAS MISMAS DOS, EN OTRO HILO. SON LAS QUE HAY QUE USAR DESDE UNA RUTA.
# ══════════════════════════════════════════════════════════════════════════
#
# BCRYPT ES LENTO A PROPOSITO, Y ESO ES BUENO
#
#     Las doce rondas son la defensa contra quien prueba contraseñas en masa:
#     cada intento le cuesta caro. Medido en este proyecto: **266 milisegundos**
#     por operación, tanto cifrar como comprobar.
#
# PERO NO PUEDE COSTARLE ESO AL RESTO DE LA APLICACION
#
#     El servicio corre en UN SOLO proceso con UN SOLO hilo (`railway.toml`,
#     una réplica). Un cuarto de segundo de CPU adentro de ese hilo no lo paga
#     sólo quien está entrando: lo paga TODO EL MUNDO. A los ritmos de consulta
#     que tiene el panel, un cuarto de segundo son unos dieciocho pedidos
#     haciendo cola detrás de un solo inicio de sesión.
#
#     Los dos peores casos estaban en el 2FA: generar los diez códigos de
#     respaldo son 2,7 segundos, y meter un código equivocado los prueba uno
#     por uno contra los diez guardados — otros 2,7 segundos. La aplicación
#     entera congelada por un código mal tipeado.
#
# EL ARREGLO NO ES ACELERAR BCRYPT
#
#     Bajarle las rondas lo haría rápido y débil, que es exactamente lo que no
#     se quiere. Lo que cambia es DONDE corre: en otro hilo, y el que atiende
#     queda libre mientras tanto. Tarda lo mismo para quien está entrando y
#     deja de costarle nada a los demás.

async def hash_password_async(password: str) -> str:
    """Cifra la contraseña sin congelar al resto. Ver el bloque de arriba."""
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, hashed: str) -> bool:
    """Comprueba la contraseña sin congelar al resto. Ver el bloque de arriba."""
    return await asyncio.to_thread(verify_password, password, hashed)

def validate_password(password: str) -> tuple[bool, str]:
    """
    Validate password strength
    Returns: (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres"
    
    if not re.search(r'[A-Z]', password):
        return False, "La contraseña debe contener al menos una letra mayúscula"
    
    if not re.search(r'[a-z]', password):
        return False, "La contraseña debe contener al menos una letra minúscula"
    
    if not re.search(r'\d', password):
        return False, "La contraseña debe contener al menos un número"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "La contraseña debe contener al menos un carácter especial (!@#$%^&*(),.?\":{}|<>)"
    
    return True, ""

def generate_reset_token() -> str:
    """Generate a secure random token for password reset"""
    return secrets.token_urlsafe(32)

def generate_temp_password() -> str:
    """Generate a temporary password that meets all requirements"""
    # Ensure at least one of each required character type
    uppercase = secrets.choice(string.ascii_uppercase)
    lowercase = secrets.choice(string.ascii_lowercase)
    digit = secrets.choice(string.digits)
    special = secrets.choice('!@#$%^&*')
    
    # Fill remaining with random characters
    remaining = ''.join(secrets.choice(string.ascii_letters + string.digits + '!@#$%^&*') for _ in range(8))
    
    # Combine and shuffle
    password_chars = list(uppercase + lowercase + digit + special + remaining)
    secrets.SystemRandom().shuffle(password_chars)
    
    return ''.join(password_chars)
