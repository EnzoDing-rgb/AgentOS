# AgentOS Paper 1 Concept (Rewrite)

> **Core claim**: Paper 1 studies how agent frameworks can expose workflow-level utility contracts so that a runtime can transparently allocate LLM spending under hard budgets, and then evaluate that allocation on public workflow-level benchmarks rather than on self-defined step scores.

> **中文一句话**：这篇 paper 不是再做一个“自动选模型”的 router，而是研究 agent framework 如何把每一步的价值、预算和可验证信号显式交给运行时，让系统能在固定预算下透明、可审计地花钱，并最终用 SWE-bench 这类公开 workflow benchmark 检验是否真的更划算。

> **建议定位**：`training-free, auditable utility governance for budget-constrained coding-agent workflows`

---

## 0. 这篇 Paper 到底在做什么？

先用最直白的话说：

> 一个 coding agent 跑任务时，会连续调用很多次 LLM。预算有限时，系统要决定哪些步骤值得用贵模型，哪些步骤可以省钱。本文关心的不是单次调用怎么选模型，而是整个 workflow 怎么声明价值、怎么花预算、怎么记账、怎么证明钱花得值。

这里有三个关键词。

**Workflow**：不是一次孤立的 prompt，而是一整个 agent run。例如修 bug、重构模块、生成测试，通常包含 planning、search、edit、validate 等多个步骤。

**Utility**：不是抽象的“用户心里满意不满意”，也不是论文最后拿来证明自己的主指标。它是运行时内部用来分配预算的信号，帮助系统判断“这一步值不值得花贵模型”。本文把它写成：

$$
\text{utility}_i = w_i \cdot q_i
$$

其中 $q_i$ 不是作者随便打分，而是从公开 benchmark 或确定性 harness 中提炼出来的可观测信号，例如 localization 是否命中 gold patch 文件、patch 是否能 apply、`FAIL_TO_PASS` 测试是否通过、`PASS_TO_PASS` 测试是否保持通过。$w_i$ 也不是拍脑袋的重要性，而是通过历史 runs、消融实验或对照组估计出来的相对贡献。

最关键的是：论文最终不靠 $\sum_i w_iq_i$ 说服 reviewer。最终评估应该回到 workflow 级别，例如在同样预算下 SWE-bench Verified 的 resolve rate 是否更高，或者达到同样 resolve rate 是否花更少钱。

**Governance**：不是只做一个 router，而是定义一套运行时治理机制：谁声明价值先验、谁管预算、谁选模型、谁记录每一步为什么这样花钱、最后用什么公开 benchmark 和确定性信号评估。

所以这篇 paper 最稳的主张是：

> **把 coding-agent workflow 的 LLM 花费变成显式、可审计、可 benchmark-grounded 的 utility governance problem。**

---

## 0.5 最终形态：不是替代 Cursor，而是治理已有 agent workflow

这篇 paper 最容易跑偏的地方，是把系统写成另一个 Cursor / Claude Code / 通用 coding CLI。这个方向不稳，因为 Cursor 和 Claude Code 的核心价值不只是调用 LLM，而是交互体验、上下文管理、文件级 diff、编辑确认、终端集成和产品闭环。本文不应该重新实现这些能力。

更稳的最终形态是：

> 一个面向 coding-agent 平台的 **budget / utility governance runtime**。研究原型可以做成 Python runtime + CLI evaluation harness + UtilityLedger，而不是一个完整 IDE 或完整 coding agent 产品。

也就是说，CLI 在本文里不是“用户每天使用的 Claude Code 替代品”，而是：

> 用命令行跑一个已有 agent workflow，并在每次 LLM 调用外面加预算治理、模型选择和 ledger 记录。

系统形态可以写成三层：

```text
Enterprise admin / platform team
  configures budgets, teams, model pools, policies
        |
        v
AgentOS governance runtime
  UtilityContract + Governor + ModelSelector + UtilityLedger
        |
        v
Existing coding agents
  SWE-agent / OpenHands / internal agents / CLI harness
```

这里的重点是：本文不发明一个新的 coding agent，而是治理已有 agent 的 LLM spending。

### 0.5.1 谁用这个系统？

主场景应该是 multi-team enterprise budget governance，而不是个人开发者省钱工具。

不同角色的边界可以这样定义：

| 角色 | 关心什么 | 是否直接操作系统 |
|---|---|---|
| CFO / finance | 总预算、部门成本、超支风险 | 通常不直接操作，只看汇总报告 |
| Engineering platform / infra team | 模型池、价格表、默认策略、审计规则、系统部署 | 是主要部署者 |
| Team lead / EM | team/project/workflow 的预算、优先级和策略 | 会配置或审批策略 |
| Developer | agent 是否被降级/升级、任务花了多少钱、为什么这样选模型 | 主要通过已有 agent 间接感知 |

