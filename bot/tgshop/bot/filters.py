from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message


class IsAdmin(Filter):
    """Passes updates from users listed in ``ADMIN_IDS`` (injected as ``admin_ids``)."""

    async def __call__(self, event: Message | CallbackQuery, admin_ids: frozenset[int]) -> bool:
        user = event.from_user
        return user is not None and user.id in admin_ids
