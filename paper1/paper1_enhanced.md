# AgentOS Paper 1 概念导读（Quality-under-Budget 版）

> **这份文档回答：AgentOS Paper 1 到底在做什么？**  
> 主叙事：**在预算约束下最大化有效质量（quality under budget）**；系统机制（Governor / ModelSelector / Preemption / Zombie）是实现该目标的**约束与手段**。  
> 本文包含：动机、核心概念、优化视角、实验直觉、术语表；不含接口/实现细节（见 `paper1_design.md` / `paper1_implementation.md`）。

---

## Big Picture：一句话 + 一张图

**一句话**：AgentOS 是夹在 *Agent* 和 *LLM 后端* 之间的“调用操作系统”。它的主目标不是“只要不崩”，而是 **在预算约束下最大化有效质量产出，并把交互体验（TTFT/P99）作为必须满足的 SLO 约束**。稳定性机制（不超支、不打爆 API、不被僵尸吃掉）是**让优化问题可定义、可测量**的前提，而不是论文唯一卖点。

**核心思路**：把问题拆成三件事——**管入口（准入/排队）**、**选质量水位（质量-成本权衡）**、**回收无效成本（抢占/僵尸）**。每个决策都写进 `events.jsonl`，所以这不是"讲故事"，而是可度量、可复现的实验系统。

```text
Workload（实验剧本：turns[] + mock + 预算/并发）
        |
        v
  每个 Turn = 一次 llm.call（priority / task_type / difficulty_weight …）
        |
        v
======================  AgentOS（治理+调度层）  ======================
|  【约束层】Governor（预算/限流/并发准入）                          |
|  - 保证优化问题本身 well-defined：预算硬封顶、API 不打爆             |
|                                                                  |
|  【优化层】ModelSelector（在预算下决定每个 Turn 的质量水位）          |
|  - 按 task_type 过"质量及格线"                                    |
|  - 按 w_i · Δq_i / Δc_i（边际加权性价比）选后端                    |
|  - budget_factor 作为"预算影子价格"的在线估计                       |
|                                                                  |
|  【止损层】Preemption + ZombieDetector                            |
|  - 交互 SLO 约束：必要时抢占 batch，保证 TTFT/P99                   |
|  - 把"烧钱但零质量收益"的调用从目标函数里剔除                        |
===================================================================
        |
        v
LLM 后端池（云端 API / 本地模型）
        |
        v
events.jsonl（唯一真相源） -->  summary.json（QWCR、`Q/$`、Pareto 等）
```

---

## 0. 问题空间重定义：从“稳定性”到“成本-质量优化”

同类工作常把问题讲成“怎么让系统稳定、不崩”。Paper 1 更适合把主问题讲成**“怎么让预算花得值”**：把限流/准入/回收等机制定位为**约束与实现手段**，把“质量-成本最优化”放到叙事正中间。（相关工作提到类似方向即可，点到为止。）

| AgentRM 关注 | **Paper 1 主轴** |
|---|---|
| 系统稳定性 | **成本可控性**（budget under control） |
| 吞吐量 | **质量/成本比**（quality per dollar） |
| 优先级排队 | **任务价值感知**（哪些 turn 值得花贵模型） |
| 静态约束 | **动态预算适应**（预算影子价格驱动在线决策） |

**三条 RQ 因此成为同一优化目标的三步递进**：

- **RQ1（让约束可控）**：只开 Governor，把外部 429 / 崩溃变成内部可控排队——**让 quality/cost 指标能被稳定测量**。
- **RQ2（把钱花在刀刃上）**：开 Governor + ModelSelector，在同一预算下做任务价值感知的选模，**最大化 $\sum_i w_i q_i$**，而不只是完成更多 Turn。
- **RQ3（剔除无效成本）**：加 Preemption + ZombieDetector，把尾延迟违约与僵尸燃烧视为"无效成本/无效产出"从目标函数里剔除，同时满足交互体验 SLO。

---

## 1. 核心洞察：**LLM 调用的质量是连续的，不是 binary 的**

这是整篇论文的直觉锚点，也是 Paper 1 和传统 OS 调度工作的根本差异。

经典 OS 调度（MLFQ、CFS、Borg 等）隐含了一个前提：任务结果近似二元——编译成功/失败、SQL 返回/超时、HTTP 200/500。调度器因此天然围绕"让更多任务跑完、别饿死、别超时"优化。

LLM 几乎总能"给你个答案"——差别在于**答案好坏**。同样是写一段代码：

| 配置 | 质量 |
|---|---|
| GPT-4 + 长 context + 思维链 | 接近可直接合入，$q \approx 0.95$ |
| GPT-4 + 短 prompt | 能跑但有小 bug，$q \approx 0.70$ |
| GPT-3.5 | 能跑但很糙，$q \approx 0.50$ |
| 小模型 | 能输出但错误多，$q \approx 0.30$ |

