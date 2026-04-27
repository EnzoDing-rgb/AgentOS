# AgentOS Paper 1 Concept (GPT Version)

> **Core claim**: Paper 1 studies how agent frameworks can expose workflow-level utility contracts so that a runtime can transparently allocate LLM spending under hard budgets, maximizing benchmark-grounded effective utility without training a new router.

> **中文一句话**：这篇 paper 不是再做一个“自动选模型”的 router，而是研究 agent framework 如何把每一步的价值、预算和 grader 显式交给运行时，让系统能在固定预算下透明、可审计地花钱，并最大化可测量的有效效用。

> **建议定位**：`training-free, auditable utility governance for budget-constrained coding-agent workflows`

---

## 0. 这篇 Paper 到底在做什么？

先用最直白的话说：

> 一个 coding agent 跑任务时，会连续调用很多次 LLM。预算有限时，系统要决定哪些步骤值得用贵模型，哪些步骤可以省钱。本文关心的不是单次调用怎么选模型，而是整个 workflow 怎么声明价值、怎么花预算、怎么记账、怎么证明钱花得值。

这里有三个关键词。

**Workflow**：不是一次孤立的 prompt，而是一整个 agent run。例如修 bug、重构模块、生成测试，通常包含 planning、search、edit、validate 等多个步骤。

**Utility**：不是抽象的“用户心里满意不满意”，而是一个可测量的代理量。本文把它写成：

$$
\text{utility}_i = w_i \cdot q_i
$$

其中 $w_i$ 表示这一步在 workflow 里的相对价值，$q_i$ 表示这一步输出的可测质量。

**Governance**：不是只做一个 router，而是定义一套运行时治理机制：谁声明价值、谁管预算、谁选模型、谁记录每一步为什么这样花钱、最后用什么 grader 评估。

所以这篇 paper 最稳的主张是：

> **把 coding-agent workflow 的 LLM 花费变成显式、可审计、可 grader-grounded 的 utility governance problem。**

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
| 看到的信息 | prompt、上下文、复杂度、模型成本 | prompt + workflow 位置 + $w_i$ + budget + grader |
| 预算 | 通常是“尽量省”或单次成本权衡 | workflow 级 hard budget |
| 价值结构 | 多数不显式暴露 | agent framework 显式声明 |
| 输出 | 这次用哪个模型 | 每一步为什么这样花钱、花了多少、换来多少 measured utility |

这不是说 Cursor Auto 或云端 router 不重要。相反，它们可以成为本文系统里的底层执行器。本文更像在它们上面加一层：

```text
Agent framework
  declares: task_type, w_i, grader, budget
        |
        v
Utility governance layer (本文)
  decides and logs: budget state, model choice, utility accounting
        |
        v
Model selector / router
  could be heuristic, Cursor Auto, BAAR, or another learned router
        |
        v
LLM backend
```

本文的差异不是“我也会自动选模型”，而是：

> **我要求 agent framework 把 workflow 的价值结构显式交出来，并让运行时按 hard budget 做可审计的 utility allocation。**

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
| 任务价值 | 从轨迹和 reward 中隐式学习 | 由 agent framework 显式声明 $w_i$、`task_type`、grader |
| 评估重点 | cost-success frontier | measured utility、WQ/$、Pareto、per-step ledger |
| 可替换性 | 是一个 learned router | 可以作为本文的 `ModelSelector` 插件 |

所以本文不要和 BAAR 硬拼“谁的 router 更强”。本文应该说：

> BAAR 是 router-level 方法；本文是 router 上层的 governance layer。BAAR 可以放进本文系统里，当作一个 learned `ModelSelector`。

这会让差异更实在。

---

## 3. 核心对象：Utility Contract

本文最重要的概念不是 router，而是 `UtilityContract`。

人话定义：

> `UtilityContract` 是 agent framework 在每次 LLM 调用前交给运行时的一份声明，说明这一步是什么、重要性多高、用什么 grader 评估、整个 workflow 还有多少预算。

最小字段可以是：

| 字段 | 含义 |
|---|---|
| `turn_id` | 当前 LLM 调用编号 |
| `task_type` | 例如 planning、generation、bug_fix、validation |
| $w_i$ | 这一步的 workflow-level utility weight |
| `grader` | 这一步结束后如何测质量 |
| `priority` | interactive / batch 等体验上下文 |
| $B$ | workflow 总预算 |
| `spent_so_far` | 当前已经花了多少 |

这里的 $w_i$ 不是系统凭空猜出来的。它来自上层 agent framework 的控制流。