个人开发者不是不能支持，但应该作为退化场景：

> 如果只有一个 user、一个 daily/monthly budget、一个可用模型池，那么 enterprise policy 退化成 personal budget policy。

这样论文只需要维护一套抽象：企业是 general case，个人是 special case。

### 0.5.2 Library、CLI 和产品的边界

如果做成 library，它不是给普通开发者每天手动 `import` 的库，而是给 agent framework 或企业平台团队接入的 runtime SDK。类似 LangChain 的地方只在于它也是开发者框架；不同点是 LangChain 主要负责把 prompt、model、tool、retriever、agent workflow 串起来，而本文 runtime 负责预算、utility contract、model selection 和 ledger accounting。

如果做成 CLI，它也不应该是完整 coding agent CLI。更合适的是 evaluation harness：

- 输入：一个已有 agent workflow、预算、模型池、policy config；
- 运行：拦截或包装每次 LLM call，生成 `UtilityContract`，选择模型，扣预算；
- 输出：patch / task result、per-step `UtilityLedger`、budget trace，以及最终 workflow benchmark 结果。

因此本文 artifact 可以同时有研究和产品雏形：

> Research prototype: Python runtime + CLI harness for open or instrumentable coding-agent workflows.  
> Product direction: enterprise budget governance layer for teams that already use coding agents.

### 0.5.3 SWE-agent 和 OpenHands 在本文中的位置

SWE-agent 是一个开源 research coding agent，常用来跑 SWE-bench。它会根据 GitHub issue 搜索代码、编辑文件、运行测试，并输出 patch。OpenHands 是一个开源软件工程 agent 平台，原名 OpenDevin，提供更完整的 agent execution environment。

它们和本文的关系不是“被本文替代”，而是实验载体和接入对象：

```text
SWE-agent / OpenHands / internal coding agent
  provides the existing multi-step coding workflow
        |
        v
AgentOS governance runtime
  wraps LLM calls, selects models, enforces budget, writes ledger
        |
        v
SWE-bench / deterministic tests
  grades final workflow outcome under budget
```

对 Cursor、Claude Code 这类闭源商业 agent，本文不要承诺直接接入。更稳的边界是：

> Closed commercial agents would require provider-side hooks or exported call traces. This paper focuses on open or instrumentable coding-agent workflows.

---

## 1. 为什么 Cursor Auto / opencode Auto / 云端 Auto 没有直接解决这个问题？

现在很多系统都有 auto model selection：

- Cursor Auto 会自动选择模型；
- opencode 支持按 agent / subagent 配置模型，也在讨论动态模型选择；
- OpenAI GPT-5 Auto 会在不同能力模式之间切换；
- RouteLLM、CARROT、OmniRouter 研究 per-query 或 query-distribution routing。

这些工作都很有用，但它们主要回答的是：

> **当前这一次请求，该用哪个模型？**

本文关心的是另一层问题：

> **整个 agent workflow 的预算有限时，哪些步骤更值得花钱？系统如何知道、记录并评估这种花法？**

区别在这里：

| 问题 | Auto model / per-query router | 本文 |
|---|---|---|
| 决策对象 | 当前一次请求或子任务 | 一个 multi-step workflow |
| 看到的信息 | prompt、上下文、复杂度、模型成本 | prompt + workflow 位置 + $w_i$ + budget + benchmark-derived signals |
| 预算 | 通常是“尽量省”或单次成本权衡 | workflow 级 hard budget |
| 价值结构 | 多数不显式暴露 | agent framework 显式声明 |
| 输出 | 这次用哪个模型 | 每一步为什么这样花钱、花了多少、最终 workflow benchmark 结果如何 |

这不是说 Cursor Auto 或云端 router 不重要。相反，它们可以成为本文系统里的底层执行器或类比对象。只是对 Cursor、Claude Code 这类闭源产品，真实接入需要 provider-side hooks、API-level routing control 或 exported call traces；本文实验应聚焦 SWE-agent、OpenHands、internal agents 这类 open or instrumentable workflows。

本文更像在已有 agent 或 router 上面加一层：

```text
Agent framework
  declares: task_type, w_i, budget, observable signals
        |
        v
Utility governance layer (本文)
  decides and logs: budget state, model choice, utility signal
        |
        v
Model selector / router
  could be heuristic, Cursor Auto, BAAR, or another learned router
        |
        v
LLM backend
```

本文的差异不是“我也会自动选模型”，而是：

> **我要求 agent framework 把 workflow 的价值结构显式交出来，并让运行时按 hard budget 做可审计的 allocation，最后用公开 benchmark 的 workflow outcome 检验这套 allocation 是否真的有用。**

---

## 2. 和 Budget-Aware Agentic Routing (BAAR) 的关系