**四种全都“完成”了**——都没有超时、没有报错。但质量在 $[0,1]$ 上连续变化，而且你通常**可以通过增加成本把质量推高**。

于是调度问题从：

> "谁先跑？谁能跑完？"

变成：

> **"预算有限时，每个任务应该被做到多好？"**

一个具体化的对比：你有 10 美元预算、100 个任务。
- **binary 思维**：追求 100% 完成率 → 全用最便宜模型，每任务 $q=0.3$，表面完成但产出不可用
- **连续质量思维**：关键的 20 个推到 $q=0.95$，其余 80 个推到 $q=0.5$ → 完成率仍 100%，但**真正有用的产出**大得多

**全文直觉锚点**：
> 资源分配的核心不再是让更多 job 完成，而是**决定每个 job 应该被推到多高的质量水平**。

---

## 2. 形式化：预算约束下的质量最大化

给直觉，不追求严格定理。

### 2.1 离散版（两后端或多后端选择）

设 workload 有 $N$ 个 turn，每个 turn $i$ 选后端 $a_i \in \mathcal{A}$：

- 成本 $c_i(a_i)$（USD），质量 $q_i(a_i) \in [0,1]$
- 任务权重 $w_i$（对应 workload 里的 `difficulty_weight` / `priority`；无则取 1）
- 总预算 $B$，交互 SLO（如 TTFT P99 上限）

$$
\max_{a_1,\dots,a_N}\ \sum_{i=1}^{N} w_i\,q_i(a_i)\quad \text{s.t.}\quad \sum_{i=1}^{N} c_i(a_i)\le B,\ \text{SLO constraints}
$$

这是多选择背包的变体。**对照组的差异用它讲得特别清楚**：

| 对照组 | 它在近似哪个最优？ | 失败模式 |
|---|---|---|
| **A. 总是高质量** | 忽略预算 | 很快触预算边界，后半段没钱 |
| **B. 逐请求贪心性价比** | 忽略全局预算时序 | 把贵选项用在低 $w_i$ turn 上 |
| **C. 全局预算感知 + $w_i \equiv 1$** | $w_i$ 粗糙近似 | 对“关键 vs 非关键”盲视 |
| **D. AgentOS** | 用 task_type / priority / difficulty_weight 近似 $w_i$ | 在线近似，不做离线最优 |

### 2.2 连续版（把"选后端"推广成"选质量水位"）

每个 turn 的决策不只是"选哪个后端"，而是"把这个 turn 推到多高的 $q_i$"（成本曲线 $c_i(q_i)$ 通常单调递增且有边际递减）：

$$
\max_{q_1,\dots,q_N}\ \sum_{i=1}^{N} w_i\,q_i \quad \text{s.t.}\quad \sum_{i=1}^{N} c_i(q_i)\le B,\ \text{SLO constraints}
$$

**设计原则（直觉，非定理）**：

预算最优的结构通常不是“谁优先谁先跑”，而是**“把每个 turn 推到同一个边际加权性价比水位线”**。系统存在一个隐式的“预算影子价格” $\lambda$：
- 花快了（$\lambda$ 高）→ 降低目标质量门槛
- 花慢了（$\lambda$ 低）→ 提高目标质量门槛

**`budget_factor` 可被解释为 $\lambda$ 的在线估计**；“质量及格线 + budget_factor 调门槛”是这种水位线结构的工程化、可解释近似。

### 2.4 `budget_factor` 需要知道未来流量吗？

在 mock 实验里，workload 由生成器给出，因此“预算应该按时间怎么花”的配速函数可以被视作已知；但在真实系统里，未来请求分布不一定稳定、甚至没有历史数据，因此不应把“准确预测未来”当作前提。生产里常见做法（复杂度递增）是：

- **线性配速**：直接用 $F(t)=t/T$ 做预算进度基线（按时间均匀花）。
- **滑动窗口 burn rate**：只看最近 $\Delta$ 时间的消耗速率外推短期 runway，花得快就提高 $\lambda$，花得慢就降低 $\lambda$。
- **在线学习配速**：用 EWMA 或小模型从历史中持续更新 $F(t)$，适合大规模且有明显周期的流量。

对本文叙事来说关键点更弱：`budget_factor` 的价值主要来自闭环反馈本身——只要“花快了就提高 $\lambda$ 抑制消费，花慢了就降低 $\lambda$ 放宽门槛”的方向正确，即使配速模型很粗，预算也能保持可控，质量分配也会随预算状态自适应。

### 2.3 为什么会出现“水位线”（一阶必要条件，非定理）

这里给出一阶条件来说明“同一个边际阈值 $\lambda$”从哪里来，但**不把它写成一般场景下的定理**。

把“选后端”抽象成“为每个 turn 选择质量 $q_i$”，并假设每个 turn 的成本是质量的函数 $c_i(q_i)$。考虑以下简化问题：

