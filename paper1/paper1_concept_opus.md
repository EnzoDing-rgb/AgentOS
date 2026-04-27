# AgentOS: A Workflow-Aware, Training-Free Runtime for Cost-Quality Optimization in Multi-Agent LLM Systems

> **一句话**：给定固定预算和一系列 LLM 调用，如何把钱花在刀刃上——让高价值步骤用好模型、低价值步骤用便宜模型、僵尸调用及时止损？
>

---

## 0. 定位：这篇论文在解决什么问题？

### 背景：现在已经有很多 auto-routing 了

今天的开发者已经被各种"自动选模型"功能包围：

- **Cursor Auto / OpenCode Auto**：在多步 agent workflow 中，对每次 LLM 调用自动选模型
- **OpenAI GPT-5 Auto**：在聊天端自动在 Instant / Thinking 间切换
- **LiteLLM Auto Router / Cloudflare Dynamic Routing**：基于规则或 embedding 的 per-query 路由
- **学术 router**：RouteLLM、CARROT、OmniRouter（训练一个预测器来估计 per-query 性价比）
- **RL-based agentic router**：Budget-Aware Agentic Routing（BoPO）（用强化学习训练路由策略）

它们都在回答同一个问题："**这一次** LLM 调用该用哪个模型？"

本文不和它们抢这个问题。本文回答的是更上一层的问题：

> **在一个甚至多个完整的 agent workflow（每个 workflow 包含多步 LLM 调用）中，如何利用 workflow 级的结构信息（哪一步关键、剩多少预算、多个 workflow 怎么共享资源），做整体的成本-质量分配？**

### 真正的 gap：现有 auto-router 都是 workflow-blind 的

下面给出两个可操作定义：

- **workflow-aware**：路由决策会显式使用 workflow 级信息，例如：这一步是否关键（$w_i$，由 agent 每次调用时声明）、本 workflow 还剩多少预算、当前花钱速度是否合理、同一时间有多少 workflow 在共享并发/RPM 资源。**不需要提前知道 workflow 总共有多少步**——$w_i$ 是逐步声明的，budget_factor 是闭环反馈的。
- **workflow-blind**：路由决策主要依赖本次调用的局部信息（prompt/token/延迟），不显式接收上述 workflow 级信号，因此无法做跨步骤预算配速或跨 workflow 调度。

| 它们看得到 | 它们看不到（但上层 agent 自己知道） |
|-----------|----------------------------------|
| 当前这次 prompt 的内容、长度、复杂度 | **这一步是 planning / generation / validation 中哪种**（agent 发起调用时声明） |
| 模型成本与能力差异 | **这一步有多关键**（$w_i$，agent 发起调用时声明，不需要知道总步数） |
| 大致 latency 和 token 消耗 | 错在 planning 比错在 validation 代价大——因为 planning 错了后续步骤会沿着错误方向继续 |
| 用户订阅 tier | 整个 task 的预算上限是 \$0.50 |
| | 到目前为止已花 \$0.40，剩余预算只够便宜模型（budget_factor 实时追踪，不需要预测总步数） |
| | 现在有 50 个 workflow 在并发抢 RPM 配额 |

**这不是 Cursor Auto 不努力，是架构上"看不到"**——agent workflow 的步骤价值结构（哪一步关键、错了下游代价多大）和预算消耗状态，是**上层 agent 框架的私有信息**，闭源黑盒 router 拿不到，per-query 学术 router 也设计上不接收这个信号。

### 和 BoPO（Budget-Aware Agentic Routing）有什么不同？

BoPO（Zhang et al. 2026, arxiv:2602.21227）是目前和本文最接近的工作——它也做 agent workflow 内的多步路由，也考虑预算约束。但两者在设计理念上有 4 条根本差异：

> **前置知识**：BoPO 把路由问题建模为"受约束的马尔可夫决策过程"（CMDP），用强化学习（RL）去学一个路由策略。所谓"二元后端"是指它只在 cheap model 和 expensive model 之间做二选一。

| 维度 | 本文（AgentOS） | BoPO |
|------|----------------|------|
| **后端数量** | N-ary（任意多个模型，如 GPT-5 Thinking / Instant / mini / Claude / 本地 Llama） | 二元（只在一个 cheap 和一个 expensive 之间切换） |
| **训练需求** | **零训练**——启发式规则 + 闭环反馈，安装即可用 | 需要先 SFT（监督微调）再 RL（强化学习），训练成本不低 |
| **Workflow 范围** | 支持**多个 workflow 并发**共享资源池 | 只处理单个 task 的路由 |
| **路由信号** | 显式 $w_i$（agent 框架声明每一步的重要性） | 稀疏 RL 奖励（只在任务结束时才知道做得好不好） |

**两者是互补的，不是替代关系**。BoPO 能学到更精细的路由策略（如果愿意付训练成本），本文提供开箱即用的系统运行时。本文的 ModelSelector 接口设计上支持把 BoPO 的 RL 策略接入——详见 §4.1 和附录 C。

### 本文的定位：agent 框架与 LLM 后端之间的 workflow-aware 治理中间层

```
Agent 框架（SWE-agent / Cursor / MetaGPT）
    │  声明 workflow 结构：w_i, 预算 B, task_type, ...
    ▼
═══════ AgentOS（本文）═══════       workflow-aware 成本-质量分配
    │  基于 w_i · Δq_i / Δc_i + budget_factor
    ▼
Per-call router（Cursor Auto / GPT-5 Auto / RouteLLM）   可选的单次调用路由
    │
    ▼
LLM 后端池（GPT-5 Thinking / Instant / mini / Claude / 本地 Llama）
```