Budget-Aware Agentic Routing 是最接近的相关工作。它也研究 multi-step agent 在预算下如何选择 cheap / expensive model。

如果本文只说：

> 我也做 multi-step budget-aware routing，但不用 RL。

那会太接近 BAAR，贡献不够稳。

更合理的区分是：

| 维度 | BAAR | 本文 |
|---|---|---|
| 核心贡献 | 训练一个 budget-aware sequential router | 定义 workflow-level utility contract + governance + accounting |
| 方法 | BoSFT + BoPO + budget-constrained decoding | training-free reference policy + 可插拔运行时 |
| 任务价值 | 从轨迹和 reward 中隐式学习 | 由 agent framework 显式声明 `task_type`，$w_i$ 则由消融或历史对照估计 |
| 评估重点 | cost-success frontier | workflow-level resolve rate / cost frontier + per-step ledger |
| 可替换性 | 是一个 learned router | 可以作为本文的 `ModelSelector` 插件 |

所以本文不要和 BAAR 硬拼“谁的 router 更强”。本文应该说：

> BAAR 是 router-level 方法；本文是 router 上层的 governance layer。BAAR 可以放进本文系统里，当作一个 learned `ModelSelector`。

这会让差异更实在。

---

## 3. 核心对象：Utility Contract

本文最重要的概念不是 router，而是 `UtilityContract`。

人话定义：

> `UtilityContract` 是 agent framework 在每次 LLM 调用前交给运行时的一份声明，说明这一步是什么、预算还剩多少、可以观察哪些质量信号，以及当前估计它对最终 workflow 成功有多大贡献。

最小字段可以是：

| 字段 | 含义 |
|---|---|
| `turn_id` | 当前 LLM 调用编号 |
| `task_type` | 例如 planning、generation、bug_fix、validation |
| $w_i$ | 这一步对最终 workflow 成功的估计贡献权重 |
| `signal_source` | 这一步能接到哪些公开或确定性信号，例如 localization、patch apply、test result |
| `priority` | interactive / batch 等体验上下文 |
| $B$ | workflow 总预算 |
| `spent_so_far` | 当前已经花了多少 |

这里的 $w_i$ 不是系统凭空猜出来的，也不应该靠作者主观指定。它可以有三种来源，可信度从高到低：

- 历史消融：在历史 runs 中去掉某个 step，或把这个 step 固定换成便宜模型，看最终 SWE-bench resolve rate 掉多少；
- 对照组估计：比较 `all-one w_i`、random $w_i$、coarse high/low $w_i$、task-type default $w_i$ 等设置在同一预算下的结果；
- 工程默认表：冷启动时按已有 workflow 经验给一个默认值，但论文必须把它当作待验证的先验，而不是客观真理。

例如一个 bug-fix workflow：

| 步骤 | `task_type` | 可观察信号 | $w_i$ 来源 |
|---|---|---|---|
| 读 issue | retrieval | 后续是否定位到 gold patch 文件 | 历史对照 / 默认表 |
| 定位 bug | localization / reasoning | file-level Acc@k、MRR | 历史消融 |
| 修改代码 | repair / generation | patch apply、FAIL_TO_PASS | 历史消融 |
| 写测试 | validation / generation | reproduction test 是否能暴露原问题 | 对照组 |
| 跑测试并总结 | validation | PASS_TO_PASS、测试执行结果 | 历史对照 |

这个声明让运行时不用只看 prompt 猜重要性，而是直接拿到 workflow 的结构信息。它不是评估结论本身，最后仍然要用 SWE-bench resolve rate、成本和消融实验来证明这些权重有没有用。

---

## 4. 最小数学：我们到底优化什么？

这里要分清楚两件事：

- 运行时内部怎么做预算分配；
- 论文最终怎么向 reviewer 证明这套分配有用。

设一个 workflow 有 $N$ 个 turn。每个 turn $i$ 可以选择一个后端或一个质量-花费方案 $a_i$。

- $q_i(a_i)\in[0,1]$：从公开 benchmark 或确定性 harness 中提炼的可观察质量信号；
- $c_i(a_i)$：这一步成本；
- $w_i$：这一步对最终 workflow 成功的估计贡献权重；
- $B$：workflow 总预算。

运行时内部可以用下面这个分数做分配：

$$
\max_{a_1,\dots,a_N}\sum_{i=1}^{N} w_i q_i(a_i)
\quad \text{s.t.}\quad
\sum_{i=1}^{N} c_i(a_i)\le B
$$

这句话的人话解释是：

> 在不超预算的前提下，让高价值步骤得到更高质量，让低价值步骤不要浪费钱。

但这不是论文最终的主评估指标。最终主指标必须回到 workflow 级别：

