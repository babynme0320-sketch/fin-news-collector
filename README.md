# fin-news-collector

macOS에서 금융 뉴스와 리포트를 모아 HTML 데일리 리포트를 만드는 Python 프로젝트입니다.

## 기능

- 한국경제 기사 수집 (금융·마켓 / 경제 / 사설 — 섹션 HTML 페이지)
- 오늘의 핵심 요약 (헤드라인을 LLM으로 5줄 요약 + 키워드)
- 지난 리포트 아카이브 (`reports/archive/` → `docs/archive/`, 영구 보관)
- 텔레그램 알림 (하루 1회 브리핑 + 속보 즉시)
- FOMC 성명서·의사록·경제전망(SEP) PDF 수집
- 미래에셋·KB금융 리서치 PDF 링크 수집
- 하나증권 유튜브 댓글의 고정 PDF 링크 수집
- KOSPI, KOSDAQ, S&P500, NASDAQ 등 지수·금리·환율 14종 카드 생성
- 미국 기준금리·근원 CPI·비농업 고용 (FRED, 키 불필요)
- 날짜별 PDF 저장 및 HTML 리포트 생성
- 하나증권 모닝브리프 최근 10일치 표시
- `data/`, `reports/` 의 10일 초과 산출물 자동 삭제
- 수집 실패 시 해당 섹션만 에러 표시 (일부만 실패하면 남은 항목은 그대로 표시)

## 구조

```text
fin-news-collector/
├── run.py
├── sources.yaml
├── summarizer.py            # 오늘의 핵심 요약 (생성 + 근거 검증)
├── notifier.py              # 텔레그램 알림 (하루 1회 브리핑 + 속보)
├── validate_collectors.py   # 전체 소스 수집 검증 (0건/오류 시 exit 1)
├── collectors/
├── reporter/
│   └── archive.py           # 지난 리포트 보관 + 목록 생성
├── tests/
├── data/
├── reports/
│   └── archive/             # 날짜별 리포트 (발행 시 docs/archive 로 복사)
└── launchd/
```

## 설치

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 실행

```bash
python run.py
```

실행이 끝나면 `reports/report_YYYYMMDD.html` 이 생성되고 기본 브라우저가 열립니다.

## 설정

### `sources.yaml`

- `web_sources`: HTML/PDF 기반 소스 목록
- `interest_keywords`: 제목에 들어가면 "⭐ 관심" 섹션으로 모을 키워드
- `summary`: 오늘의 핵심 요약 (모델·헤드라인 수·문장 수)
- `notify`: 텔레그램 알림 (활성화 여부·발송 시각·리포트 URL)
- `fomc.include`: FOMC에서 가져올 문서 종류 (`statement` / `minutes` / `projections`)
- `hana_brief.channel_id`: 하나증권 공식 유튜브 채널 ID
- `hana_brief.max_videos`: 최근 몇 개 영상까지 확인할지 설정
- `housekeeping.retention_days`: PDF/리포트 보관 일수
- `market_data.symbols`: 지수 티커 목록

새 웹/PDF 소스는 `web_sources` 에 항목을 추가하면 코드 수정 없이 섹션이 늘어납니다.

한국경제는 RSS(`/feed/*`)가 Cloudflare 챌린지로 403을 반환해 섹션 HTML 페이지를 긁습니다.
목록에 날짜가 없는 기사는 기사 URL의 `YYYYMMDD`로 날짜를 복원하므로 셀렉터가 비어도 날짜는 맞습니다.

## 소스 추가 시 알아둘 것

`web_sources`에 항목을 넣으면 코드 수정 없이 섹션이 늘어납니다. 다만 사이트마다 걸리는 함정이 있어 옵션을 몇 가지 뒀습니다.

