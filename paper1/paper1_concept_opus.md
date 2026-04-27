# AgentOS: A Workflow-Aware, Training-Free Runtime for Budget-Constrained Quality Optimization in Multi-Agent LLM Systems

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

本文的研究问题是：**当优化单位从"一次 LLM 请求"变成"一个完整 agent workflow"，并且多个 workflow 共享同一个预算、RPM 和并发上限时，显式维护 workflow 状态是否会改变固定预算下的最终成功率？** 如果答案是肯定的，再进一步问：这个收益来自预算配速、步骤重要性、进展先验，还是多 workflow 调度？把 agent workflow 的 LLM 花费变成一个可审计、可消融、可复现实验的问题。

### 真正的 gap：现有 auto-router 都是 workflow-blind 的

- **workflow-aware**：路由决策会使用 workflow 级状态，例如：这个 workflow 还剩多少预算、当前花钱速度是否合理、同一时间有多少 workflow 在共享并发/RPM 资源，以及当前 LLM 调用的决策上下文是否关键（$w_i$，可显式传入，也可由工具输出/observation 推断）。**不需要提前知道 workflow 总共有多少步**——`budget_pressure` 是闭环反馈，$w_i$ 是每次调用时从可用信号获得。
- **workflow-blind**：路由决策主要依赖本次调用的局部信息（prompt/token/延迟），不维护 workflow 预算状态，也不接收或推断跨步骤的重要性信号，因此无法做跨步骤预算配速或跨 workflow 调度。

| Per-call router 通常看得到 | AgentOS 额外维护 / 获取的 workflow 级信号 |
|-----------|----------------------------------|
| 当前这次 prompt 的内容、长度、复杂度 | 本 workflow 的预算上限、已花成本、剩余预算 |
| 模型成本与能力差异 | `budget_pressure`：当前预算有多紧，升级门槛有多高 |
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
       | ModelSelector: budget_pressure + importance |
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
| 预算失控 | 没有配速——先跑的 10 个 agent 把贵模型预算花光 | 后 40 个 agent 全程只能用 mini，resolved rate 变差 |
| 资源饥饿 | 跑得快的 agent 吃光并发槽和 RPM 配额 | 跑得慢或后启动的 agent 被系统性饿死 |
| 僵尸占槽 | 卡死的 agent 占着并发槽不释放 | 健康 agent 排队等位，整体吞吐下降 |

**上 AgentOS 后四条机制如何协同？**

| AgentOS 机制 | 在本场景中做什么 |
|-------------|----------------|
| **Governor** | 顶住 400 RPM 峰值——admission control 排队而非雪崩；每次调用先做 `reserved_cost` 原子预留，保证 \$50 hard budget 不超支 |
| **ModelSelector** | 基于 `budget_pressure`、预计进展增益和显式/推断 $w_i$ 决定是否升档：测试失败诊断等高风险上下文倾向好模型，目录浏览/search 等低风险上下文倾向便宜模型；从 5 个后端的成本梯度中选最佳档位 |
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
| 1 | 研究 benchmark 评估 | 研究者本人 | 一道 SWE-bench 题目 | **是**（§7 主实验） |
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

成本在系统里分成三类，避免把"决策前估计"和"实验后结算"混在一起：`expected_cost` 用于路由排序，`reserved_cost` 用于 hard-budget 准入，`actual_cost` 用于账本结算和论文评估。具体机制见 §3.4。

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

## 1. 核心洞察：LLM 调用不只分"成败"，还分"值不值得花这笔钱"

一个 coding agent 跑 SWE-bench 任务时，不是只调用一次模型。它会先读 issue、找文件、看代码、写 patch、跑测试、再根据测试结果修补。每一步都要花 token，也都可能影响最后 patch 能不能通过测试。

因此本文关心的问题不是"这一次请求用哪个模型最强"，而是：

> **固定预算下，哪些步骤值得多花钱，哪些步骤应该省下来？**

这里有三个量要先讲清楚：

| 量 | 本文含义 | 可信来源 |
|----|----------|----------|
| 成本 $c_i$ | 第 $i$ 次 LLM 调用真实花了多少钱 | API token 账单，或本地 GPU 摊销后的 token 成本 |
| 步骤进展 $q_i$ | 第 $i$ 步产生的可验证进展，不等于"真实主观质量" | SWE-bench 测试、gold patch 解析、agent 运行记录 |
| 权重 $w_i$ | 这一步对最终成功的大致重要性 | 显式声明、callback 事件、或 observation 类型推断，并用消融验证 |

所以本文不声称知道"绝对真实质量"。本文只做一件更可验证的事：用公开 benchmark 能复现的步骤进展信号指导预算分配，然后看最终 workflow 结果是否更好。

---

## 2. 形式化：预算约束下的步骤进展分配

### 2.1 单 workflow 场景

一个 workflow 有 $N$ 个 turn（每个 turn 是一次 LLM 调用）。每个 turn $i$ 选一个后端 $a_i \in \mathcal{A}$（后端池，如上表 5 个选项）：

$$
\max_{a_1,\dots,a_N}\ \sum_{i=1}^{N} w_i\,q_i(a_i)\quad \text{s.t.}\quad \sum_{i=1}^{N} c_i(a_i)\le B
$$

各符号含义：
- $q_i(a_i) \in [0,1]$：turn $i$ 的可验证步骤进展。它来自 SWE-bench 相关的确定性信号，例如是否定位到 gold patch 文件、patch 是否能 apply、`FAIL_TO_PASS` 是否通过、`PASS_TO_PASS` 是否保持通过。它不是作者主观打分，细节见 §3。
- $c_i(a_i)$：turn $i$ 的成本。决策时使用 `expected_cost`，预算准入使用 `reserved_cost`，评估时使用 ledger 中的 `actual_cost`。API 模型按 token 价格计算；本地模型按 GPU 成本摊销，细节见 §3.4。
- $w_i$：任务价值权重。它表示"同样的质量进展发生在这一步是否更关键"。权重可由显式声明、callback/tool event 或 Observation 推断获得，并通过消融验证，而不是直接当作论文结论。
- $B$：总预算硬约束
- $\mathcal{A}$：可用后端集合（N-ary，不限于二元）

这个目标函数是运行时的内部分配规则，不是论文最终自评指标。论文最终仍看 workflow 级指标：SWE-bench Verified resolved rate，以及在不同预算约束下的 resolved-rate-vs-budget 曲线。

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

