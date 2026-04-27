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
| 预算失控 | 没有配速——先跑的 10 个 agent 把贵模型预算花光 | 后 40 个 agent 全程只能用 mini，resolved rate 和 cost per resolved 变差 |
| 资源饥饿 | 跑得快的 agent 吃光并发槽和 RPM 配额 | 跑得慢或后启动的 agent 被系统性饿死 |
| 僵尸占槽 | 卡死的 agent 占着并发槽不释放 | 健康 agent 排队等位，整体吞吐下降 |

**上 AgentOS 后四条机制如何协同？**

| AgentOS 机制 | 在本场景中做什么 |
|-------------|----------------|
| **Governor** | 顶住 400 RPM 峰值——admission control 排队而非雪崩，预算硬封顶保证 \$50 不超支 |
| **ModelSelector** | 基于 `budget_factor` 和显式/推断 $w_i$ 决定是否升档：测试失败诊断等高风险上下文倾向好模型，目录浏览/search 等低风险上下文倾向便宜模型；从 5 个后端的成本梯度中选最佳档位 |
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
| 质量代理 $q_i$ | 第 $i$ 步产生的可验证进展，不等于"真实主观质量" | SWE-bench 测试、gold patch 解析、agent trajectory |
| 权重 $w_i$ | 这一步对最终成功的大致重要性 | 显式声明、callback 事件、或 observation 类型推断，并用消融验证 |

所以本文不声称知道"绝对真实质量"。本文只做一件更可验证的事：用公开 benchmark 能复现的代理信号指导预算分配，然后看最终 workflow 结果是否更好。

---

## 2. 形式化：预算约束下的代理效用分配

### 2.1 单 workflow 场景

一个 workflow 有 $N$ 个 turn（每个 turn 是一次 LLM 调用）。每个 turn $i$ 选一个后端 $a_i \in \mathcal{A}$（后端池，如上表 5 个选项）：

$$
\max_{a_1,\dots,a_N}\ \sum_{i=1}^{N} w_i\,q_i(a_i)\quad \text{s.t.}\quad \sum_{i=1}^{N} c_i(a_i)\le B
$$

各符号含义：
- $q_i(a_i) \in [0,1]$：turn $i$ 的可验证质量代理。它来自 SWE-bench 相关的确定性信号，例如是否定位到 gold patch 文件、patch 是否能 apply、`FAIL_TO_PASS` 是否通过、`PASS_TO_PASS` 是否保持通过。它不是作者主观打分，细节见 §3。
- $c_i(a_i)$：turn $i$ 的成本。API 模型用真实输入/输出 token 数乘以公开价格；本地模型用 GPU 小时成本、吞吐和本次 token 数摊销。所有成本写入 ledger，评估时用实际值。
- $w_i$：任务价值权重。它表示"同样的质量进展发生在这一步是否更关键"。权重可由显式声明、callback/tool event 或 Observation 推断获得，并通过消融验证，而不是直接当作论文结论。
- $B$：总预算硬约束
- $\mathcal{A}$：可用后端集合（N-ary，不限于二元）

这个目标函数是运行时的内部分配规则，不是论文最终自评指标。论文最终仍看 workflow 级指标：SWE-bench Verified resolve rate、cost per resolved instance 和成本-成功率 Pareto 前沿。

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
| `budget_uniform` | 有预算配速，但 $w_i \equiv 1$ | 只控预算、不区分步骤价值够不够 |
| **AgentOS** | 预算配速 + $w_i$ + 边际性价比 | 本文方法是否改善最终 benchmark outcome |

这四组足够回答核心问题。N-ary 后端、proxy/callback 信号强弱可以作为补充敏感性分析，不需要把主实验拆得过碎。

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
| $\Delta q_i^{(k)}$ | 从 tier $k$ 升到 tier $k+1$ 预计多获得多少可验证进展 | 基于历史 benchmark/trajectory 统计，按 task_type × 后端对分组，可用 EWMA 更新 |
| $\Delta c_i^{(k)}$ | 升一档要多花多少钱 | 决策前用 token 估计，评估时用 ledger 中的真实 token 成本 |
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

**Observation-based importance 的原则**：AgentOS 不预测 agent 下一步会做什么，而是看当前 LLM 输入里已经出现了什么信息。信息越接近最终修复决策，权重越高；信息越像导航和检索，权重越低。

