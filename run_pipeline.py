#!/usr/bin/env python3
"""
run_pipeline.py - 端到端运行完整项目流水线。
run_pipeline.py - Run the full project pipeline end to end.

用法 / Usage:
    python run_pipeline.py
    python run_pipeline.py --skip-download
    python run_pipeline.py --analysis correlation
    python run_pipeline.py --analysis var_irf
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def run_step(command: list[str], label: str) -> None:
    print(f"\n[PIPELINE] {label}", flush=True)
    print(f"[PIPELINE] Running: {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=BASE_DIR, check=False)
    if completed.returncode != 0:
        raise SystemExit(
            f"[PIPELINE] Step failed with exit code {completed.returncode}: {label}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full project pipeline")
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip raw-data download and reuse existing files",
    )
    parser.add_argument(
        "--analysis",
        choices=["all", "correlation", "comparison", "anomaly", "var_irf", "rolling_granger"],
        default="all",
        help="Analysis mode for the final visualization step",
    )
    args = parser.parse_args()

    python_cmd = [sys.executable, "-u"]

    if not args.skip_download:
        run_step(python_cmd + ["src/get_data.py"], "Download raw data")

    run_step(python_cmd + ["src/clean_data.py"], "Clean and aggregate raw data")
    run_step(python_cmd + ["src/integrate_data.py"], "Integrate monthly datasets")
    run_step(
        python_cmd + ["src/analyze_visualize.py", "--analysis", args.analysis],
        "Run analysis and generate figures",
    )

    print("\n[PIPELINE] Pipeline complete.", flush=True)


if __name__ == "__main__":
    main()