| 对照组 | 策略 | 回答什么 |
|--------|------|----------|
| `always_expensive` | 每步都用最贵模型，直到预算耗尽 | 只追求单步强模型是否会浪费预算 |
| `per_request_greedy` | 每步独立选当下看起来性价比最高的模型 | 不看 workflow 状态会不会短视 |
| `omnirouter_or_carrot` | 使用已有 per-call router，只对单次请求做选择 | 强 per-call baseline 是否已经足够 |
| `litellm_auto_router` | 使用工程上常见的自动路由策略 | 商业/开源网关式 auto-router 是否已经覆盖本文收益 |
| `budget_uniform` | 有预算配速，但 $w_i \equiv 1$ | 只控预算、不区分步骤价值够不够 |
| `bopo_selector` | 将 BoPO / learned agentic router 接成 `ModelSelector` | 学习型 routing policy 能否替代本文默认启发式 |
| **AgentOS** | 预算配速 + $w_i$ + 预计进展增益 | 本文方法是否改善最终 benchmark outcome |

主线对照不需要无限扩张，但必须包含一个强 per-call baseline 和一个学习型 agentic baseline。否则审稿人会合理地质疑：本文只是赢了弱 baseline。本文的判断标准也不是"启发式一定打败 RL"，而是看 **workflow-aware runtime state** 是否带来额外收益：同一个 AgentOS Governor / Ledger / Scheduler 下，默认启发式、BoPO、CARROT/OmniRouter 风格 selector 都可以作为 `ModelSelector` 插件被公平比较。

### 2.4 决策直觉：预算有限时，先买单位成本进展最大的升级

AgentOS 的运行时问题可以先用一个简单例子理解：你有固定预算，面前有很多"模型升级机会"。每个升级机会都要多花一笔钱，也可能多带来一点步骤进展。预算有限时，合理做法不是"最重要的步骤直接用最贵模型"，而是逐个问：

> 这次升级每多花 1 美元，预计能多买到多少对最终解决问题有用的进展？

这个思想不是本文自创。经典的 fractional knapsack 问题（Dantzig 1957）就是在容量有限时按 `value / weight` 排序，先装"单位重量价值最高"的物品。本文把同一个思想搬到 agent workflow：`expected_progress_gain / extra_cost` 就是一次模型升级的"单位成本进展"。

因为不同步骤的重要性不同，AgentOS 再把这一步的进展乘上 $w_i$。同样的定位命中，如果发生在 root-cause debugging 步，通常比发生在随手浏览目录步更值钱。最后还要和当前预算状态比较：预算紧时，升级门槛高；预算松时，升级门槛低。本文把这个门槛叫 `budget_pressure`，避免使用需要优化背景知识的术语。

### 2.5 运行时决策公式：步骤重要性 × 预计进展增益 ÷ 多花成本

将后端池 $\mathcal{A}$ 中的 $N$ 个后端按成本升序排列：$a_1 \prec a_2 \prec \dots \prec a_N$。AgentOS 不一次性决定"这步用最贵还是最便宜"，而是从最便宜的 $a_1$ 开始，逐档判断"再升一档值不值"。

对 turn $i$，从 tier $k$ 升到 tier $k+1$ 的两个核心量是：

$$
\Delta \widehat{\text{progress}}_i^{(k)}
= \widehat{\text{Progress}}[\text{task\_type}_i, a_{k+1}]
- \widehat{\text{Progress}}[\text{task\_type}_i, a_k]
$$

$$
\Delta \widehat{\text{cost}}_i^{(k)}
= \widehat{\text{cost}}_i(a_{k+1}) - \widehat{\text{cost}}_i(a_k)
$$

人话版决策规则：

```text
如果：步骤重要性 × 预计进展增益 ÷ 多花成本 >= 当前预算门槛
那么：从当前模型升到下一档模型
否则：停在当前模型
```

数学写法：

$$
\text{升级条件：} \quad
w_i \cdot
\frac{\Delta \widehat{\text{progress}}_i^{(k)}}
     {\Delta \widehat{\text{cost}}_i^{(k)}}
\ge \text{budget\_pressure}_t
$$

选中的后端是满足上式的**最高 tier**。若所有 tier 都不值得升级（`budget_pressure` 高 = 预算紧），则留在 $a_1$（最便宜）。选出候选后端后，还必须经过 Governor 的 `reserved_cost` 检查；如果剩余预算无法覆盖最坏情况下的本次调用成本，就继续降级、降低输出上限、排队或拒绝。换句话说，ModelSelector 负责"值不值"，Governor 负责"能不能安全发起调用"。

| 量 | 人话含义 | 怎么得到 |
|------|------|-------|
| $w_i$ | 这一步有多关键 | 显式传入、callback 结构化推断，或从 ToolMessage / Observation 推断（见 §2.6） |
| $\Delta \widehat{\text{progress}}_i^{(k)}$ | 升一档预计多带来多少步骤进展 | 从历史 SWE-bench 运行记录、校准集和在线 EWMA 得到（见 §3.3） |
| $\Delta \widehat{\text{cost}}_i^{(k)}$ | 升一档预计多花多少钱 | 排序用 `expected_cost` 差值；预算安全用 `reserved_cost` 检查；评估用 `actual_cost` |
| `budget_pressure` | 当前预算有多紧，升级门槛有多高 | 闭环反馈在线更新：花快了升高，花慢了降低 |

**数字例子**：当前是测试失败后的 debugging step。历史运行记录显示，在 debugging step 上，Sonnet 比 mini 更容易让后续修复进入正确方向，预计进展增益是 0.12；Thinking 比 Sonnet 还会再多 0.05。当前预算门槛是 4。

| 升级 | 步骤重要性 $w_i$ | 预计进展增益 | 多花成本 | 分数 | 决策 |
|------|------------------|--------------|----------|------|------|
| mini → Sonnet | 3 | 0.12 | \$0.04 | $3 \times 0.12 / 0.04 = 9.0$ | $9.0 \ge 4$，升级 |
| Sonnet → Thinking | 3 | 0.05 | \$0.20 | $3 \times 0.05 / 0.20 = 0.75$ | $0.75 < 4$，不升级 |

结果：这一步用 Sonnet，不用 Thinking。若同样的预计进展增益发生在"列目录"这类低重要性步骤，$w_i=1$，mini → Sonnet 的分数变成 $1 \times 0.12 / 0.04 = 3$，低于预算门槛 4，就不会升级。

这个公式里的具体数值会有不确定性，这是所有运行时路由都无法避免的：调用前没人知道真实结果。但公式形式不是随机的。它来自两个标准思想：

- **单位成本价值**：Dantzig 1957 的 fractional knapsack 按 `value / weight` 选择物品。这里的 `预计进展增益 / 多花成本` 就是一次模型升级的单位成本价值。
- **预算约束下的门槛比较**：在带预算约束的优化问题里，合理策略会把资源投向"单位成本收益高于当前预算门槛"的选择。本文的 `budget_pressure` 就是这个门槛的工程实现：预算越紧，门槛越高；预算越松，门槛越低。

因此，本文不要求 `expected_progress_gain` 完美预测未来，只要求它比随机表和全等表更有信息量。这个点由 §3.5 的消融实验检验。

### 2.6 $w_i$ 如何获得？

