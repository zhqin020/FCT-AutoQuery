# Issue 0004: Batch retrieve mode — safe probing and robust scraping fallbacks

## Summary

Implement safe, efficient batch retrieval for `IMM-<number>-<yy>` case ids with:
- a probe mode to detect an upper bound (high-water mark) with low request budgets,
- a bounded traversal that classifies outcomes (`success`, `no-record`, `failed`),
- configurable safe-stop thresholds and polite crawling parameters.

This Issue drives the feature documented in `specs/0004-batch-mode-problem/spec.md` and the implementation plan in `specs/0004-batch-mode-problem/plan.md`.

## Acceptance Criteria

- CLI provides `probe` mode and `batch` mode with `--start` and `--max-cases`.
- Upper-bound detection runs within the configured probe budget and is tested via mocks.
- Final summary audit (JSON) and NDJSON attempt logs are produced under `output/`.
- Tests added cover `find_upper_bound`, classification logic, retry behavior, and summary correctness.

## Notes

- See `specs/0004-batch-mode-problem/tasks.md` for task breakdown and owners.

## Bug修复记录

### 2021年失败案例统计问题 - FIXED (2025-12-04)

**问题描述**：
- 运行统计显示14个案例失败，但日志中所有案例都显示"No data available"
- 用户质疑为什么没有真正的采集失败却有14个failed统计

**根本原因**：
- 批量处理逻辑bug：`scrape_single_case`返回`None`时没有区分原因
- 检测到"No data available"和真正的采集失败都返回`None`
- 批量处理错误地将所有`None`都当作失败处理，导致no_data案例被错误标记为failed

**修复内容**：
- 在`src/cli/main.py`第715-718行和第885-892行添加状态检查逻辑
- 检查案例是否已被标记为no_data，避免错误标记为failed
- 只有真正失败的案例才标记为failed状态

**测试验证**：
- 单元测试：`test_no_data_fix.py` ✅
- 集成测试：`test_batch_fix.py` ✅  
- 真实案例测试：`test_existing_no_data.py` ✅
- 单案例测试：`test_single_case.py` ✅

**修复效果**：
- 修复前：85成功, 14失败, 2无数据
- 修复后：85成功, 0失败, 16无数据

**相关文件**：
- 修复代码：`src/cli/main.py`
- 测试文件：`test_no_data_fix.py`, `test_batch_fix.py`, `test_existing_no_data.py`, `test_single_case.py`
- 详细分析：`issues/0004-batch-mode-problem-failure-analysis.md`

### 批处理服务状态显示问题 - FIXED (2025-12-04)

**问题描述**：
- 原本 `status=success` 的案例（如IMM-1-21）在批处理服务中显示为 `status=unknown`
- 日志显示：`status=unknown, reason='exists_in_db (status: success, retry_count: 0)'`

**根本原因**：
- `src/services/case_tracking_service.py` 中的 `get_case_status` 方法查询了不存在的数据库列
- SQL查询中包含 `created_at` 和 `updated_at` 列，但实际数据库表结构中不存在这些列
- 导致查询失败，返回 `None`，进而被标记为 `unknown`

**修复内容**：
- 修复 `get_case_status` 方法中的SQL查询，移除不存在的列
- 调整返回字段映射，使用 `last_attempt_at` 作为 `updated_at`
- 更新字段索引以匹配实际的表结构

**错误状态更正**：
- 执行 `correct_case_status.py` 脚本，将14个错误标记为 `failed` 的案例更正为 `no_data`
- 这些案例之前检测到了"No data available"但由于批处理bug被错误标记

**修复验证**：
- 测试脚本 `test_status_fix.py` 验证状态显示正常
- IMM-1-21 现在正确显示 `status=success`
- IMM-18-21 现在正确显示 `status=no_data`（之前为 failed）

**最终统计（修复后）**：
- success: 85
- no_data: 18
- failed: 0

## 需求详细解释

以下是对采集过程中确定边界的查询需求的详细解释，确保逻辑清晰，并与实现对齐。

### 1. **整体目标**
- 需求旨在实现一个高效的“批量模式”来查找案例编号的上限（highest existing ID），例如 `IMM-<number>-<yy>` 格式的编号。
- 核心思想：避免盲目地从头到尾线性扫描（这在编号空间很大时效率低），而是结合**线性扫描**（找到初步边界）和**指数探测**（快速跳跃式检查更高编号）来确定上限。
- 最终输出：上限编号, case data采集。
- 强调：记录每次检查的状态，避免重复采集；使用指数探测来节省请求次数。
- 工作模式：探测模式——只是检测记录是否存在，记录检测状态，不采集案件详细数据； 采集模式——实际采集数据，并记录状态
- 程序重新启动，可以读取上次记录的状态，进行跳过处理。

