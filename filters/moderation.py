import re
from pyrogram import filters

COMMAND_RE = re.compile(r"^/([A-Za-z0-9_]+)(?:@\w+)?(?:\s+(.*))?$", re.S)

def command_filter(commands):
    commands = {commands} if isinstance(commands, str) else set(commands)
    return filters.regex(r"^/(?:" + "|".join(map(re.escape, commands)) + r")(?:@\w+)?(?:\s|$)", flags=re.I)
