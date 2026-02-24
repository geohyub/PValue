# Marine P-Value Simulator

해양/해상 작업 캠페인의 실현 가능성을 기상 조건 하에서 분석하는 Monte Carlo 시뮬레이션 도구입니다.

과거 메토시안 데이터(파고 Hs, 풍속 Wind)를 기반으로 작업 캠페인 완료에 필요한 **백분위 기반 소요일수**(P50, P75, P90 등)를 산출하여 해상 작업 일정 수립 시 기상 리스크를 정량화합니다.

## Features

| 기능 | 설명 |
|------|------|
| **Monte Carlo 엔진** | 1,000~50,000회 랜덤 캠페인 시뮬레이션 |
| **2가지 작업 모드** | Continuous (연속 기상창) / Split (누적 작업시간) |
| **ERA5 Hindcast 지원** | ERA5 30년 재분석 CSV 자동 파싱 |
| **최적 시작월 분석** | 12개월 비교로 P90 최소 월 탐색 |
| **배치 비교** | 다수 사이트 동시 분석·비교 |
| **Desktop GUI (PyQt6)** | 단계별 가이드, 툴팁, 탭 잠금, 결과 해석 |
| **Web GUI (Streamlit)** | 브라우저 대시보드 + Plotly 차트 |
| **CLI (Click)** | 커맨드라인 인터페이스 |
| **오프라인 .exe** | PyInstaller로 Windows 배포용 단독 실행파일 |
| **Excel 리포트** | 요약·결과·작업정보 포함 `.xlsx` 자동 생성 |

## Quick Start

### 설치

```bash
pip install -e ".[all]"
```

필요한 것만 선택 설치:

```bash
pip install -e .              # 코어 (CLI만)
pip install -e ".[desktop]"   # + PyQt6 데스크톱 GUI
pip install -e ".[gui]"       # + Streamlit 웹 GUI
pip install -e ".[excel]"     # + Excel 리포트 생성
pip install -e ".[dev]"       # + pytest 테스트
```

### Desktop GUI (권장)

```bash
pvalue-desktop
# 또는:
python -m pvalue.desktop
```

**주요 기능:**

- **단계별 워크플로** — 탭이 순차적으로 활성화 (Data → Config → Run → Results → Charts)
- **Load Example 버튼** — 내장 예제 데이터+설정으로 즉시 체험
- **JSON Import/Export** — 설정 파일 불러오기 시 모든 항목 자동 반영 (시작월, 작업시간, 스플릿 모드, NA 처리, 시드 등)
- **모든 위젯에 툴팁** — 마우스 호버로 상세 설명 확인
- **결과 해석 패널** — P50/P90 값을 일반 언어로 설명
- **차트** — 히스토그램, CDF, Work/Wait Scatter, Timeline (Top 5)

### Web GUI

```bash
pvalue gui
# 또는 직접:
streamlit run pvalue/app.py
```

Windows에서는 **`run_web_gui.bat`** 더블클릭으로 실행 가능합니다.

### CLI

```bash
# 단일 파일 분석
pvalue run data.csv -c config.json -o ./results

# 배치 분석 (다수 사이트)
pvalue batch site_a.csv site_b.csv -c config.json -o ./batch_results

# 최적 시작월 분석
pvalue optimal-month data.csv -c config.json

# CSV 검증만 수행
pvalue validate data.csv --csv-type hindcast
```

### Python API

```python
from pvalue import load_csv, validate_metocean, Task, simulate_campaign, summarize_pxx

df = load_csv("metocean.csv")
ok, msg = validate_metocean(df)

tasks = [
    Task("Installation", duration_h=48, thresholds={"Hs": 1.5, "Wind": 10}),
]

results = simulate_campaign(df, tasks, n_sims=2000, start_month=4, seed=7)
summary = summarize_pxx(results, p_list=[50, 75, 90])
print(summary)
```

## 오프라인 .exe 빌드 (Windows)

```bash
# 1. 클린 빌드 환경 생성
python -m venv .build_venv
.build_venv\Scripts\activate
pip install -e ".[desktop,excel,build]"

# 2. 빌드 실행
python build_exe.py
```

빌드 결과: `dist/PValueSimulator/` 폴더 전체 배포 (`PValueSimulator.exe` + `_internal` 폴더 모두 필요)

> 빌드 시 tensorflow, torch 등 불필요한 대형 패키지는 자동 제외됩니다.

## JSON 설정 파일

작업 정의 및 시뮬레이션 설정을 JSON으로 관리합니다.

### 전체 설정 예시

```json
{
  "tasks": [
    {
      "name": "BH01",
      "duration_h": 48,
      "thresholds": {"Hs": 1.2, "Wind": 10.0},
      "setup_h": 0,
      "teardown_h": 0
    },
    {
      "name": "BH02",
      "duration_h": 48,
      "thresholds": {"Hs": 1.2, "Wind": 10.0},
      "setup_h": 0,
      "teardown_h": 0
    }
  ],
  "n_sims": 2000,
  "pvals": [60, 70, 80, 90, 100],
  "split_mode": false,
  "na_handling": "permissive",
  "start_month": 4,
  "seed": 7,
  "calendar": ["all", "Asia/Seoul", "7-19"]
}
```