| 当前 LLM 输入包含什么 | AgentOS 的判断 | 默认 $w_i$ |
|---------------------|---------------|------------|
| 目录 / 文件列表 | 低风险导航，通常可恢复 | 1.0 |
| 搜索结果 / 源码片段 | 需要理解代码，可能影响后续编辑 | 1.5–2.0 |
| 测试失败 / traceback | 直接影响 root cause 判断和修复方向 | 3.0 |
| 测试通过 / 编辑完成 | 多用于验证和收尾 | 1.0–1.5 |

**怎么知道上层用了哪个 tool？** Proxy mode 只能看到"最终喂给 LLM 的内容"：如果标准 tool message 带 `name` / `tool_call_id`，就结构化解析；如果只是 `Observation: ...` 文本，就用规则或小模型分类 observation 类型。Callback mode 则直接接入上层框架事件：LangChain 的 `wrap_tool_call` 可读到 `request.tool_call["name"]`，SWE-agent hook 可读到 action / step，AutoGen 的 `FunctionExecutionResult` 带有 tool name。本文把这层称为**信号抽取层**，其输出统一变成 `TurnInfo(task_type, w_i, workflow_id, step_index, ...)` 供 ModelSelector 使用。

§3.4 的消融只保留少量关键对照：去掉 $w_i$、随机化 $w_i$、使用粗粒度 task_type 权重、使用完整 AgentOS。这样能直接回答"权重信号是否真的有用"，不把实验拆成难以解释的九组。

### 2.7 N-ary 后端的现实性检查

**代价 1：先验矩阵规模从 $O(T)$ 涨到 $O(T \times N)$**。应对：静态先验表 + EWMA 在线更新 + 冷启动回退。

**代价 2：部分后端可能被 Pareto 支配**。应对：启动期 Pareto 剪枝——按 task_type 分组，剔除被严格支配的后端。预计有效 N 在 3–5 之间。**N-ary 的价值不是"5 个后端全被用上"，而是"成本梯度够细"**——即使有效 N=3，也比二元多出一个中间档。

**代价 3：更大的后端集合会扩大搜索空间**。应对：本文默认使用启发式边际收益排序，而不是训练一个覆盖全部 action space 的策略；action 数从 2 扩展到 N 时，学习型策略通常需要更多样本。

---

## 3. 质量怎么衡量？

**核心原则**：不自己发明主观评分。本文把质量分成两层：

1. **最终质量**：一个 SWE-bench Verified 任务最后有没有 resolved。这是主指标。
2. **步骤质量代理**：每一步是否产生了可验证进展。它只用于运行时分配预算和事后审计，不作为论文最终胜利标准。

### 3.1 最终质量：看 SWE-bench Verified 是否 resolved

SWE-bench 的任务来自真实 GitHub issue。系统要生成 patch，评估 harness 会把 patch 放回原仓库跑测试。对本文来说，最重要的不是"模型回答看起来好不好"，而是：

- patch 是否存在并能 apply；
- `FAIL_TO_PASS` 测试是否从失败变为通过；
- `PASS_TO_PASS` 测试是否继续通过；
- 最终状态是否为 `resolved`。

这套评估是确定性的、可复现的，也已经被软件工程和 LLM agent 社区广泛使用。因此本文的主结果报告 workflow 级指标：同样预算下 resolved rate 是否更高，resolved 一个任务平均花费是否更低，成本-成功率 Pareto 前沿是否更好。

### 3.2 步骤质量代理：从公开 artifact 提取，不主观打分

AgentOS 需要在任务还没结束时做预算决策，所以它不能等最终测试结果出来才决定前面该不该花钱。它需要 step-level proxy。本文使用的 proxy 都来自已有 artifact：

| 代理信号 | 怎么得到 | 用在什么步骤 |
|----------|----------|--------------|
| 定位是否命中 | 从 gold patch 的 unified diff 解析被修改文件，计算 Acc@k / MRR | search / localization |
| patch 是否可用 | harness 记录 patch 是否存在、是否 successfully applied | repair / generation |
| 测试是否改善 | `FAIL_TO_PASS`、`PASS_TO_PASS` 和 timeout/error 日志 | validation / debugging |
| 轨迹是否支持审计 | SWE-agent `.traj` 的 thought/action/observation/state；mini-SWE-agent 的 per-step cost、timestamp、model_stats | 对齐每一步的行为、成本和结果 |

