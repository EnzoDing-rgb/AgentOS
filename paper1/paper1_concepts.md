# AgentOS Paper 1 概念导读

> **这份文档回答一个问题：AgentOS Paper 1 到底在做什么？**
>
> 包含问题动机、核心概念、实验直觉和术语表。不含接口/算法/实现细节。
>
> 读完这份，再看 `paper1_design.md`（规格书）和 `paper1_implementation.md`（操作手册）。

---

## Big Picture：一句话 + 一张图

**一句话**：AgentOS 是夹在 *Agent* 和 *LLM 后端*之间的“调用操作系统”，核心目标不是“系统不崩”，而是**在预算约束下最大化有效质量（quality under budget）**——让钱花得值，同时把交互体验（TTFT/P99）作为必须满足的体验底线（SLO）。

**核心思路**：把问题拆成三件事——**管入口（准入/排队）**、**选模型（质量-成本权衡）**、**回收资源（抢占/僵尸）**。系统做的每个决策都写进 `events.jsonl`，所以这不是“讲故事”，而是可度量、可复现的实验系统。

```text
Workload（实验剧本：turns[] + mock + 预算/并发）
        |
        |  语义上：若干 Task 被拆成一串 Turn（Task 不必在文件里显式出现）
        v
  每个 Turn = 一次 llm.call（priority / task_type / difficulty_weight …）
        |
        v
======================  AgentOS（治理层）  ======================
|  Governor（准入/排队）                                     |
|  - 预算不够/并发满 -> wait/reject，避免 429 雪崩与破产        |
|                                                          |
|  ModelSelector（选模型）                                   |
|  - 先过“质量够用”门槛（按 task_type）                        |
|  - 再结合 budget_factor（松紧度）与 cost_est 选更省钱的模型    |
|  - 新口径：budget_factor 用“加权进度”算 target_spend         |
|                                                           |
|  Preemption + ZombieDetector（动态资源回收）                |
|  - 交互请求插入：必要时抢占低优先级任务，让出并发槽               |
|  - 卡死/超长：识别僵尸并回收，释放预算与并发槽                   |
===============================================================
        |
        v
LLM 后端池（云端 API / 本地模型）
        |
        v
events.jsonl（唯一真相源）  --->  summary.json / 指标（完成率/花费/TTFT/429…）
```

---

## 问题空间重定义：从“系统稳定性”到“成本-质量优化”

同类工作（例如 AgentRM）更常把问题讲成“怎么让系统稳定、不崩”。Paper 1 更适合把主问题讲成“怎么让预算花得值”：把稳定性机制（限流、准入、回收）降级为**约束与实现手段**，把“质量-成本最优化”放到叙事的正中间。

| AgentRM关注 | Paper 1 应关注 |
|---|---|
| 系统稳定性 | **成本可控性**（budget under control） |
| 吞吐量 | **质量/成本比**（quality per dollar） |
| 优先级排队 | **任务价值感知**（哪些 turn 值得花贵模型） |
| 静态约束 | **动态预算适应**（预算松紧度驱动在线决策） |

把这张表接到 RQ 的表达上，会让三条 RQ 更像是在逼近同一个优化目标（cost-effectiveness）：
- **RQ1**：把外部失败（429）变成内部可控排队，从而让 cost/quality 指标可被稳定测量
- **RQ2**：预算约束下最大化质量（关键：任务价值感知 + budget-aware routing）
- **RQ3**：把尾延迟与僵尸损耗视为“无效成本”，通过抢占/回收提升体验并减少浪费

对应地，评估指标也应随之对齐（如果别的文档已展开公式，这里只点名口径；细节见 `paper1_extended.md`）：
- **Quality-Weighted Completion Rate（QWCR）**：不只算完成数量，而是算“有效完成量”
- **Cost efficiency**：例如 \( \text{USD per quality point} \) 或 \( \text{quality per dollar} \)
- **Formal analysis**：给出一个可证明的 ModelSelector 最优/近最优结论（例如两后端 setting 下的边际收益/边际成本排序最优性，或在线情形的竞争比分析）