例如一个 bug-fix workflow：

| 步骤 | `task_type` | 直觉 | $w_i$ |
|---|---|---|---|
| 读 issue | retrieval | 重要，但便宜模型通常够 | 1 |
| 定位 bug | planning / reasoning | 错了会拖垮后续 | 3 |
| 修改代码 | generation | 主产出 | 3 |
| 写测试 | generation / validation | 影响正确性 | 2 |
| 跑测试并总结 | validation | 需要可靠，但不一定要最贵 | 1 |

这个声明让运行时不用只看 prompt 猜重要性，而是直接拿到 workflow 的结构信息。

---

## 4. 最小数学：我们到底优化什么？

设一个 workflow 有 $N$ 个 turn。每个 turn $i$ 可以选择一个后端或一个质量-花费方案 $a_i$。

- $q_i(a_i)\in[0,1]$：grader 给出的质量分数；
- $c_i(a_i)$：这一步成本；
- $w_i$：这一步的 utility weight；
- $B$：workflow 总预算。

目标函数是：

$$
\max_{a_1,\dots,a_N}\sum_{i=1}^{N} w_i q_i(a_i)
\quad \text{s.t.}\quad
\sum_{i=1}^{N} c_i(a_i)\le B
$$

这句话的人话解释是：

> 在不超预算的前提下，让高价值步骤得到更高质量，让低价值步骤不要浪费钱。

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

本文不需要把这个启发式包装成很重的理论。它的作用是提供一个 training-free、可解释、可审计的 baseline。未来如果有更强的 learned router，比如 BAAR，也可以替换这个 `ModelSelector`。

---

## 5. 系统层贡献：不是只选模型，而是治理和记账

本文的系统可以拆成四个核心部件。

| 组件 | 人话解释 | 作用 |
|---|---|---|
| `UtilityContract` | 上层 agent 声明这一步的价值和 grader | 让运行时知道“这一步为什么重要” |
| `Governor` | 管预算、限流、并发 | 保证 hard budget 和资源约束成立 |
| `ModelSelector` | 选择模型或质量-花费方案 | 可以是本文启发式，也可以是 BAAR 这类 learned router |
| `UtilityLedger` | 记账本 | 记录每一步花了多少钱、得了多少质量、产生多少 utility |

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
- grader score $q_i$
- measured utility $w_i q_i$
- budget remaining

这样，论文才能回答：

> 这一步为什么花钱？花了多少？最后换来了多少 measured utility？

这是和纯 router paper 的差异。纯 router 重点是“选了哪个模型”；本文重点是“整个 workflow 的花费和效用是否可解释、可审计、可复现”。

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
- 这一步的 $w_i$ 大概多高；
- 当前 workflow 的预算是多少；
- 已经花了多少钱。

这些信息不是从历史数据里学出来的，而是 agent framework 在执行控制流时本来就有的上下文。

### 6.2 企业长期 workload 分布

企业可能关心长期统计：

- 每天多少 agent task；
- planning / generation / validation 各占多少；
- 平均 token 消耗；
- 不同模型在不同 task type 上的质量先验。

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

质量先验、成本估计、workload 分布估计，确实都接近传统的不确定性估计、online learning、bandit 或 Bayesian calibration。

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

本文应该说：

> 我们最大化 benchmark-grounded effective utility proxy。

也就是：

$$
\text{measured utility}_i = w_i \cdot q_i
$$

其中：

- $q_i$ 是该 task type 的 deterministic grader score；
- $w_i$ 是 workflow 里这一步的相对价值权重；
- $\sum_i w_i q_i$ 是这个 workflow 的 measured effective utility。

这不是哲学意义上的用户满意度，而是软件工程任务中可复现的质量代理。

### 7.1 最推荐的主 benchmark：SWE-bench Verified

如果本文落在 coding agent / software engineering 场景，最稳的 grader 是 SWE-bench / SWE-bench Verified 风格。

SWE-bench 的任务是：给一个真实 GitHub issue 和代码仓库，让系统生成 patch，然后用测试判断 patch 是否真的解决问题。

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

### 7.2 HumanEval / MBPP 放在哪里？

HumanEval 也可信：

- OpenAI 官方；
- GitHub 约 3.2k stars；
- 用 unit tests / functional correctness / pass@k。

但 HumanEval 更像函数级代码生成 benchmark，不太像完整 agent workflow。因此它适合作为 `code_generation` 子任务的补充，不应该成为本文的唯一主 benchmark。

