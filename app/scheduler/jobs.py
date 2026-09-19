from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from app.database.repo import Repository
from app.utils.giveaways import run_giveaway
from app.utils.formatters import format_user_name
from app.config import settings

logger = logging.getLogger(__name__)


def _coerce_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
    return None


async def job_check_subscriptions(repo: Repository) -> None:
    from app.loader import bot, get_channel_member

    logger.info("Checking channel subscription expiration dates")
    for user in await repo.get_all_users():
        try:
            member = await get_channel_member(bot, int(user["tg_id"]))
            channel_end = _coerce_dt(getattr(member, "until_date", None)) if member else None
            if channel_end and await repo.apply_channel_subscription_end(int(user["id"]), channel_end):
                referral = await repo.get_referral_by_referee(int(user["id"]))
                if referral:
                    owner = await repo.get_user_by_id(int(referral["owner_id"]))
                    if owner:
                        try:
                            await bot.send_message(
                                chat_id=int(owner["tg_id"]),
                                text=(
                                    f"🔁 {format_user_name(user)} продлил подписку.\n"
                                    f"Вам начислено {settings.RENEWAL_BONUS} ⭐."
                                ),
                            )
                        except TelegramBadRequest as exc:
                            logger.warning(
                                "Could not notify referral owner %s (tg_id=%s): %s",
                                owner["id"],
                                owner["tg_id"],
                                exc,
                            )
                logger.info("Recorded channel subscription update for user %s", user["id"])
        except Exception:
            logger.exception("Failed to check channel subscription for user %s", user["id"])


async def job_run_giveaways(repo: Repository, bot: Bot) -> None:
    logger.info("=" * 60)
    now = datetime.utcnow()
    logger.info("job_run_giveaways START, UTC now = %s", now.isoformat())
    all_active = await repo._rows(
        "SELECT * FROM giveaways WHERE status = 'active' ORDER BY id"
    )
    logger.info("Total active giveaways in DB: %s", len(all_active))
    for ga in all_active:
        ends_raw = ga["ends_at"]
        ends_dt = _coerce_dt(ends_raw)
        logger.info(
            "  Giveaway #%s status=%s ends_at(raw)=%s ends_at(utc)=%s channel_msg_id=%s winner_id=%s",
            ga["id"],
            ga["status"],
            repr(ends_raw),
            ends_dt.isoformat() if ends_dt else "None",
            ga["channel_msg_id"],
            ga["winner_id"],
        )
        if ends_dt is None:
            logger.warning("  Giveaway #%s: cannot parse ends_at, skipping", ga["id"])
            continue
        if ends_dt > now:
            diff = ends_dt - now
            logger.info("  Giveaway #%s: NOT YET, %s remaining", ga["id"], diff)
            continue
        logger.info("  Giveaway #%s: TIME HAS COME! Running finish logic...", ga["id"])
        try:
            await run_giveaway(repo, bot, ga, now=now)
            logger.info("  Giveaway #%s: FINISHED successfully", ga["id"])
        except Exception as e:
            logger.exception("  Giveaway #%s: ERROR during finish: %s", ga["id"], e)
    logger.info("job_run_giveaways DONE")
    logger.info("=" * 60)
