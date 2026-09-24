"""한국어 텍스트에서 비교·검증용 단어를 뽑는 유틸.

형태소 분석기 없이 조사만 떼어낸다. 뉴스 제목처럼 짧고 명사 위주인
텍스트에는 이 정도로 충분하다.
"""
from __future__ import annotations

import re

# 긴 조사부터 검사해야 "으로"가 "로"로 잘리지 않는다.
_PARTICLES = (
    "으로써", "으로서", "에서는", "에게서", "이라고", "라는", "이라는", "에서", "에게",
    "으로", "로써", "까지", "부터", "보다", "처럼", "만큼", "이며", "이고", "인", "은",
    "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "로", "만", "나", "며",
)

# 비교에 의미 없는 말. 제목마다 흔히 나와서 아무 제목이나 비슷해 보이게 만든다.
_STOPWORDS = {
    "오늘", "이번", "지난", "관련", "대한", "위해", "통해", "따라", "대해", "가운데",
    "전망", "발표", "지적", "강조", "나타", "밝혔", "있다", "했다", "된다", "기자",
}


def content_tokens(text: str) -> list[str]:
    """비교 대상 단어만 뽑는다(조사·기호·불용어 제거)."""
    tokens = []
    # 숫자와 기호를 따로 떼어낸다. "2.6%→3.7%"가 한 덩어리로 남으면
    # 같은 수치를 쓴 두 제목이 전혀 다른 것으로 취급된다.
    for chunk in re.split(r"[\s,·…·、。\"'()\[\]{}<>~\-—%→↑↓▲▼/|=+*:;!?]+", text):
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


