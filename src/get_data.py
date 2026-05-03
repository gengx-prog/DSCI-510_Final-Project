#!/usr/bin/env python3
"""
get_data.py - 下载冲突与商品价格项目的原始数据。
get_data.py - Download raw data for the conflict-commodity project.

数据源 / Sources:
  1. ACLED REST API    -> data/raw/acled_raw.csv
  2. EIA REST API v2   -> data/raw/eia_energy.csv
  3. Yahoo Finance     -> data/raw/gold_futures.csv
  4. FRED (copper)     -> data/raw/copper_fred.csv
  5. FRED (coal)       -> data/raw/coal_fred.csv
  6. USGS (helium)     -> data/raw/helium_usgs.csv

氦气说明 / Helium note:
  官方 API 不容易直接提供开放月度氦气现货数据。
  Open monthly helium spot data are not readily available from an official API.
  为保证可复现并使用官方来源，本脚本从 USGS PDF 提取年度氦价，
  再扩展为 2019-2025 的月度序列。
  To keep the project reproducible on official sources, this script extracts
  annual helium prices from USGS PDFs and expands them monthly for 2019-2025.

用法 / Usage:
    python src/get_data.py
    python src/get_data.py --source acled
    python src/get_data.py --source eia
    python src/get_data.py --source gold
    python src/get_data.py --source copper
    python src/get_data.py --source coal
    python src/get_data.py --source helium
"""

import argparse
from io import BytesIO, StringIO
import os
import re
import sys
import time

import pandas as pd
import requests
import yfinance as yf
from pypdf import PdfReader


# 配置 / Configuration
# 先定位项目根目录；set the project root before resolving data paths.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 原始数据统一落在这里；raw source files are written here.
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")

# 采集窗口固定在这些日期；these constants define the download range.
START_DATE = "2019-01-01"
END_DATE = "2025-12-31"
START_MONTH = "2019-01"
END_MONTH = "2025-12"
YFINANCE_END_EXCLUSIVE = "2026-01-01"

# ACLED 配置 / ACLED configuration
# 同时支持新旧认证；OAuth is preferred, key+email remains as fallback.
ACLED_OAUTH_TOKEN_URL = "https://acleddata.com/oauth/token"
ACLED_API_URL_NEW = "https://acleddata.com/api/acled/read"
ACLED_API_URL_LEGACY = "https://api.acleddata.com/acled/read"
ACLED_PAGE_SIZE = 500
# 只请求后续分析需要的 ACLED 字段；keep the payload focused on required columns.
ACLED_FIELDS = [
    "event_id_cnty",
    "event_date",
    "year",
    "event_type",
    "sub_event_type",
    "actor1",
    "actor2",
    "country",
    "region",
    "latitude",
    "longitude",
    "fatalities",
    "notes",
]
# 仅保留五个目标国家；limit ACLED pulls to the study conflicts.
# 这样减少数据量；this keeps downloads and cleaning manageable.
ACLED_TARGET_COUNTRIES = [
    "Ukraine",
    "Russia",
    "Israel",
    "Palestine",
    "Yemen",
]

# EIA 配置 / EIA configuration
# EIA 能源数据入口；base endpoint for energy series.
EIA_API_URL = "https://api.eia.gov/v2"
# 每个 EIA 序列声明路径、字段和时间范围；each series carries its route, label, and query facets.
EIA_SERIES = [
    {
        "route": "petroleum/pri/spt",
        "label": "wti_crude_usd_bbl",
        "frequency": "monthly",
        "value_field": "value",
        "start": START_MONTH,
        "end": END_MONTH,
        "facets": {"series": ["RWTC"]},
    },
    {
        "route": "petroleum/pri/spt",
        "label": "brent_crude_usd_bbl",
        "frequency": "monthly",
        "value_field": "value",
        "start": START_MONTH,
        "end": END_MONTH,
        "facets": {"series": ["RBRTE"]},
    },
    {
        "route": "petroleum/pri/spt",
        "label": "heating_oil_usd_gal",
        "frequency": "monthly",
        "value_field": "value",
        "start": START_MONTH,
        "end": END_MONTH,
        "facets": {"series": ["EER_EPD2F_PF4_Y35NY_DPG"]},
    },
    {
        "route": "natural-gas/pri/fut",
        "label": "henry_hub_gas_usd_mmbtu",
        "frequency": "monthly",
        "value_field": "value",
        "start": START_MONTH,
        "end": END_MONTH,
        "facets": {"series": ["RNGWHHD"]},
    },
]

