from __future__ import annotations

from aiogram import Bot, Router, F
from aiogram.filters.callback_data import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery

from app.database.repo import Repository
from app.handlers.common import ensure_user, clear_state
from app.keyboards.user_kb import back_to_menu
from app.states.form_states import WithdrawRequestState
from app.utils.formatters import format_stars, format_user_name

router = Router()


@router.callback_query(F.data == "deposit_start")
@router.message(F.text == "➕ Пополнить")
async def deposit_start(event, repo: Repository, state: FSMContext, bot: Bot):
    """Пополнение через Telegram Stars"""
    if isinstance(event, CallbackQuery):
        message = event.message
        await event.answer()
    else:
        message = event
    await ensure_user(repo, message)
    await clear_state(state)
    
    await message.answer(
        "⭐ <b>Пополнение баланса через Telegram Stars</b>\n\n"
        "Введите сумму звёзд для пополнения (целое число):",
        reply_markup=back_to_menu(),
    )
    await state.set_state("awaiting_stars_amount")


@router.message(F.text, F.func(lambda m: m.text.strip().isdigit()))
async def deposit_amount_stars(message: Message, state: FSMContext, bot: Bot, repo: Repository):
    """Создание инвойса для оплаты звездами"""
    current_state = await state.get_state()
    if current_state != "awaiting_stars_amount":
        return
    
    amount = int(message.text.strip())
    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше нуля:")
        return
    
    uid = await ensure_user(repo, message)
    u = await repo.get_user_by_id(uid)
    
    # Создаём инвойс для оплаты звёздами
    await bot.send_invoice(
        chat_id=message.chat.id,
        title=f"Пополнение баланса",
        description=f"Пополнение баланса на {amount} ⭐",
        payload=f"deposit_{uid}_{amount}",
        provider_token="",  # Для Stars оставляем пустым
        currency="XTR",  # Telegram Stars
        prices=[LabeledPrice(label=f"{amount} звёзд", amount=amount)],
    )
    
    await state.clear()


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    """Подтверждение платежа перед оплатой"""
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message, repo: Repository, bot: Bot):
    """Обработка успешного платежа"""
    payment = message.successful_payment
    payload = payment.invoice_payload

    # Парсим payload: "deposit_{uid}_{amount}"
    try:
        parts = payload.split("_")
        uid = int(parts[1])
        amount = int(parts[2])
    except (IndexError, ValueError):
        await message.answer("❌ Ошибка обработки платежа. Обратитесь в поддержку.")
        return
    
    # Начисляем звёзды на баланс
    await repo.add_stars(uid, amount, "deposit")
    
    u = await repo.get_user_by_id(uid)
    await message.answer(
        f"✅ Оплата успешна!\n\n"
        f"Начислено: {format_stars(amount)}\n"
        f"Ваш баланс: {format_stars(int(u['balance']))}",
        reply_markup=back_to_menu(),
    )


@router.callback_query(F.data == "withdraw_start")
@router.message(F.text == "💸 Вывести")
async def withdraw_start(event, repo: Repository, state: FSMContext):
    if isinstance(event, CallbackQuery):
        message = event.message
        await event.answer()
    else:
        message = event
    uid = await ensure_user(repo, message)
    await clear_state(state)
    u = await repo.get_user_by_id(uid)
    if int(u["balance"]) <= 0:
        await message.answer("❌ Ваш баланс пуст.", reply_markup=back_to_menu())
        return
    await state.set_state(WithdrawRequestState.amount)
    await message.answer(
        f"💸 Заявка на вывод\nДоступный баланс: {format_stars(int(u['balance']))}\n\n"
        "Введите сумму к выводу:",
        reply_markup=back_to_menu(),
    )


@router.message(WithdrawRequestState.amount)
async def withdraw_amount_step(message: Message, state: FSMContext, repo: Repository):
    uid = await ensure_user(repo, message)
    u = await repo.get_user_by_id(uid)
    t = message.text.strip()
    if not t.isdigit() or int(t) <= 0:
        await message.answer("❌ Введите сумму целым числом больше нуля:")
        return
    amount = int(t)
    if amount > int(u["balance"]):
        await message.answer(f"❌ Недостаточно средств. Баланс {format_stars(int(u['balance']))}:")
        return
    await state.update_data(amount=amount)
    await state.set_state(WithdrawRequestState.details)
    await message.answer(
        "🏦 Введите реквизиты для вывода (номер карты, кошелёк и т.п.):"
    )


@router.message(WithdrawRequestState.details)
async def withdraw_details_step(message: Message, state: FSMContext, repo: Repository, bot: Bot):
    uid = await ensure_user(repo, message)
    details = message.text.strip()[:1000]
    data = await state.get_data()
    amount = int(data["amount"])
    cur_user = await repo.get_user_by_id(uid)
    if int(cur_user["balance"]) < amount:
        await message.answer("❌ Недостаточно средств на балансе.")
        await state.clear()
        return
    req_id = await repo.create_withdraw_request(uid, amount, details)
    u = await repo.get_user_by_id(uid)
    
    caption = (
        f"💸 Новая заявка на ВЫВОД #{req_id}\n"
        f"Пользователь: {format_user_name(u)}\n"
        f"Сумма: {format_stars(amount)}\n"
        f"Реквизиты: {details}\n\n"
        f"Откройте «📋 Список заявок» и отправьте номер {req_id} для обработки."
    )
    
    # Уведомляем админов
    try:
        for aid in __import__("app.config", fromlist=["settings"]).settings.ADMIN_IDS:
            try:
                await bot.send_message(chat_id=aid, text=caption)
            except Exception:
                pass
    except Exception:
        pass
    
    await state.clear()
    await message.answer(
        f"✅ Заявка на вывод #{req_id} создана.\n"
        f"Сумма: {format_stars(amount)}\n"
        "Ожидайте обработки администратором.",
        reply_markup=back_to_menu(),
    )