- 在同样 budget 下，SWE-bench Verified resolve rate 是否更高；
- 达到同样 resolve rate，需要多少 token / dollar；
- 成本-成功率 Pareto frontier 是否更好；
- budget violation rate 是否更低。

也就是说，$\sum_i w_iq_i$ 是 runtime 的内部决策信号，不是论文拿来自证成功的最终分数。Reviewer 不需要相信每个 step 的 utility 是“客观真理”；他只需要看这套内部信号是否让公开 benchmark 上的最终结果变好。

如果 expensive model 相比 cheap model 的提升是：

$$
\Delta q_i = q_i(\text{expensive}) - q_i(\text{cheap})
$$

成本增加是：

$$
\Delta c_i = c_i(\text{expensive}) - c_i(\text{cheap})
$$

那么一个简单、可解释的 reference policy 是按下面这个分数排序：

$$
\text{score}(i)=\frac{w_i\Delta q_i}{\Delta c_i}
$$

含义也很直接：

- $\Delta q_i / \Delta c_i$：多花一美元，这一步质量能多涨多少；
- 乘 $w_i$：如果这一步更关键，同样的质量提升更值钱。

本文不需要把这个启发式包装成很重的理论。它的作用是提供一个 training-free、可解释、可审计的 baseline。未来如果有更强的 learned router，比如 BAAR，也可以替换这个 `ModelSelector`。替换之后，评估口径仍然不变：看同一批公开 workflow benchmark 在同一预算下的最终结果。

---

## 5. 系统层贡献：不是只选模型，而是治理和记账

本文的系统可以拆成四个核心部件。

| 组件 | 人话解释 | 作用 |
|---|---|---|
| `UtilityContract` | 上层 agent 声明这一步的类型、预算和可观察信号 | 让运行时知道“这一步为什么可能值得花钱” |
| `Governor` | 管预算、限流、并发 | 保证 hard budget 和资源约束成立 |
| `ModelSelector` | 选择模型或质量-花费方案 | 可以是本文启发式，也可以是 BAAR 这类 learned router |
| `UtilityLedger` | 记账本 | 记录每一步花了多少钱、观察到什么信号、最终 workflow 结果如何 |

另外两个机制可以作为辅助：

| 组件 | 作用 |
|---|---|
| `ZombieDetector` | 截断成本继续上涨但有效质量不涨的调用 |
| `Preemption` | 在预算不被打破的前提下保护 interactive 体验 |

这里最重要的是 `UtilityLedger`。

每一步至少记录：

- `turn_id`
- `task_type`
- $w_i$
- selected backend
- estimated cost
- actual cost
- observable signal $q_i$
- internal utility signal $w_i q_i$
- budget remaining
- final workflow outcome

这样，论文才能回答：

> 这一步为什么花钱？花了多少？观察到了什么中间信号？最后整个 workflow 过没过公开 benchmark？

这是和纯 router paper 的差异。纯 router 重点是“选了哪个模型”；本文重点是“整个 workflow 的花费、内部决策依据和最终 benchmark 结果是否可解释、可审计、可复现”。

---

## 6. 一开始不知道 workload 怎么办？

这个问题很关键，但它不是本文必须完整解决的核心问题。

本文不假设系统一开始知道企业或用户未来会有多少 workload。更稳的说法是：

> 本文不假设系统预知未来 workload；系统只需要在运行时维护当前 workflow 的预算、已消耗成本、剩余步骤估计和 `UtilityContract`。长期 workload 分布可以通过默认配置、小样本校准或在线更新逐步学习。

这里要分三层。

### 6.1 单个 workflow 内

当前 agent run 的结构通常由 agent framework 知道。

例如：

- 当前步骤是 planning 还是 validation；
- 当前 turn 的 `task_type` 是什么；
- 这一步当前使用哪个 $w_i$ 先验；
- 当前 workflow 的预算是多少；
- 已经花了多少钱。

其中 `task_type` 和预算状态来自 agent framework 的控制流；$w_i$ 则来自历史消融、对照组或冷启动默认表。系统不能假装第一次运行时就知道真实权重，它只能使用一个透明的先验，然后用后续实验检验这个先验有没有用。

### 6.2 企业长期 workload 分布

企业可能关心长期统计：

- 每天多少 agent task；
- planning / generation / validation 各占多少；
- 平均 token 消耗；
- 不同模型在不同 task type 上的质量先验；
- 不同 step 权重在历史消融中的效果。

这些可以先用默认表启动，再用少量历史样本校准。这里可以用很普通的方法，例如分桶均值、EWMA、简单 Bayesian update 或小样本 A/B。

本文不需要声称自己发明了 workload prediction。

### 6.3 未知未来请求流

未来请求什么时候来、会来多少，本来就不可能准确知道。运行时只需要做预算配速：

- 花得太快，就收紧；
- 花得太慢，就放宽；
- 用 burn rate、sliding window、EWMA 这类在线反馈即可。

