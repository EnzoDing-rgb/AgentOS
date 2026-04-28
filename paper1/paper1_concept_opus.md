# Spend Tokens Where They Matter: Workflow-Aware Budgeting for LLM Agents

> **一句话**：在固定 token / dollar 预算下，BudgetFlow 把强模型留给 agent workflow 中真正关键的步骤，并在多 workflow 并发时守住全局预算、后端 RPM 和并发槽。

---

## 0. 这篇论文到底解决什么问题？

今天的 LLM agent 通常不是调用一次模型就结束。以 SWE-bench 为例，一个 coding agent 会读 issue、找文件、看代码、写 patch、跑测试、再根据失败日志继续修。每一步都要花 token，但每一步的价值不一样：目录浏览错了通常能恢复，测试失败后的 root-cause 判断错了可能直接毁掉整条轨迹。

本文的问题不是“哪一个模型最好”，也不是“怎样训练一个最强 router”。本文问的是：

> **给定固定预算，能不能在 agent workflow 的每一步决定钱该不该花、花到多强的模型上，并在很多 workflow 并发时仍然守住全局预算和后端资源限制？**

我们提出 **BudgetFlow**：一个 training-free 的 workflow-aware budgeting runtime。它不接管 agent loop，不重写 LangChain / SWE-agent / AutoGen，只接在 LLM 调用层，维护预算账本、后端限流和步骤重要性信号。

BudgetFlow 的两个核心贡献是：

1. **Training-free hard-cap adaptation**：不同预算上限下，不训练新策略，而是用运行时的 `budget_pressure` 调整模型升级门槛。预算紧时少升档，预算松时关键步骤更容易升档。
2. **Multi-workflow runtime governance**：多个 workflow 共享一个总预算、provider RPM 和并发槽时，BudgetFlow 对每次 LLM call 做准入、排队、降级、换后端或拒绝，并回收卡死 workflow 的预算和槽位。

---

## 1. 核心洞察：不要只按 workflow 选模型，要按 step 花预算

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

BudgetFlow 不声称这些权重是真理。它只把它们当作粗粒度预算分配信号，并通过对照实验验证：只看预算够不够，是否不如同时看 step 重要性。

---

## 2. BudgetFlow 放在哪里？

BudgetFlow 位于 agent 框架和 LLM 后端之间。

```text
LangChain / SWE-agent / AutoGen / 自研 agent loop
        |
        |  LLM request + messages + tool observations
        v
BudgetFlow Runtime
        |
        |  admit / queue / downgrade / switch backend / reject
        v
LLM backend pool
```

它可以三种方式接入：

- **Proxy mode**：agent 只把 OpenAI-compatible `base_url` 指向 BudgetFlow。BudgetFlow 从 `messages`、ToolMessage、Observation 文本里推断当前 step 类型。
- **Callback / adapter mode**：LangChain、SWE-agent、AutoGen 通过 hook 提供 tool name、tool output、step index 等结构化信号。
- **SDK mode**：自研平台显式传入 `task_type`、`w_i`、`workflow_id`。

BudgetFlow 不做完整 Agent OS。它只治理 LLM 调用：选模型、守预算、限流、排队、记账、回收卡死 workflow。

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

BudgetFlow 处理的不是“谁有资格先用贵模型”这种多租户公平问题，而是每次 LLM call 到来时：

1. 当前全局预算是否还能覆盖本次调用？
2. 当前 step 值不值得升档？
3. 目标后端是否还有 RPM / 并发槽？
4. 如果没有槽，是排队、降级、换后端，还是拒绝？
5. 如果 workflow 卡死，如何释放预留预算和并发槽？

这种 runtime governance 是单条 trajectory router 不处理的系统层问题。

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

本文的对照不是“打败所有 router”，而是问：

> 在 SWE-bench 这种多步 agent workflow 里，只做 workflow-level routing 是否足够？

### Budget-Aware Agentic Routing / BoPO

BoPO 说明了一件重要事实：长程 agent 的 step-level model routing 是一个真实研究问题，不是本文凭空提出的。它用强化学习训练 learned router，在 ALFWorld、SciWorld、AppWorld 上研究成本和成功率的权衡。

本文不把 BoPO 作为主实验 baseline，因为 benchmark、模型池、agent scaffold 和训练流程都不同，直接混在 SWE-bench 主实验里会让故事变散。本文研究的是另一条路线：

> 不训练 learned router，而是在 SWE-bench-style coding workflow 上构建一个 training-free 的 budgeting runtime，并研究多 workflow 共享预算和后端资源时的系统行为。

未来可以把 BoPO-style learned selector 接到 BudgetFlow 的 ModelSelector 位置，用学习策略替换本文的启发式策略。

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

### Cache-aware routing

如果 provider 或本地 serving 暴露 cached-token / prefix-cache 信息，BudgetFlow 可以把 cache locality 纳入 `actual_cost` 或 future selector。本文不假设能直接操控 KV cache。

### Non-coding workflows

客服、RAG、科学推理等任务可以复用 ledger、reservation 和 scheduler，但需要新的 step progress signal。没有可靠 evaluator 时，不应直接套用 SWE-bench 的 progress table。

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
| Workflow-Level Router | workflow 开始时选一次模型或 routing profile |
| Budget-Only Step Router | 每步决策，但只看预算水位，不看 step 重要性 |
| BudgetFlow Full | 每步决策 + 预算压力 + step 重要性 + runtime governance |
