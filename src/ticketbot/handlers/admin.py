"""Administrator-only FSM workflow for generating workshop invitations."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from contextlib import suppress
from html import escape
from typing import Any, Protocol

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.chat_action import ChatActionSender

from ticketbot.keyboards import (
    APPROVE_TEMPLATE_CALLBACK,
    CANCEL_CALLBACK,
    CONFIRM_CALLBACK,
    CREATE_CALLBACK,
    NEW_CALLBACK,
    REGENERATE_CALLBACK,
    REUSE_SCHEDULE_CALLBACK,
    cancel_keyboard,
    main_menu_keyboard,
    result_keyboard,
    review_keyboard,
    template_result_keyboard,
)
from ticketbot.models.invitation import InvitationData, ValidationError
from ticketbot.states import InvitationStates

router = Router(name="invitation-admin")

_LOGGER = logging.getLogger(__name__)
_ACTIVE_GENERATIONS: dict[tuple[int, int], asyncio.Task[Any]] = {}
_LAST_SCHEDULES: dict[tuple[int, int], tuple[str, str]] = {}

_GENERATION_FRAMES = (
    "🎨 <b>Taklifnoma yaratilmoqda</b>\n\n▰▱▱▱▱\n🧩 Kompozitsiya tayyorlanmoqda",
    "🖌️ <b>Taklifnoma yaratilmoqda</b>\n\n▰▰▱▱▱\n🎨 Rang va dizayn ishlanmoqda",
    "✍️ <b>Taklifnoma yaratilmoqda</b>\n\n▰▰▰▱▱\n👤 Ma’lumotlar joylashtirilmoqda",
    "🪄 <b>Taklifnoma yaratilmoqda</b>\n\n▰▰▰▰▱\n✨ Yakuniy ishlov berilmoqda",
    "⏳ <b>Taklifnoma yaratilmoqda</b>\n\n▰▰▰▰▰\n🖼️ Rasm tayyorlanmoqda",
    "✨ <b>Taklifnoma yaratilmoqda</b>\n\n▱▰▰▰▰\n🔍 Sifat tekshirilmoqda",
)

_FULL_NAME = "full_name"
_LEAD_ID = "lead_id"
_START_TIME = "start_time"
_EVENT_DATE = "event_date"

_VALID_DEFAULTS = {
    _FULL_NAME: "Ali Valiyev",
    _LEAD_ID: "TEST-1",
    _START_TIME: "12:00",
    _EVENT_DATE: "Shanba 15-avgust",
}

_VALIDATION_HINTS = {
    _FULL_NAME: (
        "Ism-familiya harflar, bo‘sh joy, apostrof va tiredan iborat bo‘lishi "
        "hamda layoutga sig‘ishi kerak."
    ),
    _LEAD_ID: "ID 1–20 ta lotin harfi, raqam, tire yoki underscore dan iborat bo‘lsin.",
    _START_TIME: "Vaqtni 24 soatlik HH:MM formatida kiriting (masalan, 18:00).",
    _EVENT_DATE: "Sana/kuni bitta qatorda va 36 belgidan oshmagan bo‘lishi kerak.",
}


class GeneratedInvitation(Protocol):
    """Minimal generator response used by the Telegram transport layer."""

    data: bytes
    mime_type: str
    filename: str


class InvitationGenerator(Protocol):
    """Dependency injected into generation handlers by aiogram."""

    async def generate_template(
        self, invitation: InvitationData
    ) -> GeneratedInvitation: ...

    async def generate_ai(self, invitation: InvitationData) -> GeneratedInvitation: ...


def _cancel_active_generation(chat_id: int, user_id: int) -> None:
    """Cancel an in-flight request when its draft is reset or cancelled."""

    task = _ACTIVE_GENERATIONS.get((chat_id, user_id))
    if task is not None and task is not asyncio.current_task() and not task.done():
        task.cancel()


async def shutdown_active_generations() -> None:
    """Cancel and await generation handlers before provider/bot shutdown."""

    current_task = asyncio.current_task()
    tasks = {
        task
        for task in _ACTIVE_GENERATIONS.values()
        if task is not current_task and not task.done()
    }
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _animate_generation_status(
    bot: Any,
    chat_id: int,
    message_id: int,
    *,
    interval_seconds: float = 1.1,
) -> None:
    """Cycle one Telegram status message until the generation task finishes."""

    frame_index = 1
    while True:
        await asyncio.sleep(interval_seconds)
        frame = _GENERATION_FRAMES[frame_index % len(_GENERATION_FRAMES)]
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=frame,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            # Animation is decorative; an edit failure must never fail image generation.
            return
        frame_index += 1


def _message_thread_id(message: Any) -> int | None:
    """Support both Message and aiogram's InaccessibleMessage callback payload."""

    return getattr(message, "message_thread_id", None)


