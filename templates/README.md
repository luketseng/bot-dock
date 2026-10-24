# 專案接入模板與快速安裝

所有情境共用一支 `botdock_app.py` 與一份 `botdock.json`。不需要安裝 BotDock Python 套件；純通知只使用 Python 3.10+ 標準函式庫，互動服務才需要 FastAPI、Uvicorn。

要由代理引導安裝，請使用 [INSTALL_SOP](../INSTALL_SOP.md)：它會先詢問「通知／互動／兩者」，再完成接入與驗證，最後更新目標專案 README。可以直接說：

```text
請依 /home/zane/git/bot-dock/INSTALL_SOP.md 安裝，目標專案是 [絕對路徑]。
```

BotDock repo 位於其他位置時，請替換提示詞中的路徑。

## 1. 選擇情境

| 情境 | 目標專案執行方式 | BotDock 端設定片段 | 額外依賴 |
|---|---|---|---|
| 純通知 | 腳本、排程或 CI 呼叫 `send()` 或 CLI | `bot-dock.notification.fragment.json` | 無 |
| 純互動 | 常駐 callback，接收 Telegram 指令並回傳查詢結果 | `bot-dock.interactive.fragment.json` | FastAPI、Uvicorn |
| 通知＋互動 | 排程發通知，同時執行常駐 callback | `bot-dock.interactive.fragment.json` | FastAPI、Uvicorn |

純互動與通知＋互動使用相同 BotDock 設定；差別在目標專案是否呼叫通知功能。不需要複製第二份 Python。

## 2. 檔案各放哪裡

| 模板檔案 | 放置端與正式名稱 | 用途 |
|---|---|---|
| `botdock_app.py` | 目標專案，原名 | 通知 client、CLI 與 callback factory |
| `botdock.example.json` | 目標專案，改名 `botdock.json` | URL、路由 ID、環境變數名稱與 callback 權限 |
| `.env.example` | 目標專案，改名 `.botdock.env` | 目標專案使用的真實金鑰 |
| `bot-dock.notification.fragment.json` | 合併進 BotDock 的 `bot-dock.json` | 純通知專案註冊 |
| `bot-dock.interactive.fragment.json` | 合併進 BotDock 的 `bot-dock.json` | 含互動專案註冊，也可主動通知 |
| `.env.botdock.example` | 合併進 BotDock 的 `.env` | Telegram token、通知 key、callback key |

**fragment 是 BotDock 端的設定片段，不是目標專案設定，也不要直接覆蓋既有 `bot-dock.json`。** `*.example.json` 才是給目標專案複製的設定範本。兩端的正式設定可能同名，請用完整路徑辨識。

JSON 只存環境變數名稱，真實值放 env 或現有 secret manager。目標專案不需要 Telegram token。

## 3. 安裝前準備

確認以下資訊；不知道的欄位可交由文末提示詞協助盤點：

- BotDock repo 與目標專案的絕對路徑。
- 使用情境、唯一 `project_id`、唯一 `bot_id`，以及環境變數前綴，例如 `MYPROJECT`。
- 從目標專案可連線的 BotDock URL，範例 `http://127.0.0.1:8090`。
- Telegram bot token、收件 chat ID、允許使用者的 user ID；chat ID 與 user ID 可能不同，群組 chat ID 也可能是負數。
- 含互動時：從 BotDock 可連線的 callback URL，以及目標專案要提供的查詢指令。
- 排程或服務由誰管理，例如既有 systemd user service、cron、CI 或容器。

範例 callback port 為 `8092`，請先檢查是否被占用。不同專案應配置不同 port。`127.0.0.1` 只適用於兩端在相同主機網路環境；分機或容器必須調整 URL、監聽位址及網路存取設定。

## 4. 複製共用模板到目標專案

以下從 BotDock repo 執行。先把 `/path/to/project` 換成目標專案的既有目錄，確認沒有同名檔案再複製；若已有接入設定，應更新或合併，而非覆寫。

```bash
cp templates/botdock_app.py /path/to/project/
cp templates/botdock.example.json /path/to/project/botdock.json
cp templates/.env.example /path/to/project/.botdock.env
chmod 600 /path/to/project/.botdock.env
```

