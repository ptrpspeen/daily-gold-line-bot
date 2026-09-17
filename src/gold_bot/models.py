from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from typing import Any, Literal


State = Literal["up", "down", "neutral"]


@dataclass(frozen=True)
class GoldPrice:
    date: date
    time: time
    announcement: int
    buy: int
    sell: int
    change: int
    source_url: str
    fetched_at: datetime

    @property
    def state(self) -> State:
        if self.change > 0:
            return "up"
        if self.change < 0:
            return "down"
        return "neutral"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["date"] = self.date.isoformat()
        result["time"] = self.time.strftime("%H:%M")
        result["fetched_at"] = self.fetched_at.isoformat()
        result["state"] = self.state
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "GoldPrice":
        return cls(
            date=date.fromisoformat(value["date"]),
            time=time.fromisoformat(value["time"]),
            announcement=int(value["announcement"]),
            buy=int(value["buy"]),
            sell=int(value["sell"]),
            change=int(value["change"]),
            source_url=str(value["source_url"]),
            fetched_at=datetime.fromisoformat(value["fetched_at"]),
        )
