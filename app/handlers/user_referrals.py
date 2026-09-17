from __future__ import annotations

import uuid

from aiogram import Bot, Router, F
from aiogram.types import Message

from app.config import settings
from app.database.repo import Repository
from app.handlers.common import ensure_user
from app.keyboards.user_kb import back_to_menu
from app.loader import is_subscribed_to_channel
from app.utils.formatters import format_stars, format_user_name, format_subscription_end

router = Router()


def _make_unique_code() -> str:
    return uuid.uuid4().hex[:10]


@router.message(F.text == "🔗 Реф-ссылка")
async def my_referral_link(message: Message, repo: Repository, bot: Bot):
    uid = await ensure_user(repo, message)
    if not settings.CHANNEL_ID:
        await message.answer("⚠️ Канал ещё не настроен администратором.")
        return
    is_subscribed = await is_subscribed_to_channel(bot, message.from_user.id)
    if not is_subscribed:
        await message.answer(
            "⚠️ Создавать реферальные ссылки могут только подписчики канала.\n\n"
            "Сначала оформите подписку на канал.",
            reply_markup=back_to_menu(),
        )
        return
    existing = await repo.get_active_link_by_owner(uid, settings.CHANNEL_ID)
    if existing:
        await message.answer(
            "🔗 Ваша персональная реферальная ссылка:\n\n"
            f"<b>Ссылка на подписку в канал:</b>\n{existing['invite_link']}",
            disable_web_page_preview=True,
            reply_markup=back_to_menu(),
        )
        return
    code = _make_unique_code()
    try:
        invite = await bot.create_chat_subscription_invite_link(
            chat_id=settings.CHANNEL_ID,
            name=f"ref_{uid}_{code}",
            subscription_period=2592000,
            subscription_price=settings.REF_LINK_COST,
        )
    except Exception as e:
        await message.answer(
            f"❌ Не удалось создать инвайт-ссылку.\n"
            f"Ошибка: {e}"
        )
        return
    await repo.create_referral_link(uid, code, settings.CHANNEL_ID, invite.invite_link)
    await message.answer(
        "✅ Реферальная ссылка создана!\n\n"
        f"Стоимость месячной подписки по ссылке: {format_stars(settings.REF_LINK_COST)}\n\n"
        f"<b>Ссылка на подписку в канал:</b>\n{invite.invite_link}\n\n"
        f"💰 За каждого приглашённого вы получите +{settings.REF_BONUS} ⭐, "
        f"за каждое его продление +{settings.RENEWAL_BONUS} ⭐.",
        disable_web_page_preview=True,
        reply_markup=back_to_menu(),
    )


@router.message(F.text == "👥 Мои рефералы")
async def my_referrals(message: Message, repo: Repository):
    uid = await ensure_user(repo, message)
    refs = await repo.get_referrals_by_owner(uid)
    if not refs:
        await message.answer(
            "👥 У вас пока нет приглашённых рефералов.\n\n"
            "Создайте реф-ссылку в меню и поделитесь ею!",
            reply_markup=back_to_menu(),
        )
        return
    total = len(refs)
    on_market = sum(1 for r in refs if int(r["on_market"]) == 1)
    lines = [f"👥 Ваши рефералы (всего {total}, на маркете {on_market}):\n"]
    for r in refs:
        mark = "🛒" if int(r["on_market"]) == 1 else "👤"
        lines.append(
            f"{mark} {format_user_name(r)} — L{r['level']} — {format_subscription_end(r['subscription_end'])}"
        )
    renewals = await repo.get_renewals_by_owner(uid)
    if renewals:
        lines.append("\n🔁 Продления по вашей ссылке:")
        lines.extend(
            f"• {format_user_name(renewal)} — {format_stars(int(renewal['amount']))}"
            for renewal in renewals
        )
    if len(lines) > 60:
        lines = lines[:60]
        lines.append("... показаны первые 60")
    await message.answer("\n".join(lines), reply_markup=back_to_menu())
