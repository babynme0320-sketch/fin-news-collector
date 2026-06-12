from __future__ import annotations

import requests

from .base import CollectorResult

TIMEOUT_SEC = 10
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def _fetch_fred_series(series_id: str, count: int = 14) -> list[tuple[str, float]]:
    """FRED 공개 CSV 엔드포인트로 최근 N개 값 조회 (API 키 불필요)."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=TIMEOUT_SEC)
        if r.status_code != 200:
            return []
        rows = []
        for line in r.text.strip().split("\n")[1:]:
            parts = line.split(",")
            if len(parts) >= 2 and parts[1].strip() not in (".", ""):
                try:
                    rows.append((parts[0].strip(), float(parts[1].strip())))
                except ValueError:
                    continue
        return rows[-count:]
    except Exception:
        return []


def _fetch_fear_greed() -> dict | None:
    """CNN Fear & Greed Index API (인증 불필요)."""
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=TIMEOUT_SEC)
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

        # 기준금리 (Fed Funds Rate)
        fedfunds = _fetch_fred_series("FEDFUNDS", 2)
        if fedfunds:
            cur, prev = fedfunds[-1], fedfunds[-2] if len(fedfunds) >= 2 else fedfunds[-1]
            result.econ_indicators.append({
                "name": "기준금리", "value": cur[1], "prev": prev[1],
                "unit": "%", "date": cur[0],
            })
        else:
            result.econ_indicators.append({"name": "기준금리", "value": None, "prev": None, "unit": "%", "date": None})

        # CPI YoY (CPIAUCSL 지수 → 전년 동월 대비 % 계산)
        cpi = _fetch_fred_series("CPIAUCSL", 14)
        if len(cpi) >= 13:
            cur_val, yoy_val = cpi[-1][1], cpi[-13][1]
            cpi_yoy = round((cur_val - yoy_val) / yoy_val * 100, 1)
            prev_yoy = round((cpi[-2][1] - cpi[-14][1]) / cpi[-14][1] * 100, 1) if len(cpi) >= 14 else cpi_yoy
            result.econ_indicators.append({
                "name": "CPI (YoY)", "value": cpi_yoy, "prev": prev_yoy,
                "unit": "%", "date": cpi[-1][0],
            })
        else:
            result.econ_indicators.append({"name": "CPI (YoY)", "value": None, "prev": None, "unit": "%", "date": None})

        # 실업률
        unrate = _fetch_fred_series("UNRATE", 2)
        if unrate:
            cur, prev = unrate[-1], unrate[-2] if len(unrate) >= 2 else unrate[-1]
            result.econ_indicators.append({
                "name": "실업률", "value": cur[1], "prev": prev[1],
                "unit": "%", "date": cur[0],
            })
        else:
            result.econ_indicators.append({"name": "실업률", "value": None, "prev": None, "unit": "%", "date": None})

        return result
