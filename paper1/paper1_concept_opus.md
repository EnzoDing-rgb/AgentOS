# AgentOS: A Workflow-Aware, Training-Free Runtime for Cost-Quality Optimization in Multi-Agent LLM Systems

> **一句话**：给定固定预算和一系列 LLM 调用，如何把钱花在刀刃上——让高价值步骤用好模型、低价值步骤用便宜模型、僵尸调用及时止损？

---

## 0. 定位：这篇论文在解决什么问题？
### 背景：现在已经有很多 auto-routing 了

今天的开发者已经被各种"自动选模型"功能包围：

- **商业产品内置 auto-routing**：在多步 agent workflow 中，对每次 LLM 调用自动选模型
- **OpenAI GPT-5 Auto**：在聊天端自动在 Instant / Thinking 间切换
- **LiteLLM Auto Router / Cloudflare Dynamic Routing**：基于规则或 embedding 的 per-query 路由
- **学术 router**：RouteLLM、CARROT、OmniRouter（训练一个预测器来估计 per-query 性价比）
- **RL-based agentic router**：把多步路由建模为 RL 策略学习问题

它们都在回答同一个问题："**这一次** LLM 调用该用哪个模型？"

本文不和它们抢这个问题。本文回答的是更上一层的问题：

> **在一个甚至多个完整的 agent workflow（每个 workflow 包含多步 LLM 调用）中，如何利用 workflow 级的结构信息（哪一步关键、剩多少预算、多个 workflow 怎么共享资源），做整体的成本-质量分配？**

### 真正的 gap：现有 auto-router 都是 workflow-blind 的

- **workflow-aware**：路由决策会使用 workflow 级状态，例如：这个 workflow 还剩多少预算、当前花钱速度是否合理、同一时间有多少 workflow 在共享并发/RPM 资源，以及当前 LLM 调用的决策上下文是否关键（$w_i$，可显式传入，也可由工具输出/observation 推断）。**不需要提前知道 workflow 总共有多少步**——`budget_factor` 是闭环反馈，$w_i$ 是每次调用时从可用信号获得。
- **workflow-blind**：路由决策主要依赖本次调用的局部信息（prompt/token/延迟），不维护 workflow 预算状态，也不接收或推断跨步骤的重要性信号，因此无法做跨步骤预算配速或跨 workflow 调度。

| Per-call router 通常看得到 | AgentOS 额外维护 / 获取的 workflow 级信号 |
|-----------|----------------------------------|
| 当前这次 prompt 的内容、长度、复杂度 | 本 workflow 的预算上限、已花成本、剩余预算 |
| 模型成本与能力差异 | `budget_factor`：花钱速度相对预算水位是偏快还是偏慢 |
| 大致 latency 和 token 消耗 | 当前并发 workflow 数、全局 RPM / concurrency 压力 |
| 用户订阅 tier | 当前调用的决策上下文重要性 $w_i$：显式传入、callback 结构化获得，或从 LLM request 中的 ToolMessage / Observation 推断 |
| | 例如目录列表通常是低风险导航；测试失败 traceback 通常是高风险诊断 |

**这不是 per-call router 不努力，是架构上"没有状态"**——普通 router 只处理孤立请求，而 AgentOS 维护 workflow ledger、预算水位、全局资源压力，并在可获得时使用当前调用的重要性信号。

### 本文的定位：agent 框架与 LLM 后端之间的 workflow-aware 治理中间层

```text
 +----------------------------------+       +-----------------------------+
 | LangChain / SWE-agent / AutoGen  |       | Self-built agent platform   |
 +----------------------------------+       +-----------------------------+
       |                    |                         |
       | Proxy mode:        | Callback mode:          | Explicit mode:
       | LLM request msgs   | tool events + metadata  | task_type + w_i
       v                    v                         v
 +------------------+ +------------------+      +------------------+
 |  AgentOS Proxy   | | AgentOS Adapter  |      |   AgentOS SDK    |
 +------------------+ +------------------+      +------------------+
          \                  |                         /
           \                 |                        /
            +----------------+-----------------------+
                             |
                             v
                    +--------------------+
                    |  AgentOS Runtime   |
                    +--------------------+
                             |
                             v
          +-------------------------------------+
          | Governor: budget + RPM + concurrency |
          +-------------------------------------+
                             |
                             v
       +------------------------------------------+
       | ModelSelector: budget_factor + importance |
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

**Proxy mode 的例子**：开发者原本已经在用 LangChain / SWE-agent / AutoGen 造 agent；AgentOS 只是在 **LLM API 层** 插进去：开发者把 LLM client 的 `base_url` 从 OpenAI 改成 `http://localhost:8080/v1`，框架仍然发送普通 chat completion 请求。AgentOS proxy 接住这次请求，读取 `messages` 以及其中可能包含的 ToolMessage / Observation（也就是上一步 tool output 被放回 prompt 的部分），再结合 workflow 预算状态，决定把请求转发给 GPT-5、mini、本地 Llama 或其他后端。

```text
Developer's agent code
  -> LangChain / SWE-agent
  -> OpenAI-compatible client
  -> AgentOS proxy endpoint
  -> real backend LLMs
```

**Explicit mode 的例子**：这里的"自研平台"指的是：团队没有用 LangChain 这类框架，而是自己写了 agent loop——自己决定什么时候 planning、什么时候调用 tool、什么时候再问 LLM。AgentOS 不接管这个 loop，只替换其中"调用 LLM"这一行。

```python
# 原来：平台自己直接调用某个模型
response = openai.chat.completions.create(
    model="gpt-5",
    messages=messages,
)
```

接入 AgentOS 后，改成：

```python
# 现在：把这一步的类型和重要性一起告诉 AgentOS
response = agentos.chat(
    messages=messages,
    task_type="debugging",
    w_i=3.0,
    workflow_id=run_id,
)
```

也可以拆得更底层：AgentOS 只负责选模型，平台仍然用自己的 LLM client 发请求。

```python
backend = agentos.select_model(task_type="planning", w_i=3.0, workflow_id=run_id)
response = llm_client.chat(model=backend.name, messages=messages)
agentos.record_usage(workflow_id=run_id, backend=backend, response=response)
```

所以 Explicit mode 不是让 AgentOS 变成 LangChain-like 框架；它只要求 AgentOS 提供 `chat(...)` 或 `select_model(...)` 这类 workflow-aware LLM 调用接口。上层平台显式告诉 AgentOS：这一步是什么类型、重要性多高；AgentOS 不需要从 observation 里猜 $w_i$。

**一句话**：AgentOS 不依赖某一个上层 agent 框架。它可以作为 OpenAI-compatible proxy 接在 LangChain / SWE-agent / AutoGen 下面，也可以通过 callback / middleware 获取结构化工具事件，还可以被自研 agent 平台通过 SDK 显式调用。本文的核心不是重做一个 LangChain，而是把 LLM 路由从"孤立请求选择模型"提升为**有状态的 workflow 预算-质量优化**。

