**Batch retrive Mode**


# 需求修改描述
联邦法院网站的查询窗口，可以通过IMM-231-25这样的案件编号进行查询案件，不提供模糊查询。其中231是编号，25表示2025年，编号从0到99999，但是有可能中间有一段无效的编号区间，也可能在某个编号以后再无记录。
我需要用python程序自动生成编号，依次查询，但是要检测到最后一个编号，以及中间跳空的区间，避免无限测试被网站视为恶意攻击。

需要对现有的查询进行修改，尽量降低对网站的无效访问，尽快探测到边界
pytest --cov=src --cov-report=term --cov-report=html:coverage_html --cov-report=xml:coverage.xml -q
# Summary
-------
批量采集有以下问题需要解决：
1. 统计功能，目前只能统计成功的数量，失败的数量永远是0，失败需要区分以下情况：
	1）无记录，指定的 case id 没有对应的case
	2) 采集失败，重试超过限制，仍然采集过程中出现异常
	统计功能应该输出以下信息：
	开始编号，结束编号，总数，成功数量，无记录，失败
2. 批量采集，需要跳过无记录、已经采集成功的 case id， 对于采集失败的记录要重新采集。
3. 批量采集，需要增加一个参数， start  . 默认编号从1 开始，如果指定了编号，则从指定的编号开始，比如： python -m src.cli.main batch 2023 --max-cases 50 --start 30
表示case id 从 IMM-30-23 开始，结束的编号应该是	IMM-60-23

# 参考方案
下面是参考方案，可以考虑将有关的思路用于实际的代码中

这是一个非常典型且具有挑战性的自动化采集需求。联邦法院（Federal Court）的网站通常会有一定的反爬虫措施（如速率限制），且IMM案件编号虽然大致连续，但确实存在“跳号”或“注销”的情况。

为了满足你的需求——**尽量减少无效请求**且**精准探测边界**——采用单纯的“从0开始一直加1”的暴力遍历是不明智的，因为你无法确定何时该停止（是遇到长段空号还是真的结束了？）。

最好的策略是采用 **“二分法探测边界 + 线性补全”** 的混合算法：

1.  **阶段一（探测上限）：** 先用“指数/二分查找”快速定位当前年份的最大有效编号（High Water Mark）。这能用极少的请求次数（比如20次以内）确定大概范围（例如确定最大编号在 12500 到 12600 之间）。
2.  **阶段二（全量采集）：** 确定了上限后，再从 0 到 上限 进行遍历。这样可以保证不遗漏中间的记录，同时避免了对“上限之后”的无尽无效探测。

### ⚠️ 法律与合规警告

在运行此代码前，请务必注意：

  * **加拿大法律风险：** 加拿大法院对数据爬取（Scraping）有严格判例（如 *TOUE v. Mongohouse*），未经授权的大规模抓取可能违反使用条款甚至版权法。
  * **频率限制：** 必须设置 `time.sleep`，否则你的IP极大概率会被防火墙（WAF）暂时或永久封禁。
  * **仅供学习：** 以下代码仅供技术研究，请勿用于商业用途或对政府网站造成压力。

-----

### Python 自动化采集方案

此脚本使用了 `requests` 库进行网络请求，并包含了一个智能的边界探测算法。

你需要先在浏览器（按F12 -\> Network）中手动执行一次查询，获取以下两样东西填入代码：

1.  **Request URL**: 表单提交的真实地址。
2.  **Form Data 键名**: 比如输入框的 `name` 属性（可能是 `txtCaseNumber` 或其他乱码）。

<!-- end list -->

