# Related Work: Budget-Aware Model Routing for LLM Agents

> Phase 2 文献综述。锚点：共享硬预算下最大化已验证任务价值（Yield）。
> 初稿，待 Phase 5 评审与范文校准。

---

## 1. LLM Cascading and Model Routing

The dominant paradigm for cost-efficient LLM deployment is **cascade routing**: send a query to a cheap model first, escalate to a strong model only when necessary.

**FrugalGPT** (Chen et al., 2023) established the foundational cascade strategy. It queries LLMs in order from cheapest to most expensive, using a DistilBERT-based scoring model to evaluate answer quality and decide when to stop. The paper demonstrated up to 98% cost reduction while matching GPT-4 performance on benchmark tasks. Its three strategies — prompt adaptation, LLM approximation via caching, and LLM cascade — remain the reference architecture for subsequent routing work.

**RouteLLM** (Ong et al., 2024) replaced FrugalGPT's scoring model with a BERT-style classifier trained on human preference data to predict which model best handles each query. **HybridLLM** (Ding et al., 2024) routes based on predicted performance gaps between small and large models. **AutoMix** (Aggarwal et al., 2024) introduced self-verification into the cascade loop, using the model's own confidence signals rather than an auxiliary scorer.

These cascade routers share a common limitation: they operate **per-query**. Each query is an independent cost-accuracy tradeoff. They do not allocate one shared budget across a batch of tasks, track cumulative spending, or prioritize high-value tasks when budget is scarce.

**RouteNLP** (Guo et al., 2026) moves closer to deployment-level routing with a closed-loop framework that integrates conformal cascading and distillation co-optimization. In an 8-week enterprise deployment processing ~5K queries/day, RouteNLP reduced inference costs by 58% while maintaining 91% response acceptance. It introduces per-task quality sensitivity parameters and a global cost-sensitivity tradeoff. However, RouteNLP still routes each query independently — its budget-based routing mode uses dynamic programming to maximize quality under a fixed per-workflow cost cap, not a shared hard budget that depletes across an ordered task sequence.

---

## 2. Calibrated Uncertainty for Cascade Routing (UCCI)

**UCCI** (Kotte, 2026) addresses a specific weakness in cascade routers: uncalibrated confidence scores that require per-workload threshold tuning. UCCI maps token-level margin uncertainty to per-query error probabilities via isotonic regression, then selects escalation thresholds through constrained cost minimization. Under explicit assumptions, threshold policies on calibrated scores are provably cost-optimal, with $O(n^{-1/3})$ sample complexity for expected calibration error (ECE).

On a production NER workload of 75K queries served by 4B and 12B models on H100 GPUs, UCCI cut inference cost by 31% (95% CI: [27%, 35%]) at micro-F1 = 0.91 while reducing ECE from 0.12 to 0.03. All results use end-to-end routing on actual model outputs and measured H100 latency.

UCCI demonstrates that calibrated model confidence can drive cost-effective escalation decisions. However, it remains a per-query cascade: it does not manage a shared budget, does not track cumulative value across tasks, and does not face the allocation problem of depleting a hard cap across a fixed task batch.

---

## 3. Inference-Time Budget Control

A parallel literature controls compute budgets **within** a single model call, reasoning trace, or agent run, rather than routing across models. These systems enforce per-example constraints: a run that exceeds its budget is treated as a failure.

### 3.1 Token-Level Reasoning Budgets

**Predictive Scheduling** (Brown et al., ICML 2025) uses lightweight MLP probes on transformer hidden states to predict each query's optimal reasoning length before generation begins. A greedy batch allocator distributes a fixed total token budget to maximize expected accuracy, achieving +7.9pp on GSM8K at identical cost vs. uniform allocation. The key insight — that middle layers carry predictive signal for task difficulty — informs cost estimation before committing compute.

**e1: Adaptive Effort Control** (Kleinman et al., 2025) uses RL to train models that follow a user-specified effort fraction $r \in [0,1]$ relative to average chain-of-thought length, achieving 2--3$\times$ reduction in CoT tokens while maintaining performance. **AnytimeReasoner / BRPO** (Qi et al., ICML 2025) trains models for optimal performance at any thinking budget via truncated CoT traces and dense verifiable rewards. **BudgetThinker** (Wen et al., 2025) inserts special control tokens at fixed budget fractions to continuously signal remaining token budget during generation, achieving +4.9% avg accuracy across budgets on MATH-500.

**BAR Conjecture** (Zhou et al., 2025) provides a formal foundation: it proves that no LLM system can simultaneously optimize inference-time budget, factual authenticity, and reasoning capacity once input size exceeds a critical threshold. The proof establishes an unavoidable trilemma that constrains all budget-aware systems.

