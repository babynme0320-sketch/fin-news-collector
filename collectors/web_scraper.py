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
        self._article_meta_cache: dict[str, dict[str, str]] = {}

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
        categories = self._extract_categories_from_element(element, selectors)
        if not self._passes_filters(title=title, url=full_url, categories=categories):
            return None

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
            categories = self._extract_categories_from_record(record, fields)
            if not self._passes_filters(title=title, url=item_url, categories=categories):
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

    def _passes_filters(self, *, title: str, url: str, categories: tuple[str, ...] = ()) -> bool:
        allow_title = self._normalize_filter_values(self.config.get("allow_title_contains_any"))
        deny_title = self._normalize_filter_values(self.config.get("deny_title_contains_any"))
        allow_url = self._normalize_filter_values(self.config.get("allow_url_contains_any"))
        deny_url = self._normalize_filter_values(self.config.get("deny_url_contains_any"))
        allow_categories = self._normalize_filter_values(self.config.get("allowed_categories_any"))
        deny_categories = self._normalize_filter_values(self.config.get("denied_categories_any"))
        allow_sections = self._normalize_filter_values(self.config.get("allowed_article_sections_any"))
        deny_sections = self._normalize_filter_values(self.config.get("denied_article_sections_any"))

        if allow_title and not any(term in title for term in allow_title):
            return False
        if deny_title and any(term in title for term in deny_title):
            return False
        if allow_url and not any(term in url for term in allow_url):
            return False
        if deny_url and any(term in url for term in deny_url):
            return False
        if allow_categories and not self._matches_any(categories, allow_categories):
            return False
        if deny_categories and self._matches_any(categories, deny_categories):
            return False
        if allow_sections or deny_sections:
            article_section = self._resolve_article_section(url)
            if allow_sections and not self._matches_any((article_section,), allow_sections):
                return False
            if deny_sections and self._matches_any((article_section,), deny_sections):
                return False
        return True

    def _normalize_filter_values(self, raw: object) -> tuple[str, ...]:
        if raw is None:
            return ()
        if isinstance(raw, str):
            return (raw,)
        if isinstance(raw, list):
            return tuple(str(value) for value in raw if str(value))
        return ()

    def _extract_categories_from_element(self, element, selectors: dict) -> tuple[str, ...]:
        selector = selectors.get("category")
        return self._extract_text_values(element, selector)

    def _extract_categories_from_record(self, record: dict, fields: dict) -> tuple[str, ...]:
        field_name = fields.get("category")
        if not field_name:
            return ()
        raw = record.get(field_name, ())
        if isinstance(raw, list):
            return tuple(str(value).strip() for value in raw if str(value).strip())
        if raw is None:
            return ()
        text = str(raw).strip()
        return (text,) if text else ()

    def _extract_text_values(self, element, selector: str | None) -> tuple[str, ...]:
        if not selector:
            return ()
        values = []
        for node in element.select(selector):
            text = node.get_text(" ", strip=True)
            if text:
                values.append(text)
        return tuple(values)

    def _matches_any(self, values: tuple[str, ...], patterns: tuple[str, ...]) -> bool:
        if not values:
            return False
        for value in values:
            for pattern in patterns:
                if pattern and pattern in value:
                    return True
        return False

    def _resolve_article_section(self, url: str) -> str:
        metadata = self._fetch_article_metadata(url)
        for key in ("article_section", "section", "breadcrumb"):
            value = metadata.get(key, "").strip()
            if value:
                return value
        return ""

    def _fetch_article_metadata(self, url: str) -> dict[str, str]:
        cached = self._article_meta_cache.get(url)
        if cached is not None:
            return cached

        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()
        except requests.RequestException:
            self._article_meta_cache[url] = {}
            return {}

        if self.config.get("encoding"):
            response.encoding = self.config["encoding"]

        soup = BeautifulSoup(response.text, "html.parser")
        metadata = {
            "description": self._read_meta_content(
                soup,
                ("meta[property='og:description']", "meta[name='description']"),
            ),
            "article_section": self._read_meta_content(
                soup,
                (
                    "meta[property='article:section']",
                    "meta[name='article:section']",
                    "meta[name='section']",
                ),
            ),
            "breadcrumb": self._read_breadcrumb_text(soup),
            "first_paragraph": self._read_first_paragraph_text(soup),
        }

        metadata["section"] = metadata["article_section"] or metadata["breadcrumb"]
        self._article_meta_cache[url] = metadata
        return metadata

    def _read_meta_content(self, soup: BeautifulSoup, selectors: tuple[str, ...]) -> str:
        for selector in selectors:
            meta = soup.select_one(selector)
            content = (meta.get("content", "") if meta else "").strip()
            if content:
                return content
        return ""

    def _read_breadcrumb_text(self, soup: BeautifulSoup) -> str:
        for selector in (
            "nav[aria-label='breadcrumb'] a",
            ".breadcrumb a",
            ".location a",
            ".article-breadcrumb a",
        ):
            nodes = soup.select(selector)
            if nodes:
                text = nodes[-1].get_text(" ", strip=True)
                if text:
                    return text
        return ""

    def _read_first_paragraph_text(self, soup: BeautifulSoup) -> str:
        for paragraph in soup.find_all("p"):
            text = paragraph.get_text(" ", strip=True)
            if len(text) > 30 and "Google 검색에서 한국경제 기사를 더 자주 볼 수 있습니다." not in text:
                return text[:200]
        return ""

    def _fetch_lede(self, url: str) -> str:
        metadata = self._fetch_article_metadata(url)
        if metadata.get("description"):
            return metadata["description"][:200]
        return metadata.get("first_paragraph", "")

    def _download(self, url: str) -> str:
        try:
            return download_pdf(url, self.config["name"])
        except (requests.RequestException, OSError):
            return ""