$$
\max_{q_1,\dots,q_N}\ \sum_{i=1}^{N} w_i q_i \quad \text{s.t.}\quad \sum_{i=1}^{N} c_i(q_i)\le B
$$

对最优解的内部点（忽略边界与不可导点），KKT 一阶必要条件给出：

$$
w_i = \lambda\,c_i'(q_i)\quad \Longleftrightarrow \quad \frac{w_i}{c_i'(q_i)} = \lambda
$$

其中 $\lambda \ge 0$ 是预算约束的拉格朗日乘子。这个式子表达的含义是：在最优点上，每个 turn 都被推到一个位置，使得它的“边际加权收益 / 边际成本”达到同一个阈值 $\lambda$。在工程实现里，用 `budget_factor` 作为 $\lambda$ 的在线估计，就能把“花快了/花慢了”的反馈，转成“提高/降低质量门槛”的可解释调节。

**三个必须记住的前提（决定它只能当设计骨架）**：

- **成本曲线形状**：需要把 $c_i(q_i)$ 视作“随质量单调递增，且边际收益递减”的可优化对象；现实里常常是离散选项（选哪个模型）+ 估算误差，因此只能近似为连续曲线。
- **turn 近似独立**：多轮 agent 中后续 turn 的效果依赖前序 turn，严格建模会变成路径依赖优化；这里把依赖折叠进 $c_i(\cdot)$ 或 $w_i$ 的粗粒度信号里。
- **忽略硬 SLO 的简化**：一旦加入交互 SLO 或最低质量保底（例如要求 $q_i \ge q_i^{\min}$），KKT 条件会多出下界约束项；结果是某些 turn 会被“保底钉住”，不再遵循同一条水位线。

一旦接受这点，很多设计选择就从"经验规则"变成"优化结构的自然结果"：

- **为什么要区分 $w_i$**：目标函数里 $w_i$ 直接决定了最优 $q_i$ 的分配
- **为什么要动态预算适应**：在线场景里 $\lambda$ 必须随运行进度更新
- **为什么要把僵尸当作止损**：僵尸相当于成本推到极端高、质量不增长（边际收益 $\approx 0$），任何合理策略都会截断

---

## 3. ModelSelector 的设计原则：边际加权性价比

**核心直觉**：预算有限时，最合理的做法是把"更贵的选项"留给**"边际收益 / 边际成本"最高**的 turn。按下式排序：

$$
\text{score}(i) = \frac{w_i\,\Delta q_i}{\Delta c_i},\quad \Delta q_i = q_i(E) - q_i(C),\ \Delta c_i = c_i(E) - c_i(C)
$$

- $\Delta q_i/\Delta c_i$：每多花 1 美元，质量能提升多少（单位成本的边际收益）
- 乘上 $w_i$：**重要任务的提升更值钱**

**数字例子**：
- 任务 A（关键）$w_A=3$，$\Delta q_A=0.20$，$\Delta c_A=2$：$\text{score}(A)=3 \times 0.20/2 = 0.30$
- 任务 B（不关键）$w_B=1$，$\Delta q_B=0.30$，$\Delta c_B=4$：$\text{score}(B)=1 \times 0.30/4 = 0.075$

B 的绝对提升更大，但"每 1 美元带来的加权提升"更小——**预算紧时应把昂贵选项留给 A**。

**AgentOS 实现怎么对应到这个原则**：
- `task_type / priority / difficulty_weight` → $w_i$ 的显式近似
- `quality_prior` 差值 → $\Delta q_i$ 的先验估计
- token 估算 × 价格表 → $\Delta c_i$ 的估计
- `budget_factor` → $\lambda$ 的在线估计，用于做“预算乘子阈值”

**承认现实约束**：$q_i, c_i$ 不可完全知道，因此使用先验估计 + 在线预算信号；实验用 RQ2 对照 C（全局预算感知但不看 task_type）排除“只是控预算更好”的解释。

---

## 4. 系统机制的重新定位（作为优化问题的约束与项）

| 机制 | 在优化问题中的角色 |
|---|---|
| **Governor** | 保证预算 $B$ 与限流约束**硬成立**——否则优化问题本身 not well-defined |
| **ModelSelector** | 在线近似 $\max \sum w_i q_i$ s.t. budget 的求解器 |
| **Preemption** | 将交互 SLO（TTFT P99）作为硬约束或目标函数中的 penalty $-\alpha \cdot \text{TTFT}$ |
| **ZombieDetector** | 把"无效燃烧成本"从目标函数里剔除（否则 `Q/$` 被噪声污染）|

这个重定位的好处：读者能清晰看到**"机制 → 约束/目标项"的映射**，而不是四个互相独立的模块堆在一起。

---

## 5. 概念对齐：Workload → Task → Turn

很多人困惑："用户脑子里是一个 Task，文档里为什么满屏 Turn？"

