# 금융 지표 14종 확장 및 30년 역사 대시보드 + '30분만에 읽기' 방송 기사 연동 구축 계획서

본 계획서는 `fin-news-collector` 프로그램의 시장 지수 수집 범위를 14가지 핵심 거시경제 지표로 확대하고, 과거 30년 장기 시계열 데이터를 효율적으로 저장·관리하며, 사용자 리포트 화면(HTML) 내에서 인터랙티브 차트 모달을 통해 이를 시각화하고, **유튜브 방송(한경코리아마켓의 한국경제신문 30분만에 읽기)에 소개되는 매일 아침 추천 기사들을 자동으로 선별 수집**하기 위한 아키텍처 설계와 구현 마일스톤을 기술합니다.

---

## 1. 수집 대상 지표 (14종) 및 데이터 소스 정의

각 지표는 `yfinance`에서 과거 데이터를 직접 가져오거나, 한국 국채 금리와 같이 yfinance에 없는 지표는 국내 금융 포털(네이버페이 증권)을 스크래핑하여 보완합니다.

| 번호 | 지표명 | 수집 구분 | yfinance 티커 / 스크래핑 URL | 상세 설명 |
| :--- | :--- | :--- | :--- | :--- |
| **1** | 코스피 (KOSPI) | yfinance | `^KS11` | 한국 종합주가지수 |
| **2** | 코스닥 (KOSDAQ) | yfinance | `^KQ11` | 한국 코스닥지수 |
| **3** | 다우존스 (Dow Jones) | yfinance | `^DJI` | 미국 다우존스 산업평균지수 |
| **4** | S&P 500 | yfinance | `^GSPC` | 미국 S&P 500 지수 |
| **5** | 나스닥 (NASDAQ) | yfinance | `^IXIC` | 미국 나스닥 종합지수 |
| **6** | 한국 국채 3년물 | 스크래핑 | `https://finance.naver.com/marketindex/interestDetail.naver?code=IRR_GOVT03Y` | 한국 국고채 3년물 최종호가수익률 |
| **7** | 한국 국채 10년물 | 스크래핑 | `https://finance.naver.com/marketindex/interestDetail.naver?code=IRR_GOVT10Y` | 한국 국고채 10년물 최종호가수익률 |
| **8** | 미국 국채 10년물 | yfinance | `^TNX` | 미국 국채 10년물 수익률 (10 Year Treasury Yield) |
| **9** | 미국 국채 30년물 | yfinance | `^TYX` | 미국 국채 30년물 수익률 (30 Year Treasury Yield) |
| **10** | 달러 인덱스 (Dollar Index) | yfinance | `DX-Y.NYB` | 주요 통화 대비 달러화 가치 지수 |
| **11** | WTI 원유 선물 | yfinance | `CL=F` | 서부 텍사스산 원유 선물 가격 |
| **12** | 달러/원 환율 (USD/KRW) | yfinance | `USDKRW=X` | 1달러당 원화 가격 |
| **13** | 달러/엔 환율 (USD/JPY) | yfinance | `USDJPY=X` | 1달러당 엔화 가격 |
| **14** | 유로/달러 환율 (EUR/USD) | yfinance | `EURUSD=X` | 1유로당 달러 가격 |

---

## 2. 유튜브 '한국경제신문 30분만에 읽기' 추천 기사 연동 설계

유튜브 방송 "한경코리아마켓 - 한국경제신문 30분만에 읽기(모닝루틴)" 영상에서 엄선하여 소개해주는 기사들은 한국경제 모닝루틴 공식 웹 페이지에 **"모닝루틴 Pick! 오늘의 기사"**로 매일 매치되어 업로드됩니다. 

기존의 경제 카테고리 전체 RSS 피드 수집 방식을 버리고, **이 모닝루틴 웹페이지를 타겟으로 크롤링을 수행**하여 방송에서 실제 브리핑한 기사만 정확하게 리포트에 담아냅니다.

### 2.1 스크래핑 아키텍처 (코드 수정 최소화 설계)
기존 프로젝트의 `WebScraperCollector`는 이미 범용 HTML/CSS 셀렉터 파싱이 가능하도록 설계되어 있습니다. 따라서 별도의 파이썬 코드 개발 없이 **`sources.yaml` 설정값 교체**만으로 해당 방송 추천 기사들을 완벽하게 수집할 수 있습니다.

* **수집 대상 URL**: `https://www.hankyung.com/mr` (한경 모닝루틴 공식 페이지)
* **CSS 셀렉터 매핑 정의**:
  - 목록 컨테이너 (`list_container`): `div.aside-news-module div.news-list`
  - 개별 기사 아이템 (`item`): `div.news-item`
  - 기사 제목 (`title`): `h3.news-tit a`
  - 기사 링크 (`link`): `h3.news-tit a`
  - 발행 날짜 (`date`): `span.date`
  - 상세문 파싱 (`lede_url`): `true` (기존 상세 페이지 크롤러를 통해 각 기사의 본문 요약을 채워줌)

