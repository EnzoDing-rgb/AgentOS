# BudgetFlow: 面向Agent工作流的动态预算路由机制

## 论文大纲

---

## 1. 论文主线

- 在一个甚至多个完整的 agent workflow（每个 workflow 包含多步 LLM 调用）中，如何利用 workflow 级的结构信息（哪一步关键、剩多少预算、多个 workflow 怎么共享资源），做整体的成本-质量分配？
- 本文的研究问题是：当优化单位从「一次 LLM 请求」变成「一个完整 agent workflow」，并且多个 workflow 共享同一个预算池和多条后端路径的 RPM / 并发配额时，显式维护 workflow 状态是否会改变固定预算下的最终成功率？若肯定，再问：收益来自预算配速、步骤重要性、进展先验，还是多 workflow 调度？把 agent workflow 的 LLM 花费变成一个可审计、可消融、可复现实验的问题。

---

## 2. 本文的三个研究问题与独特贡献

### 2.1 三个研究问题

| RQ | 问题 | 主要指标 |
| :--- | :--- | :--- |
| **RQ1** | 多 workflow 在同一固定预算与共享后端限流下并行运行时，预算浪费在何处、哪些运行时限制最先成为瓶颈？ | 预算违规率、429 率、队列延迟、回收预算、僵尸取消数等 |
| **RQ2** | 在相同预算下，利用 workflow 阶段状态做多步模型档位选择，是否比「仅按 workflow」或「仅按预算」的调度 resolve 更多 SWE-bench 类任务？ | 固定预算下 resolved rate；BudgetFlow Full vs Workflow-Level Router vs Budget-Only Step Scheduler |
| **RQ3** | 当换模型削弱 prefix-cache 局部性时，workflow 阶段调度是否仍能带来净收益？ | 换模频率、prefill 延迟、cached-token 比例；BudgetFlow Full vs BudgetFlow Cache-Sticky |

### 2.2 独特贡献

1. **连续质量视角**：将 LLM 质量视为 [0,1] 连续变量
2. **预算硬约束 + 动态配速**：`budget_factor` 近似预算边际价值 λ
3. **显式任务价值 wi**：调用方声明的可解释信号
4. **僵尸止损**：截断「成本涨、质量不涨」的无效调用
5. **无需训练**：优化启发式，即时部署，对比 RL 方法更轻量

---

## 3. 项目架构

