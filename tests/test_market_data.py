from __future__ import annotations

import shutil
from pathlib import Path
import pandas as pd
import pytest
from collectors.market_data import MarketDataCollector
import collectors.market_data


class FakeHistory:
    def __init__(self, records):
        # records: list of dict, e.g., [{"Date": "2026-06-11", "Close": 100.0}]
        self._df = pd.DataFrame(records)
        if not self._df.empty:
            self._df["Date"] = pd.to_datetime(self._df["Date"])
            self._df.set_index("Date", inplace=True)

    def iterrows(self):
        return self._df.iterrows()

    def __len__(self):
        return len(self._df)


class FakeTicker:
    def __init__(self, records):
        self._records = records

    def history(self, start=None, timeout=None):
        return FakeHistory(self._records)


def test_market_data_collects_change_percent(monkeypatch, tmp_path):
    # 캐시 저장 경로를 pytest 임시 폴더로 격리
    monkeypatch.setattr(collectors.market_data, "CACHE_DIR", tmp_path)

    fake_records = [
        {"Date": "2026-06-11", "Close": 100.0},
        {"Date": "2026-06-12", "Close": 105.0},
    ]
    monkeypatch.setattr(
        "collectors.market_data.yf.Ticker",
        lambda symbol: FakeTicker(fake_records),
    )

    collector = MarketDataCollector({"symbols": [{"ticker": "^KS11", "name": "KOSPI"}]})
    result = collector.collect()

    assert result.error is None
    assert len(result.indices) == 1
    assert result.indices[0].price == 105.0
    assert result.indices[0].change_pct == 5.0
    assert result.indices[0].available is True
    
    # 캐시 파일이 정상 생성되었는지 검증
    cache_file = tmp_path / "^KS11.csv"
    assert cache_file.exists()


def test_market_data_returns_unavailable_on_symbol_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(collectors.market_data, "CACHE_DIR", tmp_path)

    def raise_error(symbol):
        raise RuntimeError("boom")

    monkeypatch.setattr("collectors.market_data.yf.Ticker", raise_error)

    collector = MarketDataCollector({"symbols": [{"ticker": "^IXIC", "name": "NASDAQ"}]})
    result = collector.collect()

    assert result.error is None
    assert result.indices[0].available is False


def test_stale_days_counts_from_last_data_point():
    from datetime import date, timedelta
    from collectors.market_data import _days_since

    assert _days_since(date.today().strftime("%Y-%m-%d")) == 0
    assert _days_since((date.today() - timedelta(days=8)).strftime("%Y-%m-%d")) == 8


def test_days_since_ignores_unparsable_date():
    """날짜를 못 읽으면 경고하지 않는다 — 잘못된 경고는 경고 자체를 무시하게 만든다."""
    from collectors.market_data import _days_since

    assert _days_since("") == 0
    assert _days_since("2026/09/25") == 0
    assert _days_since(None) == 0


def test_market_index_flags_stale_series():
    from datetime import date, timedelta
    from collectors.market_data import MarketDataCollector

    collector = MarketDataCollector({})
    old = (date.today() - timedelta(days=8)).strftime("%Y-%m-%d")
    fresh = date.today().strftime("%Y-%m-%d")

    stale = collector._create_market_index(
        {"ticker": "KR_BOND_3Y", "name": "국고채 3년"},
        [{"Date": old, "Close": 4.0}, {"Date": old, "Close": 4.06}],
    )
    current = collector._create_market_index(
        {"ticker": "^KS11", "name": "KOSPI"},
        [{"Date": fresh, "Close": 100.0}, {"Date": fresh, "Close": 101.0}],
    )

    assert stale.stale_days == 8
    assert current.stale_days == 0