# FRED 与 USGS 补充源 / FRED and USGS additions
# FRED 图表 CSV 是铜价和煤价入口；use the FRED graph CSV endpoint for commodity series.
FRED_GRAPH_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
COPPER_FRED_SERIES_ID = "PCOPPUSDM"
COAL_FRED_SERIES_ID = "PCOALAUUSDM"

# USGS 官方 PDF 来源；official PDFs used to extract annual helium prices.
HELIUM_USGS_SOURCE_URLS = {
    2019: "https://pubs.usgs.gov/periodicals/mcs2020/mcs2020.pdf",
    2020: "https://pubs.usgs.gov/periodicals/mcs2021/mcs2021.pdf",
    2021: "https://pubs.usgs.gov/periodicals/mcs2022/mcs2022-helium.pdf",
    2022: "https://pubs.usgs.gov/periodicals/mcs2023/mcs2023-helium.pdf",
    2023: "https://pubs.usgs.gov/periodicals/mcs2024/mcs2024-helium.pdf",
    2024: "https://pubs.usgs.gov/periodicals/mcs2025/mcs2025-helium.pdf",
    2025: "https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-helium.pdf",
}


# 工具函数 / Helpers
# 读取 .env 文件；load local environment variables when present.
# 如果项目根目录有 .env；merge KEY=VALUE pairs into os.environ.
def _load_env_file() -> None:
    """读取项目根目录 .env；load simple KEY=VALUE pairs if present."""
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as file_obj:
        for raw_line in file_obj:
            line = raw_line.strip()
            # 跳过空行、注释行和无效行；ignore blanks, comments, and malformed entries.
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # 只补充尚未设置的变量；do not override existing environment values.
            if key and key not in os.environ:
                os.environ[key] = value

# 启动时先尝试读取 .env；check for local secrets before building clients.
_load_env_file()

# 这些令牌分别用于 ACLED 和 EIA；credentials for ACLED and EIA access.
ACLED_EMAIL = os.environ.get("ACLED_EMAIL", "")
ACLED_PASSWORD = os.environ.get("ACLED_PASSWORD", "")    # 新 OAuth 方式 / New OAuth method
ACLED_API_KEY = os.environ.get("ACLED_API_KEY", "")      # 旧 key+email 方式 / Legacy key+email method
EIA_API_KEY = os.environ.get("EIA_API_KEY", "YOUR_EIA_API_KEY_HERE")

