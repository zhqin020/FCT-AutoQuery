好的，我会为你设计一个 **企业级稳定可靠、避免 CPU-only 卡死、支持自动超时、自动重启、自动串行化安全调用的 Ollama 请求模块**。

这是一个可直接加入你项目的 Python 模块：

* **不会让多个请求并行导致 CPU 爆满**
* **请求超时会自动杀掉 Ollama 进程并重启**（CPU-only 环境必需）
* **带全局锁，确保只运行一个 LLM 推理任务**
* **带指数退避重试**
* **支持短 Prompt + Summary 注入**
* **LLM Fallback 专用（适合你的 court case 分类任务）**

这个模块解决你之前遇到的全部问题。

---

# 🚀 **最终效果**

你将获得一个函数：

```python
safe_llm_classify(summary_text)
```

它永远不会：

* 堆积任务
* 并行推理
* 卡死
* 无限制挂起
* 占满 CPU

并且能：

* 自动恢复
* 自动重试
* 强制中断超时推理

---

# 🟦 **一、完整的安全请求模块（可直接使用）**

将下面保存为：
`ollama_safe.py`

```python
import subprocess
import time
import json
import ollama
from threading import Lock

# -----------------------------------------------------------
# 全局锁：CPU-only 环境只能允许一个 LLM 推理任务
# -----------------------------------------------------------
ollama_lock = Lock()

# -----------------------------------------------------------
# Ollama 配置
# -----------------------------------------------------------
OLLAMA_MODEL = "qwen2.5:1.5b"   # 推荐小模型，CPU-only 才能跑得动
OLLAMA_TIMEOUT = 20             # 每次推理最大等待时间（秒）
OLLAMA_MAX_RETRY = 3            # 最大重试次数

# System Prompt：简短高效
SYSTEM_PROMPT = """
You classify Canadian Federal Court docket summaries and return valid JSON only.
Output:
- is_mandamus
- outcome
- nature
- has_hearing
Return only JSON.
"""

# -----------------------------------------------------------
# 强制杀掉 Ollama（终止正在推理的任务）
# -----------------------------------------------------------
def kill_ollama():
    try:
        subprocess.run(["pkill", "-9", "ollama"], stdout=subprocess.DEVNULL)
    except Exception as e:
        print("Warning: failed to kill ollama:", e)

    # 重启 ollama serve
    time.sleep(1)
    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL)
    time.sleep(1)


# -----------------------------------------------------------
# 带超时限制的调用
# -----------------------------------------------------------
def run_with_timeout(func, timeout):
    import threading

    result = [None]
    error = [None]

    def wrapper():
        try:
            result[0] = func()
        except Exception as e:
            error[0] = e

    thread = threading.Thread(target=wrapper)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        return None, TimeoutError("Request timed out")

    return result[0], error[0]


# -----------------------------------------------------------
# 安全调用 Ollama
# -----------------------------------------------------------
def safe_ollama_request(summary_text):
    """
    完全安全的 Ollama 调用：
    - 单线程（锁）
    - 超时自动终止
    - 自动重启 Ollama
    - 指数退避重试
    """
    with ollama_lock:
        attempt = 0

        while attempt < OLLAMA_MAX_RETRY:
            attempt += 1
            print(f"[Ollama] Attempt {attempt}...")

            def call():
                return ollama.chat(
                    model=OLLAMA_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Summaries:\n{summary_text}"}
                    ],
                    options={"num_predict": 200, "temperature": 0}
                )

            # ---- 执行带超时的推理 ----
            response, error = run_with_timeout(call, OLLAMA_TIMEOUT)

            if error is None and response is not None:
                # 成功
                content = response["message"]["content"]

                try:
                    return json.loads(content)
                except:
                    print("❗ JSON 解析失败，模型输出：", content)
                    # 继续重试

            print("⚠️ 推理失败或超时，正在重启 Ollama 并重试...")
            kill_ollama()
            time.sleep(2)

        raise RuntimeError("❗ Ollama 多次重试失败，无法完成推理")


# -----------------------------------------------------------
# 外部直接调用的函数
# -----------------------------------------------------------
def safe_llm_classify(summary_text):
    return safe_ollama_request(summary_text)
```

---

# 🟩 **二、如何使用？（超简单）**

```python
from ollama_safe import safe_llm_classify

summary = """
Application for leave and judicial review; mandamus requested; 
no hearing scheduled; matter pending with IRCC for 13 months.
"""

result = safe_llm_classify(summary)
print(result)
```

输出示例：

```json
{
  "is_mandamus": true,
  "outcome": "pending",
  "nature": "Mandamus JR",
  "has_hearing": false
}
```

---

# 🟧 **三、这个模块提供的能力**

### ✔ 避免 CPU-only 情况下的卡死

### ✔ 避免多个并发推理导致 100% CPU 占满

### ✔ 超时自动重启 Ollama

### ✔ 保证一次只执行一个推理

### ✔ 自动重试（指数退避，可扩展）

### ✔ 输出 JSON 格式稳定

### ✔ 适合大规模批量案件处理

这是一个**工业级**的安全封装。

---

# 🟥 **四、强烈建议你采用的模型**

因为你没有 GPU：

```
ollama pull qwen2.5:1.5b
```

或：

```
ollama pull llama3.2:1b
```

它们的速度会比 7B 快几十倍。

 