### 3.2 Tool-Call and Monetary Budgets

**INTENT** (Liu et al., ICML 2025) formalizes tool-augmented LLM agents under strict monetary budgets with priced, stochastic tool calls. It uses a learned language world model for Monte Carlo lookahead to anticipate future tool costs, with intention-based decomposition separating semantic intent from concrete output. INTENT strictly enforces hard budget feasibility — a run that would exceed the budget is terminated.

**BATS: Budget-Aware Tool-Use Enables Effective Agent Scaling** (Liu et al., 2025) identifies a critical failure mode: simply giving agents larger tool-call budgets is ineffective without budget *awareness*. BATS introduces a lightweight Budget Tracker plug-in that provides continuous budget state to the agent, enabling dynamic adaptation between "dig deeper" and "pivot" strategies. It unifies token and tool costs into a single metric.

**AVA: Anytime Verified Agents** (Patel et al., TMLR 2026) provides an open-source framework combining adaptive search, uncertainty estimation, and verification cascades under explicit token, tool-call, and verification budgets.

These papers establish that budget constraints can be enforced at inference time with learned or heuristic controllers. But they operate at the **per-example or per-agent-run level**. They do not address: how should a batch of tasks of varying value and difficulty share one hard budget?

### 3.3 Multi-Agent Budget Coordination

**CoRL** (Jin et al., 2025) frames multi-LLM coordination as RL with dual objectives — maximize task performance and minimize inference cost — enabling the same system to adapt behavior under different budget conditions. **FutureWeaver** (Jung et al., 2025) addresses compute allocation across collaborating agents using dual-level planning with short-horizon action selection and long-horizon A*-style speculation.

These multi-agent approaches allocate budget across agents working on a shared task, not across independent tasks within a fixed batch.

---

## 4. Explainable and Auditable Routing (Topaz)

**Topaz** (Okamoto et al., CHI 2026 HCXAI Workshop) introduces explainable model routing for agentic workflows. It builds a shared 8-dimensional skill taxonomy (mathematical reasoning, logical reasoning, code generation, tool use, factual knowledge, writing quality, instruction following, summarization), profiles both models and subtasks against this taxonomy, and provides two routing modes: objective-based (maximize weighted quality-cost tradeoff) and budget-based (dynamic programming maximizing cumulative quality under a fixed cost cap).

Topaz's key contribution is **auditability**: all routing decisions are recorded in structured trace logs with natural-language explanations for developers. This addresses the production concern that "a developer should be able to ask: was the system smart, or was it just cheap?" However, Topaz's routing optimizes a per-workflow quality-cost tradeoff; its budget is a parameter to maximize against, not a binding constraint that depletes in real time. It does not verify task outcomes or measure verified resolved value.

---

## 5. Agent-Level Budget Constraints

**BCAS: Budget-Constrained Agentic Search** (McCleary & Ghawaly, 2026) is a model-agnostic evaluation harness that surfaces remaining budget to an agent during iterative RAG. It gates tool calls against explicit token and turn budgets, studying how search depth, retrieval strategy, and completion budget affect accuracy. Key finding: accuracy improves with additional searches only up to a small cap — a result that directly informs when a budget-constrained agent should stop spending on a given task.

**AgentServe** (Zhang et al., 2026) addresses GPU-level resource contention in multi-agent serving, using dynamic budgeting for resume prefills and adaptive GPU allocation. It demonstrates that budget awareness must span from infrastructure to agent policy, though its contribution is systems-level rather than policy-level.

Neither paper addresses budget allocation across tasks of heterogeneous value.

---

## 6. Survey and Taxonomy

**Dynamic Model Routing and Cascading for Efficient LLM Inference: A Survey** (Moslem & Kelleher, 2026) provides a systematic taxonomy of multi-LLM routing across eight paradigms: query difficulty, human preferences, clustering, uncertainty quantification, reinforcement learning, multimodality, and cascading. It introduces a three-dimensional conceptual framework characterizing routing systems along: *when* decisions are made, *what* information is used, and *how* they are computed. The survey confirms that practical systems are often compositional, integrating multiple paradigms under operational constraints. Open challenges include routing generalization across diverse architectures, modalities, and applications.

---

## 7. Positioning: The Shared-Budget Gap

The literature converges on a consistent pattern. Each system controls cost at a single level — per-query, per-trace, per-agent-run — without managing a shared resource pool across multiple valued tasks.