# 确保输出目录存在；create the parent directory before writing.
def _ensure_parent_dir(output_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

# 压平多层列名；flatten nested or tuple columns into simple names.
def _flatten_columns(columns) -> list[str]:
    flat = []
    for col in columns:
        if isinstance(col, tuple):
            parts = [str(part) for part in col if part not in (None, "")]
            flat.append("_".join(parts))
        else:
            flat.append(str(col))
            # 统一小写并替换空格；normalize column names to lowercase snake-like text.
    return [name.lower().replace(" ", "_") for name in flat]

# 年度值扩展到月度；repeat each annual observation across all months.
def _expand_annual_series_to_monthly(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """把年度值复制到当年 12 个月；repeat each annual value across its months."""
    expanded_rows = []
    for row in df.itertuples(index=False):
        year = int(str(row.date))
        value = getattr(row, label)
        # 同一年十二个月共享同一数值；copy the annual value into each month.
        for month in range(1, 13):
            expanded_rows.append(
                {
                    "date": f"{year}-{month:02d}-01",
                    label: value,
                }
            )
    return pd.DataFrame(expanded_rows)

# 清理 PDF 抽取文本；normalize odd characters before parsing.
def _normalize_pdf_text(text: str) -> str:
    normalized = (
        text.replace("＊", "'")
        .replace("’", "'")
        .replace("‘", "'")
        .replace("\u00a0", " ")
    )
    return re.sub(r"\s+", " ", normalized)

# 从 USGS 文本中解析氦价；extract helium prices from report text.
def _extract_helium_price_from_text(text: str) -> float:
    patterns = [
        r"estimated(?: base)? price for private industry.?s Grade\s*-\s*A helium was about \$([0-9]+(?:\.[0-9]+)?) per cubic meter",
        r"estimated(?: base)? price for private industry.?s Grade-A helium was about \$([0-9]+(?:\.[0-9]+)?) per cubic meter",
        r"Grade\s*-\s*A helium was about \$([0-9]+(?:\.[0-9]+)?) per cubic meter",
        r"Grade-A helium was about \$([0-9]+(?:\.[0-9]+)?) per cubic meter",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
        # 找不到价格时直接报错；raise clearly when the expected price pattern is missing.
    raise ValueError("Could not extract helium price from USGS PDF text.")

# 逐年下载 USGS 年鉴；pull annual helium prices from each PDF.
def _fetch_helium_annual_prices() -> dict[int, float]:
    annual_prices: dict[int, float] = {}

    for year, url in HELIUM_USGS_SOURCE_URLS.items():
        print(f"[INFO]   Fetching helium price for {year} from USGS...", file=sys.stderr)
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()

        reader = PdfReader(BytesIO(resp.content))
        text = " ".join(page.extract_text() or "" for page in reader.pages)
        price = _extract_helium_price_from_text(_normalize_pdf_text(text))
        annual_prices[year] = price
        # 请求之间短暂停顿；pause between PDF requests to be polite.
        time.sleep(0.2)

    return annual_prices


# 数据源 1：ACLED / Source 1: ACLED
# 先获取 OAuth 令牌；request a token before using the new ACLED API.
def _acled_get_oauth_token() -> str:
    """用 ACLED 账号换取 Bearer token；exchange username+password for a 24h token."""
    resp = requests.post(
        ACLED_OAUTH_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "username": ACLED_EMAIL,
            "password": ACLED_PASSWORD,
            "grant_type": "password",
            "client_id": "acled",
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise ValueError(f"No access_token in ACLED OAuth response: {resp.text}")
    return token

# 新接口使用 Bearer token 分页读取；page through events with OAuth auth.
def _acled_fetch_page_new(token: str, page: int) -> list[dict]:
    """从新 OAuth 接口抓一页全球事件；fetch one page from the new ACLED endpoint."""
    resp = requests.get(
        ACLED_API_URL_NEW,
        params={
            "_format": "json",
            "event_date": f"{START_DATE}|{END_DATE}",
            "event_date_where": "BETWEEN",
            "fields": "|".join(ACLED_FIELDS),
            "limit": ACLED_PAGE_SIZE,
            "page": page,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") not in (200, None):
        raise RuntimeError(f"ACLED API error on page {page}: {payload.get('error')}")
    return payload.get("data", [])

# 旧接口使用 key 与 email；fall back to legacy key+email auth.
def _acled_fetch_page_legacy(page: int) -> list[dict]:
    """从旧 key+email 接口抓一页全球事件；fetch one page from the legacy endpoint."""
    resp = requests.get(
        ACLED_API_URL_LEGACY,
        params={
            "key": ACLED_API_KEY,
            "email": ACLED_EMAIL,
            "event_date": f"{START_DATE}|{END_DATE}",
            "event_date_where": "BETWEEN",
            "fields": "|".join(ACLED_FIELDS),
            "limit": ACLED_PAGE_SIZE,
            "page": page,
        },
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != 200:
        raise RuntimeError(f"ACLED API error on page {page}: {payload.get('error')}")
    return payload.get("data", [])

# 分页抓取 ACLED 事件；download ACLED events page by page.
# 支持 2019-2025 全量与断点续传；cover 2019-2025 and resume from checkpoints.
def download_acled(output_path: str) -> None:
    """分页下载 2019-2025 全球 ACLED 事件；download all global events via pagination.

    支持断点续传：每 CHECKPOINT_EVERY 页保存一次进度。
    Supports resuming by saving progress every CHECKPOINT_EVERY pages.

    认证优先级 / Authentication priority:
      1. OAuth (ACLED_EMAIL + ACLED_PASSWORD) - new acleddata.com API
      2. Key+email (ACLED_EMAIL + ACLED_API_KEY) - legacy api.acleddata.com API

    这里不筛国家，后续由 clean_data.py 处理。
    Country filtering is intentionally omitted here; clean_data.py handles it.
    """
    CHECKPOINT_EVERY = 200  # 定期落盘页数；flush to disk every N pages, roughly 100K rows.

    _ensure_parent_dir(output_path)
    checkpoint_path = output_path + ".checkpoint"

    use_oauth = bool(ACLED_EMAIL and ACLED_PASSWORD)
    use_legacy = bool(ACLED_EMAIL and ACLED_API_KEY)
    # 没有任何凭证时停止；stop early if neither auth method is configured.

    if not use_oauth and not use_legacy:
        print(
            "[WARNING] ACLED credentials not set.\n"
            "  For OAuth (recommended): set ACLED_EMAIL and ACLED_PASSWORD in .env\n"
            "  For legacy API key:      set ACLED_EMAIL and ACLED_API_KEY in .env\n"
            "  Skipping ACLED download.",
            file=sys.stderr,
        )
        return

    # 若有检查点则续跑；resume from the saved checkpoint when available.
    start_page = 1
    if os.path.exists(checkpoint_path) and os.path.exists(output_path):
        with open(checkpoint_path, "r") as f:
            start_page = int(f.read().strip()) + 1
        existing_rows = sum(1 for _ in open(output_path)) - 1  # 扣掉 CSV 表头；subtract the header row from the previous count.
        print(
            f"[INFO] Resuming ACLED download from page {start_page} "
            f"({existing_rows} rows already saved).",
            file=sys.stderr,
        )
    else:
        print(
            f"[INFO] Downloading ALL global ACLED events ({START_DATE} – {END_DATE})...",
            file=sys.stderr,
        )

    token = None
    if use_oauth:
        print("[INFO]   Using OAuth (new acleddata.com API)...", file=sys.stderr)
        try:
            token = _acled_get_oauth_token()
            print("[INFO]   OAuth token obtained.", file=sys.stderr)
        except Exception as exc:
            print(
                f"[WARNING] OAuth token request failed: {exc}. "
                "Falling back to legacy key+email API.",
                file=sys.stderr,
            )
            use_oauth = False

    page = start_page
    total = 0
    write_header = not os.path.exists(output_path) or start_page == 1

    # 全新运行时移走旧文件；archive any old output before rewriting.
    if start_page == 1 and os.path.exists(output_path):
        os.remove(output_path)

    buffer: list[dict] = []
    # 批量写入缓冲区；flush buffered rows and save the checkpoint page.
    def _flush(buf: list[dict], last_page: int, header: bool) -> bool:
        if not buf:
            return header
        df = pd.DataFrame(buf)
        existing_fields = [f for f in ACLED_FIELDS if f in df.columns]
        df = df[existing_fields]
        df.to_csv(output_path, mode="a", index=False, header=header)
        with open(checkpoint_path, "w") as f:
            f.write(str(last_page))
        return False  # 表头已经写过；avoid writing the CSV header twice.

    while True:
        try:
            if use_oauth and token:
                rows = _acled_fetch_page_new(token, page)
            else:
                rows = _acled_fetch_page_legacy(page)
        except Exception as exc:
            print(f"[ERROR] Failed fetching page {page}: {exc}", file=sys.stderr)
            # 异常时先保存已抓数据；flush buffered rows before exiting on errors.
            write_header = _flush(buffer, page - 1, write_header)
            break
        # 空页表示已经到末尾；an empty page means the dataset is exhausted.
        if not rows:
            write_header = _flush(buffer, page - 1, write_header)
            break

        buffer.extend(rows)
        total += len(rows)
        print(f"[INFO]   Page {page:>4}: cumulative {total:>7} rows this session", file=sys.stderr)
        # 定期保存进度；flush at fixed page intervals for safer long runs.
        if page % CHECKPOINT_EVERY == 0:
            write_header = _flush(buffer, page, write_header)
            buffer = []
            print(f"[INFO]   Checkpoint saved at page {page}.", file=sys.stderr)
        # 未满一页即到末页；a short page means the final page was reached.
        if len(rows) < ACLED_PAGE_SIZE:
            write_header = _flush(buffer, page, write_header)
            buffer = []
            break

        page += 1
        time.sleep(0.3)

    # 成功后清理检查点；remove the checkpoint after a complete run.
    if os.path.exists(output_path):
        final_rows = sum(1 for _ in open(output_path)) - 1
        if os.path.exists(checkpoint_path):
            os.remove(checkpoint_path)
        print(f"[INFO] ACLED saved -> {output_path} ({final_rows} total rows)", file=sys.stderr)
    else:
        print("[ERROR] No ACLED data was fetched. Check credentials and date range.", file=sys.stderr)


# 数据源 2：EIA 能源价格 / Source 2: EIA energy prices
# 逐条抓取 EIA 序列；fetch each EIA series one by one.
def _fetch_eia_series(config: dict) -> pd.DataFrame:
    """抓取一个 EIA v2 序列；fetch one series and return [date, <label>]."""
    route = config["route"]
    label = config["label"]
    url = f"{EIA_API_URL}/{route}/data/"
    params = {
        "api_key": EIA_API_KEY,
        "frequency": config["frequency"],
        "data[0]": config["value_field"],
        "start": config["start"],
        "end": config["end"],
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 5000,
    }
    for facet_name, facet_values in config.get("facets", {}).items():
        for facet_value in facet_values:
            params[f"facets[{facet_name}][]"] = facet_value

    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    records = payload.get("response", {}).get("data", [])
    if not records:
        print(
            f"[WARNING] No EIA data returned for {label}",
            file=sys.stderr,
        )
        return pd.DataFrame(columns=["date", label])

    df = pd.DataFrame(records).rename(
        columns={"period": "date", config["value_field"]: label}
    )
    df = df[["date", label]].copy()
    df[label] = pd.to_numeric(df[label], errors="coerce")

    # 年频展开到月频，月频归一到月初；expand annual data or normalize monthly dates.
    if config.get("expand_annual_to_monthly"):
        df = _expand_annual_series_to_monthly(df.dropna(subset=[label]), label)
    elif config["frequency"] == "monthly":
        df["date"] = df["date"].astype(str) + "-01"
    elif config["frequency"] == "annual":
        df["date"] = df["date"].astype(str) + "-01-01"

    return df

# 合并多路 EIA 能源价格；combine all EIA series into one table.
def download_eia(output_path: str) -> None:
    """下载并合并 EIA 能源价格；download EIA series and merge into one CSV."""
    _ensure_parent_dir(output_path)

    if EIA_API_KEY == "YOUR_EIA_API_KEY_HERE":
        print("[WARNING] EIA_API_KEY not set; skipping EIA download.", file=sys.stderr)
        return

    print("[INFO] Downloading EIA energy price data...", file=sys.stderr)

    merged = None
    for config in EIA_SERIES:
        print(
            f"[INFO]   Fetching {config['label']} from {config['route']}",
            file=sys.stderr,
        )
        df = _fetch_eia_series(config)
        merged = df if merged is None else pd.merge(merged, df, on="date", how="outer")
        time.sleep(0.4)

    if merged is None:
        print("[WARNING] No EIA series were downloaded.", file=sys.stderr)
        return

    merged = merged.sort_values("date").reset_index(drop=True)
    merged.to_csv(output_path, index=False)
    print(f"[INFO] EIA saved -> {output_path} ({len(merged)} rows)", file=sys.stderr)


# 数据源 3：Yahoo Finance 黄金期货 / Source 3: Gold futures via Yahoo Finance
# 通过 Yahoo Finance 抓取金价日线；download daily gold futures prices.
def download_gold(output_path: str) -> None:
    """下载黄金期货日线 OHLCV；download daily gold futures OHLCV via yfinance."""
    _ensure_parent_dir(output_path)

    print("[INFO] Downloading gold futures (GC=F)...", file=sys.stderr)

    df = yf.download(
        "GC=F",
        start=START_DATE,
        end=YFINANCE_END_EXCLUSIVE,
        auto_adjust=True,
        progress=False,
    )
    if df.empty:
        print("[ERROR] yfinance returned no gold data for GC=F.", file=sys.stderr)
        return
    # 日期索引转列并压平列名；move the index to a date column and flatten columns.
    df.index.name = "date"
    df.columns = _flatten_columns(df.columns)
    df = df.reset_index()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    df.to_csv(output_path, index=False)
    print(f"[INFO] Gold saved -> {output_path} ({len(df)} rows)", file=sys.stderr)



# 数据源 4：FRED 铜价 / Source 4: Copper via FRED
# 铜价来自 FRED 官方序列；load the copper price series from FRED.
def download_copper(output_path: str) -> None:
    """下载 FRED 月度铜价；download monthly copper prices from FRED."""
    _ensure_parent_dir(output_path)

    print(
        "[INFO] Downloading copper prices from FRED "
        f"({COPPER_FRED_SERIES_ID})...",
        file=sys.stderr,
    )

    resp = requests.get(
        FRED_GRAPH_CSV_URL,
        params={"id": COPPER_FRED_SERIES_ID},
        timeout=60,
    )
    resp.raise_for_status()

    df = pd.read_csv(StringIO(resp.text))
    if df.empty:
        print("[ERROR] FRED returned no copper data.", file=sys.stderr)
        return
    # 自动识别 FRED 日期列；detect the date column name returned by FRED.
    date_column = next(
        (
            col
            for col in df.columns
            if str(col).strip().lower() in {"date", "observation_date"}
        ),
        None,
    )
    if date_column is None:
        raise ValueError("FRED copper download did not include a date column.")

    raw_value_col = [col for col in df.columns if col != date_column][0]
    df = df.rename(
        columns={
            date_column: "date",
            raw_value_col: "copper_usd_metric_ton",
        }
    )
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["copper_usd_metric_ton"] = pd.to_numeric(
        df["copper_usd_metric_ton"],
        errors="coerce",
    )
        # 只保留研究时段内记录；filter rows to the project date window.
    df = df[
        (df["date"] >= pd.Timestamp(START_DATE))
        & (df["date"] <= pd.Timestamp(END_DATE))
    ].copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    df.to_csv(output_path, index=False)
    print(f"[INFO] Copper saved -> {output_path} ({len(df)} rows)", file=sys.stderr)


# 数据源 5：FRED 煤价 / Source 5: Coal via FRED
# 煤价同样来自 FRED；load the coal series with its own series ID.

def download_coal(output_path: str) -> None:
    """下载 FRED 月度煤价；download monthly coal prices from FRED."""
    _ensure_parent_dir(output_path)

    print(
        "[INFO] Downloading coal prices from FRED "
        f"({COAL_FRED_SERIES_ID})...",
        file=sys.stderr,
    )

    resp = requests.get(
        FRED_GRAPH_CSV_URL,
        params={"id": COAL_FRED_SERIES_ID},
        timeout=60,
    )
    resp.raise_for_status()

    df = pd.read_csv(StringIO(resp.text))
    if df.empty:
        print("[ERROR] FRED returned no coal data.", file=sys.stderr)
        return
    # 识别日期列并重命名价格列；detect the date column and rename the value field.

    date_column = next(
        (
            col
            for col in df.columns
            if str(col).strip().lower() in {"date", "observation_date"}
        ),
        None,
    )
    if date_column is None:
        raise ValueError("FRED coal download did not include a date column.")

    raw_value_col = [col for col in df.columns if col != date_column][0]
    df = df.rename(
        columns={
            date_column: "date",
            raw_value_col: "coal_australia_usd_metric_ton",
        }
    )
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["coal_australia_usd_metric_ton"] = pd.to_numeric(
        df["coal_australia_usd_metric_ton"],
        errors="coerce",
    )
    df = df[
        (df["date"] >= pd.Timestamp(START_DATE))
        & (df["date"] <= pd.Timestamp(END_DATE))
    ].copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    df.to_csv(output_path, index=False)
    print(f"[INFO] Coal saved -> {output_path} ({len(df)} rows)", file=sys.stderr)

# 数据源 6：USGS 氦价 / Source 6: Helium via USGS annual prices
# 先取 USGS 年价再扩展到月度；parse annual prices and expand them monthly.

def download_helium(output_path: str) -> None:
    """从 USGS 年价构建月度氦价；build monthly helium from annual USGS PDF prices."""
    _ensure_parent_dir(output_path)

    print(
        "[INFO] Downloading helium prices from USGS PDF sources...",
        file=sys.stderr,
    )

    try:
        annual_prices = _fetch_helium_annual_prices()
    except Exception as exc:
        print(f"[ERROR] Failed to extract helium prices from USGS: {exc}", file=sys.stderr)
        return
    # 建月度索引并映射年价；map each month to its annual price and source URL.

    month_index = pd.date_range(start=START_DATE, end=END_DATE, freq="MS")
    df = pd.DataFrame({"date": month_index})
    df["source_year"] = df["date"].dt.year
    df["helium_usd_cubic_meter"] = df["source_year"].map(annual_prices)
    df["source_url"] = df["source_year"].map(HELIUM_USGS_SOURCE_URLS)
    df["price_basis"] = "usgs_pdf_annual_price_expanded_to_monthly"
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    # 若仍有缺口则提示解析失败；warn when some years could not be priced.

    if df["helium_usd_cubic_meter"].isna().any():
        missing_years = sorted(df.loc[df["helium_usd_cubic_meter"].isna(), "source_year"].unique())
        raise ValueError(f"Missing helium annual prices for years: {missing_years}")

    df.to_csv(output_path, index=False)
    print(f"[INFO] Helium saved -> {output_path} ({len(df)} rows)", file=sys.stderr)

# 命令行入口 / CLI

# 主入口配置可选数据源；choose one source or run all sources.
# 支持单源运行，也支持一次抓全；allow targeted or full downloads.

def main() -> None:
    parser = argparse.ArgumentParser(description="Download raw data for the project")
    parser.add_argument(
        "--source",
        choices=["acled", "eia", "gold", "copper", "coal", "helium", "all"],
        default="all",
        help="Which source to download (default: all)",
    )
    args = parser.parse_args()
    # 先创建 raw 目录；make sure the raw-data folder exists.
    os.makedirs(RAW_DIR, exist_ok=True)

    if args.source in ("acled", "all"):
        download_acled(os.path.join(RAW_DIR, "acled_raw.csv"))

    if args.source in ("eia", "all"):
        download_eia(os.path.join(RAW_DIR, "eia_energy.csv"))

    if args.source in ("gold", "all"):
        download_gold(os.path.join(RAW_DIR, "gold_futures.csv"))

    if args.source in ("copper", "all"):
        download_copper(os.path.join(RAW_DIR, "copper_fred.csv"))

    if args.source in ("coal", "all"):
        download_coal(os.path.join(RAW_DIR, "coal_fred.csv"))

    if args.source in ("helium", "all"):
        download_helium(os.path.join(RAW_DIR, "helium_usgs.csv"))

    # 全部下载完成提示；print a completion message.
    print("[INFO] Download step complete.", file=sys.stderr)

# 仅直接运行脚本时执行主程；run main only when invoked as a script.
if __name__ == "__main__":
    main()