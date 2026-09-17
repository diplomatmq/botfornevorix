from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message

from app.database.repo import Repository
from app.handlers.common import ensure_user
from app.keyboards.admin_kb import (
    StatsCallback,
    admin_menu,
    level_statistics_kb,
    statistics_kb,
)
from app.middlewares.acl import IsAdmin
from app.utils.formatters import format_datetime, format_user_name, format_subscription_end

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(F.text == "📊 Статистика")
async def statistics_menu(message: Message, repo: Repository):
    await ensure_user(repo, message)
    await message.answer("📊 Статистика:", reply_markup=statistics_kb())


@router.callback_query(StatsCallback.filter(F.action == "levels"))
async def statistics_levels(callback: CallbackQuery, repo: Repository):
    users = await repo.get_all_users()
    levels = sorted({int(user["level"]) for user in users})
    await callback.message.edit_text(
        "👥 Выберите уровень:",
        reply_markup=level_statistics_kb(levels),
    )
    await callback.answer()


@router.callback_query(StatsCallback.filter(F.action == "level"))
async def statistics_level(callback: CallbackQuery, callback_data: StatsCallback, repo: Repository):
    users = await repo.get_users_by_level(int(callback_data.level))
    lines = [f"👥 Пользователи уровня L{callback_data.level} ({len(users)}):"]
    lines.extend(f"• {format_user_name(user)}" for user in users[:100])
    await callback.message.edit_text("\n".join(lines), reply_markup=statistics_kb())
    await callback.answer()


@router.callback_query(StatsCallback.filter(F.action == "subscriptions"))
async def statistics_subscriptions(callback: CallbackQuery, repo: Repository):
    users = await repo.get_recent_subscriptions()
    lines = ["🆕 10 последних подписок:"]
    lines.extend(
        f"• {format_user_name(user)} — {format_datetime(user['first_subscription_at'])}"
        for user in users
    )
    await callback.message.edit_text("\n".join(lines), reply_markup=statistics_kb())
    await callback.answer()


@router.callback_query(StatsCallback.filter(F.action == "renewals"))
async def statistics_renewals(callback: CallbackQuery, repo: Repository):
    renewals = await repo.get_recent_renewals()
    lines = ["🔁 Последние продления подписки:"]
    lines.extend(
        f"• {format_user_name(renewal)} — {format_datetime(renewal['created_at'])}"
        for renewal in renewals
    )
    await callback.message.edit_text("\n".join(lines), reply_markup=statistics_kb())
    await callback.answer()
