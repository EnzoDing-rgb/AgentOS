# AgentOS（paper1）设计文档

> 这份文档就是为了让你**马上能开写代码**：先把“最后要跑出的实验结果/指标”定死，再倒推模块与接口；同时把实现拆成阶段，每阶段你都能用很短的人工步骤验收。

## 术语速查（给大一读者）

- **`<...>` 这种尖括号**：表示“占位符”，意思是“这里要换成你自己的值”，不是某种语言。
- **`<ts>`**：timestamp（时间戳），用“当前时间”当文件夹名，避免覆盖上一次 run 的结果。
- **RQ**：Research Question（研究问题编号）。
- **baseline（对照组）**：用来比较的“普通做法/现有做法”。
- **token**：模型计费的单位（大致可理解成“按字数计费的单位”）。
- **429**：HTTP 错误码，表示“请求太多，被限流了”。
- **TTFT**：Time To First Token（从发请求到模型吐出第一个字的时间）。
- **Governor（治理器）**：管预算/限额/准入（像“管钱+管闸门”）。
- **Scheduler（调度器）**：管排队与优先级（像“谁先跑、谁后跑”）。
- **Mock（模拟）**：不连真实模型，用可控参数模拟成本/延迟/错误，保证实验可复现。

---

## 1. 做完算完成（DoD：以终为始）

你说“原型完成”时，至少要满足这三类输出。

### 1.1 能跑出核心对比实验（先 RQ1/RQ2/RQ5）

- **RQ1 Governor 的工程价值**：并发 \(N=10/20/50\)
  - 裸跑 vs Governor-only（Budget + RateLimit + Admission）
  - 看：完成率、429/限流错误率、平均 TTFT、总花费、预算耗尽时间

- **RQ2 异构调度收益**：至少 2 个后端（贵强 / 便宜弱）
  - Baseline A：固定贵模型，无预算管理
  - Baseline B：Governor + 单模型（有预算但不做异构选择）
  - Baseline C：逐请求“性价比路由”（近似 RouteLLM/FrugalGPT，不管全局水位/时间）
  - AgentOS：Governor + Scheduler（先做模型选择即可，抢占可后置）
  - 看：同预算下完成更多 or 同任务量更省钱；质量均值+方差；预算利用率

- **RQ5 Zombie 回收效果**：工作负载里注入“卡死/重复/烧钱”
  - 无回收 vs 自动回收
  - 看：吞吐、端到端完成时间、回收次数与原因分布

> RQ3/RQ4（语义存档抢占）先别绑在主线：保留接口与插桩，等 RQ1/2/5 跑通再上。

### 1.2 所有结果都能复现（结构化日志是硬要求）

最少要有这些事件/字段（不求一次完美，但字段要稳定）：

- Turn 生命周期：`created/admitted/queued/dispatched/running/completed/failed/zombie_reaped/(preempted,archived,resumed)`
- 每次后端调用：backend、模型、input/output tokens、美元成本、TTFT、总延迟、错误类型（429/timeout/5xx）
- Governor：预算水位（tighten/loosen 或 delta）、期望 vs 实际、admit/wait/reject 计数
- Scheduler：队列长度、选模决策（为什么选它）、回收/抢占理由

### 1.3 你最终要能怎么跑（一个命令出一份 run）

- `agentos run --workload workloads/mixed.json --policy agentos --out runs/<timestamp>/`
- 输出至少包含：
  - `events.jsonl`
  - `summary.json`

---

## 2. 范围：先把主线跑通（MVP vs 后置）

### 2.1 MVP 必做

- **Gateway 统一入口**：所有 `llm.call()` 都走这里（先只做文本生成即可）。
- **Drivers**：至少两个 driver
  - `MockDriver`（可控延迟/失败/token/质量分）
  - `RealDriver`（任选一个真实后端做 sanity，能返回就行）
- **Governor（工程基线）**：Budget + RateLimit + Admission（带 reservation/结算）
- **Scheduler（研究最小版）**：PriorityQueue（两级）+ ModelSelector（启发式）+ ZombieDetector（两条规则）
- **ExperimentRunner**：读 workload、跑 baseline、汇总指标
  - （Runner=跑实验的小程序；baseline=对照组；汇总指标=把 `events.jsonl` 里的流水账算成表格/数字。）

### 2.2 明确后置（避免项目膨胀）

- 强制隔离（绕过 Gateway 的问题先不解决）
- 工具安全/语义防火墙
- 服务端推理调度（vLLM/KV cache 那套）
- Auto-Prober 全自动探测（先用 `backends.yaml` 手填）
- 语义存档抢占（先留接口 + 日志点）

---

## 3. 代码里要有哪些“基本对象”（别让 AI 写歪）

### 3.1 Turn

Turn 就是一笔 `llm.call()` 交易（排队/等待/重试都算它的一部分）。

最低字段建议：
- `turn_id`, `created_at`
- `priority`: `interactive | batch`
- `task_type`: `codegen | retrieval | reasoning | format | other`
- `resource_spec`
- `state`

### 3.2 ResourceSpec（用于 admission/reservation）

- `max_input_tokens_est`, `max_output_tokens_est`
- `max_cost_usd_est`
- `concurrency_slots`（默认 1）

### 3.3 BackendProfile（先手填 `backends.yaml`）

- `backend_id`
- `price_usd_per_1k_input/output`
- `context_window`
- `rpm_limit`, `tpm_limit`
- （可选）`quality_prior[task_type]`

