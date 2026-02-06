# Marine P-Value Simulator

Monte Carlo simulation tool for analyzing marine/offshore operation campaign feasibility under meteorological constraints.

Given historical metocean data (wave height, wind speed), the simulator estimates **percentile-based durations** (P50, P75, P90) for completing work campaigns — helping engineers plan offshore operations with quantified weather risk.

## Features

- **Monte Carlo engine** — 1000+ randomised campaign simulations per run
- **Dual work modes** — continuous blocks or accumulated (split) scheduling
- **ERA5 hindcast support** — auto-parses ERA5 30-year hindcast CSVs
- **Optimal start-month** — analyses all 12 months to find the best window
- **Batch comparison** — run multiple sites and compare side-by-side
- **Interactive web GUI** — Streamlit dashboard with Plotly charts
- **CLI** — Click-based command-line interface
- **Excel reports** — formatted `.xlsx` with summary, results, and task sheets

## Quick Start

### Installation

```bash
pip install -e ".[all]"
```

Or install only what you need:

```bash
pip install -e .           # core (CLI only)
pip install -e ".[gui]"    # + Streamlit web GUI
pip install -e ".[excel]"  # + Excel report generation
pip install -e ".[dev]"    # + pytest
```

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

# Launch web GUI
pvalue gui
```

### Web GUI

```bash
pvalue gui
# or directly:
streamlit run pvalue/app.py
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
  "na_handling": "permissive"
}
```

See [`examples/`](examples/) for more configuration templates.

## CSV Formats

### General CSV

Standard format with `timestamp` index and `Hs`, `Wind` columns:

```csv
timestamp,Hs,Wind
2020-01-01 00:00:00,1.2,8.5
2020-01-01 01:00:00,1.3,9.1
```

### Hindcast CSV (ERA5)

ERA5 format with 5-line metadata header. Wind and Hs columns are auto-detected.

## Project Structure

```
PValue/
├── pvalue/                  # Main package
│   ├── __init__.py          # Public API
│   ├── __main__.py          # python -m pvalue
│   ├── models.py            # Task, SimulationConfig dataclasses
│   ├── data.py              # CSV loading, validation, condition masks
│   ├── simulation.py        # Monte Carlo engine
│   ├── visualization.py     # Matplotlib chart functions
│   ├── reporting.py         # Excel report generation
│   ├── analysis.py          # High-level workflows (batch, optimal month)
│   ├── cli.py               # Click CLI
│   └── app.py               # Streamlit web GUI
├── tests/                   # Unit tests
├── examples/                # Sample configs
├── pyproject.toml           # Project metadata & build config
├── requirements.txt         # Dependencies
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

## License

MIT
