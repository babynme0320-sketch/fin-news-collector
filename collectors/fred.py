"""FRED(세인트루이스 연은) 공개 CSV에서 시계열을 가져온다.

API 키가 필요 없는 `fredgraph.csv` 엔드포인트를 쓴다. 한국 국고채처럼
국내 소스가 죽었거나(네이버 marketindex 이전) 국내 공공 API가 키를 요구하는
지표를 여기서 대신 가져온다.

주의: 값이 없는 구간은 "."으로 온다. 그리고 없는 시리즈를 요청하면 CSV 대신
HTML 오류 페이지가 200으로 돌아오므로 헤더 검사가 필요하다.
"""
from __future__ import annotations

import csv
import io

import requests

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
TIMEOUT = (5, 25)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}


def fetch_series(series_id: str) -> list[dict]:
    """[(date, value)] 를 오래된 순으로. 실패하면 빈 리스트."""
    try:
        response = requests.get(
            FRED_CSV, params={"id": series_id}, headers=_HEADERS, timeout=TIMEOUT
        )
        response.raise_for_status()
        text = response.text
    except requests.RequestException:
        return []

    # 없는 시리즈는 HTML 오류 페이지가 200으로 온다.
    if not text.lstrip().startswith("observation_date"):
        return []

    records = []
    for row in csv.DictReader(io.StringIO(text)):
        raw_date = (row.get("observation_date") or "").strip()
        raw_value = (row.get(series_id) or "").strip()
        if not raw_date or raw_value in ("", "."):
            continue
        try:
            value = float(raw_value)
        except ValueError:
            continue
        records.append({"Date": raw_date, "Close": value})

    return records