### 3.4 Ledger/Meter（记账必须真算钱）

- 预算账本（累计、按时间桶）
- 调用计量（tokens/cost/延迟/错误）
- reservation：先预留估算成本，结束再结算差额（不然预算会乱）

---

## 4. 模块怎么拆（接口先定，AI 才好干活）

### 4.1 Gateway（统一入口）

做这几件事就够了：
- 接收 `llm.call(prompt, task_type, priority, hints)`
- 估算 ResourceSpec
- 让 Governor 做 admission + reservation
- 入队 Scheduler 拿到“用哪个 backend”
- 调用 driver，拿到 metering
- 把 metering 回写（账本/统计/后续校准）

### 4.2 Governor（Budget + RateLimit + Admission）

- `BudgetGovernor`：预算水位信号（tighten/loosen）、预留/结算
- `RateLimiter`：按 backend 做 RPM/TPM 窗口
- `AdmissionControl`：不够就 wait/reject（先简单）
  - （RPM/TPM=限流指标；wait=排队等；reject=直接拒绝。）

### 4.3 Scheduler（Queue + Select + Reap）

- `PriorityQueue`：interactive 优先（先两级）
- `ModelSelector`：给 Turn 选 backend（先启发式）
- `ZombieDetector`：先两条（超时/烧钱）
- `Preemption`：接口预留即可（先不启用）

### 4.4 Drivers（统一返回格式）

`BackendDriver.call()` 统一返回：
- `text`
- `input_tokens`, `output_tokens`
- `ttft_ms`, `total_latency_ms`
- `error_type?`

---

## 5. 算法先“能跑 + 可解释”，别上来就最优解

### 5.1 预算水位（最小可用）

- 配置：`budget_total_usd`, `budget_reserve_usd`, `horizon_seconds`
- 期望曲线：线性 \(E(t)\)
- 实际花费：\(A(t)\)
- `delta = A(t) - E(t)`：>0 就 tighten，<0 就 loosen

### 5.2 选模（启发式就够写论文第一版）

核心就是一句话：**优先级越高越愿意花钱，预算越紧越少花钱**。

- `score = w(priority) * q_prior(task_type, backend) / cost_est`
- 约束：预算/速率/上下文窗口不过就行

### 5.3 Zombie（先两条）

- **超时**：`no_progress_for > T`
- **烧钱异常**：`spent_usd(turn) > k * baseline_spent(task_type)`

动作：回收、释放槽位与 reservation、打事件 `zombie_reaped` + `reap_reason`。

---

## 6. 分阶段做（每阶段你怎么验收）

### Phase 0：骨架 + events（当天）

- 做：数据模型 + `events.jsonl` + 最小 CLI
- 你验：跑 3 个 Turn，events 里每个 Turn 至少 `created -> completed`

### Phase 1：MockDriver + RateLimiter

- 做：mock 可控 429/延迟/token；限流窗口
- 你验：20 个并发、RPM=5；有/无限流的 429 数明显差异

### Phase 2：Budget + Admission（RQ1 先能跑）

- 做：预算账本 + reservation + admit/wait/reject
- 你验：预算 \$1、每次 \$0.2；接近耗尽后会 wait/reject；总花费不发散

### Phase 3：PriorityQueue

- 做：interactive 优先 + 并发槽
- 你验：先一堆 batch，再来 1 个 interactive；interactive 明显更快被执行

### Phase 4：ModelSelector + RQ2

- 做：贵/便宜两个 profile；A/B/C/AgentOS 四个 policy
- 你验：同 workload 跑四次；看到“更省/更稳/完成率更高”之一

### Phase 5：ZombieDetector + RQ5

- 做：mock 注入卡死/烧钱；回收协议
- 你验：20% 僵尸；启用回收后吞吐恢复，且原因统计合理

### Phase 6（可选）：语义存档抢占（RQ3/RQ4）

- 做：先用 MockArchive（固定成本+可控有损率）
- 你验：interactive TTFT 下降 + 存档开销/成功率可量化

---

## 7. 已明确的默认选择（无需再拍板）

为避免反复决策拖慢实现，以下选择视为“已定稿”，文档后续按此推进：

- **实现语言与分工**
  - **核心系统（Gateway/Governor/Scheduler/Drivers/Events）用 C++**（常驻、并发、计量与调度逻辑单一实现）
  - **实验与分析用 Python**（读取 `events.jsonl`、计算指标、批量跑 baseline、出图出表）

- **后端策略**
  - **先只用 `MockDriver` 跑通 RQ1/RQ2/RQ5**（保证可控、可复现）
  - `RealDriver` 仅作为后置 sanity（可选接任意一家 API），不影响主线实验

- **质量指标**
  - 第一版统一用 **mock `quality_score`**（使 RQ2 的“质量均值/方差”可稳定复现）
  - LLM-as-judge 作为后置增强，不阻塞主线

- **时间与工作负载**
  - 默认按**实验分钟级 horizon**做模拟（便于快速跑 sweep）
  - workload JSON 至少包含：到达时间 `at_ms`、`priority`、`task_type`、以及 mock 行为（token/延迟/错误/质量）

---

## 8. 下一步怎么用

按 Phase 0→5 顺序实现并验收：每个 Phase 都要能产出一份 `runs/<ts>/events.jsonl` + `summary.json`（其中 `<ts>` 是时间戳占位符），然后再进入下一个 Phase。
