# BudgetFlow 相关工作与差异化备忘录（更新于 2026-05-04）

本文以 `paper1_concept_opus.md` 为准。当前 paper 的核心是提出并验证一个 **agent workflow hard-spend governance** 问题：

> 给定固定 token / dollar 预算，如何在多步 agent workflow 的每一步分配强模型调用，让一批并发 workflow 在同一预算下完成更多可验证任务？

主指标应围绕 **SWE-bench Verified `resolved @ fixed budget`**。系统贡献应围绕 **step-level spend allocation + `budget_pressure` + hard reservation / settlement + multi-workflow runtime governance**。

## 0. 结论先行

最安全、最有贡献感的说法是：

> BudgetFlow formulates and implements hard-spend governance for multi-step LLM agent workflows: a runtime decides where a fixed economic budget should be spent across workflow steps and concurrent tasks, with verified task success as the outcome.

这个 formulation 比“无需训练的 router”更强。`training-free` 是方法特点，不应成为唯一贡献。真正的贡献是把预算、workflow step value、并发 runtime ledger 和可验证任务成功放进同一个问题里。

## 1. 本文的正面问题定义

| 维度 | BudgetFlow 的选择 |
|---|---|
| 资源 | token / dollar spend，外加 provider RPM / 并发槽 |
| 单位 | workflow 中的一次 LLM step |
| 状态 | workflow ledger、全局预算水位、step type、后端配额 |
| 决策 | 当前 step 用便宜模型、强模型、降级、排队、换后端或拒绝 |
| 方法 | training-free `budget_pressure` + step importance $w_i$ + estimated progress / cost |
| hard budget 机制 | `expected_cost` 用于排序，`reserved_cost` 用于准入，`actual_cost` 用于结算 |
| 主指标 | SWE-bench Verified `resolved @ fixed budget`、cost per resolved、budget violation |

一句话版本：

> BudgetFlow spends stronger model calls where they are most likely to change final task success, while a shared ledger keeps the whole batch inside a hard economic budget.

## 2. 哪些论文是真威胁，哪些反而有帮助？

| 类别 | 代表论文 | 对 BudgetFlow 的威胁 | 对 BudgetFlow 的帮助 |
|---|---|---:|---|
| RL agentic routing | Budget-Aware Agentic Routing / BoPO, xRouter | 高 | 证明 step-level agent routing 是真实问题；可作为 future learned selector |
| Per-query / task router | RouteLLM, CARROT, OmniRouter | 中 | 提供 request-level router baseline；可接到 BudgetFlow 的 ModelSelector 里 |
| Serving scheduler | ATHENA-Serve | 中 | 提醒我们别把 scheduler 本身说成新贡献；可作为 backend serving layer 对照 |
| Workflow-aware serving | Aragog, Helium, Autellix | 低到中 | 证明 workflow-aware runtime 很重要；可与 BudgetFlow 叠加 |
| Workflow orchestration | Murakkab | 低到中 | 证明 cloud workflow orchestration 是系统问题；帮助定位 BudgetFlow 的轻量接入层 |
| Programming / semantic serving | Parrot | 低 | 说明 LLM app 有结构化变量和程序语义；帮助解释为什么 step context 有价值 |
| Infrastructure measurement | The Cost of Dynamic Reasoning | 低 | 帮助 motivation：agent test-time scaling 让成本治理成为一等问题 |
| Agent OS / resource isolation | AgentRM, AgentCgroup, AIOS, pMVX | 低 | 支撑“agent runtime 需要资源治理”的大背景 |

## 3. 最接近的竞争者

### 3.1 Budget-Aware Agentic Routing / BoPO

这是最直接的研究邻居，因为它也把 agent 的多步路由看成成本-成功率权衡问题。

| 维度 | BoPO-style work | BudgetFlow |
|---|---|---|
| 路线 | learned routing policy / RL | training-free runtime rule |
| 决策对象 | agent trajectory 中的模型选择 | agent workflow step 的 spend allocation + runtime admission |
| 预算 | 训练和推理中的 budget-aware reward / constraint | 运行时 hard economic budget with reservation |
| 可解释性 | 策略由训练得到 | `budget_pressure`、$w_i$、progress/cost 都可审计 |
| 系统状态 | 主要关注 routing policy | workflow ledger、global budget、backend RPM、concurrency slots |
| 本文处理方式 | 相关工作和 future learned selector | paper 1 主干 |

