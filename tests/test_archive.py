from __future__ import annotations

from datetime import date
from pathlib import Path

from reporter.archive import add_report, archived_dates, build_index


def _report(tmp_path: Path, name: str, body: str = "<html>리포트</html>") -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_add_report_archives_under_yyyymmdd(tmp_path: Path):
    report = _report(tmp_path, "report_20260925.html", "<html>오늘</html>")
    archive_dir = tmp_path / "archive"

    destination = add_report(report, archive_dir)

    assert destination == archive_dir / "20260925.html"
    assert destination.read_text(encoding="utf-8") == "<html>오늘</html>"


def test_add_report_keeps_previously_archived_days(tmp_path: Path):
    """CI에는 그날치만 있으므로, 추가가 기존 아카이브를 지우지 않아야 한다."""
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    (archive_dir / "20260923.html").write_text("이전", encoding="utf-8")
    (archive_dir / "20260924.html").write_text("어제", encoding="utf-8")

    add_report(_report(tmp_path, "report_20260925.html", "오늘"), archive_dir)

    assert archived_dates(archive_dir) == [
        date(2026, 9, 25),
        date(2026, 9, 24),
        date(2026, 9, 23),
    ]
    assert (archive_dir / "20260923.html").read_text(encoding="utf-8") == "이전"


def test_index_lists_all_archived_dates_newest_first(tmp_path: Path):
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    for day in ("20260923", "20260924", "20260925"):
        (archive_dir / f"{day}.html").write_text("x", encoding="utf-8")

    index = build_index(archive_dir).read_text(encoding="utf-8")

    assert "총 3일치" in index
    positions = [index.index(f"{day}.html") for day in ("20260925", "20260924", "20260923")]
    assert positions == sorted(positions)


def test_index_groups_by_month(tmp_path: Path):
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    for day in ("20260831", "20260901"):
        (archive_dir / f"{day}.html").write_text("x", encoding="utf-8")

    index = build_index(archive_dir).read_text(encoding="utf-8")

    assert "2026년 09월" in index
    assert "2026년 08월" in index


def test_index_marks_today(tmp_path: Path):
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    (archive_dir / f"{date.today().strftime('%Y%m%d')}.html").write_text("x", encoding="utf-8")

    index = build_index(archive_dir).read_text(encoding="utf-8")

    assert 'class="badge today"' in index


def test_index_handles_empty_archive(tmp_path: Path):
    index = build_index(tmp_path / "archive").read_text(encoding="utf-8")

    assert "아직 보관된 리포트가 없습니다" in index


def test_archived_dates_ignores_unrelated_files(tmp_path: Path):
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    (archive_dir / "20260925.html").write_text("x", encoding="utf-8")
    (archive_dir / "index.html").write_text("x", encoding="utf-8")
    (archive_dir / "notadate.html").write_text("x", encoding="utf-8")
    (archive_dir / "20261332.html").write_text("x", encoding="utf-8")  # 존재하지 않는 날짜

    assert archived_dates(archive_dir) == [date(2026, 9, 25)]


def test_build_index_links_back_to_latest_report(tmp_path: Path):
    index = build_index(tmp_path / "archive").read_text(encoding="utf-8")

    assert 'href="../"' in index