**三条研究问题（RQ）是一条主线的三步递进**：
- **RQ1（让约束可控）**：只开 Governor，把外部限流冲突变成内部排队，显著降低 429 与失败，让后续“质量/成本”对比有意义。
- **RQ2（让钱花得值）**：开 Governor + ModelSelector，在同一预算下做任务感知选模，最大化有效质量（而不只是完成更多 turn）。
- **RQ3（让浪费可回收）**：在 RQ2 基础上加 Preemption + ZombieDetector，把尾延迟与僵尸燃烧当作无效成本回收掉，提升交互体验并挽救吞吐。

**你讲这页时的顺序（照着念就行）**：
- Paper 1 关注的对象不是“单次问答”，而是 *Agent 把一次请求拆成很多 Turn* 的真实工作流。
- 系统要同时管三种资源：预算（钱）、限流/并发（次数与槽位）、优先级（交互 vs 后台）。
- 所有设计都落在三块：Governor 负责“能不能进、怎么排队”，ModelSelector 负责“用哪个模型”，Preemption/Zombie 负责“把被占住的资源拿回来”。
- 结果评估完全基于 `events.jsonl`：每个 Turn 的 created/dispatch/completed/failed/reaped 都可追溯，指标可复算。

---

## 概念对齐：Workload → Task → Turn

很多人困惑：“用户脑子里是一个 Task，文档里为什么满屏 Turn？”  
用三层**由外到内**说清楚就顺了：

| 层级 | 名称 | 是什么 | 谁管 |
|---|---|---|---|
| 最外 | **Workload** | 一次实验用的**剧本/负载**：里面列出（或隐含）要跑哪些 Turn、何时到、mock 怎么表现 | 实验作者 / `agentos run --workload` 指向的文件 |
| 中间 | **Task** | **高层目标**（例如“把这个模块拆成三个文件”）；一个 Task 通常会被上层拆成多步 | 上层 Agent/工作流；Paper 1 **不**在调度器里建 Task 对象 |
| 最小 | **Turn** | **一次** `llm.call()`；调度、记账、事件日志的**最小单位** | AgentOS（本文核心） |

**Workload 文件长什么样**：主体往往是 `turns: [ ... ]`——你可以把它读成：**把若干 Task 拆解后的 Turn 序列，写进同一份剧本里**（实验里也可以刻意写成“平铺的一条龙”，不标 Task 边界）。

**为什么 Paper 1 只调度 Turn**：AgentOS 只保证“每个 Turn 在预算与并发约束下跑完”，不在本文展开 Task 级编排（多 Task 分预算、跨 Task 依赖、谁抢谁的额度）。这是**研究边界**，不是概念缺失。

**钱从哪算**：账单按 **Token** 进 Turn 的结算；Token 不单独占一层，只是 Turn 内部的计费粒度。

---

## 1. 从一个具体场景开始

你在 Cursor 里让 AI agent 帮你重构一个项目。你打了一句话："把这个模块拆成三个文件"。

接下来 agent 不是"想一下就给你答案"——它要做一连串事情：

1. **读代码**：调用 LLM，把当前文件内容发过去，问"这个模块的结构是什么？"
2. **制定方案**：再调用 LLM，问"怎么拆最合理？"
3. **生成文件 A**：再调用 LLM，问"按这个方案，第一个文件的代码是什么？"
4. **生成文件 B**：再调用 LLM……
5. **生成文件 C**：再调用 LLM……
6. **验证**：再调用 LLM，问"这三个文件能不能正确 import？"

一次用户请求，agent 背后调用了 **6 次** LLM。每次调用就是一个 **Turn**。

**Turn 是本文最核心的概念：一次完整的 LLM 调用，从发出请求到拿回结果。**

---

## 2. 每个 Turn 要花什么

每次调用 LLM，不是免费的。一个 Turn 同时消耗三样东西：

**钱**——LLM 按 token（文本片段）计费。你发过去 500 token、模型回你 300 token，都要付费。GPT-4 级别的模型，一次调用可能花 $0.05；一个便宜的本地模型，可能只花 $0.0005。同一个任务在不同模型上的花费可以差 100 倍。