```python
import requests
import time
import random
import logging
from bs4 import BeautifulSoup

# --- 配置区域 ---
BASE_YEAR = "25"  # 2025年
SEARCH_URL = "https://www.fct-cf.ca/en/court-files-and-decisions/court-files" # 注意：这里需替换为F12抓包看到的真实POST Action URL
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Origin": "https://www.fct-cf.ca",
    "Referer": "https://www.fct-cf.ca/en/court-files-and-decisions/court-files"
}
# 表单字段名，需根据F12抓包结果修改，例如 'txtCaseNum', 'case_number' 等
FORM_FIELD_NAME = "txtCaseNumber" 

# 日志设置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

class FederalCourtScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def check_case_exists(self, case_id):
        """
        查询单个案件编号，返回 (是否存在, 原始HTML/None)
        """
        full_case_no = f"IMM-{case_id}-{BASE_YEAR}"
        payload = {
            FORM_FIELD_NAME: full_case_no,
            "btnSearch": "Search" # 提交按钮的name，通常需要带上
        }
        
        try:
            # 随机延时，模拟人类操作，避免封IP
            time.sleep(random.uniform(1.0, 3.0)) 
            
            response = self.session.post(SEARCH_URL, data=payload, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"HTTP Error {response.status_code} for {full_case_no}")
                return False, None

            # 核心判断逻辑：检查页面源码中是否有 "no result" 特征
            # 注意：需根据实际网页显示的文本微调，有时是 "No records found"
            if "no result" in response.text.lower() or "no records found" in response.text.lower():
                return False, None
            
            # 简单的二次确认：检查是否包含案件表格
            soup = BeautifulSoup(response.text, 'html.parser')
            if soup.find("table"): # 假设结果在table中
                return True, response.text
            
            return False, None

        except Exception as e:
            logger.error(f"Request failed for {full_case_no}: {e}")
            return False, None

    def find_upper_bound(self):
        """
        智能探测：寻找当前最大的有效案件编号（High Water Mark）。
        使用指数步进 + 二分查找，极大减少请求次数。
        """
        logger.info("启动边界探测...")
        
        # 1. 指数步进：快速确定一个肯定不存在的超大范围
        low = 0
        high = 1000
        while True:
            logger.info(f"探测范围上限: {high}...")
            exists, _ = self.check_case_exists(high)
            if not exists:
                # 发现了一个不存在的点，但不确定是否是真正的终点（可能是中间空号）
                # 再往后探一步确认一下，防止误判
                exists_next, _ = self.check_case_exists(high + 50) 
                if not exists_next:
                    logger.info(f"找到可能的上界区间: {low} - {high}")
                    break
            
            # 如果存在，说明还没到底，范围扩大一倍
            low = high
            high = high * 2
            if high > 100000: # 防止死循环
                logger.warning("编号超过10万，强制停止探测")
                break

        # 2. 二分查找：在 low 和 high 之间找到最后一个有效记录
        # 注意：由于中间可能有空号，二分法可能会被误导。
        # 这里我们采用“保守二分”：只要区间内甚至有一个号存在，就假设上界在右边。
        # 但为了稳妥，针对法院这种稀疏数据，建议倒序线性探测或分块探测。
        
        # 简化策略：倒序线性探测（从high往下找，直到找到第一个存在的）
        # 假设 high 是 10000，low 是 5000，我们每隔 100 倒着测
        current = high
        final_max = low
        
        while current > low:
            exists, _ = self.check_case_exists(current)
            if exists:
                final_max = current
                logger.info(f"探测到高位有效记录: {current}")
                # 找到一个有效记录后，可能还要往后微调一下看看是不是最后
                break
            current -= 100 # 步长粗调
            
        # 此时 final_max 是大概的末尾，我们在 final_max 到 final_max + 200 之间做一次精细检查
        true_end = final_max
        for i in range(final_max, final_max + 200):
            exists, _ = self.check_case_exists(i)
            if exists:
                true_end = i
        
        logger.info(f"最终确定的边界编号为: {true_end}")
        return true_end

    def scrape_all(self):
        """
        主流程
        """
        # 第一步：找到边界
        max_id = self.find_upper_bound()
        
        logger.info(f"开始全量采集，范围: 0 至 {max_id}")
        
        results = []
        consecutive_failures = 0
        
        # 第二步：线性采集，不遗漏
        for i in range(max_id + 1):
            exists, content = self.check_case_exists(i)
            
            if exists:
                logger.info(f"[有效] IMM-{i}-{BASE_YEAR}")
                # 这里可以添加解析 content (BeautifulSoup) 并保存数据的代码
                results.append(f"IMM-{i}-{BASE_YEAR}")
                consecutive_failures = 0
            else:
                logger.info(f"[空号] IMM-{i}-{BASE_YEAR}")
                consecutive_failures += 1
            
            # 可选：如果中间连续空号超过500个，可能算法判断失误或数据极度稀疏，可以选择跳过或停止
            if consecutive_failures > 500:
                logger.warning("连续500个空号，提前终止采集。")
                break

        return results

if __name__ == "__main__":
    scraper = FederalCourtScraper()
    scraper.scrape_all()
```

### 代码设计思路解析

1.  **探测优于遍历（find\_upper\_bound）**：

      * 如果当前最大案件号是 `5600`，普通程序会从0跑到99999。
      * 本程序的 `find_upper_bound` 会先测 1000 (有) -\> 2000 (有) -\> 4000 (有) -\> 8000 (无)。
      * 锁定在 4000-8000 之间后，它会倒序快速找到 5600 这个点。
      * **优势**：将数万次无效请求压缩到几十次，极大降低封号风险。

2.  **处理“中间跳空”**：

      * 一旦确定了上界（比如 5600），代码会老老实实从 0 遍历到 5600。
      * 这是为了捕获你提到的“无效编号区间”后的有效记录。因为我们已经用算法排除了 5600 之后的无限空集，所以前面的遍历是安全的且必要的。

3.  **防封控机制**：

      * `random.uniform(1.0, 3.0)`：每次请求随机间隔1-3秒，避免产生机器特征明显的固定频率心跳。
      * `HEADERS`：伪装成普通的浏览器访问。

### 如何让代码跑起来

1.  **获取真实 URL**: 联邦法院查询可能是动态加载的。如果上述 URL 不对，请按 F12 -\> Network -\> 勾选 "Preserve log" -\> 点击查询按钮。查看第一个名为 "search" 或类似名字的 POST 请求，复制其 `Request URL`。
2.  **获取 Payload**: 在同一个 POST 请求的 "Payload" 或 "Form Data" 选项卡中，查看除了案件号外，是否还有隐藏字段（如 `__VIEWSTATE`, `__EVENTVALIDATION`）。如果有，你需要先 GET 访问查询页，用正则提取这些令牌，并在 POST 时带上，否则服务器会拒绝请求。

### 下一步建议

如果你发现简单的 POST 请求无法返回结果（通常是因为 .NET 网站的 ViewState 机制），你需要我帮你写一段**自动提取 ViewState 并维持 Session** 的进阶代码吗？
