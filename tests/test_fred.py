from __future__ import annotations

import pytest

from collectors.fred import fetch_series

CSV_OK = """observation_date,FEDFUNDS
2026-07-01,3.63
2026-08-01,3.63
"""

CSV_WITH_GAPS = """observation_date,GDPC1
2026-01-01,24000.5
2026-04-01,.
2026-07-01,24269.6
"""


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


def _patch(monkeypatch, text, status=200):
    monkeypatch.setattr("collectors.fred.requests.get", lambda *a, **kw: _Resp(text, status))


def test_parses_records(monkeypatch):
    _patch(monkeypatch, CSV_OK)

    rows = fetch_series("FEDFUNDS")

    assert rows == [
        {"Date": "2026-07-01", "Close": 3.63},
        {"Date": "2026-08-01", "Close": 3.63},
    ]


def test_html_error_page_is_not_parsed_as_data(monkeypatch):
    """없는 시리즈는 CSV 대신 HTML 오류 페이지가 200으로 돌아온다."""
    _patch(monkeypatch, "<html><body>Series not found</body></html>")

    assert fetch_series("NOPE") == []


def test_missing_values_are_skipped(monkeypatch):
    """FRED는 결측을 '.'으로 내려준다."""
    _patch(monkeypatch, CSV_WITH_GAPS)

    rows = fetch_series("GDPC1")

    assert [r["Date"] for r in rows] == ["2026-01-01", "2026-07-01"]


def test_network_error_returns_empty(monkeypatch):
    import requests

    def _boom(*a, **kw):
        raise requests.ConnectionError("down")

    monkeypatch.setattr("collectors.fred.requests.get", _boom)

    assert fetch_series("FEDFUNDS") == []