**一句话**：Cursor Auto 是 AgentOS 的下游（最终执行单次调用），不是竞争者。AgentOS 把上层 agent 的私有信息（workflow 价值 + 预算状态）接进来用上——这正是 per-call router 设计上做不了的事。

| 维度 | Cursor Auto / GPT-5 Auto / RouteLLM / CARROT | BoPO | **本文** |
|------|---------------------------------------------|------|---------|
| 路由信号 | 单次 prompt 内容 | RL 奖励信号 | prompt + **workflow 位置 ($w_i$)** + 预算状态 |
| 后端选择 | N-ary 但 per-call | 二元 | **N-ary + workflow-aware** |
| 跨步骤预算 | 无 | 单 task 内有 | **多 workflow 跨步骤 + 跨 workflow** |
| 训练需求 | 需训练（CARROT/RouteLLM）或无（Cursor） | SFT + RL | **零训练** |
| 止损 | 无 | 无 | 僵尸检测 + 截断 |
| 多 workflow 并发 | 无 | 无 | **admission control + 公平调度** |

### 谁会真正用这个？

- **Agent 框架开发者**（SWE-agent / MetaGPT / Cursor 自身）：在框架内集成 AgentOS，把 workflow 结构通过 $w_i$ 暴露给运行时
- **企业多 agent 部署**：比如字节跳动同时跑 50 个 agent 处理不同需求，共享 API 配额和预算——AgentOS 做跨 workflow 的公平调度
- **研究者跑 SWE-bench 评估**：50 个 SWE-agent 并发跑 SWE-bench Verified，固定总预算，AgentOS 确保每个 agent 都拿到合理份额
- **个人开发者**：即使 1 个 agent 6 步，"该把哪步推到多好"仍是核心决策

---

## 1. 核心洞察：LLM 质量是连续的，调度问题变了

经典操作系统调度假设任务结果是二元的——完成或失败。LLM 不同——**几乎总能给答案，差别在于答案好坏**：

| 后端配置 | 质量 $q$ | 每次调用成本 | 说明 |
|---------|---------|------------|------|
| GPT-5 Thinking + 长 context | $\approx 0.95$ | \$0.10 | 最强但最贵 |
| GPT-5 Instant | $\approx 0.70$ | \$0.01 | 快速但质量一般 |
| Claude Sonnet | $\approx 0.80$ | \$0.03 | 中间档 |
| Llama-3-70B-Int4（本地） | $\approx 0.55$ | \$0.002 | 成本极低，质量有限 |
| GPT-5 mini | $\approx 0.40$ | \$0.001 | 最便宜 |

五种都"完成"了任务，但质量在 $[0,1]$ 上连续变化。于是调度问题从"谁先跑"变成：

> **预算有限时，每个步骤应该被做到多好？**

注意这里有 5 个后端可选，不是 2 个——这就是"N-ary"。后端越多，分配越精细，但决策空间也越大。BoPO 只处理二元（cheap vs expensive），我们支持任意多个。

---

## 2. 形式化：预算约束下的质量最大化

### 2.1 单 workflow 场景

一个 workflow 有 $N$ 个 turn（每个 turn 是一次 LLM 调用）。每个 turn $i$ 选一个后端 $a_i \in \mathcal{A}$（后端池，如上表 5 个选项）：

$$
\max_{a_1,\dots,a_N}\ \sum_{i=1}^{N} w_i\,q_i(a_i)\quad \text{s.t.}\quad \sum_{i=1}^{N} c_i(a_i)\le B
$$

各符号含义：
- $q_i(a_i) \in [0,1]$：turn $i$ 选后端 $a_i$ 时的输出质量（由 benchmark grader 打分，见 §3）
- $c_i(a_i)$：对应的美元成本
- $w_i$：任务价值权重——**由调用方声明**（如 planning 步 $w=3$ 表示"这步很关键"，retrieval 步 $w=1$ 表示"不太关键"）
- $B$：总预算硬约束
- $\mathcal{A}$：可用后端集合（N-ary，不限于二元）

这个问题本质是"多选择背包"的变体：每个 turn 是一个物品，有多种"装法"（选哪个后端），每种装法有不同的收益（$w_i \cdot q_i$）和体积（$c_i$），背包容量是预算 $B$。

### 2.2 多 workflow 场景（本文扩展）

实际部署中，多个 workflow 往往同时运行、共享资源。设有 $J$ 个并发 workflow，第 $j$ 个 workflow 有自己的 turn 集合 $W_j$ 和预算 $B_j$：

$$
\max \sum_{j=1}^{J} \sum_{i \in W_j} w_{j,i}\,q_{j,i}(a_{j,i}) \quad \text{s.t.}\quad
\begin{cases}
\sum_{i \in W_j} c_{j,i}(a_{j,i}) \le B_j & \forall\, j \\
\text{RPM}(t) \le R_{\max} & \text{（全局每分钟请求数限制）} \\
\text{Concurrency}(t) \le K_{\max} & \text{（全局并发槽限制）}
\end{cases}
$$

> **前置知识**：RPM = Requests Per Minute，是 API 提供商对每分钟请求数的限制。并发槽是指同时在飞的请求数上限。这两个约束意味着不同 workflow 之间在**抢共享资源**，不能各自独立优化。

