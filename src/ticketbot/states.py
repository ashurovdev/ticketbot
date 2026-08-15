"""Finite-state machine states for the invitation creation flow."""

from aiogram.fsm.state import State, StatesGroup


class InvitationStates(StatesGroup):
    """One-at-a-time invitation draft collected from an administrator."""

    full_name = State()
    lead_id = State()
    start_time = State()
    event_date = State()
    review = State()


# A descriptive alias kept for callers that prefer to name the state group after
# the form rather than the domain object.
InvitationForm = InvitationStates


__all__ = ["InvitationForm", "InvitationStates"]
