#!/usr/bin/env python3
"""
clean_data.py - 清洗并预处理所有原始数据源。
clean_data.py - Clean and preprocess all raw data sources.

输出 / Outputs:
  data/processed/acled_monthly.csv
  data/processed/eia_monthly.csv
  data/processed/gold_monthly.csv
  data/processed/copper_monthly.csv
  data/processed/coal_monthly.csv
  data/processed/helium_monthly.csv

用法 / Usage:
    python src/clean_data.py
"""

from __future__ import annotations

import os
import sys

import pandas as pd


# 路径 / Paths
# 先定位项目根目录与数据目录；set project, raw, and processed paths.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 原始数据目录；raw files live here before cleaning.
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
# 清洗后数据目录；processed monthly files are written here.
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")



# 常量 / Constants
# 研究只覆盖这五个冲突相关国家；limit the conflict universe to the five study countries.
CONFLICT_COUNTRIES = {"Ukraine", "Russia", "Israel", "Palestine", "Yemen"}
# 只保留核心暴力事件；keep event types most relevant to conflict intensity.
CORE_VIOLENCE_TYPES = {
    "Battles",
    "Explosions/Remote violence",
    "Violence against civilians",
}


# 工具函数 / Helpers
# 检查输入文件是否存在；warn and skip cleanly when a source file is missing.

def _require_input(input_path: str, hint: str) -> bool:
    if os.path.exists(input_path):
        return True

    print(f"[WARNING] File not found: {input_path}", file=sys.stderr)
    print(f"[INFO] {hint}", file=sys.stderr)
    return False

# 保存月度清洗结果；write a cleaned monthly table to disk.

def _save_monthly(df: pd.DataFrame, output_path: str, label: str) -> None:
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"[INFO] {label} cleaned -> {output_path} ({len(df)} rows)", file=sys.stderr)

# 通用月度价格清洗；shared cleaner for monthly price series.
# 铜、煤、氦结构相近；reuse one path for these similar price feeds.
def _clean_monthly_price_series(
    input_path: str,
    output_path: str,
    value_column: str,
    label: str,
) -> None:
    print(f"[INFO] Cleaning {label} data...", file=sys.stderr)
    # 原始数据缺失时退出；skip this source if its raw file is absent.

    if not _require_input(input_path, f"Run src/get_data.py --source {label} first."):
        return

    df = pd.read_csv(input_path, low_memory=False)
    print(f"[INFO]   Loaded {len(df)} raw rows", file=sys.stderr)
    # 日期列和目标价格列必不可少；date and value columns are required.

    if "date" not in df.columns:
        print(f"[ERROR] 'date' column not found in {input_path}", file=sys.stderr)
        return
    if value_column not in df.columns:
        print(f"[ERROR] '{value_column}' column not found in {input_path}", file=sys.stderr)
        return
    # 日期和价格转为可分析格式；coerce dates and numeric values before grouping.

    df["date"] = pd.to_datetime(df["date"], errors="coerce", format="mixed")
    df[value_column] = pd.to_numeric(df[value_column], errors="coerce")
    df = df.dropna(subset=["date", value_column]).copy()
    df["year_month"] = df["date"].dt.to_period("M").astype(str)

    monthly = (
        df.groupby("year_month")[value_column]
        .mean()
        .reset_index()
        .sort_values("year_month")
        .reset_index(drop=True)
    )

    _save_monthly(monthly, output_path, label.capitalize())