这里不需要预测得很准。只要反馈方向正确，系统就能避免明显超支，并在预算紧张时自动降级。

### 6.4 这是不是传统 ML 问题？

一部分是。

质量先验、成本估计、$w_i$ 估计、workload 分布估计，确实都接近传统的不确定性估计、online learning、bandit 或 Bayesian calibration。

但 agent workflow 又有几个现实困难：

- 前面步骤错了会影响后面，存在 path-dependence；
- 很多任务只有最终结果，反馈 sparse；
- 企业 workload 会变，分布 non-stationary；
- 不同 repo、不同 agent scaffold、不同模型版本都会改变统计规律。

所以本文不应该 claim：

> 我们能准确预测未来 workload。

更稳的 claim 是：

> 本文提供 contract + governance + accounting 层。质量/成本先验可以粗糙，可以小样本校准，也可以未来接入 learned router。实验会测试先验有噪声时系统是否仍然比无治理或均匀预算更稳；无信息时系统应退化到 uniform baseline。

---

## 7. Quality / utility 到底怎么定义？

这里必须非常诚实。

本文不应该说：

> 我们最大化真实 user utility。

因为真实用户效用不是天然存在、统一、可直接测量的东西。

本文也不应该说：

> 我们自己定义每一步的 quality，然后把这些 quality 加起来证明系统更好。

这会被 reviewer 直接质疑：你自己拆 step、自己定 $q_i$、自己定 $w_i$，最后自己证明自己。这个逻辑不够硬。

更稳的说法是：

> Step-level utility 是运行时的内部分配信号；论文最终评估必须落在 workflow-level public benchmark 上。

也就是说，$q_i$ 和 $w_i$ 可以帮助 runtime 决定怎么花钱，但 paper 最终要报告的是：

- SWE-bench Verified resolve rate；
- cost per resolved instance；
- resolution-cost Pareto frontier；
- budget violation rate；
- 消融实验中不同 $w_i$ 设定带来的 workflow-level 结果差异。

这样 reviewer 不需要先接受“每一步 utility 是否客观”。他只需要看：这套内部信号有没有让公开 benchmark 上的最终结果更好。

### 7.1 最推荐的主 benchmark：SWE-bench Verified

如果本文落在 coding agent / software engineering 场景，最稳的 grader 是 SWE-bench / SWE-bench Verified 风格。

SWE-bench 的任务是：给一个真实 GitHub issue 和代码仓库，让系统生成 patch，然后用测试判断 patch 是否真的解决问题。

SWE-agent 可以作为本文最自然的实验载体之一。它不是本文要提出的新方法，而是一个已有 coding-agent workflow：读 issue、搜索代码、编辑文件、运行测试、生成 patch。本文 runtime 可以包在它的 LLM call 外面，记录每一步的 cost、model choice、budget state 和中间信号。

核心 grader 口径是：

- patch 能否 apply；
- `FAIL_TO_PASS` tests 是否从失败变为通过；
- `PASS_TO_PASS` tests 是否仍然通过，说明没有破坏已有功能。

这比“看起来写得不错”强得多，因为它是可执行的、可复现的 correctness signal。

可信度也够：

- SWE-bench GitHub 约 4.7k stars；
- SWE-bench 是 ICLR 2024 工作；
- 使用真实 GitHub issues；
- 有 Docker evaluation harness；
- SWE-bench Verified 是和 OpenAI 合作人工筛过的 500 个可解任务；
- SWE-agent 约 19k stars，并明确以 SWE-bench / SWE-bench Verified 作为 coding agent 评估基准。

所以本文可以写：

> 对 bug-fix / coding-agent workloads，本文采用 SWE-bench Verified style deterministic grading：patch applies, fail-to-pass tests pass, and pass-to-pass tests remain passing.

### 7.2 那 step-level 的 $q_i$ 从哪里来？

关键原则是：$q_i$ 尽量从同一个公开 benchmark 或确定性执行结果里提炼，不另起炉灶发明主观 grader。

对 SWE-bench 风格任务，可以这样定义：

| Step | 可用的 $q_i$ 信号 | 来源 |
|---|---|---|
| localization / search | agent 找到的文件是否覆盖 gold patch 修改过的文件；Top-k accuracy、MRR、MAP | SWE-bench 的 `patch` 字段可解析出 gold files；SweRank / Agentless 已使用类似 localization 指标 |
| repair / edit | patch 是否存在、是否能 apply、`FAIL_TO_PASS` 测试通过比例 | SWE-bench harness 的 evaluation report |
| validation | `PASS_TO_PASS` 是否保持通过、测试是否成功执行、是否 timeout / error | SWE-bench harness 日志和 `grading.py` |
| planning | 没有独立客观 gold label，不单独当主指标；只用 downstream proxy，例如 plan 后是否更快定位到 gold files | localization / repair 的 downstream signal |