### 2. **关键概念和参数**
- **init_number**：起始编号（例如 `--start 12000`）。
- **DEFAULT_SAFE_STOP_NO_RECORDS**（简称 safe_stop）：连续 'No data available' 的次数阈值（默认 20）。这表示“安全停止点”，即认为从这里开始是连续无数据区域。
- **DEFAULT_PROBE_BUDGET**（简称 probe_budget）：指数探测的最大指数 n（默认 20），控制 2^i 的最大值（i是索引，i_max=n例如 i=20）。
- **A**：最近一个有效的编号（有数据的编号）。
- **i**：探测步长内的索引，从 1 开始（需求中提到“i 从 1 开始”）。
- **probe_budget**：指数，限制 n 的最大值。n从 0 到 probe_budget 。 

### 3. **详细步骤分解**
需求分为两个主要阶段：**探测上限** 和 **线性采集**。 

####  **步骤 1: 指数探测上限**
  **探测模式仅运行在这个阶段，采集模式的第一阶段**
  1. 从 init_number 开始，指数递增检查，递增的step公式为 **step = 2^i**， 从0开始, 每个元素+1, i_max=probe_budget。
    - 检查方式：先根据 case tracker 检查 case number 是否在数据库中已经存在，是否曾经采集过，如果已经采集成功，或 no data, 则跳过，进行后续case 的查询和采集。如果没有采集过，或者上次采集失败，则需要执行采集并记录结果。 

    - 从 init_number 检查，后续的编号公式为 **A = init_number + step**。
        - i是index, i 从 0 开始,i_max=probe_budget（例如 i=0,1,2,3,...,20）。
        - 示例：假设 init_number=12000， safe_stop=20。
        - 第一次检查: number = init_number = 12000
        - 第二次检查: i=0, step = 2^0 , number = 12000 + step=12001
        - 第三次检查: i=1, step = 2^1 , number = 12000 + step=12002
        - 第四次检查: i=2, step = 2^2 , number = 12000 + step=12004
        - 以此类推，直到 i=probe-budget 或者采集模式下，已经采集的记录数量>=max_limit, number = 12000 + 2^10 = 121024
    - 对于采集结果，根据情况进行相应的处理：
  2. 如果连续遇到 safe_stop 次 'No data available', 最后检测的编号是IMM-B-YY, 则需要返回最后一次有数据的case number :IMM-A-YY, 从A+1 开始重复开始指数递增检查。也可以从 case tracker 中查询离本次返回 no data 最近的一次有数据的编号作为新的起点 A, 以后循环指数递增采集，编号不能超过 B， 即编号的终点是IMM-B-YY。
  3. 每次连续出现 safe_stop 次 'No data available', 或者编号到达IMM-B-YY，就返回最后一次有数据的 case number 作为新的起点A继续探测。直到从A到B所有的采集都以'no data available'结束。最后一个有效的编号就是采集到的上限

  4. 如果扫描到 max_limit 仍未达到 safe_stop，最后一个有效编号就是上限。
  5. 采集模式下，需要实际采集并记录数据。
  6. 上限数据必须记录在数据库中，有效期为一周，超过一周，再次运行采集程序时，则以现有的上限为基础(init_number)继续探测新的上限， 如果已经有上限数据，并且在有效期内， 则直接进入步骤2. 线性采集阶段。


####   **步骤 2: 线性采集阶段**
  - 仅用于采集模式， 编号线性增长，从 init_number 依次采集, step=1
  - 结束条件： 记录数量达到 max_limit； 或采集到达上边界
  - number 从init_number 开始，跳过已经采集的记录，('No data available' or 已经采集过) 

 

### 4. **与之前实现的对比**
- **之前的问题（不符合需求）**：
 

- **现在的修复**：
 

### 5. **其他注意事项**
- **随机延时**：需求提到“随机延时，模拟人类操作，避免封IP”，这已在代码中实现（`time.sleep(random.uniform(1.0, 3.0))`）。
- **边界情况**：
  - 如果从 start 开始就是连续无数据，A = None 或 start-1。
  - 如果探测超过 max_limit，停止。
  - max_probes 作为安全上限，防止无限请求。
- **测试影响**：修改后，测试仍应通过，因为结果逻辑类似（上限正确，probes 控制在预算内）。

- **随机延时，模拟人类操作，避免封IP：** 
time.sleep(random.uniform(1.0, 3.0)) 