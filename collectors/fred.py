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
import subprocess

import requests

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
TIMEOUT = (5, 25)
CURL_TIMEOUT = 30
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}


def _download(series_id: str) -> str:
    """FRED CSV 본문. 실패하면 빈 문자열.

    FRED는 TLS 지문으로 파이썬 HTTP 클라이언트를 막는다 — 같은 러너에서
    requests는 ReadTimeout인데 curl은 200을 0.04초에 받는다(맥·CI 양쪽에서 재현).
    헤더 차이가 아니라 TLS 계층 문제라 requests 설정으로는 풀리지 않으므로,
    먼저 requests로 시도하고 실패하면 curl로 받는다. curl은 macOS·ubuntu 러너에 기본 포함.
    """
    try:
        response = requests.get(
            FRED_CSV, params={"id": series_id}, headers=_HEADERS, timeout=TIMEOUT
        )
        response.raise_for_status()
        return response.text
    except requests.RequestException:
        return _download_via_curl(series_id)


def _download_via_curl(series_id: str) -> str:
    try:
        result = subprocess.run(
            ["curl", "-sS", "--max-time", str(CURL_TIMEOUT), f"{FRED_CSV}?id={series_id}"],
            capture_output=True,
            text=True,
            timeout=CURL_TIMEOUT + 5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def fetch_series(series_id: str) -> list[dict]:
    """[(date, value)] 를 오래된 순으로. 실패하면 빈 리스트."""
    text = _download(series_id)

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
