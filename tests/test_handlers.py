from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from ticketbot.handlers import admin
from ticketbot.keyboards import (
    APPROVE_TEMPLATE_CALLBACK,
    CANCEL_CALLBACK,
    REGENERATE_CALLBACK,
    REUSE_SCHEDULE_CALLBACK,
    cancel_keyboard,
    review_keyboard,
    template_result_keyboard,
)
from ticketbot.states import InvitationStates


@pytest.fixture(autouse=True)
def clear_saved_schedules() -> None:
    admin._LAST_SCHEDULES.clear()


class FakeState:
    def __init__(self) -> None:
        self.current: Any = None
        self.data: dict[str, Any] = {}

    async def clear(self) -> None:
        self.current = None
        self.data.clear()

    async def set_state(self, state: Any) -> None:
        self.current = state

    async def get_state(self) -> Any:
        return self.current

    async def update_data(self, **values: Any) -> None:
        self.data.update(values)

    async def get_data(self) -> dict[str, Any]:
        return dict(self.data)


class FakeMessage:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.chat = SimpleNamespace(id=100)
        self.from_user = SimpleNamespace(id=200)
        self.message_id = 300
        self.answers: list[tuple[str, dict[str, Any]]] = []

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.answers.append((text, kwargs))


@pytest.mark.asyncio
async def test_full_fsm_collection_reaches_review() -> None:
    state = FakeState()
    await state.set_state(InvitationStates.full_name)

    await admin.receive_full_name(FakeMessage("  Jumayev   Shaxzod "), state)  # type: ignore[arg-type]
    assert state.current == InvitationStates.lead_id
    await admin.receive_lead_id(FakeMessage("387RVR"), state)  # type: ignore[arg-type]
    assert state.current == InvitationStates.start_time
    await admin.receive_start_time(FakeMessage("18:00"), state)  # type: ignore[arg-type]
    assert state.current == InvitationStates.event_date
    date_message = FakeMessage("Shanba 15-avgust")
    await admin.receive_event_date(date_message, state)  # type: ignore[arg-type]

    assert state.current == InvitationStates.review
    assert state.data == {
        "full_name": "Jumayev Shaxzod",
        "lead_id": "387RVR",
        "start_time": "18:00",
        "event_date": "Shanba 15-avgust",
    }
    assert admin._LAST_SCHEDULES[(100, 200)] == ("18:00", "Shanba 15-avgust")
    assert "Jumayev Shaxzod" in date_message.answers[-1][0]
    assert date_message.answers[-1][1]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_invalid_value_keeps_current_fsm_step() -> None:
    state = FakeState()
    await state.set_state(InvitationStates.start_time)
    message = FakeMessage("24:61")

    await admin.receive_start_time(message, state)  # type: ignore[arg-type]

    assert state.current == InvitationStates.start_time
    assert "start_time" not in state.data
    assert "HH:MM" in message.answers[-1][0]


@pytest.mark.asyncio
async def test_start_clears_stale_draft() -> None:
    state = FakeState()
    state.data = {"full_name": "Old Lead"}
    state.current = InvitationStates.review
    message = FakeMessage()

    await admin.start(message, state)  # type: ignore[arg-type]

    assert state.current is None
    assert state.data == {}
    assert message.answers[-1][1]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_reset_cancels_in_flight_generation() -> None:
    started = asyncio.Event()

    async def blocked_generation() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(blocked_generation())
    await started.wait()
    key = (100, 200)
    admin._ACTIVE_GENERATIONS[key] = task

    admin._cancel_active_generation(*key)

    with pytest.raises(asyncio.CancelledError):
        await task
    admin._ACTIVE_GENERATIONS.pop(key, None)


@pytest.mark.asyncio
async def test_shutdown_cancels_and_awaits_all_generations() -> None:
    cancelled = 0

    async def blocked_generation() -> None:
        nonlocal cancelled
        try:
            await asyncio.Event().wait()
        finally:
            cancelled += 1

    tasks = [asyncio.create_task(blocked_generation()) for _ in range(2)]
    await asyncio.sleep(0)
    admin._ACTIVE_GENERATIONS[(1, 1)] = tasks[0]
    admin._ACTIVE_GENERATIONS[(2, 2)] = tasks[1]

    await admin.shutdown_active_generations()

    assert cancelled == 2
    assert all(task.done() for task in tasks)
    admin._ACTIVE_GENERATIONS.clear()


