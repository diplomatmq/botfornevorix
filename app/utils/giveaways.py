from __future__ import annotations

import json
import logging
from datetime import datetime

from aiogram import Bot

from app.config import settings
from app.database.repo import Repository
from app.utils.formatters import format_datetime, format_user_name
from app.utils.levels import weighted_pick_users

logger = logging.getLogger(__name__)


def build_giveaway_post(ga) -> str:
    parts = []
    if ga["title"]:
        parts.append(f"🎁 <b>{ga['title']}</b>\n")
    parts.append(f"Приз: <b>{ga['prize']}</b>")
    parts.append(ga["text"])
    parts.append("")
    parts.append("📅 Условия участия:")
    parts.append("• Активная подписка на платный канал")
    if ga["min_level"] is not None:
        parts.append(f"• Минимальный уровень: L{ga['min_level']}")
    parts.append("")
    parts.append(f"⏳ Время завершения: <b>{format_datetime(ga['ends_at'])}</b>")
    parts.append("")
    parts.append("✅ Вам не нужно ничего делать — участвуют все подходящие подписчики автоматически!")
    return "\n".join(parts)


def _giveaway_prizes(ga) -> list[str]:
    raw = ga["prizes_json"] if "prizes_json" in ga.keys() else None
    if raw:
        try:
            return [str(item) for item in json.loads(raw)]
        except (TypeError, ValueError):
            pass
    return [str(ga["prize"])]


def build_giveaway_result_post(ga, winner, winners=None) -> str:
    parts = []
    if ga["title"]:
        parts.append(f"🎉 Результаты розыгрыша: <b>{ga['title']}</b>\n")
    else:
        parts.append("🎉 Результаты розыгрыша\n")
    parts.append(f"Призы: <b>{ga['prize']}</b>")
    parts.append("")
    if winners:
        prizes = _giveaway_prizes(ga)
        for index, current_winner in enumerate(winners):
            prize = prizes[index] if index < len(prizes) else prizes[-1]
            parts.append(f"🏆 {index + 1} место: {format_user_name(current_winner)} — {prize}")
        parts.append("")
        parts.append("Поздравляем! Свяжитесь с администрацией для получения приза.")
    elif winner:
        parts.append(f"🏆 Победитель: {format_user_name(winner)}")
        parts.append("")
        parts.append("Поздравляем! Свяжитесь с администрацией для получения приза.")
    else:
        parts.append("😔 К сожалению, нет участников, удовлетворяющих условиям.")
    return "\n".join(parts)


def build_giveaway_ended_post(ga, winner, winners=None) -> str:
    parts = []
    if ga["title"]:
        parts.append(f"🎁 <b>{ga['title']}</b>\n")
    parts.append(f"Призы: <b>{ga['prize']}</b>")
    parts.append(ga["text"])
    parts.append("")
    parts.append("📅 Условия участия:")
    parts.append("• Активная подписка на платный канал")
    if ga["min_level"] is not None:
        parts.append(f"• Минимальный уровень: L{ga['min_level']}")
    parts.append("")
    parts.append(f"⏰ Завершён: <b>{format_datetime(ga['ends_at'])}</b>")
    parts.append("")
    parts.append("────────────────────")
    if winners:
        prizes = _giveaway_prizes(ga)
        for index, current_winner in enumerate(winners):
            prize = prizes[index] if index < len(prizes) else prizes[-1]
            parts.append(f"🏆 {index + 1} место: {format_user_name(current_winner)} — {prize}")
        parts.append("")
        parts.append("Поздравляем! Свяжитесь с администрацией для получения приза.")
    elif winner:
        parts.append(f"🏆 Победитель: {format_user_name(winner)}")
        parts.append("")
        parts.append("Поздравляем! Свяжитесь с администрацией для получения приза.")
    else:
        parts.append("😔 К сожалению, нет участников, удовлетворяющих условиям.")
    return "\n".join(parts)


async def _collect_eligible_channel_users(
    repo: Repository,
    bot: Bot,
    min_level: int | None,
) -> list:
    from app.loader import is_subscribed_and_not_bot, get_channel_admin_ids_non_bot

    all_db_users = await repo.get_all_users()
    by_db_id: dict[int, dict] = {}
    admin_tg_ids = await get_channel_admin_ids_non_bot(bot)

    checked_tg_ids: set[int] = set()

    for u in all_db_users:
        tg_id = int(u["tg_id"])
        level = int(u["level"])
        if min_level is not None and level < min_level:
            continue
        if tg_id in checked_tg_ids:
            continue
        is_member, is_bot = await is_subscribed_and_not_bot(bot, tg_id)
        checked_tg_ids.add(tg_id)
        if is_member and not is_bot:
            by_db_id[int(u["id"])] = dict(u)

    for admin_tg_id in admin_tg_ids:
        if admin_tg_id in checked_tg_ids:
            continue
        checked_tg_ids.add(admin_tg_id)
        u = await repo.get_user_by_tg_id(admin_tg_id)
        if u is None:
            continue
        level = int(u["level"])
        if min_level is not None and level < min_level:
            continue
        by_db_id[int(u["id"])] = dict(u)

    logger.info(
        "Giveaway: collected %s eligible non-bot channel subscribers (min_level=%s)",
        len(by_db_id),
        min_level,
    )
    return list(by_db_id.values())


