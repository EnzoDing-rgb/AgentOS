# BudgetFlow: 面向Agent工作流的动态预算路由机制
## 论文大纲

---

## 1. 论文主线

在一个甚至多个完整的 agent workflow（每个 workflow 包含多步 LLM 调用）中，如何利用 workflow 级的结构信息（哪一步关键、剩多少预算、多个 workflow 怎么共享资源），做整体的成本-质量分配？

本文的研究问题是：当优化单位从"一次 LLM 请求"变成"一个完整 agent workflow"，并且多个 workflow 共享同一个预算池和多条后端路径的 RPM / 并发配额时，显式维护 workflow 状态是否会改变固定预算下的最终成功率？ 如果答案是肯定的，再进一步问：这个收益来自预算配速、步骤重要性、进展先验，还是多 workflow 调度？把 agent workflow 的 LLM 花费变成一个可审计、可消融、可复现实验的问题。

---

## 2. 本文的核心贡献

1. **连续质量视角**：将 LLM 质量视为 [0,1] 连续变量
2. **预算硬约束 + 动态配速**：`budget_factor` 近似预算边际价值 λ
3. **显式任务价值 wi**：调用方声明的可解释信号
4. **僵尸止损**：截断"成本涨、质量不涨"的无效调用
5. **无需训练**：优化启发式，即时部署，对比 RL 方法更轻量

---

## 3. 项目架构

```
Plain Text
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

- 操作系统资源管理：AgentRM, AgentCgroup, AIOS, pMVX
- 任务-模型路由：RouteLLM, CARROT, OmniRouter
- 分步骤强化学习的模型路由策略：BoPo
- GPU资源预算控制：Athena-Serve
- 硬件资源编排：Murakkab

---

## 5. 相关工作汇总对比表

| 论文 | 类型 | 方法 | 预算约束 | Multistep | 与本文关系 |
|------|------|------|----------|-----------|------------|
| 本文 | 优化启发式 | 边际加权性价比+budget_factor配速 | Hard budget | 有 | - |
| Budget-Aware Agentic Routing (BoPO, Zhang et al. 2026, arxiv:2602.21227) | RL (sequential) | Training+ BoPO | Hard + Soft | 有 | 最直接竞争者: RL vs启发式 |
| OmniRouter (Mei et al. 2026) | 约束优化 | Hybrid predictor + Lagrangian optimizer | 有(Lagrangian dual) | 无(独立query) | 全局约束优化但per-query |
| xRouter (2025, arxiv:2510.08439) | RL | Cost-aware reward | 有(episode) | 有 | RL方法论对手 |
| CARROT (Somerstep et al. 2025, arxiv:2502.03261) | 统计 | Minimax optimal plug-in router | Per-query cost预测 | 无 | baseline |
| RouteLLM (Ong et al.2024) | 学习型二元 | strong/weak二分 | 偏好数据训练 | 无 | baseline |
| pMVX: Policy-Level Multi-Version Execution for Agentic OS Kernel Self-Tuning (Agentic OS Workshop 2026, accepted) | Agentic OS/内核 | 多版本策略执行+kernel policy self-tuning | 无(非workflow路由) | 无 | 平行工作:偏kernel自调优,不是质量-成本分配 |
| AgentRM (arxiv:2603.13110) | OS-inspired | MLFQ+僵尸回收+上下文管理 | 并发槽/RPM | 无 | 平行工作:侧重稳定性 |
| AgentCgroup (arxiv:2602.09345) | OS内核级 | eBPF+ cgroup | CPU/内存 | 无 | 平行工作:OS级资源 |
| AIOS (arxiv:2403.16971) | OS架构 | 内核服务抽象 | 无 | 无 | 概念相似但更宽泛 |

---

## 6. 关键差异分析

### 6.1 本文 vs Budget-Aware Agentic Routing (BoPO) - 最重要的对比

| 维度 | 本文 | Budget-Aware Agentic Routing (BoPO) |
|------|------|-------------------------------------|
| 方法 | 优化启发式:无需训练,即时部署 | RL(BoPO):需要训练数据和GPU训练 |
| 可解释性 | 边际性价比排序+budget_factor,完全可解释 | RL策略难以解释 |
| 预算处理 | 运行时hard budget硬约束 | 训练时soft-budget+推理时BCD |
| 任务价值 | 显式(调用方声明) | 隐式(RL学出) |
| 止损 | ZombieDetector截断无效调用 | 无专门机制 |
| 互补性 | - | 本文启发式可作为RL warm-start baseline |

### 6.2 本文 vs Per-query Routers (RouteLLM, CARROT, OmniRouter)

| 维度 | 本文 | Per-query Routers |
|------|------|-------------------|
| 决策 | 跨N步联合预算约束 | 每条query独立最优 |
| 状态 | 有状态(跟踪预算/burn rate) | 无状态 |
| 预算 | Hard budget 硬约束 | 不管或仅预测per-query cost |
| 任务价值 | 显式Wi | 不区分 |

### 6.3 本文 vs OS-Inspired工作 (AgentRM, AgentCgroup, AIOS, pMVX)

| 维度 | OS-Inspired工作 | 本文 |
|------|----------------|------|
| 核心问题 | 系统稳定性/资源隔离 | 质量-成本优化 |
| 优化目标 | 延迟/吞吐量/隔离 | QWCR, Q/$, Pareto |
| 资源类型 | CPU/内存/并发槽/RPM | LLM调用质量与成本 |

---

## 7. 和本文最接近的论文：BoPO

> 注：完整电子表格内容请参考原文档附件

---

## 8. 论文边界

> 注：完整电子表格内容请参考原文档附件

---

## 9. 叙事：参照vLLM

vLLM 是 UC Berkeley 于 2023 年发布的开源 LLM 推理引擎（SOSP 2023）。其第一篇论文处理的是 single-tenant 问题：给定一台 GPU 服务器收到多个独立推理请求，引擎应如何 batch 与调度以最大化吞吐？该工作假设硬件由单一运营方拥有，未对竞争用户之间的策略仲裁做任何主张。后续工作——包括 Andes（OSDI 2024）、SGLang router 等——把这一基础扩展到 multi-tenant 设定：多个用户、团队或服务共享同一推理基础设施，系统在 priority、quota、SLA 约束下做仲裁。

这种"先优化单决策主体、再引入多决策主体仲裁"的两阶段演进，是 systems 社区的成熟研究路径。第一阶段建立核心机制（在 vLLM 的例子中是 paged KV-cache 与 continuous batching）；第二阶段在 single-tenant 案例被充分理解之后，在该机制之上叠加政策层。

BudgetFlow 走同样的路径。本文（paper 1）处理 single-budget-owner 情形：一个实体持有固定的算力 / token 预算，在其上运行多个 agent workflow；本文的贡献是构建在该预算之上做跨 workflow 分配的 cost-model-agnostic scheduler。

自然的续作是 multi-tenant agent compute resource allocation：多个团队、部门或外部客户各自持有独立预算、优先级与 SLA，共享同一个 agent 执行底层。这一设定引入新的问题——cross-tenant 隔离、异构 workload 混合下的 quota 仲裁、budget-aware admission control——超出本文 scope，但都是本文框架的直接扩展。

重要的是，本文 scheduler 的 cost-model-agnostic 性质在 multi-tenant 扩展中得以保留：租户可以使用不同的底层模型与成本结构，无需修改仲裁层。

我们因此把本文定位为：multi-tenant workflows 工作可以在其上构建的 single-tenant 基础。

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

---
