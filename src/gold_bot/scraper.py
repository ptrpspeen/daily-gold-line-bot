from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Callable
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, Tag

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


def _table_rows(document: bytes | str) -> list[tuple[list[str], Tag]]:
    soup = BeautifulSoup(document, "html.parser")
    rows: list[tuple[list[str], Tag]] = []
    for row in soup.find_all("tr"):
        cells = [_clean(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
        if cells:
            rows.append((cells, row))
    return rows


def _find_first_row(document: bytes | str) -> tuple[list[str], Tag]:
    candidates: list[tuple[list[str], Tag]] = []
    for cells, row in _table_rows(document):
        if len(cells) < 9:
            continue
        if not re.search(r"\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}", cells[0]):
            continue
        try:
            announcement = _number(cells[1])
        except GoldPriceParseError:
            continue
        if announcement == 1:
            candidates.append((cells, row))
    if not candidates:
        raise AnnouncementNotReady("ยังไม่พบประกาศราคาทองครั้งที่ 1")
    # A malformed page may contain more than one date. The newest date wins.
    return max(candidates, key=lambda candidate: _date_and_time(candidate[0][0]))


def parse_official_table(
    document: bytes | str,
    expected_date: date | None = None,
    source_url: str = OFFICIAL_URL,
) -> GoldPrice:
    cells, _ = _find_first_row(document)
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


def _fallback_row_direction(row: Tag, change: str) -> int | None:
    cell = row.find_all(["th", "td"])[8]
    classes = set(cell.get("class", []))
    for child in cell.find_all(class_=True):
        classes.update(child.get("class", []))
    directions: set[int] = set()
    if classes.intersection({"goldUp", "img-up"}):
        directions.add(1)
    if classes.intersection({"goldDown", "img-down"}):
        directions.add(-1)
    if re.match(r"^[+-]", change):
        directions.add(-1 if change.startswith("-") else 1)
    if len(directions) > 1:
        raise GoldPriceParseError("แหล่งข้อมูลสำรองระบุทิศทางในแถวราคาขัดแย้งกัน")
    return next(iter(directions), None)


def _fallback_direction(document: bytes | str, price_date: date) -> int:
    soup = BeautifulSoup(document, "html.parser")
    for article in soup.find_all("article") or [soup]:
        published = article.find("time", datetime=True)
        if published:
            value = str(published["datetime"])
            article_date = None
            for format in ("%d-%m-%Y", "%Y-%m-%d"):
                try:
                    article_date = datetime.strptime(value[:10], format).date()
                    break
                except ValueError:
                    continue
            if article_date != price_date:
                continue
        text = _clean(article.get_text(" ", strip=True))
        marker = re.search(r"ประกาศครั้งที่\s*1(?!\d)", text)
        if not marker:
            continue
        # Opening-price reports also describe yesterday's movement. Only the
        # announcement before that comparison determines this row's direction.
        snippet = text[marker.end() : marker.end() + 500]
        snippet = re.split(r"เมื่อเทียบ|เมื่อวาน", snippet, maxsplit=1)[0]
        direction = re.search(
            r"(?P<down>ปรับ(?:ตัว)?(?:ลดลง|ลง)|เปิดตลาด(?:ลดลง|ลง)|ร่วง)"
            r"|(?P<up>ปรับ(?:ตัว)?(?:เพิ่มขึ้น|ขึ้น)|เปิดตลาด(?:เพิ่มขึ้น|ขึ้น))"
            r"|(?P<neutral>คงที่|ไม่เปลี่ยนแปลง)",
            snippet,
        )
        if direction:
            return {"down": -1, "up": 1, "neutral": 0}[direction.lastgroup]
        break
    raise GoldPriceParseError("แหล่งข้อมูลสำรองไม่ระบุทิศทางขึ้น/ลงอย่างชัดเจน")


def parse_fallback_site(
    document: bytes | str,
    expected_date: date | None = None,
    source_url: str = FALLBACK_URL,
) -> GoldPrice:
    cells, row = _find_first_row(document)
    price_date, price_time = _date_and_time(cells[0])
    if expected_date and price_date != expected_date:
        raise AnnouncementNotReady(
            f"แหล่งสำรองยังเป็นวันที่ {price_date.isoformat()} ไม่ใช่ {expected_date.isoformat()}"
        )
    amount = abs(_number(cells[8]))
    direction = _fallback_row_direction(row, cells[8])
    if amount and direction is None:
        direction = _fallback_direction(document, price_date)
    if amount and direction == 0:
        raise GoldPriceParseError("แหล่งข้อมูลสำรองระบุว่าราคาคงที่แต่ส่วนต่างไม่เป็นศูนย์")
    change = amount * (direction or 0)
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
