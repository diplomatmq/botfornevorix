from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.database.repo import Repository
from app.handlers import register_routers
from app.loader import bot, close_db, dp, ensure_generic_invite_link, get_db, scheduler
from app.middlewares.db import RepoMiddleware
from app.middlewares.subscription import SubscriptionMiddleware
from app.scheduler.jobs import job_check_subscriptions, job_run_giveaways

logger = logging.getLogger(__name__)


def _setup_scheduler(repo: Repository) -> None:
    scheduler.add_job(
        job_check_subscriptions,
        "interval",
        hours=24,
        args=[repo],
        id="job_check_subscriptions",
        replace_existing=True,
    )
    scheduler.add_job(
        job_run_giveaways,
        "interval",
        minutes=5,
        args=[repo, bot],
        id="job_run_giveaways",
        replace_existing=True,
    )


async def main() -> None:
    logger.info("Starting bot...")
    if not settings.BOT_TOKEN:
        logger.critical("BOT_TOKEN is empty! Fill .env using .env.example")
        return
    conn = await get_db()
    repo = Repository(conn)
    await repo.init_schema()
    logger.info("DB schema initialized")

    dp.update.middleware(RepoMiddleware(repo))
    dp.update.middleware(SubscriptionMiddleware())

    register_routers(dp)

    _setup_scheduler(repo)
    scheduler.start()
    logger.info("Scheduler started")

    try:
        logger.info("Starting polling...")
        await bot.delete_webhook(drop_pending_updates=True)
        asyncio.create_task(_run_startup_jobs(repo))
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await close_db()
        logger.info("Bot stopped")


async def _run_startup_jobs(repo: Repository) -> None:
    try:
        await ensure_generic_invite_link(bot)
    except Exception as e:
        logger.error("Initial generic invite setup failed: %s", e)
    try:
        await job_check_subscriptions(repo)
    except Exception as e:
        logger.error("Initial job_check_subscriptions failed: %s", e)
    try:
        await job_run_giveaways(repo, bot)
    except Exception as e:
        logger.error("Initial job_run_giveaways failed: %s", e)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Exit signal received")
