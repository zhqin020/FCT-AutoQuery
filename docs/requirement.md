# Issue 0004: Batch scraper 

## Summary

Implement safe, efficient batch retrieval for `IMM-<number>-<yy>` case ids with:
- 以尽量低的压力，检测case number 的上边界 (high-water mark) ,
- 采集 case base info and 档案历史记录，记录采集结果，记录在数据库和 json文件中，便于后续分析。
- 能够重复运行，跳过已经采集的case，包括成功的和确认无效编号（no data）。对上次采集失败和没有采集的编号，进行采集。
- 采集失败多次，记录为failed, 下次运行可以重复采集。
- 输出采集统计结果，包括采集前的统计和采集后的最终结果。

## 需求详细解释

以下是对采集过程中确定边界的查询需求的详细解释，确保逻辑清晰，并与实现对齐。

### 1. **整体目标**
- 需求旨在实现一个高效的“批量模式”来查找案例编号的上限（highest existing ID），例如 `IMM-<number>-<yy>` 格式的编号。
- 核心思想：避免盲目地从头到尾线性扫描（这在编号空间很大时效率低），而是结合**指数采集**（快速跳跃式检查更高编号）来确定上限，和**线性采集**来完整采集指定范围内的case 数据。
- 最终输出：case and docket entries, json files, log file。
- 强调：记录每次检查的状态，避免重复采集,可以读取上次记录的状态，进行跳过处理。

### 2. **关键概念和参数**
- **init_number**：起始编号（例如 `--start 12000`）。
- **DEFAULT_SAFE_STOP_NO_RECORDS**（简称 safe_stop）：连续 'No data available' 的次数阈值（默认 20）。这表示“安全停止点”，即认为从这里开始是连续无数据区域。
- **DEFAULT_MAX_EXPONENT**（简称 max_exponent ）：指数探测的最大指数 n（默认 20），控制 2^i 的最大值（i是索引，i_max=n例如 i=20）。
- **A**：最近一个有效的编号（有数据的编号）。
- **B**：由指数和 max_cases 限制的最大编号。 
- **i**：探测步长内的索引，从 1 开始（需求中提到“i 从 0 开始”）。

### 3. **详细步骤分解**
需求分为两个主要阶段：**指数采集** 和 **线性采集**。 

####  **步骤 1: 指数采集**
  **探测模式仅运行在这个阶段，采集模式的第一阶段**
  1. 从 init_number 开始，指数递增检查，递增的step公式为 **step = 2^i**， 从0开始, 每个元素+1, i_max=max_exponent。
    - 检查方式：先根据 case tracker 检查 case number 是否在数据库中已经存在，是否曾经采集过，如果已经采集成功，或 no data, 则跳过，进行后续case 的查询和采集。如果没有采集过，或者上次采集失败，则需要执行采集并记录结果。 

    - 从 init_number 检查，后续的编号公式为 **A = init_number + step**。
        - i是index, i 从 0 开始,i_max=max_exponent（例如 i=0,1,2,3,...,20）。
        - 示例：假设 init_number=12000， safe_stop=20。
        - 第一次检查: number = init_number = 12000
        - 第二次检查: i=0, step = 2^0 , number = 12000 + step=12001
        - 第三次检查: i=1, step = 2^1 , number = 12000 + step=12002
        - 第四次检查: i=2, step = 2^2 , number = 12000 + step=12004
        - 以此类推，直到 i=max_exponent 或者已经采集的记录数量>=max_cases, number = 12000 + 2^10 = 121024
    - 对于采集结果，根据情况进行相应的处理：
  2. 如果连续遇到 safe_stop 次 'No data available', 或者采集的编号到达B(B= init_number + max_cases)，最后检测的编号是B, 则需要返回最后一次有数据的case number :A, 从A+1 开始重复开始指数递增检查。也可以从 case tracker 中查询离本次返回 no data 最近的一次有数据的编号作为新的起点 A, 以后循环指数递增采集，编号不能超过 B， 即编号的终点是IMM-B-YY。
  3. 每次连续出现 safe_stop 次 'No data available', 或者编号到达B，就返回最后一次有数据的 case number 作为新的起点A继续探测。直到从A到B所有的采集都以'no data available'结束。
  4. 如果扫描到 max_cases 仍未达到 safe_stop，最后一个有效编号就是上限。
  5. 上限数据必须记录在数据库中，有效期为一周，超过一周，再次运行采集程序时，则以现有的上限为基础(init_number)继续探测新的上限， 如果已经有上限数据，并且在有效期内， 则直接进入步骤2. 线性采集阶段。


####   **步骤 2: 线性采集阶段**
  - 编号线性增长，从 init_number 依次采集, step=1
  - 结束条件： 记录数量达到 max_cases； 或采集到达上边界
  - number 从init_number 开始，跳过已经采集的记录，('No data available' or 已经采集过) 

 

### 4. **与之前实现的对比**
- **之前的问题（不符合需求）**：
 

- **现在的修复**：
 

### 5. **其他注意事项**
- **随机延时**：需求提到“随机延时，模拟人类操作，避免封IP”，这已在代码中实现（`time.sleep(random.uniform(1.0, 3.0))`）。
- **边界情况**：
  - 如果从 start 开始就是连续无数据，A = None 或 start-1。
  - 如果探测超过 max_cases，停止。
  - max_probes 作为安全上限，防止无限请求。
- **测试影响**：修改后，测试仍应通过，因为结果逻辑类似（上限正确，probes 控制在预算内）。

- **随机延时，模拟人类操作，避免封IP：** 
time.sleep(random.uniform(1.0, 3.0)) 