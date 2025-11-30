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

## 需求详细解释

以下是对采集过程中确定边界的查询需求的详细解释，确保逻辑清晰，并与实现对齐。

### 1. **整体目标**
- 需求旨在实现一个高效的“批量模式”来查找案例编号的上限（highest existing ID），例如 `IMM-<number>-<yy>` 格式的编号。
- 核心思想：避免盲目地从头到尾线性扫描（这在编号空间很大时效率低），而是结合**线性扫描**（找到初步边界）和**指数探测**（快速跳跃式检查更高编号）来确定上限。
- 最终输出：上限编号 A，以及确保从 A+1 开始的线性确认（不遗漏任何有效编号）。
- 强调：记录每次检查的状态，避免重复采集；使用指数探测来节省请求次数。
- 工作模式：探测模式——只是检测记录是否存在，记录检测状态，不采集案件详细数据； 采集模式——实际采集数据，并记录状态
- 程序重新启动，可以读取上次记录的状态，进行跳过处理。

### 2. **关键概念和参数**
- **init_number**：起始编号（例如 `--start 12000`）。
- **DEFAULT_SAFE_STOP_NO_RECORDS**（简称 safe_stop）：连续 'No data available' 的次数阈值（默认 10）。这表示“安全停止点”，即认为从这里开始是连续无数据区域。
- **DEFAULT_PROBE_BUDGET**（简称 probe_budget）：指数探测的最大指数 n（默认 10），控制 2^i 的最大值（i是索引，i_max=n例如 i=10 时 2^10=1024）。
- **A**：最近一个有效的编号（有数据的编号）。
- **i**：探测步长内的索引，从 1 开始（需求中提到“i 从 1 开始”）。
- **probe_budget**：指数，限制 n 的最大值。n从 0 到 probe_budget 。 

### 3. **详细步骤分解**
需求分为两个主要阶段：**探测上限** 和 **线性采集**。 

####  **步骤 1: 指数探测上限**
  **探测模式仅运行在这个阶段，采集模式的第一阶段**
  - 从 init_number 开始，指数递增检查，递增的step公式为 **step = 2^i**， 从0开始, 每个元素+1, i_max=probe_budget。
  - 检查方式：调用 `check_case_exists`（实际是 `search_case`），如果返回 True（有数据），记录为有效；如果 False（'No data available'），计数连续无数据次数。
  - 继续直到连续遇到 safe_stop 次 'No data available', 表示探测结束，最后一次有数据的case number, 就是上限编号。
  - 从 init_number 检查，后续的编号公式为 **A = init_number + step**。
    - i是index, i 从 0 开始,i_max=probe_budget（例如 i=0,1,2,3,...,10）。
    - 示例：假设 init_number=12000， safe_stop=10。
      - 第一次检查: number = init_number = 12000
      - 第二次检查: i=0, step = 2^0 , number = 12000 + step=12001
      - 第三次检查: i=1, step = 2^1 , number = 12000 + step=12002
      - 第四次检查: i=2, step = 2^2 , number = 12000 + step=12004
      - 以此类推，直到 i=probe-budget 或者采集模式下，已经采集的记录数量>=max_limit, number = 12000 + 2^10 = 121024
      - 如果在探测过程中出现 'No data available'： 如果检查到 i=8, number = 12000 + 2^8 = 12256, 查询结果为'No data available'，则开始计数连续无数据。如果连续达到safe_stop次无数据，则进入 **第二次扫描**。假如检测到 number=12260有数据，连续无数据的次数是5，则更新A=12260，i=0，从下一个编号 12261 开始重新探测。
  - **第二次扫描**：
    - 如果在指数增量扫描时，连续safe_stop次无数据，则需要回到最近的一次采集成功的位置，比如本次的number1=12256, 上次的number0=12128, 从number0 开始，i=0, 递增扫描，重复前面的流程。
    - 如果这次扫描的过程中，在number0 和 number1之间出现连续的'No data available'， 探测结束，确定上限是最近有case 数据的number。
  - **记录状态**：每次检查的结果存入 `visited` 字典，避免重复检查（例如，如果之前检查过某个编号，直接用缓存结果）， 如果二次扫描期间，遇到已经检查的编号，则需要跳过，按顺序对后续的编号进行查询。
  - 如果扫描到 max_limit 仍未达到 safe_stop，则 A = 最后一个有效编号（或处理边界情况）。
  - 采集模式下，需要实际采集并记录数据。


####   **步骤 2: 线性采集阶段**
  - 仅用于采集模式， 编号线性增长，依次采集
  - 结束条件： 记录数量达到 max_limit； 采集到达上边界
  - 跳过已经采集的记录，('No data available' or 已经采集过)  
  - 如果所有可能的 i 和 n 下都没有找到新记录，则 A 就是上限。
  - **记录状态**：每次检查的结果存入 `visited` 字典，避免重复检查（例如，如果之前检查过某个编号，直接用缓存结果）。

- **为什么指数探测高效？**
  - 线性扫描慢（逐个检查），指数探测跳跃大（例如从 12015 直接跳到 12015+1024=13039），快速覆盖大范围。
  - 如果有数据簇，探测会找到并重复；如果没有，快速停止。


### 4. **与之前实现的对比**
- **之前的问题（不符合需求）**：
  - 之前的实现是**全线性扫描**从 start 到 max_limit，找到最后一个 A，然后指数探测。
  - 这忽略了“直到连续 safe_stop 无数据才进入探测”的要求，导致效率低（在稀疏数据时仍扫描大量无数据区域）。
  - 用户反馈“原来的按指数递增的探测功能反而没有了”，因为我们为了兼容测试改成了全线性，但这偏离了需求的核心（先找边界，再指数跳跃）。

- **现在的修复**：
  - 将工作模式分为探测模式和采集模式
  - 先指数探测，如果找到新记录，重复探测（动态扩展），先确定了边界。
  - 先确定了边界，最后执行线性采集，在采集模式下，在探测的过程中，已经进行了部分数据的采集，以及标记。
  - 这完全对齐需求：高效探测，避免重复，记录状态。

### 5. **其他注意事项**
- **随机延时**：需求提到“随机延时，模拟人类操作，避免封IP”，这已在代码中实现（`time.sleep(random.uniform(1.0, 3.0))`）。
- **边界情况**：
  - 如果从 start 开始就是连续无数据，A = None 或 start-1。
  - 如果探测超过 max_limit，停止。
  - max_probes 作为安全上限，防止无限请求。
- **测试影响**：修改后，测试仍应通过，因为结果逻辑类似（上限正确，probes 控制在预算内）。

- **随机延时，模拟人类操作，避免封IP：** 
time.sleep(random.uniform(1.0, 3.0)) 