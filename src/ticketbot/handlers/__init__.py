"""Telegram update handlers exposed to the application factory."""

from ticketbot.handlers.admin import router, shutdown_active_generations

__all__ = ["router", "shutdown_active_generations"]
