from datetime import date, datetime, time
from pathlib import Path

from gold_bot.line import build_payload, send_line_push
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
    assert "ปรับลง 350 บาท" in payload["messages"][1]["text"]


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
