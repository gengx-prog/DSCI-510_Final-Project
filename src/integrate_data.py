#!/usr/bin/env python3
"""
integrate_data.py - 将处理后的月度数据集合并为统一表。
integrate_data.py - Merge processed monthly datasets into a unified table.

输入文件 / Input files (data/processed/):
  acled_monthly.csv
  eia_monthly.csv
  gold_monthly.csv
  copper_monthly.csv
  coal_monthly.csv
  helium_monthly.csv

输出 / Output:
  data/processed/unified_monthly.csv

用法 / Usage:
    python src/integrate_data.py
"""

from __future__ import annotations

import os
import sys

import pandas as pd

# 寻山定穴：不管这脚本在哪个犄角旮旯跑，必须死死锚定根目录！
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 顺藤摸瓜找到藏经阁（处理过的数据全堆在这儿）
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")

def load_processed(filename: str) -> pd.DataFrame | None:
    # 招魂术：根据名字去硬盘深处把残卷挖出来
    path = os.path.join(PROCESSED_DIR, filename)
    # 缺文件时只警告；skip missing inputs without breaking the merge.
    if not os.path.exists(path):
        # 丑话说前面，文件要是丢了，我不报错，我只在标准错误流里bb两句。
 # 强行报错的话整个阵法就全毁了，忍一忍跳过算了。
        print(f"[WARNING] Missing processed file: {path}", file=sys.stderr)
        return None
 # 没丢的话就直接读，low_memory关掉，免得pandas天天在那瞎猜dtype弹warning
    return pd.read_csv(path, low_memory=False)

def integrate() -> pd.DataFrame:
    # 开启六道轮回大阵！
    print("[INFO] Integrating processed datasets...", file=sys.stderr)

     # 六路神仙各显神通。找不到的就当它羽化了（返回 None）。
    datasets = {
        "ACLED": load_processed("acled_monthly.csv"),
        "EIA": load_processed("eia_monthly.csv"),
        "Gold": load_processed("gold_monthly.csv"),
        "Copper": load_processed("copper_monthly.csv"),
        "Coal": load_processed("coal_monthly.csv"),
        "Helium": load_processed("helium_monthly.csv"),
    }

     # 铸造主心骨：强行拉出一条从 2019-01 到 2025-12 的时间灵脉。
 # 少一个月都不行，防止有的数据集缺胳膊少腿导致时间轴断裂。
    all_months = pd.period_range("2019-01", "2025-12", freq="M").astype(str)
     # 建个空壳子DataFrame，只有时间轴
    unified = pd.DataFrame({"year_month": all_months})

     # 开始疯狂吸星大法 (Left Join)
    for label, df in datasets.items():
        # 缺失的数据源直接跳过；skip sources that were not loaded.
        if df is None:
            continue# 没这号人？下一位！
        # 死死咬住 year_month 这个阵眼，把其他表的数据全吸过来。
 # 必须用 left join！以我们自己捏的时间轴为尊！
        unified = unified.merge(df, on="year_month", how="left")
         # 顺手记一笔账，省得合半天不知道合进去了啥玩意
        print(f"[INFO]   Merged {label}: {len(df)} rows", file=sys.stderr)

    # 清点杀孽：把那些带血的列全揪出来（死人_fatalities 和 打架_events）
    conflict_columns = [
        col
        for col in unified.columns
        if col.endswith("_events") or col.endswith("_fatalities")
    ]
    # 慈悲为怀：如果某个月没打架数据（原来是 NaN），那就强行当成 0（太平无事）。
 # NaN 留着后面跑模型绝对要走火入魔！
    if conflict_columns:
        unified[conflict_columns] = unified[conflict_columns].fillna(0)

    # 运功调息：把时间轴重新捋顺，免得被前后的乱序搞死
    unified = unified.sort_values("year_month").reset_index(drop=True)

    # 炼丹出炉，直接拍到硬盘上
    output_path = os.path.join(PROCESSED_DIR, "unified_monthly.csv")
    unified.to_csv(output_path, index=False)
    print(
        f"[INFO] Unified dataset saved -> {output_path} "
        f"({len(unified)} rows x {len(unified.columns)} columns)",
        file=sys.stderr,
    )
    # 查房时间：看看有没有什么妖魔鬼怪的 dtype
    print("\n[INFO] Column types:", file=sys.stderr)
    print(unified.dtypes.to_string(), file=sys.stderr)
    # 掐指一算，寿命范围对不对
    print(
        f"\n[INFO] Date range: {unified['year_month'].iloc[0]} to "
        f"{unified['year_month'].iloc[-1]}",
        file=sys.stderr,
    )
     # 漏风检测：看看各路数据里藏了多少 NaN 填不满的坑
    print("[INFO] Non-null counts:", file=sys.stderr)
    print(unified.notna().sum().to_string(), file=sys.stderr)
     # 返回这个庞然大物，交差！
    return unified

# 主入口 / Main entry point
# 直接运行时执行 integrate；call integrate when this file is invoked directly.
def main() -> None:
     # 废话不多说，开坛！
    integrate()
    # 打印整合完成信息；log completion.
    print("[INFO] Integration step complete.", file=sys.stderr)

# 防御性咒语：防止被别人当模块 import 时瞎运行
if __name__ == "__main__":
    main()