$w_i$ 不是必须由 agent 框架手写声明。AgentOS 支持从强到弱的 5 个信号来源；信号越强，ModelSelector 越接近 oracle；信号越弱，则更多依赖 `budget_pressure` 做预算配速。

| 档位 | 接入方式 | $w_i$ 来源 | 典型场景 |
|------|----------|-----------|----------|
| **L4 显式数值** | SDK / 自研平台 | `agentos.chat(..., w_i=3.0)` | 平台自己知道某一步是关键 planning / validation |
| **L3 显式类型** | SDK / 自研平台 | `task_type` 查表 | `planning→3, generation→2, validation/retrieval→1` |
| **L2 Callback 推断** | framework adapter | tool event + observation metadata | LangChain middleware、SWE-agent hook、AutoGen tool event |
| **L1 Proxy 推断** | HTTP sidecar | LLM request 中的 ToolMessage / Observation 文本 | 只改 `base_url`，零改 agent loop |
| **L0 Budget-only** | 无可用信号 | $w_i \equiv 1$，仍使用 `budget_pressure` | 退化到预算感知 baseline |

**Observation-based importance 的原则**：AgentOS 不预测 agent 下一步会做什么，而是看当前 LLM 输入里已经出现了什么信息。信息越接近最终修复决策，权重越高；信息越像导航和检索，权重越低。

| 当前 LLM 输入包含什么 | AgentOS 的判断 | 默认 $w_i$ |
|---------------------|---------------|------------|
| 目录 / 文件列表 | 低风险导航，通常可恢复 | 1.0 |
| 搜索结果 / 源码片段 | 需要理解代码，可能影响后续编辑 | 1.5–2.0 |
| 测试失败 / traceback | 直接影响 root cause 判断和修复方向 | 3.0 |
| 测试通过 / 编辑完成 | 多用于验证和收尾 | 1.0–1.5 |

这些默认值不是论文要证明的"最优常数"。它们只是一个保守的顺序先验：traceback 通常比目录列表更接近最终修复决策，所以权重更高。真正需要证明的是三件事：

1. 用 held-out calibration split 校准这些权重后，是否能在另一个不参与校准的 split 上提升 fixed-budget resolved rate；
2. 把权重范围从 `1-3` 改成 `1-2` 或 `1-4` 时，系统是否平滑退化，而不是靠某个神秘常数取胜；
3. 当推断信号变弱（L4 显式 → L2 callback → L1 proxy → L0 budget-only）时，收益下降多少。

换句话说，$w_i$ 是运行时分配预算的粗粒度信号，不是作者声称掌握了真实人类效用。默认表只负责冷启动；论文结论必须来自 held-out 和 cross-dataset 消融。

**怎么知道上层用了哪个 tool？** Proxy mode 只能看到"最终喂给 LLM 的内容"：如果标准 tool message 带 `name` / `tool_call_id`，就结构化解析；如果只是 `Observation: ...` 文本，就用规则或小模型分类 observation 类型。Callback mode 则直接接入上层框架事件：LangChain 的 `wrap_tool_call` 可读到 `request.tool_call["name"]`，SWE-agent hook 可读到 action / step，AutoGen 的 `FunctionExecutionResult` 带有 tool name。本文把这层称为**信号抽取层**，其输出统一变成 `TurnInfo(task_type, w_i, workflow_id, step_index, ...)` 供 ModelSelector 使用。

§3.5 的消融分成三层：先验证 $w_i$ 是否真的有用，再验证预计进展增益表是否优于随机表和全等表，最后看这些信号跨数据集会退化多少。这样能直接回答"步骤重要性"、"历史进展预测"和"是否循环调参"三个问题。

### 2.7 N-ary 后端的现实性检查

**代价 1：先验矩阵规模从 $O(T)$ 涨到 $O(T \times N)$**。应对：静态先验表 + EWMA 在线更新 + 冷启动回退。

**代价 2：部分后端可能被 Pareto 支配**。应对：启动期 Pareto 剪枝——按 task_type 分组，剔除被严格支配的后端。预计有效 N 在 3–5 之间。**N-ary 的价值不是"5 个后端全被用上"，而是"成本梯度够细"**——即使有效 N=3，也比二元多出一个中间档。

**代价 3：更大的后端集合会扩大搜索空间**。应对：本文默认使用启发式边际收益排序，而不是训练一个覆盖全部 action space 的策略；action 数从 2 扩展到 N 时，学习型策略通常需要更多样本。

---

## 3. 质量怎么衡量？

**核心原则**：不自己发明主观评分。本文把质量分成两层：

1. **最终质量**：一个 SWE-bench Verified 任务最后有没有 resolved。这是主指标。
2. **步骤进展结果**：每一步是否产生了可机器检查的进展。它用于构建运行时的预计进展增益表，也用于事后解释系统为什么把预算分给某些步骤；不作为论文最终胜利标准。

### 3.1 最终质量：看 SWE-bench Verified 是否 resolved

SWE-bench 的任务来自真实 GitHub issue。系统要生成 patch，评估 harness 会把 patch 放回原仓库跑测试。对本文来说，最重要的不是"模型回答看起来好不好"，而是：

- patch 是否存在并能 apply；
- `FAIL_TO_PASS` 测试是否从失败变为通过；
- `PASS_TO_PASS` 测试是否继续通过；
- 最终状态是否为 `resolved`。

这套评估是确定性的、可复现的，也已经被软件工程和 LLM agent 社区广泛使用。因此本文的主结果报告 workflow 级指标：同样预算下 resolved rate 是否更高，以及不同预算约束下 resolved rate 如何变化。

### 3.2 步骤进展结果：从公开运行记录和测试结果提取，不主观打分

AgentOS 需要在任务还没结束时做预算决策，所以它不能等最终测试结果出来才决定前面该不该花钱。本文把每一步的可机器检查进展称为 **step progress outcome**。它不是"level quality"，也不是人类主观打分，而是从 SWE-bench 和 agent 运行记录里抽出来的 0/1 或排序信号。

| 步骤进展结果 | 怎么得到 | 用在什么步骤 |
|----------|----------|--------------|
| 定位是否命中 | 从 gold patch 的 unified diff 解析被修改文件，计算 Acc@k / MRR | search / localization |
| patch 是否可用 | harness 记录 patch 是否存在、是否 successfully applied | repair / generation |
| 测试是否改善 | `FAIL_TO_PASS`、`PASS_TO_PASS` 和 timeout/error 日志 | validation / debugging |
| 轨迹是否支持审计 | SWE-agent `.traj` 的 thought/action/observation/state；mini-SWE-agent 的 per-step cost、timestamp、model_stats | 对齐每一步的行为、成本和结果 |

这里的拆分不是本文自创。Agentless 已把 SWE-bench 任务拆成 localization、repair、patch validation；SweRank 也用 gold patch 派生的标签在 SWE-bench-Lite 上做 file/module/function 粒度的 localization 评估。本文沿用这条评估习惯，而不是另造一套"看起来质量更高"的标准。

