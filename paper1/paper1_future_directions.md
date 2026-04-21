## 最现实的三条路

### 路线一：走软件工程（ICSE / FSE / ASE 均为 CCF-A；期刊走 IEEE TSE 或 ACM TOSEM，CCF-A 且常为 SCI Q1）

这是我认为最可行的路线。软件工程（SE）社区现在非常缺“面向 LLM Agent 的工程基础设施”，ICSE 2025/2026 也已经录用了大量 LLM4SE 方向的工具论文与实证研究。在这个社区里，你的贡献可以更清楚地定位为：

> “在真实的软件工程任务（代码生成、自动修复、测试生成等）中，LLM Agent 的资源治理问题缺乏系统研究；我们首次给出完整中间件，并做了大规模实证评估。”

SE 社区对“系统工具 + 扎实实验”的接受度通常高于 OS 社区——你不必证明调度算法在理论上有多新，你更需要证明：这个问题在 SE 场景里确实存在、足够严重、你的方案能显著改善。

需要补的东西：
- 把 “workload / mock turn” 这类抽象模拟，换成真实的 Agent 工作负载：例如运行 SWE-bench 的 agent，跑 HumanEval 的多 agent 协作流水线，或跑 ChatDev/MetaGPT 这类框架
- 用真实的成本指标（token 消耗/花费）与质量指标（通过率、修复成功率、生成质量分等）
- 做一篇实证研究：不加治理时浪费有多严重（预算超支、僵尸调用、429 级联），加了之后改善多少

### 路线二：加一层学习，走 AI 系统交叉（目标 AAAI / IJCAI 的 system track，CCF-A；或期刊 TPDS，CCF-A + SCI Q1）

现在的 ModelSelector 主要是规则选模（质量及格线 + `budget_factor` 三档阈值），审稿人很容易认为这是“拍脑袋”。如果把这一层换成在线学习（online learning），比如用 contextual bandit（情境多臂老虎机）做模型路由：每次决策基于 $(task\_type, budget\_factor, backend\_load)$ 等上下文，回报（reward）用质量/成本比（quality/cost）刻画，并给出 regret bound（后悔界）——你就有了更扎实的算法贡献。这时叙事可以写成：

> “LLM 调用路由是一个在线优化问题；我们形式化了带预算约束的 contextual bandit，并给出近优解。”

再配上系统实现与实证评估，就能撑起一篇“算法 + 系统”的交叉论文。

需要补的东西：
- 问题形式化
- 算法设计
- 理论分析（至少给 regret bound 或 competitive ratio）
- 与 bandit 基线方法对比  
（工作量不小，但路径清晰）

### 路线三：做多租户公平性，走分布式系统（目标 USENIX ATC / EuroSys / SoCC，其中 ATC 是 CCF-A；期刊走 TPDS）

当前设计是单租户的。如果扩展到多租户——多个 agent 团队共享同一个 LLM 资源池，每个团队有独立预算和 SLO（服务等级目标）——问题就变成“LLM 调用的多租户公平调度”。这时可以引入 DRF（Dominant Resource Fairness，主导资源公平）的变体，把 token、成本、并发度作为多维资源做公平分配；如果还能证明机制满足某种公平性质（如 envy-freeness、strategy-proofness、Pareto efficiency），就会更像一篇“有理论支撑的系统论文”。

需要补的东西：
- 多租户抽象
- 公平性定义与证明
- 多租户工作负载实验  
（改动最大，但做出来上限也最高；ATC 甚至 EuroSys 都有可能）

## 我的建议

路线一的投入产出比最高。你现在的系统架构和实验框架基本不用大改，主要是：
- 换工作负载来源（从抽象模拟到真实 SE Agent）
- 换论文叙事（从“OS 调度”转为“SE 基础设施”）

TSE/TOSEM 期刊篇幅更充裕，够你把 RQ1–RQ3 的完整消融实验都写清楚，不像会议容易受页数限制；ICSE/FSE 的 tool track 也明确鼓励这类工作。

