from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shutil
import webbrowser

import yaml

from collectors.base import Article, CollectorResult
from collectors.hana_brief import HanaBriefCollector
from collectors.market_data import MarketDataCollector
from collectors.web_scraper import WebScraperCollector
from reporter.renderer import render_report

REPORT_DATE_PATTERN = re.compile(r"report_(\d{8})\.html$")
KST = timezone(timedelta(hours=9))
ACCUMULATE_SOURCES = {"한국경제", "한국경제 금융·마켓", "한국경제 경제"}
MERGE_GROUPS = {"한국경제": ["한국경제", "한국경제 금융·마켓", "한국경제 경제"]}


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


def _load_daily_cache(date_str: str) -> dict[str, list[dict]]:
    cache_path = Path("data") / "daily_cache" / f"{date_str}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    return {}


def _save_daily_cache(date_str: str, cache: dict[str, list[dict]]) -> None:
    cache_path = Path("data") / "daily_cache" / f"{date_str}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _merge_into_result(result: CollectorResult, cached: list[dict]) -> None:
    fresh_urls = {a.url for a in result.items if isinstance(a, Article)}
    existing = [Article(**d) for d in cached if d["url"] not in fresh_urls]
    result.items = list(result.items) + existing


_SOKBO_CACHE = Path("data") / "daily_cache" / "sokbo.json"
_SOKBO_TTL = timedelta(days=2)


def _load_sokbo_cache() -> list[dict]:
    if _SOKBO_CACHE.exists():
        return json.loads(_SOKBO_CACHE.read_text(encoding="utf-8"))
    return []


def _save_sokbo_cache(items: list[dict]) -> None:
    _SOKBO_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _SOKBO_CACHE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_sokbo_result(fresh_articles: list[Article]) -> CollectorResult:
    now = datetime.now(timezone.utc)
    cutoff = now - _SOKBO_TTL

    cached = [
        a for a in _load_sokbo_cache()
        if datetime.fromisoformat(a["collected_at"]).replace(tzinfo=timezone.utc) > cutoff
    ]

    existing_urls = {a["url"] for a in cached}
    for article in fresh_articles:
        if "[속보]" in article.title and article.url not in existing_urls:
            cached.append({
                "title": article.title,
                "url": article.url,
                "date": article.date,
                "lede": article.lede,
                "source": article.source,
                "collected_at": now.replace(tzinfo=None).isoformat(),
            })
            existing_urls.add(article.url)

    _save_sokbo_cache(cached)

    result = CollectorResult(source_name="속보", kind="section")
    result.items = [
        Article(title=a["title"], url=a["url"], date=a["date"], lede=a["lede"], source=a.get("source", ""))
        for a in reversed(cached)
    ]
    return result


def _apply_merge_groups(results: list[CollectorResult]) -> list[CollectorResult]:
    merged_out: list[CollectorResult] = []
    consumed: set[str] = set()
    result_map = {r.source_name: r for r in results}

    for group_name, members in MERGE_GROUPS.items():
        group = [result_map[m] for m in members if m in result_map]
        if not group:
            continue
        merged = CollectorResult(source_name=group_name, kind="section")
        seen_urls: set[str] = set()
        for r in group:
            for item in r.items:
                url = getattr(item, "url", None) or getattr(item, "pdf_url", None) or ""
                if url not in seen_urls:
                    seen_urls.add(url)
                    merged.items.append(item)
        merged.error = next((r.error for r in group if r.error), None)
        merged_out.append(merged)
        consumed.update(members)

    for r in results:
        if r.source_name not in consumed:
            merged_out.append(r)
    return merged_out


def main() -> Path:
    config = yaml.safe_load(Path("sources.yaml").read_text(encoding="utf-8")) or {}
    retention_days = config.get("housekeeping", {}).get("retention_days", 10)
    cleanup_old_outputs(retention_days)

    today_kst = datetime.now(KST).strftime("%Y%m%d")
    daily_cache = _load_daily_cache(today_kst)
    results = []

    for source_config in config.get("web_sources", []):
        if not source_config.get("enabled", True):
            continue
        result = WebScraperCollector(source_config).collect()
        name = result.source_name
        if name in ACCUMULATE_SOURCES:
            cached_articles = daily_cache.get(name, [])
            _merge_into_result(result, cached_articles)
            daily_cache[name] = [
                {"title": a.title, "url": a.url, "date": a.date, "lede": a.lede, "source": a.source}
                for a in result.items if isinstance(a, Article)
            ]
        results.append(result)

    _save_daily_cache(today_kst, daily_cache)
    results = _apply_merge_groups(results)

    # 속보 추출: 병합된 한국경제 결과에서 [속보] 기사 분리
    hankyung = next((r for r in results if r.source_name == "한국경제"), None)
    fresh_articles = [a for a in (hankyung.items if hankyung else []) if isinstance(a, Article)]
    sokbo_result = _build_sokbo_result(fresh_articles)
    if sokbo_result.items:
        results.insert(0, sokbo_result)

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
