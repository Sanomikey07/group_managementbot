import asyncio
import html
import re
import time
from collections import defaultdict, deque
from typing import Any

from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import RPCError

_ID_RE = re.compile(r"^-?\d+$")


class RateLimiter:
    def __init__(self, limit: int, window: int):
        self.limit, self.window = limit, window
        self._events = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, key: Any) -> bool:
        now = time.monotonic()
        async with self._lock:
            q = self._events[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


def parse_user_id(value: str | None) -> int | None:
    if not value or not _ID_RE.fullmatch(value.strip()):
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if abs(number) <= 10**15 else None


def escape_html(value: str) -> str:
    return html.escape(value or "", quote=False)


def escape_md(value: str) -> str:
    return re.sub(r"([_\*\[\]\(\)~`>#+\-=|{}.!])", r"\\\1", value or "")


def extract_link(text: str) -> bool:
    return bool(re.search(r"(?:https?://|www\.|t\.me/|telegram\.me/|tg://)", text or "", re.I))


def message_text(message) -> str:
    return (message.text or message.caption or "").strip()


async def safe_delete(message) -> bool:
    try:
        await message.delete()
        return True
    except RPCError:
        return False


async def safe_answer(query, text: str, alert: bool = False) -> None:
    try:
        await query.answer(text, show_alert=alert)
    except RPCError:
        pass


async def is_admin(client, chat_id: int, user_id: int) -> tuple[bool, Any]:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR), member
    except RPCError:
        return False, None


async def bot_permissions(client, chat_id: int):
    me = await client.get_me()
    member = await client.get_chat_member(chat_id, me.id)
    return getattr(member, "privileges", None)


def has_privilege(privileges, name: str) -> bool:
    return bool(privileges and (getattr(privileges, name, False) or getattr(privileges, "can_manage_chat", False)))
