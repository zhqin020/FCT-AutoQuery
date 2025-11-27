**Yearly Data Purge**

Summary
-------
Adds a safe, auditable CLI `purge <YEAR>` that removes archive files and database rows for a single calendar year. The command supports dry-run, optional backups, and an audit JSON output describing what would be or was removed.

Quick usage
-----------

- Dry-run (no destructive actions):

```
python -m src.cli.main purge 2023 --dry-run
```

- Real run with interactive confirmation and backup (default unless `--no-backup`):

```
python -m src.cli.main purge 2023 --yes --backup
```

- Force removing files even if DB purge fails (operator expresses intent):

```
python -m src.cli.main purge 2023 --yes --force-files
```

What it does
-----------

- Enumerates filesystem artifacts for the year: `output/<YEAR>` (directory) and modal HTML files matching the project's naming convention in `logs/`.
- Optionally creates a compressed backup of `output/<YEAR>` (tar.gz) before removal.
- Attempts to remove `cases` from the DB for the given year and cascade-delete dependent rows (schema-level cascades or explicit deletes performed by `db_purge_year`).
- Writes an audit JSON to `output/purge_audit_<TIMESTAMP>_<YEAR>.json` summarizing counts, removed items, any errors, and notes.

Important flags and safety notes
------------------------------

- `--dry-run`: enumerates candidates and writes the audit JSON without deleting anything.
- `--backup` / `--no-backup`: backups are created by default; `--no-backup` disables them. You can pass a destination path with `--backup <path>` to store backups elsewhere.
- `--files-only` / `--db-only`: restrict action to filesystem or DB only.
- `--force-files`: when a DB purge fails, proceed with file removals anyway (operator acknowledges risk). By default the command is permissive (continues with file deletes and records a note); consider requiring `--force-files` in production if you want the opposite behavior.
- `--sql-year-filter` (auto|on|off): try to use database-side SQL filter for year (Postgres `EXTRACT(YEAR FROM ...)`) when `on` or `auto`; falls back to safe Python-side filtering for SQLite or DBs that don't support the SQL expression.

参数说明 (CLI 参数详解)
---------------------

以下为 `purge <YEAR>` 子命令的完整参数说明、默认值和交互行为：

- `YEAR` (位置参数，必须)：
	- 说明：要清理的日历年度（例如 `2023`）。
	- 约束：必须为 4 位整数年份。

- `--dry-run` (可选，布尔)：
	- 说明：仅枚举将被删除的候选项并写入审计 JSON，不执行任何删除或备份操作。
	- 默认：`False`。
	- 典型用法：先运行 `--dry-run`，检查 `output/purge_audit_<TS>_<YEAR>.json`，确认后再执行真实删除。

- `--yes` / `-y` (可选，布尔)：
	- 说明：跳过交互式确认提示（等同于自动回答 `YES`）。
	- 默认：`False`（会在真实删除前要求输入 `YES` 以继续）。

- `--backup [PATH]` (可选，带可选参数)：
	- 说明：在删除之前对 `output/<YEAR>` 创建一个压缩备份（tar.gz）。
	- 参数：可选的 `PATH` 指定备份存放目录或完整目标路径；如果只写 `--backup` 则使用默认存储位置 `output/backups/`。
	- 默认行为：备份默认开启（即如果不传 `--no-backup` 则会创建备份）；如果显式传 `--no-backup` 则禁用备份。

- `--no-backup` (可选，布尔)：
	- 说明：禁用备份步骤（与 `--backup` 相反）。
	- 注意：如果同时传入 `--backup PATH` 与 `--no-backup`，以 `--no-backup` 为准，备份将被禁用并在审计文件中记录此决策。

- `--files-only` (可选，布尔)：
	- 说明：仅对文件系统进行操作（备份/删除 `output/<YEAR>` 与 modal HTML），不触及数据库。
	- 用例：当你只想清理磁盘空间或测试文件删除流程时使用。

- `--db-only` (可选，布尔)：
	- 说明：仅对数据库执行删除操作，不处理文件系统。
	- 互斥说明：如果同时传 `--files-only` 与 `--db-only`，命令会报错并退出；请只选择其一或都不传（表示两者都执行）。

- `--force-files` (可选，布尔)：
	- 说明：当数据库删除失败或出现错误时，仍然允许继续执行文件删除操作（用于在 DB 修复不方便或明确需要清理文件的场景）。
	- 默认：`False`。如果 DB 删除失败且未提供 `--force-files`，命令会默认继续删除文件并在审计中记录警告（当前实现为宽松策略）；建议在生产中将策略改为需要显式 `--force-files`，以避免意外数据不一致。

