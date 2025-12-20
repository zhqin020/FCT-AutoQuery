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
    """从数据库拉取指定跨度（24个月）的 Mandamus 案件数据"""
    engine = create_engine(DB_CONNECTION_STR)
    
    # 按照用户需求，统计期间从 year-1-1 到 (year+1)-12-31 (共24个月)
    start_date = f"{year}-01-01"
    end_date = f"{year+1}-12-31"
    
    # 拉取 case_analysis 的核心数据
    # 策略：拉取在统计期间内有 Filing 或 Outcome 的所有 Mandamus 案件
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
    AND (
        (filing_date >= '{start_date}' AND filing_date <= '{end_date}')
        OR 
        (outcome_date >= '{start_date}' AND outcome_date <= '{end_date}')
    )
    ORDER BY filing_date ASC;
    """
    
    print(f"正在提取 {year} 至 {year+1} 年 Mandamus 案件核心数据 (统计期间: {start_date} 至 {end_date})...")
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
    
    print(f"提取完成: {len(df)} 条记录")
    return df


def export_cases_to_json(year=2025):
    """提取 Granted 和 Dismissed 案件的原始信息和分析结果，并保存为 JSON。"""
    engine = create_engine(DB_CONNECTION_STR)
    
    # 按照用户需求，统计期间从 year-1-1 到 (year+1)-12-31
    start_date = f"{year}-01-01"
    end_date = f"{year+1}-12-31"

    for status in ['Granted', 'Dismissed']:
        filename_base = f"{status.lower()}_cases_{year}_{year+1}.json"
        filename = os.path.join(OUTPUT_DIR, filename_base)
        print(f"\n正在导出 {status} 案件到 {filename}...")
        
        # 1. 从 case_analysis 获取该状态的 Mandamus 案件 (跨度24个月)
        analysis_query = f"""
        SELECT * FROM case_analysis 
        WHERE case_type = 'Mandamus' 
        AND case_status = '{status}'
        AND (
            (filing_date >= '{start_date}' AND filing_date <= '{end_date}')
            OR 
            (outcome_date >= '{start_date}' AND outcome_date <= '{end_date}')
        )
        """
        with engine.connect() as connect:
            analysis_df = pd.read_sql(text(analysis_query), connect)
        
        if analysis_df.empty:
            print(f"   (未发现 {year}-{year+1} 期间 {status} 状态 of Mandamus 案件数据)")
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
            d_query = f"SELECT * FROM docket_entries WHERE case_number IN ({batch_str}) ORDER BY id_from_table DESC"
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
            
        # 生成 summary，写入文件（summary 在文件开始部分）
        try:
            # 计算 summary 指标
            total_cases = len(json_results)
            case_number_list = ",".join([str(r.get('case_number') or '') for r in json_results])

            # 使用 analysis_df 中的数值列计算平均值（更可靠）
            age_avg = None
            reply_to_outcome_avg = None
            try:
                if 'age_of_case' in analysis_df.columns:
                    age_avg_val = pd.to_numeric(analysis_df['age_of_case'], errors='coerce')
                    if age_avg_val.notna().any():
                        age_avg = float(round(age_avg_val.mean(), 1))
                if 'reply_to_outcome_time' in analysis_df.columns:
                    rto_val = pd.to_numeric(analysis_df['reply_to_outcome_time'], errors='coerce')
                    if rto_val.notna().any():
                        reply_to_outcome_avg = float(round(rto_val.mean(), 1))
            except Exception:
                age_avg = None
                reply_to_outcome_avg = None

            summary = {
                'total_cases': total_cases,
                'case_number_list': case_number_list,
                'age_of_case_avg': age_avg,
                'reply_to_outcome_time_avg': reply_to_outcome_avg
            }

            out_obj = {'summary': summary, 'cases': json_results}
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(out_obj, f, ensure_ascii=False, indent=2)
            print(f"✅ 已成功生成 {filename} (含 {len(json_results)} 个案件)，并在文件开头添加 summary")
        except Exception as e:
            print(f"❌ 写入 {filename} 失败: {e}")

# --- 分析和可视化部分 ---

def plot_workload_trends(df_monthly, year=2025):
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
    title_str = f'{year}-{year+1} 年 Mandamus 案件每月负荷及积压趋势'
    if _cjk_prop:
        ax1.set_title(title_str, fontproperties=_cjk_prop)
        leg = ax1.legend(loc='upper left', prop=_cjk_prop)
    else:
        plt.title(title_str)
        leg = ax1.legend(loc='upper left')
    # ensure x tick labels use CJK font if available
    if _cjk_prop:
        for lbl in ax1.get_xticklabels():
            lbl.set_fontproperties(_cjk_prop)
    save_path = os.path.join(OUTPUT_DIR, f'mandamus_workload_trends_{year}.png')
    plt.savefig(save_path)
    print(f"📈 已保存负载趋势图至: {save_path}")
    plt.close()


def plot_outcome_trends(df_monthly, year=2025):
    """绘制每月结案方式趋势图"""

    # 堆叠图数据准备：只看已结案的部分
    df_outcome_plot = df_monthly[['settled_count', 'dismissed_count', 'granted_count']].fillna(0)

    # 将其他方式结案合并为 "Other/Dismissed"
    df_outcome_plot['Other/Dismissed'] = df_outcome_plot['dismissed_count'] # 假设败诉占比最多
    df_outcome_plot['Settled'] = df_outcome_plot['settled_count']
    df_outcome_plot['Granted'] = df_outcome_plot['granted_count']

    fig, ax = plt.subplots(figsize=(12, 6))
    df_outcome_plot[['Settled', 'Granted', 'Other/Dismissed']].plot(kind='bar', stacked=True, ax=ax)

    title_str = f'{year}-{year+1} 年 Mandamus 案件每月结案方式分布'
    if _cjk_prop:
        ax.set_title(title_str, fontproperties=_cjk_prop)
        ax.set_xlabel('月份', fontproperties=_cjk_prop)
        ax.set_ylabel('结案数量', fontproperties=_cjk_prop)
        leg = ax.legend(title='结案方式', prop=_cjk_prop)
        for lbl in ax.get_xticklabels():
            lbl.set_fontproperties(_cjk_prop)
        if leg:
            for text in leg.get_texts():
                text.set_fontproperties(_cjk_prop)
    else:
        ax.set_title(title_str)
        ax.set_xlabel('月份')
        ax.set_ylabel('结案数量')
        plt.legend(title='结案方式')
    fig.autofmt_xdate(rotation=45)
    save_path = os.path.join(OUTPUT_DIR, f'mandamus_outcome_trends_{year}.png')
    plt.savefig(save_path)
    print(f"📈 已保存结案方式趋势图至: {save_path}")
    plt.close()


def plot_timeline_trends(df_monthly, year=2025):
    """绘制每月结案耗时趋势图"""

    fig, ax = plt.subplots(figsize=(12, 6))

    # 绘制平均结案耗时 (中位数)
    ax.plot(df_monthly.index, df_monthly['median_time_to_close'], marker='s', linestyle='--', color='purple', label='中位数总耗时')

    title_str = f'{year}-{year+1} 年 Mandamus 案件中位数结案耗时趋势'
    if _cjk_prop:
        ax.set_title(title_str, fontproperties=_cjk_prop)
        ax.set_xlabel('月份', fontproperties=_cjk_prop)
        ax.set_ylabel('耗时 (天数)', fontproperties=_cjk_prop)
    else:
        ax.set_title(title_str)
        ax.set_xlabel('月份')
        ax.set_ylabel('耗时 (天数)')

    fig.autofmt_xdate(rotation=45)
    plt.legend()
    save_path = os.path.join(OUTPUT_DIR, f'mandamus_timeline_trends_{year}.png')
    plt.savefig(save_path)
    print(f"📈 已保存结案耗时趋势图至: {save_path}")
    plt.close()


def plot_memo_response_trends(df_monthly, year=2025):
    """绘制每月 DOJ Memo 响应时间趋势图"""
    # Memo response trends feature removed per user request.
    return


def plot_memo_reply_to_outcome_trends(df, year=2025):
    """按月统计：从 memo 回复到结案的时间（天），按结案类型分系列绘图。
    
    统计 24 个月的跨度 (YEAR 至 YEAR+1)。
    """
    df = df.copy()
    # 必要字段 - 包含 reply_memo_date
    required_fields = {'filing_date', 'outcome_date', 'case_status', 'case_number', 'reply_memo_date'}
    
    if not required_fields.issubset(df.columns):
        print(f"缺少必要字段，跳过 reply_memo->outcome 统计。需要：{required_fields - set(df.columns)}")
        return

    # 提取参考案例的信息作为参考
    reference_days = None
    target_case_num = f'IMM-11243-{year % 100:02d}' # 尝试匹配当前年份的参考案
    target_case = df[df['case_number'] == target_case_num]
    if target_case.empty:
        # 尝试默认案号
        target_case = df[df['case_number'] == 'IMM-11243-25']
        
    if not target_case.empty:
        case_row = target_case.iloc[0]
        if pd.notna(case_row['reply_memo_date']):
            reference_start_date = pd.to_datetime(case_row['reply_memo_date'])
        else:
            reference_start_date = pd.to_datetime(f'{year}-07-30') # 备选
        
        if reference_start_date is not None:
            if pd.notna(case_row['outcome_date']):
                end_date = pd.to_datetime(case_row['outcome_date'])
                period_desc = f"至结案日期 {end_date.date()}"
            else:
                end_date = pd.Timestamp.now()
                period_desc = f"至今天 {end_date.date()}"
            
            reference_days = (end_date - reference_start_date).days
            print(f"参考案例 {case_row['case_number']}: memo回复日期={reference_start_date.date()}, {period_desc}, 天数={reference_days:.0f}天")

    # 转换日期字段并计算 reply_to_outcome_days
    df['filing_date'] = pd.to_datetime(df['filing_date'], errors='coerce')
    df['outcome_date'] = pd.to_datetime(df['outcome_date'], errors='coerce')
    df['reply_memo_date'] = pd.to_datetime(df['reply_memo_date'], errors='coerce')
    
    df['calculated_reply_date'] = df['reply_memo_date']
    mask_need_calc = df['calculated_reply_date'].isna() & df['memo_response_time'].notna() & df['filing_date'].notna()
    if mask_need_calc.any():
        df.loc[mask_need_calc, 'calculated_reply_date'] = df.loc[mask_need_calc, 'filing_date'] + pd.to_timedelta(df.loc[mask_need_calc, 'memo_response_time'], unit='D')

    df['reply_to_outcome_days'] = None
    resolved_mask = df['case_status'].isin(['Discontinued', 'Granted', 'Dismissed'])
    resolved_with_dates = resolved_mask & df['outcome_date'].notna() & df['calculated_reply_date'].notna()
    
    if resolved_with_dates.any():
        df.loc[resolved_with_dates, 'reply_to_outcome_days'] = (
            df.loc[resolved_with_dates, 'outcome_date'] - df.loc[resolved_with_dates, 'calculated_reply_date']
        ).dt.days

    df_valid = df[df['reply_to_outcome_days'].notna() & (df['reply_to_outcome_days'] >= 0)].copy()
    if df_valid.empty:
        print("没有有效的 reply_memo 到 outcome 时间数据，跳过绘图。")
        return

    df_resolved = df_valid[df_valid['case_status'].isin(['Discontinued', 'Granted', 'Dismissed'])].copy()
    if df_resolved.empty:
        print("没有已结案的有效数据用于月度趋势，跳过绘图。")
        return

    # 限制在统计期内，且不超过今天
    period_start = f"{year}-01-01"
    today = pd.Timestamp.now()
    period_end = min(pd.Timestamp(f"{year+1}-12-31"), today)
    
    df_resolved = df_resolved[(df_resolved['outcome_date'] >= period_start) & (df_resolved['outcome_date'] <= period_end)]
    
    if df_resolved.empty:
        period_end_str = period_end.strftime('%Y-%m-%d')
        print(f"在 {year}-01-01 至 {period_end_str} 期间没有已结案的有效数据，跳过绘图。")
        return

    grouped = df_resolved.groupby([pd.Grouper(key='outcome_date', freq='ME'), 'case_status'])['reply_to_outcome_days'].agg(['mean', 'median'])
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    metrics = [('mean', '平均值'), ('median', '中位数')]
    axes = [ax1, ax2]
    
    for (metric, metric_name), ax in zip(metrics, axes):
        pivot_data = grouped[metric].unstack(level=-1)
        for col in pivot_data.columns:
            ax.plot(pivot_data.index, pivot_data[col], marker='o', linestyle='-', label=str(col))
        
        if reference_days is not None:
            ref_label = f"参考案 ({reference_days:.0f}天)"
            ax.axhline(y=reference_days, color='red', linestyle='--', linewidth=2, label=ref_label)
            if _cjk_prop:
                ax.legend(prop=_cjk_prop)
            else:
                ax.legend()
        
        if _cjk_prop:
            ax.set_title(f'{year}-{year+1} Memo回复到结案时间 - {metric_name}（天）', fontproperties=_cjk_prop)
            ax.set_xlabel('结案月份', fontproperties=_cjk_prop)
            ax.set_ylabel('天数', fontproperties=_cjk_prop)
        else:
            ax.set_title(f'{year}-{year+1} Memo Reply to Outcome Time - {metric_name} (days)')
            ax.set_xlabel('Outcome Month')
            ax.set_ylabel('Days')
        ax.tick_params(axis='x', rotation=45)

    title_main = f'{year}-{year+1} 按结案类型统计：Memo回复到结案时间分析'
    fig.suptitle(title_main, fontsize=16, fontproperties=_cjk_prop if _cjk_prop else None)
    fig.tight_layout()
    save_path = os.path.join(OUTPUT_DIR, f'mandamus_memo_to_outcome_trends_{year}.png')
    plt.savefig(save_path)
    print(f"📈 已保存 Memo 到结案时间统计图至: {save_path}")
    plt.close()

    # === 打印摘要统计内容 ===
    print("\n" + "="*60)
    print(f"【Memo回复到结案时间分析摘要 ({year}-{year+1})】")
    print("="*60)
    
    summary_overall = df_resolved.groupby(pd.Grouper(key='outcome_date', freq='ME'))['reply_to_outcome_days'].agg(['count', 'mean']).rename(columns={'count': 'resolved_count', 'mean': 'avg_days'})
    print(f"\n--- 每月总体结案统计 ({year}-{year+1}) ---")
    if not summary_overall.empty:
        summary_overall.index = summary_overall.index.strftime('%Y-%m')
        summary_overall['avg_days'] = summary_overall['avg_days'].astype(float).round(1)
        print(summary_overall) # 打印全部
    else:
        print("   (无数据)")

    monthly_status_agg = df_resolved.groupby([pd.Grouper(key='outcome_date', freq='ME'), 'case_status'])['reply_to_outcome_days'].agg(['count', 'mean'])
    
    # 构建展示用的索引：从 period_start 到 period_end
    # 使用 freq='ME'，但确保如果今天还在月中，也能显示当前月
    idx_range = pd.date_range(start=period_start, end=period_end + pd.offsets.MonthEnd(0), freq='ME')
    idx = idx_range[idx_range <= period_end + pd.offsets.MonthEnd(0)].strftime('%Y-%m')
    status_summary = pd.DataFrame(index=idx)
    
    found_any = False
    for status in ['Granted', 'Dismissed']:
        if status in monthly_status_agg.index.get_level_values('case_status'):
            s_data = monthly_status_agg.xs(status, level='case_status')
            s_data.index = s_data.index.strftime('%Y-%m')
            status_summary[f'{status}_cnt'] = s_data['count']
            status_summary[f'{status}_avg(days)'] = s_data['mean']
            found_any = True
    
    print(f"\n--- 每月分类结案统计 (Granted/Dismissed) ({year}-{year+1}) ---")
    if found_any:
        cols = [c for c in status_summary.columns if status_summary[c].notna().any()]
        if cols:
            for col in cols:
                if '_cnt' in col:
                    status_summary[col] = status_summary[col].fillna(0).astype(int)
                else:
                    status_summary[col] = status_summary[col].fillna(0).astype(float).round(1)
            print(status_summary[cols]) # 打印全部
        else:
            print("   (无数据)")
    else:
        print("   (未发现 Granted 或 Dismissed 案例数据)")

    total_count = len(df_resolved)
    avg_duration = df_resolved['reply_to_outcome_days'].mean()
    print(f"\n【总体汇总】 结案总数: {total_count} | 总体平均耗时: {avg_duration:.1f} 天")
    print("=" * 60)


def plot_case_duration_distribution(df, year=2025):
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
    
    title = f'Mandamus 案件结案时长分布 ({year}-{year+1})'
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
    save_path = os.path.join(OUTPUT_DIR, f'mandamus_duration_distribution_{year}.png')
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


def run_monthly_analysis(df, year=2025):
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

    # 限制统计展示范围为 24 个月，且最大不超过今天
    period_start = f"{year}-01-01"
    today = pd.Timestamp.now()
    period_end = min(pd.Timestamp(f"{year+1}-12-31"), today)
    
    # 填充缺失月份以确保展示，但上限为今天所在的月份
    # 使用 freq='ME' 配合 period_end 的 offsets 处理，确保包含当前月
    full_idx = pd.date_range(start=period_start, end=period_end + pd.offsets.MonthEnd(0), freq='ME')
    df_monthly = df_monthly.reindex(full_idx).fillna(0)

    # 绘制趋势图表
    plot_workload_trends(df_monthly, year)
    plot_outcome_trends(df_monthly, year)
    plot_timeline_trends(df_monthly, year)
    plot_memo_response_trends(df_monthly, year)
    
    # 准备仅限本统计周期内结案的数据，用于分布分析
    df_resolved_in_period = df_resolved[(df_resolved['outcome_date'] >= period_start) & (df_resolved['outcome_date'] <= period_end)].copy()

    # Memo reply->outcome plotting removed per user request.

    # 结案耗时分布分析 (仅限本周期内结案的案子)
    try:
        plot_case_duration_distribution(df_resolved_in_period, year)
    except Exception as e:
        print('绘制结案时长分布图失败：', e)

    # 打印文字报告
    print("\n" + "="*50)
    print(f"【{year}-{year+1} 年按月统计趋势分析报告】")
    print("="*50)
    print(f"\n--- 案件负荷与积压变化 ({year}-{year+1}) ---")
    print(df_monthly[['filing_count', 'resolution_count', 'net_change']].round(0).astype(int))

    # 文字版分布统计 (仅限本周期内结案的案子)
    analyze_resolution_time_distribution(df_resolved_in_period)

    print(f"\n--- 结案方式百分比 ({year}-{year+1}) ---")
    df_report = df_monthly.copy()
    df_report['resolution_total'] = df_report[['settled_count', 'granted_count', 'dismissed_count']].sum(axis=1).fillna(0)
    # convert to int for display counts
    df_report['resolution_total'] = df_report['resolution_total'].astype(int)

    def _count_pct_str(row, col_name):
        total = row['resolution_total']
        try:
            cnt = int(row.get(col_name, 0) if not pd.isna(row.get(col_name, 0)) else 0)
        except Exception:
            cnt = 0
        pct = (cnt / total * 100) if total > 0 else 0.0
        return f"{cnt}|{pct:.1f}%"

    df_report['Settled|Rate'] = df_report.apply(lambda r: _count_pct_str(r, 'settled_count'), axis=1)
    df_report['Granted|Rate'] = df_report.apply(lambda r: _count_pct_str(r, 'granted_count'), axis=1)
    df_report['Dismiss|Rate'] = df_report.apply(lambda r: _count_pct_str(r, 'dismissed_count'), axis=1)

    # 对中位数耗时进行四舍五入
    df_report['median_time_to_close'] = df_report['median_time_to_close'].round(1)
    df_report.index = df_report.index.strftime('%Y-%m')
    print(df_report[['resolution_total', 'Settled|Rate', 'Granted|Rate', 'Dismiss|Rate', 'median_time_to_close']])
    
    # DOJ Memo response reporting removed per user request.

    print("\n【趋势解读】")
    # 检查最近三个月的净积压变化
    recent_change = df_monthly['net_change'].tail(3).mean()
    # 检查最近三个月的中位数结案时间是否比之前三个月有所增加
    # 确保有足够的数据进行比较
    if len(df_monthly) >= 6:
        recent_median_time = df_monthly['median_time_to_close'].tail(3).mean()
        previous_median_time = df_monthly['median_time_to_close'].iloc[-6:-3].mean()
    else: # 如果数据不足6个月，则无法进行有意义的趋势比较
        recent_median_time = np.nan
        previous_median_time = np.nan

    if recent_change > 0:
        print("-> 🚨 警告：近期净积压变化平均为正值，法院/IRCC 正在承受更大压力，未来案件处理速度可能会减慢。")
    elif not np.isnan(recent_median_time) and not np.isnan(previous_median_time) and recent_median_time > previous_median_time:
        print("-> ⚠️ 注意：尽管积压变化不明显，但结案所需的中位数时间仍在增加，表明效率有所下降。")
    else:
        print("-> ✅ 稳定：目前案件积压趋势和结案耗时较为稳定。")



# --- 主执行区 ---
def main():
    parser = argparse.ArgumentParser(description='FCT Mandamus 案件分析与数据导出')
    parser.add_argument('--year', type=int, default=2025, help='要分析和导出的起始年份 (统计跨度为 YEAR 至 YEAR+1)')
    args = parser.parse_args()
    
    target_year = args.year
    
    # 1. 提取核心数据
    df_core = get_mandamus_data_for_analysis(target_year)
    
    # 2. 运行按月分析并绘制图表
    if not df_core.empty:
        run_monthly_analysis(df_core, target_year)
        
        # 3. 额外功能：导出详细信息为 JSON
        export_cases_to_json(target_year)
    else:
        print(f"未找到 {target_year}-{target_year+1} 期间 Mandamus 案件数据进行分析。")

####################################################33
if __name__ == "__main__":
    main()