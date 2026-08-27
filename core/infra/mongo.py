import os
from urllib.parse import quote_plus

import motor.motor_asyncio

_client = None
_db_name = None


def _build_mongo_uri() -> tuple[str, str]:
    host = os.getenv("MONGO_HOST", "localhost")
    port = os.getenv("MONGO_PORT", "27017")
    db_name = os.getenv("MONGO_DB_NAME", "ai_platform")
    user = os.getenv("MONGO_USER")
    password = os.getenv("MONGO_PASS")

    if not user or not password:
        raise RuntimeError("MONGO_USER and MONGO_PASS must be set.")

    encoded_user = quote_plus(user)
    encoded_password = quote_plus(password)
    uri = (
        f"mongodb://{encoded_user}:{encoded_password}@{host}:{port}/{db_name}"
        f"?authSource={db_name}&retryWrites=true&w=majority"
    )
    return uri, db_name


def get_mongo_db():
    """Return the MongoDB database handle, creating the client lazily."""
    global _client, _db_name
    if _client is None:
        mongo_uri, _db_name = _build_mongo_uri()
        _client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
    return _client[_db_name]


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
            max=10000,
        )
    await db[name].create_index([("timestamp", -1)])
