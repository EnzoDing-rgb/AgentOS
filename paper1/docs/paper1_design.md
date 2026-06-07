# BudgetFlow Design Notes

> 本文档是 `paper1_concept.md` 的配套整理稿。当前目标是：**保留已有有价值设计**，同时把实现优先级表达得更清楚。文档主线按 **Tier 1 -> Tier 2 -> LangChain / framework integration** 组织。
>
> 规则：除非设计之间明显矛盾，否则尽量保留原有内容；Tier 1 是当前主实现路径，Tier 2 与各类接入形态先作为保留设计，不提前过度展开。

---

## 0. 设计定位

BudgetFlow 回答的不是单次 LLM 请求 routing 问题，而是更上层的 workflow budgeting 问题：

> 在一个或多个完整 agent workflow 中，每个 workflow 包含多步 LLM 调用；这些 workflow 共享一个预算池和多条后端路径的 RPM / 并发配额。系统能否利用 workflow 状态，把预算花在更关键的步骤上，并在固定预算下提高最终成功率？

这里的关键词是 **workflow-aware**：

- 维护全局预算池和每个 workflow 的 ledger；
- 观察本 workflow 已花成本、预留成本、step index 和进展信号；
- 根据 `budget_pressure` 调整模型升级门槛；
- 关注后端级 RPM / concurrency 占用；
- 在可获得时使用当前调用的重要性 $w_i$，这个信号可以显式传入，也可以由 callback 或 proxy 从 observation 中推断。

对应的 **workflow-blind** router 主要看本次请求的局部信息：prompt 内容、token 长度、模型成本、延迟、用户 tier 等。它们可以是很好的 per-call router，但没有跨 step 的预算账本，也没有多 workflow 的资源调度状态。

---

## 1. 总体边界

### 1.1 目标用户

BudgetFlow 的目标用户是造 agent 的人和运营 agent 平台的团队，不是终端用户：

- agent 框架或 agent 产品构建者：SWE-agent、LangChain、AutoGen、Moatless、MetaGPT 等框架维护者，或自研 agent 的团队；
- 单团队 agent 平台运营方：一个团队持有单一预算池，对内或对外运行多并发 agent 请求；
- 研究者：把 BudgetFlow 当作 evaluation harness，跑 SWE-bench 这类基准的多策略对比。

### 1.2 Paper 1 的边界

Paper 1 只处理 **single-budget-owner + multi-workflow**：

- 一个研究者或团队持有固定预算；
- 多个 workflow 同时运行；
- 所有 workflow 共享后端 RPM 和并发槽；
- 目标是 fixed budget 下的最终 workflow 成功率，例如 SWE-bench Verified 的 `resolved`。

不在 paper 1 范围内：

- 多预算主体、多团队、多 SLA 的 quota 仲裁；
- 完整 Agent OS 或 LangChain-like agent framework；
- 没有可靠 evaluator 的非 coding 任务主实验；
- 交互式助手的 latency / SLA / throughput 目标。

### 1.3 基准备注

保留一个重要现状备注：该基准已于 2026 年 2 月被 OpenAI 正式宣布“退役”，原因是严重训练数据污染——所有前沿模型都能逐字复现部分任务补丁，仅凭 issue 描述就能以 76% 的准确率猜中需要修改的文件，导致测试结果参考价值下降。

这条备注先保留，作为 **benchmark validity caveat**，但不改变本文档当前的系统设计整理目的。

---

## 2. Tier 1：当前主实现路径

当前目录约定已经简化为 `paper1/{data,src,docs,misc}`，不再保留中间 `dev/` 层。本文后续如果提到代码或数据路径，默认分别指向 `paper1/src/` 与 `paper1/data/`。

Tier 1 的目标不是做成完整通用中间层，而是先用最小可验证系统回答：

> workflow-aware budgeting 在固定预算下，是否比 workflow-level routing 或 budget-only step routing 更有效。

Tier 1 的原则：