路线二和路线三要加的东西更重，但天花板也更高——**如果你有时间且理论功底不错，优先考虑路线二**：它能让这篇论文**同时具备系统贡献与算法贡献**，从而在投稿上**适用范围最广、选择余地最大**。

## 设计取舍补充（Workload / Task / Turn）

当前设计里调度与记账的锚点是 **Turn**；**Workload** 是“一次 run 吃进去的剧本”；**Task** 是上层心里的高层目标，Paper 1 里**不建 Task 实体**，这不是漏洞，而是研究边界：本文聚焦底层资源治理（预算、并发、选模、回收），不展开上层任务编排（多 Task 分预算、依赖、所有权）。

实现上 workload 文件通常是 **`turns[]` 列表**——语义上等价于：把若干 Task 拆解后的 Turn **写进同一份剧本**里；Task 边界可以存在（你心里知道哪几步同属一个用户目标），但实验与调度器可以只认 Turn。

后续若扩展到多租户/多团队，可显式引入 **Task 级预算与公平策略**，与路线三（多租户公平调度）衔接；Token 仍只作为 Turn 结算的计费单位，不单独成层。

---

## 更细的 evaluation（除 P99/TTFT 之外）

`paper1_design.md` 里主线指标以 **完成数/失败率、成本、TTFT P99、平均质量**为主。为了让论证更“像 SE 实证研究”（尤其是投 ICSE/FSE/TSE/TOSEM），建议在扩展实验/附录里补三类指标：**质量加权完成、预算效率、主观体验**。

### 1) Quality-weighted 完成率（不只是数量）

动机：很多策略会把“完成数”做高，但如果完成的大多是低质量输出，工程意义有限。我们需要一个把**完成**与**质量**合到同一个数里的指标。

建议指标（两种口径二选一，建议都报）：

- **QWCR（Quality-Weighted Completion Rate）**  
  令每个 turn 的终态质量 $q_i \in [0,1]$。若 turn 失败或被回收，则 $q_i=0$。则
  $$
  \text{QWCR}=\frac{1}{N}\sum_{i=1}^{N} q_i
  $$
  解释：如果全都高质量完成，QWCR 接近 1；如果大量失败/低质量，QWCR 降低。

- **QW-Completed（质量加权完成数）**  
  $$
  \text{QW-Completed}=\sum_{i=1}^{N} q_i
  $$
  解释：把“完成数”从整数推广到“有效完成量”。当你需要对比不同 workload 大小、或做横向汇总时更直观。

从日志怎么取 $q_i$：
- **Mock 主线**：使用 `completed` 事件里（或该 turn 对应 backend 调用记录里）的 `quality_score`；失败/回收记为 0。
- **RealBackend 补充实验**：按 `task_type` 用确定性 grader 得到 `quality_score`（见 `paper1_design.md §3.3`）。

### 2) Budget efficiency（钱花得值不值）

动机：RQ2/RQ3 里仅看 “cost_total_usd 是否接近预算” 还不够，需要衡量 **每一美元换来的有效质量产出**。

建议指标：

- **Quality per Dollar（Q/$）**  
  $$
  \text{Q/\$}=\frac{\sum_i q_i}{\text{cost\_total\_usd}}
  $$
  解释：单位成本换来的“有效完成量”。适合回答“钱花得值不值”。

- **Weighted Quality per Dollar（WQ/$，可选）**  
  若 workload 提供 `difficulty_weight`（见 `paper1_design.md §7.1`），令权重 $w_i$，则
  $$
  \text{WQ/\$}=\frac{\sum_i w_i q_i}{\text{cost\_total\_usd}}
  $$
  解释：把“关键/难任务”的质量收益放大，更贴近“把钱花在刀刃上”的论点（RQ2 叙事）。

