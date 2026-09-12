from __future__ import annotations

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import settings
from app.database.repo import Repository
from app.loader import bot as default_bot
from app.utils.subscription import check_and_renew_from_channel


async def ensure_user(repo: Repository, message: Message) -> int:
    tg_id = message.from_user.id
    username = message.from_user.username
    full_name = (message.from_user.full_name or str(tg_id))[:255]
    existing = await repo.get_user_by_tg_id(tg_id)
    if existing:
        if existing["username"] != username or existing["full_name"] != full_name:
            await repo.update_user_meta(tg_id, username, full_name)
        return int(existing["id"])
    return await repo.create_user(tg_id, username, full_name)


async def handle_referral_code(repo: Repository, user_db_id: int, code: str) -> None:
    link = await repo.get_link_by_code(code)
    if not link:
        return
    await _attach_referral(repo, user_db_id, link)


async def _attach_referral(repo: Repository, user_db_id: int, link) -> None:
    existing_ref = await repo.get_referral_by_referee(user_db_id)
    if existing_ref:
        return
    owner_id = int(link["owner_id"])
    if owner_id == user_db_id:
        return
    await repo.create_referral_relation(user_db_id, owner_id)
    await repo.add_stars(owner_id, settings.REF_BONUS, "ref_bonus", related_id=user_db_id)
    user_row = await repo.get_user_by_id(user_db_id)
    if user_row and not user_row["subscription_end"]:
        await repo.activate_subscription(user_db_id, settings.SUBSCRIPTION_DAYS)
        try:
            await default_bot.send_message(
                chat_id=(await repo.get_user_by_id(owner_id))["tg_id"],
                text=f"🎁 +{settings.REF_BONUS} ⭐ за нового реферала!",
            )
        except Exception:
            pass


async def handle_referral_invite(
    repo: Repository,
    tg_id: int,
    username: str | None,
    full_name: str,
    invite_link: str,
) -> bool:
    link = await repo.get_link_by_invite_link(invite_link)
    if not link:
        return False
    user = await repo.get_user_by_tg_id(tg_id)
    user_db_id = (
        int(user["id"])
        if user
        else await repo.create_user(tg_id, username, full_name[:255])
    )
    existing_ref = await repo.get_referral_by_referee(user_db_id)
    if existing_ref:
        return await check_and_renew_from_channel(repo, user_db_id, default_bot)
    await _attach_referral(repo, user_db_id, link)
    return True


async def check_referral_renewal(repo: Repository, user_db_id: int) -> bool:
    renewed = await check_and_renew_from_channel(repo, user_db_id, default_bot)
    if not renewed:
        return False
    ref = await repo.get_referral_by_referee(user_db_id)
    if ref:
        try:
            owner = await repo.get_user_by_id(int(ref["owner_id"]))
            if owner:
                await default_bot.send_message(
                    chat_id=int(owner["tg_id"]),
                    text=f"🎁 +{settings.RENEWAL_BONUS} ⭐ за продление подписки рефералом!",
                )
        except Exception:
            pass
    return True


async def send_admin_notice(text: str, bot: Bot | None = None, parse_mode: str = "HTML") -> None:
    b = bot or default_bot
    for aid in settings.ADMIN_IDS:
        try:
            await b.send_message(chat_id=aid, text=text, parse_mode=parse_mode)
        except Exception:
            pass


async def clear_state(state: FSMContext) -> None:
    try:
        await state.clear()
    except Exception:
        pass
