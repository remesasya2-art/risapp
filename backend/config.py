"""
Application configuration and environment variables
"""
import os
from dotenv import load_dotenv

load_dotenv()

# MongoDB
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "ris_app")

# JWT
SECRET_KEY = os.environ.get("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

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
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://agent-payment-hub-1.preview.emergentagent.com")
