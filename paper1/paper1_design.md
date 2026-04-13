# AgentOS（Paper 1）设计文档

> **这份文档 = 规格书 + 验收标准。** 定义"系统做什么、怎么验收、接口怎么拆"。  
> 具体怎么跑起来，看 `paper1_implementation.md`。

---

## 1. 问题：没人管钱、没人管闸、没人管顺序

先说一个事实：**调用 LLM 不是免费的。** 你每问 ChatGPT 一句话，背后都在按"输入了多少字、输出了多少字"扣钱。一个 AI Agent（自动执行任务的程序，循环调 LLM 几十上百次才能完成一个任务）跑一次可能花几美元。

现有框架（LangChain、CrewAI、AutoGen）解决了"多个 Agent 怎么协作"，但**没人管资源**：

**没人管钱。** 所有请求一律发给最贵的模型，不看任务难度。一个格式化 JSON 的简单任务，和一个写代码的复杂任务，花一样的钱。更糟的是没有全局预算意识——前半段把钱花光，后半段重要任务没钱执行。

**没人管闸。** LLM 供应商对每个 API key 限制了调用频率（比如每分钟最多 60 次）。超了就报错（HTTP 429："你太频繁了"）。多个 Agent 共享一个 key 却没有协调，一个 Agent 跑飞了能把额度全占光，其他 Agent 直接饿死。

**没人管顺序。** 用户正在屏幕前等结果的实时请求，和后台批量处理的低优先级请求，挤在同一条队里互相阻塞。更糟的是"僵尸调用"——卡死的、超时的、原地打转的 LLM 调用——继续占着资源不放，用户只能手动 kill 重来。

这三个问题互相放大：没有闸，Agent 滥用资源。没有调度，滥用的 Agent 无法被打断。没有预算意识，低价值任务把钱花光，高价值任务无法执行。

---

## 2. 思路：像操作系统管进程一样，管 LLM 调用

### 2.1 一次 LLM 调用消耗三种资源

每次调用 LLM（本文记作 `llm.call()`），同时消耗：

| 资源 | 性质 | 类比 | 管理方式 |
|---|---|---|---|
| **钱**（token 预算） | 花了就没了 | 汽车油箱 | 规划：什么时候花、花在哪 |
| **调用带宽**（每分钟次数限制） | 有瞬时上限，但会自动恢复 | 网络带宽 | 协调：别同时挤爆 |
| **并发槽**（同时能跑几个调用） | 占一个少一个，结束才释放 | 进程槽 | 调度：谁先用、要不要让路 |

三种资源逻辑完全不同，必须分开管。AgentOS 把它们当作三种独立的一等资源来治理。

### 2.2 Turn：调度的基本单位

**Turn** = 一次 `llm.call()` 的完整生命周期。从 Agent 发起调用，到拿到结果（或失败），中间可能排队、执行、被抢占、被回收——都算在同一个 Turn 里。

为什么选这个粒度？因为一个 Turn 刚好对应一次"占并发槽 + 花预算 + 用带宽"的完整周期，就像操作系统以进程（而非单条指令）为调度单位。

### 2.3 语义存档抢占

操作系统抢占进程时，把 CPU 寄存器存下来，让给更高优先级的进程，之后恢复继续执行。AgentOS 做类似的事，但存档的是 LLM 的"语义上下文"：

- **抢占**：高优先级的实时请求到来，但并发槽被低优先级的后台任务占满了。系统暂停一个后台 Turn。
- **存档**：把已经生成的中间结果（prompt + 已输出的文本）保存下来。
- **恢复**：高优先级 Turn 完成后，从存档恢复被暂停的 Turn，把已生成文本拼进新 prompt 继续，而不是从头重来。

叫"语义"是因为存的不是内存地址和寄存器值，而是对话层面有意义的内容。

