# Paper 1 Implementation Plan (C++ Core + Python Experiments)

> 这份文档有两个读者：
> - **论文作者**：先看“仓库结构 / 接口边界 / 可复现输出（events.jsonl）/ 一键运行命令”，确认 scope 与可复现性。
> - **写代码的 agent**：按后面的 Phase 清单逐步实现，优先跑通 RQ1 / RQ2 / RQ5。

## 术语速查（给大一读者）

- **`<...>` 这种尖括号**：表示“占位符”（placeholder），意思是“这里要换成你自己的值”，不是 TypeScript 也不是任何语言。
- **`<ts>`**：timestamp（时间戳）。就是用“当前时间”当作文件夹名字，保证每次运行不会覆盖上一次结果。  
  例：`<ts>` 可以是 `2026-04-07T120000Z`。
- **路径里的 `/`**：表示文件夹层级，比如 `paper1/runs/a/b.txt` 代表 `paper1`→`runs`→`a`→`b.txt`。

- **RQ**：Research Question（研究问题编号，比如 RQ1/RQ2/RQ5）。
- **baseline（对照组）**：拿来比较的“普通做法/现有做法”。
- **Governor（治理器）**：像“管钱+管限额”的模块：预算够不够、能不能现在发请求。
- **Scheduler（调度器）**：像“排队+插队”的模块：谁先跑、用哪个后端模型。
- **token**：模型处理文本的计费单位（大致可以理解为“按字数计费的单位”）。
- **429**：常见的 HTTP 错误码，表示“请求太多，被限流了”。
- **TTFT**：Time To First Token（从发请求到模型吐出第一个字的时间，越小越好）。
- **RPM/TPM**：Rate limit（限流指标）；RPM=每分钟请求数上限，TPM=每分钟 token 上限。
- **JSONL**：JSON Lines；一个文件里“一行一个 JSON 对象”，方便追加写日志（这里就是 `events.jsonl`）。
- **Mock（模拟）**：不连真实模型，用“事先写好的规则/参数”模拟延迟、成本、错误，保证实验可复现。
- **sanity（冒烟检查）**：只做最小验证“它能跑通”，不追求完整实验。
- **YAML**：一种“写配置文件的格式”（像更容易读的 JSON），文件后缀常见是 `.yaml`。
- **schema（格式约定）**：规定一个 JSON/YAML “应该有哪些字段、每个字段是什么意思”。有了它，大家写/读文件才不会乱。

---

## 0. 最终交付物（对论文作者的承诺）

### 0.1 一条命令产出一次可复现实验 run

```bash
./paper1/agentos run --workload paper1/workloads/mixed.json --policy agentos --out paper1/runs/2026-04-07T120000Z/
```

输出目录最少包含：
- `paper1/runs/<ts>/events.jsonl`（**唯一真相**：所有分析从这里算）
- `paper1/runs/<ts>/summary.json`（本次 run 的汇总指标；比如完成率、平均 TTFT、总花费）
- `paper1/runs/<ts>/config_snapshot/`（可选但推荐：把 workload/policy/backend 配置复制进来，保证复现）

### 0.2 论文核心实验先做这三项（与 `paper1_design.md` 对齐）

- **RQ1 Governor 基线价值**：裸跑 vs governor-only（只开 Governor：Budget=预算，RateLimit=限流，Admission=准入/不准进队）
- **RQ2 异构调度收益**：Baseline A/B/C vs AgentOS（至少 2 个 backend=两个“模型后端/服务”：贵强 / 便宜弱；先用 MockDriver 保证可复现）
- **RQ5 Zombie 回收效果**：注入卡死/烧钱/重复（zombie=“假活着但没进展的任务”），比较吞吐与完成时间

> RQ3/RQ4（语义存档抢占）先不绑主线：**只预留接口与日志点**。

---

## 1. 仓库文件系统结构（论文作者先看这里）

### 1.1 顶层目录

```
AgentOS/
  paper1/
    paper1.md
    paper1_design.md
    paper1_implement.md
    agentos-cpp/                 # Paper1 核心系统（C++）
    agentos-exp/                 # 实验与分析（Python）
    workloads/
    runs/                        # 运行输出（不进版本库）
  thesis.md

  paper2/
  paper3/
  prompt.md
```

