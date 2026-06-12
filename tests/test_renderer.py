from __future__ import annotations

from pathlib import Path

from collectors.base import Article, CollectorResult, MarketIndex, Report
from reporter.renderer import render_report


def test_render_report_writes_market_and_sections(tmp_path: Path):
    results = [
        CollectorResult(
            source_name="주요 증시",
            kind="market",
            indices=[
                MarketIndex(
                    symbol="^KS11",
                    name="KOSPI",
                    price=2700.12,
                    change_pct=1.23,
                    date="2026-06-12",
                )
            ],
        ),
        CollectorResult(
            source_name="한국경제",
            items=[
                Article(
                    title="첫 기사",
                    url="https://example.com/news/1",
                    date="2026-06-12",
                    lede="요약 문장",
                )
            ],
        ),
        CollectorResult(
            source_name="연준 보고서",
            items=[
                Report(
                    title="FOMC Minutes",
                    pdf_url="https://example.com/fomc.pdf",
                    date="2026-06-11",
                    local_path="data/20260612/fed/fomc.pdf",
                )
            ],
        ),
    ]

    output = tmp_path / "report.html"
    render_report(results, output)
    html = output.read_text(encoding="utf-8")

    assert "KOSPI" in html
    assert "2700.12" in html
    assert "첫 기사" in html
    assert "요약 문장" in html
    assert "FOMC Minutes" in html
    assert "PDF" in html
