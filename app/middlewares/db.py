from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.database.repo import Repository


class RepoMiddleware(BaseMiddleware):
    def __init__(self, repo: Repository):
        self.repo = repo

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data["repo"] = self.repo
        return await handler(event, data)
