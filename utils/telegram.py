from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import RPCError


async def resolve_target(client, message, arg: str | None = None):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    if arg:
        try:
            return await client.get_users(int(arg))
        except (ValueError, RPCError):
            try:
                return await client.get_users(arg.lstrip("@"))
            except RPCError:
                return None
    return None


async def ensure_group(db, message):
    if message.chat and message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        await db.ensure_group(message.chat.id, message.chat.title or "")


async def ban_user(client, chat_id, user_id):
    await client.ban_chat_member(chat_id, user_id)


async def unban_user(client, chat_id, user_id):
    await client.unban_chat_member(chat_id, user_id, only_if_banned=True)
