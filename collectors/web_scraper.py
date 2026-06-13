from __future__ import annotations

import json
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base import Article, CollectorResult, Report, normalize_date
from .pdf_downloader import download_pdf

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}
TIMEOUT = (5, 15)


class WebScraperCollector:
    """Collect articles or PDF links from a YAML-defined source config."""

    def __init__(self, config: dict):
        self.config = config

    def collect(self) -> CollectorResult:
        result = CollectorResult(source_name=self.config["name"], kind="section")

        try:
            response = self._request()
            response.raise_for_status()
        except requests.Timeout:
            result.error = "timeout (connect 5s / read 15s 초과)"
            return result
        except requests.RequestException as exc:
            result.error = str(exc)
            return result

        if self.config.get("response_format") == "json":
            return self._collect_json(response, result)

        if self.config.get("encoding"):
            response.encoding = self.config["encoding"]

        parser = self.config.get("parser", "html.parser")
        soup = BeautifulSoup(response.text, parser)
        selectors = self.config["selectors"]
        container_selector = selectors.get("list_container")
        container = soup.select_one(container_selector) if container_selector else soup
        container = container or soup
        raw_items = container.select(selectors["item"])[: self.config.get("max_items", 10)]

        if not raw_items:
            result.error = f"selector '{selectors['item']}' matched nothing"
            return result

        for element in raw_items:
            parsed = self._parse_element(element, selectors)
            if parsed is None:
                continue

            title, url, item_date = parsed
            if self.config["type"] == "articles":
                lede = self._extract_lede_from_element(element, selectors)
                if not lede and selectors.get("lede_url"):
                    lede = self._fetch_lede(url)
                result.items.append(
                    Article(
                        title=title,
                        url=url,
                        date=item_date,
                        lede=lede,
                        source=self.config["name"],
                    )
                )
            else:
                local_path = self._download(url)
                result.items.append(
                    Report(
                        title=title,
                        pdf_url=url,
                        date=item_date,
                        local_path=local_path,
                        source=self.config["name"],
                    )
                )

        if not result.items and result.error is None:
            result.error = "유효한 항목을 찾지 못함"

        return result

    def _parse_element(self, element, selectors: dict) -> tuple[str, str, str] | None:
        title_element = element.select_one(selectors["title"])
        link_element = element.select_one(selectors["link"])
        date_element = element.select_one(selectors["date"]) if selectors.get("date") else None
        if title_element is None or link_element is None:
            return None

        title = title_element.get_text(" ", strip=True)
        href = link_element.get("href") or link_element.get_text(" ", strip=True)
        if not title or not href:
            return None

        filter_text = self.config.get("filter_title_contains")
        if filter_text and filter_text not in title:
            return None

        full_url = urljoin(self.config["url"], href)
        raw_date = date_element.get_text(" ", strip=True) if date_element else ""
        normalized_date = normalize_date(raw_date, url=full_url)
        return title, full_url, normalized_date

    def _extract_lede_from_element(self, element, selectors: dict) -> str:
        lede_selector = selectors.get("lede")
        if not lede_selector:
            return ""

        lede_element = element.select_one(lede_selector)
        if lede_element is None:
            return ""
        return lede_element.get_text(" ", strip=True)[:200]

    def _request(self) -> requests.Response:
        method = self.config.get("request_method", "GET").upper()
        request_data = self.config.get("request_data")
        return requests.request(
            method,
            self.config["url"],
            headers=HEADERS,
            timeout=TIMEOUT,
            data=request_data,
        )

    def _collect_json(self, response: requests.Response, result: CollectorResult) -> CollectorResult:
        text = response.text
        json_start = text.find("{")
        if json_start > 0:
            text = text[json_start:]

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            result.error = f"json parse failed: {exc}"
            return result

        records = payload.get(self.config.get("items_key", "list"), [])
        fields = self.config["fields"]
        for record in records[: self.config.get("max_items", 10)]:
            title = str(record.get(fields["title"], "")).strip()
            url = str(record.get(fields["link"], "")).strip()
            item_url = urljoin(self.config["url"], url)
            item_date = normalize_date(str(record.get(fields["date"], "")), url=item_url)
            if not title or not url:
                continue

            if self.config["type"] == "articles":
                lede = ""
                lede_key = fields.get("lede")
                if lede_key:
                    lede = str(record.get(lede_key, "")).strip()[:200]
                elif self.config.get("selectors", {}).get("lede_url"):
                    lede = self._fetch_lede(url)

                result.items.append(
                    Article(
                        title=title,
                        url=urljoin(self.config["url"], url),
                        date=item_date,
                        lede=lede,
                        source=self.config["name"],
                    )
                )
            else:
                result.items.append(
                    Report(
                        title=title,
                        pdf_url=urljoin(self.config["url"], url),
                        date=item_date,
                        local_path=self._download(urljoin(self.config["url"], url)),
                        source=self.config["name"],
                    )
                )

        if not result.items:
            result.error = "유효한 항목을 찾지 못함"

        return result

    def _fetch_lede(self, url: str) -> str:
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()
        except requests.RequestException:
            return ""

        if self.config.get("encoding"):
            response.encoding = self.config["encoding"]

        soup = BeautifulSoup(response.text, "html.parser")
        for selector in ("meta[property='og:description']", "meta[name='description']"):
            meta = soup.select_one(selector)
            description = (meta.get("content", "") if meta else "").strip()
            if description:
                return description[:200]

        for paragraph in soup.find_all("p"):
            text = paragraph.get_text(" ", strip=True)
            if len(text) > 30 and "Google 검색에서 한국경제 기사를 더 자주 볼 수 있습니다." not in text:
                return text[:200]
        return ""

    def _download(self, url: str) -> str:
        try:
            return download_pdf(url, self.config["name"])
        except (requests.RequestException, OSError):
            return ""
