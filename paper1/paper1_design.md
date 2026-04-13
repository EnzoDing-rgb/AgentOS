# AgentOS（Paper 1）设计文档

> **这份文档 = 规格书 + 验收标准。** 定义架构、接口、算法、实验协议和验收标准。
>
> 前置阅读：`paper1_concepts.md`（问题动机、核心概念、术语表）。
> 后续操作：`paper1_implementation.md`（怎么跑起来）。

---

## 1. 设计思路：把 LLM 调用当成可治理的系统资源

> 问题动机（没人管钱、没人管闸、没人管顺序）和三种资源（预算/调用带宽/并发槽）的详细解释见 `paper1_concepts.md` §2–§4。

### 1.1 Turn：统一的调度单位

**Turn** = 一次 `llm.call()` 的完整生命周期。从发起调用到完成（或失败），中间的排队、执行、重试、抢占、回收都属于同一个 Turn。

### 1.2 语义存档抢占

这里的“语义存档”指：暂停时保存上下文，恢复时继续生成，而不是整段重跑。

- **抢占**：高优先级的实时请求到来，但并发槽被低优先级的后台任务占满了。系统暂停一个后台 Turn。
- **存档**：把已经生成的中间结果（prompt + 已输出的文本）保存下来。
- **恢复**：高优先级 Turn 完成后，恢复被暂停 Turn，继续执行剩余部分。

### 1.3 架构总览

```
┌────────────────────────────────────────────────────┐
│        Agent 应用层 (LangChain / CrewAI / etc.)     │
├────────────────────────────────────────────────────┤
│             Unified LLM API Gateway                 │
│  llm.call(prompt, task_type, priority) → result     │
│  （agent 不知道底层选了哪个模型）                    │
├────────────────────────────────────────────────────┤
│                                                      │
│  ┌─ Governor（治理层：工程保底）──────────────┐    │
│  │  Budget Governor  — 预算规划               │    │
│  │  Rate Limiter     — 调用频率协调           │    │
│  │  Admission Control — 准入检查              │    │
│  │  Zombie Detector  — 异常回收止损           │    │
│  └────────────────────────────────────────────┘   │
│                                                      │
│  ┌─ Scheduler（调度层：优化增益）─────────────┐    │
│  │  Priority Queue   — 实时请求优先           │    │
│  │  Model Selector   — 选模型（质量及格线）   │    │
│  │  Preemption       — 语义存档抢占           │    │
│  └────────────────────────────────────────────┘   │
│                                                      │
│  ┌─ 模型后端池 ──────────────────────────────┐    │
│  │  MockBackend / OpenAI / vLLM / Ollama       │    │
│  └────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────┘
```

### 1.4 为什么主线实验必须用 MockBackend

我们要测的是“策略好不好”，不是“这次 API 刚好快不快”。所以主线默认用 MockBackend：把每个 Turn 在不同后端下的表现先写死（延迟/成本/报错/质量），让大家在同一套输入上公平对比。

如果不用 mock，结论很容易被真实后端的随机性带偏，比如：
- 同一策略今天 API 慢一点，TTFT/P99 就变差，看起来像策略退化；
- 限流/429 的波动会改变排队节奏，影响吞吐和完成数；
- 网络抖动、重试、计费差异会把成本信号搅乱，让“预算松紧度”失真；
- 想复现一次极端场景（并发冲击/僵尸占槽）很难，审稿人也没法稳定复跑。

RealBackend 也会跑，但它的作用是小规模补充验证：确认系统真能接真实模型跑通，并量化实现层偏差（例如 RQ3 恢复时的 `resume_cost` 和可能的质量退化），不拿它当主线对照来下结论。

**关键决策：治理和调度分离。**

- **Governor（治理层）** 管底线：预算不超支、频率不打 429、异常调用可回收、过载时拒绝。用简单计数器和阈值就能工作，即使什么调度优化都不做，系统也不会崩。
- **Scheduler（调度层）** 管优化：在 Governor 画的红线之内，决定谁先跑、用哪个模型、要不要抢占。策略可以持续迭代，写错了 Governor 兜底，系统不会炸。

---

## 2. 怎样算做完：3 个实验问题

三个 RQ 对应三层能力，逐层叠加：

```
raw ──(+Governor)──→ governor_only（RQ1）
    ──(+ModelSelector)──→ agentos_no_preempt（RQ2）
    ──(+Preemption+Zombie)──→ agentos（RQ3）
```

文档中的 policy 名称：`raw`、`governor_only`、`baseline_A_fixed_expensive`、`baseline_B_per_request_router`、`baseline_C_budget_aware_router`、`agentos_no_preempt`、`agentos`。

### RQ1：光加治理（不做智能调度），系统就能更稳吗？

- **场景**：50 个 Agent 同时发请求，API 频率限制 = 每分钟 60 次。
- **裸跑**：没有任何协调，想调就调。
- **加 Governor**：超频时让 Agent 排队等，而不是硬打 429。
- **我们期望看到什么**：
  - 裸跑时大量请求被 429 打回（三成以上失败），加了 Governor 后 429 几乎消失（低于 1%），因为超速的请求在系统内排队而不是硬冲 API。
  - 完成率从裸跑的七成左右提升到 Governor 下的 95%+。
  - 总花费始终不超预算——这是治理层的硬底线，任何时刻都不允许"先超支再发现"。
  - 代价是 Governor 模式总耗时会更长（排队等待），但应在合理范围内（几倍以内），不能出现排了几十倍时间的反常情况。

**直觉参照**（帮助对齐预期，不是精确指标）：

| | 裸跑 (raw) | 加治理 (governor_only) |
|---|---|---|
| 429 失败数 / 50 总请求 | ~15 个 | ~0 个 |
| 完成率 | ~70% | ≥95% |
| 总花费 vs 预算 | 可能超支 | 严格不超 |

### RQ2：智能选模型，能比"无脑用贵的"更好吗？

