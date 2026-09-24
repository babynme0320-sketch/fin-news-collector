from __future__ import annotations

from collectors.base import Article, CollectorResult
from summarizer import _content_tokens, _is_grounded, _parse_json, summarize

# 실제 생성된 요약에서 확인된 실패 사례를 그대로 고정한다.
# 모델이 "워시 연준 의장", "기준금리를 0.25%p 인상"을 헤드라인에 없는데도 지어냈다.
FABRICATED = "미국 연준이 기준금리를 0.25%포인트 인상했으며, 워시 연준 의장은 인플레이션이 너무 높다고 밝혔다."

CORPUS = (
    "[한국경제] OECD, 한국 성장률 전망 2.6%→3.7% 상향 — G20 중 최대 폭\n"
    "[한국경제] 서울 아파트값 85주 연속 상승 — 역대 최장 기록과 동률\n"
    "[한국경제] 대미투자 새 축으로 떠오른 원전 — 텍사스 엔시날 가스복합화력발전소 건설 확정\n"
    "[매일경제] 글로벌 부채 365조달러 돌파 — 경제학자 경고\n"
)


def test_fabricated_sentence_is_rejected():
    assert _is_grounded(FABRICATED, CORPUS, 0.7) is False


def test_grounded_sentence_passes():
    grounded = "OECD가 한국의 성장률 전망을 2.6%에서 3.7%로 상향했다."

    assert _is_grounded(grounded, CORPUS, 0.7) is True


def test_number_not_in_corpus_is_rejected():
    """숫자 하나만 틀려도 문장 전체를 못 믿게 되므로 즉시 탈락시킨다."""
    tampered = "OECD가 한국의 성장률 전망을 2.6%에서 9.9%로 상향했다."

    assert _is_grounded(tampered, CORPUS, 0.7) is False


def test_content_tokens_strip_particles():
    tokens = _content_tokens("정부가 대미투자의 원전을 확정했다.")

    assert "정부" in tokens
    assert "대미투자" in tokens
    assert "정부가" not in tokens


def test_parse_json_handles_code_fence():
    payload = _parse_json('```json\n{"points": ["가"], "keywords": []}\n```')

    assert payload["points"] == ["가"]


def test_parse_json_handles_leading_prose():
    payload = _parse_json('설명입니다. {"points": ["가"]} 끝.')

    assert payload["points"] == ["가"]


def test_summarize_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("summarizer._api_key", lambda: "")

    results = [CollectorResult(source_name="한국경제", items=[
        Article(title=f"제목 {i}", url=f"https://e.com/{i}", date="2026-09-25") for i in range(10)
    ])]

    assert summarize(results) is None


def test_summarize_returns_none_when_too_few_headlines(monkeypatch):
    monkeypatch.setattr("summarizer._api_key", lambda: "key")
    results = [CollectorResult(source_name="한국경제", items=[
        Article(title="하나", url="u", date="d")
    ])]

    assert summarize(results) is None


def test_summarize_drops_ungrounded_points_and_keeps_good_ones(monkeypatch):
    """근거 없는 문장만 골라 버리고, 남은 것으로 요약을 만든다."""
    monkeypatch.setattr("summarizer._api_key", lambda: "key")
    monkeypatch.setattr("summarizer._request_summary", lambda key, headlines, config: {
        "points": [
            FABRICATED,  # 탈락해야 함
            "OECD가 한국의 성장률 전망을 2.6%에서 3.7%로 상향했다.",
            "서울 아파트값이 85주 연속 상승했다.",
            "글로벌 부채가 365조달러를 돌파했다.",
            "대미투자 새 축으로 원전이 떠올랐다.",
        ],
        "keywords": ["OECD 성장률", "워시 연준 의장", "원전"],
    })

    results = [CollectorResult(source_name="한국경제", items=[
        Article(title=f"제목 {i}", url=f"https://e.com/{i}", date="2026-09-25") for i in range(10)
    ])]
    # 코퍼스는 summarize 내부에서 results로 만들어지므로, 검증 대상 문장이 통과하도록
    # 헤드라인 자체를 위 문장들과 같은 내용으로 맞춘다.
    results[0].items = [
        Article(title="OECD, 한국 성장률 전망 2.6%에서 3.7%로 상향", url="u1", date="d"),
        Article(title="서울 아파트값 85주 연속 상승", url="u2", date="d"),
        Article(title="글로벌 부채 365조달러 돌파", url="u3", date="d"),
        Article(title="대미투자 새 축으로 원전 부상", url="u4", date="d"),
        Article(title="기타 기사", url="u5", date="d"),
    ]

    summary = summarize(results)

    assert summary is not None
    assert all("워시" not in point for point in summary["points"])
    assert all("연준" not in point for point in summary["points"])
    # 근거 없는 키워드도 걸러진다
    assert "워시 연준 의장" not in summary["keywords"]


def test_summarize_returns_none_when_too_few_points_survive(monkeypatch):
    """근거 있는 문장이 거의 없으면 빈 요약보다 없는 편이 낫다."""
    monkeypatch.setattr("summarizer._api_key", lambda: "key")
    monkeypatch.setattr("summarizer._request_summary", lambda key, headlines, config: {
        "points": [FABRICATED, "또 다른 지어낸 문장입니다.", "역시 없는 내용입니다."],
        "keywords": [],
    })

    results = [CollectorResult(source_name="한국경제", items=[
        Article(title=f"제목 {i}", url=f"https://e.com/{i}", date="2026-09-25") for i in range(10)
    ])]

    assert summarize(results) is None


def test_summarize_survives_request_failure(monkeypatch):
    import requests

    monkeypatch.setattr("summarizer._api_key", lambda: "key")

    def _boom(*args, **kwargs):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr("summarizer._request_summary", _boom)

    results = [CollectorResult(source_name="한국경제", items=[
        Article(title=f"제목 {i}", url=f"https://e.com/{i}", date="2026-09-25") for i in range(10)
    ])]

    assert summarize(results) is None