实现备注：
- 分母 `cost_total_usd` 直接来自 `summary.json` 或从 `events.jsonl` 汇总 `settlement_usd`。
- 如果某个 policy 因预算耗尽导致 cost 很低、但也几乎没做事，Q/$ 可能虚高；因此建议在同图里同时报告 **QWCR** 与 **Q/$**（或做 Pareto frontier：横轴 cost，纵轴 QW-Completed）。


---

## 叙事转向：从“资源治理”到“成本效益优化”（quality under budget）

如果你担心审稿人把你归类为“另一个 AgentRM：让系统不崩”，可以把 Paper 1 的主叙事改成：

> **在预算约束下最大化输出质量（并保证交互体验不崩）**  
> 系统机制（Governor/Preemption/Zombie）是约束与实现手段；论文的“主目标函数”是 **cost-effectiveness**。

这会让 RQ1–RQ3 的三层能力更像是逐步逼近同一个优化目标：
- **RQ1**：把“外部 429/崩溃”变成“内部可控排队”，使 cost-effectiveness 可被稳定测量
- **RQ2**：核心贡献：**质量-成本权衡**下的模型路由（在 budget 约束下把钱花在刀刃上）
- **RQ3**：把尾部延迟与僵尸损耗纳入“有效产出”的定义（避免预算被低价值/卡死请求吞掉）

### 1) Formal objective：预算约束下最大化质量

把一次 run 写成一个优化问题。设 workload 有 $N$ 个 turn，每个 turn $i$ 可选择后端 $a_i \in \mathcal{A}$（例如 expensive/cheap）。

- 成本：$c_i(a_i)$（USD）
- 质量：$q_i(a_i)\in[0,1]$
- 总预算：$B$

最直接的形式化是 0-1 背包/多选择背包的变体：

$$
\max_{a_1,\dots,a_N}\ \sum_{i=1}^{N} w_i\,q_i(a_i)
\quad \text{s.t.}\quad \sum_{i=1}^{N} c_i(a_i)\le B
$$

其中 $w_i$ 是任务权重（可直接对应 `paper1_design.md §7.1` 的 `difficulty_weight`；没有就取 1）。

解释（写论文时很好用）：
- baseline A：总是选最高质量动作 → 很快触发预算约束 → 目标函数未必最大
- baseline B：逐请求贪心性价比 → 不考虑全局预算时序 → 可能把预算花在低权重 turn
- baseline C：全局预算感知但不看 task_type/权重 → 相当于用粗糙的 $w_i$（全 1）近似
- AgentOS：显式利用 $w_i$（或 task_type/priority 信号）近似 “价值”，把 budget 分配给高边际收益的 turn

### 2) Quality–cost tradeoff analysis：从“更多 turn”到 Pareto

把论文图表从“完成率/成本”升级为“质量-成本 Pareto”：
- 横轴：`cost_total_usd`
- 纵轴：`QW-Completed` 或 `QWCR`
- 画出不同 policy 的点云/均值 ± CI，并报告 Pareto frontier

这样审稿人更容易接受你的 claim：
- “我们的策略不是单纯更快/更稳，而是在同预算下把质量做得更高”
- “在同质量目标下，我们用更少的钱（或在同钱下，我们拿到更高质量）”

### 3) ModelSelector 的“最优性”怎么写（一个可证明的 setting）

你现在的实现是规则路由（质量及格线 + `budget_factor` 调节门槛）。要写出“optimal”，需要一个**刻意简化但可解释**的 setting，让结论成立且可检验。

推荐一个最干净、最容易写进论文的 setting（用于 theorem，不必等同真实系统）：

**Setting S（两后端 + 已知先验 + 单调性）**
- 仅两个后端：E（expensive）与 C（cheap）
- 对每个 turn $i$，已知先验：$\Delta q_i = q_i(E)-q_i(C)\ge 0$，$\Delta c_i = c_i(E)-c_i(C)>0$
- 目标：最大化 $\sum_i w_i q_i(a_i)$ 在预算约束下

则最优解等价于：在满足预算的前提下，对一部分 turn 选择 expensive，其余选择 cheap；选择集合应按“边际收益/边际成本”排序：

