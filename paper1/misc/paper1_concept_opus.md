# Spend Tokens Where They Matter: Workflow-Aware Budgeting for LLM Agents

> **一句话**：在固定 token / dollar 预算下，BudgetFlow 把强模型留给 agent workflow 中真正关键的步骤，并在多 workflow 并发时守住全局预算、后端 RPM 和并发槽。

---

## 0. 这篇论文到底解决什么问题？

今天的 LLM agent 通常由多次模型调用组成。以 SWE-bench 为例，一个 coding agent 会读 issue、找文件、看代码、写 patch、跑测试、再根据失败日志继续修。每一步都要花 token，但每一步的价值不一样：目录浏览错了通常能恢复，测试失败后的 root-cause 判断错了可能直接毁掉整条轨迹。

本文把这个现象形式化成一个 **agent workflow hard-spend governance** 问题：

> **给定固定 token / dollar 预算，如何在 agent workflow 的每一步分配强模型调用，让一批并发 workflow 在同一预算下完成更多可验证任务？**

这个问题有三个关键要素：

1. **固定经济预算**：总 token / dollar 上限先给定，系统要在运行时守住这个 hard cap。
2. **多步 workflow 价值差异**：同样一美元，花在目录浏览、代码理解、traceback 分析、patch 修复上的边际价值不同。
3. **多 workflow 共享运行时**：许多任务同时运行，共享预算池、provider RPM、并发槽和后端模型池。

因此，本文的核心优化单位是完整 agent workflow 及其 step 序列。一次 LLM call 的模型选择仍然重要，但 BudgetFlow 关心的是这些调用在整条轨迹和整批任务里的预算位置：当前 step 值不值得升级、本 workflow 已花多少、全局预算还剩多少、后端配额是否紧张，以及这个选择是否能提高 fixed-budget 下的最终 `resolved` 数。

我们提出 **BudgetFlow**：一个 training-free 的 workflow-aware budgeting runtime。它接在 LLM 调用层，维护预算账本、后端限流和步骤重要性信号，并通过 proxy、adapter 或 SDK 接入 LangChain / SWE-agent / AutoGen 等现有 agent loop。

BudgetFlow 的核心贡献是：

1. **A hard-spend formulation for agent workflows**：把 agent 的质量-成本问题定义为 fixed budget 下的 step-level spend allocation，而主指标是可验证任务成功数。
2. **Training-free hard-cap adaptation**：不同预算上限下，用运行时的 `budget_pressure` 调整模型升级门槛。预算紧时少升档，预算松时关键步骤更容易升档。
3. **Auditable cost accounting**：区分 `expected_cost`、`reserved_cost` 和 `actual_cost`，用预留成本守住 hard budget，用真实成本做实验报告。
4. **Multi-workflow runtime governance**：多个 workflow 共享一个总预算、provider RPM 和并发槽时，BudgetFlow 对每次 LLM call 做准入、排队、降级、换后端或拒绝，并回收卡死 workflow 的预算和槽位。

---

## 1. 核心洞察：按 step 花预算

一个 workflow 开始时，我们只知道 issue 和初始上下文。真正关键的信息往往在后面才出现：搜索结果、源码片段、测试失败、traceback、patch apply error。只在 workflow 开头选一次模型，会错过这些中途信号。

BudgetFlow 的基本判断是：

> **同样一美元，花在不同 step 上的价值不同。**

例如：

| 当前 LLM 输入 | 直觉 | 默认重要性 |
|---|---|---|
| 目录列表、文件树 | 低风险导航，错了容易恢复 | 低 |
| 搜索结果、源码片段 | 需要理解代码，影响后续编辑 | 中 |
| 测试失败、traceback | 直接影响 root cause 判断 | 高 |
| patch 已生成后的简单验证 | 多为收尾或检查 | 低到中 |

BudgetFlow 把这些权重定义为粗粒度预算分配信号，并通过对照实验验证：同时使用预算水位和 step 重要性，是否能比只看预算水位解出更多任务。

