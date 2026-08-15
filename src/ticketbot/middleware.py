"""Authorization middleware for administrator-only bot updates."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Router
from aiogram.types import CallbackQuery, Message, TelegramObject

UNAUTHORIZED_MESSAGE = "⛔️ Sizda bu botdan foydalanish uchun ruxsat yo‘q."


class AdminOnlyMiddleware(BaseMiddleware):
    """Stop updates from Telegram users outside the configured allowlist."""

    def __init__(self, admin_ids: frozenset[int]) -> None:
        self.admin_ids = frozenset(admin_ids)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None and isinstance(event, (CallbackQuery, Message)):
            user = event.from_user
        if user is not None and user.id in self.admin_ids:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer(UNAUTHORIZED_MESSAGE, show_alert=True)
        elif isinstance(event, Message):
            await event.answer(UNAUTHORIZED_MESSAGE)

        return None


# Short alias for application wiring and backwards-compatible imports.
AdminMiddleware = AdminOnlyMiddleware


def register_admin_middleware(
    router: Router,
    admin_ids: frozenset[int],
) -> None:
    """Attach authorization to both message and callback update observers."""

    middleware = AdminOnlyMiddleware(admin_ids)
    router.message.outer_middleware(middleware)
    router.callback_query.outer_middleware(middleware)


__all__ = [
    "UNAUTHORIZED_MESSAGE",
    "AdminMiddleware",
    "AdminOnlyMiddleware",
    "register_admin_middleware",
]