async def run_giveaway(
    repo: Repository,
    bot: Bot,
    ga,
    now: datetime | None = None,
) -> tuple[int | None, str | None]:
    if not await repo.claim_giveaway(int(ga["id"])):
        logger.info("Giveaway #%s was already claimed for finishing", ga["id"])
        return None, None
    now = now or datetime.utcnow()
    min_level = ga["min_level"]
    eligible = []
    try:
        eligible = await _collect_eligible_channel_users(repo, bot, min_level)
    except Exception as e:
        logger.error("Giveaway #%s: failed to collect eligible users: %s", ga["id"], e)
        eligible = await repo.get_eligible_users_for_giveaway(min_level=min_level)
    logger.info("Giveaway #%s: TOTAL %s eligible users", ga["id"], len(eligible))
    winners_count = int(ga["winners_count"] or 1) if "winners_count" in ga.keys() else 1
    selected: list[dict] = []
    available = list(eligible)
    for _ in range(min(winners_count, len(available))):
        winner_id = weighted_pick_users(available)
        if winner_id is None:
            break
        winner_row = next((user for user in available if int(user["id"]) == winner_id), None)
        if winner_row is None:
            break
        selected.append(winner_row)
        available.remove(winner_row)
    winner_id = int(selected[0]["id"]) if selected else None
    await repo.finish_giveaway(
        int(ga["id"]),
        winner_id,
        json.dumps([int(user["id"]) for user in selected]),
    )
    winner = None
    winner_tg = None
    winners = []
    if selected:
        prizes = _giveaway_prizes(ga)
        for index, selected_user in enumerate(selected):
            await repo.add_win(int(selected_user["id"]))
            current_winner = await repo.get_user_by_id(int(selected_user["id"]))
            if current_winner:
                winners.append(current_winner)
            if current_winner and current_winner["tg_id"]:
                prize = prizes[index] if index < len(prizes) else prizes[-1]
                try:
                    await bot.send_message(
                        chat_id=int(current_winner["tg_id"]),
                        text=(
                            f"🎉 Поздравляем! Вы заняли {index + 1} место в розыгрыше #{ga['id']}!\n"
                            f"Приз: <b>{prize}</b>\n\n"
                            "Свяжитесь с администратором для получения приза."
                        ),
                    )
                    logger.info("Giveaway #%s: notified winner %s", ga["id"], current_winner["tg_id"])
                except Exception as e:
                    logger.error("Giveaway #%s: failed to notify winner: %s", ga["id"], e)
        winner = winners[0] if winners else None
        winner_tg = winner["tg_id"] if winner else None
        if winner and winner_tg:
            pass
    if ga["channel_id"] and ga["channel_msg_id"]:
        channel_id = int(ga["channel_id"])
        msg_id = int(ga["channel_msg_id"])
        try:
            await bot.edit_message_text(
                chat_id=channel_id,
                message_id=msg_id,
                text=build_giveaway_ended_post(ga, winner, winners),
            )
            logger.info("Giveaway #%s: channel post edited", ga["id"])
        except Exception as e:
            logger.error("Giveaway #%s: failed to edit channel post: %s", ga["id"], e)
            try:
                await bot.send_message(
                    chat_id=channel_id,
                    text=build_giveaway_result_post(ga, winner, winners),
                    reply_to_message_id=msg_id,
                )
            except Exception as e2:
                logger.error("Giveaway #%s: failed to send result reply: %s", ga["id"], e2)
    admin_id = ga["admin_id"] if "admin_id" in ga.keys() else None
    if admin_id is not None:
        try:
            admin_row = await repo.get_user_by_id(int(admin_id))
            if admin_row and admin_row["tg_id"]:
                await bot.send_message(
                    chat_id=int(admin_row["tg_id"]),
                    text=build_giveaway_result_post(ga, winner, winners),
                )
        except Exception as e:
            logger.error("Giveaway #%s: failed to notify admin %s: %s", ga["id"], admin_id, e)
    return winner_id, winner_tg
