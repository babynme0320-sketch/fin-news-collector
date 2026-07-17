"""수정된 WebScraperCollector가 CI(데이터센터 IP)에서 한경을 403 없이 수집하는지 검증."""
import yaml
from collectors.web_scraper import WebScraperCollector

with open("sources.yaml", encoding="utf-8") as f:
    config = yaml.safe_load(f)

targets = [s for s in config["web_sources"]
           if s.get("enabled", True) and "한국경제" in s["name"]]

fail = False
for src in targets:
    result = WebScraperCollector(src).collect()
    status = "OK" if result.items and not result.error else "FAIL"
    if status == "FAIL":
        fail = True
    print(f"[{status}] {src['name']:20} items={len(result.items):2}  error={result.error}", flush=True)

raise SystemExit(1 if fail else 0)