- 优先验证 runtime 机制本身；
- 优先保持因果清晰；
- 优先低成本实现；
- 不把框架集成当成主贡献。

### 2.1 Tier 1 系统位置

BudgetFlow 位于 agent 框架和 LLM 后端之间，只治理 LLM 调用，不接管 agent loop。

```text
Mini scaffold / SWE-agent-like loop
        |
        | LLM request + messages + tool observations
        v
BudgetFlow Runtime
        |
        | admit / queue / downgrade / switch backend / reject
        v
LLM backend pool
```

**Tier-1 minimal backend pool (two tiers).** A cheap paper prototype only needs a lower-cost tier and a stronger tier with known price/protocol metadata. The concrete providers live behind the model-tier catalog, so swapping Qwen/AICode007 for another OpenAI-compatible provider should be a tier-config change rather than a routing rewrite. That still exercises tier jumps, ledger settlement, and the same routing math as in `paper1_concept.md` §8.5 without a large N-ary pool.

Tier 1 当前最自然的上游不是 LangChain 本身，而是一个可控的 mini scaffold 或 SWE-agent-like loop。这样更容易控制：

- `stage` 从哪里来；
- `w_i` 是否显式；
- baseline 如何公平比较；
- runtime 收益是否来自 BudgetFlow 本身，而不是上层框架差异。

### 2.2 Tier 1 信号抽取层

Tier 1 先保留最小但干净的 turn-level 信息：

```python
class TurnInfo:
    stage: str
    w_i: float
    signal_source: Literal["explicit", "callback", "proxy", "budget_only"]
    context_len: int
    workflow_id: str
    step_index: int
    tool_name: str | None = None
    observation_type: str | None = None
```

三种接入形态最终都归一成这类信息，供 ModelSelector 和 Governor 使用。

Tier 1 推荐优先用 **explicit** 或至少可控的弱推断，不优先追求 proxy text parsing。

默认重要性表只提供冷启动先验：

| 当前 LLM 输入 | 判断 | 默认 $w_i$ |
|---|---|---|
| 目录 / 文件列表 | 低风险导航，通常可恢复 | 1.0 |
| 搜索结果 / 源码片段 | 需要理解代码，影响后续编辑 | 1.5-2.0 |
| 测试失败 / traceback | 直接影响 root cause 判断 | 3.0 |
| 测试通过 / 编辑完成 | 多用于验证和收尾 | 1.0-1.5 |

这些权重不是真实人类效用，只是预算分配信号。论文必须通过 held-out calibration 和消融验证：如果去掉 $w_i$、换成 random 表或 uniform 表后效果不下降，说明这个设计没有提供有效信息。

### 2.3 Tier 1 Runtime 机制

一次 LLM call 到来时，BudgetFlow 的逻辑可以整理为：

1. 从 request / callback / SDK 中得到 `TurnInfo`。
2. 查询 workflow ledger 和全局 governor state。
3. 对候选后端估计 `expected_cost` 和 `reserved_cost`。
4. 从便宜模型开始，逐 tier 判断是否升级：

$$
w_i \cdot
\frac{\Delta \widehat{\text{progress}}_i}
     {\Delta \widehat{\text{cost}}_i}
\ge \text{budget\_pressure}_t
$$

5. 检查目标后端的 RPM / concurrency 和全局预算是否允许。
6. 若允许，原子预留预算并 dispatch；若不允许，降级、换后端、排队或拒绝。
7. 调用结束后，用真实 token 结算 `actual_cost`，退回未使用的预留预算。

#### 2.3.1 `budget_pressure`

`budget_pressure` 是升级门槛，不需要预测未来。它只做闭环反馈：

| 观测状态 | 调整 | 效果 |
|---|---|---|
| 花钱速度快于任务进度 | 升高 | 更少升档 |
| 花钱速度慢于任务进度 | 降低 | 关键步骤更容易升档 |
| 后端 RPM / 并发槽紧张 | 升高或触发排队 | 降低低价值调用压力 |
| workflow 卡死或循环 | 触发取消和回收 | 释放预算和槽位 |