- **场景**：总预算 $1.00，50 个任务（生成/检索/转换混合），两个模型可选——GPT-4（贵、质量高）和 Llama-7B（便宜、质量一般）。
- **对照 A（只用贵的）**：所有请求发 GPT-4，$1 只够 20 个任务，剩下 30 个没钱了。
- **对照 B（逐请求路由）**：每个请求独立选性价比最高的模型，但不看全局预算松紧度——不知道钱花快了还是慢了。这是成本下界参考线（在本实验参数下通常退化为全用便宜模型）。
- **对照 C（预算感知路由）**：看全局剩余预算，按预算比例线性调节“选贵模型概率”，但不区分 task_type。
- **AgentOS（无抢占版）**：`agentos_no_preempt` 仅开启 Governor + ModelSelector（不开抢占/僵尸回收）。预算充裕时关键任务用 GPT-4，预算紧张时自动降级，简单任务一律用便宜模型。
- **我们期望看到什么**：
  - "只用贵的"钱花光后被迫停工，完成率最低。AgentOS 把钱花在刀刃上，完成更多任务。
  - AgentOS 的花费应该接近用满预算（$0.90–1.00），说明钱没有被浪费——不是省着花到一半就停了，而是精打细算花到最后一刻。
  - 质量上，AgentOS 应显著优于 baseline C（同样有预算意识但不做任务差异化），证明“把预算花在关键任务上”的增量价值。
  - baseline A / B 继续作为上界/下界参照线：A 给质量天花板，B 给成本地板。

**直觉参照**：

| | 只用贵的 (A) | 逐请求路由 (B) | 预算感知路由 (C) | AgentOS（无抢占版） |
|---|---|---|---|---|
| 完成数 / 50 | ~20 | ~50 | 40–50 | 40–50 |
| 总花费 | ~$1.00（花光停工） | $0.60–0.90 | $0.90–1.00 | $0.90–1.00（精打细算用满） |
| 平均质量 | ~0.90（高但做得少） | 0.65–0.80 | 0.72–0.84 | 0.80–0.90 |

### RQ3：动态资源回收（抢占 + 僵尸检测）能挽救多少？

两个场景，同一个底层模式——**资源被错误的东西占着，检测→中断→释放→重新分配**：

- **场景 A（低优先级阻塞高优先级）**：并发槽 = 4，先提交 8 个后台任务（每个 10 秒），第 3 秒来了 2 个实时请求。无抢占时实时请求要等前面的 batch 释放槽位；有抢占时可在 1–2 秒内开始执行。
- **场景 B（资源霸占）**：50 个任务里注入 10 个"霸占者"（例如 5 个超慢 batch 请求 + 5 个卡死/异常长输出）。无回收/无抢占时，interactive 被 batch 长任务阻塞、整体吞吐下降、P99 被拉高；开启抢占+回收后，interactive 响应和总体吞吐都恢复。

对照方式：`agentos_no_preempt`（有 Governor + ModelSelector，但无抢占/无僵尸回收）对比 `agentos`（开启抢占与僵尸回收）。

- **我们期望看到什么**：
  - 场景 A：开抢占后，用户的实时请求在 2 秒内开始收到回复（首 token 延迟 TTFT 的 P99 ≤ 2s，P99 指第 99 百分位）。
  - 场景 B：开回收后，被卡死/异常超长的 Turn 会出现 `zombie_reaped`；被释放的资源用于推进其他请求，整体吞吐和尾延迟明显改善。
  - 抢占收益需要扣除恢复开销：报告中显式给出 `resume_cost_usd` 与 `resume_prefill_ms`，并做 break-even 对比。
  - 被抢占的后台任务不能"抢了就丢"——它们最终要被恢复并正常完成，不允许出现并发槽或预算泄漏。

---

## 3. 实验产出格式

### 3.1 一条命令 = 一次实验

```bash
agentos run --workload <path> --policy <policy> --out runs/<ts>/
```

输出两个文件：
- **`events.jsonl`**——原始追踪日志。每行一条 JSON，记录每个 Turn 生命周期中的每一个事件。所有指标都从这个文件算出来，它是唯一真相源。
- **`summary.json`**——汇总指标快照。方便一眼看结果，但不是权威来源。如果和 `events.jsonl` 复算结果不一致，以后者为准。

两者的关系：`events.jsonl` 是银行流水，`summary.json` 是月度账单。

#### events.jsonl 示例

一个 Turn（t001）从创建到完成，日志里会追加这些行：

```jsonl
{"ts_ms":0, "turn_id":"t001", "event":"created", "priority":"interactive", "task_type":"generation"}
{"ts_ms":3, "turn_id":"t001", "event":"dispatched", "backend_id":"gpt4"}
{"ts_ms":1203, "turn_id":"t001", "event":"completed", "settlement_usd":0.042, "ttft_ms":200, "quality_score":0.92}
```

`ts_ms` 是 run 内相对时间（run 开始 = 0）。

#### summary.json 示例

```json
{
  "policy": "agentos",
  "workload_id": "mixed_v1",
  "turn_total": 50,
  "turn_completed": 45,
  "turn_failed": 3,
  "turn_reaped": 2,
  "cost_total_usd": 0.87,
  "quality_avg": 0.84,
  "budget_total_usd": 1.00,
  "ttft_p99": 1420,
  "error_429_rate": 0.02,
  "wall_time_s": 143
}
```

### 3.2 summary.json 字段定义

每个 Turn 最终只有一个终态事件：`completed`（成功）、`failed`（失败）、`zombie_reaped`（被回收）。

每个 Turn 最终只有一个终态事件：`completed`（成功）、`failed`（失败）、`zombie_reaped`（被回收）。

| 字段 | 含义 | 怎么从 events.jsonl 算 | 单位 |
|---|---|---|---|
| `policy` | 策略名 | 命令行 `--policy` 参数 | string |
| `workload_id` | 实验负载标识 | workload 文件里的 `workload_id` | string |
| `turn_total` | 总 Turn 数 | `event="created"` 的不重复 `turn_id` 数 | count |
| `turn_completed` | 成功完成 | 终态 = `completed` 的 Turn 数 | count |
| `turn_failed` | 失败 | 终态 = `failed` 的 Turn 数 | count |
| `turn_reaped` | 被回收的僵尸 | 终态 = `zombie_reaped` 的 Turn 数 | count |
| `cost_total_usd` | 实际总花费 | 所有 `completed` 的 `settlement_usd` 之和 | USD |
| `quality_avg` | 平均质量分 | 所有 `completed` 的 `quality_score` 算术平均 | 0–1 |
| `budget_total_usd` | 预算上限 | 配置中的预算总额 | USD |
| `ttft_p99` | 实时请求的尾延迟 | interactive 且 completed 的 `ttft_ms` 取第 99 百分位 | ms |
| `error_429_rate` | 429 错误占比 | `error_type="http_429"` 的 Turn 数 / `turn_total` | 0–1 |
| `wall_time_s` | 端到端时间 | (max ts_ms − min ts_ms) / 1000 | s |