这就是为什么单纯的 per-task 路由（BoPO）不够用——它看不到"别的 workflow 也在抢 RPM 配额"这件事。

### 2.3 对照组

| 对照组 | 策略 | 失败模式 |
|--------|------|---------|
| A. `always_expensive` | 每步都用最贵模型 | 很快花光预算，后半段没钱 |
| B. `per_request_greedy` | 每步独立最大化 $q/c$ | 不做配速、不看 $w_i$，后期质量下降 |
| C. `budget_aware_uniform` | 有预算配速，但 $w_i \equiv 1$ | 不区分任务价值——关键步和琐碎步给同样资源 |
| **D. AgentOS** | 预算配速 + 任务价值 $w_i$ + 边际性价比 | 在线近似，非离线最优 |
| **E. `bopo_style_binary`** | 限制为二元后端 + 不用 $w_i$ | 模拟 BoPO 的输入条件（只有 cheap/expensive 两个选项） |

对照组 E 的意义：D vs E 的差异可以**直接归因于** N-ary 后端 + 显式 $w_i$ 信号的贡献。

### 2.4 最优性直觉（KKT 一阶条件）

> **前置知识**：KKT（Karush-Kuhn-Tucker）条件是带约束优化问题的一阶最优性条件。你可以把它理解为"约束版的导数等于零"——在最优解处，每个变量的"边际收益-边际成本"关系满足一个特定等式。

将问题推广为连续版（选质量水平而非离散后端），KKT 条件给出：

