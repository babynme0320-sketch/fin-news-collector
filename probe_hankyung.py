"""연속 요청량에 따른 한경 403 발생 지점을 측정(레이트리밋 가설 검증, 일회용)."""
import re
import time

import requests

FEED = "https://www.hankyung.com/feed/finance"
UA = {"User-Agent": "curl/8.7.1"}


def strip(s):
    return re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S).strip()


try:
    ip = requests.get("https://api.ipify.org", timeout=10).text
except Exception as e:
    ip = f"?({e})"
print(f"\n===== egress IP: {ip} =====", flush=True)

# 피드에서 기사 링크 수집
xml = requests.get(FEED, headers=UA, timeout=15).text
links = [strip(m) for m in re.findall(r"<link>(.*?)</link>", xml, re.S)]
links = [l for l in links if "/article/" in l][:30]
print(f"feed items to hit: {len(links)}", flush=True)


def run(label, delay, use_cffi=False, impersonate=None):
    print(f"\n--- {label} (delay={delay}s) ---", flush=True)
    if use_cffi:
        from curl_cffi import requests as client
        get = lambda u: client.get(u, impersonate=impersonate, timeout=15)
    else:
        get = lambda u: requests.get(u, headers=UA, timeout=15)
    first_403 = None
    codes = []
    for i, url in enumerate(links, 1):
        try:
            c = get(url).status_code
        except Exception as e:
            c = f"ERR:{type(e).__name__}"
        codes.append(c)
        if c == 403 and first_403 is None:
            first_403 = i
        if delay:
            time.sleep(delay)
    ok = sum(1 for c in codes if c == 200)
    print(f"  200s={ok}/{len(codes)}  first_403_at={first_403}  seq={codes}", flush=True)


# 1) 무지연 연속 요청(현재 collector와 유사한 버스트)
run("plain curl UA, no delay", 0.0)
# 2) 0.5s 지연
run("plain curl UA, 0.5s delay", 0.5)
# 3) curl_cffi safari, 무지연
run("curl_cffi safari, no delay", 0.0, use_cffi=True, impersonate="safari")