---

## 2. BudgetFlow 放在哪里？

BudgetFlow 位于 agent 框架和 LLM 后端之间。

```text
+----------------------------------+       +-----------------------------+
| LangChain / SWE-agent / AutoGen  |       | Self-built agent platform   |
+----------------------------------+       +-----------------------------+
      |                    |                         |
      | Proxy mode:        | Callback mode:          | SDK mode:
      | LLM request msgs   | tool events + metadata  | task_type + w_i
      v                    v                         v
+------------------+ +------------------+      +------------------+
| BudgetFlow Proxy | | BudgetFlow Adapter|     | BudgetFlow SDK   |
+------------------+ +------------------+      +------------------+
         \                  |                         /
          \                 |                        /
           +----------------+-----------------------+
                            |
                            v
                   +--------------------+
                   | BudgetFlow Runtime |
                   +--------------------+
                            |
                            v
         +-------------------------------------+
         | Governor: budget + backend quotas  |
         +-------------------------------------+
                            |
                            v
      +------------------------------------------+
      | ModelSelector: budget_pressure + w_i     |
      +------------------------------------------+
                            |
                            v
         +-----------------------------+
         | Multi-workflow Scheduler    |
         +-----------------------------+
                            |
                            v
         +-----------------------------+
         | LLM Backend Pool            |
         +-----------------------------+
```

它可以三种方式接入：

- **Proxy mode**：agent 只把 OpenAI-compatible `base_url` 指向 BudgetFlow。BudgetFlow 从 `messages`、ToolMessage、Observation 文本里推断当前 step 类型。
- **Callback / adapter mode**：LangChain、SWE-agent、AutoGen 通过 hook 提供 tool name、tool output、step index 等结构化信号。
- **SDK mode**：自研平台显式传入 `task_type`、`w_i`、`workflow_id`。

BudgetFlow 的论文范围是 LLM-call governance：选模型、守预算、限流、排队、记账、回收卡死 workflow。它作为 agent framework 和 LLM backend 之间的预算运行时，可以接入现有 LangChain / SWE-agent / AutoGen，也可以作为自研 agent 平台的 SDK 层。

这里的 **workflow-aware** 指路由决策会使用 workflow 级状态：全局预算池还剩多少、本 workflow 已经花了多少和预留了多少、当前 `budget_pressure` 有多高、各后端 RPM / 并发槽是否紧张，以及当前调用是否处在关键上下文中。相对地，**workflow-blind** router 主要依赖本次 prompt、token 数、模型成本、延迟等局部信息；它可能是很好的单次请求 router，但没有 ledger 和跨 workflow 调度状态，就很难做跨步骤预算配速。

---

## 3. 运行时决策：这一步值不值得升档？

对一次 LLM call，BudgetFlow 先从便宜模型开始，逐档判断是否值得升级到更强模型。

人话版规则：

```text
如果：步骤重要性 × 预计进展增益 ÷ 额外成本 >= 当前预算门槛
那么：升到更强模型
否则：停在当前模型
```

数学写法：

$$
w_i \cdot
\frac{\Delta \widehat{\text{progress}}_i}
     {\Delta \widehat{\text{cost}}_i}
\ge \text{budget\_pressure}_t
$$

几个量的含义：

| 量 | 含义 |
|---|---|
| $w_i$ | 当前 step 有多关键，例如 traceback 分析高于目录浏览 |
| $\Delta \widehat{\text{progress}}_i$ | 升级模型后，预计多带来多少可验证进展 |
| $\Delta \widehat{\text{cost}}_i$ | 升级模型预计多花多少钱 |
| `budget_pressure` | 当前预算门槛；预算紧时升高，预算松时降低 |

`budget_pressure` 不需要预测未来。它只做闭环反馈：

| 观测状态 | 调整 |
|---|---|
| 花钱速度快于任务进度 | 提高门槛，减少升档 |
| 花钱速度慢于任务进度 | 降低门槛，让关键步骤更容易升档 |
| 后端 RPM / 并发槽紧张 | 提高门槛或排队、换后端 |
| workflow 卡死或循环 | 取消并回收预算和槽位 |