- `--sql-year-filter` (可选，字符串)：
	- 说明：控制是否优先使用数据库端的年份过滤表达式（例如 PostgreSQL 的 `EXTRACT(YEAR FROM scraped_at)`）。
	- 值：`auto`（默认）|`on`|`off`。
		- `auto`：在支持的数据库上尝试使用 SQL 表达式；若失败回退到 Python-side 过滤（安全但可能更慢）。
		- `on`：强制使用 SQL 年份表达式；若数据库不支持会直接抛出错误并中止（用于想要在支持 DB 上获得性能保证的场景）。
		- `off`：禁用 SQL 年份表达式，始终使用 Python-side 过滤（最大兼容性）。

- `--output-dir PATH` (可选)：
	- 说明：指定 `output/` 根目录路径（用于测试或非标准布局）。默认：项目根下的 `output/`。

- `--logs-dir PATH` (可选)：
	- 说明：指定 `logs/` 根目录路径，命令会在此目录下查找并删除与年度匹配的 modal HTML 文件。默认：项目根下的 `logs/`。

- `--audit-path PATH` (可选)：
	- 说明：覆盖生成的审计 JSON 的目标路径（完整文件名）。默认在 `output/` 下以 `purge_audit_<TS>_<YEAR>.json` 命名生成。

行为及优先级规则
------------------

- 如果既不传 `--files-only` 也不传 `--db-only`，命令会按顺序执行：备份（如启用）→ DB 删除 → 文件删除；所有主要步骤在审计文件中记录。
- 如果传 `--files-only`，将跳过 DB 操作；如果传 `--db-only`，将跳过文件操作。
- 当 `--dry-run` 被指定时，命令只会枚举候选项并写审计文件，其他任何写入、备份、删除操作都不会执行。
- `--force-files` 仅在 DB 删除失败时影响文件删除决策；它不会改变 `--dry-run`、`--db-only` 或 `--files-only` 的语义。

退出码（约定）
----------------

- `0`：成功（或 dry-run 成功枚举）。
- 非 `0`：发生错误（参数错误、DB 错误在 `--sql-year-filter=on` 下或其他未捕获异常）。具体错误信息会写入审计文件并通过 stderr 输出。

安全与操作建议
----------------

- 强烈建议在首次运行对生产数据进行真实删除之前，先执行 `--dry-run` 并由相关团队（DB/DevOps）审阅生成的审计 JSON。
- 生产部署建议保留常规 DB 备份/快照策略；此工具不会创建数据库级别的快照。
- 若希望更严格的安全策略，可在合并前将默认行为更改为：当 DB 删除失败时阻止文件删除（需要显式 `--force-files` 才允许继续）。

Audit JSON
----------

The audit file contains at least the following fields:

- `timestamp` — ISO 8601 timestamp when the run started
- `year` — integer year
- `dry_run` — boolean
- `backup` — path to created backup archive or `null`
- `files` — object with per-path counts (e.g., `output_count`, `modal_html_removed`)
- `db` — object summarizing DB rows removed per-table and any SQL fallback used
- `errors` — array of error messages (empty on success)
- `notes` — array of human-readable notes (e.g., why fallback or `force-files` behavior was used)

Example recovery steps
----------------------

1. If files were removed but backup exists, restore from the tarball:

```bash
tar -xzf output/backups/output_backup_2023_<TIMESTAMP>.tar.gz -C /path/to/recover/
```

2. To restore DB rows, use a pre-existing DB backup (this tool does not create full DB dumps). If you need DB-level restore, restore from your DB backups or WAL as appropriate for your environment.

3. If you ran with `--force-files` after a DB failure, inspect `output/purge_audit_<TIMESTAMP>_2023.json` and coordinate with DB owners to recreate or re-import removed files/rows if needed.

Operational recommendations
-------------------------

- Run the purge in `--dry-run` mode first and inspect the audit JSON.
- Keep nightly/weekly DB backups; this tool is not a substitute for database backups.
- For production environments, consider switching to a policy that requires `--force-files` to be explicitly passed when DB purge fails (prevent accidental data loss).
- Have DevOps or a DBA review the PR and the SQL-year-filter behavior for performance on large tables.

Files changed by implementation
------------------------------

- `src/cli/purge.py` — CLI handler and orchestration
- `src/services/purge_service.py` — DB purge logic with SQL-year-filter and fallback
- `src/services/files_purge.py` — backups and atomic filesystem removal

Reference (examples)
--------------------

Dry-run example:

```
python -m src.cli.main purge 2023 --dry-run
cat output/purge_audit_20251126T093045_2023.json
```

Real run with backup:

```
python -m src.cli.main purge 2023 --yes --backup
```

If you want me to also add an explicit recovery playbook (for DB restore steps per hosting type), tell me which DB host(s) we should document (e.g., self-hosted Postgres, AWS RDS, GCP Cloud SQL).


# 问题修改

**项目名称**：联邦法院案件自动查询系统 (FCT-AutoQuery)
**版本号**：V1.1
**日期**：2025-11-25 

## 1. 年度数据清理功能
增加 purge 命令，可以指定年度
删除数据包括：
1. 数据库记录清除
2. output 目录年度目录删除
3. logs 目录run_logger 以及 html 文件删除 （指定年度）
