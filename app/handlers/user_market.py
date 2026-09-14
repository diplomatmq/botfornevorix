from __future__ import annotations

from aiogram import Bot, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database.repo import Repository
from app.handlers.common import ensure_user, clear_state
from app.keyboards.user_kb import (
    MarketCallback,
    back_to_menu,
    lot_view_kb,
    market_list_kb,
    my_lots_kb,
    active_lots_kb,
    confirm_buy_ref_kb,
)
from app.states.form_states import CreateLotState
from app.utils.formatters import format_stars, format_user_name, format_subscription_end

router = Router()


@router.message(F.text == "🛒 Маркет рефералов")
async def market_root(message: Message, repo: Repository, state: FSMContext):
    await clear_state(state)
    await ensure_user(repo, message)
    lots = await repo.get_active_lots()
    await message.answer(
        "🛒 Маркет рефералов\n\n"
        "Здесь можно купить или выставить на продажу своих рефералов.\n\n"
        "📢 Как выставить рефералов:\n"
        "1. Нажмите «➕ Выставить на продажу».\n"
        "2. Выберите количество доступных рефералов.\n"
        "3. Укажите цену за одного реферала.\n"
        "4. Проверьте список и напишите «ДА».\n\n"
        "На продажу можно выставить только рефералов, которые еще не находятся в другом лоте.",
        reply_markup=back_to_menu(),
    )
    await message.answer(
        "📋 Активные лоты:",
        reply_markup=market_list_kb(lots, page=0),
    )


@router.callback_query(MarketCallback.filter(F.action == "list"))
async def market_list_cb(callback: CallbackQuery, callback_data: MarketCallback, repo: Repository):
    await ensure_user(repo, callback.message)
    page = max(0, callback_data.page)
    lots = await repo.get_active_lots(limit=50)
    per_page = 5
    start = page * per_page
    end = start + per_page
    page_lots = lots[start:end]
    text = "📋 Активные лоты:\n" if page_lots else "Лоты на этой странице отсутствуют."
    await callback.message.edit_text(text, reply_markup=market_list_kb(page_lots, page=page, per_page=per_page))
    await callback.answer()


@router.callback_query(MarketCallback.filter(F.action == "my_lots"))
async def my_lots_cb(callback: CallbackQuery, repo: Repository):
    uid = await ensure_user(repo, callback.message)
    lots = await repo.get_lots_by_seller(uid)
    if not lots:
        await callback.answer("У вас пока нет лотов", show_alert=True)
        return
    await callback.message.edit_text("📢 Ваши лоты:", reply_markup=my_lots_kb(lots))
    await callback.answer()


@router.callback_query(MarketCallback.filter(F.action == "view"))
async def lot_view_cb(callback: CallbackQuery, callback_data: MarketCallback, repo: Repository):
    uid = await ensure_user(repo, callback.message)
    lot_id = int(callback_data.lot_id)
    lot = await repo.get_lot_by_id(lot_id)
    if not lot:
        await callback.answer("Лот не найден", show_alert=True)
        return
    items = await repo.get_lot_items(lot_id)
    seller = await repo.get_user_by_id(int(lot["seller_id"]))
    lines = [
        f"🛍️ <b>Лот #{lot['id']}</b>",
        f"Продавец: {format_user_name(seller) if seller else 'id' + str(lot['seller_id'])}",
        f"Количество рефералов: {int(lot['count'])}",
        f"Цена за штуку: {format_stars(int(lot['price_per_one']))}",
        f"Итого: {format_stars(int(lot['total_price']))}",
        "",
    ]
    if items:
        lines.append("👥 Рефералы в лоте:")
        for it in items:
            lines.append(
                f"  • {format_user_name(it)} · L{it['level']} · {format_subscription_end(it['subscription_end'])}"
            )
    is_seller = int(lot["seller_id"]) == uid
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=lot_view_kb(lot_id, is_seller=is_seller)
    )
    await callback.answer()


@router.callback_query(MarketCallback.filter(F.action == "cancel"))
async def cancel_lot_cb(callback: CallbackQuery, callback_data: MarketCallback, repo: Repository):
    uid = await ensure_user(repo, callback.message)
    lot_id = int(callback_data.lot_id)
    ok = await repo.cancel_lot(lot_id, uid)
    if not ok:
        await callback.answer("Не удалось отменить лот", show_alert=True)
        return
    await callback.answer("✅ Лот отменён", show_alert=True)
    lots = await repo.get_active_lots()
    await callback.message.edit_text(
        "✅ Лот отменён. Возвращаемся в список лотов.",
        reply_markup=market_list_kb(lots),
    )


