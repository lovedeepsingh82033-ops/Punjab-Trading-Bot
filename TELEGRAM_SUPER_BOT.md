# Punjab AI Super Bot

A separate, read-only Telegram command interface for the existing Punjab Scanner.
It does not replace the existing notification bot, trigger scans, or place orders.

## Commands
- `/start`, `/help`
- `/status`, `/health`
- `/research`, `/calendar`, `/history`

## Private shared-state bridge (Supabase Storage)

The scanner runs in ephemeral GitHub Actions runners while the Telegram worker
runs on Render. They cannot share a local file. This repository therefore
supports a private Supabase Storage bucket named `scanner-state` containing
`bot_state.json`.

Create a Supabase project and a **private** Storage bucket (not public) named
`scanner-state`. Keep the bucket private. Use a Supabase server-side secret
key/service-role key only in GitHub Actions Secrets and Render Environment
Variables; never put it in source code, commit it, or send it in chat.

Add these GitHub repository Actions Secrets:
- `BOT_STATE_BRIDGE_URL`: Supabase project URL, e.g. `https://YOUR_PROJECT.supabase.co`
- `BOT_STATE_BRIDGE_KEY`: server-side secret/service-role key for that project
- `BOT_STATE_BRIDGE_BUCKET`: `scanner-state`

The scheduled scanner uploads the compact snapshot after building the
Intelligence Hub. The Render worker downloads the latest snapshot when a
command is requested. If the bridge is not configured, the scanner retains
its existing local snapshot behavior and the worker can use a local file for
development.

Add the same three variables to the Render worker. Also retain:
- `SUPER_BOT_TOKEN`
- `SUPER_BOT_ALLOWED_USER_IDS`

## Render deployment
- Runtime: Python 3
- Build command: `pip install -r requirements.txt`
- Start command: `python telegram_super_bot.py`
- Keep the worker as a persistent Background Worker.

The worker is read-only and restricted to the configured numeric Telegram
user allowlist in private chats. No scan is triggered and no orders are placed.
Do not reuse the existing notification bot token.
