import pandas as pd
import numpy as np

# Suppress future warning for downcasting
pd.set_option('future.no_silent_downcasting', True)
from sqlalchemy import create_engine, text
import re
import sys
import json
import argparse
from datetime import datetime
import os
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for headless environments

# 配置输出目录
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy.exc import OperationalError as SAOperationalError
from lib.config import Config
import matplotlib.font_manager as fm
from matplotlib.font_manager import FontProperties

# 设置 matplotlib 和 seaborn 样式以获得更好的图表视觉效果
sns.set_style("whitegrid")


# Global variable to store CJK font path
_cjk_font_path = None

def get_cjk_font_prop():
    """返回第一个可用的系统 CJK 字体的 FontProperties，或 None。

    该函数会尝试几个常见的系统字体路径（包括 Noto CJK 和 WQY），并构造
    一个 FontProperties 指向该字体文件，便于在绘图时显式传入以保证中文显示。
    """
    global _cjk_font_path
    candidate_paths = [
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttf',
    ]
    for p in candidate_paths:
        if os.path.exists(p):
            try:
                _cjk_font_path = p
                return FontProperties(fname=p)
            except Exception:
                continue
    # fallback: try to find any system font whose filename hints at CJK
    for p in fm.findSystemFonts(fontpaths=None, fontext='ttf') + fm.findSystemFonts(fontpaths=None, fontext='otf'):
        lp = p.lower()
        if any(k in lp for k in ('noto', 'wqy', 'yahei', 'msyh', 'simhei', 'ukai', 'kaiu')):
            try:
                _cjk_font_path = p
                return FontProperties(fname=p)
            except Exception:
                continue
    return None


# 尝试获取一个 FontProperties，用于在绘图时保证中文文本使用可用字体
_cjk_prop = get_cjk_font_prop()
if not _cjk_prop:
    print("注意：未检测到推荐的中文字体，图表中文可能无法正确显示。")
    print("建议在系统上安装字体，例如 (Debian/Ubuntu): sudo apt-get install fonts-noto-cjk fonts-wqy-zenhei")

plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
if _cjk_prop:
    try:
        fam = _cjk_prop.get_name()
        if fam:
            plt.rcParams['font.sans-serif'] = [fam]
            plt.rcParams['font.family'] = 'sans-serif'
    except Exception:
        pass
    # If we have a font file path, monkeypatch font_manager.findfont to always return it
    try:
        if '_cjk_font_path' in globals() and _cjk_font_path:
            # ensure font file is registered with matplotlib's font manager
            try:
                fm.fontManager.addfont(_cjk_font_path)
            except Exception:
                pass
            # after registering, try to set the sans-serif family to the font's family name
            try:
                fam2 = FontProperties(fname=_cjk_font_path).get_name()
                if fam2:
                    plt.rcParams['font.sans-serif'] = [fam2]
                    plt.rcParams['font.family'] = 'sans-serif'
            except Exception:
                pass
            # as a last resort, force findfont to return the font file path
            def _forced_findfont(*args, **kwargs):
                return _cjk_font_path
            fm.findfont = _forced_findfont
    except Exception:
        pass

# =================配置区域=================
# 优先使用环境变量 DB_CONNECTION_STR，其次从 Config.get_db_config() 中读取并构建 DSN
# Config.get_db_config() 返回: { 'host','port','database','user','password' }
db_cfg = Config.get_db_config() or {}
env_dsn = os.getenv('DB_CONNECTION_STR')
if env_dsn:
    DB_CONNECTION_STR = env_dsn
else:
    DB_CONNECTION_STR = f"postgresql://{db_cfg.get('user')}:{db_cfg.get('password')}@{db_cfg.get('host')}:{db_cfg.get('port')}/{db_cfg.get('database')}"
# 若使用环境变量，在运行前设置: export DB_CONNECTION_STR='postgresql://user:pass@host:5432/db'
# 您的案子提交 DOJ Memo 的日期 (用于计算您的静默期)
MY_CASE_MEMO_DATE = '2025-07-30' # 示例日期，请替换为实际日期
# =========================================

# --- 数据库交互部分 ---