MBPP 也常用，但同样更偏函数级代码生成。对本文这种 multi-step coding-agent workflow，主基准还是 SWE-bench Verified 更贴。

### 7.3 决策侧和评估侧必须分开

运行时决策时，系统不能知道本次真实 $q_i$。它只能用：

- 历史质量先验；
- task type 默认表；
- 小样本校准结果；
- 模型价格表和 token 估计。

评估时，才用 deterministic grader 得到真实 $q_i$。

所以文档里要写清楚：

> 决策侧使用 estimated quality prior；评估侧使用 deterministic grader。本文不让 policy 在决策时偷看 ground truth。

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
5. SWE-bench style grader 能不能给出可复现的 $q_i$；
6. 在 noisy prior / cold-start 下是否仍比 baseline 更稳。

---

## 9. 研究问题（RQ）

三条 RQ 足够。

### RQ1: Utility accounting 是否让成本-质量评估更可解释？

问题：

> 如果没有显式 `UtilityContract` 和 `UtilityLedger`，agent workflow 的质量-成本评估是否会变得不可解释、不可复现？

指标：

- per-step cost trace；
- per-step $q_i$；
- per-step $w_iq_i$；
- budget violation rate；
- audit completeness。

### RQ2: 显式 utility contract 是否提升 measured utility？

问题：

> 在相同预算下，使用显式 $w_i$ 和边际效用分配，是否比 uniform budget、per-request greedy 更好？

指标：

- QWCR；
- WQ/$；
- utility-cost Pareto；
- task-type breakdown。

关键消融：

- oracle / reference $w_i$；
- coarse high-low $w_i$；
- task-type default $w_i$；
- noisy $w_i$；
- random $w_i$；
- all-one $w_i$。

### RQ3: cold-start 和粗先验下是否仍然可用？

问题：

> 当质量/成本先验不准、样本很少、未来 workload 不知道时，系统是否平滑退化，而不是崩掉？

指标：

- utility degradation under noisy priors；
- budget overrun rate；
- WQ/$；
- 和 uniform baseline 的差距；
- 随 calibration sample size 增加的趋势。

这条 RQ 很重要，因为它直接回应“企业安装你的 GitHub 代码时，一开始什么都不知道怎么办”。

---

## 10. Baselines

至少需要这些 baseline。

| Baseline | 含义 | 回答什么问题 |
|---|---|---|
| `always_expensive` | 每步都用贵模型，直到预算爆 | 证明预算硬约束必要 |
| `always_cheap` | 每步都用便宜模型 | 证明只省钱不等于高 utility |
| `per_request_greedy` | 每步独立最大化 $q/c$ | 对比没有 workflow utility 的短视策略 |
| `budget_uniform` | 有预算配速，但 $w_i=1$ | 排除“只是控预算更好” |
| `agentos_reference` | $w_i\Delta q_i/\Delta c_i$ + budget feedback | 本文 training-free policy |
| `learned_selector_optional` | BAAR 或类似 learned router，如果可用 | 说明本文框架可插拔 |

注意：本文不一定要打败 BAAR。更重要的是证明：

> BAAR 这类 router 可以作为 selector 插入本文框架；本文额外提供 contract、ledger、grader-grounded accounting。

---

## 11. 这篇 Paper 的真实贡献

如果目标是 CCF-A 水平，不能只说“我有一个启发式 router”。更实在的贡献应该是下面四个。

### Contribution 1: Problem definition

提出 workflow-level utility governance 问题：

> coding agent 的 LLM spending 不只是 routing，也不是只看总成本，而是要把每一步的效用、预算和质量评估显式化。

### Contribution 2: Runtime abstraction

提出 `UtilityContract + Governor + ModelSelector + UtilityLedger`。

这个抽象让上层 agent、底层 router、grader、budget policy 解耦。

### Contribution 3: Reference policy

给一个无需训练、可解释的边际效用分配策略：

$$
\frac{w_i\Delta q_i}{\Delta c_i}
$$

它不是要成为最强学习算法，而是一个透明、可复现、方便部署的 baseline。

### Contribution 4: Benchmark-grounded evaluation

用 SWE-bench Verified style grader，把 utility 落到可执行测试上：

$$
\text{measured utility} = \sum_i w_i q_i
$$

再用 UtilityLedger 把每一步的 cost、quality、utility 记录下来。

---

## 12. 审稿人可能怎么质疑，怎么回答？

### Q1: 你是不是又做了一个 router？

不是。router 只是 `ModelSelector`。本文贡献是 router 上层的 utility contract、budget governance 和 utility ledger。

