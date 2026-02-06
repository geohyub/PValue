"""Command-line interface built with Click."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from pvalue import __version__
from pvalue.data import load_csv, validate_metocean, get_time_interval_minutes
from pvalue.models import SimulationConfig, Task
from pvalue.simulation import simulate_campaign, summarize_pxx

logger = logging.getLogger(__name__)

_LOG_FORMAT = "%(levelname)-8s %(message)s"


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format=_LOG_FORMAT, force=True)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(__version__, prog_name="pvalue")
def cli():
    """Marine P-Value Simulator — Monte Carlo analysis for offshore operations."""


# ---------------------------------------------------------------------------
# run — single-file simulation
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("csv_path", type=click.Path(exists=True))
@click.option("--config", "-c", "config_path", type=click.Path(exists=True), required=True, help="JSON config file with task definitions.")
@click.option("--csv-type", type=click.Choice(["general", "hindcast"]), default="general", help="CSV format type.")
@click.option("--output", "-o", "output_dir", default="./pxx_outputs", help="Output directory.")
@click.option("--start-date", default=None, help="Start date filter (hindcast, YYYY-MM-DD).")
@click.option("--end-date", default=None, help="End date filter (hindcast, YYYY-MM-DD).")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
def run(csv_path, config_path, csv_type, output_dir, start_date, end_date, verbose):
    """Run a single-file Monte Carlo simulation."""
    _setup_logging(verbose)
    from pvalue.analysis import run_single

    with open(config_path, encoding="utf-8") as f:
        raw = json.load(f)

    config = SimulationConfig.from_dict(raw)
    df = load_csv(csv_path, csv_type, start_date, end_date)
    run_single(df, config, output_dir)
    click.echo(f"\nResults saved to {output_dir}")


# ---------------------------------------------------------------------------
# batch — multi-file comparison
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("csv_files", nargs=-1, type=click.Path(exists=True))
@click.option("--config", "-c", "config_path", type=click.Path(exists=True), required=True)
@click.option("--csv-type", type=click.Choice(["general", "hindcast"]), default="general")
@click.option("--output", "-o", "output_dir", default="./batch_outputs")
@click.option("--verbose", "-v", is_flag=True)
def batch(csv_files, config_path, csv_type, output_dir, verbose):
    """Run batch analysis on multiple CSV files."""
    _setup_logging(verbose)
    from pvalue.analysis import batch_run

    with open(config_path, encoding="utf-8") as f:
        raw = json.load(f)

    config = SimulationConfig.from_dict(raw)
    results = batch_run(list(csv_files), config, csv_type, output_dir)
    click.echo(f"\nBatch analysis complete — {len(results)} sites processed")


# ---------------------------------------------------------------------------
# optimal-month — monthly analysis
# ---------------------------------------------------------------------------

@cli.command("optimal-month")
@click.argument("csv_path", type=click.Path(exists=True))
@click.option("--config", "-c", "config_path", type=click.Path(exists=True), required=True)
@click.option("--csv-type", type=click.Choice(["general", "hindcast"]), default="general")
@click.option("--output", "-o", "save_path", default=None, help="Save chart to file.")
@click.option("--verbose", "-v", is_flag=True)
def optimal_month(csv_path, config_path, csv_type, save_path, verbose):
    """Analyze all 12 months to find the optimal campaign start."""
    _setup_logging(verbose)
    from pvalue.analysis import analyze_optimal_start_month

    with open(config_path, encoding="utf-8") as f:
        raw = json.load(f)

    config = SimulationConfig.from_dict(raw)
    df = load_csv(csv_path, csv_type)
    result = analyze_optimal_start_month(df, config, save_path)
    click.echo("\nMonthly Analysis:")
    click.echo(result.to_string(index=False))


# ---------------------------------------------------------------------------
# gui — launch Streamlit app
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--port", default=8501, help="Port for Streamlit server.")
def gui(port):
    """Launch the Streamlit web interface."""
    import subprocess

    app_path = Path(__file__).parent / "app.py"
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port)],
    )


# ---------------------------------------------------------------------------
# validate — check a CSV without running simulation
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("csv_path", type=click.Path(exists=True))
@click.option("--csv-type", type=click.Choice(["general", "hindcast"]), default="general")
def validate(csv_path, csv_type):
    """Validate a metocean CSV file."""
    _setup_logging(False)
    df = load_csv(csv_path, csv_type)
    ok, msg = validate_metocean(df)
    interval = get_time_interval_minutes(df)
    if ok:
        click.echo(f"OK — {len(df)} records, {interval}-min interval")
    else:
        click.echo(f"FAIL — {msg}", err=True)
        raise SystemExit(1)
