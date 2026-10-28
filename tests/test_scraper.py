from datetime import date
from pathlib import Path

import pytest

from gold_bot.scraper import (
    AnnouncementNotReady,
    GoldPriceParseError,
    parse_fallback_site,
    parse_official_table,
)


FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_parse_official_down_first_announcement() -> None:
    price = parse_official_table(fixture("official_down.html"), date(2026, 9, 17))
    assert price.announcement == 1
    assert price.buy == 67_850
    assert price.sell == 68_050
    assert price.change == -350
    assert price.state == "down"
    assert price.time.strftime("%H:%M") == "09:02"


def test_parse_official_positive_change_without_plus_sign() -> None:
    price = parse_official_table(fixture("official_up.html"), date(2026, 9, 16))
    assert price.change == 200
    assert price.state == "up"


def test_reject_stale_date() -> None:
    with pytest.raises(AnnouncementNotReady):
        parse_official_table(fixture("official_down.html"), date(2026, 9, 18))


def test_fallback_uses_article_text_for_direction() -> None:
    price = parse_fallback_site(fixture("fallback_down.html"), date(2026, 9, 17))
    assert price.change == -350


def test_fallback_ignores_previous_days_drop_when_opening_price_rises() -> None:
    price = parse_fallback_site(fixture("fallback_up_previous_down.html"), date(2026, 10, 28))
    assert price.change == 900
    assert price.state == "up"


@pytest.mark.parametrize(
    ("opening", "comparison", "amount", "expected_change"),
    [
        ("ปรับตัวลดลง", "ปรับตัวเพิ่มขึ้น", 900, -900),
        ("คงที่ไม่เปลี่ยนแปลง", "ปรับตัวลดลง", 0, 0),
    ],
)
def test_fallback_direction_belongs_to_opening_announcement(
    opening: str, comparison: str, amount: int, expected_change: int
) -> None:
    document = fixture("fallback_up_previous_down.html").decode().replace(
        "ปรับตัวเพิ่มขึ้น 900 บาท เมื่อเทียบกับเมื่อวานที่ปรับตัวลดลง 350 บาท",
        f"{opening} {amount} บาท เมื่อเทียบกับเมื่อวานที่{comparison} 350 บาท",
    ).replace("<td>900</td>", f"<td>{amount}</td>")
    price = parse_fallback_site(document, date(2026, 10, 28))
    assert price.change == expected_change


def test_fallback_rejects_direction_only_found_in_yesterdays_comparison() -> None:
    document = fixture("fallback_up_previous_down.html").decode().replace(
        "ปรับตัวเพิ่มขึ้น 900 บาท ", ""
    )
    with pytest.raises(GoldPriceParseError):
        parse_fallback_site(document, date(2026, 10, 28))


def test_fallback_uses_selected_row_direction_before_unrelated_article() -> None:
    document = fixture("fallback_up_previous_down.html").decode().replace(
        "<td>900</td>", '<td class="goldUp"><span class="img-up"></span>900</td>'
    ).replace("ปรับตัวเพิ่มขึ้น", "ปรับตัวลดลง")
    price = parse_fallback_site(document, date(2026, 10, 28))
    assert price.change == 900


def test_fallback_rejects_stale_article_for_current_table() -> None:
    document = fixture("fallback_up_previous_down.html").decode().replace(
        "<article>", '<article><time datetime="27-10-2026">27 ต.ค. 2569</time>'
    )
    with pytest.raises(GoldPriceParseError):
        parse_fallback_site(document, date(2026, 10, 28))


def test_fallback_rejects_conflicting_direction_markers() -> None:
    document = fixture("fallback_up_previous_down.html").decode().replace(
        "<td>900</td>", '<td class="goldDown"><span class="img-up"></span>900</td>'
    )
    with pytest.raises(GoldPriceParseError):
        parse_fallback_site(document, date(2026, 10, 28))


def test_fallback_zero_change_needs_no_article_direction() -> None:
    document = fixture("fallback_up_previous_down.html").decode().split("<article>")[0]
    document = document.replace("<td>900</td>", "<td>0</td>")
    price = parse_fallback_site(document, date(2026, 10, 28))
    assert price.change == 0
    assert price.state == "neutral"


def test_fallback_direction_markers_belong_to_selected_row() -> None:
    document = fixture("fallback_up_previous_down.html").decode().split("<article>")[0]
    document = document.replace(
        "<td>900</td>", '<td class="goldUp"><span class="img-up"></span>900</td>'
    ).replace(
        "<table>",
        '<table><tr><td>28/10/2569 09:13</td><td>2</td><td>64,650</td>'
        '<td>64,850</td><td>63,353.64</td><td>65,650</td><td>4,050</td>'
        '<td>33.84</td><td class="goldDown"><span class="img-down"></span>50</td></tr>',
    )
    price = parse_fallback_site(document, date(2026, 10, 28))
    assert price.announcement == 1
    assert price.change == 900


@pytest.mark.parametrize(("value", "expected"), [("+900", 900), ("-900", -900)])
def test_fallback_preserves_explicit_table_sign(value: str, expected: int) -> None:
    document = fixture("fallback_up_previous_down.html").decode().split("<article>")[0]
    document = document.replace("<td>900</td>", f"<td>{value}</td>")
    price = parse_fallback_site(document, date(2026, 10, 28))
    assert price.change == expected


def test_fallback_rejects_neutral_article_for_nonzero_change() -> None:
    document = fixture("fallback_up_previous_down.html").decode().replace(
        "ปรับตัวเพิ่มขึ้น", "คงที่ไม่เปลี่ยนแปลง"
    )
    with pytest.raises(GoldPriceParseError):
        parse_fallback_site(document, date(2026, 10, 28))
