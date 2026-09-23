from html import escape


def user_label(user) -> str:
    if not user:
        return "Unknown user"
    name = escape(user.first_name or "User")
    if user.last_name:
        name += " " + escape(user.last_name)
    return name


def render_vars(text: str, user, chat, count: int | None = None) -> str:
    first = escape(user.first_name or "")
    last = escape(user.last_name or "")
    fullname = escape(" ".join(x for x in [user.first_name, user.last_name] if x) or "User")
    username = escape(user.username or "")
    values = {
        "first": first, "last": last, "fullname": fullname, "username": username,
        "id": str(user.id), "group": escape(chat.title or ""), "count": str(count if count is not None else ""),
    }
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text