### 2.4 架构总览

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
│  └────────────────────────────────────────────┘   │
│                                                      │
│  ┌─ Scheduler（调度层：优化增益）─────────────┐    │
│  │  Priority Queue   — 实时请求优先           │    │
│  │  Model Selector   — 选模型（性价比）       │    │
│  │  Zombie Detector  — 僵尸调用回收           │    │
│  │  Preemption       — 语义存档抢占           │    │
│  └────────────────────────────────────────────┘   │
│                                                      │
│  ┌─ 模型后端池 ──────────────────────────────┐    │
│  │  MockBackend / OpenAI / vLLM / Ollama       │    │
│  └────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────┘
```

**关键决策：治理和调度分离。**

- **Governor（治理层）** 管底线：预算不超支、频率不打 429、过载时拒绝。用简单的计数器就能工作，即使什么调度优化都不做，系统也不会崩。
- **Scheduler（调度层）** 管优化：在 Governor 画的红线之内，决定谁先跑、用哪个模型、要不要抢占。策略可以持续迭代，写错了 Governor 兜底，系统不会炸。

---

## 3. 怎样算做完：3 个实验问题

每个 RQ（Research Question）都是一个"加了 X 机制，数据会不会变好"的问题。

### RQ1：光加治理（不做智能调度），系统就能更稳吗？

- **场景**：50 个 Agent 同时发请求，API 频率限制 = 每分钟 60 次。
- **裸跑**：没有任何协调，想调就调。
- **加 Governor**：超频时让 Agent 排队等，而不是硬打 429。
- **预期**：裸跑时 429 错误率 30%+；加 Governor 后接近 0%，预算平稳消耗而不是前半段花光。

### RQ2：智能选模型，能比"无脑用贵的"更好吗？

- **场景**：总预算 $1.00，50 个任务（写代码/检索/格式化混合），两个模型可选——GPT-4（贵、质量高）和 Llama-7B（便宜、质量一般）。
- **对照 A（只用贵的）**：所有请求发 GPT-4，$1 只够 20 个任务，剩下 30 个没钱了。
- **对照 B（有预算管理 + 单模型）**：有预算控制但只有 GPT-4，快耗尽时只能拒绝。
- **对照 C（逐请求路由）**：每个请求独立选性价比最高的模型，但不看全局预算水位——不知道钱花快了还是慢了。
- **AgentOS**：Governor + Scheduler 完整协作。预算充裕时关键任务用 GPT-4，预算紧张时自动降级，简单任务一律用便宜模型。
- **预期**：AgentOS 完成率最高，关键任务质量不掉，预算花到最后一刻。

### RQ3：动态资源回收（抢占 + 僵尸检测）能挽救多少？

三种场景，同一个底层模式——**资源被错误的东西占着，检测→中断→释放→重新分配**：

- **场景 A（低优先级阻塞高优先级）**：并发槽 = 2，先提交 5 个后台任务（每个 10 秒），第 3 秒来了 1 个实时请求。无抢占时最坏等 10 秒；有抢占时 1 秒内开始执行。
- **场景 B（慢请求拖垮全局）**：50 个任务里有 5 个"怪物"——延迟 30 秒（正常 1–2 秒），长时间霸占并发槽。无抢占时 P99 被拉到 20–30 秒；有抢占时 P99 保持 3–5 秒。
- **场景 C（僵尸占着不放）**：50 个任务里有 10 个"僵尸"——5 个永不返回（卡死），5 个输出量是正常的 10 倍（烧钱）。无回收时吞吐下降 50%+；有回收时检测到超时或烧钱异常后强制回收，释放资源，吞吐恢复正常。

- **预期**：Interactive TTFT P99 从 10 秒降到 1–2 秒；整体 P99 保持在 3–5 秒；僵尸注入下吞吐恢复正常；被抢占的后台任务之后能恢复完成。

---

## 4. 实验产出格式

### 4.1 一条命令 = 一次实验

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
{"ts_ms":0,    "turn_id":"t001", "event":"created",    "priority":"interactive", "task_type":"codegen"}
{"ts_ms":1,    "turn_id":"t001", "event":"admitted",   "reservation_usd":0.05}
{"ts_ms":2,    "turn_id":"t001", "event":"queued",     "queue":"interactive", "queue_len":1}
{"ts_ms":3,    "turn_id":"t001", "event":"dispatched", "backend_id":"gpt4", "score":36.8}
{"ts_ms":3,    "turn_id":"t001", "event":"running"}
{"ts_ms":1203, "turn_id":"t001", "event":"completed",  "backend_id":"gpt4", "input_tokens":500, "output_tokens":300, "cost_usd":0.042, "ttft_ms":200, "total_latency_ms":1200, "quality_score":0.92, "settlement_usd":0.042, "reservation_refund_usd":0.008}
```