def _schedule_key(message: Message) -> tuple[int, int] | None:
    if message.from_user is None:
        return None
    return message.chat.id, message.from_user.id


def _saved_schedule(message: Message) -> tuple[str, str] | None:
    key = _schedule_key(message)
    return _LAST_SCHEDULES.get(key) if key is not None else None


def _validation_message(error: ValidationError) -> str:
    detail = _VALIDATION_HINTS.get(error.field, "Kiritilgan qiymat noto‘g‘ri.")
    return f"⚠️ {escape(detail)}\n\nQiymatni qayta kiriting."


def _validate_field(field: str, value: str) -> str:
    """Validate one field through the domain factory using safe placeholders."""

    candidate = dict(_VALID_DEFAULTS)
    candidate[field] = value
    invitation = InvitationData.from_raw(
        candidate[_FULL_NAME],
        candidate[_LEAD_ID],
        candidate[_START_TIME],
        candidate[_EVENT_DATE],
    )
    return str(getattr(invitation, field))


def _build_invitation(data: Mapping[str, Any]) -> InvitationData:
    return InvitationData.from_raw(
        str(data[_FULL_NAME]),
        str(data[_LEAD_ID]),
        str(data[_START_TIME]),
        str(data[_EVENT_DATE]),
    )


def _review_text(data: Mapping[str, Any]) -> str:
    return (
        "<b>Ma’lumotlarni tekshiring:</b>\n\n"
        f"👤 <b>Ism-familiya:</b> {escape(str(data[_FULL_NAME]))}\n"
        f"🆔 <b>ID:</b> {escape(str(data[_LEAD_ID]))}\n"
        f"🕒 <b>Vaqt:</b> {escape(str(data[_START_TIME]))}\n"
        f"📅 <b>Sana/kuni:</b> {escape(str(data[_EVENT_DATE]))}\n\n"
        "Hammasi to‘g‘ri bo‘lsa, tasdiqlang."
    )


async def _reply_for_callback(
    callback: CallbackQuery,
    text: str,
    **kwargs: Any,
) -> None:
    if callback.message is None:
        return

    await callback.bot.send_message(
        chat_id=callback.message.chat.id,
        text=text,
        message_thread_id=_message_thread_id(callback.message),
        **kwargs,
    )


