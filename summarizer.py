"""오늘의 요약.

리포트는 하루 80건을 평면 나열한다. 정작 "오늘 중요한 게 뭔가"는 읽는 사람이
80건을 훑어서 판단해야 한다 — 모으는 일은 자동화됐지만 읽는 일은 그렇지 않다.
이 모듈이 제목·요약을 LLM에 넘겨 핵심 5줄과 주목 키워드를 받아온다.

키가 없거나 호출이 실패하면 None을 돌려주고 리포트는 그대로 생성된다.
요약은 있으면 좋은 것이지, 없으면 리포트가 안 나오는 것이 아니다.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests

from collectors.base import Article, CollectorResult

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
TIMEOUT = (5, 90)
MAX_HEADLINES = 60
MAX_POINTS = 5

SYSTEM_PROMPT = (
    "너는 한국 금융 데일리 브리핑을 만드는 편집자다. "
    "주어진 헤드라인 목록에서 오늘 시장과 경제에 실제로 중요한 것만 골라라. "
    "같은 사안을 다룬 기사는 하나로 묶고, 단순 홍보성·연예·스포츠성 기사는 버려라. "
    "아래 두 규칙을 반드시 지킨다.\n"
    "1. 주어진 목록에 없는 사실은 절대 쓰지 마라. 배경지식으로 추측하거나 보태지 마라. "
    "금리 인상/인하, 수치, 발언, 인과관계는 목록에 명시된 것만 말한다.\n"
    "2. 한국어로, 각 줄은 한 문장으로 쓴다."
)

USER_TEMPLATE = """아래는 오늘 수집된 금융 뉴스 헤드라인이다. 형식은 "[출처] 제목 — 요약"이다.

{headlines}