其中 `ts_ms` 是 run 内相对时间（run 开始 = 0），方便不同机器跑出来的结果直接对齐。

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
  "budget_total_usd": 1.00,
  "ttft_p99": 1420,
  "error_429_rate": 0.02,
  "wall_time_s": 143
}
```

### 4.2 summary.json 字段定义（论文主线冻结）

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
| `budget_total_usd` | 预算上限 | 配置中的预算总额 | USD |
| `ttft_p99` | 实时请求的尾延迟 | interactive 且 completed 的 `ttft_ms` 取第 99 百分位 | ms |
| `error_429_rate` | 429 错误占比 | `error_type="http_429"` 的 Turn 数 / `turn_total` | 0–1 |
| `wall_time_s` | 端到端时间 | (max ts_ms − min ts_ms) / 1000 | s |

### 4.3 events.jsonl schema 演进规则

- **版本化**：文件头 `meta` 事件记录 `schema_version`。
- **论文冻结**：主线实验用 `schema_version = paper1_v1`，论文产出的 runs 必须能用同一份 `analyze.py` 复算出一致结果。
- **可迁移**：改字段时写迁移脚本，不指望读者手改。复现者拿到"代码 + workload + analyze + traces"应当一键出论文数字。

### 4.4 quality_score 说明

`quality_score`（0–1）衡量"这个 Turn 的输出质量好不好"。两种来源：

| 模式 | 来源 | 用途 |
|---|---|---|
| Mock 实验（主线） | `workload.mock.quality_score` 预设值 | 可复现对比，不同 policy 的差异只来自调度机制 |
| 真实实验 | 按 `task_type` 调用确定性 grader：`(prompt, output) → float` | 验证真实模型下的质量差异 |

Grader 是纯函数，不依赖 LLM：`format` 用 JSON parse，`codegen` 用编译+测试通过率，`retrieval` 用正则匹配，`reasoning` 用答案精确匹配。同输入同输出必须得到同分数。

存在的意义：RQ2 需要证明"省了钱但没胡说八道"——光比完成率不够，还得看质量。

---

## 5. MVP 范围

只做跑通 RQ1–3 需要的最小集合：

- **Gateway**：所有 `llm.call()` 的统一入口
- **两种模型后端**
  - `MockBackend`：按 workload 预设的参数直接返回结果（延迟、token 数、成本、错误、质量分都写死）。主线实验全用它——因为要公平比较不同 policy，不能让真实 API 的随机波动干扰结果。
  - `RealBackend`：接真实模型（Ollama / 云端 API），仅用于验证系统能跑通。
- **Governor**：Budget + RateLimit + Admission（含预留/结算）
- **Scheduler**：PriorityQueue（两级）+ ModelSelector（启发式）+ Preemption + ZombieDetector（两条规则）
- **ExperimentRunner**：读 workload → 跑 policy → 产出 events.jsonl + summary.json

---

## 6. 数据模型

### 6.1 Turn（一次 LLM 调用的交易单）

| 字段 | 说明 |
|---|---|
| `turn_id` | 唯一标识 |
| `created_at_ms` | 创建时间戳 |
| `priority` | `interactive`（实时）或 `batch`（后台） |
| `task_type` | `codegen / retrieval / reasoning / format / other` |
| `prompt` | prompt 内容或引用 |
| `resource_spec` | 资源需求估算（见 6.2） |
| `state` | 当前状态 |

**状态流转**：
- 正常路径：`created → admitted → queued → dispatched → running → completed`
- 异常：`failed` / `zombie_reaped`
- 抢占：`preempted → archived → resumed`

### 6.2 ResourceSpec（准入前的资源估算）

| 字段 | 说明 |
|---|---|
| `max_input_tokens_est` | 输入 token 上限估算 |
| `max_output_tokens_est` | 输出 token 上限估算 |
| `max_cost_usd_est` | 成本上限估算（美元） |
| `concurrency_slots` | 占用并发槽数（默认 1） |

### 6.3 BackendProfile（模型后端的配置卡片）

| 字段 | 说明 |
|---|---|
| `backend_id` | 后端标识 |
| `context_window` | 上下文窗口大小（能接受的最大 token 数） |
| `price_usd_per_1k_input` | 输入 token 单价（每千 token） |
| `price_usd_per_1k_output` | 输出 token 单价 |
| `rpm_limit` | 每分钟请求次数上限 |
| `tpm_limit` | 每分钟 token 数上限 |
| `quality_prior` | 按 task_type 的预估质量分（可选） |

### 6.4 记账机制（预留 + 结算）

像酒店预授权：

1. **预留（reservation）**：Turn 开始前，按估算成本从预算中冻结一笔钱。即使 10 个 Turn 并发执行，系统也不会因为"都还没扣钱"而超支。
2. **结算（settlement）**：Turn 结束后，按实际消耗算真实花费，退回多冻的差额。

---

## 7. 模块接口

### 7.1 Gateway（统一入口）

所有 `llm.call()` 必须经过 Gateway，它串联整个流程：

1. 接收调用请求（prompt + task_type + priority）
2. 估算资源需求（ResourceSpec）
3. 问 Governor：能不能执行？预留预算
4. 交给 Scheduler：排队、选模型
5. 调后端执行
6. 收集实际消耗（token 数 / 花费 / 延迟 / 错误 / 质量）
7. 结算预算，写事件日志

### 7.2 Governor（治理层）

**BudgetGovernor**
- 维护"期望花费曲线 vs 实际花费曲线"
- 发出水位信号：`tighten`（花快了）/ `loosen`（花慢了）
- 提供 reservation / settlement 接口

**RateLimiter**
- 按后端维护每分钟调用次数的滑动窗口
- 第一版只管 RPM 即可

**AdmissionControl**
- 检查预算余量、频率余量、并发槽
- 不满足时：`wait`（排队）或 `reject`（拒绝）

### 7.3 Scheduler（调度层）

**PriorityQueue**：两级队列，interactive 始终优先于 batch。

**ModelSelector**：在候选后端中选一个（启发式评分）。

**ZombieDetector**：两条规则——超时未返回、花费异常偏高。触发后回收 Turn、释放并发槽、归还预留预算、写 `zombie_reaped` 事件。

**Preemption**：当 interactive Turn 到来但无空闲槽时，暂停一个 batch Turn（存档），让 interactive 先跑；之后恢复被暂停的 Turn 继续。

### 7.4 模型后端（统一返回格式）

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

## 8. 算法与策略

### 8.1 预算水位

**配置**：`budget_total_usd`（总预算），`budget_reserve_usd`（保底留多少），`horizon_seconds`（预算窗口时长）

**逻辑**：画一条线性"期望花费曲线"——如果预算均匀花完，到时间 t 应该花了多少。然后比较实际花费和期望值：

$$E(t) = \text{budget\_total} \times (t / \text{horizon})$$
$$\Delta(t) = \text{实际花费}(t) - E(t)$$

- Δ > 0（花快了）→ `tighten`：倾向选便宜模型
- Δ < 0（花慢了）→ `loosen`：允许选更好模型

第一版只让 tighten/loosen 影响选模偏好，不做复杂优化。

### 8.2 选模型（启发式）

**核心原则**：优先级越高越愿意花钱，预算越紧越少花钱。

评分公式：

$$\text{score} = w(\text{priority}) \times q\_prior(\text{task\_type}, \text{backend}) \,/\, \text{cost\_est}$$

各项含义：
- `w(priority)`：优先级权重。interactive = 2.0，batch = 1.0。实时任务愿意为质量多付钱。
- `q_prior`：预估质量分（0–1），预先配置在后端的配置文件里。例如 GPT-4 做代码生成 = 0.92，Llama-7B 做代码生成 = 0.65。
- `cost_est`：预估花费（美元），根据 prompt 长度 × 后端单价算出。

**举个例子**：一个 interactive 的代码生成任务到来，两个后端可选：

| | GPT-4 | Llama-7B |
|---|---|---|
| q_prior | 0.92 | 0.65 |
| cost_est | $0.05 | $0.001 |
| w(interactive) | 2.0 | 2.0 |
| **score** | 2.0 × 0.92 / 0.05 = **36.8** | 2.0 × 0.65 / 0.001 = **1300** |

按性价比 Llama-7B 远胜。但如果预算充裕（loosen），系统会更倾向 GPT-4 以获得更好质量。具体做法：给 w(priority) 乘一个 budget_factor（tighten 时 < 1，loosen 时 > 1）。

**硬约束过滤**（不满足直接排除，不进入评分）：
- 预算：`cost_est ≤ remaining_budget − reserve`
- 上下文窗口：prompt 长度不超过后端容量
- 频率：RateLimiter 允许

### 8.3 僵尸检测

两条规则，都基于数值信号，不需要分析输出内容：

**规则 1：Wall-clock 超时。** Turn 进入 `running` 后，超过 `T_max` 秒未结束，判定为卡死。`T_max` 按 task_type 配置（如 codegen = 30s，format = 10s）。覆盖场景：API 挂起、网络断连。

**规则 2：Cost overrun。** 准入时已冻结 `reservation_usd`（成本估算上限）。执行期间实时追踪 `cost_so_far`（流式输出时 = `output_tokens_so_far × price_per_token`）。若 `cost_so_far > k × reservation_usd`（默认 k = 3.0），判定为烧钱僵尸。覆盖场景：模型循环输出、无限续写。关键：**不需要理解输出内容**——模型是在重复自己还是产出有意义的文本无所谓，只看账单。`cost_so_far` 是单调递增计数器，每收到一批 streaming tokens 就更新，计算开销为零。

| 规则 | 输入信号 | 触发条件 | 典型场景 |
|---|---|---|---|
| 超时 | wall_clock_elapsed | > T_max(task_type) | API 挂起、网络断连 |
| 烧钱 | cost_so_far / reservation_usd | > k（默认 3.0） | 模型循环输出、无限续写 |

触发后的回收流程：释放并发槽 → 归还预留预算 → 写 `zombie_reaped` 事件 → 标记可重试

---

## 9. 实验设计

### 9.1 Policy 集合

| Policy | 说明 | 用于 |
|---|---|---|
| `raw` | 裸跑：无 Governor、无 Scheduler | RQ1 baseline |
| `governor_only` | 只有 Governor，Scheduler 仍 FIFO | RQ1 treatment |
| `baseline_A_fixed_expensive` | 所有请求发贵模型，不管预算 | RQ2 对照 A |
| `baseline_B_governor_single_model` | Governor + 单模型 | RQ2 对照 B |
| `baseline_C_per_request_router` | 逐请求选性价比最高的，不看全局水位 | RQ2 对照 C |
| `agentos` | 全部机制开启 | RQ1–3 treatment |

### 9.2 Workload（实验脚本）

Workload 是一份提前写好的"剧本"：什么时间点来什么任务、每个任务在 mock 下表现成什么样（延迟多久、花多少钱、会不会报错）。不同 policy 在同一份 workload 上跑，保证公平对比。

**单条 Turn 记录**：

```json
{
  "turn_id": "t001",
  "at_ms": 0,
  "priority": "interactive",
  "task_type": "codegen",
  "mock": {
    "input_tokens": 500,
    "output_tokens": 300,
    "latency_ms": 1200,
    "ttft_ms": 200,
    "error": "none",
    "quality_score": 0.85
  }
}
```

**完整 workload 示例**（覆盖三种典型情况：正常完成、429 失败、超时被回收）：

```json
{
  "workload_id": "toy_3turns_v1",
  "turns": [
    {
      "turn_id": "t001", "at_ms": 0,
      "priority": "interactive", "task_type": "codegen",
      "mock": { "input_tokens": 200, "output_tokens": 120, "latency_ms": 900, "ttft_ms": 120, "error": "none", "quality_score": 0.85 }
    },
    {
      "turn_id": "t002", "at_ms": 50,
      "priority": "batch", "task_type": "retrieval",
      "mock": { "input_tokens": 80, "output_tokens": 40, "latency_ms": 300, "ttft_ms": 60, "error": "http_429", "quality_score": 0.0 }
    },
    {
      "turn_id": "t003", "at_ms": 100,
      "priority": "batch", "task_type": "reasoning",
      "mock": { "input_tokens": 150, "output_tokens": 200, "latency_ms": 5000, "ttft_ms": 200, "error": "timeout", "quality_score": 0.0 }
    }
  ]
}
```

跑这份 workload 大概会看到：
- t001：正常完成，产生花费记录
- t002：触发 429 → `failed`，推高 `error_429_rate`
- t003：超时 → 如果开了 ZombieDetector，会被 `zombie_reaped`

### 9.3 events.jsonl 事件类型汇总

events.jsonl 记录四条线的事件：

**Turn 生命周期**：`created / admitted / queued / dispatched / running / completed / failed / zombie_reaped / preempted / archived / resumed`

**后端调用**：backend_id、input_tokens、output_tokens、cost_usd、ttft_ms、total_latency_ms、error_type

**Governor 决策**：reservation_usd、settlement_usd、admit/wait/reject、tighten/loosen

**Scheduler 决策**：队列长度、选模结果与分数、抢占/存档/恢复、zombie 回收原因

每行必带三个字段：`ts_ms`（时间戳）、`turn_id`、`event`。

**完整示例**（对应上面的 3-turn workload）：

```jsonl
{"ts_ms":0,   "turn_id":"t001", "event":"created",      "priority":"interactive", "task_type":"codegen"}
{"ts_ms":2,   "turn_id":"t001", "event":"admitted",     "reservation_usd":0.05}
{"ts_ms":3,   "turn_id":"t001", "event":"dispatched",   "backend_id":"gpt4"}
{"ts_ms":4,   "turn_id":"t001", "event":"running"}
{"ts_ms":904, "turn_id":"t001", "event":"completed",    "backend_id":"gpt4", "input_tokens":200, "output_tokens":120, "ttft_ms":120, "total_latency_ms":900, "cost_usd":0.03, "settlement_usd":0.03}

