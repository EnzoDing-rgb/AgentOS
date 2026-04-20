## 四条候选路线（融合版）

下面统一用 **“目标 venue / 核心叙事 / 需要补的东西 / 备注”** 四段式组织。  
说明：所有涉及形式化证明（Setting S 定理、KKT 水位线推导、凸优化推导等）**已去除**；仅保留研究方向、工程化解释与可执行的实验/写作建议。评估指标中必要的定义公式保留。

---

## 路线一：走软件工程（SE 实证）

**目标 venue**：ICSE / FSE / ASE（CCF-A）；期刊 IEEE TSE / ACM TOSEM（CCF-A，常为 SCI Q1）。

**核心叙事**：SE 社区缺“面向 LLM Agent 的工程基础设施”，且对“系统工具 + 扎实实验”的接受度通常高于 OS 社区。贡献定位为：

> 在真实软件工程任务（代码生成、自动修复、测试生成等）中，LLM Agent 资源治理缺乏系统研究；我们给出完整中间件并做大规模实证评估。

你不必把算法理论“新”作为卖点；要证明的是：问题真实存在、足够严重、方案能显著改善（成本/质量/稳定性/体验）。

**需要补的东西**：
- **真实工作负载**：把 “workload / mock turn” 抽象模拟，替换为真实 SE Agent 负载（SWE-bench agent、HumanEval 多 agent 协作流水线、ChatDev / MetaGPT 等）。
- **真实成本与质量指标**：成本用 token/美元；质量用通过率、修复成功率、生成质量分等。
- **实证对照**：报告“无治理的浪费有多严重”（预算超支、僵尸调用、429 级联）与“加治理改善多少”。

**备注**：投入产出比最高。现有系统与实验框架基本不用大改，主要改两件事：工作负载来源（抽象→真实）+ 论文叙事（“OS 调度”→“SE 基础设施”）。TSE/TOSEM 篇幅更充裕，适合写完整消融；ICSE/FSE tool track 也天然匹配。

---

## 路线二：加一层学习，走 AI 系统交叉

**目标 venue**：AAAI / IJCAI system track（CCF-A）；期刊 TPDS（CCF-A + SCI Q1）。

**核心叙事**：当前 ModelSelector 以规则为主（质量及格线 + `budget_factor` 阈值），容易被认为“拍脑袋”。把它升级为在线学习（如 contextual bandit）驱动的路由决策，可写成：

> LLM 调用路由是一个带预算约束的在线优化问题；我们用在线学习方法做路由，并提供系统实现与实证评估。

**需要补的东西**：
- **问题形式化**（面向论文叙事层即可）：状态/上下文、动作（模型/后端选择）、回报（质量/成本或其变体）。
- **在线学习算法设计**：contextual bandit 或变体。
- **算法层面的保证**：给出“为什么合理/有什么保证”的分析口径（regret bound / competitive ratio 这类），不展开严密推导也可。
- **基线对比**：与 bandit 基线方法对比。
- **系统实现 + 实证评估**：把算法落到真实系统策略，跑出可复现实验结论。

**备注**：工作量不小但路径清晰。最大优势是同时具备系统贡献与算法贡献，投稿适用面最广；若时间充裕、理论功底不错，优先考虑。

---

## 路线三：多租户公平性，走分布式系统

**目标 venue**：USENIX ATC（CCF-A）/ EuroSys / SoCC；期刊 TPDS。

**核心叙事**：当前设计是单租户。扩展到多租户（多个 agent 团队共享 LLM 资源池、各自预算与 SLO），问题转为“多租户公平调度”。可借鉴 DRF 变体，把 token、成本、并发度作为多维资源，讨论公平性质（envy-freeness / strategy-proofness / Pareto efficiency）以增强系统论文味道。

**需要补的东西**：
- **多租户抽象**：从 Turn-only 视角扩展到 Tenant/Team（必要时引入 Task 作为预算与所有权载体）。
- **公平性定义与论证口径**：明确你要满足/近似的公平目标（不要求写严格证明）。
- **多租户工作负载实验**：混合交互/批处理、多团队竞争、预算与 SLO 冲突场景。
- **与路线四衔接**：Task 级预算与公平策略可显式化（见文末附录）。

**备注**：改动最大、上限最高；ATC 乃至 EuroSys 都有可能，但需要更多系统建模与评估投入。

---

## 路线四：成本效益优化（quality under budget）——独立主叙事 / 外壳

**目标 venue**：与路线一/二/三兼容（SE 或 Systems/AI 交叉均可）；也可独立推进，但更推荐作为其他路线的主叙事外壳。

**核心叙事**：如果担心被归类为“另一个 AgentRM：让系统不崩”，把主叙事抬升为：