다음을 JSON으로만 출력하라. 설명이나 코드블록 없이 JSON만.
{{
  "points": ["오늘의 핵심 5줄. 각 항목은 한 문장. 서로 다른 사안으로."],
  "keywords": ["주목 키워드 3~6개. 종목명·지표·정책 용어 위주로."]
}}"""


def summarize(results: list[CollectorResult], config: dict | None = None) -> dict | None:
    """수집 결과에서 오늘의 요약을 만든다. 불가능하면 None."""
    config = config or {}
    headlines = _collect_headlines(results, config.get("max_headlines", MAX_HEADLINES))
    if len(headlines) < 5:
        return None

    key = _api_key()
    if not key:
        return None

    try:
        payload = _request_summary(key, headlines, config)
    except (requests.RequestException, ValueError, KeyError):
        return None

    corpus = "\n".join(headlines)
    return _validate(payload, config, corpus, config.get("min_grounded_ratio", 0.7))


def _collect_headlines(results: list[CollectorResult], limit: int) -> list[str]:
    """요약의 근거가 되는 헤드라인 목록. 요약문(lede)을 함께 넣어 근거를 넓힌다."""
    lines: list[str] = []
    seen: set[str] = set()
    for result in results:
        for item in result.items:
            if not isinstance(item, Article):
                continue
            title = item.title.strip()
            if not title or title in seen:
                continue
            seen.add(title)
            lede = " ".join((item.lede or "").split())[:120]
            source = f"[{item.source}] " if item.source else ""
            lines.append(f"{source}{title}" + (f" — {lede}" if lede else ""))
    return lines[:limit]


def _api_key() -> str:
    key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if key:
        return key
    path = Path(os.path.expanduser("~/.deepseek_key"))
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _request_summary(key: str, headlines: list[str], config: dict) -> dict:
    response = requests.post(
        config.get("api_url", API_URL),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        json={
            "model": config.get("model", MODEL),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": USER_TEMPLATE.format(headlines="\n".join(f"- {h}" for h in headlines)),
                },
            ],
            "temperature": 1.0,
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return _parse_json(content)


def _parse_json(content: str) -> dict:
    """모델이 코드블록이나 군더더기를 붙여도 JSON 본문만 뽑아낸다."""
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"JSON을 찾지 못함: {content[:200]}")
        text = text[start : end + 1]
    return json.loads(text)


def _validate(payload: dict, config: dict, corpus: str, min_ratio: float) -> dict | None:
    """모델 출력에서 근거 없는 문장을 걸러낸다.

    실제로 확인된 실패: 헤드라인에 없는 "워시 연준 의장", "기준금리를 0.25%p 인상"을
    지어냈다. 근거 있는 문장(텍사스·엔시날·3.7%)과 섞여 나와서 그대로 두면
    읽는 사람이 구분할 수 없다. 수집한 텍스트에 실제로 있는 단어로만 이루어진
    문장만 남긴다.
    """
    points = []
    for raw in payload.get("points", []):
        text = str(raw).strip()
        if text and _is_grounded(text, corpus, min_ratio):
            points.append(text)
    # 키워드는 짧아서 비율 검사가 무의미하다 — 수집된 텍스트에 실제로 나온 말만 남긴다.
    keywords = []
    for raw in payload.get("keywords", []):
        keyword = str(raw).strip()
        if not keyword:
            continue
        tokens = _content_tokens(keyword)
        if tokens and all(token in corpus for token in tokens):
            keywords.append(keyword)
    points = points[: config.get("max_points", MAX_POINTS)]

    # 근거가 남은 문장이 너무 적으면 요약을 내보내지 않는다(빈 요약보다 없는 게 낫다).
    if len(points) < config.get("min_points", 3):
        return None
    return {"points": points, "keywords": keywords[:6]}


def _is_grounded(text: str, corpus: str, min_ratio: float) -> bool:
    tokens = _content_tokens(text)
    if not tokens:
        return False

    # 숫자는 하나라도 근거가 없으면 탈락 — 틀린 수치는 문장 전체를 못 믿게 만든다.
    for token in tokens:
        for number in re.findall(r"\d+(?:\.\d+)?", token):
            if number not in corpus:
                return False

    hits = sum(1 for token in tokens if token in corpus)
    return hits / len(tokens) >= min_ratio


_PARTICLES = (
    "으로써", "으로서", "에서는", "에게서", "이라고", "라는", "이라는", "에서", "에게",
    "으로", "로써", "까지", "부터", "보다", "처럼", "만큼", "이며", "이고", "인", "은",
    "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "로", "만", "나", "며",
)

_STOPWORDS = {
    "오늘", "이번", "지난", "관련", "대한", "위해", "통해", "따라", "대해", "가운데",
    "전망", "발표", "지적", "강조", "나타", "밝혔", "있다", "했다", "된다", "이며",
}


def _content_tokens(text: str) -> list[str]:
    """문장에서 검증 대상 단어만 뽑는다(조사·기호·불용어 제거)."""
    tokens = []
    for chunk in re.split(r"[\s,·…·、。\"'()\[\]{}<>~\-—]+", text):
        token = chunk.strip(".,!?%\"'")
        if len(token) < 2:
            continue
        for particle in _PARTICLES:
            if len(token) > len(particle) + 1 and token.endswith(particle):
                token = token[: -len(particle)]
                break
        if len(token) >= 2 and token not in _STOPWORDS:
            tokens.append(token)
    return tokens


def main(argv: list[str]) -> int:
    """수동 확인용: 리포트 HTML에서 헤드라인을 뽑아 요약을 출력한다."""
    if len(argv) < 2:
        print(__doc__)
        return 2

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(Path(argv[1]).read_text(encoding="utf-8"), "html.parser")
    results = []
    for section in soup.select(".news-section"):
        head = section.select_one(".section-head")
        name = head.get_text(" ", strip=True) if head else ""
        items = []
        for node in section.select(".news-item"):
            link = node.select_one(".item-link")
            if not link:
                continue
            lede = node.select_one(".item-lede")
            items.append(
                Article(
                    title=link.get_text(" ", strip=True),
                    url=link.get("href", ""),
                    date="",
                    lede=lede.get_text(" ", strip=True) if lede else "",
                    source=name,
                )
            )
        if items:
            results.append(CollectorResult(source_name=name, items=items))

    summary = summarize(results)
    if summary is None:
        print("요약 없음 (키 미설정 또는 호출 실패)")
        return 1
    print("▶ 오늘의 핵심")
    for point in summary["points"]:
        print(f"  - {point}")
    print(f"▶ 키워드: {', '.join(summary['keywords'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