def get_mandamus_data_for_analysis(year=2025):
    """从数据库拉取指定年份的 Mandamus 案件数据"""
    engine = create_engine(DB_CONNECTION_STR)
    
    # 拉取 case_analysis 的核心数据，仅限指定年份，并确保日期格式正确
    year_suffix = f"-{year % 100:02d}"
    query = f"""
    SELECT 
        case_id AS case_number,
        filing_date,
        case_status,
        visa_office,
        time_to_close,
        outcome_date,
        memo_response_time,
        reply_memo_date,
        reply_to_outcome_time
    FROM case_analysis 
    WHERE case_type = 'Mandamus' 
    AND (case_id LIKE '%{year_suffix}' OR case_number LIKE '%{year_suffix}')
    ORDER BY filing_date ASC;
    """
    
    print(f"正在提取 {year} 年 Mandamus 案件核心数据...")
    try:
        with engine.connect() as connect:
            df = pd.read_sql(text(query), connect)
    except SAOperationalError as e:
        print("数据库连接失败：", str(e))
        print("请检查配置或环境变量 DB_CONNECTION_STR，或确保数据库凭据在 Config 中正确设置（get_db_config）。")
        return pd.DataFrame()
    except Exception as e:
        print("读取数据库时发生错误：", str(e))
        return pd.DataFrame()
    
    df['filing_date'] = pd.to_datetime(df['filing_date'], errors='coerce')
    df['outcome_date'] = pd.to_datetime(df['outcome_date'], errors='coerce')
    
    print(f"提取完成: {len(df)} 条 {year} 年记录")
    return df


def export_cases_to_json(year=2025):
    """提取 Granted 和 Dismissed 案件的原始信息和分析结果，并保存为 JSON。"""
    engine = create_engine(DB_CONNECTION_STR)
    
    for status in ['Granted', 'Dismissed']:
        filename_base = f"{status.lower()}_cases_{year}.json"
        filename = os.path.join(OUTPUT_DIR, filename_base)
        print(f"\n正在导出 {status} 案件到 {filename}...")
        
        # 1. 从 case_analysis 获取该状态的 Mandamus 案件
        year_suffix = f"-{year % 100:02d}"
        analysis_query = f"""
        SELECT * FROM case_analysis 
        WHERE case_type = 'Mandamus' 
        AND case_status = '{status}'
        AND (case_id LIKE '%{year_suffix}' OR case_number LIKE '%{year_suffix}')
        """
        with engine.connect() as connect:
            analysis_df = pd.read_sql(text(analysis_query), connect)
        
        if analysis_df.empty:
            print(f"   (未发现 {year} 年 {status} 状态 of Mandamus 案件数据)")
            continue
            
        case_ids = analysis_df['case_id'].tolist()
        
        # 2. 获取 cases 表的原始基本信息
        cases_info_list = []
        batch_size = 500
        for i in range(0, len(case_ids), batch_size):
            batch = case_ids[i:i + batch_size]
            batch_str = ",".join([f"'{c}'" for c in batch])
            c_query = f"SELECT * FROM cases WHERE case_number IN ({batch_str})"
            with engine.connect() as connect:
                batch_df = pd.read_sql(text(c_query), connect)
            cases_info_list.append(batch_df)
        
        cases_df = pd.concat(cases_info_list) if cases_info_list else pd.DataFrame()
        
        # 3. 获取所有相关的 docket_entries
        docket_list = []
        for i in range(0, len(case_ids), batch_size):
            batch = case_ids[i:i + batch_size]
            batch_str = ",".join([f"'{c}'" for c in batch])
            d_query = f"SELECT * FROM docket_entries WHERE case_number IN ({batch_str}) ORDER BY date_filed ASC"
            with engine.connect() as connect:
                batch_df = pd.read_sql(text(d_query), connect)
            docket_list.append(batch_df)
            
        docket_df = pd.concat(docket_list) if docket_list else pd.DataFrame()
        
        # 4. 组装数据构建 JSON 格式
        json_results = []
        
        # 辅助日期处理函数
        def date_handler(obj):
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            return obj

        for _, analysis_row in analysis_df.iterrows():
            c_num = analysis_row['case_id']
            
            # 获取基本信息字典
            c_info = cases_df[cases_df['case_number'] == c_num].to_dict('records')
            c_info_dict = c_info[0] if c_info else {}
            
            # 获取该案的所有 docket entries
            entries = docket_df[docket_df['case_number'] == c_num].to_dict('records')
            
            # 合并为一个对象
            json_results.append({
                "case_number": c_num,
                "analysis_result": {k: date_handler(v) for k, v in analysis_row.to_dict().items()},
                "raw_case_info": {k: date_handler(v) for k, v in c_info_dict.items()},
                "docket_entries": [{k: date_handler(v) for k, v in e.items()} for e in entries]
            })
            
        # 写入文件
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(json_results, f, ensure_ascii=False, indent=2)
            print(f"✅ 已成功生成 {filename} (含 {len(json_results)} 个案件)")
        except Exception as e:
            print(f"❌ 写入 {filename} 失败: {e}")

# --- 分析和可视化部分 ---

