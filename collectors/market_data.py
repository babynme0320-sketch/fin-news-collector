from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
import io
import os
from pathlib import Path
import contextlib

import requests
from bs4 import BeautifulSoup
import yfinance as yf

from .base import CollectorResult, MarketIndex

TIMEOUT_SEC = 10
CACHE_DIR = Path("data") / "history"


def _scrape_naver_bond(marketindex_cd: str, pages: int = 20) -> list[dict]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
    }
    records = []
    for page in range(1, pages + 1):
        url = f"https://finance.naver.com/marketindex/interestDailyQuote.naver?marketindexCd={marketindex_cd}&page={page}"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.select_one("table.tbl_exchange.today")
            if not table:
                break
            rows = table.select("tbody tr")
            if not rows:
                break

            page_has_data = False
            for tr in rows:
                tds = tr.select("td")
                if len(tds) >= 2:
                    date_text = tds[0].get_text(strip=True).replace(".", "-")  # YYYY-MM-DD
                    val_text = tds[1].get_text(strip=True)
                    try:
                        val = float(val_text)
                        records.append({"Date": date_text, "Close": val})
                        page_has_data = True
                    except ValueError:
                        continue
            if not page_has_data:
                break
        except Exception:
            break
    records.sort(key=lambda x: x["Date"])
    return records


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
        is_korean_bond = ticker.startswith("KR_BOND")
        naver_cd = "IRR_GOVT03Y" if "3Y" in ticker else "IRR_GOVT10Y"

        if not existing_data:
            # 최초 30년 전체 수집 (Bootstrap)
            if is_korean_bond:
                new_records = _scrape_naver_bond(naver_cd, pages=30)
            else:
                try:
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        yf_ticker = yf.Ticker(ticker)
                        # 30년 역사 데이터 수집
                        hist = yf_ticker.history(start="1996-01-01", timeout=TIMEOUT_SEC)
                    for date_val, row in hist.iterrows():
                        date_str = date_val.strftime("%Y-%m-%d")
                        new_records.append({"Date": date_str, "Close": float(row["Close"])})
                except Exception:
                    pass
        else:
            # 증분 수집 (Incremental Update)
            last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
            today = datetime.today()

            if last_date.date() <= today.date():
                if is_korean_bond:
                    today_records = _scrape_naver_bond(naver_cd, pages=1)
                    for rec in today_records:
                        rec_date = datetime.strptime(rec["Date"], "%Y-%m-%d")
                        if rec_date.date() > last_date.date():
                            new_records.append(rec)
                else:
                    try:
                        # 오늘이 이미 캐시에 있으면 오늘부터 재조회 (intraday 갱신)
                        start_date = last_date if last_date.date() == today.date() else last_date + timedelta(days=1)
                        start_str = start_date.strftime("%Y-%m-%d")
                        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                            yf_ticker = yf.Ticker(ticker)
                            hist = yf_ticker.history(start=start_str, timeout=TIMEOUT_SEC)
                        for date_val, row in hist.iterrows():
                            date_str = date_val.strftime("%Y-%m-%d")
                            new_records.append({"Date": date_str, "Close": float(row["Close"])})
                    except Exception:
                        pass

        # new_records가 기존 날짜를 덮어쓰도록 최신 데이터 우선 병합
        date_to_close: dict[str, float] = {r["Date"]: r["Close"] for r in existing_data}
        for r in new_records:
            date_to_close[r["Date"]] = r["Close"]
        unique_combined = [{"Date": d, "Close": c} for d, c in sorted(date_to_close.items())]

        # 신규 데이터가 수집되었을 때만 파일에 쓰기 수행
        if new_records:
            try:
                with open(csv_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=["Date", "Close"])
                    writer.writeheader()
                    for r in unique_combined:
                        writer.writerow(r)
            except Exception:
                pass

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
