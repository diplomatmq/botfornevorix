from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from app.config import settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

TXN_REF_BONUS = "ref_bonus"
TXN_RENEWAL_BONUS = "renewal_bonus"
TXN_MARKET_SELL = "market_sell"
TXN_MARKET_BUY = "market_buy"
TXN_LOT_CANCEL = "lot_cancel"
TXN_REF_LINK_COST = "referral_link_cost"
TXN_RESTORE_LEVEL = "restore_level"
TXN_DEPOSIT = "deposit"
TXN_WITHDRAW = "withdraw"
TXN_WITHDRAW_REJECT = "withdraw_reject"
TXN_OTHER = "other"


class Repository:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn
        self.conn.row_factory = aiosqlite.Row

    async def init_schema(self) -> None:
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        await self.conn.executescript(sql)
        await self._migrate_add_wins_column()
        await self._migrate_giveaway_timezones()
        await self._migrate_remove_giveaway_max_level()
        await self._migrate_giveaway_winners()
        await self._migrate_active_subscription_levels()
        await self._migrate_referral_market_flags()
        await self.conn.commit()
        from app.database.migration import migrate_legacy_postgres
        await migrate_legacy_postgres(self)

    async def _migrate_giveaway_winners(self) -> None:
        for column, definition in (
            ("winners_count", "INTEGER NOT NULL DEFAULT 1"),
            ("prizes_json", "TEXT"),
            ("winners_json", "TEXT"),
        ):
            try:
                await self.conn.execute(f"SELECT {column} FROM giveaways LIMIT 1")
            except Exception:
                await self.conn.execute(f"ALTER TABLE giveaways ADD COLUMN {column} {definition}")

    async def _migrate_active_subscription_levels(self) -> None:
        await self.conn.execute(
            """
            UPDATE users
            SET level = CASE WHEN level < 1 THEN 1 ELSE level END,
                max_level = CASE WHEN max_level < 1 THEN 1 ELSE max_level END
            WHERE subscription_end IS NOT NULL
              AND subscription_end > CURRENT_TIMESTAMP
            """
        )

    async def _migrate_referral_market_flags(self) -> None:
        await self.conn.execute(
            "UPDATE referrals SET on_market = 0 WHERE on_market IS NULL"
        )

    async def _migrate_add_wins_column(self) -> None:
        try:
            await self.conn.execute("SELECT wins FROM users LIMIT 1")
        except Exception:
            await self.conn.execute("ALTER TABLE users ADD COLUMN wins INTEGER NOT NULL DEFAULT 0")

    async def _migrate_giveaway_timezones(self) -> None:
        tz_col_exists = True
        try:
            await self.conn.execute("SELECT tz_migrated FROM giveaways LIMIT 1")
        except Exception:
            tz_col_exists = False
        if not tz_col_exists:
            await self.conn.execute(
                "ALTER TABLE giveaways ADD COLUMN tz_migrated INTEGER NOT NULL DEFAULT 0"
            )
        cursor = await self.conn.execute(
            "UPDATE giveaways "
            "SET ends_at = datetime(ends_at, '-3 hours'), tz_migrated = 1 "
            "WHERE status = 'active' AND tz_migrated = 0"
        )
        if cursor and cursor.rowcount and cursor.rowcount > 0:
            logger = logging.getLogger(__name__)
            logger.info("Migration: shifted %s giveaway ends_at MSK→UTC", cursor.rowcount)

    async def _migrate_remove_giveaway_max_level(self) -> None:
        max_level_exists = True
        try:
            await self.conn.execute("SELECT max_level FROM giveaways LIMIT 1")
        except Exception:
            max_level_exists = False
        if max_level_exists:
            try:
                await self.conn.execute("ALTER TABLE giveaways DROP COLUMN max_level")
                logger = logging.getLogger(__name__)
                logger.info("Migration: dropped max_level column from giveaways")
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.warning("Migration: could not drop max_level column (old SQLite?): %s", e)

    async def _row(self, sql: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
        cur = await self.conn.execute(sql, params)
        try:
            return await cur.fetchone()
        finally:
            await cur.close()

    async def _rows(self, sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(sql, params)
        try:
            return await cur.fetchall()
        finally:
            await cur.close()

    async def _exec(self, sql: str, params: tuple = ()) -> int:
        cur = await self.conn.execute(sql, params)
        await self.conn.commit()
        lastrow = cur.lastrowid or 0
        await cur.close()
        return lastrow

    async def _transaction(self, statements: list[tuple[str, tuple]]) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute("BEGIN")
            try:
                for sql, params in statements:
                    await cur.execute(sql, params)
                await self.conn.commit()
            except Exception:
                await self.conn.rollback()
                raise

    async def get_user_by_tg_id(self, tg_id: int) -> Optional[aiosqlite.Row]:
        return await self._row("SELECT * FROM users WHERE tg_id = ?", (tg_id,))

    async def get_user_by_id(self, user_id: int) -> Optional[aiosqlite.Row]:
        return await self._row("SELECT * FROM users WHERE id = ?", (user_id,))

    async def create_user(
        self,
        tg_id: int,
        username: Optional[str],
        full_name: str,
        referred_by: Optional[int] = None,
    ) -> int:
        return await self._exec(
            "INSERT INTO users (tg_id, username, full_name, referred_by) VALUES (?,?,?,?)",
            (tg_id, username, full_name, referred_by),
        )

    async def update_user_meta(self, tg_id: int, username: Optional[str], full_name: str) -> None:
        await self._exec(
            "UPDATE users SET username = ?, full_name = ? WHERE tg_id = ?",
            (username, full_name, tg_id),
        )

    async def add_stars(self, user_id: int, amount: int, tx_type: str, related_id: Optional[int] = None) -> bool:
        if amount < 0:
            return False
        stmts = [
            ("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id)),
            ("INSERT INTO transactions (user_id, amount, type, related_id) VALUES (?,?,?,?)", (user_id, amount, tx_type, related_id)),
        ]
        await self._transaction(stmts)
        return True

    async def subtract_stars(self, user_id: int, amount: int, tx_type: str, related_id: Optional[int] = None) -> bool:
        if amount < 0:
            return False
        user = await self.get_user_by_id(user_id)
        if not user or user["balance"] < amount:
            return False
        stmts = [
            ("UPDATE users SET balance = balance - ? WHERE id = ? AND balance >= ?", (amount, user_id, amount)),
            ("INSERT INTO transactions (user_id, amount, type, related_id) VALUES (?,?,?,?)", (user_id, -amount, tx_type, related_id)),
        ]
        await self._transaction(stmts)
        return True

    async def set_user_level(self, user_id: int, level: int) -> None:
        await self._exec(
            "UPDATE users SET level = ?, max_level = MAX(max_level, ?) WHERE id = ?",
            (level, level, user_id),
        )

    async def reset_user_level(self, user_id: int) -> None:
        await self._exec("UPDATE users SET level = 0 WHERE id = ?", (user_id,))

    async def add_win(self, user_id: int) -> None:
        await self._exec("UPDATE users SET wins = wins + 1 WHERE id = ?", (user_id,))

    async def activate_subscription(self, user_id: int, days: int) -> None:
        now = datetime.utcnow()
        end = datetime.fromtimestamp(now.timestamp() + days * 86400)
        await self._exec(
            """
            UPDATE users
            SET subscription_end = ?,
                first_subscription_at = COALESCE(first_subscription_at, ?),
                level = CASE WHEN level < 1 THEN 1 ELSE level END,
                max_level = CASE WHEN max_level < 1 THEN 1 ELSE max_level END
            WHERE id = ?
            """,
            (end, now, user_id),
        )

    async def apply_channel_subscription_end(self, user_id: int, new_end: datetime) -> bool:
        user = await self.get_user_by_id(user_id)
        if not user:
            return False
        current_end = user["subscription_end"]
        if isinstance(current_end, str):
            try:
                current_end = datetime.fromisoformat(current_end)
            except ValueError:
                current_end = None
        if current_end and new_end <= current_end:
            return False

        now = datetime.utcnow()
        on_time = current_end is not None and now <= current_end + timedelta(days=2)
        ref = await self.get_referral_by_referee(user_id)
        async with self.conn.cursor() as cur:
            await cur.execute("BEGIN")
            try:
                await cur.execute(
                    "INSERT OR IGNORE INTO channel_subscription_updates (user_id, subscription_end) VALUES (?,?)",
                    (user_id, new_end),
                )
                if cur.rowcount != 1:
                    await self.conn.rollback()
                    return False
                await cur.execute(
                    "UPDATE users SET subscription_end = ?, first_subscription_at = COALESCE(first_subscription_at, ?) WHERE id = ?",
                    (new_end, now, user_id),
                )
                if ref and on_time:
                    owner_id = int(ref["owner_id"])
                    await cur.execute(
                        "UPDATE users SET level = level + 1, max_level = MAX(max_level, level + 1) WHERE id = ?",
                        (user_id,),
                    )
                    await cur.execute(
                        "UPDATE users SET balance = balance + ? WHERE id = ?",
                        (settings.RENEWAL_BONUS, owner_id),
                    )
                    await cur.execute(
                        "INSERT INTO transactions (user_id, amount, type, related_id) VALUES (?,?,?,?)",
                        (owner_id, settings.RENEWAL_BONUS, TXN_RENEWAL_BONUS, user_id),
                    )
                await self.conn.commit()
            except Exception:
                await self.conn.rollback()
                raise
        return True

    async def get_all_users(self) -> list[aiosqlite.Row]:
        return await self._rows("SELECT * FROM users")

    async def get_users_by_level(self, level: int) -> list[aiosqlite.Row]:
        return await self._rows(
            "SELECT * FROM users WHERE level = ? ORDER BY full_name COLLATE NOCASE",
            (level,),
        )

    async def get_recent_subscriptions(self, limit: int = 10) -> list[aiosqlite.Row]:
        return await self._rows(
            "SELECT * FROM users WHERE first_subscription_at IS NOT NULL "
            "ORDER BY first_subscription_at DESC LIMIT ?",
            (limit,),
        )

    async def get_recent_renewals(self, limit: int = 10) -> list[aiosqlite.Row]:
        return await self._rows(
            "SELECT t.created_at, t.amount, t.related_id, u.full_name, u.username "
            "FROM transactions t JOIN users u ON u.id = t.related_id "
            "WHERE t.type = ? ORDER BY t.created_at DESC LIMIT ?",
            (TXN_RENEWAL_BONUS, limit),
        )

    async def get_renewals_by_owner(self, owner_id: int, limit: int = 30) -> list[aiosqlite.Row]:
        return await self._rows(
            "SELECT t.created_at, t.amount, u.full_name, u.username "
            "FROM transactions t JOIN users u ON u.id = t.related_id "
            "JOIN referrals r ON r.referee_id = t.related_id "
            "WHERE t.type = ? AND r.owner_id = ? ORDER BY t.created_at DESC LIMIT ?",
            (TXN_RENEWAL_BONUS, owner_id, limit),
        )

    async def create_referral_link(
        self, owner_id: int, code: str, chat_id: int, invite_link: str
    ) -> int:
        return await self._exec(
            "INSERT INTO referral_links (owner_id, code, chat_id, invite_link, active) VALUES (?,?,?,?,1)",
            (owner_id, code, chat_id, invite_link),
        )

    async def get_active_link_by_owner(self, owner_id: int, chat_id: int) -> Optional[aiosqlite.Row]:
        return await self._row(
            "SELECT * FROM referral_links WHERE owner_id = ? AND chat_id = ? AND active = 1 LIMIT 1",
            (owner_id, chat_id),
        )

    async def get_link_by_code(self, code: str) -> Optional[aiosqlite.Row]:
        return await self._row(
            "SELECT * FROM referral_links WHERE code = ? AND active = 1 LIMIT 1",
            (code,),
        )

    async def get_link_by_invite_link(self, invite_link: str) -> Optional[aiosqlite.Row]:
        return await self._row(
            "SELECT * FROM referral_links WHERE invite_link = ? LIMIT 1",
            (invite_link,),
        )

    async def create_referral_relation(self, referee_id: int, owner_id: int) -> int:
        return await self._exec(
            "INSERT INTO referrals (referee_id, owner_id) VALUES (?,?)",
            (referee_id, owner_id),
        )

    async def get_referrals_by_owner(self, owner_id: int, include_on_market: bool = True) -> list[aiosqlite.Row]:
        extra = "" if include_on_market else "AND COALESCE(r.on_market, 0) = 0"
        return await self._rows(
            f"""
            SELECT r.id AS ref_id, r.on_market, r.lot_id, u.*
            FROM referrals r JOIN users u ON u.id = r.referee_id
            WHERE r.owner_id = ? {extra}
            ORDER BY u.id DESC
            """,
            (owner_id,),
        )

    async def get_referral_count_by_owner(self, owner_id: int) -> int:
        row = await self._row(
            "SELECT COUNT(*) AS c FROM referrals WHERE owner_id = ?", (owner_id,)
        )
        return int(row["c"]) if row else 0

    async def get_referral_by_referee(self, referee_id: int) -> Optional[aiosqlite.Row]:
        return await self._row(
            "SELECT * FROM referrals WHERE referee_id = ? LIMIT 1", (referee_id,)
        )

    async def get_referral_by_id(self, referral_id: int) -> Optional[aiosqlite.Row]:
        return await self._row("SELECT * FROM referrals WHERE id = ?", (referral_id,))

    async def top_referrers(self, limit: int = 10) -> list[aiosqlite.Row]:
        return await self._rows(
            """
            SELECT u.id, u.tg_id, u.username, u.full_name, u.level,
                   COUNT(r.id) AS refs_count
            FROM users u
            LEFT JOIN referrals r ON r.owner_id = u.id
            GROUP BY u.id
            ORDER BY refs_count DESC, u.id ASC
            LIMIT ?
            """,
            (limit,),
        )

    async def create_market_lot(
        self,
        seller_id: int,
        count: int,
        price_per_one: int,
        referral_ids: list[int],
        level_min: Optional[int] = None,
        level_max: Optional[int] = None,
    ) -> int:
        total = count * price_per_one
        stmts: list[tuple[str, tuple]] = []
        stmts.append(
            (
                "INSERT INTO market_lots (seller_id, count, price_per_one, total_price, level_min, level_max, status) VALUES (?,?,?,?,?,?, 'active')",
                (seller_id, count, price_per_one, total, level_min, level_max),
            )
        )
        async with self.conn.cursor() as cur:
            await cur.execute("BEGIN")
            try:
                if len(referral_ids) != count or len(set(referral_ids)) != count:
                    raise ValueError("Количество выбранных рефералов не совпадает с данными лота")
                for ref_id in referral_ids:
                    ref = await cur.execute(
                        "SELECT id, on_market FROM referrals WHERE id = ? AND owner_id = ?",
                        (ref_id, seller_id),
                    )
                    ref_row = await ref.fetchone()
                    if not ref_row:
                        raise ValueError("Выбранный реферал не найден или уже вам не принадлежит")
                    if int(ref_row["on_market"] or 0):
                        raise ValueError("Один из выбранных рефералов уже находится на продаже")
                await cur.execute(stmts[0][0], stmts[0][1])
                lot_id = int(cur.lastrowid or 0)
                if not lot_id:
                    raise RuntimeError("Не удалось получить ID созданного лота")
                for ref_id in referral_ids:
                    await cur.execute(
                        "INSERT INTO market_lot_items (lot_id, referral_id) VALUES (?,?)",
                        (lot_id, ref_id),
                    )
                    cursor = await cur.execute(
                        """
                        UPDATE referrals
                        SET on_market = 1, lot_id = ?
                        WHERE id = ? AND owner_id = ? AND COALESCE(on_market, 0) = 0
                        """,
                        (lot_id, ref_id, seller_id),
                    )
                    if cursor.rowcount != 1:
                        raise ValueError("Реферал уже выставлен на продажу или вам не принадлежит")
                await self.conn.commit()
                return lot_id
            except Exception:
                await self.conn.rollback()
                raise

    async def get_active_lots(self, limit: int = 50) -> list[aiosqlite.Row]:
        return await self._rows(
            """
            SELECT ml.*, u.username AS seller_username, u.full_name AS seller_name,
                   (SELECT COUNT(*) FROM market_lot_items mli WHERE mli.lot_id = ml.id) AS real_count
            FROM market_lots ml JOIN users u ON u.id = ml.seller_id
            WHERE ml.status = 'active'
            ORDER BY ml.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )

    async def get_lot_by_id(self, lot_id: int) -> Optional[aiosqlite.Row]:
        return await self._row("SELECT * FROM market_lots WHERE id = ?", (lot_id,))

    async def get_lot_items(self, lot_id: int) -> list[aiosqlite.Row]:
        return await self._rows(
            """
            SELECT mli.*, u.*, r.id AS ref_row_id
            FROM market_lot_items mli
            JOIN referrals r ON r.id = mli.referral_id
            JOIN users u ON u.id = r.referee_id
            WHERE mli.lot_id = ?
            """,
            (lot_id,),
        )

    async def get_lots_by_seller(self, seller_id: int) -> list[aiosqlite.Row]:
        return await self._rows(
            "SELECT * FROM market_lots WHERE seller_id = ? ORDER BY created_at DESC",
            (seller_id,),
        )

    async def cancel_lot(self, lot_id: int, seller_id: int) -> bool:
        lot = await self.get_lot_by_id(lot_id)
        if not lot or lot["seller_id"] != seller_id or lot["status"] != "active":
            return False
        stmts = [
            ("UPDATE market_lots SET status = 'cancelled' WHERE id = ?", (lot_id,)),
            ("UPDATE referrals SET on_market = 0, lot_id = NULL WHERE lot_id = ?", (lot_id,)),
        ]
        await self._transaction(stmts)
        return True

    async def buy_lot(self, lot_id: int, buyer_id: int) -> bool:
        lot = await self.get_lot_by_id(lot_id)
        buyer = await self.get_user_by_id(buyer_id)
        if not lot or not buyer:
            return False
        if lot["status"] != "active":
            return False
        if lot["seller_id"] == buyer_id:
            return False
        total_price = int(lot["total_price"])
        if int(buyer["balance"]) < total_price:
            return False
        items = await self.get_lot_items(lot_id)
        referee_ids = [int(r["referee_id"]) for r in items]
        seller_id = int(lot["seller_id"])
        stmts: list[tuple[str, tuple]] = []
        stmts.append(
            ("UPDATE users SET balance = balance - ? WHERE id = ? AND balance >= ?", (total_price, buyer_id, total_price))
        )
        stmts.append(
            ("UPDATE users SET balance = balance + ? WHERE id = ?", (total_price, seller_id))
        )
        stmts.append(
            ("INSERT INTO transactions (user_id, amount, type, related_id) VALUES (?,?,?,?)", (buyer_id, -total_price, TXN_MARKET_BUY, lot_id))
        )
        stmts.append(
            ("INSERT INTO transactions (user_id, amount, type, related_id) VALUES (?,?,?,?)", (seller_id, total_price, TXN_MARKET_SELL, lot_id))
        )
        stmts.append(
            ("UPDATE market_lots SET status = 'sold' WHERE id = ?", (lot_id,))
        )
        for rid in referee_ids:
            stmts.append(
                ("UPDATE referrals SET owner_id = ?, on_market = 0, lot_id = NULL WHERE referee_id = ?", (buyer_id, rid))
            )
        await self._transaction(stmts)
        return True

    async def create_giveaway(
        self,
        admin_id: int,
        title: Optional[str],
        prize: str,
        text: str,
        channel_id: int,
        ends_at: datetime,
        min_level: Optional[int] = None,
        winners_count: int = 1,
        prizes_json: Optional[str] = None,
    ) -> int:
        return await self._exec(
            """
            INSERT INTO giveaways (admin_id, title, prize, text, channel_id, ends_at, min_level, winners_count, prizes_json, status)
            VALUES (?,?,?,?,?,?,?,?,?, 'active')
            """,
            (admin_id, title, prize, text, channel_id, ends_at, min_level, winners_count, prizes_json),
        )

    async def set_giveaway_channel_msg(self, giveaway_id: int, channel_msg_id: int) -> None:
        await self._exec(
            "UPDATE giveaways SET channel_msg_id = ? WHERE id = ?",
            (channel_msg_id, giveaway_id),
        )

    async def get_pending_giveaways(self, now: Optional[datetime] = None) -> list[aiosqlite.Row]:
        now = now or datetime.utcnow()
        return await self._rows(
            "SELECT * FROM giveaways WHERE status = 'active' AND ends_at <= ?",
            (now,),
        )

    async def get_active_giveaways(self) -> list[aiosqlite.Row]:
        return await self._rows(
            "SELECT * FROM giveaways WHERE status = 'active' ORDER BY id"
        )

    async def cancel_giveaway(self, giveaway_id: int) -> bool:
        cursor = await self.conn.execute(
            "UPDATE giveaways SET status = 'cancelled' WHERE id = ? AND status = 'active'",
            (giveaway_id,),
        )
        await self.conn.commit()
        return cursor.rowcount == 1

    async def claim_giveaway(self, giveaway_id: int) -> bool:
        cursor = await self.conn.execute(
            "UPDATE giveaways SET status = 'processing' WHERE id = ? AND status = 'active'",
            (giveaway_id,),
        )
        await self.conn.commit()
        return cursor.rowcount == 1

    async def finish_giveaway(self, giveaway_id: int, winner_id: Optional[int], winners_json: Optional[str] = None) -> None:
        await self._exec(
            "UPDATE giveaways SET winner_id = ?, winners_json = ?, status = 'ended' WHERE id = ? AND status = 'processing'",
            (winner_id, winners_json, giveaway_id),
        )

    async def get_giveaway(self, giveaway_id: int) -> Optional[aiosqlite.Row]:
        return await self._row("SELECT * FROM giveaways WHERE id = ?", (giveaway_id,))

    async def get_eligible_users_for_giveaway(
        self, min_level: Optional[int]
    ) -> list[aiosqlite.Row]:
        sql = "SELECT * FROM users WHERE 1=1"
        params: list[Any] = []
        if min_level is not None:
            sql += " AND level >= ?"
            params.append(min_level)
        return await self._rows(sql, tuple(params))

    async def create_deposit_request(
        self, user_id: int, amount: int, screenshot_file_id: Optional[str] = None
    ) -> int:
        return await self._exec(
            "INSERT INTO deposit_requests (user_id, amount, screenshot_file_id, status) VALUES (?,?,?, 'pending')",
            (user_id, amount, screenshot_file_id),
        )

    async def create_withdraw_request(self, user_id: int, amount: int, details: str) -> int:
        return await self._exec(
            "INSERT INTO withdraw_requests (user_id, amount, details, status) VALUES (?,?,?, 'pending')",
            (user_id, amount, details),
        )

    async def get_deposit(self, request_id: int) -> Optional[aiosqlite.Row]:
        return await self._row("SELECT * FROM deposit_requests WHERE id = ?", (request_id,))

    async def get_withdraw(self, request_id: int) -> Optional[aiosqlite.Row]:
        return await self._row("SELECT * FROM withdraw_requests WHERE id = ?", (request_id,))

    async def approve_deposit(self, request_id: int, handled_by: int) -> bool:
        req = await self.get_deposit(request_id)
        if not req or req["status"] != "pending":
            return False
        stmts = [
            (
                "UPDATE deposit_requests SET status = 'approved', handled_by = ?, handled_at = ? WHERE id = ?",
                (handled_by, datetime.utcnow(), request_id),
            ),
            ("UPDATE users SET balance = balance + ? WHERE id = ?", (int(req["amount"]), int(req["user_id"]))),
            (
                "INSERT INTO transactions (user_id, amount, type, related_id) VALUES (?,?,?,?)",
                (int(req["user_id"]), int(req["amount"]), TXN_DEPOSIT, request_id),
            ),
        ]
        await self._transaction(stmts)
        return True

    async def reject_deposit(self, request_id: int, handled_by: int, comment: Optional[str] = None) -> bool:
        req = await self.get_deposit(request_id)
        if not req or req["status"] != "pending":
            return False
        await self._exec(
            "UPDATE deposit_requests SET status = 'rejected', handled_by = ?, handled_at = ?, comment = ? WHERE id = ?",
            (handled_by, datetime.utcnow(), comment, request_id),
        )
        return True

    async def approve_withdraw(self, request_id: int, handled_by: int) -> bool:
        req = await self.get_withdraw(request_id)
        if not req or req["status"] != "pending":
            return False
        amt = int(req["amount"])
        uid = int(req["user_id"])
        async with self.conn.cursor() as cur:
            await cur.execute("BEGIN")
            try:
                await cur.execute(
                    "UPDATE users SET balance = balance - ? WHERE id = ? AND balance >= ?",
                    (amt, uid, amt),
                )
                if cur.rowcount != 1:
                    await self.conn.rollback()
                    return False
                await cur.execute(
                    "UPDATE withdraw_requests "
                    "SET status = 'approved', handled_by = ?, handled_at = ? "
                    "WHERE id = ? AND status = 'pending'",
                    (handled_by, datetime.utcnow(), request_id),
                )
                if cur.rowcount != 1:
                    await self.conn.rollback()
                    return False
                await cur.execute(
                    "INSERT INTO transactions (user_id, amount, type, related_id) VALUES (?,?,?,?)",
                    (uid, -amt, TXN_WITHDRAW, request_id),
                )
                await self.conn.commit()
                return True
            except Exception:
                await self.conn.rollback()
                raise

    async def reject_withdraw(self, request_id: int, handled_by: int, comment: Optional[str] = None) -> bool:
        req = await self.get_withdraw(request_id)
        if not req or req["status"] != "pending":
            return False
        stmts = [
            (
                "UPDATE withdraw_requests SET status = 'rejected', handled_by = ?, handled_at = ?, comment = ? WHERE id = ?",
                (handled_by, datetime.utcnow(), comment, request_id),
            ),
        ]
        await self._transaction(stmts)
        return True

    async def get_recent_transactions(self, user_id: int, limit: int = 20) -> list[aiosqlite.Row]:
        return await self._rows(
            "SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )

    async def get_all_active_lot_items(self) -> list[aiosqlite.Row]:
        """Получить все рефералы из активных лотов"""
        return await self._rows(
            """
            SELECT mli.*, r.id AS ref_row_id, r.owner_id AS seller_id,
                   u.tg_id, u.username, u.full_name, u.level, u.subscription_end,
                   ml.price_per_one, ml.id AS lot_id
            FROM market_lot_items mli
            JOIN referrals r ON r.id = mli.referral_id
            JOIN users u ON u.id = r.referee_id
            JOIN market_lots ml ON ml.id = mli.lot_id
            WHERE ml.status = 'active'
            ORDER BY ml.created_at DESC, u.level DESC
            """
        )

    async def get_lot_item_by_ref_id(self, ref_row_id: int) -> Optional[aiosqlite.Row]:
        """Получить информацию о лоте и реферале по ref_row_id"""
        return await self._row(
            """
            SELECT mli.*, r.id AS ref_row_id, r.owner_id AS seller_id, r.referee_id,
                   u.tg_id, u.username, u.full_name, u.level,
                   ml.price_per_one, ml.id AS lot_id, ml.seller_id AS lot_seller_id, ml.status AS lot_status
            FROM market_lot_items mli
            JOIN referrals r ON r.id = mli.referral_id
            JOIN users u ON u.id = r.referee_id
            JOIN market_lots ml ON ml.id = mli.lot_id
            WHERE r.id = ?
            """,
            (ref_row_id,)
        )

    async def buy_single_referral(self, ref_row_id: int, buyer_id: int) -> bool:
        """Купить одного реферала из лота"""
        item = await self.get_lot_item_by_ref_id(ref_row_id)
        buyer = await self.get_user_by_id(buyer_id)
        
        if not item or not buyer:
            return False
        
        if item["lot_status"] != "active":
            return False
        
        seller_id = int(item["seller_id"])
        if seller_id == buyer_id:
            return False
        
        price = int(item["price_per_one"])
        if int(buyer["balance"]) < price:
            return False
        
        lot_id = int(item["lot_id"])
        referee_id = int(item["referee_id"])
        
        stmts: list[tuple[str, tuple]] = []
        
        # Списываем деньги с покупателя
        stmts.append(
            ("UPDATE users SET balance = balance - ? WHERE id = ? AND balance >= ?", (price, buyer_id, price))
        )
        
        # Начисляем деньги продавцу
        stmts.append(
            ("UPDATE users SET balance = balance + ? WHERE id = ?", (price, seller_id))
        )
        
        # Транзакции
        stmts.append(
            ("INSERT INTO transactions (user_id, amount, type, related_id) VALUES (?,?,?,?)", 
             (buyer_id, -price, TXN_MARKET_BUY, lot_id))
        )
        stmts.append(
            ("INSERT INTO transactions (user_id, amount, type, related_id) VALUES (?,?,?,?)", 
             (seller_id, price, TXN_MARKET_SELL, lot_id))
        )
        
        # Передаем реферала новому владельцу
        stmts.append(
            ("UPDATE referrals SET owner_id = ?, on_market = 0, lot_id = NULL WHERE referee_id = ?", 
             (buyer_id, referee_id))
        )
        
        # Удаляем из лота
        stmts.append(
            ("DELETE FROM market_lot_items WHERE referral_id = ?", (ref_row_id,))
        )
        
        # Проверяем, остались ли еще рефералы в лоте
        # Если нет — закрываем лот
        stmts.append(
            ("""
            UPDATE market_lots 
            SET status = CASE 
                WHEN (SELECT COUNT(*) FROM market_lot_items WHERE lot_id = ?) = 0 
                THEN 'sold' 
                ELSE 'active' 
            END,
            count = (SELECT COUNT(*) FROM market_lot_items WHERE lot_id = ?)
            WHERE id = ?
            """, (lot_id, lot_id, lot_id))
        )
        
        await self._transaction(stmts)
        return True
