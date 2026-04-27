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
Agent 框架（SWE-agent / Moatless / MetaGPT）
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

**一句话**：Cursor Auto 在概念分层上属于 per-call router 这一层，是 AgentOS 设计上的下游同类调用方（不是竞争者）。本文实际集成对象是**开源 agent 框架**（SWE-agent / Moatless / MetaGPT 等），**不声称真实接入 Cursor / Claude Code 等闭源桌面应用**——这些产品没有公开 hook 让外部进程拦截 LLM 调用，集成需要厂商配合，超出学术工作范围。AgentOS 把上层 agent 的私有信息（workflow 价值 + 预算状态）接进来用上——这正是 per-call router 设计上做不了的事。

| 维度 | Cursor Auto / GPT-5 Auto / RouteLLM / CARROT | BoPO | **本文** |
|------|---------------------------------------------|------|---------|
| 路由信号 | 单次 prompt 内容 | RL 奖励信号 | prompt + **workflow 位置 ($w_i$)** + 预算状态 |
| 后端选择 | N-ary 但 per-call | 二元 | **N-ary + workflow-aware** |
| 跨步骤预算 | 无 | 单 task 内有 | **多 workflow 跨步骤 + 跨 workflow** |
| 训练需求 | 需训练（CARROT/RouteLLM）或无（Cursor） | SFT + RL | **零训练** |
| 止损 | 无 | 无 | 僵尸检测 + 截断 |
| 多 workflow 并发 | 无 | 无 | **admission control + 公平调度** |

### 谁会真正用这个？

AgentOS 的目标用户是**造 agent 的人**和**运营 agent 平台的团队**——不是终端用户（用 Cursor / Claude Code 干活的开发者本身不直接接触 AgentOS，AgentOS 不是 IDE 也不是 CLI 替代品）。具体三类：

- **Agent 框架 / agent 产品的构建者**（SWE-agent、Moatless、MetaGPT 等开源框架的维护者，以及自研 agent 的创业团队和企业小队）：在框架代码里 `import agentos`，把 workflow 结构通过 $w_i$ 暴露给运行时
- **单团队 agent 平台的运营方**（持有单一预算池、对内或对外服务多并发 agent 请求的产品团队 / 平台团队 / DevOps 团队）：把 AgentOS 当作内部 LLM 网关，让多 agent 在共享预算池下不打架——具体落地场景见 §0.5.2
- **研究者**：把 AgentOS 当 evaluation harness 跑 SWE-bench、HumanEval 等基准的多策略对比

无论 1 个 agent 6 步还是 50 个 agent 6 步，"哪一步该推到多好"都是核心决策，scope 在以上三类用户内部一致。**多预算主体（多团队 / 多部门 / 多 SLA 共享同一 agent 平台）的层级仲裁是 paper 边界外的问题**，留作 future work（§12）。

### 旗舰场景：50 个 SWE-agent 并发跑 SWE-bench Verified

为让上述 4 类用户的诉求具体化，下面用一个完整场景展示 AgentOS 四条贡献的协同。

**场景设定**：研究者用 SWE-bench Verified（500 题）评估自己的 agent 框架。开 50 个 SWE-agent 并发跑，固定**总预算 \$50**（名义人均 \$1），后端池 5 个：GPT-5 Thinking / GPT-5 Instant / GPT-5 mini / Claude Sonnet / 本地 Llama-3-70B-Int4。每个 agent 平均 6–12 个 turn，50 并发峰值产生约 400 RPM（逼近 OpenAI tier-3 的 500 RPM 限额）。

**不上 AgentOS 会发生什么？**

| 失败模式 | 原因 | 后果 |
|----------|------|------|
| RPM 雪崩 | 50 agent 同时发请求，瞬间打满 500 RPM | 大量 429 错误，约一半 agent 在关键步骤失败 |
| 预算失控 | 没有配速——先跑的 10 个 agent 把贵模型预算花光 | 后 40 个 agent 全程只能用 mini，QWCR 严重下降 |
| 资源饥饿 | 跑得快的 agent 吃光并发槽和 RPM 配额 | 跑得慢或后启动的 agent 被系统性饿死，Jain's FI 趋近 $1/J$ |
| 僵尸占槽 | 卡死的 agent 占着并发槽不释放 | 健康 agent 排队等位，整体吞吐下降 |

**上 AgentOS 后四条贡献如何协同？**

| AgentOS 机制 | 对应贡献 | 在本场景中做什么 |
|-------------|---------|----------------|
| **Governor** | 约束治理 | 顶住 400 RPM 峰值——admission control 排队而非雪崩，预算硬封顶保证 \$50 不超支 |
| **ModelSelector** | workflow-aware 路由 + N-ary 后端 | 把 GPT-5 Thinking 留给 $w=3$ 的 planning 步，retrieval/validation 步用 Instant 或 mini；从 5 个后端的成本梯度中选最佳档位，而非二选一 |
| **WFQ Scheduler** | 多 workflow 公平调度 | 50 个 agent 按 weighted fair queuing 分享 RPM/并发槽，保证每个 agent 都拿到合理份额（目标 Jain's FI $\ge 0.95$） |
| **ZombieDetector** | 僵尸截断 | 检测卡死 agent 并释放其并发槽和预算残值，回收给健康 agent |