| 层级 | 名称 | 是什么 | 谁管 |
|---|---|---|---|
| 最外 | **Workload** | 一次实验的剧本/负载：列出要跑哪些 Turn、何时到、mock 表现 | 实验作者 |
| 中间 | **Task** | 高层目标（"把这个模块拆成三个文件"）；上层 Agent 拆成多步 | 上层 Agent；Paper 1 **不**建 Task 对象 |
| 最小 | **Turn** | 一次 `llm.call()`；调度、计费、事件日志的最小单位 | AgentOS（本文核心） |

**Workload 文件**：主体是 `turns: [ ... ]`——把若干 Task 拆解后的 Turn 序列写进同一份剧本。

**为什么 Paper 1 只调度 Turn**：AgentOS 只保证"每个 Turn 在预算与并发约束下被推到合适的质量水平"，不展开 Task 级编排（多 Task 分预算、跨 Task 依赖）。这是**研究边界**，不是概念缺失。

**钱从哪算**：Token 是 Turn 内部的计费粒度，不单独占一层。

---

## 6. 从一个具体场景开始

你在 Cursor 里让 AI agent 帮你重构一个项目："把这个模块拆成三个文件"。

agent 要做一连串事情：

1. **读代码** → LLM 调用 1（retrieval，$w$ 低，便宜模型就够）
2. **制定方案** → LLM 调用 2（reasoning，$w$ **高**，值得用好模型）
3. **生成文件 A** → LLM 调用 3（generation，$w$ **高**）
4. **生成文件 B** → LLM 调用 4（generation，$w$ 高）
5. **生成文件 C** → LLM 调用 5（generation，$w$ 高）
6. **验证 import** → LLM 调用 6（transform，$w$ 低，便宜）

一次用户请求 = **6 个 Turn**。**Turn 是本文最核心的概念：一次完整的 LLM 调用**。

注意：在连续质量视角下，ModelSelector 的决策不是“平均分配预算”，而是把更高的质量水位分配给 $w$ 高的 Turn（2–5），把 $w$ 低的 Turn（1、6）降到“及格水位”——这就是 §3 边际性价比排序的一次具体实例。

---

## 7. 每个 Turn 要花什么 + 为什么是这三种资源

每个 Turn 同时消耗三样东西：

**钱（预算 $B$）**——LLM 按 token 计费。不同后端一次调用成本可能差 **100 倍**。这就是“质量-成本权衡”存在的物理基础。

**API 调用次数（RPM）**——供应商硬限制（如 tier-1 = 60 RPM），超过报 429。额度每分钟刷新。

**并发槽**——同时在空中的请求数上限。瓶颈不在你的机器，在对面：API 的 RPM 限制、本地 GPU 的显存。并发槽是信号量。

### 7.1 RPM 和并发槽不是一件事

先纠正一个常见误解：并发槽不是“因为服务端只有 10 个线程”。更常见的情况是**服务端为了自我保护**（并行推理能力、显存/KV cache、连接数等），会对每个客户强制一个“同时在跑的请求数上限”。客户端维护并发槽，是为了**和服务端的并发上限对齐**，避免请求被拒绝或在服务端不可控排队。

RPM 和并发槽约束的是两个正交维度：

- **并发槽**：约束“此刻同时在跑多少个请求”，防止瞬间把执行资源占满（影响排队与 TTFT）。
- **RPM**：约束“一分钟累计发起多少个请求”，防止长期高频调用导致成本失控、日志/监控与下游依赖被打爆（影响累计成本与公平性）。

两个反例说明缺一不可：

- **只有并发槽、没有 RPM**：短请求（例如平均 100ms）可以在不超过并发上限的情况下持续高频循环调用，一天内累计请求数会非常高，导致计费、日志/监控、鉴权/数据库/下游 API 的累计压力不可控。
- **只有 RPM、没有并发槽**：可以在同一分钟内一次性打满 RPM 配额并让大量长请求同时在跑，造成瞬时并发尖峰，直接放大排队与尾延迟，甚至触发后端资源不足。

**N 怎么定？** 它是外部硬约束的已知量，启动时配置保守值即可（RPM=60 → N=16）。**Paper 1 刻意把 N 固定为启动参数**——实验要比较不同调度策略，N 动态变化会引入额外变量。系统中**唯一的动态反馈信号是预算水位（budget_factor）**，它作用在"选哪个模型"上，而不是"同时跑几个"。

---

## 8. 这个系统给谁用

**Paper 1 的设计是通用的，不区分个人/企业**：

| | 个人（macOS + Cursor） | 企业（云端 50 个 agent） |
|---|---|---|
| 预算 | 本月剩 10 美元 | 团队月预算 5000 美元 |
| 限流 | 个人 key RPM=60 | 企业 key RPM=3000，50 个 agent 还是不够 |
| 价值差异 | 主线代码 vs 后台 lint | 老板实时请求 vs 批量报告 |
| 僵尸 | agent 卡死占额度 | 某 agent 跑飞烧 200 美元 |

