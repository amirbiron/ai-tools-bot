from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, DB_NAME

client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]

users_col = db["users"]
submissions_col = db["submissions"]


async def get_user(user_id: int):
    return await users_col.find_one({"user_id": user_id})


async def upsert_user(user_id: int, username: str):
    await users_col.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"user_id": user_id, "username": username, "last_published_at": None}},
        upsert=True,
    )


async def update_last_published(user_id: int, dt):
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"last_published_at": dt}},
    )


async def save_submission(data: dict) -> str:
    result = await submissions_col.insert_one(data)
    return str(result.inserted_id)


async def get_submission(submission_id: str):
    from bson import ObjectId
    return await submissions_col.find_one({"_id": ObjectId(submission_id)})


async def update_submission_status(submission_id: str, status: str, reject_reason: str = None):
    from bson import ObjectId
    from datetime import datetime, timezone
    update = {"$set": {"status": status, "reviewed_at": datetime.now(timezone.utc)}}
    if reject_reason is not None:
        update["$set"]["reject_reason"] = reject_reason
    await submissions_col.update_one({"_id": ObjectId(submission_id)}, update)
