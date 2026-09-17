from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

from .models import GoldPrice
from .renderer import thai_datetime_label


LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
BANGKOK = ZoneInfo("Asia/Bangkok")


class LineDeliveryError(RuntimeError):
    pass


def build_caption(price: GoldPrice) -> str:
    status = {"up": "ปรับขึ้น", "down": "ปรับลง", "neutral": "คงที่"}[price.state]
    return (
        "ราคาทองคำแท่ง\n"
        f"{thai_datetime_label(price.date, price.time)}\n"
        f"รับซื้อ {price.buy:,} บาท\n"
        f"ขายออก {price.sell:,} บาท\n"
        f"{status} {abs(price.change):,} บาท"
    )


def build_payload(to: str, price: GoldPrice, image_url: str) -> dict:
    parsed = urlparse(image_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("LINE image URL ต้องเป็น public HTTPS URL")
    return {
        "to": to,
        "messages": [
            {
                "type": "image",
                "originalContentUrl": image_url,
                "previewImageUrl": image_url,
            },
            {"type": "text", "text": build_caption(price)},
        ],
    }


def _receipt_path(receipt_dir: Path, price: GoldPrice) -> Path:
    return receipt_dir / f"{price.date.isoformat()}.json"


def send_line_push(
    price: GoldPrice,
    image_url: str,
    receipt_dir: Path,
    token: str | None = None,
    to: str | None = None,
    force: bool = False,
    session: requests.Session | None = None,
) -> tuple[bool, Path]:
    token = token or os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    to = to or os.environ.get("LINE_TO")
    if not token:
        raise LineDeliveryError("ยังไม่ได้ตั้งค่า LINE_CHANNEL_ACCESS_TOKEN")
    if not to:
        raise LineDeliveryError("ยังไม่ได้ตั้งค่า LINE_TO")

    receipt_dir = Path(receipt_dir)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = _receipt_path(receipt_dir, price)
    if receipt.exists() and not force:
        return False, receipt

    retry_seed = f"gold-card:{to}:{price.date.isoformat()}:{price.buy}:{price.sell}:{price.change}"
    if force:
        retry_seed += f":force:{datetime.now(BANGKOK).isoformat()}"
    retry_key = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            retry_seed,
        )
    )
    response = (session or requests.Session()).post(
        LINE_PUSH_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Line-Retry-Key": retry_key,
        },
        json=build_payload(to, price, image_url),
        timeout=30,
    )
    if response.status_code >= 400:
        detail = response.text[:500]
        raise LineDeliveryError(f"LINE API ตอบ {response.status_code}: {detail}")

    record = {
        "date": price.date.isoformat(),
        "sent_at": datetime.now(BANGKOK).isoformat(),
        "to_suffix": to[-6:] if len(to) >= 6 else "***",
        "image_url": image_url,
        "retry_key": retry_key,
        "status_code": response.status_code,
    }
    temporary = receipt.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(receipt)
    return True, receipt