架构一样，只是参数不同。**连续质量视角让小规模场景也有意义**——即使只有 1 个 agent，"该把这个 turn 推到多好"的决策依然存在。

---

## 9. Interactive 和 Batch：不是任务类型，是 SLO 约束

Turn 按"**有没有人在等**"分两种优先级：

- **Interactive**：用户在屏幕前等 → TTFT P99 是硬 SLO 约束
- **Batch**：后台任务 → 仅受预算与最终完成约束

**同一种 task_type 既可以是 interactive 也可以是 batch**：

| 场景 | task_type | priority | 为什么 |
|---|---|---|---|
| IDE 里等 agent 写代码 | generation | **interactive** | 用户在等 |
| 后台批量生成 100 封邮件回复 | generation | **batch** | 没人盯着 |
| 用户问"这 bug 怎么修？" | reasoning | **interactive** | 用户在等 |
| 离线批量总结 200 篇文章 | summarization | **batch** | 后台任务 |

**在优化框架下**：priority = interactive 对应目标函数里加一项 $-\alpha \cdot \text{TTFT}_i$ 或 SLO 硬约束。Preemption 就是这个约束的执行机制。

---

## 10. Workload：把实验变成可对比的"输入"

**Workload 是"一批需要处理的 Turn 的清单"**，模拟一段时间内系统收到的所有 LLM 调用。

简化示例：

```json
{
  "workload_id": "rq2_mixed",
  "budget_usd": 5.0,
  "turns": [
    { "turn_id": "t001", "at_ms": 0,   "priority": "interactive", "task_type": "reasoning",      "difficulty_weight": 3.0 },
    { "turn_id": "t002", "at_ms": 50,  "priority": "batch",       "task_type": "transform",      "difficulty_weight": 1.0 },
    { "turn_id": "t003", "at_ms": 100, "priority": "interactive", "task_type": "generation",     "difficulty_weight": 3.0 },
    { "turn_id": "t004", "at_ms": 100, "priority": "batch",       "task_type": "summarization",  "difficulty_weight": 1.0 },
    { "turn_id": "t005", "at_ms": 200, "priority": "batch",       "task_type": "retrieval",      "difficulty_weight": 1.0 }
  ]
}
```

字段说明：
- `at_ms`：到达时间（模拟请求非同时到）
- `priority`：interactive / batch（决定 SLO 约束强度）
- `task_type`：决定质量及格线与后端候选集
- **`difficulty_weight`**：对应优化问题里的 $w_i$，标识"这个 turn 多重要 / 多值得被推到高质量"

**workload 的 $w_i$ 设计应有现实依据**：可引用真实 agent 系统的阶段划分与阶段级成本统计（例如文献/开源实现中的阶段占比与成本 profile）来校准 turn mix 与 `difficulty_weight`，把预算优先留给高价值/高质量敏感阶段。（这里点到为止即可，避免喧宾夺主。）

仓库实现按 RQ 拆分 workload 文件（如 `paper1/workloads/rq1_mixed.json / rq2_mixed.json / rq3_zombie.json`）。

---

## 11. 为什么用 Mock，不调真模型

要回答"不同的调度策略效果差多少"，需要**公平比较**。调真 LLM 的问题：

1. 每次延迟波动，无法公平比较
2. 花真钱，跑 100 次就破产
3. 同输入不同输出，结果不可复现

所以每个 Turn 有 `mock` 字段，预设"这个 Turn 在不同后端上会表现成什么样"：

```json
{
  "turn_id": "t001",
  "mock": {
    "gpt4":    { "input_tokens": 500, "output_tokens": 300, "latency_ms": 1200, "ttft_ms": 200, "error": "none", "quality_score": 0.90 },
    "llama7b": { "input_tokens": 500, "output_tokens": 280, "latency_ms":  450, "ttft_ms":  90, "error": "none", "quality_score": 0.65 }
  }
}
```

**`quality_score` 的两种来源**：

| 模式 | 来源 | 约束 |
|---|---|---|
| Mock 实验（主线） | `workload.mock.quality_score` 预设 | 同 workload + 同 backend → 同分数 |
| 真实实验 | 按 `task_type` 调用确定性 grader | 纯函数，同输入同输出 → 同分数 |

Grader 注册表（每 task_type 对应一个 `(prompt, output) → float` 纯函数）：

| task_type | grader | 返回 |
|---|---|---|
| `generation` | 编译/执行通过 ×0.5 + 测试通过率 ×0.5 | 0–1.0 |
| `reasoning` | 答案精确匹配 / 逻辑链校验 | 0–1.0 |
| `retrieval` | 含期望答案子串 | 1.0 / 0.0 |
| `transform` | `json.loads` 成功且含必需字段 | 1.0 / 0.0 |
| `summarization` | 必需小节/关键词齐全 | 0–1.0 |
| `conversation` | 相关性 + 格式正确性 | 0–1.0 |

