# AgentOS（Paper 1）设计文档

> **这份文档是规格书 + 验收标准（DoD）**：定清楚"最后要跑出什么结果、每阶段怎么验收、接口怎么拆"，然后倒推实现。  
> **怎么在某台机器上敲命令跑起来**不在这里讲，去看 `paper1_implementation.md`。

---

## 0. 我们在解决什么问题

LangChain、CrewAI、AutoGen 等框架解决了 agent **编排**，但缺少系统性的**资源治理与调度**，典型表现为三类问题：

**预算盲目（没人管花多少钱）**  
所有请求无差别地发往同一个昂贵模型，不区分任务难度。没有全局预算意识——前半段把钱花光，后半段高优任务无法执行。没有跨模型的 cost-quality 优化——明明本地 7B 就能做好的任务也在烧云端 API 额度。

**约束缺失（没人管上限）**  
多个 agent 共享同一 API key，没有任何 rate limit 协调机制。一个跑飞的 agent 可以把 token 预算耗尽，其余 agent 只能饿死。并发请求过多直接打出 429，崩掉整条流水线。

**调度缺失（没人管顺序）**  
高优先级任务（用户实时交互）和低优先级任务（后台批处理）争抢同一个并发槽，互相阻塞。僵尸 Turn——卡死、超时、语义原地打转——继续占着并发槽和预算预留，用户只能手动 kill 重开（这正是 Cursor 用户频繁遭遇"agent 不动了、只能 new context"的根本原因）。

三者彼此放大：无约束 → 滥用；无调度 → 滥用者不可打断；无成本意识 → 预算被低价值任务提前耗尽。

---

## 1. 核心抽象：我们把什么当作一等资源

AgentOS 将 LLM 相关资源抽象为**三类一等公民**，每类有不同的管理语义：

| 资源类型 | 类比 OS | 关键特性 |
|---|---|---|
| **Token 预算** | 内存（但花完不可补） | 带价格标签、不可再生；同一 token 在不同后端价格相差 10–100 倍 |
| **API 速率**（RPM/TPM） | I/O 带宽 | 可再生、有窗口；不同后端独立，可并行利用 |
| **并发槽** | 进程槽 / 文件描述符 | 排他分配、有硬上限 |

**Turn** 是调度与记账的基本单位：一次完整的 `llm.call()`，从创建到结束，中间可能排队、等待、重试、被回收，这些都算在同一个 Turn 里。

**架构两层设计**：

