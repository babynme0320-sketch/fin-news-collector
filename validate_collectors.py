"""활성화된 모든 소스를 실제로 수집해 0건/오류/급감이 있으면 실패한다.

리포트는 섹션별 오류를 HTML로만 표시하고 워크플로는 성공으로 끝나기 때문에,
한 소스가 조용히 죽어도 알아채기 어렵다. 이 스크립트는 그 경우 exit 1로 CI를 실패시킨다.

0건만 보면 "평소 10건 → 3건" 같은 조용한 열화를 놓친다(사이트 개편으로 셀렉터가
절반만 맞는 경우). 직전 실행의 소스별 건수와 비교해 급감도 함께 잡는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from collectors.base import CollectorResult
from collectors.fomc import FomcCollector
from collectors.hana_brief import HanaBriefCollector
from collectors.market_data import MarketDataCollector
from collectors.web_scraper import WebScraperCollector


STATE_PATH = Path("data") / "validate_state.json"
DROP_THRESHOLD = 0.5   # 직전 대비 절반 이하로 줄면 급감으로 본다
MIN_BASELINE = 5       # 직전이 이보다 적었으면 급감 판정을 하지 않는다(원래 적은 소스)


def _count(result: CollectorResult) -> int:
    return len(result.items) if result.items else len(result.indices)


def _check(result: CollectorResult) -> tuple[bool, str]:
    if result.error:
        return False, f"error={result.error}"
    if not result.items and not result.indices:
        return False, "수집된 항목 0건 (오류 없음)"
    if result.items:
        return True, f"items={len(result.items)}"
    return True, f"indices={len(result.indices)}"


def _check_drop(name: str, count: int, previous: dict[str, int]) -> str:
    """직전 대비 급감했으면 사유 문자열, 아니면 빈 문자열."""
    before = previous.get(name)
    if before is None or before < MIN_BASELINE:
        return ""
    if count <= before * DROP_THRESHOLD:
        return f"직전 {before}건 → 이번 {count}건"
    return ""


def _load_state() -> dict[str, int]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_state(counts: dict[str, int]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    config = yaml.safe_load(Path("sources.yaml").read_text(encoding="utf-8")) or {}
    failures: list[str] = []

    previous = _load_state()
    counts: dict[str, int] = {}
    drops: list[str] = []

    def report(name: str, result: CollectorResult) -> None:
        ok, detail = _check(result)
        count = _count(result)
        counts[name] = count

        note = ""
        if ok:
            drop_reason = _check_drop(name, count, previous)
            if drop_reason:
                ok = False
                detail = drop_reason
                drops.append(name)
        print(f"[{'OK' if ok else 'FAIL'}] {name:24s} {detail}", flush=True)
        if not ok:
            failures.append(name)

    for source_config in config.get("web_sources", []):
        if not source_config.get("enabled", True):
            continue
        name = source_config["name"]
        try:
            result = WebScraperCollector(source_config).collect()
        except Exception as exc:  # 수집기 자체가 터지는 경우도 실패로 취급
            result = CollectorResult(source_name=name, error=f"{type(exc).__name__}: {exc}")
        report(name, result)

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
        report(name, result)

    # 이번 건수를 다음 실행의 기준으로 남긴다. 실패한 실행도 기록해
    # 일시적 장애가 다음 실행의 기준선을 망가뜨리지 않게 한다(급감은 직전 대비만 본다).
    _save_state(counts)

    if failures:
        if drops:
            print(f"\n수집량 급감: {', '.join(drops)}", flush=True)
        print(f"\n수집 실패 소스 {len(failures)}개: {', '.join(failures)}", flush=True)
        return 1
    print("\n모든 소스 정상", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
