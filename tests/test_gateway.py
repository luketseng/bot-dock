import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from aiogram import Bot
from aiogram.types import Update
from fastapi.testclient import TestClient
from bot_dock.app import create_app
from bot_dock.config import Settings


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setenv("KEY", "secret")
    monkeypatch.setenv("CALLBACK", "callback-secret")
    monkeypatch.setenv("OTHER_KEY", "other-secret")
    settings = Settings.model_validate({
        "projects": {"demo": {"api_key_env": "KEY", "callback_key_env": "CALLBACK",
            "callback_url": "http://project/query", "routes": [
                {"command": "/status", "button": "Status", "aliases": []}]}},
        "bots": {"demo": {"token_env": "TOKEN", "project_id": "demo",
            "destinations": {"owner": 42}, "allowed_chat_ids": [42], "allowed_user_ids": [7]}}
    })
    settings.projects["other"] = settings.projects["demo"].model_copy(update={"api_key_env": "OTHER_KEY"})
    settings.bots["other"] = settings.bots["demo"].model_copy(update={"project_id": "other"})
    other_bot = Bot(token="654321:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    other_bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=100))
    bot = Bot(token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=99))
    calls = []
    def callback(request):
        calls.append(request)
        return httpx.Response(200, json={"text": "Ready", "parse_mode": "HTML"})
    client = httpx.AsyncClient(transport=httpx.MockTransport(callback))
    app = create_app(settings, polling=False, bots={"demo": bot, "other": other_bot}, client=client)
    return app, bot, calls, client


def test_notifications_auth_and_destination_isolation(gateway):
    app, bot, _, _ = gateway
    body = {"project_id": "demo", "bot_id": "demo", "destination_id": "owner", "text": "Done"}
    with TestClient(app) as client:
        assert client.post("/v1/messages", json=body).status_code == 401
        headers = {"Authorization": "Bearer secret"}
        assert client.post("/v1/messages", json={**body, "bot_id": "other"}, headers=headers).status_code == 403
        assert client.post("/v1/messages", json={**body, "destination_id": "other"}, headers=headers).status_code == 403
        assert client.post("/v1/messages", json={**body, "bot_id": "other"}, headers=headers).status_code == 403
        assert client.post("/v1/messages", json={**body, "project_id": "other", "bot_id": "other"}, headers=headers).status_code == 401
        other_response = client.post("/v1/messages", json={**body, "project_id": "other", "bot_id": "other"}, headers={"Authorization": "Bearer other-secret"})
        assert other_response.json() == {"ok": True, "message_id": 100}
        response = client.post("/v1/messages", json=body, headers=headers)
        assert response.json() == {"ok": True, "message_id": 99}
        assert client.post("/v1/messages", json={**body, "text": "x" * 4097}, headers=headers).status_code == 422
    bot.send_message.assert_awaited_once_with(chat_id=42, text="Done", parse_mode=None)


@pytest.mark.parametrize("text", ["Status", "/status", "/status@demo_bot"])
def test_buttons_and_commands_call_project(gateway, text):
    app, bot, calls, client = gateway
    update = Update.model_validate({"update_id": 1, "message": {
        "message_id": 1, "date": int(datetime.now(timezone.utc).timestamp()),
        "chat": {"id": 42, "type": "private"},
        "from": {"id": 7, "is_bot": False, "first_name": "Owner"}, "text": text}})
    async def run():
        bot.session.make_request = AsyncMock(return_value=True)
        await app.state.dispatcher.feed_update(bot, update)
        await client.aclose()
        await bot.session.close()
    asyncio.run(run())
    assert len(calls) == 1
    assert calls[0].headers["Authorization"] == "Bearer callback-secret"
    assert b'"command":"/status"' in calls[0].content
    method = bot.session.make_request.call_args.args[1]
    assert method.text == "Ready"
    assert method.reply_markup.remove_keyboard is True


def test_unauthorized_user_cannot_query(gateway):
    app, bot, calls, client = gateway
    update = Update.model_validate({"update_id": 2, "message": {
        "message_id": 1, "date": 1700000000, "chat": {"id": 42, "type": "private"},
        "from": {"id": 8, "is_bot": False, "first_name": "Other"}, "text": "/status"}})
    async def run():
        bot.session.make_request = AsyncMock()
        await app.state.dispatcher.feed_update(bot, update)
        bot.session.make_request.assert_not_called()
        await client.aclose()
        await bot.session.close()
    asyncio.run(run())
    assert calls == []