对本文的调整建议：

- 把贡献写成 **problem formulation + runtime contract**，而不是只写“启发式 router”。
- 实验里必须保留 `Workflow-Level Router`、`Budget-Only Step Router`、`BudgetFlow Full`，用 ablation 证明收益来自 workflow-aware step value 与 hard-spend governance。
- Future work 可以写：BoPO-style learned selector 可以替换 `ModelSelector`，但 ledger、reservation、settlement、governor 仍是 runtime contract。

### 3.2 xRouter

xRouter 属于 RL / tool-calling router 路线。它的威胁在方法论，不在系统层。BudgetFlow 的防线是 fixed economic budget、SWE-bench verified outcome、multi-workflow ledger 和 training-free deployability。

## 4. ATHENA-Serve：重点相关，但放在 Related Work

ATHENA-Serve 值得认真写，并适合放在 related work 中处理。

| 维度 | ATHENA-Serve | BudgetFlow |
|---|---|---|
| 核心问题 | LLM serving under bursty traffic | Agent workflow hard-spend governance |
| budget 含义 | KV-cache / compute / concurrency resource envelope | token / dollar spend cap |
| 目标 | tail latency、SLO violation、HoL blocking | verified task success under fixed spend |
| 方法 | horizon-cost prediction + hierarchical RL scheduling | training-free `budget_pressure` + workflow ledger |
| workload | ShareGPT-like online serving traces（需以原文确认） | SWE-bench Verified coding workflows |
| 对本文角色 | serving-layer related work / reviewer warning | paper 1 主线 |

ATHENA 给本文的最大提醒：

- 运行时 scheduler、admission、concurrency control 已经是活跃系统方向。
- 本文应把 Governor / Scheduler 写成 hard-spend runtime 的必要支撑，把主要新意放在 agent workflow spending formulation 上。
- ATHENA 的评审意见说明：如果引入 RL，审稿人会问 RL 是否必要；BudgetFlow 选择 training-free，可以把这点转化为清晰优势。

可写进 related work 的一句话：

> ATHENA-Serve maps predicted generation horizons to KV/compute budgets and schedules requests for tail-latency control. BudgetFlow uses budget as an economic spend cap over agent workflows; it decides which workflow steps deserve stronger model calls to improve verified task success under fixed spend. These layers are complementary: an ATHENA-like scheduler can execute admitted requests below a BudgetFlow-style spend governor.

## 5. Scratch.md 七篇论文：解决的问题、与 BudgetFlow 的关联（含链接）

下面与 `paper1/scratch.md` 417–479 行对齐。每行先写该文正面要解决的问题，再写 BudgetFlow 如何把它放进 related work 或 motivation。