### 1.2 语言分工（为什么混合而不是全 Python / 全 C++）

- **C++（在线路径）**：常驻执行、并发调度、限流/准入、预算记账、事件日志写入 —— 逻辑必须单一实现，避免漂移。
- **Python（离线路径）**：workload 生成/变体、批量跑实验、统计汇总、画图 —— Python 的优势最大且对系统正确性零风险。

---

## 2. 对外接口与最小 API 边界（论文作者关心）

### 2.1 CLI 接口（必须稳定）

- `agentos run --workload <path> --policy <name> --out <dir> [--seed N] [--repeat K]`（CLI=命令行接口）
- `agentos validate-workload <path>`（可选，建议做）

`--policy` 至少支持：
- `bare`：无治理/无调度（对照）
- `governor_only`：Budget+RateLimit+Admission（RQ1）
- `route_like`：逐请求性价比路由（近似 RouteLLM/FrugalGPT 的 baseline C）
- `agentos`：Governor + Scheduler（RQ2/RQ5）

### 2.2 核心调用接口（C++内部）

Paper1 的执行单位是 Turn（一次 `llm.call` 交易）。
（Turn=一次“调用模型+可能的等待/排队+最终成功/失败”的完整过程。）

```cpp
struct LlmCallRequest {
  std::string prompt;
  TaskType task_type;          // codegen|retrieval|reasoning|format|other
  Priority priority;           // interactive|batch
  CallHints hints;             // 可选：max_tokens_est, deadline, etc.
};

struct LlmCallResult {
  std::string text;
  Metering metering;           // tokens/cost/ttft/latency/error
};

class Gateway {
public:
  LlmCallResult Call(const LlmCallRequest& req);
};
```

### 2.3 “唯一真相”接口：`events.jsonl`（必须稳定）

所有指标（TTFT、429 错误率、成本、完成率、回收次数等）都只能从 `events.jsonl` 推导，避免“代码里算一套、论文里算一套”。
（`events.jsonl`=系统运行时写出来的流水账；Python 分析脚本只读它来算结果。）

每行一个 JSON object，至少包含：

- **通用字段**：`ts_ms`, `run_id`, `event_type`, `turn_id`, `agent_id?`
- **Turn 生命周期**：`created/admitted/queued/dispatched/running/completed/failed/zombie_reaped/(preempted,archived,resumed)`
- **后端调用**：`backend_id`, `model_id`, `input_tokens`, `output_tokens`, `cost_usd`, `ttft_ms`, `latency_ms`, `error_type`（429/timeout/5xx/none）
- **Governor 状态**：`budget_total_usd`, `budget_spent_usd`, `budget_reserved_usd`, `budget_reserve_usd`, `admit_decision`（admit/wait/reject）
- **Scheduler 决策**：`queue_len`, `selected_backend_id`, `select_reason`, `reap_reason`

> 事件字段宁可多一点，也不要后期改名/删字段（会破坏复现与画图脚本）。

---

## 3. 配置与输入文件格式（给论文作者看可复现性）

### 3.1 `workloads/*.json`（最小 schema）

每个 workload 是一组到达的 Turn：

```json
{
  "workload_id": "mixed",
  "seed": 1,
  "turns": [
    {
      "at_ms": 0,
      "priority": "batch",
      "task_type": "format",
      "prompt_template": "…",
      "mock": {
        "input_tokens": 800,
        "output_tokens": 400,
        "latency_ms": 1200,
        "ttft_ms": 200,
        "quality_score": 0.8,
        "error_type": "none",
        "zombie_mode": "none"
      }
    }
  ]
}
```

### 3.2 `backends.yaml`（先手填，Auto-Prober 后置）

至少两个 backend（backend=一个“模型后端/服务端点”）：`expensive_strong` / `cheap_weak`，字段对齐 `paper1_design.md` 的 `BackendProfile`。

---

## 4. 关键模块与职责边界（给 agent 写代码用，但论文作者也能审）