# 数据源 1：ACLED / Source 1: ACLED
# ACLED 先筛国家、事件类型、去重，再聚合；filter, deduplicate, and aggregate ACLED events.
def clean_acled(input_path: str, output_path: str) -> None:
    print("[INFO] Cleaning ACLED data...", file=sys.stderr)
    # 缺少原始 ACLED 文件时跳过；skip ACLED cleaning when the raw file is unavailable.

    if not _require_input(input_path, "Run src/get_data.py --source acled first."):
        return

    df = pd.read_csv(input_path, low_memory=False)
    print(f"[INFO]   Loaded {len(df)} raw rows", file=sys.stderr)
    # 只保留目标战场国家；keep rows from the study countries only.

    df = df[df["country"].isin(CONFLICT_COUNTRIES)].copy()
    print(f"[INFO]   After country filter: {len(df)} rows", file=sys.stderr)
    # 只保留核心暴力事件；drop non-core event types.

    df = df[df["event_type"].isin(CORE_VIOLENCE_TYPES)].copy()
    print(f"[INFO]   After event-type filter: {len(df)} rows", file=sys.stderr)
    # 同一事件只保留一次；deduplicate repeated ACLED event records.

    df = df.drop_duplicates(subset=["event_id_cnty"])
    print(f"[INFO]   After deduplication: {len(df)} rows", file=sys.stderr)
    # fatalities 转数值，event_date 转日期；coerce fatalities and dates.

    df["fatalities"] = pd.to_numeric(df["fatalities"], errors="coerce").fillna(0).astype(int)
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    # 无法解析日期的记录弃用；drop rows with invalid event dates.

    df = df.dropna(subset=["event_date"]).copy()
    # year_month 是月度聚合键；create the monthly grouping key.

    df["year_month"] = df["event_date"].dt.to_period("M").astype(str)
    # 国家映射到冲突区域；map countries into broader conflict regions.

    region_map = {
        "Ukraine": "Russia-Ukraine",
        "Russia": "Russia-Ukraine",
        "Israel": "Israel-Palestine",
        "Palestine": "Israel-Palestine",
        "Yemen": "Yemen",
    }
    df["conflict_region"] = df["country"].map(region_map)
    # 按月份和冲突区域汇总；aggregate by month and conflict region.
    # 同时统计事件数和死亡人数；count events and sum fatalities together.
    agg = (
        df.groupby(["year_month", "conflict_region"])
        .agg(
            event_count=("event_id_cnty", "count"),
            total_fatalities=("fatalities", "sum"),
        )
        .reset_index()
    )
    # 事件数宽表化；pivot event counts into one column per region.

    pivot_events = agg.pivot(
        index="year_month",
        columns="conflict_region",
        values="event_count",
    ).rename(columns=lambda col: f"{col.lower().replace('-', '_').replace(' ', '_')}_events")
    # 死亡人数也宽表化；pivot fatalities with matching column names.

    pivot_fatalities = agg.pivot(
        index="year_month",
        columns="conflict_region",
        values="total_fatalities",
    ).rename(columns=lambda col: f"{col.lower().replace('-', '_').replace(' ', '_')}_fatalities")
    # 合并事件与死亡表并补零；join the pivots and fill missing conflict counts.

    monthly = (
        pivot_events.join(pivot_fatalities)
        .fillna(0)
        .reset_index()
        .sort_values("year_month")
        .reset_index(drop=True)
    )

    _save_monthly(monthly, output_path, "ACLED")


# 数据源 2：EIA / Source 2: EIA
# EIA 清洗重点是归月和多列均值；normalize dates and average values by month.
def clean_eia(input_path: str, output_path: str) -> None:
    print("[INFO] Cleaning EIA data...", file=sys.stderr)

    if not _require_input(input_path, "Run src/get_data.py --source eia first."):
        return

    df = pd.read_csv(input_path, low_memory=False)
    print(f"[INFO]   Loaded {len(df)} raw rows", file=sys.stderr)
    # date 转日期并删除无效行；parse dates and drop invalid rows.
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()
    # 每日记录归并到月份；derive the month key from each date.
    df["year_month"] = df["date"].dt.to_period("M").astype(str)

    # 除日期键外的列都按数值指标处理；treat non-date columns as numeric series.
    value_columns = [col for col in df.columns if col not in {"date", "year_month"}]
    for col in value_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # 先按日期排序；sort before monthly aggregation.
    df = df.sort_values("date")
    # 同月多条记录按列取均值；average multiple rows within each month.

    monthly = (
        df.groupby("year_month")[value_columns]
        .mean()
        .reset_index()
        .sort_values("year_month")
        .reset_index(drop=True)
    )

    _save_monthly(monthly, output_path, "EIA")