其中最接近的竞争工作是 **Budget-Aware Agentic Routing（BoPO, Zhang et al. 2026）**：它也关注 agent workflow 内的预算感知路由，但把问题建模为单 task 的 RL 策略学习。核心差异集中如下：

| 维度 | Per-call router（RouteLLM / CARROT / GPT-5 Auto 等） | 最接近的 RL agentic router | **本文** |
|------|---------------------------------------------|------|---------|
| **核心优化对象** | 单次 request 的模型选择 | 单个 task / episode 内的路由策略 | **全局 stateful runtime：多 workflow 共享预算下的质量-成本优化** |
| **状态范围** | 基本无 workflow 状态 | 单 task 内状态 | **跨 step + 跨 workflow 的 ledger：已花成本、剩余预算、burn rate、并发/RPM 压力** |
| **预算语义** | 不管预算或只做 per-query cost 估计 | 训练时 soft budget，推理时受约束 | **运行时 hard budget + 闭环配速，防止前期花光预算** |
| **质量目标** | 局部性价比或偏好预测 | RL 奖励最大化 | **显式最大化 budget-constrained quality：把钱分给更高价值步骤** |
| **任务价值信号** | 单次 prompt 内容 | 稀疏任务奖励 | prompt + **显式/推断的重要性 $w_i$** + 预算状态 |
| **多 workflow 并发** | 无 | 无 | **admission control + 跨 workflow 协调，避免资源饥饿** |
| **训练需求** | 需训练（CARROT/RouteLLM）或无 | SFT + RL | **零训练，启发式 + 在线反馈即可部署** |
| **后端选择空间** | 可 N-ary，但仍 per-call | 通常二元 cheap / expensive | **N-ary 后端池；这是收益来源之一，但不是最核心区别** |
| **止损机制** | 无 | 无 | 僵尸检测 + 截断 |

### 谁会真正用这个？

AgentOS 的目标用户是**造 agent 的人**和**运营 agent 平台的团队**——不是终端用户。具体三类：

- **Agent 框架 / agent 产品的构建者**（SWE-agent、LangChain、AutoGen、Moatless、MetaGPT 等开源框架的维护者，以及自研 agent 的创业团队和企业小队）：通过 proxy、callback/middleware 或 SDK 接入 AgentOS，把原本 workflow-blind 的 LLM 调用纳入统一预算和调度
- **单团队 agent 平台的运营方**（持有单一预算池、对内或对外服务多并发 agent 请求的产品团队 / 平台团队 / DevOps 团队）：把 AgentOS 当作内部 LLM 网关，让多 agent 在共享预算池下不打架
- **研究者**：把 AgentOS 当 evaluation harness 跑 SWE-bench、HumanEval 等基准的多策略对比

无论 1 个 agent 6 步还是 50 个 agent 6 步，"哪一步该推到多好"都是核心决策。**多预算主体（多团队 / 多部门 / 多 SLA 共享同一 agent 平台）的层级仲裁是 paper 边界外的问题**，留作 future work（§12）。

### 旗舰场景：50 个 SWE-agent 并发跑 SWE-bench Verified

**场景设定**：研究者用 SWE-bench Verified（500 题）评估自己的 agent 框架。开 50 个 SWE-agent 并发跑，固定**总预算 \$50**（名义人均 \$1），后端池 5 个：GPT-5 Thinking / GPT-5 Instant / GPT-5 mini / Claude Sonnet / 本地 Llama-3-70B-Int4。每个 agent 平均 6–12 个 turn，50 并发峰值产生约 400 RPM（逼近 OpenAI tier-3 的 500 RPM 限额）。

**不上 AgentOS 会发生什么？**

| 失败模式 | 原因 | 后果 |
|----------|------|------|
| RPM 雪崩 | 50 agent 同时发请求，瞬间打满 500 RPM | 大量 429 错误，约一半 agent 在关键步骤失败 |
| 预算失控 | 没有配速——先跑的 10 个 agent 把贵模型预算花光 | 后 40 个 agent 全程只能用 mini，QWCR 严重下降 |
| 资源饥饿 | 跑得快的 agent 吃光并发槽和 RPM 配额 | 跑得慢或后启动的 agent 被系统性饿死 |
| 僵尸占槽 | 卡死的 agent 占着并发槽不释放 | 健康 agent 排队等位，整体吞吐下降 |

**上 AgentOS 后四条机制如何协同？**

| AgentOS 机制 | 在本场景中做什么 |
|-------------|----------------|
| **Governor** | 顶住 400 RPM 峰值——admission control 排队而非雪崩，预算硬封顶保证 \$50 不超支 |
| **ModelSelector** | 基于 `budget_factor` 和显式/推断 $w_i$ 决定是否升档：测试失败诊断等高风险上下文倾向好模型，目录浏览/search 等低风险上下文倾向便宜模型；从 5 个后端的成本梯度中选最佳档位，而非二选一 |
| **WFQ Scheduler** | 50 个 agent 按 weighted fair queuing 分享 RPM/并发槽，保证后启动的 agent 不被先启动的吃光资源 |
| **ZombieDetector** | 检测卡死 agent 并释放其并发槽和预算残值，回收给健康 agent |

此外，混合后端池（GPT-5 系列 + Claude + 本地 Llama-3-70B）天然演示了 §0.5.3 的 cost-model-agnostic 性质——同一算法在 USD 计价的 API 后端和本地摊销成本的本地后端上无需修改即可工作。

---

## 0.5 部署形态、落地场景与成本模型

### 0.5.1 形态：Proxy / Callback / SDK 三种接入

AgentOS 是基础设施，不是端用户产品——使用 agent 应用的人不直接接触 AgentOS，AgentOS 在 agent 框架内部对端用户透明。

- **HTTP sidecar proxy（零改代码主形态）**：部署一个 OpenAI-compatible 本地服务，agent 只需把 `base_url` 指向 `http://localhost:8080/v1`。AgentOS 能看到最终发给 LLM 的 `messages`：prompt、history、ToolMessage、ReAct 风格的 `Observation: ...` 等。如果 tool name 出现在标准 tool message 里，AgentOS 直接解析；如果只看到纯文本 observation，则用规则/小模型判断这是目录列表、搜索结果、测试失败还是普通命令输出。
- **Framework adapter（轻量集成形态）**：对 LangChain / SWE-agent / AutoGen 这类框架写 callback / middleware adapter，直接接收结构化事件：tool name、tool args、tool output、step index、run id 等。LangChain middleware 有 `wrap_tool_call`，SWE-agent 有 `on_model_query` / `on_action_executed` / `on_step_done` hooks，AutoGen 的 tool agent 会返回带 `name` 的 `FunctionExecutionResult`。这一层比 proxy 更准，但仍不要求开发者逐个 LLM 调用手写权重。
- **Python SDK（显式形态）**：自研 agent 平台可以直接 `import agentos`，把原本的 `openai.chat.completions.create(...)` 替换为 `agentos.chat(messages=[...], task_type="planning", w_i=3.0, budget=0.5)`。这是信号最干净的集成方式，也是本文用于解释 ModelSelector contract 的标准接口。

