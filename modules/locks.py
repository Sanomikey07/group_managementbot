from utils.security import extract_link, safe_delete


def locked_types(message) -> set[str]:
    found = set()
    if message.photo: found.add("photo")
    if message.video: found.add("video")
    if message.sticker: found.add("sticker")
    if message.animation: found.add("gif")
    if message.document: found.add("document")
    if message.voice: found.add("voice")
    if message.audio: found.add("audio")
    if message.contact: found.add("contact")
    if message.location: found.add("location")
    if message.poll: found.add("poll")
    if message.game: found.add("game")
    if message.forward_date: found.add("forward")
    text = message.text or message.caption or ""
    if extract_link(text): found.add("link")
    return found


async def enforce(ctx, message) -> bool:
    if not message.from_user:
        return False
    group = await ctx.db.group(message.chat.id)
    locks = set(group.get("locks", []))
    if not locks:
        return False
    types = locked_types(message)
    if "all" in locks or types & locks:
        await safe_delete(message)
        return True
    return False
