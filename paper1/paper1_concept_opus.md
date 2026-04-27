# AgentOS Paper 1: Budget-Constrained Quality Maximization for LLM Agent Workflows

> **一句话**：给定固定预算和一系列 LLM 调用，如何把钱花在刀刃上——让高价值步骤用好模型、低价值步骤用便宜模型、僵尸调用及时止损？
>

---

## 0. 定位：Cursor Auto 已经存在，这篇论文还有意义吗？

公平拷问。今天的开发者已经被 auto-routing 包围：

- **Cursor Auto / OpenCode Auto**：在多步 agent workflow 中对每次 LLM 调用自动选模型
- **OpenAI GPT-5 Auto**：聊天端在 Instant / Thinking 间切换
- **LiteLLM Auto Router / Cloudflare Dynamic Routing**：基于 embedding/规则的 per-query 路由
- **学术 router**：RouteLLM、CARROT、OmniRouter（per-query 性价比预测）

它们都在回答："**这一次** LLM 调用该用哪个模型？"——本文不和它们抢这个问题。本文回答的是更上一层的问题：

> **在一个完整的 agent workflow（多步 LLM 调用）中，如何利用 workflow 级的结构信息（哪一步关键、剩多少预算），做整体的成本-质量分配？**

### 真正的 gap：现有 auto-router 都是 **workflow-blind** 的

| 它们看得到 | 它们看不到（但上层 agent 自己知道） |
|-----------|----------------------------------|
| 当前这次 prompt 的内容、长度、复杂度 | 这次调用是 6 步 refactor 的**第几步** |
| 模型成本与能力差异 | 是 planning / generation / validation 中哪一步 |
| 大致 latency 和 token 消耗 | 错在 planning 比错在 validation 代价大 3 倍 |
| 用户订阅 tier | 整个 task 的预算上限是 \$0.50 |
| | 前 3 步已花 \$0.40，剩 \$0.10 给后面 3 步 |

**这不是 Cursor Auto 不努力，是它"看不到"**——agent workflow 的步骤价值结构（哪一步关键、哪一步不关键、错了下游代价多大）是**上层 agent 的私有信息**，闭源黑盒 router 拿不到，per-query 学术 router 也设计上不接收这个信号。

### 本文的定位：agent 框架与 LLM 后端之间的 **workflow-aware** 治理中间层

```
Agent 框架（SWE-agent / Cursor / MetaGPT）
    │  把 workflow 结构传下来：w_i, 预算 B, task_type, ...
    ▼
═══════ AgentOS（本文）═══════       workflow-aware 成本-质量分配
    │  基于 w_i · Δq_i / Δc_i + budget_factor
    ▼
Per-call router（Cursor Auto / GPT-5 Auto / RouteLLM）   单次调用
    │
    ▼
LLM 后端池
```

**一句话**：Cursor Auto 是 AgentOS 的**底层**（最终决定单次调用怎么发），不是竞争者。AgentOS 把上层 agent 的私有信息（workflow 价值 + 预算状态）接进来用上——这正是 per-call router 设计上做不了的事。

| 维度 | Cursor Auto / GPT-5 Auto / RouteLLM / CARROT | **本文** |
|------|---------------------------------------------|---------|
| 路由信号 | 单次 prompt 内容 | prompt + **workflow 位置 ($w_i$)** + 预算状态 |
| 跨步骤预算 | 无 | 可选 hard budget + 动态配速 |
| 止损 | 无 | 僵尸检测 + 截断（成本涨、质量不涨） |
| 开放性 | 闭源黑盒 | 开放、可测量、可解释 |
| 谁能调用 | 终端用户 / 后端 | **agent 框架**（声明 $w_i$ 即可） |

### 谁会真正用这个？

- **Agent 框架开发者**（SWE-agent / MetaGPT / Cursor 自身）：在框架内集成 AgentOS，把 workflow 结构通过 $w_i$ 暴露给运行时
- **企业多 agent 部署**：多个 agent 共享 LLM 资源池，按 task 给预算
- **个人开发者跑 SWE-bench-style agent**：固定预算下让 agent 跑得更准

---

## 1. 核心洞察：LLM 质量是连续的，调度问题变了

经典 OS 调度假设任务结果是二元的（完成/失败）。LLM 不同——**几乎总能给答案，差别在于答案好坏**：