注意：BudgetFlow 在调用前不知道真实输出 token 数，只能估计。它用估计成本做排序，用预留成本守预算，用真实账单做实验评估。

一个简单例子：当前是测试失败后的 debugging step，默认 $w_i=3$。如果从 mini 升到 Sonnet 预计多带来 0.12 的 step progress，额外花费 \$0.04，那么升级分数是 $3 \times 0.12 / 0.04 = 9$；若当前 `budget_pressure=4`，这一步值得升级。若同样的进展增益发生在目录浏览 step，$w_i=1$，分数变成 3，系统会留在便宜模型。这个例子体现了 BudgetFlow 的核心原则：强模型预算优先流向更接近最终修复决策的步骤。

---

## 4. 成本怎么记？

成本分三种，不能混用。

### 4.1 `expected_cost`：决策前估计

调用前可以准确知道输入 token 数，但不知道输出 token 数，所以输出只能按历史均值或滚动均值估计。

$$
\text{expected\_cost}
= \text{input\_tokens} \cdot p_{\text{in}}
+ \widehat{\text{output\_tokens}} \cdot p_{\text{out}}
$$

它只用于比较“升一档是否划算”。

### 4.2 `reserved_cost`：调用前预留

如果要声称 hard budget，就不能靠平均输出长度。BudgetFlow 在发起调用前按可控上界预留预算：

$$
\text{reserved\_cost}
= \text{input\_tokens} \cdot p_{\text{in}}
+ \text{max\_output\_tokens} \cdot p_{\text{out}}
$$

若剩余预算无法覆盖预留成本，系统只能降级模型、降低输出上限、排队或拒绝。

### 4.3 `actual_cost`：调用后结算

调用结束后，用 provider 或本地 serving 日志返回的真实 token 数结算：

$$
\text{actual\_cost}
= \text{actual\_input\_tokens} \cdot p_{\text{in}}
+ \text{actual\_output\_tokens} \cdot p_{\text{out}}
$$

如果 `actual_cost < reserved_cost`，差额退回全局预算池。并发场景下，预留和退回必须是原子操作，避免 50 个 workflow 同时读取同一个剩余预算而超支。

---

## 5. 质量怎么衡量？

### 5.1 先解释一下 SWE-bench Verified 是什么

SWE-bench 是一个 coding agent 评测基准：从 Django、scikit-learn、sympy 这样的真实开源 Python 项目里，挑出已经被人类修复过的 bug。每个任务给 agent 一份 GitHub issue 的描述和对应的代码仓库快照，要求 agent 自己定位问题、改代码、产出一个 patch。

**SWE-bench Verified** 是 OpenAI 在 2024 年发布的人工筛选子集，共 500 个任务，去掉了原始 SWE-bench 中描述模糊或测试不可靠的样本，是目前 coding agent 论文最常用的主指标来源。

每个任务自带一份 ground truth 信息：

- **gold patch**：人类开发者当年的真实修复 diff；
- **`FAIL_TO_PASS` 测试**：在 bug 被修之前会失败、修好之后必须通过的测试。这是判断「bug 是否真的修好了」的硬指标；
- **`PASS_TO_PASS` 测试**：在 bug 修复前后都应该通过的测试，用来检查 agent 没有把别的功能改坏。

### 5.2 论文的主指标：`resolved`

本文不发明任何主观质量分。主指标就是 SWE-bench Verified 官方 harness 输出的 `resolved` 布尔值。

一个任务被判定为 resolved，需要同时满足：

1. agent 产出了一个非空 patch；
2. 这个 patch 能在原仓库上 `git apply` 成功；
3. apply 之后，所有 `FAIL_TO_PASS` 测试通过；
4. apply 之后，所有 `PASS_TO_PASS` 测试仍然通过。

