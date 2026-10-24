import asyncio
import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import httpx
import pytest

from bot_dock.app import Notification
from bot_dock.config import Settings

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


def load_template(name):
    spec = importlib.util.spec_from_file_location(name, TEMPLATES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("mode", ["notification", "interactive", "combined"])
def test_template_config_matches_gateway(mode):
    directory = TEMPLATES / mode
    settings = Settings.load(str(directory / "bot-dock.fragment.json"))
    bot = settings.bots["my-bot"]
    project = settings.projects[bot.project_id]
    assert bot.receive_updates == (mode != "notification")
    if mode != "interactive":
        config = json.loads((directory / ("botdock.example.json" if mode == "combined" else "botdock_client.example.json")).read_text())
        assert config["project_id"] == bot.project_id
        assert config["bot_id"] == "my-bot"
        assert config["destination_id"] in bot.destinations
        assert config["api_key_env"] == project.api_key_env
    if mode != "notification":
        config = json.loads((directory / ("botdock.example.json" if mode == "combined" else "botdock_callback.example.json")).read_text())
        assert config["callback_key_env"] == project.callback_key_env
        assert config["allowed_chat_ids"] == bot.allowed_chat_ids
        assert config["allowed_user_ids"] == bot.allowed_user_ids


@pytest.mark.parametrize("combined", [False, True])
def test_notification_template_sends_gateway_payload(monkeypatch, combined):
    module = load_template("combined/botdock_app" if combined else "notification/botdock_client")
    monkeypatch.setenv("MYPROJECT_BOTDOCK_API_KEY", "test-key")
    if combined:
        monkeypatch.setenv("BOTDOCK_CONFIG", str(TEMPLATES / "combined/botdock.example.json"))
        client = module.BotDockClient()
    else:
        client = module.BotDockClient(TEMPLATES / "notification/botdock_client.example.json")
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"ok": true, "message_id": 7}'
    with patch.object(module, "urlopen", return_value=response) as send:
        assert client.send("完成") == {"ok": True, "message_id": 7}
    request = send.call_args.args[0]
    assert request.full_url == "http://127.0.0.1:8090/v1/messages"
    assert request.get_header("Authorization") == "Bearer test-key"
    body = Notification.model_validate(json.loads(request.data))
    assert body.text == "完成"
    assert body.project_id == "my-project"
    assert send.call_args.kwargs["timeout"] == 20
    with patch.object(module, "urlopen", side_effect=HTTPError(request.full_url, 429, "Limit", {}, None)) as send:
        with pytest.raises(HTTPError):
            client.send("完成")
        assert send.call_count == 1
    monkeypatch.delenv("MYPROJECT_BOTDOCK_API_KEY")
    with pytest.raises(ValueError, match="Missing environment variable"):
        client.send("完成")


@pytest.mark.parametrize("combined", [False, True])
def test_callback_template_auth_permissions_and_routes(monkeypatch, combined):
    module = load_template("combined/botdock_app" if combined else "interactive/callback_app")
    monkeypatch.setenv(
        "BOTDOCK_CONFIG" if combined else "BOTDOCK_CALLBACK_CONFIG",
        str(TEMPLATES / ("combined/botdock.example.json" if combined else "interactive/botdock_callback.example.json")),
    )
    monkeypatch.setenv("MYPROJECT_CALLBACK_KEY", "callback-key")
    app = module.create_app()

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://project") as client:
            body = {"command": "/status", "bot_id": "my-bot", "chat_id": 123456789, "user_id": 123456789}
            headers = {"Authorization": "Bearer callback-key"}
            assert (await client.post("/botdock/query", json=body)).status_code == 401
            for change in [{"bot_id": "other"}, {"chat_id": 1}, {"user_id": 1}, {"user_id": None}]:
                assert (await client.post("/botdock/query", json={**body, **change}, headers=headers)).status_code == 403
            settings = Settings.load(str(TEMPLATES / "interactive/bot-dock.fragment.json"))
            for route in settings.projects["my-project"].routes:
                response = await client.post("/botdock/query", json={**body, "command": route.command}, headers=headers)
                assert response.status_code == 200
                assert 1 <= len(response.json()["text"]) <= 4096
            assert (await client.post("/botdock/query", json={**body, "command": "/unknown"}, headers=headers)).status_code == 400

    asyncio.run(run())
