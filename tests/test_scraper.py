from datetime import date
from pathlib import Path

import pytest

from gold_bot.scraper import AnnouncementNotReady, parse_fallback_site, parse_official_table


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