这句话很重要：

> 本文不要求 reviewer 相信 planning quality 这种主观分数。没有公开 gold label 的 step 不做独立主评估，只看它是否改善后续 localization、repair 和最终 resolve rate。

SWE-bench 的数据结构也支持这个设计。Verified 数据里有 `patch`、`test_patch`、`FAIL_TO_PASS`、`PASS_TO_PASS`。其中 `patch` 是 gold solution patch，可以解析出参考 PR 修改过哪些文件；`FAIL_TO_PASS` 和 `PASS_TO_PASS` 是最终确定性测试集合。SWE-bench harness 的 `grading.py` 会检查 patch 是否存在、是否成功 apply、失败测试是否转为通过、原本通过的测试是否保持通过。

SWE-agent / mini-SWE-agent 的输出也支持 step-level 记录。SWE-agent 的 `.traj` 是 JSON，里面有每步的 `thought`、`action`、`observation`、`state`；mini-SWE-agent 还会记录每步 cost、timestamp、总 instance cost 和 API calls。因此本文不需要凭空发明 step trace，只需要把这些已有 trajectory 和 SWE-bench 的 gold / test signal 对齐。

### 7.3 这类 step 拆分不是本文自创的

这点也要写清楚，否则 reviewer 会问：为什么你有权把一个 SWE-bench task 拆成 localization、repair、validation？

已有工作已经这么做了：

- Agentless 把 SWE-bench issue resolution 明确拆成 localization、repair、patch validation 三个阶段；
- SweRank 在 SWE-bench-Lite / LocBench 上做 file、module、function 三个粒度的 localization，并报告 Acc@k；
- SWE-bench 原论文也讨论过 oracle retrieval，把 gold patch 修改过的文件作为 oracle context，用来分析 retrieval 对最终修复结果的影响。

所以本文不是随便发明 workflow steps，而是复用已有 SWE-bench 生态里常见的 decomposition：先定位相关代码，再生成 patch，再用测试验证。

### 7.4 HumanEval / MBPP 放在哪里？

HumanEval 也可信：

- OpenAI 官方；
- GitHub 约 3.2k stars；
- 用 unit tests / functional correctness / pass@k。

但 HumanEval 更像函数级代码生成 benchmark，不太像完整 agent workflow。因此它适合作为 `code_generation` 子任务的补充，不应该成为本文的唯一主 benchmark。

MBPP 也常用，但同样更偏函数级代码生成。对本文这种 multi-step coding-agent workflow，主基准还是 SWE-bench Verified 更贴。

### 7.5 决策侧和评估侧必须分开

运行时决策时，系统不能偷看本次的 ground truth。它只能用：

- 历史质量先验；
- task type 默认表；
- 小样本校准结果；
- 模型价格表和 token 估计。

评估时，才用 SWE-bench harness、gold patch 解析和 trajectory 分析得到真实观察信号。

所以文档里要写清楚：

> 决策侧使用 estimated quality prior；评估侧使用 public benchmark / deterministic harness signal。本文不让 policy 在决策时偷看 ground truth。

---

## 8. 可行实验：你的服务器能支持什么？

你的服务器条件：

- GPU：单张 NVIDIA A800-SXM4-80GB；
- CPU：2 × Intel Xeon Platinum 8358，总 128 线程；
- RAM：1TB；
- Storage：NFS 约 118TB。

这对本文足够有用，但要诚实使用。

适合做：

- SWE-bench Lite / Verified 子集实验；
- 用 CLI harness 跑 SWE-agent / OpenHands / internal agent workflow；
- 本地 open-weight coding model 的推理；
- mock-to-real validation；
- 本地模型和 API 模型的 cost-quality 对比；
- Docker benchmark artifacts、logs、UtilityLedger 保存；
- 小规模重复实验和 sensitivity analysis。

不应该承诺：

- 大规模训练一个新 router；
- 全量 SWE-bench 多轮大规模 sweep；
- 解决通用 workload prediction；
- 和 frontier API model 做完全公平的大规模线上竞赛。

对这篇 paper 来说，最重要的是跑通：

1. `UtilityContract` 能不能接入 workflow；
2. `Governor` 能不能守住 budget；
3. `ModelSelector` 能不能按 utility-aware 规则分配；
4. `UtilityLedger` 能不能记录每一步；
5. SWE-bench harness / gold patch / trajectory 能不能给出可复现的 workflow outcome 和 step-level observable signals；
6. 在 noisy prior / cold-start 下是否仍比 baseline 更稳。

原型形态可以明确写成：

> We implement AgentOS as a Python governance runtime and CLI evaluation harness that wraps open or instrumentable coding-agent workflows, rather than as a replacement for IDE-based products such as Cursor or Claude Code.

