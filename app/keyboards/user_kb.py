from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="👤 Профиль"),
        KeyboardButton(text="⭐ Баланс"),
    )
    builder.row(
        KeyboardButton(text="🔗 Реф-ссылка"),
        KeyboardButton(text="👥 Мои рефералы"),
    )
    builder.row(
        KeyboardButton(text="🏆 Топ рефоводов"),
        KeyboardButton(text="🛒 Маркет рефералов"),
    )
    builder.row(
        KeyboardButton(text="🎟️ Розыгрыши"),
    )
    builder.row(
        KeyboardButton(text="➕ Пополнить"),
        KeyboardButton(text="💸 Вывести"),
    )
    if is_admin:
        builder.row(KeyboardButton(text="⚙️ Админ-меню"))
    return builder.as_markup(resize_keyboard=True, input_field_placeholder="Выберите действие")


def back_to_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 В меню")]],
        resize_keyboard=True,
    )


def profile_kb(can_restore: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if can_restore:
        builder.button(text="♻️ Восстановить уровень (100 ⭐)", callback_data="restore_level")
    builder.button(text="📜 История транзакций", callback_data="transactions")
    builder.adjust(1)
    return builder.as_markup()


def balance_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Пополнить баланс", callback_data="deposit_start")
    builder.button(text="💸 Создать заявку на вывод", callback_data="withdraw_start")
    builder.button(text="📜 История транзакций", callback_data="transactions")
    builder.adjust(1)
    return builder.as_markup()


class MarketCallback(CallbackData, prefix="m"):
    action: str
    lot_id: int | None = None
    ref_id: int | None = None
    page: int = 0


def market_list_kb(lots, page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for lot in lots:
        builder.button(
            text=f"Лот #{lot['id']} · {lot['real_count'] or lot['count']}шт · {lot['price_per_one']}⭐/шт",
            callback_data=MarketCallback(action="view", lot_id=int(lot["id"])).pack(),
        )
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=MarketCallback(action="list", page=page - 1).pack()))
    nav.append(InlineKeyboardButton(text="🛍️ Активные лоты", callback_data=MarketCallback(action="active_lots").pack()))
    nav.append(InlineKeyboardButton(text="📢 Мои лоты", callback_data=MarketCallback(action="my_lots").pack()))
    nav.append(InlineKeyboardButton(text="➕ Выставить на продажу", callback_data=MarketCallback(action="create_lot").pack()))
    builder.row(*nav[:2])
    builder.row(*nav[2:])
    builder.adjust(1)
    return builder.as_markup()


def lot_view_kb(lot_id: int, is_seller: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_seller:
        builder.button(text="❌ Отменить лот", callback_data=MarketCallback(action="cancel", lot_id=lot_id).pack())
    else:
        builder.button(text="💳 Купить весь лот", callback_data=MarketCallback(action="buy", lot_id=lot_id).pack())
    builder.button(text="⬅️ К списку лотов", callback_data=MarketCallback(action="list").pack())
    builder.adjust(1)
    return builder.as_markup()


def my_lots_kb(lots) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for lot in lots:
        status_label = {"active": "🟢", "sold": "✅", "cancelled": "❌"}.get(lot["status"], "⚪")
        builder.button(
            text=f"{status_label} Лот #{lot['id']} · {lot['count']}шт · {lot['total_price']}⭐",
            callback_data=MarketCallback(action="view", lot_id=int(lot["id"])).pack(),
        )
    builder.button(text="⬅️ К маркету", callback_data=MarketCallback(action="list").pack())
    builder.adjust(1)
    return builder.as_markup()


def confirm_restore_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, восстановить за 100 ⭐", callback_data="restore_level_confirm")
    builder.button(text="❌ Отмена", callback_data="restore_level_cancel")
    builder.adjust(1)
    return builder.as_markup()


class LotCreateCallback(CallbackData, prefix="lc"):
    step: str
    value: str | None = None


def active_lots_kb(lots_with_refs, page: int = 0) -> InlineKeyboardMarkup:
    """Клавиатура для отображения всех рефералов из активных лотов"""
    builder = InlineKeyboardBuilder()
    
    # Каждый реферал — отдельная кнопка
    for item in lots_with_refs:
        ref_name = item["full_name"] or "Пользователь"
        username = item["username"] or ""
        if username:
            ref_name = f"@{username}"
        level = item["level"] or 0
        price = item["price_per_one"] or 0
        ref_id = item["ref_row_id"]
        
        builder.button(
            text=f"{ref_name} · L{level} · {price}⭐",
            callback_data=MarketCallback(action="buy_ref", ref_id=int(ref_id)).pack(),
        )
    
    builder.button(text="⬅️ К списку лотов", callback_data=MarketCallback(action="list").pack())
    builder.adjust(1)
    return builder.as_markup()


def confirm_buy_ref_kb(ref_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения покупки реферала"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Да, купить",
        callback_data=MarketCallback(action="confirm_buy_ref", ref_id=ref_id).pack()
    )
    builder.button(
        text="❌ Отмена",
        callback_data=MarketCallback(action="active_lots").pack()
    )
    builder.adjust(1)
    return builder.as_markup()


def lot_ref_selection_kb(refs, selected_ids: set[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ref in refs:
        ref_id = int(ref["ref_id"])
        mark = "✅" if ref_id in selected_ids else "⬜"
        builder.button(
            text=f"{mark} {format_market_ref_name(ref)} · L{ref['level']}",
            callback_data=LotCreateCallback(step="toggle", value=str(ref_id)).pack(),
        )
    builder.button(text="✅ Готово", callback_data=LotCreateCallback(step="done").pack())
    builder.button(text="❌ Отмена", callback_data=LotCreateCallback(step="cancel").pack())
    builder.adjust(1)
    return builder.as_markup()


def format_market_ref_name(ref) -> str:
    username = ref["username"] if "username" in ref.keys() else None
    full_name = ref["full_name"] if "full_name" in ref.keys() else "Пользователь"
    return f"@{username}" if username else full_name
