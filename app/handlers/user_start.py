from __future__ import annotations

from aiogram import Bot, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ChatMemberUpdated, Message

from app.config import settings
from app.database.repo import Repository
from app.handlers.common import clear_state, ensure_user, handle_referral_invite
from app.keyboards.user_kb import main_menu

router = Router()


@router.chat_member()
async def channel_referral_join(event: ChatMemberUpdated, repo: Repository):
    if not settings.CHANNEL_ID or event.chat.id != settings.CHANNEL_ID:
        return
    if not event.invite_link:
        return
    if event.new_chat_member.status not in {"member", "administrator", "creator"}:
        return
    if event.old_chat_member.status in {"member", "administrator", "creator"}:
        return
    member = event.new_chat_member.user
    await handle_referral_invite(
        repo,
        member.id,
        member.username,
        member.full_name,
        event.invite_link.invite_link,
    )


def _is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, repo: Repository, bot: Bot):
    await clear_state(state)
    user_db_id = await ensure_user(repo, message)
    u = await repo.get_user_by_id(user_db_id)
    refs_count = await repo.get_referral_count_by_owner(user_db_id)
    await message.answer(
        "👋 Добро пожаловать!\n\n"
        f"Рефералов приглашено: {refs_count}\n"
        f"Баланс: {u['balance']} ⭐\n\n"
        "Выберите пункт в меню ниже:",
        reply_markup=main_menu(_is_admin(message.from_user.id)),
    )


@router.message(Command("menu"))
@router.message(F.text == "🔙 В меню")
async def cmd_menu(message: Message, state: FSMContext, repo: Repository):
    await clear_state(state)
    user_db_id = await ensure_user(repo, message)
    u = await repo.get_user_by_id(user_db_id)
    await message.answer(
        "📋 Главное меню",
        reply_markup=main_menu(_is_admin(message.from_user.id)),
    )


@router.message(F.text == "⚙️ Админ-меню")
async def open_admin_menu(message: Message, repo: Repository):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    from app.keyboards.admin_kb import admin_menu
    await message.answer("⚙️ Админ-панель", reply_markup=admin_menu())