@router.callback_query(MarketCallback.filter(F.action == "buy"))
async def buy_lot_cb(callback: CallbackQuery, callback_data: MarketCallback, repo: Repository, bot: Bot):
    uid = await ensure_user(repo, callback.message)
    lot_id = int(callback_data.lot_id)
    lot = await repo.get_lot_by_id(lot_id)
    if not lot:
        await callback.answer("Лот не найден", show_alert=True)
        return
    if int(lot["seller_id"]) == uid:
        await callback.answer("Нельзя купить свой лот", show_alert=True)
        return
    ok = await repo.buy_lot(lot_id, uid)
    if not ok:
        u = await repo.get_user_by_id(uid)
        if u and int(u["balance"]) < int(lot["total_price"]):
            await callback.answer(
                f"❌ Недостаточно средств. Нужно {format_stars(int(lot['total_price']))}",
                show_alert=True,
            )
        else:
            await callback.answer("❌ Не удалось купить лот", show_alert=True)
        return
    seller_id = int(lot["seller_id"])
    buyer = await repo.get_user_by_id(uid)
    seller = await repo.get_user_by_id(seller_id)
    try:
        if seller:
            await bot.send_message(
                chat_id=int(seller["tg_id"]),
                text=(
                    f"✅ Ваш лот #{lot['id']} куплен!\n"
                    f"Начислено: {format_stars(int(lot['total_price']))}"
                ),
            )
    except Exception:
        pass
    await callback.answer(
        f"✅ Вы купили лот #{lot['id']} за {format_stars(int(lot['total_price']))}!",
        show_alert=True,
    )
    lots = await repo.get_active_lots()
    await callback.message.edit_text(
        "✅ Покупка совершена успешно.", reply_markup=market_list_kb(lots)
    )


@router.callback_query(MarketCallback.filter(F.action == "create_lot"))
async def create_lot_start_cb(callback: CallbackQuery, repo: Repository, state: FSMContext):
    uid = await ensure_user(repo, callback)
    refs = await repo.get_referrals_by_owner(uid, include_on_market=False)
    if not refs:
        await callback.answer(
            "У вас нет рефералов, доступных для продажи.",
            show_alert=True,
        )
        return
    await state.set_state(CreateLotState.count)
    await state.update_data(available_refs=[{"ref_id": int(r["ref_id"]), "tg_id": r["tg_id"]} for r in refs])
    lines = [
        f"💎 Доступно для продажи: {len(refs)} рефералов.",
        "Введите, сколько выставить на продажу.",
        "Будут выбраны первые рефералы из списка ниже:",
    ]
    for r in refs[:15]:
        lines.append(f"  • {format_user_name(r)} · L{r['level']}")
    if len(refs) > 15:
        lines.append(f"  ... и ещё {len(refs) - 15}")
    await callback.message.edit_text("\n".join(lines), reply_markup=None)
    await callback.answer()