```
Agent Workflow（N 个 LLM 调用步骤）× J 个并发 workflow
        │
        ▼
═══════════════════ BudgetFlow ═══════════════════
│ 【约束层】Governor                           │  ← policy-agnostic
│   预算预留/结算 + 后端级限流 + 并发准入       │
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

---

## 4. 相关工作分类

（与 **§5** 一览表同一批工作；§5 第一列为下列聚类标签。）

- 操作系统资源管理：AgentRM, AgentCgroup, AIOS, pMVX
- 任务-模型路由：RouteLLM, CARROT, OmniRouter
- 分步骤强化学习的模型路由策略：BoPo（**同类**多步 RL / 工具编排路由：xRouter）
- GPU资源预算控制：Athena-Serve
- 硬件资源编排：Murakkab

---

## 5. 相关工作一览（§4 聚类 + 符号）

下表 **「§4 聚类」列** 与 **§4** 五条索引一一对应；**未在 §4 列名中出现的工作不入表**（Aragog、Parrot 等推理栈仅见 **Appendix A.2**）。

**①～③**：**①** 多并发 agent WF 共享 **$ / token 硬顶** + 预留–结算；**②** **同一条** agent 轨迹上多轮 LLM **状态化**选档；**③** **无任务域**大规模离线训练 / RL 即可跑（仅有小表标定仍记 ✓）。**④** 一句话差分。

| §4 聚类 | 工作 | ① | ② | ③ | ④ 与本文 |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **（本文）** | **BudgetFlow** | ✓ | ✓ | ✓ | — |
| 操作系统资源管理 | **AgentRM** (arxiv:2603.13110) | ✗ | ✗ | ✓ | RPM / 稳定 / 回收；非 API **$** 硬账本 |
| 操作系统资源管理 | **AgentCgroup** (arxiv:2602.09345) | ✗ | ✗ | ✓ | 主机 CPU / Mem **cgroup** |
| 操作系统资源管理 | **AIOS** (arxiv:2403.16971) | ✗ | ✗ | ✓ | **Agent OS** 抽象 |
| 操作系统资源管理 | **pMVX** (Agentic OS Wkshp 2026) | ✗ | ✗ | ✗ | **Kernel** 多版本策略自调优 |
| 任务-模型路由 | **RouteLLM** (Ong et al. 2024) | ✗ | ✗ | ✗ | Strong / weak **偏好学习**；无运行预算账本 |
| 任务-模型路由 | **CARROT** (Somerstep et al. 2025, arxiv:2502.03261) | ✗ | ✗ | ✓ | **Per-query** minimax；无跨步联合状态 |
| 任务-模型路由 | **OmniRouter** (Mei et al. 2026) | ✗ | ✗ | ✗ | **Per-query** Lagrangian；非多 WF **池** |
| 分步骤强化学习的模型路由策略 | **BoPO** / Budget-Aware Agentic Routing (Zhang et al. 2026, arxiv:2602.21227) | ✗ | ✓ | ✗ | **单任务** RL step 路由；可插 **ModelSelector**；无 **①** |
| 分步骤强化学习的模型路由策略 | **xRouter** (arxiv:2510.08439；*Training Cost-Aware LLMs Orchestration via RL*) | ✗ | ✓ | ✗ | RL **工具 / 多模型编排**；非多 agent **共享池**账本 |
| GPU资源预算控制 | **ATHENA-Serve** (Liang & Wu；ICLR 2026 投稿，OpenReview #10330；Serving 侧 horizon–cost + 分层 RL) | ✗ | ✗ | ✗ | **Serving** 长尾延迟与 KV / 算力 **budget**；非 agent **计价** **①** |
| 硬件资源编排 | **Murakkab**（待投） | ✗ | ✗ | ✗ | **云 / WF** 级成本与并行；无 **$ / token 硬顶** 账本 |

**Murakkab**、**ATHENA-Serve** 等可与本文在工程上纵向叠放；表内仅收录 §4 已索引文献。

### 论文边界（本文 scope）

**本文明确覆盖**

- **单一预算主体（single budget owner）**：多个并发 workflow 共享一池预算与后端 RPM / 并发配额；账本、准入、结算、ZombieDetector、多 workflow 调度属于本文 runtime 命题。
- **决策单位**：workflow 内每一步 LLM 调用 + 全局预算池状态；评测常以 SWE-bench Verified 批量并发 + 固定总预算等为场景。

**本文不 Claim / 留作扩展**

- **Multi-tenant**：跨团队预算与 SLA — 自然续作，与 §8 vLLM 叙事第二阶段一致。
- **非 GPU serving 独占论文**：不取代 Athena-Serve / vLLM 侧的 **KV / batch** 全集最优；本文为 **workflow 花费治理与步骤配额**。
- **ZombieDetector**：运行时止损构件，可做消融；非独立 RL/ML 方法论主贡献。
- **成本模型**：不绑定具体 SKU；用抽象 dollar / token 计价即可复现结论。

---

## 6. 关键差异分析

以下为 **轴向对照**（BoPO / per-query router / OS-inspired）；**①②③** 与 §4 **聚类** 见 §5。

### 6.1 本文 vs Budget-Aware Agentic Routing（最重要的对比）

| 维度 | Budget-Aware Agentic Routing | **本文** |
| :--- | :--- | :--- |
| **方法** | RL（BoPO）：需要训练数据和 GPU 训练 | 优化启发式：无需训练，即时部署 |
| **可解释性** | RL 策略难以解释 | 边际性价比排序 + budget_factor，完全可解释 |
| **预算处理** | 训练时 soft-budget + 推理时 BCD | 运行时 hard budget 硬约束 |
| **任务价值** | 隐式（RL 学出） | 显式 $w_i$（调用方声明） |
| **止损** | 无专门机制 | ZombieDetector 截断无效调用 |
| **互补性** | 本文启发式可作为 RL warm-start baseline | — |

### 6.2 本文 vs Per-query Routers（RouteLLM, CARROT, OmniRouter）

| 维度 | Per-query Routers | **本文** |
| :--- | :--- | :--- |
| **决策** | 每条 query 独立最优 | 跨 N 步联合预算约束 |
| **状态** | 无状态 | 有状态（跟踪预算 / burn rate） |
| **预算** | 不管或仅预测 per-query cost | Hard budget 硬约束 |
| **任务价值** | 不区分 | 显式 $w_i$ |

### 6.3 本文 vs OS-Inspired 工作（AgentRM, AgentCgroup, AIOS, pMVX）

| 维度 | OS-Inspired 工作 | **本文** |
| :--- | :--- | :--- |
| **核心问题** | 系统稳定性 / 资源隔离 | 质量-成本优化 |
| **优化目标** | 延迟 / 吞吐量 / 隔离 | QWCR，Q/$，Pareto |
| **资源类型** | CPU / 内存 / 并发 / RPM | LLM 调用质量与成本 |

---

## 7. 和本文最接近的论文：BoPO

**Budget-Aware Agentic Routing via Boundary-Guided Training**（Zhang et al., arXiv:2602.21227，2026）。核心算法 **BoPO** = **Boundary-Guided Policy Optimization**，按 agent **step** 做 RL 路由；训练侧通常含 BoSFT，在线侧用 GRPO 等做边界引导，缓解稀疏奖励。

### 7.1 与本文的关系

BoPO 产出的是**单任务 step 级路由策略**，在 BudgetFlow 架构里对应 **ModelSelector 的一种可插拔实现**。本文贡献是**运行时治理底座**：全局账本（预留 / 结算）、硬预算与后端 RPM / 并发准入、多 workflow 调度、ZombieDetector 等。BoPO **脱离该底座**无法单独解决「多并发、共享**同一**全局预算与配额」下的系统级问题；反之，**底座与 BoPO 兼容**——可将 RL 策略接入 ModelSelector，由运行时继续保证全局硬约束并放大其决策。

### 7.2 极简场景（与 SWE-bench 类任务对齐）

单条修复轨迹：读 issue → 搜仓库 → 读文件 → 定根因 → 写补丁 → 跑测试 → 迭代；**单任务**预算如 `$0.5`，每步选强 / 弱模型。**BoPO**：在同域大量轨迹上预训练；执行时每步根据上下文、历史与**该任务剩余预算**输出档位；奖励绑定**该任务**成败与花费，边界引导在关键 step 鼓励用强模。**本文评测焦点**常为多实例并发（如共享 `$B_total`），决策在**全局待执行 call**上按加权边际进度、预算压力等在**系统级**择优，优化**汇总**完成率，而非仅单轨迹内部局部最优。

### 7.3 BudgetFlow vs BoPO（层级与能力）

| 维度 | BudgetFlow（本文） | BoPO（相关工作） |
| :--- | :--- | :--- |
| **优化目标（典型）** | 共享硬预算 + 后端配额下 **全局**任务完成率（或等价系统指标） | **单任务**内预算—成功率 trade-off，**单轨迹**意义下的局部最优 |
| **决策视野** | 全局账本 + **跨 workflow** 的就绪 / 排队集合 | 单 trajectory 状态 + **该任务**剩余预算 |
| **预算与配额** | 运行时 **预留—结算**、硬上限、429 / 并发准入 | 训练期 soft-budget + 推理 BCD 等（**非**本文级原子账本语义） |
| **止损与回收** | ZombieDetector、抢占、释放预留与槽位 | 无对等机制 |
| **部署** | Training-free，跨框架接入 | **域专属**轨迹与训练；换域重训成本高 |
| **重叠与组合** | Step 重要性驱动路由；**BoPO policy 可作 ModelSelector plug-in** | 仅解决 step 选模子问题；**不替代**全局治理层 |

### 7.4 BoPO 明确不覆盖（与本文差分）

- 多 agent **共享单一全局预算**时的跨任务分配与「前期耗光、后期饥饿」  
- 生产级 **RPM / 并发** 强准入与 429 治理  
- **僵尸 / 无进度** 任务占用的预算与槽位回收  
- **本地推理 / KV** 切换代价显式建模  
- **零域数据**下的免训练冷启动路由

---

## 8. 叙事：参照vLLM

- vLLM 是 UC Berkeley 于 2023 年发布的开源 LLM 推理引擎（SOSP 2023）。其第一篇论文处理的是 single-tenant 问题：给定一台 GPU 服务器收到多个独立推理请求，引擎应如何 batch 与调度以最大化吞吐？该工作假设硬件由单一运营方拥有，未对竞争用户之间的策略仲裁做任何主张。后续工作——包括 Andes（OSDI 2024）、SGLang router 等——把这一基础扩展到 multi-tenant 设定：多个用户、团队或服务共享同一推理基础设施，系统在 priority、quota、SLA 约束下做仲裁。
- 这种「先优化单决策主体、再引入多决策主体仲裁」的两阶段演进，是 systems 社区的成熟研究路径。第一阶段建立核心机制（在 vLLM 的例子中是 paged KV-cache 与 continuous batching）；第二阶段在 single-tenant 案例被充分理解之后，在该机制之上叠加政策层。
- BudgetFlow 走同样的路径。本文（paper 1）处理 single-budget-owner 情形：一个实体持有固定的算力 / token 预算，在其上运行多个 agent workflow；本文的贡献是构建在该预算之上做跨 workflow 分配的 cost-model-agnostic scheduler。
- 自然的续作是 multi-tenant agent compute resource allocation：多个团队、部门或外部客户各自持有独立预算、优先级与 SLA，共享同一个 agent 执行底层。这一设定引入新的问题——cross-tenant 隔离、异构 workload 混合下的 quota 仲裁、budget-aware admission control——超出本文 scope，但都是本文框架的直接扩展。
- 重要的是，本文 scheduler 的 cost-model-agnostic 性质在 multi-tenant 扩展中得以保留：租户可以使用不同的底层模型与成本结构，无需修改仲裁层。
- 我们因此把本文定位为：multi-tenant workflows 工作可以在其上构建的 single-tenant 基础。

---

## Appendix

### A.1 BudgetFlow 集成架构

```
+----------------------------------+       +-----------------------------+
| LangChain / SWE-agent / AutoGen  |       | Self-built agent platform   |
+----------------------------------+       +-----------------------------+
       |                    |                         |
       | Proxy mode:        | Callback mode:          | Explicit mode:
       | LLM request msgs   | tool events + metadata  | task_type + w_i
       v                    v                         v
