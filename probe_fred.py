"""CI 러너에서 FRED에 접근되는지 확인 (임시 진단용)."""
import requests

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS"
try:
    r = requests.get(URL, timeout=(10, 30),
                     headers={"User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/125.0"})
    print(f"requests: status={r.status_code} len={len(r.text)}")
    print(f"본문 앞부분: {r.text[:120]!r}")
except Exception as exc:
    print(f"requests 실패: {type(exc).__name__}: {exc}")

from collectors.fred import fetch_series
rows = fetch_series("FEDFUNDS")
print(f"fetch_series: {len(rows)}행, 최근={rows[-1] if rows else '(없음)'}")
