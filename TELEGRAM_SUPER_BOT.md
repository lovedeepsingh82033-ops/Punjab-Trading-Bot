# Punjab AI Super Bot

A separate, read-only Telegram command interface for the existing Punjab Scanner.
It does not replace the existing notification bot, trigger scans, or place orders.

## Commands
- `/start`, `/help`
- `/status`, `/health`
- `/research`, `/calendar`, `/history`

## Environment
- `SUPER_BOT_TOKEN`: token from a newly created Telegram bot. Store only in the host's secret manager.
- `SUPER_BOT_ALLOWED_USER_IDS`: comma-separated numeric Telegram user IDs. The worker refuses to start if empty.
- `BOT_STATE_PATH`: path to the scanner's `bot_state.json`.

## Deployment requirement
Run `python telegram_super_bot.py` as a persistent worker on a host that supports
long-running Python processes. The scanner and worker must share a durable,
refreshed state file. GitHub Actions runners are ephemeral: writing the snapshot
during a workflow does not automatically make it visible to a separately hosted
worker. Configure an authenticated artifact/object-storage sync or another
secure state bridge before expecting live command data. Create a separate bot
with BotFather; do not reuse or disclose the existing bot token.
