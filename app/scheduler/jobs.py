from __future__ import annotations

import logging
from datetime import datetime, timedelta

from aiogram import Bot

from app.database.repo import Repository
from app.utils.giveaways import run_giveaway
from app.utils.levels import calc_level_from_dates
from app.config import settings

logger = logging.getLogger(__name__)


def _coerce_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
    return None


async def job_check_subscriptions(repo: Repository) -> None:
    from app.loader import bot, is_subscribed_to_channel

    logger.info("Running job_check_subscriptions")
    now = datetime.utcnow()
    users = await repo.get_all_users()
    for u in users:
        uid = int(u["id"])
        sub_end = _coerce_dt(u["subscription_end"])
        first = _coerce_dt(u["first_subscription_at"])
        cur = int(u["level"])
        try:
            is_channel_member = await is_subscribed_to_channel(bot, int(u["tg_id"]))
        except Exception:
            is_channel_member = False

        if is_channel_member and cur == 0:
            logger.info("Set initial L1 for active channel member %s", uid)
            await repo.set_user_level(uid, 1)
            cur = 1

        expired_at = sub_end + timedelta(days=settings.SUBSCRIPTION_GRACE_DAYS) if sub_end else None
        if not sub_end or (expired_at and expired_at < now):
            keep_level = is_channel_member
            if not keep_level and cur != 0:
                logger.info("Reset level for user %s: was L%s", uid, cur)
                await repo.reset_user_level(uid)
            elif keep_level and cur != 0:
                logger.info("Keep level L%s for user %s: real channel member", cur, uid)
            continue
        calc = calc_level_from_dates(first, sub_end)
        new_level = max(cur, calc)
        if new_level != cur:
            logger.info("Update level for user %s: L%s -> L%s", uid, cur, new_level)
            await repo.set_user_level(uid, new_level)


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
