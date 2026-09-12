from __future__ import annotations

from datetime import datetime, timedelta, timezone

MONTH_LABELS = ["января", "февраля", "марта", "апреля", "мая", "июня",
                "июля", "августа", "сентября", "октября", "ноября", "декабря"]

MSK = timezone(timedelta(hours=3))


def format_stars(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " ⭐"


def format_user_name(row) -> str:
    username = row["username"] if "username" in row.keys() else None
    full_name = row["full_name"] if "full_name" in row.keys() else ""
    tg_id = row["tg_id"] if "tg_id" in row.keys() else row["id"]
    if username:
        return f"@{username} (id{tg_id})"
    if full_name:
        return f"{full_name} (id{tg_id})"
    return f"id{tg_id}"


def _to_msk(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt_utc = dt.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.astimezone(MSK)


def format_datetime(dt: datetime | str | None) -> str:
    if dt is None:
        return "—"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    dt = datetime.strptime(dt, fmt)
                    break
                except ValueError:
                    continue
        if not isinstance(dt, datetime):
            return str(dt)
    try:
        dt_msk = _to_msk(dt)
    except Exception:
        dt_msk = dt
    m = MONTH_LABELS[dt_msk.month - 1]
    return dt_msk.strftime(f"%d {m} %Y %H:%M МСК")


def format_subscription_end(dt: datetime | str | None) -> str:
    if not dt:
        return "❌ Нет активной подписки"
    now = datetime.utcnow()
    end = dt
    if isinstance(dt, str):
        try:
            end = datetime.fromisoformat(dt)
        except ValueError:
            return str(dt)
    if end < now:
        return f"⚠️ Истекла {format_datetime(end)}"
    return f"✅ Активна до {format_datetime(end)}"


TX_TYPE_LABELS = {
    "ref_bonus": "Бонус за реферала",
    "renewal_bonus": "Бонус за продление рефералом",
    "market_sell": "Продажа рефералов",
    "market_buy": "Покупка рефералов",
    "lot_cancel": "Отмена лота",
    "referral_link_cost": "Создание реф-ссылки",
    "restore_level": "Восстановление уровня",
    "deposit": "Пополнение баланса",
    "withdraw": "Вывод средств",
    "withdraw_reject": "Возврат при отклонении вывода",
    "other": "Прочее",
}


def format_tx_type(t: str) -> str:
    return TX_TYPE_LABELS.get(t, t)