### 3.3 预计进展增益：运行时用历史表预测，不偷看未来结果

关键点是：AgentOS 在第 2 步、第 3 步做路由时，不知道这个 issue 最后能不能 resolved。因此运行时不能使用真实的质量增量，只能使用**预计进展增益**：

> 过去在同类步骤里，从模型 A 升到模型 B，平均多带来了多少可机器检查的步骤进展？

这张历史表可以从三类来源得到。

**第一，held-out calibration split。** 从 SWE-bench Lite 或 SWE-bench Verified 中抽一小部分任务作为校准集，不参与主实验。对每个 `task_type × backend` 组合，跑同一个 agent loop，记录步骤进展结果，得到：

$$
\widehat{\text{Progress}}[\text{task\_type}, \text{backend}]
= \text{mean step progress outcome}
$$

于是从 $a_k$ 升到 $a_{k+1}$ 的预计进展增益就是：

$$
\Delta \widehat{\text{progress}}^{(k)}
= \widehat{\text{Progress}}[\text{task\_type}, a_{k+1}]
- \widehat{\text{Progress}}[\text{task\_type}, a_k]
$$

这和 RouteLLM / CARROT 这类 router 先用校准集估计模型能力差异的思路一致，只是本文估计的是 agent workflow 中不同步骤的进展差异。为避免循环论证，校准集和主测试集必须分开：例如用 SWE-bench Lite 校准，在 SWE-bench Verified 或 RepoBench 上测试；或者在 Verified 内部使用严格 disjoint split。论文需要报告从 calibration domain 到 held-out domain 的退化幅度，而不是只报告同分布最佳结果。

**第二，公开运行记录。** SWE-bench 生态里已经有大量不同模型、不同 agent scaffold 的运行记录。只要记录里包含 agent 做了什么、看到了什么、最后 patch 是否 apply、测试是否通过，就能回放出步骤进展结果。这样可以在自己大规模实验前，先得到一张保守的初始表：例如过去在 debugging 步，Sonnet 比 mini 更常把后续修复带到可通过 `FAIL_TO_PASS` 的方向。

**第三，在线 EWMA 更新。** 系统每跑完一个 step，就把真实观察到的步骤进展更新回历史表：

$$
\widehat{\text{Progress}} \leftarrow
(1-\alpha)\widehat{\text{Progress}} + \alpha \cdot \text{observed\_progress}
$$

这和成本估计完全对称：调用前只能估计输出 token，调用后用真实 token 更新均值；质量进展也是调用前只能估计，调用后用真实步骤进展更新均值。

**冷启动。** 如果某个 `task_type × backend` 组合从未见过，就用一张保守默认表：贵模型的预计进展不低于便宜模型，但差距很小。这样系统不会因为没数据就疯狂升档。主实验通过消融证明这张表是否真的有用：如果 calibrated 表不能优于 random 表和 uniform 表，说明这个设计失败；如果能优于它们，说明历史步骤进展确实提供了可用的事前信号。

还需要一个 **zero-calibration** 设置：完全不用校准数据，只用保守默认表（例如贵模型只比便宜模型高 10% 的弱先验）。如果 zero-calibration 已经接近 calibrated 结果，说明收益主要来自 workflow-aware 预算配速；如果 calibrated 明显更好，则说明步骤进展表提供了额外信息。两种结果都可以解释，但必须分清楚收益来源。

### 3.4 成本：路由用估计，预算安全用预留，评估用真实账单

成本比质量更容易客观化，但要分清楚三个时刻。

**第一，决策前的 `expected_cost`。** AgentOS 选模型时还没有发起 LLM call，因此不知道真实输出 token 数。它能准确知道输入 token，因为 prompt / messages 已经组好；输出 token 只能估计，例如按 `task_type × model` 的历史均值、rolling average 或 EWMA。这个估计只用于路由排序，例如比较"升一档模型预期多花多少钱"：

$$
\text{expected\_cost}_i(a)
= \text{input\_tokens}_i \cdot p_{\text{in}}(a)
+ \widehat{\text{output\_tokens}}_i(a) \cdot p_{\text{out}}(a)
$$

真实使用量可以反过来更新这些均值，让估计更准。但这只是提高预算利用率，不是 hard budget 的安全来源。

**第二，调用前的 `reserved_cost`。** 如果论文声称 hard budget，就不能靠平均输出长度保证不超支。AgentOS 必须在发起调用前预留本次调用的可控上界：

$$
\text{reserved\_cost}_i(a)
= \text{input\_tokens}_i \cdot p_{\text{in}}(a)
+ \text{max\_output\_tokens}_i \cdot p_{\text{out}}(a)
$$

这里的 `max_output_tokens` 必须是 provider-enforced 的输出上限，或者本地推理服务强制执行的生成上限。若剩余预算无法覆盖 `reserved_cost`，系统不能直接发起这次调用，只能降级模型、降低 `max_output_tokens`、排队，或拒绝本次 workflow。这样 hard budget 不是靠预测，而是靠准入控制。

**第三，调用后的 `actual_cost`。** 调用结束后，provider 或本地 serving 日志会返回真实 input/output token 数。实验评估和账本结算只使用真实成本：

$$
\text{actual\_cost}_i(a)
= \text{actual\_input\_tokens}_i \cdot p_{\text{in}}(a)
+ \text{actual\_output\_tokens}_i \cdot p_{\text{out}}(a)
$$

如果 `actual_cost < reserved_cost`，差额退回预算池。并发场景下，reservation 必须是原子操作：dispatch 前从 `available_budget` 扣到 `reserved_budget`，调用结束后再从 `reserved_budget` 结算到 `spent_budget`，并退回未使用部分。这样 50 个 workflow 同时启动时，也不会因为同时读取同一个剩余预算而超支。

因此本文的成本口径是：`expected_cost` 用于排序，`reserved_cost` 用于预算安全，`actual_cost` 用于 accounting 和约束检查。论文的质量主指标不使用作者估计的成本，而是在固定预算和不同预算约束下报告 resolved rate。

### 3.5 步骤重要性和预计进展增益怎么证明有用？

消融实验的作用不是发明质量标准，而是验证这些可复现的步骤进展信号用来分配预算时是否有用。这里要特别避免一个循环论证：不能在 SWE-bench 上调出 `$w_i$` 和 progress table，再只在同一批 SWE-bench 任务上证明它有效。因此本文把验证拆成三层。

**第一层：步骤重要性 $w_i$ 是否有用？**

| 设置 | 含义 | 回答什么 |
|------|------|----------|
| `budget_uniform` | 有预算配速，但 $w_i=1$ | 只控预算是否已经足够 |
| `random_weight` | 随机打乱或随机生成 $w_i$ | 任意权重是否也能带来收益 |
| `task_type_weight` | 只用粗粒度任务类型权重 | 简单可部署信号是否有效 |
| `learned_weight` | 用 calibration split 拟合 task_type / observation 权重 | 手工先验是否接近数据估计 |
| **AgentOS-full** | 使用 callback / request 内容提取的 $w_i$ + `budget_pressure` | 完整步骤重要性信号是否最好 |

