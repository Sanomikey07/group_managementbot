import asyncio
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatMembersFilter
from pyrogram.errors import RPCError, FloodWait
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import ChatPermissions, ChatPrivileges, InlineKeyboardButton, InlineKeyboardMarkup

from config.constants import MODERATION_COMMANDS, LOCK_TYPES
from modules.permissions import access, bot_can
from modules.help_menu import menu, page
from modules.notes import save_message, send_note
from modules.templates import send_template
from utils.security import parse_user_id, safe_delete, safe_answer, RateLimiter
from utils.formatting import render_vars
from utils.telegram import resolve_target

DURATION_RE = re.compile(r"^(\d+)([smhdw])$", re.I)
BUTTON_RE = re.compile(r"\[([^\]]{1,64})\]\((https?://[^\s)]+)\)")


def parse_command(message):
    text = message.text or ""
    if not text.startswith("/"):
        return None, ""
    first, *rest = text.split(maxsplit=1)
    command = first[1:].split("@", 1)[0].lower()
    return command, rest[0].strip() if rest else ""


def parse_duration(value: str | None) -> timedelta | None:
    if not value: return None
    m = DURATION_RE.fullmatch(value.strip())
    if not m: return None
    amount, unit = int(m.group(1)), m.group(2).lower()
    if unit == "s": return timedelta(seconds=amount)
    if unit == "m": return timedelta(minutes=amount)
    if unit == "h": return timedelta(hours=amount)
    if unit == "d": return timedelta(days=amount)
    return timedelta(weeks=amount)


async def deny(message, text="❌ You don't have permission."):
    await message.reply_text(text)


async def require_access(ctx, message, required=None, owner_only=False):
    a = await access(ctx, message, required, owner_only)
    if not a.allowed:
        await deny(message, f"❌ {a.reason}")
    return a


async def target_or_reply(ctx, message, args):
    arg = args.split(maxsplit=1)[0] if args else None
    user = await resolve_target(ctx.app, message, arg)
    if not user:
        await message.reply_text("⚠️ Reply to a user or provide a valid user ID/username.")
        return None
    return user


async def punish(ctx, message, action: str, args: str, temporary: timedelta | None = None):
    target = await target_or_reply(ctx, message, args)
    if not target: return
    if target.id == ctx.settings.owner_id or await ctx.db.is_sudo(target.id):
        await message.reply_text("❌ Protected user.")
        return
    if action in {"ban", "tban", "kick"}:
        if not await bot_can(ctx, message.chat.id, "can_restrict_members"):
            await message.reply_text("❌ I need permission to restrict members.")
            return
        await ctx.app.ban_chat_member(message.chat.id, target.id)
        if action == "kick":
            await ctx.app.unban_chat_member(message.chat.id, target.id, only_if_banned=True)
        elif temporary:
            until = datetime.now(timezone.utc) + temporary
            await ctx.app.ban_chat_member(message.chat.id, target.id, until_date=until)
        await ctx.db.log(message.chat.id, message.from_user.id, action, target.id)
        await message.reply_text(f"☑ {target.mention} {'kicked' if action == 'kick' else 'banned'}.")
    elif action in {"mute", "tmute"}:
        if not await bot_can(ctx, message.chat.id, "can_restrict_members"):
            await message.reply_text("❌ I need permission to restrict members.")
            return
        until = datetime.now(timezone.utc) + temporary if temporary else None
        await ctx.app.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=until)
        await ctx.db.log(message.chat.id, message.from_user.id, action, target.id)
        await message.reply_text(f"☑ {target.mention} muted.")


