from unittest.mock import AsyncMock

import pytest
from aiogram.types import Message, TelegramObject, User

from ticketbot.middleware import AdminOnlyMiddleware


@pytest.mark.asyncio
async def test_admin_middleware_allows_configured_user() -> None:
    middleware = AdminOnlyMiddleware(frozenset({123}))
    handler = AsyncMock(return_value="handled")
    event = TelegramObject()
    data = {"event_from_user": User(id=123, is_bot=False, first_name="Admin")}

    result = await middleware(handler, event, data)

    assert result == "handled"
    handler.assert_awaited_once_with(event, data)


@pytest.mark.asyncio
async def test_admin_middleware_blocks_unknown_user_without_dispatch() -> None:
    middleware = AdminOnlyMiddleware(frozenset({123}))
    handler = AsyncMock()
    event = TelegramObject()
    data = {"event_from_user": User(id=999, is_bot=False, first_name="Unknown")}

    result = await middleware(handler, event, data)

    assert result is None
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_middleware_answers_unauthorized_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    middleware = AdminOnlyMiddleware(frozenset({123}))
    handler = AsyncMock()
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    event = Message.model_construct()
    data = {"event_from_user": User(id=999, is_bot=False, first_name="Unknown")}

    await middleware(handler, event, data)

    answer.assert_awaited_once()
    handler.assert_not_awaited()
