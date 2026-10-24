"""Copy into a project and replace the example query handlers."""
import hmac
import json
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


class Query(BaseModel):
    command: str
    bot_id: str
    chat_id: int
    user_id: int | None = None


def create_app():
    config_path = os.environ.get(
        "BOTDOCK_CALLBACK_CONFIG", str(Path(__file__).with_name("botdock_callback.json")))
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
