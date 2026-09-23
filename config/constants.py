from enum import StrEnum


class LockType(StrEnum):
    MEDIA = "media"
    PHOTO = "photo"
    VIDEO = "video"
    STICKER = "sticker"
    GIF = "gif"
    DOCUMENT = "document"
    LINK = "link"
    FORWARD = "forward"
    POLL = "poll"
    GAME = "game"
    INLINE = "inline"
    VOICE = "voice"
    AUDIO = "audio"
    CONTACT = "contact"
    LOCATION = "location"
    SERVICE = "service"
    ALL = "all"

LOCK_TYPES = {x.value for x in LockType}

MODERATION_COMMANDS = {
    "ban": "can_restrict_members", "tban": "can_restrict_members", "unban": "can_restrict_members",
    "kick": "can_restrict_members", "mute": "can_restrict_members", "tmute": "can_restrict_members",
    "unmute": "can_restrict_members", "warn": "can_restrict_members", "warns": "can_restrict_members",
    "resetwarns": "can_restrict_members", "delwarn": "can_restrict_members", "purge": "can_delete_messages",
    "spurge": "can_delete_messages", "purgefrom": "can_delete_messages", "purgeto": "can_delete_messages",
    "purgeuser": "can_delete_messages", "pin": "can_pin_messages", "unpin": "can_pin_messages",
    "promote": "can_promote_members", "demote": "can_promote_members", "setphoto": "can_change_info",
    "setdescription": "can_change_info", "title": "can_promote_members", "invitelink": "can_invite_users",
    "revoke": "can_invite_users", "lock": "can_delete_messages", "unlock": "can_delete_messages",
    "addfilter": "can_delete_messages", "delfilter": "can_delete_messages", "save": "can_delete_messages",
    "clear": "can_delete_messages", "setwelcome": "can_change_info", "resetwelcome": "can_change_info",
    "welcome": "can_change_info", "setgoodbye": "can_change_info", "goodbye": "can_change_info",
}

HELP_CATEGORIES = {
    "general": ["/start", "/help", "/ping", "/about", "/settings", "/stats", "/id", "/info"],
    "administration": ["/admins", "/promote", "/demote", "/pin", "/unpin", "/invitelink", "/revoke", "/title", "/setphoto", "/setdescription"],
    "moderation": ["/ban", "/tban", "/unban", "/kick", "/mute", "/tmute", "/unmute", "/purge", "/spurge", "/purgefrom", "/purgeto", "/purgeuser"],
    "locks": ["/lock", "/unlock"],
    "warnings": ["/warn", "/warns", "/resetwarns", "/delwarn"],
    "filters": ["/addfilter", "/delfilter", "/filters"],
    "notes": ["/save", "/get", "/notes", "/clear"],
    "welcome": ["/setwelcome", "/resetwelcome", "/welcome on|off", "/setgoodbye", "/goodbye on|off"],
    "settings": ["/settings", "/settings warnlimit 3", "/settings raid on|off"],
    "owner": ["/addsudo", "/delsudo", "/sudolist", "/blacklist", "/unblacklist", "/broadcast", "/join", "/leave", "/reload", "/approve"],
}
