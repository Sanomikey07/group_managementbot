from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config.constants import HELP_CATEGORIES


def menu():
    names = ["general", "administration", "moderation", "locks", "warnings", "filters", "notes", "welcome", "settings", "owner"]
    return InlineKeyboardMarkup([[InlineKeyboardButton(n.title(), callback_data=f"help:{n}")] for n in names])


def page(category: str):
    commands = HELP_CATEGORIES.get(category, [])
    body = f"<b>{category.title()}</b>\n\n" + "\n".join(f"<code>{c}</code>" for c in commands)
    return body, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="help:home")]])