**这一个场景同时考验本文的四条核心机制——workflow-aware 路由、零训练、N-ary 后端、多 workflow 资源协调（含跨 workflow 不饿死的保证 + 僵尸截断）。它也是 §7 RQ4 的旗舰实验。** 此外，混合后端池（GPT-5 系列 + Claude + 本地 Llama-3-70B）天然演示了 §0.5.3 的 cost-model-agnostic 性质——同一算法在 USD 计价的 API 后端和本地摊销成本的本地后端上无需修改即可工作。

---

## 0.5 部署形态、落地场景与成本模型

> 本节回答三个产品形态层面的具体问题：(1) AgentOS 长什么样、谁来调用？(2) 在没有"多团队仲裁"的 scope 下，paper 的落地场景到底是什么？(3) 如果调用方有自己的本地 GPU 算力（如字节、阿里、Meta 这种公司），AgentOS 还成立吗？

### 0.5.1 形态：Python SDK + 可选 HTTP Sidecar Proxy

AgentOS 有两种部署形态，**不是 CLI 工具、不是 IDE 插件、不直接面向终端用户**：

- **Python SDK（主形态）**：调用方在自己的 agent 代码里 `import agentos`，把原本的 `openai.chat.completions.create(...)` 替换为 `agentos.chat(messages=[...], task_type="planning", w_i=3.0, budget=0.5)`。SWE-agent / Moatless / MetaGPT 这类**开源 agent 框架**是直接受众——它们都是 Python 写的 agent loop，集成只需替换一行 LLM 调用。本文 §7 RQ4 旗舰实验的 4–6 个真 SWE-agent 端到端佐证就是通过这种方式集成的。
- **HTTP sidecar proxy（可选形态）**：部署一个本地服务，agent 通过改 `base_url` 指向 `http://localhost:8080/v1` 接入。语言无关、低侵入——任何能发 HTTP 的 agent（包括非 Python 的）都能接，对应**单团队 LLM 网关**场景（一个团队部署一份 AgentOS 实例，团队内多个 agent 服务都从这里走）。

**明确不是**什么：

| 不是 | 为什么不是 |
|------|----------|
| CLI 工具（不和 Claude Code 抢用户） | 那会变成"端用户产品"而非"中间层基础设施"，与本文定位（agent 框架与 LLM 后端之间的治理中间层）冲突 |
| Cursor / Claude Code 插件 | 这些产品闭源、无公开 hook，集成需要厂商配合，超出学术工作范围 |
| 端用户工具 | 用 Cursor / Claude Code 干活的工程师不会接触 AgentOS——AgentOS 在 agent 框架内部对端用户透明 |

### 0.5.2 落地场景：单一预算主体 + 多并发 workflow

AgentOS 的 scope 是 **"单一预算主体下的多并发 workflow"**——下标 $j$（§2.2 公式）是同一钱包之下的并发 workflow 数，不跨多预算主体。在这一结构上，论文识别四个具体的落地场景：

| # | 场景 | 单一预算主体 | 一个 workflow = 什么 | 论文实验是否覆盖 |
|---|------|------------|---------------------|----------------|
| 1 | 研究 benchmark 评估 | 研究者本人 | 一道 SWE-bench 题目 | **是**（§7 RQ4 旗舰） |
| 2 | 单团队生产 agent 服务 | 创业团队 / 产品团队 | 一次外部用户请求（如 PR review、客服会话、数据抽取） | 机制类比，不跑实验 |
| 3 | CI / 批量评估管线 | DevOps / 数据团队 | 一次 commit 触发的 agent 任务（如 nightly 测试生成、代码审计） | 机制类比，不跑实验 |
| 4 | 公司内部开发者工具 | 平台团队 | 一名工程师的一次请求（如"问代码库" agent、内部 RAG agent） | 机制类比，不跑实验 |

四个场景共同结构是 **"单一预算主体（一个钱包）+ 多并发 workflow + 共享 RPM/并发上限"**——对应 §2.2 的多 workflow 优化问题。这一结构带来两个具体好处（避免只用"公平"这个孤立词汇）：

- **保证后启动的 workflow 不被先启动的吃光资源**：FIFO 分配下先启动的 50 个 SWE-agent 会用尽 GPT-5 Thinking 配额，后启动的 agent 在关键 planning 步只能用 mini，整体成功率拉胯。AgentOS 通过 §5.2 的 weighted fair queuing 让每个 workflow 获得稳定的资源份额，避免"先到先得"导致的系统性饿死。
- **保证单个失控 workflow 不污染整体预算**：某个 agent 卡死或陷入循环时，AgentOS 通过 §4 的 ZombieDetector 截断它，回收并发槽和预算残值给健康 agent，而不是任由它把共享预算池烧光。

