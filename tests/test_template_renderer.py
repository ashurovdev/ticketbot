from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops

from ticketbot.models.invitation import InvitationData
from ticketbot.services.template_renderer import TemplateRenderer

REFERENCE = (
    Path(__file__).parents[1]
    / "src"
    / "ticketbot"
    / "assets"
    / "invitation_reference.png"
)


def test_renderer_changes_dynamic_regions_and_preserves_header() -> None:
    invitation = InvitationData.from_raw(
        "Jumayev Shaxzod", "387RVR", "18:00", "Shanba 15-avgust"
    )
    rendered = TemplateRenderer(REFERENCE).render(invitation)

    with Image.open(REFERENCE) as source, Image.open(BytesIO(rendered)) as result:
        source_rgb = source.convert("RGB")
        result_rgb = result.convert("RGB")
        assert result_rgb.size == source_rgb.size
        assert ImageChops.difference(
            source_rgb.crop((0, 0, source.width, 500)),
            result_rgb.crop((0, 0, result.width, 500)),
        ).getbbox() is None
        assert ImageChops.difference(
            source_rgb.crop((180, 550, 1010, 1730)),
            result_rgb.crop((180, 550, 1010, 1730)),
        ).getbbox() is not None


def test_renderer_handles_multiline_name_without_ai() -> None:
    invitation = InvitationData.from_raw(
        "Abdurahmonov Muhammadali Bahodir o'g'li",
        "LONG-ID-123",
        "09:30",
        "Yakshanba 28-sentabr",
    )

    rendered = TemplateRenderer(REFERENCE).render(invitation)

    assert rendered.startswith(b"\x89PNG\r\n\x1a\n")


def test_renderer_matches_calibrated_reference_typography() -> None:
    invitation = InvitationData.from_raw(
        "Alijoon",
        "645XGN",
        "18:00",
        "Shanba 15-avgust",
    )
    rendered = TemplateRenderer(REFERENCE).render(invitation)

    with Image.open(BytesIO(rendered)).convert("RGB") as image:
        name = _threshold_bbox(image, (190, 570, 900, 680), white=True)
        identifier = _threshold_bbox(image, (190, 820, 900, 930), white=True)
        time = _threshold_bbox(image, (190, 1290, 900, 1410), white=True)
        date = _threshold_bbox(image, (100, 1600, 950, 1760), white=False)

    assert _near(name, (213, 608, 462, 674))
    assert _near(identifier, (216, 861, 493, 909))
    assert _near(time, (214, 1337, 409, 1389))
    assert _near(date, (271, 1650, 743, 1704))


def _threshold_bbox(
    image: Image.Image,
    region: tuple[int, int, int, int],
    *,
    white: bool,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = region
    points = [
        (x, y)
        for y in range(top, bottom)
        for x in range(left, right)
        if (
            min(image.getpixel((x, y))) > 225
            if white
            else max(image.getpixel((x, y))) < 100
        )
    ]
    return (
        min(x for x, _ in points),
        min(y for _, y in points),
        max(x for x, _ in points),
        max(y for _, y in points),
    )


def _near(
    actual: tuple[int, int, int, int],
    expected: tuple[int, int, int, int],
    tolerance: int = 3,
) -> bool:
    return all(
        abs(actual_value - expected_value) <= tolerance
        for actual_value, expected_value in zip(actual, expected, strict=True)
    )
