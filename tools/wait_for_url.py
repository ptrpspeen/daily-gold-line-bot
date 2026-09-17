from __future__ import annotations

import argparse
import time

import requests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    last = "no response"
    while time.monotonic() < deadline:
        try:
            response = requests.get(args.url, timeout=15, headers={"Cache-Control": "no-cache"})
            last = f"HTTP {response.status_code}, {response.headers.get('content-type')}"
            if response.ok and response.headers.get("content-type", "").startswith("image/"):
                print(last)
                return 0
        except requests.RequestException as exc:
            last = str(exc)
        time.sleep(5)
    raise SystemExit(f"public image URL ยังไม่พร้อมภายใน {args.timeout} วินาที: {last}")


if __name__ == "__main__":
    raise SystemExit(main())
