from __future__ import annotations

import asyncio
import base64
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from ticketbot.models.invitation import InvitationData
from ticketbot.services import nano_banana
from ticketbot.services.nano_banana import (
    NanoBananaClient,
    NanoBananaGenerationError,
)


def invitation() -> InvitationData:
    return InvitationData.from_raw(
        full_name="Jumayev Shaxzod",
        lead_id="387RVR",
        start_time="18:00",
        event_date="Shanba 15-avgust",
    )


def image_response(
    payload: bytes = b"generated-image",
    mime_type: str = "image/png",
) -> SimpleNamespace:
    return SimpleNamespace(
        output_image=SimpleNamespace(
            data=base64.b64encode(payload).decode("ascii"),
            mime_type=mime_type,
        )
    )


class FakeInteractions:
    def __init__(self, effects: Iterable[Any]) -> None:
        self.effects = list(effects)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        effect = self.effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect


class FakeAsyncClient:
    def __init__(self, interactions: Any) -> None:
        self.interactions = interactions
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeRootClient:
    def __init__(self, interactions: Any) -> None:
        self.aio = FakeAsyncClient(interactions)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def make_client(
    reference_path: Path,
    interactions: Any,
    *,
    max_attempts: int = 2,
    max_concurrent: int = 2,
) -> tuple[NanoBananaClient, FakeRootClient]:
    root = FakeRootClient(interactions)
    service = NanoBananaClient(
        api_key="test-key",
        model="gemini-3-pro-image",
        image_size="2K",
        aspect_ratio="9:16",
        timeout_seconds=10,
        max_attempts=max_attempts,
        max_concurrent=max_concurrent,
        reference_path=reference_path,
        client=root,
    )
    return service, root


@pytest.mark.asyncio
async def test_generate_uses_async_interactions_with_reference_first_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"reference-image")
    interactions = FakeInteractions([image_response(b"result")])
    service, _ = make_client(reference, interactions)
    prompt_builder = Mock(return_value="render this invitation")
    monkeypatch.setattr(nano_banana, "build_invitation_prompt", prompt_builder)
    data = invitation()

    result = await service.generate(data)

    assert result.data == b"result"
    assert result.mime_type == "image/png"
    prompt_builder.assert_called_once_with(data)
    assert len(interactions.calls) == 1
    request = interactions.calls[0]
    assert request["model"] == "gemini-3-pro-image"
    assert request["store"] is False
    assert request["response_format"] == {
        "type": "image",
        "aspect_ratio": "9:16",
        "image_size": "2K",
    }
    assert request["input"][0] == {
        "type": "text",
        "text": "render this invitation",
    }
    assert request["input"][1]["type"] == "image"
    assert request["input"][1]["mime_type"] == "image/png"
    assert base64.b64decode(request["input"][1]["data"]) == b"reference-image"


@pytest.mark.asyncio
async def test_generate_retries_timeout_and_then_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"reference")
    interactions = FakeInteractions([TimeoutError(), image_response(b"retry-result")])
    service, _ = make_client(reference, interactions, max_attempts=2)
    sleep = AsyncMock()
    monkeypatch.setattr(nano_banana.asyncio, "sleep", sleep)

    result = await service.generate(invitation())

    assert result.data == b"retry-result"
    assert len(interactions.calls) == 2
    sleep.assert_awaited_once_with(0.25)


@pytest.mark.asyncio
async def test_generate_retries_empty_output_only_to_attempt_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"reference")
    interactions = FakeInteractions(
        [SimpleNamespace(output_image=None), SimpleNamespace(output_image=None)]
    )
    service, _ = make_client(reference, interactions, max_attempts=2)
    monkeypatch.setattr(nano_banana.asyncio, "sleep", AsyncMock())

    with pytest.raises(NanoBananaGenerationError, match=r"after 2 attempt\(s\)"):
        await service.generate(invitation())

    assert len(interactions.calls) == 2


@pytest.mark.asyncio
async def test_generate_does_not_retry_non_transient_api_error(
    tmp_path: Path,
) -> None:
    class BadRequestError(Exception):
        code = 400

    reference = tmp_path / "reference.png"
    reference.write_bytes(b"reference")
    interactions = FakeInteractions([BadRequestError("invalid prompt")])
    service, _ = make_client(reference, interactions, max_attempts=3)

    with pytest.raises(NanoBananaGenerationError, match=r"after 1 attempt\(s\)"):
        await service.generate(invitation())

    assert len(interactions.calls) == 1


class ConcurrentInteractions:
    def __init__(self, expected_peak: int) -> None:
        self.expected_peak = expected_peak
        self.active = 0
        self.peak = 0
        self.reached_limit = asyncio.Event()
        self.release = asyncio.Event()

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        del kwargs
        self.active += 1
        self.peak = max(self.peak, self.active)
        if self.active == self.expected_peak:
            self.reached_limit.set()
        try:
            await self.release.wait()
            return image_response()
        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_generate_bounds_concurrent_api_calls(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"reference")
    interactions = ConcurrentInteractions(expected_peak=2)
    service, _ = make_client(reference, interactions, max_concurrent=2)

    tasks = [asyncio.create_task(service.generate(invitation())) for _ in range(4)]
    await asyncio.wait_for(interactions.reached_limit.wait(), timeout=1)
    await asyncio.sleep(0)

    assert interactions.peak == 2
    interactions.release.set()
    results = await asyncio.gather(*tasks)
    assert len(results) == 4
    assert interactions.peak == 2


@pytest.mark.asyncio
async def test_aclose_closes_async_and_sync_transports_once(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"reference")
    service, root = make_client(reference, FakeInteractions([]))

    await service.aclose()
    await service.aclose()

    assert root.aio.closed is True
    assert root.closed is True
    with pytest.raises(nano_banana.NanoBananaError, match="closed"):
        await service.generate(invitation())
