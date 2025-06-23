import os
import motor.motor_asyncio
from urllib.parse import quote_plus
from datetime import datetime

# Load MongoDB configuration from environment
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = os.getenv("MONGO_PORT", "27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "ai_platform")
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASS = os.getenv("MONGO_PASS")

# Ensure credentials are present
if not MONGO_USER or not MONGO_PASS:
    raise RuntimeError("MONGO_USER and MONGO_PASS must be set.")

# Percent-encode credentials
user = quote_plus(MONGO_USER)
pwd = quote_plus(MONGO_PASS)

# Build Mongo URI
MONGO_URI = (
    f"mongodb://{user}:{pwd}@{MONGO_HOST}:{MONGO_PORT}/{MONGO_DB_NAME}"
    f"?authSource={MONGO_DB_NAME}&retryWrites=true&w=majority"
)

# Singleton Motor client
_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)


def get_mongo_db():
    """Returns the MongoDB database handle (for repo use only)."""
    return _client[MONGO_DB_NAME]

async def ensure_capped_collection():
    """Create or verify the short-term chat memory capped collection."""
    db = get_mongo_db()
    name = "conversations_current"
    existing = await db.list_collection_names()
    if name not in existing:
        await db.create_collection(
            name,
            capped=True,
            size=100 * 1024 * 1024,
            max=10000
        )
    await db[name].create_index([("timestamp", -1)])