def plot_workload_trends(df_monthly):
    """绘制每月注册量、结案量和净积压变化趋势图"""

    fig, ax1 = plt.subplots(figsize=(12, 6))

    # 绘制注册量 (Filing Count)
    ax1.plot(df_monthly.index, df_monthly['filing_count'], marker='o', linestyle='-', color='tab:blue', label='案件注册量')
    if _cjk_prop:
        ax1.set_xlabel('月份', fontproperties=_cjk_prop)
        ax1.set_ylabel('案件数量', color='tab:blue', fontproperties=_cjk_prop)
    else:
        ax1.set_xlabel('月份')
        ax1.set_ylabel('案件数量', color='tab:blue')
    ax1.tick_params(axis='y', labelcolor='tab:blue')

    # 第二个Y轴绘制净积压变化 (Net Change)
    ax2 = ax1.twinx() 
    ax2.bar(df_monthly.index, df_monthly['net_change'], width=20, alpha=0.6, color=np.where(df_monthly['net_change'] >= 0, 'tab:red', 'tab:green'), label='净积压变化')
    if _cjk_prop:
        ax2.set_ylabel('净积压变化 (注册 - 结案)', color='tab:red', fontproperties=_cjk_prop)
    else:
        ax2.set_ylabel('净积压变化 (注册 - 结案)', color='tab:red')
    ax2.tick_params(axis='y', labelcolor='tab:red')

    fig.autofmt_xdate(rotation=45)
    if _cjk_prop:
        ax1.set_title('2025 年 Mandamus 案件每月负荷及积压趋势', fontproperties=_cjk_prop)
        leg = ax1.legend(loc='upper left', prop=_cjk_prop)
    else:
        plt.title('2025 年 Mandamus 案件每月负荷及积压趋势')
        leg = ax1.legend(loc='upper left')
    # ensure x tick labels use CJK font if available
    if _cjk_prop:
        for lbl in ax1.get_xticklabels():
            lbl.set_fontproperties(_cjk_prop)
    save_path = os.path.join(OUTPUT_DIR, 'mandamus_workload_trends.png')
    plt.savefig(save_path)
    print(f"📈 已保存负载趋势图至: {save_path}")
    plt.close()


def plot_outcome_trends(df_monthly):
    """绘制每月结案方式趋势图"""

    # 堆叠图数据准备：只看已结案的部分
    df_outcome_plot = df_monthly[['settled_count', 'dismissed_count', 'granted_count']].fillna(0)

    # 将其他方式结案合并为 "Other/Dismissed"
    df_outcome_plot['Other/Dismissed'] = df_outcome_plot['dismissed_count'] # 假设败诉占比最多
    df_outcome_plot['Settled'] = df_outcome_plot['settled_count']
    df_outcome_plot['Granted'] = df_outcome_plot['granted_count']

    fig, ax = plt.subplots(figsize=(12, 6))
    df_outcome_plot[['Settled', 'Granted', 'Other/Dismissed']].plot(kind='bar', stacked=True, ax=ax)

    if _cjk_prop:
        ax.set_title('2025 年 Mandamus 案件每月结案方式分布', fontproperties=_cjk_prop)
        ax.set_xlabel('月份', fontproperties=_cjk_prop)
        ax.set_ylabel('结案数量', fontproperties=_cjk_prop)
        leg = ax.legend(title='结案方式', prop=_cjk_prop)
        for lbl in ax.get_xticklabels():
            lbl.set_fontproperties(_cjk_prop)
        if leg:
            for text in leg.get_texts():
                text.set_fontproperties(_cjk_prop)
    else:
        ax.set_title('2025 年 Mandamus 案件每月结案方式分布')
        ax.set_xlabel('月份')
        ax.set_ylabel('结案数量')
        plt.legend(title='结案方式')
    fig.autofmt_xdate(rotation=45)
    save_path = os.path.join(OUTPUT_DIR, 'mandamus_outcome_trends.png')
    plt.savefig(save_path)
    print(f"📈 已保存结案方式趋势图至: {save_path}")
    plt.close()


def plot_timeline_trends(df_monthly):
    """绘制每月结案耗时趋势图"""

    fig, ax = plt.subplots(figsize=(12, 6))

    # 绘制平均结案耗时 (中位数)
    ax.plot(df_monthly.index, df_monthly['median_time_to_close'], marker='s', linestyle='--', color='purple', label='中位数总耗时')

    if _cjk_prop:
        ax.set_title('2025 年 Mandamus 案件中位数结案耗时趋势', fontproperties=_cjk_prop)
        ax.set_xlabel('月份', fontproperties=_cjk_prop)
        ax.set_ylabel('耗时 (天数)', fontproperties=_cjk_prop)
    else:
        ax.set_title('2025 年 Mandamus 案件中位数结案耗时趋势')
        ax.set_xlabel('月份')
        ax.set_ylabel('耗时 (天数)')

    fig.autofmt_xdate(rotation=45)
    plt.legend()
    save_path = os.path.join(OUTPUT_DIR, 'mandamus_timeline_trends.png')
    plt.savefig(save_path)
    print(f"📈 已保存结案耗时趋势图至: {save_path}")
    plt.close()


