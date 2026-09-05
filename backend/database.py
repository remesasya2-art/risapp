"""
Database connection and initialization
"""
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URL, DB_NAME

logger = logging.getLogger(__name__)

# MongoDB connection
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


async def create_indexes():
    """Create database indexes for optimal performance"""
    try:
        # Users indexes
        await db.users.create_index("user_id", unique=True)
        await db.users.create_index("email", unique=True, sparse=True)
        await db.users.create_index("phone", sparse=True)
        await db.users.create_index("referral_code", sparse=True)
        await db.users.create_index("role")

        # Sessions indexes
        await db.sessions.create_index("session_token", unique=True)
        await db.sessions.create_index("user_id")
        await db.sessions.create_index("expires_at")

        # Transactions indexes
        await db.transactions.create_index("transaction_id", unique=True)
        await db.transactions.create_index("user_id")
        await db.transactions.create_index("type")
        await db.transactions.create_index("status")
        await db.transactions.create_index("created_at")
        await db.transactions.create_index([("type", 1), ("status", 1)])
        await db.transactions.create_index("display_id", sparse=True)

        # Beneficiaries indexes
        await db.beneficiaries.create_index("beneficiary_id", unique=True)
        await db.beneficiaries.create_index("user_id")

        # Notifications indexes
        await db.notifications.create_index("notification_id", unique=True)
        await db.notifications.create_index("user_id")
        await db.notifications.create_index([("user_id", 1), ("read", 1)])

        # Support messages indexes
        await db.support_messages.create_index("message_id", unique=True)
        await db.support_messages.create_index("user_id")
        await db.support_messages.create_index([("user_id", 1), ("created_at", -1)])

        # Gestor indexes
        await db.gestor_transactions.create_index("transaction_id", unique=True)
        await db.gestor_transactions.create_index("gestor_id")
        await db.gestor_beneficiaries.create_index("beneficiary_id", unique=True)
        await db.gestor_beneficiaries.create_index("gestor_id")

        # Partner indexes
        await db.partner_earnings.create_index([("partner_id", 1), ("created_at", -1)])

        # Crypto deposits indexes (creditos USDT/USDC via NOWPayments)
        await db.crypto_deposits.create_index("order_id", unique=True)
        await db.crypto_deposits.create_index("user_id")
        await db.crypto_deposits.create_index([("credited", 1), ("status", 1)])

        # Mesa de ayuda (casos). Las tres consultas que se hacen todo el
        # dia: «mis casos» del cliente, la bandeja del asesor filtrada por
        # estado o area, y la conversacion de un caso. Sin estos indices cada
        # vuelta del reloj de la pantalla recorre la coleccion entera, y la
        # bandeja se consulta cada pocos segundos por cada asesor conectado.
        await db.soporte_casos.create_index("caso_id", unique=True)
        await db.soporte_casos.create_index([("user_id", 1), ("actualizado_en", -1)])
        await db.soporte_casos.create_index([("estado", 1), ("actualizado_en", -1)])
        await db.soporte_casos.create_index([("area", 1), ("estado", 1)])
        await db.soporte_casos.create_index([("asignado_a", 1), ("estado", 1)])
        # El numero NO es unico a proposito: si un caso viejo de la migracion
        # trajera uno repetido, un indice unico haria fallar la creacion y se
        # perderian todos los indices que vienen despues, dentro del mismo try.
        await db.soporte_casos.create_index("numero")
        await db.soporte_mensajes.create_index("mensaje_id", unique=True)
        await db.soporte_mensajes.create_index([("caso_id", 1), ("creado_en", 1)])
        await db.soporte_pedidos.create_index("pedido_id", unique=True)
        await db.soporte_pedidos.create_index([("area", 1), ("estado", 1)])
        await db.soporte_pedidos.create_index([("caso_id", 1), ("creado_en", 1)])

        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")


async def init_db():
    """Initialize database with default data"""
    await create_indexes()

    # Check if default rate exists
    rate = await db.rates.find_one()
    if not rate:
        await db.rates.insert_one({
            "rate_id": "default",
            "ris_to_ves": 92.0,
            "ves_to_ris": 0.0109,
            "updated_at": None
        })
        logger.info("Default exchange rate created")