| 옵션 | 쓰는 곳 | 이유 |
| :--- | :--- | :--- |
| `FRED:시리즈ID` | 국고채 10년 | FRED에서 키 없이 가져온다. 티커에 이 접두사가 있으면 `collectors/fred.py`를 탄다 |
| `encoding` | 미래에셋 (EUC-KR) | 없으면 제목이 깨진다 |
| `link_pattern` | 미래에셋 | href가 `javascript:downConfirm('https://…')` 형태라 안에서 URL만 뽑아야 한다 |
| `lede_url` | 한국경제 | 목록에 요약이 없어 기사 페이지의 `og:description`을 가져온다 |
| `inspect_article_section` | (구) 한경 RSS | 기사별 섹션 판정 — 요청이 배로 늘어 되도록 쓰지 않는다 |

JS로만 렌더되는 사이트(네이버 금융 신규 페이지, 삼성증권 등)는 정적 요청으로는 불가능합니다.

### 멈춘 지표 표시

값이 오래된 지표는 카드를 흐리게 하고 "⚠️ YYYY-MM-DD 기준 (N일 전)"을 붙입니다.
경고 기준은 **지표 주기에서 자동 계산**합니다(관측 간격 중앙값 × 3). 일간 지표에 3일,
월간 지표에 90일이 적용되는 식입니다 — 월간 지표에 3일 기준을 쓰면 정상인데도 경고가
늘 켜져 있어 아무도 안 보게 됩니다.

이 장치가 실제로 잡아낸 것: 국고채 3년이 2026-09-17에 멈춰 있었는데(네이버 소스가 410을
반환) 캐시된 값이 몇 주째 현재값처럼 표시되고 있었습니다. 지금은 FRED로 교체했습니다.

## 오늘의 핵심 요약

수집된 헤드라인을 LLM에 넘겨 5줄 요약과 키워드를 받아 리포트 최상단에 넣습니다.
DEEPSEEK_API_KEY 환경변수나 `~/.deepseek_key` 파일이 필요하고, 없으면 요약 없이 리포트만 생성됩니다.

모델이 헤드라인에 없는 내용을 지어내는 문제가 실제로 확인돼(없는 인물·없는 금리 인상),
생성된 문장을 수집 텍스트와 대조해 근거 없는 문장은 버립니다(`summarizer._is_grounded`).
숫자가 하나라도 근거에 없으면 그 문장은 탈락합니다. 근거 있는 문장이 3개 미만이면 요약을 넣지 않습니다.

```bash
python summarizer.py reports/report_YYYYMMDD.html   # 요약만 확인
```

## 알림 (텔레그램)

`notify.enabled: true`로 바꾸고 자격증명을 넣으면 동작합니다. 없으면 조용히 건너뜁니다.

1. 텔레그램에서 `@BotFather`로 봇을 만들고 토큰을 받습니다.
2. 봇과 대화를 시작한 뒤 `https://api.telegram.org/bot<토큰>/getUpdates`에서 chat id를 확인합니다.
3. 환경변수로 넣습니다 — 로컬은 셸 프로필, CI는 GitHub Secrets(`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).

| 알림 | 시점 |
| :--- | :--- |
| 하루 1회 브리핑 | `daily_after_hour`(기본 06 KST) 이후 첫 실행. 요약 + 변동 큰 지수 + 링크 |
| 속보 | `[속보]` 기사가 새로 잡히면 즉시. 같은 기사는 다시 보내지 않음 |

발송 이력은 `data/notify_state.json`에 남고, CI에서는 캐시로 보존됩니다(없으면 실행마다 다시 보냅니다).

## 수집 검증

```bash
python validate_collectors.py
```

활성화된 모든 소스를 실제로 수집해 0건이거나 오류가 있으면 exit 1로 끝납니다.
리포트는 섹션이 비어도 워크플로가 성공으로 끝나기 때문에, 조용한 수집 실패를 잡는 용도입니다.
(`.github/workflows/validate-collectors.yml` 이 매일 11:37 KST에 실행)

## 자동 실행

`launchd/com.user.finnews.plist` 의 경로 플레이스홀더를 실제 절대경로로 바꾼 뒤 `launchctl` 에 등록하면 됩니다.

## 테스트

```bash
python -m pytest tests/ -v
```
