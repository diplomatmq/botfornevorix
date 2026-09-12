from __future__ import annotations

import asyncio

from aiogram import Bot, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database.repo import Repository
from app.handlers.common import ensure_user, clear_state
from app.keyboards.admin_kb import RequestCallback, admin_menu, request_action_kb
from app.middlewares.acl import IsAdmin
from app.states.form_states import BroadcastState, RequestRejectState, AdminRequestCheckState
from app.utils.formatters import format_stars, format_user_name

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(F.text == "📋 Список заявок")
async def list_requests(message: Message, repo: Repository, state: FSMContext):
    await ensure_user(repo, message)
    await clear_state(state)
    
    # Показываем только заявки на вывод
    wds = await repo._rows(
        "SELECT wr.*, u.tg_id, u.username, u.full_name "
        "FROM withdraw_requests wr JOIN users u ON u.id = wr.user_id "
        "WHERE wr.status = 'pending' ORDER BY wr.created_at DESC LIMIT 30"
    )
    
    if not wds:
        await message.answer("📋 Нет ожидающих заявок на вывод.", reply_markup=admin_menu())
        return
    
    lines = ["📋 <b>Заявки на ВЫВОД:</b>\n"]
    for w in wds:
        lines.append(
            f"#{w['id']} — {format_user_name(w)} — {format_stars(int(w['amount']))}"
        )
    
    lines.append("\n💡 Для обработки заявки отправьте её номер (например: 5)")
    
    await message.answer("\n".join(lines), reply_markup=admin_menu())
    await state.set_state(AdminRequestCheckState.request_id)


@router.message(AdminRequestCheckState.request_id)
async def check_request_by_id(message: Message, state: FSMContext, repo: Repository):
    """Обработка номера заявки от админа"""
    text = message.text.strip()
    
    if not text.isdigit():
        await message.answer("❌ Введите номер заявки (целое число) или отправьте /cancel для отмены")
        return
    
    req_id = int(text)
    
    # Проверяем только заявки на вывод
    req = await repo.get_withdraw(req_id)
    
    if not req:
        await message.answer(f"❌ Заявка #{req_id} не найдена.")
        return
    
    if req["status"] != "pending":
        await message.answer(f"⚠️ Заявка #{req_id} уже обработана (статус: {req['status']})")
        return
    
    user = await repo.get_user_by_id(int(req["user_id"]))
    
    if not user:
        await message.answer(f"❌ Пользователь заявки #{req_id} не найден.")
        return
    
    # Показываем детали заявки с кнопками
    caption = (
        f"💸 <b>Заявка на ВЫВОД #{req_id}</b>\n\n"
        f"👤 Пользователь: {format_user_name(user)}\n"
        f"💰 Сумма: {format_stars(int(req['amount']))}\n"
        f"🏦 Реквизиты: {req['details']}\n"
        f"📅 Создана: {req['created_at']}"
    )
    
    from app.keyboards.admin_kb import request_action_kb
    await message.answer(caption, reply_markup=request_action_kb(req_type="wd", req_id=req_id))
    await state.clear()