### 0.5.2 落地场景：单一预算主体 + 多并发 workflow

AgentOS 的 scope 是 **"单一预算主体下的多并发 workflow"**——下标 $j$（§2.2 公式）是同一钱包之下的并发 workflow 数，不跨多预算主体。在这一结构上，论文识别四个具体的落地场景：

| # | 场景 | 单一预算主体 | 一个 workflow = 什么 | 论文实验是否覆盖 |
|---|------|------------|---------------------|----------------|
| 1 | 研究 benchmark 评估 | 研究者本人 | 一道 SWE-bench 题目 | **是**（§7 RQ4 旗舰） |
| 2 | 单团队生产 agent 服务 | 创业团队 / 产品团队 | 一次外部用户请求（如 PR review、客服会话、数据抽取） | 机制类比，不跑实验 |
| 3 | CI / 批量评估管线 | DevOps / 数据团队 | 一次 commit 触发的 agent 任务（如 nightly 测试生成、代码审计） | 机制类比，不跑实验 |
| 4 | 公司内部开发者工具 | 平台团队 | 一名工程师的一次请求（如"问代码库" agent、内部 RAG agent） | 机制类比，不跑实验 |

四个场景共同结构是 **"单一预算主体（一个钱包）+ 多并发 workflow + 共享 RPM/并发上限"**——对应 §2.2 的多 workflow 优化问题。这一结构带来两个具体好处：

- **保证后启动的 workflow 不被先启动的吃光资源**：FIFO 分配下先启动的 agent 会用尽贵模型配额，后启动的 agent 在关键 planning 步只能用最便宜模型。AgentOS 通过 §5.2 的 weighted fair queuing 让每个 workflow 获得稳定的资源份额。
- **保证单个失控 workflow 不污染整体预算**：某个 agent 卡死或陷入循环时，AgentOS 通过 §4 的 ZombieDetector 截断它，回收并发槽和预算残值给健康 agent。

> **关键说明**：即便场景 4 的 agent 服务于全公司多个工程团队，AgentOS **不需要建模这些下游团队的归属**——平台团队是预算所有者，下游用户在 AgentOS 视角里全部坍缩为"并发 workflow"。多预算主体（跨团队 quota 仲裁 + SLA 抢占）是不同问题，见 §12 future work。

### 0.5.3 Cost Model Agnostic：scope 内的核心性质

§2.5 的 N-ary 后端选择器**只依赖后端之间的成本梯度**（哪个比哪个贵多少），不依赖货币单位本身。这意味着 AgentOS 在以下三种成本模型上**直接成立、无需修改算法**：

| 成本模型 | 成本如何换算 | 代表性场景 |
|---------|------------|----------|
| 纯 API 计价 | 后端单价 = 模型 USD/1K tokens | OpenAI / Anthropic 等付费 API 用户 |
| 本地 GPU 摊销 | 后端单价 = （硬件折旧 + 电费 + 运维成本）÷ 服务的 token 总量 | 自有 H100 集群跑本地 Llama-3-70B-Int4 |
| **混合**（最常见） | 不同后端用不同模型计价，统一成"每 1K tokens 多少钱" | **本文 §7 后端池**：GPT-5 系列 API + 本地 Llama-3-70B |

**本地 GPU 不是免费的**——它仍是稀缺资源、仍有折旧 / 电费 / 运维成本——只是单价比 API 低 5–10x。字节、阿里、Meta 这种"既有大量本地 GPU、又调用外部前沿模型 API"的混合部署是 AgentOS 的一线用例。§2.5 的 tier-progressive 决策只看相邻 tier 的 $\Delta c$（成本差），不关心成本是怎么算出来的。

**这是 paper 1 scope 内的核心性质，不是 future work**——§2.5 公式已经支持，本文以 §7 的混合后端池作为佐证。

### 0.5.4 最小代码示例（三种形态）

**Proxy 形态（SWE-agent / LangChain / AutoGen 零改 agent loop）**：

```yaml
model:
  name: gpt-5
  api_base: "http://localhost:8080/v1"  # 指向 AgentOS proxy
```

此时上层框架仍按原来的方式执行 agent loop。AgentOS 在 LLM request 进入后解析 `messages`，从 ToolMessage / Observation 中推断当前调用的重要性，并维护 workflow 预算状态。

**Adapter 形态（结构化工具事件）**：

```python
class AgentOSLangChainMiddleware(AgentMiddleware):
    def wrap_tool_call(self, request, handler):
        # LangChain 调用这个 middleware；handler 才是真正执行 tool 的函数。
        result = handler(request)
        agentos.observe_tool(
            workflow_id=runtime.run_id,
            tool_name=request.tool_call["name"],
            tool_args=request.tool_call["args"],
            tool_output=result.content,
        )
        return result

agent = create_agent(..., middleware=[AgentOSLangChainMiddleware()])
```

方向是 **AgentOS → LangChain**：AgentOS 提供一个符合 LangChain callback / middleware 接口的类，用户注册进去；运行时 LangChain 在 tool call 前后自动调用它。这个 adapter 不改变 agent 的决策逻辑，只把上层框架已经知道的 tool metadata 暴露给 AgentOS。

**SDK 形态（显式信号）**：

```python
import agentos

client = agentos.Client(
    budget=0.50,
    backends=["gpt-5-thinking", "gpt-5-instant", "gpt-5-mini",
              "claude-sonnet", "llama-3-70b-int4-local"],
)

plan = client.chat(
    messages=[{"role": "user", "content": "重构这个模块为三个文件"}],
    task_type="planning", w_i=3.0,
)
code = client.chat(messages=[...], task_type="generation",  w_i=3.0)
chk  = client.chat(messages=[...], task_type="validation",  w_i=1.0)
```

无论哪种接入方式，AgentOS 在内部完成路由（§2.5）、限流（§4 Governor）、僵尸检测（§4 ZombieDetector）、跨 workflow 协调（§5）。差别只在于 $w_i$ 的来源：显式传入、结构化事件推断、或从 request 文本中推断。

---

## 1. 核心洞察：LLM 质量是连续的，调度问题变了

经典操作系统调度假设任务结果是二元的——完成或失败。LLM 不同——**几乎总能给答案，差别在于答案好坏**：

