from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from collectors.base import CollectorResult, Report

SECTION_ORDER = ["속보", "한국경제", "매일경제", "사설", "미국 뉴스", "연준 보고서", "KB금융 리서치", "하나증권 모닝브리프"]


def _result_to_section(result: CollectorResult) -> dict:
    items = []
    for item in result.items:
        is_pdf = isinstance(item, Report)
        items.append(
            {
                "title": item.title,
                "url": item.pdf_url if is_pdf else item.url,
                "date": item.date,
                "lede": getattr(item, "lede", ""),
                "local_path": getattr(item, "local_path", ""),
                "is_pdf": is_pdf,
            }
        )

    return {
        "name": result.source_name,
        "error": result.error,
        "entries": items,
    }


def render_report(results: list[CollectorResult], output_path: Path) -> None:
    market_result = next((result for result in results if result.kind == "market"), None)
    econ_result = next((result for result in results if result.kind == "econ"), None)
    section_results = [result for result in results if result.kind == "section"]
    ordered_sections = sorted(
        section_results,
        key=lambda result: (
            SECTION_ORDER.index(result.source_name)
            if result.source_name in SECTION_ORDER
            else len(SECTION_ORDER)
        ),
    )

    environment = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=select_autoescape(enabled_extensions=("html", "j2")),
    )
    template = environment.get_template("daily.html.j2")
    html = template.render(
        date=date.today().strftime("%Y년 %m월 %d일"),
        generated_at=date.today().isoformat(),
        indices=market_result.indices if market_result else [],
        market_error=market_result.error if market_result else None,
        history_data=market_result.history_data if market_result else {},
        fear_greed=econ_result.fear_greed if econ_result else None,
        econ_indicators=econ_result.econ_indicators if econ_result else [],
        sections=[_result_to_section(result) for result in ordered_sections],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
