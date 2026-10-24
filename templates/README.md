# 專案接入模板

這些檔案供其他專案複製使用，不需要安裝 BotDock Python 套件。

| 模板 | 用途 | 專案端 Python |
|---|---|---|
| `notification/` | 排程、CI、腳本主動發送通知 | `botdock_client.py` |
| `interactive/` | 使用者輸入 Telegram 指令，專案查詢後回覆 | `callback_app.py` |
| `combined/` | 主動通知＋互動查詢 | 以上兩個檔案 |

互動查詢的回覆由 callback 回傳，再由 BotDock 發送；不需要再呼叫通知 client，否則會重複回覆。目前介面只傳指令名稱，不傳指令參數。

## 檔案放置位置

| 放置端 | 檔案 | 用途 |
|---|---|---|
| 目標專案 | `botdock_client.py`、`botdock_client.json` | 純通知或通知＋互動：主動發送訊息 |
| 目標專案 | `callback_app.py`、`botdock_callback.json` | 純互動或通知＋互動：處理指令查詢 |
| 目標專案 | `.botdock.env` | 專案 API key；加入該專案 `.gitignore`，限制權限為 `0600` |
| BotDock | `bot-dock.json` | 合併所選模板的 `bot-dock.fragment.json`，保留既有專案 |
| BotDock | `.env` | 合併 `.env.botdock.example` 的變數，包含 Telegram token 與對應 key |

JSON 只保存環境變數名稱，真實 key 放 env 檔。`*.example.json` 複製到目標專案後移除 `.example`；`.env.example` 在目標專案命名為 `.botdock.env`。載入環境變數與執行方式見下方步驟。

## 1. 在專案端複製檔案

以下命令從 BotDock repo 執行。將 `/path/to/project` 改為目標專案的既有目錄；先確認沒有同名設定，避免覆寫。

純通知：

```bash
cp templates/botdock_client.py /path/to/project/
cp templates/notification/botdock_client.example.json /path/to/project/botdock_client.json
cp templates/notification/.env.example /path/to/project/.botdock.env
```

純互動：

```bash
cp templates/callback_app.py /path/to/project/
cp templates/interactive/botdock_callback.example.json /path/to/project/botdock_callback.json
cp templates/interactive/.env.example /path/to/project/.botdock.env
```

通知＋互動：

```bash
cp templates/botdock_client.py templates/callback_app.py /path/to/project/
cp templates/combined/botdock_client.example.json /path/to/project/botdock_client.json
cp templates/combined/botdock_callback.example.json /path/to/project/botdock_callback.json
cp templates/combined/.env.example /path/to/project/.botdock.env
```

修改 JSON 的 URL、專案／bot ID 與收件設定。JSON 只保存環境變數名稱；在 `.botdock.env` 填入真實 key，並將此檔加入目標專案的 `.gitignore`，限制權限為 `0600`。Python 通知 client 不會自行讀取 env 檔，由啟動環境載入。

## 2. 在 BotDock 端合併設定

1. 將所選模板的 `bot-dock.fragment.json` 中 `projects`、`bots` 項目合併進既有 `bot-dock.json`，保留其他專案。
2. 將該模板的 `.env.botdock.example` 變數加入 BotDock 的 `.env` 並填入真實值。
3. 將 `my-project`、`my-bot` 改成唯一 ID；通知 client 與 callback 設定必須同步修改。將所有 `123456789` 改成實際 chat／user ID；兩者可能不同。
4. 通知 API key 在專案端與 BotDock 端必須一致；callback key 也必須一致，且使用不同於通知 key 的值。Telegram token 只需放在 BotDock。
5. 互動款的 `callback_url` 必須從 BotDock 主機可連線。預設 `8092` 是範例，與現有 TX 的 `8091` 分開；多個新專案應分配不同 port。分機或容器部署需調整 URL、監聽介面與網路存取設定。
6. 啟動 callback 後重啟 BotDock；純通知款可直接重啟 BotDock。每個 token 只能由一個程序 polling，目標專案不需自己接收 Telegram updates。

純互動款仍需在 BotDock 設定 `api_key_env` 與 `destinations`，因為目前設定模型要求這些欄位；專案端不必使用通知 client。純通知款不啟動 callback、不註冊指令選單。

```bash
systemctl --user restart botdock.service
```

## 3. 純通知：執行與引用

以下從目標專案目錄執行，Python 3.10+ 即可，不需額外套件。命令會實際發送 Telegram 訊息。

```bash
set -a
. ./.botdock.env
set +a
python3 botdock_client.py '排程執行完成'
```

也可從既有程式呼叫：

```python
from pathlib import Path
from botdock_client import BotDockClient

client = BotDockClient(Path(__file__).with_name("botdock_client.json"))
result = client.send("排程執行完成")
print(result["message_id"])
```

`send()` 成功回傳 `{"ok": true, "message_id": ...}`；HTTP 錯誤會拋出 `urllib.error.HTTPError`，連線失敗或逾時會拋出相應例外，CLI 則以非零狀態退出。常見 HTTP 狀態：401 key 錯誤、403 專案／bot／收件設定不符、422 輸入不合法、429 限流、502 Telegram 發送失敗。模板不自動重送，因為逾時時可能已成功送出。

預設純文字，長度限制 1–4096 字元。若使用 `parse_mode="HTML"` 或 `"MarkdownV2"`，呼叫端必須自行跳脫動態內容。

## 4. 純互動：啟動 callback

在目標專案的虛擬環境安裝並啟動：

```bash
python3 -m pip install 'fastapi>=0.115,<1' 'uvicorn>=0.30,<1'
set -a
. ./.botdock.env
set +a
python3 -m uvicorn callback_app:create_app --factory --host 127.0.0.1 --port 8092
```

callback 預設讀取 Python 檔案旁的 `botdock_callback.json`；可透過 `BOTDOCK_CALLBACK_CONFIG` 指定其他路徑。常駐部署時請用目標專案既有的服務管理方式載入環境變數及啟動此命令。

在 `callback_app.py` 的 `/status` handler 換上專案實際查詢；新增指令時，同時更新 callback handler 與 BotDock routes，再重啟兩端服務。callback 必須在 15 秒內回傳 `{"text": "..."}`，可選 `parse_mode`，文字限制與通知相同。耗時任務應立即回覆已受理，再用通知款 client 主動回報結果。

重啟 BotDock 後，在 Telegram 輸入 `/` 確認選單，再執行 `/status`。範例回傳「Project callback is ready.」只代表接入成功，請換成專案本身的狀態。

## 5. 通知＋互動

依序完成通知與互動步驟，使用同一組 project／bot ID。callback 回傳即時查詢結果，排程或背景工作透過 `BotDockClient.send()` 發送主動通知。