@pytest.mark.asyncio
async def test_generation_status_cycles_until_cancelled() -> None:
    bot = AnimationBot(expected_edits=3)
    task = asyncio.create_task(
        admin._animate_generation_status(
            bot,
            chat_id=100,
            message_id=300,
            interval_seconds=0,
        )
    )

    await asyncio.wait_for(bot.enough_edits.wait(), timeout=1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert bot.edits == list(admin._GENERATION_FRAMES[1:4])


def test_inaccessible_message_has_no_thread_id() -> None:
    assert admin._message_thread_id(SimpleNamespace()) is None


def test_saved_schedule_button_is_above_cancel() -> None:
    keyboard = cancel_keyboard(("18:00", "Shanba 15-avgust"))

    assert keyboard.inline_keyboard[0][0].callback_data == REUSE_SCHEDULE_CALLBACK
    assert "18:00" in keyboard.inline_keyboard[0][0].text
    assert "Shanba 15-avgust" in keyboard.inline_keyboard[0][0].text
    assert keyboard.inline_keyboard[1][0].callback_data == CANCEL_CALLBACK


def test_template_first_keyboards_make_ai_an_explicit_fallback() -> None:
    review = review_keyboard()
    result = template_result_keyboard()

    assert "Bepul" in review.inline_keyboard[0][0].text
    assert result.inline_keyboard[0][0].callback_data == APPROVE_TEMPLATE_CALLBACK
    assert result.inline_keyboard[1][0].callback_data == REGENERATE_CALLBACK
    assert "AI" in result.inline_keyboard[1][0].text


@pytest.mark.asyncio
async def test_reuse_schedule_skips_time_and_date_inputs() -> None:
    state = FakeState()
    state.current = InvitationStates.start_time
    state.data = {"full_name": "Jumayev Shaxzod", "lead_id": "387RVR"}
    admin._LAST_SCHEDULES[(100, 200)] = ("18:00", "Shanba 15-avgust")
    callback = FakeCallback()

    await admin.reuse_schedule_callback(callback, state)  # type: ignore[arg-type]

    assert state.current == InvitationStates.review
    assert state.data["start_time"] == "18:00"
    assert state.data["event_date"] == "Shanba 15-avgust"
    assert callback.answer.calls[-1][0] == ("Oldingi sana va vaqt tanlandi",)
    assert "Jumayev Shaxzod" in callback.bot.messages[-1][1]


@pytest.mark.asyncio
async def test_approving_template_finishes_without_ai_generation() -> None:
    state = FakeState()
    state.current = InvitationStates.review
    state.data = {
        "full_name": "Jumayev Shaxzod",
        "lead_id": "387RVR",
        "start_time": "18:00",
        "event_date": "Shanba 15-avgust",
    }
    callback = FakeCallback()

    await admin.approve_template_callback(callback, state)  # type: ignore[arg-type]

    assert state.current is None
    assert state.data == {}
    assert callback.bot.reply_markup_edits == [(100, 300, None)]
    assert "AI chaqirilmadi" in callback.bot.messages[-1][1]


@pytest.mark.asyncio
async def test_stale_generation_callback_answers_and_clears() -> None:
    state = FakeState()
    state.current = InvitationStates.review
    state.data = {"full_name": "Expired Lead"}
    callback = SimpleNamespace(answer=AsyncAnswer())

    await admin.stale_generation_callback(callback, state)  # type: ignore[arg-type]

    assert state.current is None
    assert state.data == {}
    assert callback.answer.calls[-1][1]["show_alert"] is True


class AsyncAnswer:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str, dict[str, Any]]] = []
        self.reply_markup_edits: list[tuple[int, int, Any]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> None:
        self.messages.append((chat_id, text, kwargs))

    async def edit_message_reply_markup(
        self,
        *,
        chat_id: int,
        message_id: int,
        reply_markup: Any,
    ) -> None:
        self.reply_markup_edits.append((chat_id, message_id, reply_markup))


class FakeCallback:
    def __init__(self) -> None:
        self.message = FakeMessage()
        self.from_user = SimpleNamespace(id=200)
        self.answer = AsyncAnswer()
        self.bot = FakeBot()


class AnimationBot:
    def __init__(self, expected_edits: int) -> None:
        self.expected_edits = expected_edits
        self.edits: list[str] = []
        self.enough_edits = asyncio.Event()

    async def edit_message_text(
        self,
        *,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: Any,
    ) -> None:
        assert chat_id == 100
        assert message_id == 300
        assert parse_mode is not None
        self.edits.append(text)
        if len(self.edits) >= self.expected_edits:
            self.enough_edits.set()
