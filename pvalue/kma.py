"""KMA (Korea Meteorological Administration) API client for fetching ocean observation data.

Supports three observation types:
- 해양기상부이 (Ocean Weather Buoy) — kma_buoy2.php  [44개소]
- 등표기상관측 (Lighthouse Weather Obs) — kma_lhaws2.php  [9개소]
- 기상1호/2000호 (Weather Ship) — kma_kship.php  [2개소]

Notes / 제한사항:
- 관측 간격: 부이 30분 (일부 신규 10분), 등표 1분, 선박 가변 — API에서 인터벌 변경 불가
- Hs 정밀도: 소수점 1자리 (P값 차이 ~1% 이내, 검증 완료)
- 등표: Wind만 제공, Hs(파고) 미제공 — Wind 단독 분석 시에만 사용 가능
- 선박(기상1호): 운항 기간에만 데이터 존재
- 비정상값 필터: Hs > 30m 또는 Wind > 80m/s 값은 자동 NaN 처리
- 인증키: apihub.kma.go.kr에서 무료 발급, API별 활용신청 필요
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE = "https://apihub.kma.go.kr"

# Station types and their API endpoints (period query)
STATION_TYPES = {
    "buoy": {
        "label": "해양기상부이",
        "endpoint": "/api/typ01/url/kma_buoy2.php",
    },
    "lighthouse": {
        "label": "등표기상관측",
        "endpoint": "/api/typ01/url/kma_lhaws2.php",
    },
    "ship": {
        "label": "기상1호/2000호",
        "endpoint": "/api/typ01/url/kma_kship.php",
    },
}

# Buoy stations (33 sites) — source: getBuoyLstTbl API
BUOY_STATIONS: Dict[str, str] = {
    "21229": "울릉도",
    "22101": "덕적도",
    "22102": "칠발도",
    "22103": "거문도",
    "22104": "거제도",
    "22105": "동해",
    "22106": "포항",
    "22107": "마라도",
    "22108": "외연도",
    "22183": "신안",
    "22184": "추자도",
    "22185": "인천",
    "22186": "부안",
    "22187": "서귀포",
    "22188": "통영",
    "22189": "울산",
    "22190": "울진",
    "22191": "서해170",
    "22192": "서해206",
    "22193": "서해163",
    "22297": "가거도",
    "22298": "홍도",
    "22300": "남해239",
    "22301": "남해465",
    "22302": "동해78",
    "22303": "풍도",
    "22304": "남해244",
    "22305": "동해57",
    "22306": "서해151",
    "22307": "서해143",
    "22308": "서해192",
    "22309": "남해111",
    "22310": "고성",
    "22311": "삼척",
    "22446": "연평도",
    "22485": "강릉",
    "22489": "자은",
    "22510": "내파수도",
    "22512": "죽변",
    "22513": "지심도",
    "22514": "이수도",
    "22515": "구엄",
    "22520": "위미",
    "22522": "대치마도",
}

# Lighthouse stations (9 sites) — source: kma_lhaws.php
LIGHTHOUSE_STATIONS: Dict[str, str] = {
    "955": "가대암",
    "956": "칠암",
    "957": "남형제도",
    "958": "연도",
    "959": "소매물도",
    "960": "동화도",
    "961": "소청도",
    "963": "목포구",
    "984": "장기갑",
}

# Weather ships
SHIP_STATIONS: Dict[str, str] = {
    "22003": "기상1호",
    "1": "기상2000호",
}

# Unified dict: type -> stations
ALL_STATIONS = {
    "buoy": BUOY_STATIONS,
    "lighthouse": LIGHTHOUSE_STATIONS,
    "ship": SHIP_STATIONS,
}

# Max days per single API call
_MAX_DAYS_PER_CALL = 31

# Column indices per station type (0-based, in comma-separated output)
# buoy (kma_buoy2): TM[0], STN[1], WD1[2], WS1[3], ..., WH_SIG[13]
# lighthouse (kma_lhaws2): TM[0], STN[1], WD[2], WS[3], ..., WH_SIG[15]
# ship (kma_kship): TM[0], STN[1], ..., WS[4], ..., WH_SIG[19]
_COL_MAP = {
    "buoy": {"tm": 0, "ws": 3, "wh_sig": 13, "min_cols": 14},
    "lighthouse": {"tm": 0, "ws": 3, "wh_sig": 15, "min_cols": 16},
    "ship": {"tm": 0, "ws": 4, "wh_sig": 19, "min_cols": 20},
}


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _fetch_text(url: str, timeout: int = 30) -> str:
    """Fetch a URL and return decoded text."""
    try:
        with urlopen(url, timeout=timeout) as resp:
            raw = resp.read()
            return raw.decode("euc-kr", errors="replace")
    except HTTPError as e:
        if e.code == 403:
            raise PermissionError(
                "API 접근이 거부되었습니다 (403). "
                "API Hub에서 해당 API 활용신청이 필요합니다."
            ) from e
        raise ConnectionError(f"HTTP {e.code}: {e.reason}") from e
    except URLError as e:
        raise ConnectionError(f"네트워크 오류: {e.reason}") from e


def _parse_obs_text(text: str, stype: str) -> pd.DataFrame:
    """Parse KMA observation text response into a DataFrame.

    Works for buoy, lighthouse, and ship data (different column indices).
    """
    cmap = _COL_MAP[stype]
    idx_tm = cmap["tm"]
    idx_ws = cmap["ws"]
    idx_wh = cmap["wh_sig"]
    min_cols = cmap["min_cols"]

    rows = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < min_cols:
            continue
        try:
            tm_str = parts[idx_tm]
            ws_val = float(parts[idx_ws])
            wh_val = float(parts[idx_wh])
        except (ValueError, IndexError):
            continue

        hs = wh_val if -90 < wh_val <= 30 else float("nan")
        wind = ws_val if -90 < ws_val <= 80 else float("nan")

        try:
            dt = datetime.strptime(tm_str, "%Y%m%d%H%M")
        except ValueError:
            continue

        rows.append({"timestamp": dt, "Hs": hs, "Wind": wind})

    if not rows:
        raise ValueError("API 응답에서 유효한 데이터를 찾을 수 없습니다.")

    df = pd.DataFrame(rows)
    df = df.set_index("timestamp").sort_index()
    df = df.dropna(how="all")
    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_station_label(stype: str, stn_id: str) -> str:
    """Return display label like '덕적도 (22101)'."""
    stations = ALL_STATIONS.get(stype, {})
    name = stations.get(stn_id, stn_id)
    return f"{name} ({stn_id})"


def fetch_timeseries(
    api_key: str,
    stype: str,
    station_id: str,
    start: datetime,
    end: datetime,
    progress_callback: Optional[callable] = None,
) -> pd.DataFrame:
    """Fetch observation time series from KMA API Hub.

    Parameters
    ----------
    api_key : str
        KMA API Hub authentication key.
    stype : str
        Station type: "buoy", "lighthouse", or "ship".
    station_id : str
        Station ID (e.g. "22101" for 덕적도).
    start, end : datetime
        Query period (KST).
    progress_callback : callable, optional
        Called with (current_chunk, total_chunks) for progress reporting.

    Returns
    -------
    pd.DataFrame
        DataFrame with DatetimeIndex and columns 'Hs' (m) and 'Wind' (m/s).
    """
    if not api_key or not api_key.strip():
        raise ValueError("API 인증키가 필요합니다.")
    if stype not in STATION_TYPES:
        raise ValueError(f"알 수 없는 관측 유형: {stype}")
    stations = ALL_STATIONS[stype]
    if station_id not in stations:
        raise ValueError(f"알 수 없는 관측소 ID: {station_id}")
    if end <= start:
        raise ValueError("종료일이 시작일보다 뒤여야 합니다.")

    endpoint = STATION_TYPES[stype]["endpoint"]

    # Chunk into windows
    chunks: List[Tuple[datetime, datetime]] = []
    cur = start
    while cur < end:
        chunk_end = min(cur + timedelta(days=_MAX_DAYS_PER_CALL), end)
        chunks.append((cur, chunk_end))
        cur = chunk_end

    frames: List[pd.DataFrame] = []
    for i, (c_start, c_end) in enumerate(chunks):
        if progress_callback:
            progress_callback(i + 1, len(chunks))

        tm1 = c_start.strftime("%Y%m%d%H%M")
        tm2 = c_end.strftime("%Y%m%d%H%M")
        url = (
            f"{_BASE}{endpoint}"
            f"?tm1={tm1}&tm2={tm2}&stn={station_id}&authKey={api_key}"
        )
        text = _fetch_text(url)
        try:
            chunk_df = _parse_obs_text(text, stype)
            frames.append(chunk_df)
        except ValueError:
            continue

    if not frames:
        label = get_station_label(stype, station_id)
        raise ValueError(
            f"선택한 기간({start.date()} ~ {end.date()})에 "
            f"관측소 {label}의 데이터가 없습니다."
        )

    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    return df
