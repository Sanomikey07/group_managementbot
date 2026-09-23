import re
import time
from collections import defaultdict, deque
from utils.security import extract_link, safe_delete


class AntiSpam:
    def __init__(self, db):
        self.db = db
        self.recent = defaultdict(lambda: deque(maxlen=8))
        self.links = defaultdict(deque)
        self.mentions = defaultdict(deque)
        self.media = defaultdict(deque)
        self.raid = defaultdict(deque)

    async def check(self, ctx, message) -> bool:
        if not message.from_user or message.from_user.id == ctx.settings.owner_id or await ctx.db.is_sudo(message.from_user.id):
            return False
        if not message.chat or message.chat.type.name not in {"GROUP", "SUPERGROUP"}:
            return False
        cfg = (await self.db.group(message.chat.id)).get("settings", {}).get("antispam", {})
        if not cfg.get("enabled", True):
            return False
        now = time.monotonic()
        key = (message.chat.id, message.from_user.id)
        text = message.text or message.caption or ""
        self.recent[key].append((now, text.lower()))
        repeated = len(self.recent[key]) >= 4 and len({x[1] for x in list(self.recent[key])[-4:]}) == 1 and now - self.recent[key][0][0] <= 12
        link = extract_link(text)
        links = self.links[key]
        if link: links.append(now)
        while links and now - links[0] > 15: links.popleft()
        mention_count = len(re.findall(r"@\w+", text))
        self.mentions[key].append((now, mention_count))
        mentions = sum(x[1] for x in self.mentions[key] if now - x[0] <= 10)
        media_kind = "sticker" if message.sticker else "gif" if message.animation else None
        if media_kind: self.media[key].append((now, media_kind))
        while self.media[key] and now - self.media[key][0][0] > 20: self.media[key].popleft()
        repeated_media = len([x for x in self.media[key] if x[1] == media_kind]) >= 5
        if repeated or len(links) >= 5 or mentions >= 12 or repeated_media:
            await safe_delete(message)
            await ctx.db.increment_stat(message.chat.id, message.from_user.id, "antispam_actions")
            return True
        return False
