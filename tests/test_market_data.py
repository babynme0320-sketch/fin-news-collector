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
