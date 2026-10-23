"""Validated configuration with environment-only secrets."""
import json
import os
from pathlib import Path
from pydantic import BaseModel, Field, model_validator


class Route(BaseModel):
    command: str
    aliases: list[str] = Field(default_factory=list)
    button: str | None = None


class Project(BaseModel):
    api_key_env: str
    callback_url: str | None = None
    callback_key_env: str | None = None
    routes: list[Route] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_routes(self):
        if self.routes and (not self.callback_url or not self.callback_key_env):
            raise ValueError("Interactive routes require callback_url and callback_key_env")
        names = [name.lower() for route in self.routes
                 for name in [route.command, *route.aliases, *([route.button] if route.button else [])]]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate command, alias, or button")
        return self


class BotConfig(BaseModel):
    receive_updates: bool = True
    token_env: str
    project_id: str
    destinations: dict[str, int]
    allowed_chat_ids: list[int] = Field(min_length=1)
    allowed_user_ids: list[int] = Field(default_factory=list)


class Settings(BaseModel):
    projects: dict[str, Project] = Field(min_length=1)
    bots: dict[str, BotConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bots(self):
        for bot in self.bots.values():
            if bot.project_id not in self.projects:
                raise ValueError("Unknown project_id")
        return self

    @classmethod
    def load(cls, path: str):
        return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def secret(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing environment variable: {name}")
    return value