### Q2: BAAR 已经做了 budget-aware agentic routing，你还有什么？

BAAR 学 router policy。本文定义 workflow-level utility contract 和 accounting layer。BAAR 可以作为本文的 learned selector。

### Q3: 你怎么知道一开始 workload 是什么？

本文不假设知道未来 workload。当前 workflow 的结构由 agent framework 声明；长期分布用默认表、小样本校准和在线更新；无信息时退化到 uniform baseline。

### Q4: 你说 utility，凭什么？

本文不声称真实用户效用 oracle。本文最大化 benchmark-grounded effective utility proxy，即 $w_iq_i$。其中 $q_i$ 来自 deterministic grader，主推 SWE-bench Verified style tests。

### Q5: 不同 task type 的 $q_i$ 能加吗？

不能假装完美同尺度。主指标之外要报告 per-task-type breakdown，并固定 workload mix。整体分数是 operational proxy，不是绝对真理。

### Q6: 这是不是传统 ML 不确定性问题？

质量先验和 workload 估计部分确实接近传统 online calibration / bandit / Bayesian estimation。但本文不把最优学习作为主贡献，而是提供 contract、governance、ledger，让不同 prior 或 learned router 都能被审计和比较。

---

## 13. 最终推荐表述

如果要向导师或评审介绍，建议用这段：

> This paper studies utility governance for budget-constrained coding-agent workflows. Instead of proposing yet another model router, we define a workflow-level utility contract through which an agent framework declares each step's task type, utility weight, budget, and grader. A runtime then enforces hard budgets, selects models through a pluggable selector, and records a utility ledger that explains how much each step costs and what measured utility it produces. We operationalize utility as `w_i × q_i`, where `q_i` is a benchmark-grounded deterministic grader score, such as SWE-bench Verified style fail-to-pass and pass-to-pass tests. The goal is not to predict future workloads perfectly or to learn the strongest router, but to make LLM spending in coding-agent workflows explicit, auditable, and empirically comparable under hard budgets.

中文版本：

> 这篇 paper 研究的是预算约束下 coding-agent workflow 的用户效用治理。它不是再提出一个模型 router，而是定义一套 workflow-level utility contract：agent framework 声明每一步的任务类型、效用权重、预算和 grader；运行时负责守住预算、选择模型，并用 utility ledger 记录每一步花了多少钱、产生了多少可测效用。本文把 utility 操作化为 `w_i × q_i`，其中 `q_i` 来自 SWE-bench Verified 风格的确定性 grader。本文不声称能完美预测未来 workload，也不声称最大化真实人类满意度；它的贡献是让 coding-agent workflow 的 LLM 花费变得显式、可审计、可复现实证比较。

---

## 14. 最后一条边界

这篇 paper 如果要站得住，必须坚持这个边界：

> **不要把自己写成弱版 BAAR；要写成 BAAR、Cursor Auto、heuristic selector 都可以接入的 utility governance layer。**

这比“我有一个更简单的 router”更稳，也更有实打实的系统贡献。
# AgentOS Paper 1 Concept (GPT Version)

> **一句话**：这篇 paper 研究的不是“单条请求该路由到哪个模型”，也不只是训练一个 budget-aware router；而是**agent framework 如何显式声明 workflow 的 utility contract，使运行时能在固定预算下透明、可审计地分配 LLM 花费，从而最大化用户有效效用**。

> **建议主定位**：`training-free, auditable utility governance for budget-constrained coding-agent workflows`

> **Core claim (EN)**: Paper 1 studies how agent frameworks can expose workflow-level utility contracts so that a runtime can transparently allocate LLM spending under hard budgets, maximizing effective user utility without training a router.

---

## 1. 先回答最关键的问题：云端 auto-routing 已经存在，这篇 paper 还有没有意义？

有，但前提是**把问题定义得比云端 auto-routing 更准确**。

今天很多云端产品已经有 auto-routing。它们确实解决了一部分问题，但主要解决的是：

> **这一次请求，该用快模型还是强模型？**

这类问题通常是：
- `per-query`
- 近似无状态
- 目标是单次请求的 cost-quality tradeoff

而这篇 paper 真正要解决的是：

> **一个 agent run 有很多步 LLM 调用，总预算固定，贵模型额度有限，应该优先给哪些步骤？**

这类问题是：
- `multi-step`
- `stateful`
- `budget-constrained`
- 要考虑步骤之间价值不一样