$$
\text{score}(i)=\frac{w_i\,\Delta q_i}{\Delta c_i}
$$

**结论（可写成定理）**：若允许对 turn 进行离线排序（workload 事先已知），选择 score 最高的若干个 turn 用 expensive（直到预算用尽）是最优（对应“fractional knapsack”时严格最优；对应 0-1 knapsack 时是经典贪心近似/在额外条件下最优）。

怎么把它接回你的系统叙事：
- 把 `task_type/priority/difficulty_weight` 当作 $w_i$ 的显式近似
- 把 `quality_prior` 差值当作 $\Delta q_i$ 的估计
- 把 token 估算与价格表当作 $\Delta c_i$ 的估计
- 你的 ModelSelector 可以被解释为：在在线场景里用 `budget_factor` 做一个“预算乘子/阈值”来近似上述离线最优解

**写法建议（避免被抓漏洞）**
- 主文：给出 Setting S + 一个清晰定理（或 proposition），强调“在该 setting 下我们的方法等价于/逼近最优”
- 真实系统：承认 $q_i,c_i$ 不可完全知道，因此使用先验估计 + 在线预算信号；用实验展示鲁棒性（RQ2 的对照 C 正是为了排除“只是控预算更好”的解释）

### 4) 把“系统机制”重新定位为优化约束

当主叙事换成 cost-effectiveness 后，Governor/Preemption/Zombie 的位置更自然：
- **Governor**：保证预算约束与限流约束“硬成立”（否则优化问题本身不定义良好）
- **Preemption**：把交互体验作为约束（例如 TTFT P99 视作 SLO）或作为目标函数中的 penalty
- **ZombieDetector**：把“无效燃烧成本”从目标函数里剔除（否则 Q/$ 被噪声污染）

一句话版结尾（可放 extended 或摘要草稿里）：

> 我们将 LLM 调用治理表述为一个 **budget-constrained quality maximization** 问题；系统机制保证约束成立，而路由策略在可证明的简化 setting 下最优/近最优，并在真实 workload 上实现更好的质量-成本 Pareto。

---

## 进一步拔高：新的调度理论 + 深层洞察（10/10 版本）

上面那段 “Setting S 的最优/近最优” 只能算是**把经典背包/贪心叙事写得更严谨**，但仍然容易被批评为“把 OS/OR 老理论拿来套 LLM”。如果你想冲 10/10 的理论贡献，需要把论点从“optimality proof”升级成：

- **提出一个新的调度理论对象**：专门针对 LLM agent 的“质量是连续的、可随成本平滑变化”的特性
- **给出定理 + 证明 + 边界条件**：清楚写出何时成立、何时不成立，以及失效时会发生什么

下面给一个可写进论文的框架草稿：**Quality–Cost Aware Scheduling（QCAS）**。

### 1) 理论创新：Quality–Cost Aware Scheduling（QCAS）

经典 OS 调度（例如 MLFQ）隐含了一个前提：任务的“收益/完成”是近似二元的（跑完/没跑完），优化多围绕吞吐、等待时间、公平性。

LLM agent 调用的关键不同点是：**质量是连续的**，并且通常可以通过增加成本（更强模型、更长输出、更大上下文）来提高质量，形成 **质量-成本曲线**。

把每个 turn $i$ 的“决策”从选一个后端，升级为选一个**质量水平** $q_i\in[0,1]$（或等价地选一个“推理预算/模型强度”），并设：
- 成本函数：$c_i(q)$，随 $q$ 单调递增（更高质量更贵）
- 价值权重：$w_i$（任务价值/关键性）
- 交互约束：例如 interactive 的 TTFT P99 必须 $\le \tau$（SLO）

则一次 run 的核心问题可以写成：

$$
\max_{q_1,\dots,q_N} \sum_{i=1}^{N} w_i\,q_i
\quad \text{s.t.}\quad \sum_{i=1}^{N} c_i(q_i) \le B,\ \ \text{SLO constraints}
$$

