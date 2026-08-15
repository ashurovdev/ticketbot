"""Inline keyboards used by the administrator invitation flow."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CREATE_CALLBACK = "invitation:create"
CONFIRM_CALLBACK = "invitation:confirm"
CANCEL_CALLBACK = "invitation:cancel"
REGENERATE_CALLBACK = "invitation:regenerate"
NEW_CALLBACK = "invitation:new"
REUSE_SCHEDULE_CALLBACK = "invitation:reuse_schedule"
APPROVE_TEMPLATE_CALLBACK = "invitation:approve_template"


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Return the idle-state keyboard."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎟 Taklifnoma yaratish",
                    callback_data=CREATE_CALLBACK,
                )
            ]
        ]
    )


def cancel_keyboard(
    saved_schedule: tuple[str, str] | None = None,
) -> InlineKeyboardMarkup:
    """Return collection actions, optionally with the last schedule shortcut."""

    rows: list[list[InlineKeyboardButton]] = []
    if saved_schedule is not None:
        start_time, event_date = saved_schedule
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🕒 {start_time} · 📅 {event_date}",
                    callback_data=REUSE_SCHEDULE_CALLBACK,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="❌ Bekor qilish",
                callback_data=CANCEL_CALLBACK,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def review_keyboard() -> InlineKeyboardMarkup:
    """Return actions for a complete, not-yet-generated draft."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚙️ Bepul usulda yaratish",
                    callback_data=CONFIRM_CALLBACK,
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Bekor qilish",
                    callback_data=CANCEL_CALLBACK,
                )
            ],
        ]
    )


def template_result_keyboard() -> InlineKeyboardMarkup:
    """Let the admin accept the free render or explicitly spend on AI."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Shu rasmni tasdiqlash",
                    callback_data=APPROVE_TEMPLATE_CALLBACK,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🤖 AI bilan qayta chizish",
                    callback_data=REGENERATE_CALLBACK,
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Yangi taklifnoma",
                    callback_data=NEW_CALLBACK,
                )
            ],
        ]
    )


def result_keyboard() -> InlineKeyboardMarkup:
    """Return actions available after a paid AI generation succeeds."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤖 AI bilan qayta yaratish",
                    callback_data=REGENERATE_CALLBACK,
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Yangi taklifnoma",
                    callback_data=NEW_CALLBACK,
                )
            ],
        ]
    )


# Readable aliases for integrations that use action-oriented names.
create_keyboard = main_menu_keyboard
confirm_keyboard = review_keyboard
generated_keyboard = result_keyboard


__all__ = [
    "APPROVE_TEMPLATE_CALLBACK",
    "CANCEL_CALLBACK",
    "CONFIRM_CALLBACK",
    "CREATE_CALLBACK",
    "NEW_CALLBACK",
    "REGENERATE_CALLBACK",
    "REUSE_SCHEDULE_CALLBACK",
    "cancel_keyboard",
    "confirm_keyboard",
    "create_keyboard",
    "generated_keyboard",
    "main_menu_keyboard",
    "result_keyboard",
    "review_keyboard",
    "template_result_keyboard",
]
