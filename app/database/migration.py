from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)
MIGRATION_NAME = "legacy_referrals_from_dump_v1"


async def migrate_legacy_postgres(repo: Any) -> None:
    if not settings.LEGACY_POSTGRES_DUMP.exists():
        return
    if await repo._row("SELECT name FROM migration_state WHERE name = ?", (MIGRATION_NAME,)):
        return
    rows = await asyncio.to_thread(_read_dump, settings.LEGACY_POSTGRES_DUMP)
    await _import_rows(repo, rows)
    logger.info("Legacy referral dump migration completed")


def _read_dump(dump_path: Path) -> dict[str, list[dict[str, Any]]]:
    sql_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as output:
            sql_path = Path(output.name)
        result = subprocess.run(
            [settings.PG_RESTORE_COMMAND, "--data-only", "--no-owner", "--file", str(sql_path), str(dump_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"pg_restore failed: {result.stderr.strip()}")
        return _parse_copy_sql(sql_path)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Для миграции нужен только клиент PostgreSQL с командой pg_restore; сервер PostgreSQL не нужен."
        ) from exc
    finally:
        if sql_path:
            sql_path.unlink(missing_ok=True)


def _parse_copy_sql(sql_path: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    current: tuple[str, list[str]] | None = None
    for raw_line in sql_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip("\r")
        if line.startswith("COPY public.") and " FROM stdin;" in line:
            header = line[len("COPY public."):].split(" FROM stdin;", 1)[0]
            table, columns_text = header.split(" (", 1)
            columns = [item.strip() for item in columns_text.rstrip(")").split(",")]
            current = (table, columns)
            continue
        if current and line == "\\.":
            current = None
            continue
        if current:
            table, columns = current
            values = [_decode_copy_value(value) for value in line.split("\t")]
            result[table].append(dict(zip(columns, values)))
    return result


def _decode_copy_value(value: str) -> Any:
    if value == r"\N":
        return None
    return (value.replace(r"\t", "\t").replace(r"\n", "\n").replace(r"\r", "\r").replace(r"\\", "\\"))


async def _import_rows(repo: Any, rows: dict[str, list[dict[str, Any]]]) -> None:
    source_users = rows.get("users", [])
    source_channels = rows.get("channels", [])
    source_links = rows.get("referral_links", [])
    source_assets = rows.get("referral_assets", [])
    source_payments = rows.get("subscription_payment_events", [])
    source_transactions = rows.get("ledger_transactions", [])

    balances: dict[int, int] = defaultdict(int)
    for row in source_transactions:
        balances[int(row["user_id"])] += int(row["amount"])

    first_subscription: dict[int, Any] = {}
    subscription_end: dict[int, Any] = {}
    for row in source_payments:
        tg_id = int(row["telegram_user_id"])
        created = row["created_at"]
        expires = row["subscription_expiration_date"]
        if tg_id not in first_subscription or str(created) < str(first_subscription[tg_id]):
            first_subscription[tg_id] = created
        if expires and str(expires) > str(subscription_end.get(tg_id, "")):
            subscription_end[tg_id] = expires

    user_ids: dict[int, int] = {}
    channel_ids = {int(row["id"]): int(row["telegram_chat_id"]) for row in source_channels}
    await repo.conn.execute("BEGIN")
    try:
        for row in source_users:
            tg_id = int(row["telegram_id"])
            full_name = (row["first_name"] or row["username"] or str(tg_id))[:255]
            await repo.conn.execute(
                """INSERT INTO users (tg_id, username, full_name, balance, subscription_end, first_subscription_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(tg_id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name""",
                (tg_id, row["username"], full_name, balances.get(int(row["id"]), 0), subscription_end.get(tg_id), first_subscription.get(tg_id)),
            )
            local = await repo._row("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
            user_ids[int(row["id"])] = int(local["id"])
            await repo.conn.execute(
                "UPDATE users SET balance=?, subscription_end=?, first_subscription_at=? WHERE id=?",
                (balances.get(int(row["id"]), 0), subscription_end.get(tg_id), first_subscription.get(tg_id), int(local["id"])),
            )

        for row in source_links:
            owner_id = user_ids.get(int(row["owner_id"]))
            chat_id = channel_ids.get(int(row["channel_id"]))
            if owner_id and chat_id:
                await repo.conn.execute(
                    "INSERT OR IGNORE INTO referral_links (owner_id, code, chat_id, invite_link, active, created_at) VALUES (?,?,?,?,?,?)",
                    (owner_id, str(row["link_name"]), chat_id, row["invite_link"], 1 if row["status"] == "ACTIVE" else 0, row["created_at"]),
                )

        for row in source_assets:
            owner_id = user_ids.get(int(row["current_owner_id"]))
            referee = await repo._row("SELECT id FROM users WHERE tg_id=?", (int(row["telegram_user_id"]),))
            if owner_id and referee:
                await repo.conn.execute(
                    "INSERT INTO referrals (referee_id, owner_id, created_at) VALUES (?,?,?) ON CONFLICT(referee_id) DO UPDATE SET owner_id=excluded.owner_id",
                    (int(referee["id"]), owner_id, row["created_at"]),
                )

        type_map = {
            "REFERRAL_EARNING": "ref_bonus",
            "MARKETPLACE_SALE": "market_sell",
            "MARKETPLACE_PURCHASE": "market_buy",
            "STARS_TOPUP": "deposit",
            "WITHDRAWAL": "withdraw",
            "ADJUSTMENT": "other",
        }
        for row in source_transactions:
            local_id = user_ids.get(int(row["user_id"]))
            if local_id:
                await repo.conn.execute(
                    "INSERT INTO transactions (user_id, amount, type, related_id, created_at) VALUES (?,?,?,?,?)",
                    (local_id, int(row["amount"]), type_map.get(row["type"], "other"), row["reference_id"], row["created_at"]),
                )

        await repo.conn.execute("INSERT INTO migration_state (name) VALUES (?)", (MIGRATION_NAME,))
        await repo.conn.commit()
    except Exception:
        await repo.conn.rollback()
        raise