async def handle_command(ctx, message):
    command, args = parse_command(message)
    if not command:
        return False
    await ctx.db.ensure_group(message.chat.id, message.chat.title or "") if message.chat else None

    # Global blacklist is enforced before ordinary commands.
    if message.from_user and await ctx.db.is_blacklisted(message.from_user.id) and message.from_user.id != ctx.settings.owner_id:
        await safe_delete(message)
        return True

    if not await ctx.rate_limiter.allow((message.from_user.id if message.from_user else 0, command)):
        await message.reply_text("⏳ Slow down. Please try again in a moment.")
        return True

    if command in {"start", "about", "ping", "help", "id", "info", "settings", "stats", "admins"}:
        return await general(ctx, message, command, args)

    if command in {"addsudo", "delsudo", "sudolist", "blacklist", "unblacklist", "broadcast", "leave", "join", "reload", "approve"}:
        return await owner_commands(ctx, message, command, args)

    if command in {"ban", "tban", "kick", "mute", "tmute"}:
        required = "can_restrict_members"
        if not (await require_access(ctx, message, required)).allowed: return True
        if command in {"tban", "tmute"}:
            parts = args.split(maxsplit=1)
            duration = parse_duration(parts[0]) if parts else None
            if not duration:
                await message.reply_text("⚠️ Usage: /tban 10m (reply to a user) or /tmute 1h")
                return True
            target_args = parts[1] if len(parts) > 1 else ""
            await punish(ctx, message, command, target_args, duration)
        else:
            await punish(ctx, message, command, args)
        return True

    if command in {"unban", "unmute"}:
        if not (await require_access(ctx, message, "can_restrict_members")).allowed: return True
        target = await target_or_reply(ctx, message, args)
        if not target: return True
        if command == "unban": await ctx.app.unban_chat_member(message.chat.id, target.id, only_if_banned=True)
        else: await ctx.app.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=True))
        await ctx.db.log(message.chat.id, message.from_user.id, command, target.id)
        await message.reply_text(f"☑ {target.mention} {'unbanned' if command == 'unban' else 'unmuted'}.")
        return True

    if command in {"warn", "warns", "resetwarns", "delwarn"}:
        return await warnings(ctx, message, command, args)

    if command in {"purge", "spurge", "purgefrom", "purgeto", "purgeuser"}:
        return await purge(ctx, message, command, args)

    if command in {"pin", "unpin", "promote", "demote", "title", "setphoto", "setdescription", "invitelink", "revoke"}:
        return await admin_tools(ctx, message, command, args)

    if command in {"lock", "unlock"}:
        return await lock_command(ctx, message, command, args)

    if command in {"setwelcome", "resetwelcome", "welcome", "setgoodbye", "goodbye"}:
        return await welcome_commands(ctx, message, command, args)

    if command in {"addfilter", "delfilter", "filters"}:
        return await filter_commands(ctx, message, command, args)

    if command in {"save", "get", "notes", "clear"}:
        return await note_commands(ctx, message, command, args)

    return False


