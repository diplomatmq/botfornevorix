from __future__ import annotations

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.database.repo import Repository
from app.handlers.common import ensure_user, clear_state
from app.keyboards.admin_kb import admin_menu
from app.middlewares.acl import IsAdmin
from app.states.form_states import AdminSetLevelState
from app.utils.formatters import format_user_name

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(F.text == "🎯 Назначить уровень")
async def set_level_start(message: Message, state: FSMContext, repo: Repository):
    await ensure_user(repo, message)
    await clear_state(state)
    await state.set_state(AdminSetLevelState.user_identifier)
    await message.answer(
        "🎯 Введите ID пользователя (tg_id или id из базы) или @username:"
    )


@router.message(AdminSetLevelState.user_identifier)
async def set_level_user_step(message: Message, state: FSMContext, repo: Repository):
    text = message.text.strip()
    target = None
    if text.startswith("@"):
        uname = text[1:]
        for u in await repo.get_all_users():
            if u["username"] and u["username"].lower() == uname.lower():
                target = u
                break
    else:
        if text.isdigit():
            num = int(text)
            target = await repo.get_user_by_tg_id(num) or await repo.get_user_by_id(num)
    if not target:
        await message.answer("❌ Пользователь не найден. Попробуйте ещё раз:")
        return
    await state.update_data(target_id=int(target["id"]))
    await state.set_state(AdminSetLevelState.level)
    await message.answer(
        f"👤 Пользователь: {format_user_name(target)}\n"
        f"Текущий уровень: L{target['level']}  Макс: L{target['max_level']}\n\n"
        "Введите новый уровень (целое число >= 0):"
    )


@router.message(AdminSetLevelState.level)
async def set_level_level_step(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Введите целое число >= 0:")
        return
    level = int(text)
    if level < 0:
        await message.answer("❌ Уровень не может быть отрицательным:")
        return
    await state.update_data(level=level)
    await state.set_state(AdminSetLevelState.confirm)
    await message.answer(
        f"Назначить L{level}?\nВведите <b>ДА</b> для подтверждения, что угодно другое для отмены."
    )


@router.message(AdminSetLevelState.confirm)
async def set_level_confirm_step(message: Message, state: FSMContext, repo: Repository):
    if message.text.strip().lower() != "да":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_menu())
        return
    data = await state.get_data()
    target_id = int(data["target_id"])
    level = int(data["level"])
    await repo.set_user_level(target_id, level)
    tgt = await repo.get_user_by_id(target_id)
    await state.clear()
    await message.answer(
        f"✅ Уровень установлен:\n{format_user_name(tgt)} → L{tgt['level']} (max L{tgt['max_level']})",
        reply_markup=admin_menu(),
    )
