from datetime import date, datetime, time
from pathlib import Path

from PIL import Image

from gold_bot.models import GoldPrice
from gold_bot.renderer import render_card, thai_datetime_label


def price(change: int) -> GoldPrice:
    return GoldPrice(
        date=date(2026, 9, 17),
        time=time(9, 2),
        announcement=1,
        buy=67_850,
        sell=68_050,
        change=change,
        source_url="test://fixture",
        fetched_at=datetime(2026, 9, 17, 9, 10),
    )


def test_thai_datetime() -> None:
    assert thai_datetime_label(date(2026, 9, 17), time(9, 2)) == "17 กันยายน 2569  09:02 น."


def test_render_all_states(tmp_path: Path) -> None:
    for change, expected_color in (
        (200, (65, 144, 40)),
        (-350, (234, 51, 35)),
        (0, (77, 57, 13)),
    ):
        output = tmp_path / f"{change}.png"
        render_card(price(change), output)
        with Image.open(output) as image:
            assert image.size == (1080, 1080)
            colors = image.convert("RGB").getcolors(maxcolors=2_000_000)
            assert colors is not None
            palette = {color for _, color in colors}
            assert expected_color in palette
