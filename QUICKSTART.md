# FCT-AutoQuery 快速开始指南

## 🚀 5分钟快速上手

### 1. 环境激活
```bash
conda activate fct
```

### 2. 测试单个案例采集
```bash
# 采集一个测试案例
python -m src.cli.main single IMM-12345-25
```

### 3. 批量采集示例
```bash
# 采集2025年的50个案例
python -m src.cli.main batch 2025 --max-cases 50
```

### 4. 查看统计
```bash
# 查看采集统计
python -m src.cli.main stats
```

---

## 📋 常用命令速查表

| 任务 | 命令 |
|------|------|
| **单个案例** | `python -m src.cli.main single IMM-12345-25` |
| **强制重采** | `python -m src.cli.main single IMM-12345-25 --force` |
| **批量采集** | `python -m src.cli.main batch 2025 --max-cases 100` |
| **从指定编号开始** | `python -m src.cli.main batch 2025 --start 1000 --max-cases 50` |
| **快速采集** | `python -m src.cli.main batch 2025 --rate-interval 0.5 --max-cases 20` |
| **查看统计** | `python -m src.cli.main stats` |
| **年度统计** | `python -m src.cli.main stats --year 2025` |
| **安全清理** | `python -m src.cli.main purge 2024 --dry-run` |
| **实际清理** | `python -m src.cli.main purge 2024 --yes` |

---

## 🔧 性能调优参数

| 参数 | 默认值 | 快速模式 | 标准模式 | 保守模式 |
|------|--------|----------|----------|----------|
| 速率间隔 | 1.0s | 0.5s | 1.0s | 2.0s |
| 退避因子 | 1.5 | 1.0 | 1.5 | 2.0 |
| 最大重试 | 3 | 2 | 3 | 4 |
| 最大指数 | 20 | 15 | 18 | 20 |

### 快速模式命令
```bash
python -m src.cli.main batch 2025 --max-cases 20 --rate-interval 0.5 --backoff-factor 1.0 --max-exponent 15
```

### 标准模式命令
```bash
python -m src.cli.main batch 2025 --max-cases 100 --rate-interval 1.0 --backoff-factor 1.5 --max-exponent 18
```

### 保守模式命令
```bash
python -m src.cli.main batch 2025 --max-cases 50 --rate-interval 2.0 --backoff-factor 2.0 --max-exponent 20
```

---

## 📊 输出文件位置

```
output/
├── json/                    # JSON格式的案例数据
│   ├── 2025/              # 按年份分组
│   │   ├── IMM-12345-25.json
│   │   └── ...
├── backups/                # 备份文件
└── purge_audit_*.json     # 清理审计文件
```

---

## 🔍 日志查看

```bash
# 查看最新日志
tail -20 logs/scraper.log

# 查看成功采集记录
grep "Successfully scraped case" logs/scraper.log | tail -10

# 查看错误信息
grep "ERROR" logs/scraper.log | tail -5

# 查看采集统计
grep "Statistics" logs/scraper.log | tail -5
```

---

## ⚠️ 快速问题排查

| 问题 | 解决方案 |
|------|----------|
| **浏览器启动失败** | `sudo apt install google-chrome-stable` |
| **数据库连接错误** | `sudo systemctl status postgresql` |
| **权限不足** | `chmod +x logs/ output/` |
| **依赖缺失** | `pip install -r requirements.txt` |
| **端口被占用** | `pkill -f chrome` |

---

## 🎯 实用脚本

### 测试系统状态
```bash
python -c "
from src.lib.config import Config
print('✅ 配置正常' if Config.get_db_config() else '❌ 配置异常')
"
```

### 快速数据统计
```bash
python -c "
import psycopg2
from src.lib.config import Config
config = Config.get_db_config()
conn = psycopg2.connect(**config)
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM cases')
count = cur.fetchone()[0]
print(f'📊 总记录数: {count}')
cur.close()
conn.close()
"
```

### 检查最新输出
```bash
ls -la output/json/2025/ | tail -5
```

---

## 📞 获取帮助

```bash
# 查看完整帮助
python -m src.cli.main --help

# 查看子命令帮助
python -m src.cli.main batch --help
python -m src.cli.main single --help
python -m src.cli.main purge --help
```

---

## 💡 专业提示

1. **增量采集**: 系统自动跳过已采集的案例
2. **断点续传**: 重新运行时会从中断点继续
3. **智能探测**: 自动找到案例编号的上边界
4. **数据验证**: 每个案例都有完整性检查
5. **自动备份**: 清理操作前自动创建备份

---

## 🎉 成功验证

如果看到以下输出，说明系统运行正常：

```
2025-XX-XX XX:XX:XX | INFO | Successfully scraped case: IMM-12345-25 (attempt 1)
2025-XX-XX XX:XX:XX | INFO | Database save status for IMM-12345-25: success
2025-XX-XX XX:XX:XX | INFO | Per-case JSON written: output/json/2025/IMM-12345-25.json
```

---

**📚 更多信息**: 
- 完整文档: [README.md](README.md)
- 详细操作: [docs/operations-manual.md](docs/operations-manual.md)
- 问题报告: `issues/` 目录

**开始采集吧! 🚀**