---

## 9. 研究问题（RQ）

三条 RQ 足够。

### RQ1: Utility accounting 是否让成本-结果评估更可解释？

问题：

> 如果没有显式 `UtilityContract` 和 `UtilityLedger`，agent workflow 的成本、模型选择和最终 benchmark 结果是否会变得不可解释、不可复现？

指标：

- per-step cost trace；
- per-step observable signal；
- internal $w_iq_i$ decision signal；
- final SWE-bench outcome；
- budget violation rate；
- audit completeness。

### RQ2: 显式 utility contract 是否提升 workflow-level benchmark outcome？

问题：

> 在相同预算下，使用显式 $w_i$ 和边际效用分配，是否比 uniform budget、per-request greedy、random allocation 获得更高 SWE-bench resolve rate 或更低 cost per resolved instance？

指标：

- resolve rate @ fixed budget；
- cost per resolved instance；
- resolution-cost Pareto frontier；
- budget violation rate；
- localization Acc@k / patch apply / FAIL_TO_PASS / PASS_TO_PASS breakdown。

关键消融：

- ablation-derived $w_i$；
- coarse high-low $w_i$；
- task-type default $w_i$；
- noisy $w_i$；
- random $w_i$；
- all-one $w_i$。

### RQ3: cold-start 和粗先验下是否仍然可用？

问题：

> 当质量/成本先验不准、样本很少、未来 workload 不知道时，系统是否平滑退化，而不是崩掉？

指标：

- workflow outcome degradation under noisy priors；
- budget overrun rate；
- cost per resolved instance；
- 和 uniform baseline 的差距；
- 随 calibration sample size 增加的趋势。

这条 RQ 很重要，因为它直接回应“企业安装你的 GitHub 代码时，一开始什么都不知道怎么办”。

---

## 10. Baselines

至少需要这些 baseline。

| Baseline | 含义 | 回答什么问题 |
|---|---|---|
| `always_expensive` | 每步都用贵模型，直到预算爆 | 证明预算硬约束必要 |
| `always_cheap` | 每步都用便宜模型 | 证明只省钱不等于高 resolve rate |
| `per_request_greedy` | 每步独立最大化 estimated $q/c$ | 对比没有 workflow utility 的短视策略 |
| `budget_uniform` | 有预算配速，但 $w_i=1$ | 排除“只是控预算更好” |
| `agentos_reference` | $w_i\Delta q_i/\Delta c_i$ + budget feedback | 本文 training-free policy |
| `learned_selector_optional` | BAAR 或类似 learned router，如果可用 | 说明本文框架可插拔 |

注意：本文不一定要打败 BAAR。更重要的是证明：

> BAAR 这类 router 可以作为 selector 插入本文框架；本文额外提供 contract、ledger、benchmark-grounded accounting。

---

## 11. 这篇 Paper 的真实贡献

如果目标是 CCF-A 水平，不能只说“我有一个启发式 router”。更实在的贡献应该是下面四个。

### Contribution 1: Problem definition

提出 workflow-level utility governance 问题：

> coding agent 的 LLM spending 不只是 routing，也不是只看总成本，而是要把每一步的预算决策、价值先验和可观察信号显式化，并最终用 workflow-level public benchmark 检验。

### Contribution 2: Runtime abstraction

提出 `UtilityContract + Governor + ModelSelector + UtilityLedger`。

这个抽象让上层 agent、底层 router、benchmark signal、budget policy 解耦。

### Contribution 3: Reference policy

给一个无需训练、可解释的边际效用分配策略：

$$
\frac{w_i\Delta q_i}{\Delta c_i}
$$

它不是要成为最强学习算法，而是一个透明、可复现、方便部署的 baseline。

### Contribution 4: Benchmark-grounded evaluation

用 SWE-bench Verified style workflow benchmark 做最终评估：在固定预算下比较 resolve rate、cost per resolved instance 和 resolution-cost Pareto frontier。

Step-level 的 $q_i$ 只作为中间观察信号，来自 SWE-bench harness、gold patch localization 和 agent trajectory；$w_i$ 通过消融和对照组估计。UtilityLedger 负责把这些内部决策信号、成本和最终 benchmark outcome 记录下来。

---

## 12. 审稿人可能怎么质疑，怎么回答？

### Q1: 你是不是又做了一个 router？

不是。router 只是 `ModelSelector`。本文贡献是 router 上层的 utility contract、budget governance 和 utility ledger。

### Q2: BAAR 已经做了 budget-aware agentic routing，你还有什么？

BAAR 学 router policy。本文定义 workflow-level utility contract 和 accounting layer。BAAR 可以作为本文的 learned selector。

### Q3: 你怎么知道一开始 workload 是什么？

