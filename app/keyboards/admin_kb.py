from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def admin_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🎲 Создать розыгрыш"), KeyboardButton(text="🎯 Назначить уровень"))
    builder.row(KeyboardButton(text="📋 Список заявок"), KeyboardButton(text="📣 Рассылка (доп.)"))
    builder.row(KeyboardButton(text="📊 Статистика"))
    builder.row(KeyboardButton(text="🔙 В меню"))
    return builder.as_markup(resize_keyboard=True, input_field_placeholder="Админ-панель")


class RequestCallback(CallbackData, prefix="req"):
    action: str
    req_type: str  # dep | wd
    req_id: int


def request_action_kb(req_type: str, req_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Подтвердить",
        callback_data=RequestCallback(action="approve", req_type=req_type, req_id=req_id).pack(),
    )
    builder.button(
        text="❌ Отклонить",
        callback_data=RequestCallback(action="reject", req_type=req_type, req_id=req_id).pack(),
    )
    builder.adjust(2)
    return builder.as_markup()


class GiveawayCallback(CallbackData, prefix="ga"):
    action: str
    ga_id: int | None = None


class StatsCallback(CallbackData, prefix="stats"):
    action: str
    level: int | None = None


def statistics_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Рефералы по уровням", callback_data=StatsCallback(action="levels").pack())
    builder.button(text="🆕 10 последних подписок", callback_data=StatsCallback(action="subscriptions").pack())
    builder.button(text="🔁 Последние продления", callback_data=StatsCallback(action="renewals").pack())
    builder.adjust(1)
    return builder.as_markup()


def level_statistics_kb(levels: list[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for level in levels:
        builder.button(text=f"L{level}", callback_data=StatsCallback(action="level", level=level).pack())
    builder.adjust(4)
    return builder.as_markup()


def giveaway_admin_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🆕 Создать новый розыгрыш", callback_data=GiveawayCallback(action="new").pack())
    builder.button(text="❌ Отменить конкурс", callback_data=GiveawayCallback(action="cancel_menu").pack())
    builder.button(text="⏩ Закончить досрочно", callback_data=GiveawayCallback(action="finish_menu").pack())
    builder.adjust(1)
    return builder.as_markup()