+------------------+ +------------------+      +------------------+
|  BudgetFlow Proxy   | | BudgetFlow Adapter  |      |   BudgetFlow SDK    |
+------------------+ +------------------+      +------------------+
          \                  |                         /
           \                 |                        /
            +----------------+-----------------------+
                             |
                             v
                    +--------------------+
                    |  BudgetFlow Runtime   |
                    +--------------------+
                             |
                             v
          +-------------------------------------+
          | Governor: budget + backend quotas |
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

### A.2 Agent 计算栈分层对比

```
+-----------------------------------------------------------------------------+
|                               Murakkab (Top Layer)                          |
|  全栈SLO编排：整个agent工作流怎么全局优化硬件成本，保证按时完成任务          |
+-----------------------------------------------------------------------------+
|  核心问题：云怎么用最少的GPU跑所有agent | 优化目标：最小化云的硬件成本       |
|  决策单位：整个工作流                   | 预算约束：❌ 只优化单位成本，无硬上限 |
+-----------------------------------------------------------------------------+
                                      ↓
+-----------------------------------------------------------------------------+
|                              BudgetFlow (Upper Layer)                        |
|  全局预算控制：给你固定100块钱，怎么花能解最多的bug，不超支也不浪费          |
+-----------------------------------------------------------------------------+
|  核心问题：用户怎么用固定的钱完成最多任务 | 优化目标：固定预算下最大化成功率   |
|  决策单位：单个步骤 + 全局预算池         | 预算约束：✅ 核心就是硬预算上限     |
+-----------------------------------------------------------------------------+
                                      ↓
+-----------------------------------------------------------------------------+
|                               Aragog (Middle Layer)                         |
|  动态模型路由：每个步骤用哪个模型能最快跑完，不浪费空闲GPU                  |
+-----------------------------------------------------------------------------+
|  核心问题：怎么让GPU一直忙，不闲着        | 优化目标：最大化系统吞吐量         |
|  决策单位：单个步骤                     | 预算约束：❌ 只要GPU闲着就用，不管多贵 |
+-----------------------------------------------------------------------------+
                                      ↓
+-----------------------------------------------------------------------------+
|                               Parrot (Bottom Layer)                         |
|  多轮请求流水线：同一个agent的多轮对话怎么跑更快，减少等待时间              |
+-----------------------------------------------------------------------------+
|  核心问题：单轮请求怎么跑更快            | 优化目标：最小化单请求延迟         |
|  决策单位：单请求内部的token流           | 预算约束：❌ 完全不考虑钱           |
+-----------------------------------------------------------------------------+
                                      ↓
+-----------------------------------------------------------------------------+
|                          LLM Backends + GPU/CPU Hardware                    |
+-----------------------------------------------------------------------------+
```