async def general(ctx, message, command, args):
    if command == "start":
        await message.reply_text("👋 <b>DEMON Admin</b>\nAdd me to a group as admin, then use /help.", parse_mode="html")
    elif command == "about": await message.reply_text("<b>DEMON Admin</b> — async group moderation bot.", parse_mode="html")
    elif command == "ping": await message.reply_text("🏓 Pong!")
    elif command == "help": await message.reply_text("<b>DEMON Admin Help</b>\nChoose a category:", reply_markup=menu(), parse_mode="html")
    elif command == "id": await message.reply_text(f"👤 User ID: <code>{message.from_user.id}</code>\n💬 Chat ID: <code>{message.chat.id}</code>", parse_mode="html")
    elif command == "info":
        u = message.from_user
        await message.reply_text(f"<b>{u.mention}</b>\nID: <code>{u.id}</code>\nUsername: @{u.username or 'none'}", parse_mode="html")
    elif command == "admins":
        rows = []
        async for m in ctx.app.get_chat_members(message.chat.id, filter=ChatMembersFilter.ADMINISTRATORS):
            rows.append(f"• {m.user.mention}")
        await message.reply_text("<b>Admins</b>\n" + "\n".join(rows[:100]), parse_mode="html")
    elif command == "settings":
        if args and not (await require_access(ctx, message, "can_change_info")).allowed: return True
        g = await ctx.db.group(message.chat.id)
        if not args:
            s = g.get("settings", {})
            await message.reply_text(f"<b>Settings</b>\nWarn mute: {s.get('warn_limit',3)}\nWarn ban: {s.get('warn_ban_limit',5)}\nAnti-spam: {s.get('antispam',{}).get('enabled',True)}\nRaid: {s.get('raid',{}).get('enabled',False)}", parse_mode="html")
        else:
            p = args.split(maxsplit=1)
            if len(p) != 2: await message.reply_text("⚠️ Usage: /settings warnlimit 3 | warnbanlimit 5 | antispam on|off | raid on|off"); return True
            key, value = p[0].lower(), p[1].lower()
            if key in {"warnlimit", "warnbanlimit"}:
                try: n = max(1, min(20, int(value)))
                except ValueError: await message.reply_text("⚠️ Value must be a number."); return True
                field = "warn_limit" if key == "warnlimit" else "warn_ban_limit"
                await ctx.db.update_group(message.chat.id, {f"settings.{field}": n})
            elif key in {"antispam", "raid"}:
                await ctx.db.update_group(message.chat.id, {f"settings.{key}.enabled": value in {"on","yes","true","1"}})
            else: await message.reply_text("⚠️ Unknown setting."); return True
            await ctx.db.log(message.chat.id, message.from_user.id, "setting_change", details={"key":key,"value":value})
            await message.reply_text("☑ Setting updated.")
    elif command == "stats":
        if not (await require_access(ctx, message)).allowed: return True
        if message.from_user.id == ctx.settings.owner_id or await ctx.db.is_sudo(message.from_user.id):
            groups = await ctx.db.groups.count_documents({})
            users = await ctx.db.users.count_documents({})
            warns = await ctx.db.warns.count_documents({})
            await message.reply_text(f"<b>Global stats</b>\nGroups: {groups}\nUsers: {users}\nWarn records: {warns}", parse_mode="html")
        else:
            stats = await ctx.db.stats.find({"chat_id": message.chat.id}).to_list(1000)
            await message.reply_text(f"<b>Group stats</b>\nTracked users: {len(stats)}", parse_mode="html")
    return True


async def owner_commands(ctx, message, command, args):
    if command in {"addsudo", "delsudo", "sudolist"}:
        if not (await require_access(ctx, message, owner_only=True)).allowed: return True
    elif not (await require_access(ctx, message)).allowed:
        return True
    if command == "addsudo":
        uid = parse_user_id(args)
        if uid is None: await message.reply_text("⚠️ Provide a valid numeric user ID."); return True
        await ctx.db.add_sudo(uid); await message.reply_text("☑ Sudo user added.")
    elif command == "delsudo":
        uid = parse_user_id(args)
        if uid is None: await message.reply_text("⚠️ Provide a valid numeric user ID."); return True
        await ctx.db.del_sudo(uid); await message.reply_text("☑ Sudo user removed.")
    elif command == "sudolist": await message.reply_text("<b>Sudo</b>\n" + "\n".join(f"• <code>{x}</code>" for x in await ctx.db.sudo_ids()) or "No sudo users.", parse_mode="html")
    elif command in {"blacklist", "unblacklist"}:
        if message.from_user.id != ctx.settings.owner_id and not await ctx.db.is_sudo(message.from_user.id): await deny(message); return True
        target = await target_or_reply(ctx, message, args)
        if not target: return True
        if command == "blacklist": await ctx.db.set_blacklist(target.id, args); await message.reply_text("☑ User globally blacklisted.")
        else: await ctx.db.del_blacklist(target.id); await message.reply_text("☑ User removed from global blacklist.")
    elif command == "broadcast":
        if not message.reply_to_message: await message.reply_text("⚠️ Reply to the message you want to broadcast."); return True
        sem = asyncio.Semaphore(ctx.settings.max_broadcast_concurrency)
        sent = failed = 0
        async def one(chat_id):
            nonlocal sent, failed
            async with sem:
                try: await message.reply_to_message.copy(chat_id); sent += 1
                except Exception: failed += 1
        tasks = [one(int(x["chat_id"])) async for x in ctx.db.all_groups()]
        await asyncio.gather(*tasks)
        await message.reply_text(f"☑ Broadcast finished. Sent: {sent}, failed: {failed}.")
    elif command == "join":
        if not args: await message.reply_text("⚠️ Usage: /join <public username or invite link>"); return True
        try: await ctx.app.join_chat(args.strip()); await message.reply_text("☑ Joined the chat.")
        except RPCError as e: await message.reply_text(f"❌ Telegram rejected the join request: {e.__class__.__name__}")
    elif command == "leave":
        if not args: await message.reply_text("⚠️ Usage: /leave <chat_id>"); return True
        cid = parse_user_id(args)
        if cid is None: await message.reply_text("⚠️ Invalid chat ID."); return True
        await ctx.app.leave_chat(cid); await message.reply_text("☑ Left the chat.")
    elif command == "reload":
        from config.settings import get_settings
        get_settings.cache_clear()
        ctx.settings = get_settings()
        await message.reply_text("☑ Configuration reloaded.")
    elif command == "approve":
        if not message.chat or not (await require_access(ctx, message, "can_restrict_members")).allowed: return True
        target = await target_or_reply(ctx, message, args)
        if not target: return True
        await ctx.app.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=True))
        await message.reply_text("☑ Member approved.")
    return True


