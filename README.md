# Marine P-Value Simulator

Monte Carlo simulation tool for analyzing marine/offshore operation campaign feasibility under meteorological constraints.

Given historical metocean data (wave height, wind speed), the simulator estimates **percentile-based durations** (P50, P75, P90) for completing work campaigns — helping engineers plan offshore operations with quantified weather risk.

## Features

- **Monte Carlo engine** — 1000+ randomised campaign simulations per run
- **Dual work modes** — continuous blocks or accumulated (split) scheduling
- **ERA5 hindcast support** — auto-parses ERA5 30-year hindcast CSVs
- **Optimal start-month** — analyses all 12 months to find the best window
- **Batch comparison** — run multiple sites and compare side-by-side
- **Desktop GUI (PyQt6)** — standalone application with step-by-step guided workflow
- **Web GUI (Streamlit)** — browser-based dashboard with Plotly charts
- **CLI** — Click-based command-line interface
- **Offline .exe** — PyInstaller packaging for Windows distribution
- **Excel reports** — formatted `.xlsx` with summary, results, and task sheets

## Quick Start

### Installation

```bash
pip install -e ".[all]"
```

Or install only what you need:

```bash
pip install -e .              # core (CLI only)
pip install -e ".[desktop]"   # + PyQt6 desktop GUI
pip install -e ".[gui]"       # + Streamlit web GUI
pip install -e ".[excel]"     # + Excel report generation
pip install -e ".[dev]"       # + pytest
```

### Desktop GUI

```bash
pvalue-desktop
# or:
python -m pvalue.desktop
```

The desktop GUI features:
- **Step-by-step workflow** — tabs are unlocked progressively (Data → Config → Run → Results)
- **Tooltips on every widget** — hover for detailed explanations
- **Load Example button** — try the simulator instantly with bundled sample data
- **Result interpretation** — plain-language P-value explanations
- **Charts** — histogram, CDF, work/wait scatter, timeline

### Web GUI

```bash
pvalue gui
# or directly:
streamlit run pvalue/app.py
```

On Windows, double-click **`run_web_gui.bat`** to launch the web interface.

### CLI Usage

```bash
# Single-file analysis
pvalue run data.csv -c config.json -o ./results

# Batch analysis (multiple sites)
pvalue batch site_a.csv site_b.csv -c config.json -o ./batch_results

# Find optimal start month
pvalue optimal-month data.csv -c config.json

# Validate a CSV file
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

results = simulate_campaign(df, tasks, n_sims=1000)
summary = summarize_pxx(results)
print(summary)
```

## Building Standalone .exe (Windows)

```bash
# Create clean build environment
python -m venv .build_venv
.build_venv\Scripts\activate
pip install -e ".[desktop,excel,build]"

# Build
python build_exe.py
```

Output: `dist/PValueSimulator/` (distribute entire folder — `.exe` + `_internal`)

## Configuration

Task definitions are provided via JSON:

```json
{
  "tasks": [
    {
      "name": "Mobilization",
      "duration_h": 12,
      "thresholds": {"Hs": 2.0, "Wind": 12},
      "setup_h": 2,
      "teardown_h": 0
    },
    {
      "name": "Installation",
      "duration_h": 48,
      "thresholds": {"Hs": 1.5, "Wind": 10},
      "setup_h": 4,
      "teardown_h": 2
    }
  ],
  "n_sims": 1000,
  "pvals": [50, 75, 90],
  "split_mode": false,
  "na_handling": "permissive",
  "start_month": null
}
```

| Field | Description |
|-------|-------------|
| `tasks` | Ordered list of operation phases |
| `duration_h` | Required work hours (weather-dependent) |
| `thresholds` | Max Hs (m) and Wind (m/s) for work |
| `setup_h` / `teardown_h` | Additional hours before/after main work |
| `n_sims` | Number of Monte Carlo iterations (default: 1000) |
| `pvals` | Percentiles to report, e.g. `[50, 75, 90]` |
| `split_mode` | `false` = continuous window, `true` = accumulated hours |
| `na_handling` | `"permissive"` (NA = work OK) or `"conservative"` (NA = blocked) |
| `start_month` | Restrict start to a month (1-12) or `null` for any |
| `calendar` | `["all"]` for 24h, or `["custom", "tz", "7-19"]` for business hours |

See [`examples/`](examples/) for sample configs and metocean data.

## CSV Formats

### General CSV

Standard format with `timestamp` index and `Hs`, `Wind` columns:

```csv
timestamp,Hs,Wind
2020-01-01 00:00:00,1.2,8.5
2020-01-01 01:00:00,1.3,9.1
```

Supports any regular time interval (10-min, 1-hour, etc.) — auto-detected.

### Hindcast CSV (ERA5)

ERA5 format with 5-line metadata header. Wind and Hs columns are auto-detected by pattern matching.

## Project Structure

```
PValue/
├── pvalue/                     # Main package
│   ├── __init__.py             # Public API
│   ├── __main__.py             # python -m pvalue
│   ├── models.py               # Task, SimulationConfig dataclasses
│   ├── data.py                 # CSV loading, validation, condition masks
│   ├── simulation.py           # Monte Carlo engine
│   ├── analysis.py             # High-level workflows (batch, optimal month)
│   ├── visualization.py        # Matplotlib chart functions
│   ├── reporting.py            # Excel report generation
│   ├── cli.py                  # Click CLI
│   ├── app.py                  # Streamlit web GUI
│   ├── desktop.py              # PyQt6 entry point
│   └── gui/                    # Desktop GUI components
│       ├── main_window.py      #   Main window + tab management
│       ├── tabs.py             #   Tab pages (Data, Config, Run, Results, Charts, Optimal)
│       ├── widgets.py          #   Reusable widgets (ChartWidget, SummaryTable, TaskTable)
│       └── workers.py          #   QThread workers for background simulation
├── tests/                      # Unit tests (38 tests)
│   ├── test_models.py
│   ├── test_data.py
│   └── test_simulation.py
├── examples/                   # Sample data & configs
│   ├── sample_metocean.csv     #   Example metocean CSV (10-day, 1h interval)
│   ├── sample_config.json      #   Single-run config template
│   └── batch_config.json       #   Batch-run config template
├── build_exe.py                # PyInstaller build script
├── build.spec                  # PyInstaller spec file
├── run_web_gui.bat             # Windows launcher for Streamlit GUI
├── pyproject.toml              # Project metadata & build config
├── requirements.txt            # Core dependencies
├── P_Value_Program.py          # Legacy monolithic script (reference)
└── README.md
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=pvalue
```

## Verification

The refactored `pvalue` package has been verified against the original `P_Value_Program.py` — all P-value outputs (P60, P70, P80, P90, P100, Mean, Std, Min, Max) match exactly with identical data, config, and seed.

## License

MIT
