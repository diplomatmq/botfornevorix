from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import settings
from app.loader import generic_invite_link, is_subscribed_to_channel
from app.utils.formatters import format_stars


def _extract_user_id(event: TelegramObject) -> int | None:
    if isinstance(event, Message):
        return event.from_user.id if event.from_user else None
    if isinstance(event, CallbackQuery):
        return event.from_user.id
    return None


def _is_start_command(event: TelegramObject) -> bool:
    if not isinstance(event, Message):
        return False
    text = event.text or ""
    if text.startswith("/start") or text.startswith("/menu"):
        return True
    if text == "🔙 В меню":
        return True
    return False


def _is_listed_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in settings.ADMIN_IDS


async def _has_active_state(data: Dict[str, Any]) -> bool:
    state: FSMContext | None = data.get("state")
    if state is None:
        return False
    try:
        current = await state.get_state()
        return current is not None
    except Exception:
        return False


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = _extract_user_id(event)
        if user_id is None:
            return await handler(event, data)
        if _is_listed_admin(user_id):
            return await handler(event, data)
        if _is_start_command(event):
            return await handler(event, data)
        if await _has_active_state(data):
            return await handler(event, data)
        bot: Bot = data.get("bot") or data.get("bot_instance")
        if bot is None:
            from app.loader import bot as default_bot
            bot = default_bot
        subscribed = await is_subscribed_to_channel(bot, user_id)
        if subscribed:
            return await handler(event, data)
        link = generic_invite_link or ""
        price_text = format_stars(settings.REF_LINK_COST)
        text = (
            "⚠️ Бот доступен только подписчикам канала.\n\n"
            "Оформите месячную подписку по ссылке ниже:\n"
            f"{link}\n\n"
            f"Стоимость: {price_text} в месяц.\n"
            "После оплаты вернитесь в бот и нажмите /start"
        )
        if isinstance(event, Message):
            await event.answer(text, disable_web_page_preview=True)
        elif isinstance(event, CallbackQuery):
            try:
                await event.message.edit_text(text, disable_web_page_preview=True)
            except Exception:
                await event.answer(text, show_alert=True)
        return None