Tier 1 中它可以先来自保守默认值、小规模试跑或简单 heuristic；不要求一开始就有完整 calibration split。

#### 2.3.2 成本三分法

BudgetFlow 必须区分三个成本口径：

| 成本 | 时机 | 用途 |
|---|---|---|
| `expected_cost` | 调用前估计 | 路由排序，比较升档是否划算 |
| `reserved_cost` | 调用前预留 | hard budget 准入控制 |
| `actual_cost` | 调用后结算 | ledger、实验报告、约束检查 |

如果 `actual_cost < reserved_cost`，差额退回预算池。并发场景下，预留和退回必须是原子操作，避免多个 workflow 同时读到同一份剩余预算。

#### 2.3.3 Cost Model Agnostic

ModelSelector 只依赖后端之间的成本梯度，不关心成本单位来自哪里：

| 成本模型 | 成本如何换算 | 场景 |
|---|---|---|
| API 计价 | 模型 USD / token | OpenAI / Anthropic 等 API |
| 本地 GPU 摊销 | 折旧、电费、运维成本摊到 token | 自有 GPU 跑本地模型 |
| 混合 | 统一换算到每 token 成本 | API 模型 + 本地 Llama 等混合后端 |

本地 GPU 不是免费的，只是成本结构不同。Paper 1 可以用混合后端池说明这点，但不需要把成本会计写成主要贡献。

### 2.4 Tier 1 Multi-Workflow Governance

BudgetFlow 在多 workflow 并发下维护四类机制：

| 机制 | 作用 |
|---|---|
| Ledger | 记录每个 workflow 的预留成本、实际花费、状态和 step |
| Governor | 做全局预算原子预留、结算、后端限流 |
| ModelSelector | 根据 $w_i$、预计进展、额外成本和 `budget_pressure` 选模型 |
| Scheduler | 在后端 RPM / 并发槽约束下准入、排队、降级或换后端 |

典型失败模式：

| 失败模式 | 原因 | 后果 |
|---|---|---|
| RPM 雪崩 | 多个 agent 同时打满某后端配额 | 大量 429，关键步骤失败 |
| 预算失控 | 先跑的 workflow 把贵模型预算花光 | 后启动 workflow 被迫全程用弱模型 |
| 资源饥饿 | 快 workflow 长期占满并发槽 | 慢 workflow 或后启动 workflow 被饿死 |
| 僵尸占槽 | 卡死 workflow 不释放资源 | 健康 workflow 排队，完成率下降 |

#### 2.4.1 ZombieDetector

ZombieDetector 是资源保险丝，不是主要算法贡献。它只管理 BudgetFlow 登记过的 workflow / LLM call，不扫描或杀系统里的任意进程。

可审计规则包括：

- 单步超过 wall-clock timeout；
- 连续重复同一 tool/action 超过阈值；
- 长时间无新 token、无新 tool event、无 ledger 更新；
- 成本持续增加，但 step progress 长时间无改善。

触发后先向上层 agent 或 provider 发 cancel / interrupt，并记录 `zombie_cancelled` 事件；如果无法优雅停止，再回收 BudgetFlow 内部的 reserved budget 和 backend-specific concurrency slot。实验中可以报告开/关 ZombieDetector 时的 recovered budget、healthy workflow completion rate、queue latency 和误杀率。

### 2.5 Tier 1 质量和进展信号

Paper 1 不发明主观质量分。最终质量只看 SWE-bench Verified 官方 harness 的 `resolved`。

Step-level progress 只给 runtime 和 case study 使用，不进入主结果表：

| 信号 | 获取方式 | 用途 |
|---|---|---|
| 是否打开 gold patch 涉及文件 | 轨迹访问文件和 gold patch changed files 对齐 | localization / search |
| patch 是否能 apply | 沙箱 dry-run 或 harness 记录 | repair / generation |
| 失败测试数是否减少 | 跑 `FAIL_TO_PASS` 子集或读取日志 | validation / debugging |
| 轨迹是否支持审计 | `.traj`、step cost、timestamp、model stats | 对齐行为、成本和结果 |