### 필드 설명

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `tasks` | array | (필수) | 작업 목록 (순서대로 실행) |
| `tasks[].name` | string | (필수) | 작업명 |
| `tasks[].duration_h` | int | (필수) | 순수 작업시간 (시간) |
| `tasks[].thresholds` | object | (필수) | 기상 제한 — `Hs` (파고 m), `Wind` (풍속 m/s) |
| `tasks[].setup_h` | int | `0` | 사전 준비시간 (시간) |
| `tasks[].teardown_h` | int | `0` | 사후 정리시간 (시간) |
| `n_sims` | int | `1000` | Monte Carlo 반복 횟수 |
| `pvals` | array | `[50,75,90]` | 산출할 백분위 (0~100) |
| `split_mode` | bool | `false` | `false`: 연속 기상창 필요, `true`: 누적 작업시간 |
| `na_handling` | string | `"permissive"` | `"permissive"`: 결측=작업가능, `"conservative"`: 결측=작업불가 |
| `start_month` | int/null | `null` | 시뮬레이션 시작 월 제한 (1~12), `null`이면 전체 |
| `seed` | int | `7` | 난수 시드 (재현성 보장) |
| `calendar` | array | `["all"]` | `["all"]`: 24시간, `["custom", "TZ", "7-19"]`: 업무시간 제한 |

### JSON Import/Export (GUI)

Desktop GUI의 **Import JSON** 버튼으로 설정 파일을 불러오면 다음 항목이 모두 GUI에 자동 반영됩니다:

- `tasks` → 작업 테이블
- `n_sims`, `pvals`, `seed` → 시뮬레이션 설정
- `start_month` → 시작 월 체크박스 + 콤보박스
- `split_mode` → Continuous/Split 라디오 버튼
- `na_handling` → Permissive/Conservative 라디오 버튼
- `calendar` → Business hours 체크박스 + 시작/종료 시간

**Export JSON** 시에도 모든 설정이 동일 형식으로 저장됩니다.

## CSV 형식

### General CSV

`timestamp`, `Hs`, `Wind` 컬럼이 포함된 표준 CSV:

```csv
timestamp,Hs,Wind
2020-01-01 00:00:00,1.2,8.5
2020-01-01 00:10:00,1.3,9.1
2020-01-01 00:20:00,1.2,8.8
```

- 시간 간격 자동 감지 (10분, 1시간 등)
- 인코딩 자동 감지 (UTF-8, CP949, EUC-KR)

### Hindcast CSV (ERA5)

5줄 메타데이터 헤더가 있는 ERA5 형식. Wind/Hs 컬럼명 자동 인식 (패턴 매칭).

## 프로젝트 구조

```
PValue/
├── pvalue/                     # 메인 패키지
│   ├── __init__.py             # 공개 API + 버전
│   ├── __main__.py             # python -m pvalue
│   ├── models.py               # Task, SimulationConfig 데이터클래스
│   ├── data.py                 # CSV 로드, 검증, 조건 마스크
│   ├── simulation.py           # Monte Carlo 엔진
│   ├── analysis.py             # 고수준 워크플로 (배치, 최적월)
│   ├── visualization.py        # Matplotlib 차트 함수
│   ├── reporting.py            # Excel 리포트 생성
│   ├── cli.py                  # Click CLI
│   ├── app.py                  # Streamlit 웹 GUI
│   ├── desktop.py              # PyQt6 진입점
│   └── gui/                    # Desktop GUI 컴포넌트
│       ├── main_window.py      #   메인 윈도우 + 탭 관리 + 탭 잠금
│       ├── tabs.py             #   탭 페이지 (Data, Config, Run, Results, Charts, Optimal)
│       ├── widgets.py          #   재사용 위젯 (ChartWidget, SummaryTable, TaskTable)
│       └── workers.py          #   QThread 워커 (백그라운드 시뮬레이션)
├── tests/                      # 단위 테스트 (38개)
│   ├── test_models.py
│   ├── test_data.py
│   └── test_simulation.py
├── examples/                   # 예제 데이터 & 설정
│   ├── sample_metocean.csv     #   예제 메토시안 CSV (10일, 1시간 간격)
│   ├── sample_config.json      #   단일 실행 설정 템플릿
│   └── batch_config.json       #   배치 실행 설정 템플릿
├── build_exe.py                # PyInstaller 빌드 스크립트
├── build.spec                  # PyInstaller spec 파일
├── run_web_gui.bat             # Windows Streamlit 실행 배치파일
├── pyproject.toml              # 프로젝트 메타데이터 & 빌드 설정
├── requirements.txt            # 코어 의존성
├── P_Value_Program.py          # 레거시 단일 파일 (참고용)
└── README.md
```

## 개발

```bash
# 개발 의존성 포함 설치
pip install -e ".[dev]"

# 테스트 실행
pytest

# 커버리지 포함 테스트
pytest --cov=pvalue
```

## 검증

리팩토링된 `pvalue` 패키지는 원본 `P_Value_Program.py`와 동일 데이터·설정·시드(7) 조건에서 **모든 P값 출력이 소수점 4자리까지 완전 일치**함을 검증하였습니다.

| 지표 | 원본 | 리팩토링 | 차이 |
|------|------|----------|------|
| P60 | 40.1111일 | 40.1111일 | 0.0000 |
| P70 | 41.7868일 | 41.7868일 | 0.0000 |
| P80 | 42.6875일 | 42.6875일 | 0.0000 |
| P90 | 43.7500일 | 43.7500일 | 0.0000 |
| P100 | 45.5903일 | 45.5903일 | 0.0000 |

검증 데이터: 우이도 2504-2507 (10분 간격, 17,488 레코드), 10개 태스크, 2,000회 시뮬레이션

## License

MIT
