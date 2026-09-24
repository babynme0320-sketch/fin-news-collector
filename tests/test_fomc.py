from __future__ import annotations

from collectors.fomc import FomcCollector

# 실제 fomccalendars.htm의 행 구조를 축약한 것.
# - 1월 회의: 성명서 + 의사록 공표 완료
# - 9월 회의: 성명서 + 경제전망, 의사록 미공표
# - 10월 회의: 예정 회의라 링크 없음
CALENDAR_HTML = """
<html><body>
<div class="panel panel-default">
  <div class="panel-heading">2026 FOMC Meetings</div>

  <div class="row fomc-meeting">
    <div class="fomc-meeting__month col-xs-5"><strong>January</strong></div>
    <div class="fomc-meeting__date col-xs-4">27-28</div>
    <div class="col-xs-12 col-md-4">
      <strong>Statement:</strong><br/>
      <a href="/monetarypolicy/files/monetary20260128a1.pdf">PDF</a> |
      <a href="/newsevents/pressreleases/monetary20260128a.htm">HTML</a><br/>
      <a href="/newsevents/pressreleases/monetary20260128a1.htm">Implementation Note</a>
    </div>
    <div class="col-xs-12 col-md-4 col-lg-3">
      <a href="/monetarypolicy/fomcpressconf20260128.htm">Press Conference</a>
    </div>
    <div class="col-xs-12 col-md-4 col-lg-4 fomc-meeting__minutes">
      <strong>Minutes:</strong><br/>
      <a href="/monetarypolicy/files/fomcminutes20260128.pdf">PDF</a> |
      <a href="/monetarypolicy/fomcminutes20260128.htm">HTML</a>
      <br/> (Released February 18, 2026)
    </div>
  </div>

  <div class="row fomc-meeting">
    <div class="fomc-meeting__month col-xs-5"><strong>September</strong></div>
    <div class="fomc-meeting__date col-xs-4">15-16*</div>
    <div class="col-xs-12 col-md-4">
      <strong>Statement:</strong><br/>
      <a href="/monetarypolicy/files/monetary20260916a1.pdf">PDF</a> |
      <a href="/newsevents/pressreleases/monetary20260916a.htm">HTML</a><br/>
      <a href="/newsevents/pressreleases/monetary20260916a1.htm">Implementation Note</a>
    </div>
    <div class="col-xs-12 col-md-4 col-lg-3">
      <a href="/monetarypolicy/fomcpresconf20260916.htm">Press Conference</a><br/>
      <a href="/monetarypolicy/files/fomcprojtabl20260916.pdf">PDF</a> |
      <a href="/monetarypolicy/fomcprojtabl20260916.htm">HTML</a>
    </div>
    <div class="col-xs-12 col-md-4 col-lg-4 fomc-meeting__minutes"></div>
  </div>

  <div class="row fomc-meeting">
    <div class="fomc-meeting__month col-xs-5"><strong>October</strong></div>
    <div class="fomc-meeting__date col-xs-4">27-28</div>
    <div class="col-xs-12 col-md-4"></div>
    <div class="col-xs-12 col-md-4 col-lg-3"></div>
    <div class="col-xs-12 col-md-4 col-lg-4 fomc-meeting__minutes"></div>
  </div>
</div>
</body></html>
"""


class _DummyResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        return None


def _patch(monkeypatch) -> None:
    monkeypatch.setattr(
        "collectors.fomc.requests.get", lambda url, headers, timeout: _DummyResponse(CALENDAR_HTML)
    )
    monkeypatch.setattr("collectors.fomc.download_pdf", lambda url, source: "")


def test_fomc_collects_statement_projections_and_minutes(monkeypatch):
    _patch(monkeypatch)

    result = FomcCollector({}).collect()

    assert result.error is None
    assert result.source_name == "연준 보고서"
    # 1월: 성명서 + 의사록 / 9월: 성명서 + 경제전망 (10월 예정 회의는 링크 없음)
    assert len(result.items) == 4

    files = {item.pdf_url.rsplit("/", 1)[-1] for item in result.items}
    assert files == {
        "monetary20260128a1.pdf",
        "monetary20260916a1.pdf",
        "fomcprojtabl20260916.pdf",
        "fomcminutes20260128.pdf",
    }
    # 9월 회의 의사록은 아직 공표 전이라 1월 회의 것만 들어온다.
    assert [f for f in files if f.startswith("fomcminutes")] == ["fomcminutes20260128.pdf"]


def test_fomc_minutes_use_release_date_but_statement_uses_meeting_date(monkeypatch):
    _patch(monkeypatch)

    result = FomcCollector({}).collect()
    by_file = {item.pdf_url.rsplit("/", 1)[-1]: item for item in result.items}

    # 성명서는 회의 종료일(1/28) 기준
    assert by_file["monetary20260128a1.pdf"].date == "2026-01-28"
    # 의사록은 공표일(2/18) 기준 — 3주 뒤에 나오므로 이래야 최신 정렬이 맞는다
    assert by_file["fomcminutes20260128.pdf"].date == "2026-02-18"
    # 경제전망은 회의 종료일(9/16) 기준
    assert by_file["fomcprojtabl20260916.pdf"].date == "2026-09-16"


def test_fomc_sorts_newest_first(monkeypatch):
    _patch(monkeypatch)

    result = FomcCollector({}).collect()
    dates = [item.date for item in result.items]

    assert dates == sorted(dates, reverse=True)


def test_fomc_respects_max_items_and_include_filter(monkeypatch):
    _patch(monkeypatch)

    only_minutes = FomcCollector({"include": ["minutes"], "max_items": 1}).collect()
    assert len(only_minutes.items) == 1
    assert "fomcminutes" in only_minutes.items[0].pdf_url

    limited = FomcCollector({"max_items": 2}).collect()
    assert len(limited.items) == 2
    assert limited.items[0].date == "2026-09-16"


def test_fomc_reports_error_when_calendar_has_no_links(monkeypatch):
    monkeypatch.setattr(
        "collectors.fomc.requests.get",
        lambda url, headers, timeout: _DummyResponse("<html><body></body></html>"),
    )

    result = FomcCollector({}).collect()

    assert result.error == "회의자료 링크를 찾지 못함"
    assert result.items == []


def test_fomc_reports_error_on_request_failure(monkeypatch):
    import requests

    def _boom(url, headers, timeout):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr("collectors.fomc.requests.get", _boom)

    result = FomcCollector({}).collect()

    assert "boom" in result.error