**两种来源产出同一个 `quality_score ∈ [0,1]`**，`analyze.py` 不区分来源——这就是 §12 评估指标能在 mock 和真实实验上**一致计算**的基础。

---

## 6. 评估指标：质量-成本优化视角

传统 P99 / TTFT / 完成数 / 成本保留为**工程侧指标**；核心论证依赖三类**质量-成本复合指标**。

### 6.1 Quality-Weighted Completion Rate（QWCR）

不只看完成数量，还看"有效完成量"。令 turn $i$ 的终态质量为 $q_i \in [0,1]$（失败/回收记为 0）：

$$
\text{QWCR} = \frac{1}{N}\sum_{i=1}^{N} q_i
$$

**数字例子**：5 个 turn，质量 $[1.0, 0.8, 0.6, 0, 0.9]$（第 4 个失败）→ QWCR = 3.3 / 5 = **0.66**。

### 6.2 QW-Completed（质量加权完成数）

$$
\text{QW-Completed} = \sum_{i=1}^{N} q_i
$$

把整数"完成数"推广为"有效产出量"。上例 = **3.3**（≈ 做出了 3.3 个满分任务的产出）。

### 6.3 Quality per Dollar（`Q/$`）与 `WQ/$`

$$
\text{Q/\$} = \frac{\sum_i q_i}{\text{cost\_total\_usd}},\qquad \text{WQ/\$} = \frac{\sum_i w_i q_i}{\text{cost\_total\_usd}}
$$

**数字例子**：$\sum q_i = 330$、花费 55 美元 → `Q/$` = **6**（每 1 美元换到 6 单位有效质量产出）。

**防坑**：某 policy 因预算耗尽几乎没做事会使 `Q/$` 虚高——因此实验报告里**永远同时报告 QWCR 与 `Q/$`**。

### 6.4 质量-成本 Pareto

把核心图表从"完成率 / 成本"升级为：
- 横轴：`cost_total_usd`
- 纵轴：`QW-Completed` 或 `QWCR`
- 不同 policy 点云（均值 ± CI）+ Pareto frontier

这样审稿人容易接受两个 claim：
- **"同预算下质量更高"**
- **"同质量目标下成本更低"**

---

## 7. 实验在验证什么（三条 RQ 重写）

### RQ1：约束可控 → 让质量/成本指标可被稳定测量

**对应架构**：Governor 治理层。

**问题**：不加治理时 429 雪崩、失败率高——此时 `Q/$`、QWCR 根本没法稳定测量（分母都没了）。

**做法**：同 workload 跑 `raw` vs `governor_only`，比较 `error_429_rate / turn_completed / cost_total_usd`。

**主张**：Governor 是"让优化问题 well-defined"的**前提**。

### RQ2（核心贡献）：预算下的质量最大化

**对应架构**：Governor + ModelSelector。

**问题**：同预算下，能否通过"把贵模型留给高 $w_i$ 的 turn"最大化 QWCR / `WQ/$`？

**对照组（对应 §2.1 表）**：
- A. `always_expensive`（总是高质量，不管预算）
- B. `per_request_greedy`（逐请求贪心性价比，不看全局预算时序）
- C. `budget_aware_uniform`（全局预算感知，但 $w_i \equiv 1$）
- D. `agentos_no_preempt`（Governor + ModelSelector，使用 task_type / priority / difficulty_weight）

**核心图表**：质量-成本 Pareto（横轴 cost，纵轴 QW-Completed）；**D 应当在 Pareto frontier 上或更靠右下**。

**消融**：关闭 $w_i$（令所有权重=1）应当退化到接近 C——证明 **$w_i$ 信号是有效的**。

### RQ3：剔除无效成本 → 满足 SLO + 提升 `Q/$`

**对应架构**：Preemption + ZombieDetector。

**问题**：
- 交互 SLO：并发槽被 batch 占满时，interactive TTFT P99 爆炸
- 尾部拖累：5 个异常慢 turn 拖累整体吞吐
- 僵尸燃烧：20% 僵尸注入烧掉预算却零质量收益

**做法**：固定 `Governor + ModelSelector`，切换 `agentos_no_preempt` vs `agentos`。

**核心指标**：interactive TTFT P99（SLO）+ **`Q/$` 提升**（僵尸剔除带来）+ QWCR（整体）。

**主张**：动态回收不是"让系统更快"，而是**从目标函数里剔除无效成本项 + 满足 SLO 约束**。

---

## 8. AgentOS 怎么解决这些问题（架构一句话版）

系统分两层：

**治理层（Governor）**——保证优化问题 well-defined 的**硬约束**：
- 预算不能超支（Budget）
- API 不能超速（RateLimit）
- 并发不能超槽（Admission）

