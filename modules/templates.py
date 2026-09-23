from pyrogram.enums import ParseMode
from utils.formatting import render_vars


def _mode(text: str):
    # HTML is selected when Telegram-style tags are present; otherwise Markdown is used.
    return ParseMode.HTML if any(tag in text for tag in ("<b>", "<i>", "<u>", "<code>", "<a ")) else ParseMode.MARKDOWN


async def send_template(ctx, chat, user, config, count=None):
    if not config.get("enabled") or not config.get("text"):
        return None
    text = render_vars(config["text"], user, chat, count)
    mode = _mode(text)
    media = config.get("media")
    if media:
        kind, file_id = media.get("kind"), media.get("file_id")
        if kind == "photo": return await ctx.app.send_photo(chat.id, file_id, caption=text, parse_mode=mode)
        if kind == "animation": return await ctx.app.send_animation(chat.id, file_id, caption=text, parse_mode=mode)
        if kind == "sticker": return await ctx.app.send_sticker(chat.id, file_id)
    return await ctx.app.send_message(chat.id, text, parse_mode=mode)