# 数据源 3：黄金 / Source 3: Gold
# 黄金按月统计均值、最高和最低；summarize gold prices by monthly mean, max, and min.

def clean_gold(input_path: str, output_path: str) -> None:
    print("[INFO] Cleaning gold futures data...", file=sys.stderr)

    if not _require_input(input_path, "Run src/get_data.py --source gold first."):
        return

    df = pd.read_csv(input_path, low_memory=False)
    print(f"[INFO]   Loaded {len(df)} raw rows", file=sys.stderr)
    # 日期转好后归入月份；parse dates and assign month keys.

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()
    df["year_month"] = df["date"].dt.to_period("M").astype(str)
    # 动态寻找 close 价格列；detect the close-price column flexibly.

    close_column = next((col for col in df.columns if "close" in col.lower()), None)
    if close_column is None:
        print("[ERROR] No close-price column found in gold data.", file=sys.stderr)
        return
    # close 转数值并按日期排序；coerce close prices and sort by time.

    df[close_column] = pd.to_numeric(df[close_column], errors="coerce")
    df = df.dropna(subset=[close_column]).sort_values("date")
    # 每月输出均值和波动范围；keep mean, high, and low for each month.

    monthly = (
        df.groupby("year_month")
        .agg(
            gold_close_mean=(close_column, "mean"),
            gold_close_max=(close_column, "max"),
            gold_close_min=(close_column, "min"),
        )
        .reset_index()
        .sort_values("year_month")
        .reset_index(drop=True)
    )

    _save_monthly(monthly, output_path, "Gold")

# 数据源 4-6：铜、煤、氦 / Sources 4-6: Copper, coal, and helium
# 铜价使用通用价格清洗器；clean copper with the shared price-series helper.
def clean_copper(input_path: str, output_path: str) -> None:
    _clean_monthly_price_series(
        input_path=input_path,
        output_path=output_path,
        value_column="copper_usd_metric_ton",
        label="copper",
    )

# 煤价沿用同一清洗流程；clean coal with the same helper and a different value column.

def clean_coal(input_path: str, output_path: str) -> None:
    _clean_monthly_price_series(
        input_path=input_path,
        output_path=output_path,
        value_column="coal_australia_usd_metric_ton",
        label="coal",
    )

# 氦价也复用通用流程；clean helium through the shared helper.

def clean_helium(input_path: str, output_path: str) -> None:
    _clean_monthly_price_series(
        input_path=input_path,
        output_path=output_path,
        value_column="helium_usd_cubic_meter",
        label="helium",
    )
# 主流程 / Main
# 依次清洗六路数据；run each source cleaner in sequence.

def main() -> None:
    clean_acled(
        input_path=os.path.join(RAW_DIR, "acled_raw.csv"),
        output_path=os.path.join(PROCESSED_DIR, "acled_monthly.csv"),
    )
    clean_eia(
        input_path=os.path.join(RAW_DIR, "eia_energy.csv"),
        output_path=os.path.join(PROCESSED_DIR, "eia_monthly.csv"),
    )
    clean_gold(
        input_path=os.path.join(RAW_DIR, "gold_futures.csv"),
        output_path=os.path.join(PROCESSED_DIR, "gold_monthly.csv"),
    )
    clean_copper(
        input_path=os.path.join(RAW_DIR, "copper_fred.csv"),
        output_path=os.path.join(PROCESSED_DIR, "copper_monthly.csv"),
    )
    clean_coal(
        input_path=os.path.join(RAW_DIR, "coal_fred.csv"),
        output_path=os.path.join(PROCESSED_DIR, "coal_monthly.csv"),
    )
    clean_helium(
        input_path=os.path.join(RAW_DIR, "helium_usgs.csv"),
        output_path=os.path.join(PROCESSED_DIR, "helium_monthly.csv"),
    )
        # 清洗步骤完成；all source cleaners have run.

    print("[INFO] Cleaning step complete.", file=sys.stderr)

# 直接运行脚本时启动清洗；start cleaning only when executed as a script.
if __name__ == "__main__":
    main()