### 3.3 quality_score 说明

`quality_score`（0–1）衡量"这个 Turn 的输出质量好不好"。两种来源：

| 模式 | 来源 | 用途 |
|---|---|---|
| Mock 实验（主线） | `workload.mock[backend_id].quality_score` 预设值 | 可复现对比，且模型选择会真实影响质量结果 |
| 真实实验 | 按 `task_type` 调用确定性 grader：`(prompt, output) → float` | 验证真实模型下的质量差异 |

Grader 是纯函数，不依赖 LLM。同输入同输出必须得到同分数。各 task_type 的判分方式：

| task_type | grader 逻辑 | 返回 |
|---|---|---|
| `generation` | 编译/执行通过 ×0.5 + 单元测试通过率 ×0.5（代码）；必需字段齐全（文本） | 0–1.0 |
| `reasoning` | 答案精确匹配 / 逻辑链校验 | 0–1.0 |
| `retrieval` | 输出含期望答案子串（正则匹配） | 1.0 / 0.0 |
| `transform` | `json.loads(output)` 成功且含必需字段 | 1.0 / 0.0 |
| `summarization` | 必需小节/关键词齐全（正则匹配） | 0–1.0 |
| `conversation` | 回复相关性 + 格式正确性 | 0–1.0 |

存在的意义：RQ2 需要证明"省了钱但没胡说八道"——光比完成率不够，还得看质量。

---

## 4. MVP 范围

只做跑通 RQ1–3 需要的最小集合：

- **Gateway**：所有 `llm.call()` 的统一入口
- **两种模型后端**
  - `MockBackend`：按 workload 预设参数返回结果（延迟、token 数、成本、质量分，以及非速率类错误），并内置与 `rpm_limit` 对齐的动态 RPM 计数器。请求到达时先做 RPM 检查，超限即时返回 `http_429`；未超限再读取 `mock[backend_id]`。主线实验全用它——因为要公平比较不同 policy，不能让真实 API 的随机波动干扰结果。
  - `RealBackend`：接真实模型（Ollama / 云端 API），仅用于验证系统能跑通。
- **Governor**：Budget + RateLimit + Admission
- **Scheduler**：PriorityQueue + ModelSelector + Preemption
- **ExperimentRunner**：读 workload → 跑 policy → 产出 events.jsonl + summary.json

---

## 5. 数据模型

### 5.1 Turn（一次 LLM 调用的交易单）

| 字段 | 说明 |
|---|---|
| `turn_id` | 唯一标识 |
| `created_at_ms` | 创建时间戳 |
| `priority` | `interactive`（实时）或 `batch`（后台） |
| `task_type` | `generation / reasoning / retrieval / transform / summarization / conversation` |
| `prompt` | prompt 内容或引用 |
| `resource_spec` | 资源需求估算（见 6.2） |
| `state` | 当前状态 |

`task_type` 覆盖真实 agent 的多样化调用场景，不只是写代码。分类依据是“对模型能力的依赖程度”——这直接决定了该给它配贵模型还是便宜模型：

| task_type | 典型场景 | 对模型能力的依赖 | 为什么这样分 |
|---|---|---|---|
| `generation` | 写代码、起草邮件、生成营销文案、创作故事 | **高** | 生成类任务质量差距最大：GPT-4 写的代码能跑，便宜模型可能语法都不对 |
| `reasoning` | 数学推理、方案评估、bug 定位、数据分析 | **高** | 推理链断了一环结论就全错，这类任务最不能省钱 |
| `retrieval` | 查文档回答问题、知识问答、信息抽取 | **中** | 答案通常在 context 里，模型只需“找到并复述”，中档模型就够 |
| `transform` | JSON↔YAML、翻译、格式化、数据清洗 | **低** | 最适合便宜模型：规则明确，只要格式对了就行 |
| `summarization` | 长文摘要、会议纪要、变更日志、review 总结 | **中** | 差异主要在“有没有遗漏关键点”，中档模型通常够用 |
| `conversation` | 客服回复、用户咨询、多轮对话 | **中** | 对延迟敏感（用户在等），但对绝对质量的要求不如 generation/reasoning |

**状态流转**：
- 正常路径：`created → admitted → queued → dispatched → running → completed`
- 异常：`failed` / `zombie_reaped`
- 抢占：`preempted → archived → resumed`

### 5.2 ResourceSpec（准入前的资源估算）

| 字段 | 说明 |
|---|---|
| `max_input_tokens_est` | 输入 token 上限估算 |
| `max_output_tokens_est` | 输出 token 上限估算 |
| `max_cost_usd_est` | 成本上限估算（美元） |
| `concurrency_slots` | 占用并发槽数（默认 1） |

`max_cost_usd_est` 的计算约定（v0）：
- `max_input_tokens_est`：由 prompt 长度估算得到。
- `max_output_tokens_est`：按 `task_type` 给经验上限（如 generation=500、transform=200）。
- `max_cost_usd_est`：按"最贵候选后端"单价计算，作为保守上限。

### 5.3 BackendProfile（模型后端的配置卡片）

| 字段 | 说明 |
|---|---|
| `backend_id` | 后端标识 |
| `context_window` | 上下文窗口大小（能接受的最大 token 数） |
| `price_usd_per_1k_input` | 输入 token 单价（每千 token） |
| `price_usd_per_1k_output` | 输出 token 单价 |
| `rpm_limit` | 每分钟请求次数上限 |
| `tpm_limit` | 每分钟 token 数上限 |
| `quality_prior` | 按 task_type 的预估质量分（可选） |