所以这篇 paper 不应该再把自己讲成泛泛的“又一个 Agent OS”或者“又一个 router”，而应该讲成：

> **一种面向 multi-step coding agents 的 utility-governance layer**  
> 核心任务不是替代底层 router，而是让 agent framework 把 workflow 的价值结构、预算约束和评估口径显式交给运行时，使模型选择变成可解释、可审计、可复现的预算内效用分配。

这就是它相对云端 auto-routing 的独立性。

### 1.1 更强的 challenge：Cursor / opencode 也有 auto model，这还成立吗？

仍然成立，但需要把对手从“云端 per-query router”扩展到“IDE / coding-agent 产品里的 auto model selection”。

Cursor 的 Auto 会在请求级别或子任务级别自动选择模型，目标通常是平衡 intelligence、cost、reliability。opencode 也支持按 agent / subagent 配置模型，并且社区已经在讨论按 task type 或 model tier 做动态模型选择。这说明：**自动选模型已经是产品趋势**，不能把“会自动路由”本身当作本文贡献。

因此本文的立论必须更精确：

> 本文不是提出“IDE 里也要有 auto model selection”，而是研究这种 auto selection 背后缺失的一个可解释契约：**agent framework 如何声明每一步的用户效用、预算边界和 grader，使运行时在固定预算下最大化 workflow 级有效效用。**

换句话说，Cursor / opencode 的 auto model 更像一个产品策略或隐藏 heuristic；本文要研究的是它应该优化的系统问题：

- 一个 agent run 里有多个步骤，而不是一次孤立请求；
- 总预算是 hard constraint，而不是模糊的“尽量省”；
- 不同步骤的 user utility 不同，需要显式 `utility contract`（例如 $w_i$、`task_type`、grader、预算）；
- 决策应该能被日志、grader、QWCR / Q/$ / Pareto 复现实证；
- 策略不应只回答“这步用哪个模型”，还要回答“有限预算应该优先买哪几步的高质量”。

所以，IDE auto model 的存在不是否定本文，反而说明这个问题已经有现实需求。本文的 niche 是把这种产品直觉形式化为一个开放的 utility/budget contract，并提供一个无需训练、可审计的治理层。

---

## 2. Paper 的最稳定位：不是另一个 BAAR，而是 utility governance layer

我建议你把定位收成两层：

- **主轴**：workflow-level utility/budget governance
- **应用落点**：software engineering / coding agents

不建议继续把 “Agent OS” 当主卖点。`Agent OS` 可以保留为系统 flavor，但不能再当论文主 claim。原因很简单：

1. `Agent OS` 太宽，容易和 AIOS、AgentRM、AgentCgroup 混在一起。
2. 真正让你有新意的，不是“像 OS 一样管理资源”，而是**把 agent workflow 的效用结构、预算约束和评估口径显式化成一个可执行 contract**。
3. 如果投 SE 方向，评审更容易接受“成本治理 + 可解释策略 + benchmark grader + 实证”这条线，而不是宽泛系统愿景。
4. 与 Budget-Aware Agentic Routing (BAAR) 相比，本文不能只说“我们也做 multi-step budget routing 但不用 RL”。更稳的差异是：BAAR 学一个 router；本文定义 router 上层的 utility contract、审计日志和评估框架，并给出一个 training-free reference policy。

更直接一点说，这篇 paper 最合适的 claim 不是：

> 我们提出一个新的 Agent OS。

而是：

> 我们提出一种无需训练、可审计的 workflow-level utility governance layer：agent framework 显式声明每一步的效用权重、任务类型、预算和 grader，运行时据此分配 LLM 花费，并记录每一美元换来的有效效用。

---

## 3. 核心问题定义：utility contract under budget

设一个 agent workflow 有 $N$ 个 turn。本文要求上层 agent framework 为每个 turn 暴露一个最小 `utility contract`，而不是让运行时从 prompt 里猜测重要性：

- $q_i(a_i)\in[0,1]$：该步最终质量，由 deterministic grader 或 mock oracle 评估
- $c_i(a_i)$：该步成本
- $w_i$：该步用户效用权重，由 agent framework / workload 声明
- `task_type`：决定 grader 和候选后端集合
- `priority`：interactive / batch 等体验上下文
- $B$：workflow 级总预算

最自然的目标函数就是：

$$
\max_{a_1,\dots,a_N}\sum_{i=1}^{N} w_i q_i(a_i)
\quad \text{s.t.}\quad
\sum_{i=1}^{N} c_i(a_i)\le B
$$