$$
\frac{w_i}{c_i'(q_i)} = \lambda \quad \text{（对所有内点 turn）}
$$

$\lambda$ 是预算约束的"影子价格"（shadow price）——它表示"再多 1 美元能换多少加权质量"。含义：**最优时，每个 turn 的"每美元加权边际收益"趋于同一个水位线**。

工程实现中 `budget_factor` 就是 $\lambda$ 的在线近似：花快了调高（更舍不得花）、花慢了调低（更敢花）。

**数学复杂度**：KKT 条件 + 凸优化基础，1-2 周可掌握。不需要 RL / bandit 理论。

### 2.5 边际加权性价比（ModelSelector 的排序准则）

$$
\text{score}(i) = \frac{w_i \cdot \Delta q_i}{\Delta c_i}, \quad \Delta q_i = q_i(\text{expensive}) - q_i(\text{cheap}), \quad \Delta c_i = c_i(\text{expensive}) - c_i(\text{cheap})
$$

**数字例子**：
- 任务 A（规划步）$w=3, \Delta q=0.20, \Delta c=\$2$ → score = 0.30
- 任务 B（检索步）$w=1, \Delta q=0.30, \Delta c=\$4$ → score = 0.075

B 的绝对质量提升更大，但"每 1 美元带来的加权提升"更小——**预算紧时贵模型应该留给 A**。

### 2.6 $w_i$ 如何声明？（工程实现）

**$w_i$ 不是 AgentOS 硬编码的，而是 agent 框架在每次调用时通过 API 传入的**——AgentOS 不猜任务重要性，由调用方告诉系统。这个设计与 Linux `nice` 值和 K8s `PriorityClass` 同理：调度器不推断进程/Pod 重要性，由用户声明。

采纳设计分 4 个渐进档位，集成程度越高收益越好，但**不集成也能跑**：

| 档位 | agent 框架做的事 | $w_i$ 来源 | 集成工作量 |
|------|----------------|-----------|----------|
| **L4 完整** | 每次调用直接传数值 | `agentos.chat(..., w_i=3.0)` | 最精细，agent 开发者自己定 |
| **L3 标准** | 每次调用传 `task_type` 字符串 | 系统查下方预置表 | 只需标"这是哪种步骤" |
| **L2 最小** | 区分 interactive vs batch | `interactive→2, batch→1` | 最低集成成本 |
| **L1 不集成** | 什么都不传 | $w_i \equiv 1$ | 退化到对照组 C，系统仍可运行 |

**L3 默认 $w_i$ 表**（本工作给出，用户可扩展覆盖）：

| task_type | 默认 $w_i$ | 说明 |
|-----------|----------|------|
| `planning`, `reasoning` | 3 | 错了则下游连错，代价最高 |
| `generation` | 2 | 主产出步骤 |
| `validation`, `transform`, `retrieval` | 1 | 局部影响，便宜模型通常够用 |
| `summarization`, `classification` | 1 | 通常不需要最强模型 |

**鲁棒性**：§3.5 消融实验 E1–E7 正面回答"权重不准怎么办"——粗粒度的 L3 映射仍有明显收益（E3），加噪 $\sigma=0.5$ 时收益基本保留（E4），完全无信号时退化到 C 而非崩溃（E6）。权重越精细收益越高，但"分不准"不是致命问题。

---

## 3. 质量怎么衡量？（回应导师 Challenge）

**导师质疑**：质量 $q_i$ 凭什么说好就好？你自己定义的分数别人认可吗？

**回答**：不自己发明评分标准——**复用社区已经广泛认可的 benchmark grader**。

### 3.1 评估策略：使用社区标准 Benchmark

"质量好不好"这个问题的权威性，不来自本文——来自这些 benchmark 社区已经背书过的标准：

| task_type | Benchmark | 评分方式 | 仓库 | GitHub Star | 出处 |
|-----------|-----------|---------|------|-------------|------|
| `bug_fix`（agentic SE） | **SWE-bench Verified** | fail-to-pass 测试（修复了就通过） | `princeton-nlp/SWE-bench` | 3k+ | ICLR 2024 |
| `code_generation` | **HumanEval** | pass@1（生成代码能跑通单测） | `openai/human-eval` | 3k+ | OpenAI Codex 论文，4000+ 引用 |
| `code_generation+` | **MBPP / BigCodeBench** | 功能单测通过率 | `google-research` / `bigcode-project/bigcodebench` | k+ each | NeurIPS / arXiv 2024 |
| `reasoning` | **GSM8K** | exact match（答案完全匹配） | `openai/grade-school-math` | 1k+ | OpenAI 2021 |
| `math` | **MATH** | exact match | `hendrycks/math` | 1k+ | NeurIPS 2021 |

### 3.2 为什么审稿人会接受这套 grader

三个理由：

1. **全部 deterministic**：同输入同输出，pass/fail 或 exact match——不存在"心情好多给几分"的问题。没有"用 LLM 评 LLM"的循环论证
2. **全部高度采纳**：OpenAI、Anthropic、Google 的公开模型评测全用这些 benchmark，GitHub 上都是几千 star 的项目
3. **不是我们发明的标准**：我们只是在这些权威 benchmark 上度量不同路由策略的 cost-quality trade-off。"质量好不好"的定义权在 benchmark 社区，不在本文

一句话："$q_i$ 的定义不是我们说了算，是 SE / reasoning 社区已经背书的。"

### 3.3 实验中的两种模式

| 模式 | $q_i$ 来源 | 用途 |
|------|-----------|------|
| **Mock 实验**（主线） | workload 预设的 `quality_score` | 控制变量：所有 policy 读同一张表，比的是"谁会分配预算"而不是"LLM 本身强不强" |
| **真实 LLM 实验**（补充） | 调用真 LLM + 上述 benchmark grader 打分 | 验证 mock 结论在真实模型上成立 |

Mock 的目的不是声称线上也有上帝视角，而是**把"分配策略好不好"从"先验估计准不准"里剥离开**——先证明策略本身有效，再验证端到端也有效。

### 3.4 决策侧 vs 评估侧（必须解耦）

> **前置知识**：任何智能系统都面临同一个问题——做决策时用的信息和事后评估用的信息不能是同一个。否则就是"开卷考"，证明不了任何东西。

- **决策时**：ModelSelector 用的是先验估计 $\Delta \hat{q}_i$（历史统计 / 静态表），不需要知道本次真实分数
- **评估时**：用 benchmark grader 得到真实 $q_i$，计算 QWCR / Q/\$ 等指标
- **类似做法**：推荐系统用预测点击率做决策、用实际留存率做评估——决策从不依赖 ground truth

### 3.5 先验不准怎么办？

RQ2 消融实验 E1–E7 正面回答：

| 实验 | 设置 | 回答什么 |
|------|------|---------|
| E1 Oracle | workload 参考权重 | 上限——先验完美时能做多好 |
| E2 二档 | high/low 两档 | 粗分（只分"重要/不重要"）也有收益 |
| E3 task_type 表 | 按类型固定权重 | 无精细标注也能落地 |
| E4 加噪 | $w_i$ + 噪声 $\sigma=0.3/0.5/1.0$ | 对权重误差鲁棒 |
| E5 随机 | 随机 $w_i$ | 最坏情况 |
| E6 全 1 | $w_i \equiv 1$ | 自洽检查：应退化到对照组 C |
| **E7 binary-backend** | 限制只有 cheap/expensive 两个后端 | 在 BoPO 同等输入条件下，启发式是否仍有优势 |

**结论**：权重越准收益越高；很粗糙时仍有收益；无信息时退化到 C。E7 专门回应 BoPO 对比——在同等二元条件下观察差异。

---

## 4. 系统架构：policy-agnostic 的 workflow-aware runtime

> **前置知识**：所谓 "policy-agnostic"，是指系统的基础设施（预算管控、限流、僵尸检测等）**不绑定任何特定的路由策略**。你可以换掉"怎么选模型"的部分，其他所有机制照常运行。这就像操作系统的调度器可以从 CFS 换成 FIFO，但文件系统、内存管理不受影响。

```
Agent Workflow（N 个 LLM 调用步骤）× J 个并发 workflow
        │
        ▼
═══════════════════ AgentOS ═══════════════════
│ 【约束层】Governor                           │  ← policy-agnostic
│   预算硬封顶 + API RPM 限流 + 并发准入        │
│   → 保证优化问题的约束成立                    │
│                                              │
│ 【优化层】ModelSelector（可插拔）             │  ← 只有这层是 routing policy
│   本文默认：边际加权性价比 + budget_factor    │
│   可替换为：BoPO RL policy / CARROT / ...    │
│   → 在线近似 max Σ w_i q_i s.t. budget      │
│                                              │
│ 【止损层】ZombieDetector + Preemption        │  ← policy-agnostic
│   僵尸截断 + 交互式任务抢占                   │
│   → 回收无效成本 + best-effort 体验          │
│                                              │
│ 【调度层】Multi-Workflow Scheduler           │  ← policy-agnostic
│   跨 workflow 公平调度 + admission control   │
│   → 多 workflow 共享资源不打架               │
═══════════════════════════════════════════════
        │
        ▼
LLM 后端池 → events.jsonl → 指标计算
```

**核心设计**：Governor / ZombieDetector / Preemption / Multi-Workflow Scheduler 这四层全部 policy-agnostic——**只有 ModelSelector 是 routing policy**。这意味着任何 routing policy（含 BoPO 的 RL 策略、CARROT 风格 predictor）都可以接入并共享所有系统机制。

| 机制 | 在优化问题中的角色 | BoPO 有吗？ | Per-call router 有吗？ |
|------|-------------------|------------|---------------------|
| **Governor** | 保证 $B$ 与限流约束硬成立 | 有 budget 约束，无 RPM/并发管控 | 无 |
| **ModelSelector** | 在线近似 $\max \sum w_i q_i$ s.t. budget | 用 RL 策略 | 用 per-call predictor |
| **ZombieDetector** | 截断"成本涨但质量不涨"的调用 | 无 | 无 |
| **Preemption** | 交互式任务抢占 batch 任务 | 无 | 无 |
| **Multi-Workflow Scheduler** | 跨 workflow 公平调度 | 无（单 task 设计） | 无 |

### 4.1 ModelSelector 可插拔接口

```python
class ModelSelectorPolicy(ABC):
    """所有路由策略的统一接口。
    Governor / Zombie / Preemption / Scheduler 不关心这里的实现。"""

    @abstractmethod
    def select(self, turn: TurnInfo, gov_state: GovernorState,
               backends: list[Backend]) -> Backend:
        """给定当前 turn 信息、Governor 状态、可用后端列表，返回选中的后端。"""
        ...
```

本工作实现了以下 4 个 policy：

| Policy | 说明 | 角色 |
|--------|------|------|
| `WorkflowAwareHeuristic` | 边际加权性价比 + budget_factor 配速（§2.5） | **主贡献** |
| `PerCallGreedy` | 每次独立最大化 $q/c$，不看 $w_i$ 也不配速 | baseline（对照组 B） |
| `BudgetAwareUniform` | 有配速但 $w_i \equiv 1$ | 消融用（对照组 C） |
| `CARROTStylePredictor` | per-call cost-quality predictor（模拟 CARROT 思路） | baseline |

`BoPOPolicy`（接入 BoPO 的 RL 策略）**留作 future work**——接口已就绪，需要 multi-GPU 训练资源来训练 RL 模型（详见附录 C）。

---

## 5. Multi-Workflow 并发调度

**三句话定义**：一个 workflow = 一个任务从开始到结束的一串 LLM 调用步骤。multi-workflow = 同一时间有很多个 workflow 在跑，它们共享同一组资源（RPM、并发槽、后端池、甚至全局预算）。因此系统除了要在“一个 workflow 内”分配预算，还必须在“不同 workflow 之间”做调度与公平性保证。

### 5.1 为什么需要这一层

现实部署中，多个 agent workflow 往往同时运行：

- 50 个 SWE-agent 并发跑 SWE-bench 评估
- 企业 DevOps 团队同时跑代码审查、测试生成、文档更新等 agent
- 多个用户共享同一个 LLM API 配额

它们共享有限的资源：API RPM 配额、并发槽、总预算。如果不做调度，先到先得——前面的 workflow 可能吃光资源，后面的饿死。

**BoPO 做不了这个**——它的 CMDP 是 per-task 的（一次只建模一个任务的路由决策），要处理多 workflow 并发需要重新设计整个 RL 训练框架。

### 5.2 调度算法：Weighted Fair Queuing

> **前置知识**：Weighted Fair Queuing（WFQ）是网络领域经典的公平调度算法。核心思想是：每个流（这里是 workflow）按权重分配带宽（这里是 RPM/并发槽），权重高的流获得更多资源，但不会完全饿死权重低的流。

本文的多 workflow 调度有三个组件：

1. **每 workflow 独立 budget tracker**：每个 workflow 有自己的预算 $B_j$ 和 budget_factor $\lambda_j$，互不干扰
2. **跨 workflow weighted fair queuing**：共享 RPM/并发槽按 workflow 的优先级（如 SLA 级别）加权分配
3. **Admission control**：当资源满载时，新到的请求排队或拒绝——不需要预测到达分布

数学复杂度：只用到 WFQ 和 admission control，**不引入** DRF（Dominant Resource Fairness）等高级公平性理论。

### 5.3 Workload 不确定性处理

> 审稿人可能会问：系统启动时不知道会有多少 workflow、每个 workflow 会有多少 turn，怎么办？

回答：**本系统不依赖 workload 预测，也不需要任何 ML 训练**——这是 "training-free" 主张的一部分。三种不确定性各有对应的处理方式：

| 不确定性 | 处理方式 | 为什么不需要 ML |
|----------|---------|---------------|
| 并发 workflow 数量未知 | Admission control：RPM/并发槽满了就排队 | 不需要预测到达分布——满了就不放进来 |
| 每 turn 的 cost/quality 未知 | 闭环 budget_factor 反馈：花快了收紧，花慢了放宽 | 不需要预测——反馈方向对就行 |
| 新 task_type 的 quality 先验冷启动 | EWMA 在线滚动更新 + 静态先验回退（§3.4） | 这是最简单的在线统计，不算"ML 训练" |

> **EWMA 前置知识**：Exponentially Weighted Moving Average（指数加权移动平均）——每看到一个新数据点，用一个衰减因子 $\alpha$ 把新值融入历史估计：$\hat{q}_{\text{new}} = \alpha \cdot q_{\text{observed}} + (1-\alpha) \cdot \hat{q}_{\text{old}}$。一行代码就能实现，几个数据点就能收敛到合理范围。

**Future work**：更复杂的 workload predictor（time-series forecasting / online bandit）可以作为 ModelSelector 的旁路输入接入（接口已预留），但本工作刻意不引入，以保持 training-free 主张的完整性。

---

## 6. 评估指标

### 6.1 单 workflow 指标

| 指标 | 公式 | 含义 |
|------|------|------|
| **QWCR** | $\frac{1}{N}\sum q_i$ | 平均质量（失败记 0） |
| **QW-Completed** | $\sum q_i$ | 有效产出总量 |
| **Q/\$** | $\sum q_i / \text{cost}$ | 每美元质量产出 |
| **WQ/\$** | $\sum w_i q_i / \text{cost}$ | 每美元加权质量产出 |
| **Pareto 图** | 横轴 cost, 纵轴 QW-Completed | 核心论证图——同样的钱谁干得更好 |

QWCR 与 Q/\$ 必须同时报告（防止"没花钱也没干活"导致 Q/\$ 虚高）。

### 6.2 多 workflow 指标（新增）

| 指标 | 公式 | 含义 |
|------|------|------|
| **Per-workflow QWCR / Q\$** | 每个 workflow 单独计算 | 检查是否有 workflow 被系统性饿死 |
| **Cross-workflow QWCR 方差** | $\text{Var}(\{\text{QWCR}_j\}_{j=1}^J)$ | 方差越小说明越公平 |
| **Jain's Fairness Index** | $\frac{(\sum_j x_j)^2}{J \cdot \sum_j x_j^2}$ 其中 $x_j$ 为 workflow $j$ 的 QWCR | 经典公平性指标，1 = 完全公平，$1/J$ = 最不公平 |

> **Jain's Fairness Index 前置知识**：这是网络和系统领域最常用的公平性度量（Jain et al. 1984，5000+ 引用）。值域 $[1/J, 1]$，越接近 1 表示各 workflow 获得的服务越均等。

---

## 7. 四条 RQ

| RQ | 问题 | 对应机制 | 核心指标 |
|----|------|---------|---------|
| **RQ1** | 不加治理时 429 限流雪崩，指标无法稳定测量 | Governor | error_429_rate, 完成率 |
| **RQ2**（主贡献） | 同预算下，任务价值感知的模型选择是否提升质量？ | ModelSelector | QWCR, WQ/\$, Pareto |
| **RQ3** | 僵尸调用和尾延迟是否污染指标？截断后改善多少？ | Zombie + Preemption | Q/\$ 提升, 违约率 |
| **RQ4**（新增） | 多 workflow 并发 + 共享资源 + 各自预算下，workflow-aware 启发式能否同时维持 (a) 整体 Pareto 前沿 (b) 跨 workflow 公平性？ | Multi-Workflow Scheduler | Jain's FI, QWCR 方差, 整体 Pareto |

RQ4 的 baseline：round-robin、FIFO、weighted-fair-queuing-without-budget-awareness。

---

## 8. Related Work

### 8.1 与 Budget-Aware Agentic Routing（BoPO）的详细对比

BoPO（Zhang et al. 2026）是和本文最接近的工作。两者的定位差异可以归纳为 4 个维度：

| 维度 | 本文（AgentOS） | BoPO | 影响 |
|------|----------------|------|------|
| **后端** | N-ary（5+ 模型） | 二元（cheap/expensive） | N-ary 允许更精细的 cost-quality 梯度 |
| **训练** | 零训练（启发式 + 闭环反馈） | SFT + RL（BoPO 训练） | 零训练意味着安装即用，无部署门槛 |
| **范围** | 多 workflow 并发 | 单 task | 多 workflow 是企业部署的基本需求 |
| **信号** | 显式 $w_i$（框架声明） | 稀疏 RL 奖励（任务结束才有反馈） | 显式信号可解释、可调试 |

**两者互补而非替代**：BoPO 通过 RL 训练可以学到更精细的路由策略（前提是愿意付训练成本和拥有训练资源），本文提供开箱即用、零训练成本的系统运行时。两者都可以接入本文的 ModelSelector 接口——BoPO 作为一个 policy 实现，共享 Governor / ZombieDetector / Scheduler 等系统基础设施。

### 8.2 Per-query LLM Routing

| 论文 | 方法 | 预算约束 | Multi-step | $w_i$ | 与本文关系 |
|------|------|---------|-----------|-------|-----------|
| **RouteLLM** (Ong et al. 2024) | 二元 router (strong/weak) | 无 | 无 | 无 | Per-call baseline |
| **CARROT** (Somerstep et al. 2025) | Cost-aware router, minimax 最优 | Per-query cost 预测 | 无 | 无 | Per-call baseline |
| **OmniRouter** (Mei et al. 2026) | 全局约束优化 router | 有（Lagrangian） | 无（独立 query） | 无 | 最接近的 per-query 对手 |
| **xRouter** (2025) | RL-based router | Cost-aware reward | 有（episode） | 隐式 | 方法论对手 |

这些工作优化的是"每次调用选哪个模型最划算"，不涉及 workflow 结构、跨步骤预算配速、多 workflow 调度。本文和它们是不同层次——AgentOS 可以在底层使用这些 per-call router 作为 ModelSelector 的实现之一。

### 8.3 OS-Inspired Agent 系统

| 论文 | 核心问题 | 与本文差异 |
|------|---------|-----------|
| **AgentRM** (arxiv:2603.13110) | 调度失败 + 上下文退化 | 侧重系统稳定性，不做 cost-quality 优化 |
| **AgentCgroup** (arxiv:2602.09345) | OS 级 CPU/内存资源隔离 | 不涉及 LLM 调用质量 |
| **AIOS** (arxiv:2403.16971) | 通用 Agent OS 架构 | 宽泛架构，无 cost-quality trade-off 分析 |

这些工作关注"agent 系统别崩"，本文关注"钱怎么花得值"。问题不同，互相补充。

### 8.4 定位总结

| 研究类别 | 代表工作 | 关注点 | 本文差异 |
|----------|---------|--------|---------|
| Per-query routing | RouteLLM, CARROT, OmniRouter | 单条 query 选模型 | 本文是 workflow 级 |
| Agentic routing (RL) | BoPO, xRouter | 学习型多步路由 | 本文零训练 + 多 workflow |
| OS 资源管理 | AgentRM, AgentCgroup, AIOS | 系统稳定性 | 本文做 cost-quality 优化 |
| **本文** | AgentOS | **workflow-aware, training-free, multi-workflow cost-quality runtime** | — |

### 8.5 LLM Router Benchmark

| Benchmark | 说明 | 与本文关系 |
|-----------|------|-----------|
| **LLMRouterBench** (2026) | 21 datasets, 33 models, 400K instances | 可用于构造 quality_prior 表 |
| **RouterArena** (2025) | 开放 router 评估平台 | 可对比 per-query routing baseline |

---

## 9. 关键概念速查

| 概念 | 一句话 |
|------|-------|
| **Turn** | 一次 LLM 调用——调度和计费的最小单位 |
| **Workflow** | 一个完整任务的 LLM 调用序列（如 6 步 refactor） |
| **Workload** | 实验剧本：N 个 turn + 预算 + mock 表现 |
| **$w_i$** | 任务价值权重（调用方声明，非系统推断） |
| **$q_i$** | Turn 输出质量 $\in [0,1]$——由社区标准 benchmark grader 打分 |
| **budget_factor** | 预算松紧的反馈信号（近似 KKT 的 $\lambda$） |
| **Governor** | 约束层：预算 + 限流 + 并发（policy-agnostic） |
| **ModelSelector** | 优化层：可插拔的路由策略（唯一 policy-specific 组件） |
| **ZombieDetector** | 止损层：截断"花钱但质量不涨"的调用 |
| **QWCR** | $\frac{1}{N}\sum q_i$——平均质量 |
| **Q/\$** | $\sum q_i / \text{cost}$——每美元质量产出 |
| **Jain's Fairness Index** | 多 workflow 公平性指标，1 = 完全公平 |

---

## 10. 投稿建议

**首选路线：软件工程（ICSE / FSE / TSE / TOSEM，CCF-A）**

SE 社区缺"面向 LLM Agent 的成本治理基础设施"，对"系统工具 + 扎实实验"接受度高。

需要做的：
- Workload 用真实 SE agent 任务（SWE-bench agent 的多步 workflow）
- 质量用 SWE-bench Verified / HumanEval grader（§3.1 的社区标准，审稿人没法质疑"你的分数不客观"）
- 实证：不加治理 vs 加治理的成本浪费改善

**硬件支持**：单卡 A800-SXM4-80GB 可支持 Llama-3-70B-Int4 本地推理 + GPT-5 / Claude API 调用，足以在 SE benchmark 上做真实 LLM 实验。本地+云端混合后端正好体现 N-ary 优势。

**数学复杂度**：约束优化 + KKT 条件 + 背包贪心近似 + Weighted Fair Queuing。不需要 RL 理论。

---

## 11. 审稿人常见质疑

**Q: "你只是预算控制做得好。"**
→ 用对照组 C（$w_i \equiv 1$）排除：若 D 显著优于 C，差异来自任务价值感知，不是单纯的预算控制。

**Q: "$q$ 和 $w$ 怎么来？拍脑袋吗？"**
→ $q$ 来自社区标准 benchmark grader（SWE-bench Verified / HumanEval / GSM8K，§3.1 有完整表）；$w$ 由调用方在每次 LLM 调用时通过 API 传入（类似 Linux `nice` 值——不是系统猜的，是 agent 框架告诉系统的）。采纳路径 4 档渐进：L4 直接传数值 → L3 传 `task_type` 查预置表 → L2 区分 interactive/batch → L1 不传则 $w \equiv 1$ 退化到对照组 C（见 §2.6）。E1–E7 消融证明对权重噪声鲁棒，粗粒度分类也有明显收益。

**Q: "Cursor Auto / OpenCode Auto / GPT-5 Auto 已经解决了这个问题。"**
→ 这些 router 是 workflow-blind 的：它们看每次 prompt 选模型，但看不到 workflow 的步骤价值结构、全局预算状态、多 workflow 竞争。本文是 agent 框架与 LLM 后端之间的中间层——和 Cursor Auto 不是同一层，是它的调用方。详见 §0。

**Q: "和 Budget-Aware Agentic Routing (BoPO) 比呢？"**
→ 4 条差异化轴：(1) N-ary 后端 vs 二元，(2) 零训练 vs SFT+RL，(3) 多 workflow vs 单 task，(4) 显式 $w_i$ vs 稀疏 RL 奖励。两者互补——BoPO 的 RL 策略可以作为 ModelSelector 的一个 policy 接入本文的 runtime。详见 §8.1。

**Q: "为什么不复现 BoPO 做端到端对比？"**
→ 诚实回答：BoPO 的完整 SFT + RL 训练 pipeline 需要 multi-GPU 训练资源。本工作使用单卡 A800-80GB，足以做推理实验但不足以复现 RL 训练。BoPO 集成留作 future work，§4.1 的 ModelSelector 接口已为此预留好接入点。这是资源限制，不是设计缺陷。

**Q: "小规模有意义吗？"**
→ 即使 1 个 agent 6 步，"该把这步推到多好"仍是核心决策。

**Q: "质量分数跨 task_type 可比吗？"**
→ 承认不同 benchmark 的刻度有差异；主指标之外按 task_type 分组报告，并固定 workload 的 task_type 组成比例。

---

## 附录 A：一个具体场景（与 Cursor Auto 的差异）

让 SWE-agent / Cursor 重构代码（"把这个模块拆成三个文件"）。假设这次 workflow 实际走了 6 步（但系统事先不知道总步数——$w_i$ 是每步调用时由 agent 框架逐步声明的）：

| 步 | 任务 | task_type | $w_i$ | 备注 |
|----|------|-----------|------|------|
| 1 | 读代码 | retrieval | 1 | 便宜模型够用 |
| 2 | 制定方案 | reasoning | 3 | **关键**——错了拖累后面 4 步 |
| 3–5 | 生成文件 A/B/C | generation | 3 | 主产出 |
| 6 | 验证 import | transform | 1 | 便宜模型够用 |

**Cursor Auto 的做法**：每次调用独立看 prompt 选模型。它无法区分"这是关键的规划步 vs 不关键的验证步"，也不知道整个 task 的预算上限——因为这些信息只在 agent 框架的脑子里。

**AgentOS 的做法**：agent 框架把 $w_i$ 和预算 \$0.50 通过 API 传给 AgentOS。ModelSelector 按 $w_i \cdot \Delta q_i / \Delta c_i$ 排序，把贵模型（GPT-5 Thinking）留给 $w=3$ 的步骤（2–5），$w=1$ 的步骤（1、6）用 GPT-5 mini 或本地 Llama。从 5 个后端中选，不是二选一。

## 附录 B：budget_factor 不需要预测未来

`budget_factor` 的核心是闭环反馈（花快了收紧、花慢了放宽），不要求准确预测未来流量。常见配速策略（复杂度递增）：

1. **线性配速**：$F(t) = t/T$，按时间均匀花
2. **滑动窗口 burn rate**：只看最近 $\Delta$ 时间的消耗速率
3. **EWMA**：从历史中持续更新配速模型

即使配速粗糙，只要反馈方向正确，预算就能保持可控。

## 附录 C：Pluggability 设计

### 接口定义

```python
from abc import ABC, abstractmethod

class ModelSelectorPolicy(ABC):
    """所有路由策略的统一接口。
    Governor / Zombie / Preemption / Scheduler 不关心这里怎么实现。"""

    @abstractmethod
    def select(self, turn: TurnInfo, gov_state: GovernorState,
               backends: list[Backend]) -> Backend:
        ...

class TurnInfo:
    task_type: str       # "code_generation", "reasoning", ...
    w_i: float           # 调用方声明的任务价值权重
    context_len: int     # 当前上下文长度
    workflow_id: str     # 所属 workflow
    step_index: int      # 当前是 workflow 的第几步
    total_steps: int     # workflow 总步数（如果已知）

class GovernorState:
    budget_remaining: float   # 当前 workflow 剩余预算
    budget_factor: float      # 当前 λ 近似值
    rpm_remaining: int        # 全局剩余 RPM 配额
    concurrency_remaining: int  # 剩余并发槽
```

### 本工作实现的 4 个 Policy

| Policy 类 | 核心逻辑 | 用途 |
|-----------|---------|------|
| `WorkflowAwareHeuristic` | $\text{score} = w_i \cdot \Delta q / \Delta c$，结合 `budget_factor` 配速 | **本文主贡献** |
| `PerCallGreedy` | 每次独立选 $\max(q/c)$，不看 $w_i$、不配速 | 对照组 B |
| `BudgetAwareUniform` | 有配速（看 `budget_factor`），但 $w_i \equiv 1$ | 对照组 C |
| `CARROTStylePredictor` | 训练一个 cost-quality predictor，per-call 路由 | Per-call baseline |

### Future Work: BoPOPolicy

```python
class BoPOPolicy(ModelSelectorPolicy):
    """接入 BoPO 的 RL 策略。
    需要预训练的 RL 模型权重（SFT + BoPO 训练）。
    接口已就绪，训练需要 multi-GPU 资源。"""

    def __init__(self, rl_model_path: str):
        self.rl_model = load_rl_model(rl_model_path)

    def select(self, turn, gov_state, backends):
        # BoPO 原始设计只支持二元选择；
        # 在 N-ary 后端池中，可先降级为最贵/最便宜两个，
        # 或扩展 RL 模型输出为 N-ary softmax（需重新训练）
        return self.rl_model.route(turn, gov_state)
```

**为什么不在本文实现 BoPOPolicy？**
BoPO 的完整训练 pipeline 包括 boundary-guided SFT 数据合成 + BoPO 强化学习优化，需要 multi-GPU 训练环境。本工作使用单卡 A800-80GB，足以做 LLM 推理实验，但不足以复现 RL 训练。接口已预留，集成是工程问题而非设计问题。