同时做 sensitivity：把默认权重范围从 `1-3` 改成 `1-2`、`1-4`，看 resolved rate 是否大幅波动。如果只有某组手写数字有效，说明方法不稳；如果变化很小，说明 `$w_i$` 只是粗粒度排序信号。

**第二层：预计进展增益表是否有用？**

| 设置 | 含义 | 回答什么 |
|------|------|----------|
| `uniform_progress_gain` | 所有模型升级的预计进展相同 | 只靠预算门槛是否已经够 |
| `random_progress_gain` | 随机打乱历史表 | 任意历史表是否也能赢 |
| `zero_calibration` | 只用保守默认表，不看校准数据 | 冷启动时是否仍有价值 |
| `calibrated_progress_gain` | 使用校准集、公开运行记录和 EWMA | 本文的事前预测是否有效 |
| `oracle_progress_gain` | 用事后结果构造上界，只作分析 | 离理想上界还有多远 |

**第三层：跨数据集是否退化？**

最小设置是：在 SWE-bench Lite 上校准 `$w_i$` 和 progress table，在 SWE-bench Verified 上测试；如果资源允许，再用 RepoBench 或另一个 coding-agent benchmark 做外部验证。论文要报告 cross-domain drop，而不是回避它。若跨域下降很大，结论就收窄到"可观察 step-progress 的 SWE-bench-style coding workflow"；若下降可控，才说明这套信号有更强泛化性。

如果 AgentOS-full 在固定预算下取得更高 resolved rate，且 `calibrated_progress_gain` 优于 `uniform_progress_gain` 和 `random_progress_gain`，就说明步骤重要性和预计进展增益对预算分配有实际价值。本文不需要声称它们等于真实人类效用，只需要证明它们是比随机或全等策略更好的运行时信号。

---

## 4. 系统架构：policy-agnostic 的 workflow-aware runtime

> "policy-agnostic" 是指系统基础设施（预算管控、限流、僵尸检测等）**不绑定任何特定的路由策略**。你可以换掉"怎么选模型"的部分，其他所有机制照常运行。

```
Agent Workflow（N 个 LLM 调用步骤）× J 个并发 workflow
        │
        ▼
═══════════════════ AgentOS ═══════════════════
│ 【约束层】Governor                           │  ← policy-agnostic
│   预算预留/结算 + API RPM 限流 + 并发准入     │
│                                              │
│ 【优化层】ModelSelector（可插拔）             │  ← 唯一 routing policy
│   本文默认：预计进展增益 + budget_pressure    │
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

这里要说清楚一个容易被误解的点：AgentOS 没有声称重新发明 token bucket、reservation、WFQ、watchdog 或 EWMA。这些都是成熟机制。本文的新问题在于把它们放到 **agent workflow 的 LLM 预算治理** 这个单位上，并用同一套 ledger 追踪"每一步为什么花这笔钱、是否守住预算、是否改善最终 resolved outcome"。因此实验的关键不是证明 WFQ 本身新，而是证明 workflow-level state 加进来以后，per-call router 的 fixed-budget Pareto frontier 是否被改变。

### 4.1 ModelSelector 可插拔接口

```python
class ModelSelectorPolicy(ABC):
    @abstractmethod
    def select(self, turn: TurnInfo, gov_state: GovernorState,
               backends: list[Backend]) -> Backend: ...
