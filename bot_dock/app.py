"""HTTP notification API and Telegram command routing."""
import asyncio
import hmac
import logging
from contextlib import asynccontextmanager, suppress

import httpx
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import BotCommand, Message, ReplyKeyboardRemove
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .config import Settings, secret

LOGGER = logging.getLogger("bot_dock")


class Notification(BaseModel):
    project_id: str
    bot_id: str
    destination_id: str
    text: str = Field(min_length=1, max_length=4096)
    parse_mode: str | None = Field(default=None, pattern="^(HTML|MarkdownV2)$")


def create_app(settings: Settings, *, polling: bool = True, bots=None, client=None):
    tokens = [secret(config.token_env) for config in settings.bots.values()] if bots is None else []
    if len(tokens) != len(set(tokens)):
        raise ValueError("Each bot token must have exactly one polling owner")
    senders = bots if bots is not None else {
        name: Bot(token=token) for (name, _), token in zip(settings.bots.items(), tokens)
    }
    api_keys = {name: secret(p.api_key_env) for name, p in settings.projects.items()}
    callback_keys = {name: secret(p.callback_key_env) for name, p in settings.projects.items() if p.callback_key_env}
    polling_bots = [senders[name] for name, config in settings.bots.items() if config.receive_updates]
    dispatcher = Dispatcher()
    by_token = {bot.token: name for name, bot in senders.items()}
    callback_client = client if client is not None else httpx.AsyncClient(timeout=15, follow_redirects=False)

    async def receive(message: Message, bot: Bot):
        config = settings.bots[by_token[bot.token]]
        if message.chat.id not in config.allowed_chat_ids:
            return
        if config.allowed_user_ids and (not message.from_user or message.from_user.id not in config.allowed_user_ids):
            return
        if not message.text:
            return
        text = message.text.strip().lower()
        if text.startswith("/"):
            text = text.split()[0].split("@", 1)[0]
        project = settings.projects[config.project_id]
        route = next((r for r in project.routes if text in
                      [s.lower() for s in [r.command, *r.aliases, *([r.button] if r.button else [])]]), None)
        keyboard = ReplyKeyboardRemove()
        if route is None:
            await message.answer("請使用選單或已設定的指令。", reply_markup=keyboard)
            return
        try:
            response = await callback_client.post(
                project.callback_url,
                headers={"Authorization": f"Bearer {callback_keys[config.project_id]}"},
                json={"command": route.command, "bot_id": by_token[bot.token],
                      "chat_id": message.chat.id, "user_id": message.from_user.id if message.from_user else None},
            )
            response.raise_for_status()
            result = response.json()
            reply = result["text"]
            mode = result.get("parse_mode")
            if not isinstance(reply, str) or not reply or len(reply) > 4096 or mode not in (None, "HTML", "MarkdownV2"):
                raise ValueError("Invalid callback response")
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            LOGGER.warning("Project callback failed for %s", config.project_id)
            reply, mode = "專案查詢暫時無法使用，請稍後再試。", None
        await message.answer(reply, parse_mode=mode, reply_markup=keyboard)

    dispatcher.message.register(receive)

    @asynccontextmanager
    async def lifespan(app):
        task = None
        try:
            if polling:
                for bot in senders.values():
                    await bot.get_me()
                for bot in polling_bots:
                    webhook = await bot.get_webhook_info()
                    if webhook.url:
                        raise RuntimeError("Existing webhook must be removed before enabling polling")
                for name, config in settings.bots.items():
                    if config.receive_updates:
                        routes = settings.projects[config.project_id].routes
                        await senders[name].set_my_commands([
                            BotCommand(command=route.command[1:],
                                       description=route.description or route.command)
                            for route in routes
                        ])
                if polling_bots:
                    task = asyncio.create_task(dispatcher.start_polling(
                        *polling_bots, handle_signals=False, close_bot_session=False,
                        allowed_updates=["message"], handle_as_tasks=False,
                    ))
            app.state.polling_task = task
            yield
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if client is None:
                await callback_client.aclose()
            if bots is None:
                for bot in senders.values():
                    await bot.session.close()

    app = FastAPI(title="BotDock", version="0.1.0", lifespan=lifespan)
    app.state.dispatcher = dispatcher

    @app.get("/health")
    async def health():
        task = getattr(app.state, "polling_task", None)
        if polling and polling_bots and (task is None or task.done()):
            raise HTTPException(503, "Polling unavailable")
        return {"status": "ok"}

    @app.post("/v1/messages")
    async def send(body: Notification, authorization: str = Header(default="")):
        expected = api_keys.get(body.project_id)
        if expected is None or not hmac.compare_digest(authorization, f"Bearer {expected}"):
            raise HTTPException(401, "Invalid credentials")
        config = settings.bots.get(body.bot_id)
        if config is None or config.project_id != body.project_id or body.destination_id not in config.destinations:
            raise HTTPException(403, "Destination not permitted")
        try:
            result = await senders[body.bot_id].send_message(
                chat_id=config.destinations[body.destination_id], text=body.text, parse_mode=body.parse_mode,
            )
        except TelegramRetryAfter as error:
            raise HTTPException(429, "Telegram rate limit", headers={"Retry-After": str(error.retry_after)}) from None
        except TelegramAPIError:
            raise HTTPException(502, "Telegram delivery failed; delivery may be uncertain") from None
        return {"ok": True, "message_id": result.message_id}

    return app
