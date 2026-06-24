from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import run
from collectors.base import Article, CollectorResult


def test_main_wires_collectors_and_opens_report(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    Path("sources.yaml").write_text(
        """
web_sources:
  - name: "한국경제"
    enabled: true
hana_brief:
  enabled: true
market_data:
  enabled: true
housekeeping:
  retention_days: 10
""".strip(),
        encoding="utf-8",
    )

    calls = []

    class FakeWebCollector:
        def __init__(self, config):
            calls.append(("web-init", config["name"]))

        def collect(self):
            calls.append(("web-collect", "한국경제"))
            return CollectorResult(source_name="한국경제")

    class FakeHanaCollector:
        def __init__(self, config):
            calls.append(("hana-init", config["enabled"]))

        def collect(self):
            calls.append(("hana-collect", True))
            return CollectorResult(source_name="하나증권 모닝브리프")

    class FakeMarketCollector:
        def __init__(self, config):
            calls.append(("market-init", config["enabled"]))

        def collect(self):
            calls.append(("market-collect", True))
            return CollectorResult(source_name="주요 증시", kind="market")

    rendered = {}
    opened = {}

    monkeypatch.setattr(run, "WebScraperCollector", FakeWebCollector)
    monkeypatch.setattr(run, "HanaBriefCollector", FakeHanaCollector)
    monkeypatch.setattr(run, "MarketDataCollector", FakeMarketCollector)
    monkeypatch.setattr(
        run,
        "render_report",
        lambda results, output_path: rendered.update({"count": len(results), "path": output_path}),
    )
    monkeypatch.setattr(run.webbrowser, "open", lambda uri: opened.update({"uri": uri}))

    output = run.main()

    assert output == rendered["path"]
    assert rendered["count"] == 4
    assert opened["uri"].startswith("file://")
    assert ("web-collect", "한국경제") in calls
    assert ("hana-collect", True) in calls
    assert ("market-collect", True) in calls


def test_cleanup_old_outputs_removes_entries_older_than_retention(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    data_dir = tmp_path / "data"
    reports_dir.mkdir()
    data_dir.mkdir()

    keep_date = date.today().strftime("%Y%m%d")
    old_date = (date.today() - timedelta(days=10)).strftime("%Y%m%d")

    (reports_dir / f"report_{keep_date}.html").write_text("keep", encoding="utf-8")
    (reports_dir / f"report_{old_date}.html").write_text("delete", encoding="utf-8")
    (data_dir / keep_date).mkdir()
    (data_dir / old_date).mkdir()

    run._cleanup_report_files(reports_dir, date.today() - timedelta(days=9))
    run._cleanup_dated_directories(data_dir, date.today() - timedelta(days=9))

    assert (reports_dir / f"report_{keep_date}.html").exists()
    assert not (reports_dir / f"report_{old_date}.html").exists()
    assert (data_dir / keep_date).exists()
    assert not (data_dir / old_date).exists()


def test_apply_merge_groups_excludes_broad_hankyung_source():
    broad = CollectorResult(
        source_name="한국경제",
        items=[
            Article(
                title="국방장관 탄핵",
                url="https://example.com/politics/1",
                date="2026-06-12",
            )
        ],
    )
    finance = CollectorResult(
        source_name="한국경제 금융·마켓",
        items=[
            Article(
                title="코스피 급등",
                url="https://example.com/finance/1",
                date="2026-06-12",
            )
        ],
    )
    economy = CollectorResult(
        source_name="한국경제 경제",
        items=[
            Article(
                title="환율 하락",
                url="https://example.com/economy/1",
                date="2026-06-12",
            )
        ],
    )

    merged = run._apply_merge_groups([broad, finance, economy])
    hankyung = next(result for result in merged if result.source_name == "한국경제")

    assert [item.title for item in hankyung.items] == ["코스피 급등", "환율 하락"]
