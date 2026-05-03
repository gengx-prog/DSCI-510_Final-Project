# 示例 shebang / Example shebang: #!/usr/bin/env python3
# 文件说明开始 / File notes start
# 抓取范围为 2019-2025；the API returns up to 500 rows per page, so pagination is used.

# 常用跑法 / Common usage
# 示例命令 / Example command: python scraper.py
# 默认输出完整 CSV 到终端；by default, stream all rows to stdout.

# 示例命令 / Example command: python scraper.py --scrape 10
# 只抓前 10 条用于检查；fetch the first 10 rows for a quick data check.

# 示例命令 / Example command: python scraper.py --save my_data.csv
# 全量抓取后保存为 CSV；save the full pull to a local CSV file.

# 运行前需要两个环境变量；set these environment variables before running.
# 环境变量 / Environment variable: ACLED_API_KEY
# 环境变量 / Environment variable: ACLED_EMAIL
# 文件说明结束 / File notes end

import sys
import argparse
import csv
import io
import os

import requests

# 当前脚本目录；used when loading .env.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ACLED 读取接口；ACLED read API endpoint.
ACLED_API_URL = "https://api.acleddata.com/acled/read"

PAGE_SIZE = 500          # 单次请求上限为 500；official page-size limit is 500.
START_DATE = "2019-01-01" # 时间范围先固定；parameterize later if the study window changes.
END_DATE   = "2025-12-31"

# 只保留后续分析字段；avoid pulling unused ACLED columns.
FIELDS = [
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


def _load_env_file() -> None:
    # 简单读取 .env；load the small project .env file.
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as file_obj:
        for raw_line in file_obj:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:  # 跳过空行、注释和异常格式；skip blanks, comments, and malformed lines.
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")  # 不覆盖已有系统环境变量；preserve environment values already set.
            if key and key not in os.environ:
                os.environ[key] = value


_load_env_file()  # 优先从 .env 读取配置；try local configuration first.

ACLED_API_KEY = os.environ.get("ACLED_API_KEY", "YOUR_API_KEY_HERE")  # 缺少配置时先用占位值；placeholder values trigger a runtime warning.
ACLED_EMAIL = os.environ.get("ACLED_EMAIL", "YOUR_EMAIL_HERE")

# 核心 API 工具函数 / Core API helpers
# 组装请求参数；prepare request parameters for API calls.
def _build_params(page: int, limit: int) -> dict:  # 组装请求参数；prepare request parameters for API calls.
    return {
        "key":              ACLED_API_KEY,
        "email":            ACLED_EMAIL,
        "event_date":       f"{START_DATE}|{END_DATE}",
        "event_date_where": "BETWEEN",
        "fields":           "|".join(FIELDS),
        "limit":            limit,
        "page":             page,
    }


def fetch_page(page: int, limit: int = PAGE_SIZE) -> list:
    # 抓取单页 ACLED 事件；fetch one page of ACLED event rows.
    params = _build_params(page, limit)
    try:  # 设置超时避免请求卡住；set a timeout so requests cannot hang forever.
        resp = requests.get(ACLED_API_URL, params=params, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[ERROR] ACLED API request failed: {exc}", file=sys.stderr)
        sys.exit(1)

    payload = resp.json()
    if payload.get("status") != 200:  # HTTP 成功也可能有 API 级错误；check ACLED status inside the JSON payload.
        msg = payload.get("error", "Unknown API error")
        print(f"[ERROR] ACLED API returned error: {msg}", file=sys.stderr)
        sys.exit(1)

    return payload.get("data", [])


def iter_events(max_events: int = None):
    # 事件迭代器说明开始 / Event iterator notes start
    # 逐条产出 ACLED 事件字典；yield ACLED event dictionaries one at a time.

    # max_events 存在时达到数量即停；stop after max_events rows when provided.
    # 按需分页避免多余请求；lazy pages keep --scrape N efficient.
    # 英文说明结束 / English notes end
# 中文说明开始 / Chinese notes start
# 一条一条产出数据；stream rows instead of loading everything into memory.
# 避免一次性装入所有页面；keeps memory use low for large pulls.
# 中文说明结束 / Chinese notes end
    page = 1
    yielded = 0

    while True:
        # 只看前 N 条时减少请求量；limit requests when the user asked for N rows.
        if max_events is not None:
            remaining = max_events - yielded
            if remaining <= 0:
                return
            limit = min(PAGE_SIZE, remaining)
        else:
            limit = PAGE_SIZE

        rows = fetch_page(page, limit)
        if not rows:  # 空页通常代表数据结束；an empty page usually means the dataset is exhausted.
            return

        for row in rows:
            yield row
            yielded += 1
            if max_events is not None and yielded >= max_events:
                return

        # 未满页表示已经抓完；a short page means the dataset is exhausted.
        if len(rows) < limit:  # 未满页通常就是最后一页；a short page is normally the final page.
            return

        page += 1
        print(f"[INFO] Fetched page {page - 1} ({yielded} rows so far) ...",
              file=sys.stderr)


# 输出工具函数 / Output helpers

def _make_writer(fileobj):  # 统一 CSV 写出配置；centralize CSV writer settings.
    return csv.DictWriter(fileobj, fieldnames=FIELDS, extrasaction="ignore",
                          lineterminator="\n")


def print_as_csv(events):
    # 直接将结果输出为 CSV；write header and rows to stdout as CSV.
    writer = _make_writer(sys.stdout)
    writer.writeheader()
    for row in events:
        writer.writerow(row)


def save_to_file(path: str, events):
    # 将抓取结果保存为 CSV；save fetched events to a CSV file.
    abs_path = os.path.abspath(path)
    parent   = os.path.dirname(abs_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # 确保目标目录存在；create the target directory if needed.
    with open(abs_path, "w", newline="", encoding="utf-8") as fh:
        writer = _make_writer(fh)
        writer.writeheader()
        count = 0
        for row in events:
            writer.writerow(row)
            count += 1

    print(f"[INFO] Saved {count} rows to {abs_path}", file=sys.stderr)

# 命令行入口 / CLI entry point
def main():
    parser = argparse.ArgumentParser(
        description="Scrape ACLED armed conflict data via REST API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )  # scrape 和 save 互斥；only one of these two options can be used.
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--scrape", type=int, metavar="N",
        help="Print only the first N rows to stdout (efficient: stops early)",
    )
    group.add_argument(
        "--save", type=str, metavar="PATH",
        help="Save the complete dataset to PATH (CSV)",
    )
    args = parser.parse_args()
    # 缺少账号时先提醒；warn before the first real request if credentials are missing.
    if ACLED_API_KEY == "YOUR_API_KEY_HERE" or ACLED_EMAIL == "YOUR_EMAIL_HERE":
        print(
            "[WARNING] ACLED credentials not set.\n"
            "  Set environment variables ACLED_API_KEY and ACLED_EMAIL before running.\n"
            "  Register for free at https://acleddata.com/register/",
            file=sys.stderr,
        )

    if args.scrape is not None:
        print_as_csv(iter_events(max_events=args.scrape))
    elif args.save is not None:
        save_to_file(args.save, iter_events())
    else:
        print_as_csv(iter_events())


if __name__ == "__main__":
    main()