### 2.2 sources.yaml 설정 변경 (구현 내용)
`sources.yaml` 파일 내 "한국경제" 섹션을 아래와 같이 업데이트합니다.

```yaml
  - name: "한국경제"
    enabled: true
    url: "https://www.hankyung.com/mr"
    type: "articles"
    parser: "html.parser"
    selectors:
      list_container: "div.aside-news-module div.news-list"
      item: "div.news-item"
      title: "h3.news-tit a"
      link: "h3.news-tit a"
      date: "span.date"
      lede_url: true
    max_items: 10
    encoding: "utf-8"
```

---

## 3. 데이터 아키텍처 및 저장 방식 (CSV 캐싱 & 증분 수집)

매일 전체 30년 데이터를 외부 네트워크를 통해 수집할 경우 병목 및 API 제한(Rate Limit)이 발생합니다. 이를 방지하고자 **로컬 CSV 캐시** 기반의 **증분 수집(Incremental Update)**을 구현합니다.

```mermaid
flowchart TD
    Start([프로그램 시작]) --> LoadConfig[sources.yaml 설정 로드]
    LoadConfig --> CheckCache{로컬 CSV 캐시가 존재하는가?}
    
    CheckCache -- "아니오 (최초 실행)" --> InitCollect["과거 데이터 초기 수집 (Bootstrap)
    - yfinance: 30년치 수집 (period='max')
    - 한국 국채: 네이버 스크래핑으로 수집 가능한 최대 기간 수집"]
    InitCollect --> SaveCache[data/history/{ticker}.csv 파일로 저장]
    
    CheckCache -- "예 (기존 파일 존재)" --> ReadLastDate[CSV 파일의 마지막 기록 날짜 파악]
    ReadLastDate --> CollectToday["당일(혹은 누락 기간) 신규 데이터 수집"]
    CollectToday --> AppendCache[기존 CSV 파일 끝에 누락 행 추가]
    
    SaveCache --> PrepareData[렌더링용 차트 데이터 가공]
    AppendCache --> PrepareData
    
    PrepareData --> Downsample["과거 30년 시계열 데이터 다운샘플링 (주간/월간 종가 추출)
    - HTML 파일 크기 최적화 목적"]
    Downsample --> Render[daily.html.j2 템플릿에 JSON 변수로 주입 및 생성]
    Render --> End([종료 및 브라우저 열기])
```

