# fin-news-collector

macOS에서 금융 뉴스와 리포트를 모아 HTML 데일리 리포트를 만드는 Python 프로젝트입니다.

## 기능

- 한국경제 기사 수집
- 연준 보고서 PDF 링크 수집
- KB금융 리서치 PDF 링크 수집
- 하나증권 유튜브 댓글의 고정 PDF 링크 수집
- KOSPI, KOSDAQ, S&P500, NASDAQ 지수 카드 생성
- 날짜별 PDF 저장 및 HTML 리포트 생성
- 하나증권 모닝브리프 최근 10일치 표시
- `data/`, `reports/` 의 10일 초과 산출물 자동 삭제
- 수집 실패 시 해당 섹션만 에러 표시

## 구조

```text
fin-news-collector/
├── run.py
├── sources.yaml
├── collectors/
├── reporter/
├── tests/
├── data/
├── reports/
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
- `hana_brief.channel_id`: 하나증권 공식 유튜브 채널 ID
- `hana_brief.max_videos`: 최근 몇 개 영상까지 확인할지 설정
- `housekeeping.retention_days`: PDF/리포트 보관 일수
- `market_data.symbols`: 지수 티커 목록

새 웹/PDF 소스는 `web_sources` 에 항목을 추가하면 코드 수정 없이 섹션이 늘어납니다.

## 자동 실행

`launchd/com.user.finnews.plist` 의 경로 플레이스홀더를 실제 절대경로로 바꾼 뒤 `launchctl` 에 등록하면 됩니다.

## 테스트

```bash
python -m pytest tests/ -v
```
