#!/usr/bin/env python3
"""
analyze_visualize.py - 【绝密】老夫熬了三个通宵推演的《九州物价与刀兵劫数考》。
别乱动这里面的阵法！主要是拿来算打仗怎么影响黑市行情的。

咱们这门手艺，分三步走：
 第一步：画那个什么皮尔逊阴阳八卦图（错位相关热力图）。
 第二步：把各地堂口的仇杀记录，跟灵石法宝的黑市价放在一起过过招（区域冲突与指数化商品价格对比）。
 第三步：抓那些引发天地异象的导火索（关键升级事件窗口异常检测）。

要是想催动阵法，在终端里捏这几个诀：
 python src/analyze_visualize.py
 python src/analyze_visualize.py --analysis correlation
 python src/analyze_visualize.py --analysis comparison
 python src/analyze_visualize.py --analysis anomaly
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings

import matplotlib
# 给画师喂一副哑药。老夫搞推演向来闷声发大财，别弹窗出来烦人（无界面后端）。
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import grangercausalitytests, adfuller
# 闭上耳朵，眼不见心不烦！把那些鸡毛蒜皮的报错全给老夫按死（压制警告）。
warnings.filterwarnings("ignore")


# ---------------------------------------------------------
# 【卷一：定龙脉，找堂口】 
# ---------------------------------------------------------
# 狡兔三窟，先把咱的家底和出货的位置踩好点。
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
FIGURES_DIR = os.path.join(BASE_DIR, "results", "figures")
# 要是连个放图纸的暗阁都没有，老夫就当场开辟一个（建文件夹）。
os.makedirs(FIGURES_DIR, exist_ok=True)

# ---------------------------------------------------------
# 【卷二：天下英雄（和倒霉蛋）花名册】
# ---------------------------------------------------------

# 乱世榜：看清楚了，哪家地盘在火拼，对应咱库房里的哪本账册。
CONFLICT_COLS = {
    "Russia-Ukraine": "russia_ukraine_events",# 罗刹与乌孙的恩怨局
    "Israel-Palestine": "israel_palestine_events",# 圣地百年血仇
    "Yemen": "yemen_events",# 也门风沙里的乱战
}
# 阎王帖：这列专门记刀下亡魂的数量，造孽啊……

FATALITY_COLS = {
    "Russia-Ukraine": "russia_ukraine_fatalities",
    "Israel-Palestine": "israel_palestine_fatalities",
    "Yemen": "yemen_fatalities",
}
# 黑市奇珍录：天下熙熙皆为利来，这些个天材地宝的洋文名字都给老夫对上号！

COMMODITY_COLS = {
    "WTI Crude ($/bbl)": "wti_crude_usd_bbl",# 西洋黑血（原油）
    "Brent Crude ($/bbl)": "brent_crude_usd_bbl",# 北海黑血
    "Henry Hub Gas ($/mmBtu)": "henry_hub_gas_usd_mmbtu", # 幽冥地气
    "Heating Oil ($/gal)": "heating_oil_usd_gal", # 纯阳灵液（取暖油）
    "Coal, Australia ($/metric ton)": "coal_australia_usd_metric_ton", # 南洋黑火石
    "Gold ($/oz)": "gold_close_mean",# 真金白银，永远的神！
    "Copper ($/metric ton)": "copper_usd_metric_ton",# 紫极魔铜
    "Helium ($/m^3)": "helium_usd_cubic_meter",# 浮空仙气（氦气）
}
# 天地大劫记事本：啥时候打得最凶？就在这几个月，插个眼做标记。
ESCALATION_EVENTS = {
    "2021-03": "Yemen escalation",# 辛丑年春，也门大乱
    "2022-02": "Russia-Ukraine escalation", # 壬寅年初，罗刹兵锋乍起
    "2023-10": "Israel-Hamas escalation",# 癸卯年秋，圣地业火重燃
}
# 风水羁绊：哪块地盘见血，哪样宝贝就要涨价，这里头的水深着呢！

REGION_PRICE_CONFIGS = {
    "Russia-Ukraine": [
        "wti_crude_usd_bbl",
        "brent_crude_usd_bbl",
        "copper_usd_metric_ton",
    ],
    "Israel-Palestine": [
        "gold_close_mean",
        "copper_usd_metric_ton",
        "helium_usd_cubic_meter",
    ],
    "Yemen": [
        "gold_close_mean",
        "brent_crude_usd_bbl",
        "helium_usd_cubic_meter",
    ],
}
# 各派法宝的本命灵光（线条颜色配置）。
# 记住，这些护体神光千万别乱改！不然真气逆流，画出来的阵图比走火入魔还难看！
SERIES_COLORS = {
    "wti_crude_usd_bbl": "#1f77b4", # 幽蓝水行真气
    "brent_crude_usd_bbl": "#ff7f0e", # 纯阳烈火真气
    "henry_hub_gas_usd_mmbtu": "#2ca02c",# 枯木逢春真气
    "heating_oil_usd_gal": "#9467bd",# 紫气东来
    "coal_usd_ton": "#8c564b",# 厚土玄黄
    "gold_close_mean": "#bc8f00",# 庚金剑芒
    "copper_usd_metric_ton": "#b45f06",# 铜皮铁骨
    "helium_usd_cubic_meter": "#17becf",# 冰风怒吼
}


# ---------------------------------------------------------
# 【杂学与左道】/ Helper Functions (The Miscellaneous Arts)
# ---------------------------------------------------------

# 去总舵的藏经阁把那本《九州万邦月度总账》拿来（读取统一月度表）。
def load_unified() -> pd.DataFrame:
    path = os.path.join(PROCESSED_DIR, "unified_monthly.csv")
    # 找不到账本？那还推演个屁！直接拔剑自刎吧（文件不存在则报错退出）。
    if not os.path.exists(path):
        print(
            f"[ERROR] {path} not found. Run src/integrate_data.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    df = pd.read_csv(path, low_memory=False)
         # 给岁月打上烙印，把干巴巴的甲子纪年变成能推演天机的时辰（生成日期列）。
    df["year_month"] = df["year_month"].astype(str)
    df["date"] = pd.to_datetime(df["year_month"], format="%Y-%m", errors="coerce")
    return df

 # 验明正身！点名看看哪些堂口被灭了（列不存在），没被灭的活口才留下来听用。
def _available_mapping(df: pd.DataFrame, mapping: dict[str, str]) -> dict[str, str]:
    return {label: col for label, col in mapping.items() if col in df.columns}

# 万法归宗，九九归一（将序列指数化到起点 100）。
# 不管你原来是天价神兵还是地摊破铜烂铁，起手式全给老夫压到一百点内力，这样才好上擂台比拼！
def _index_to_100(series: pd.Series) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=series.index)
    base = valid.iloc[0]
     # 要是起手连点内力都没有（底数为0或空），那就直接是个废人。
    if pd.isna(base) or base == 0:
        return pd.Series(np.nan, index=series.index)
    return series / base * 100

# 易容术：把那些乱七八糟的江湖黑话（内部字段名）翻译成人话，免得外门弟子看不懂。
def _prettify_column(column: str) -> str:
    for label, col in COMMODITY_COLS.items():
        if col == column:
            return label
    return column.replace("_", " ")

# 往比武擂台（图表）上插引雷针（在图中标记关键事件）。
# 哪天打得最凶，老夫就在哪天画条血线立下生死状！
def _add_event_markers(ax: plt.Axes) -> None:
    ymin, ymax = ax.get_ylim()
     # 找个高处挂牌子。
    label_height = ymax - (ymax - ymin) * 0.05
    for year_month, label in ESCALATION_EVENTS.items():
        event_date = pd.to_datetime(year_month, format="%Y-%m")
        ax.axvline(event_date, color="#d62728", linestyle="--", linewidth=1, alpha=0.45)
        ax.text(
            event_date,
            label_height,
            label,
            rotation=90,
            va="top",
            ha="right",
            fontsize=7,
            color="#8c1d1d",
        )


# ---------------------------------------------------------
# 【第一门绝学：隔山打牛】/ Analysis 1: Cross-lag correlation
# ---------------------------------------------------------

# 看看是这边刚一亮剑见血（冲突），那边黑市的物价是不是隔了几个月才开始作妖（滞后 0、1、2 个月）。
def analysis_correlation(df: pd.DataFrame) -> pd.DataFrame:
    print("\n=== Analysis 1: Cross-Lag Pearson Correlation ===")

    available_conflicts = _available_mapping(df, CONFLICT_COLS)
    available_commodities = _available_mapping(df, COMMODITY_COLS)
     # 要是连兵器和对手都凑不齐，这架没法打，直接散伙！（可用列不足时退出）
    if not available_conflicts or not available_commodities:
        print("  Not enough conflict or commodity columns available for correlation.")
        return pd.DataFrame()
 # 蓄力期：当场发作、憋一个月、憋两个月。
    lags = [0, 1, 2]
    results = []
   # 天罡三十六阵，套地煞七十二阵！老夫设下这三重连环死局。
 # 别跟我提什么代码复杂度，第一层套堂口，第二层套法宝，第三层看时辰。
 # 哪个小兔崽子敢说这嵌套循环写得丑，老夫一巴掌拍碎他的天灵盖！
    for region_label, conflict_col in available_conflicts.items():
        for commodity_label, commodity_col in available_commodities.items():
            for lag in lags:
                                # 乾坤大挪移！把未来的黑市账本硬生生扯到现在来对质！
 # 别问为什么用shift(-lag)，因果律武器懂不懂？打仗是因，涨价是果！
                shifted = df[commodity_col].shift(-lag)
                # 把两个死对头关进同一个铁笼子（DataFrame）。
 # 那些缺胳膊少腿的残废数据（dropna），直接扔进化尸水里化掉！留着过年吗？！
                pair = pd.DataFrame(
                    {
                        "conflict": pd.to_numeric(df[conflict_col], errors="coerce"),
                        "commodity": pd.to_numeric(shifted, errors="coerce"),
                    }
                ).dropna()
                # 打擂台连十招都撑不过的弱鸡？直接滚！（样本太少算个屁）
                if len(pair) < 10:
                    continue
                 # 要是俩人站着一动不动装死（方差为0，没波动），那还算个毛的卦！浪费老夫真气！
                if pair["conflict"].std() == 0 or pair["commodity"].std() == 0:
                    continue

                r_value, p_value = stats.pearsonr(pair["conflict"], pair["commodity"])
                 # 赶紧把这卦象抄在竹简上，免得待会忘了。
                results.append(
                    {
                        "Conflict Region": region_label, # 哪块地盘见血了
                        "Commodity": commodity_label,# 哪件宝贝被炒起来了
                        "Lag (months)": lag,# 憋了几个月的内伤
                        "Pearson r": round(r_value, 3),# 孽缘指数（越大越邪门）
                        "p-value": round(p_value, 4),# 遭天谴的概率
                        "Significant": p_value < 0.05,# 算不算大凶之兆？低于一分五厘就算！
                    }
                )

    result_df = pd.DataFrame(results)
    if result_df.empty:
        print("  No correlation results were produced.")
        return result_df
   # 把那些真正能引发天地异象的大凶卦象挑出来挂在城墙上示众！

    significant = result_df[result_df["Significant"]]
    if significant.empty:
        print("  No statistically significant pairs at p < 0.05.")
    else:
        print(significant.to_string(index=False))
     # 掏出朱砂笔，老夫要画符了！（画几个滞后热力图）
 # 搞个一字长蛇阵，有几个时辰就摆几个阵盘。
    fig, axes = plt.subplots(1, len(lags), figsize=(22, 5), sharey=True)
    if len(lags) == 1:
        axes = [axes]
 # 挨个往阵眼里面灌注真气……
    for axis, lag in zip(axes, lags):
        lag_df = result_df[result_df["Lag (months)"] == lag].pivot(
            index="Conflict Region",
            columns="Commodity",
            values="Pearson r",
        )
 # 阵眼要是空的，就贴个狗皮膏药。
        if lag_df.empty:
            axis.text(0.5, 0.5, "No data", ha="center", va="center")
            axis.set_axis_off()
            continue
 # 催动离火玄冰大阵！（生成热力图）
 # 越红说明杀气越重，越蓝说明被吸干了阳气！
        sns.heatmap(
            lag_df,
            ax=axis,
            annot=True,
            fmt=".2f",
            center=0,
            cmap="RdBu_r",
            vmin=-0.7,
            vmax=0.7,
            linewidths=0.5,
            cbar=(lag == lags[-1]),
        )
        axis.set_title(f"Lag {lag} month" + ("" if lag == 1 else "s"))
        axis.set_xlabel("")
        axis.set_ylabel("Conflict Region" if lag == 0 else "")
 # 给这幅鬼画符题个狂草牌匾！
    fig.suptitle("Conflict Intensity vs. Commodity Prices (2019-2025)", fontsize=14)
    plt.tight_layout()
    output_path = os.path.join(FIGURES_DIR, "fig1_correlation_heatmap.png")
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Figure saved -> {output_path}")

    return result_df



# ---------------------------------------------------------
# 【第二门邪术：双目失明术】/ Analysis 2: Regional comparison
# ---------------------------------------------------------
# 左眼贪财，右眼看杀！同图对照各州府的拼杀烈度与宝贝涨跌。
def analysis_comparison(df: pd.DataFrame) -> None:
    print("\n=== Analysis 2: Regional Conflict vs. Commodity Comparison ===")

    available_conflicts = _available_mapping(df, CONFLICT_COLS)
    if not available_conflicts:
        print("  Conflict columns are missing; skipping comparison figure.")
        return
     # 老夫大手一挥，直接搭起三层楼的生死大擂台！
 # 左边算盘响（看价格），右边刀剑盲（看冲突）。
    fig, axes = plt.subplots(3, 2, figsize=(17, 14), sharex=True)

    for row_index, region in enumerate(CONFLICT_COLS):
        event_col = CONFLICT_COLS[region]
        fatality_col = FATALITY_COLS[region]
        # 扒出这个堂口最关心的几样宝贝，不是什么垃圾都配上桌的。
        commodity_cols = [
            column
            for column in REGION_PRICE_CONFIGS[region]
            if column in df.columns
        ]

        left_axis = axes[row_index, 0]# 左护法管账
        right_axis = axes[row_index, 1]# 右护法管杀人

        plotted_left = False
        for column in commodity_cols:
        # 散去多余功力！不管你是黄金还是烂煤，上台前全给老夫压到一百点内力起步！
            indexed = _index_to_100(pd.to_numeric(df[column], errors="coerce"))
            if indexed.notna().sum() == 0:
                continue
             # 泼墨挥毫，画出灵石法宝的诡异K线！
            left_axis.plot(
                df["date"],
                indexed,
                label=_prettify_column(column),
                linewidth=1.8,
                color=SERIES_COLORS.get(column),
            )
            plotted_left = True
 # 要是有宝贝画上去了，就给老夫立个字号（图例）。
        if plotted_left:
            left_axis.legend(fontsize=8, loc="upper left")
        else:
            left_axis.text(0.5, 0.5, "No commodity data", ha="center", va="center")

        left_axis.set_title(f"{region}: Indexed Commodity Prices")
        left_axis.set_ylabel("Indexed price (first value = 100)")
        left_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
         # 往天上扔引
        _add_event_markers(left_axis)
        # 擦！要在正中央挂这面染血的战旗了！（主轴画厮杀次数，大面积涂色）
        # 看看这堂口的生死簿还在不在...
        if event_col in df.columns:
            events = pd.to_numeric(df[event_col], errors="coerce").fillna(0)
            right_axis.fill_between(
                df["date"],
                events,
                color="#9ecae1",
                alpha=0.6,
                label="Monthly events",
            )
            right_axis.plot(df["date"], events, color="#08519c", linewidth=1.3)
        else:
            # 没数据？没数据玩个毛啊！
            right_axis.text(0.5, 0.5, "No event data", ha="center", va="center")

        right_axis.set_title(f"{region}: Conflict Intensity")
        right_axis.set_ylabel("Monthly events")
        right_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        _add_event_markers(right_axis)
         #如果有伤亡数据，加个副轴（twinx）。
 # 之前嫌只看事件数不够直观，所以临时补的这个维度
        if fatality_col in df.columns:
            fatalities = pd.to_numeric(df[fatality_col], errors="coerce")
            twin_axis = right_axis.twinx()
             # 随便画个虚线就行，免得喧宾夺主
            twin_axis.plot(
                df["date"],
                fatalities,
                color="#333333",
                linestyle=":",
                linewidth=1.1,
            )
            twin_axis.set_ylabel("Fatalities", fontsize=8)
            twin_axis.tick_params(axis="y", labelsize=7)
 # 底部x轴统一加个Year，不然一堆数字挤在一起没法看
    for axis in axes[-1, :]:
        axis.set_xlabel("Year")
 # 起个大标题
    fig.suptitle("Regional Conflict Intensity vs. Indexed Commodity Prices", fontsize=14)
    plt.tight_layout()
    output_path = os.path.join(FIGURES_DIR, "fig2_conflict_comparison.png")
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Figure saved -> {output_path}")


# 分析 3：异常检测 / Analysis 3: Anomaly detection

# 关注事件窗口中的价格异动；look for price anomalies around escalations.
# 在重大事件前后比较平时基线；compare event windows with pre-event baselines.
def analysis_anomaly(df: pd.DataFrame) -> None:
    print("\n=== Analysis 3: Event-Window Anomaly Detection ===")
    # 预设重点案例、窗口和商品；define key cases, windows, and commodities.
    case_studies = {
        "Russia invasion (Feb 2022)": {
            "center": "2022-02",
            "window": ("2021-08", "2022-08"),
            "commodities": [
                "wti_crude_usd_bbl",
                "brent_crude_usd_bbl",
                "henry_hub_gas_usd_mmbtu",
                "gold_close_mean",
                "copper_usd_metric_ton",
                "helium_usd_cubic_meter",
            ],
        },
        "Israel-Hamas escalation (Oct 2023)": {
            "center": "2023-10",
            "window": ("2023-04", "2024-04"),
            "commodities": [
                "gold_close_mean",
                "brent_crude_usd_bbl",
                "wti_crude_usd_bbl",
                "copper_usd_metric_ton",
                "helium_usd_cubic_meter",
            ],
        },
    }

    fig, axes = plt.subplots(len(case_studies), 2, figsize=(16, 10))
    if len(case_studies) == 1:
        axes = np.array([axes])

    for row_index, (case_name, config) in enumerate(case_studies.items()):
        center_date = pd.to_datetime(config["center"], format="%Y-%m")
        window_start = pd.to_datetime(config["window"][0], format="%Y-%m")
        window_end = pd.to_datetime(config["window"][1], format="%Y-%m")
        available_columns = [col for col in config["commodities"] if col in df.columns]

        if not available_columns:
            axes[row_index, 0].text(0.5, 0.5, "No commodity data", ha="center", va="center")
            axes[row_index, 0].set_axis_off()
            axes[row_index, 1].text(0.5, 0.5, "No commodity data", ha="center", va="center")
            axes[row_index, 1].set_axis_off()
            continue
        # 事件窗与前 12 个月基线分开；use the event window and a 12-month baseline.
        window_df = df[(df["date"] >= window_start) & (df["date"] <= window_end)].copy()
        baseline_df = df[
            (df["date"] < center_date)
            & (df["date"] >= center_date - pd.DateOffset(months=12))
        ].copy()

        left_axis = axes[row_index, 0]
        right_axis = axes[row_index, 1]
        # 左图展示事件窗指数走势；left panel shows indexed prices in the event window.
        for column in available_columns:
            indexed = _index_to_100(pd.to_numeric(window_df[column], errors="coerce"))
            if indexed.notna().sum() == 0:
                continue
            left_axis.plot(
                window_df["date"],
                indexed,
                label=_prettify_column(column),
                linewidth=1.5,
                color=SERIES_COLORS.get(column),
            )

        left_axis.axvline(center_date, color="#d62728", linestyle="--", linewidth=1.4)
        left_axis.set_title(f"{case_name}: Indexed prices")
        left_axis.set_ylabel("Indexed price (window start = 100)")
        left_handles, left_labels = left_axis.get_legend_handles_labels()
        if left_handles:
            left_axis.legend(fontsize=7, loc="upper left")
        left_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        plt.setp(left_axis.xaxis.get_majorticklabels(), rotation=30, ha="right")
        # 右图用前期均值和标准差算 z-score；right panel computes z-scores from the baseline.

        for column in available_columns:
            baseline_series = pd.to_numeric(baseline_df[column], errors="coerce").dropna()
            series = pd.to_numeric(window_df[column], errors="coerce")
            if len(baseline_series) < 3:
                continue

            baseline_mean = baseline_series.mean()
            baseline_std = baseline_series.std()
            if pd.isna(baseline_std) or baseline_std == 0:
                continue

            z_scores = (series - baseline_mean) / baseline_std
            z_col = f"{column}_z"
            window_df[z_col] = z_scores

            right_axis.plot(
                window_df["date"],
                z_scores,
                label=_prettify_column(column),
                linewidth=1.5,
                color=SERIES_COLORS.get(column),
            )
            # |z| 超过 2 视为明显异动；flag values with absolute z-score above 2.
            anomalies = window_df.loc[z_scores.abs() > 2, ["year_month", z_col]]
            if not anomalies.empty:
                print(f"  {case_name} anomalies for {_prettify_column(column)}:")
                print(anomalies.to_string(index=False))

        right_axis.axvline(center_date, color="#d62728", linestyle="--", linewidth=1.4)
        right_axis.axhline(0, color="#222222", linewidth=0.8)
        right_axis.axhline(2, color="#7f7f7f", linestyle=":", linewidth=1)
        right_axis.axhline(-2, color="#7f7f7f", linestyle=":", linewidth=1)
        right_axis.set_title(f"{case_name}: Z-scores vs. prior 12 months")
        right_axis.set_ylabel("Z-score")
        right_handles, right_labels = right_axis.get_legend_handles_labels()
        if right_handles:
            right_axis.legend(fontsize=7, loc="upper left")
        right_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        plt.setp(right_axis.xaxis.get_majorticklabels(), rotation=30, ha="right")

    fig.suptitle("Commodity Price Anomalies Around Major Conflict Escalations", fontsize=14)
    plt.tight_layout()
    output_path = os.path.join(FIGURES_DIR, "fig3_anomaly_detection.png")
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Figure saved -> {output_path}")


# 分析 4：VAR + Cholesky IRF / Analysis 4: VAR + Cholesky IRF

# 重点观察冲突到价格的传导；focus on conflict shocks and price responses.
# 变量顺序保持冲突在前、价格在后；order variables as conflict first, price second.
VAR_PAIRS = [
    ("Russia-Ukraine", "russia_ukraine_events", "wti_crude_usd_bbl",   "WTI Crude"),
    ("Russia-Ukraine", "russia_ukraine_events", "brent_crude_usd_bbl", "Brent Crude"),
    ("Israel-Palestine", "israel_palestine_events", "gold_close_mean",  "Gold"),
    ("Yemen",            "yemen_events",             "brent_crude_usd_bbl", "Brent Crude"),
]

# 必要时做一阶差分以增强平稳性；difference non-stationary series before VAR.

def _make_stationary_df(df_in: pd.DataFrame) -> pd.DataFrame:
    """对非平稳列做一阶差分；first-difference columns with ADF p > 0.05."""
    out = df_in.copy()
    for col in out.columns:
        series = out[col].dropna()
        if len(series) < 10:
            continue
        p_val = adfuller(series, autolag="AIC")[1]
        if p_val > 0.05:
            out[col] = out[col].diff()
    return out.dropna().reset_index(drop=True)

# 用残差 bootstrap 估计 IRF 区间；bootstrap residuals to build IRF confidence bands.

def _bootstrap_irf(fitted_model, combined: pd.DataFrame,
                   impulse_idx: int, response_idx: int,
                   periods: int = 12, n_boot: int = 200, seed: int = 42) -> tuple:
    """
    为 Cholesky IRF 生成残差 bootstrap 置信区间。
    Residual bootstrap for Cholesky IRF confidence bands.

    用重抽样残差向前模拟 VAR 数据，再用相同滞后阶数重新拟合。
    Re-generates VAR data with resampled residuals, then re-fits at the same lag order.
    """
    rng    = np.random.default_rng(seed)
    k_ar   = fitted_model.k_ar
    resid  = fitted_model.resid.values          # 形状为 (T-p, k) / Shape is (T-p, k).
    coefs  = fitted_model.coefs                 # 形状为 (p, k, k) / Shape is (p, k, k).
    intercept = fitted_model.params.iloc[0].values  # 常数项形状为 (k,) / Constant term shape is (k,).
    T, k   = combined.shape
    boot_irfs = np.zeros((n_boot, periods + 1))

    for b in range(n_boot):
        # 重抽样 VAR 残差；resample residual shocks for bootstrap simulation.
        idx      = rng.integers(0, len(resid), size=len(resid))
        boot_res = resid[idx]

        # 从前 k_ar 个观测开始递推；simulate forward using the VAR structure.
        data_boot = np.zeros((T, k))
        data_boot[:k_ar] = combined.values[:k_ar]
        for t in range(k_ar, T):
            pred = intercept.copy()
            for lag in range(k_ar):
                pred += coefs[lag] @ data_boot[t - lag - 1]
            data_boot[t] = pred + boot_res[t - k_ar]

        try:
            boot_fit = VAR(data_boot).fit(maxlags=k_ar, ic=None, verbose=False)
            if boot_fit.k_ar == 0:
                raise ValueError("lag 0")
            boot_irf = boot_fit.irf(periods=periods)
            boot_irfs[b] = boot_irf.orth_irfs[:, response_idx, impulse_idx]
        except Exception:
            boot_irfs[b] = np.nan

    lower = np.nanpercentile(boot_irfs, 16, axis=0)
    upper = np.nanpercentile(boot_irfs, 84, axis=0)
    return lower, upper

# VAR IRF 关注冲突冲击后的价格响应；IRF asks how price responds after a conflict shock.
def analysis_var_irf(df: pd.DataFrame) -> None:
    """
    方法 1：VAR + Cholesky IRF（Caldara & Iacoviello 2022 风格）。
    Method 1: VAR + Cholesky IRF (Caldara & Iacoviello 2022 style).

    对每个关键冲突区域和商品组合 / For each key pair:
      1. ADF 检验后必要时差分；make both series stationary if needed.
      2. 拟合双变量 VAR，AIC 选滞后阶数；fit a bivariate VAR with AIC lag selection.
      3. 用 Cholesky 识别冲击，冲突变量排在前；identify shocks with conflict ordered first.
      4. 绘制 12 个月 IRF 与 bootstrap 区间；plot the 12-month IRF with confidence bands.

    回答的问题 / Answers:
      How large is the price response to a one-SD conflict shock, and how long does it persist?
    """
    print("\n=== Analysis 4: VAR + Cholesky IRF (Caldara & Iacoviello style) ===")

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes_flat = axes.flatten()

    for idx, (region, conflict_col, price_col, price_label) in enumerate(VAR_PAIRS):
        ax = axes_flat[idx]

        if conflict_col not in df.columns or price_col not in df.columns:
            ax.text(0.5, 0.5, "Data unavailable", ha="center", va="center")
            ax.set_axis_off()
            continue
        # 抽取冲突和价格两列；build the minimal two-variable VAR input.

        raw = pd.DataFrame({
            "conflict": pd.to_numeric(df[conflict_col], errors="coerce"),
            "price":    pd.to_numeric(df[price_col],    errors="coerce"),
        })
        combined = _make_stationary_df(raw)

        if len(combined) < 20:
            ax.text(0.5, 0.5, "Insufficient data", ha="center", va="center")
            ax.set_axis_off()
            continue

        try:
            model  = VAR(combined)
            fitted = model.fit(maxlags=4, ic="aic", verbose=False)
            # AIC 选 0 阶时强制至少 1 阶；force at least one lag so IRF is defined.
            if fitted.k_ar == 0:
                fitted = model.fit(maxlags=1, ic=None, verbose=False)
            irf    = fitted.irf(periods=12)

            impulse_idx  = combined.columns.get_loc("conflict")
            response_idx = combined.columns.get_loc("price")

            irf_vals = irf.orth_irfs[:, response_idx, impulse_idx]
            lower, upper = _bootstrap_irf(fitted, combined, impulse_idx, response_idx,
                                          periods=12, n_boot=200)

            periods_x = np.arange(len(irf_vals))
            ax.plot(periods_x, irf_vals, color="#08519c", linewidth=2, label="IRF (Cholesky)")
            ax.fill_between(periods_x, lower, upper, alpha=0.25, color="#6baed6",
                            label="±1 SD (bootstrap, 200 reps)")
            ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
            ax.set_title(f"{region} → {price_label}", fontsize=10)
            ax.set_xlabel("Months after shock")
            ax.set_ylabel("Price response (Δ, Cholesky orth.)")
            ax.legend(fontsize=7)
            ax.set_xticks(periods_x)
            peak_h = int(np.argmax(np.abs(irf_vals)))
            print(f"  [{region} → {price_label}] VAR lag order: {fitted.k_ar}, "
                  f"peak IRF at h={peak_h}: {irf_vals[peak_h]:.4f}")

        except Exception as exc:
            ax.text(0.5, 0.5, f"VAR failed:\n{exc}", ha="center", va="center", fontsize=7)
            ax.set_axis_off()
            print(f"  [WARNING] VAR failed for {region} → {price_label}: {exc}")

    fig.suptitle(
        "Method 1: VAR Impulse Response Functions (Cholesky)\n"
        "Conflict shock → Commodity price response (2019-2025)",
        fontsize=12,
    )
    plt.tight_layout()
    output_path = os.path.join(FIGURES_DIR, "fig4_var_irf.png")
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Figure saved -> {output_path}")


# 分析 5：滚动 Granger 因果 / Analysis 5: Rolling-window Granger causality

# 观察预测力随时间何时显现；track when conflict gains predictive power for prices.
GRANGER_PAIRS = [
    ("Russia-Ukraine",    "russia_ukraine_events",    "wti_crude_usd_bbl",   "WTI Crude"),
    ("Russia-Ukraine",    "russia_ukraine_events",    "brent_crude_usd_bbl", "Brent Crude"),
    ("Israel-Palestine",  "israel_palestine_events",  "gold_close_mean",     "Gold"),
    ("Yemen",             "yemen_events",             "brent_crude_usd_bbl", "Brent Crude"),
]
# 使用 24 个月窗口和最多 3 阶滞后；use 24-month windows and up to 3 lags.

GRANGER_WINDOW   = 24   # 每个滚动窗口的月份数 / Months per rolling window
GRANGER_MAX_LAG  = 3    # Granger 检验的最大滞后阶数 / Maximum Granger lag order to test

# 滚动 Granger 同时回答是否和何时；rolling tests ask both whether and when.
def analysis_rolling_granger(df: pd.DataFrame) -> None:
    """
    方法 2：滚动窗口 Granger 因果检验（Zafeiriou et al. 风格）。
    Method 2: Rolling-window Granger causality (Zafeiriou et al. style).

    对每个组合逐月滑动 24 个月窗口 / For each pair, slide a 24-month window:
      H0：冲突事件不 Granger 导致商品价格。
      H0: conflict events do NOT Granger-cause the commodity price.
    在每个窗口结束月记录 1-3 阶中的最小 p 值。
    Record the minimum p-value across lag orders 1-3 at each window end-date.

    绘制 p 值时间序列和 p=0.05 显著性线。
    Plots the p-value time series with a p=0.05 significance line.

    回答的问题 / Answers: When does conflict significantly predict prices?
    """
    print("\n=== Analysis 5: Rolling-window Granger Causality (Zafeiriou et al. style) ===")

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharex=False)
    axes_flat = axes.flatten()

    for idx, (region, conflict_col, price_col, price_label) in enumerate(GRANGER_PAIRS):
        ax = axes_flat[idx]

        if conflict_col not in df.columns or price_col not in df.columns:
            ax.text(0.5, 0.5, "Data unavailable", ha="center", va="center")
            ax.set_axis_off()
            continue
        # 取原始序列并保留日期；carry raw values together with dates.

        conflict_raw = pd.to_numeric(df[conflict_col], errors="coerce")
        price_raw    = pd.to_numeric(df[price_col],    errors="coerce")
        dates        = pd.to_datetime(df["year_month"], format="%Y-%m", errors="coerce")
        # 对冲突和价格差分后拼表；difference both series before rolling tests.

        combined = pd.concat([dates, conflict_raw.diff(), price_raw.diff()], axis=1).dropna()
        combined.columns = ["date", "conflict", "price"]
        combined = combined.reset_index(drop=True)

        window_ends  = []
        pvalues      = []
        n = len(combined)
        # 每移动一个月重新检验；rerun Granger tests for each rolling window.

        for end in range(GRANGER_WINDOW, n + 1):
            window_data = combined.iloc[end - GRANGER_WINDOW : end][["conflict", "price"]].values
            end_date    = combined.iloc[end - 1]["date"]

            try:
                # statsmodels 需要输入顺序为 [y, x]；statsmodels expects [y, x].
                # 检验 conflict 是否导致 price；use [price, conflict] to test conflict causing price.
                test_input = window_data[:, [1, 0]]   # 输入顺序：[price, conflict] / Input order: [price, conflict]
                results    = grangercausalitytests(test_input, maxlag=GRANGER_MAX_LAG, verbose=False)
                # 取所有滞后与 F 检验中的最小 p 值；take the minimum p-value across lags and F-tests.
                min_p = min(
                    results[lag][0]["ssr_ftest"][1]
                    for lag in range(1, GRANGER_MAX_LAG + 1)
                )
            except Exception:
                min_p = np.nan

            window_ends.append(end_date)
            pvalues.append(min_p)

        pvalues = np.array(pvalues, dtype=float)
        sig_mask = pvalues < 0.05

        ax.plot(window_ends, pvalues, color="#08519c", linewidth=1.5, label="Min p-value")
        ax.axhline(0.05, color="#d62728", linestyle="--", linewidth=1.2, label="p = 0.05")
        ax.fill_between(
            window_ends, 0, 0.05,
            where=sig_mask,
            alpha=0.20, color="#d62728",
            label="Significant (p < 0.05)",
            interpolate=True,
        )

        # 同步标记重大升级事件；mark escalations to compare with p-value dips.
        for ym, event_label in ESCALATION_EVENTS.items():
            edate = pd.to_datetime(ym, format="%Y-%m")
            if window_ends and edate >= window_ends[0]:
                ax.axvline(edate, color="#7f7f7f", linestyle=":", linewidth=1)
                ax.text(edate, 0.95, event_label, rotation=90, va="top", ha="right",
                        fontsize=6, color="#555555",
                        transform=ax.get_xaxis_transform())

        sig_pct = 100 * sig_mask.sum() / max(len(sig_mask), 1)
        ax.set_title(f"{region} → {price_label}\n({sig_pct:.0f}% of windows significant)",
                     fontsize=9)
        ax.set_xlabel("Window end date")
        ax.set_ylabel("Min Granger p-value")
        ax.set_ylim(0, 1.05)
        ax.legend(fontsize=7)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")

        sig_periods = [str(d.strftime("%Y-%m")) for d, s in zip(window_ends, sig_mask) if s]
        print(f"  [{region} → {price_label}] significant windows ({len(sig_periods)}): "
              f"{sig_periods[:5]}{'...' if len(sig_periods) > 5 else ''}")

    fig.suptitle(
        "Method 2: Rolling-window Granger Causality (24-month window)\n"
        "H0: conflict events do NOT Granger-cause commodity price",
        fontsize=12,
    )
    plt.tight_layout()
    output_path = os.path.join(FIGURES_DIR, "fig5_rolling_granger.png")
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Figure saved -> {output_path}")


# 汇总 / Summary

# 分析前先报告数据范围和可用列；summarize date coverage and available variables.

def print_summary(df: pd.DataFrame) -> None:
    print("\n=== Dataset Summary ===")
    print(f"  Months covered : {df['year_month'].iloc[0]} to {df['year_month'].iloc[-1]}")
    print(f"  Total rows     : {len(df)}")

    available_prices = [col for col in COMMODITY_COLS.values() if col in df.columns]
    available_conflicts = [col for col in CONFLICT_COLS.values() if col in df.columns]

    print(f"  Commodity cols : {available_prices}")
    print(f"  Conflict cols  : {available_conflicts}")

    if available_prices:
        print("\n  Commodity summary:")
        print(df[available_prices].describe().round(2).to_string())

    if available_conflicts:
        print("\n  Conflict summary:")
        print(df[available_conflicts].describe().round(1).to_string())


# 命令行入口 / CLI

# 主入口可选择分析类型；choose one analysis or run all analyses.
def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze and visualize project data")
    parser.add_argument(
        "--analysis",
        choices=["all", "correlation", "comparison", "anomaly", "var_irf", "rolling_granger"],
        default="all",
    )
    args = parser.parse_args()
# 先读取统一表并打印概况；load the unified table and print a summary.
    df = load_unified()
    print_summary(df)

    if args.analysis in ("all", "correlation"):
        analysis_correlation(df)

    if args.analysis in ("all", "comparison"):
        analysis_comparison(df)

    if args.analysis in ("all", "anomaly"):
        analysis_anomaly(df)

    if args.analysis in ("all", "var_irf"):
        analysis_var_irf(df)

    if args.analysis in ("all", "rolling_granger"):
        analysis_rolling_granger(df)

    print(f"\n[INFO] Figures are saved to {FIGURES_DIR}")

# 直接运行脚本时启动主程；run main only when invoked directly.
if __name__ == "__main__":
    main()