本文不假设知道未来 workload。当前 workflow 的结构由 agent framework 声明；长期分布、质量先验和 $w_i$ 用默认表、小样本校准、历史消融和在线更新；无信息时退化到 uniform baseline。

### Q4: 你说 utility，凭什么？

本文不声称真实用户效用 oracle，也不要求 reviewer 相信每个 step 的 utility 是客观真理。$w_iq_i$ 是运行时内部的预算分配信号，最终评估回到 workflow-level public benchmark：同样预算下 SWE-bench Verified resolve rate 是否更高、cost per resolved instance 是否更低。

### Q5: 你的 step-level $q_i$ 会不会自说自话？

不能用作者自定义的主观 grader 当主指标。本文的 $q_i$ 尽量来自公开或确定性信号：gold patch 文件定位、patch apply、`FAIL_TO_PASS`、`PASS_TO_PASS`、测试 timeout / error、trajectory 中的 tool action。没有公开 gold label 的 planning 不单独评主观质量，只看它是否改善 downstream localization、repair 和最终 resolve rate。

### Q6: 不同 task type 的 $q_i$ 能加吗？

不能假装完美同尺度。$\sum_i w_iq_i$ 只作为内部决策和审计信号，不作为最终主评估。主指标是 workflow-level resolve rate、成本和 Pareto frontier；同时报告 task-type breakdown。

### Q7: 这是不是传统 ML 不确定性问题？

质量先验、$w_i$ 估计和 workload 估计部分确实接近传统 online calibration / bandit / Bayesian estimation。但本文不把最优学习作为主贡献，而是提供 contract、governance、ledger，让不同 prior 或 learned router 都能被审计和比较。

### Q8: 这到底是 library、CLI，还是产品？

研究原型是 Python governance runtime + CLI evaluation harness。CLI 用来运行已有 agent workflow 并记录 budget / utility ledger，不是要替代 Cursor 或 Claude Code。未来产品方向是 enterprise budget governance layer，由 platform team 接入到 SWE-agent、OpenHands 或内部 coding-agent stack。

---

## 13. 最终推荐表述

如果要向导师或评审介绍，建议用这段：

> This paper studies utility governance for budget-constrained coding-agent workflows. Instead of proposing yet another model router or replacing IDE-based products such as Cursor and Claude Code, we define a workflow-level utility contract through which an agent framework exposes each step's task type, budget state, estimated contribution weight, and observable benchmark-derived signals. A governance runtime then wraps open or instrumentable coding-agent workflows, enforces hard budgets, selects models through a pluggable selector, and records a utility ledger explaining how much each step costs and why the runtime made that allocation. Step-level utility `w_i × q_i` is used as an internal allocation signal, not as the final evaluation metric. The final evaluation is workflow-level: SWE-bench Verified resolve rate under fixed budgets, cost per resolved instance, and resolution-cost Pareto frontier. The `q_i` signals are derived from public or deterministic sources such as gold-patch localization, patch application, fail-to-pass tests, pass-to-pass tests, and agent trajectories; the `w_i` weights are estimated through historical ablations and controlled baselines. The goal is not to claim an oracle for human utility, predict future workloads perfectly, or learn the strongest router, but to make LLM spending in coding-agent workflows explicit, auditable, and empirically comparable under hard budgets.

中文版本：

> 这篇 paper 研究的是预算约束下 coding-agent workflow 的效用治理。它不是再提出一个模型 router，也不是替代 Cursor 或 Claude Code，而是定义一套 workflow-level utility contract：agent framework 暴露每一步的任务类型、预算状态、估计贡献权重和可观察信号；governance runtime 包住 SWE-agent、OpenHands 或企业内部 agent 这类可接入 workflow 的 LLM 调用，负责守住预算、选择模型，并用 utility ledger 记录每一步为什么这样花钱。`w_i × q_i` 不是论文最终自评指标，而是运行时内部的预算分配信号。最终评估回到 workflow 级别：固定预算下 SWE-bench Verified 的 resolve rate、cost per resolved instance 和 resolution-cost Pareto frontier。这里的 `q_i` 来自公开或确定性信号，例如 gold patch localization、patch apply、fail-to-pass、pass-to-pass 和 agent trajectory；`w_i` 通过历史消融和对照组估计。本文不声称能完美预测未来 workload，也不声称最大化真实人类满意度；它的贡献是让 coding-agent workflow 的 LLM 花费变得显式、可审计、可用公开 benchmark 复现实证比较。

---

## 14. 最后一条边界

这篇 paper 如果要站得住，必须坚持这个边界：

> **不要把自己写成弱版 BAAR；要写成 BAAR、Cursor Auto、heuristic selector 都可以接入的 utility governance layer。**

这比“我有一个更简单的 router”更稳，也更有实打实的系统贡献。