| 配置 | 质量 $q$ | 成本 |
|------|---------|------|
| GPT-5 Thinking + 长 context | $\approx 0.95$ | \$0.10 |
| GPT-5 Instant | $\approx 0.70$ | \$0.01 |
| 小模型 | $\approx 0.30$ | \$0.001 |

三种都"完成"了，但质量在 $[0,1]$ 上连续变化。于是调度问题从"谁先跑"变成：

> **预算有限时，每个步骤应该被做到多好？**

---

## 2. 形式化：预算约束下的质量最大化

Workload 有 $N$ 个 turn，每个 turn $i$ 选后端 $a_i \in \mathcal{A}$：

$$
\max_{a_1,\dots,a_N}\ \sum_{i=1}^{N} w_i\,q_i(a_i)\quad \text{s.t.}\quad \sum_{i=1}^{N} c_i(a_i)\le B
$$

- $q_i(a_i) \in [0,1]$：turn $i$ 选后端 $a_i$ 的质量
- $c_i(a_i)$：对应成本（USD）
- $w_i$：任务价值权重（调用方声明，如 planning 步 $w=3$，retrieval 步 $w=1$）
- $B$：总预算硬约束

这是多选择背包的变体。对照组自然形成：

| 对照组 | 策略 | 失败模式 |
|--------|------|---------|
| A. `always_expensive` | 每步都用最贵模型 | 很快花光预算，后半段没钱 |
| B. `per_request_greedy` | 每步独立最大化 $q/c$ | 不做配速、不看 $w_i$，后期质量塌陷 |
| C. `budget_aware_uniform` | 有预算配速，但 $w_i \equiv 1$ | 不区分任务价值 |
| **D. AgentOS** | 预算配速 + 任务价值 $w_i$ + 边际性价比 | 在线近似，非离线最优 |

### 2.1 最优性直觉（KKT 一阶条件）

将问题推广为连续版（选质量水平而非离散后端），KKT 条件给出：