**API 调用次数**——供应商限制了每分钟能调多少次（比如每分钟 60 次）。超过就报 429 错误（"你太频繁了"）。但这个额度每分钟自动刷新——不像钱花了就没了。

**并发槽**——同时在空中飞着的 LLM 请求数有上限。注意，瓶颈不在你自己的机器（你的 CPU/内存发 1000 个 HTTP 请求毫无压力），而在**对面**：云端 API 有每分钟请求数上限（超了报 429），本地 GPU 有显存上限（同时推理太多请求会 OOM）。并发槽就是一个信号量（semaphore）："最多同时 N 个请求在跑"。

**N 怎么定？** 它是外部硬约束的已知量，不需要运行时探测：云端 API 的 RPM 写在供应商文档里（如 OpenAI tier-1 = 60 RPM），本地 GPU 的推理并发数取决于显存和模型大小，也是部署时已知的。所以 N 在启动时配置一个保守值即可（如 RPM=60 → N=16），不需要动态自适应。Paper 1 的设计刻意把并发槽固定为启动参数——实验要比较不同调度策略的效果，如果 N 在运行中不断变化，就引入了额外变量，结论不干净。系统中唯一的动态反馈信号是**预算水位**（花快了→选便宜模型，花慢了→允许好模型），它作用在"选哪个模型"上，而不是"同时跑几个"。

---

## 3. 这个系统给谁用

**短回答：Paper 1 的设计是通用的，不区分个人/企业。**

AgentOS 是一个**中间件**——夹在 agent 和 LLM 之间。不管上面跑 1 个 agent 还是 50 个，不管下面接本地模型还是云端 API，同样的问题都存在：

| | 个人（你在 macOS 上用 Cursor） | 企业（云端 50 个 agent） |
|---|---|---|
| 预算 | OpenAI 账户这个月只剩 $10 | 团队月预算 $5000 |
| 限流 | 你的 key RPM=60 | 企业 key RPM=3000，但 50 个 agent 一起打还是不够 |
| 优先级 | 你在等 Cursor 回答 vs 后台跑 lint | 老板的实时请求 vs 后台批量报告 |
| 僵尸 | agent 卡死占着你的 API 额度 | 某个 agent 跑飞烧了 $200 |

架构完全一样，只是参数不同（预算大小、并发槽数量、后端数量）。

---

## 4. 多 agent 共享资源时，问题出在哪

现在想象不是你一个人在用，而是 **50 个 agent 同时在跑**——有的在帮人写代码，有的在后台批量处理文档，有的在做数据分析。它们全都在调用同一个 LLM API。

**没人管钱**：所有 agent 都用最贵的模型，不管任务难不难。一个只需要把 JSON 格式化一下的简单任务，也在烧 GPT-4 的额度。结果：钱前半段就花光了，后面的重要任务没钱做。

**没人管次数**：50 个 agent 同时疯狂发请求，一秒钟打出去 200 个调用，API 限制是每分钟 60 次——直接被封，所有人一起失败。

**没人管顺序**：你正在屏幕前等 agent 回答你的问题（很急），但并发槽全被后台的批量任务占着。你的请求排在第 47 位，等了 30 秒还没轮到。

**僵尸调用**：有个 agent 的 LLM 调用卡死了——不返回也不报错，就一直占着并发槽和钱。其他 agent 只能干等。

这就是 AgentOS 要解决的问题。

---

## 5. Interactive 和 Batch：两种优先级

Turn 有两种优先级，不是按"任务类型"分的，而是按**"有没有人在等"**分的：

**Interactive（交互式）**= 有用户正在屏幕前等结果。用户能感知到延迟，等久了就烦了。比如：
- 你在 Cursor 里打了一句话，等 agent 回答
- 你在 ChatGPT 里问了个问题，看着光标在闪

**Batch（批量式）**= 没有人在盯着等。任务在后台慢慢跑，晚几秒甚至几分钟都无所谓。比如：
- 后台自动给 100 个文件生成文档
- 定时批量翻译一批邮件
- 离线跑一组数据分析

**同一种任务既可以是 interactive 也可以是 batch**。"内容生成"（generation）不一定是 interactive——关键看场景：

