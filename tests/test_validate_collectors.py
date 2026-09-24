from __future__ import annotations

import json
from pathlib import Path

import validate_collectors as vc
from collectors.base import Article, CollectorResult, MarketIndex


def _result(name: str, count: int) -> CollectorResult:
    return CollectorResult(
        source_name=name,
        items=[Article(title=f"기사 {i}", url=f"https://e.com/{i}", date="2026-09-25") for i in range(count)],
    )


def test_drop_detected_when_count_halves():
    assert vc._check_drop("한국경제 경제", 4, {"한국경제 경제": 10}) != ""
    assert vc._check_drop("한국경제 경제", 10, {"한국경제 경제": 10}) == ""


def test_drop_ignored_for_small_baselines():
    """원래 3건짜리 소스가 1건이 된 건 사이트 개편인지 일상 변동인지 알 수 없다."""
    assert vc._check_drop("연준 보고서", 1, {"연준 보고서": 3}) == ""


def test_drop_ignored_when_source_is_new():
    assert vc._check_drop("새 소스", 1, {}) == ""


def test_drop_boundary_is_inclusive():
    # 정확히 절반이면 급감으로 본다
    assert vc._check_drop("한국경제 경제", 5, {"한국경제 경제": 10}) != ""
    # 절반을 넘으면 통과
    assert vc._check_drop("한국경제 경제", 6, {"한국경제 경제": 10}) == ""


def test_state_round_trips(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(vc, "STATE_PATH", tmp_path / "state.json")

    vc._save_state({"한국경제 경제": 8})

    assert vc._load_state() == {"한국경제 경제": 8}


def test_corrupt_state_is_treated_as_empty(monkeypatch, tmp_path: Path):
    state = tmp_path / "state.json"
    state.write_text("{ 깨진 json", encoding="utf-8")
    monkeypatch.setattr(vc, "STATE_PATH", state)

    assert vc._load_state() == {}


def test_main_fails_on_drop_and_records_new_counts(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sources.yaml").write_text(
        """
web_sources:
  - name: "한국경제 경제"
    enabled: true
""".strip(),
        encoding="utf-8",
    )
    state = tmp_path / "data" / "validate_state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"한국경제 경제": 20}), encoding="utf-8")
    monkeypatch.setattr(vc, "STATE_PATH", state)

    class FakeCollector:
        def __init__(self, config):
            pass

        def collect(self):
            return _result("한국경제 경제", 4)

    monkeypatch.setattr(vc, "WebScraperCollector", FakeCollector)
    monkeypatch.setattr(vc, "FomcCollector", lambda config: type("C", (), {"collect": lambda self: _result("연준 보고서", 8)})())
    monkeypatch.setattr(vc, "HanaBriefCollector", lambda config: type("C", (), {"collect": lambda self: _result("하나", 10)})())
    monkeypatch.setattr(vc, "MarketDataCollector", lambda config: type("C", (), {"collect": lambda self: CollectorResult(source_name="시장", kind="market", indices=[MarketIndex(symbol="^KS11", name="KOSPI", price=1.0, change_pct=0.0, date="2026-09-25")])})())

    assert vc.main() == 1
    # 급감한 실행도 기록한다 — 안 그러면 다음 실행이 이미 줄어든 값을 기준으로 삼는다
    assert json.loads(state.read_text(encoding="utf-8"))["한국경제 경제"] == 4


def test_main_passes_when_counts_are_stable(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sources.yaml").write_text(
        """
web_sources:
  - name: "한국경제 경제"
    enabled: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(vc, "STATE_PATH", tmp_path / "data" / "state.json")
    vc._save_state({"한국경제 경제": 8})

    class FakeCollector:
        def __init__(self, config):
            pass

        def collect(self):
            return _result("한국경제 경제", 8)

    monkeypatch.setattr(vc, "WebScraperCollector", FakeCollector)
    monkeypatch.setattr(vc, "FomcCollector", lambda config: type("C", (), {"collect": lambda self: _result("연준 보고서", 8)})())
    monkeypatch.setattr(vc, "HanaBriefCollector", lambda config: type("C", (), {"collect": lambda self: _result("하나", 10)})())
    monkeypatch.setattr(vc, "MarketDataCollector", lambda config: type("C", (), {"collect": lambda self: CollectorResult(source_name="시장", kind="market", indices=[MarketIndex(symbol="^KS11", name="KOSPI", price=1.0, change_pct=0.0, date="2026-09-25")])})())

    assert vc.main() == 0
