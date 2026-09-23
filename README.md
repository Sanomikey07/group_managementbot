# DEMON Admin — Production Telegram Group Management Bot

A modular, async Telegram group administration/moderation bot built around the Pyrogram API style, MongoDB, and a strict permission boundary.

## Important 2026 dependency decision

The original Pyrogram project is archived and explicitly says it is no longer maintained. This project therefore uses **Kurigram**, an actively maintained Pyrogram-compatible fork. Your Python imports remain `from pyrogram ...`, so the application architecture remains Pyrogram-style. MongoDB's async Motor driver was deprecated on May 14, 2026; this project uses the official native `pymongo.AsyncMongoClient` instead.

## Included

- Global owner and unlimited sudo users
- Owner-only developer controls
- Telegram admin permission verification for every moderation command
- Protected owner/sudo targets
- Ban, temporary ban, kick, mute, temporary mute, unmute
- Warning system with configurable mute/ban thresholds
- Purge, purge ranges and purge-by-user
- Pin/unpin, promote/demote/title, invite/revoke, chat photo/description
- Persistent locks
- Repeated-message/link/mention/sticker/GIF anti-spam
- Welcome/goodbye templates with `{first}`, `{last}`, `{fullname}`, `{username}`, `{id}`, `{group}`, `{count}`
- Markdown/HTML welcome output detection
- Persistent keyword filters with URL buttons and media
- Persistent notes with text/media
- Global blacklist
- Broadcast with bounded concurrency
- Inline help navigation
- Per-command rate limiting
- MongoDB indexes and async I/O
- Structured moderation/settings logs
- Graceful SIGINT/SIGTERM shutdown

## Requirements

- Python 3.11+ recommended
- MongoDB 6/7/8 or MongoDB Atlas
- Telegram bot token
- Telegram API ID and API hash
- Numeric Telegram owner ID

## Setup

```bash
git clone <your-repository>
cd demon_admin_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and provide real values for `API_ID`, `API_HASH`, `BOT_TOKEN`, `OWNER_ID`, and `MONGO_URI`.

The owner ID is intentionally read from an environment variable rather than hard-coded into source control. Never commit a bot token or MongoDB password.

## MongoDB security

Use a dedicated database user with only the permissions required for this database. For Atlas, restrict network access to the deployment environment where practical. Enable TLS and use a `mongodb+srv://` URI for Atlas.

## Telegram setup

Add the bot to the group and make it an administrator. Grant only the permissions required by the features you intend to use:

- Delete messages for purge/locks/anti-spam
- Restrict members for mute/ban/warnings
- Pin messages for pinning
- Invite users for invite-link commands
- Change group info for welcome/settings/photo/description
- Promote members for promote/demote/title

The bot checks its current Telegram privileges before executing actions and reports insufficient permissions instead of crashing.

## Run

```bash
source .venv/bin/activate
python main.py
```

## Termux

```bash
pkg update
pkg install python
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python main.py
```

For long-running production hosting, prefer a VPS/container/process manager instead of relying on a phone terminal session.

## Docker

A minimal image can be built with Python 3.12:

```bash
docker build -t demon-admin .
docker run --env-file .env --restart unless-stopped demon-admin
```

## Railway / Render / VPS

Use the repository as a Python service. The start command is:

```text
python main.py
```

Provide the environment variables from `.env` in the hosting provider's secret/environment settings. Do not upload `.env` to GitHub.

## Command examples

```text
/ban                 # reply to a user
/tban 30m            # reply to a user
/mute                # reply to a user
/tmute 2h            # reply to a user
/warn spam links     # reply to a user
/warns               # reply to a user
/resetwarns          # reply to a user
/purge               # reply to first message to purge through command
/purgeuser 123456789
/lock link
/unlock link
/setwelcome Welcome {fullname}! You are member #{count}.
/welcome on
/goodbye off
/addfilter hello | Hi there! [Website](https://example.com)
/save rules          # reply to a text/media message
/get rules
```

## Owner commands

```text
/addsudo 123456789
/delsudo 123456789
/sudolist
/blacklist 123456789
/unblacklist 123456789
/broadcast           # reply to the message to broadcast
/leave -1001234567890
/reload
```

## Security model

1. Owner ID is checked before all other role checks.
2. Sudo users bypass Telegram group-admin checks but cannot change owner/sudo state or developer/database controls.
3. Normal admins are checked against the exact Telegram privilege needed by the command.
4. Protected owner/sudo users cannot be moderated through ordinary moderation commands.
5. IDs are parsed and bounded before use.
6. Command rate limiting is applied per user/command.
7. Database operations are asynchronous and indexed.
8. Telegram RPC failures are caught at command boundaries and do not terminate the process.
9. Secrets are loaded from environment variables and are not stored in MongoDB.

## Project layout

```text
config/         settings and constants
database/       MongoDB access and indexes
handlers/       Telegram command/event registration
modules/        permissions, anti-spam, locks, notes, templates
utils/          parsing, formatting, Telegram helpers
filters/        custom command-filter helpers
main.py         application bootstrap
requirements.txt
.env.example
README.md
```

## Notes on Telegram limitations

Some Telegram actions are inherently controlled by Telegram itself. For example, a bot cannot bypass Telegram's hierarchy rules, cannot moderate the owner of a group, and cannot grant privileges it does not possess. The bot treats those API responses as expected operational failures rather than application crashes.

## License

Choose and add the license appropriate for your deployment before publishing the repository.
