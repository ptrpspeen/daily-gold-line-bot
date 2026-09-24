from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path

from gold_bot.line import build_caption, build_payload, send_line_push
from gold_bot.models import GoldPrice


PRICE = GoldPrice(
    date=date(2026, 9, 17),
    time=time(9, 2),
    announcement=1,
    buy=67_850,
    sell=68_050,
    change=-350,
    source_url="test://fixture",
    fetched_at=datetime(2026, 9, 17, 9, 10),
)


class Response:
    status_code = 200
    text = "{}"


class Session:
    def __init__(self) -> None:
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return Response()


def test_payload_contains_image_and_caption() -> None:
    payload = build_payload("U123", PRICE, "https://example.com/latest.png")
    assert payload["messages"][0]["type"] == "image"
    assert payload["messages"][1] == {"type": "text", "text": build_caption(PRICE)}


def test_caption_is_ready_to_copy_as_post() -> None:
    price = replace(PRICE, date=date(2026, 9, 23), time=time(9, 4), change=150)
    assert build_caption(price) == (
        "ราคาทอง วันที่ 23 กันยายน 2569 เวลา 09:04 น. ค่ะ\n"
        "⬆️ +150 ฿\n"
        ".\n"
        "สนใจซื้อ-ขาย-ออม แวะมาที่ร้านแสงอรุณได้เลยนะคะ ☺️\n"
        ".\n"
        "พิกัด : ตลาดสดเทศบาลศีขรภูมิ ใกล้ Big-C mini\n"
        "https://maps.app.goo.gl/QCHkEfNAacJDQfYFA?g_st=ic\n"
        ".\n"
        "เปิดทุกวัน จันทร์ - เสาร์\n"
        "เวลา 07:00 - 17:00\n"
        "โทร : 065-5848287\n"
        "ID Line : 044561161\n"
        ".\n"
        "#ห้างทองแสงอรุณ #ทองเยาวราช #ทองคำแท่ง #ทองรูปพรรณ #ราคาทอง "
        "#ขายฝากทอง #จำนำทอง #ร้านทองสุรินทร์ #ร้านทองศีขรภูมิ #รีวิวสุรินทร์"
    )


def test_caption_direction_for_down_and_unchanged_prices() -> None:
    assert build_caption(PRICE).splitlines()[1] == "⬇️ -350 ฿"
    assert build_caption(replace(PRICE, change=0)).splitlines()[1] == "➡️ 0 ฿"


def test_receipt_prevents_duplicate(tmp_path: Path) -> None:
    session = Session()
    first, receipt = send_line_push(
        PRICE,
        "https://example.com/latest.png",
        tmp_path,
        token="token",
        to="U123456789",
        session=session,
    )
    second, same_receipt = send_line_push(
        PRICE,
        "https://example.com/latest.png",
        tmp_path,
        token="token",
        to="U123456789",
        session=session,
    )
    assert first is True
    assert second is False
    assert receipt == same_receipt
    assert len(session.calls) == 1
