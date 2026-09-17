from __future__ import annotations

import argparse
import json
import shutil
import sys
import time as sleep_module
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from .line import send_line_push
from .models import GoldPrice
from .renderer import render_card
from .scraper import AnnouncementNotReady, fetch_first_announcement


BANGKOK = ZoneInfo("Asia/Bangkok")


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read_price(path: Path) -> GoldPrice:
    return GoldPrice.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _sample(state: str, sample_date: date | None = None) -> GoldPrice:
    changes = {"up": 200, "down": -350, "neutral": 0}
    values = {
        "up": (67400, 67600),
        "down": (67850, 68050),
        "neutral": (68250, 68450),
    }
    buy, sell = values[state]
    return GoldPrice(
        date=sample_date or datetime.now(BANGKOK).date(),
        time=time(9, 2),
        announcement=1,
        buy=buy,
        sell=sell,
        change=changes[state],
        source_url="sample://local",
        fetched_at=datetime.now(BANGKOK),
    )


def command_fetch_render(args: argparse.Namespace) -> int:
    expected = date.fromisoformat(args.date) if args.date else datetime.now(BANGKOK).date()
    last_error: Exception | None = None
    price: GoldPrice | None = None
    for attempt in range(1, args.retries + 1):
        try:
            price = fetch_first_announcement(expected_date=expected)
            break
        except AnnouncementNotReady as exc:
            last_error = exc
            if attempt == args.retries:
                break
            print(f"ยังไม่พร้อม (ครั้งที่ {attempt}/{args.retries}): {exc}", file=sys.stderr)
            sleep_module.sleep(args.retry_delay)
    if price is None:
        raise SystemExit(f"ไม่พบประกาศครั้งที่ 1 หลังลอง {args.retries} ครั้ง: {last_error}")

    output = Path(args.output)
    render_card(price, output)
    archive = Path(args.archive_dir) / f"{price.date.isoformat()}.png"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.resolve() != output.resolve():
        shutil.copy2(output, archive)
    _write_json(Path(args.data_output), price.to_dict())
    print(json.dumps(price.to_dict(), ensure_ascii=False))
    return 0


def command_render_demo(args: argparse.Namespace) -> int:
    sample_date = date.fromisoformat(args.date) if args.date else None
    price = _sample(args.state, sample_date)
    render_card(price, Path(args.output))
    if args.data_output:
        _write_json(Path(args.data_output), price.to_dict())
    print(json.dumps(price.to_dict(), ensure_ascii=False))
    return 0


def command_send_line(args: argparse.Namespace) -> int:
    price = _read_price(Path(args.data))
    sent, receipt = send_line_push(
        price=price,
        image_url=args.image_url,
        receipt_dir=Path(args.receipt_dir),
        force=args.force,
    )
    print(json.dumps({"sent": sent, "receipt": str(receipt)}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="สร้างและส่งภาพราคาทองคำประกาศครั้งที่ 1")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch-render", help="ดึงข้อมูลจริงแล้วสร้างภาพ")
    fetch.add_argument("--date", help="วันที่แบบ YYYY-MM-DD; ค่าเริ่มต้นคือวันนี้ในไทย")
    fetch.add_argument("--output", default="generated/latest.png")
    fetch.add_argument("--archive-dir", default="generated")
    fetch.add_argument("--data-output", default="generated/latest.json")
    fetch.add_argument("--retries", type=int, default=5)
    fetch.add_argument("--retry-delay", type=int, default=300, help="วินาทีระหว่างการลองใหม่")
    fetch.set_defaults(handler=command_fetch_render)

    demo = subparsers.add_parser("render-demo", help="สร้างภาพตัวอย่างโดยไม่เรียกเว็บไซต์")
    demo.add_argument("--state", choices=("up", "down", "neutral"), required=True)
    demo.add_argument("--date", help="วันที่แบบ YYYY-MM-DD")
    demo.add_argument("--output", required=True)
    demo.add_argument("--data-output")
    demo.set_defaults(handler=command_render_demo)

    line = subparsers.add_parser("send-line", help="ส่งภาพ public URL ผ่าน LINE Messaging API")
    line.add_argument("--data", default="generated/latest.json")
    line.add_argument("--image-url", required=True)
    line.add_argument("--receipt-dir", default="state/sent")
    line.add_argument("--force", action="store_true")
    line.set_defaults(handler=command_send_line)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)
