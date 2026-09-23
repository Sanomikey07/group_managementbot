from dataclasses import dataclass
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import RPCError
from utils.security import has_privilege


@dataclass
class Access:
    allowed: bool
    owner: bool = False
    sudo: bool = False
    member: object | None = None
    reason: str = ""


async def access(ctx, message, required: str | None = None, owner_only: bool = False) -> Access:
    uid = message.from_user.id if message.from_user else 0
    if uid == ctx.settings.owner_id:
        return Access(True, owner=True)
    sudo = await ctx.db.is_sudo(uid)
    if sudo:
        return Access(True, sudo=True)
    if owner_only:
        return Access(False, reason="Owner-only command.")
    if message.chat.type.name not in {"GROUP", "SUPERGROUP"}:
        return Access(False, reason="This command is only available in groups.")
    try:
        member = await ctx.app.get_chat_member(message.chat.id, uid)
        if member.status not in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            return Access(False, reason="You don't have permission to use this command.")
        if required and member.status != ChatMemberStatus.OWNER and not has_privilege(member.privileges, required):
            return Access(False, member=member, reason=f"You need Telegram permission: {required.replace('can_', '').replace('_', ' ')}.")
        return Access(True, member=member)
    except RPCError:
        return Access(False, reason="I couldn't verify your Telegram admin permissions.")


async def bot_can(ctx, chat_id: int, required: str) -> bool:
    try:
        me = await ctx.app.get_me()
        member = await ctx.app.get_chat_member(chat_id, me.id)
        if member.status == ChatMemberStatus.OWNER:
            return True
        return has_privilege(member.privileges, required)
    except RPCError:
        return False