预计进展增益来自历史表：

$$
\widehat{\text{Progress}}[\text{stage}, \text{backend}]
= \text{mean step progress outcome}
$$

从 $a_k$ 升到 $a_{k+1}$ 的预计增益是：

$$
\Delta \widehat{\text{progress}}^{(k)}
= \widehat{\text{Progress}}[\text{stage}, a_{k+1}]
- \widehat{\text{Progress}}[\text{stage}, a_k]
$$

Tier 1 当前可以先使用 `zero-calibration` 或保守默认表；但这套进展信号定义本身仍应保留，因为它决定了后续 Tier 2 如何自然扩展。

### 2.6 Tier 1 实验整理

#### 2.6.1 主 Baselines

| 系统 | 说明 | 回答的问题 |
|---|---|---|
| Workflow-Level Router | workflow 开始时选一次模型或 routing profile | 只在任务开始做模型选择是否足够 |
| Budget-Only Step Router | 每步决策，但只看预算水位和成本 | 收益是否只来自预算配速 |
| BudgetFlow Full | 每步决策 + $w_i$ + progress prior + ledger/governor/scheduler | workflow-aware step budgeting 是否更好 |

#### 2.6.2 关键消融

Tier 1 最应优先保留：

- **No importance**：去掉 $w_i$，验证 step importance 是否有用。
- **Uniform / random progress table**：验证预计进展表是否比无信息表更好。
- **Zero-calibration**：不用校准数据，只用保守默认表，区分收益来自预算治理还是 progress prior。
- **ZombieDetector off**：验证 zombie recovery 对资源利用率和完成率的影响。
- **Concurrency scale**：比较 `J = 1 / 10 / 50 / 100` 时的预算 violation、429 rate、queue latency 和 resolved rate。

`signal source degradation` 在 Tier 1 不是必须主线，但因其对后续 integration story 有价值，先不删除，放到 Tier 2 保留。

#### 2.6.3 主指标

| 指标 | 含义 |
|---|---|
| Resolved rate @ fixed budget | 同样预算下解决多少 SWE-bench 任务 |
| Cost per resolved | 每解决一个任务花多少钱 |
| Budget violation rate | 是否超出 hard budget |
| 429 rate | 是否打爆 provider RPM |
| p50 / p99 queue latency | 调度排队延迟 |
| Recovered budget | 从 zombie workflow 退回的预算 |
| Healthy workflow completion rate | 健康 workflow 是否被资源饥饿拖垮 |

---

## 3. Tier 2：保留设计与后续扩展

Tier 2 暂不提前展开实现细节，但原有有价值设计都保留在这里，作为自然延伸，而不是现在删除。

### 3.1 Tier 2 核心方向

Tier 2 主要做三件事：

1. 从保守默认表走向 calibration / replay-driven progress table；
2. 从 Tier-1 最小后端池走向更完整 backend pool；
3. 从最小验证走向 paper-grade 主结果和系统性 ablation。

### 3.2 信号强度退化实验

下面这组设计对论文完整性仍有价值，先保留：

- **Signal source degradation**：比较 explicit、callback、proxy、budget-only 四种信号强度。
- 比较 L4 explicit、L2 callback、L1 proxy、L0 budget-only 的收益差异。
- 回答“workflow-aware signal 需要多强才值得做”这一问题。

### 3.3 历史表与 calibration

历史表可以来自：

- held-out calibration split；
- 公开运行记录；
- 在线滑动更新。

主实验要避免用 evaluation split 调参。

Tier 2 中，以下方向保留：

- 从 public `.traj` 回放中估计 `Progress[stage, tier]`；
- 用 Localization / Repair / Validation 三阶段组织 progress table；
- 从 gold patch changed files、patch apply success、test delta 等信号中构造更稳健 progress proxy；
- 比较 calibrated table、uniform table、random table、zero-calibration table。

