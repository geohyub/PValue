"""KHOA (Korea Hydrographic and Oceanographic Agency) API client.

Fetches ocean observation buoy data from data.go.kr (공공데이터포털).
Uses the GetTWRecentApiService endpoint for wave height + wind speed.  [26개소]

Notes / 제한사항:
- 관측 간격: 5~10분 (관측소마다 다름) — API에서 인터벌 변경 불가
- Hs 정밀도: 소수점 1자리 (P값 차이 ~1% 이내, 검증 완료)
  고정밀(소수 2자리) 데이터가 필요하면 KHOA 홈페이지에서 CSV 직접 다운로드 권장
- 항만 관측소 (평택당진항, 군산항, 인천항 등): Hs/Wind 미제공
- 하루 단위 조회: reqDate 파라미터로 하루씩 호출 (장기간 시 느림)
- 인증키: data.go.kr에서 무료 발급
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

import json
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE = "https://apis.data.go.kr/1192136/twRecent/GetTWRecentApiService"

# Max rows per API call (one day = 144 records at 10-min interval)
_ROWS_PER_DAY = 144

# KHOA ocean observation buoy stations (해양관측부이)
KHOA_STATIONS: Dict[str, str] = {
    "TW_0062": "해운대해수욕장",
    "TW_0069": "대천해수욕장",
    "TW_0070": "평택당진항",
    "TW_0072": "군산항",
    "TW_0074": "광양항",
    "TW_0075": "중문해수욕장",
    "TW_0076": "인천항",
    "TW_0077": "경인항",
    "TW_0078": "완도항",
    "TW_0079": "상왕등도",
    "TW_0080": "우이도",
    "TW_0081": "생일도",
    "TW_0082": "태안항",
    "TW_0083": "여수항",
    "TW_0084": "통영항",
    "TW_0085": "마산항",
    "TW_0086": "부산항신항",
    "TW_0087": "부산항",
    "TW_0088": "감천항",
    "TW_0089": "경포대해수욕장",
    "TW_0090": "송정해수욕장",
    "TW_0091": "낙산해수욕장",
    "TW_0092": "임랑해수욕장",
    "TW_0093": "속초해수욕장",
    "TW_0094": "망상해수욕장",
    "TW_0095": "고래불해수욕장",
}


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _fetch_json(url: str, timeout: int = 30) -> dict:
    """Fetch a URL and return parsed JSON."""
    try:
        with urlopen(url, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8"))
    except HTTPError as e:
        if e.code == 403:
            raise PermissionError(
                "API 접근이 거부되었습니다 (403). "
                "공공데이터포털에서 해당 API 활용신청이 필요합니다."
            ) from e
        raise ConnectionError(f"HTTP {e.code}: {e.reason}") from e
    except URLError as e:
        raise ConnectionError(f"네트워크 오류: {e.reason}") from e


def _parse_items(items: list) -> pd.DataFrame:
    """Parse API response items into a DataFrame with Hs and Wind columns."""
    rows = []
    for item in items:
        try:
            dt = datetime.strptime(item["obsrvnDt"], "%Y-%m-%d %H:%M")
        except (ValueError, KeyError):
            continue

        hs = item.get("wvhgt")
        wind = item.get("wspd")

        if hs is not None:
            hs = float(hs) if hs != "" else float("nan")
        else:
            hs = float("nan")

        if wind is not None:
            wind = float(wind) if wind != "" else float("nan")
        else:
            wind = float("nan")

        rows.append({"timestamp": dt, "Hs": hs, "Wind": wind})

    if not rows:
        raise ValueError("API 응답에서 유효한 데이터를 찾을 수 없습니다.")

    df = pd.DataFrame(rows)
    df = df.set_index("timestamp").sort_index()
    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_station_label(obs_code: str) -> str:
    """Return display label like '우이도 (TW_0080)'."""
    name = KHOA_STATIONS.get(obs_code, obs_code)
    return f"{name} ({obs_code})"


def fetch_timeseries(
    service_key: str,
    obs_code: str,
    start: datetime,
    end: datetime,
    progress_callback: Optional[callable] = None,
) -> pd.DataFrame:
    """Fetch observation time series from KHOA API (data.go.kr).

    Parameters
    ----------
    service_key : str
        data.go.kr service key (공공데이터포털 인증키).
    obs_code : str
        Station code (e.g. "TW_0080" for 우이도).
    start, end : datetime
        Query period.
    progress_callback : callable, optional
        Called with (current_day, total_days) for progress reporting.

    Returns
    -------
    pd.DataFrame
        DataFrame with DatetimeIndex and columns 'Hs' (m) and 'Wind' (m/s).
        Note: Hs precision is limited to 1 decimal place by the API.
    """
    if not service_key or not service_key.strip():
        raise ValueError("API 인증키가 필요합니다.")
    if obs_code not in KHOA_STATIONS:
        raise ValueError(f"알 수 없는 관측소 코드: {obs_code}")
    if end <= start:
        raise ValueError("종료일이 시작일보다 뒤여야 합니다.")

    # API queries one day at a time (reqDate=YYYYMMDD)
    days: List[datetime] = []
    cur = start
    while cur.date() <= end.date():
        days.append(cur)
        cur += timedelta(days=1)

    frames: List[pd.DataFrame] = []
    for i, day in enumerate(days):
        if progress_callback:
            progress_callback(i + 1, len(days))

        req_date = day.strftime("%Y%m%d")
        url = (
            f"{_BASE}"
            f"?serviceKey={quote(service_key, safe='')}"
            f"&obsCode={obs_code}"
            f"&reqDate={req_date}"
            f"&type=json"
            f"&numOfRows={_ROWS_PER_DAY}"
            f"&pageNo=1"
        )

        try:
            data = _fetch_json(url)
        except ConnectionError:
            continue

        result_code = data.get("header", {}).get("resultCode", "")
        if result_code != "00":
            continue

        items_wrapper = data.get("body", {}).get("items", {})
        items = items_wrapper.get("item", [])
        if not items:
            continue

        try:
            chunk_df = _parse_items(items)
            frames.append(chunk_df)
        except ValueError:
            continue

    if not frames:
        label = get_station_label(obs_code)
        raise ValueError(
            f"선택한 기간({start.date()} ~ {end.date()})에 "
            f"관측소 {label}의 데이터가 없습니다."
        )

    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="first")].sort_index()

    # Trim to requested range
    df = df[(df.index >= start) & (df.index <= end)]
    return df