### 5.4 记账机制（预留 + 结算）

像酒店预授权：

1. **预留（reservation）**：Turn 开始前，按估算成本从预算中冻结一笔钱。即使 10 个 Turn 并发执行，系统也不会因为"都还没扣钱"而超支。
2. **结算（settlement）**：Turn 结束后，按实际消耗算真实花费，退回多冻的差额。

BudgetGovernor 维护三个核心状态（run 级）：

- `actual_spent_usd`：已结算实际花费
- `frozen_total_usd`：当前所有未结算 Turn 的冻结总额
- `available_budget_usd = budget_total_usd - actual_spent_usd - frozen_total_usd`

预算相关判断一律基于 `available_budget_usd`。这保证并发情况下不会出现“每个请求看起来都能过，但总和超支”的漏洞。

术语对齐（同一条流水线）：
- `cost_est`（选模打分用）= 在某个候选后端上的单次成本估算。
- `max_cost_usd_est`（ResourceSpec）= 所有候选后端里最保守的成本上限。
- `reservation_usd`（事件字段）= 本次 dispatch 前冻结金额，v0 取 `max_cost_usd_est`。
- `frozen_total_usd`（Governor 状态）= 所有在途 Turn 的 `reservation_usd` 总和。

### 5.5 实验基本单位（run 与矩阵）

- **run**：一份 workload + 一种 policy 的一次执行。
- **实验矩阵**：`workload × policy`。矩阵每个格子就是一次 run，预算和指标都按格子独立计算。

---

## 6. 模块接口

### 6.1 Gateway（统一入口）

所有 `llm.call()` 必须经过 Gateway，它串联整个流程：

1. 接收调用请求（prompt + task_type + priority）
2. 估算资源需求（ResourceSpec）
3. Admission 粗检（Governor）：`available_budget_usd`/并发槽可行，且 `anyBackendAvailable() = true`
4. 入队（Scheduler）：按优先级排队
5. 选模型（Scheduler）：ModelSelector 结合 budget_factor + `hasCapacity(backend_id)` + backend health 过滤候选
6. 原子获取（Governor）：对选中后端一次性执行 `reserve_budget + acquire(backend_id)`，任一失败就回滚并重选/等待（`frozen_total_usd` 随预留/回滚原子更新）
7. 调后端执行（dispatch）
8. 收集实际消耗（token 数 / 花费 / 延迟 / 错误 / 质量）
9. 结算预算并释放频率槽，写事件日志

### 6.2 Governor（治理层）

**BudgetGovernor**
- 维护 run 级预算状态：`actual_spent_usd / frozen_total_usd / available_budget_usd`
- 维护"期望花费曲线（target） vs 已结算花费曲线（actual）"
- 计算 `budget_factor`（花快了 < 1 / 正好 = 1 / 花慢了 > 1）
- 提供 reservation / settlement 接口

**RateLimiter**
- 按后端维护每分钟调用次数的滑动窗口（v0 先管 RPM）
- 对外暴露三类接口：
  - `anyBackendAvailable() -> bool`：Admission 粗检，判断是否存在至少一个后端有频率余量
  - `hasCapacity(backend_id) -> bool`：ModelSelector 过滤候选时用
  - `acquire(backend_id) -> bool`：dispatch 前原子占位

**BackendHealth（熔断器）**
- 维护每个后端的 `healthy / unhealthy` 状态
- 连续失败达到阈值 `N_fail`（默认 5）后熔断为 `unhealthy`，进入冷却期（默认 30s）
- 冷却期内 ModelSelector 不再路由该后端；冷却结束后以低频探测请求恢复

**AdmissionControl**
- 只做模型无关的底线检查：`available_budget_usd`、并发槽、`anyBackendAvailable()`
- 不满足时：`wait`（排队）或 `reject`（拒绝）
- 判定规则（v0）：可恢复条件（并发槽满、频率超限）→ `wait`；不可恢复条件（`available_budget_usd` 连最便宜候选的 `cost_est` 都覆盖不了）→ `reject`

**ZombieDetector**
- 两条规则：超时未返回、花费异常偏高
- 触发后执行止损回收：释放并发槽、归还预留预算、写 `zombie_reaped` 事件

### 6.3 Scheduler（调度层）

**PriorityQueue**：两级队列，interactive 始终优先于 batch。

**ModelSelector**：在候选后端中选一个（质量及格线 + 预算/频率/健康状态过滤）。

重试约束：同一个 Turn 的每次重试都重新执行 ModelSelector；且对该 Turn 已返回错误的 backend 加入临时黑名单（仅本 Turn 生效），避免在同一失败后端上原地重试耗尽次数。

**Preemption**：当 interactive Turn 到来但无空闲槽时，暂停一个 batch Turn（存档），让 interactive 先跑；之后恢复被暂停的 Turn 继续。

**Anti-starvation（防饥饿）**
- 对被抢占或长期等待的 batch Turn 启用 aging：每等待 `aging_step_s`（默认 15s）优先级提升一档
- 同一 Turn 被抢占超过 `max_preemptions`（默认 2）后提升到与 interactive 同级，防止无限延期

### 6.4 模型后端（统一返回格式）

| 字段 | 说明 |
|---|---|
| `text` | 模型输出文本 |
| `input_tokens` | 实际输入 token 数 |
| `output_tokens` | 实际输出 token 数 |
| `ttft_ms` | 首 token 延迟（从发请求到模型开始输出的时间，毫秒） |
| `total_latency_ms` | 总延迟（毫秒） |
| `error_type?` | 错误类型（可选）：`http_429 / timeout / http_5xx / backend_error / none` |
| `quality_score?` | 输出质量分（0–1）。MockBackend 返回预设值；RealBackend 由 grader 按 task_type 计算 |

---

## 7. 算法与策略

> **人话版**：这三节讲的是系统怎么**管钱、选模型、杀僵尸**。
> - **管钱（§7.1）**：钱花快了就“省着点”，花慢了就“可以用好点的”。
> - **选模型（§7.2）**：先过“质量够用”门槛，再在可用候选里选最便宜的。
> - **杀僵尸（§7.3）**：跑太久/花太多就回收，别让它占着预算和并发槽。