**调度层（Scheduler）**——在约束内**求解质量最大化**：
- 谁先跑？（PriorityQueue：interactive 的 SLO 约束优先）
- **推到多高质量？**（ModelSelector：边际加权性价比 + budget_factor 影子价格）
- 调用卡住怎么办？（Timeout + Failover）
- 卡死了怎么办？（ZombieDetector：从目标函数剔除无效成本）
- 怎么让用户少等？（Preemption：SLO 违约时从 batch 抢回资源）

### 8.1 用一个场景把五件事串起来（精简版）

假设同一平台同时跑两类任务：
- **Interactive**：用户在等，要求 10 秒内返回
- **Batch**：后台任务，不急

队列里有 3 个 interactive 和 100 个 batch，GPU/API 资源固定。一个请求从进入系统到结束，依次经过五个决策点：

- **PriorityQueue（谁先跑）**：按“离 SLO 截止还剩多少时间”排序；快到期的先出队，不是固定把 batch 永远放后面。
- **Preemption（资源不够怎么办）**：如果没有空并发槽但 interactive 预计会超时，就暂停/取消一部分 batch 释放槽位，让 interactive 先开始执行。
- **ModelSelector（推到多高质量）**：在可用后端集合里选质量档位，核心信号是任务权重 $w_i$、成本-质量权衡 $c_i(\cdot)$ 与全局预算乘子 $\lambda$（`budget_factor` 的在线估计）。预算紧时提高 $\lambda$，同一任务会被分配到更便宜的档位。
- **Timeout + Failover（调用卡住怎么办）**：首字/空闲/总时长超时触发后，先中止当前后端，再切到备用后端重试，尽量不把临时故障暴露给上层。
- **ZombieDetector（长期无进展怎么办）**：如果成本持续增加但质量信号长期不提升，判定为僵尸并止损回收，返回当前最佳可用结果。

**抢占的语义存档**：不是保存寄存器，而是保存 prompt + 已生成部分输出。恢复时拼回 prompt 继续生成，**避免"抢占 = 浪费已生成内容"的反效果**。

两层分离的意义：即使调度策略写错了，治理层仍在兜底——预算不超支、API 不被打爆、优化问题仍 well-defined。

---

## 9. 调用卡住时的自救（超时 + 自动切换 + 熔断）

在优化视角下，"卡住的调用" = **成本在涨、质量不涨**（边际收益 ≈ 0）——必须截断。

**三段超时**：
- **首字超时（first token timeout）**：N 秒无首字
- **空闲超时（idle timeout）**：流式输出 M 秒无新 token
- **总时长超时（deadline timeout）**：整次超过 T 秒

**触发后四步**：
1. 取消当前请求，释放并发槽
2. 记录事件（哪个模型、哪种超时、已耗时）
3. 按预设链路切换模型重试（主 → 备用云 → 本地快模型）
4. 仍失败则快速返回可读错误

**小熔断**：某模型短窗口内连续超时超阈值 → 临时熔断（如 30s）→ 熔断到点半开一次 → 成功恢复/失败续熔断。

**评估指标**：超时率、自动切换率、interactive TTFT/P99、**`Q/$` 提升（截断带来的无效成本下降）**。

---

## 10. 实验的输出长什么样

每次实验（workload + policy = 一次 run）至少产出两个文件：

**`events.jsonl`**——流水账（每个 Turn 的 created / admitted / queued / dispatched / executing / completed / failed / reaped 全部可追溯）

**`summary.json`**（带行内注释版）：

```jsonc
{
  "turn_total": 50,           // 创建的 Turn 总数
  "turn_completed": 45,       // 成功完成
  "turn_failed": 3,           // 失败（429 / timeout / 5xx）
  "turn_reaped": 2,           // 僵尸回收
  "cost_total_usd": 0.87,     // 实际总花费
  "ttft_p99_ms": 1420,        // Interactive TTFT P99（SLO 指标）
  "error_429_rate": 0.02,     // 429 占比（RQ1）

  // ==== 路线四新增的核心指标 ====
  "qwcr": 0.78,               // Quality-Weighted Completion Rate（§12.1）
  "qw_completed": 39.0,       // 质量加权完成数（§12.2）
  "quality_per_dollar": 44.8, // Q/$（§12.3）
  "w_quality_per_dollar": 62.1, // WQ/$（加权版，§12.3）
  "pareto_point": [0.87, 39.0]  // (cost, qw_completed) for Pareto 图
}
```

> 注：上面是 `jsonc`，真实落盘不含注释。

额外落盘 `config_snapshot/`（workload / policy / backends 配置快照）保证**可复现**：同输入同配置 → 同结果。

论文图表全部从这些数据画出来。

---

## 11. 写法建议：三段式结构

给自己定一个不走极端的叙事节奏：

