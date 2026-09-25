from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
import io
from pathlib import Path
import contextlib

import yfinance as yf

from .base import CollectorResult, MarketIndex
from .fred import fetch_series

TIMEOUT_SEC = 10
CACHE_DIR = Path("data") / "history"


FRED_PREFIX = "FRED:"


def _fetch_yfinance(ticker: str, start: str) -> list[dict]:
    """yfinance에서 (날짜, 종가)를 가져온다. 실패하면 빈 리스트."""
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            hist = yf.Ticker(ticker).history(start=start, timeout=TIMEOUT_SEC)
        return [
            {"Date": date_val.strftime("%Y-%m-%d"), "Close": float(row["Close"])}
            for date_val, row in hist.iterrows()
        ]
    except Exception:
        return []


def _write_cache(csv_path: Path, records: list[dict]) -> None:
    try:
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["Date", "Close"])
            writer.writeheader()
            writer.writerows(records)
    except Exception:
        pass


def _read_cache(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        return []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            return [{"Date": row["Date"], "Close": float(row["Close"])} for row in csv.DictReader(f)]
    except Exception:
        return []


def _days_since(date_str: str) -> int:
    """마지막 데이터가 며칠 전 것인지. 파싱 실패 시 0(경고하지 않음)."""
    try:
        last = datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return 0
    return max(0, (date.today() - last).days)


def _stale_threshold(history: list[dict]) -> int:
    """지표 주기에서 경고 기준을 계산한다.

    일간 지표에 3일 기준을 쓰면 맞지만, 월간 지표(국고채·FRED 시리즈)에 그대로 쓰면
    정상적으로 갱신되는 중인데도 매번 경고가 뜬다 — 경고가 늘 켜져 있으면 아무도 안 본다.
    관측 간격의 중앙값 × 3을 기준으로 삼는다(주말·휴일 감안).
    """
    dates = []
    for row in history[-40:]:
        try:
            dates.append(datetime.strptime(row["Date"], "%Y-%m-%d").date())
        except (ValueError, KeyError, TypeError):
            continue
    if len(dates) < 3:
        return 3

    gaps = sorted((b - a).days for a, b in zip(dates, dates[1:]) if (b - a).days > 0)
    if not gaps:
        return 3
    return max(3, gaps[len(gaps) // 2] * 3)


class MarketDataCollector:
    def __init__(self, config: dict):
        self.config = config

    def collect(self) -> CollectorResult:
        result = CollectorResult(source_name="주요 증시", kind="market")

        for symbol_config in self.config.get("symbols", []):
            try:
                history = self._load_and_update_cache(symbol_config)
                # 당일 지수 생성
                market_idx = self._create_market_index(symbol_config, history)
                result.indices.append(market_idx)

                # 30년 월간 종가 다운샘플링 데이터 생성
                monthly_history = self._downsample_monthly(history)
                result.history_data[symbol_config["name"]] = monthly_history
            except Exception as e:
                # 개별 지표 실패 시에도 fallback 제공하여 독립성 유지
                fallback = MarketIndex(
                    symbol=symbol_config["ticker"],
                    name=symbol_config["name"],
                    price=0.0,
                    change_pct=0.0,
                    date=str(date.today()),
                    available=False,
                )
                result.indices.append(fallback)

        if not result.indices:
            result.error = "symbols 설정이 비어 있음"

        return result

    def _load_and_update_cache(self, symbol_config: dict) -> list[dict]:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ticker = symbol_config["ticker"]
        csv_path = CACHE_DIR / f"{ticker}.csv"

        # FRED 시리즈는 전체가 수백 행이라 증분 없이 통째로 받아 덮어쓴다.
        if ticker.startswith(FRED_PREFIX):
            records = fetch_series(ticker[len(FRED_PREFIX):])
            if records:
                _write_cache(csv_path, records)
                return records
            # 실패하면 기존 캐시로 버틴다(값이 없으면 _create_market_index가 처리).
            return _read_cache(csv_path)

        existing_data = []
        last_date_str = None

        if csv_path.exists():
            try:
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        existing_data.append({"Date": row["Date"], "Close": float(row["Close"])})
                if existing_data:
                    last_date_str = existing_data[-1]["Date"]
            except Exception:
                existing_data = []

        new_records = []

        if not existing_data:
            # 최초 30년 전체 수집 (Bootstrap)
            new_records = _fetch_yfinance(ticker, start="1996-01-01")
        else:
            # 증분 수집 (Incremental Update)
            last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
            today = datetime.today()

            if last_date.date() <= today.date():
                # 오늘이 이미 캐시에 있으면 오늘부터 재조회 (intraday 갱신)
                start_date = last_date if last_date.date() == today.date() else last_date + timedelta(days=1)
                new_records = _fetch_yfinance(ticker, start=start_date.strftime("%Y-%m-%d"))

        # new_records가 기존 날짜를 덮어쓰도록 최신 데이터 우선 병합
        date_to_close: dict[str, float] = {r["Date"]: r["Close"] for r in existing_data}
        for r in new_records:
            date_to_close[r["Date"]] = r["Close"]
        unique_combined = [{"Date": d, "Close": c} for d, c in sorted(date_to_close.items())]

        # 신규 데이터가 수집되었을 때만 파일에 쓰기 수행
        if new_records:
            _write_cache(csv_path, unique_combined)

        return unique_combined

    def _create_market_index(self, symbol_config: dict, history: list[dict]) -> MarketIndex:
        ticker = symbol_config["ticker"]
        name = symbol_config["name"]

        if len(history) >= 2:
            last, prev = history[-1], history[-2]
            change_pct = 0.0 if prev["Close"] == 0 else ((last["Close"] - prev["Close"]) / prev["Close"]) * 100
            return MarketIndex(
                symbol=ticker,
                name=name,
                price=round(last["Close"], 2),
                change_pct=round(change_pct, 2),
                date=last["Date"],
                available=True,
                stale_days=_days_since(last["Date"]),
                stale_threshold=_stale_threshold(history),
            )
        elif len(history) == 1:
            last = history[-1]
            return MarketIndex(
                symbol=ticker,
                name=name,
                price=round(last["Close"], 2),
                change_pct=0.0,
                date=last["Date"],
                available=True,
                stale_days=_days_since(last["Date"]),
                stale_threshold=_stale_threshold(history),
            )
        else:
            return MarketIndex(
                symbol=ticker,
                name=name,
                price=0.0,
                change_pct=0.0,
                date=str(date.today()),
                available=False,
            )

    def _downsample_monthly(self, data: list[dict]) -> list[dict]:
        monthly_map = {}
        for r in data:
            ym = r["Date"][:7]  # YYYY-MM
            monthly_map[ym] = r
        sorted_ym = sorted(monthly_map.keys())
        return [{"date": monthly_map[ym]["Date"], "value": round(monthly_map[ym]["Close"], 2)} for ym in sorted_ym]
