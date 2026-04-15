# Paper 1 Next Steps（把“宝藏”落地）

> 目标：把 Paper 1 的叙事从“我们发明了一套 task_type”升级成“我们参考了真实 SOTA agent 系统的行为分布，因此 RQ2/RQ3 的 workload 与对照组有现实依据”，并把这套证据链写进论文。

核心素材（当作“需求文档/背景板”，不是代码依赖）：
- [AgentLaboratory](https://github.com/SamuelSchmidgall/AgentLaboratory)
- [AI-Scientist-v2](https://github.com/sakanaai/ai-scientist-v2)

---

## 0. 为什么它们是“宝藏”（落地价值）

虽然这两个仓库的代码不需要直接集成到 AgentOS，但它们对你的科研有决定性的支撑，主要体现在：

- **RQ2（任务感知选模）**：证明你的 `task_type` 不是拍脑袋，而是能映射到真实系统阶段/角色；并给出现实行为分布作为 workload 建模依据。
- **Storytelling（讲故事）**：把“资源治理”叙事换成“成本效益优化（quality under budget）”，让审稿人更容易接受：你解决的是“钱花得值”的核心问题。
- **RQ3（抢占/僵尸）**：多分支探索/树搜索天然会产生并发、卡死、长尾与预算燃烧，是抢占与 zombie detector 的最佳应用场景与动机来源。

---

## 1. 它们是你最硬核的 “Real-World Workload” 证据

### 1.1 解决 Paper 1 最大软肋：task_type 是否拍脑袋？

把“真实系统阶段/角色”映射到你的 `task_type`（论文里写成现实依据，而不是凭空设计）：

- **AgentLaboratory 的阶段（phase）≈ 你的 task_type**
  - Literature Review → `retrieval`（查文献、读论文、信息抽取）
  - Experimentation / MLE-Solver → `reasoning` + `generation`（设计实验、写代码、调参/诊断）
  - Report Writing / Paper-Solver → `transform` + `summarization`（填模板、结构化输出、写摘要/小节）

这段话术的关键不是“完全一致”，而是：**你用的是“可解释的现实映射”来支撑分类法的合理性**。

### 1.2 你不需要跑它们，只需要“读它们的行为/日志/提示词结构”

落地动作（优先级从高到低）：

- **读 prompt / agent role 定义**：提取“这个阶段到底在做什么”，据此确认 `task_type` 的边界（例如“写代码”和“写论文段落”都属于 generation，但质量敏感度可能不同）。
- **读日志/调用统计（如果仓库或论文提供）**：估计真实系统里不同阶段的 LLM 调用占比、典型延迟/成本范围、是否存在 burst 并发。
- **把统计写入 Paper 1**：  
  “我们的 workload 配置参考了 AgentLaboratory/AI-Scientist-v2 的真实行为分布（阶段占比/调用模式/并发形态），因此 mock 实验不是自嗨。”

预期产出（写进论文的一张图/一段话）：
- 一张 **stage/task_type 占比柱状图**（哪怕是粗粒度区间估计，也比“凭经验设定”强很多）
- 一段 **workload 合法性声明**（为什么 turn mix、priority mix 合理）

---

## 2. 它们是你最强的 “Baseline A（无脑贵的）” 现实原型

RQ2 的对照组 A 是“全程用最贵模型”。你可以把 AgentLaboratory 当作现实映射来讲：

- 话术模板（可放 Related Work / Motivation / RQ2 setting）：
  - “现有端到端科研 agent（如 AgentLaboratory）展示了巨大潜力，但常采用全程高端模型驱动，导致成本高昂。”
  - “我们的目标不是让系统不崩，而是在预算约束下最大化质量：将质量敏感的关键步骤保留给高端模型，将检索/格式转换等步骤路由到廉价模型，从而获得更好的质量-成本 Pareto。”

注意：这里**不需要声称 AgentLaboratory ‘就是’ baseline A**，只要强调它是“现实中常见的极端策略原型”，用来支撑对照组的必要性。

---

## 3. 用它们反向支撑 RQ3：抢占与僵尸的现实必要性

AI-Scientist-v2 的 agentic tree search / 多分支探索天然有这些痛点：
- 并发分支多 → 容易出现资源争抢与交互被阻塞
- 个别分支卡死（训练/评估挂起）→ 占槽、拖垮吞吐
- 某些分支异常输出/日志爆炸 → 烧钱、拉高尾部成本

落地话术（RQ3 动机段）：
- “多分支探索型 agent（如 AI-Scientist-v2）面临严重的资源协调问题：单个失控分支会拖垮整体预算与交互体验。AgentOS 的 preemption 与 zombie detector 专门解决这一痛点。”

落地实验建议（作为补充实验/附录，不影响主线 mock 可复现性）：
- 用 RQ3 的 workload 直接模拟“并发分支 + interactive 插入 + 失控分支”
- 额外报告：`zombie_reaped` 数、`resume_cost_usd`/`resume_prefill_ms`、以及用户主观体验分（如果做 UX study）

---

## 4. “抄作业版”具体行动清单（最小闭环）

### 4.1 抄作业：用真实角色/阶段来定义 task_type

动作：
- 打开 AgentLaboratory 的 agent 角色定义文件（例如 `agents.py`），抽取角色/阶段清单（MLE-Solver、Paper-Solver 等）。
- 打开 AI-Scientist-v2 的入口与搜索/分支控制逻辑（例如启动脚本/搜索主循环），抽取“并发与分支结构”的关键行为模式。
- 输出一张 mapping 表：**{real system role/phase} → {AgentOS task_type} → {质量敏感度/是否关键}**。

产出：
- `paper1_design.md` 或论文正文里的一个小表格（task_type 的现实来源）

### 4.2 构造（不是复刻）你的 Mock Workload

动作：
- 用“阶段占比”构造 turn mix，例如：
  - 前 20%：`retrieval`
  - 中间 50%：`reasoning`
  - 后 30%：`generation`/`summarization`/`transform`
- 用 RQ2 的关键叙事设置 “关键任务权重更高”（`difficulty_weight` 或隐式权重）。

产出：
- 一份新的 `workload`（或在现有 RQ2 workload 上给出“来源解释段落”）
- 论文里一句话：workload distribution 的来源与合理性

### 4.3 把它们的缺点当成你的卖点

动作：
- 明确对比点：现有系统“降本”往往依赖人工介入；你强调 AgentOS 的自动化预算分配与止损。

产出：
- RQ2/RQ3 的一句硬话：  
  “我们在不增加人工干预的前提下，实现了更好的质量-成本 Pareto 与更稳定的交互体验。”

---
