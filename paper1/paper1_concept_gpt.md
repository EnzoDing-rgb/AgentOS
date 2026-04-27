# AgentOS Paper 1 Concept (GPT Version)

> **一句话**：这篇 paper 研究的不是“单条请求该路由到哪个模型”，而是**一个 multi-step agent workflow 在固定预算下，如何把贵模型额度分配给最值得的步骤，从而最大化有效任务质量**。

> **建议主定位**：`workflow-level budget-constrained quality optimization for coding agents`

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

> **一种面向 multi-step coding agents 的 budget allocation system**  
> 核心任务是在工作流级别做质量-成本分配，而不是只在单次 query 级别做模型选择。

这就是它相对云端 auto-routing 的独立性。

---

## 2. Paper 的最稳定位

我建议你把定位收成两层：

- **主轴**：workflow-level budget-constrained quality optimization
- **应用落点**：software engineering / coding agents

不建议继续把 “Agent OS” 当主卖点。`Agent OS` 可以保留为系统 flavor，但不能再当论文主 claim。原因很简单：

1. `Agent OS` 太宽，容易和 AIOS、AgentRM、AgentCgroup 混在一起。
2. 真正让你有新意的，不是“像 OS 一样管理资源”，而是**把 agent workflow 建模成预算下的质量分配问题**。
3. 如果投 SE 方向，评审更容易接受“成本治理 + 可解释策略 + benchmark grader + 实证”这条线，而不是宽泛系统愿景。

更直接一点说，这篇 paper 最合适的 claim 不是：

> 我们提出一个新的 Agent OS。

而是：

> 我们提出一种无需训练、可解释的 workflow-level budget allocation 方法，用于在多步 agent 执行中最大化质量 under budget。

---

## 3. 核心问题定义

设一个 agent workflow 有 $N$ 个 turn。每个 turn $i$ 可以选择一个后端或一个质量-花费方案 $a_i$。

- $q_i(a_i)\in[0,1]$：该步最终质量
- $c_i(a_i)$：该步成本
- $w_i$：该步任务价值权重
- $B$：总预算

最自然的目标函数就是：

$$
\max_{a_1,\dots,a_N}\sum_{i=1}^{N} w_i q_i(a_i)
\quad \text{s.t.}\quad
\sum_{i=1}^{N} c_i(a_i)\le B
$$

这里最重要的点不是数学本身，而是**问题对象终于说清楚了**：

- 不是每次 query 自己做最优
- 而是整个 workflow 在共享一个总预算
- 并且不同步骤的价值并不相同

这也是本文最核心的 conceptual move。

---

## 4. 为什么这不是“又一个 per-query router”

| 维度 | 云端 auto-routing / RouteLLM / CARROT / OmniRouter 一类 | 本文 |
|---|---|---|
| 决策粒度 | 单条 query | 整个 workflow 的多个 turn |
| 状态 | 近似无状态 | 有状态，跟踪剩余预算和 burn rate |
| 预算对象 | 单次请求 cost tradeoff 或 query distribution | 单个 agent run 的 hard budget |
| 任务价值 | 通常不显式建模 | 显式建模 $w_i$ |
| 目标 | 给这次请求选一个合适模型 | 把贵模型额度分给最值得的步骤 |
| 是否需要训练 | 很多方法需要训练或预测器 | 本文主张可解释启发式，无需训练 |

一句话总结：

> per-query routing 解决的是“这一题用谁答”；本文解决的是“一个多步任务里，有限的好额度留给谁”。

---

## 5. 最核心的设计直觉

这篇 paper 最值得保留的数学只有两个东西。

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

这就足够支撑 ModelSelector 的直觉了。

`budget_factor` 只需要被解释为：

> 一个在线预算松紧反馈信号。花得太快就更保守，花得太慢就更激进。

不需要把它写成太重的理论对象。最多一句话补充：

> 在理想化连续情形下，它可被理解为预算边际价值的工程近似。