### 3.4 更完整后端池

BoPO 风格工作多是 cheap / expensive 二元；BudgetFlow 设计允许 N-ary backend pool，逐 tier 升级。Tier 2 可以重新启用这个差异点：

- 3-5 个 tier；
- 更复杂成本梯度；
- 更完整 provider / local hybrid pool；
- 更明显的 `switch backend` 行为。

### 3.5 Related Work 定位

#### 3.5.1 Per-Query Routing

RouteLLM、CARROT、OmniRouter、LiteLLM auto-router 等主要优化 per-call 或 task-level 模型选择。BudgetFlow 不试图证明这些 router 不好，而是把问题上移：在多步 agent workflow 中，只看孤立请求是否足够？

#### 3.5.2 BoPO / Agentic Routing

BoPO 和本文共享背景：长程 agent workflow 受预算约束，不应每步都默认最强模型。差异在于：

| 维度 | BoPO | BudgetFlow |
|---|---|---|
| 方法 | 学一个 implicit routing policy | 暴露可审计 runtime decision rule |
| 训练 | BoSFT / BoPO 强化学习 | training-free，依赖显式规则和 calibration |
| 后端 | 多为 cheap / expensive 二元 | N-ary backend pool，逐 tier 升级 |
| 系统范围 | 单 task / episode routing | ledger、reservation、governor、scheduler、zombie recovery |

BoPO-style learned selector 可以作为 BudgetFlow 的 `ModelSelector` 插件，但不能替代 BudgetFlow 的预算账本和多 workflow 资源治理。

#### 3.5.3 Agent Runtime / Resource Governance

AgentRM、AgentCgroup、AIOS 等工作关注 agent 系统的资源管理、隔离或稳定性。BudgetFlow 的范围更窄：只治理 LLM 调用预算，但把质量目标、预算账本和后端配额放进同一个可实验 runtime。

### 3.6 Future Work 归档

#### 3.6.1 Multi-Tenant Resource Allocation

Paper 1 是 single-budget-owner 设定。后续可以研究多个团队、部门或外部客户共享同一 agent 执行底座时的 quota、priority、SLA 和 isolation。这个问题需要政策层，不应混进 paper 1 的主贡献。

#### 3.6.2 BudgetFlow-Native Agent Loop

当前设计把 BudgetFlow 放在现有 agent 框架和 LLM 后端之间。后续可以提供 native agent loop，把 tool execution、observation、ledger、ModelSelector 和 scheduler 做成统一 runtime，降低工程接入成本。

#### 3.6.3 Non-Coding Workflows

客服、RAG、科学推理等任务可以复用 ledger、reservation 和 scheduler，但需要新的 progress source。可能来源包括 domain verifier、learned evaluator、规则 + 模型混合 evaluator 或人类质检。关键是这些信号也必须 held-out 验证。

#### 3.6.4 Interactive / SLA Workloads

Paper 1 的主设定是批量评估 workload，不优化用户等待时间。交互式助手需要加入 deadline、SLA tier、latency、throughput 等指标，可以作为后续 workload extension。

---

## 4. LangChain / framework integration（放底部保留）

这一节不是 Tier 1 当前主实现路径，但原有设计有价值，先完整保留并重排。

先给结论：**LangChain 接入是有价值的工程化方向，但不是 Tier 1 必须前提，也不是 Paper 1 核心 claim 的必要组成。** 因此它放在文档底部，作为接入全景，而不抢占主实现主线。

### 4.1 总体接入形态

BudgetFlow 位于 agent 框架和 LLM 后端之间，只治理 LLM 调用，不接管 agent loop。

```text
LangChain / SWE-agent / AutoGen / 自研 agent loop
        |
        | LLM request + messages + tool observations
        v
BudgetFlow Runtime
        |
        | admit / queue / downgrade / switch backend / reject
        v
LLM backend pool
```

### 4.2 Proxy Mode