### 4.1 Gateway（唯一入口）

职责：
- 生成 `Turn`
- 估算 `ResourceSpec`（基于 hints 或 workload 提供的估计）
- 调用 Governor：admission + reservation
- 入 Scheduler 队列并获取 backend 决策
- 调用 Driver 获取结果与 metering
- 结算/释放 reservation
- 写 `events.jsonl`（生命周期 + 调用细节 + 决策理由）

### 4.2 Governor（Budget + RateLimit + Admission + Ledger）

- **BudgetGovernor**：reservation + settlement（reservation=先“预留一笔预算”；settlement=结束后按真实花费“结算”）；输出“水位信号”（tight=预算紧/少花钱，loose=预算松/可多花钱，delta=偏差值）
- **RateLimiter**：按 backend 维护 RPM/TPM（限流；先做简化滑动窗口/令牌桶）
- **AdmissionControl**：不满足则 wait/reject（wait=先排队等资源；reject=直接拒绝这次请求）
- **Ledger**：每次调用精确记账（token→usd），并记录 reserved（预留） vs spent（实际花费）

### 4.3 Scheduler（PriorityQueue + ModelSelector + ZombieDetector）

- **PriorityQueue**：优先级队列（interactive=用户在等的交互请求；batch=后台请求）
- **ModelSelector**：选后端/选模型的简单规则（启发式）：优先级越高越愿意花钱，预算越紧越少花钱
- **ZombieDetector**：先两条规则
  - no-progress timeout
  - burn-rate anomaly（烧钱异常：花费超过同类 baseline 的 \(k\) 倍）
- **Preemption（预留接口）**：先不启用，只留 event_type 与 hook

### 4.4 Drivers

- **MockDriver（必须）**：按 workload 指定的 mock（模拟）行为返回 metering/错误/质量分，用于稳定实验
- **RealDriver（后置）**：只做 sanity（冒烟检查：能通一次 call 即可）

---

## 5. Phase 计划（严格按“先能跑”推进）

> 每个 Phase 都必须：能运行、能写 events、能产出 summary。不要等“架构完美”。

### Phase 0：骨架 + events.jsonl（当天）
- 数据模型：Turn/ResourceSpec/BackendProfile/Metering
- `agentos run` 跑 3 个 turn：events 里至少 `created -> completed`

### Phase 1：MockDriver + RateLimiter（RQ1/RQ2 的基础）
- mock 可控：429/延迟/token/质量分
- RPM=5，20 并发时 429 数明显下降（启/不启限流对比）

### Phase 2：Budget + Admission + reservation（RQ1）
- 预算 \$1，每次估算 \$0.2：接近耗尽会 wait/reject
- 总花费不发散，reserved 与 spent 对得上

### Phase 3：PriorityQueue + 并发槽
- 先堆 batch，再来 interactive：interactive 明显更快 dispatch

### Phase 4：ModelSelector + RQ2
- 两个 backend profile（贵强/便宜弱）
- 跑四个 policy（policy=策略/配置组合）：A/B/C/AgentOS；summary 出：成本、完成率、质量均值/方差（方差=“波动大不大”）、预算利用率

### Phase 5：ZombieDetector + RQ5
- workload 注入 20% zombie（卡死/烧钱）
- 启用回收后吞吐恢复；events 里 `zombie_reaped` 原因分布合理

### Phase 6（可选）：语义存档抢占（RQ3/RQ4）
- 先用 MockArchive（固定成本 + 可控有损率）验证接口与指标

---

## 6. Python 实验链（只做离线，保证复现）

### 6.1 输入/输出
- 输入：`paper1/runs/**/events.jsonl`
- 输出：`figures/*.pdf` + `tables/*.csv` + `report.md`

### 6.2 先实现的指标函数（与 paper1 的图表对齐）
- 完成率（按 turn）
- 429/timeout/5xx 错误率
- 平均/分位 TTFT（分位=比如 P50/P95，“大多数情况”和“最慢那一批”分别多慢）
- 总花费、预算耗尽时间、预算利用率
- 质量均值 + 方差（先用 mock quality）
- zombie 回收次数与原因分布

