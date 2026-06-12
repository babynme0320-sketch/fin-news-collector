#!/usr/bin/env python3
"""
로컬 개발 서버: 리포트를 생성하고 HTTP로 서빙.
파일 변경을 감지해 자동으로 리포트를 재생성합니다.
브라우저에서 새로고침하면 최신 내용을 확인할 수 있습니다.
"""
from __future__ import annotations

from datetime import date
import http.server
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import webbrowser

PORT = 8080
WATCH_PATHS = ["collectors", "reporter", "sources.yaml", "run.py"]
POLL_INTERVAL = 2.0


def _mtimes(paths: list[str]) -> dict[str, float]:
    result: dict[str, float] = {}
    for p in paths:
        path = Path(p)
        if path.is_file():
            result[str(path)] = path.stat().st_mtime
        elif path.is_dir():
            for f in path.rglob("*"):
                if f.is_file():
                    result[str(f)] = f.stat().st_mtime
    return result


def _generate() -> None:
    print("[serve] 리포트 생성 중...")
    env = {**os.environ, "CI": ""}  # CI 환경변수 제거해 webbrowser.open 방지
    res = subprocess.run(
        [sys.executable, "run.py"],
        capture_output=True, text=True, env=env,
    )
    if res.returncode != 0:
        print(f"[serve] 오류:\n{res.stderr.strip()}")
    else:
        print("[serve] 완료")


def _watcher(initial: dict[str, float]) -> None:
    prev = dict(initial)
    while True:
        time.sleep(POLL_INTERVAL)
        cur = _mtimes(WATCH_PATHS)
        changed = [k for k, v in cur.items() if prev.get(k) != v] + \
                  [k for k in prev if k not in cur]
        if changed:
            names = ", ".join(Path(c).name for c in changed[:3])
            print(f"[serve] 변경 감지 ({names}) → 재생성")
            _generate()
            prev = cur


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_request(self, code="-", size="-"):
        if str(code) not in ("304", "200"):
            print(f"[serve] {self.path} → {code}")

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    root = Path(__file__).parent
    os.chdir(root)

    _generate()

    initial = _mtimes(WATCH_PATHS)
    threading.Thread(target=_watcher, args=(initial,), daemon=True).start()

    today = date.today().strftime("%Y%m%d")
    url = f"http://localhost:{PORT}/report_{today}.html"

    handler = lambda *a, **kw: _Handler(*a, directory=str(root / "reports"), **kw)
    server = http.server.HTTPServer(("localhost", PORT), handler)

    print(f"[serve] {url}")
    print("[serve] 파일 변경 시 자동 재생성 | 종료: Ctrl+C")
    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve] 종료")