### 7.1 预算松紧度

**作用域**：每个 run 一笔独立预算，互不影响。矩阵里每个格子各算各的账。

**配置**：`budget_total_usd`（总预算），`budget_reserve_usd`（保底留多少）

每个 Turn 选模型时计算一次 `budget_factor`。  
**v1 口径（修正后）**：`budget_factor` 只比较“目标花费”与“已结算实际花费”；冻结额不参与选模信号。

进度怎么量？看已完成的 Turn 占总数多少。实验中 workload 预先定义了所有 Turn，总数 `n_total` 已知：

$$\text{target\_spend}(n) = \text{budget\_total\_usd} \times \frac{n_{\text{settled}}}{n_{\text{total}}}$$

$n_{\text{settled}}$ = 已结算的 Turn 数（completed + failed + reaped），不含还在跑的或排队的。

用于预算松紧度信号的“实际花费”直接使用 `actual_spent_usd`（已结算实际花费）。

冻结额仍保留在 Governor 的**准入安全检查**中：

$$\text{available\_budget\_usd} = \text{budget\_total\_usd} - \text{actual\_spent\_usd} - \text{frozen\_total\_usd}$$

即：Admission 管“会不会超支”，`budget_factor` 管“该不该省着花”，两者解耦。

**budget_factor（预算松紧度）：告诉选模器"现在该省还是该花"的一个数字。**

- `budget_factor > 1`：钱花慢了，可以用好一点的模型
- `budget_factor = 1`：正好
- `budget_factor < 1`：钱花快了，优先选便宜的

从偏差到 budget_factor 的映射保持可插拔（输入：已结算花费、进度、总预算；输出：float）。

**v0（起步方案）：三挡阈值。**

| 已结算花费 vs 期望花费 | budget_factor | 含义 |
|---|---|---|
| 超出 10% 以上 | 0.5 | 省着花 |
| 上下 10% 以内 | 1.0 | 正常 |
| 低于期望 10% 以上 | 2.0 | 可以用好的 |

若三挡太粗，可换连续函数（如 `clamp(target_spend(n) / max(actual_spent_usd, \epsilon), 0.2, 5.0)`）。

**边界情况**：还没有 Turn 结算时（`n_settled = 0`），`target_spend(0) = 0`，没法算比例，此时 budget_factor = 1.0——第一个 Turn 不受预算松紧度影响。

### 7.2 选模型（质量及格线 + 预算松紧度）

核心原则：先判定“够不够用”，再在可用候选里选最便宜的。

为每种 `task_type` 配置质量及格线 `quality_threshold`（0–1）：

| task_type | `quality_threshold`（v0） | 说明 |
|---|---:|---|
| `generation` | 0.80 | 质量不足会直接产生不可用输出 |
| `reasoning` | 0.85 | 推理断链的代价最高 |
| `retrieval` | 0.50 | 中档模型通常可用 |
| `transform` | 0.30 | 规则明确，低成本模型优先 |
| `summarization` | 0.60 | 需要覆盖关键点 |
| `conversation` | 0.55 | 强调可用性与响应 |

预算松紧度只用于调节“够用”门槛。

$$\text{required\_quality} = \text{quality\_threshold}(\text{task\_type}) \times \text{clamp}(\text{budget\_factor}, 0.3, 1.5)$$

然后按三步选择：

1. 计算当前 Turn 的 `required_quality`
2. 过滤候选后端，必须同时满足：
   - 质量够用：`q_prior(task_type, backend) ≥ required_quality`
   - 买得起：`cost_est(backend) ≤ available_budget_usd`
   - 有容量：`hasCapacity(backend_id) = true` 且上下文窗口可容纳
3. 在剩余候选里选 `cost_est` 最低者

若无候选，fallback：忽略质量门槛，在满足预算/容量条件的候选里选 `q_prior` 最高者。

`cost_est` 用于候选比较；`max_cost_usd_est` 用于 reservation 上限。

**基线对齐**：
- `baseline_B_per_request_router`：继续采用逐请求性价比路由（不设质量及格线、不看预算松紧度）
- `baseline_C_budget_aware_router`：看预算不看任务，按预算比例调节贵模型使用概率
- `agentos`：采用本节的质量及格线 + 预算松紧度机制

### 7.3 抢占与恢复规则

为了避免未定义行为，抢占协议明确为：

- Turn 进入 `preempted/archived` 时，**暂停**僵尸计时器（`running_duration_s` 不再增长）。
- Turn 进入 `resumed/running` 时，**恢复累计计时**（从暂停前的运行时长继续算）。
- 恢复后的 Turn 不保留专属并发槽，按调度规则重新竞争。
- 恢复队列采用"队首插入"：优先于普通 batch，但仍低于 interactive。
- 单次调度周期最多抢占 `available_interactive_gap` 个 batch Turn（不做过量抢占）；恢复顺序用 FIFO（先被抢占先恢复）。
- 防饥饿：被抢占/等待越久优先级越高（aging），且超过 `max_preemptions` 后强制提级。

抢占恢复的额外代价必须显式计入：

- `resume_input_tokens`：恢复时重传的上下文 token 数
- `resume_cost_usd = resume_input_tokens / 1000 × price_usd_per_1k_input × cache_discount`
- `resume_prefill_ms`：恢复请求的额外 prefill 延迟

其中 `cache_discount ∈ (0,1]` 用来表示前缀缓存带来的折扣（无缓存 = 1.0，命中缓存时 < 1.0）。
Turn 的总成本与总延迟更新为：

- `cost_total = base_cost + Σ resume_cost_usd`
- `latency_total = base_latency + Σ resume_prefill_ms`

MockBackend 下的抢占语义（v0）：
- 若某 Turn 的 `latency_ms = L`，在已运行 `x` ms 时被抢占，则恢复后只执行剩余 `L - x` ms。
- `quality_score` 与未抢占时一致（语义存档不丢进度）。
- 实现上记录 `elapsed_run_ms`，恢复时按 `remaining_ms` 继续，并额外注入 `resume_cost_usd` 与 `resume_prefill_ms`。