- **问题定义段（主文）**：给出连续质量模型与优化问题形式化，强调**设计原则（边际加权性价比水位线）为直觉，不强求完整定理**
- **系统段（主文）**：说明 AgentOS 启发式如何对应在线近似（`budget_factor` ≈ 预算影子价格 $\lambda$ 的在线估计；quality threshold ≈ 水位阈值）
- **实证段（RQ2/RQ3）**：用 QWCR、`Q/$`、Pareto frontier 证明"我们确实更接近这种最优结构"，而不是只靠类比

**摘要草稿（一句话版）**：

> 我们将 LLM 调用治理表述为一个 **budget-constrained quality maximization** 问题；系统机制（Governor / Preemption / ZombieDetector）保证约束成立，路由策略（ModelSelector）实现边际加权性价比导向的在线近似，并在真实 workload 上达成更好的质量-成本 Pareto。

---

## 12. 概念关系图

```
用户请求
  │
  ▼
Agent Session
  │  每次 LLM 调用 = 一个 Turn
  ▼
Turn  ──────────────────────────────────────────────────────
  │  属性：                                                  │
  │   - priority（interactive/batch）→ SLO 约束               │
  │   - task_type → 质量及格线 & 后端候选集                   │
  │   - difficulty_weight w_i → 优化目标里的任务价值权重       │
  │   - 成本 c_i、质量 q_i（连续 [0,1]）                      │
  ───────────────────────────────────────────────────────────
  │
  ▼
Workload（turns 清单 + 预算 B + mock 表现）
  │
  │  workload + policy = run
  ▼
Run  →  events.jsonl + summary.json（QWCR / `Q/$` / Pareto）
  │
  │  多 policy 对比
  ▼
Pareto Frontier → RQ1–RQ3 的答案
```

---

## 13. 术语速查（按认知顺序）

| 术语 | 一句话 |
|---|---|
| **LLM** | 大语言模型 |
| **Token** | LLM 处理文本的最小单位；按 token 收费 |
| **Agent** | 自主循环调用 LLM 的程序 |
| **Turn** | 一次完整的 LLM 调用；调度和计费的基本单位 |
| **Interactive / Batch** | 有无用户在等；决定 SLO 约束强度 |
| **Task Type** | generation / reasoning / retrieval / transform / summarization / conversation |
| **Quality Score $q_i$** | Turn 的输出质量，$[0,1]$ 连续——**本文核心变量** |
| **Difficulty Weight $w_i$** | Turn 的任务价值权重（优化目标里的系数）|
| **Budget $B$** | 本次 run 的总预算（美元） |
| **Workload** | 实验脚本；公平对比不同策略的输入 |
| **Mock** | workload 里预设的延迟/成本/质量/错误；保证可复现 |
| **Policy** | 一套调度策略（如 `raw` / `governor_only` / `agentos_no_preempt` / `agentos`） |
| **Run** | workload + policy = 一次实验运行 |
| **429** | API 限流错误 |
| **TTFT** | Time To First Token；interactive 的 SLO 指标 |
| **P99** | 第 99 百分位；最差 1% 体验 |
| **QWCR** | Quality-Weighted Completion Rate（本文核心指标） |
| **QW-Completed** | $\sum q_i$；质量加权完成数 |
| **`Q/$`, `WQ/$`** | 每美元的（加权）质量产出 |
| **Budget Factor** | 预算影子价格 $\lambda$ 的在线估计；驱动质量门槛动态调整 |
| **Shadow Price $\lambda$** | 对应"预算的边际价值"；最优性的隐式水位线变量 |
| **Marginal Cost-Benefit $w_i \Delta q_i / \Delta c_i$** | ModelSelector 的排序原则 |
| **Governor** | 治理层；保证优化问题 well-defined 的硬约束 |
| **Scheduler** | 调度层；在约束内近似求解质量最大化 |
| **ModelSelector** | 在线近似边际加权性价比排序的选模器 |
| **Preemption** | 抢占；对 interactive SLO 约束的执行机制 |
| **Zombie** | 成本涨、质量不涨（边际收益 ≈ 0）的 Turn；从目标函数剔除 |
| **First / Idle / Deadline Timeout** | 三段超时 |
| **Failover / Circuit Breaker** | 故障切换 / 熔断 |
| **Pareto Frontier** | 质量-成本平面上的最优前沿；论文核心图 |

---

---

## 附录 A：审稿人常见质疑（简版回答）

- **“你只是预算控制做得好。”**  
  用 RQ2 对照组 C（全局预算感知但 $w_i \equiv 1$）排除该解释：若 D 显著优于 C，差异来自“任务价值感知”而非单纯控预算。

- **“$q$ 和 $w$ 怎么来？拍脑袋吗？”**  
  $q$ 来自 mock 预设或确定性 grader（同输入同输出 → 同分数）；$w$ 来自 workload 的显式信号（`difficulty_weight`/priority），并应有现实依据进行校准（阶段占比、成本 profile 等）。

- **“这套东西在小规模有意义吗？”**  
  有。即使只有 1 个 agent，“这个 turn 该推到多好”仍然是核心决策；预算约束下的质量分配依然存在。