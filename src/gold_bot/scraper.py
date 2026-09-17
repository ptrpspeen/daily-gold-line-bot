from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Callable
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .models import GoldPrice


BANGKOK = ZoneInfo("Asia/Bangkok")
OFFICIAL_URL = "https://classic.goldtraders.or.th/UpdatePriceList.aspx"
FALLBACK_URL = "https://xn--42cah7d0cxcvbbb9x.com/"


class GoldPriceError(RuntimeError):
    """Base error for gold-price acquisition."""


class AnnouncementNotReady(GoldPriceError):
    """Today's announcement number 1 has not appeared yet."""


class GoldPriceParseError(GoldPriceError):
    """A source responded, but its data could not be parsed safely."""


@dataclass(frozen=True)
class Source:
    url: str
    parser: Callable[[bytes | str, date | None, str], GoldPrice]


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _number(value: str) -> int:
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", _clean(value))
    if not match:
        raise GoldPriceParseError(f"ไม่พบตัวเลขในค่า {value!r}")
    return round(float(match.group(0).replace(",", "")))


def _date_and_time(value: str) -> tuple[date, time]:
    match = re.search(
        r"(?P<day>\d{1,2})/(?P<month>\d{1,2})/(?P<year>\d{4})\s+"
        r"(?P<hour>\d{1,2}):(?P<minute>\d{2})",
        _clean(value),
    )
    if not match:
        raise GoldPriceParseError(f"อ่านวันเวลาไม่ได้: {value!r}")
    year = int(match["year"])
    if year >= 2400:
        year -= 543
    return (
        date(year, int(match["month"]), int(match["day"])),
        time(int(match["hour"]), int(match["minute"])),
    )


def _table_rows(document: bytes | str) -> list[list[str]]:
    soup = BeautifulSoup(document, "html.parser")
    rows: list[list[str]] = []
    for row in soup.find_all("tr"):
        cells = [_clean(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    return rows


def _find_first_row(document: bytes | str) -> list[str]:
    candidates: list[list[str]] = []
    for cells in _table_rows(document):
        if len(cells) < 9:
            continue
        if not re.search(r"\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}", cells[0]):
            continue
        try:
            announcement = _number(cells[1])
        except GoldPriceParseError:
            continue
        if announcement == 1:
            candidates.append(cells)
    if not candidates:
        raise AnnouncementNotReady("ยังไม่พบประกาศราคาทองครั้งที่ 1")
    # A malformed page may contain more than one date. The newest date wins.
    return max(candidates, key=lambda row: _date_and_time(row[0]))


def parse_official_table(
    document: bytes | str,
    expected_date: date | None = None,
    source_url: str = OFFICIAL_URL,
) -> GoldPrice:
    cells = _find_first_row(document)
    price_date, price_time = _date_and_time(cells[0])
    if expected_date and price_date != expected_date:
        raise AnnouncementNotReady(
            f"พบประกาศวันที่ {price_date.isoformat()} แต่กำลังรอวันที่ {expected_date.isoformat()}"
        )
    return GoldPrice(
        date=price_date,
        time=price_time,
        announcement=1,
        buy=_number(cells[2]),
        sell=_number(cells[3]),
        change=_number(cells[8]),
        source_url=source_url,
        fetched_at=datetime.now(BANGKOK),
    )


def _fallback_direction(document: bytes | str) -> int:
    soup = BeautifulSoup(document, "html.parser")
    text = _clean(soup.get_text(" ", strip=True))
    marker = re.search(r"ประกาศครั้งที่\s*1", text)
    snippet = text[marker.start() : marker.start() + 500] if marker else text[:1500]
    if re.search(r"(?:ปรับ(?:ตัว)?(?:ลดลง|ลง)|เปิดตลาด(?:ลดลง|ลง)|ร่วง)", snippet):
        return -1
    if re.search(r"(?:ปรับ(?:ตัว)?(?:เพิ่มขึ้น|ขึ้น)|เปิดตลาด(?:เพิ่มขึ้น|ขึ้น))", snippet):
        return 1
    if re.search(r"(?:คงที่|ไม่เปลี่ยนแปลง)", snippet):
        return 0
    raise GoldPriceParseError("แหล่งข้อมูลสำรองไม่ระบุทิศทางขึ้น/ลงอย่างชัดเจน")


def parse_fallback_site(
    document: bytes | str,
    expected_date: date | None = None,
    source_url: str = FALLBACK_URL,
) -> GoldPrice:
    cells = _find_first_row(document)
    price_date, price_time = _date_and_time(cells[0])
    if expected_date and price_date != expected_date:
        raise AnnouncementNotReady(
            f"แหล่งสำรองยังเป็นวันที่ {price_date.isoformat()} ไม่ใช่ {expected_date.isoformat()}"
        )
    change = abs(_number(cells[8])) * _fallback_direction(document)
    return GoldPrice(
        date=price_date,
        time=price_time,
        announcement=1,
        buy=_number(cells[2]),
        sell=_number(cells[3]),
        change=change,
        source_url=source_url,
        fetched_at=datetime.now(BANGKOK),
    )


def fetch_first_announcement(
    expected_date: date | None = None,
    session: requests.Session | None = None,
    timeout: float = 25,
) -> GoldPrice:
    expected_date = expected_date or datetime.now(BANGKOK).date()
    session = session or requests.Session()
    sources = (
        Source(OFFICIAL_URL, parse_official_table),
        Source(FALLBACK_URL, parse_fallback_site),
    )
    errors: list[str] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; daily-gold-card/1.0; +GitHub-Actions)",
        "Accept-Language": "th-TH,th;q=0.9,en;q=0.5",
        "Cache-Control": "no-cache",
    }
    for source in sources:
        try:
            response = session.get(source.url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return source.parser(response.content, expected_date, source.url)
        except (requests.RequestException, GoldPriceError) as exc:
            errors.append(f"{source.url}: {exc}")
    raise AnnouncementNotReady(" | ".join(errors))
