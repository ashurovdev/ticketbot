"""High-level invitation generation pipeline."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Protocol

from ticketbot.models.invitation import InvitationData
from ticketbot.services.image_processor import ImageProcessor
from ticketbot.services.template_renderer import TemplateRenderer


class _RawImage(Protocol):
    data: bytes
    mime_type: str


class _ImageProvider(Protocol):
    async def generate(self, invitation: InvitationData) -> _RawImage: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class GeneratedInvitation:
    data: bytes
    mime_type: str
    filename: str


class InvitationGenerator:
    """Provide a free template-first path and an explicit AI fallback path."""

    def __init__(
        self,
        provider: _ImageProvider,
        processor: ImageProcessor,
        renderer: TemplateRenderer,
    ) -> None:
        self._provider = provider
        self._processor = processor
        self._renderer = renderer

    async def generate_template(self, invitation: InvitationData) -> GeneratedInvitation:
        rendered = await asyncio.to_thread(self._renderer.render, invitation)
        png = await asyncio.to_thread(self._processor.normalize_png, rendered)
        return self._result(invitation, png)

    async def generate_ai(self, invitation: InvitationData) -> GeneratedInvitation:
        raw = await self._provider.generate(invitation)
        png = await asyncio.to_thread(self._processor.normalize_png, raw.data)
        return self._result(invitation, png)

    async def generate(self, invitation: InvitationData) -> GeneratedInvitation:
        """Backward-compatible alias for the explicit AI path."""

        return await self.generate_ai(invitation)

    @staticmethod
    def _result(invitation: InvitationData, png: bytes) -> GeneratedInvitation:
        safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", invitation.lead_id).strip("_")
        safe_id = safe_id[:48] or "lead"
        return GeneratedInvitation(
            data=png,
            mime_type="image/png",
            filename=f"invitation_{safe_id}.png",
        )

    async def aclose(self) -> None:
        await self._provider.aclose()
