from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Literal, Optional, Protocol, runtime_checkable

KST = timezone(timedelta(hours=9))

_RFC_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def normalize_date(raw: str, url: str = "") -> str:
    """날짜 문자열을 YYYY-MM-DD로 정규화. 파싱 실패 시 url에서 추출하거나 KST 오늘 날짜 반환."""
    # YYYY.MM.DD / YYYY-MM-DD / YYYY/MM/DD (시간 포함 무관)
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"

    # YYYYMMDD
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", raw.strip())
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # RFC 2822: "Fri, 12 Jun 2026 07:01:15 GMT"
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", raw)
    if m:
        month_num = _RFC_MONTHS.get(m.group(2).lower()[:3])
        if month_num:
            return f"{m.group(3)}-{month_num:02d}-{int(m.group(1)):02d}"

    # 한국어 상대 날짜: "N일 전" → N일 빼기, "N시간/분 전" → 오늘
    m = re.search(r"(\d+)\s*일\s*전", raw)
    if m:
        target = datetime.now(KST) - timedelta(days=int(m.group(1)))
        return target.strftime("%Y-%m-%d")

    if re.search(r"\d+\s*시간\s*전|\d+\s*분\s*전", raw):
        return _today_kst()

    if "어제" in raw:
        return (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")

    if "오늘" in raw:
        return _today_kst()

    # MM.DD 또는 MM/DD (연도 없음) — 현재 연도 사용
    m = re.search(r"^(\d{1,2})[./](\d{1,2})(?:\s|$)", raw.strip())
    if m:
        year = datetime.now(KST).year
        return f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"

    # URL에서 날짜 추출 (예: /article/2026061237051)
    if url:
        m = re.search(r"/((?:19|20)\d{2})([01]\d)([0123]\d)", url)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    return _today_kst()


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
    kind: Literal["market", "section", "econ"] = "section"
    items: list[Article | Report] = field(default_factory=list)
    indices: list[MarketIndex] = field(default_factory=list)
    history_data: dict[str, list[dict]] = field(default_factory=dict)
    error: Optional[str] = None
    fear_greed: Optional[dict[str, Any]] = None
    econ_indicators: list[dict[str, Any]] = field(default_factory=list)


@runtime_checkable
class Collector(Protocol):
    def collect(self) -> CollectorResult: ...
