from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import notifier
from collectors.base import Article, CollectorResult, MarketIndex

KST = timezone(timedelta(hours=9))


def _patch_state(monkeypatch, tmp_path: Path) -> Path:
    state_path = tmp_path / "notify_state.json"
    monkeypatch.setattr(notifier, "STATE_PATH", state_path)
    return state_path


def _indices() -> list[MarketIndex]:
    return [
        MarketIndex(symbol="^KS11", name="KOSPI", price=2700.12, change_pct=1.23, date="2026-09-25"),
        MarketIndex(symbol="^IXIC", name="NASDAQ", price=21000.5, change_pct=-2.10, date="2026-09-25"),
        MarketIndex(symbol="^DJI", name="다우존스", price=44000.0, change_pct=0.10, date="2026-09-25"),
        MarketIndex(symbol="^VIX", name="VIX", price=18.2, change_pct=0.0, date="2026-09-25", available=False),
    ]


def test_disabled_config_sends_nothing(monkeypatch, tmp_path: Path):
    _patch_state(monkeypatch, tmp_path)
    sent = []

    assert notifier.notify_daily(None, _indices(), {"enabled": False}, send=sent.append) is False
    assert sent == []


def test_missing_credentials_sends_nothing(monkeypatch, tmp_path: Path):
    _patch_state(monkeypatch, tmp_path)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    sent = []

    config = {"enabled": True, "chat_id": "123"}
    assert notifier.notify_daily(None, _indices(), config, send=sent.append) is False
    assert sent == []


def test_daily_sends_once_per_day(monkeypatch, tmp_path: Path):
    _patch_state(monkeypatch, tmp_path)
    sent = []
    config = {"enabled": True, "bot_token": "t", "chat_id": "1"}
    at_noon = datetime(2026, 9, 25, 12, 0, tzinfo=KST)

    first = notifier.notify_daily({"points": ["요약"]}, _indices(), config, now=at_noon, send=sent.append)
    second = notifier.notify_daily({"points": ["요약"]}, _indices(), config, now=at_noon, send=sent.append)

    assert first is True
    assert second is False
    assert len(sent) == 1


def test_daily_waits_until_configured_hour(monkeypatch, tmp_path: Path):
    _patch_state(monkeypatch, tmp_path)
    sent = []
    config = {"enabled": True, "bot_token": "t", "chat_id": "1", "daily_after_hour": 6}

    early = datetime(2026, 9, 25, 3, 0, tzinfo=KST)
    assert notifier.notify_daily(None, _indices(), config, now=early, send=sent.append) is False

    later = datetime(2026, 9, 25, 6, 30, tzinfo=KST)
    assert notifier.notify_daily(None, _indices(), config, now=later, send=sent.append) is True
    assert len(sent) == 1


def test_daily_retries_next_run_when_send_fails(monkeypatch, tmp_path: Path):
    """전송이 실패했는데 보냈다고 기록하면 그날 브리핑을 영영 못 받는다."""
    _patch_state(monkeypatch, tmp_path)
    config = {"enabled": True, "bot_token": "t", "chat_id": "1"}
    at_noon = datetime(2026, 9, 25, 12, 0, tzinfo=KST)

    assert notifier.notify_daily(None, _indices(), config, now=at_noon, send=lambda text: False) is False
    assert notifier.notify_daily(None, _indices(), config, now=at_noon, send=lambda text: True) is True


def test_daily_message_contains_points_indices_and_link(monkeypatch, tmp_path: Path):
    _patch_state(monkeypatch, tmp_path)
    sent = []
    config = {
        "enabled": True,
        "bot_token": "t",
        "chat_id": "1",
        "report_url": "https://example.com/report",
    }

    notifier.notify_daily(
        {"points": ["첫째 줄", "둘째 줄"], "keywords": []},
        _indices(),
        config,
        now=datetime(2026, 9, 25, 9, 0, tzinfo=KST),
        send=sent.append,
    )

    text = sent[0]
    assert "첫째 줄" in text
    assert "둘째 줄" in text
    assert "KOSPI" in text
    assert "+1.23%" in text
    assert "https://example.com/report" in text
    # 데이터가 없는 지수는 넣지 않는다
    assert "VIX" not in text


def test_daily_puts_biggest_movers_first(monkeypatch, tmp_path: Path):
    _patch_state(monkeypatch, tmp_path)
    sent = []
    config = {"enabled": True, "bot_token": "t", "chat_id": "1"}

    notifier.notify_daily(
        None, _indices(), config, now=datetime(2026, 9, 25, 9, 0, tzinfo=KST), send=sent.append
    )

    text = sent[0]
    assert text.index("NASDAQ") < text.index("KOSPI") < text.index("다우존스")


def test_daily_reports_missing_summary_explicitly(monkeypatch, tmp_path: Path):
    _patch_state(monkeypatch, tmp_path)
    sent = []
    config = {"enabled": True, "bot_token": "t", "chat_id": "1"}

    notifier.notify_daily(None, _indices(), config, now=datetime(2026, 9, 25, 9, 0, tzinfo=KST), send=sent.append)

    assert "요약을 만들지 못했습니다" in sent[0]


