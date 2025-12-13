# FCT-AutoQuery 操作指南

## 目录
1. [环境准备](#环境准备)
2. [日常操作](#日常操作)
3. [数据管理](#数据管理)
4. [问题排查](#问题排查)
5. [性能优化](#性能优化)
6. [维护任务](#维护任务)

---

## 环境准备

### 1. 激活环境
```bash
conda activate fct
```

### 2. 检查系统状态
```bash
# 检查数据库连接
python -c "from src.lib.config import Config; print('DB OK' if Config.get_db_config() else 'DB Error')"

# 检查Chrome浏览器
google-chrome --version

# 查看最新日志
tail -20 logs/scraper.log
```

### 3. 验证配置
```bash
# 检查当前配置
python -m src.cli.main --help
```

---

## 日常操作

### 单个案例采集

#### 基础用法
```bash
# 采集单个案例
python -m src.cli.main single IMM-12345-25
```

#### 强制重新采集
```bash
# 即使案例已存在也重新采集
python -m src.cli.main single IMM-12345-25 --force
```

#### 使用URL采集
```bash
# 支持完整URL格式
python -m src.cli.main single "https://www.fct-cf.gc.ca/en/activities/cases/imm-12345-25"
```

### 批量采集

#### 标准批量采集
```bash
# 采集指定年份的所有案例
python -m src.cli.main batch 2025
```

#### 定向采集
```bash
# 从编号1000开始，最多采集100个案例
python -m src.cli.main batch 2025 --start 1000 --max-cases 100

# 采集到指定编号为止
python -m src.cli.main batch 2025 --start 500 --max-cases 2000
```

#### 性能调优采集
```bash
# 快速采集（适合测试环境）
python -m src.cli.main batch 2025 --max-cases 50 --rate-interval 0.5 --backoff-factor 1.2

# 标准采集（生产环境推荐）
python -m src.cli.main batch 2025 --max-cases 100 --rate-interval 1.0 --backoff-factor 1.5

# 慢速采集（网络不稳定时）
python -m src.cli.main batch 2025 --max-cases 50 --rate-interval 2.0 --backoff-factor 2.0
```

#### 自定义探测参数
```bash
# 扩大探测范围
python -m src.cli.main batch 2025 --max-exponent 25 --max-cases 1000

# 缩小探测范围（快速测试）
python -m src.cli.main batch 2025 --max-exponent 15 --max-cases 50
```

### 统计信息查看

#### 整体统计
```bash
# 查看所有年份的统计
python -m src.cli.main stats

# 查看特定年份统计
python -m src.cli.main stats --year 2025

# 查看最近更新的日志统计
tail -50 logs/scraper.log | grep "Statistics"
```

---

## 数据管理

### 数据导出

#### 导出特定类型数据
```bash
# 导出filing_date为空的记录
python export_null_filing_date_cases.py

# 导出样本数据（用于测试）
python export_sample_null_cases.py
```

#### 数据备份
```bash
# 手动创建备份（输出目录）
mkdir -p output/backups/manual_backup_$(date +%Y%m%d_%H%M%S)
cp -r output/json/* output/backups/manual_backup_$(date +%Y%m%d_%H%M%S)/
```

### 数据清理

#### 问题数据清理
```bash
# 清理filing_date为空的success状态记录
python cleanup_null_filing_date_records.py

# 运行清理前，先分析影响范围
python analyze_null_filing_date_cases.py
```

#### 文件清理
```bash
# 清理特定年份的输出文件（安全操作）
python -m src.cli.main purge 2024 --dry-run  # 先预览
python -m src.cli.main purge 2024 --yes       # 确认执行

# 只清理文件，不清理数据库
python -m src.cli.main purge 2023 --files-only --yes
```

### 数据质量检查

#### 常规检查
```bash
# 检查数据完整性
python detailed_case_analysis.py

# 分析案例年份分布
python -c "
import psycopg2
from src.lib.config import Config
config = Config.get_db_config()
conn = psycopg2.connect(**config)
cur = conn.cursor()
cur.execute('SELECT EXTRACT(YEAR FROM scraped_at)::int as year, COUNT(*) FROM cases GROUP BY year ORDER BY year')
for row in cur.fetchall():
    print(f'{row[0]}: {row[1]} 条记录')
cur.close()
conn.close()
"
```

---

## 问题排查

### 常见问题解决

#### 1. 浏览器相关问题
```bash
# 问题：浏览器启动失败
# 解决方案：
sudo apt update
sudo apt install -y google-chrome-stable
pip install --upgrade webdriver-manager

# 清理浏览器缓存
rm -rf ~/.cache/google-chrome/
```

#### 2. 数据库连接问题
```bash
# 问题：数据库连接失败
# 检查服务状态：
sudo systemctl status postgresql

# 测试连接：
psql -h localhost -U fct_user -d fct_db -c "SELECT 1;"

# 重启数据库：
sudo systemctl restart postgresql
```

#### 3. 采集失败问题
```bash
# 问题：连续采集失败
# 查看详细日志：
tail -100 logs/scraper.log | grep -E "(ERROR|WARNING)"

# 检查网络连接：
ping www.fct-cf.gc.ca

# 重启采集服务：
python -m src.cli.main single IMM-1-25 --force  # 测试单个案例
```

#### 4. 内存不足问题
```bash
# 问题：内存使用过高
# 监控内存使用：
watch -n 2 'ps aux | grep python'

# 重启采集进程：
pkill -f "src.cli.main"
conda activate fct
python -m src.cli.main batch 2025 --max-cases 20  # 小批量测试
```

### 日志分析

#### 查看特定类型日志
```bash
# 查看采集统计
grep "Statistics" logs/scraper.log | tail -10

# 查看错误信息
grep "ERROR" logs/scraper.log | tail -10

# 查看成功采集的案例
grep "Successfully scraped case" logs/scraper.log | tail -20

# 查看UI操作时间
grep "UI_ACTION" logs/scraper.log | tail -20
```

#### 性能分析
```bash
# 分析采集速度
grep "Successfully scraped case" logs/scraper.log | 
awk '{print $NF}' | 
sed 's/(.*)//' | 
sort | uniq -c

# 统计错误类型
grep "ERROR" logs/scraper.log | 
awk -F':' '{print $NF}' | 
sort | uniq -c | 
sort -nr
```

---

## 性能优化

### 采集速度优化

#### 快速测试模式
```bash
# 测试环境快速采集
python -m src.cli.main batch 2025 \
    --max-cases 10 \
    --rate-interval 0.3 \
    --backoff-factor 1.0 \
    --max-exponent 12
```

#### 生产环境平衡配置
```bash
# 推荐的生产环境配置
python -m src.cli.main batch 2025 \
    --max-cases 200 \
    --rate-interval 1.0 \
    --backoff-factor 1.5 \
    --max-exponent 18 \
    --safe-stop-no-records 15
```

#### 网络不稳定环境配置
```bash
# 网络不稳定时的保守配置
python -m src.cli.main batch 2025 \
    --max-cases 50 \
    --rate-interval 2.0 \
    --backoff-factor 2.5 \
    --max-exponent 15 \
    --safe-stop-no-records 10
```

### 内存优化

#### 分批处理大量数据
```bash
# 分多个批次采集大量数据
for batch in {1..5}; do
    start=$((($batch - 1) * 200 + 1))
    python -m src.cli.main batch 2025 \
        --start $start \
        --max-cases 200 \
        --rate-interval 1.0
    echo "批次 $batch 完成，等待30秒..."
    sleep 30
done
```

#### 内存监控
```bash
# 实时监控内存使用
while true; do
    echo "$(date): $(ps aux | grep 'src.cli.main' | awk '{sum+=$6} END {print sum/1024 "MB"}')"
    sleep 30
done
```

---

## 维护任务

### 定期维护

#### 每日任务
```bash
# 1. 检查日志
tail -50 logs/scraper.log

# 2. 查看采集统计
python -m src.cli.main stats

# 3. 检查磁盘空间
df -h output/

# 4. 备份重要数据
tar -czf "output/backups/daily_backup_$(date +%Y%m%d).tar.gz" output/json/
```

#### 每周任务
```bash
# 1. 数据质量检查
python analyze_null_filing_date_cases.py

# 2. 清理旧日志
find logs/ -name "scraper-*.log" -mtime +7 -delete

# 3. 优化数据库
psql -h localhost -U fct_user -d fct_db -c "VACUUM ANALYZE;"

# 4. 性能报告
python detailed_case_analysis.py > weekly_performance_report.txt
```

#### 每月任务
```bash
# 1. 完整数据备份
mkdir -p output/backups/monthly_backup_$(date +%Y%m)
pg_dump -h localhost -U fct_user fct_db > "output/backups/monthly_backup_$(date +%Y%m)/fct_db_$(date +%Y%m%d).sql"

# 2. 清理旧文件
find output/ -name "*.json" -mtime +90 -delete
find output/backups/ -name "*.tar.gz" -mtime +180 -delete

# 3. 生成月度报告
python -c "
from src.services.enhanced_statistics_service import EnhancedStatisticsService
stats = EnhancedStatisticsService()
# 生成各月统计报告
print('月度数据统计报告已生成')
"
```

### 系统更新

#### 更新依赖包
```bash
# 检查过期包
pip list --outdated

# 更新关键包
pip install --upgrade selenium pandas loguru webdriver-manager psycopg2-binary
```

#### 配置调优
```bash
# 查看当前配置
python -c "
from src.lib.config import Config
print('当前配置:')
print(f'速率限制: {Config.get_rate_limit_seconds()}秒')
print(f'退避因子: {Config.get_backoff_factor()}')
print(f'最大重试: {Config.get_max_retries()}')
print(f'最大指数: {Config.get_max_exponent()}')
"

# 根据实际情况调整配置文件
```

---

## 应急处理

### 紧急停止恢复

```bash
# 1. 停止所有采集进程
pkill -f "src.cli.main"

# 2. 查看紧急停止原因
grep "Emergency stop" logs/scraper.log | tail -5

# 3. 重置系统状态
rm -f /tmp/.scraper_lock

# 4. 小批量测试恢复
python -m src.cli.main batch 2025 --max-cases 5 --rate-interval 3.0
```

### 数据恢复

```bash
# 从备份恢复
# 1. 恢复数据库
psql -h localhost -U fct_user -d fct_db < backup_file.sql

# 2. 恢复JSON文件
tar -xzf backup_file.tar.gz -C output/

# 3. 验证数据完整性
python -m src.cli.main stats --year 2025
```

---

## 技术参考

### 性能基准

| 操作类型 | 标准配置 | 优化配置 | 保守配置 |
|---------|----------|----------|----------|
| 单案例采集 | 5-8秒 | 4-5秒 | 8-12秒 |
| 批量采集 | 1案例/分钟 | 2案例/分钟 | 0.5案例/分钟 |
| 数据导出 | 1000记录/分钟 | 2000记录/分钟 | 500记录/分钟 |

### 监控指标

```bash
# 关键监控脚本
monitor_system() {
    echo "=== 系统监控 $(date) ==="
    echo "内存使用: $(free -h | grep Mem)"
    echo "磁盘使用: $(df -h output/ | tail -1)"
    echo "进程数: $(ps aux | grep 'src.cli.main' | wc -l)"
    echo "最近错误: $(grep 'ERROR' logs/scraper.log | wc -l)"
}

# 定期监控
while true; do
    monitor_system
    sleep 300  # 每5分钟
done
```

---

**注意**: 本操作手册基于项目当前版本编写，随着系统更新可能需要调整。建议定期查看 `docs/` 目录下的最新文档。