这不是简单“调优先级”，而是把调度变成：**在预算约束下，把质量配额分配给不同 turn**。

#### 定理方向（可证明、可写边界条件）

在下列条件下：
- $c_i(q)$ 连续可微、严格凸（quality 越往上提，边际成本越高）
- 目标是线性的 $\sum w_i q_i$
- 只考虑预算约束（暂忽略 SLO/并发，或把它们写成可分解约束）

则该问题是一个标准凸优化（或可转化为凸优化），满足 KKT 条件。最优解具有“水位线”结构：

> 存在一个全局乘子 $\lambda^*$（可解释为“当前预算的影子价格”），使得每个 turn 的最优质量满足  
> $w_i = \lambda^* \, c'_i(q_i^*)$（在内点解时），即  
> $\frac{w_i}{c'_i(q_i^*)} = \lambda^*$ ——所有被分配到非 0/非 1 的 turn 具有相同的边际“价值/边际成本”。

这条结论是一个新的“调度原则”：**预算最优不是“谁优先”，而是“把每个 turn 推到同一个边际性价比水位线”**。

边界条件（必须写清楚，否则会被抓）：
- 若某些 $c_i(q)$ 不是凸的（例如存在跳变：从小模型到大模型是离散跃迁），则最优解会退化为“分段凸 + 离散选择”，需要用近似或 mixed-integer 方法；此时给出近似界或经验鲁棒性。
- 若质量不可平滑控制、只有离散后端集合（现实常见），则 QCAS 给出的是一个“连续松弛”的上界；实际系统可用启发式/在线学习去逼近该上界。

把它接回 AgentOS 的实现（作为“理论→系统”桥）：
- `budget_factor` 可以被解释为对 $\lambda^*$ 的在线估计：花快了表示 $\lambda^*$ 更大（钱更贵）→ 降低目标质量门槛；花慢了 $\lambda^*$ 更小 → 提高目标质量。
- “质量及格线 + budget_factor 调门槛”是对“水位线结构”的一个工程化、可解释近似。

### 2) 深层洞察：连续质量 ⇒ 调度是在线凸优化，而不只是类比 OS process

更强的洞察不是“agent 像进程”，而是：

> **LLM 调用的输出质量不是 binary 的，它是连续谱；因此资源分配的核心不再是让更多 job 完成，而是决定每个 job 应该被推到多高的质量水平。**

一旦接受这点，很多设计选择都会从“经验规则”变成“优化结构的近似”：
- **为什么要区分任务价值（w_i）**：因为线性目标里 $w_i$ 直接决定了最优分配的质量水平
- **为什么要动态预算适应**：因为在线场景里 $\lambda^*$ 必须随运行进度更新（预算影子价格是动态的）
- **为什么要把僵尸当作止损**：因为僵尸相当于把 $c_i(\cdot)$ 的尾部推到极端高成本、但 $q_i$ 不增长（边际收益≈0），任何合理的水位线策略都会把它截断

如果你愿意再拔高一层（可选）：
- 把 TTFT/P99 写成 penalty（例如 $-\alpha \cdot \text{TTFT}$）或约束（SLO），就得到一个“质量-成本-体验”三目标问题；可以用拉格朗日松弛把它写成多乘子形式，继续得到“多水位线”结构（一个是预算影子价格，一个是交互体验影子价格）。

### 3) 怎么写进论文（避免过度承诺）

建议写法是“三段式”，既显得硬核，又不把自己逼死：
- **理论段（主文/附录）**：给出 QCAS 的连续模型、定理（KKT 水位线结构）、以及清晰的边界条件
- **系统段（主文）**：说明 AgentOS 的启发式如何对应对偶变量/水位线的在线近似（budget_factor、quality threshold）
- **实证段（RQ2/RQ3）**：用 QWCR、Q/$、Pareto frontier 证明“我们确实更接近该理论最优结构”，而不是只靠类比