def test_sokbo_sends_only_new_articles(monkeypatch, tmp_path: Path):
    _patch_state(monkeypatch, tmp_path)
    config = {"enabled": True, "bot_token": "t", "chat_id": "1"}
    results = [CollectorResult(source_name="속보", items=[
        Article(title="[속보] 금리 인하", url="https://e.com/1", date="2026-09-25"),
        Article(title="일반 기사", url="https://e.com/2", date="2026-09-25"),
    ])]
    sent = []

    assert notifier.notify_sokbo(results, config, send=sent.append) == 1
    assert "[속보] 금리 인하" in sent[0]
    assert "일반 기사" not in sent[0]
    # 같은 기사는 다시 보내지 않는다
    assert notifier.notify_sokbo(results, config, send=sent.append) == 0
    assert len(sent) == 1


def test_sokbo_sends_new_article_added_later(monkeypatch, tmp_path: Path):
    _patch_state(monkeypatch, tmp_path)
    config = {"enabled": True, "bot_token": "t", "chat_id": "1"}
    sent = []

    first = [CollectorResult(source_name="속보", items=[
        Article(title="[속보] 하나", url="https://e.com/1", date="2026-09-25"),
    ])]
    second = [CollectorResult(source_name="속보", items=[
        Article(title="[속보] 하나", url="https://e.com/1", date="2026-09-25"),
        Article(title="[속보] 둘", url="https://e.com/2", date="2026-09-25"),
    ])]

    assert notifier.notify_sokbo(first, config, send=sent.append) == 1
    assert notifier.notify_sokbo(second, config, send=sent.append) == 1
    assert "둘" in sent[1]
    assert "하나" not in sent[1].split("\n", 1)[1]


def test_sokbo_not_recorded_when_send_fails(monkeypatch, tmp_path: Path):
    _patch_state(monkeypatch, tmp_path)
    config = {"enabled": True, "bot_token": "t", "chat_id": "1"}
    results = [CollectorResult(source_name="속보", items=[
        Article(title="[속보] 금리 인하", url="https://e.com/1", date="2026-09-25"),
    ])]

    assert notifier.notify_sokbo(results, config, send=lambda text: False) == 0
    assert notifier.notify_sokbo(results, config, send=lambda text: True) == 1


def test_sokbo_escapes_html_markup(monkeypatch, tmp_path: Path):
    _patch_state(monkeypatch, tmp_path)
    config = {"enabled": True, "bot_token": "t", "chat_id": "1"}
    sent = []
    results = [CollectorResult(source_name="속보", items=[
        Article(title="[속보] <b>금리</b> & 환율", url="https://e.com/1", date="2026-09-25"),
    ])]

    notifier.notify_sokbo(results, config, send=sent.append)

    assert "&lt;b&gt;" in sent[0]
    assert "&amp;" in sent[0]
    assert "<b>" not in sent[0]


def test_send_posts_to_telegram_api(monkeypatch):
    """실제 발송 경로의 요청 형태를 고정한다(토큰 없이도 검증 가능한 유일한 지점)."""
    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

    def fake_post(url, json=None, timeout=None):
        captured.update({"url": url, "json": json, "timeout": timeout})
        return DummyResponse()

    monkeypatch.setattr(notifier.requests, "post", fake_post)

    ok = notifier._send("TOKEN123", "999", "본문", {})

    assert ok is True
    assert captured["url"] == "https://api.telegram.org/botTOKEN123/sendMessage"
    assert captured["json"]["chat_id"] == "999"
    assert captured["json"]["text"] == "본문"


def test_send_returns_false_on_network_error(monkeypatch):
    import requests

    def fake_post(url, json=None, timeout=None):
        raise requests.ConnectionError("unreachable")

    monkeypatch.setattr(notifier.requests, "post", fake_post)

    assert notifier._send("TOKEN", "1", "본문", {}) is False


def test_credentials_prefer_environment_variables(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "from-env")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    token, chat_id = notifier._credentials({"bot_token": "from-config", "chat_id": "1"})

    assert (token, chat_id) == ("from-env", "42")


def test_corrupt_state_file_does_not_crash(monkeypatch, tmp_path: Path):
    """상태 파일이 깨져도 알림 자체는 나가야 한다(그날 브리핑을 놓치면 안 된다)."""
    state_path = _patch_state(monkeypatch, tmp_path)
    state_path.write_text("{ 깨진 json", encoding="utf-8")
    config = {"enabled": True, "bot_token": "t", "chat_id": "1"}
    sent = []

    sent_ok = notifier.notify_daily(
        None, _indices(), config, now=datetime(2026, 9, 25, 9, 0, tzinfo=KST), send=sent.append
    )

    assert sent_ok is True
    assert len(sent) == 1