| 场景 | 任务类型 | 优先级 | 为什么 |
|---|---|---|---|
| 用户在 IDE 里等 agent 写代码 | generation | **interactive** | 用户在等，延迟 = 痛感 |
| 后台批量给 100 封邮件生成回复草稿 | generation | **batch** | 没人盯着，慢点没关系 |
| 用户问"这个 bug 怎么修？" | reasoning | **interactive** | 用户在等 |
| 离线批量分析 200 篇文章生成摘要 | summarization | **batch** | 后台任务 |

所以 workload 文件里每个 Turn 都会标明 `priority: "interactive"` 或 `"batch"`——这是在模拟"这个调用是在什么场景下发出的"。

---

## 6. 为什么一个 Workload 有很多 Turn

回到第 1 节的例子：一个用户请求产生 6 个 Turn。现在有 10 个用户同时在用，每人的请求平均产生 5 个 Turn——系统一共要处理 50 个 Turn。

**Workload 就是"一批需要处理的 Turn 的清单"**。它模拟的是一段时间内系统收到的所有 LLM 调用请求。

一个 workload 文件长这样（简化版）：

```json
{
  "workload_id": "demo",
  "turns": [
    { "turn_id": "t001", "at_ms": 0,    "priority": "interactive", "task_type": "generation" },
    { "turn_id": "t002", "at_ms": 50,   "priority": "batch",       "task_type": "transform"  },
    { "turn_id": "t003", "at_ms": 100,  "priority": "interactive", "task_type": "reasoning" },
    { "turn_id": "t004", "at_ms": 100,  "priority": "batch",       "task_type": "summarization" },
    { "turn_id": "t005", "at_ms": 200,  "priority": "batch",       "task_type": "retrieval" }
  ]
}
```

怎么读这个文件：

- **`turn_id`**：每个 Turn 的编号
- **`at_ms`**：这个 Turn 在第几毫秒到达系统。`at_ms: 0` 表示一开始就来了，`at_ms: 100` 表示 100ms 后才来。这模拟了"请求不是同时到达的"
- **`priority`**：interactive 或 batch
- **`task_type`**：这个 Turn 在做什么类型的事（`generation / reasoning / retrieval / transform / summarization / conversation`）。类型影响的是"需要多强的模型"——生成/推理通常更吃模型能力，而 `transform`（格式转换、翻译）最适合便宜模型

这些 Turn 可能来自同一个 agent session（一个用户请求拆出来的多步），也可能来自不同 agent（不同用户同时在用）。**Workload 不关心"谁发的"，只关心"系统要处理哪些 Turn、什么时候到、什么优先级"。**

在仓库的实现里，workload 通常按研究问题拆分成几份文件，便于复现实验并对应论文图表（例如 `paper1/workloads/rq1_mixed.json / rq2_mixed.json / rq3_zombie.json` 这类命名；具体以 runbook 为准）。

---

## 7. 为什么要用 Mock（模拟），不调真模型

这是一个实验系统。我们要回答的问题是：**不同的调度策略，效果差多少？**

比如我们想比较：
- 策略 A：所有请求无脑发给最贵的模型
- 策略 B：根据任务类型和预算情况智能选模型

如果每次都调真实的 GPT-4，问题是：
1. 每次调用的延迟不一样（网络波动、服务端排队……），无法公平比较
2. 每次调用花真钱，跑 100 次实验就破产了
3. 结果不可复现——同样的输入，两次调用可能返回不同长度的回答

所以 workload 里每个 Turn 除了基本信息，还有一个 `mock` 字段，预设了“**这个 Turn 在不同后端上**会表现成什么样”（延迟/成本/质量/错误）。主线实验用它保证可控、可复现。

```json
{
  "turn_id": "t001",
  "at_ms": 0,
  "priority": "interactive",
  "task_type": "generation",
  "mock": {
    "gpt4": {
      "input_tokens": 500,
      "output_tokens": 300,
      "latency_ms": 1200,
      "ttft_ms": 200,
      "error": "none",
      "quality_score": 0.90
    },
    "llama7b": {
      "input_tokens": 500,
      "output_tokens": 280,
      "latency_ms": 450,
      "ttft_ms": 90,
      "error": "none",
      "quality_score": 0.65
    }
  }
}
```