> **关键说明**：场景 1 的"研究者"、场景 2 的"创业团队"、场景 3 的"DevOps 团队"、场景 4 的"平台团队"——这些都是**单一**预算决策主体。即便场景 4 的 agent 服务于全公司多个工程团队（市场组 Alice、销售组 Bob ……），AgentOS **不需要建模这些下游团队的归属**——平台团队是预算所有者，下游用户在 AgentOS 视角里全部坍缩为"并发 workflow"。下游团队的部门归属属于计费系统 / quota 系统的事，不是 routing 系统的事。
>
> 多预算主体（多团队各自持有独立预算 + 跨团队 quota 仲裁 + SLA 抢占）是不同问题，见 §12 future work。

### 0.5.3 Cost Model Agnostic：scope 内的核心性质

§2.5 的 N-ary 后端选择器**只依赖后端之间的成本梯度**（哪个比哪个贵多少），不依赖货币单位本身。这意味着 AgentOS 在以下三种成本模型上**直接成立、无需修改算法**：

| 成本模型 | 成本如何换算 | 代表性场景 |
|---------|------------|----------|
| 纯 API 计价 | 后端单价 = 模型 USD/1K tokens | OpenAI / Anthropic 等付费 API 用户 |
| 本地 GPU 摊销 | 后端单价 = （硬件折旧 + 电费 + 运维成本）÷ 服务的 token 总量 | 自有 H100 集群跑本地 Llama-3-70B-Int4 |
| **混合**（最常见） | 不同后端用不同模型计价，统一成"每 1K tokens 多少钱" | **本文 §7 后端池**：GPT-5 系列 API + 本地 Llama-3-70B |

**工业代表性**：字节、阿里、Meta 这种"既有大量本地 GPU、又调用外部前沿模型 API"的混合部署是 AgentOS 的一线用例。**本地 GPU 不是免费的**——它仍是稀缺资源、仍有折旧 / 电费 / 运维成本——只是单价比 API 低 5–10x（粗算 Llama-70B-Int4 自托管约 \$0.0002/1K tokens vs GPT-5 Thinking 约 \$0.10/1K tokens）。§2.2 的优化问题原封不动适用，§2.5 的 tier-progressive 决策只看相邻 tier 的 $\Delta c$（成本差），不关心 \$0.0002 还是 \$0.10 是怎么算出来的。

**这是 paper 1 scope 内的核心性质，不是 future work**——§2.5 公式已经支持，本文显式声明并以 §7 的混合后端池（GPT-5 系列 + Claude + 本地 Llama-3-70B）作为佐证。多预算主体的 future work（§12）中，cost-model-agnostic 性质自动继承——多团队 quota 同样可以以 USD、本地 GPU 摊销、或混合成本计量。

### 0.5.4 最小代码示例（SDK 形态）

```python
import agentos

client = agentos.Client(
    budget=0.50,                                  # 本 workflow 美元预算（或本地 GPU 摊销等价值）
    backends=[                                    # N-ary 后端池，混合 API + 本地
        "gpt-5-thinking",
        "gpt-5-instant",
        "gpt-5-mini",
        "claude-sonnet",
        "llama-3-70b-int4-local",
    ],
)

plan = client.chat(
    messages=[{"role": "user", "content": "重构这个模块为三个文件"}],
    task_type="planning",
    w_i=3.0,                                       # planning 步关键，错了下游连错
)
code = client.chat(messages=[...], task_type="generation",  w_i=3.0)
chk  = client.chat(messages=[...], task_type="validation",  w_i=1.0)
```

调用方（agent 框架代码）只需声明 `task_type` 和 `w_i`；AgentOS 在内部完成路由（§2.5）、限流（§4 Governor）、僵尸检测（§4 ZombieDetector）、跨 workflow 协调（§5）。

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

**Scope 注（重要）**：下标 $j$ 是**同一预算主体之下**的并发 workflow——例如同一研究者跑的多个 SWE-bench 题目，或同一团队 agent 服务收到的多个用户请求。$\sum_j B_j$ 是这一预算主体的**单一钱包**。本文不建模多预算主体（多团队 / 多部门 / 多 SLA 等级共享同一 agent 平台时的 quota 仲裁），相关问题作为 future work 见 §12。这一 scope 划分对应了 §0.5.2 列出的四个落地场景的共同结构。

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

### 2.5 边际加权性价比（ModelSelector 的排序准则，N-ary 版）

将后端池 $\mathcal{A}$ 中的 $N$ 个后端按成本升序排列：$a_1 \prec a_2 \prec \dots \prec a_N$（例如 mini $\prec$ Llama-70B $\prec$ Instant $\prec$ Sonnet $\prec$ Thinking）。定义**逐 tier 边际增量**：

$$
\Delta q_i^{(k)} = q_i(a_{k+1}) - q_i(a_k), \quad \Delta c_i^{(k)} = c_i(a_{k+1}) - c_i(a_k), \quad k = 1, \dots, N-1
$$

**决策规则（tier-progressive）**：对 turn $i$，从最便宜的 $a_1$ 起，逐 tier 评估"再升一档值不值"：

$$
\text{升级条件：} \quad w_i \cdot \frac{\Delta q_i^{(k)}}{\Delta c_i^{(k)}} \ge \lambda
$$

