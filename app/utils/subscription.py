from __future__ import annotations

from datetime import datetime, timedelta

from app.config import settings
from app.database.repo import Repository, TXN_RENEWAL_BONUS


async def renew_subscription(repo: Repository, user_id: int) -> None:
    user = await repo.get_user_by_id(user_id)
    if not user:
        return
    now = datetime.utcnow()
    current_end = user["subscription_end"]
    if isinstance(current_end, str):
        try:
            current_end = datetime.fromisoformat(current_end)
        except ValueError:
            current_end = None
    renewal_deadline = (
        current_end + timedelta(days=settings.SUBSCRIPTION_GRACE_DAYS)
        if current_end
        else None
    )
    is_on_time_renewal = renewal_deadline is not None and now <= renewal_deadline
    if current_end and current_end > now:
        base = current_end
    else:
        base = now
    new_end = datetime.fromtimestamp(base.timestamp() + settings.SUBSCRIPTION_DAYS * 86400)
    if not user["first_subscription_at"]:
        await repo._exec(
            "UPDATE users SET first_subscription_at = ? WHERE id = ?",
            (now, user_id),
        )
    await repo._exec(
        "UPDATE users SET subscription_end = ? WHERE id = ?",
        (new_end, user_id),
    )
    ref = await repo.get_referral_by_referee(user_id)
    if ref and is_on_time_renewal:
        owner_id = int(ref["owner_id"])
        await repo.add_stars(owner_id, settings.RENEWAL_BONUS, TXN_RENEWAL_BONUS, related_id=user_id)


async def check_and_renew_from_channel(repo: Repository, user_id: int, bot) -> bool:
    user = await repo.get_user_by_id(user_id)
    if not user or not user["subscription_end"]:
        return False

    current_end = user["subscription_end"]
    if isinstance(current_end, str):
        try:
            current_end = datetime.fromisoformat(current_end)
        except ValueError:
            return False

    now = datetime.utcnow()
    deadline = current_end + timedelta(days=settings.SUBSCRIPTION_GRACE_DAYS)
    if current_end >= now or now > deadline:
        return False

    from app.loader import is_subscribed_to_channel

    if not await is_subscribed_to_channel(bot, int(user["tg_id"])):
        return False

    await renew_subscription(repo, user_id)
    return True