```

本工作实现了 4 个 policy：`WorkflowAwareHeuristic`（默认 reference policy）、`PerCallGreedy`（对照组 B）、`BudgetAwareUniform`（对照组 C）、`CARROTStylePredictor`（per-call baseline）。如果能获得 BoPO 或类似 learned agentic router 的训练策略，它也作为 `ModelSelectorPolicy` 接入同一套 Governor / Ledger，而不是在另一套系统里单独比较。

### 4.2 ZombieDetector 的边界

ZombieDetector 不是本文的主要算法贡献，作用更像 agent runtime 的保险丝：当一个 workflow 明显卡住时，释放并发槽和预留预算，避免拖累其他健康 workflow。它只管理 AgentOS 启动或登记过的 workflow / LLM call，不扫描或杀掉系统里的任意进程。

本文采用可审计的规则组合，而不是黑箱判断：

| 信号 | 僵尸风险 |
|------|----------|
| 单步超过 wall-clock timeout | 可能卡在工具调用、测试或 provider stream |
| 连续重复同一 tool/action 超过阈值 | 可能陷入循环 |
| 长时间无新 token、无新 tool event、无 ledger 更新 | 可能已经失去进展 |
| 成本持续增加，但 step progress 长时间无改善 | 可能在无效消耗预算 |

触发后先向上层 agent 或 provider 发 cancel / interrupt；如果无法优雅停止，再回收 AgentOS 内部的 reserved budget 和 concurrency slot。实验里不把 ZombieDetector 写成质量提升的核心来源，只报告开/关它时的资源利用率、healthy workflow completion rate，以及误杀率或人工抽样审计结果。

---

## 5. Multi-Workflow 并发调度

一个 workflow = 一个任务从开始到结束的一串 LLM 调用步骤。multi-workflow = 同一时间有很多个 workflow 在跑，共享同一组资源。

### 5.1 为什么需要这一层

50 个 SWE-agent 同时跑时，系统处于 RPM 限额的 80% 水位。如果不做调度：先到先得导致后启动 agent 被饿死、前几个 agent 把贵模型预算花光、卡死 agent 占着并发槽不释放。

per-task 路由策略本身不处理这一层——要覆盖多 workflow 并发，需要把共享预算、队列和 RPM/concurrency 压力纳入 runtime 级状态。

### 5.2 调度算法：Weighted Fair Queuing

本文的多 workflow 调度有三个组件：

1. **每 workflow 独立 budget tracker**：每个 workflow 有自己的预算 $B_j$ 和 `budget_pressure_j`
2. **跨 workflow weighted fair queuing**：共享 RPM/并发槽按 workflow 优先级加权分配
3. **Admission control**：资源满载时排队——不需要预测到达分布

### 5.3 Workload 不确定性处理

**本系统不依赖 workload 预测，也不需要任何 ML 训练**：

| 不确定性 | 处理方式 |
|----------|---------|
| 并发 workflow 数量未知 | Admission control：满了就排队 |
| 每 turn 的 cost / step progress 未知 | cost 用 `expected_cost` 排序、`reserved_cost` 保预算、`actual_cost` 结算；step progress 用历史运行记录估计 |
| 新 task_type 的进展先验冷启动 | EWMA 在线更新 + 静态先验回退 |

---

## 6. 评估指标

指标分两类。第一类是论文主指标，用来判断系统是否真的更好；第二类是诊断指标，用来解释为什么更好或哪里失败。

| 指标 | 类型 | 含义 |
|------|------|------|
| **Resolved rate @ fixed budget** | 主指标 | 同样预算下，SWE-bench Verified 解决了多少任务 |
| **Resolved rate vs budget curve** | 主指标 | 在不同固定预算下，resolved rate 如何变化 |
| **Budget violation rate** | 约束指标 | 是否守住 hard budget |
| **Step progress breakdown** | 诊断指标 | localization、patch apply、F2P/P2P 等中间信号如何变化 |

`sum_i w_i q_i` 不作为主指标。它只帮助解释 ModelSelector 为什么把钱分给某一步。多 workflow 场景下再补充报告 Jain's Fairness Index 和队列延迟，用来说明后启动 workflow 有没有被饿死。

---

## 7. 四条 RQ

| RQ | 问题 | 核心指标 |
|----|------|----------|
| **RQ1** | AgentOS 能否在 hard budget 和 RPM/concurrency 限制下稳定运行？ | budget violation rate、429 rate、queue latency |
| **RQ2** | workflow-aware 决策是否比 workflow-blind per-call router 有更高 fixed-budget resolved rate？ | resolved rate、resolved-rate-vs-budget curve、cost per resolved |
| **RQ3** | 收益来自哪一层机制：预算配速、$w_i$、进展先验，还是调度？ | component ablation、step progress breakdown |
| **RQ4** | 当步骤重要性或预计进展增益变粗、变噪、跨数据集迁移时，系统是否平滑退化？ | cross-domain drop、与 `budget_uniform` / `random_weight` 的差距 |

**主实验设计**：

| 维度 | 设定 |
|------|------|
| **Workload** | SWE-bench Verified 子集，使用 SWE-agent / mini-SWE-agent 轨迹和真实 LLM 调用 |
| **Calibration** | SWE-bench Lite 或 Verified held-out split；不参与主测试 |
| **总预算** | \$50 |
| **后端池** | GPT-5 Thinking / Instant / mini / Claude Sonnet / 本地 Llama-3-70B-Int4（N=5） |
| **RPM 限额** | 500 RPM |

| 对照组 | 策略 |
|--------|------|
| `omnirouter_or_carrot` | 强 per-call router，不维护 workflow ledger |
| `litellm_auto_router` | 工程网关式 auto-router baseline |
| `per_request_greedy` | 每步独立选模型，不看 workflow 预算状态 |
| `budget_uniform` | 有预算配速，但 $w_i=1$ |
| `task_type_weight` | 只用 planning/debugging/validation 等粗粒度权重 |
| `bopo_selector` | 学习型 agentic router 作为 `ModelSelector` 插件 |
| **AgentOS-full** | 使用 callback / request 内容提取的 $w_i$、预计进展增益和 `budget_pressure` |

**机制归因实验**：

| 设置 | 加入的机制 | 回答什么 |
|------|------------|----------|
| `per_call_router_only` | 只做单次请求路由 | 没有 workflow 状态时的上限 |
| `+ hard_budget_reservation` | 增加预算预留和结算 | 只是守预算是否已经足够 |
| `+ budget_pressure` | 增加闭环配速 | 避免前期花光预算的收益有多大 |
| `+ w_i` | 增加步骤重要性 | 把钱留给关键步骤是否有用 |
| `+ progress_prior` | 增加预计进展增益表 | 历史步骤进展是否提供事前信号 |
| `+ WFQ` | 增加多 workflow 公平调度 | 并发下是否减少饥饿 |
| `+ ZombieDetector` | 增加卡死回收 | 是否提高资源利用率和健康任务完成率 |

这个表的目的不是证明每个组件都是新算法，而是回答一个更重要的问题：workflow-aware runtime 的收益到底来自哪里。如果某个组件贡献很小，正文就弱化它；如果完整组合明显优于单点 router，论文才能说 AgentOS 改变了固定预算下的 cost-quality frontier。

**跨数据集和稳健性实验**：

| 设置 | 目的 |
|------|------|
| Lite → Verified | 用 SWE-bench Lite 校准，在 SWE-bench Verified 测试 |
| Verified split → Verified held-out | 同 benchmark 内严格 disjoint 验证 |
| Verified/Lite → RepoBench（可选） | 看 coding workflow 之外的 repo reasoning 是否退化 |
| `zero_calibration` | 不用校准数据，只用保守默认表 |
| `1-2 / 1-3 / 1-4` weight ranges | 看 `$w_i$` 数值是否敏感 |
| L4/L2/L1/L0 signal sources | 看显式、callback、proxy、budget-only 的退化曲线 |

**多 workflow 压力测试**：

并发规模设为 `J=1/10/50/100`，调度策略比较 FIFO、shortest-job-first 和 WFQ。报告 Jain's Fairness Index、p50/p99 queue latency、429 rate、budget violation rate、平均完成时间和 fixed-budget resolved rate。突发流量实验在中途注入一批新 workflow，系统事先不知道 burst 到来；目标是观察预算、队列和 RPM 压力是否可控。

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
| **AgentRM** (2026) | 调度失败 + 上下文退化 | 侧重系统稳定性，不做预算约束下的质量优化 |
| **AgentCgroup** (2026) | OS 级资源隔离 | 不涉及 LLM 调用质量 |
| **AIOS** (2024) | 通用 Agent OS 架构 | 宽泛架构，无预算约束下的质量优化 |

### 8.3 Budget-Aware Agentic Routing / BoPO

Budget-Aware Agentic Routing via Boundary-Guided Training（BoPO）是最接近的 agentic routing 工作之一。它和本文共享同一个问题背景：agent workflow 是长程、路径依赖、受预算约束的，不能每一步都默认使用最强模型。

但两者的贡献点不同：

| 维度 | BoPO | 本文 AgentOS |
|------|------|--------------|
| 核心目标 | 学一个 cheap / expensive 二元 routing policy | 构建可审计的 workflow runtime，让每次模型升级都经过预算门槛决策 |
| 方法 | always-small / always-large 边界策略 + BoSFT + BoPO 强化学习 | 零训练：步骤重要性 × 预计进展增益 ÷ 多花成本，与预算门槛比较 |
| 质量信号 | sparse terminal reward 下学习隐式策略 | 从 SWE-bench 历史运行记录构建显式预计进展增益表，并在线更新 |
| 后端选择 | 通常二元 cheap / expensive | N-ary 后端池，逐 tier 决定升到哪一档 |
| 系统范围 | 单 task / episode 的 learned routing | workflow ledger、hard-budget reservation、RPM/concurrency governor、多 workflow 调度、僵尸检测 |

一句话：BoPO learns an implicit routing policy；AgentOS exposes an auditable runtime decision rule。BoPO 这类学习型 router 可以作为 AgentOS 的 `ModelSelector` 插件，但不能替代 AgentOS 的预算账本、并发治理和多 workflow 资源协调。

### 8.4 定位总结

| 研究类别 | 代表工作 | 本文差异 |
|----------|---------|---------|
| Per-query routing | RouteLLM, CARROT, OmniRouter | 本文是 workflow 级 |
| Agentic routing (RL) | BoPO, xRouter 等 | 本文零训练 + N-ary + 多 workflow runtime |
| OS 资源管理 | AgentRM, AgentCgroup, AIOS | 本文做预算约束下的质量优化 |
| **本文** | AgentOS | **workflow-aware, training-free, multi-workflow budget-constrained quality runtime** |

---

## 9. 关键概念速查

| 概念 | 一句话 |
|------|-------|
| **Turn** | 一次 LLM 调用——调度和计费的最小单位 |
| **Workflow** | 一个完整任务的 LLM 调用序列 |
| **$w_i$** | 当前调用的任务价值权重；它是预算分配信号，需要通过消融验证有效性 |
| **$q_i$** | Step-level 步骤进展；来自 SWE-bench 测试结果、gold patch 解析和 agent 运行记录，不是主观评分 |
| **$c_i$** | 当前调用的成本；排序看 `expected_cost`，预算安全看 `reserved_cost`，评估看 `actual_cost` |

其他系统组件可以按一句话理解：Governor 守住预算和限流，ModelSelector 选择模型，ZombieDetector 截断无效调用，resolved-rate-vs-budget 曲线展示不同预算约束下的 resolved rate。

---

## 10. 投稿建议

**首选路线：软件工程（ICSE / FSE / TSE / TOSEM，CCF-A）**

SE 社区缺"面向 LLM Agent 的成本治理基础设施"，对"系统工具 + 扎实实验"接受度高。

**硬件支持**：单卡 A800-SXM4-80GB 可支持 Llama-3-70B-Int4 本地推理 + GPT-5 / Claude API 调用，足以在 SE benchmark 上做真实 LLM 实验。本地+云端混合后端正好体现 N-ary + cost-model-agnostic 优势。

---

## 11. 审稿人常见质疑

**Q: 成本是不是你自己估的？**
→ 分三步。路由排序用 `expected_cost`，其中输入 token 可在调用前精确计数，输出 token 用历史均值或 EWMA 估计。hard budget 不靠这个估计，而靠 provider-enforced `max_output_tokens` 计算 `reserved_cost`，调用前原子预留预算。实验报告用 `actual_cost`：真实 input/output token 数乘以公开价格；本地后端用 GPU 小时成本和吞吐摊销到 token。

**Q: 你的 quality 是不是自说自话？**
→ 最终质量不用作者打分，而是 SWE-bench Verified 的 resolved outcome。Step-level $q_i$ 是可机器检查的步骤进展，来自 gold patch localization、patch apply、`FAIL_TO_PASS`、`PASS_TO_PASS`、timeout/error 和 SWE-agent 运行记录。这些信号可复现，也和 Agentless、SweRank 的拆分方式一致。

**Q: 你的公式是不是拍脑袋？**
→ 公式形式不是随机的。预算有限时，经典 fractional knapsack 会按 `value / weight` 优先选择单位成本价值高的物品（Dantzig 1957）。AgentOS 的 `预计进展增益 / 多花成本` 就是模型升级的单位成本进展；$w_i$ 把"这一步有多关键"乘进去；`budget_pressure` 是当前预算门槛，预算越紧门槛越高。具体数值估计一定有噪声，但本文用 calibration、在线更新和 `uniform/random/oracle` 消融证明它是否是有用信号，而不是假装能完美预知未来。

**Q: $w_i$ 是不是拍脑袋？**
→ 默认表不是最优常数，只是冷启动先验：traceback 通常比目录列表更接近修复决策，所以权重更高。真正的证据来自实验：用 held-out calibration split 学或校准 `$w_i$`，再在 disjoint SWE-bench Verified、RepoBench 或另一个 held-out split 上测试；同时报告 `w_i=1`、`random_weight`、`learned_weight` 和不同权重范围下的退化。如果只在同一批任务上调参和测试，这个设计就不成立。

**Q: 这会不会还是 SWE-bench 内循环论证？**
→ 所以实验必须区分 calibration 和 test。预计进展表和 `$w_i$` 可以在 SWE-bench Lite 或 Verified calibration split 上得到，但主结果要在不参与校准的 Verified split 上报告；可选再用 RepoBench 做 cross-domain 检查。论文不回避退化幅度：如果跨域下降明显，结论就限定在 SWE-bench-style coding workflow；如果下降可控，才说明信号有更强泛化性。

**Q: 你只是预算控制做得好。**
→ 用 `budget_uniform` 单独隔离预算控制效果。若 AgentOS-full 进一步优于 `budget_uniform`，提升才归因于步骤重要性和预计进展增益；否则只能说预算控制有效，不能夸大 $w_i$ 的贡献。

**Q: "现有 per-call auto-router 已经解决了这个问题。"**
→ 它们是 workflow-blind 的：看不到 workflow 的步骤价值结构、全局预算状态、多 workflow 竞争。AgentOS 解决的是不同层次的问题（详见 §0）。

**Q: "和学习型 agentic router 比呢？"**
→ 以 BoPO 为例，学习型 agentic router 训练一个 cheap / expensive 二元策略，解决 sparse terminal reward 下如何学会花预算的问题。AgentOS 的贡献不是训练最强 router，而是提供 training-free、N-ary、可审计的 workflow runtime：预算账本、`reserved_cost` 准入、RPM/concurrency 控制、多 workflow 调度和步骤级预算决策。学习型 router 可以作为 AgentOS 的 ModelSelector 插件。

**Q: 这些机制不都是旧的吗？WFQ、token bucket、reservation、watchdog、EWMA 都不是新东西。**
→ 是的，本文不把这些机制包装成新算法。AgentOS 的研究贡献在更高一层：把 agent workflow 作为预算治理单位，定义一套可插拔、可审计的 runtime contract，并用实验回答"workflow-level state 是否让固定预算下的 agent 成功率更高"。类比数据库和操作系统论文，很多系统贡献并不是发明锁、队列或缓存本身，而是在新的 workload 和约束下证明一套抽象改变了性能/可靠性边界。本文必须通过机制归因实验说明收益来自 workflow-aware state 与 selector/governor/scheduler 的耦合，而不是只列组件。

**Q: 你是不是应该同时覆盖客服、创意写作、长程科学推理？**
→ Paper 1 不做这个主张。本文选择 SWE-bench-style coding workflow，是因为它有可复现的最终指标和可机器检查的 step progress。没有明确 step progress 的任务需要 human feedback、rubric evaluator、conversation outcome 或 learned progress estimator；这些可以接入同一个 `ModelSelectorPolicy` / ledger contract，但属于后续工作。本文的结论边界是：有可观察中间进展信号、受预算和并发约束的 agent workflow。

---

## 12. Future Work：从 Single-Tenant 到 Multi-Tenant 的 Agent Resource Allocation

为帮助不熟悉 LLM systems 文献的读者理解 AgentOS 的演进规划，本节以 vLLM 作为参照点。

vLLM 是 UC Berkeley 于 2023 年发布的开源 LLM 推理引擎（SOSP 2023）。其第一篇论文处理的是 single-tenant 问题：给定一台 GPU 服务器收到多个独立推理请求，引擎应如何 batch 与调度以最大化吞吐？该工作假设硬件由单一运营方拥有，未对竞争用户之间的公平性做任何主张。后续工作——包括 Andes（OSDI 2024）、SGLang router 等——把这一基础扩展到 multi-tenant 设定：多个用户、团队或服务共享同一推理基础设施，系统在 fairness、priority、SLA 约束下做仲裁。

**这种"先优化单决策主体、再引入多决策主体仲裁"的两阶段演进，是 systems 社区的成熟研究路径**。第一阶段建立**核心机制**（在 vLLM 的例子中是 paged KV-cache 与 continuous batching）；第二阶段在 single-tenant 案例被充分理解之后，在该机制之上叠加**政策层**。

AgentOS 走同样的路径。本文（paper 1）处理 **single-budget-owner** 情形：一个实体持有固定的算力 / token 预算，在其上运行多个 agent workflow；本文的贡献是构建在该预算之上做跨 workflow 分配的 cost-model-agnostic scheduler。自然的续作是 **multi-tenant agent compute resource allocation**：多个团队、部门或外部客户各自持有独立预算、优先级与 SLA，共享同一个 agent 执行底层。这一设定引入新的问题——cross-tenant 隔离、异构 workload 混合下的 weighted fairness、budget-aware admission control——超出本文 scope，但都是本文框架的直接扩展。**重要的是，本文 scheduler 的 cost-model-agnostic 性质在 multi-tenant 扩展中得以保留**：租户可以使用不同的底层模型与成本结构，无需修改仲裁层。

我们因此把本文定位为：**不是企业规模 agent 资源管理的完整解决方案，而是开启这一研究方向的第一篇——multi-tenant agent OS 工作可以在其上构建的 single-tenant 基础**。

### 12.1 Future Work：AgentOS-native agent loop

本文把 AgentOS 放在现有 agent 框架与 LLM 后端之间：LangChain / SWE-agent / AutoGen 可以通过 proxy、callback/middleware 或 SDK 接入。另一个自然方向是提供 **AgentOS-native agent loop**：把 tool execution、observation、budget ledger、ModelSelector 和 scheduler 都做成一套统一执行循环。

这在工程上很有价值：开发者可以不再同时维护 LangChain agent loop、外部 LLM gateway、预算脚本和限流脚本，而是直接用 AgentOS 作为 agent runtime。但这不是 paper 1 的主贡献。本文的核心贡献是**有状态的 workflow-aware budget-constrained quality optimization**；native loop 是把这套机制产品化、降低开发者接入成本的后续工程扩展。

### 12.2 Future Work：没有确定性 step progress 的任务

SWE-bench 的好处是进展信号相对清楚：文件定位、patch apply、`FAIL_TO_PASS`、`PASS_TO_PASS` 都能机器检查。客服、创意写作、长程科学推理不是这样。它们可能没有 gold patch，也没有一组确定性测试告诉系统"这一步更接近成功了"。

这不是 AgentOS runtime 不能用于这些任务，而是 ModelSelector 需要换一个 progress source。例如客服可以用任务是否解决、是否升级人工、用户满意度或事后质检作为 outcome；RAG 可以用 citation correctness、answer faithfulness 或 retrieval hit rate；科学推理可以用 benchmark verifier、self-consistency 或专家评分。AgentOS 的 ledger、budget reservation、scheduler 仍然可用，但 `$q_i$` 和 `$w_i$` 的来源要由领域 evaluator 或学习型 selector 提供。

因此 paper 1 不声称一张 SWE-bench 校准表能泛化到所有 agent 任务。更合理的路线是：本文先在可复现的 coding workflow 上证明 workflow-aware budget governance 是否成立；后续工作研究不同任务域如何定义可靠的 progress signal。

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

**AgentOS 的做法**：AgentOS 维护 workflow 预算状态，并从三类信号中获得 $w_i$：如果是自研平台，可显式传入；如果是 LangChain / SWE-agent / AutoGen，可通过 callback/tool event 获得 tool name 和 output；如果只是 proxy 接入，则从 LLM request 中的 ToolMessage / Observation 文本推断。ModelSelector 按"步骤重要性 × 预计进展增益 ÷ 多花成本"和 `budget_pressure` 共同决定是否升档：测试失败诊断等高风险上下文优先保留好模型，目录浏览/search 等低风险上下文优先用便宜模型。从 5 个后端中选，不是二选一。

## 附录 B：budget_pressure 不需要预测未来

`budget_pressure` 的核心是闭环反馈（花快了收紧、花慢了放宽），不要求准确预测未来流量。它不是"预测明天会来多少请求"，而是在每个滚动窗口内根据真实状态更新升级门槛：

| 观测状态 | `budget_pressure` 变化 | 效果 |
|----------|----------------------|------|
| 已花预算超过当前时间水位 | 上升 | 升级到贵模型更难 |
| 队列长度 / RPM 压力上升 | 上升 | 低重要性调用更多走便宜模型 |
| 预算使用低于水位且队列空 | 下降 | 高重要性调用更容易升档 |
| 某 workflow 卡死或循环 | 结合 ZombieDetector 截断 | 回收预算和并发槽 |

因此，真实场景里即使某天调用量突然升高，AgentOS 也不依赖提前知道 burst。它先通过 admission control 排队、WFQ 保证并发 workflow 不互相饿死，再通过 `budget_pressure` 把低重要性请求降级。压力测试会注入突发到达率，验证系统在不知道 burst 的情况下是否仍能控制预算、队列和 RPM 压力。

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
    budget_pressure: float
    rpm_remaining: int
    concurrency_remaining: int
```

### 本工作实现的 4 个 Policy

| Policy 类 | 核心逻辑 | 用途 |
|-----------|---------|------|
| `WorkflowAwareHeuristic` | $\text{score} = w_i \cdot \Delta \widehat{\text{progress}} / \Delta \widehat{\text{cost}}$，结合 `budget_pressure` 配速 | 本文默认 reference policy |
| `PerCallGreedy` | 每次独立选 $\max(q/c)$，不看 $w_i$、不配速 | 对照组 B |
| `BudgetAwareUniform` | 有配速但 $w_i \equiv 1$ | 对照组 C |
| `CARROTStylePredictor` | per-call cost-quality predictor | Per-call baseline |

学习型 agentic routing policy（如 BoPO）也应作为同一接口下的 selector 插件来比较。这样实验回答的是"workflow-aware runtime state 是否有价值"，而不是把 heuristic 和 RL 放在两套不可比的系统里各跑各的。