> 说明：上面的“质量不降”仅是 Mock 语义定义，不应外推为真实后端结论。

**RealBackend 补充验证（小规模，RQ3 附加实验）**
- 目标：验证“真实抢占恢复下质量退化可控”，而非假设其严格为 0。
- 设计：选 20 个 generation/reasoning turn，固定 prompt 与温度；每个 turn 做 A/B 配对：
  - A：无抢占完整执行；
  - B：在 30%–50% 已执行时触发一次抢占，再恢复。
- 记录：`quality_score`、`resume_prefill_ms`、`resume_cost_usd`、`ttft_ms`、`latency_total_ms`。
- 报告指标：
  - `delta_quality = quality_B - quality_A`（均值、P95、最差值）；
  - 恢复开销占比：`resume_cost_usd / base_cost` 与 `resume_prefill_ms / base_latency`；
  - break-even 是否成立（延迟收益是否覆盖恢复开销）。
- 论文主线表述：RQ3 的主结论是“调度机制可回收资源并改善交互时延”；质量损失属于实现层变量，需由上述 real backend 补充实验给出上界。

RQ3 报告中必须给出 break-even 条件：只有当“抢占减少的 interactive 尾延迟收益”大于“恢复开销（`resume_cost_usd + resume_prefill_ms`）”时，抢占才算净收益。

### 7.4 僵尸检测（Governor 侧）

完整设计有两条规则，都基于数值信号，不需要分析输出内容：

**规则 1：执行超时。** Turn 进入 `running` 后，超过 `T_max` 秒未结束，判定为卡死。`T_max` 按 task_type 配置（如 generation = 30s，transform = 10s）。覆盖场景：API 挂起、网络断连。

**规则 2：烧钱超限（Cost overrun）。** 准入时已冻结 `reservation_usd`（成本估算上限）。执行期间实时追踪 `cost_so_far`（流式输出时 = `output_tokens_so_far × price_per_token`）。若 `cost_so_far > k × reservation_usd`（默认 k = 3.0），判定为烧钱僵尸。覆盖场景：模型循环输出、无限续写。关键：**不需要理解输出内容**——模型是在重复自己还是产出有意义的文本无所谓，只看账单。`cost_so_far` 是单调递增计数器，每收到一批 streaming tokens 就更新，计算开销为零。

| 规则 | 输入信号 | 触发条件 | 典型场景 |
|---|---|---|---|
| 执行超时 | running_duration_s | > T_max(task_type) | API 挂起、网络断连 |
| 烧钱超限 | cost_so_far / reservation_usd | > k（默认 3.0） | 模型循环输出、无限续写 |

触发后的回收流程：释放并发槽 → 归还预留预算 → 写 `zombie_reaped` 事件 → 标记可重试

Mock/Real 的启用范围（v0）：
- **MockBackend 主线实验**：仅启用规则 1（超时）。因为 mock 默认非流式返回，`cost_so_far` 不可连续观测。
- **RealBackend 验证性测试**：启用规则 1 + 规则 2。
- RQ3 的 Mock 场景 B（资源霸占合并场景）用"超长延迟 + 高 output_tokens"近似烧钱僵尸，并通过超时回收验证止损路径。

### 7.5 失败与重试（全局策略）

- 默认重试上限：`max_retries = 2`（首次失败后最多再试两次）。
- 可重试错误：`http_429 / timeout / http_5xx`；不可重试错误：`backend_error`（默认）。
- 重试采用指数退避：第 `k` 次重试等待 `delay_k = base_delay_ms × 2^k`（默认 `base_delay_ms = 200`，可加 10% jitter）。
- 每次重试都必须重新走完整流程：Admission → 排队 → 选模型 → 原子获取 → dispatch。
- 同一 Turn 内，已失败 backend 会被临时排除；直到 Turn 终态落定后才清空该排除集合。
- 后端熔断：某后端连续失败达到阈值后进入 `unhealthy`，冷却期内不再路由，避免故障放大。
- 超过重试上限后终态记为 `failed`，并保留最后一次错误类型。

---

## 8. 实验设计

实验的核心是**交叉对比**：准备几份不同的 workload（任务清单），再准备几套不同的 policy（处理规则），让每份 workload 分别用不同的 policy 跑一遍，比较结果。

三个关键概念：
- **workload**：一份“剧本”——规定了要来哪些 Turn、什么时候来、每个 Turn 在 mock 下表现如何（延迟、token 数、会不会出错等）。不同 RQ 用不同的 workload 来制造不同的压力场景。
- **policy**：一套“规则开关”——决定系统怎么处理这些 Turn（是否启用 Governor、是否启用选模/抢占/僵尸回收，以及各模块的参数）。
- **run**：一个 workload + 一个 policy，跑一遍，产出一份 events.jsonl + summary.json。

整个实验就是一张 **workload × policy** 的矩阵。每个格子 = 一次 run = 一份可对比的实验数据：

| | `raw` | `governor_only` | `baseline_A` | `baseline_B` | `baseline_C` | `agentos_no_preempt` | `agentos` |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **RQ1 workload**（50 并发冲击限流） | ✓ | ✓ | | | | | |
| **RQ2 workload**（50 混合任务 + 预算约束） | | | ✓ | ✓ | ✓ | ✓ | |
| **RQ3 workload**（资源霸占合并场景：慢请求 + 僵尸 + interactive 插入） | | | | | | ✓ | ✓ |

每一行是同一份 workload，横着比不同 policy 的表现；每一列是同一个 policy，竖着看它在不同压力下的表现。Mock 输入是确定的，但在真实时间执行下，时序指标会受线程调度影响，因此要求是：核心计量（完成数、总花费、错误数）一致，延迟类指标允许小幅波动。

### 8.1 Policy 集合