这里的拆分不是本文自创。Agentless 已把 SWE-bench 任务拆成 localization、repair、patch validation；SweRank 也用 gold patch 派生的标签在 SWE-bench-Lite 上做 file/module/function 粒度的 localization 评估。本文沿用这条评估习惯，而不是另造一套"看起来质量更高"的标准。

### 3.3 成本：评估时用真实 ledger，不用估计值冒充结果

成本比质量更容易客观化，但也要写清楚。每次 LLM 调用都会记录输入 token、输出 token、模型名和时间戳：

$$
c_i = \text{input\_tokens}_i \cdot p_{\text{in}} + \text{output\_tokens}_i \cdot p_{\text{out}}
$$

如果后端是本地模型，则先把 GPU 小时成本折算成每 token 成本，再乘以本次 token 数。决策时可以用预估 token 数做选择；实验报告必须用 ledger 里的实际 token 和实际价格重算成本。这样 `cost per resolved instance` 和 Pareto 图不会依赖作者拍脑袋。

### 3.4 权重和 proxy 怎么证明有用？

消融实验的作用不是发明质量标准，而是验证这些公开确定性 proxy 用来分配预算时是否有用。本文只保留四组关键对照：

| 设置 | 含义 | 回答什么 |
|------|------|----------|
| `budget_uniform` | 有预算配速，但 $w_i=1$ | 只控预算是否已经足够 |
| `random_weight` | 随机打乱或随机生成 $w_i$ | 任意权重是否也能带来收益 |
| `task_type_weight` | 只用粗粒度任务类型权重 | 简单可部署信号是否有效 |
| **AgentOS-full** | 使用 proxy/callback 提取的 $w_i$ + budget_factor | 完整设计是否带来最好 cost-success tradeoff |

如果 AgentOS-full 在固定预算下取得更高 resolved rate、更低 cost per resolved instance，且优于 `budget_uniform` 和 `random_weight`，就说明质量代理和权重信号对预算分配有实际价值。本文不需要声称它们等于真实人类效用。

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

指标分两类。第一类是论文主指标，用来判断系统是否真的更好；第二类是诊断指标，用来解释为什么更好或哪里失败。

| 指标 | 类型 | 含义 |
|------|------|------|
| **Resolved rate @ fixed budget** | 主指标 | 同样预算下，SWE-bench Verified 解决了多少任务 |
| **Cost per resolved instance** | 主指标 | 平均解决一个任务花多少钱 |
| **Cost-success Pareto frontier** | 主指标 | 不同预算下，成功率和成本的整体权衡 |
| **Budget violation rate** | 约束指标 | 是否守住 hard budget |
| **Step proxy breakdown** | 诊断指标 | localization、patch apply、F2P/P2P 等中间信号如何变化 |

`sum_i w_i q_i` 不作为主指标。它只帮助解释 ModelSelector 为什么把钱分给某一步。多 workflow 场景下再补充报告 Jain's Fairness Index 和队列延迟，用来说明后启动 workflow 有没有被饿死。

---

## 7. 三条 RQ

| RQ | 问题 | 核心指标 |
|----|------|----------|
| **RQ1** | AgentOS 能否在 hard budget 和 RPM/concurrency 限制下稳定运行？ | budget violation rate、429 rate、queue latency |
| **RQ2** | 使用 $w_i$ 和 step proxy 做预算分配，是否比可比 baseline 有更好的 cost-success tradeoff？ | resolved rate、cost per resolved、Pareto frontier |
| **RQ3** | 当 $w_i$ 或 proxy 变粗、变噪、部分缺失时，系统是否平滑退化？ | resolved rate 下降幅度、与 `budget_uniform` 的差距 |

**主实验设计**：

| 维度 | 设定 |
|------|------|
| **Workload** | SWE-bench Verified 子集，使用 SWE-agent / mini-SWE-agent 轨迹和真实 LLM 调用 |
| **总预算** | \$50 |
| **后端池** | GPT-5 Thinking / Instant / mini / Claude Sonnet / 本地 Llama-3-70B-Int4（N=5） |
| **RPM 限额** | 500 RPM |