$$
\frac{w_i}{c_i'(q_i)} = \lambda \quad \text{（对所有内点 turn）}
$$

$\lambda$ 是预算边际价值（"再多 1 美元能换多少加权质量"）。含义：**最优时每个 turn 的"边际划算程度"趋于同一水位线**。

工程实现中 `budget_factor` 就是 $\lambda$ 的在线近似：花快了调高（更舍不得花）、花慢了调低（更敢花）。

**数学复杂度**：KKT 条件 + 凸优化基础，1-2 周可掌握。不需要 RL/bandit 理论。

### 2.2 边际加权性价比（ModelSelector 排序准则）

$$
\text{score}(i) = \frac{w_i \cdot \Delta q_i}{\Delta c_i}, \quad \Delta q_i = q_i(\text{expensive}) - q_i(\text{cheap}), \quad \Delta c_i = c_i(\text{expensive}) - c_i(\text{cheap})
$$

**数字例子**：
- 任务 A（规划步）$w=3, \Delta q=0.20, \Delta c=\$2$ → score = 0.30
- 任务 B（检索步）$w=1, \Delta q=0.30, \Delta c=\$4$ → score = 0.075

B 的绝对提升更大，但"每 1 美元带来的加权提升"更小——**预算紧时贵模型留给 A**。

---

## 3. 质量怎么衡量？（回应导师 Challenge）

**导师质疑**：质量 $q_i$ 凭什么说好就好？你自己定义的分数别人认可吗？

**回答**：不自己发明评分——**复用 SE 社区已被广泛接受的 benchmark grader**。

### 3.1 评估策略：确定性 Grader

| task_type | Grader | 输出 | 社区接受度 |
|-----------|--------|------|-----------|
| `code_generation` | 编译 + 单测通过率（HumanEval pass@1 范式） | 0–1.0 连续 | HumanEval (Chen et al. 2021), MBPP — 数千引用 |
| `bug_fix` | fail-to-pass 测试（SWE-bench 范式） | 0/1 二值 | SWE-bench (Jimenez et al. 2024) — 顶会标准 |
| `reasoning` | 精确匹配 / 逻辑链校验 | 0/1 | MATH, GSM8K — 标准 benchmark |
| `transform` | JSON schema 校验 + 必需字段检查 | 0/1 | 工业标准 |
| `summarization` | 关键词/小节覆盖率 | 0–1.0 | ROUGE 系列 |

**关键原则**：

1. **Grader 是确定性纯函数**：同输入同输出 → 可复现
2. **不依赖 LLM-as-judge**（避免"用 LLM 评 LLM"的循环论证）
3. **每个 task_type 的 grader 独立于路由策略**：所有 policy 用同一个 grader 打分
4. **分数刻度统一**：0 = 不可用/失败，1 = 满足该 task_type 的正确性标准

### 3.2 实验中的两种模式

| 模式 | $q_i$ 来源 | 用途 |
|------|-----------|------|
| **Mock 实验**（主线） | workload 预设的 `quality_score` | 控制变量：所有 policy 读同一张表，比的是"谁会分配预算" |
| **真实 LLM 实验**（补充） | 调用真 LLM + 确定性 grader 打分 | 验证 mock 结论在真实模型上成立 |

Mock 的目的不是声称线上也有上帝视角，而是**把"分配策略好不好"从"先验估计准不准"里剥离开**。

### 3.3 决策侧 vs 评估侧（必须解耦）

- **决策时**：ModelSelector 用的是先验估计 $\Delta \hat{q}_i$（历史统计 / 静态表），不需要知道本次真实分数
- **评估时**：用 grader 得到真实 $q_i$，计算 QWCR / Q/\$ 等指标
- **类比**：推荐系统用点击率做决策、用留存率做评估——决策从不依赖 ground truth

### 3.4 先验不准怎么办？

RQ2 消融实验 E1–E6 正面回答：

| 实验 | $w_i$ 设置 | 回答什么 |
|------|-----------|---------|
| E1 Oracle | workload 参考权重 | 上限 |
| E2 二档 | high/low 两档 | 粗分也有收益 |
| E3 task_type 表 | 按类型固定权重 | 无精细标注也能落地 |
| E4 加噪 | $w_i$ + 噪声 $\sigma=0.3/0.5/1.0$ | 对误差鲁棒 |
| E5 随机 | 随机 $w_i$ | 最坏情况 |
| E6 全 1 | $w_i \equiv 1$ | 自洽检查：应退化到 C |

**结论**：权重越准收益越高；很粗糙时仍有收益；无信息时退化到 C。

---

## 4. 系统架构：三层映射到优化问题

```
Agent Workflow（N 个 LLM 调用步骤）
        │
        ▼
═══════════════════ AgentOS ═══════════════════
│ 【约束层】Governor                           │
│   预算硬封顶 + API 限流 + 并发准入            │
│   → 保证优化问题 well-defined                │
│                                              │
│ 【优化层】ModelSelector                      │
│   边际加权性价比 + budget_factor 配速         │
│   → 在线近似 max Σ w_i q_i s.t. budget      │
│                                              │
│ 【止损层】ZombieDetector + Preemption        │
│   僵尸截断 + 体验时延抢占                     │
│   → 回收无效成本 + best-effort 体验          │
═══════════════════════════════════════════════
        │
        ▼
LLM 后端池 → events.jsonl → 指标计算
```

| 机制 | 在优化问题中的角色 |
|------|-------------------|
| **Governor** | 保证 $B$ 与限流约束硬成立——否则优化问题 not well-defined |
| **ModelSelector** | 在线近似 $\max \sum w_i q_i$ s.t. budget 的求解器 |
| **ZombieDetector** | 截断"成本涨但质量不涨"的调用——从 Q/\$ 中剔除无效消耗 |
| **Preemption** | 体验时延 best-effort：抢占 batch 给 interactive，冲突时记录违约 |

---

## 5. 评估指标

| 指标 | 公式 | 含义 |
|------|------|------|
| **QWCR** | $\frac{1}{N}\sum q_i$ | 平均质量（失败记 0） |
| **QW-Completed** | $\sum q_i$ | 有效产出总量 |
| **Q/\$** | $\sum q_i / \text{cost}$ | 每美元质量产出 |
| **WQ/\$** | $\sum w_i q_i / \text{cost}$ | 每美元加权质量产出 |
| **Pareto 图** | 横轴 cost, 纵轴 QW-Completed | 核心论证图 |

QWCR 与 Q/\$ 必须同时报告（防止"没花钱也没干活"导致 Q/\$ 虚高）。

---

## 6. 三条 RQ

| RQ | 问题 | 对应机制 | 核心指标 |
|----|------|---------|---------|
| **RQ1** | 不加治理时 429 雪崩，指标无法稳定测量 | Governor | error_429_rate, 完成率 |
| **RQ2**（主贡献） | 同预算下，任务价值感知的选模是否提升质量？ | ModelSelector | QWCR, WQ/\$, Pareto |
| **RQ3** | 僵尸和尾延迟是否污染指标？截断后改善多少？ | Zombie + Preemption | Q/\$ 提升, 违约率 |

---

## 7. Related Work 对比

### 7.1 与 LLM Routing 工作的对比

| 论文 | 类型 | 预算约束 | Multi-step | 任务价值 $w_i$ | 与本文关系 |
|------|------|---------|-----------|---------------|-----------|
| **RouteLLM** (Ong et al. 2024) | 二元 router (strong/weak) | 无 | 无 | 无 | Per-query baseline |
| **CARROT** (Somerstep et al. 2025) | Cost-aware router, minimax 最优 | Per-query cost 预测 | 无 | 无 | Per-query baseline |
| **OmniRouter** (Mei et al. 2026) | 全局约束优化 router | 有（Lagrangian） | 无（独立 query） | 无 | 最近的 per-query 对手 |
| **xRouter** (2025) | RL-based router | Cost-aware reward | 有（episode） | 隐式 | 方法论对手 |
| **Budget-Aware Agentic Routing** (Zhang et al. 2026, arxiv:2602.21227) | RL (BoPO) agentic router | Hard budget | 有（sequential） | 隐式（RL 学出） | **最直接竞争者** |
| **本文** | 优化 + 启发式 | Hard budget | 有（sequential） | 显式 $w_i$ | — |

**与 Budget-Aware Agentic Routing 的关键差异**：
- 他们用 RL（BoPO）学路由策略——需要训练数据、训练成本高、可解释性弱
- 本文用优化启发式（边际性价比 + budget_factor）——无需训练、可解释、可即时部署
- 两种方法互补：本文的启发式可作为 RL 方法的 warm-start baseline

### 7.2 与 OS-Inspired 工作的对比

| 论文 | 核心问题 | 优化目标 | 与本文差异 |
|------|---------|---------|-----------|
| **AgentRM** (arxiv:2603.13110) | 调度失败 + 上下文退化 | 延迟/吞吐量 | 侧重稳定性，不做质量-成本优化 |
| **AgentCgroup** (arxiv:2602.09345) | OS 级资源隔离 | CPU/内存控制 | 不涉及 LLM 调用质量 |
| **AIOS** (arxiv:2403.16971) | 通用 Agent OS 架构 | 系统效率 | 宽泛架构，无质量-成本分析 |

### 7.3 与 LLM Router Benchmark 的关系

| Benchmark | 说明 | 与本文关系 |
|-----------|------|-----------|
| **LLMRouterBench** (2026) | 21 datasets, 33 models, 400K instances | 可用于构造 quality_prior 表 |
| **RouterArena** (2025) | 开放 router 评估平台 | 可对比 per-query routing baseline |
| **RouterBench+** | 33K queries, 85 models, OOD 测试 | 补充评估 |

### 7.4 定位总结

| 研究类别 | 代表工作 | 关注点 |
|----------|---------|--------|
| **Per-query routing** | RouteLLM, CARROT, OmniRouter | 单条 query 选模型 |
| **Agentic routing (RL)** | Budget-Aware Agentic Routing, xRouter | 学习型多步路由 |
| **OS 资源管理** | AgentRM, AgentCgroup, AIOS | 系统稳定性/资源隔离 |
| **Budget-constrained quality optimization（本文）** | AgentOS Paper 1 | 启发式多步质量-成本优化 |

本文的 niche：**不需要训练的、可解释的、基于优化原理的 budget-aware multi-step routing**。

---

## 8. 关键概念速查

| 概念 | 一句话 |
|------|-------|
| **Turn** | 一次 LLM 调用——调度和计费的最小单位 |
| **Workload** | 实验剧本：N 个 turn + 预算 + mock 表现 |
| **$w_i$** | 任务价值权重（调用方声明，非系统推断） |
| **$q_i$** | Turn 输出质量 $\in [0,1]$——由确定性 grader 打分 |
| **budget_factor** | 预算紧松反馈信号（近似 $\lambda$） |
| **Governor** | 约束层：预算 + 限流 + 并发 |
| **ModelSelector** | 优化层：边际加权性价比排序 |
| **ZombieDetector** | 止损层：截断无效消耗 |
| **QWCR** | $\frac{1}{N}\sum q_i$——质量加权完成率 |
| **Q/\$** | $\sum q_i / \text{cost}$——每美元质量产出 |

---

## 9. 投稿建议

**首选路线：软件工程（ICSE / FSE / TSE / TOSEM，CCF-A）**

SE 社区缺"面向 LLM Agent 的成本治理基础设施"，对"系统工具 + 扎实实验"接受度高。

需要做的：
- Workload 用真实 SE agent 任务（SWE-bench agent 的多步 workflow）
- 质量用 SWE-bench / HumanEval grader（社区标准）
- 实证：不加治理 vs 加治理的成本浪费改善

**数学复杂度**：约束优化 + KKT 条件 + 背包贪心近似。不需要 RL 理论。

---

## 10. 审稿人常见质疑

**Q: "你只是预算控制做得好。"**
→ 用 C（$w_i \equiv 1$）排除：若 D 显著优于 C，差异来自任务价值感知。

**Q: "$q$ 和 $w$ 怎么来？拍脑袋吗？"**
→ $q$ 来自确定性 grader（SE benchmark 标准）；$w$ 由调用方声明（类比 Linux `nice` / K8s `PriorityClass`）；降级路径：显式声明 → task_type 默认表 → 二元 interactive/batch → $w \equiv 1$。E1–E6 消融证明鲁棒性。

**Q: "Cursor Auto / OpenCode Auto / GPT-5 Auto 已经解决了这个问题。"**
→ 这些 router 是 **workflow-blind** 的：它们看每次 prompt 选模型，但 agent workflow 的步骤价值结构（哪一步是 planning、错了下游代价多大、整个 task 还剩多少预算）是上层 agent 的私有信息，闭源黑盒 router 拿不到。本文是 agent 框架与 LLM 后端之间的中间层，把这些信息接进来用上——和 Cursor Auto 不是同一层，是它的**调用方**。详见 §0。

**Q: "小规模有意义吗？"**
→ 即使 1 个 agent 6 步，"该把这步推到多好"仍是核心决策。

**Q: "和 Budget-Aware Agentic Routing (BoPO) 比呢？"**
→ 他们需要 RL 训练；我们是无需训练的优化启发式，可即时部署、可解释、可作为 RL warm-start baseline。两种方法互补。

**Q: "质量分数跨 task_type 可比吗？"**
→ 承认刻度差异；主指标外按 task_type 分组报告，并固定 workload 的 task_type mix。

---

## 附录 A：一个具体场景（与 Cursor Auto 的差异）

让 SWE-agent / Cursor 重构代码（"把这个模块拆成三个文件"），workflow 6 步：

| 步 | 任务 | task_type | $w_i$ | 备注 |
|----|------|-----------|------|------|
| 1 | 读代码 | retrieval | 1 | 便宜模型够用 |
| 2 | 制定方案 | reasoning | 3 | **关键**——错了拖累后面 4 步 |
| 3–5 | 生成文件 A/B/C | generation | 3 | 主产出 |
| 6 | 验证 import | transform | 1 | 便宜模型够用 |

**Cursor Auto 的做法**：每次调用独立看 prompt 选模型。它**无法区分**"这是关键的规划步 vs 不关键的验证步"，也**不知道**整个 task 的预算上限——因为这些信息只在 agent 框架的脑子里。

**本文方案**：agent 框架把 $w_i$ 和预算 \$0.50 通过 API 传给 AgentOS。ModelSelector 按 $w_i \cdot \Delta q_i / \Delta c_i$ 排序，把贵模型留给 $w=3$ 的步骤（2–5），$w=1$ 的步骤（1、6）用便宜模型——这是 **workflow 价值结构 × 预算约束**下的边际性价比排序，per-call router 设计上做不了。

## 附录 B：budget_factor 不需要预测未来

`budget_factor` 的核心是闭环反馈（花快了收紧、花慢了放宽），不要求准确预测未来流量。常见配速策略（复杂度递增）：

1. **线性配速**：$F(t) = t/T$，按时间均匀花
2. **滑动窗口 burn rate**：只看最近 $\Delta$ 时间的消耗速率
3. **EWMA**：从历史中持续更新配速模型

即使配速粗糙，只要反馈方向正确，预算就能保持可控。