async def warnings(ctx, message, command, args):
    if not (await require_access(ctx, message, "can_restrict_members")).allowed: return True
    target = await target_or_reply(ctx, message, args)
    if not target: return True
    if command == "warn":
        reason = args
        count = await ctx.db.add_warn(message.chat.id, target.id, reason, message.from_user.id)
        g = await ctx.db.group(message.chat.id); s = g.get("settings", {})
        if count >= s.get("warn_ban_limit", 5):
            await ctx.app.ban_chat_member(message.chat.id, target.id)
            action = "banned"
        elif count >= s.get("warn_limit", 3):
            await ctx.app.restrict_chat_member(message.chat.id, target.id, permissions=ChatPermissions(can_send_messages=False))
            action = "muted"
        else: action = "warned"
        await ctx.db.log(message.chat.id, message.from_user.id, "warn", target.id, {"count":count})
        await message.reply_text(f"⚠️ {target.mention} {action}. Warnings: {count}.")
    elif command == "warns":
        w = await ctx.db.get_warn(message.chat.id, target.id); await message.reply_text(f"⚠️ {target.mention} has <b>{w.get('count',0)}</b> warning(s).", parse_mode="html")
    elif command == "resetwarns": await ctx.db.reset_warns(message.chat.id, target.id); await message.reply_text("☑ Warnings reset.")
    else: await message.reply_text(f"☑ Warning removed. Remaining: {await ctx.db.del_warn(message.chat.id, target.id)}")
    return True


async def purge(ctx, message, command, args):
    if not (await require_access(ctx, message, "can_delete_messages")).allowed: return True
    if command in {"purge", "spurge"}:
        if not message.reply_to_message: await message.reply_text("⚠️ Reply to the first message to purge from."); return True
        start = message.reply_to_message.id
        end = message.id
    elif command == "purgefrom":
        parts = args.split(); start = int(parts[0]) if parts and parts[0].isdigit() else 0; end = message.id
    elif command == "purgeto":
        start = int(args) if args.isdigit() else 0; end = message.id
    else:
        target = await target_or_reply(ctx, message, args)
        if not target: return True
        ids = []
        async for m in ctx.app.search_messages(message.chat.id, from_user=target.id, limit=100): ids.append(m.id)
        await ctx.app.delete_messages(message.chat.id, ids); await message.reply_text(f"☑ Deleted {len(ids)} message(s) from {target.mention}."); return True
    if not start: await message.reply_text("⚠️ Provide a valid message ID."); return True
    ids = list(range(start, end + 1))
    for i in range(0, len(ids), 100):
        try: await ctx.app.delete_messages(message.chat.id, ids[i:i+100])
        except FloodWait as e: await asyncio.sleep(e.value)
        except RPCError: pass
    return True


