import logging
import asyncio
import sqlite3
import sys
from pathlib import Path

import aiosqlite
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ChatMemberAdministrator, ChatMemberMember, ChatMemberOwner
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


_setup_logging()

_db_init_lock = False


async def _init_db(db_path: Path) -> aiosqlite.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    await conn.execute("PRAGMA journal_mode = WAL")
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.commit()
    cursor = await conn.execute("PRAGMA journal_mode")
    row = await cursor.fetchone()
    logger.info("Database journal_mode: %s", row and row[0])
    return conn


bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher()

scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

db: aiosqlite.Connection | None = None

generic_invite_link: str | None = None


async def ensure_generic_invite_link(bot_instance: Bot) -> str:
    global generic_invite_link
    if generic_invite_link:
        return generic_invite_link
    if not settings.CHANNEL_ID:
        return ""
    try:
        invite = await asyncio.wait_for(
            bot_instance.create_chat_subscription_invite_link(
                chat_id=settings.CHANNEL_ID,
                name="bot_generic_subscription",
                subscription_period=2592000,
                subscription_price=settings.REF_LINK_COST,
            ),
            timeout=10,
        )
        generic_invite_link = invite.invite_link
        logger.info("Generic subscription invite link ready")
    except Exception as e:
        logger.error("Failed to create generic invite link: %s", e)
        generic_invite_link = ""
    return generic_invite_link or ""


async def get_channel_member(bot_instance: Bot, user_id: int):
    if not settings.CHANNEL_ID:
        return None
    try:
        return await asyncio.wait_for(
            bot_instance.get_chat_member(settings.CHANNEL_ID, user_id),
            timeout=5,
        )
    except Exception:
        return None


async def is_subscribed_to_channel(bot_instance: Bot, user_id: int) -> bool:
    member = await get_channel_member(bot_instance, user_id)
    if member is None:
        return not settings.CHANNEL_ID
    return isinstance(member, (ChatMemberMember, ChatMemberAdministrator, ChatMemberOwner))


async def is_subscribed_and_not_bot(bot_instance: Bot, user_id: int) -> tuple[bool, bool]:
    member = await get_channel_member(bot_instance, user_id)
    if member is None:
        return (False, False)
    is_member = isinstance(member, (ChatMemberMember, ChatMemberAdministrator, ChatMemberOwner))
    try:
        is_bot = bool(member.user.is_bot)
    except Exception:
        is_bot = False
    return (is_member, is_bot)


async def get_channel_admin_ids_non_bot(bot_instance: Bot) -> set[int]:
    if not settings.CHANNEL_ID:
        return set()
    try:
        admins = await bot_instance.get_chat_administrators(settings.CHANNEL_ID)
    except Exception:
        return set()
    result: set[int] = set()
    for admin in admins:
        try:
            if not admin.user.is_bot:
                result.add(int(admin.user.id))
        except Exception:
            continue
    return result


async def get_db() -> aiosqlite.Connection:
    global db, _db_init_lock
    if db is None:
        if _db_init_lock:
            raise RuntimeError("DB not initialized yet")
        _db_init_lock = True
        db = await _init_db(settings.DB_PATH)
    return db


async def close_db() -> None:
    global db
    if db is not None:
        await db.close()
        db = None
