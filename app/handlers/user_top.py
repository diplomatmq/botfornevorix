from __future__ import annotations

from aiogram import Router, F
from aiogram.types import Message

from app.database.repo import Repository
from app.handlers.common import ensure_user
from app.utils.formatters import format_user_name

router = Router()


@router.message(F.text == "🏆 Топ рефоводов")
async def top_referrers(message: Message, repo: Repository):
    await ensure_user(repo, message)
    rows = await repo.top_referrers(limit=30)
    if not rows:
        await message.answer("🏆 Пока ни у кого нет рефералов.")
        return
    lines = ["🏆 <b>Топ рефоводов</b>\n"]
    for idx, r in enumerate(rows, start=1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
        lines.append(
            f"{medal} {format_user_name(r)} — L{r['level']} — <b>{r['refs_count']}</b> рефералов"
        )
    await message.answer("\n".join(lines))