> **在预算约束下最大化输出质量（并保证交互体验不崩）。**  
> Governor / Preemption / Zombie 是约束与实现手段；论文主目标是 **cost-effectiveness**。

这能把 RQ1–RQ3 串成同一个优化目标的逐步逼近：
- **RQ1**：把外部 429/崩溃变成内部可控排队，使 cost-effectiveness 可稳定测量
- **RQ2（核心）**：质量-成本权衡下的模型路由，把钱花在刀刃上
- **RQ3**：把尾延迟与僵尸损耗纳入“有效产出”，避免预算被低价值/卡死请求吞掉

**需要补的东西**（评估指标体系升级为主）：

1) **Quality-weighted 完成（不只看数量）**
- **QWCR**：令 turn 终态质量 \(q_i\in[0,1]\)，失败/回收记 \(q_i=0\)，则
  $$
  \text{QWCR}=\frac{1}{N}\sum_{i=1}^{N} q_i
  $$
- **QW-Completed**：
  $$
  \text{QW-Completed}=\sum_{i=1}^{N} q_i
  $$
- **\(q_i\) 来源**：
  - Mock：`completed` 事件（或对应调用记录）里的 `quality_score`
  - RealBackend：按 `task_type` 用确定性 grader 得到 `quality_score`（见 `paper1_design.md §3.3`）

2) **Budget efficiency（钱花得值不值）**
- **Q/$**：
  $$
  \text{Q/\$}=\frac{\sum_i q_i}{\text{cost\_total\_usd}}
  $$
- **WQ/$（可选）**：若 workload 提供 `difficulty_weight`（权重 \(w_i\)），则
  $$
  \text{WQ/\$}=\frac{\sum_i w_i q_i}{\text{cost\_total\_usd}}
  $$
- **实现备注**：
  - 分母 `cost_total_usd` 来自 `summary.json`，或从 `events.jsonl` 汇总 `settlement_usd`
  - 防坑：某 policy 因预算耗尽导致 cost 很低、几乎没做事，Q/$ 可能虚高；建议同图报 **QWCR** 与 **Q/$**，或直接做 Pareto frontier

3) **质量-成本 Pareto 分析**
- 横轴 `cost_total_usd`，纵轴 `QW-Completed` 或 `QWCR`
- 画不同 policy 的点云/均值 ± CI，并标出 Pareto frontier
- 便于写硬话：同预算下质量更高 / 同质量目标下成本更少

4) **交互体验（可选但很加分）**
- 小规模用户研究：对比 `agentos_no_preempt` vs `agentos`
- 量表：Responsiveness / Smoothness / Trust / Overall satisfaction
- 输出：均值 + 95% CI（或配对 t-test / Wilcoxon），并与 `ttft_p99`、`zombie_reaped` 做相关性对齐

**备注**：
- 这条路线本质上是“主叙事外壳”：把研究问题从“资源治理工具”抬升为“预算约束下的质量最大化”，更容易让 SE / Systems / AI 审稿人有共同语言。
- 系统机制在该叙事下的统一定位：
  - **Governor**：保证预算/限流约束硬成立（否则指标与对照不稳定）
  - **Preemption**：把交互体验作为 SLO 或 penalty，避免尾部拖垮有效产出
  - **ZombieDetector**：止损无效燃烧成本，避免 Q/$ 被噪声污染

---

## 附：设计取舍说明（Workload / Task / Turn）

当前设计里调度与记账锚点是 **Turn**；**Workload** 是“一次 run 吃进去的剧本”；**Task** 是上层语义目标。Paper 1 **不建 Task 实体**，这不是漏洞，而是研究边界：聚焦底层资源治理（预算、并发、选模、回收），不展开上层任务编排（多 Task 分预算、依赖、所有权）。

实现上 workload 文件通常是 `turns[]` 列表——语义上等价于把若干 Task 拆解后的 Turn 写进同一份剧本。Task 边界可以存在于研究者心里，但实验与调度器只认 Turn。Token 仍只作为 Turn 结算单位，不单独成层。

后续扩展方向：
- 接路线三：显式引入 Task/Tenant 级预算与公平策略
- 接路线四：Task 作为任务价值信号（如 `task_type` / `priority` / `difficulty_weight`）的载体

---

## 推荐组合

- **投入最小、最稳**：路线一 + 路线四作主叙事外壳  
- **理论 + 系统最强、投稿适用面最广**：路线二 + 路线四作主叙事外壳  
- **天花板最高、改动最大**：路线三（并在需要时引入 Task/Tenant 层）+ 路线四的“任务价值/有效产出”指标体系

---

## 一句话总建议

先按路线一把真实 SE 证据链做硬；同时把路线四的 cost-effectiveness 指标体系与叙事外壳套上去。若你要冲更高上限，再把路线二的在线学习层加到 ModelSelector 上；路线三适合作为后续扩展或 Paper 2。