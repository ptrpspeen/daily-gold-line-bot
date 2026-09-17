"""Build the 1080x1080 clean runtime template from the Canva guide export.

Anantason is intentionally not bundled: all Anantason/static Canva elements
remain baked into the background image. Only the five dynamic fields are
removed and later rendered with the bundled Noto Sans Thai font.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SIZE = (1080, 1080)


def erase_field(
    image: Image.Image,
    box: tuple[int, int, int, int],
    feather: int = 2,
) -> Image.Image:
    """Replace a text rectangle with the Canva card's sampled flat fill."""
    fill = image.copy()
    ImageDraw.Draw(fill).rectangle(box, fill=(247, 252, 254))

    mask = Image.new("L", SIZE, 0)
    ImageDraw.Draw(mask).rectangle(box, fill=255)
    if feather:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
    return Image.composite(fill, image, mask)


def normalize(source: Path, destination: Path) -> Image.Image:
    image = Image.open(source).convert("RGB").resize(SIZE, Image.Resampling.LANCZOS)
    image.save(destination, optimize=True)
    return image


def main() -> None:
    guide = normalize(
        ASSETS / "canva_template_guide_source.png",
        ASSETS / "template_guide.png",
    )
    normalize(
        ASSETS / "canva_up_reference_source.png",
        ASSETS / "reference_up.png",
    )
    normalize(
        ASSETS / "canva_down_reference_source.png",
        ASSETS / "reference_down.png",
    )

    # Rectangles intentionally stay inside the two white Canva cards, so the
    # logo, Anantason heading, labels, divider, rounded corners and shadows are
    # preserved pixel-for-pixel from the user's design.
    clean = guide
    clean = erase_field(clean, (205, 404, 875, 477))
    clean = erase_field(clean, (145, 624, 535, 758))
    clean = erase_field(clean, (140, 832, 535, 966))
    clean = erase_field(clean, (592, 570, 990, 938), feather=4)
    destination = ASSETS / "template_clean.png"
    temporary = destination.with_suffix(".tmp.png")
    clean.save(temporary, format="PNG", compress_level=6)
    temporary.replace(destination)


if __name__ == "__main__":
    main()