| 对照组 | 策略 |
|--------|------|
| `per_request_greedy` | 每步独立选模型，不看 workflow 预算状态 |
| `budget_uniform` | 有预算配速，但 $w_i=1$ |
| `task_type_weight` | 只用 planning/debugging/validation 等粗粒度权重 |
| **AgentOS-full** | 使用 proxy/callback 提取的 $w_i$、step proxy 和 budget_factor |

突发流量作为 RQ1/RQ3 的压力测试：中途注入更高到达率，系统事先不知道 burst 到来。报告预算是否超支、排队延迟是否可控、低价值调用是否自动降级。

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
| **$w_i$** | 当前调用的任务价值权重；它是预算分配信号，需要通过消融验证有效性 |
| **$q_i$** | Step-level 质量代理；来自 SWE-bench artifact、测试结果和 agent trajectory，不是主观评分 |
| **$c_i$** | 当前调用的真实成本；API 用 token 账单，本地模型用 GPU 成本摊销 |

其他系统组件可以按一句话理解：Governor 守住预算和限流，ModelSelector 选择模型，ZombieDetector 截断无效调用，cost-success Pareto 图展示不同预算下的 resolved rate。

---

## 10. 投稿建议

**首选路线：软件工程（ICSE / FSE / TSE / TOSEM，CCF-A）**

SE 社区缺"面向 LLM Agent 的成本治理基础设施"，对"系统工具 + 扎实实验"接受度高。

**硬件支持**：单卡 A800-SXM4-80GB 可支持 Llama-3-70B-Int4 本地推理 + GPT-5 / Claude API 调用，足以在 SE benchmark 上做真实 LLM 实验。本地+云端混合后端正好体现 N-ary + cost-model-agnostic 优势。

---

## 11. 审稿人常见质疑

**Q: 成本是不是你自己估的？**
→ 不是。API 后端用真实 input/output token 数乘以公开价格；本地后端用 GPU 小时成本和吞吐摊销到 token。决策时可以估计成本，但实验报告用 ledger 里的实际 token、模型名、时间戳和价格表重算。

**Q: 你的 quality 是不是自说自话？**
→ 最终质量不用作者打分，而是 SWE-bench Verified 的 resolved outcome。Step-level $q_i$ 只是预算分配代理，来自 gold patch localization、patch apply、`FAIL_TO_PASS`、`PASS_TO_PASS`、timeout/error 和 SWE-agent trajectory。这些信号可复现，也和 Agentless、SweRank 的拆分方式一致。

**Q: $w_i$ 是不是拍脑袋？**
→ $w_i$ 是运行时的价值先验，不是最终结论。本文用 `budget_uniform`、`random_weight`、`task_type_weight` 和 AgentOS-full 做消融。如果完整权重信号不能带来更好的 resolved rate 或 cost per resolved，就说明设计无效。

**Q: 你只是预算控制做得好。**
→ 用 `budget_uniform` 单独隔离预算控制效果。若 AgentOS-full 进一步优于 `budget_uniform`，提升才归因于步骤价值信号和质量代理；否则只能说预算控制有效，不能夸大 $w_i$ 的贡献。

**Q: "现有 per-call auto-router 已经解决了这个问题。"**
→ 它们是 workflow-blind 的：看不到 workflow 的步骤价值结构、全局预算状态、多 workflow 竞争。AgentOS 解决的是不同层次的问题（详见 §0）。

**Q: "和学习型 agentic router 比呢？"**
→ 学习型 router 可以作为 AgentOS 的 ModelSelector 插件。本文主贡献不是训练最强 router，而是把预算、成本、质量代理、权重和 ledger 放进同一个可审计 workflow runtime，并用公开 benchmark outcome 评估。

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

因此，真实场景里即使某天调用量突然升高，AgentOS 也不依赖提前知道 burst。它先通过 admission control 排队、WFQ 保证并发 workflow 不互相饿死，再通过 `budget_factor` 把低重要性请求降级。压力测试会注入突发到达率，验证系统在不知道 burst 的情况下是否仍能控制预算、队列和 RPM 压力。

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
