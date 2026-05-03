# The Impact of Armed Conflict on Commodity Prices (2019–2025)

Author: Xinchen Geng  
Course: DSCI 510

## Project Overview

This project investigates whether armed-conflict intensity helps predict commodity price movements from 2019 to 2025. Three structurally distinct conflicts—Russia-Ukraine, Israel-Palestine, and Yemen—serve as independent test cases. The analysis applies correlation analysis, VAR impulse-response functions, and rolling-window Granger causality to a unified monthly panel of conflict events and commodity prices.

Research Questions:

1. Does conflict intensity correlate with commodity prices at 0–2 month lags?
2. Do different conflict regions align with different commodity responses?
3. What price anomalies appear around the February 2022 and October 2023 escalation windows?

---

## Repository Structure

```
.
├── README.md
├── requirements.txt
├── scraper.py
├── proposal.pdf
├── FinalProject_Report.pdf
├── run_pipeline.py
├── data/
│   ├── raw/          # Original files downloaded from each source
│   └── processed/    # Cleaned and integrated CSV files
├── results/
│   ├── final_report.md
│   └── figures/      # Output charts (fig1–fig5)
└── src/
    ├── get_data.py
    ├── clean_data.py
    ├── integrate_data.py
    ├── analyze_visualize.py
    └── utils/
```

---

## Installation Requirements

Python 3.9+ is required. Install all dependencies with:

```bash
pip install -r requirements.txt
```

Key libraries used: `requests`, `pandas`, `numpy`, `yfinance`, `matplotlib`, `seaborn`, `scipy`, `statsmodels`, `pypdf`.

### API Keys

Two sources require free API credentials:

| Source | Environment Variable | Registration |
|--------|---------------------|--------------|
| ACLED  | OAuth: `ACLED_EMAIL` and `ACLED_PASSWORD`; legacy fallback: `ACLED_EMAIL` and `ACLED_API_KEY` | https://acleddata.com/register/ |
| EIA    | `EIA_API_KEY` | https://www.eia.gov/opendata/register.php |

Set them in your shell before running:

```bash
# Linux / macOS
export ACLED_EMAIL="your@email.com"
export ACLED_PASSWORD="your_password"
export EIA_API_KEY="your_key"

# Windows PowerShell
$env:ACLED_EMAIL="your@email.com"
$env:ACLED_PASSWORD="your_password"
$env:EIA_API_KEY="your_key"
```

Alternatively, copy `.env.example` to `.env` in the project root and fill in the values — all scripts load it automatically.

---

## Data Sources

| # | Source | Method | Raw Output | Samples |
|---|--------|--------|------------|---------|
| 1 | ACLED REST API | Paginated REST API (500 rows/page) | `acled_raw.csv` | ~1,166,745 events |
| 2 | EIA Open Data API v2 | Multi-series REST loop | `eia_energy.csv` | 84 monthly rows |
| 3 | Yahoo Finance (`GC=F`) | `yfinance` library | `gold_futures.csv` | 1,762 daily rows |
| 4 | FRED `PCOPPUSDM` | CSV download endpoint | `copper_fred.csv` | 84 monthly rows |
| 5 | FRED `PCOALAUUSDM` | CSV download endpoint | `coal_fred.csv` | 84 monthly rows |
| 6 | USGS Helium PDFs | `requests` + `pypdf` text extraction | `helium_usgs.csv` | 84 monthly rows (annual→monthly expanded) |

Note: the full ACLED raw exports are very large and are intentionally ignored by `.gitignore` for GitHub upload. Recreate them with `python src/get_data.py --source acled` when needed.

---

## How to Run

### Step 1 — Download Raw Data

```bash
python src/get_data.py
```

Download one source at a time (optional):

```bash
python src/get_data.py --source acled
python src/get_data.py --source eia
python src/get_data.py --source gold
python src/get_data.py --source copper
python src/get_data.py --source coal
python src/get_data.py --source helium
```

Outputs are written to `data/raw/`.

### Step 2 — Clean and Aggregate

```bash
python src/clean_data.py
```

Each raw file is cleaned (missing values handled, duplicates removed, dates normalized to `YYYY-MM`) and aggregated to monthly frequency. Outputs are written to `data/processed/`.

### Step 3 — Integrate All Sources

```bash
python src/integrate_data.py
```

All monthly tables are joined on the shared `year_month` key, producing `data/processed/unified_monthly.csv` (84 rows × 17 columns).

### Step 4 — Analyze and Visualize

```bash
python src/analyze_visualize.py
```

Run a specific analysis only:

```bash
python src/analyze_visualize.py --analysis correlation
python src/analyze_visualize.py --analysis comparison
python src/analyze_visualize.py --analysis anomaly
python src/analyze_visualize.py --analysis var_irf
python src/analyze_visualize.py --analysis rolling_granger
```

All figures are saved to `results/figures/`.

### Run the Full Pipeline

```bash
python run_pipeline.py
```

To reuse previously downloaded raw files:

```bash
python run_pipeline.py --skip-download
```

---

## Data Cleaning

`src/clean_data.py` performs the following steps for each source:

- ACLED: filter to three conflict regions (Russia-Ukraine, Israel-Palestine, Yemen) by country codes; aggregate event count and fatalities to monthly totals.
- EIA: parse multi-series API responses, cast values to numeric, and average to monthly frequency.
- Gold: resample daily OHLCV to monthly mean/max/min close price.
- Copper / Coal (FRED): parse CSV, detect the date column, cast prices to numeric, and average monthly values.
- Helium (USGS): extract annual price text from PDFs; expand each annual value across all 12 months of that year.

---

## Data Integration

`src/integrate_data.py` merges all six cleaned tables on `year_month` (YYYY-MM string) using a complete month spine from January 2019 – December 2025. The final unified panel contains 84 months × 17 columns:

- Conflict: `israel_palestine_events`, `russia_ukraine_events`, `yemen_events`, and corresponding `_fatalities` columns
- Energy: `wti_crude_usd_bbl`, `brent_crude_usd_bbl`, `heating_oil_usd_gal`, `henry_hub_gas_usd_mmbtu`
- Metals/Other: `gold_close_mean`, `copper_usd_metric_ton`, `coal_australia_usd_metric_ton`, `helium_usd_cubic_meter`

---

## Visualizations

All figures are static PNG files in `results/figures/`.

| File | Description |
|------|-------------|
| `fig1_correlation_heatmap.png` | Pearson correlation heatmap — conflict intensity vs. all commodity prices at lags 0, 1, 2 months |
| `fig2_conflict_comparison.png` | Time-series overlay of monthly conflict events and commodity prices per region |
| `fig3_anomaly_detection.png` | Z-score anomaly detection highlighting price spikes around Feb 2022 and Oct 2023 |
| `fig4_var_irf.png` | VAR impulse-response functions — commodity price response to a 1-SD conflict shock over 12 months |
| `fig5_rolling_granger.png` | Rolling 24-month Granger causality p-values — shows when conflict Granger-causes prices |

---

## ACLED Scraper (Submission 2)

The standalone scraper still works independently with the legacy `ACLED_API_KEY` + `ACLED_EMAIL` method:

```bash
python scraper.py                          # print all rows to stdout
python scraper.py --scrape 10             # print first 10 rows
python scraper.py --save data/raw/acled_raw.csv  # save to file
```

API key setup and usage details are documented in the **Installation Requirements** section above.