| Policy | 说明 | 用于 |
|---|---|---|
| `raw` | 裸跑：无 Governor、无 Scheduler；只记录成本，不执行预算约束 | RQ1 对照组 |
| `governor_only` | 只有 Governor，Scheduler 仍 FIFO | RQ1 实验组 / RQ2 与 RQ3 的前置层 |
| `baseline_A_fixed_expensive` | 所有请求发贵模型，不管预算 | RQ2 对照 A |
| `baseline_B_per_request_router` | 逐请求选性价比最高的，不看全局预算松紧度（在本实验参数下通常退化为全用便宜模型） | RQ2 对照 B |
| `baseline_C_budget_aware_router` | 预算感知但不看 task_type：按 `available_budget_usd / budget_total_usd` 线性调节选贵模型概率（例如 `p_expensive = clamp(ratio, 0, 1)`） | RQ2 主对照组 |
| `agentos_no_preempt` | 开启 Governor + ModelSelector；关闭 Preemption + ZombieDetector | RQ2 实验组 / RQ3 对照组 |
| `agentos` | 全部机制开启（在 `agentos_no_preempt` 基础上打开 Preemption + ZombieDetector） | RQ3 实验组 |

### 8.2 Workload（实验脚本）

每个 workload 是一份提前写好的 JSON 文件，定义了"什么时间来什么任务、每个任务在不同后端下的 mock 表现"。矩阵里同一行的不同 policy 跑的是同一份 workload，保证公平对比。并发槽数也放在 workload/policy 配置中显式给出（例如 `concurrency_slots: 4`），确保可复现。

**单条 Turn 记录**：

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
      "quality_score": 0.92
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

**完整 workload 示例**（覆盖三种典型情况：正常完成、动态 429、超时被回收）：

```json
{
  "workload_id": "toy_3turns_v1",
  "concurrency_slots": 4,
  "turns": [
    {
      "turn_id": "t001", "at_ms": 0,
      "priority": "interactive", "task_type": "generation",
      "mock": {
        "gpt4": { "input_tokens": 200, "output_tokens": 120, "latency_ms": 900, "ttft_ms": 120, "error": "none", "quality_score": 0.90 },
        "llama7b": { "input_tokens": 200, "output_tokens": 110, "latency_ms": 350, "ttft_ms": 70, "error": "none", "quality_score": 0.66 }
      }
    },
    {
      "turn_id": "t002", "at_ms": 50,
      "priority": "batch", "task_type": "retrieval",
      "mock": {
        "gpt4": { "input_tokens": 80, "output_tokens": 40, "latency_ms": 300, "ttft_ms": 60, "error": "none", "quality_score": 1.0 },
        "llama7b": { "input_tokens": 80, "output_tokens": 40, "latency_ms": 220, "ttft_ms": 40, "error": "none", "quality_score": 1.0 }
      }
    },
    {
      "turn_id": "t003", "at_ms": 100,
      "priority": "batch", "task_type": "reasoning",
      "mock": {
        "gpt4": { "input_tokens": 150, "output_tokens": 200, "latency_ms": 5000, "ttft_ms": 200, "error": "timeout", "quality_score": 0.0 },
        "llama7b": { "input_tokens": 150, "output_tokens": 180, "latency_ms": 4200, "ttft_ms": 160, "error": "timeout", "quality_score": 0.0 }
      }
    }
  ]
}
```

MockBackend 的读取规则（v1）：
- 先看当前 Turn 选中的 `backend_id`，并执行该后端 RPM 动态计数检查；若超限，直接返回 `http_429`；
- 若未超限，再读取 `mock[backend_id]`；
- `mock[backend_id].error` 仅用于非速率类错误（`timeout / http_5xx / backend_error / none`），不再用于注入 429。

这样同一份 workload 就能稳定复现 RQ1：`raw` 会因突发并发触发动态 429，`governor_only` 会在 dispatch 前限速排队，后端侧 429 接近 0。重试时仍会重新选模，并跳过该 Turn 已失败过的 backend。

跑这份 workload 大概会看到：
- t001：正常完成，产生花费记录
- t002：第一次因动态 RPM 超限命中 429，重试时切到另一后端后完成
- t003：超时 → 如果开了 ZombieDetector，会被 `zombie_reaped`

### 8.3 events.jsonl 事件类型汇总

**Turn 生命周期**：`created / admitted / queued / dispatched / running / completed / failed / zombie_reaped / preempted / archived / resumed`

**后端调用**：backend_id、input_tokens、output_tokens、cost_usd、ttft_ms、total_latency_ms、error_type

**Governor 决策**：reservation_usd、frozen_total_usd、available_budget_usd、settlement_usd、admit/wait/reject、budget_factor、zombie 回收原因

**Scheduler 决策**：队列长度、选模结果、抢占/存档/恢复、aging 提级、retry_backoff_ms、circuit_breaker_state

每行必带三个字段：`ts_ms`（时间戳）、`turn_id`、`event`。

**完整示例**（对应上面的 3-turn workload）：

```jsonl
{"ts_ms":0,   "turn_id":"t001", "event":"created",      "priority":"interactive", "task_type":"generation"}
{"ts_ms":2,   "turn_id":"t001", "event":"admitted",     "reservation_usd":0.05}
{"ts_ms":3,   "turn_id":"t001", "event":"queued",       "queue":"interactive", "queue_len":1}
{"ts_ms":3,   "turn_id":"t001", "event":"dispatched",   "backend_id":"gpt4"}
{"ts_ms":4,   "turn_id":"t001", "event":"running"}
{"ts_ms":904, "turn_id":"t001", "event":"completed",    "backend_id":"gpt4", "input_tokens":200, "output_tokens":120, "ttft_ms":120, "total_latency_ms":900, "cost_usd":0.03, "settlement_usd":0.03}

{"ts_ms":50,  "turn_id":"t002", "event":"created",      "priority":"batch", "task_type":"retrieval"}
{"ts_ms":50,  "turn_id":"t002", "event":"admitted",     "reservation_usd":0.01}
{"ts_ms":51,  "turn_id":"t002", "event":"queued",       "queue":"batch", "queue_len":1}
{"ts_ms":55,  "turn_id":"t002", "event":"dispatched",   "backend_id":"gpt4"}
{"ts_ms":105, "turn_id":"t002", "event":"failed",       "backend_id":"gpt4", "error_type":"http_429"}
{"ts_ms":106, "turn_id":"t002", "event":"admitted",     "reservation_usd":0.01, "retry":1}
{"ts_ms":106, "turn_id":"t002", "event":"queued",       "queue":"batch", "queue_len":1, "retry":1, "exclude_backends":["gpt4"]}
{"ts_ms":110, "turn_id":"t002", "event":"dispatched",   "backend_id":"llama7b"}
{"ts_ms":360, "turn_id":"t002", "event":"completed",    "backend_id":"llama7b", "input_tokens":80, "output_tokens":40, "ttft_ms":40, "total_latency_ms":250, "cost_usd":0.002, "settlement_usd":0.002}

{"ts_ms":100, "turn_id":"t003", "event":"created",      "priority":"batch", "task_type":"reasoning"}
{"ts_ms":100, "turn_id":"t003", "event":"admitted",     "reservation_usd":0.05}
{"ts_ms":101, "turn_id":"t003", "event":"queued",       "queue":"batch", "queue_len":2}
{"ts_ms":109, "turn_id":"t003", "event":"dispatched",   "backend_id":"gpt4"}
{"ts_ms":110, "turn_id":"t003", "event":"running"}
{"ts_ms":5200,"turn_id":"t003", "event":"zombie_reaped","reap_reason":"timeout", "reservation_refund_usd":0.05}
```

