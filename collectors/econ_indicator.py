from __future__ import annotations

import contextlib
import io
from datetime import date

import requests
import yfinance as yf

from .base import CollectorResult
from .fred import fetch_series

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

        result.econ_indicators.extend(self._fred_indicators())

        return result

    def _fred_indicators(self) -> list[dict]:
        """FRED에서 키 없이 가져오는 지표들.

        T-Bill은 기준금리 프록시일 뿐이라 실제 정책금리를 따로 보여주고,
        물가·고용은 연준이 보는 지표라 금리 판단의 근거가 된다.
        """
        indicators = []

        # 미국 기준금리 (실제 정책금리)
        fedfunds = fetch_series("FEDFUNDS")
        if fedfunds:
            indicators.append(self._make(
                "미국 기준금리", round(float(fedfunds[-1]["Close"]), 2),
                round(float(fedfunds[-2]["Close"]), 2) if len(fedfunds) >= 2 else None,
                "%", fedfunds[-1]["Date"][:7],
            ))

        # 근원 CPI YoY (식료품·에너지 제외 — 연준이 더 중시)
        core = fetch_series("CPILFESL")
        indicators.append(self._yoy(core, "근원 CPI (YoY)"))

        # 비농업 신규고용 MoM (레벨 차분, 단위: 천명)
        payrolls = fetch_series("PAYEMS")
        if len(payrolls) >= 3:
            change = round(float(payrolls[-1]["Close"]) - float(payrolls[-2]["Close"]), 0)
            prev_change = round(float(payrolls[-2]["Close"]) - float(payrolls[-3]["Close"]), 0)
            indicators.append(self._make("비농업 고용 (MoM)", change, prev_change, "천명", payrolls[-1]["Date"][:7]))
        else:
            indicators.append(self._make("비농업 고용 (MoM)", None, None, "천명", None))

        return indicators

    def _yoy(self, series: list[dict], name: str) -> dict:
        """전년 동월 대비 증가율. 13개월치가 없으면 값을 비운다."""
        if len(series) < 13:
            return self._make(name, None, None, "%", None)
        try:
            current = float(series[-1]["Close"])
            year_ago = float(series[-13]["Close"])
            prev_yoy = round((float(series[-2]["Close"]) - float(series[-14]["Close"])) / float(series[-14]["Close"]) * 100, 1) if len(series) >= 14 else None
            return self._make(
                name, round((current - year_ago) / year_ago * 100, 1), prev_yoy, "%", series[-1]["Date"][:7]
            )
        except (ZeroDivisionError, KeyError, ValueError):
            return self._make(name, None, None, "%", None)

    def _make(self, name: str, value, prev, unit: str, date: str | None) -> dict:
        return {"name": name, "value": value, "prev": prev, "unit": unit, "date": date}
