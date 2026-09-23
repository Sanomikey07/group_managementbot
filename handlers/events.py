import time
from collections import defaultdict, deque

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.handlers import ChatMemberUpdatedHandler, MessageHandler, DeletedMessagesHandler, EditedMessageHandler
from pyrogram.errors import RPCError
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions

from modules.templates import send_template
from modules.antispam import AntiSpam
from modules.locks import enforce
from utils.security import safe_delete


class RaidTracker:
    def __init__(self):
        self.joins = defaultdict(deque)

    def hit(self, chat_id, now=None):
        now = now or time.monotonic()
        q = self.joins[chat_id]
        q.append(now)
        while q and now - q[0] > 30:
            q.popleft()
        return len(q)


async def member_update(ctx, _, update):
    chat = update.chat
    old = update.old_chat_member
    new = update.new_chat_member
    if not chat or not new: return
    await ctx.db.ensure_group(chat.id, chat.title or "")
    old_status = getattr(old, "status", None)
    new_status = getattr(new, "status", None)
    user = new.user
    if new_status == ChatMemberStatus.MEMBER and old_status in {None, ChatMemberStatus.LEFT, ChatMemberStatus.BANNED, ChatMemberStatus.RESTRICTED}:
        g = await ctx.db.group(chat.id)
        try: count = await ctx.app.get_chat_members_count(chat.id)
        except RPCError: count = None
        await ctx.db.increment_stat(chat.id, user.id, "joins")
        raid = g.get("settings", {}).get("raid", {})
        if raid.get("enabled"):
            burst = ctx.raid.hit(chat.id)
            threshold = int(raid.get("threshold", 8))
            if burst >= threshold:
                action = raid.get("action", "mute")
                try:
                    if action in {"mute", "approval", "verify"}:
                        await ctx.app.restrict_chat_member(chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
                    if action == "verify":
                        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Verify", callback_data=f"raid:verify:{chat.id}:{user.id}")]])
                        await ctx.app.send_message(chat.id, f"<a href='tg://user?id={user.id}'>{user.first_name or 'Member'}</a>, verify to participate.", reply_markup=kb, parse_mode="html")
                    elif action == "approval":
                        await ctx.app.send_message(chat.id, f"⚠️ Raid protection: {user.mention} is temporarily restricted. An admin can use /approve by reply.")
                except RPCError:
                    pass
        await send_template(ctx, chat, user, g.get("welcome", {}), count)
    elif old_status not in {ChatMemberStatus.LEFT, ChatMemberStatus.BANNED} and new_status in {ChatMemberStatus.LEFT, ChatMemberStatus.BANNED}:
        g = await ctx.db.group(chat.id); await ctx.db.increment_stat(chat.id, user.id, "leaves")
        await send_template(ctx, chat, user, g.get("goodbye", {}))


async def message_guard(ctx, client, message):
    if not message.chat or message.chat.type.name not in {"GROUP", "SUPERGROUP"}: return
    await ctx.db.ensure_group(message.chat.id, message.chat.title or "")
    if message.from_user:
        await ctx.db.increment_stat(message.chat.id, message.from_user.id, "messages")
        try:
            member = await client.get_chat_member(message.chat.id, message.from_user.id)
            if member.status in {ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR}:
                return
        except RPCError: pass
    if await enforce(ctx, message): return
    await ctx.antispam.check(ctx, message)


async def filter_guard(ctx, client, message):
    if not message.chat or message.chat.type.name not in {"GROUP", "SUPERGROUP"}: return
    if not message.text or message.text.startswith("/"): return
    if message.from_user:
        try:
            member = await client.get_chat_member(message.chat.id, message.from_user.id)
            if member.status in {ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR}: return
        except RPCError: pass
    text = message.text.lower().strip()
    doc = await ctx.db.filters.find_one({"chat_id": message.chat.id, "keyword": text})
    if not doc: return
    markup = None
    if doc.get("buttons"):
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(x["text"], url=x.get("url")) for x in row] for row in doc["buttons"]])
    media = doc.get("media")
    if media:
        fn = {"photo":"send_photo","animation":"send_animation","sticker":"send_sticker"}.get(media["kind"])
        if fn == "send_sticker": await client.send_sticker(message.chat.id, media["file_id"])
        elif fn: await getattr(client, fn)(message.chat.id, media["file_id"], caption=doc.get("text"), reply_markup=markup)
    else: await message.reply_text(doc.get("text") or "", reply_markup=markup)


async def deleted_log(ctx, client, messages):
    for message in messages:
        if message.chat:
            await ctx.db.log(message.chat.id, None, "message_deleted", message.from_user.id if message.from_user else None, {"message_id": message.id})


async def edited_log(ctx, client, message):
    if message.chat:
        await ctx.db.log(message.chat.id, message.from_user.id if message.from_user else None, "message_edited", message.from_user.id if message.from_user else None, {"message_id": message.id})


async def raid_callback(ctx, query):
    if not query.data.startswith("raid:verify:"): return
    _, _, chat_id, user_id = query.data.split(":")
    if query.from_user.id != int(user_id):
        await query.answer("This verification button is for the joining member.", show_alert=True); return
    try:
        await ctx.app.restrict_chat_member(int(chat_id), int(user_id), permissions=ChatPermissions(can_send_messages=True))
        await query.message.edit_text("✅ Verification complete.")
        await query.answer("Verified.")
    except RPCError:
        await query.answer("Verification could not be completed.", show_alert=True)


def register(app, ctx):
    ctx.antispam = AntiSpam(ctx.db)
    ctx.raid = RaidTracker()
    from pyrogram.handlers import CallbackQueryHandler
    app.add_handler(ChatMemberUpdatedHandler(lambda c,u: member_update(ctx,c,u)), group=5)
    app.add_handler(MessageHandler(lambda c,m: message_guard(ctx,c,m), filters.group & ~filters.service), group=1)
    app.add_handler(MessageHandler(lambda c,m: filter_guard(ctx,c,m), filters.group & filters.text), group=2)
    app.add_handler(DeletedMessagesHandler(lambda c,m: deleted_log(ctx,c,m)), group=5)
    app.add_handler(EditedMessageHandler(lambda c,m: edited_log(ctx,c,m), filters.group), group=5)
    app.add_handler(CallbackQueryHandler(lambda c,q: raid_callback(ctx,q), filters.regex(r"^raid:")), group=5)
