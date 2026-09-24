"""알림 발송.

리포트가 갱신돼도 URL을 열어야 알 수 있고, 속보 섹션을 만들어놨지만 정작
속보가 떴을 때 알려주지 않는다. 이 모듈이 텔레그램으로 두 가지를 보낸다.

- 하루 1회 브리핑: 오늘의 핵심 요약 + 주요 지수 + 리포트 링크
- 속보: [속보] 기사가 새로 잡히면 즉시(같은 기사는 다시 보내지 않음)

자격증명(bot token / chat id)이 없으면 조용히 아무것도 하지 않는다.
알림은 부가 기능이지, 리포트 생성의 전제가 아니다.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from collectors.base import Article, CollectorResult, MarketIndex

KST = timezone(timedelta(hours=9))
TELEGRAM_API = "https://api.telegram.org"
TIMEOUT = (5, 20)
STATE_PATH = Path("data") / "notify_state.json"
MAX_SOKBO_PER_RUN = 5
_MARKUP = re.compile(r"[<>&]")


def notify_daily(
    summary: dict | None,
    indices: list[MarketIndex],
    config: dict,
    now: datetime | None = None,
    send=None,
) -> bool:
    """하루 1회 브리핑을 보낸다. 이미 보냈거나 아직 이른 시간이면 False."""
    if not config.get("enabled", False):
        return False

    now = now or datetime.now(KST)
    if now.hour < config.get("daily_after_hour", 6):
        return False

    token, chat_id = _credentials(config)
    if not token:
        return False

    state = _load_state()
    today = now.strftime("%Y-%m-%d")
    if state.get("daily_sent_on") == today:
        return False

    text = _format_daily(summary, indices, config, now)
    if not _send(token, chat_id, text, config, send):
        return False

    state["daily_sent_on"] = today
    _save_state(state)
    return True


def notify_sokbo(
    results: list[CollectorResult],
    config: dict,
    now: datetime | None = None,
    send=None,
) -> int:
    """새로 잡힌 [속보]를 알린다. 보낸 기사 수를 반환."""
    if not config.get("enabled", False):
        return 0

    token, chat_id = _credentials(config)
    if not token:
        return 0

    now = now or datetime.now(KST)
    state = _load_state()
    sent_urls = set(state.get("sokbo_urls", []))

    fresh = []
    for result in results:
        for item in result.items:
            if not isinstance(item, Article) or not item.url:
                continue
            if "[속보]" not in item.title or item.url in sent_urls:
                continue
            fresh.append(item)

    if not fresh:
        return 0

    fresh = fresh[:MAX_SOKBO_PER_RUN]
    lines = ["🚨 속보", ""]
    for item in fresh:
        lines.append(f"• {_escape(item.title)}")
    report_url = config.get("report_url", "")
    if report_url:
        lines.extend(["", report_url])

    if not _send(token, chat_id, "\n".join(lines), config, send):
        return 0

    # 보낸 것만 기록한다. 전송이 실패하면 다음 실행에서 다시 시도된다.
    state["sokbo_urls"] = sorted(sent_urls | {item.url for item in fresh})[-200:]
    _save_state(state)
    return len(fresh)


def _format_daily(
    summary: dict | None, indices: list[MarketIndex], config: dict, now: datetime
) -> str:
    lines = [f"📊 금융 데일리 · {now.strftime('%m월 %d일')}", ""]

    if summary and summary.get("points"):
        lines.append("✨ 오늘의 핵심")
        for point in summary["points"]:
            lines.append(f"• {_escape(point)}")
        lines.append("")
    else:
        lines.extend(["✨ 오늘의 핵심", "• 요약을 만들지 못했습니다 (아래 리포트에서 확인)", ""])

    # 값이 멈춘 지표는 뺀다. 브리핑에서 오래된 등락률은 없는 것보다 나쁘다.
    movers = [idx for idx in indices if idx.available and idx.stale_days < 3]
    if movers:
        lines.append("📈 주요 지수")
        for idx in _top_movers(movers, config.get("max_movers", 6)):
            sign = "+" if idx.change_pct > 0 else ""
            lines.append(f"• {_escape(idx.name)} {idx.price:,.2f} ({sign}{idx.change_pct:.2f}%)")
        lines.append("")

    report_url = config.get("report_url", "")
    if report_url:
        lines.append(report_url)

    return "\n".join(lines).strip()


def _top_movers(indices: list[MarketIndex], limit: int) -> list[MarketIndex]:
    """변동이 큰 순으로 고른다 — 브리핑에서 의미 있는 건 큰 움직임이다."""
    return sorted(indices, key=lambda idx: abs(idx.change_pct), reverse=True)[:limit]


def _credentials(config: dict) -> tuple[str, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or config.get("bot_token", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config.get("chat_id", "")
    return token.strip(), str(chat_id).strip()


def _send(token: str, chat_id: str, text: str, config: dict, send=None) -> bool:
    if send is not None:
        # 주입된 발송기는 예외를 던지거나 False를 반환해 실패를 알린다.
        # None을 실패로 보면 list.append 같은 자연스러운 대역이 조용히 실패한다.
        return send(text) is not False
    url = f"{config.get('api_base', TELEGRAM_API)}/bot{token}/sendMessage"
    try:
        response = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": config.get("parse_mode", "HTML"),
                "disable_web_page_preview": True,
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException:
        return False
    return True


def _escape(text: str) -> str:
    """parse_mode=HTML에서 깨지지 않도록 최소한만 이스케이프한다."""
    return _MARKUP.sub(lambda m: {"<": "&lt;", ">": "&gt;", "&": "&amp;"}[m.group(0)], text)


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
