# BotDock

A shared Telegram gateway built with aiogram and FastAPI. Projects send notifications over HTTP; interactive bots forward commands and buttons to project APIs.

[繁體中文](README-zh-TW.md)

## Requirements

- Python 3.10+ and [uv](https://docs.astral.sh/uv/), with access to PyPI and Telegram.
- Linux with user systemd services for the deployment below.
- A Telegram bot token and permitted chat IDs for each bot.

## Deployment

```bash
cd ~/git/bot-dock
uv venv .venv
uv pip install --python .venv/bin/python -e '.[test]'
```

For a new installation, copy `bot-dock.example.json` to `bot-dock.json`, set real IDs and callback URLs, and copy `.env.example` to `.env` with your own secret values. Keep existing settings when updating.

| Configuration | Purpose |
|---|---|
| `bot-dock.json` | Projects, bots, destinations, access rules, commands and buttons |
| `.env` | Bot tokens, project notification API keys and callback keys |
| `../TX_Predictor/botdock_client.json` | TX notification URL, API key and routing IDs |
| `../TX_Predictor/.botdock-project.env` | TX callback authentication key |
| `../no_ip_renew/.env` | No-IP credentials and BotDock notification settings |

Keep secret files out of Git and restrict their permissions to `0600`. Give each project its own API key. Notification keys must match between the project and BotDock; callback keys must match between BotDock and the project API.

The supplied service files use `/home/zane/git`; adjust paths for other hosts. For the current TX + No-IP deployment:

```bash
systemctl --user link "$PWD/deploy/botdock.service" "$PWD/deploy/tx-predictor-botdock.service"
systemctl --user daemon-reload
systemctl --user enable --now tx-predictor-botdock.service botdock.service
```

BotDock listens on localhost:8090; the TX query API listens on localhost:8091. No-IP needs no additional port or persistent service. User services start with the user session; unattended boot requires user lingering.

For foreground debugging, stop the BotDock service first, then run:

```bash
.venv/bin/python -m bot_dock --config bot-dock.json --env-file .env
```

Each receiving bot token must have one polling owner, with no existing webhook. Use one process without reload or multiple workers. Startup validates bot credentials. Restart BotDock after changing its settings; restart the TX API too when changing its callback key.

## Data exchange

For copyable Python clients and JSON configuration, see the [integration templates](templates/README.md): notification-only, interactive-only, and combined projects.

| Location | Files | Purpose |
|---|---|---|
| Target project | `botdock_client.py`, `botdock_client.json` | Send notifications |
| Target project | `callback_app.py`, `botdock_callback.json` | Handle interactive queries |
| Target project | `.botdock.env` | Project API keys; exclude from Git and restrict to `0600` |
| BotDock | `bot-dock.json` | Merge template `bot-dock.fragment.json` entries, keeping existing projects |
| BotDock | `.env` | Merge variables from `.env.botdock.example` and set real keys |

JSON stores environment variable names; env files store actual keys. Copy only the Python and JSON files needed for your mode; notification-only projects need no callback.

```text
TX:    run_daily.py -> notify_telegram.py ----> BotDock:8090 -> TX bot
No-IP: run.sh -> notify_botdock.py -----------> BotDock:8090 -> No-IP bot

Telegram command/button -> BotDock -> TX API:8091
                                      -> project_queries.py -> reply -> BotDock -> Telegram
```

**Notifications:** `POST /v1/messages`, authenticated with the project's API key:

```bash
curl --fail-with-body http://127.0.0.1:8090/v1/messages \
  -H "Authorization: Bearer $BOTDOCK_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"no-ip-renew","bot_id":"no-ip","destination_id":"owner","text":"Job completed"}'
```

Success returns `{"ok":true,"message_id":123}`. Text is limited to 4096 characters; omit `parse_mode` for plain text. Errors: 401 credentials, 403 bot/destination permission, 422 invalid input, 429 rate limit (`Retry-After`), 502 Telegram failure. Delivery can be uncertain after a timeout; BotDock has no persistent queue or automatic delivery retries.

**Interactive queries:** configure `callback_url`, `callback_key_env` and `routes`. BotDock sends an authenticated POST with `command`, `bot_id`, `chat_id` and `user_id`; the project returns `{"text":"Result","parse_mode":"HTML"}`. The project owns data access and HTML escaping. Chat allowlists apply; configured user allowlists must also match.

**Command menu:** each route accepts an optional `description` (1–256 characters). At startup, BotDock replaces each receiving bot's default Telegram command menu with its project routes; aliases are excluded. Without a description, the command itself is used. An empty route list clears the default menu. Restart BotDock after editing JSON to sync changes; TX needs no changes or restart. Existing language-specific or chat-specific menus configured elsewhere are not replaced. Telegram sync failures fail startup.

**Notification-only projects:** set `api_key_env` on the project and `receive_updates: false` on its bot. No callback or query service is required. No-IP uses this mode.

## Service debugging and testing

```bash
systemctl --user status botdock.service tx-predictor-botdock.service
journalctl --user -u botdock.service -u tx-predictor-botdock.service -n 50 --no-pager
curl --fail http://127.0.0.1:8090/health
.venv/bin/python -m pytest tests -q
```

Unit tests mock Telegram and send no real messages. `/health` checks the polling task, not continuous connectivity to every bot. A `getUpdates` conflict means another process is receiving updates with the same token.

For the current deployment, link the optional verification services once:

```bash
systemctl --user link "$PWD/deploy/botdock-verify.service" "$PWD/deploy/no-ip-botdock-verify.service"
systemctl --user daemon-reload
systemctl --user start botdock-verify.service
systemctl --user start no-ip-botdock-verify.service
journalctl --user -u botdock-verify.service -u no-ip-botdock-verify.service -n 50 --no-pager
```

These manual checks run tests and **send real Telegram test notifications**; the TX check also exercises query APIs. They do not run No-IP renewal. Successful oneshot services return to `inactive` with `ExecMainStatus=0`.
