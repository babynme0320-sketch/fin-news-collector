from __future__ import annotations

import requests

from collectors.web_scraper import WebScraperCollector


class DummyResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code
        self.encoding = None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


def test_collects_article_items(monkeypatch):
    listing_html = """
    <ul class="news_list">
      <li>
        <a class="tit" href="/article/1">첫 기사</a>
        <span class="time">2026.06.12</span>
      </li>
    </ul>
    """
    article_html = "<html><body><p>충분히 긴 첫 문단 텍스트가 있어서 lede로 사용됩니다.</p></body></html>"

    def fake_get(url, headers, timeout):
        if "article" in url:
            return DummyResponse(article_html)
        return DummyResponse(listing_html)

    monkeypatch.setattr("collectors.web_scraper.requests.request", lambda method, url, headers, timeout, data=None: DummyResponse(listing_html))
    monkeypatch.setattr("collectors.web_scraper.requests.get", fake_get)

    collector = WebScraperCollector(
        {
            "name": "한국경제",
            "url": "https://example.com/news",
            "type": "articles",
            "selectors": {
                "list_container": "ul.news_list",
                "item": "li",
                "title": "a.tit",
                "link": "a.tit",
                "date": "span.time",
                "lede_url": True,
            },
            "max_items": 5,
            "encoding": "utf-8",
        }
    )

    result = collector.collect()

    assert result.error is None
    assert len(result.items) == 1
    item = result.items[0]
    assert item.title == "첫 기사"
    assert item.url == "https://example.com/article/1"
    assert item.date == "2026-06-12"
    assert "첫 문단" in item.lede


def test_collects_pdf_items_without_failing_on_download_error(monkeypatch):
    listing_html = """
    <table class="board_list"><tbody>
      <tr>
        <td class="subject"><a href="/docs/sample.pdf">샘플 리포트</a></td>
        <td class="date">20260612</td>
      </tr>
    </tbody></table>
    """

    monkeypatch.setattr(
        "collectors.web_scraper.requests.request",
        lambda method, url, headers, timeout, data=None: DummyResponse(listing_html),
    )
    monkeypatch.setattr(
        "collectors.web_scraper.download_pdf",
        lambda url, source: (_ for _ in ()).throw(requests.RequestException("download failed")),
    )

    collector = WebScraperCollector(
        {
            "name": "KB금융 리서치",
            "url": "https://example.com/research",
            "type": "pdf_links",
            "selectors": {
                "list_container": "table.board_list tbody",
                "item": "tr",
                "title": "td.subject a",
                "link": "td.subject a",
                "date": "td.date",
            },
        }
    )

    result = collector.collect()

    assert result.error is None
    assert len(result.items) == 1
    item = result.items[0]
    assert item.pdf_url == "https://example.com/docs/sample.pdf"
    assert item.local_path == ""


def test_returns_error_when_selector_matches_nothing(monkeypatch):
    monkeypatch.setattr(
        "collectors.web_scraper.requests.request",
        lambda method, url, headers, timeout, data=None: DummyResponse("<html><body>empty</body></html>"),
    )

    collector = WebScraperCollector(
        {
            "name": "연준 보고서",
            "url": "https://example.com/fed",
            "type": "pdf_links",
            "selectors": {
                "list_container": "div.none",
                "item": "a[href$='.pdf']",
                "title": "a",
                "link": "a",
            },
        }
    )

    result = collector.collect()

    assert "matched nothing" in result.error


def test_collects_json_pdf_items(monkeypatch):
    payload = """
    \n\n{"list":[{"docTitle":"KB 데일리","urlLink":"https://example.com/report.pdf","publicDate":"2026-06-12"}]}
    """

    monkeypatch.setattr(
        "collectors.web_scraper.requests.request",
        lambda method, url, headers, timeout, data=None: DummyResponse(payload),
    )
    monkeypatch.setattr(
        "collectors.web_scraper.download_pdf",
        lambda url, source: "data/20260612/KB/report.pdf",
    )

    collector = WebScraperCollector(
        {
            "name": "KB금융 리서치",
            "url": "https://example.com/api",
            "type": "pdf_links",
            "response_format": "json",
            "request_method": "POST",
            "request_data": {"tab": "1"},
            "items_key": "list",
            "fields": {
                "title": "docTitle",
                "link": "urlLink",
                "date": "publicDate",
            },
        }
    )

    result = collector.collect()

    assert result.error is None
    assert len(result.items) == 1
    assert result.items[0].title == "KB 데일리"
    assert result.items[0].local_path.endswith("report.pdf")