举个具体例子。`django__django-11099` 这个任务的 issue 是「`UsernameValidator` 允许用户名末尾是换行符」。agent 需要：

- 找到 `django/contrib/auth/validators.py`；
- 把正则里的 `$` 改成 `\Z`，避免末尾换行被当成匹配结束；
- 提交 patch。

harness 会跑这个任务对应的 `FAIL_TO_PASS` 测试（一个专门检查「带换行符的用户名应该被拒绝」的测试），通过即 resolved=True，否则 resolved=False。注意：agent 用什么模型、走多少步、花多少钱，harness 完全不看，只看最终 patch 的行为。

论文层面的胜利标准就只有一句话：

> 在同样总预算下，BudgetFlow 比对照组让多少个 SWE-bench Verified 任务被判 resolved。

### 5.3 Step-level progress：只给 runtime 用，不算胜利标准

第 3 节里的 $\Delta \widehat{\text{progress}}_i$ 需要一个「这一步有没有让任务往前推进」的代理信号。

| 信号 | 怎么计算 | 用途 |
|---|---|---|
| 是否打开了 gold patch 涉及的文件 | 拿 agent 当前轨迹里访问过的文件路径，和 gold patch 的 changed files 对比 | localization / search 阶段 |
| patch 是否能 `git apply` | 在沙箱里 dry-run 一下 | repair / generation 阶段 |
| 失败测试数是否减少 | 跑一个轻量子集（如只跑 `FAIL_TO_PASS`），统计通过数变化 | validation / debugging 阶段 |
| `.traj` 文件里的 thought/action/observation | SWE-agent 默认会把每一步的思考、调用的工具、工具返回写进 `<task_id>.traj` 这个 JSON 文件，方便事后把成本、决策和结果对齐 | 调试和分析 |

这些信号只用于：(a) runtime 决策时估计「升档值不值」；(b) 写 paper 时做 case study 解释 BudgetFlow 在哪一类 step 上多花了钱。**它们不进入主结果表**，主结果表只看 `resolved`。

### 5.4 为什么要 held-out calibration split？

这里要避免一个隐蔽的循环论证。

第 1 节给了一张「step 重要性」表（traceback 高于目录浏览之类）。这些权重 $w_i$ 不是天上掉下来的，多少需要根据数据调一调，比如：「在 traceback 那一步用 GPT-4 升档到底比用 Haiku 多解出几个任务？」如果回答是 8 个，那权重就调高一点；如果只是 1 个，就调低一点。

问题来了：**如果用 SWE-bench Verified 的全部 500 个任务来调 $w_i$，再用同一批 500 个任务报告 resolved rate，等于用考试答案训练，再用同一份卷子测分。** 任何看起来的提升都可能只是过拟合。

解决办法是把数据切成两半：

- **Calibration split**（校准集）：用来调权重。可以是 SWE-bench Verified 之外的数据，例如原始 SWE-bench 中没有进入 Verified 的样本，或 SWE-bench Lite 中和 Verified 不重叠的部分。在这一半上反复试不同的 $w_i$、不同的 progress 信号阈值，找一组合理参数。
- **Evaluation split**（评测集）：完整的 SWE-bench Verified 500 题，**调参阶段一次都不许碰**。最终 paper 里的 resolved rate、cost per resolved 全部在这一半上报告。

「held-out」就是「保留、不碰」的意思——把 evaluation split 锁起来，等所有设计决策定下来再开盒。

如果某个版本的 BudgetFlow 完全不需要调参（比如 $w_i$ 全部用一个固定的 default 表，从头到尾不改），那严格来说不需要 calibration split。但本文为了诚实，假设权重总要调一点，所以预先声明这个 split 协议。

---

## 6. 三个主系统对照

### 6.1 Workflow-Level Router

在 workflow 开始时，根据初始 issue / prompt / repository context 选一个模型或 routing profile，后续整条 workflow 都按这个选择走。

它回答：

> 只在任务开始时做一次模型选择，够不够？

