from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from app.config import settings


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id if event.from_user else 0
        return user_id in settings.ADMIN_IDS