这里最重要的点不是数学本身，而是**系统契约终于说清楚了**：

- 不是每次 query 自己做最优
- 而是整个 workflow 在共享一个总预算
- 并且不同步骤的用户效用、grader 和失败代价由上层 agent 显式声明

这也是本文最核心的 conceptual move：**把 routing 从黑盒模型选择，提升为一个可声明、可审计、可评估的 workflow utility accounting 问题**。

---

## 4. 为什么这不是“又一个 router”

| 维度 | Per-query / IDE auto model | Budget-Aware Agentic Routing (BAAR) | 本文 |
|---|---|---|---|
| 核心对象 | 单次请求或子任务 | 学习一个 budget-aware sequential router | workflow utility/budget governance layer |
| 决策粒度 | 单条 query / subtask | agent trajectory 中每一步 cheap/expensive | agent framework 声明 contract，运行时分配预算并审计 |
| 预算对象 | 通常是“尽量省”或请求级 cost | strict per-task budget | workflow 级 hard budget + 每步 utility accounting |
| 任务价值 | 通常不显式暴露 | 隐式从轨迹和 reward 中学 | 显式 `utility contract`：$w_i$、`task_type`、grader、priority |
| 方法风格 | 产品 heuristic / predictor | BoSFT + BoPO + budget-constrained decoding | training-free reference policy + 可插拔 governance framework |
| 评估重点 | 响应质量、成本、可靠性 | cost-success frontier | QWCR、WQ/$、Pareto、per-step audit log、grader-grounded utility |
| 与本文关系 | 可作为底层 per-call executor | 可作为一个 learned `ModelSelectionRule` | 本文提供更外层的 contract、日志和评估口径 |

一句话总结：

> per-query routing 解决的是“这一题用谁答”；BAAR 解决的是“如何训练一个预算感知 router”；本文解决的是“agent framework 如何声明 workflow 效用结构，并让运行时在 hard budget 下透明地花钱、记账和评估”。

---

## 5. 最核心的设计直觉

这篇 paper 最值得保留的数学只有两个东西；但要注意，数学服务的是 **utility accounting**，不是为了宣称我们发明了一个最优 router。

### 5.1 目标函数

就是上面的预算约束质量最大化：

$$
\max \sum_i w_i q_i
\quad \text{s.t.}\quad
\sum_i c_i \le B
$$

### 5.2 一个足够直观的排序准则

如果 expensive 相比 cheap 的增益为：

$$
\Delta q_i = q_i(\text{expensive}) - q_i(\text{cheap}),\qquad
\Delta c_i = c_i(\text{expensive}) - c_i(\text{cheap})
$$

那么最自然的优先级分数是：

$$
\text{score}(i)=\frac{w_i\Delta q_i}{\Delta c_i}
$$

含义很简单：

- $\Delta q_i/\Delta c_i$：多花 1 美元，这步能多涨多少质量
- 再乘 $w_i$：关键步骤的质量提升更值钱

这就足够支撑一个 training-free reference policy 的直觉了。

`budget_factor` 只需要被解释为：

> 一个在线预算松紧反馈信号。花得太快就更保守，花得太慢就更激进。

不需要把它写成太重的理论对象。最多一句话补充：

> 在理想化连续情形下，它可被理解为预算边际价值的工程近似。

这已经够了。

更重要的是，每次决策都应该落到审计日志里：

- 这个 turn 的 $w_i$ 是什么；
- 当前预算状态是什么；
- 选择贵模型的 $\Delta q_i / \Delta c_i$ 依据是什么；
- 最终 grader 给了多少 $q_i$；
- 这一步贡献了多少 $w_i q_i$ 和 WQ/$。

这部分是本文区别于纯 routing paper 的关键：**我们不仅要选模型，还要把“为什么这样花钱、花完换来多少效用”记清楚。**

---

## 6. 质量到底怎么衡量？这个口径客观吗？

这是导师 challenge 里最关键的点之一，而且我认为你现在的方向是对的：

> **不要自己拍脑袋定义“质量”，优先复用社区已接受的 deterministic grader。**

对 software engineering / coding agent 任务，最稳的说法是：

- `code_generation`：编译、执行、单测通过率
- `bug_fix`：SWE-bench / SWE-bench Verified 风格的 `FAIL_TO_PASS + PASS_TO_PASS`
- `transform`：schema / 格式校验
- `retrieval`：命中正确答案或关键字段

所以文中可以明确写：

> 本文不主张作者主观打分；在软件工程场景下，quality 优先由 benchmark-style deterministic graders 定义。