这是最关键的对照，因为现实里很多 routing 系统本质上是 request-level 或 task-level 的。

### 6.2 Budget-Only Step Router

它也按 step 决策，也守预算，但不看 step 重要性，不看 observation 类型。

它只看：

- `spent_budget / total_budget`
- `completed_tasks / total_tasks` 或当前批量进度
- 当前 call 的 `expected_cost` / `reserved_cost`

等价于从 BudgetFlow 公式里去掉 $w_i$ 和 observation-aware signals：

```text
只看预算水位和本次调用成本，不看这一步是不是关键。
```

它回答：

> 收益是不是只来自预算配速？还是确实需要知道哪些 step 更值得花钱？

### 6.3 BudgetFlow Full

完整系统包括：

- per-step routing；
- `budget_pressure`；
- step importance $w_i$；
- observation-aware signals；
- workflow ledger；
- hard-budget reservation；
- backend admission control；
- zombie recovery。

它回答：

> 在同样总预算下，workflow-aware step-level budgeting 是否比 workflow-level routing 和 budget-only step routing 解出更多 SWE-bench 任务？

---

## 7. Multi-workflow runtime

本文的主场景是批量 SWE-bench 评估：

> 50 个 SWE-agent 并发跑 SWE-bench Verified，共享一个总预算，例如 \$50，同时受到 provider RPM 和并发槽限制。

目标用户是造 agent 的人和运营 agent 平台的团队：开源 agent 框架维护者、自研 agent 产品团队、单团队内部 LLM 网关运营方，以及需要可复现实验 harness 的研究者。本文聚焦“单一预算主体 + 多并发 workflow”的情形；多团队、多 SLA、多预算池之间的 quota 仲裁放到 future work。

BudgetFlow 在这个设定下处理每次 LLM call 到来时的五个运行时问题：

1. 当前全局预算是否还能覆盖本次调用？
2. 当前 step 值不值得升档？
3. 目标后端是否还有 RPM / 并发槽？
4. 如果没有槽，是排队、降级、换后端，还是拒绝？
5. 如果 workflow 卡死，如何释放预留预算和并发槽？

这种 runtime governance 把 step-level spend decision 放进可执行的系统环境里：预算预留要原子化，调用完成要结算退款，后端配额要被遵守，卡死 workflow 要释放资源。它支撑本文的 hard-spend formulation，并把论文主线稳定在 agent workflow budget governance 上。

BudgetFlow 的关键组件：

| 组件 | 作用 |
|---|---|
| Ledger | 记录每个 workflow 的预留、实际花费和状态 |
| Governor | 原子预算预留、结算、后端限流 |
| ModelSelector | 根据 step 重要性、预计收益和预算压力选模型 |
| Scheduler | 在后端 RPM / 并发槽下准入、排队、降级或换后端 |
| ZombieDetector | 取消无进展 workflow，回收预算和槽位 |

---

## 8. 实验设计

### 8.1 Workload

- Benchmark：SWE-bench Verified；
- Agent scaffold：SWE-agent 或 mini-SWE-agent，全文固定一种；
- 并发规模：`J = 1 / 10 / 50 / 100`；
- 总预算：例如 `B_total = $50`，并报告不同预算下曲线；
- 后端池：可包含 API 模型和本地模型，但主张不依赖具体模型名。

### 8.2 RQ

| RQ | 问题 | 指标 |
|---|---|---|
| RQ1 | BudgetFlow 能否守住 hard budget 和后端 RPM / 并发限制？ | budget violation、429 rate、queue latency |
| RQ2 | Step-level routing 是否优于 workflow-level routing？ | resolved rate、cost per resolved |
| RQ3 | Step importance 是否优于只看预算水位？ | BudgetFlow Full vs Budget-Only Step Router |
| RQ4 | 多 workflow 并发下，ledger / admission / zombie recovery 是否减少资源浪费？ | recovered budget、cancelled zombie、p99 latency |

### 8.3 主指标

