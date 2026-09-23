from datetime import datetime, timezone


def utcnow(): return datetime.now(timezone.utc)


async def save_message(ctx, message, name: str):
    name = name.lower().strip("# ")[:64]
    if not name or any(c.isspace() for c in name):
        raise ValueError("Note name must be one word.")
    media = None
    if message.photo: media = {"kind": "photo", "file_id": message.photo.file_id}
    elif message.video: media = {"kind": "video", "file_id": message.video.file_id}
    elif message.document: media = {"kind": "document", "file_id": message.document.file_id}
    elif message.animation: media = {"kind": "animation", "file_id": message.animation.file_id}
    elif message.sticker: media = {"kind": "sticker", "file_id": message.sticker.file_id}
    doc = {"chat_id": message.chat.id, "name": name, "text": message.text or message.caption, "media": media, "created_at": utcnow(), "updated_at": utcnow()}
    await ctx.db.notes.update_one({"chat_id": message.chat.id, "name": name}, {"$set": doc}, upsert=True)


async def send_note(ctx, message, name: str):
    doc = await ctx.db.notes.find_one({"chat_id": message.chat.id, "name": name.lower().strip("# ")})
    if not doc: return False
    media = doc.get("media")
    if media:
        kind, fid = media["kind"], media["file_id"]
        fn = {"photo": "send_photo", "video": "send_video", "document": "send_document", "animation": "send_animation", "sticker": "send_sticker"}.get(kind)
        if fn == "send_sticker": await ctx.app.send_sticker(message.chat.id, fid)
        elif fn: await getattr(ctx.app, fn)(message.chat.id, fid, caption=doc.get("text"))
    else: await message.reply_text(doc.get("text") or "")
    return True