將 `.botdock.env` 加入目標專案 `.gitignore`。以下是共用 JSON 的欄位說明：

| 欄位 | 通知 | 互動 | 填寫方式 |
|---|---|---|---|
| `base_url` | 必填 | 不使用 | BotDock URL，不含 `/v1/messages` |
| `project_id` | 必填 | 不使用 | 對應 BotDock `projects` 的 ID |
| `bot_id` | 必填 | 必填 | 對應 BotDock `bots` 的 ID |
| `destination_id` | 必填 | 不使用 | 對應 BotDock `destinations` 的名稱，預設 `owner` |
| `api_key_env` | 必填 | 不使用 | 通知 key 的環境變數名稱 |
| `timeout_seconds` | 選填 | 不使用 | 通知 HTTP timeout，預設 20 秒 |
| `callback_key_env` | 不使用 | 必填 | callback key 的環境變數名稱 |
| `allowed_chat_ids` | 不使用 | 必填 | callback 可接受的 chat ID，與 BotDock 同步 |
| `allowed_user_ids` | 不使用 | 選填 | callback 可接受的 user ID；空清單不限制 user，仍檢查 chat |

可以保留目前情境不使用的 JSON 欄位；不會啟動額外功能。純通知可從 `.botdock.env` 移除 callback key；純互動可移除通知 key。通知與 callback 各自只檢查自己需要的設定。

Python 不會自行載入 env 檔。手動執行時，在目標專案目錄載入：

```bash
set -a
. ./.botdock.env
set +a
```

只載入可信任的 env 檔。常駐或排程部署請用既有服務環境載入機制，不要假設它會繼承目前終端的環境。systemd 可使用指向絕對路徑的 `EnvironmentFile=`。

## 5. 在 BotDock 註冊專案

1. 依情境選擇通知或互動 fragment，將 `projects`、`bots` 中的新項目合併進既有 `bot-dock.json`，保留其他專案及全域設定。只選一份片段，不要把兩份同 ID 範例一起合併。
2. 將 `my-project`、`my-bot` 改成唯一 ID，並同步修改目標專案 JSON。通知的 `destination_id` 必須對應 `destinations` 中的名稱。
3. 將 `MYPROJECT_*` 改為專案專用環境變數名稱；依 `.env.botdock.example` 將需要的變數合併到 BotDock `.env`，不要覆蓋其他變數。
4. Telegram token 只放 BotDock。通知 key 在兩端必須相同；callback key 在兩端也必須相同，且與通知 key 使用不同值。可用 `openssl rand -hex 32` 分別產生，透過安全管道填入，勿貼進提示詞、日誌或版本控制。
5. 替換 `destinations`、`allowed_chat_ids`、`allowed_user_ids` 的範例 ID。互動的允許清單與目標專案 JSON 同步。
6. 含互動時修改 `callback_url`，啟動 callback 後再重啟 BotDock。純通知直接重啟 BotDock。

純通知片段設定 `receive_updates: false`，不接收 Telegram 指令，也不註冊指令選單。含互動片段為 `true`，並配置 callback、`/status`、`/help` 與 `/start` alias；alias 由 BotDock 轉換成正式指令再轉送。

純互動仍需在 **BotDock 端**設定 `api_key_env`、對應通知 key 與 `destinations`，因為目前設定模型要求這些欄位；目標專案不用呼叫或配置通知功能。

若這套部署使用既有的 systemd user service：

```bash
systemctl --user restart botdock.service
systemctl --user status botdock.service
```

若服務名稱或部署方式不同，使用現有啟動方式。每個 Telegram token 只能有一個 polling 程序；目標專案不需要接收 Telegram updates。

## 6. 情境 A：純通知

在目標專案載入環境變數後執行；**此命令會實際發送訊息**：

```bash
python3 botdock_app.py '排程執行完成'
```

既有 Python 程式可以引用：

```python
from botdock_app import BotDockClient

client = BotDockClient()
result = client.send("排程執行完成")
print(result["message_id"])
```

預設設定路徑是 `botdock_app.py` 旁的 `botdock.json`，不依賴目前工作目錄。可用 `BOTDOCK_CONFIG` 改路徑，或在程式使用 `BotDockClient("/absolute/path/botdock.json")`。CLI 也支援：

