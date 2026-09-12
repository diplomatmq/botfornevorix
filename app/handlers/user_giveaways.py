from __future__ import annotations

from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message

from app.database.repo import Repository
from app.handlers.common import ensure_user
from app.utils.formatters import format_datetime

router = Router()


@router.message(F.text == "🎟️ Розыгрыши")
async def list_giveaways(message: Message, repo: Repository):
    await ensure_user(repo, message)
    rows = await repo._rows(
        "SELECT * FROM giveaways ORDER BY created_at DESC LIMIT 15"
    )
    if not rows:
        await message.answer("🎟️ Пока нет розыгрышей.")
        return
    now = datetime.utcnow()
    lines = ["🎟️ <b>Активные и прошедшие розыгрыши</b>\n"]
    for g in rows:
        status_icon = "🟢" if g["status"] == "active" else ("✅" if g["winner_id"] else "⚪")
        level_part = ""
        if g["min_level"] is not None:
            level_part = f"Мин. уровень: L{g['min_level']}\n"
        winner_part = ""
        if g["status"] == "ended" and g["winner_id"]:
            w = await repo.get_user_by_id(int(g["winner_id"]))
            if w:
                winner_part = f"🏆 Победитель: @{w['username'] or 'id'+str(w['tg_id'])}\n"
            else:
                winner_part = f"🏆 Победитель ID: {g['winner_id']}\n"
        elif g["status"] == "active":
            winner_part = f"⏳ Завершение: {format_datetime(g['ends_at'])}\n"
        lines.append(
            f"{status_icon} <b>#{g['id']}</b> Приз: {g['prize']}\n"
            f"{level_part}"
            f"{winner_part}"
        )
    await message.answer("\n".join(lines))
