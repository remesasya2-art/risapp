"""
Application configuration and environment variables
"""
import os
from dotenv import load_dotenv

load_dotenv()

# MongoDB
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "ris_app")

# Sesiones
#
# Acá vivían SECRET_KEY, ALGORITHM y ACCESS_TOKEN_EXPIRE_MINUTES, con el
# default "your-secret-key-change-in-production". No había JWT en ninguna
# parte del backend: las tres constantes no se usaban, y SECRET_KEY se
# importaba dos veces en routes/dependencies.py sin llegar a usarse.
#
# La app usa tokens de sesión opacos: `secrets.token_urlsafe(32)` —256 bits
# de un generador criptográfico— guardados en la colección `sessions` y
# resueltos contra la base en cada request. No hay nada firmado, así que no
# hace falta ninguna clave de firma.
#
# Se borran porque eran una trampa: quien mañana agregue JWT va a buscar
# SECRET_KEY, la va a encontrar, y va a firmar tokens con un placeholder que
# está en el historial público del repositorio. Si algún día hace falta
# firmar algo, la clave se lee del entorno y la app no arranca sin ella.

# Twilio (WhatsApp)
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")
ADMIN_WHATSAPP_NUMBER = os.environ.get("ADMIN_WHATSAPP_NUMBER", "")

# Resend (Email)
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "noreply@example.com")

# Firebase (Push Notifications)
FIREBASE_SERVER_KEY = os.environ.get("FIREBASE_SERVER_KEY", "")

# VAPID (Web Push)
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_CLAIMS_EMAIL = os.environ.get("VAPID_CLAIMS_EMAIL", "admin@example.com")

# Stripe
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")

# App URLs
# El default era https://agent-payment-hub-1.preview.emergentagent.com, el
# preview de la herramienta con la que se armó el proyecto. `routes/partner.py`
# arma con esto el link de referido que el socio copia y reparte: sin la
# variable seteada, cada socio estaba repartiendo links a un dominio ajeno, con
# su código de referido adentro. El resto del backend ya usaba www.risappbr.com
# (ver PUBLIC_BASE_URL en routes/transactions.py y routes/credits.py).
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://www.risappbr.com")