其中 $\lambda$ 是 `budget_factor`（§2.4 的影子价格在线近似）。选中的后端是满足上式的**最高 tier**：

$$
a_i^* = a_{k^*+1}, \quad k^* = \max\left\{k : w_i \cdot \frac{\Delta q_i^{(k)}}{\Delta c_i^{(k)}} \ge \lambda\right\}
$$

若所有 tier 都不值得升级（$\lambda$ 很高 = 预算紧），则留在 $a_1$（最便宜）。

**等价的对偶 argmax 写法**：

$$
a_i^* = \arg\max_{a \in \mathcal{A}}\ w_i\,q_i(a) - \lambda\,c_i(a)
$$

两者在分段线性近似下数学等价。本文实现采用 tier-progressive 写法，理由是 EWMA 维护"相邻 tier 增量"$(\Delta q^{(k)}, \Delta c^{(k)})$ 对冷启动更友好——只需观测相邻两个后端的差异，而非每个后端的绝对 $q$。

各符号汇总：

| 符号 | 含义 | 怎么算 |
|------|------|-------|
| $w_i$ | 这一步的任务价值权重 | 调用方通过 API 声明（见 §2.6），不是系统猜的 |
| $\Delta q_i^{(k)}$ | 从 tier $k$ 升到 tier $k+1$ 能多换多少质量 | 基于历史统计先验（实时 EWMA 更新，按 task_type × 后端对分组） |
| $\Delta c_i^{(k)}$ | 升一档要多花多少钱 | 按 token 单价 × 估计 token 数 |
| $\lambda$ | budget_factor（预算紧则高、松则低） | 闭环反馈在线更新（§2.4 / 附录 B） |

**数字例子**（5 个后端、两个 turn 并行竞争升级）：

| 步骤 | $w_i$ | 当前 tier | 下一 tier | $\Delta q^{(k)}$ | $\Delta c^{(k)}$ | $w_i \cdot \Delta q / \Delta c$ | $\lambda=0.20$ 时决策 |
|------|-------|----------|----------|-----------------|-----------------|-------------------------------|---------------------|
| 规划步（planning） | 3 | Instant (\$0.01) | Sonnet (\$0.03) | 0.10 | \$0.02 | **1.50** | 升级 |
| 规划步（planning） | 3 | Sonnet (\$0.03) | Thinking (\$0.10) | 0.15 | \$0.07 | **0.64** | 升级 |
| 检索步（retrieval） | 1 | mini (\$0.001) | Llama (\$0.002) | 0.15 | \$0.001 | **15.0** | 升级 |
| 检索步（retrieval） | 1 | Llama (\$0.002) | Instant (\$0.01) | 0.15 | \$0.008 | **1.88** | 升级 |
| 检索步（retrieval） | 1 | Instant (\$0.01) | Sonnet (\$0.03) | 0.10 | \$0.02 | **0.50** | 升级 |
| 检索步（retrieval） | 1 | Sonnet (\$0.03) | Thinking (\$0.10) | 0.05 | \$0.07 | **0.07** | 不升级 |

结果：规划步一路升到 Thinking（$w=3$ 放大了每次升级的加权收益），检索步停在 Sonnet（$w=1$ 使最后一跳的加权边际收益 0.07 低于 $\lambda=0.20$）。**N-ary 后端让"升到哪一档"成为连续渐进的决策，而非二选一的粗粒度跳跃**。

**公式的理论根基**：

1. **拉格朗日松弛 / KKT 一阶条件**（§2.4 已给出）：带预算约束的连续质量最大化问题，最优解的充要条件就是"每个 turn 的边际加权收益与边际成本之比相等"。tier-progressive 规则是对该连续最优条件的离散近似。
2. **多选择背包贪心近似**（Sinha & Zoltners 1979, Dantzig 1957）：MCKP 的 LP-relaxation 标准做法——将每个 group 内的 item 按逐增边际效率排序后依次填包。本文在此基础上加入 $w_i$ 权重并接入在线 $\lambda$ 反馈，形成可操作的 N-ary 启发式。

一句话：**思想是百年教科书标准，公式是本文对 LLM agent 路由场景的首次 N-ary 具体化**——不是发明边际分析，而是把它接入 workflow 结构（$w_i$、预算状态、N 个后端的成本梯度）中形成可操作的启发式。

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

### 2.7 N-ary 后端的现实性检查

N-ary 后端（5+ 个模型可选）是本文相对 BoPO 二元设计的核心差异化轴。本节诚实开列 N-ary 在工程中的真实代价与应对方式，避免审稿人在 rebuttal 阶段才暴露这些问题。

**代价 1：先验矩阵规模从 $O(T)$ 涨到 $O(T \times N)$**

§2.5 的 tier-progressive 决策需要为每个 (task_type, 后端对) 维护 $\Delta q^{(k)}$ 估计。$T$ 个 task_type × $N$ 个后端 → $T \times (N-1)$ 个边际增量。以 $T=6$, $N=5$ 为例，共 24 个先验（对比二元时仅 6 个）。