def plot_memo_response_trends(df_monthly):
    """绘制每月 DOJ Memo 响应时间趋势图"""

    if 'median_memo_response_time' not in df_monthly.columns:
        print("没有 Memo 响应时间数据，跳过图表绘制。")
        return

    fig, ax = plt.subplots(figsize=(12, 6))

    # 绘制平均 Memo 响应时间 (中位数)
    ax.plot(df_monthly.index, df_monthly['median_memo_response_time'], marker='o', linestyle='-', color='orange', label='中位数 DOJ Memo 响应时间')

    if _cjk_prop:
        ax.set_title('2025 年 Mandamus 案件 DOJ Memo 响应时间趋势', fontproperties=_cjk_prop)
        ax.set_xlabel('月份', fontproperties=_cjk_prop)
        ax.set_ylabel('响应时间 (天数)', fontproperties=_cjk_prop)
    else:
        ax.set_title('2025 年 Mandamus 案件 DOJ Memo 响应时间趋势')
        ax.set_xlabel('月份')
        ax.set_ylabel('响应时间 (天数)')

    fig.autofmt_xdate(rotation=45)
    plt.legend()
    save_path = os.path.join(OUTPUT_DIR, 'mandamus_memo_response_trends.png')
    plt.savefig(save_path)
    print(f"📈 已保存 Memo 响应趋势图至: {save_path}")
    plt.close()