| 指标 | 含义 |
|---|---|
| Resolved rate @ fixed budget | 同样预算下解决多少 SWE-bench 任务 |
| Cost per resolved | 每解决一个任务花多少钱 |
| Budget violation rate | 是否超出 hard budget |
| 429 rate | 是否打爆 provider RPM |
| p50/p99 queue latency | 排队延迟 |
| Recovered budget | 从卡死 workflow 退回的预算 |

---

## 9. Related Work

### Per-query / task-level routing

RouteLLM、CARROT、OmniRouter、LiteLLM auto-router 等工作主要优化单次请求或任务开始时的模型选择。它们可以是很强的工程工具，但通常不维护 workflow ledger，也不利用中途 observation 判断当前 step 是否关键。

本文的对照问题是：

> 在 SWE-bench 这种多步 agent workflow 里，只做 workflow-level routing 是否足够？

### Budget-Aware Agentic Routing / BoPO

BoPO 说明了一件重要事实：长程 agent 的 step-level model routing 是一个真实研究问题。它用强化学习训练 learned router，在 ALFWorld、SciWorld、AppWorld 上研究成本和成功率的权衡。

本文把 BoPO 作为 closely related work 和 future learned selector 方向。由于 benchmark、模型池、agent scaffold 和训练流程差异较大，SWE-bench 主实验优先使用可复现的 workflow-level、budget-only 和 BudgetFlow full 对照。本文研究的是另一条路线：

> 在 SWE-bench-style coding workflow 上构建一个 training-free 的 budgeting runtime，并研究多 workflow 共享预算和后端资源时的系统行为。

一句话说，BoPO learns an implicit routing policy；BudgetFlow exposes an auditable runtime decision rule。未来可以把 BoPO-style learned selector 接到 BudgetFlow 的 ModelSelector 位置，用学习策略替换本文的启发式策略，同时沿用 ledger、hard-budget reservation、backend governor 和 multi-workflow scheduler。

### LLM serving and workflow orchestration

ATHENA-Serve、Parrot、Aragog、Murakkab、Autellix、Helium 等工作对 BudgetFlow 很有帮助，因为它们说明 agentic LLM workloads 已经变成真实的 serving / orchestration 问题：请求有不同长度、workflow 有不同阶段、后端有 KV cache、batching、concurrency、RPM、SLO 和 tail-latency 压力。

这些系统主要给 BudgetFlow 提供两类启发：

1. **Serving layer can be smarter**：ATHENA-Serve 把 generation horizon 映射成 KV / compute budget，并用 hierarchical RL 做 admission、batching 和 concurrency control。Autellix、Helium 等也强调 workflow-aware serving 能减少 head-of-line blocking、提升吞吐和尾延迟。
2. **Runtime layer should expose structure**：Parrot 的 semantic variable、Aragog 的 just-in-time routing、Murakkab 的 workflow orchestration 都说明，agent workflow 的结构信息可以进入运行时决策，让每个 prompt 带着 step context 和 workflow state 进入系统层。

BudgetFlow 使用这些结论作为系统背景：agent runtime 需要理解 workflow，后端调度也会影响最终成本和延迟。本文的研究问题放在另一层：给定一个固定经济预算，如何把强模型调用分配到更能提升最终任务成功率的 workflow steps。一个实际部署可以把 BudgetFlow 放在 agent framework 和 serving engine 之间：BudgetFlow 决定这一步值得花多少钱、用哪个模型或后端；ATHENA / Autellix / Helium 类 serving 系统负责把已准入请求更高效地跑完。

### Agent runtime / resource governance

AgentRM、AgentCgroup、AIOS 等工作关注 agent 系统的资源管理、隔离或稳定性。BudgetFlow 的范围更窄：它只治理 LLM 调用预算，但把质量目标、预算账本和后端配额放在同一个可实验的 runtime 里。

---

## 10. Threats to Validity

### SWE-bench scope

本文只声称适用于有可验证中间信号的 coding-agent workflow。客服、创意写作、科学推理等任务没有 gold patch 和确定性测试，需要新的 progress signal 或 evaluator。

