# 项目部署指南

## 环境要求

- Python 3.14 或更高版本
- Conda/Miniconda
- PostgreSQL 18.1 或更高版本
- Chrome/Chromium 浏览器（用于 Selenium）

## 快速部署步骤

### 1. 克隆项目（或复制项目文件）

```bash
# 如果是从 git 克隆
git clone <repository-url>
cd fct-scraper

# 如果是从压缩包
tar -xzf fct-scraper.tar.gz
cd fct-scraper
```

### 2. 创建 Conda 环境

**方法 A：使用完整配置（推荐用于相同操作系统）**

```bash
conda env create -f environment.yml
```

**方法 B：使用精简配置（推荐用于跨平台）**

```bash
conda env create -f environment-minimal.yml
conda activate fct
pip install -r requirements-pip.txt
```

**方法 C：手动创建（如果上述方法失败）**

```bash
# 创建基础环境
conda create -n fct python=3.14 -y

# 激活环境
conda activate fct

# 安装 conda 包
conda install beautifulsoup4 pandas numpy -y

# 安装 pip 包
pip install -r requirements.txt
```

### 3. 激活环境

```bash
conda activate fct
```

### 4. 配置数据库

**选项 A：使用默认配置**

默认配置已在 `src/lib/config.py` 中设置：
- Host: localhost
- Port: 5432
- Database: fct_db
- User: fct_user
- Password: fctpass

**选项 B：使用自定义配置（推荐）**

创建 `config.private.toml` 文件（不会提交到版本控制）：

```toml
[database]
host = "localhost"
port = 5432
name = "fct_db"
user = "fct_user"
password = "your_secure_password"

[app]
headless = true
browser = "chrome"
log_level = "INFO"
```

**选项 C：使用环境变量**

```bash
export DB_HOST="localhost"
export DB_PORT="5432"
export DB_NAME="fct_db"
export DB_USER="fct_user"
export DB_PASSWORD="your_password"
```

### 5. 初始化数据库

**新建数据库：**

```bash
# 完整初始化（需要 sudo 权限）
python scripts/init_database.py

# 或使用便捷脚本
scripts/db.sh init
```

**从备份恢复：**

```bash
# 如果有备份文件
scripts/db.sh restore backups/backup_fct_db_20260128_084430.sql
```

### 6. 验证安装

```bash
# 检查数据库状态
scripts/db.sh status

# 查看数据库信息
scripts/db.sh shell
```

## 项目结构

```
fct-scraper/
├── src/                    # 源代码
│   ├── lib/               # 库模块
│   │   ├── config.py      # 配置管理
│   │   ├── db.py          # 数据库连接
│   │   └── ...
│   └── ...
├── scripts/               # 管理脚本
│   ├── db.sh              # 数据库管理
│   ├── init_database.py   # 数据库初始化
│   ├── backup_database.py # 数据库备份
│   └── schema.sql         # 数据库结构
├── tests/                 # 测试文件
├── logs/                  # 日志目录
├── output/                # 输出目录
├── backups/               # 备份目录
├── environment.yml        # Conda 完整环境
├── environment-minimal.yml # Conda 精简环境
├── requirements.txt       # Python 依赖
├── requirements-pip.txt   # pip 包列表
└── README.md             # 项目说明
```

## 常用命令

### 数据库管理

```bash
# 初始化数据库
scripts/db.sh init

# 备份数据库
scripts/db.sh backup

# 恢复数据库
scripts/db.sh restore backups/backup_file.backup

# 查看状态
scripts/db.sh status

# 打开 PostgreSQL shell
scripts/db.sh shell

# 查看帮助
scripts/db.sh help
```

### 运行爬虫

```bash
# 激活环境
conda activate fct

# 查看帮助信息
python src/cli/main.py --help

# 单个案件爬取
python src/cli/main.py single IMM-12345-25

# 强制重新爬取已存在的案件
python src/cli/main.py single IMM-12345-25 --force

# 批量爬取指定年份的案件
python src/cli/main.py batch 2025 --max-cases 100

# 从指定编号开始爬取
python src/cli/main.py batch 2025 --start 30 --max-cases 10

# 更新模式：重新爬取进行中(on-going)的案件，追加 docket entries
python src/cli/main.py batch 2025 --update --max-cases 50

# 调整爬取速率（0.5秒间隔，更快但保持礼貌）
python src/cli/main.py batch 2025 --max-cases 100 --rate-interval 0.5 --backoff-factor 1.5

# 自定义最大指数探测
python src/cli/main.py batch 2025 --max-cases 50 --max-exponent 15

# 查看爬取统计
python src/cli/main.py stats

# 清除数据（干运行，仅审计）
python src/cli/main.py purge 2024 --dry-run

# 清除数据（实际执行，危险操作）
python src/cli/main.py purge 2024 --yes
```

### 命令说明

**子命令：**
- `single` - 爬取单个案件
- `batch` - 批量爬取指定年份的案件
- `stats` - 显示爬取统计信息
- `purge` - 清除指定年份的数据（危险操作）

**全局参数：**
- `--force` - 强制重新爬取已存在的案件
- `--rate-interval` - 请求间隔秒数（默认：1.0）
- `--backoff-factor` - 失败重试的指数退避系数（默认：1.0）
- `--max-backoff-seconds` - 最大退避延迟秒数（默认：60.0）

**batch 常用参数：**
- `--update` - 更新模式，重新爬取进行中的案件并追加 docket entries（跳过 no_data 记录）
- `--start` - 起始编号
- `--max-cases` - 最大爬取案件数
- `--max-exponent` - 指数探测的最大指数值

**purge 参数：**
- `--dry-run` - 干运行模式，只显示将要删除的数据
- `--yes` - 确认执行删除操作

### 查看日志

```bash
# 查看最新日志
tail -f logs/scraper-1.log

# 查看错误日志
grep ERROR logs/scraper-1.log
```

## 故障排查

### 问题 1: 无法连接数据库

```bash
# 检查 PostgreSQL 服务状态
sudo systemctl status postgresql

# 启动服务
sudo systemctl start postgresql

# 测试连接
psql -h localhost -U fct_user -d fct_db
```

### 问题 2: Python 包导入错误

```bash
# 重新安装依赖
conda activate fct
pip install -r requirements.txt --force-reinstall
```

### 问题 3: Conda 环境创建失败

```bash
# 清理 conda 缓存
conda clean --all -y

# 使用精简配置重试
conda env create -f environment-minimal.yml
```

## 注意事项

1. **安全性**：
   - 不要将 `config.private.toml` 提交到版本控制
   - 使用强密码保护数据库
   - 限制数据库访问权限

2. **备份**：
   - 定期备份数据库：`scripts/db.sh backup`
   - 备份文件保存在 `backups/` 目录

3. **日志**：
   - 日志文件位于 `logs/` 目录
   - 定期清理旧日志文件

4. **性能**：
   - 确保有足够的磁盘空间
   - 数据库建议使用 SSD 存储

## 更新部署

在现有环境上更新项目：

```bash
# 1. 激活环境
conda activate fct

# 2. 拉取最新代码（如果使用 git）
git pull

# 3. 更新依赖
conda env update -f environment.yml
pip install -r requirements.txt --upgrade

# 4. 备份数据库（重要！）
scripts/db.sh backup

# 5. 应用数据库迁移（如果有）
# python scripts/migrate.py

# 6. 重启服务
# systemctl restart fct-scraper
```

## 技术支持

如有问题，请：
1. 查看日志文件：`logs/scraper-1.log`
2. 查看 issues 目录：`issues/`
3. 联系维护人员

## 许可证

参考项目根目录的 LICENSE 文件