`mock` 字段的含义：

| 字段 | 含义 |
|---|---|
| `mock[backend_id]` | 某个后端下的预设表现（例如 `gpt4`、`llama7b`） |
| `input_tokens` | 发给模型的文本长度（500 个 token） |
| `output_tokens` | 模型回复的文本长度（300 个 token） |
| `latency_ms` | 这次调用总共花多长时间（1200 毫秒） |
| `ttft_ms` | 模型吐出第一个字要等多久（200 毫秒）——衡量用户感知到的“响应速度” |
| `error` | 会不会出错。`"none"` = 正常；`"timeout"`/`"http_5xx"` 等 = 非速率类错误注入 |
| `quality_score` | 输出质量分（0–1）。Mock 实验用预设值；真实实验由确定性 grader 计算 |

MockBackend 的读取规则要点（只保留一句话，避免在概念导读里展开细节）：先做后端侧 RPM 检查，超限才返回 `http_429`；否则读取 `mock[backend_id]` 返回预设结果。这样同一份 workload 能稳定复现“raw 会打爆、governor_only 会排队消 429”的差异。

**quality_score 的两种来源**：

| 模式 | 来源 | 约束 |
|---|---|---|
| Mock 实验（主线） | `workload.mock.quality_score` 预设值 | 同 workload + 同 backend → 同分数；不同 backend 由预设质量差异体现 |
| 真实实验 | 按 `task_type` 调用确定性 grader | 纯函数，不依赖 LLM，同输入同输出 → 同分数 |

Grader 注册表——每个 task_type 对应一个 `(prompt, output) → float` 的纯函数：

| task_type | grader | 返回 |
|---|---|---|
| `generation` | 编译/执行通过 ×0.5 + 测试通过率 ×0.5（代码）；必需字段齐全（文本） | 0–1.0 |
| `reasoning` | 答案精确匹配 / 逻辑链校验 | 0–1.0 |
| `retrieval` | output 含期望答案子串（正则匹配） | 1.0 / 0.0 |
| `transform` | `json.loads(output)` 成功且含必需字段 | 1.0 / 0.0 |
| `summarization` | 必需小节/关键词齐全（正则匹配） | 0–1.0 |
| `conversation` | 回复相关性 + 格式正确性 | 0–1.0 |

两种来源产出同一个 `quality_score: float[0,1]`，`analyze.py` 不区分来源。

---

## 8. 实验在验证什么

有了 workload（测试脚本）和 mock（可控模拟），我们可以公平地比较不同策略。Paper 1 要回答 3 个问题，刚好对应架构的三个关键断言：

### RQ1：光管住资源，系统就能稳很多吗？

**对应架构**：Governor 治理层（Budget + RateLimit + Admission）。

**直觉**：50 个 agent 同时发请求，API 限制每分钟 60 次。不管的话一半请求直接被打回 429 错误。加个"排队系统"（超速的先等一会儿再发），是不是 429 就接近零了？

**做法**：同一个 workload，跑两次——一次裸跑（谁想调就调），一次加上排队机制。比较 429 错误率和完成率。

### RQ2：智能选模型能比"无脑用贵的"好多少？

**对应架构**：Governor + ModelSelector 协同——预算水位信号驱动选模决策。

**直觉**：预算 $1，GPT-4 做一次 generation 花 $0.05，只够做 20 次，剩下 30 个 Turn 没钱了。如果把简单任务（格式化 JSON）交给便宜模型（$0.001/次），把省下的钱留给关键任务用 GPT-4，是不是能完成更多 Turn、整体质量还不差？

**做法**：同一个 workload，用多种策略跑：无脑贵 / 逐请求选性价比最高的但不看全局预算水位 / 预算感知但不看 task_type / `agentos_no_preempt`（Governor + ModelSelector，关闭抢占与僵尸回收）。比较完成率、花费和质量。

### RQ3：动态资源回收——抢占 + 僵尸检测能挽救多少？