### Step importance 的粗糙性

$w_i$ 只是粗粒度预算信号，不是真实人类效用。必须通过 Budget-Only Step Router 对照验证：去掉 $w_i$ 后，性能是否下降。

### 预计成本不等于真实成本

调用前不知道输出 token 数，所以 BudgetFlow 只能用 `expected_cost` 排序，用 `reserved_cost` 守预算，最后用 `actual_cost` 报告实验结果。

### KV / prompt caching

云 API 通常不暴露原始 KV cache。连续使用同一模型可能享受 provider-side prompt caching 或 prefix caching，而频繁切模型可能失去这部分收益。跨模型 KV/cache 成本很难干净量化，因为 tokenizer、架构、输出长度和计费规则都不同。本文把它作为 threat / future work，不在主实验里人为加入 synthetic switching penalty。

---

## 11. Future Work

### Learned selector

一个自然扩展是把 BudgetFlow 的启发式 ModelSelector 换成学习型 selector，例如借鉴 BoPO-style boundary-guided training。本文先证明 runtime 问题本身：workflow ledger、hard-budget reservation、backend admission 和 zombie recovery 是否能改变固定预算下的 SWE-bench 结果。

### Multi-tenant resource allocation

本文只处理单一预算主体：一个研究者或一个团队持有总预算，运行多个 workflow。多团队、多 SLA、多优先级的 quota 仲裁是下一步问题。

这条路线类似很多 systems 工作的演进方式：先在 single-tenant 设定下把核心机制做清楚，再叠加多租户政策层。BudgetFlow 的第一步是证明 workflow ledger、预算预留和后端调度能否改变固定预算下的质量；multi-tenant agent compute allocation 可以在这个基础上继续研究。

### Agent-native loop

本文把 BudgetFlow 放在现有 agent 框架和 LLM 后端之间，优先证明 hard-spend workflow governance 的价值。后续可以提供 BudgetFlow-native agent loop，把 tool execution、observation、ledger、ModelSelector 和 scheduler 做成统一 runtime，降低接入成本；paper 1 的主线仍然是预算 formulation 和 runtime contract。

### Cache-aware routing

如果 provider 或本地 serving 暴露 cached-token / prefix-cache 信息，BudgetFlow 可以把 cache locality 纳入 `actual_cost` 或 future selector。本文不假设能直接操控 KV cache。

### Non-coding workflows

客服、RAG、科学推理等任务可以复用 ledger、reservation 和 scheduler，但需要新的 step progress signal。没有可靠 evaluator 时，不应直接套用 SWE-bench 的 progress table。

交互式 workload 还会引入 deadline、SLA tier、latency 和 throughput 目标。本文主实验先聚焦批量 SWE-bench 式 workload：固定预算下最大化最终 resolved rate；interactive / SLA 约束是自然扩展，不偷偷混入 paper 1 的目标函数。

---

## 12. 关键概念速查

| 概念 | 一句话 |
|---|---|
| Turn / Step | 一次 LLM 调用 |
| Workflow | 一个任务从开始到结束的一串 LLM 调用 |
| $w_i$ | 当前 step 的重要性信号 |
| `budget_pressure` | 当前预算有多紧，决定升档门槛 |
| `expected_cost` | 调用前估计成本，用于排序 |
| `reserved_cost` | 调用前预留成本，用于 hard-budget 安全 |
| `actual_cost` | 调用后真实成本，用于实验报告 |
| Workflow-aware | 维护 workflow ledger、预算水位、后端配额和 step importance 的路由 |
| Workflow-blind | 主要看单次请求局部信息，不维护跨步骤预算状态的路由 |
| Workflow-Level Router | workflow 开始时选一次模型或 routing profile |
| Budget-Only Step Router | 每步决策，但只看预算水位，不看 step 重要性 |
| BudgetFlow Full | 每步决策 + 预算压力 + step 重要性 + runtime governance |