| 论文 | 链接 | 它正面解决的问题 | 与 BudgetFlow 的关联 |
|---|---|---|---|
| The Cost of Dynamic Reasoning | [arXiv:2506.04301](https://arxiv.org/abs/2506.04301) | 系统级刻画 agent 多轮推理与 test-time scaling 的资源、延迟、能耗与数据中心功耗，并分析设计选择对 accuracy–cost 的影响 | 给 BudgetFlow 的 motivation：agent workflow 的成本与收益曲线值得系统研究；BudgetFlow 给出固定经济预算下的运行时 spend governance 与 SWE-bench `resolved` 证据 |
| Parrot | [arXiv:2405.19888](https://arxiv.org/abs/2405.19888) | 让 public LLM service 看到 application-level 结构（Semantic Variable），做跨请求数据流分析与端到端优化 | 支撑 BudgetFlow 的输入信号设计：step / tool / observation 的结构化上下文可以进入预算决策；BudgetFlow 仍聚焦 hard-spend ledger 与 `resolved @ fixed budget` |
| Aragog | [arXiv:2511.20975v1](https://arxiv.org/abs/2511.20975v1) | agentic workflow 在 scale 下很贵；在运行期根据系统观测做 just-in-time configuration，提高吞吐、降低延迟，同时保持与最贵配置相当的 accuracy | 最接近的 serving-side 邻居：共享“workflow 运行期再决策”；BudgetFlow 的主轴是 **固定 dollar/token 预算** 下的 step spend 与 verified task success，可把 Aragog 写成 backend routing 层对照 |
| Murakkab | [arXiv:2508.18298](https://arxiv.org/abs/2508.18298) | 用 declarative 抽象解耦 workflow 与执行配置，跨层优化 accuracy、latency、energy、cost 以满足 SLO | 支撑“workflow 结构应进入系统层”的大趋势；BudgetFlow 取更窄接口：接在 LLM 调用层做 hard-spend governance，把 full-stack orchestration 留给 Murakkab 类系统 |
| Autellix | [arXiv:2502.13965](https://arxiv.org/abs/2502.13965) | 把 agent 程序当作 first-class，利用 program 与 call 依赖减少 HoL、降低程序端到端延迟 | 支撑 stacking story：Autellix 优化程序级执行效率；BudgetFlow 优化 **在固定预算下** 的程序成功率；可画成 BudgetFlow → Autellix → vLLM 类栈 |
| ATHENA-Serve | [OpenReview](https://openreview.net/forum?id=GULnhNbvb9) | 把预测 horizon 映射为 KV/compute budget，用 hierarchical RL 调度 admission/batching/concurrency，控制 bursty 负载下的尾延迟与 HoL | related work 中的 serving scheduler 参照；提醒 BudgetFlow 的主贡献应是 agent hard-spend formulation，Governor/Scheduler 为支撑层 |
| Helium（论文题目在 arXiv 上为 Efficient LLM Serving for Agentic Workflows） | [arXiv:2603.16104v1](https://arxiv.org/abs/2603.16104v1) | 把 agentic workflow 建成 query plan，跨调用做 cache-aware scheduling 与重用 | 支撑 workflow-aware serving 的必要性；BudgetFlow 侧重点是 **经济预算与 step value**，缓存与算子级优化可作为 future work 或 backend 协同 |

## 6. 新增论文：保留、弱化、借力（展开说明）

### The Cost of Dynamic Reasoning

关系：有帮助的 motivation paper。

它强调 agent / test-time scaling 会带来真实基础设施成本。本文可以借它说明：agent reasoning 的成本治理已经成为系统问题。它通常不直接给出 step-level hard-spend allocation runtime，因此威胁较低。

### Parrot

关系：有帮助的 programming/serving paper。

Parrot 的 semantic variable 说明 LLM application 不是孤立 prompt，而是有程序结构和变量依赖。BudgetFlow 可以借这个思想解释：workflow step、tool observation、traceback、patch state 这些结构化上下文应进入预算决策。它对本文的威胁低，因为它主要优化 serving / application execution efficiency，而不是 fixed spend 下的 verified task success。

### Aragog

关系：有帮助，也需要认真定位。

Aragog 的 just-in-time model routing for agentic workflows 与 BudgetFlow 共享“agent workflow 运行时做模型选择”的直觉。它可能是新增论文里最像 BudgetFlow 的系统之一。

本文的定位应是：

- Aragog 更像 serving/runtime layer 的 just-in-time routing；
- BudgetFlow 的中心是 hard economic budget、step value、ledger reservation 和 `resolved @ fixed budget`；
- Aragog 若采用规则式或硬编码策略，反而支持本文的 training-free 路线：系统论文可以用可解释 runtime policy，而不必把 RL 放进 paper 1 主干。

需要确认的事实：venue、benchmark、headline gain、是否真的优化 fixed spend。

### Murakkab

关系：有帮助的 workflow orchestration paper。

Murakkab 说明 cloud platform 里的 agentic workflow orchestration 可以带来资源效率提升。它对本文有帮助，因为它证明 workflow 结构进入系统层是顶会/系统社区关心的问题。

本文应避免和它抢“workflow orchestration platform”这个大目标。BudgetFlow 的 paper 1 更窄：在现有 agent loop 和 LLM backend 之间做 hard-spend governance。

需要确认的事实：venue、数据集、提升数字、是否有 cost under SLO 目标。

### Autellix

关系：有帮助的 serving engine paper。

Autellix 把 LLM agents 当作 general programs 来服务，说明 agent execution 已经需要 program-aware serving engine。BudgetFlow 可以放在它上层：BudgetFlow 决定每个 step 的 spend / model / admission，Autellix 类 engine 负责高效执行程序化 agent 请求。

威胁点：如果 Autellix 也做 workflow-aware routing，需要在 related work 中说明它优化的是 engine efficiency / HoL / throughput，而 BudgetFlow 的主指标是 task success under fixed spend。

### Helium

关系：有帮助的 workflow-aware serving paper。

Helium 证明 workflow-aware serving 是合理方向。本文可以借它强化“workflow state matters”这个大前提。它的威胁取决于是否包含 hard economic budget 和 task-success objective；如果主要优化 serving efficiency，则属于可叠加 backend layer。

### ATHENA-Serve

关系：重要相关工作 + 审稿风险提醒。

ATHENA 说明 resource budget / horizon prediction / hierarchical RL scheduler 已经被认真研究。本文应吸收它的审稿教训：报告 p99 / violation / overhead，加入强 heuristic baseline，清楚解释 training-free policy 的价值。

它强化了 BudgetFlow 的 positive framing：BudgetFlow 的问题是 agent workflow spend allocation。

## 7. 旧表中的论文如何处理

| 论文 | 是否保留 | 位置 | 理由 |
|---|---|---|---|
| RouteLLM | 保留 | per-query router baseline | 强/弱模型 routing 的经典背景 |
| CARROT | 保留 | per-query cost-aware router | cost-aware 但通常不是 workflow ledger |
| OmniRouter | 保留 | constrained per-query / global routing | 可作为优化视角 baseline |
| Budget-Aware Agentic Routing / BoPO | 强保留 | closest competitor | multi-step + cost/success + RL |
| xRouter | 保留 | RL routing related work | 方法论邻居 |
| AgentRM | 弱保留 | runtime governance background | 资源稳定性，不是 spend allocation 主线 |
| AgentCgroup | 弱保留 | OS/resource isolation background | OS 隔离背景 |
| AIOS | 弱保留 | broad agent OS background | 概念背景，少写 |
| pMVX | 弱保留 | agent OS self-tuning background | 平行工作，少写 |

## 8. RL / ML 使用情况

| 论文类别 | 使用 RL/ML | 本文策略 |
|---|---|---|
| BoPO / xRouter | 是，核心方法 | 放 closest related work；future learned selector |
| ATHENA-Serve | 是，hierarchical RL + predictor | 放 serving related work；吸收评审教训 |
| RouteLLM / OmniRouter / CARROT | 多数使用学习器或统计预测 | 作为 per-query baseline 或组件 |
| Aragog / Murakkab / Autellix / Helium | 需按原文确认，可能包含规则、优化或学习组件 | 作为系统层对照，不把 ML 与否作为唯一差异 |
| BudgetFlow paper 1 | 主干 training-free | 把 learned selector 写进 future work / pluggable extension |

本文可以明确写：

> BudgetFlow's ModelSelector is a plug point. Paper 1 uses a training-free auditable rule to isolate the value of the runtime formulation. A learned selector can replace this rule later, while the ledger, reservation, settlement, and governor remain the same runtime contract.

## 9. 顶会化建议

顶会审稿人更可能接受的问题定义：

> We identify hard-spend governance for agent workflows as a systems problem: model routing, budget accounting, and backend admission must be decided together when many agent workflows share a fixed economic budget.

需要补强的实验：

1. **Fixed-budget curves**：不同总预算下的 `resolved`、cost per resolved、budget violation。
2. **Ablation**：Workflow-Level Router、Budget-Only Step Router、BudgetFlow Full。
3. **Runtime stress**：并发数 `J = 1 / 10 / 50 / 100`，报告 429 rate、queue latency、recovered budget。
4. **Heuristic strength**：给 Budget-Only 和 Workflow-Level baseline 足够强的调参，避免被审稿人说 strawman。
5. **Overhead**：BudgetFlow 的 routing / accounting / scheduling overhead。
6. **Generalization note**：主实验在 SWE-bench，其他领域需要新的 progress signal；论文主张可复用的是 ledger + hard reservation + step-value formulation。

## 10. 最终定位

本文的 niche 应写成：

> BudgetFlow is a training-free runtime for hard economic budget governance in multi-step LLM agent workflows. It allocates stronger model calls across workflow steps and concurrent tasks using auditable step-value signals, while a shared ledger enforces reservation, settlement, and backend quotas. The paper evaluates whether this formulation improves verified task success under fixed spend.
