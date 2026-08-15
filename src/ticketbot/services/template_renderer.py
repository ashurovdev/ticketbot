"""Deterministic, zero-API-cost invitation rendering on the reference template."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from ticketbot.models.invitation import InvitationData

_BASE_WIDTH = 1080
_BASE_HEIGHT = 1960
_BUNDLED_FONT = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "fonts"
    / "Montserrat-Variable.ttf"
)


class TemplateRenderError(ValueError):
    """Raised when the bundled reference cannot be rendered safely."""


class TemplateRenderer:
    """Replace the four dynamic text regions without calling an AI provider."""

    def __init__(self, reference_path: Path) -> None:
        self.reference_path = reference_path

    def render(self, invitation: InvitationData) -> bytes:
        try:
            with Image.open(self.reference_path) as source:
                source.load()
                image = source.convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise TemplateRenderError("Reference template is not a valid image") from exc

        if image.width < 600 or image.height < 1000:
            raise TemplateRenderError("Reference template dimensions are too small")

        draw = ImageDraw.Draw(image)
        scale_x = image.width / _BASE_WIDTH
        scale_y = image.height / _BASE_HEIGHT
        scale = min(scale_x, scale_y)

        name_erase_box = _scaled_box((190, 575, 1010, 810), scale_x, scale_y)
        id_erase_box = _scaled_box((190, 825, 1010, 1000), scale_x, scale_y)
        time_erase_box = _scaled_box((190, 1300, 1010, 1480), scale_x, scale_y)
        date_erase_box = _scaled_box((100, 1620, 950, 1740), scale_x, scale_y)
        name_box = _scaled_box((213, 607, 1010, 810), scale_x, scale_y)
        id_box = _scaled_box((213, 856, 1010, 1000), scale_x, scale_y)
        time_box = _scaled_box((213, 1332, 1010, 1480), scale_x, scale_y)
        date_box = _scaled_box((82, 1628, 934, 1717), scale_x, scale_y)

        _erase_with_background_gradient(image, name_erase_box)
        _erase_with_background_gradient(image, id_erase_box)
        _erase_with_background_gradient(image, time_erase_box)
        draw.rectangle(date_erase_box, fill=(255, 255, 255))

        _draw_name(draw, invitation, name_box, scale)
        _draw_labeled_value(
            draw,
            invitation.lead_id,
            "Test uchun ID",
            id_box,
            scale,
            value_size=67,
            label_size=46,
            gap_size=26,
            label_indent=3,
        )
        _draw_labeled_value(
            draw,
            invitation.start_time,
            "Boshlanish vaqti",
            time_box,
            scale,
            value_size=74,
            label_size=44,
            gap_size=27,
            label_indent=0,
        )
        _draw_centered_date(draw, invitation.event_date, date_box, scale)

        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()


def _scaled_box(
    box: tuple[int, int, int, int],
    scale_x: float,
    scale_y: float,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    return (
        round(left * scale_x),
        round(top * scale_y),
        round(right * scale_x),
        round(bottom * scale_y),
    )


def _erase_with_background_gradient(
    image: Image.Image,
    box: tuple[int, int, int, int],
) -> None:
    """Reconstruct the template's blue horizontal gradient from clean edge pixels."""

    left, top, right, bottom = box
    edge_gap = max(8, round(image.width * 0.01))
    left_x = edge_gap
    right_x = image.width - edge_gap - 1
    height = bottom - top
    width = right - left

    field_width = right_x - left_x + 1
    left_strip = image.crop((left_x, top, left_x + 1, bottom)).resize(
        (field_width, height)
    )
    right_strip = image.crop((right_x, top, right_x + 1, bottom)).resize(
        (field_width, height)
    )
    mask = Image.new("L", (field_width, 1))
    mask.putdata(
        [round(index * 255 / max(field_width - 1, 1)) for index in range(field_width)]
    )
    mask = mask.resize((field_width, height))
    full_gradient = Image.composite(right_strip, left_strip, mask)
    crop_left = left - left_x
    image.paste(
        full_gradient.crop((crop_left, 0, crop_left + width, height)),
        (left, top),
    )


