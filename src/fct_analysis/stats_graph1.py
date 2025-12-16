import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import re
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
import os
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

def get_mandamus_data_for_analysis():
    """从数据库拉取 2025 年的 Mandamus 案件数据"""
    engine = create_engine(DB_CONNECTION_STR)
    
    # 拉取 case_analysis 的核心数据，仅限2025年，并确保日期格式正确
    query = """
    SELECT 
        case_number,
        filing_date,
        case_status,
        visa_office,
        time_to_close,
        outcome_date,
        memo_response_time
    FROM case_analysis 
    WHERE case_type = 'Mandamus' 
    AND EXTRACT(YEAR FROM filing_date) = 2025
    ORDER BY filing_date ASC;
    """
    
    print("正在提取 2025 年 Mandamus 案件核心数据...")
    try:
        df = pd.read_sql(query, engine)
    except SAOperationalError as e:
        print("数据库连接失败：", str(e))
        print("请检查配置或环境变量 DB_CONNECTION_STR，或确保数据库凭据在 Config 中正确设置（get_db_config）。")
        return pd.DataFrame()
    except Exception as e:
        print("读取数据库时发生错误：", str(e))
        return pd.DataFrame()
    
    df['filing_date'] = pd.to_datetime(df['filing_date'], errors='coerce')
    df['outcome_date'] = pd.to_datetime(df['outcome_date'], errors='coerce')
    
    print(f"提取完成: {len(df)} 条 2025 年记录")
    return df

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
    fig.tight_layout()
    plt.show()


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
    plt.show()


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
    plt.show()


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
    plt.show()


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

    # 打印文字报告
    print("\n" + "="*50)
    print("【2025 年按月统计趋势分析报告】")
    print("="*50)
    print("\n--- 案件负荷与积压变化 (最近 6 个月) ---")
    print(df_monthly[['filing_count', 'resolution_count', 'net_change']].tail(6).round(0).astype(int))

    print("\n--- 结案方式百分比 (最近 6 个月) ---")
    df_recent_outcome = df_monthly.tail(6).copy()
    df_recent_outcome['resolution_total'] = df_recent_outcome[['settled_count', 'granted_count', 'dismissed_count']].sum(axis=1)
    # avoid division by zero
    df_recent_outcome['Settled Rate'] = df_recent_outcome.apply(lambda r: (f"{round(r['settled_count']/r['resolution_total']*100, 1)}%") if r['resolution_total']>0 else '0.0%', axis=1)
    df_recent_outcome['Granted Rate'] = df_recent_outcome.apply(lambda r: (f"{round(r['granted_count']/r['resolution_total']*100, 1)}%") if r['resolution_total']>0 else '0.0%', axis=1)
    print(df_recent_outcome[['Settled Rate', 'Granted Rate', 'median_time_to_close']])
    
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
    
    # 1. 提取核心数据
    df_core = get_mandamus_data_for_analysis()
    
    # 2. 运行按月分析并绘制图表
    if not df_core.empty:
        run_monthly_analysis(df_core)
    else:
        print("未找到 Mandamus 案件数据进行分析。")

    # 注意：微观分析 (Memo to Outcome) 需要 docket_entries 表，请在实际运行中整合 V3 和 V4 脚本。

####################################################33
main()    