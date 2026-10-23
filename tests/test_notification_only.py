from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from bot_dock.app import create_app
from bot_dock.config import Settings


def test_notification_only_project_needs_no_callback_or_polling(monkeypatch):
    monkeypatch.setenv("NOIP_KEY", "noip-test-key")
    settings = Settings.model_validate({"projects": {"no-ip": {"api_key_env": "NOIP_KEY"}},
        "bots": {"no-ip": {"token_env": "UNUSED", "project_id": "no-ip", "receive_updates": False,
            "destinations": {"owner": 42}, "allowed_chat_ids": [42]}}})
    bot = SimpleNamespace(token="test-token", get_me=AsyncMock(), get_webhook_info=AsyncMock(),
                          send_message=AsyncMock(return_value=SimpleNamespace(message_id=7)))
    app = create_app(settings, bots={"no-ip": bot})
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.post("/v1/messages", headers={"Authorization": "Bearer noip-test-key"},
            json={"project_id": "no-ip", "bot_id": "no-ip", "destination_id": "owner", "text": "Renewed"})
        assert response.json() == {"ok": True, "message_id": 7}
    bot.get_me.assert_awaited_once()
    bot.get_webhook_info.assert_not_awaited()
    bot.send_message.assert_awaited_once_with(chat_id=42, text="Renewed", parse_mode=None)


def test_interactive_routes_still_require_callback():
    with pytest.raises(ValidationError, match="Interactive routes require"):
        Settings.model_validate({"projects": {"no-ip": {"api_key_env": "NOIP_KEY",
            "routes": [{"command": "/status"}]}}, "bots": {"no-ip": {"token_env": "UNUSED",
            "project_id": "no-ip", "destinations": {"owner": 42}, "allowed_chat_ids": [42]}}})