{"ts_ms":50,  "turn_id":"t002", "event":"created",      "priority":"batch", "task_type":"retrieval"}
{"ts_ms":55,  "turn_id":"t002", "event":"dispatched",   "backend_id":"gpt4"}
{"ts_ms":105, "turn_id":"t002", "event":"failed",       "backend_id":"gpt4", "error_type":"http_429"}

{"ts_ms":100, "turn_id":"t003", "event":"created",      "priority":"batch", "task_type":"reasoning"}
{"ts_ms":110, "turn_id":"t003", "event":"running"}
{"ts_ms":5200,"turn_id":"t003", "event":"zombie_reaped","reap_reason":"timeout", "reservation_refund_usd":0.05}
```

---

## 10. 分阶段实现与验收

### Phase 0：骨架 + 事件日志
- **做什么**：数据模型 + events.jsonl writer + 最小 CLI
- **验收**：跑 3 个 Turn，events 里出现 `created → completed`，summary.json 能生成

### Phase 1：MockBackend + RateLimiter
- **做什么**：mock 可控延迟/429/token/质量分；滑动窗口限流
- **验收**：20 并发、RPM=5；有/无限流时 429 数明显不同

### Phase 2：Budget + Admission（跑通 RQ1）
- **做什么**：预算账本 + reservation/settlement；admit/wait/reject
- **验收**：预算 $1、每次估算 $0.2；接近耗尽会 reject；总花费不超预算；预留被正确归还

### Phase 3：PriorityQueue
- **做什么**：interactive 优先 + 并发槽限制
- **验收**：先提交一堆 batch，再来 1 个 interactive；interactive 明显更快被调度

### Phase 4：ModelSelector（跑通 RQ2）
- **做什么**：贵/便宜两个后端；四种 policy 全部跑通
- **验收**：同 workload 跑四次，能看到明确收益（更省钱或完成率更高）

### Phase 5：Preemption + ZombieDetector（跑通 RQ3）
- **做什么**：抢占协议（preempt → archive → resume）；触发策略（interactive 到来 + 无空闲槽 → 抢占 batch）；workload 注入卡死/烧钱 Turn；僵尸回收协议
- **验收**：events 里出现 preempted/archived/resumed；恢复后的 Turn 正常完成；不丢账不丢槽；20% 僵尸注入下吞吐恢复；预算/并发槽不泄漏

---

## 11. 技术选型

| 决策 | 选择 | 原因 |
|---|---|---|
| 核心系统语言 | C++ | 常驻进程，并发调度，计量逻辑单一实现 |
| 实验与分析 | Python | 读 events.jsonl、算指标、出图表 |
| 主线实验后端 | MockBackend | 可控可复现，论文数据来自它 |
| RealBackend | 仅做 sanity check | 验证系统能跑通，不用于主线对比 |
| 质量指标 | mock quality_score | 使 RQ2 可稳定复现，LLM-as-judge 后置 |
| 时间尺度 | 分钟级 horizon | 便于快速跑实验 |
| 并发槽 | 启动时固定配置，不做运行时动态调整 | 并发上限是外部已知硬约束（云端 RPM 写在供应商文档、本地 GPU 并发取决于显存），不需要运行时探测；实验中固定 N 避免引入额外变量 |
| 适用场景 | 通用中间件，不区分个人/企业 | 同样的四个问题（预算/限流/优先级/僵尸）在个人和企业场景都存在，架构一致，只是参数不同 |

---

## 术语速查

| 术语 | 含义 |
|---|---|
| **Token** | LLM 计费单位。约 1 英文词 ≈ 1 token，1 中文字 ≈ 1.5–2 token |
| **Agent** | 循环调 LLM 自主完成任务的程序 |
| **Turn** | 一次 `llm.call()` 的完整生命周期，调度和计费的基本单位 |
| **429** | HTTP 错误码："请求太频繁，被限流" |
| **RPM / TPM** | 每分钟请求数 / 每分钟 token 数，API 的频率上限 |
| **TTFT** | Time To First Token：从发请求到模型开始输出的时间 |
| **P99** | 第 99 百分位延迟：最慢的 1% 请求等了多久 |
| **Governor** | 治理层：管钱、管闸、管准入 |
| **Scheduler** | 调度层：管顺序、选模型、管抢占 |
| **reservation / settlement** | 预留（执行前冻结预算）/ 结算（执行后按实际扣费，退差额） |
| **quality_score** | 输出质量分（0–1），第一版在 mock 中预设 |
| **q_prior** | 质量先验：预先配置的"某后端在某类任务上的预期质量" |
| **zombie** | 僵尸 Turn：占着资源但无实质进展的调用 |
| **tighten / loosen** | 预算水位信号：花快了 → 选便宜模型 / 花慢了 → 允许好模型 |
| **语义存档抢占** | 暂停低优先级 Turn，保存已生成内容，让高优先级先跑；之后恢复继续 |
| **MockBackend** | 按预设参数返回结果，不调真实模型，让实验只比较策略差异 |