| Approach | Decision Unit | Budget Scope | Value Awareness | Verified Outcomes |
|---|---|---|---|---|
| FrugalGPT / RouteLLM / HybridLLM | Per-query | None (cost minimization) | No | No |
| UCCI | Per-query | None (cost minimization) | No | No |
| RouteNLP | Per-workflow | Per-workflow cap | Quality sensitivity | No |
| Predictive Scheduling / e1 / BRPO / BudgetThinker | Per-trace | Per-example token budget | No | No |
| INTENT / BATS / AVA | Per-agent-run | Per-run tool/monetary budget | No | Task success (binary) |
| CoRL / FutureWeaver | Multi-agent per-task | Per-task compute | No | Task success |
| Topaz | Per-subtask | Cost-sensitivity parameter | Indirect (quality) | No |
| BCAS | Per-agent-session | Token/turn budget | No | No |
| **BudgetFlow** | **Per-task within fixed batch** | **Shared hard budget** | **Pre-registered task value** | **Verified resolution** |

No existing system combines these four properties: (1) one shared hard budget across a fixed batch of tasks, (2) pre-registered per-task value that is not post-hoc fitted, (3) a runtime policy that allocates scarce model opportunities to maximize total verified value, and (4) a pre-run budget regime compiler that makes the cap auditable rather than hand-picked.

The closest neighbors — UCCI's calibrated escalation, RouteNLP's quality-constrained routing, Topaz's budget-aware dynamic programming, and BATS's budget tracking — each address one piece of the puzzle. BudgetFlow's contribution is to unify these concerns under a shared-budget governance layer where the objective is not per-query cost savings but **total verified task value under one hard budget**.

---

## 8. Future Work

BudgetFlow's current scope (Claim 1) establishes that a shared-budget governance layer improves verified value Yield over pure-tier baselines. Future work can extend this foundation to mechanism-level analysis: learned routing policies that improve with deployment experience, stage-aware or segment-aware budget allocation, stop-loss and escalation strategies informed by live progress signals, and continual cost memory that refines budget estimates across runs. These mechanism dimensions are natural extensions of the Claim 1 framework and are explicitly reserved for follow-up investigation.

---

## References

See `references.bib` for BibTeX entries. Key papers cited:

1. Chen, L., Zaharia, M., & Zou, J. (2023). FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance. arXiv:2305.05176.
2. Ong, I., et al. (2024). RouteLLM: Learning to Route LLMs with Preference Data. arXiv:2406.18665.
3. Ding, S., et al. (2024). HybridLLM: Dynamic Model Selection for Cost-Efficient LLM Applications.
4. Aggarwal, P., et al. (2024). AutoMix: Cascading with Self-Verification Results.
5. Guo, D., Wu, J., & Yiu, S. (2026). RouteNLP: Closed-Loop LLM Routing with Conformal Cascading and Distillation Co-Optimization.
6. Kotte, V. (2026). UCCI: Calibrated Uncertainty for Cost-Optimal LLM Cascade Routing.
7. Okamoto, M., Erol, A. K., & Riedl, M. (2026). Explainable Model Routing for Agentic Workflows (Topaz). CHI 2026 HCXAI Workshop. arXiv:2604.03527.
8. Brown, D., Muppidi, S., & Shahout, R. (2025). Predictive Scheduling for Efficient Inference-Time Reasoning in LLMs. ICML 2025.
9. Kleinman, M., et al. (2025). e1: Learning Adaptive Control of Reasoning Effort.
10. Qi, W., et al. (2025). Optimizing Anytime Reasoning via Budget Relative Policy Optimization. ICML 2025.
11. Wen, Z., et al. (2025). BudgetThinker: Empowering Budget-Aware LLM Reasoning with Control Tokens. arXiv:2508.17196.
12. Zhou, X., et al. (2025). BAR Conjecture: the Feasibility of Inference Budget-Constrained LLM Services. arXiv:2507.23170.
13. Liu, C., et al. (2025). Budget-Constrained Agentic LLMs: Intention-Based Planning for Costly Tool Use (INTENT). ICML 2025.
14. Liu, C., et al. (2025). Budget-Aware Tool-Use Enables Effective Agent Scaling (BATS). arXiv:2511.17006.
15. Patel, K., et al. (2026). Anytime Verified Agents (AVA). TMLR 2026.
16. Jin, H., et al. (2025). Controlling Performance and Budget of a Centralized Multi-agent LLM System with RL (CoRL). arXiv:2511.02755.
17. Jung, S., et al. (2025). FutureWeaver: Planning Test-Time Compute for Multi-Agent Systems. arXiv:2512.11213.
18. Moslem, Y. & Kelleher, J.D. (2026). Dynamic Model Routing and Cascading for Efficient LLM Inference: A Survey.
19. McCleary, K. & Ghawaly, J.M. (2026). Quantifying the Accuracy and Cost Impact of Design Decisions in Budget-Constrained Agentic LLM Search (BCAS).
20. Zhang, Y., et al. (2026). AgentServe: Algorithm-System Co-Design for Efficient Agentic AI Serving.