```
┌──────────────────────────────────────────────────────┐
│          Agent 应用层 (LangChain / CrewAI / etc.)     │
├──────────────────────────────────────────────────────┤
│               Unified LLM API Gateway                 │
│   llm.call(prompt, task_type, priority) → result      │
│   （对上层透明：agent 不知道底层用了哪个模型）          │
├──────────────────────────────────────────────────────┤
│                                                        │
│   ┌─ Resource Governor（治理层，工程保底）────────┐   │
│   │  Budget Governor    — 预算规划与时间分布       │   │
│   │  Rate Limiter       — API 速率协调             │   │
│   │  Admission Control  — Turn 准入检查            │   │
│   └────────────────────────────────────────────────┘  │
│                                                        │
│   ┌─ Multi-Backend Scheduler（调度层，研究增益）──┐   │
│   │  Priority Queue     — 两级队列，Turn 级调度    │   │
│   │  Model Selector     — 任务-模型匹配，cost-quality│ │
│   │  Zombie Detector    — 僵尸 Turn 检测与回收     │   │
│   │  Preemption         — 语义存档抢占             │   │
│   └────────────────────────────────────────────────┘  │
│                                                        │
│   ┌─ 基础设施 ────────────────────────────────────┐   │
│   │  LLM 模型后端池  — 异构后端统一适配          │   │
│   │    (MockBackend / OpenAI / vLLM / Ollama)        │   │
│   └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

**关键设计决策：治理与调度分离。**  
Governor（Budget / Rate Limiter / Admission Control）不依赖语义存档，用 FIFO + 计数器即可工作；Scheduler 在 Governor 的预算红线之内添加模型选择、优先级与**抢占（语义存档）**能力。两层分离的意义是：即使抢占策略迭代，Governor 的预算/速率/准入仍提供确定性工程底盘。

---

## 2. 做完算完成（DoD：以终为始）

> 先定好"验收标准"，再去写代码——这样不容易写歪、写大。

### 2.1 一条命令产出一次 run

```
agentos run --workload <path> --policy <policy> --out runs/<ts>/
```

输出目录最少包含两个文件：

- **`events.jsonl`**（JSON Lines 格式：每行一条独立的 JSON 记录，便于流式追加和逐行解析）——它是整个实验的**唯一事实来源**，所有后续分析脚本都从这个文件重算指标。为了保证旧 run 的数据能被新版分析脚本正确重算，schema 只允许**新增字段**，不得重命名或改变已有字段的语义。
- **`summary.json`**（标准 JSON，单个对象）——本次 run 的汇总指标快照，方便快速查看结果而无需重跑分析。正确性约束：对同一份 workload + policy + 随机种子，`summary.json` 中的指标必须与从 `events.jsonl` 复算得到的结果一致。

### 2.2 核心对比实验能跑通（RQ1/RQ2/RQ3/RQ4/RQ5）

**RQ1（Governor 的工程价值）**：并发 $N=10/20/50$
- **baseline**：裸跑（无预算/无共享限流协调/无准入）
- **treatment**：Governor-only（Budget + RateLimit + Admission）
- **指标**：完成率；429/限流错误率；预算耗尽时间（是否“前半段花光”）

**RQ2（异构调度收益）**：至少 2 个后端（贵强 / 便宜弱）
- **Baseline A**：固定贵模型 + 无预算管理
- **Baseline B**：Governor + 单模型（有预算但不选模）
- **Baseline C**：逐请求"性价比路由"（类似 RouteLLM/FrugalGPT：不看全局水位/时间）
- **AgentOS**：Governor + Scheduler（选模 + 抢占）
- **指标**：完成率（同预算下完成更多）；总花费/预算利用率；interactive 的 P99 延迟

**RQ3（抢占的尾延迟收益）**：interactive 与 batch 混合、并发槽紧张
- **对比**：无抢占 vs 有抢占（语义存档）
- **指标**：interactive 的 P99 延迟；被抢占次数；恢复成功率

**RQ4（抢占的系统稳定性）**：注入长尾 Turn（长输出/长延迟/高成本）
- **对比**：无抢占 vs 有抢占
- **指标**：tail amplification（interactive P99 受长尾影响幅度）；系统吞吐；被抢占 Turn 最终完成率

**RQ5（Zombie 回收效果）**：workload 注入"卡死/重复/烧钱"
- **对比**：无回收 vs 自动回收
- **指标**：系统吞吐；回收次数；资源归还正确性（预算/并发槽不泄漏）

---

## 3. MVP 范围（先把主线跑通）

### 3.1 范围（只为跑通 RQ1/2/3/4/5）

- **统一入口 `Gateway`**：所有 `llm.call()` 都必须走这里
- **模型后端至少两个**
  - `MockBackend`：不调用真实模型，而是按 workload 里预设的参数（延迟、token 数、成本、错误率、质量分）直接返回结果。主线实验全用它——原因是：我们要比较不同 policy（有无 Governor / 有无调度）的效果，如果每次调用真实 API，延迟和成本每次都不同，根本没法公平对比。Mock 就是把"外部噪声"控死，让每次运行结果只差在 policy 本身
  - `RealBackend`：接真实模型（本地 Ollama / 云端 API 均可），用来验证系统能跑通、行为和 Mock 一致——不用于主线对比实验
- **Governor（工程保底）**：Budget + RateLimit + Admission（必须有 reservation/结算）
- **Scheduler（研究最小版）**：PriorityQueue（两级）+ ModelSelector（启发式）+ **Preemption（语义存档抢占）** + ZombieDetector（两条规则起步）
- **ExperimentRunner**：读 workload、跑 baseline/policy、产出 `summary.json`

---

## 4. 数据模型（写代码用的"对象清单"）

### 4.1 Turn

Turn 是调度与记账的基本单位：一次完整的 `llm.call()` 交易单。

| 字段 | 说明 |
|---|---|
| `turn_id` | 唯一标识 |
| `created_at_ms` | 创建时间戳 |
| `priority` | `interactive \| batch` |
| `task_type` | `codegen \| retrieval \| reasoning \| format \| other` |
| `prompt` | prompt 内容（或引用） |
| `resource_spec` | 资源需求估算（见下） |
| `state` | 当前状态（见下） |

**Turn 状态流**：
- 正常：`created → admitted → queued → dispatched → running → completed`
- 异常：`failed`、`zombie_reaped`
- 抢占：`preempted / archived / resumed`（主线启用）

### 4.2 ResourceSpec（准入与预留用）

| 字段 | 说明 |
|---|---|
| `max_input_tokens_est` | 输入 token 上限估算 |
| `max_output_tokens_est` | 输出 token 上限估算 |
| `max_cost_usd_est` | 成本上限估算（美元） |
| `concurrency_slots` | 占用并发槽数（默认 1） |

### 4.3 BackendProfile（先从 `backends.yaml` 手填）

| 字段 | 说明 |
|---|---|
| `backend_id` | 后端唯一标识 |
| `context_window` | 上下文窗口大小（tokens） |
| `price_usd_per_1k_input` | 输入 token 单价 |
| `price_usd_per_1k_output` | 输出 token 单价 |
| `rpm_limit` | 每分钟请求数上限 |
| `tpm_limit` | 每分钟 token 数上限 |
| `quality_prior` | 按 task_type 的质量先验（可选） |

### 4.4 Ledger / Metering（记账要"真算钱"）

- **reservation**：Turn 开始前按估算成本预留（并发下避免超支）
- **settlement**：Turn 结束后按实际 tokens/cost 结算，退回差额

---

## 5. 模块边界（接口先定，后面不容易写歪）

### 5.1 Gateway（统一入口）

Gateway 做的事不多，但必须"全都从这里走"：

1. 接收 `llm.call(prompt, task_type, priority, hints)`
2. 估算 `ResourceSpec`
3. 调 Governor：admission + reservation
4. 把 Turn 交给 Scheduler（排队、选 backend）
5. 调后端执行
6. 收集 metering（tokens/cost/ttft/latency/error/quality）
7. 回写 ledger，并写事件到 `events.jsonl`

### 5.2 Governor（预算 + 限流 + 准入）

**BudgetGovernor**  
- 维护"期望消耗曲线 vs 实际消耗曲线"
- 水位信号：tighten（花快了）/ loosen（花慢了）
- reservation / settlement 接口

**RateLimiter**  
- 按 backend 维护 RPM/TPM 滑动窗口
- 第一版只做 RPM 也行

**AdmissionControl**  
- 检查 budget 余量、rate limit 余量、并发槽
- 不满足：wait（排队等）或 reject（直接拒绝）

### 5.3 Scheduler（排队 + 选模 + 止损）

**PriorityQueue**：两级队列（interactive 优先于 batch）

**ModelSelector**：在候选 backend 里选一个（启发式够用）

**ZombieDetector**：两条规则起步
- 超时：`no_progress_for > T`
- 烧钱异常：`spent_usd(turn) > k * baseline_spent(task_type)`
- 动作：回收 + 释放并发槽 + 结算/归还 reservation + 写 `zombie_reaped` 事件

**Preemption**：语义存档抢占（把 running/batch Turn 存档释放资源，让 interactive 先跑；之后再恢复继续）

### 5.4 模型后端（统一返回格式）

`Backend.call()` 统一返回：

| 字段 | 说明 |
|---|---|
| `text` | 模型输出文本 |
| `input_tokens` | 实际输入 token 数 |
| `output_tokens` | 实际输出 token 数 |
| `ttft_ms` | 首 token 延迟（毫秒） |
| `total_latency_ms` | 总延迟（毫秒） |
| `error_type?` | 错误类型（可选） |
| `quality_score?` | 质量分（MockBackend 必须有；RealBackend 可先无） |

---

## 6. 策略/算法（先"能跑 + 可解释"，别上来就最优解）

### 6.1 预算水位

**配置**：`budget_total_usd`，`budget_reserve_usd`，`horizon_seconds`

**逻辑**：
- 期望曲线：线性 $E(t) = \text{budget\_total} \times (t / \text{horizon})$
- 水位差：$\Delta(t) = A(t) - E(t)$（$A(t)$ 为实际累计花费）
  - $\Delta > 0$：花快了 → tighten（倾向便宜后端）
  - $\Delta < 0$：花慢了 → loosen（允许更好模型）

第一版 tighten/loosen 只需要影响 **ModelSelector 的偏好**，先别做复杂最优化。

### 6.2 选模（启发式）

**核心原则**：优先级越高越愿意花钱，预算越紧越少花钱。

评分公式：
$$\text{score} = w(\text{priority}) \times q\_prior(\text{task\_type}, \text{backend}) \,/\, \text{cost\_est}$$

硬约束过滤（不满足直接排除）：
- 预算：`cost_est ≤ remaining_budget − budget_reserve_usd`
- 上下文：`prompt_tokens_est ≤ context_window`
- 速率：RateLimiter 允许（或预计等待不超过阈值）

### 6.3 Zombie 检测（先两条规则）

| 规则 | 触发条件 |
|---|---|
| 超时 | `no_progress_for > T`（T 可按 task_type 配置） |
| 烧钱异常 | `spent_usd(turn) > k × baseline_spent(task_type)` |

触发后的回收协议：
1. 释放并发槽
2. 结算/归还 reservation（通知 Governor）
3. 写 `zombie_reaped` 事件（带 `reap_reason`）
4. 将 Turn 标记为可重试（若适用）

---

## 7. 实验与对照组（把对照组写死，后面才不会跑偏）

### 7.1 Policy 集合（Paper 1 最小集合）

| Policy 名 | 说明 | 用于 |
|---|---|---|
| `raw` | 无 Governor、无 Scheduler（裸跑 FIFO） | RQ1 baseline |
| `governor_only` | Budget + RateLimit + Admission，Scheduler 仍 FIFO | RQ1 treatment |
| `baseline_A_fixed_expensive` | 固定贵后端，无预算管理 | RQ2 对照 A |
| `baseline_B_governor_single_model` | Governor + 单模型，有预算无选模 | RQ2 对照 B |
| `baseline_C_per_request_router` | 每请求性价比路由，无全局水位/时间规划 | RQ2 对照 C |
| `agentos` | Governor + PriorityQueue + ModelSelector + Preemption + ZombieDetector | RQ1/2/3/4/5 treatment |

### 7.2 Workload 最小 schema（Mock 保证可复现）

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

---

## 8. 日志与产出格式

### 8.1 `events.jsonl`（唯一真相）

每行一个 JSON 事件，必须覆盖三条线：

**Turn 生命周期事件**  
事件类型：`created / admitted / queued / dispatched / running / completed / failed / zombie_reaped / preempted / archived / resumed`  
必带字段：`ts_ms`（时间戳）、`turn_id`、`event`

**后端调用事件**（每次真实/模拟调用都要写一行）

| 字段 | 说明 |
|---|---|
| `backend_id` | 后端标识 |
| `model` | 模型名 |
| `input_tokens` | 输入 token 数 |
| `output_tokens` | 输出 token 数 |
| `cost_usd` | 本次花费（美元） |
| `ttft_ms` | 首 token 延迟 |
| `total_latency_ms` | 总延迟 |
| `error_type` | `http_429 / timeout / http_5xx / backend_error / none` |

**Governor 事件**：预算水位 `delta_usd` 或 `tighten/loosen`；`reservation_usd`；`settlement_usd`；`admit/wait/reject`

**Scheduler 事件**：队列长度（interactive/batch）；选模决策（选了哪个 backend + 分数/拒绝原因）；抢占/存档/恢复（原因、释放/占用的资源、恢复点）；zombie 回收（原因 + 释放了什么资源）

### 8.2 `summary.json` 最小指标

```json
{
  "run_id": "...",
  "policy": "agentos",
  "workload_id": "mixed_v1",
  "seed": 42,

  "turn_total": 50,
  "turn_completed": 45,
  "turn_failed": 3,
  "turn_reaped": 2,

  "quality_mean": 0.82,
  "quality_std": 0.09,

  "ttft_mean": 312,
  "ttft_p95": 890,
  "ttft_p99": 1420,

  "cost_total_usd": 0.87,
  "budget_total_usd": 1.00,
  "budget_time_exhausted_s": null,

  "error_429_rate": 0.02,
  "timeout_rate": 0.01,

  "wall_time_s": 143,
  "throughput_turns_per_s": 0.31
}
```

---

## 9. 分阶段实现与验收

### Phase 0：骨架 + 事件日志（目标：当天完成）

- **做什么**：数据模型 + `events.jsonl` writer + 最小 CLI
- **验收**：跑 3 个 Turn，每个 Turn 在 events 里出现 `created → completed`，`summary.json` 能生成

### Phase 1：MockBackend + RateLimiter

- **做什么**：mock 可控 429/延迟/token/质量分；滑动窗口限流
- **验收**：20 并发、RPM=5；有/无限流时 429 数明显差异；events 里能看出 wait（等待放行）

### Phase 2：Budget + Admission（先把 RQ1 跑通）

- **做什么**：预算账本 + reservation + settlement；admit/wait/reject 逻辑
- **验收**：预算 $1、每次估算 $0.2；接近耗尽会 wait/reject；总花费不发散；reservation 被正确归还

### Phase 3：PriorityQueue

- **做什么**：interactive 优先 + 并发槽限制
- **验收**：先提交一堆 batch，再来 1 个 interactive；interactive 明显更快被 dispatched（events 里能看到时间差）

### Phase 4：ModelSelector + RQ2

- **做什么**：贵/便宜两个 BackendProfile；Policy A/B/C/AgentOS 全部跑通
- **验收**：同 workload 跑四次；至少能看到一个明确收益（更省钱 / 更稳 / 完成率更高）

### Phase 5：Preemption（语义存档抢占）+ RQ3/RQ4

- **做什么**：抢占协议（preempt→archive→resume）；抢占触发策略（最小可行：interactive 到来且无空闲并发槽时，抢占 batch 的 running 或队首长任务）；恢复策略（interactive 队列清空或水位恢复时逐步 resume）
- **验收**：并发槽=1 或 2；先提交长 batch，再来 interactive；interactive 明显更快完成；events 里能看到 `preempted / archived / resumed`；恢复后的 Turn 能继续完成（不丢账、不丢槽）

### Phase 6：ZombieDetector + RQ5

- **做什么**：workload 注入卡死/烧钱 turn；回收协议（释放槽 + 预算结算/归还）
- **验收**：20% 僵尸注入；启用回收后吞吐恢复；原因统计合理；预算/并发槽不会"越用越少"

---

## 10. 已定默认选择

**语言分工**
- 核心系统（Gateway/Governor/Scheduler/模型后端/Events）：**C++**（常驻、并发、计量与调度逻辑单一实现）
- 实验与分析（读 `events.jsonl`、算指标/出图表）：**Python**

**后端策略**
- 主线对比实验（RQ1/RQ2/RQ5）全用 `MockBackend`，论文里的表格/图来自它产出的 `events.jsonl`
- `RealBackend` 用于验证系统能跑通，配置细节在 `paper1_implementation.md`

**质量指标**
- 第一版统一用 **mock `quality_score`**（使 RQ2 的"质量均值/方差"可稳定复现）
- LLM-as-judge 作为后置增强，不阻塞主线

**时间与工作负载**
- 默认按**分钟级 horizon** 做模拟（便于快速跑 sweep）
- workload JSON 至少包含：`at_ms`、`priority`、`task_type`、以及 mock 行为字段

---

## 术语速查

| 术语 | 含义 |
|---|---|
| **Turn** | 一次完整 `llm.call()` 的调度与计量单位 |
| **429** | HTTP 错误码，表示"请求太多，被限流了" |
| **TTFT** | Time To First Token：从发请求到模型吐出第一个 token 的时间 |
| **Governor** | 治理器：管预算/限额/准入（"管钱 + 管闸门"） |
| **Scheduler** | 调度器：管排队与优先级（"谁先跑、谁后跑"） |
| **reservation** | 预留：Turn 开始前按估算成本锁定预算，防止并发超支 |
| **settlement** | 结算：Turn 结束后按实际消耗对账，归还多预留部分 |
| **zombie** | 僵尸 Turn：还在占着资源但没有实质进展的 Turn |
| **tighten / loosen** | 预算水位信号：花快了收紧（倾向便宜模型）/ 花慢了放松 |
| **RQ** | Research Question：研究问题编号 |
| **MockBackend** | 不调用真实模型，按 workload 预设参数直接返回结果。目的是把外部噪声（网络、API 版本、实时价格）控死，让实验结果只差在 policy 本身，方便公平对比 |