def _font(size: int, *, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if _BUNDLED_FONT.is_file():
        font = ImageFont.truetype(str(_BUNDLED_FONT), size=size)
        font.set_variation_by_axes([800 if bold else 400])
        return font

    windows_name = "GOTHICB.TTF" if bold else "GOTHIC.TTF"
    linux_name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    candidates = (
        Path("C:/Windows/Fonts") / windows_name,
        Path("C:/Windows/Fonts") / ("arialbd.ttf" if bold else "arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu") / linux_name,
        Path("/usr/share/fonts/truetype/liberation2")
        / ("LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"),
    )
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    max_size: int,
    min_size: int,
    max_width: int,
    bold: bool,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for size in range(max_size, min_size - 1, -1):
        font = _font(size, bold=bold)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
    return _font(min_size, bold=bold)


def _text_height(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font, anchor="lt")
    return box[3]


def _draw_name(
    draw: ImageDraw.ImageDraw,
    invitation: InvitationData,
    box: tuple[int, int, int, int],
    scale: float,
) -> None:
    left, top, right, bottom = box
    layout = invitation.name_layout
    lines = layout.lines
    label = "Ism Familiya"
    label_font = _font(max(round(43 * scale), 18), bold=False)
    label_height = _text_height(draw, label, label_font)
    available_height = bottom - top - label_height - round(14 * scale)
    max_line_size = round((68 if len(lines) == 1 else 50 if len(lines) == 2 else 38) * scale)
    min_line_size = max(round(25 * scale), 16)
    max_width = right - left - round(20 * scale)

    name_font = _font(max_line_size, bold=True)
    while max_line_size > min_line_size:
        heights = [_text_height(draw, line, name_font) for line in lines]
        widest = max(draw.textlength(line, font=name_font) for line in lines)
        spacing = round(max_line_size * 0.12)
        if widest <= max_width and sum(heights) + spacing * (len(lines) - 1) <= available_height:
            break
        max_line_size -= 1
        name_font = _font(max_line_size, bold=True)

    y = top
    spacing = round(max_line_size * 0.12)
    for line in lines:
        draw.text((left, y), line, font=name_font, fill="white", anchor="lt")
        y += _text_height(draw, line, name_font) + spacing
    if len(lines) == 1:
        label_y = min(bottom - label_height, top + round(79 * scale))
    else:
        label_y = min(bottom - label_height, y + round(17 * scale))
    draw.text(
        (left + round(1 * scale), label_y),
        label,
        font=label_font,
        fill="white",
        anchor="lt",
    )


def _draw_labeled_value(
    draw: ImageDraw.ImageDraw,
    value: str,
    label: str,
    box: tuple[int, int, int, int],
    scale: float,
    *,
    value_size: int,
    label_size: int,
    gap_size: int,
    label_indent: int,
) -> None:
    left, top, right, bottom = box
    width = right - left - round(20 * scale)
    value_font = _fit_font(
        draw,
        value,
        max_size=round(value_size * scale),
        min_size=max(round(32 * scale), 16),
        max_width=width,
        bold=True,
    )
    label_font = _font(max(round(label_size * scale), 18), bold=False)
    value_height = _text_height(draw, value, value_font)
    label_height = _text_height(draw, label, label_font)
    gap = round(gap_size * scale)
    total_height = value_height + gap + label_height
    y = top + max(0, min(round(4 * scale), bottom - top - total_height))
    draw.text((left, y), value, font=value_font, fill="white", anchor="lt")
    draw.text(
        (left + round(label_indent * scale), y + value_height + gap),
        label,
        font=label_font,
        fill="white",
        anchor="lt",
    )


def _draw_centered_date(
    draw: ImageDraw.ImageDraw,
    value: str,
    box: tuple[int, int, int, int],
    scale: float,
) -> None:
    left, top, right, bottom = box
    font = _fit_font(
        draw,
        value,
        max_size=round(55 * scale),
        min_size=max(round(30 * scale), 16),
        max_width=right - left - round(50 * scale),
        bold=False,
    )
    x = left + (right - left) // 2
    y = top + (bottom - top) // 2
    draw.text((x, y), value, font=font, fill=(12, 12, 12), anchor="mm")


__all__ = ["TemplateRenderError", "TemplateRenderer"]