@router.message(CreateLotState.count)
async def lot_count_step(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Введите только целое число:")
        return
    count = int(text)
    data = await state.get_data()
    available = data.get("available_refs") or []
    if count <= 0 or count > len(available):
        await message.answer(f"❌ Введите число от 1 до {len(available)}:")
        return
    await state.update_data(count=count)
    await state.set_state(CreateLotState.price)
    await message.answer("💸 Введите цену за 1 реферала (звёзд):")


@router.message(CreateLotState.price)
async def lot_price_step(message: Message, state: FSMContext, repo: Repository):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Введите только целое число:")
        return
    price = int(text)
    if price <= 0:
        await message.answer("❌ Цена должна быть больше нуля:")
        return
    data = await state.get_data()
    count = int(data["count"])
    available = list(data.get("available_refs") or [])
    chosen = available[:count]
    ref_db_ids = [int(r["ref_id"]) for r in chosen]
    uid = await ensure_user(repo, message)
    levels = []
    for rid in ref_db_ids:
        ref_row = await repo.get_referral_by_id(rid)
        if ref_row:
            u = await repo.get_user_by_id(int(ref_row["referee_id"]))
            if u:
                levels.append(int(u["level"]))
    lmin = min(levels) if levels else None
    lmax = max(levels) if levels else None
    total = count * price
    await state.update_data(price=price, chosen_ref_ids=ref_db_ids, total=total, lmin=lmin, lmax=lmax)
    await state.set_state(CreateLotState.confirm)
    preview_lines = [
        "📋 Подтвердите лот:\n",
        f"Количество рефералов: {count}",
        f"Цена за штуку: {format_stars(price)}",
        f"Итого к получению: {format_stars(total)}",
        f"Уровни рефералов: L{lmin}–L{lmax}" if lmin is not None else "",
        "",
        "Введите: <b>ДА</b> для создания лота или любое другое сообщение для отмены.",
    ]
    await message.answer("\n".join([l for l in preview_lines if l]))


@router.message(CreateLotState.confirm)
async def lot_confirm_step(message: Message, state: FSMContext, repo: Repository):
    text = message.text.strip().lower()
    if text != "да":
        await state.clear()
        await message.answer("❌ Создание лота отменено.", reply_markup=back_to_menu())
        return
    data = await state.get_data()
    count = int(data["count"])
    price = int(data["price"])
    ref_ids = list(data["chosen_ref_ids"] or [])
    lmin = data.get("lmin")
    lmax = data.get("lmax")
    uid = await ensure_user(repo, message)
    if not ref_ids or len(ref_ids) != count:
        await state.clear()
        await message.answer("❌ Ошибка данных лота.", reply_markup=back_to_menu())
        return
    lot_id = await repo.create_market_lot(uid, count, price, ref_ids, level_min=lmin, level_max=lmax)
    await state.clear()
    await message.answer(
        f"✅ Лот #{lot_id} создан.\n"
        f"К выставлению: {count} рефералов по {format_stars(price)} за штуку.\n"
        f"Итого при продаже: {format_stars(count * price)}",
        reply_markup=back_to_menu(),
    )


@router.callback_query(MarketCallback.filter(F.action == "active_lots"))
async def active_lots_cb(callback: CallbackQuery, repo: Repository):
    """Показать все рефералы из активных лотов"""
    await ensure_user(repo, callback.message)
    
    # Получаем все рефералы из активных лотов
    items = await repo.get_all_active_lot_items()
    
    if not items:
        await callback.answer("Нет активных лотов с рефералами", show_alert=True)
        return
    
    text = f"🛍️ <b>Активные лоты ({len(items)} рефералов):</b>\n\n"
    text += "Выберите реферала для покупки:"
    
    await callback.message.edit_text(text, reply_markup=active_lots_kb(items))
    await callback.answer()


@router.callback_query(MarketCallback.filter(F.action == "buy_ref"))
async def buy_ref_cb(callback: CallbackQuery, callback_data: MarketCallback, repo: Repository):
    """Показать подтверждение покупки реферала"""
    uid = await ensure_user(repo, callback.message)
    ref_id = int(callback_data.ref_id)
    
    item = await repo.get_lot_item_by_ref_id(ref_id)
    if not item:
        await callback.answer("Реферал не найден", show_alert=True)
        return
    
    if int(item["seller_id"]) == uid:
        await callback.answer("Это ваш реферал", show_alert=True)
        return
    
    price = int(item["price_per_one"])
    ref_name = format_user_name(item)
    level = int(item["level"])
    sub_end = format_subscription_end(item.get("subscription_end"))
    
    text = (
        f"🛍️ <b>Подтверждение покупки</b>\n\n"
        f"👤 Реферал: {ref_name}\n"
        f"📊 Уровень: L{level}\n"
        f"💎 Подписка: {sub_end}\n"
        f"💰 Цена: {format_stars(price)}\n\n"
        f"Подтвердите покупку:"
    )
    
    await callback.message.edit_text(text, reply_markup=confirm_buy_ref_kb(ref_id))
    await callback.answer()


@router.callback_query(MarketCallback.filter(F.action == "confirm_buy_ref"))
async def confirm_buy_ref_cb(callback: CallbackQuery, callback_data: MarketCallback, repo: Repository, bot: Bot):
    """Подтвердить покупку реферала"""
    uid = await ensure_user(repo, callback.message)
    ref_id = int(callback_data.ref_id)
    
    item = await repo.get_lot_item_by_ref_id(ref_id)
    if not item:
        await callback.answer("❌ Реферал не найден", show_alert=True)
        return
    
    if int(item["seller_id"]) == uid:
        await callback.answer("❌ Нельзя купить своего реферала", show_alert=True)
        return
    
    # Проверяем баланс
    buyer = await repo.get_user_by_id(uid)
    price = int(item["price_per_one"])
    
    if not buyer or int(buyer["balance"]) < price:
        await callback.answer(
            f"❌ Недостаточно средств. Нужно {format_stars(price)}",
            show_alert=True
        )
        return
    
    # Покупаем
    ok = await repo.buy_single_referral(ref_id, uid)
    
    if not ok:
        await callback.answer("❌ Не удалось совершить покупку", show_alert=True)
        return
    
    # Уведомляем продавца
    seller_id = int(item["seller_id"])
    seller = await repo.get_user_by_id(seller_id)
    ref_name = format_user_name(item)
    
    try:
        if seller:
            await bot.send_message(
                chat_id=int(seller["tg_id"]),
                text=(
                    f"✅ Ваш реферал продан!\n"
                    f"👤 Реферал: {ref_name}\n"
                    f"💰 Получено: {format_stars(price)}"
                )
            )
    except Exception:
        pass
    
    await callback.answer(
        f"✅ Вы купили реферала {ref_name} за {format_stars(price)}!",
        show_alert=True
    )
    
    # Возвращаемся к списку активных лотов
    items = await repo.get_all_active_lot_items()
    if items:
        text = f"🛍️ <b>Активные лоты ({len(items)} рефералов):</b>\n\n"
        text += "Выберите реферала для покупки:"
        await callback.message.edit_text(text, reply_markup=active_lots_kb(items))
    else:
        lots = await repo.get_active_lots()
        await callback.message.edit_text(
            "✅ Покупка совершена! Все лоты проданы.",
            reply_markup=market_list_kb(lots)
        )