| 后端配置 | 质量 $q$ | 每次调用成本 |
|---------|---------|------------|
| GPT-5 Thinking + 长 context | $\approx 0.95$ | \$0.10 |
| GPT-5 Instant | $\approx 0.70$ | \$0.01 |
| Claude Sonnet | $\approx 0.80$ | \$0.03 |
| Llama-3-70B-Int4（本地） | $\approx 0.55$ | \$0.002 |
| GPT-5 mini | $\approx 0.40$ | \$0.001 |

五种都"完成"了任务，但质量在 $[0,1]$ 上连续变化。于是调度问题从"谁先跑"变成：

> **预算有限时，每个步骤应该被做到多好？**

这里有 5 个后端可选，不是 2 个——这就是"N-ary"。本文支持任意多个后端，因此可以利用更细的 cost-quality 梯度。

---

## 2. 形式化：预算约束下的质量最大化

### 2.1 单 workflow 场景

一个 workflow 有 $N$ 个 turn（每个 turn 是一次 LLM 调用）。每个 turn $i$ 选一个后端 $a_i \in \mathcal{A}$（后端池，如上表 5 个选项）：

$$
\max_{a_1,\dots,a_N}\ \sum_{i=1}^{N} w_i\,q_i(a_i)\quad \text{s.t.}\quad \sum_{i=1}^{N} c_i(a_i)\le B
$$

各符号含义：
- $q_i(a_i) \in [0,1]$：turn $i$ 选后端 $a_i$ 时的输出质量（由 benchmark grader 打分，见 §3）
- $c_i(a_i)$：对应的成本（USD / 本地 GPU 摊销 / 混合，见 §0.5.3）
- $w_i$：任务价值权重——**由显式声明、callback/tool event 或 Observation 推断获得**（如高风险诊断 $w=3$，低风险检索 $w=1$）
- $B$：总预算硬约束
- $\mathcal{A}$：可用后端集合（N-ary，不限于二元）

这个问题本质是"多选择背包"的变体。

### 2.2 多 workflow 场景（本文扩展）

设有 $J$ 个并发 workflow，第 $j$ 个 workflow 有自己的 turn 集合 $W_j$ 和预算 $B_j$：

$$
\max \sum_{j=1}^{J} \sum_{i \in W_j} w_{j,i}\,q_{j,i}(a_{j,i}) \quad \text{s.t.}\quad
\begin{cases}
\sum_{i \in W_j} c_{j,i}(a_{j,i}) \le B_j & \forall\, j \\
\text{RPM}(t) \le R_{\max} & \text{（全局每分钟请求数限制）} \\
\text{Concurrency}(t) \le K_{\max} & \text{（全局并发槽限制）}
\end{cases}
$$

**Scope 注**：下标 $j$ 是**同一预算主体之下**的并发 workflow——例如同一研究者跑的多个 SWE-bench 题目，或同一团队 agent 服务收到的多个用户请求。本文不建模多预算主体的 quota 仲裁，相关问题见 §12 future work。

> **前置知识**：RPM = Requests Per Minute，是 API 提供商对每分钟请求数的限制。并发槽是指同时在飞的请求数上限。这两个约束意味着不同 workflow 之间在**抢共享资源**，不能各自独立优化。

### 2.3 对照组

| 对照组 | 策略 | 失败模式 |
|--------|------|---------|
| A. `always_expensive` | 每步都用最贵模型 | 很快花光预算，后半段没钱 |
| B. `per_request_greedy` | 每步独立最大化 $q/c$ | 不做配速、不看 $w_i$，后期质量下降 |
| C. `budget_aware_uniform` | 有预算配速，但 $w_i \equiv 1$ | 不区分任务价值——关键步和琐碎步给同样资源 |
| **D. AgentOS** | 预算配速 + 任务价值 $w_i$ + 边际性价比 | 在线近似，非离线最优 |
| **E. `binary_backend`** | 限制为二元后端 + 不用 $w_i$ | 检验多后端梯度和任务价值信号的贡献 |

D vs E 的差异可以**直接归因于** N-ary 后端 + 显式/推断 $w_i$ 信号的贡献。

### 2.4 最优性直觉（KKT 一阶条件）

将问题推广为连续版，KKT 条件给出：

