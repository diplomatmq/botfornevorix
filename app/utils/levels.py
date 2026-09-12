from __future__ import annotations

from datetime import datetime
from typing import Iterable


def calc_level_from_dates(first_subscription_at: datetime | str | None, subscription_end: datetime | str | None) -> int:
    if not first_subscription_at or not subscription_end:
        return 0
    now = datetime.utcnow()
    if isinstance(first_subscription_at, str):
        try:
            first_subscription_at = datetime.fromisoformat(first_subscription_at)
        except ValueError:
            return 0
    if isinstance(subscription_end, str):
        try:
            subscription_end = datetime.fromisoformat(subscription_end)
        except ValueError:
            return 0
    if subscription_end < now:
        return 0
    start = first_subscription_at
    total_days = (now - start).days
    if total_days < 0:
        return 0
    return total_days // 30


def get_level_weight(level: int) -> int:
    return max(1, int(level))


def weighted_pick_users(users, seed: int | None = None) -> int | None:
    import random
    if not users:
        return None
    weights = [get_level_weight(int(u["level"])) for u in users]
    ids = [int(u["id"]) for u in users]
    if seed is not None:
        rnd = random.Random(seed)
    else:
        rnd = random.Random()
    return rnd.choices(ids, weights=weights, k=1)[0]
