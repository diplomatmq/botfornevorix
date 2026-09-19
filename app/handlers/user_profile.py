from __future__ import annotations

from aiogram import Router, F
from aiogram.filters.callback_data import CallbackQuery
from aiogram.types import Message

from app.config import settings
from app.database.repo import Repository, TXN_RESTORE_LEVEL
from app.handlers.common import ensure_user
from app.keyboards.user_kb import confirm_restore_kb, profile_kb, balance_kb
from app.utils.formatters import format_datetime, format_stars, format_subscription_end, format_tx_type

router = Router()


@router.message(F.text == "👤 Профиль")
async def my_profile(message: Message, repo: Repository):
    uid = await ensure_user(repo, message)
    u = await repo.get_user_by_id(uid)
    refs = await repo.get_referral_count_by_owner(uid)
    can_restore = int(u["level"]) < int(u["max_level"]) and int(u["max_level"]) > 0
    wins = int(u["wins"]) if "wins" in u.keys() else 0
    text = (
        "👤 <b>Ваш профиль</b>\n\n"
        f"Имя: {u['full_name']}\n"
        f"Баланс: {format_stars(int(u['balance']))}\n\n"
        f"🎖️ Текущий уровень: <b>L{u['level']}</b>\n"
        f"🏆 Максимальный уровень: <b>L{u['max_level']}</b>\n"
        f"🥇 Победы в розыгрышах: <b>{wins}</b>\n"
        f"Подписка: {format_subscription_end(u['subscription_end'])}\n"
        f"Присоединился: {format_datetime(u['first_subscription_at'] or u['created_at'])}\n\n"
        f"👥 Рефералов приглашено: {refs}"
    )
    await message.answer(text, reply_markup=profile_kb(can_restore=can_restore))


@router.message(F.text == "⭐ Баланс")
async def my_balance(message: Message, repo: Repository):
    uid = await ensure_user(repo, message)
    u = await repo.get_user_by_id(uid)
    await message.answer(
        f"💰 Баланс: <b>{format_stars(int(u['balance']))}</b>\n\n"
        "Выберите действие:",
        reply_markup=balance_kb(),
    )


@router.callback_query(F.data == "restore_level")
async def cb_restore_level(callback: CallbackQuery, repo: Repository):
    uid = await ensure_user(repo, callback.message)
    u = await repo.get_user_by_id(uid)
    if int(u["level"]) >= int(u["max_level"]):
        await callback.answer("✅ У вас уже максимальный уровень", show_alert=True)
        return
    if int(u["balance"]) < settings.RESTORE_LEVEL_COST:
        await callback.answer(f"❌ Нужно {settings.RESTORE_LEVEL_COST} ⭐", show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=confirm_restore_kb())
    await callback.answer()


@router.callback_query(F.data == "restore_level_confirm")
async def cb_restore_confirm(callback: CallbackQuery, repo: Repository):
    uid = await ensure_user(repo, callback.message)
    u = await repo.get_user_by_id(uid)
    if int(u["balance"]) < settings.RESTORE_LEVEL_COST or int(u["level"]) >= int(u["max_level"]):
        await callback.answer("Невозможно выполнить", show_alert=True)
        return
    ok = await repo.subtract_stars(uid, settings.RESTORE_LEVEL_COST, TXN_RESTORE_LEVEL)
    if not ok:
        await callback.answer("Ошибка списания", show_alert=True)
        return
    await repo.set_user_level(uid, int(u["max_level"]))
    await callback.answer(f"✅ Уровень восстановлен до L{u['max_level']}", show_alert=True)
    u2 = await repo.get_user_by_id(uid)
    await callback.message.edit_text(
        f"✅ Уровень восстановлен до <b>L{u2['level']}</b>\n\n"
        f"Новый баланс: {format_stars(int(u2['balance']))}",
        reply_markup=None,
    )


@router.callback_query(F.data == "restore_level_cancel")
async def cb_restore_cancel(callback: CallbackQuery, repo: Repository):
    uid = await ensure_user(repo, callback.message)
    u = await repo.get_user_by_id(uid)
    can_restore = int(u["level"]) < int(u["max_level"]) and int(u["max_level"]) > 0
    await callback.message.edit_reply_markup(reply_markup=profile_kb(can_restore=can_restore))
    await callback.answer()


@router.callback_query(F.data == "transactions")
async def cb_transactions(callback: CallbackQuery, repo: Repository):
    uid = await ensure_user(repo, callback.message)
    rows = await repo.get_recent_transactions(uid, limit=20)
    if not rows:
        await callback.answer("История пуста", show_alert=True)
        return
    lines = ["📜 Последние транзакции:\n"]
    for r in rows:
        sign = "+" if int(r["amount"]) > 0 else ""
        lines.append(f"{format_datetime(r['created_at'])}  {sign}{r['amount']} ⭐  {format_tx_type(r['type'])}")
    await callback.message.answer("\n".join(lines))
    await callback.answer()