$$
\frac{w_i}{c_i'(q_i)} = \lambda \quad \text{（对所有内点 turn）}
$$

$\lambda$ 是预算约束的"影子价格"（shadow price）——**最优时，每个 turn 的"每美元加权边际收益"趋于同一个水位线**。工程实现中 `budget_factor` 就是 $\lambda$ 的在线近似：花快了调高、花慢了调低。

### 2.5 边际加权性价比（ModelSelector 的排序准则，N-ary 版）

将后端池 $\mathcal{A}$ 中的 $N$ 个后端按成本升序排列：$a_1 \prec a_2 \prec \dots \prec a_N$。定义**逐 tier 边际增量**：

$$
\Delta q_i^{(k)} = q_i(a_{k+1}) - q_i(a_k), \quad \Delta c_i^{(k)} = c_i(a_{k+1}) - c_i(a_k)
$$

**决策规则（tier-progressive）**：对 turn $i$，从最便宜的 $a_1$ 起，逐 tier 评估"再升一档值不值"：

$$
\text{升级条件：} \quad w_i \cdot \frac{\Delta q_i^{(k)}}{\Delta c_i^{(k)}} \ge \lambda
$$

选中的后端是满足上式的**最高 tier**。若所有 tier 都不值得升级（$\lambda$ 很高 = 预算紧），则留在 $a_1$（最便宜）。

| 符号 | 含义 | 怎么算 |
|------|------|-------|
| $w_i$ | 这一步的任务价值权重 | 显式传入、callback 结构化推断，或从 ToolMessage / Observation 推断（见 §2.6） |
| $\Delta q_i^{(k)}$ | 从 tier $k$ 升到 tier $k+1$ 能多换多少质量 | 基于历史统计先验（EWMA 更新，按 task_type × 后端对分组） |
| $\Delta c_i^{(k)}$ | 升一档要多花多少钱 | 按 token 单价 × 估计 token 数 |
| $\lambda$ | budget_factor（预算紧则高、松则低） | 闭环反馈在线更新 |

**数字例子**（5 个后端、两个 turn 并行竞争升级，$\lambda=0.20$）：

| 步骤 | $w_i$ | 当前 tier | 下一 tier | $w_i \cdot \Delta q / \Delta c$ | 决策 |
|------|-------|----------|----------|-------------------------------|------|
| 规划步 | 3 | Instant (\$0.01) | Sonnet (\$0.03) | **1.50** | 升级 |
| 规划步 | 3 | Sonnet (\$0.03) | Thinking (\$0.10) | **0.64** | 升级 |
| 检索步 | 1 | Instant (\$0.01) | Sonnet (\$0.03) | **0.50** | 升级 |
| 检索步 | 1 | Sonnet (\$0.03) | Thinking (\$0.10) | **0.07** | 不升级 |

结果：规划步一路升到 Thinking（$w=3$ 放大了每次升级的加权收益），检索步停在 Sonnet。**N-ary 后端让"升到哪一档"成为连续渐进的决策，而非二选一的粗粒度跳跃**。

**理论根基**：拉格朗日松弛 / KKT 一阶条件 + 多选择背包贪心近似（Sinha & Zoltners 1979, Dantzig 1957）。**思想是教科书标准，公式是本文对 LLM agent 路由场景的首次 N-ary 具体化**。

### 2.6 $w_i$ 如何获得？

$w_i$ 不是必须由 agent 框架手写声明。AgentOS 支持从强到弱的 5 个信号来源；信号越强，ModelSelector 越接近 oracle；信号越弱，则更多依赖 `budget_factor` 做预算配速。

| 档位 | 接入方式 | $w_i$ 来源 | 典型场景 |
|------|----------|-----------|----------|
| **L4 显式数值** | SDK / 自研平台 | `agentos.chat(..., w_i=3.0)` | 平台自己知道某一步是关键 planning / validation |
| **L3 显式类型** | SDK / 自研平台 | `task_type` 查表 | `planning→3, generation→2, validation/retrieval→1` |
| **L2 Callback 推断** | framework adapter | tool event + observation metadata | LangChain middleware、SWE-agent hook、AutoGen tool event |
| **L1 Proxy 推断** | HTTP sidecar | LLM request 中的 ToolMessage / Observation 文本 | 只改 `base_url`，零改 agent loop |
| **L0 Budget-only** | 无可用信号 | $w_i \equiv 1$，仍使用 `budget_factor` | 退化到预算感知 baseline |

**Observation-based importance 的原则**：AgentOS 不预测 agent 下一步会调用哪个工具，而是判断"当前 LLM 调用看到的上下文有多关键"。

| 当前 LLM 输入包含什么 | AgentOS 的判断 | 默认 $w_i$ |
|---------------------|---------------|------------|
| 目录列表（如 `ls src/` 输出） | 低风险导航；选错文件通常可恢复 | 1.0 |
| 搜索结果 / 文件列表 | 检索导航；有用但通常可继续修正 | 1.0–1.5 |
| 源码片段 | 需要理解代码，可能影响后续编辑 | 2.0 |
| 测试失败 / traceback | 高风险诊断；误判 root cause 会导致错误编辑和预算浪费 | 3.0 |
| 编辑成功提示 | 中等重要性；下一步可能继续编辑或进入验证 | 1.5–2.0 |
| 测试全部通过 | 通常进入收尾或提交 | 1.0 |

**怎么知道上层用了哪个 tool？** Proxy mode 只能看到"最终喂给 LLM 的内容"：如果标准 tool message 带 `name` / `tool_call_id`，就结构化解析；如果只是 `Observation: ...` 文本，就用规则或小模型分类 observation 类型。Callback mode 则直接接入上层框架事件：LangChain 的 `wrap_tool_call` 可读到 `request.tool_call["name"]`，SWE-agent hook 可读到 action / step，AutoGen 的 `FunctionExecutionResult` 带有 tool name。本文把这层称为**信号抽取层**，其输出统一变成 `TurnInfo(task_type, w_i, workflow_id, step_index, ...)` 供 ModelSelector 使用。

§3.4 消融实验 E1–E9 证明：权重越准收益越高；proxy / callback 的粗粒度推断也有收益；没有重要性信号时退化到 budget-only baseline，而不是依赖 oracle 标注。

### 2.7 N-ary 后端的现实性检查

**代价 1：先验矩阵规模从 $O(T)$ 涨到 $O(T \times N)$**。应对：静态先验表 + EWMA 在线更新 + 冷启动回退。

**代价 2：部分后端可能被 Pareto 支配**。应对：启动期 Pareto 剪枝——按 task_type 分组，剔除被严格支配的后端。预计有效 N 在 3–5 之间。**N-ary 的价值不是"5 个后端全被用上"，而是"成本梯度够细"**——即使有效 N=3，也比二元多出一个中间档。

**代价 3：更大的后端集合会扩大搜索空间**。应对：本文默认使用启发式边际收益排序，而不是训练一个覆盖全部 action space 的策略；action 数从 2 扩展到 N 时，学习型策略通常需要更多样本。

---

## 3. 质量怎么衡量？

**核心原则**：不自己发明评分标准——**复用社区已经广泛认可的 benchmark grader**。

**实验场景 vs 落地场景的客观性边界**：本文实验的 quality 测量全部使用社区标准 deterministic grader。§0.5.2 的四个落地场景中，**只有场景 1（研究 benchmark 评估）直接落入这些 grader 的覆盖范围**，故 §7 RQ4 实证集中在场景 1；场景 2-4 是机制类比的可推广性主张，本文不在这些场景上跑实验。

### 3.1 评估策略：使用社区标准 Benchmark

| task_type | Benchmark | 评分方式 |
|-----------|-----------|---------|
| `bug_fix`（agentic SE） | **SWE-bench Verified** | fail-to-pass 测试 |
| `code_generation` | **HumanEval** | pass@1 |
| `reasoning` | **GSM8K** | exact match |
| `math` | **MATH** | exact match |

全部 deterministic、全部高度采纳、全部不是我们发明的标准。

### 3.2 实验中的两种模式

| 模式 | $q_i$ 来源 | 用途 |
|------|-----------|------|
| **Mock 实验**（主线） | workload 预设的 `quality_score` | 控制变量：比的是"谁会分配预算"而不是"LLM 本身强不强" |
| **真实 LLM 实验**（补充） | 调用真 LLM + benchmark grader 打分 | 验证 mock 结论在真实模型上成立 |

### 3.3 决策侧 vs 评估侧（必须解耦）

- **决策时**：ModelSelector 用先验估计 $\Delta \hat{q}_i$（历史统计 / 静态表），不需要知道本次真实分数
- **评估时**：用 benchmark grader 得到真实 $q_i$，计算 QWCR / Q/\$ 等指标

### 3.4 先验不准怎么办？

消融实验 E1–E9：

| 实验 | 设置 | 回答什么 |
|------|------|---------|
| E1 Oracle | workload 参考权重 | 上限 |
| E2 二档 | high/low 两档 | 粗分也有收益 |
| E3 task_type 表 | 按类型固定权重 | 无精细标注也能落地 |
| E4 加噪 | $w_i$ + 噪声 $\sigma=0.3/0.5/1.0$ | 对权重误差鲁棒 |
| E5 随机 | 随机 $w_i$ | 最坏情况 |
| E6 全 1 | $w_i \equiv 1$ | 自洽检查：应退化到对照组 C |
| **E7 binary-backend** | 限制只有 cheap/expensive 两个后端 | 验证 N-ary 成本梯度的贡献 |
| **E8 proxy-inferred** | 只从 LLM request messages / Observation 文本推断 $w_i$ | 零改代码接入能拿到多少收益 |
| **E9 callback-inferred** | 从 LangChain/SWE-agent/AutoGen 结构化 tool event 推断 $w_i$ | 轻量 adapter 比纯 proxy 提升多少 |

预期排序是：Oracle > callback-inferred > proxy-inferred > 全 1。本文不要求推断器达到 oracle 精度；只要能稳定区分"测试失败诊断"和"目录浏览/普通检索"这类明显高低价值场景，就能在相同预算下优于 $w_i \equiv 1$。

---

## 4. 系统架构：policy-agnostic 的 workflow-aware runtime

> "policy-agnostic" 是指系统基础设施（预算管控、限流、僵尸检测等）**不绑定任何特定的路由策略**。你可以换掉"怎么选模型"的部分，其他所有机制照常运行。

```
Agent Workflow（N 个 LLM 调用步骤）× J 个并发 workflow
        │
        ▼
═══════════════════ AgentOS ═══════════════════
│ 【约束层】Governor                           │  ← policy-agnostic
│   预算硬封顶 + API RPM 限流 + 并发准入        │
│                                              │
│ 【优化层】ModelSelector（可插拔）             │  ← 唯一 routing policy
│   本文默认：边际加权性价比 + budget_factor    │
│   可替换为：RL policy / CARROT / ...         │
│                                              │
│ 【止损层】ZombieDetector + Preemption        │  ← policy-agnostic
│   僵尸截断 + 交互式任务抢占                   │
│                                              │
│ 【调度层】Multi-Workflow Scheduler           │  ← policy-agnostic
│   跨 workflow 协调 + admission control       │
═══════════════════════════════════════════════
        │
        ▼
LLM 后端池 → events.jsonl → 指标计算
```

**只有 ModelSelector 是 routing policy**，其余全部 policy-agnostic。任何 routing policy（包括学习型策略）都可以接入并共享所有系统机制。

### 4.1 ModelSelector 可插拔接口

```python
class ModelSelectorPolicy(ABC):
    @abstractmethod
    def select(self, turn: TurnInfo, gov_state: GovernorState,
               backends: list[Backend]) -> Backend: ...
```

本工作实现了 4 个 policy：`WorkflowAwareHeuristic`（主贡献）、`PerCallGreedy`（对照组 B）、`BudgetAwareUniform`（对照组 C）、`CARROTStylePredictor`（per-call baseline）。学习型 agentic routing policy 的接入留作 future work（接口已就绪，需要额外训练资源）。

---

## 5. Multi-Workflow 并发调度

一个 workflow = 一个任务从开始到结束的一串 LLM 调用步骤。multi-workflow = 同一时间有很多个 workflow 在跑，共享同一组资源。

### 5.1 为什么需要这一层

50 个 SWE-agent 同时跑时，系统处于 RPM 限额的 80% 水位。如果不做调度：先到先得导致后启动 agent 被饿死、前几个 agent 把贵模型预算花光、卡死 agent 占着并发槽不释放。

per-task 路由策略本身不处理这一层——要覆盖多 workflow 并发，需要把共享预算、队列和 RPM/concurrency 压力纳入 runtime 级状态。

### 5.2 调度算法：Weighted Fair Queuing

本文的多 workflow 调度有三个组件：

1. **每 workflow 独立 budget tracker**：每个 workflow 有自己的预算 $B_j$ 和 budget_factor $\lambda_j$
2. **跨 workflow weighted fair queuing**：共享 RPM/并发槽按 workflow 优先级加权分配
3. **Admission control**：资源满载时排队——不需要预测到达分布

### 5.3 Workload 不确定性处理

**本系统不依赖 workload 预测，也不需要任何 ML 训练**：

| 不确定性 | 处理方式 |
|----------|---------|
| 并发 workflow 数量未知 | Admission control：满了就排队 |
| 每 turn 的 cost/quality 未知 | 闭环 budget_factor 反馈 |
| 新 task_type 的 quality 先验冷启动 | EWMA 在线更新 + 静态先验回退 |

---

## 6. 评估指标

### 6.1 单 workflow 指标

| 指标 | 公式 | 含义 |
|------|------|------|
| **QWCR** | $\frac{1}{N}\sum q_i$ | 平均质量（失败记 0） |
| **Q/\$** | $\sum q_i / \text{cost}$ | 每美元质量产出 |
| **WQ/\$** | $\sum w_i q_i / \text{cost}$ | 每美元加权质量产出 |
| **Pareto 图** | 横轴 cost, 纵轴 QW-Completed | 核心论证图 |

### 6.2 多 workflow 指标

| 指标 | 含义 |
|------|------|
| **Cross-workflow QWCR 方差** | 方差越小说明 workflow 间质量越一致 |
| **Jain's Fairness Index** | 度量后启动 workflow 是否被先启动者吃光资源（1 = 完全均等，$1/J$ = 最不均等） |

三个指标联合报告：Jain's FI + QWCR 方差 + 整体 Pareto 前沿。

---

## 7. 五条 RQ

| RQ | 问题 | 对应机制 | 核心指标 |
|----|------|---------|---------|
| **RQ1** | 不加治理时 429 限流雪崩 | Governor | error_429_rate, 完成率 |
| **RQ2**（主贡献） | 同预算下，任务价值感知的模型选择是否提升质量？ | ModelSelector | QWCR, WQ/\$, Pareto |
| **RQ3** | 僵尸调用截断后改善多少？ | Zombie + Preemption | Q/\$ 提升 |
| **RQ4**（旗舰） | 50-agent 并发评估：固定总预算、AgentOS 能否同时维持整体 Pareto 前沿和跨 workflow 质量一致性？ | 全部机制 | Jain's FI, QWCR 方差, Pareto, 429 率, N-ary 使用分布 |
| **RQ5** | 未来任务量未知且突发增长时，budget_factor + admission control 是否仍能控制成本和公平性？ | Governor + budget_factor + Scheduler | budget overrun, queue latency, Jain's FI, Q/\$ |

**RQ4 实验设计**：

| 维度 | 设定 |
|------|------|
| **Workload（mock 主线）** | SWE-bench Verified 子集 100 题 × 50 mock workflow 并发 |
| **Workload（真实佐证）** | 4–6 个真 SWE-agent 并发 × 20 题 |
| **总预算** | \$50 |
| **后端池** | GPT-5 Thinking / Instant / mini / Claude Sonnet / 本地 Llama-3-70B-Int4（N=5） |
| **RPM 限额** | 500 RPM |
| **Burst 设置** | 200 个 workflow replay，中途注入 3x arrival burst；系统事先不知道 burst 到来 |

| 对照组 | 策略 |
|--------|------|
| F1. `round_robin` | 轮流分配 RPM 槽，不看预算也不看 $w_i$ |
| F2. `fifo` | 先到先得 |
| F3. `wfq_no_budget` | WFQ 公平分 RPM/并发，但无 workflow 内预算配速 |
| F4. `budget_only_agentos` | $w_i \equiv 1$，只用 `budget_factor` + WFQ |
| F5. `proxy_inferred_agentos` | 从 LLM request / Observation 文本推断 $w_i$ |
| F6. `callback_inferred_agentos` | 从结构化 tool event 推断 $w_i$ |
| **F7. AgentOS-oracle** | WFQ + Governor + ModelSelector + oracle $w_i$ 上限 |

**RQ5 的关键不是预测未来流量**。AgentOS 不假设知道下午会不会突然多 3 倍任务；`budget_factor` 是反馈控制量：看到花费速度、队列长度、RPM/concurrency 压力上升后，提高升级门槛，让低重要性调用降级到便宜模型，同时用 admission control 和 WFQ 防止前几个 workflow 吃光预算。实验报告 burst 前后昂贵 tier 使用比例、预算超支率、队列延迟和跨 workflow 公平性。

---

## 8. Related Work

### 8.1 Per-query LLM Routing

| 论文 | 方法 | 与本文关系 |
|------|------|-----------|
| **RouteLLM** (2024) | 二元 router (strong/weak) | Per-call baseline |
| **CARROT** (2025) | Cost-aware router | Per-call baseline |
| **OmniRouter** (2026) | 全局约束优化 router | 最接近的 per-query 对手 |

这些工作优化 per-call 决策，不涉及 workflow 结构或多 workflow 调度。

### 8.2 OS-Inspired Agent 系统

| 论文 | 核心问题 | 与本文差异 |
|------|---------|-----------|
| **AgentRM** (2026) | 调度失败 + 上下文退化 | 侧重系统稳定性，不做 cost-quality 优化 |
| **AgentCgroup** (2026) | OS 级资源隔离 | 不涉及 LLM 调用质量 |
| **AIOS** (2024) | 通用 Agent OS 架构 | 宽泛架构，无 cost-quality trade-off |

### 8.3 定位总结

| 研究类别 | 代表工作 | 本文差异 |
|----------|---------|---------|
| Per-query routing | RouteLLM, CARROT, OmniRouter | 本文是 workflow 级 |
| Agentic routing (RL) | xRouter 等 | 本文零训练 + 多 workflow |
| OS 资源管理 | AgentRM, AgentCgroup, AIOS | 本文做 cost-quality 优化 |
| **本文** | AgentOS | **workflow-aware, training-free, multi-workflow cost-quality runtime** |

---

## 9. 关键概念速查

| 概念 | 一句话 |
|------|-------|
| **Turn** | 一次 LLM 调用——调度和计费的最小单位 |
| **Workflow** | 一个完整任务的 LLM 调用序列 |
| **$w_i$** | 当前调用的任务价值权重；可显式传入，也可由 callback/tool event 或 Observation 推断 |
| **$q_i$** | Turn 输出质量 $\in [0,1]$——由社区标准 benchmark grader 打分 |
| **budget_factor** | 预算松紧的在线反馈信号（近似 KKT 的 $\lambda$）；花快了收紧，花慢了放宽 |
| **Governor** | 约束层：预算 + 限流 + 并发 |
| **ModelSelector** | 优化层：可插拔的路由策略 |
| **ZombieDetector** | 止损层：截断"花钱但质量不涨"的调用 |
| **QWCR** | $\frac{1}{N}\sum q_i$——平均质量 |
| **Q/\$** | $\sum q_i / \text{cost}$——每美元质量产出 |

---

## 10. 投稿建议

**首选路线：软件工程（ICSE / FSE / TSE / TOSEM，CCF-A）**

SE 社区缺"面向 LLM Agent 的成本治理基础设施"，对"系统工具 + 扎实实验"接受度高。

**硬件支持**：单卡 A800-SXM4-80GB 可支持 Llama-3-70B-Int4 本地推理 + GPT-5 / Claude API 调用，足以在 SE benchmark 上做真实 LLM 实验。本地+云端混合后端正好体现 N-ary + cost-model-agnostic 优势。

---

## 11. 审稿人常见质疑

**Q: "你只是预算控制做得好。"**
→ 用 `budget_only_agentos`（$w_i \equiv 1$）和 inferred/oracle AgentOS 分开报告。若 budget-only 已优于 per-call baseline，说明 stateful budget control 本身有价值；若 inferred/oracle 进一步提升，差异来自任务价值感知。

**Q: "$q$ 和 $w$ 怎么来？"**
→ $q$ 来自社区标准 benchmark grader；$w$ 有三种来源：显式 SDK、callback/tool event 推断、proxy request / Observation 推断。E1–E9 消融报告 oracle、callback-inferred、proxy-inferred、全 1 的差距。

**Q: "现有 per-call auto-router 已经解决了这个问题。"**
→ 它们是 workflow-blind 的：看不到 workflow 的步骤价值结构、全局预算状态、多 workflow 竞争。AgentOS 解决的是不同层次的问题（详见 §0）。

**Q: "和学习型 agentic router 比呢？"**
→ 核心差异不是换一种 router，而是层级不同：本文是全局 stateful runtime，维护跨 workflow 的 budget ledger、RPM/concurrency 压力和 $w_i$ 信号，在运行时做 hard-budget quality maximization；学习型策略可以作为 ModelSelector 的一个可插拔 policy，但不替代 Governor / Scheduler / ZombieDetector 这些 runtime 机制。

**Q: "budget_factor 怎么处理未来流量突然增加？"**
→ `budget_factor` 不是未来流量预测器，而是在线反馈控制量。突发流量由 admission control、WFQ 和 tier 降级共同处理；RQ5 用 200-workflow replay + 3x arrival burst 验证在未知 burst 下的预算超支率、队列延迟和公平性。

**Q: "为什么不复现 RL router 做端到端对比？"**
→ 完整的 SFT + RL 训练 pipeline 需要 multi-GPU 资源。本工作单卡 A800 足以做推理实验但不足以复现这类训练流程。接口已预留，集成留作 future work。

**Q: "N-ary 真的有用吗？"**
→ §2.7 给出了 Pareto 剪枝机制。N-ary 的价值是"成本梯度够细"——即使有效 N=3，也比二元多出一个中间档。RQ4 的"N-ary 后端使用分布"直接验证。

**Q: "Jain's FI 高就一定好吗？"**
→ 三个指标联合报告：Jain's FI（后启动者是否被饿死）+ QWCR 方差（质量一致性）+ 整体 Pareto 前沿（绝对产出）。"均等地都做不好"在 Pareto 图上会立刻露出来。

---

## 12. Future Work：从 Single-Tenant 到 Multi-Tenant 的 Agent Resource Allocation

为帮助不熟悉 LLM systems 文献的读者理解 AgentOS 的演进规划，本节以 vLLM 作为参照点。

vLLM 是 UC Berkeley 于 2023 年发布的开源 LLM 推理引擎（SOSP 2023）。其第一篇论文处理的是 single-tenant 问题：给定一台 GPU 服务器收到多个独立推理请求，引擎应如何 batch 与调度以最大化吞吐？该工作假设硬件由单一运营方拥有，未对竞争用户之间的公平性做任何主张。后续工作——包括 Andes（OSDI 2024）、SGLang router 等——把这一基础扩展到 multi-tenant 设定：多个用户、团队或服务共享同一推理基础设施，系统在 fairness、priority、SLA 约束下做仲裁。

**这种"先优化单决策主体、再引入多决策主体仲裁"的两阶段演进，是 systems 社区的成熟研究路径**。第一阶段建立**核心机制**（在 vLLM 的例子中是 paged KV-cache 与 continuous batching）；第二阶段在 single-tenant 案例被充分理解之后，在该机制之上叠加**政策层**。

AgentOS 走同样的路径。本文（paper 1）处理 **single-budget-owner** 情形：一个实体持有固定的算力 / token 预算，在其上运行多个 agent workflow；本文的贡献是构建在该预算之上做跨 workflow 分配的 cost-model-agnostic scheduler。自然的续作是 **multi-tenant agent compute resource allocation**：多个团队、部门或外部客户各自持有独立预算、优先级与 SLA，共享同一个 agent 执行底层。这一设定引入新的问题——cross-tenant 隔离、异构 workload 混合下的 weighted fairness、budget-aware admission control——超出本文 scope，但都是本文框架的直接扩展。**重要的是，本文 scheduler 的 cost-model-agnostic 性质在 multi-tenant 扩展中得以保留**：租户可以使用不同的底层模型与成本结构，无需修改仲裁层。

我们因此把本文定位为：**不是企业规模 agent 资源管理的完整解决方案，而是开启这一研究方向的第一篇——multi-tenant agent OS 工作可以在其上构建的 single-tenant 基础**。

### 12.1 Future Work：AgentOS-native agent loop

本文把 AgentOS 放在现有 agent 框架与 LLM 后端之间：LangChain / SWE-agent / AutoGen 可以通过 proxy、callback/middleware 或 SDK 接入。另一个自然方向是提供 **AgentOS-native agent loop**：把 tool execution、observation、budget ledger、ModelSelector 和 scheduler 都做成一套统一执行循环。

这在工程上很有价值：开发者可以不再同时维护 LangChain agent loop、外部 LLM gateway、预算脚本和限流脚本，而是直接用 AgentOS 作为 agent runtime。但这不是 paper 1 的主贡献。本文的核心贡献是**有状态的 workflow-aware budget-quality optimization**；native loop 是把这套机制产品化、降低开发者接入成本的后续工程扩展。

---

## 附录 A：一个具体场景（workflow-aware vs per-call 路由的差异）

让 SWE-agent 重构代码（"把这个模块拆成三个文件"）。假设这次 workflow 实际走了 6 步：

| 步 | 任务 | task_type | $w_i$ | 备注 |
|----|------|-----------|------|------|
| 1 | 读代码 | retrieval | 1 | 便宜模型够用 |
| 2 | 制定方案 | reasoning | 3 | **关键**——错了拖累后面 4 步 |
| 3–5 | 生成文件 A/B/C | generation | 3 | 主产出 |
| 6 | 验证 import | transform | 1 | 便宜模型够用 |

**Per-call router 的做法**：每次调用独立看 prompt 选模型。它通常不知道这个 workflow 已经花了多少钱、后面还有多少预算、当前有多少并发 workflow 在抢 RPM，也不维护跨步骤的 budget ledger。

**AgentOS 的做法**：AgentOS 维护 workflow 预算状态，并从三类信号中获得 $w_i$：如果是自研平台，可显式传入；如果是 LangChain / SWE-agent / AutoGen，可通过 callback/tool event 获得 tool name 和 output；如果只是 proxy 接入，则从 LLM request 中的 ToolMessage / Observation 文本推断。ModelSelector 按 $w_i \cdot \Delta q_i / \Delta c_i$ 和 `budget_factor` 共同决定是否升档：测试失败诊断等高风险上下文优先保留好模型，目录浏览/search 等低风险上下文优先用便宜模型。从 5 个后端中选，不是二选一。

## 附录 B：budget_factor 不需要预测未来

`budget_factor` 的核心是闭环反馈（花快了收紧、花慢了放宽），不要求准确预测未来流量。它不是"预测明天会来多少请求"，而是在每个滚动窗口内根据真实状态更新升级门槛：

| 观测状态 | `budget_factor` 变化 | 效果 |
|----------|----------------------|------|
| 已花预算超过当前时间水位 | 上升 | 升级到贵模型更难 |
| 队列长度 / RPM 压力上升 | 上升 | 低重要性调用更多走便宜模型 |
| 预算使用低于水位且队列空 | 下降 | 高重要性调用更容易升档 |
| 某 workflow 卡死或循环 | 结合 ZombieDetector 截断 | 回收预算和并发槽 |

因此，真实场景里即使某天调用量突然升高，AgentOS 也不依赖提前知道 burst。它先通过 admission control 排队、WFQ 保证并发 workflow 不互相饿死，再通过 `budget_factor` 把低重要性请求降级。本文的 RQ5 用 200-workflow replay + 3x arrival burst 验证这一点：系统事先不知道 burst，只根据观测到的成本、队列和 RPM 压力做反馈。

## 附录 C：Pluggability 设计

### 接口定义

```python
class ModelSelectorPolicy(ABC):
    @abstractmethod
    def select(self, turn: TurnInfo, gov_state: GovernorState,
               backends: list[Backend]) -> Backend: ...

class TurnInfo:
    task_type: str
    w_i: float
    signal_source: Literal["explicit", "callback", "proxy", "budget_only"]
    context_len: int
    workflow_id: str
    step_index: int
    tool_name: str | None = None
    observation_type: str | None = None

class GovernorState:
    budget_remaining: float
    budget_factor: float
    rpm_remaining: int
    concurrency_remaining: int
```

### 本工作实现的 4 个 Policy

| Policy 类 | 核心逻辑 | 用途 |
|-----------|---------|------|
| `WorkflowAwareHeuristic` | $\text{score} = w_i \cdot \Delta q / \Delta c$，结合 `budget_factor` 配速 | **本文主贡献** |
| `PerCallGreedy` | 每次独立选 $\max(q/c)$，不看 $w_i$、不配速 | 对照组 B |
| `BudgetAwareUniform` | 有配速但 $w_i \equiv 1$ | 对照组 C |
| `CARROTStylePredictor` | per-call cost-quality predictor | Per-call baseline |

学习型 agentic routing policy 接入留作 future work——接口已就绪，需要额外训练资源。