async def admin_tools(ctx, message, command, args):
    required = {"pin":"can_pin_messages","unpin":"can_pin_messages","promote":"can_promote_members","demote":"can_promote_members","title":"can_promote_members","setphoto":"can_change_info","setdescription":"can_change_info","invitelink":"can_invite_users","revoke":"can_invite_users"}[command]
    if not (await require_access(ctx, message, required)).allowed: return True
    if command in {"pin", "unpin"}:
        target = message.reply_to_message
        if command == "pin":
            if not target: await message.reply_text("⚠️ Reply to the message to pin."); return True
            await target.pin(disable_notification=True)
        else: await ctx.app.unpin_chat_message(message.chat.id, target.id if target else None)
        await message.reply_text("☑ Done."); return True
    if command in {"promote", "demote", "title"}:
        target = await target_or_reply(ctx, message, args)
        if not target: return True
        if command == "demote": await ctx.app.promote_chat_member(message.chat.id, target.id, privileges=ChatPrivileges())
        elif command == "promote": await ctx.app.promote_chat_member(message.chat.id, target.id, privileges=ChatPrivileges(can_manage_chat=True, can_delete_messages=True, can_restrict_members=True, can_promote_members=False, can_invite_users=True, can_pin_messages=True, can_change_info=False))
        else:
            title = args.split(maxsplit=1)[1] if len(args.split(maxsplit=1)) > 1 else ""
            if not title: await message.reply_text("⚠️ Usage: /title <user> <custom title> or reply with /title <title>"); return True
            await ctx.app.set_administrator_title(message.chat.id, target.id, title[:16])
        await message.reply_text("☑ Done."); return True
    if command == "setdescription":
        if not args: await message.reply_text("⚠️ Provide a description."); return True
        await ctx.app.set_chat_description(message.chat.id, args[:255]); await message.reply_text("☑ Description updated."); return True
    if command == "setphoto":
        src = message.reply_to_message
        if not src or not src.photo: await message.reply_text("⚠️ Reply to a photo."); return True
        path = await ctx.app.download_media(src, in_memory=False)
        try: await ctx.app.set_chat_photo(message.chat.id, photo=path)
        finally:
            if path and os.path.exists(path): os.unlink(path)
        await message.reply_text("☑ Chat photo updated."); return True
    if command == "invitelink":
        link = await ctx.app.export_chat_invite_link(message.chat.id); await message.reply_text(f"🔗 {link}"); return True
    if command == "revoke":
        link = args.strip()
        if not link: await message.reply_text("⚠️ Provide an invite link to revoke."); return True
        await ctx.app.revoke_chat_invite_link(message.chat.id, link); await message.reply_text("☑ Invite link revoked.")
    return True


async def lock_command(ctx, message, command, args):
    if not (await require_access(ctx, message, "can_delete_messages")).allowed: return True
    typ = args.lower().split()[0] if args else ""
    if typ not in LOCK_TYPES: await message.reply_text("⚠️ Invalid lock type. Use /help → Locks."); return True
    g = await ctx.db.group(message.chat.id); locks = set(g.get("locks", []))
    if command == "lock": locks.add(typ)
    else: locks.discard(typ)
    await ctx.db.update_group(message.chat.id, {"locks": sorted(locks)})
    await ctx.db.log(message.chat.id, message.from_user.id, command, details={"type":typ})
    await message.reply_text(f"☑ {typ.title()} {'locked' if command == 'lock' else 'unlocked'}.")
    return True


async def welcome_commands(ctx, message, command, args):
    if not (await require_access(ctx, message, "can_change_info")).allowed: return True
    key = "welcome" if command in {"setwelcome", "resetwelcome", "welcome"} else "goodbye"
    if command in {"welcome", "goodbye"}:
        enabled = args.lower() in {"on","yes","true","1"}
        await ctx.db.update_group(message.chat.id, {f"{key}.enabled": enabled}); await message.reply_text(f"☑ {key.title()} {'enabled' if enabled else 'disabled'}."); return True
    if command.startswith("reset"): await ctx.db.update_group(message.chat.id, {f"{key}.text": "", f"{key}.media": None, f"{key}.enabled": False}); await message.reply_text("☑ Reset."); return True
    src = message.reply_to_message
    text = (src.text or src.caption) if src else args
    if not text: await message.reply_text("⚠️ Reply to a message or provide welcome text."); return True
    media = None
    if src and src.photo: media = {"kind":"photo","file_id":src.photo.file_id}
    elif src and src.animation: media = {"kind":"animation","file_id":src.animation.file_id}
    elif src and src.sticker: media = {"kind":"sticker","file_id":src.sticker.file_id}
    await ctx.db.update_group(message.chat.id, {f"{key}.text": text[:4096], f"{key}.media":media, f"{key}.enabled":True}); await message.reply_text(f"☑ {key.title()} saved.")
    return True


