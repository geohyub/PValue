"""Streamlit web GUI for Marine P-Value Simulator."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from pvalue import __version__
from pvalue.data import get_time_interval_minutes, load_csv, validate_metocean
from pvalue.models import SimulationConfig, Task
from pvalue.simulation import simulate_campaign, summarize_pxx

# Lazy API imports (optional dependencies)
from pvalue.kma import (
    STATION_TYPES as KMA_STATION_TYPES,
    ALL_STATIONS as KMA_ALL_STATIONS,
    fetch_timeseries as kma_fetch,
    get_station_label as kma_label,
)
from pvalue.khoa import (
    KHOA_STATIONS,
    fetch_timeseries as khoa_fetch,
    get_station_label as khoa_label,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Marine P-Value Simulator",
    page_icon="\u2693",  # anchor
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.title(f"\u2693 Marine P-Value Simulator")
st.sidebar.caption(f"v{__version__}")

page = st.sidebar.radio(
    "Navigation",
    ["Simulation", "Batch Analysis", "Optimal Month", "About"],
)

# ---------------------------------------------------------------------------
# Helper: Plotly charts (richer than matplotlib in a browser)
# ---------------------------------------------------------------------------

def _try_import_plotly():
    try:
        import plotly.express as px
        import plotly.graph_objects as go
        return px, go
    except ImportError:
        return None, None


def _plotly_histogram(res: pd.DataFrame, pvals: list):
    px, go = _try_import_plotly()
    if px is None:
        st.warning("Install plotly for interactive charts: `pip install plotly`")
        return

    fig = px.histogram(
        res, x="elapsed_days", nbins=40,
        labels={"elapsed_days": "Campaign Duration (days)"},
        title="Campaign Duration Distribution",
        color_discrete_sequence=["#87CEEB"],
    )
    for p in pvals:
        val = np.percentile(res["elapsed_days"], p)
        color = {"50": "royalblue", "75": "orange", "90": "crimson"}.get(str(p), "gray")
        fig.add_vline(x=val, line_dash="dash", line_color=color, annotation_text=f"P{p}={val:.1f}d")
    fig.update_layout(bargap=0.05)
    st.plotly_chart(fig, use_container_width=True)


def _plotly_cdf(res: pd.DataFrame):
    px, go = _try_import_plotly()
    if px is None:
        return
    sorted_d = np.sort(res["elapsed_days"])
    cdf = np.arange(1, len(sorted_d) + 1) / len(sorted_d) * 100
    fig = px.line(x=sorted_d, y=cdf, labels={"x": "Duration (days)", "y": "Cumulative %"}, title="CDF")
    st.plotly_chart(fig, use_container_width=True)


def _plotly_scatter(res: pd.DataFrame):
    px, go = _try_import_plotly()
    if px is None:
        return
    fig = px.scatter(
        res, x=res["work_hours"] / 24, y=res["wait_hours"] / 24,
        labels={"x": "Work (days)", "y": "Wait (days)"},
        title="Work vs. Wait",
        opacity=0.5,
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Shared: data source (CSV upload or API fetch)
# ---------------------------------------------------------------------------

def _validate_and_show(df, key_prefix):
    """Validate DataFrame and display summary. Returns (df, csv_type) or (None, None)."""
    ok, msg = validate_metocean(df)
    if not ok:
        st.error(f"Validation failed: {msg}")
        return None, None
    interval = get_time_interval_minutes(df)
    st.success(f"Loaded {len(df):,} records | {interval}-min interval | {df.index.min().date()} to {df.index.max().date()}")

    # Missing data warning
    hs_nan = int(df["Hs"].isna().sum())
    wind_nan = int(df["Wind"].isna().sum())
    total = len(df)
    if hs_nan > 0 or wind_nan > 0:
        parts = []
        if hs_nan > 0:
            parts.append(f"Hs {hs_nan:,}건 ({hs_nan/total*100:.1f}%)")
        if wind_nan > 0:
            parts.append(f"Wind {wind_nan:,}건 ({wind_nan/total*100:.1f}%)")
        st.warning(
            f"⚠ 결측 데이터 감지: {', '.join(parts)}  \n"
            f"결측 구간은 시뮬레이션에서 작업 가능으로 처리됩니다 (NA handling: permissive)"
        )

    return df, "general"


def _csv_source(key_prefix):
    """CSV upload data source."""
    csv_type = st.selectbox("CSV Format", ["general", "hindcast"], key=f"{key_prefix}_type")
    uploaded = st.file_uploader("Upload metocean CSV", type=["csv"], key=f"{key_prefix}_file")

    if uploaded is None:
        return None, csv_type

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(uploaded.read())
        tmp_path = tmp.name

    start_date = end_date = None
    if csv_type == "hindcast":
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.text_input("Start date (YYYY-MM-DD)", value="", key=f"{key_prefix}_sd")
        with col2:
            end_date = st.text_input("End date (YYYY-MM-DD)", value="", key=f"{key_prefix}_ed")
        start_date = start_date or None
        end_date = end_date or None

    try:
        df = load_csv(tmp_path, csv_type, start_date, end_date)
    except ValueError as exc:
        st.error(f"Failed to load CSV: {exc}")
        return None, csv_type

    return _validate_and_show(df, key_prefix)


def _kma_api_source(key_prefix):
    """KMA API data source."""
    st.caption("기상청 API Hub에서 해양기상부이/등표/기상1호 데이터를 가져옵니다.")
    st.warning("⚠ API 데이터는 파고(Hs) 소수점 1자리 정밀도로 제공됩니다 (P값 차이 ~1% 이내)")

    api_key = st.text_input("KMA API 인증키", type="password", key=f"{key_prefix}_kma_key",
                            help="apihub.kma.go.kr에서 무료 발급")
    if not api_key:
        st.info("API 인증키를 입력하세요.")
        return None, None

    c1, c2 = st.columns(2)
    stype = c1.selectbox("관측 유형", list(KMA_STATION_TYPES.keys()),
                         format_func=lambda x: KMA_STATION_TYPES[x]["label"],
                         key=f"{key_prefix}_kma_stype")
    stations = KMA_ALL_STATIONS.get(stype, {})
    stn_options = sorted(stations.keys())
    stn_id = c2.selectbox("관측소", stn_options,
                          format_func=lambda x: f"{stations[x]} ({x})",
                          key=f"{key_prefix}_kma_stn")

    c3, c4 = st.columns(2)
    default_start = datetime.now() - timedelta(days=365 * 3)
    start_date = c3.date_input("시작일", value=default_start, key=f"{key_prefix}_kma_start")
    end_date = c4.date_input("종료일", value=datetime.now(), key=f"{key_prefix}_kma_end")

    if not st.button("Fetch Data", type="primary", key=f"{key_prefix}_kma_fetch"):
        return None, None

    start_dt = datetime(start_date.year, start_date.month, start_date.day)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59)

    progress = st.progress(0, text="KMA API에서 데이터 수신 중...")
    try:
        df = kma_fetch(
            api_key, stype, stn_id, start_dt, end_dt,
            progress_callback=lambda cur, tot: progress.progress(cur / tot, text=f"수신 중... {cur}/{tot}건")
        )
        progress.empty()
        label = kma_label(stype, stn_id)
        st.info(f"📡 {label} | {len(df):,}건")

        # CSV download button
        stations = KMA_ALL_STATIONS.get(stype, {})
        name = stations.get(stn_id, stn_id).replace(" ", "_")
        fname = f"{name}_{df.index.min().strftime('%y%m')}_{df.index.max().strftime('%y%m')}.csv"
        csv_out = df.copy()
        csv_out.index.name = "timestamp"
        st.download_button("Save CSV", csv_out.to_csv(), fname, "text/csv",
                           key=f"{key_prefix}_kma_dl")

        return _validate_and_show(df, key_prefix)
    except Exception as e:
        progress.empty()
        st.error(f"API 오류: {e}")
        return None, None


def _khoa_api_source(key_prefix):
    """KHOA API data source."""
    st.caption("국립해양조사원(KHOA) 해양관측부이 데이터를 공공데이터포털(data.go.kr)에서 가져옵니다.")
    st.warning("⚠ API 데이터는 파고(Hs) 소수점 1자리 정밀도로 제공됩니다 (P값 차이 ~1% 이내). "
               "고정밀(소수 2자리) 데이터가 필요하면 KHOA 홈페이지에서 CSV를 다운받아 사용하세요.")

    service_key = st.text_input("data.go.kr 인증키", type="password", key=f"{key_prefix}_khoa_key",
                                help="공공데이터포털에서 무료 발급")
    if not service_key:
        st.info("API 인증키를 입력하세요.")
        return None, None

    stn_options = sorted(KHOA_STATIONS.keys())
    obs_code = st.selectbox("관측소", stn_options,
                            format_func=lambda x: f"{KHOA_STATIONS[x]} ({x})",
                            key=f"{key_prefix}_khoa_stn")

    c1, c2 = st.columns(2)
    default_start = datetime.now() - timedelta(days=365 * 3)
    start_date = c1.date_input("시작일", value=default_start, key=f"{key_prefix}_khoa_start")
    end_date = c2.date_input("종료일", value=datetime.now(), key=f"{key_prefix}_khoa_end")

    if not st.button("Fetch Data", type="primary", key=f"{key_prefix}_khoa_fetch"):
        return None, None

    start_dt = datetime(start_date.year, start_date.month, start_date.day)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59)

    total_days = (end_dt.date() - start_dt.date()).days + 1
    progress = st.progress(0, text="KHOA API에서 데이터 수신 중...")
    try:
        df = khoa_fetch(
            service_key, obs_code, start_dt, end_dt,
            progress_callback=lambda cur, tot: progress.progress(cur / tot, text=f"수신 중... {cur}/{tot}일")
        )
        progress.empty()
        label = khoa_label(obs_code)
        st.info(f"📡 {label} | {len(df):,}건")

        # CSV download button
        name = KHOA_STATIONS.get(obs_code, obs_code).replace(" ", "_")
        fname = f"{name}_{df.index.min().strftime('%y%m')}_{df.index.max().strftime('%y%m')}.csv"
        csv_out = df.copy()
        csv_out.index.name = "timestamp"
        st.download_button("Save CSV", csv_out.to_csv(), fname, "text/csv",
                           key=f"{key_prefix}_khoa_dl")

        return _validate_and_show(df, key_prefix)
    except Exception as e:
        progress.empty()
        st.error(f"API 오류: {e}")
        return None, None


def upload_and_validate(key_prefix="main"):
    """Combined data source: CSV, KMA API, or KHOA API."""
    source = st.radio("Data Source", ["CSV 파일", "KMA API (기상청)", "KHOA API (해양조사원)"],
                      horizontal=True, key=f"{key_prefix}_source")

    if source == "CSV 파일":
        return _csv_source(key_prefix)
    elif source == "KMA API (기상청)":
        return _kma_api_source(key_prefix)
    else:
        return _khoa_api_source(key_prefix)


# ---------------------------------------------------------------------------
# Shared: task editor
# ---------------------------------------------------------------------------

def task_editor(key_prefix="main"):
    st.subheader("Task Definitions")

    input_mode = st.radio("Input mode", ["Form", "JSON"], horizontal=True, key=f"{key_prefix}_mode")

    if input_mode == "JSON":
        default_json = json.dumps({
            "tasks": [
                {"name": "Task A", "duration_h": 24, "thresholds": {"Hs": 1.5, "Wind": 10}},
            ],
            "n_sims": 1000,
            "pvals": [50, 75, 90],
        }, indent=2)
        raw = st.text_area("Paste JSON config", value=default_json, height=250, key=f"{key_prefix}_json")
        try:
            data = json.loads(raw)
            config = SimulationConfig.from_dict(data)
            st.info(f"{len(config.tasks)} task(s) loaded")
            return config
        except Exception as exc:
            st.error(f"Invalid JSON: {exc}")
            return None

    # Form mode
    n_tasks = st.number_input("Number of tasks", 1, 20, 1, key=f"{key_prefix}_ntask")
    tasks = []
    for i in range(n_tasks):
        with st.expander(f"Task {i + 1}", expanded=(i == 0)):
            c1, c2 = st.columns(2)
            name = c1.text_input("Name", f"Task {i + 1}", key=f"{key_prefix}_name_{i}")
            duration = c2.number_input("Duration (h)", 1, 10000, 24, key=f"{key_prefix}_dur_{i}")
            c3, c4 = st.columns(2)
            hs_thr = c3.number_input("Hs limit (m)", 0.1, 20.0, 1.5, step=0.1, key=f"{key_prefix}_hs_{i}")
            wind_thr = c4.number_input("Wind limit (m/s)", 0.1, 70.0, 10.0, step=0.5, key=f"{key_prefix}_wind_{i}")
            c5, c6 = st.columns(2)
            setup = c5.number_input("Setup (h)", 0, 100, 0, key=f"{key_prefix}_su_{i}")
            teardown = c6.number_input("Teardown (h)", 0, 100, 0, key=f"{key_prefix}_td_{i}")
            tasks.append(Task(name=name, duration_h=duration, thresholds={"Hs": hs_thr, "Wind": wind_thr}, setup_h=setup, teardown_h=teardown))

    st.subheader("Simulation Settings")
    c1, c2, c3 = st.columns(3)
    n_sims = c1.number_input("Simulations", 100, 50000, 1000, step=100, key=f"{key_prefix}_nsim")
    na_mode = c2.selectbox("NA handling", ["permissive", "conservative"], key=f"{key_prefix}_na")
    split = c3.checkbox("Split (accumulated) mode", key=f"{key_prefix}_split")

    c4, c5 = st.columns(2)
    month_opt = c4.selectbox("Start month", ["Any"] + [str(m) for m in range(1, 13)], key=f"{key_prefix}_month")
    start_month = None if month_opt == "Any" else int(month_opt)
    pvals_str = c5.text_input("Percentiles (comma-separated)", "50,75,90", key=f"{key_prefix}_pv")
    pvals = [int(x.strip()) for x in pvals_str.split(",")]

    return SimulationConfig(
        tasks=tasks, n_sims=n_sims, start_month=start_month,
        split_mode=split, na_handling=na_mode, pvals=pvals,
    )


# ---------------------------------------------------------------------------
# Page: Simulation
# ---------------------------------------------------------------------------

def page_simulation():
    st.header("Single-file Simulation")

    col_left, col_right = st.columns([1, 1])

    with col_left:
        df, csv_type = upload_and_validate("sim")

    with col_right:
        config = task_editor("sim")

    if df is None or config is None:
        return

    if st.button("Run Simulation", type="primary", use_container_width=True):
        interval = get_time_interval_minutes(df)

        progress = st.progress(0, text="Running simulation...")

        def _cb(current, total):
            progress.progress(current / total, text=f"Simulation {current}/{total}")

        res = simulate_campaign(
            df, config.tasks,
            n_sims=config.n_sims, start_month=config.start_month,
            calendar_mask_fn=config.build_calendar_mask_fn(),
            split_mode=config.split_mode, time_interval_min=interval,
            na_handling=config.na_handling, seed=config.seed,
            progress_callback=_cb,
        )
        progress.empty()

        summary = summarize_pxx(res, config.pvals)

        st.subheader("Results Summary")
        col1, col2, col3, col4 = st.columns(4)
        for i, row in summary.iterrows():
            cols = [col1, col2, col3, col4]
            cols[i % 4].metric(row["Metric"], f"{row['Value_days']:.2f} days")

        tab1, tab2, tab3, tab4 = st.tabs(["Distribution", "CDF", "Work vs Wait", "Raw Data"])
        with tab1:
            _plotly_histogram(res, config.pvals)
        with tab2:
            _plotly_cdf(res)
        with tab3:
            _plotly_scatter(res)
        with tab4:
            st.dataframe(res, use_container_width=True)

        csv_data = res.to_csv(index=False)
        st.download_button("Download Results (CSV)", csv_data, "simulation_results.csv", "text/csv")


# ---------------------------------------------------------------------------
# Page: Batch
# ---------------------------------------------------------------------------

def page_batch():
    st.header("Batch Analysis")
    st.info("Upload multiple CSV files to compare sites side by side.")

    files = st.file_uploader("Upload CSV files", type=["csv"], accept_multiple_files=True, key="batch_files")
    csv_type = st.selectbox("CSV Format", ["general", "hindcast"], key="batch_type")
    config = task_editor("batch")

    if not files or config is None:
        return

    if st.button("Run Batch", type="primary"):
        all_results = {}
        progress = st.progress(0)

        for idx, f in enumerate(files):
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                tmp.write(f.read())
                tmp_path = tmp.name

            try:
                df = load_csv(tmp_path, csv_type)
                ok, msg = validate_metocean(df)
                if not ok:
                    st.warning(f"{f.name}: {msg}")
                    continue

                interval = get_time_interval_minutes(df)
                res = simulate_campaign(
                    df, config.tasks, n_sims=config.n_sims,
                    start_month=config.start_month, split_mode=config.split_mode,
                    time_interval_min=interval, na_handling=config.na_handling,
                    seed=config.seed,
                )
                summary = summarize_pxx(res, config.pvals)
                name = f.name.replace(".csv", "")
                all_results[name] = {"results": res, "summary": summary}
            except Exception as exc:
                st.error(f"{f.name}: {exc}")

            progress.progress((idx + 1) / len(files))

        progress.empty()

        if all_results:
            px, go = _try_import_plotly()
            if px:
                box_data = []
                for name, r in all_results.items():
                    for d in r["results"]["elapsed_days"]:
                        box_data.append({"Site": name, "Duration (days)": d})
                fig = px.box(pd.DataFrame(box_data), x="Site", y="Duration (days)", title="Site Comparison")
                st.plotly_chart(fig, use_container_width=True)

            comparison = pd.DataFrame(
                {n: r["summary"]["Value_days"].values for n, r in all_results.items()},
                index=list(all_results.values())[0]["summary"]["Metric"],
            )
            st.dataframe(comparison, use_container_width=True)


# ---------------------------------------------------------------------------
# Page: Optimal Month
# ---------------------------------------------------------------------------

def page_optimal_month():
    st.header("Optimal Start Month Analysis")

    df, csv_type = upload_and_validate("opt")
    config = task_editor("opt")

    if df is None or config is None:
        return

    if st.button("Analyze All 12 Months", type="primary"):
        interval = get_time_interval_minutes(df)
        rows = []
        progress = st.progress(0)

        for month in range(1, 13):
            res = simulate_campaign(
                df, config.tasks,
                n_sims=max(500, config.n_sims // 2),
                start_month=month, split_mode=config.split_mode,
                time_interval_min=interval, na_handling=config.na_handling,
                seed=config.seed,
            )
            rows.append({
                "Month": month,
                "P90 (days)": float(np.percentile(res["elapsed_days"], 90)),
                "Mean (days)": float(res["elapsed_days"].mean()),
            })
            progress.progress(month / 12)

        progress.empty()
        result_df = pd.DataFrame(rows)
        optimal = int(result_df.loc[result_df["P90 (days)"].idxmin(), "Month"])

        st.success(f"Optimal start month: **{optimal}** (P90 = {result_df['P90 (days)'].min():.1f} days)")

        px, go = _try_import_plotly()
        if px:
            fig = px.line(result_df, x="Month", y=["P90 (days)", "Mean (days)"], markers=True, title="Monthly Analysis")
            fig.add_vline(x=optimal, line_dash="dash", line_color="red", annotation_text=f"Optimal: Month {optimal}")
            fig.update_xaxes(dtick=1)
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(result_df, use_container_width=True)


# ---------------------------------------------------------------------------
# Page: About
# ---------------------------------------------------------------------------

def page_about():
    st.header("About")
    st.markdown(f"""
**Marine P-Value Simulator** v{__version__}

A Monte Carlo simulation tool for analyzing the feasibility of marine/offshore
operation campaigns under meteorological constraints.

### Features
- **Single-file analysis** — general CSV or ERA5 hindcast data
- **Batch analysis** — compare multiple sites
- **Optimal month** — find the best time to start operations
- **Interactive charts** — Plotly-powered visualizations
- **Excel reports** — formatted spreadsheets with summary statistics

### How it works
1. Upload historical metocean (wave height, wind speed) data
2. Define work tasks with weather thresholds
3. Run Monte Carlo simulations to estimate campaign duration
4. View P50/P75/P90 percentile results

### Links
- CLI usage: `pvalue --help`
""")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_PAGES = {
    "Simulation": page_simulation,
    "Batch Analysis": page_batch,
    "Optimal Month": page_optimal_month,
    "About": page_about,
}

_PAGES[page]()
