"""Aiogram application factory and polling lifecycle."""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from ticketbot.config import Settings
from ticketbot.handlers import router, shutdown_active_generations
from ticketbot.middleware import register_admin_middleware
from ticketbot.services.generator import InvitationGenerator
from ticketbot.services.image_processor import ImageProcessor
from ticketbot.services.nano_banana import NanoBananaClient
from ticketbot.services.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


def build_generator(settings: Settings) -> InvitationGenerator:
    """Construct the image pipeline from validated settings."""

    provider = NanoBananaClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_image_model,
        image_size=settings.gemini_image_size,
        aspect_ratio=settings.gemini_image_aspect_ratio,
        timeout_seconds=settings.generation_timeout_seconds,
        max_attempts=settings.generation_max_attempts,
        max_concurrent=settings.max_concurrent_generations,
        reference_path=settings.reference_image_path,
    )
    processor = ImageProcessor(
        width=settings.output_image_width,
        height=settings.output_image_height,
    )
    renderer = TemplateRenderer(settings.reference_image_path)
    return InvitationGenerator(provider, processor, renderer)



async def run_bot(settings: Settings | None = None) -> None:
    """Start long polling and close network resources on shutdown."""

    settings = settings or Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher(storage=MemoryStorage())
    generator = build_generator(settings)

    register_admin_middleware(router, settings.admin_ids)
    dispatcher.include_router(router)

    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Bosh menyu"),
                BotCommand(command="cancel", description="Jarayonni bekor qilish"),
            ]
        )
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Workshop invitation bot started")
        await dispatcher.start_polling(
            bot,
            invitation_generator=generator,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        await shutdown_active_generations()
        await generator.aclose()
        await bot.session.close()
        logger.info("Workshop invitation bot stopped")
