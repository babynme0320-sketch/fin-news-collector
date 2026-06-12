from __future__ import annotations

import contextlib
import io
from datetime import date

import requests
import yfinance as yf

from .base import CollectorResult

TIMEOUT_SEC = 10
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def _fetch_bls_series(series_id: str, years_back: int = 2) -> list[dict]:
    """BLS Public Data API v1 (API 키 불필요)."""
    today = date.today()
    url = (
        f"https://api.bls.gov/publicAPI/v1/timeseries/data/{series_id}"
        f"?startyear={today.year - years_back}&endyear={today.year}"
    )
    try:
        r = requests.get(url, headers=_HEADERS, timeout=TIMEOUT_SEC)
        if r.status_code != 200:
            return []
        series = r.json().get("Results", {}).get("series", [])
        if not series:
            return []
        monthly = [d for d in series[0].get("data", []) if d.get("period", "").startswith("M") and d["period"] != "M13"]
        return sorted(monthly, key=lambda x: (x["year"], x["period"]))
    except Exception:
        return []


def _fetch_irx() -> tuple[str, float] | None:
    """^IRX (13주 T-Bill)를 Fed Funds Rate 프록시로 사용."""
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            hist = yf.Ticker("^IRX").history(period="5d")
        if hist.empty:
            return None
        return str(hist.index[-1].date()), round(float(hist["Close"].iloc[-1]), 2)
    except Exception:
        return None


def _fetch_fear_greed() -> dict | None:
    """CNN Fear & Greed Index API (인증 불필요)."""
    try:
        r = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers=_HEADERS,
            timeout=TIMEOUT_SEC,
        )
        if r.status_code != 200:
            return None
        fg = r.json().get("fear_and_greed", {})
        return {
            "score": round(float(fg.get("score", 0))),
            "rating": fg.get("rating", "").replace("_", " ").title(),
            "prev_close": round(float(fg.get("previous_close", 0))),
        }
    except Exception:
        return None


class EconIndicatorCollector:
    def collect(self) -> CollectorResult:
        result = CollectorResult(source_name="경제 지표", kind="econ")
        result.fear_greed = _fetch_fear_greed()

        # 기준금리 프록시: ^IRX (13주 T-Bill)
        irx = _fetch_irx()
        result.econ_indicators.append({
            "name": "기준금리 (T-Bill)",
            "value": irx[1] if irx else None,
            "prev": None,
            "unit": "%",
            "date": irx[0] if irx else None,
        })

        # CPI YoY: BLS CUUR0000SA0
        cpi = _fetch_bls_series("CUUR0000SA0", 2)
        if len(cpi) >= 13:
            cur_v, yago_v = float(cpi[-1]["value"]), float(cpi[-13]["value"])
            cpi_yoy = round((cur_v - yago_v) / yago_v * 100, 1)
            prev_yoy = (
                round((float(cpi[-2]["value"]) - float(cpi[-14]["value"])) / float(cpi[-14]["value"]) * 100, 1)
                if len(cpi) >= 14 else None
            )
            result.econ_indicators.append({
                "name": "CPI (YoY)",
                "value": cpi_yoy,
                "prev": prev_yoy,
                "unit": "%",
                "date": f"{cpi[-1]['year']}-{cpi[-1]['period'][1:]}",
            })
        else:
            result.econ_indicators.append({"name": "CPI (YoY)", "value": None, "prev": None, "unit": "%", "date": None})

        # 실업률: BLS LNS14000000
        ur = _fetch_bls_series("LNS14000000", 1)
        if ur:
            result.econ_indicators.append({
                "name": "실업률",
                "value": round(float(ur[-1]["value"]), 1),
                "prev": round(float(ur[-2]["value"]), 1) if len(ur) >= 2 else None,
                "unit": "%",
                "date": f"{ur[-1]['year']}-{ur[-1]['period'][1:]}",
            })
        else:
            result.econ_indicators.append({"name": "실업률", "value": None, "prev": None, "unit": "%", "date": None})

        return result
