"""지난 리포트 아카이브.

커밋되는 산출물은 docs/index.html 하나뿐이라 매 실행 덮어써지고, reports/ 는
gitignore 대상이라 보관 기간이 지나면 사라진다 → 어제 리포트가 남지 않는다.
이 모듈은 생성된 리포트를 날짜별 파일로 보관하고 목록 페이지를 만든다.

CLI로도 쓸 수 있다(CI에서 docs/archive 를 갱신할 때):
    python -m reporter.archive add <report.html> <archive_dir>
    python -m reporter.archive build <archive_dir>
"""
from __future__ import annotations

import re
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
ARCHIVE_NAME = re.compile(r"^(\d{8})\.html$")
PAGE_SIZE_LIMIT = 200  # 목록이 길어져도 페이지가 감당하도록 최근 N일만 링크

_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def archived_dates(archive_dir: Path) -> list[date]:
    """아카이브에 실제로 존재하는 날짜 목록(최신순)."""
    if not archive_dir.is_dir():
        return []

    dates = []
    for entry in archive_dir.iterdir():
        if not entry.is_file():
            continue
        match = ARCHIVE_NAME.match(entry.name)
        if not match:
            continue
        try:
            dates.append(datetime.strptime(match.group(1), "%Y%m%d").date())
        except ValueError:
            continue
    return sorted(dates, reverse=True)


def add_report(report_path: Path, archive_dir: Path) -> Path:
    """리포트를 archive_dir/YYYYMMDD.html 로 보관하고 목록을 다시 만든다."""
    date_str = _date_from_name(report_path.name) or datetime.now(KST).strftime("%Y%m%d")
    archive_dir.mkdir(parents=True, exist_ok=True)

    destination = archive_dir / f"{date_str}.html"
    shutil.copyfile(report_path, destination)
    build_index(archive_dir)
    return destination


def build_index(archive_dir: Path) -> Path:
    """archive_dir/index.html 을 디렉터리 내용 기준으로 다시 만든다."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    dates = archived_dates(archive_dir)
    today = datetime.now(KST).date()

    index_path = archive_dir / "index.html"
    index_path.write_text(_render_index(dates, today), encoding="utf-8")
    return index_path


def _date_from_name(name: str) -> str:
    match = re.match(r"^report_(\d{8})\.html$", name)
    return match.group(1) if match else ""


def _render_index(dates: list[date], today: date) -> str:
    shown = dates[:PAGE_SIZE_LIMIT]

    if shown:
        newest = shown[0]
        summary = f"총 {len(dates)}일치 · 최근 {newest.strftime('%Y-%m-%d')}"
    else:
        summary = "아직 보관된 리포트가 없습니다"

    # 월별로 묶어서 표시
    groups: list[tuple[str, list[date]]] = []
    for value in shown:
        key = value.strftime("%Y년 %m월")
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        groups[-1][1].append(value)

    sections = []
    for month, values in groups:
        rows = []
        for value in values:
            label = f"{value.month}월 {value.day}일 ({_WEEKDAYS[value.weekday()]})"
            badge = '<span class="badge today">오늘</span>' if value == today else ""
            rows.append(
                f'<a class="row" href="{value.strftime("%Y%m%d")}.html">'
                f'<span class="date">{label}</span>{badge}'
                f'<span class="arrow">›</span></a>'
            )
        sections.append(f'<div class="month">{month}</div>\n' + "\n".join(rows))

    body = "\n".join(sections) if sections else '<div class="empty">아직 보관된 리포트가 없습니다</div>'
    truncated = (
        f'<div class="note">목록은 최근 {PAGE_SIZE_LIMIT}일까지만 표시합니다. '
        f"그 이전 리포트도 파일은 남아 있습니다.</div>"
        if len(dates) > PAGE_SIZE_LIMIT
        else ""
    )

    return _INDEX_TEMPLATE.format(summary=summary, body=body, truncated=truncated, today=today.isoformat())


_INDEX_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>지난 리포트 · 금융 데일리</title>
<style>
:root {{
  --bg:#f5f6f8; --surface:#fff; --surface2:#f0f2f5; --text:#111827; --muted:#6b7280;
  --line:#e5e7eb; --primary:#2563eb; --primary-light:#dbeafe;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg:#0f1115; --surface:#181b21; --surface2:#22262e; --text:#e8eaed; --muted:#9aa1ac;
    --line:#2a2f38; --primary:#60a5fa; --primary-light:#1e3a5f;
  }}
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; padding:20px 16px 60px; background:var(--bg); color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",
    "Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  line-height:1.6; -webkit-text-size-adjust:100%;
}}
.wrap {{ max-width:560px; margin:0 auto; }}
.top {{ display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin-bottom:4px; }}
h1 {{ font-size:21px; margin:0; letter-spacing:-0.3px; }}
.back {{ font-size:13px; color:var(--primary); text-decoration:none; white-space:nowrap; }}
.summary {{ color:var(--muted); font-size:13px; margin-bottom:20px; }}
.month {{
  font-size:12px; font-weight:700; color:var(--muted); text-transform:none;
  margin:22px 0 8px; padding-left:2px;
}}
.row {{
  display:flex; align-items:center; gap:10px; padding:14px 16px; background:var(--surface);
  border-radius:12px; margin-bottom:8px; text-decoration:none; color:var(--text);
  border:1px solid var(--line);
}}
.row:active {{ background:var(--surface2); }}
.date {{ font-size:15px; font-weight:600; }}
.badge {{
  font-size:11px; font-weight:700; padding:1px 7px; border-radius:999px;
  background:var(--primary-light); color:var(--primary);
}}
.arrow {{ margin-left:auto; color:var(--muted); font-size:18px; }}
.empty, .note {{ color:var(--muted); font-size:13px; padding:14px 2px; }}
.note {{ margin-top:16px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <h1>지난 리포트</h1>
    <a class="back" href="../">오늘 리포트 →</a>
  </div>
  <div class="summary">{summary}</div>
  {body}
  {truncated}
</div>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2

    command = argv[1]
    if command == "add":
        if len(argv) < 4:
            print("usage: python -m reporter.archive add <report.html> <archive_dir>")
            return 2
        report_path, archive_dir = Path(argv[2]), Path(argv[3])
        if not report_path.is_file():
            print(f"리포트가 없습니다: {report_path}")
            return 1
        destination = add_report(report_path, archive_dir)
        print(f"보관: {destination}")
        return 0

    if command == "build":
        archive_dir = Path(argv[2])
        index = build_index(archive_dir)
        print(f"목록 생성: {index} ({len(archived_dates(archive_dir))}일치)")
        return 0

    print(f"알 수 없는 명령: {command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