def plot_memo_reply_to_outcome_trends(df):
    """按月统计：从 memo 回复到结案的时间（天），按结案类型分系列绘图。

    计算方法:
    - 优先使用 reply_memo_date（实际的 DOJ Memo 回复日期）
    - 如果 reply_memo_date 为空，则使用 filing_date + memo_response_time 作为备选
    - reply_to_outcome_days = (outcome_date or 当前日期) - reply_memo_date 的天数
    按 outcome_date 的月末频率分组，并对每个 case_status 计算最大、最小、平均、中位数。
    同时显示 IMM-11243-25 案例从 memo 回复到当前的时间作为参考线。
    """
    df = df.copy()
    # 必要字段 - 包含 reply_memo_date
    required_fields = {'filing_date', 'outcome_date', 'case_status', 'case_number', 'reply_memo_date'}
    optional_fields = {'memo_response_time'}  # 备用字段
    
    if not required_fields.issubset(df.columns):
        print(f"缺少必要字段，跳过 reply_memo->outcome 统计。需要：{required_fields - set(df.columns)}")
        return

    # 提取特定案例 IMM-11243-25 的信息作为参考
    reference_days = None
    reference_start_date = None
    
    target_case = df[df['case_number'] == 'IMM-11243-25']
    if not target_case.empty:
        case_row = target_case.iloc[0]
        
        # 优先使用 reply_memo_date，如果没有则使用您指定的日期
        if pd.notna(case_row['reply_memo_date']):
            reference_start_date = pd.to_datetime(case_row['reply_memo_date'])
        else:
            # 使用您指定的日期 2025-07-30
            reference_start_date = pd.to_datetime('2025-07-30')
        
        if reference_start_date is not None:
            # 对于未结案案例，使用当前日期；对于已结案案例，使用outcome_date
            if pd.notna(case_row['outcome_date']):
                end_date = pd.to_datetime(case_row['outcome_date'])
                period_desc = f"至结案日期 {end_date.date()}"
            else:
                end_date = pd.Timestamp.now()
                period_desc = f"至今天 {end_date.date()}"
            
            reference_days = (end_date - reference_start_date).days
            print(f"参考案例 IMM-11243-25: memo回复日期={reference_start_date.date()}, {period_desc}, 天数={reference_days:.0f}天")

    # 处理所有案例的 reply_memo_date
    # 转换日期字段
    df['filing_date'] = pd.to_datetime(df['filing_date'], errors='coerce')
    df['outcome_date'] = pd.to_datetime(df['outcome_date'], errors='coerce')
    df['reply_memo_date'] = pd.to_datetime(df['reply_memo_date'], errors='coerce')
    
    # 计算 reply_memo_date：优先使用实际值，其次使用估算值
    df['calculated_reply_date'] = df['reply_memo_date']  # 优先使用实际 reply_memo_date
    
    # 对于没有 reply_memo_date 但有 memo_response_time 的案例，使用备选计算
    mask_need_calc = df['calculated_reply_date'].isna() & df['memo_response_time'].notna() & df['filing_date'].notna()
    if mask_need_calc.any():
        df.loc[mask_need_calc, 'calculated_reply_date'] = df.loc[mask_need_calc, 'filing_date'] + pd.to_timedelta(df.loc[mask_need_calc, 'memo_response_time'], unit='D')
        print(f"为 {mask_need_calc.sum()} 个案例使用估算的 memo 回复日期")

    # 计算 reply_to_outcome_days
    df['reply_to_outcome_days'] = None
    
    # 对于已结案案例
    resolved_mask = df['case_status'].isin(['Discontinued', 'Granted', 'Dismissed'])
    resolved_with_dates = resolved_mask & df['outcome_date'].notna() & df['calculated_reply_date'].notna()
    
    if resolved_with_dates.any():
        df.loc[resolved_with_dates, 'reply_to_outcome_days'] = (
            df.loc[resolved_with_dates, 'outcome_date'] - df.loc[resolved_with_dates, 'calculated_reply_date']
        ).dt.days

    # 对于未结案案例（有 reply_memo_date 但没有 outcome_date），计算到当前的时间
    unresolved_mask = ~resolved_mask & df['calculated_reply_date'].notna()
    if unresolved_mask.any():
        current_date = pd.Timestamp.now()
        df.loc[unresolved_mask, 'reply_to_outcome_days'] = (
            current_date - df.loc[unresolved_mask, 'calculated_reply_date']
        ).dt.days

    # 只统计有效的数据
    df_valid = df[df['reply_to_outcome_days'].notna() & (df['reply_to_outcome_days'] >= 0)].copy()
    
    if df_valid.empty:
        print("没有有效的 reply_memo 到 outcome 时间数据，跳过绘图。")
        return

    # 对于月度趋势，我们只看已结案案例（因为 outcome_date 是分组依据）
    df_resolved = df_valid[df_valid['case_status'].isin(['Discontinued', 'Granted', 'Dismissed'])].copy()
    if df_resolved.empty:
        print("没有已结案的有效数据用于月度趋势，跳过绘图。")
        return

    # 按 outcome_date 月末 和 case_status 分组，计算多个统计指标
    grouped = df_resolved.groupby([pd.Grouper(key='outcome_date', freq='ME'), 'case_status'])['reply_to_outcome_days'].agg(['mean', 'median'])
    if grouped.empty:
        print("分组后无数据，跳过绘图。")
        return

    # 创建 2 个子图，分别显示平均值、中位数
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    metrics = [('mean', '平均值'), ('median', '中位数')]
    axes = [ax1, ax2]
    
    for (metric, metric_name), ax in zip(metrics, axes):
        # 重置索引以便于绘图
        pivot_data = grouped[metric].unstack(level=-1)
        
        # 为每个结案类型绘制线条
        for col in pivot_data.columns:
            ax.plot(pivot_data.index, pivot_data[col], marker='o', linestyle='-', label=str(col))
        
        # 添加参考案例的水平线
        if reference_days is not None:
            ax.axhline(y=reference_days, color='red', linestyle='--', linewidth=2, 
                      label=f'IMM-11243-25 ({reference_days:.0f}天)')
            # 重新绘制图例以包含参考线
            if _cjk_prop:
                leg = ax.legend(prop=_cjk_prop)
            else:
                ax.legend()
        
        # 设置标题和标签
        if _cjk_prop:
            ax.set_title(f'Memo回复到结案时间 - {metric_name}（天）', fontproperties=_cjk_prop)
            ax.set_xlabel('结案月份', fontproperties=_cjk_prop)
            ax.set_ylabel('天数', fontproperties=_cjk_prop)
            if not _cjk_prop:
                for lbl in ax.get_xticklabels():
                    lbl.set_fontproperties(_cjk_prop)
        else:
            ax.set_title(f'Memo Reply to Outcome Time - {metric_name} (days)')
            ax.set_xlabel('Outcome Month')
            ax.set_ylabel('Days')
        
        ax.tick_params(axis='x', rotation=45)

    fig.suptitle('按结案类型统计：Memo回复到结案时间分析（含IMM-11243-25参考线）', fontsize=16, fontproperties=_cjk_prop if _cjk_prop else None)
    fig.tight_layout()
    save_path = os.path.join(OUTPUT_DIR, 'mandamus_memo_to_outcome_trends.png')
    plt.savefig(save_path)
    print(f"📈 已保存 Memo 到结案时间统计图至: {save_path}")
    plt.close()

    # === 打印摘要统计内容 ===
    print("\n" + "="*60)
    print("【Memo回复到结案时间分析摘要 (最近 6 个月)】")
    print("="*60)
    
    # 1. 每月总体结案统计 (DataFrame 风格)
    summary_overall = df_resolved.groupby(pd.Grouper(key='outcome_date', freq='ME'))['reply_to_outcome_days'].agg(['count', 'mean']).rename(columns={'count': 'resolved_count', 'mean': 'avg_days'})
    print("\n--- 每月总体结案统计 (最近 6 个月) ---")
    if not summary_overall.empty:
        # 格式化索引为 YYYY-MM 字符串以获得更好的打印效果
        summary_overall.index = summary_overall.index.strftime('%Y-%m')
        # 强制将数值列转换为 float 并四舍五入到1位小数，确保打印效果
        summary_overall['avg_days'] = summary_overall['avg_days'].astype(float).round(1)
        print(summary_overall.tail(6))
    else:
        print("   (无数据)")

    # 2. 每月分类结案统计 (DataFrame 风格)
    monthly_status_agg = df_resolved.groupby([pd.Grouper(key='outcome_date', freq='ME'), 'case_status'])['reply_to_outcome_days'].agg(['count', 'mean'])
    
    # 构建宽表供打印
    status_summary = pd.DataFrame(index=pd.date_range(start=summary_overall.index[0] if not summary_overall.empty else '2025-01-01', 
                                                     periods=len(summary_overall), freq='ME'))
    status_summary.index = status_summary.index.strftime('%Y-%m')
    
    found_any = False
    for status in ['Granted', 'Dismissed']:
        if status in monthly_status_agg.index.get_level_values('case_status'):
            s_data = monthly_status_agg.xs(status, level='case_status')
            # 转换 s_data 索引为字符串匹配
            s_data.index = s_data.index.strftime('%Y-%m')
            
            status_summary[f'{status}_cnt'] = s_data['count']
            status_summary[f'{status}_avg(days)'] = s_data['mean']
            found_any = True
    
    print("\n--- 每月分类结案统计 (Granted/Dismissed) (最近 6 个月) ---")
    if found_any:
        # 只保留有数据的列
        cols = [c for c in status_summary.columns if status_summary[c].notna().any()]
        if cols:
            # 确保数值格式一致，四舍五入到1位小数
            for col in cols:
                if '_cnt' in col:
                    status_summary[col] = status_summary[col].fillna(0).astype(int)
                else:
                    status_summary[col] = status_summary[col].fillna(0).astype(float).round(1)
            print(status_summary[cols].tail(6))
        else:
            print("   (无数据)")
    else:
        print("   (未发现 Granted 或 Dismissed 案例数据)")

    # 3. 总计
    total_count = len(df_resolved)
    avg_duration = df_resolved['reply_to_outcome_days'].mean()
    print(f"\n【总体汇总】 结案总数: {total_count} | 总体平均耗时: {avg_duration:.1f} 天")
    print("=" * 60)