开发者把 OpenAI-compatible client 的 `base_url` 指向 BudgetFlow proxy：

```yaml
model:
  name: gpt-5
  api_base: "http://localhost:8080/v1"
```

上层 agent loop 不变。BudgetFlow 能看到最终发给 LLM 的 `messages`，包括 prompt、history、ToolMessage、ReAct 风格的 `Observation: ...` 等。它从这些文本或结构化 tool message 中推断当前 step 类型和重要性。

Proxy mode 的优点是低接入成本；缺点是信号比较噪声，尤其当工具输出只是普通文本时，需要规则或小模型判断 observation 类型。

这条路径的价值：

- 说明 BudgetFlow 可以低侵入部署；
- 对 framework-agnostic story 有帮助；
- 未来做 sidecar / gateway 时自然可用。

这条路径在 Tier 1 不优先做主实现，原因不是它没价值，而是它会把精力拉向 text parsing，而不是 runtime 核心机制。

### 4.3 Callback / Adapter Mode

对 LangChain、SWE-agent、AutoGen 这类框架写 callback 或 middleware，把工具事件结构化暴露给 BudgetFlow：

```python
class BudgetFlowLangChainMiddleware(AgentMiddleware):
    def wrap_tool_call(self, request, handler):
        result = handler(request)
        budgetflow.observe_tool(
            workflow_id=runtime.run_id,
            tool_name=request.tool_call["name"],
            tool_args=request.tool_call["args"],
            tool_output=result.content,
        )
        return result
```

这一层不改变 agent 决策逻辑，只把上层框架已经知道的 tool metadata 交给 BudgetFlow。它比 proxy 更准，但需要框架侧轻量集成。

对 LangChain 而言，这条路径的价值在于：

- 不必重新造完整 agent framework；
- 可以直接拿到更强结构化信号；
- 比 proxy 更适合做 signal-quality 对比实验；
- 未来如果需要展示“BudgetFlow 可嵌入现有生态”，这是最自然的工程路径。

但对 Paper 1 / Tier 1 而言，这条路径当前不是主线，因为：

- 论文核心贡献不依赖 LangChain 本身；
- 过早接入会引入框架生命周期、tool event 结构、middleware 兼容性等额外变量；
- 这些工程复杂度会削弱最小验证阶段的因果清晰度。

### 4.4 SDK Mode

自研 agent 平台可以显式告诉 BudgetFlow 当前 step 的类型和重要性：

```python
response = budgetflow.chat(
    messages=messages,
    stage="repair",
    w_i=3.0,
    workflow_id=run_id,
)
```

也可以只让 BudgetFlow 选模型，上层继续用自己的 LLM client 发请求：

```python
backend = budgetflow.select_model(
    stage="localization",
    w_i=3.0,
    workflow_id=run_id,
)
response = llm_client.chat(model=backend.name, messages=messages)
budgetflow.record_usage(workflow_id=run_id, backend=backend, response=response)
```

SDK mode 的信号最干净，但需要上层平台主动标注 `stage`（Localization / Repair / Validation，与 `paper1_concept.md` §1.5 对齐）和 $w_i$。

这也是当前 Tier 1 最合适的主路径，因为：

- 信号最可控；
- 最容易做 clean ablation；
- 最不容易把系统收益和框架噪声混在一起；
- 最接近“先验证 runtime rule 本身”的目标。

### 4.5 当前文档状态

当前文档把接入形态放在最底，不代表它们不重要，而是表示实现优先级：

1. **Tier 1 先走最小可验证主路径**；
2. **Tier 2 再扩到 richer signal / richer backend / richer calibration**；
3. **LangChain / framework adapter 保留为外部适配与工程化扩展。**

后续如果继续展开，优先补：

- `GovernorState`、`WorkflowLedger`、`Backend` 的接口；
- scheduler 伪代码；
- calibration pipeline；
- SWE-bench harness 集成；
- ablation table 模板和预期图表；
- LangChain callback interface 的最小契约。
