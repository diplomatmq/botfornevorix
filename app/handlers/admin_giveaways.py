from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import Bot, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.database.repo import Repository
from app.handlers.common import ensure_user, clear_state
from app.keyboards.admin_kb import admin_menu, giveaway_admin_menu, GiveawayCallback
from app.middlewares.acl import IsAdmin
from app.states.form_states import CreateGiveawayState
from app.utils.formatters import format_datetime
from app.utils.giveaways import build_giveaway_post

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


MSK = timezone(timedelta(hours=3))


def _parse_dt(text: str) -> datetime | None:
    text = text.strip()
    dt: datetime | None = None
    for fmt in ("%d.%m.%Y %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    if dt is None:
        return None
    dt_msk = dt.replace(tzinfo=MSK)
    dt_utc = dt_msk.astimezone(timezone.utc).replace(tzinfo=None)
    return dt_utc


@router.message(F.text == "🎲 Создать розыгрыш")
async def giveaway_menu_msg(message: Message, state: FSMContext, repo: Repository):
    await ensure_user(repo, message)
    await clear_state(state)
    await message.answer("🎲 Управление розыгрышами:", reply_markup=giveaway_admin_menu())


@router.callback_query(GiveawayCallback.filter(F.action == "new"))
async def new_giveaway_cb(callback: CallbackQuery, state: FSMContext, repo: Repository):
    await ensure_user(repo, callback.message)
    await state.clear()
    await state.set_state(CreateGiveawayState.title)
    await callback.message.edit_text(
        "🎲 <b>Создание розыгрыша (шаг 1/5)</b>\n\nВведите заголовок розыгрыша (можно пропустить — отправьте 0):",
        reply_markup=None,
    )
    await callback.answer()


@router.message(CreateGiveawayState.title)
async def ga_title_step(message: Message, state: FSMContext):
    text = message.text.strip()
    title = None if text == "0" else text[:200]
    await state.update_data(title=title)
    await state.set_state(CreateGiveawayState.prize)
    await message.answer("🎁 <b>Шаг 2/5</b>\nВведите название приза (напр. iPhone 16):")


@router.message(CreateGiveawayState.prize)
async def ga_prize_step(message: Message, state: FSMContext):
    await state.update_data(prize=message.text.strip()[:200])
    await state.set_state(CreateGiveawayState.text)
    await message.answer("📝 <b>Шаг 3/5</b>\nВведите текст/описание розыгрыша:")


@router.message(CreateGiveawayState.text)
async def ga_text_step(message: Message, state: FSMContext):
    await state.update_data(text=message.text.strip()[:2000])
    await state.set_state(CreateGiveawayState.ends_at)
    await message.answer(
        "⏰ <b>Шаг 4/5</b>\n"
        "Введите дату и время завершения в формате ДД.ММ.ГГГГ ЧЧ:ММ (напр. 15.10.2026 20:00):"
    )


@router.message(CreateGiveawayState.ends_at)
async def ga_ends_at_step(message: Message, state: FSMContext):
    dt = _parse_dt(message.text)
    if dt is None:
        await message.answer("❌ Не удалось распознать дату. Введите в формате ДД.ММ.ГГГГ ЧЧ:ММ:")
        return
    if dt <= datetime.utcnow():
        await message.answer("❌ Дата должна быть в будущем. Попробуйте снова:")
        return
    await state.update_data(ends_at=dt)
    await state.set_state(CreateGiveawayState.min_level)
    await message.answer(
        "📊 <b>Шаг 5/5</b>\n"
        "Введите МИНИМАЛЬНЫЙ уровень участников (0 — без ограничения):"
    )


@router.message(CreateGiveawayState.min_level)
async def ga_min_level_step(message: Message, state: FSMContext):
    t = message.text.strip()
    try:
        val = int(t)
    except (TypeError, ValueError):
        await message.answer("❌ Введите целое число (0 = без ограничения):")
        return
    if val < 0:
        await message.answer("❌ Уровень не может быть отрицательным:")
        return
    min_level = None if val == 0 else val
    data = await state.get_data()
    data.update(min_level=min_level)
    await state.update_data(min_level=min_level)
    preview = {
        "id": None,
        "title": data.get("title"),
        "prize": data.get("prize"),
        "text": data.get("text"),
        "ends_at": data.get("ends_at"),
        "min_level": data.get("min_level"),
    }
    await state.set_state(CreateGiveawayState.confirm)
    await message.answer(
        "📋 Предпросмотр розыгрыша:\n\n"
        + build_giveaway_post(preview)
        + "\n\n✅ Отправить <b>ДА</b> для создания розыгрыша и публикации в канале. "
        "Любое другое сообщение — отмена."
    )


@router.message(CreateGiveawayState.confirm)
async def ga_confirm_step(message: Message, state: FSMContext, repo: Repository, bot: Bot):
    if message.text.strip().lower() != "да":
        await state.clear()
        await message.answer("❌ Создание розыгрыша отменено.", reply_markup=admin_menu())
        return
    data = await state.get_data()
    uid = await ensure_user(repo, message)
    channel_id = settings.CHANNEL_ID
    if not channel_id:
        await message.answer("❌ CHANNEL_ID не настроен в .env", reply_markup=admin_menu())
        await state.clear()
        return
    ga_id = await repo.create_giveaway(
        admin_id=uid,
        title=data.get("title"),
        prize=data.get("prize") or "Приз",
        text=data.get("text") or "",
        channel_id=channel_id,
        ends_at=data["ends_at"],
        min_level=data.get("min_level"),
    )
    ga = await repo.get_giveaway(ga_id)
    try:
        msg = await bot.send_message(chat_id=channel_id, text=build_giveaway_post(ga))
        await repo.set_giveaway_channel_msg(ga_id, int(msg.message_id))
    except Exception as e:
        await message.answer(
            f"⚠️ Розыгрыш #{ga_id} создан в БД, но не удалось отправить в канал:\n{e}",
            reply_markup=admin_menu(),
        )
        await state.clear()
        return
    await state.clear()
    await message.answer(
        f"✅ Розыгрыш #{ga_id} создан и опубликован в канале!\n"
        f"Завершение: {format_datetime(ga['ends_at'])}\n"
        f"ID сообщения в канале: {msg.message_id}",
        reply_markup=admin_menu(),
    )
