"""차단 IP에서 어떤 접근법이 한경 Cloudflare를 통과하는지 비교(일회용 진단)."""
import requests

URL = "https://www.hankyung.com/feed/finance"
GOOGLE_NEWS = ("https://news.google.com/rss/search?"
               "q=site:hankyung.com%20when:1d&hl=ko&gl=KR&ceid=KR:ko")


def line(label, code, n, extra=""):
    print(f"{label:38} -> {code}  len={n}  {extra}", flush=True)


try:
    ip = requests.get("https://api.ipify.org", timeout=10).text
except Exception as e:
    ip = f"?({e})"
print(f"\n===== egress IP: {ip} =====", flush=True)

# 1) plain requests + curl UA (현재 설정)
try:
    r = requests.get(URL, headers={"User-Agent": "curl/8.7.1"}, timeout=15)
    line("requests curl/8.7.1 (current)", r.status_code, len(r.content))
except Exception as e:
    line("requests curl/8.7.1 (current)", "ERR", 0, str(e))

# 2) curl_cffi 브라우저 TLS 지문 여러 종
try:
    from curl_cffi import requests as cffi
    for imp in ["chrome", "chrome131", "chrome124", "safari", "safari17_0"]:
        try:
            r = cffi.get(URL, impersonate=imp, timeout=15)
            line(f"curl_cffi {imp}", r.status_code, len(r.content))
        except Exception as e:
            line(f"curl_cffi {imp}", "ERR", 0, str(e))
except Exception as e:
    print("curl_cffi unavailable:", e, flush=True)

# 3) Google News RSS (Cloudflare 우회 대체 소스)
try:
    r = requests.get(GOOGLE_NEWS, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    n_items = r.text.count("<item>")
    line("google-news RSS (site:hankyung)", r.status_code, len(r.content), f"items={n_items}")
except Exception as e:
    line("google-news RSS (site:hankyung)", "ERR", 0, str(e))