这个表述的好处是三重的：

1. **客观**：同输入同输出，同一 grader 会给同一分数。
2. **社区认可**：HumanEval、MBPP、SWE-bench、SWE-bench Verified 都是标准基线。
3. **可复现**：结果不依赖 LLM-as-judge 的漂移。

### 6.1 最稳的写法

建议你把 quality 分成两层：

**决策侧**：
- 决策时用的是 prior / proxy / 历史估计
- 不是本次真实 ground-truth quality

**评估侧**：
- 评估时用 deterministic grader 得到真实 $q_i$
- 再计算 QWCR、Q/$、WQ/$

这能避免别人说你“决策时偷看答案”。

### 6.2 可以直接写进文档的一句硬话

> 对 coding-agent workloads，本文采用 benchmark-grounded quality measurement：例如 HumanEval/MBPP 风格的 test-based grading，以及 SWE-bench Verified 风格的 fail-to-pass and pass-to-pass verification。因而 quality 并非作者主观定义，而是由可重复执行的 correctness criteria 决定。

### 6.3 也要主动承认一个边界

跨 task type 的质量分数不是完美同尺度的，所以最稳的说法是：

- 主指标报告整体 QWCR / Q/$ / WQ/$
- 附加报告按 task type 分组结果
- 固定 workload 的 task-type mix

这样更诚实，也更像 SE paper。

---

## 7. 这篇 paper 的系统抽象应该保留到什么程度？

保留，但要变成**为目标函数服务**，而不是自己喧宾夺主。

### 推荐的系统分层

| 组件 | 角色 |
|---|---|
| `UtilityContract` | agent framework 声明每步 $w_i$、`task_type`、grader、priority、预算 |
| `Governor` | 保证预算、RPM、并发等硬约束成立 |
| `ModelSelector` | 在约束内分配质量-成本方案；可以是本文启发式，也可以替换成 BAAR 这类 learned router |
| `UtilityLedger` | 记录每步花费、质量、$w_iq_i$、WQ/$，支持审计和复现实验 |
| `ZombieDetector` | 截断“成本涨、有效质量几乎不涨”的无效调用 |
| `Preemption` | 尽量保护 interactive 体验，但不打破预算硬约束 |

这里最重要的重写是：

- `UtilityContract` 和 `UtilityLedger` 是区别于 BAAR 的关键：本文不只是给出一个 router，而是定义 workflow 级效用如何声明、执行、记账和评估
- `Governor` 不是主贡献，而是让优化问题 `well-defined`
- `ModelSelector` 是可插拔执行器，不一定非要用本文启发式；BAAR 可以被视为一个 learned `ModelSelectionRule`
- `ZombieDetector` 和 `Preemption` 是防止“烂账污染评价”的辅助机制

也就是说，这篇 paper 的主叙事应该是：

> **预算下用户效用治理**

而不是：

> **系统稳定性治理**

---

## 8. Related Work 应该怎么讲

不要再平均用力。Related work 只需要分三类。

### 8.1 Per-query routing

- `RouteLLM`
- `CARROT`
- `OmniRouter`

这类工作主要研究：
- 单条 query 选模型
- cost-quality tradeoff
- 有的有全局约束，但仍是对 query distribution 的分配

它们是本文的**上游邻居**，但不是同一个问题。

### 8.2 Agentic routing with training / RL

- `Budget-Aware Agentic Routing`
- `xRouter`

这类工作最接近你，因为它们也承认 multi-step budgeted routing 是独立问题。  
但本文必须把差异讲得更深，而不是只说“不用 RL”：

- 它们主要贡献是**训练一个 router policy**，解决 sparse reward、always-small collapse、strict budget decoding 等学习问题；
- 本文主要贡献是**定义 workflow utility contract + runtime governance + utility accounting**；
- BAAR 可以被放进本文系统里，作为一个 learned `ModelSelectionRule`；
- 本文的 reference policy 是无需训练、可解释、即时部署的 baseline，而不是要在算法层面全面替代 BAAR。

这组是最直接相关工作，但更准确的关系是：**BAAR 是 router-level 方法，本文是 router 上层的治理与评估框架**。

### 8.3 OS-inspired agent systems

- `AgentRM`
- `AgentCgroup`
- `AIOS`

这类工作主要是：
- 稳定性
- 资源隔离
- 上下文/内核服务

它们可以放进 related work，但不应该再被写成你的正面对手。因为它们研究的不是“预算下质量分配”。

---

## 9. 一张最该放进 concept doc 的对比表