def plot_case_duration_distribution(df):
    """绘制结案耗时分布直方图"""
    # 仅统计已结案且有耗时数据的 Mandamus 案件
    df_resolved = df[df['case_status'].isin(['Discontinued', 'Granted', 'Dismissed'])].copy()
    if df_resolved.empty or 'time_to_close' not in df_resolved.columns or df_resolved['time_to_close'].isna().all():
        return

    durations = df_resolved['time_to_close'].dropna()
    
    plt.figure(figsize=(12, 6))
    
    # 自动确定 bin 数量
    sns.histplot(durations, bins=min(30, len(durations.unique())), kde=True, color='teal', alpha=0.6)
    
    # 添加中位数线
    median_val = durations.median()
    plt.axvline(median_val, color='red', linestyle='--', linewidth=2, label=f'中位数: {median_val:.1f}天')
    
    title = 'Mandamus 案件结案时长分布 (Filing to Outcome)'
    xlabel = '结案耗时 (天)'
    ylabel = '案件数量'
    
    if _cjk_prop:
        plt.title(title, fontproperties=_cjk_prop, fontsize=16)
        plt.xlabel(xlabel, fontproperties=_cjk_prop)
        plt.ylabel(ylabel, fontproperties=_cjk_prop)
        plt.legend(prop=_cjk_prop)
    else:
        plt.title(title, fontsize=16)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.legend()
        
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    save_path = os.path.join(OUTPUT_DIR, 'mandamus_duration_distribution.png')
    plt.savefig(save_path)
    print(f"📈 已保存结案耗时分布图至: {save_path}")
    plt.close()