**对应架构**：Preemption + ZombieDetector（Scheduler 层的动态资源管理）。

**直觉**：资源被"错误的东西"占着，有三种表现形式：
- **低优先级阻塞高优先级**：并发槽只有 2 个，都被后台 batch 占着，用户来了 interactive 请求却要干等 10 秒。抢占能暂停 batch、让用户先跑。
- **慢请求拖垮正常请求**：50 个 Turn 里有 5 个特别慢（30 秒），占着槽不放，后面 1-2 秒就能完成的请求全在排队。抢占能限制这种"害群之马"效应。
- **僵尸调用占着不放**：有些调用卡死了（永远不返回），有些在疯狂输出无意义内容（烧钱）。检测机制不需要理解输出内容，只看两个数字：执行超时（跑太久没返回）和烧钱超限（花费超过预估的 k 倍）。触发后强制终止，释放并发槽和预算。

三者的底层模式一致：**检测到资源被误占 → 中断 → 释放 → 重新分配**。抢占是从低优先级那里收回，僵尸回收是从死掉/失控的调用那里收回。

**做法**：同一个 workload，包含三种场景——batch 占满槽后来 interactive、注入少量异常慢 Turn、注入 20% 僵尸 Turn（卡死 + 烧钱）。固定 `Governor + ModelSelector`，只切换是否开启动态回收：`agentos_no_preempt` vs `agentos`。比较 interactive 的 TTFT P99、整体 P99 延迟、系统吞吐。

---

## 9. AgentOS 怎么解决这些问题（架构一句话版）

系统分两层：

**治理层（Governor）**——管红线。不管你有多聪明的调度策略，这三个硬约束必须守住：
- 预算不能超支（Budget）
- API 调用不能超速（RateLimit）
- 同时跑的不能太多（Admission）

**调度层（Scheduler）**——在红线之内做优化：
- 谁先跑？（PriorityQueue：interactive 优先于 batch）
- 用哪个模型？（ModelSelector：关键任务用好模型，简单任务用便宜模型，预算紧时降级）
- 卡死了怎么办？（ZombieDetector：自动发现并回收僵尸调用）
- 怎么让用户少等？（Preemption：暂停后台任务，让用户先跑）

这里的抢占更像“操作系统抢占进程”，但存档的不是寄存器而是 **语义上下文**：

- **抢占**：高优先级 interactive 到来，但并发槽被低优先级 batch 占满
- **存档**：保存该 Turn 的 prompt + 已经生成的部分输出（中间结果）
- **恢复**：interactive 先跑完后，把已生成文本拼回新 prompt 继续生成，而不是从头重来

这点很关键：否则“抢占”会变成“浪费已生成内容”，对 batch 来说代价太大，系统也会倾向于不抢占。

两层分离的意义：即使调度策略写错了（比如选模逻辑有 bug），治理层仍然在兜底——预算不会超支、API 不会被打爆。

---

## 10. 实验的输出长什么样

每次实验（一个 workload + 一个策略 = 一次 run）至少产出两个文件：

**`events.jsonl`**——流水账。每个 Turn 从创建到完成的每一步都记录下来：

```
t001 创建了 → t001 被准入了 → t001 开始排队 → t001 被分配到 GPT-4 → t001 正在执行 → t001 完成了（花了 $0.03，耗时 900ms）
```

**`summary.json`**——一次 run 的成绩单（带行内注释版，便于读懂口径）：

```jsonc
{
  "turn_total": 50,        // 本次 run 里“总共创建了多少个 Turn”（= 调用请求总数）
  "turn_completed": 45,    // 成功完成的 Turn 数（终态为 completed）
  "turn_failed": 3,        // 失败的 Turn 数（终态为 failed；比如 http_429 / timeout / 5xx 等）
  "turn_reaped": 2,        // 被当作“僵尸”回收的 Turn 数（终态为 zombie_reaped；被系统强制终止）
  "cost_total_usd": 0.87,  // 实际总花费（美元）；通常是所有成功 Turn 的实际结算 cost/settlement 之和
  "ttft_p99": 1420,        // TTFT 的 P99（单位 ms）；TTFT=Time To First Token，“等到第一个 token 出来的时间”
  "error_429_rate": 0.02   // 429 错误占比（0–1）；= http_429 的 Turn 数 / turn_total
}
```

