"""Async Nano Banana Pro adapter for reference-based invitation generation."""

from __future__ import annotations

import asyncio
import base64
import binascii
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from google import genai

from ticketbot.models.invitation import InvitationData
from ticketbot.services.prompt_builder import build_invitation_prompt

_REFERENCE_MIME_TYPES: Final = {
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_RETRYABLE_STATUS_CODES: Final = frozenset({408, 409, 425, 429})
_INITIAL_RETRY_DELAY_SECONDS: Final = 0.25
_MAX_RETRY_DELAY_SECONDS: Final = 2.0


class NanoBananaError(RuntimeError):
    """Base error raised by the Nano Banana integration."""


class NanoBananaResponseError(NanoBananaError):
    """Raised when Gemini completes without a usable image payload."""


class NanoBananaGenerationError(NanoBananaError):
    """Raised when an invitation cannot be generated within the attempt budget."""


@dataclass(frozen=True, slots=True)
class RawGeneratedImage:
    """Unprocessed image bytes returned by the Gemini image model."""

    data: bytes
    mime_type: str


class NanoBananaClient:
    """Generate invitations with Gemini's async Interactions API.

    ``client`` may be either a normal ``google.genai.Client`` (with an ``aio``
    property) or an async-client-shaped test double. The reference is loaded
    once at startup so configuration errors fail before an administrator starts
    a Telegram workflow.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        image_size: str,
        aspect_ratio: str,
        timeout_seconds: float,
        max_attempts: int,
        max_concurrent: int,
        reference_path: str | Path,
        client: Any | None = None,
    ) -> None:
        if client is None and not api_key.strip():
            raise ValueError("api_key must not be empty")
        if not model.strip():
            raise ValueError("model must not be empty")
        if image_size not in {"1K", "2K", "4K"}:
            raise ValueError("image_size must be one of: 1K, 2K, 4K")
        if not aspect_ratio.strip():
            raise ValueError("aspect_ratio must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")

        self._model = model
        self._image_size = image_size
        self._aspect_ratio = aspect_ratio
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._closed = False

        self._reference_path = Path(reference_path)
        try:
            self._reference_mime_type = _REFERENCE_MIME_TYPES[
                self._reference_path.suffix.lower()
            ]
        except KeyError as exc:
            supported = ", ".join(sorted(_REFERENCE_MIME_TYPES))
            raise ValueError(f"reference image must use one of: {supported}") from exc

        self._reference_data = self._reference_path.read_bytes()
        if not self._reference_data:
            raise ValueError("reference image must not be empty")
        self._reference_base64 = base64.b64encode(self._reference_data).decode("ascii")

        self._root_client = client if client is not None else genai.Client(api_key=api_key)
        self._client = getattr(self._root_client, "aio", self._root_client)

    async def generate(self, invitation: InvitationData) -> RawGeneratedImage:
        """Generate one image, retrying only transient and invalid-output failures."""

        if self._closed:
            raise NanoBananaError("Nano Banana client is closed")

        prompt = build_invitation_prompt(invitation)
        request_input = [
            {"type": "text", "text": prompt},
            {
                "type": "image",
                "mime_type": self._reference_mime_type,
                "data": self._reference_base64,
            },
        ]
        response_format = {
            "type": "image",
            "aspect_ratio": self._aspect_ratio,
            "image_size": self._image_size,
        }

        for attempt in range(1, self._max_attempts + 1):
            try:
                interaction = await self._create_interaction(
                    request_input=request_input,
                    response_format=response_format,
                )
                return _extract_image(interaction)
            except Exception as exc:
                retryable = _is_retryable(exc)
                if not retryable or attempt >= self._max_attempts:
                    raise NanoBananaGenerationError(
                        f"Nano Banana generation failed after {attempt} attempt(s)"
                    ) from exc

                delay = min(
                    _INITIAL_RETRY_DELAY_SECONDS * (2 ** (attempt - 1)),
                    _MAX_RETRY_DELAY_SECONDS,
                )
                await asyncio.sleep(delay)

        raise AssertionError("attempt loop exited unexpectedly")

    async def _create_interaction(
        self,
        *,
        request_input: list[dict[str, str]],
        response_format: dict[str, str],
    ) -> Any:
        # Limit only live API calls. A retry backoff does not occupy a slot and
        # prevent another administrator's request from making progress.
        async with self._semaphore:
            async with asyncio.timeout(self._timeout_seconds):
                return await self._client.interactions.create(
                    model=self._model,
                    input=request_input,
                    response_format=response_format,
                    store=False,
                )

    async def aclose(self) -> None:
        """Close async and sync transports exactly once."""

        if self._closed:
            return
        self._closed = True

        async_close = getattr(self._client, "aclose", None)
        try:
            if async_close is not None:
                result = async_close()
                if inspect.isawaitable(result):
                    await result
        finally:
            if self._root_client is not self._client:
                sync_close = getattr(self._root_client, "close", None)
                if sync_close is not None:
                    result = sync_close()
                    if inspect.isawaitable(result):
                        await result


def _extract_image(interaction: Any) -> RawGeneratedImage:
    image = getattr(interaction, "output_image", None)
    if image is None:
        raise NanoBananaResponseError("Gemini response did not contain an image")

    encoded_data = getattr(image, "data", None)
    if not encoded_data:
        raise NanoBananaResponseError("Gemini returned an empty image payload")

    try:
        data = base64.b64decode(encoded_data, validate=True)
    except (binascii.Error, TypeError, ValueError) as exc:
        raise NanoBananaResponseError("Gemini returned invalid base64 image data") from exc
    if not data:
        raise NanoBananaResponseError("Gemini returned an empty decoded image")

    mime_type = getattr(image, "mime_type", None) or "image/png"
    if not isinstance(mime_type, str) or not mime_type.startswith("image/"):
        raise NanoBananaResponseError("Gemini returned an invalid image MIME type")
    return RawGeneratedImage(data=data, mime_type=mime_type)


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, OSError, NanoBananaResponseError)):
        return True

    raw_code = getattr(exc, "code", None)
    if raw_code is None:
        raw_code = getattr(exc, "status_code", None)
    try:
        status_code = int(raw_code)
    except (TypeError, ValueError):
        return False
    return status_code in _RETRYABLE_STATUS_CODES or 500 <= status_code <= 599


__all__ = [
    "NanoBananaClient",
    "NanoBananaError",
    "NanoBananaGenerationError",
    "NanoBananaResponseError",
    "RawGeneratedImage",
]