规范约定：`queued` 事件始终写入（即使排队时长为 0），保证生命周期事件序列完整、分析脚本无需分支判断。

---

## 9. 分阶段实现与验收

### Phase 0：骨架 + 事件日志
- **做什么**：先把最小可跑通版本搭起来：数据模型、`events.jsonl` 写入器、基础 CLI。
- **验收**：连续跑 3 个 Turn，`events` 里完整出现 `created → admitted → queued → dispatched → running → completed`；同时能生成字段完整的 `summary.json`。

### Phase 1：MockBackend + RateLimiter
- **做什么**：Mock 要按不同后端返回结果（`mock[backend_id]`）；MockBackend 能按 RPM 动态返回 429；再加上滑动窗口限流（`anyBackendAvailable/hasCapacity/acquire`）。
- **验收**：在 20 并发、RPM=5 下，无限流时动态 429 比例 > 20%，加限流后 < 1%；同一 Turn 重试会重新选模型并跳过失败 backend；同一 Turn 换 `backend_id` 后质量分会跟着变化。

### Phase 2：Budget + Admission（跑通 RQ1）
- **做什么**：实现预算账本，支持预留和结算（reservation/settlement）以及 `frozen_total_usd`；请求入场只有三种结果：admit / wait / reject。
- **验收**：预算 $1、单次估算 $0.2 时，10 个并发请求同时到达也不能超支；任意时刻都满足 `available_budget_usd = budget_total_usd - actual_spent_usd - frozen_total_usd`；预算快耗尽时会 reject；`governor_only` 总花费 <= $1.00；预留归还误差 <= $0.001。

### Phase 3：PriorityQueue
- **做什么**：做优先队列，让 interactive 优先，同时加并发槽位限制。
- **验收**：先压入 batch 再提交 interactive，interactive 的排队等待 P99 至少比 batch 低 50%。

### Phase 4：ModelSelector（跑通 RQ2）
- **做什么**：准备贵/便宜两个后端；把七种 policy 全部跑通（含 baseline C 和 `agentos_no_preempt`）；选模时同时考虑质量及格线和预算紧张程度。
- **验收**：`agentos_no_preempt` 完成数 >= `baseline_A_fixed_expensive` + 30%；`agentos_no_preempt` 平均质量 >= `baseline_C_budget_aware_router`；`agentos_no_preempt` 总花费落在预算的 90%–100%。

### Phase 5：Preemption + Zombie 回收（跑通 RQ3）
- **做什么**：实现抢占流程（preempt → archive → resume）；Mock 能从“剩余时长”继续跑；计时器支持暂停/恢复；把恢复开销建模进来（`resume_cost_usd / resume_prefill_ms`）；加 aging 防饥饿；在 workload 里注入卡死/慢请求；Governor 侧实现僵尸回收（Mock 用超时规则，Real 用超时+烧钱规则）。
- **验收**：`events` 中出现 `preempted/archived/resumed`；Mock 恢复后 Turn 只执行剩余时长且质量不下降；RealBackend 小样本 A/B 报告给出 `delta_quality` 分布和开销占比；注入 20% 僵尸时，`agentos` 吞吐比 `agentos_no_preempt` 至少高 30%；给出 RQ3 break-even（延迟收益 vs 恢复开销）；预算/并发槽零泄漏；持续 interactive 压力下 batch 不会无限饥饿。

### Phase 6：重试退避 + 熔断
- **做什么**：实现指数退避重试（每次失败后等待时间变长，并加一点随机等待，避免请求同时重试把后端打爆）；加后端健康状态机和熔断恢复。
- **验收**：后端短时间全故障时，不会在几秒内把重试打满；熔断后错误洪峰明显下降；冷却期结束后能自动探测后端恢复。

---

## 10. 技术选型

| 决策 | 选择 | 原因 |
|---|---|---|
| 核心系统语言 | C++ | 长生命周期服务，并发调度，计量逻辑单一实现 |
| 实验与分析 | Python | 读 events.jsonl、算指标、出图表 |
| 主线实验后端 | MockBackend | 可控可复现，论文数据来自它 |
| RealBackend | 小规模补充实验 | 验证 RQ3 抢占恢复下的质量退化是否可控，并报告开销 |
| 质量指标 | mock quality_score | 使 RQ2 可稳定复现，LLM-as-judge 后置 |
| 预算松紧度怎么判断"花快了" | 按已完成 Turn 占比，对比已结算花费（actual_spent），不按时间 | 避免“冻结额按最贵估算”在高并发早期系统性拉低 budget_factor；冻结额仅用于 admission 防超支 |
| 并发槽 | 启动时固定配置，不做运行时动态调整 | 并发上限是外部已知硬约束（云端 RPM 写在供应商文档、本地 GPU 并发取决于显存），不需要运行时探测；实验中固定 N 避免引入额外变量 |
| 适用场景 | 通用中间件，不区分个人/企业 | 同样的四个问题（预算/限流/优先级/僵尸）在个人和企业场景都存在，架构一致，只是参数不同 |

 