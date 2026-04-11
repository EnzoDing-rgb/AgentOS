# Scoped Recovery: Fault-Tolerant Execution for LLM Agent Workflows

## 核心 Insight

LLM agent 的执行失败有**作用域**。多数失败——工具报错、输出格式错误、参数幻觉——局限于单个步骤，不波及整个工作流。但现有框架把执行当作扁平序列：一步出错，要么盲目重试同一步，要么从头开始，白烧之前所有 token。我们引入**作用域恢复**：将工作流分层执行，每层定义错误边界；失败时在最小作用域内，用语义检查点恢复进度，用反射式修正（LLM 看到错误信息后调整策略）替代盲重试。

---

## 问题定位

LangChain / CrewAI / AutoGen 执行工具链时，遇到失败只有三条路：

**盲重试。** 用相同输入再跑一遍 step 5。如果失败原因是参数错误或工具本身不可用，重试必然再次失败。

**全量重启。** 从 step 1 开始重跑。Steps 1–4 的 token 全部浪费。一个 10 步任务在 step 8 失败，前 7 步的推理、工具调用、中间结果全部丢弃。

**人工介入。** 不 scale。

**token 浪费在预算治理下被放大。** 在 Paper 1 的 Resource Governor 管辖下，浪费的 token 就是浪费的预算。如果 10 个并发 agent 每个因全量重启浪费 50% 的 token，系统的有效吞吐直接减半——不是因为资源不够，而是因为恢复策略太蠢。

由此自然要问：能不能靠「把 context 撑满」解决问题？并不能。轨迹越长，关键信息越容易被埋在中段（lost-in-the-middle），网页/HTML、冗长日志等噪声也会稀释注意力；在按输入 token 计费的 API 上，把整条历史原样塞回模型往往**更贵**，也未必**更稳**。全量重启则逼模型在更长的历史中重找结论——等价于拒绝**选择性遗忘**。语义检查点**只固化结论、决策与产物引用**，不保存完整推理链，用压缩与外置对抗上述问题；与 Paper 1 共享同一套 archive 语义——在 AgentOS 里服务抢占与预算，在本文里服务故障恢复，触发不同、思想一致。

**关键观察：LLM 可以理解自己的失败。** 如果 step 5 因为调用工具时传了错误参数而失败，LLM 看到错误消息 + 原始意图后，往往能修正参数重新调用——不需要重做 steps 1–4 的规划和上下文收集。这和传统程序的 crash recovery 根本不同：传统程序不能"看看报错然后换个写法"。若 agent 在同一作用域内反复铺陈推理、却很少落地为有效行动，恢复会被动反复触发，放大 token 消耗；步级何时缩短推理、直接调用工具，属于元策略，不在本文展开，与 Paper 1 的 Turn 级计量与止损正交。

---

## 核心机制

### 分层执行模型（Hierarchical Execution）

将任务分解为三层，每层定义独立的错误边界：

```
Goal: "帮用户重构这个 Python 模块"
│
├─ Plan Layer (子任务级)
│  ├─ Subtask 1: "分析现有代码结构"
│  ├─ Subtask 2: "设计重构方案"
│  └─ Subtask 3: "逐函数重构并测试"
│      │
│      ├─ Action Layer (原子操作级)
│      │  ├─ Action 3.1: read_file("module.py")
│      │  ├─ Action 3.2: rewrite_function("parse_input")
│      │  ├─ Action 3.3: run_tests()          ← 失败
│      │  └─ Action 3.4: rewrite_function("format_output")
```

Action 3.3 测试失败时：先在 Action Layer 内尝试修复（修改 3.2 的重构逻辑，重跑 3.3）。如果 Action Layer 修不了（比如设计方案本身有问题），才升级到 Plan Layer（修改 Subtask 2 的设计方案）。**不需要重做 Subtask 1 的代码分析。**

### 语义检查点（Semantic Checkpoint）

在每层边界生成结构化的进度快照：

```
Checkpoint(Subtask 1 完成后):
{
  "completed": "代码结构分析",
  "key_findings": "模块有 3 个公开函数、2 个内部函数、循环依赖于 utils.py",
  "decisions_made": "决定先解耦循环依赖再重构各函数",
  "artifacts": ["dependency_graph.json"]
}
```