@router.callback_query(RequestCallback.filter(F.action == "approve"))
async def approve_request_cb(callback: CallbackQuery, callback_data: RequestCallback, repo: Repository, bot: Bot):
    await ensure_user(repo, callback.message)
    admin = await repo.get_user_by_tg_id(callback.from_user.id)
    admin_id = int(admin["id"]) if admin else 0
    req_type = callback_data.req_type
    req_id = int(callback_data.req_id)
    ok = False
    user_id = 0
    amount = 0
    
    # Обрабатываем только заявки на вывод
    if req_type == "wd":
        ok = await repo.approve_withdraw(req_id, admin_id)
        if ok:
            w = await repo.get_withdraw(req_id)
            user_id = int(w["user_id"])
            amount = int(w["amount"])
    else:
        await callback.answer("❌ Неизвестный тип заявки", show_alert=True)
        return
    
    if not ok:
        await callback.answer("Ошибка или заявка уже обработана", show_alert=True)
        return
    
    try:
        u = await repo.get_user_by_id(user_id)
        if u:
            await bot.send_message(
                chat_id=int(u["tg_id"]),
                text=f"✅ Ваша заявка #{req_id} на вывод подтверждена!\nСумма: {format_stars(amount)}",
            )
    except Exception:
        pass
    
    await callback.answer("✅ Заявка подтверждена, средства списаны с пользователя", show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.edit_text(callback.message.text + "\n\n✅ ПОДТВЕРЖДЕНО")
    except Exception:
        pass


@router.callback_query(RequestCallback.filter(F.action == "reject"))
async def reject_request_cb(callback: CallbackQuery, callback_data: RequestCallback, state: FSMContext):
    await state.clear()
    await state.set_state(RequestRejectState.comment)
    await state.update_data(req_type=callback_data.req_type, req_id=int(callback_data.req_id), admin_msg=callback.message)
    await callback.answer()
    await callback.message.answer(
        f"❌ Укажите причину отказа для заявки #{callback_data.req_id} (отправьте 0 чтобы без комментария):"
    )


@router.message(RequestRejectState.comment)
async def reject_comment_step(message: Message, state: FSMContext, repo: Repository, bot: Bot):
    data = await state.get_data()
    req_type = data["req_type"]
    req_id = int(data["req_id"])
    comment_text = message.text.strip()
    if comment_text == "0":
        comment_text = None
    admin = await repo.get_user_by_tg_id(message.from_user.id)
    admin_id = int(admin["id"]) if admin else 0
    ok = False
    user_id = 0
    amount = 0
    
    # Обрабатываем только заявки на вывод
    if req_type == "wd":
        ok = await repo.reject_withdraw(req_id, admin_id, comment=comment_text)
        if ok:
            w = await repo.get_withdraw(req_id)
            user_id = int(w["user_id"])
            amount = int(w["amount"])
    else:
        await message.answer("❌ Неизвестный тип заявки.", reply_markup=admin_menu())
        await state.clear()
        return
    
    if not ok:
        await state.clear()
        await message.answer("⚠️ Заявка уже обработана или ошибка.", reply_markup=admin_menu())
        return
    
    try:
        u = await repo.get_user_by_id(user_id)
        if u:
            text = f"❌ Ваша заявка #{req_id} на вывод отклонена\nСумма: {format_stars(amount)}"
            if comment_text:
                text += f"\n\n💬 Комментарий: {comment_text}"
            await bot.send_message(chat_id=int(u["tg_id"]), text=text)
    except Exception:
        pass
    
    admin_msg = data.get("admin_msg")
    try:
        if admin_msg:
            await admin_msg.edit_reply_markup(reply_markup=None)
            await admin_msg.edit_text(admin_msg.text + "\n\n❌ ОТКЛОНЕНО")
    except Exception:
        pass
    
    await state.clear()
    await message.answer("✅ Заявка отклонена, пользователь уведомлён.", reply_markup=admin_menu())


@router.message(F.text == "📣 Рассылка (доп.)")
async def broadcast_start(message: Message, state: FSMContext):
    await clear_state(state)
    await state.set_state(BroadcastState.text)
    await message.answer(
        "📣 <b>Создание рассылки (шаг 1/2)</b>\n\n"
        "Отправьте текст рассылки. Поддерживаются:\n"
        "• Обычный текст\n"
        "• HTML-разметка (&lt;b&gt;, &lt;i&gt;, &lt;code&gt;, ссылки)\n\n"
        "Отправьте 0 для отмены."
    )


@router.message(BroadcastState.text)
async def broadcast_text_step(message: Message, state: FSMContext):
    text = message.text or ""
    if text.strip() == "0":
        await state.clear()
        await message.answer("❌ Рассылка отменена.", reply_markup=admin_menu())
        return
    if not message.text and not message.caption:
        await message.answer("❌ Отправьте текст рассылки (или 0 для отмены):")
        return
    content_text = message.text or message.caption or ""
    has_media = message.content_type not in ("text",)
    await state.update_data(
        text=content_text,
        content_type=message.content_type,
        has_media=has_media,
        message_copy=message.message_id,
        from_chat_id=message.chat.id,
    )
    preview = f"📋 <b>Предпросмотр рассылки:</b>\n\n{content_text}"
    if len(preview) > 3500:
        preview = preview[:3500] + "\n... (текст обрезан в предпросмотре)"
    await state.set_state(BroadcastState.confirm)
    await message.answer(
        preview
        + "\n\n"
        "📊 Отправить <b>ДА</b> — рассылка пойдёт всем пользователям бота.\n"
        "Любое другое сообщение — отмена."
    )


@router.message(BroadcastState.confirm)
async def broadcast_confirm_step(message: Message, state: FSMContext, repo: Repository, bot: Bot):
    if message.text.strip().lower() != "да":
        await state.clear()
        await message.answer("❌ Рассылка отменена.", reply_markup=admin_menu())
        return
    data = await state.get_data()
    users = await repo.get_all_users()
    total = len(users)
    if total == 0:
        await state.clear()
        await message.answer("⚠️ В базе нет пользователей для рассылки.", reply_markup=admin_menu())
        return
    status_msg = await message.answer(f"🚀 Запущена рассылка для {total} пользователей...")
    ok = 0
    fail = 0
    from_chat_id = data.get("from_chat_id", message.chat.id)
    message_copy = data.get("message_copy")
    for u in users:
        tg_id = int(u["tg_id"])
        try:
            if message_copy:
                await bot.copy_message(
                    chat_id=tg_id,
                    from_chat_id=from_chat_id,
                    message_id=message_copy,
                )
            else:
                await bot.send_message(chat_id=tg_id, text=data.get("text", ""))
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    try:
        await status_msg.edit_text(
            f"✅ Рассылка завершена!\n\nУспешно: {ok}\nНе удалось: {fail}\nВсего: {total}",
            reply_markup=admin_menu(),
        )
    except Exception:
        await message.answer(
            f"✅ Рассылка завершена!\n\nУспешно: {ok}\nНе удалось: {fail}\nВсего: {total}",
            reply_markup=admin_menu(),
        )
    await state.clear()
