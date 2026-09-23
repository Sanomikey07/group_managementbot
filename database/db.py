from datetime import datetime, timezone
from typing import Any
from pymongo import AsyncMongoClient, ASCENDING, DESCENDING


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Database:
    def __init__(self, uri: str, name: str):
        self.client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[name]
        self.groups = self.db.groups
        self.users = self.db.users
        self.warns = self.db.warns
        self.filters = self.db.filters
        self.notes = self.db.notes
        self.logs = self.db.logs
        self.sudos = self.db.sudos
        self.blacklist = self.db.blacklist
        self.stats = self.db.stats

    async def connect(self) -> None:
        await self.client.admin.command("ping")
        await self._indexes()

    async def close(self) -> None:
        await self.client.close()

    async def _indexes(self) -> None:
        await self.groups.create_index("chat_id", unique=True)
        await self.users.create_index([("chat_id", ASCENDING), ("user_id", ASCENDING)], unique=True)
        await self.warns.create_index([("chat_id", ASCENDING), ("user_id", ASCENDING)], unique=True)
        await self.filters.create_index([("chat_id", ASCENDING), ("keyword", ASCENDING)], unique=True)
        await self.notes.create_index([("chat_id", ASCENDING), ("name", ASCENDING)], unique=True)
        await self.logs.create_index([("chat_id", ASCENDING), ("created_at", DESCENDING)])
        await self.sudos.create_index("user_id", unique=True)
        await self.blacklist.create_index("user_id", unique=True)
        await self.stats.create_index([("chat_id", ASCENDING), ("user_id", ASCENDING)], unique=True)

    async def ensure_group(self, chat_id: int, title: str = "") -> dict:
        return await self.groups.find_one_and_update(
            {"chat_id": chat_id},
            {"$setOnInsert": {
                "chat_id": chat_id, "title": title, "created_at": utcnow(),
                "locks": [], "welcome": {"enabled": False, "text": "Welcome, {fullname}!", "media": None},
                "goodbye": {"enabled": False, "text": "Goodbye, {fullname}!", "media": None},
                "settings": {"warn_limit": 3, "warn_ban_limit": 5, "antispam": {"enabled": True}, "raid": {"enabled": False}},
                "log_chat_id": None,
            }, "$set": {"title": title, "updated_at": utcnow()}},
            upsert=True, return_document=True,
        )

    async def group(self, chat_id: int) -> dict:
        return await self.groups.find_one({"chat_id": chat_id}) or await self.ensure_group(chat_id)

    async def update_group(self, chat_id: int, update: dict) -> None:
        await self.groups.update_one({"chat_id": chat_id}, {"$set": {**update, "updated_at": utcnow()}})

    async def log(self, chat_id: int, actor_id: int | None, action: str, target_id: int | None = None, details: dict | None = None) -> None:
        await self.logs.insert_one({"chat_id": chat_id, "actor_id": actor_id, "target_id": target_id, "action": action, "details": details or {}, "created_at": utcnow()})

    async def increment_stat(self, chat_id: int, user_id: int, field: str, amount: int = 1) -> None:
        await self.stats.update_one({"chat_id": chat_id, "user_id": user_id}, {"$inc": {field: amount}, "$set": {"updated_at": utcnow()}}, upsert=True)

    async def get_warn(self, chat_id: int, user_id: int) -> dict:
        return await self.warns.find_one({"chat_id": chat_id, "user_id": user_id}) or {"chat_id": chat_id, "user_id": user_id, "count": 0, "items": []}

    async def add_warn(self, chat_id: int, user_id: int, reason: str, actor_id: int) -> int:
        doc = {"at": utcnow(), "reason": reason[:500], "actor_id": actor_id}
        result = await self.warns.find_one_and_update({"chat_id": chat_id, "user_id": user_id}, {"$inc": {"count": 1}, "$push": {"items": {"$each": [doc], "$slice": -50}}}, upsert=True, return_document=True)
        return int(result.get("count", 1))

    async def reset_warns(self, chat_id: int, user_id: int) -> None:
        await self.warns.delete_one({"chat_id": chat_id, "user_id": user_id})

    async def del_warn(self, chat_id: int, user_id: int) -> int:
        result = await self.warns.find_one_and_update({"chat_id": chat_id, "user_id": user_id}, {"$inc": {"count": -1}, "$pop": {"items": 1}}, return_document=True)
        if not result or result.get("count", 0) <= 0:
            await self.reset_warns(chat_id, user_id)
            return 0
        return int(result["count"])

    async def add_sudo(self, user_id: int) -> None:
        await self.sudos.update_one({"user_id": user_id}, {"$set": {"user_id": user_id, "updated_at": utcnow()}}, upsert=True)

    async def del_sudo(self, user_id: int) -> None:
        await self.sudos.delete_one({"user_id": user_id})

    async def is_sudo(self, user_id: int) -> bool:
        return bool(await self.sudos.find_one({"user_id": user_id}))

    async def sudo_ids(self) -> list[int]:
        return [int(x["user_id"]) async for x in self.sudos.find({}, {"user_id": 1})]

    async def set_blacklist(self, user_id: int, reason: str = "") -> None:
        await self.blacklist.update_one({"user_id": user_id}, {"$set": {"user_id": user_id, "reason": reason[:500], "created_at": utcnow()}}, upsert=True)

    async def is_blacklisted(self, user_id: int) -> bool:
        return bool(await self.blacklist.find_one({"user_id": user_id}))

    async def del_blacklist(self, user_id: int) -> None:
        await self.blacklist.delete_one({"user_id": user_id})

    async def all_groups(self):
        return self.groups.find({}, {"chat_id": 1})

    async def close_all(self):
        await self.client.close()
