# Agent OS 论文对比分析（更新于 2026-04-27）

## 完整对比表格

| 论文 | 类型 | 预算约束 | Multi-step | 方法 | 与本文关系 |
|------|------|---------|-----------|------|-----------|
| **本文** | 优化启发式 | Hard budget | 有 | 边际加权性价比 + budget_factor 配速 | — |
| **Budget-Aware Agentic Routing** (Zhang et al. 2026, arxiv:2602.21227) | RL (BoPO) | Hard + Soft | 有（sequential） | Boundary-Guided Training + BoPO | **最直接竞争者**：RL vs 启发式 |
| **OmniRouter** (Mei et al. 2026) | 约束优化 | 有（Lagrangian dual） | 无（独立 query） | Hybrid predictor + Lagrangian optimizer | 全局约束优化但 per-query |
| **xRouter** (2025, arxiv:2510.08439) | RL | Cost-aware reward | 有（episode） | Tool-calling RL router | RL 方法论对手 |
| **CARROT** (Somerstep et al. 2025, arxiv:2502.03261) | 统计 | Per-query cost 预测 | 无 | Minimax optimal plug-in router | Per-query baseline |
| **RouteLLM** (Ong et al. 2024) | 学习型二元 | 无 | 无 | 偏好数据训练 strong/weak 二分 | Per-query baseline |
| **pMVX: Policy-Level Multi-Version Execution for Agentic OS Kernel Self-Tuning** (Agentic OS Workshop 2026, accepted) | Agentic OS / 内核自调优 | 未见明确 budget 优化目标 | 无（非 workflow 路由） | 多版本策略执行 + kernel policy self-tuning | 平行工作：偏 kernel 自调优，不是质量-成本分配 |
| **AgentRM** (arxiv:2603.13110) | OS-inspired | 并发槽/RPM | 无 | MLFQ + 僵尸回收 + 上下文管理 | 平行工作：侧重稳定性 |
| **AgentCgroup** (arxiv:2602.09345) | OS 内核级 | CPU/内存 | 无 | eBPF + cgroup | 平行工作：OS 级资源 |
| **AIOS** (arxiv:2403.16971) | OS 架构 | 无 | 无 | 内核服务抽象 | 概念相似但更宽泛 |

## 关键差异分析

### 1. 本文 vs Budget-Aware Agentic Routing（最重要的对比）

| 维度 | Budget-Aware Agentic Routing | 本文 |
|------|----------------------------|------|
| **方法** | RL (BoPO)：需要训练数据和 GPU 训练 | 优化启发式：无需训练，即时部署 |
| **可解释性** | RL 策略难以解释 | 边际性价比排序 + budget_factor，完全可解释 |
| **预算处理** | 训练时 soft-budget + 推理时 BCD | 运行时 hard budget 硬约束 |
| **任务价值** | 隐式（RL 学出） | 显式 $w_i$（调用方声明） |
| **止损** | 无专门机制 | ZombieDetector 截断无效调用 |
| **互补性** | 本文启发式可作为 RL warm-start baseline | — |

### 2. 本文 vs Per-query Routers (RouteLLM, CARROT, OmniRouter)

| 维度 | Per-query Routers | 本文 |
|------|-------------------|------|
| **决策** | 每条 query 独立最优 | 跨 N 步联合预算约束 |
| **状态** | 无状态 | 有状态（跟踪预算 / burn rate） |
| **预算** | 不管或仅预测 per-query cost | Hard budget 硬约束 |
| **任务价值** | 不区分 | 显式 $w_i$ |

### 3. 本文 vs OS-Inspired 工作 (AgentRM, AgentCgroup, AIOS, pMVX)

| 维度 | OS-Inspired 工作 | 本文 |
|------|-----------------|------|
| **核心问题** | 系统稳定性/资源隔离 | 质量-成本优化 |
| **优化目标** | 延迟/吞吐量/隔离 | QWCR, Q/\$, Pareto |
| **资源类型** | CPU/内存/并发槽/RPM | LLM 调用质量与成本 |

## 本文的独特贡献

1. **连续质量视角**：将 LLM 质量视为 $[0,1]$ 连续变量
2. **预算硬约束 + 动态配速**：budget_factor 近似预算边际价值 $\lambda$
3. **显式任务价值 $w_i$**：调用方声明的可解释信号
4. **僵尸止损**：截断"成本涨、质量不涨"的无效调用
5. **无需训练**：优化启发式，即时部署，对比 RL 方法更轻量

## 定位总结

| 研究类别 | 代表工作 | 关注点 |
|----------|---------|--------|
| **Per-query routing** | RouteLLM, CARROT, OmniRouter | 单条 query 选模型 |
| **Agentic routing (RL)** | Budget-Aware Agentic Routing, xRouter | 学习型多步路由 |
| **OS 资源管理** | AgentRM, AgentCgroup, AIOS, pMVX | 系统稳定性/资源隔离/内核自调优 |
| **Budget-constrained quality optimization（本文）** | AgentOS Paper 1 | **启发式**多步质量-成本优化 |

本文的 niche：**不需要训练的、可解释的、基于优化原理的 budget-aware multi-step routing**。与 RL 方法互补，与 per-query router 正交。