应对：
- **静态先验表**（本文给出）：基于公开 benchmark 数据（LLMRouterBench / SWE-bench 公开 leaderboard）预填，覆盖常见 task_type × 后端组合
- **EWMA 在线更新**：每次真实调用后，用观测到的 $q$ 按 $\hat{q}_{\text{new}} = \alpha \cdot q_{\text{observed}} + (1-\alpha) \cdot \hat{q}_{\text{old}}$ 更新对应 (task_type, backend) 的先验，通常 5–10 次观测即收敛到合理范围
- **冷启动回退**：未观测过的 (task_type, backend) 组合回退到静态表默认值，不拒绝服务

**代价 2：部分后端可能被 Pareto 支配**

现实中 5 个后端不太可能全部都在 Pareto 前沿上——某些后端在特定 task_type 上可能既贵又不比相邻后端质量高。例如对 `retrieval` 任务，Llama-70B 可能被 GPT-5 Instant 严格支配（Instant 更便宜且质量更高）。

应对：**启动期 Pareto 剪枝**——系统启动时按 task_type 分组，对每组后端做一次 Pareto 非支配检查，剔除被严格支配的后端（$\exists a': q(a') \ge q(a)$ 且 $c(a') \le c(a)$）。剪枝后的"有效 N"才是 tier-progressive 决策的实际选择空间。

| task_type | 标称 N | 预计有效 N | 被剪掉的后端（示例） |
|-----------|-------|----------|-------------------|
| `reasoning` / `planning` | 5 | 4–5 | mini 在复杂推理上可能被 Llama 支配 |
| `retrieval` / `validation` | 5 | 3–4 | Thinking 在简单检索上多花钱但没多少质量提升 |
| `generation` | 5 | 4–5 | 多数后端有区分度 |

**诚实的边界**：我们预计实际有效 N 在 3–5 之间浮动。**N-ary 的价值不是"5 个后端全被用上"，而是"成本梯度够细"**——即使有效 N=3，也比二元的 2 个多出一个中间档，能把"值得升一档但不值得升两档"的 turn 安排到正确位置。

**与 BoPO 的代价对照**

BoPO 限制为二元不是设计缺陷，而是 RL action space 的代价——action 从 2 扩展到 N 时，RL 的 sample complexity 显著增加，需要更多训练数据和 GPU 时间。本文使用启发式"免费"获得 N-ary 支持，但代价转移到了先验表维护上。**这是 trade-off，不是免费的午餐**——启发式不需要训练但依赖先验质量，RL 不需要先验但需要训练资源。两者各有适用场景。

---

## 3. 质量怎么衡量？（回应导师 Challenge）

**导师质疑**：质量 $q_i$ 凭什么说好就好？你自己定义的分数别人认可吗？

**回答**：不自己发明评分标准——**复用社区已经广泛认可的 benchmark grader**。

**实验场景 vs 落地场景的客观性边界**：本文实验的 quality 测量全部使用社区标准 deterministic grader（详见 §3.1）。§0.5.2 列出的四个落地场景中，**只有场景 1（研究 benchmark 评估）直接落入这些 grader 的覆盖范围**，故 §7 RQ4 实证集中在场景 1；场景 2-4（单团队生产 agent / CI 批量评估 / 公司内部开发者工具）是机制类比的可推广性主张，**本文不在这些场景上跑实验**——它们的 quality grader 因任务而异（部分客观如 PR review 的 bug 检出率，部分需要人评），与本文的"客观 grader 立论"不兼容，留给具体应用研究处理。

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

### 5.1 为什么需要这一层——以 SWE-bench 并发评估为例

**核心场景**：研究者用 SWE-bench Verified（500 题）评估 agent 框架，开 50 个 SWE-agent 并发跑。以下是真实量级的资源压力估算：

| 参数 | 数值 | 来源 |
|------|------|------|
| 单题平均 turn 数 | 6–12 | SWE-agent / Moatless 公开 trace |
| 单题平均成本（混合后端） | \$0.50–\$2.00 | 取决于后端选择 |
| 50 并发峰值 RPM | $\approx 50 \times 8 \text{ turns/min} = 400$ RPM | 假设平均 turn 间隔 7.5s |
| OpenAI tier-3 RPM 限额 | 500 RPM | OpenAI 官方文档 |
| RPM 利用率 | **80%**——极度紧张 | 400 / 500 |

50 个 agent 同时跑时，系统处于 RPM 限额的 80% 水位——任何突发都会触发 429。如果不做调度：

- **先到先得**：先启动的 agent 抢占 RPM 和贵模型预算，晚启动的全程只能用 mini，造成跨 workflow 质量方差极大（Jain's FI 趋近 $1/J$）
- **无配速**：前 10 个 agent 在 planning 步疯狂消耗 Thinking 配额，后 40 个 agent 的 planning 步也只能用 Instant——而 planning 步质量下降会拖垮整个 workflow 的下游
- **无止损**：卡死的 agent 占着并发槽 5 分钟不释放，健康 agent 排队等位

这个场景同时需要 RPM 准入（Governor）、预算配速（ModelSelector）、跨 workflow 公平（WFQ Scheduler）、僵尸回收（ZombieDetector）。企业多 agent 部署（DevOps 团队并行跑代码审查 + 测试生成 + 文档更新）和多用户共享 API 配额面临同样的资源争抢问题。

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
| **RQ4**（旗舰） | **SWE-bench 50-agent 并发评估**：固定总预算 \$50、50 个 mock workflow 并发（+ 4–6 个真 SWE-agent 端到端佐证），AgentOS 能否同时维持 (a) 整体 Pareto 前沿 (b) 跨 workflow 公平性（Jain's FI $\ge 0.95$）？ | Multi-Workflow Scheduler + Governor + ModelSelector + Zombie | Jain's FI, QWCR 方差, 整体 Pareto, 429 率, N-ary 使用分布 |

**RQ4 实验设计（旗舰）**：

| 维度 | 设定 |
|------|------|
| **Workload（mock 主线）** | SWE-bench Verified 子集 100 题 × 50 mock workflow 并发，每 workflow 6–12 turn，task_type 按 SWE-agent 真实 trace 分布（planning / generation / validation） |
| **Workload（真实佐证）** | 4–6 个真 SWE-agent 并发 × SWE-bench Verified 子集 20 题，真实 LLM 调用 + fail-to-pass grader |
| **总预算** | \$50（名义人均 \$1，实际由调度分配） |
| **后端池** | GPT-5 Thinking / Instant / mini / Claude Sonnet / 本地 Llama-3-70B-Int4（N=5） |
| **RPM 限额** | 500 RPM（模拟 OpenAI tier-3） |

| 对照组 | 策略 | 预期失败模式 |
|--------|------|------------|
| F1. `round_robin` | 轮流分配 RPM 槽，不看预算也不看 $w_i$ | 均匀但浪费——关键步和琐碎步给同等资源 |
| F2. `fifo` | 先到先得 | 先启动的 agent 吃光资源，后启动的饿死 |
| F3. `wfq_no_budget` | WFQ 公平分 RPM/并发，但无 workflow 内预算配速 | 公平但不 cost-aware——每个 agent 内部预算失控 |
| **F4. AgentOS** | WFQ + Governor 预算配速 + ModelSelector ($w_i$ + N-ary) + Zombie | 完整系统 |

| 核心指标 | 含义 | 预期结论 |
|---------|------|---------|
| **Jain's Fairness Index** | 跨 workflow QWCR 公平性 | F4 $\ge 0.95$，F2 接近 $1/J$ |
| **Cross-workflow QWCR 方差** | 方差越小越公平 | F4 最小 |
| **整体 Pareto 前沿** | 横轴总 cost、纵轴总 QW-Completed | F4 在 Pareto 前沿上；F1 公平但产出低 |
| **极差比** | 最强 / 最弱 workflow 的 QWCR 比值 | F4 $\le 1.5$，F2 $\ge 5$ |
| **429 错误率** | RPM 超限导致的失败 | F4 $\approx 0$（Governor 兜底），F2 / F3 显著 |
| **N-ary 后端使用分布** | 5 个后端各被用了多少次 | 验证有效 N $\ge 3$，非退化为二元 |

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

### 8.6 Fairness in Shared LLM Serving

| 工作 | 关注点 | 公平性对象 | 与本文差异 |
|------|--------|-----------|-----------|
| **vLLM** (Kwon et al. 2023) / **SGLang** (Zheng et al. 2024) | 推理引擎内的请求级公平调度 | per-request latency fairness | 不涉及 workflow 结构或预算分配——做的是"把请求公平地处理掉" |
| **Andes** (OSDI 2024) | SLO-aware serving，按 deadline 优先 | per-request SLO 达标率 | 关注 latency SLO，不关注 cost-quality trade-off |
| **DRF** (Ghodsi et al. 2011) | 多维资源的 max-min 公平性 | 用户间 CPU/内存/带宽 | 经典理论基础，但不建模 LLM 调用的质量连续性 |
| **WFQ** (Demers et al. 1989) | 按权重分配带宽 | 网络流 | 本文 §5.2 采用的调度基础，扩展到 LLM RPM/并发槽 |

**定位差异**：上述工作做的是"把**请求**公平地处理掉"（延迟公平或资源量公平），本文做的是"把**预算和质量**在多 workflow 间公平地分配"。具体来说，本文的 fairness 目标是 cross-workflow QWCR 方差最小化（Jain's FI $\ge 0.95$），同时不牺牲整体 Pareto 前沿——这要求调度器同时理解每个 workflow 的预算消耗状态和步骤价值结构，是 request-level fairness 做不到的。

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
| **Multi-workflow fairness** | 在固定共享预算 + RPM 配额下，让 $J$ 个并发 workflow 都拿到合理质量份额（用 Jain's FI + QWCR 方差 + 整体 Pareto 联合度量） |

---

## 10. 投稿建议

**首选路线：软件工程（ICSE / FSE / TSE / TOSEM，CCF-A）**

SE 社区缺"面向 LLM Agent 的成本治理基础设施"，对"系统工具 + 扎实实验"接受度高。

需要做的：
- **旗舰实验（RQ4）**：50 个 SWE-agent 并发跑 SWE-bench Verified——mock 主线（50 workflow × 100 题）验证调度策略 + 4–6 个真 SWE-agent 端到端佐证。固定总预算 \$50，对比 round-robin / FIFO / WFQ-no-budget / AgentOS 四种调度。报告 Jain's FI、QWCR 方差、Pareto 前沿、429 率、N-ary 后端使用分布。这是论文的"一句话就能讲清楚"的 headline 实验
- Workload 用真实 SE agent 任务（SWE-bench agent 的多步 workflow）
- 质量用 SWE-bench Verified / HumanEval grader（§3.1 的社区标准，审稿人没法质疑"你的分数不客观"）
- 实证：不加治理 vs 加治理的成本浪费改善

**硬件支持**：单卡 A800-SXM4-80GB 可支持 Llama-3-70B-Int4 本地推理 + GPT-5 / Claude API 调用，足以在 SE benchmark 上做真实 LLM 实验。本地+云端混合后端正好体现 N-ary 优势。4–6 个真 SWE-agent 并发佐证实验成本约 \$20（4 agent × 5 题 × \$1），在单卡硬件上完全可行。

**数学复杂度**：约束优化 + KKT 条件 + 背包贪心近似 + Weighted Fair Queuing。不需要 RL 理论。

---

## 11. 审稿人常见质疑

**Q: "你只是预算控制做得好。"**
→ 用对照组 C（$w_i \equiv 1$）排除：若 D 显著优于 C，差异来自任务价值感知，不是单纯的预算控制。

**Q: "$q$ 和 $w$ 怎么来？拍脑袋吗？"**
→ $q$ 来自社区标准 benchmark grader（SWE-bench Verified / HumanEval / GSM8K，§3.1 有完整表）；$w$ 由调用方在每次 LLM 调用时通过 API 传入（类似 Linux `nice` 值——不是系统猜的，是 agent 框架告诉系统的）。采纳路径 4 档渐进：L4 直接传数值 → L3 传 `task_type` 查预置表 → L2 区分 interactive/batch → L1 不传则 $w \equiv 1$ 退化到对照组 C（见 §2.6）。E1–E7 消融证明对权重噪声鲁棒，粗粒度分类也有明显收益。

**Q: "Cursor Auto / OpenCode Auto / GPT-5 Auto 已经解决了这个问题。"**
→ 这些 router 是 workflow-blind 的：它们看每次 prompt 选模型，但看不到 workflow 的步骤价值结构、全局预算状态、多 workflow 竞争。本文是 agent 框架与 LLM 后端之间的中间层——和 Cursor Auto 不是同一层，是它**概念上**的调用方（Cursor / Claude Code 等闭源产品没有公开 hook，本工作不声称真实集成；实际集成对象是开源 agent 框架，详见 §0 与 §0.5）。

**Q: "和 Budget-Aware Agentic Routing (BoPO) 比呢？"**
→ 4 条差异化轴：(1) N-ary 后端 vs 二元，(2) 零训练 vs SFT+RL，(3) 多 workflow vs 单 task，(4) 显式 $w_i$ vs 稀疏 RL 奖励。两者互补——BoPO 的 RL 策略可以作为 ModelSelector 的一个 policy 接入本文的 runtime。详见 §8.1。

**Q: "为什么不复现 BoPO 做端到端对比？"**
→ 诚实回答：BoPO 的完整 SFT + RL 训练 pipeline 需要 multi-GPU 训练资源。本工作使用单卡 A800-80GB，足以做推理实验但不足以复现 RL 训练。BoPO 集成留作 future work，§4.1 的 ModelSelector 接口已为此预留好接入点。这是资源限制，不是设计缺陷。

**Q: "小规模有意义吗？"**
→ 即使 1 个 agent 6 步，"该把这步推到多好"仍是核心决策。

**Q: "质量分数跨 task_type 可比吗？"**
→ 承认不同 benchmark 的刻度有差异；主指标之外按 task_type 分组报告，并固定 workload 的 task_type 组成比例。

**Q: "N-ary 真的有用吗？是不是 5 个后端里 3 个都被 Pareto 支配了？"**
→ 诚实回答：§2.7 给出了 Pareto 剪枝机制，并在实验中报告每个 task_type 的有效 N（预计 3–5）。N-ary 的价值不是"5 个后端全被用上"，而是"成本梯度够细"——即使有效 N=3，也比二元的 2 个多出一个中间档，能把"值得升一档但不值得升两档"的 turn 安排到正确位置。RQ4 的二级指标"N-ary 后端使用分布"直接验证这一点。

**Q: "Jain's FI 高就一定好吗？50 个 agent 都被均匀压制到很差的 QWCR 也是 FI = 1。"**
→ 这正是为什么 §6.2 要求三个指标**联合**报告：Jain's FI（跨 workflow 资源份额一致性）+ Cross-workflow QWCR 方差（输出质量一致性）+ 整体 Pareto 前沿（绝对产出）。"均等地都做不好"在整体 Pareto 图上会立刻露出来——F1 round-robin 的 Jain's FI 可能接近 1，但其 Pareto 前沿位置应远低于 F4 AgentOS，因为 round-robin 不做 $w_i$ 感知的预算分配。三个指标里 Jain's FI 度量的具体好处是"后启动的 workflow 不被先启动的吃光资源"，而非孤立的"公平"概念。

---

## 12. Future Work：Multi-Tenant Agent Compute Resource Allocation

### 12.1 systems 社区的 single-tenant → multi-tenant 演进路径

> **背景介绍**（给不熟悉 systems 社区的读者）：vLLM 是 2023 年 UC Berkeley 发布的开源 LLM 推理引擎（GitHub 30k+ stars，SOSP 2023），目前业界最广泛部署的开源推理后端之一。vLLM 第一篇论文只解决一件事——**在一台机器上把多个推理请求 batch 在一起跑得更快**。这是典型的 single-tenant 问题：所有请求来自同一个调用方（同一个产品 / 同一个研究者），决策主体只有一个，目标是吞吐最大化。
>
> 后续工作 Andes（OSDI 2024）和 SGLang router（2024 系列工作）才把 multi-tenant 问题打开——**多个不同租户的请求如何公平分享一台或一群推理服务器**。这是 multi-tenant fairness 问题：多个**有竞争关系的调用方**共享资源，目标变成"既要总吞吐又要租户间公平"。

**single-tenant → multi-tenant 是 systems 论文的标准演进路径**。两者数学上是不同问题：

| 维度 | single-tenant | multi-tenant |
|------|--------------|--------------|
| 决策主体 | 1 个 | 多个，可能利益冲突 |
| 数学形式 | 单目标约束优化（如 max ∑ w q s.t. budget） | 多目标 / 博弈 / Pareto / DRF |
| "公平"的含义 | 单 owner 下的 workflow 间不饿死 | 多 owner 间的 quota 公平 + SLA 抢占规则 |
| 工程附加 | 算法 + 运行时 | 必备 admin layer：dashboard / 计费 / 审计 / 配额回拨 |

通俗讲：single-tenant 是"我怎么花我的钱"，multi-tenant 是"几个人怎么分一块蛋糕"。前者是优化问题，后者本质是协调与博弈问题。

### 12.2 AgentOS 的 paper 1 → 续作演进定位

AgentOS 走与 vLLM 完全同型的路径：

- **本文（paper 1）= AgentOS single-tenant 版**——单一预算主体（一个研究者 / 一个团队 / 一个 DevOps 单元）下的多 workflow 优化（§2.2）+ workflow-aware routing（§2.5）+ N-ary 后端（§2.7）+ 多 workflow 内部协调与僵尸回收（§5）+ cost-model-agnostic 性质（§0.5.3）。这一 scope 对应 vLLM 第一篇 SOSP 2023 的位置。
- **续作 = AgentOS multi-tenant 版**——多个有竞争关系的预算主体（多团队 / 多部门 / 多 SLA 等级）共享同一个 agent 编排平台时的 quota 仲裁与跨租户协调。具体内容包括：
  - **层级预算配额**：CFO → 部门 → team → workflow 的多级 quota（仿照 K8s ResourceQuota，但适配 LLM 单价异质性与 cost-model-agnostic）
  - **SLA 优先级与抢占**：金牌客户的 agent > 内部探索 agent > 后台批处理 agent，优先级反转 / 抢占规则需要明确建模
  - **跨团队监控**：burn rate dashboard、admin UI、计费与回拨机制（market 部花了 sales 部的钱怎么算回去）
  - **配额耗尽溢出策略**：某团队预算花完时是拒绝、降级到便宜后端、还是借用其他团队配额？这是政策决策，不是优化决策

### 12.3 续作问题与 paper 1 的边界

| 维度 | paper 1（single-tenant）| 续作（multi-tenant） |
|------|-----------------------|-------------------|
| 决策主体数量 | 1 | 多，且可能利益冲突 |
| 数学形式 | $\max \sum w_i q_i$ s.t. budget + RPM | 多目标 / 博弈 / DRF / 帕累托均衡 |
| Workflow 间协调目标 | 单 owner 下不饿死后启动者（Jain's FI 度量） | 多 owner 间 quota 公平 + 跨 owner SLA 抢占 |
| 工程层面 | SDK + 可选 proxy | 必备 admin layer：dashboard / 计费 / 审计 / 政策引擎 |
| Cost model | API / 本地 GPU 摊销 / 混合（§0.5.3） | **同样三种**——cost-model-agnostic 性质从 paper 1 自动继承到续作，只需更换 quota 计量单位 |

**续作定位的好处**：把多预算主体明确划入"下一篇论文 / 工业续作"而非 paper 1 的遗憾，反而**抬高 paper 1 定位**——本文是这个新研究方向（agent 编排平台的多租户资源治理）的基础层。审稿人问"为什么不解决企业层级"时，回答是"那是 multi-tenant agent compute resource allocation 这个独立问题，本文是其 single-tenant 基础"，路径清晰、scope 自洽。

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
