from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .models import GoldPrice, State


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE = ROOT / "assets" / "template_clean.png"
DEFAULT_SPEC = ROOT / "assets" / "style_spec.json"
THAI_MONTHS = (
    "",
    "มกราคม",
    "กุมภาพันธ์",
    "มีนาคม",
    "เมษายน",
    "พฤษภาคม",
    "มิถุนายน",
    "กรกฎาคม",
    "สิงหาคม",
    "กันยายน",
    "ตุลาคม",
    "พฤศจิกายน",
    "ธันวาคม",
)


def thai_datetime_label(day: date, at: time) -> str:
    return f"{day.day} {THAI_MONTHS[day.month]} {day.year + 543}  {at:%H:%M} น."


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size=size, layout_engine=ImageFont.Layout.RAQM)
    except (AttributeError, OSError):
        return ImageFont.truetype(path, size=size)


def _hex(value: str) -> tuple[int, int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"สีไม่ถูกต้อง: {value!r}")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4)) + (255,)


class CardRenderer:
    def __init__(
        self,
        template_path: Path = DEFAULT_TEMPLATE,
        spec_path: Path = DEFAULT_SPEC,
        supersampling: int = 4,
    ) -> None:
        self.template_path = Path(template_path)
        self.spec_path = Path(spec_path)
        self.spec: dict[str, Any] = json.loads(self.spec_path.read_text(encoding="utf-8"))
        self.scale = supersampling
        self.font_root = self.spec_path.parent

    def _font_for(self, field: dict[str, Any], size: int | None = None) -> ImageFont.FreeTypeFont:
        font_spec = self.spec["fonts"][field["font"]]
        path = (self.font_root / font_spec["file"]).resolve()
        return _font(path, (size or field["render_size_px"]) * self.scale)

    def _fit_font(self, draw: ImageDraw.ImageDraw, text: str, field: dict[str, Any]) -> ImageFont.FreeTypeFont:
        size = int(field["render_size_px"])
        maximum = int(field["max_width"]) * self.scale
        tracking = float(field.get("tracking_px", 0)) * self.scale
        while size >= 24:
            font = self._font_for(field, size)
            if tracking:
                width = sum(draw.textlength(character, font=font) for character in text)
                width += tracking * max(len(text) - 1, 0)
            else:
                bbox = draw.textbbox((0, 0), text, font=font)
                width = bbox[2] - bbox[0]
            if width <= maximum:
                return font
            size -= 1
        raise ValueError(f"ข้อความยาวเกินพื้นที่: {text!r}")

    def _text_position(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        center_x: int,
        origin_y: int,
        tracking: float = 0,
    ) -> tuple[int, int]:
        if tracking:
            width = sum(draw.textlength(character, font=font) for character in text)
            width += tracking * max(len(text) - 1, 0)
            x = round(center_x * self.scale - width / 2)
        else:
            bbox = draw.textbbox((0, 0), text, font=font)
            x = center_x * self.scale - (bbox[0] + bbox[2]) // 2
        return x, origin_y * self.scale

    @staticmethod
    def _draw_text(
        draw: ImageDraw.ImageDraw,
        position: tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
        fill: tuple[int, int, int, int],
        tracking: float = 0,
    ) -> None:
        if not tracking:
            draw.text(position, text, font=font, fill=fill)
            return
        x, y = position
        for character in text:
            draw.text((round(x), y), character, font=font, fill=fill)
            x += draw.textlength(character, font=font) + tracking

    def render(self, price: GoldPrice, output_path: Path) -> Path:
        canvas_size = (self.spec["canvas"]["width"], self.spec["canvas"]["height"])
        base = Image.open(self.template_path).convert("RGBA")
        if base.size != canvas_size:
            raise ValueError(f"template ต้องมีขนาด {canvas_size}, ได้ {base.size}")

        size_hi = (canvas_size[0] * self.scale, canvas_size[1] * self.scale)
        shadow = Image.new("RGBA", size_hi, (0, 0, 0, 0))
        ink = Image.new("RGBA", size_hi, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        ink_draw = ImageDraw.Draw(ink)

        colors = {key: _hex(value) for key, value in self.spec["colors"].items()}
        shadow_spec = self.spec["shadow"]
        shadow_color = colors["shadow"][:3] + (round(255 * shadow_spec["opacity"]),)
        offset = (
            round(shadow_spec["offset_x"] * self.scale),
            round(shadow_spec["offset_y"] * self.scale),
        )

        def draw_text(field_name: str, text: str, color_key: str, origin_y: int | None = None) -> None:
            field = self.spec["fields"][field_name]
            font = self._fit_font(ink_draw, text, field)
            tracking = float(field.get("tracking_px", 0)) * self.scale
            field_shadow_offset = (
                round(field.get("shadow_offset_x", shadow_spec["offset_x"]) * self.scale),
                round(field.get("shadow_offset_y", shadow_spec["offset_y"]) * self.scale),
            )
            position = self._text_position(
                ink_draw,
                text,
                font,
                int(field["center_x"]),
                int(origin_y if origin_y is not None else field["origin_y"]),
                tracking,
            )
            self._draw_text(
                shadow_draw,
                (
                    position[0] + field_shadow_offset[0],
                    position[1] + field_shadow_offset[1],
                ),
                text,
                font,
                shadow_color,
                tracking,
            )
            self._draw_text(ink_draw, position, text, font, colors[color_key], tracking)

        draw_text("datetime", thai_datetime_label(price.date, price.time), "brown")
        draw_text("buy", f"{price.buy:,}", "brown")
        draw_text("sale", f"{price.sell:,}", "brown")

        state: State = price.state
        state_text = {"up": "ปรับขึ้น", "down": "ปรับลง", "neutral": "คงที่"}[state]
        state_color = {"up": "up", "down": "down", "neutral": "neutral"}[state]
        draw_text("status", state_text, state_color)
        delta_field = self.spec["fields"]["delta"]
        draw_text("delta", f"{abs(price.change):,}", state_color, int(delta_field[f"origin_y_{state}"]))

        if state != "neutral":
            arrow = self.spec["fields"]["arrow"]
            cx = int(arrow["center_x"]) * self.scale
            width = int(arrow["width"]) * self.scale
            height = int(arrow["height"]) * self.scale
            top = int(arrow[f"top_{state}"]) * self.scale
            left, right, bottom = cx - width // 2, cx + width // 2, top + height
            if state == "up":
                points = [(cx, top), (left, bottom), (right, bottom)]
            else:
                points = [(left, top), (right, top), (cx, bottom)]
            shadow_points = [(x + offset[0], y + offset[1]) for x, y in points]
            shadow_draw.polygon(shadow_points, fill=shadow_color)
            ink_draw.polygon(points, fill=colors[state_color])

        blur = float(shadow_spec["blur_radius"]) * self.scale
        if blur:
            shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
        dynamic = Image.alpha_composite(shadow, ink).resize(canvas_size, Image.Resampling.LANCZOS)
        result = Image.alpha_composite(base, dynamic).convert("RGB")
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(".tmp.png")
        result.save(temporary, format="PNG", compress_level=7)
        temporary.replace(output_path)
        return output_path


def render_card(
    price: GoldPrice,
    output_path: Path,
    template_path: Path = DEFAULT_TEMPLATE,
    spec_path: Path = DEFAULT_SPEC,
) -> Path:
    return CardRenderer(template_path, spec_path).render(price, output_path)
