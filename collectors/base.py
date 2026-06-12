from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type
import re
from typing import Literal, Optional, Protocol, runtime_checkable


def normalize_date(raw: str) -> str:
    """날짜 문자열을 YYYY-MM-DD로 정규화. 파싱 실패 시 오늘 날짜 반환."""
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", raw.strip())
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return str(date_type.today())


@dataclass
class Article:
    title: str
    url: str
    date: str
    lede: str = ""
    source: str = ""


@dataclass
class Report:
    title: str
    pdf_url: str
    date: str
    local_path: str = ""
    source: str = ""


@dataclass
class MarketIndex:
    symbol: str
    name: str
    price: float
    change_pct: float
    date: str
    available: bool = True


@dataclass
class CollectorResult:
    source_name: str
    kind: Literal["market", "section"] = "section"
    items: list[Article | Report] = field(default_factory=list)
    indices: list[MarketIndex] = field(default_factory=list)
    history_data: dict[str, list[dict]] = field(default_factory=dict)
    error: Optional[str] = None


@runtime_checkable
class Collector(Protocol):
    def collect(self) -> CollectorResult: ...