def analyze_resolution_time_distribution(df):
    """统计不同结案时长 (age_of_case at resolution) 的案件分布"""
    # 筛选已结案的案件
    df_resolved = df[df['case_status'].isin(['Discontinued', 'Granted', 'Dismissed'])].copy()
    
    if df_resolved.empty or 'time_to_close' not in df_resolved.columns or df_resolved['time_to_close'].isna().all():
        print("\n--- 结案耗时分布统计 ---")
        print("   (没有有效的结案耗时数据)")
        return

    # time_to_close 即为结案时的 age_of_case
    durations = df_resolved['time_to_close'].dropna()
    
    print("\n--- 结案耗时分布统计 (Mandamus) ---")
    
    # 定义区间 (0, 30, 60, ..., 240, 365, +inf)
    bins = [0, 30, 60, 90, 120, 150, 180, 210, 240, 365, float('inf')]
    labels = ['0-30天', '31-60天', '61-90天', '91-120天', '121-150天', '151-180天', '181-210天', '211-240天', '241-365天', '365天以上']
    
    # 统计
    dist = pd.cut(durations, bins=bins, labels=labels, right=True).value_counts().sort_index()
    total = len(durations)
    
    for label, count in dist.items():
        percentage = (count / total) * 100 if total > 0 else 0
        print(f"   {label:12}: {count:>4} 案 ({percentage:>4.1f}%)")
    
    # 找出多数案件所在范围
    if total > 0:
        most_common_range = dist.idxmax()
        print(f"\n📊 结论: 多数 Mandamus 案件在 {most_common_range} 范围内结案。")
    print("-" * 50)