```bash
python3 botdock_app.py --config /absolute/path/botdock.json '排程執行完成'
```

排程請使用 Python、程式、設定與 env 的絕對路徑，並確保啟動環境有載入通知 key。此情境不需要安裝 FastAPI、Uvicorn，不需要常駐 callback，也不需要開 callback port。

## 7. 情境 B：純互動

在目標專案既有虛擬環境中安裝依賴；若專案已有 dependency manifest，請同時記錄相容依賴，不要只裝在臨時環境：

```bash
python3 -m pip install 'fastapi>=0.115,<1' 'uvicorn>=0.30,<1'
```

載入 `.botdock.env` 後，從目標專案目錄啟動：

```bash
python3 -m uvicorn botdock_app:create_app --factory --host 127.0.0.1 --port 8092
```

此程序需要持續執行。正式部署用目標專案現有服務管理方式，指定工作目錄、虛擬環境 Python 與 env 檔；不要僅依靠終端背景程序。設定 `BOTDOCK_CONFIG` 可改 callback 的設定路徑。

在 `botdock_app.py` 的 `create_app()` 裡修改 `/status` 分支，換成專案實際的唯讀查詢。範例文字 `Project callback is ready.` 只代表接入成功。

新增指令時，同時新增 callback handler 與 BotDock `projects.<id>.routes`，再重啟兩端。當前 callback 介面只傳指令名稱，不提供指令參數；不要直接設計需要 `/query 123` 的流程。

callback 必須在 15 秒內回傳 `{"text": "..."}`，可另帶 `parse_mode`。BotDock 會發送回覆，handler 不要再呼叫 `send()`，否則會重複回覆。耗時工作可先回覆已受理，再以通知功能回報完成；這時就屬於情境 C。

callback 啟動並重啟 BotDock 後，在 Telegram 輸入 `/` 確認指令選單，再執行 `/status` 與 `/help`。請從 BotDock 所在的網路環境確認 callback 可連線；未帶正確 key 的直接 HTTP 請求應被拒絕。

## 8. 情境 C：通知＋互動

完成情境 B 的 callback 部署，並設定情境 A 的通知欄位與通知 key。兩者共用同一支 Python、同一份 JSON，但通知與 callback 使用不同金鑰。

- 常駐服務執行 `uvicorn botdock_app:create_app --factory ...`。
- 排程或背景工作引用 `BotDockClient().send(...)`，或執行通知 CLI。
- 互動 handler 直接回傳查詢結果，由 BotDock 回覆。

不需要另外複製 client 或 callback 檔案；CLI 發送完即退出，不會自動啟動互動服務。

## 9. 驗證與排錯

先做不發訊息的檢查，再依情境執行真實驗收：

```bash
python3 -m json.tool botdock.json > /dev/null
python3 botdock_app.py --help
```

| 檢查項目 | 預期結果 |
|---|---|
| BotDock 合併設定 | 既有專案保留，新 project、bot ID 無衝突 |
| 通知驗收（A、C） | 指定聊天收到一則測試訊息，CLI 回傳 `ok: true` 與 `message_id` |
| 互動驗收（B、C） | `/status` 與 `/help` 有回覆且不重複 |
| 權限 | 未授權 chat/user 被拒絕，callback 無正確 key 時回 401 |
| 持續運行 | 關閉安裝終端後，排程及 callback 仍由服務管理器正常啟動 |
| 金鑰保護 | env 不被 Git 追蹤，權限為 `0600`，日誌及報告不含金鑰 |

通知常見錯誤：401 是 key 不符；403 是 project、bot 或收件設定不符；422 是輸入不合法；429 是限流；502 是 Telegram 發送失敗。callback 回 403 時檢查 bot ID 與兩端允許清單。選單沒出現時檢查 `receive_updates`、routes、BotDock 重啟結果及 token 是否有其他 polling 程序。

`send()` 成功回傳 `{"ok": true, "message_id": ...}`。HTTP 錯誤拋出 `urllib.error.HTTPError`，連線或逾時會拋出相應例外，CLI 以非零狀態退出。不會自動重送，因為逾時時訊息可能已送達。