**这直接复用 Paper 1 的语义存档机制，但用途不同**：Paper 1 用语义存档做抢占保存（让位给高优先级 Turn），Paper 2 用它做故障恢复（从失败点前的快照续跑）。底层是同一个 archive engine，上层是不同的触发逻辑。

检查点的成本远低于全量 context 保存：只保存决策和结果，不保存完整推理链。

### 反射式局部恢复（Reflective Local Recovery）

当某个 action 失败时，生成一个**恢复 prompt**：

```
你正在执行任务：[从检查点恢复的目标和进度]
Step [X] 失败了，错误信息：[具体报错]
请分析失败原因，修正你的方案，然后继续执行。
```

这不是盲重试——LLM 拿到了错误信息和上下文，可以：换一个工具、修改参数、调整策略。这是 LLM agent 独有的恢复能力，传统程序做不到。

**预算感知：** 恢复尝试受 Paper 1 的 Budget Governor 约束。如果当前作用域内的 remaining budget 不够一次恢复尝试，直接升级到上层作用域或 graceful fail，不做无谓挣扎。

### 爆炸半径分析（Blast Radius Containment）

分析失败影响的范围：哪些下游步骤依赖失败步骤的输出，哪些是独立的。独立分支可以继续执行，不因一个分支的失败而暂停。

例："生成报告" = [查数据库, 格式化模板, 写摘要]。数据库查询失败时，模板格式化可以先做，不必等。

---

## 执行模型的诚实限制

**反射式恢复不是万能的。** 如果失败原因是任务本身超出模型能力（比如要求解一个模型解不了的数学问题），无论重试几次都不会成功。本文的恢复机制只处理"可修正的失败"（参数错误、工具暂时不可用、输出格式错误），不处理"能力边界失败"。

**检查点有损。** 和 Paper 1 的语义存档一样，语义检查点是有损压缩。恢复后的 context 不等于原始 context。在推理链深度大（>10 步连续推理）的任务上，检查点恢复的质量可能显著下降。

**恢复本身消耗资源。** 生成恢复 prompt + LLM 推理 = 额外 token。如果失败频率高，恢复开销可能超过全量重启。存在一个盈亏平衡点，需要实验确定。

**层级划分需要任务结构。** 对于没有自然分层结构的任务（单轮问答、纯推理），分层执行退化为扁平执行，本文的机制不提供额外收益。

---

## 研究问题与实验计划

### RQ1：Token 效率

在标准 agent benchmark（SWE-bench、WebArena、HumanEval multi-step）上，scoped recovery vs. flat restart vs. blind retry，每成功完成一个任务消耗多少 token？

预期：对多步工具调用任务，scoped recovery 应显著节省 token（因为不丢弃前面步骤的进度）。对单步任务，无差异。

### RQ2：局部恢复成功率

当 action 失败时，reflective local recovery 的成功率是多少？按失败类型分类：工具报错、格式错误、参数幻觉、逻辑错误、能力边界。哪些类型局部恢复有效？哪些必须升级？

### RQ3：检查点保真度

从语义检查点恢复 vs. 从完整 context 恢复，后续步骤的成功率差多少？在不同检查点深度（5 步、10 步、20 步后生成的检查点）下，保真度如何衰减？

### RQ4：最优粒度

错误边界设在什么粒度最有效？过细（每个 tool call 一个边界）→ 检查点开销大；过粗（整个任务一个边界）→ 退化为全量重启。实验测量不同粒度的 cost/benefit 曲线。

---

## 与 Paper 1 的关系

Paper 1 的 zombie detector 发现一个 Turn 卡死了。在没有 Paper 2 的世界里，zombie 被 kill 并标记为可重试——全量重启。有了 Paper 2，zombie 被检测后可以触发 scoped recovery：从最近的检查点开始，用反射式修正尝试恢复，而不是完全丢弃进度。

Paper 1 的 Budget Governor 为 Paper 2 的恢复尝试划定硬红线：恢复不是无限重试，而是在预算余额内尽力。这让整个恢复过程有确定性上限。

反过来，Paper 2 提高了 Paper 1 的资源效率：恢复成功意味着少浪费 token，Governor 管辖下的全局吞吐因此提升。