注意：上面是 `jsonc`（JSON with comments）写法，**不能当作严格 JSON 直接被解析器读取**；真实落盘的 `summary.json` 不应包含注释。

实际工程里通常还会额外落盘一个 `config_snapshot/`（workload / policy / backends 的配置快照），用来保证**可复现**：同一份输入和配置，跑出来的结果应当一致。

此外，文档中有时会用“目标形态”的 CLI 来描述一次 run（例如 `agentos run ...`）；而当前仓库的“可跑实现”一般是直接调用实验 runner（例如 `python paper1/agentos-exp/runner.py ...`）。两者表达的是同一件事：**给定 workload + policy → 产出 events + summary**。

论文里的图表就是从这些数据里画出来的。

---

## 11. 概念关系图

```
用户请求
  │
  │  一个用户请求可能需要 agent 调用多次 LLM
  ▼
Agent Session（一次会话）
  │
  │  每次 LLM 调用 = 一个 Turn
  ▼
Turn ────────────────────────────────────────────────
  │  属性：                                           │
  │   - priority: interactive 或 batch（有没有人在等） │
  │   - task_type: generation / reasoning / retrieval / transform / summarization / conversation │
  │   - 资源需求：多少 token、多少钱、占一个并发槽     │
  ──────────────────────────────────────────────────── 
  │
  │  很多 Turn 组成一个实验场景
  ▼
Workload（实验脚本）
  │  = 一份"哪些 Turn、什么时候来、mock 下表现如何"的清单
  │  目的：让不同策略在同一批输入上公平对比
  │
  │  一个 workload + 一个策略 = 一次 run
  ▼
Run（一次实验运行）
  │  产出：events.jsonl（流水账）+ summary.json（成绩单）
  │
  │  多次 run（不同策略）互相对比
  ▼
实验结论（RQ1–RQ3 的答案）
```

---

## 12. 术语速查（按认知顺序）

| 术语 | 一句话 |
|---|---|
| **LLM** | 大语言模型。给它文本，它回文本。ChatGPT、Claude 都是 |
| **Token** | LLM 处理文本的最小单位。约 1 英文词 ≈ 1 token。按 token 收费 |
| **Agent** | 自主循环调用 LLM 来完成任务的程序 |
| **Turn** | 一次完整的 LLM 调用（发请求 → 等结果）。调度和计费的基本单位 |
| **Interactive** | 有用户在等的 Turn。延迟 = 用户痛感。优先级高 |
| **Batch** | 后台运行的 Turn。没人盯着，晚点没关系。优先级低 |
| **Task Type** | Turn 在做什么类型的事：generation / reasoning / retrieval / transform / summarization / conversation。影响"需要多强的模型" |
| **Workload** | 实验脚本。一份"这次实验要跑哪些 Turn"的清单，用于公平对比不同策略 |
| **Mock** | workload 里每个 Turn 预设的行为（延迟多少、花多少钱、会不会出错）。保证实验可复现 |
| **Policy** | 一套调度策略。比如"裸跑"、"只有预算管理"、"AgentOS 全家桶"。同一个 workload 用不同 policy 跑，比较效果 |
| **Run** | 一个 workload + 一个 policy = 一次实验运行 |
| **429** | HTTP 错误码："你请求太频繁了"。API 供应商的限流惩罚 |
| **TTFT** | Time To First Token：从发请求到模型吐出第一个字的时间。用户感知的"响应速度" |
| **P99** | 第 99 百分位。"最慢的 1% 请求要等多久"。衡量最差体验 |
| **Governor** | 治理层：管预算、管速率、管准入。工程底线 |
| **Scheduler** | 调度层：管排队顺序、选模型、抢占、回收僵尸。在治理红线内做优化 |
| **Preemption** | 抢占：暂停低优先级 Turn，把资源让给高优先级 Turn。之后再恢复继续 |
| **Zombie** | 僵尸 Turn：卡死或疯狂烧钱，占着资源不放 |

---

