目前的采集程序，在处理docket_entries 数据的采集时，出现 id_from_table 和 页面上的记录顺序相反的问题。
页面上的记录时倒序的，开始的id是最大值，table 底部的id=1.  但是采集程序忽视了这个列，在数据库中最后一个记录的 id_from_table =1，和实际相反。

需要做的工作：
1. 首先将数据库中的id 全部纠正过来
2. 修改采集程序，确保后续采集的 docket_entries 的 id_from_table 和页面匹配
在修改前，请先备份数据库

已采取的变更 / 下一步
-------------------
- 已更新 `src/services/case_scraper_service.py` 中的 `_extract_docket_entries`：
	- 现在会检测表头中的 ID 列（例如 'ID', '#', 'No.'）并优先使用该列的数值作为 `doc_id` / `id_from_table`。
	- 若无显式 ID 列，仍会尝试使用首列数字值（若不是日期列），否则回退到行号索引。
- 新增迁移脚本 `scripts/fix_docket_id_order.py`：
	- 会导出 `docket_entries` 的 CSV 备份到 `output/backups/`，并可在确认后执行按 case 逐个反转 id_from_table 的更新。
	- 使用方法示例：
		- 仅备份与干运行：
			- `python scripts/fix_docket_id_order.py --backup-dir output/backups --dry-run`
		- 执行修改（会要求输入 YES 进行二次确认）：
			- `python scripts/fix_docket_id_order.py --backup-dir output/backups --apply`

注意：脚本会先创建 CSV 备份作为恢复点。强烈建议在生产 DB 上执行任何写操作前，先执行完整的数据库备份（pg_dump 或其他备份方案）。