| 工作 | 核心对象 | 是否 multi-step | 是否 hard budget | 是否显式任务价值 | 方法风格 | 与本文关系 |
|---|---|---|---|---|---|---|
| RouteLLM / CARROT | 单条 query | 否 | 弱或无 | 否 | router / predictor | per-query baseline |
| OmniRouter | query distribution | 否 | 有 | 否 | constrained optimization | 全局约束但非 workflow |
| Budget-Aware Agentic Routing | agent trajectory router | 是 | 是 | 隐式 | RL / BoPO | router-level 最近邻；可作为本文的 learned selector |
| AgentRM / AgentCgroup / AIOS | 系统资源管理 | 否 | 非核心 | 否 | OS-inspired systems | 平行工作 |
| **本文** | workflow utility contract + budget governance | **是** | **是** | **是，$w_i$ + grader + ledger** | **training-free reference policy + 可审计治理层** | — |

这张表已经足够把整个定位打稳。

---

## 10. 这篇 paper 最适合的 claim

我建议你最后把 claim 收敛成下面这几句，而不是再发散。

### 主 claim

> 我们提出一个面向 multi-step coding agents 的 workflow-level utility governance framework，使 agent framework 能声明每一步的效用、预算和 grader，并让运行时在固定预算下透明地最大化有效用户效用。

### 方法 claim

> 方法核心不是训练一个新 router，而是定义 `UtilityContract + Governor + ModelSelector + UtilityLedger`。其中 ModelSelector 可以使用本文的无需训练边际效用启发式，也可以替换成 BAAR 这类 learned router。

### 评估 claim

> 在 benchmark-grounded workloads 上，我们使用 deterministic graders 衡量 task quality，并以 QWCR、Q/$、WQ/$、Pareto 与 per-step utility ledger 比较不同策略。

### 边界 claim

> 本文不试图解决通用的重要性推断问题，也不把 Agent OS 的全部系统问题都纳入；它聚焦于 workflow-level utility contracts and accounting under budget。

---

## 11. 建议的 RQ

不需要太多，三条就够。

### RQ1

如果没有显式 utility contract 和 ledger，agent workflow 的质量-成本评估是否会变得不可解释、不可复现？

### RQ2

在相同预算下，显式任务效用 $w_i$ 与边际效用分配是否能提升有效用户效用？

### RQ3

Zombie truncation 与体验保护机制是否能减少无效成本，并改善 utility-cost Pareto？

---

## 12. 这篇文档应该故意不做什么

为了让 concept 足够 solid 且可读，我建议这个版本**故意不做**下面几件事：

- 不把 `budget_factor` 展开成太长的理论推导
- 不把 timeout、failover、circuit breaker 写成大段系统设计文档
- 不把所有 possible signals 都展开成长 taxonomy
- 不把 `Agent OS` 愿景写得比核心问题还大
- 不把本文写成“我们比 BAAR 训练得更好”。这不是本文的战场；本文的战场是 contract、governance、accounting、auditability

因为这些都会削弱主线。

---

## 13. 最终建议：你这篇 paper 到底应该怎么自我介绍

如果我要替你向导师或评审介绍，我会用下面这个版本：

> 这篇 paper 研究的是 multi-step coding agents 的预算内用户效用治理问题。与 Cursor Auto 或云端 auto-routing 不同，它不是只给单条请求选模型；与 Budget-Aware Agentic Routing 不同，它也不是主要训练一个 learned router。本文要求 agent framework 显式声明 workflow-level utility contract，包括每一步的效用权重、任务类型、预算和 grader。运行时据此在 hard budget 下分配 LLM 花费，并通过 utility ledger 记录每一步为什么花钱、花了多少、最终 grader 得到多少有效质量。本文的 reference policy 是无需训练的边际效用启发式，但系统本身允许替换为 BAAR 这类 learned selector。质量评估不依赖主观打分，而是尽量落到 software engineering 社区已接受的 deterministic graders，如 test-based grading 和 SWE-bench 风格验证。本文的贡献不在于提出一个泛化的 Agent OS 愿景，也不在于和 RL router 比拼训练算法，而在于把 workflow-level utility-under-budget 这个治理问题定义清楚，并给出一个轻量、可审计、可实证验证的系统层。

---

## 14. 一句收尾判断

**你的 paper 是合理的，但前提是别把它写成“另一个 budget-aware agentic router”，而要写成“router 上层的 workflow utility contract and governance layer”。**

这层一旦说清楚，paper 就站得住。
