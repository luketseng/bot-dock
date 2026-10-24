# BotDock

以 aiogram 與 FastAPI 建立的共用 Telegram 通訊服務。各專案透過 HTTP 發送通知；互動 bot 將指令與按鈕查詢轉交給專案 API。

[English](README.md)

## 環境需求

- Python 3.10+ 與 [uv](https://docs.astral.sh/uv/)，可連線至 PyPI 與 Telegram。
- 以下部署方式需要 Linux 與使用者 systemd 服務。
- 每個 bot 的 Telegram token 與允許使用的 chat ID。

## 部署

```bash
cd ~/git/bot-dock
uv venv .venv
uv pip install --python .venv/bin/python -e '.[test]'
```

首次安裝時，將 `bot-dock.example.json` 複製為 `bot-dock.json`，填入實際 ID 與 callback URL，再將 `.env.example` 複製為 `.env`，填入自己的秘密值。更新既有部署時保留原設定。

| 設定檔 | 用途 |
|---|---|
| `bot-dock.json` | 專案、bot、收件對象、權限、指令與按鈕 |
| `.env` | Bot token、各專案通知 API key 與 callback key |
| `../TX_Predictor/botdock_client.json` | TX 通知網址、API key 與路由 ID |
| `../TX_Predictor/.botdock-project.env` | TX 查詢 API 的驗證金鑰 |
| `../no_ip_renew/.env` | No-IP 登入資訊與 BotDock 通知設定 |

秘密設定不提交 Git，檔案權限設為 `0600`。每個專案使用獨立 API key；通知金鑰需在專案與 BotDock 配對，callback 金鑰需在 BotDock 與專案查詢 API 配對。

現有 service 檔使用 `/home/zane/git`；部署至其他主機時須調整路徑。目前 TX + No-IP 的部署方式：

```bash
systemctl --user link "$PWD/deploy/botdock.service" "$PWD/deploy/tx-predictor-botdock.service"
systemctl --user daemon-reload
systemctl --user enable --now tx-predictor-botdock.service botdock.service
```

BotDock 監聽 localhost:8090，TX 查詢 API 監聽 localhost:8091。No-IP 不需額外 port 或常駐 service。使用者服務隨使用者工作階段啟動；若要無人登入也隨開機啟動，須啟用使用者 lingering。

前景除錯時，先停止 BotDock service，再執行：

```bash
.venv/bin/python -m bot_dock --config bot-dock.json --env-file .env
```

每個收訊 bot token 只能有一個 polling 程序，且不能有既存 webhook。使用單一程序，不開 reload 或多 workers。啟動時會驗證 bot 憑證。修改 BotDock 設定後重啟服務；修改 TX callback key 時，TX 查詢 API 也須重啟。

## 資料交換

```text
TX:    run_daily.py -> notify_telegram.py ----> BotDock:8090 -> TX bot
No-IP: run.sh -> notify_botdock.py -----------> BotDock:8090 -> No-IP bot

Telegram 指令／按鈕 -> BotDock -> TX API:8091
                                 -> project_queries.py -> 查詢結果 -> BotDock -> Telegram
```

**發送通知：**使用專案 API key 呼叫 `POST /v1/messages`：

```bash
curl --fail-with-body http://127.0.0.1:8090/v1/messages \
  -H "Authorization: Bearer $BOTDOCK_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"no-ip-renew","bot_id":"no-ip","destination_id":"owner","text":"Job completed"}'
```

成功回傳 `{"ok":true,"message_id":123}`。文字上限為 4096 字元，省略 `parse_mode` 即使用純文字。錯誤碼：401 憑證錯誤、403 bot／收件權限不足、422 輸入錯誤、429 限流（附 `Retry-After`）、502 Telegram 呼叫失敗。逾時後可能已送出；BotDock 沒有持久佇列或自動發送重試。

**互動查詢：**設定 `callback_url`、`callback_key_env` 與 `routes`。BotDock 以附帶驗證的 POST 傳送 `command`、`bot_id`、`chat_id`、`user_id`；專案回傳 `{"text":"Result","parse_mode":"HTML"}`。資料讀取與 HTML 跳脫由專案負責。請求須符合 chat 白名單；若另有 user 白名單，也須同時符合。

**只發通知：**專案設定 `api_key_env`，對應 bot 設為 `receive_updates: false`，不需 callback 或查詢 service。No-IP 採用此模式。

**指令選單：**每個 route 可設定 `description`（1–256 字元）。BotDock 啟動時會以專案 routes 覆寫接收互動訊息之 bot 的 Telegram 預設指令選單，不列出 aliases；未填說明時使用指令本身。空 routes 會清除預設選單。修改 JSON 後重啟 BotDock 即可同步，TX 不需修改或重啟。其他地方設定的語言或聊天室專用選單不會被覆寫。Telegram 同步失敗時啟動會失敗。

## Service 除錯與測試

```bash
systemctl --user status botdock.service tx-predictor-botdock.service
journalctl --user -u botdock.service -u tx-predictor-botdock.service -n 50 --no-pager
curl --fail http://127.0.0.1:8090/health
.venv/bin/python -m pytest tests -q
```

單元測試模擬 Telegram，不發送真實訊息。`/health` 檢查 polling 任務，不保證每個 bot 持續連線。出現 `getUpdates` 衝突時，表示另一個程序也在使用相同 token 收訊。

目前部署可先連結選用的驗證 service，再執行整合驗證：

```bash
systemctl --user link "$PWD/deploy/botdock-verify.service" "$PWD/deploy/no-ip-botdock-verify.service"
systemctl --user daemon-reload
systemctl --user start botdock-verify.service
systemctl --user start no-ip-botdock-verify.service
journalctl --user -u botdock-verify.service -u no-ip-botdock-verify.service -n 50 --no-pager
```

這些手動驗證會執行測試並**發送真實 Telegram 測試通知**；TX 驗證也會檢查查詢 API，不會執行 No-IP 續約。成功的 oneshot service 會回到 `inactive`，且 `ExecMainStatus=0`。

## 其他專案快速接入

請參考 [接入模板](templates/README.md)，提供純通知、純互動查詢及通知＋互動三款 JSON／Python 範例與兩端設定步驟。

| 放置端 | 檔案 | 用途 |
|---|---|---|
| 目標專案 | `botdock_client.py`、`botdock_client.json` | 主動通知 |
| 目標專案 | `callback_app.py`、`botdock_callback.json` | 互動查詢 |
| 目標專案 | `.botdock.env` | 專案 API key；加入該專案 `.gitignore`，限制權限為 `0600` |
| BotDock | `bot-dock.json` | 合併模板的 `bot-dock.fragment.json`，保留其他專案 |
| BotDock | `.env` | 合併 `.env.botdock.example` 的變數與真實 key |

JSON 只保存環境變數名稱，真實 key 放 env 檔。依使用的款式複製對應 Python 與 JSON；純通知不需 callback。