def run_monthly_analysis(df):
    """
    实现按月统计的逻辑，健壮处理没有日期或全部为 NaT 的情况。
    """

    df = df.copy()
    df['filing_date'] = pd.to_datetime(df.get('filing_date'), errors='coerce')
    df['outcome_date'] = pd.to_datetime(df.get('outcome_date'), errors='coerce')

    # 如果既没有 filing_date 也没有 outcome_date，则无法做按月分析
    if not (df['filing_date'].notna().any() or df['outcome_date'].notna().any()):
        print("无有效日期数据，无法进行按月分析。")
        return

    # 按 filing_date (注册日期) 统计每月注册量
    if df['filing_date'].notna().any():
        df_filed_monthly = df.groupby(pd.Grouper(key='filing_date', freq='ME'))['case_number'].count().rename('filing_count')
    else:
        df_filed_monthly = pd.Series(dtype='int64', name='filing_count')

    # 按 outcome_date (结案日期) 统计每月结案量
    df_resolved = df[df['case_status'].isin(['Discontinued', 'Granted', 'Dismissed'])]
    if (not df_resolved.empty) and df_resolved['outcome_date'].notna().any():
        df_resolved_monthly = df_resolved.groupby(pd.Grouper(key='outcome_date', freq='ME'))['case_number'].count().rename('resolution_count')
    else:
        df_resolved_monthly = pd.Series(dtype='int64', name='resolution_count')

    # 合并数据并计算净积压变化
    df_monthly = pd.concat([df_filed_monthly, df_resolved_monthly], axis=1).fillna(0)
    df_monthly['net_change'] = df_monthly['filing_count'] - df_monthly['resolution_count']

    # 结案方式趋势
    def _safe_group(res_df, status, col='outcome_date'):
        if res_df.empty or res_df[col].notna().sum() == 0:
            return pd.Series(dtype='int64')
        return res_df[res_df['case_status'] == status].groupby(pd.Grouper(key=col, freq='ME'))['case_number'].count().rename(f"{status.lower()}_count")

    df_monthly['settled_count'] = _safe_group(df_resolved, 'Discontinued')
    df_monthly['granted_count'] = _safe_group(df_resolved, 'Granted')
    df_monthly['dismissed_count'] = _safe_group(df_resolved, 'Dismissed')

    # 关键耗时趋势 (中位数)
    if (not df_resolved.empty) and df_resolved['outcome_date'].notna().any() and df_resolved['time_to_close'].notna().any():
        df_time_to_close_monthly = df_resolved.groupby(pd.Grouper(key='outcome_date', freq='ME'))['time_to_close'].median().rename('median_time_to_close')
        df_monthly = pd.concat([df_monthly, df_time_to_close_monthly], axis=1)
    else:
        df_monthly['median_time_to_close'] = np.nan
    
    # Memo 响应时间趋势
    df_with_memo = df[df['memo_response_time'].notna()]
    if not df_with_memo.empty:
        df_memo_monthly = df_with_memo.groupby(pd.Grouper(key='filing_date', freq='ME'))['memo_response_time'].median().rename('median_memo_response_time')
        df_monthly = pd.concat([df_monthly, df_memo_monthly], axis=1)
    else:
        df_monthly['median_memo_response_time'] = np.nan

    if df_monthly.empty:
        print("没有生成任何按月统计数据。")
        return

    # 绘制图表
    plot_workload_trends(df_monthly)
    plot_outcome_trends(df_monthly)
    plot_timeline_trends(df_monthly)
    plot_memo_response_trends(df_monthly)
    # 新增：按月统计 memo 回复 到 结案 的时间，按结案类型分系列
    try:
        plot_memo_reply_to_outcome_trends(df)
    except Exception as e:
        print('绘制 memo->outcome 趋势失败：', e)

    # 新增：结案耗时分布分析
    try:
        plot_case_duration_distribution(df)
    except Exception as e:
        print('绘制结案时长分布图失败：', e)

    # 打印文字报告
    print("\n" + "="*50)
    print("【2025 年按月统计趋势分析报告】")
    print("="*50)
    print("\n--- 案件负荷与积压变化 (最近 6 个月) ---")
    print(df_monthly[['filing_count', 'resolution_count', 'net_change']].tail(6).round(0).astype(int))

    # 新增文字版分布统计
    analyze_resolution_time_distribution(df)

    print("\n--- 结案方式百分比 (最近 6 个月) ---")
    df_recent_outcome = df_monthly.tail(6).copy()
    df_recent_outcome['resolution_total'] = df_recent_outcome[['settled_count', 'granted_count', 'dismissed_count']].sum(axis=1)
    # avoid division by zero
    df_recent_outcome['Settled Rate'] = df_recent_outcome.apply(lambda r: (f"{round(r['settled_count']/r['resolution_total']*100, 1)}%") if r['resolution_total']>0 else '0.0%', axis=1)
    df_recent_outcome['Granted Rate'] = df_recent_outcome.apply(lambda r: (f"{round(r['granted_count']/r['resolution_total']*100, 1)}%") if r['resolution_total']>0 else '0.0%', axis=1)
    df_recent_outcome['Dismiss Rate'] = df_recent_outcome.apply(lambda r: (f"{round(r['dismissed_count']/r['resolution_total']*100, 1)}%") if r['resolution_total']>0 else '0.0%', axis=1)
    # 对中位数耗时进行四舍五入
    df_recent_outcome['median_time_to_close'] = df_recent_outcome['median_time_to_close'].round(1)
    print(df_recent_outcome[['resolution_total', 'Settled Rate', 'Granted Rate', 'Dismiss Rate', 'median_time_to_close']])
    
    # Memo 响应时间统计
    df_with_memo = df[df['memo_response_time'].notna()]
    if not df_with_memo.empty:
        print("\n--- DOJ Memo 响应时间统计 ---")
        overall_avg = df_with_memo['memo_response_time'].mean()
        overall_median = df_with_memo['memo_response_time'].median()
        
        print(f"总体 Memo 响应时间:")
        print(f"   平均值: {overall_avg:.1f} 天")
        print(f"   中位数: {overall_median:.1f} 天")
        print(f"   最快: {df_with_memo['memo_response_time'].min()} 天")
        print(f"   最慢: {df_with_memo['memo_response_time'].max()} 天")
        print(f"   数据覆盖率: {len(df_with_memo)/len(df)*100:.1f}%")
        
        # 按状态分析
        status_memo_stats = df_with_memo.groupby('case_status')['memo_response_time'].agg(['count', 'mean', 'median'])
        print(f"\n按案件状态分析:")
        for status, stats in status_memo_stats.iterrows():
            print(f"   {status[0]}: {stats['count']} 案, 平均 {stats['mean']:.1f} 天, 中位数 {stats['median']:.1f} 天")
        
        if 'median_memo_response_time' in df_monthly.columns:
            print("\n--- 最近 6 个月 Memo 响应时间趋势 ---")
            recent_memo = df_monthly[['median_memo_response_time']].tail(6).round(1)
            print(recent_memo)
    else:
        print("\n--- DOJ Memo 响应时间统计 ---")
        print("   未找到 Memo 响应时间数据")

    print("\n【趋势解读】")
    if df_monthly['net_change'].tail(3).mean() > 0:
        print("-> 🚨 警告：近三个月净积压变化平均为正值，法院/IRCC 正在承受更大压力，未来案件处理速度可能会减慢。")
    elif df_monthly['median_time_to_close'].tail(3).mean() > df_monthly['median_time_to_close'].iloc[:-3].mean():
        print("-> ⚠️ 注意：尽管积压变化不明显，但结案所需的中位数时间仍在增加，表明效率有所下降。")
    else:
        print("-> ✅ 稳定：目前案件积压趋势和结案耗时较为稳定。")



# --- 主执行区 ---
def main():
    parser = argparse.ArgumentParser(description='FCT Mandamus 案件分析与数据导出')
    parser.add_argument('--year', type=int, default=2025, help='要分析和导出的年份 (默认: 2025)')
    args = parser.parse_args()
    
    target_year = args.year
    
    # 1. 提取核心数据
    df_core = get_mandamus_data_for_analysis(target_year)
    
    # 2. 运行按月分析并绘制图表
    if not df_core.empty:
        run_monthly_analysis(df_core)
        
        # 3. 额外功能：导出详细信息为 JSON
        export_cases_to_json(target_year)
    else:
        print(f"未找到 {target_year} 年 Mandamus 案件数据进行分析。")

    # 注意：微观分析 (Memo to Outcome) 需要 docket_entries 表，请在实际运行中整合 V3 和 V4 脚本。

####################################################33
if __name__ == "__main__":
    main()