async def parse_buttons(text):
    buttons = BUTTON_RE.findall(text or "")
    clean = BUTTON_RE.sub("", text or "").strip()
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(label, url=url)] for label, url in buttons]) if buttons else None
    return clean, markup


async def filter_commands(ctx, message, command, args):
    if not (await require_access(ctx, message, "can_delete_messages")).allowed: return True
    if command == "filters":
        rows = [f"• <code>{x['keyword']}</code>" async for x in ctx.db.filters.find({"chat_id":message.chat.id}).sort("keyword",1)]
        await message.reply_text("<b>Filters</b>\n" + ("\n".join(rows) or "None"), parse_mode="html"); return True
    if command == "delfilter":
        key = args.lower().strip()
        await ctx.db.filters.delete_one({"chat_id":message.chat.id,"keyword":key}); await message.reply_text("☑ Filter deleted."); return True
    if "|" not in args: await message.reply_text("⚠️ Usage: /addfilter keyword | reply text"); return True
    key, reply = [x.strip() for x in args.split("|",1)]; clean, markup = await parse_buttons(reply)
    src = message.reply_to_message
    media = None
    if src and src.photo: media={"kind":"photo","file_id":src.photo.file_id}
    elif src and src.animation: media={"kind":"animation","file_id":src.animation.file_id}
    elif src and src.sticker: media={"kind":"sticker","file_id":src.sticker.file_id}
    buttons = [[{"text":b.text, "url":b.url} for b in row] for row in markup.inline_keyboard] if markup else None
    await ctx.db.filters.update_one({"chat_id":message.chat.id,"keyword":key.lower()},{"$set":{"chat_id":message.chat.id,"keyword":key.lower(),"text":clean[:4096],"media":media,"buttons":buttons}},{"upsert":True})
    await message.reply_text("☑ Filter saved."); return True


async def note_commands(ctx, message, command, args):
    if not (await require_access(ctx, message, "can_delete_messages")).allowed: return True
    if command == "save":
        src = message.reply_to_message
        if not src: await message.reply_text("⚠️ Reply to a message: /save name"); return True
        try: await save_message(ctx, src, args)
        except ValueError as e: await message.reply_text(f"⚠️ {e}"); return True
        await message.reply_text("☑ Note saved.")
    elif command == "get":
        if not await send_note(ctx, message, args): await message.reply_text("❌ Note not found.")
    elif command == "notes":
        rows = [f"• <code>{x['name']}</code>" async for x in ctx.db.notes.find({"chat_id":message.chat.id}).sort("name",1)]
        await message.reply_text("<b>Notes</b>\n" + ("\n".join(rows) or "None"), parse_mode="html")
    else:
        await ctx.db.notes.delete_one({"chat_id":message.chat.id,"name":args.lower().strip("# ")}); await message.reply_text("☑ Note cleared.")
    return True


async def callbacks(ctx, query):
    if not query.data.startswith("help:"): return
    key = query.data.split(":",1)[1]
    if key == "home": await query.message.edit_text("<b>DEMON Admin Help</b>\nChoose a category:", reply_markup=menu(), parse_mode="html")
    else:
        body, markup = page(key); await query.message.edit_text(body, reply_markup=markup, parse_mode="html")
    await safe_answer(query, "")


def register(app, ctx):
    app.add_handler(MessageHandler(lambda c,m: handle_command(ctx,m), filters.text | filters.caption), group=10)
    app.add_handler(CallbackQueryHandler(lambda c,q: callbacks(ctx,q), filters.regex(r"^help:")), group=10)