通知與互動回覆文字限制為 1–4096 字元，預設純文字。使用 `HTML` 或 `MarkdownV2` 時，呼叫端須自行跳脫動態內容。

## 10. 可直接複製的 setup 提示詞

在可以讀取 BotDock repo 與目標專案的代理工作階段使用。將方括號換成實際資訊；金鑰請放安全的 env 或 secret manager，不要填進提示詞。若代理無法寫入其中一個專案，請讓它產出該端精確的待合併內容與操作步驟。

### 共用 setup 提示詞

複製以下內容，再接上後面的 A、B 或 C 情境補充：

```text
請協助完成 BotDock 接入，直接實作必要檔案與設定，並依 README 驗證。
先閱讀兩端 AGENTS.md，以及 [BotDock repo 絕對路徑]/templates/README.md。

BotDock repo：[絕對路徑]
目標專案：[絕對路徑]
情境：[A 純通知 / B 純互動 / C 通知＋互動]
project_id：[唯一 ID]
bot_id：[唯一 ID]
環境變數前綴：[例如 MYPROJECT]
BotDock URL：[從目標專案可連線的 URL]
destination_id：[例如 owner]
Telegram chat ID：[實際 ID]
允許的 user ID：[實際 ID 清單]
callback URL 與監聽位址：[B/C 必填，A 不適用]
Python 環境與部署方式：[既有 venv、systemd/cron/CI/容器；未知請先檢查]
真實發送測試與服務重啟：[允許 / 先完成設定並列出待執行命令]

請先檢查現有專案結構、接入設定、服務和 port，沿用既有部署慣例。
統一使用 templates/botdock_app.py 與 botdock.example.json；
目標專案正式名稱為 botdock_app.py、botdock.json、.botdock.env。
依情境僅選一份 BotDock fragment，合併 projects、bots，保留既有設定。
同步 ID、環境變數名稱與互動允許清單，不要遺留範例 ID 或 placeholder。
真實金鑰透過現有安全機制配置；不要讀出或回報金鑰值。
若缺必要資訊，先完成可獨立完成的工作，再集中詢問缺項，不要猜測。
加入 env 的 Git 忽略規則並限制權限，依現有方式配置啟動環境。
不要增加不相關功能，不要覆蓋既有檔案或建立重複 polling 程序。
先執行本地靜態檢查；依上方授權範圍進行服務重啟與真實驗收。
最後列出修改檔案、啟動方式、驗證結果及尚需人工完成的項目。
```

### A：純通知補充

```text
我只需要純通知，不部署 callback、不安裝 FastAPI/Uvicorn。
使用 bot-dock.notification.fragment.json，receive_updates 必須為 false。
通知觸發點：[例如既有每日排程完成或失敗時]
通知內容：[需要的摘要]
請沿用既有腳本的錯誤處理，不要讓通知失敗掩蓋原始任務錯誤。
只配置通知所需的金鑰與執行環境，驗證 CLI 或程式引用方式。
```

### B：純互動補充

```text
我只需要互動查詢，使用 bot-dock.interactive.fragment.json。
需要指令：[例如 /status 查詢最近一次執行結果、/help 顯示說明]
資料來源：[現有檔案、函式或 API；未知請先盤點]
請實作唯讀查詢，確保 15 秒內回傳；不要假設可接收指令參數。
回覆由 callback 回傳，再交給 BotDock 發送，不要另呼叫通知 client。
在目標專案既有依賴管理中加入 callback 依賴，配置常駐服務與 env 載入。
BotDock 端仍依設定模型配置通知 key 與 destinations；目標專案不使用通知 key。
```

### C：通知＋互動補充

```text
我需要通知＋互動，使用 bot-dock.interactive.fragment.json。
通知觸發點與內容：[例如每日任務完成後發送摘要]
互動指令與資料來源：[例如 /status 讀取最近一次結果、/help 顯示說明]
同一支 botdock_app.py 同時供排程引用及 callback 服務使用。
通知與 callback 使用不同金鑰，同步兩端設定。
配置常駐 callback 與既有排程，不要在每次發通知時啟動 callback。
分別驗證通知與指令查詢，確認互動回覆只有一則。
```
