"""FOMC 회의자료 수집.

fomccalendars.htm은 회의별로 성명서·의사록·경제전망(SEP) PDF 링크를 한 행에 묶어 제공한다.
"1회의 = 1문서"가 아니므로 YAML 셀렉터로는 표현할 수 없어 전용 클래스로 처리한다.

날짜 기준
- 성명서/경제전망: 회의 종료일 (파일명에 박힌 날짜를 그대로 사용)
- 의사록: 공표일 (회의 3주 뒤 공표되므로, 공표일로 정렬해야 "최신"이 맞는다)
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base import CollectorResult, Report
from .pdf_downloader import download_pdf

BASE = "https://www.federalreserve.gov"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}
TIMEOUT = (5, 20)

_STATEMENT_PDF = re.compile(r"/monetary\d{8}a\d*\.pdf$", re.IGNORECASE)
_PROJECTIONS_PDF = re.compile(r"/fomcprojtabl\d{8}\.pdf$", re.IGNORECASE)
_MINUTES_PDF = re.compile(r"/fomcminutes\d{8}\.pdf$", re.IGNORECASE)
_RELEASED_ON = re.compile(r"Released\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})")
_FILE_DATE = re.compile(r"(?:monetary|fomcprojtabl|fomcminutes)(\d{8})", re.IGNORECASE)

_KIND_LABELS = {
    "statement": "FOMC 성명서",
    "minutes": "FOMC 의사록",
    "projections": "FOMC 경제전망 SEP",
}


class FomcCollector:
    def __init__(self, config: dict):
        self.config = config

    def collect(self) -> CollectorResult:
        result = CollectorResult(source_name="연준 보고서", kind="section")
        url = self.config.get("url", f"{BASE}/monetarypolicy/fomccalendars.htm")

        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()
        except requests.Timeout:
            result.error = "timeout (connect 5s / read 20s 초과)"
            return result
        except requests.RequestException as exc:
            result.error = str(exc)
            return result

        documents = self._parse_documents(response.text)
        if not documents:
            result.error = "회의자료 링크를 찾지 못함"
            return result

        wanted = set(self.config.get("include", ["statement", "minutes", "projections"]))
        documents = [doc for doc in documents if doc["kind"] in wanted]
        documents.sort(key=lambda doc: (doc["date"], doc["kind"]), reverse=True)
        documents = documents[: self.config.get("max_items", 8)]

        for doc in documents:
            result.items.append(
                Report(
                    title=doc["title"],
                    pdf_url=doc["url"],
                    date=doc["date"],
                    local_path=self._download(doc["url"]),
                    source="연준",
                )
            )

        if not result.items:
            result.error = "조건에 맞는 회의자료가 없음"
        return result

    def _parse_documents(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        documents: list[dict] = []

        # 최신 연도 패널부터 훑는다. 성명서/의사록/전망은 회의당 최대 3건.
        for panel in soup.select("div.panel.panel-default")[:4]:
            for row in panel.select("div.row.fomc-meeting"):
                documents.extend(self._parse_row(row))

        return documents

    def _parse_row(self, row) -> list[dict]:
        # "PDF" 링크가 성명서/의사록에 각각 있어 텍스트로는 구분할 수 없다. href 패턴으로만 판별한다.
        hrefs = [a.get("href", "") for a in row.find_all("a", href=True)]
        statement = next((h for h in hrefs if _STATEMENT_PDF.search(h)), "")
        projections = next((h for h in hrefs if _PROJECTIONS_PDF.search(h)), "")
        minutes = next((h for h in hrefs if _MINUTES_PDF.search(h)), "")
        if not (statement or projections or minutes):
            return []

        meeting_date = self._meeting_date(statement or projections or minutes)
        if not meeting_date:
            return []

        documents = []
        if statement:
            documents.append(self._build("statement", statement, meeting_date, meeting_date))
        if projections:
            documents.append(self._build("projections", projections, meeting_date, meeting_date))
        if minutes:
            # 의사록은 회의 3주 뒤 공표된다. 공표일이 있으면 그 날짜로 정렬한다.
            released = self._minutes_release_date(row) or (meeting_date + timedelta(days=21)).isoformat()
            documents.append(self._build("minutes", minutes, meeting_date, released))
        return documents

    def _build(self, kind: str, href: str, meeting_date: str, published_date: str) -> dict:
        return {
            "kind": kind,
            "url": urljoin(BASE, href),
            "date": published_date,
            "title": f"{_KIND_LABELS[kind]} ({meeting_date} 회의)",
        }

    def _meeting_date(self, href: str) -> str:
        match = _FILE_DATE.search(href)
        if not match:
            return ""
        raw = match.group(1)
        try:
            datetime.strptime(raw, "%Y%m%d")
        except ValueError:
            return ""
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"

    def _minutes_release_date(self, row) -> str:
        block = row.select_one(".fomc-meeting__minutes")
        if not block:
            return ""
        match = _RELEASED_ON.search(block.get_text(" ", strip=True))
        if not match:
            return ""
        # "February 18, 2026" 형식. normalize_date는 이 형식을 못 읽고 오늘 날짜를 돌려주므로 직접 파싱한다.
        try:
            return datetime.strptime(match.group(1), "%B %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            return ""

    def _download(self, url: str) -> str:
        try:
            return download_pdf(url, "연준")
        except (requests.RequestException, OSError):
            return ""