### 3.1 디렉토리 경로
* 캐시 저장 폴더: [data/history/](file:///Volumes/SK_2TB/CODING/PROGRAM/그냥작어업/harness%20practice/fin-news-collector/data/history/) (자동 생성)
* 캐시 파일명: `^KS11.csv`, `USDKRW=X.csv`, `KR_BOND_3Y.csv` 등 티커 및 지표 식별자 기반 매핑

### 3.2 수집 로직 세부 설계
1. **yfinance 수집**:
   - 최초 수집: `history(period="max")` 또는 `history(start="1996-01-01")`를 호출하여 수집 가능한 30년 데이터를 CSV로 저장합니다.
   - 증분 수집: 마지막 저장일이 `2026-06-11`이라면, `history(start="2026-06-11")`을 통해 누락 기간만 가져와 CSV 파일 하단에 `append`합니다.
2. **한국 국채 스크래핑**:
   - 네이버페이 증권 상세 페이지(HTML) 내의 일별 시세 표 또는 API 엔드포인트를 크롤링하여 최근 수년 치 일별 데이터를 일차적으로 확보합니다.
   - 매일 실행 시 당일 고시된 금리(수치) 및 날짜를 스크래핑하여 CSV 파일 끝에 누락분을 기록합니다.

### 3.3 렌더링 성능 최적화 (다운샘플링)
* 30년 일별 데이터는 지표당 약 7,500개의 데이터 포인트를 가집니다. 14종을 합치면 약 10만 개가 넘어, HTML 리포트에 원본을 그대로 하드코딩하면 파일 크기가 수십 메가바이트(MB)로 비대해집니다.
* **대안**: 30년 장기 추이를 확인하는 차트의 특성상 일별 변화 대신 **월간 종가(Monthly Close)** 또는 **주간 종가(Weekly Close)** 데이터만 필터링하여 다운샘플링합니다.
* 30년 기준 월간 종가는 지표당 단 **360개**의 데이터 포인트로 압축되어 HTML 리포트의 가독성과 로딩 속도를 대폭 개선할 수 있습니다.

---

## 4. 대시보드 및 차트 프론트엔드 UI/UX 설계

새로워진 금융 리포트 화면은 14종 지표의 가독성을 높이고, 클릭 시 즉시 30년 데이터를 시각화하는 인터랙티브 모달 시스템을 채택합니다.

### 4.1 메인 대시보드 개선
* **CSS Grid 레이아웃**: 
  기존 4개 카드 구조에서 14개 카드로 늘어남에 따라, 화면 해상도에 맞게 자동으로 컬럼 수가 늘어나는 그리드 레이아웃을 사용합니다.
  ```css
  .indices {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
  }
  ```
* **프리미엄 피드백 효과**:
  - 마우스 호버 시 마우스 포인터가 손가락(`cursor: pointer`) 모양으로 변경됩니다.
  - 카드가 부드럽게 위로 뜨는 3D 카드 리프트 애니메이션 및 섀도우 블러 처리를 적용합니다.
  - 클릭 가능함을 명시하는 마이크로 배지("차트 보기 📊")를 카드 모서리에 배치합니다.

### 4.2 차트 모달 (SPA 구조)
* **JS 차트 라이브러리 탑재**:
  외부 파일 없이 단일 HTML 리포트가 정상 동작하도록 CDN을 통해 [ApexCharts](https://apexcharts.com/) 또는 [Chart.js](https://www.chartjs.org/)를 로드합니다. ApexCharts는 모바일 친화적이고 드래그 줌(Zoom) 기능이 기본 제공되어 장기 시계열 조회에 매우 적합합니다.
* **모달 윈도우(Modal Window)**:
  - 지표 카드 클릭 시 뒷배경이 어두워지며(`backdrop-filter: blur(4px)`) 중앙에 깔끔하고 모던한 유리 느낌(Glassmorphism)의 차트 창이 애니메이션과 함께 활성화됩니다.
  - 차트 내부에는 해당 지표의 30년 추이 꺾은선 그래프가 렌더링됩니다.
  - **기간 필터 기능**: 차트 상단에 `1년`, `5년`, `10년`, `30년 (전체)` 단축 버튼을 제공하여 선택한 기간으로 차트 X축 범위(Zoom)가 자동 줌인/줌아웃되도록 구현합니다.
  - **상세 툴팁**: 마우스 오버 시 정확한 날짜와 지수 수치(환율의 경우 원, 지수의 경우 포인트 등)를 툴팁 형태로 깔끔하게 표시합니다.

---

## 5. 상세 구현 마일스톤

| 단계 | 태스크 | 상세 작업 내용 | 예상 소요 |
| :--- | :--- | :--- | :--- |
| **1단계** | **한국경제 수집처 및 설정 변경** | - [sources.yaml](file:///Volumes/SK_2TB/CODING/PROGRAM/그냥작어업/harness%20practice/fin-news-collector/sources.yaml)의 "한국경제" 소스를 한경 모닝루틴 페이지(`https://www.hankyung.com/mr`)와 전용 셀렉터 세트로 변경<br>- 스크래퍼 실행 및 정상 수집 여부 테스트 | 0.5일 |
| **2단계** | **데이터 캐시 엔진 구축** | - [collectors/market_data.py](file:///Volumes/SK_2TB/CODING/PROGRAM/그냥작어업/harness%20practice/fin-news-collector/collectors/market_data.py)에 CSV 캐시 초기화 및 증분 업데이트 로직 구현<br>- 한국 국채 금리용 네이버 스크래퍼 신규 개발 | 1일 |
| **3단계** | **다운샘플링 & 데이터 파이프라인 연동** | - 수집 완료된 30년 CSV 데이터를 주간/월간 종가 기준으로 압축하는 다운샘플링 필터 추가<br>- 렌더러로 전달할 최종 데이터 스키마 가공 및 연동 | 0.5일 |
| **4단계** | **HTML 템플릿 UI 확장 및 차트 모달** | - 14종의 지수 카드 그리드 마크업 및 CSS 개선<br>- ApexCharts 라이브러리 로드 및 동적 차트 초기화 스크립트 구현<br>- 모달 레이아웃 및 팝업 효과 스타일링 | 1일 |
| **5단계** | **통합 테스트 및 디버깅** | - 최초 30년 수집 병목 체크 및 증분 스크래핑 작동 검증<br>- 모닝루틴 기사 수집의 안정성 및 이미지 노출 체크 | 0.5일 |

---

## 6. 승인 및 피드백 요청

본 계획에 동의하신다면 하단의 **[Proceed]** 버튼을 눌러 작업을 계속 진행할 수 있습니다. 수집 주기나 수집 원천의 추가 변경 사항이 필요하다면 언제든 알려주시기 바랍니다.