async def _begin_draft(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is not None:
        _cancel_active_generation(callback.message.chat.id, callback.from_user.id)
    await state.clear()
    await state.set_state(InvitationStates.full_name)
    await _reply_for_callback(
        callback,
        "Ishtirokchining <b>ism-familiyasini</b> kiriting:",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(),
    )


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    """Reset any stale draft and show the administrator main menu."""

    if message.from_user is not None:
        _cancel_active_generation(message.chat.id, message.from_user.id)
    await state.clear()
    await message.answer(
        "Assalomu alaykum! Workshop uchun shaxsiy taklifnoma yaratishingiz mumkin.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    """Cancel a draft from any FSM step."""

    if message.from_user is not None:
        _cancel_active_generation(message.chat.id, message.from_user.id)
    await state.clear()
    await message.answer(
        "Jarayon bekor qilindi.",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data == CANCEL_CALLBACK)
async def cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Bekor qilindi")
    if callback.message is not None:
        _cancel_active_generation(callback.message.chat.id, callback.from_user.id)
    await state.clear()
    await _reply_for_callback(
        callback,
        "Jarayon bekor qilindi.",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data == CREATE_CALLBACK)
async def create_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await _begin_draft(callback, state)


@router.callback_query(F.data == NEW_CALLBACK)
async def new_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await _begin_draft(callback, state)


@router.message(InvitationStates.full_name)
async def receive_full_name(message: Message, state: FSMContext) -> None:
    if message.text is None:
        await message.answer(
            "Ism-familiyani matn ko‘rinishida yuboring.",
            reply_markup=cancel_keyboard(),
        )
        return

    try:
        full_name = _validate_field(_FULL_NAME, message.text)
    except ValidationError as error:
        await message.answer(
            _validation_message(error),
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(full_name=full_name)
    await state.set_state(InvitationStates.lead_id)
    await message.answer(
        "Lead/ishtirokchining <b>ID</b> sini kiriting:",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(),
    )


@router.message(InvitationStates.lead_id)
async def receive_lead_id(message: Message, state: FSMContext) -> None:
    if message.text is None:
        await message.answer(
            "ID ni matn ko‘rinishida yuboring.",
            reply_markup=cancel_keyboard(),
        )
        return

    try:
        lead_id = _validate_field(_LEAD_ID, message.text)
    except ValidationError as error:
        await message.answer(
            _validation_message(error),
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(lead_id=lead_id)
    await state.set_state(InvitationStates.start_time)
    await message.answer(
        "Boshlanish vaqtini <b>HH:MM</b> formatida kiriting (masalan, 18:00):",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(_saved_schedule(message)),
    )


@router.message(InvitationStates.start_time)
async def receive_start_time(message: Message, state: FSMContext) -> None:
    if message.text is None:
        await message.answer(
            "Vaqtni matn ko‘rinishida, HH:MM formatida yuboring.",
            reply_markup=cancel_keyboard(_saved_schedule(message)),
        )
        return

    try:
        start_time = _validate_field(_START_TIME, message.text)
    except ValidationError as error:
        await message.answer(
            _validation_message(error),
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_keyboard(_saved_schedule(message)),
        )
        return

    await state.update_data(start_time=start_time)
    await state.set_state(InvitationStates.event_date)
    await message.answer(
        "Tadbir <b>sana/kuni</b> ni kiriting (masalan, Shanba 15-avgust):",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(),
    )


@router.message(InvitationStates.event_date)
async def receive_event_date(message: Message, state: FSMContext) -> None:
    if message.text is None:
        await message.answer(
            "Sana/kunni matn ko‘rinishida yuboring.",
            reply_markup=cancel_keyboard(),
        )
        return

    try:
        event_date = _validate_field(_EVENT_DATE, message.text)
        draft = await state.get_data()
        complete_draft = {**draft, _EVENT_DATE: event_date}
        invitation = _build_invitation(complete_draft)
    except (KeyError, ValidationError) as error:
        if isinstance(error, ValidationError):
            text = _validation_message(error)
        else:
            text = "⚠️ Draft ma’lumotlari topilmadi. /start dan qayta boshlang."
        await message.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_keyboard(),
        )
        return

    schedule_key = _schedule_key(message)
    if schedule_key is not None:
        _LAST_SCHEDULES[schedule_key] = (
            invitation.start_time,
            invitation.event_date,
        )
    await state.update_data(event_date=event_date)
    await state.set_state(InvitationStates.review)
    await message.answer(
        _review_text(complete_draft),
        parse_mode=ParseMode.HTML,
        reply_markup=review_keyboard(),
    )


@router.callback_query(
    InvitationStates.start_time,
    F.data == REUSE_SCHEDULE_CALLBACK,
)
async def reuse_schedule_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Apply the admin's last date/time and skip both schedule text inputs."""

    if callback.message is None:
        await callback.answer()
        return

    key = (callback.message.chat.id, callback.from_user.id)
    saved_schedule = _LAST_SCHEDULES.get(key)
    if saved_schedule is None:
        await callback.answer(
            "Oldingi sana va vaqt topilmadi. Qiymatni qo‘lda kiriting.",
            show_alert=True,
        )
        return

    start_time, event_date = saved_schedule
    draft = await state.get_data()
    complete_draft = {
        **draft,
        _START_TIME: start_time,
        _EVENT_DATE: event_date,
    }
    try:
        invitation = _build_invitation(complete_draft)
    except (KeyError, ValidationError):
        await callback.answer(
            "Draft eskirgan. Yangi taklifnoma yaratishni boshlang.",
            show_alert=True,
        )
        return

    await callback.answer("Oldingi sana va vaqt tanlandi")
    await state.update_data(
        start_time=invitation.start_time,
        event_date=invitation.event_date,
    )
    await state.set_state(InvitationStates.review)
    await _reply_for_callback(
        callback,
        _review_text(complete_draft),
        parse_mode=ParseMode.HTML,
        reply_markup=review_keyboard(),
    )


@router.callback_query(F.data == REUSE_SCHEDULE_CALLBACK)
async def stale_schedule_callback(callback: CallbackQuery) -> None:
    await callback.answer(
        "Bu sana/vaqt tugmasi eskirgan. Yangi taklifnomada qayta tanlang.",
        show_alert=True,
    )


async def _generate_invitation(
    callback: CallbackQuery,
    state: FSMContext,
    invitation_generator: InvitationGenerator,
    *,
    use_ai: bool,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    generation_key = (callback.message.chat.id, callback.from_user.id)
    # Dispatcher handlers share one event loop. With no ``await`` between this
    # membership check and ``add``, a second tap cannot enter the generation
    # section for the same admin/chat pair.
    active_task = _ACTIVE_GENERATIONS.get(generation_key)
    if active_task is not None and not active_task.done():
        await callback.answer("Taklifnoma allaqachon yaratilmoqda.", show_alert=True)
        return
    generation_task = asyncio.current_task()
    if generation_task is None:  # pragma: no cover - asyncio always provides it here.
        await callback.answer("Ichki async xatolik.", show_alert=True)
        return
    _ACTIVE_GENERATIONS[generation_key] = generation_task

    try:
        await callback.answer(
            "AI orqali yaratilmoqda…" if use_ai else "Bepul template to‘ldirilmoqda…"
        )
        data = await state.get_data()
        try:
            invitation = _build_invitation(data)
        except (KeyError, ValidationError):
            await state.clear()
            await _reply_for_callback(
                callback,
                "Draft eskirgan yoki noto‘g‘ri. Yangi taklifnoma yaratishni boshlang.",
                reply_markup=main_menu_keyboard(),
            )
            return

        chat_id = callback.message.chat.id
        status_message: Any | None = None
        animation_task: asyncio.Task[Any] | None = None
        try:
            if use_ai:
                status_message = await callback.bot.send_message(
                    chat_id=chat_id,
                    text=_GENERATION_FRAMES[0],
                    parse_mode=ParseMode.HTML,
                    message_thread_id=_message_thread_id(callback.message),
                )
                animation_task = asyncio.create_task(
                    _animate_generation_status(
                        callback.bot,
                        chat_id,
                        status_message.message_id,
                    )
                )
            async with ChatActionSender.upload_document(
                bot=callback.bot,
                chat_id=chat_id,
                message_thread_id=_message_thread_id(callback.message),
            ):
                if use_ai:
                    generated = await invitation_generator.generate_ai(invitation)
                else:
                    generated = await invitation_generator.generate_template(invitation)

            image = BufferedInputFile(generated.data, filename=generated.filename)
            await callback.bot.send_document(
                chat_id=chat_id,
                document=image,
                caption=(
                    "🤖 AI orqali taklifnoma tayyor. Natijani tekshiring."
                    if use_ai
                    else "⚙️ Bepul algoritm orqali tayyorlandi. Ma’qul bo‘lsa "
                    "tasdiqlang, aks holda AI bilan qayta chizing."
                ),
                message_thread_id=_message_thread_id(callback.message),
                reply_markup=(result_keyboard() if use_ai else template_result_keyboard()),
            )
        except Exception as error:
            # Service-layer exceptions must not expose provider details, credentials,
            # prompts, or participant PII in Telegram responses or application logs.
            _LOGGER.error(
                "Invitation generation or delivery failed; exception type=%s",
                type(error).__name__,
            )
            await _reply_for_callback(
                callback,
                "Taklifnomani yaratib bo‘lmadi. Birozdan keyin qayta urinib ko‘ring.",
                reply_markup=review_keyboard(),
            )
        finally:
            if animation_task is not None:
                animation_task.cancel()
                await asyncio.gather(animation_task, return_exceptions=True)
            if status_message is not None:
                with suppress(Exception):
                    await callback.bot.delete_message(
                        chat_id=chat_id,
                        message_id=status_message.message_id,
                    )
    finally:
        if _ACTIVE_GENERATIONS.get(generation_key) is generation_task:
            _ACTIVE_GENERATIONS.pop(generation_key, None)


@router.callback_query(InvitationStates.review, F.data == CONFIRM_CALLBACK)
async def confirm_callback(
    callback: CallbackQuery,
    state: FSMContext,
    invitation_generator: InvitationGenerator,
) -> None:
    await _generate_invitation(
        callback,
        state,
        invitation_generator,
        use_ai=False,
    )


@router.callback_query(InvitationStates.review, F.data == REGENERATE_CALLBACK)
async def regenerate_callback(
    callback: CallbackQuery,
    state: FSMContext,
    invitation_generator: InvitationGenerator,
) -> None:
    await _generate_invitation(
        callback,
        state,
        invitation_generator,
        use_ai=True,
    )


@router.callback_query(InvitationStates.review, F.data == APPROVE_TEMPLATE_CALLBACK)
async def approve_template_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Finish without an AI call after the admin accepts the free render."""

    await callback.answer("Taklifnoma tasdiqlandi")
    if callback.message is not None:
        with suppress(Exception):
            await callback.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                reply_markup=None,
            )
    await state.clear()
    await _reply_for_callback(
        callback,
        "✅ Taklifnoma tasdiqlandi. AI chaqirilmadi va generatsiya xarajati bo‘lmadi.",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(
    F.data.in_({APPROVE_TEMPLATE_CALLBACK, CONFIRM_CALLBACK, REGENERATE_CALLBACK})
)
async def stale_generation_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Stop the Telegram spinner when a button outlives its in-memory draft."""

    await state.clear()
    await callback.answer(
        "Draft eskirgan. /start orqali yangi taklifnoma boshlang.",
        show_alert=True,
    )


__all__ = ["router", "shutdown_active_generations"]
