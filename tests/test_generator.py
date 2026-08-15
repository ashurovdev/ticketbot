from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from ticketbot.models.invitation import InvitationData
from ticketbot.services.generator import InvitationGenerator
from ticketbot.services.image_processor import ImageProcessor
from ticketbot.services.template_renderer import TemplateRenderer

REFERENCE = (
    Path(__file__).parents[1]
    / "src"
    / "ticketbot"
    / "assets"
    / "invitation_reference.png"
)


class RawImage:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.mime_type = "image/jpeg"


class FakeProvider:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.closed = False
        self.calls = 0

    async def generate(self, invitation: InvitationData) -> RawImage:
        self.calls += 1
        assert invitation.lead_id == "387RVR"
        return RawImage(self.data)

    async def aclose(self) -> None:
        self.closed = True


def make_image() -> bytes:
    image = Image.new("RGB", (768, 1376), "navy")
    buffer = BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_generator_normalizes_and_names_output() -> None:
    provider = FakeProvider(make_image())
    generator = InvitationGenerator(
        provider,
        ImageProcessor(705, 1280),
        TemplateRenderer(REFERENCE),
    )
    invitation = InvitationData.from_raw(
        "Jumayev Shaxzod", "387RVR", "18:00", "Shanba 15-avgust"
    )

    result = await generator.generate(invitation)

    assert result.mime_type == "image/png"
    assert result.filename == "invitation_387RVR.png"
    with Image.open(BytesIO(result.data)) as image:
        assert image.size == (705, 1280)

    await generator.aclose()
    assert provider.closed is True


@pytest.mark.asyncio
async def test_template_generation_never_calls_ai_provider() -> None:
    provider = FakeProvider(make_image())
    generator = InvitationGenerator(
        provider,
        ImageProcessor(705, 1280),
        TemplateRenderer(REFERENCE),
    )
    invitation = InvitationData.from_raw(
        "Jumayev Shaxzod", "387RVR", "18:00", "Shanba 15-avgust"
    )

    result = await generator.generate_template(invitation)

    assert provider.calls == 0
    with Image.open(BytesIO(result.data)) as image:
        assert image.size == (705, 1280)
