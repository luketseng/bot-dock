"""Copy into a project for notifications and interactive queries."""
import argparse
import hmac
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen



def default_config_path():
    return os.environ.get("BOTDOCK_CONFIG", str(Path(__file__).with_name("botdock.json")))


class BotDockClient:
    def __init__(self, config_path=None):
        self.config = json.loads(Path(config_path or default_config_path()).read_text(encoding="utf-8"))

    def send(self, text, *, parse_mode=None):
        if not isinstance(text, str) or not 1 <= len(text) <= 4096:
            raise ValueError("text must contain 1 to 4096 characters")
        if parse_mode not in (None, "HTML", "MarkdownV2"):
            raise ValueError("Unsupported parse_mode")
        key_name = self.config["api_key_env"]
        key = os.environ.get(key_name, "").strip()
        if not key:
            raise ValueError(f"Missing environment variable: {key_name}")
        payload = {name: self.config[name]
                   for name in ("project_id", "bot_id", "destination_id")}
        payload.update(text=text, parse_mode=parse_mode)
        request = Request(
            self.config["base_url"].rstrip("/") + "/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        # Do not retry automatically: a timeout may follow successful delivery.
        with urlopen(request, timeout=self.config.get("timeout_seconds", 20)) as response:
            result = json.load(response)
        if result.get("ok") is not True or not isinstance(result.get("message_id"), int):
            raise ValueError("Invalid BotDock response")
        return result


def main():
    parser = argparse.ArgumentParser(description="Send a BotDock notification")
    parser.add_argument("text")
    parser.add_argument("--config", default=default_config_path())
    parser.add_argument("--parse-mode", choices=["HTML", "MarkdownV2"])
    args = parser.parse_args()
    try:
        result = BotDockClient(args.config).send(args.text, parse_mode=args.parse_mode)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"BotDock notification failed: {error}\n")
    print(json.dumps(result))


def create_app():
    # Import callback dependencies only when starting the interactive service.
    from fastapi import FastAPI, Header, HTTPException
    from pydantic import BaseModel

    class Query(BaseModel):
        command: str
        bot_id: str
        chat_id: int
        user_id: int | None = None

    config_path = default_config_path()
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    key_name = config["callback_key_env"]
    key = os.environ.get(key_name, "").strip()
    if not key:
        raise ValueError(f"Missing environment variable: {key_name}")
    app = FastAPI(title="Project BotDock callback")

    @app.post("/botdock/query")
    def query(body: Query, authorization: str = Header(default="")):
        if not hmac.compare_digest(authorization.encode(), f"Bearer {key}".encode()):
            raise HTTPException(401, "Invalid credentials")
        if body.bot_id != config["bot_id"] or body.chat_id not in config["allowed_chat_ids"]:
            raise HTTPException(403, "Query not permitted")
        users = config.get("allowed_user_ids", [])
        if users and body.user_id not in users:
            raise HTTPException(403, "Query not permitted")
        # Replace these replies with project queries that finish within 15 seconds.
        if body.command == "/status":
            return {"text": "Project callback is ready."}
        if body.command == "/help":
            return {"text": "/status — project status\n/help — command help"}
        raise HTTPException(400, "Unknown command")

    return app


if __name__ == "__main__":
    main()
