from __future__ import annotations

from datetime import date, datetime, timedelta
import os
from pathlib import Path
import re
import shutil
import webbrowser

import yaml

from collectors.hana_brief import HanaBriefCollector
from collectors.market_data import MarketDataCollector
from collectors.web_scraper import WebScraperCollector
from reporter.renderer import render_report

REPORT_DATE_PATTERN = re.compile(r"report_(\d{8})\.html$")


def cleanup_old_outputs(retention_days: int) -> None:
    if retention_days < 1:
        return

    cutoff_date = date.today() - timedelta(days=retention_days - 1)
    _cleanup_dated_directories(Path("data"), cutoff_date)
    _cleanup_report_files(Path("reports"), cutoff_date)


def _cleanup_dated_directories(root: Path, cutoff_date: date) -> None:
    if not root.exists():
        return

    for entry in root.iterdir():
        if not entry.is_dir():
            continue

        try:
            entry_date = datetime.strptime(entry.name, "%Y%m%d").date()
        except ValueError:
            continue

        if entry_date < cutoff_date:
            shutil.rmtree(entry)


def _cleanup_report_files(root: Path, cutoff_date: date) -> None:
    if not root.exists():
        return

    for entry in root.iterdir():
        if not entry.is_file():
            continue

        match = REPORT_DATE_PATTERN.match(entry.name)
        if not match:
            continue

        entry_date = datetime.strptime(match.group(1), "%Y%m%d").date()
        if entry_date < cutoff_date:
            entry.unlink()


def main() -> Path:
    config = yaml.safe_load(Path("sources.yaml").read_text(encoding="utf-8")) or {}
    retention_days = config.get("housekeeping", {}).get("retention_days", 10)
    cleanup_old_outputs(retention_days)
    results = []

    for source_config in config.get("web_sources", []):
        if source_config.get("enabled", True):
            results.append(WebScraperCollector(source_config).collect())

    hana_config = config.get("hana_brief", {})
    if hana_config.get("enabled", True):
        results.append(HanaBriefCollector(hana_config).collect())

    market_config = config.get("market_data", {})
    if market_config.get("enabled", True):
        results.append(MarketDataCollector(market_config).collect())

    today = date.today().strftime("%Y%m%d")
    output_path = Path("reports") / f"report_{today}.html"
    render_report(results, output_path)
    if not os.getenv("CI"):
        webbrowser.open(output_path.resolve().as_uri())
    return output_path


if __name__ == "__main__":
    main()
