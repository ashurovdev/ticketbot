from io import BytesIO

import pytest
from PIL import Image

from ticketbot.services.image_processor import ImageProcessingError, ImageProcessor


def image_bytes(size: tuple[int, int] = (768, 1376), mode: str = "RGB") -> bytes:
    image = Image.new(mode, size, (20, 38, 140) if mode == "RGB" else (20, 38, 140, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_normalize_png_has_expected_dimensions() -> None:
    result = ImageProcessor(705, 1280).normalize_png(image_bytes())

    with Image.open(BytesIO(result)) as image:
        assert image.size == (705, 1280)
        assert image.mode == "RGB"
        assert image.format == "PNG"


def test_normalize_png_flattens_alpha() -> None:
    result = ImageProcessor().normalize_png(image_bytes(mode="RGBA"))

    with Image.open(BytesIO(result)) as image:
        assert image.mode == "RGB"


@pytest.mark.parametrize("payload", [b"", b"not an image"])
def test_normalize_png_rejects_invalid_input(payload: bytes) -> None:
    with pytest.raises(ImageProcessingError):
        ImageProcessor().normalize_png(payload)
