# Purge 命令日志改进

## 问题描述

原来的 purge 命令日志输出不清晰，无法看到：
- 清除了什么内容
- 是否成功或失败
- 程序输出了什么文件

## 改进内容

### 1. 增强的日志输出

在 `src/cli/main.py` 的第 1805-1840 行添加了详细的日志信息：

#### Dry Run 模式
- 明确标识 `[DRY RUN] Purge simulation completed - no data was actually deleted`
- 显示将要删除的数据库行数：`[DRY RUN] Database rows that would be deleted: X`
- 显示审计文件路径：`Purge summary written to: /path/to/audit.json`

#### 实际执行模式
- 明确标识 `Purge operation completed successfully`
- 显示实际删除的文件数量：`Files deleted: X files, Y directories, Z modal HTML files`
- 显示实际删除的数据库行数：`Database rows deleted: X`

### 2. 控制台摘要输出

添加了格式化的控制台输出：

```
=== Purge DRY RUN - Summary ===
Audit file: output/purge_audit_20251211_175837_2025.json
Files deleted: 0 files, 0 dirs, 0 modal files
Database rows would be deleted: 9998
========================================
```

### 3. 详细的审计文件

审计文件现在包含：
- 完整的时间戳和配置信息
- 文件删除的详细统计
- 数据库操作的详细结果
- 所有候选案例ID列表
- 错误和警告信息
- 操作备注

## 使用示例

### Dry Run（预览模式）
```bash
python -m src.cli.main purge 2021 --dry-run
```

输出：
```
2025-12-11 18:01:26 | INFO | [DRY RUN] Purge simulation completed - no data was actually deleted
2025-12-11 18:01:26 | INFO | [DRY RUN] Database rows that would be deleted: 9998

=== Purge DRY RUN - Summary ===
Audit file: output/purge_audit_20251211_180126_2021.json
Database rows would be deleted: 9998
========================================
```

### 实际执行
```bash
python -m src.cli.main purge 2025
```

输出：
```
2025-12-11 17:59:26 | INFO | Purge operation completed successfully
2025-12-11 17:59:26 | INFO | Files deleted: 0 files, 0 directories, 0 modal HTML files

=== Purge Summary ===
Audit file: output/purge_audit_20251211_175926_2025.json
Files deleted: 0 files, 0 dirs, 0 modal files
========================================
```

## 审计文件结构

审计文件包含以下关键信息：
- `timestamp`: 操作时间
- `year`: 目标年份
- `dry_run`: 是否为预览模式
- `files`: 文件操作统计
- `db`: 数据库操作统计
- `notes`: 操作备注
- `errors`: 错误信息（如有）

## 改进效果

1. **透明度**：用户可以清楚看到 purge 操作的所有细节
2. **安全性**：dry-run 模式让用户可以预览将要删除的内容
3. **可追溯性**：详细的审计文件记录了所有操作
4. **友好性**：格式化的控制台输出便于快速了解操作结果

## 相关文件

- `src/cli/main.py`: 主要改进位置
- `src/cli/purge.py`: purge 核心逻辑
- `output/purge_audit_*.json`: 生成的审计文件