这已经够了。

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
| `Governor` | 保证预算、RPM、并发等硬约束成立 |
| `ModelSelector` | 在约束内分配质量-成本方案 |
| `ZombieDetector` | 截断“成本涨、有效质量几乎不涨”的无效调用 |
| `Preemption` | 尽量保护 interactive 体验，但不打破预算硬约束 |

这里最重要的重写是：

- `Governor` 不是主贡献，而是让优化问题 `well-defined`
- `ModelSelector` 才是 Paper 1 的主角
- `ZombieDetector` 和 `Preemption` 是防止“烂账污染评价”的辅助机制

也就是说，这篇 paper 的主叙事应该是：

> **预算下质量最大化**

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
但你的差异点很清楚：

- 它们走 RL / policy learning
- 你走 optimization-inspired heuristic
- 你更强调无需训练、可解释、即时部署

这组是你最直接的竞争对手。

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
| Budget-Aware Agentic Routing | agent trajectory | 是 | 是 | 隐式 | RL / BoPO | 最直接竞争者 |
| AgentRM / AgentCgroup / AIOS | 系统资源管理 | 否 | 非核心 | 否 | OS-inspired systems | 平行工作 |
| **本文** | agent workflow budget allocation | **是** | **是** | **是，$w_i$** | **可解释启发式** | — |

这张表已经足够把整个定位打稳。

---

## 10. 这篇 paper 最适合的 claim

我建议你最后把 claim 收敛成下面这几句，而不是再发散。

### 主 claim

> 我们提出一个面向 multi-step coding agents 的 workflow-level budget allocation framework，在固定预算下最大化有效任务质量。

### 方法 claim

> 方法核心是一个无需训练、可解释的 budget-aware model selection heuristic：它结合任务价值权重、边际质量增益与在线预算反馈进行分配。

### 评估 claim

> 在 benchmark-grounded workloads 上，我们使用 deterministic graders 衡量 task quality，并以 QWCR、Q/$、WQ/$ 与 Pareto 分析比较不同策略。

### 边界 claim

> 本文不试图解决通用的重要性推断问题，也不把 Agent OS 的全部系统问题都纳入；它聚焦于 workflow-level quality allocation under budget。

---

## 11. 建议的 RQ

不需要太多，三条就够。

### RQ1

在没有治理的情况下，预算、限流和并发失控是否会使质量-成本评估失真？

### RQ2

在相同预算下，任务价值感知的 budget-aware model selection 是否能提升有效质量产出？

### RQ3

Zombie truncation 与体验保护机制是否能减少无效成本，并改善质量-成本 Pareto？

---

## 12. 这篇文档应该故意不做什么

为了让 concept 足够 solid 且可读，我建议这个版本**故意不做**下面几件事：

- 不把 `budget_factor` 展开成太长的理论推导
- 不把 timeout、failover、circuit breaker 写成大段系统设计文档
- 不把所有 possible signals 都展开成长 taxonomy
- 不把 `Agent OS` 愿景写得比核心问题还大

因为这些都会削弱主线。

---

## 13. 最终建议：你这篇 paper 到底应该怎么自我介绍

如果我要替你向导师或评审介绍，我会用下面这个版本：

> 这篇 paper 研究的是 multi-step coding agents 的预算内质量分配问题。与云端 auto-routing 不同，它不是给单条请求选模型，而是在整个 workflow 内决定哪些步骤值得使用更贵、更强的模型。我们把问题形式化为 budget-constrained quality maximization，并提出一个无需训练、可解释的启发式策略，结合任务价值权重、边际质量增益和在线预算反馈进行分配。质量评估不依赖主观打分，而是尽量落到 software engineering 社区已接受的 deterministic graders，如 test-based grading 和 SWE-bench 风格验证。本文的贡献不在于提出一个泛化的 Agent OS 愿景，而在于把 workflow-level quality-under-budget 这个问题定义清楚，并给出一个足够轻量、可部署、可实证验证的解法。 

---

## 14. 一句收尾判断

**你的 paper 是合理的，但前提是别把它写成“云端 router 的替代品”，而要写成“云端 router 没有覆盖的 workflow-level budget allocation 层”。**

这层一旦说清楚，paper 就站得住。
