"""한경 Cloudflare WAF 우회 방법을 CI(데이터센터 IP)에서 실측하는 일회용 진단 스크립트."""
import requests

URL = "https://www.hankyung.com/feed/finance"
BROWSER = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
FULL = {
    "User-Agent": BROWSER,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.hankyung.com/",
}


def show(label, code, body_len, extra=""):
    print(f"{label:48} -> {code}  len={body_len}  {extra}", flush=True)


print("=== plain requests ===", flush=True)
for label, headers in [
    ("curl/8.7.1 UA (current config)", {"User-Agent": "curl/8.7.1"}),
    ("googlebot UA", {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"}),
    ("browser UA + full headers", FULL),
]:
    try:
        r = requests.get(URL, headers=headers, timeout=15)
        show(label, r.status_code, len(r.content))
    except Exception as e:
        show(label, "ERR", 0, str(e))

print("=== curl_cffi (browser TLS impersonation) ===", flush=True)
try:
    from curl_cffi import requests as cffi
    for imp in ["chrome", "chrome124", "chrome110", "safari"]:
        try:
            r = cffi.get(URL, impersonate=imp, timeout=15)
            show(f"curl_cffi impersonate={imp}", r.status_code, len(r.content))
        except Exception as e:
            show(f"curl_cffi impersonate={imp}", "ERR", 0, str(e))
    # 브라우저 지문 + curl UA 조합
    try:
        r = cffi.get(URL, impersonate="chrome", headers={"User-Agent": "curl/8.7.1"}, timeout=15)
        show("curl_cffi chrome + curl UA", r.status_code, len(r.content))
    except Exception as e:
        show("curl_cffi chrome + curl UA", "ERR", 0, str(e))
except Exception as e:
    print(f"curl_cffi import failed: {e}", flush=True)

print("=== outbound IP ===", flush=True)
try:
    print("egress IP:", requests.get("https://api.ipify.org", timeout=10).text, flush=True)
except Exception as e:
    print("ip check failed:", e, flush=True)
