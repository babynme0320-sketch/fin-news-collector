"""활성화된 모든 소스를 실제로 수집해 0건/오류가 있으면 실패한다.

리포트는 섹션별 오류를 HTML로만 표시하고 워크플로는 성공으로 끝나기 때문에,
한 소스가 조용히 죽어도 알아채기 어렵다. 이 스크립트는 그 경우 exit 1로 CI를 실패시킨다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from collectors.base import CollectorResult
from collectors.fomc import FomcCollector
from collectors.hana_brief import HanaBriefCollector
from collectors.market_data import MarketDataCollector
from collectors.web_scraper import WebScraperCollector


def _check(result: CollectorResult) -> tuple[bool, str]:
    if result.error:
        return False, f"error={result.error}"
    if not result.items and not result.indices:
        return False, "수집된 항목 0건 (오류 없음)"
    if result.items:
        return True, f"items={len(result.items)}"
    return True, f"indices={len(result.indices)}"


def main() -> int:
    config = yaml.safe_load(Path("sources.yaml").read_text(encoding="utf-8")) or {}
    failures: list[str] = []

    for source_config in config.get("web_sources", []):
        if not source_config.get("enabled", True):
            continue
        name = source_config["name"]
        try:
            result = WebScraperCollector(source_config).collect()
        except Exception as exc:  # 수집기 자체가 터지는 경우도 실패로 취급
            result = CollectorResult(source_name=name, error=f"{type(exc).__name__}: {exc}")
        ok, detail = _check(result)
        print(f"[{'OK' if ok else 'FAIL'}] {name:24s} {detail}", flush=True)
        if not ok:
            failures.append(name)

    extra_collectors = []
    for key, name, factory in (
        ("fomc", "연준 보고서", FomcCollector),
        ("hana_brief", "하나증권 모닝브리프", HanaBriefCollector),
        ("market_data", "시장 지수", MarketDataCollector),
    ):
        section_config = config.get(key, {})
        if section_config.get("enabled", True):
            extra_collectors.append((name, factory(section_config)))

    for name, collector in extra_collectors:
        try:
            result = collector.collect()
        except Exception as exc:
            result = CollectorResult(source_name=name, error=f"{type(exc).__name__}: {exc}")
        ok, detail = _check(result)
        print(f"[{'OK' if ok else 'FAIL'}] {name:24s} {detail}", flush=True)
        if not ok:
            failures.append(name)

    if failures:
        print(f"\n수집 실패 소스 {len(failures)}개: {', '.join(failures)}", flush=True)
        return 1
    print("\n모든 소스 정상", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
