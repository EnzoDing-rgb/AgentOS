# BudgetFlow Paper 1 -- Metrics and Evaluation Audit

## Status: research audit, not code change. Author: metrics research worker, 2026-06-25.

## 1. Executive Summary

1. **Rename "Yield" to "Verified Resolved Value" (VRV).** "Yield" is not a term used in any SWE-bench, routing, or benchmark paper surveyed. "Verified Resolved Value" or "Total Verified Value" is self-documenting and Reviewer-safe. In formula-heavy contexts, use VRV. In prose, use "total verified resolved value."

2. **Replace "Yield / Dollar" with "Verified Value per Dollar" (VVD).** The form "X per Dollar" is the standard across all surveyed cost-aware benchmarks (CLEAR CNA, SWE-Effi EuCB, RouteLLM's cost-benefit framing, industry leaderboard "cost per resolved task"). No paper surveyed uses "Yield / Dollar." If the Reviewer Googles it, 0 hits. Use "Verified Value per Dollar" (VVD) in tables. In prose, "verified value per dollar of model spend."

3. **Keep Pass / Resolved Count as a diagnostic, not as a headline.** SWE-bench itself uses "% Resolved" / "Resolved Rate" as the primary metric. BudgetFlow should report this because it is the most recognized number in the SWE-bench community. But Claim 1 is about value under budget, so pass count alone undersells the mechanism. Place resolved count and resolved rate in the main table; place VVD as the headline efficiency metric.

4. **Adopt SWE-bench term "Resolved Rate" not "Pass Rate".** The official SWE-bench paper (Jimenez et al., arXiv:2310.06770) and swebench.com use "resolved" (meeting FAIL_TO_PASS + PASS_TO_PASS criteria), not "pass." BudgetFlow currently uses both terms interchangeably; standardize on "resolved" for SWE-bench compatibility. "Pass" can appear in prose for readability but the metric column should read "Resolved" or "Resolved Rate."

5. **For reviewer defense, add an appendix row that recasts VVD as the reciprocal (Cost per Resolved Value) and compares it against "Cost per Resolved Task" from the industry leaderboard literature.** This preempts the objection that VVD is self-invented by showing it directly mirrors the established metric.

## 2. SWE-bench Standard Metrics

### 2.1 Core evaluation: % Resolved (Resolved Rate)

Source: SWE-bench paper (Jimenez et al., arXiv:2310.06770). Official site: <https://www.swebench.com>.

Definition:
- A task instance is **resolved** iff:
  1. The generated patch applies without error.
  2. All FAIL_TO_PASS tests now pass (the original failing tests are fixed).
  3. All PASS_TO_PASS tests still pass (no regression).
- **Resolved Rate** = (# of resolved instances) / (total instances).

The leaderboard at <https://www.swebench.com> uses "% Resolved" as the sole primary column. There is **no cost column on the official SWE-bench leaderboard** -- cost-aware evaluation is a third-party add-on.

### 2.2 Dataset variants

| Variant | Instances | Status |
|---|---|---|
| SWE-bench Full | 2,294 | Original test set |
| SWE-bench Verified | 500 | Human-filtered; **de facto standard for leaderboard** |
| SWE-bench Lite | 300 | Cheaper subset |

### 2.3 SWE-bench's relationship to cost

SWE-bench **does not define a cost-aware metric**. The benchmark provides tasks, a verifier (test logs), and a grading script (`log_parsers/`). Cost is entirely external. Industry evaluators (Artificial Analysis, ContraCollective, Requesty, Effloow Lab) compute "Cost per Resolved Task" ad hoc:

> "Cost per Resolved = Total Attempt Cost / Solve Rate"

This is exact reciprocal of BudgetFlow's current Yield/Dollar (if task values are all 1.0).

### 2.4 Has SWE-bench considered cost formally?

No official cost-aware variant exists. However, **SWE-Effi** (Fan et al., arXiv:2509.09853) introduces a formal resource-effectiveness framework on top of SWE-bench tasks. Its metric naming system is highly relevant (see Section 5).

**Recommendation:**
- Use "Resolved" (not "Pass") as the column header when reporting counts and rates.
- Report both "Resolved Count" and "Resolved Rate" in your main table.
- Cite <https://www.swebench.com> and arXiv:2310.06770 for the definition.

## 3. Routing / Cascade Cost-Quality Metrics

### 3.1 FrugalGPT (Chen et al., arXiv:2305.05176)

Source: <https://arxiv.org/abs/2305.05176>

Metric vocabulary used:
- **Cost Savings** (percentage reduction vs. best single LLM, e.g. "98.3% cost savings")
- **Cost (USD)** per dataset (absolute spend)
- **Performance** = raw accuracy (no value weighting)

FrugalGPT does **not** define a per-unit-efficiency ratio metric. Its headline is "we match GPT-4's performance at X% lower cost" -- an accuracy-at-budget framing, not a rate-per-dollar framing. This is very different from BudgetFlow, which uses a fixed budget and reports resolved value per dollar.

### 3.2 RouteLLM (Ong et al., arXiv:2406.18665)

Source: <https://arxiv.org/abs/2406.18665>, <https://lmsys.org/blog/2024-07-01-routellm/>

Three primary evaluation metrics:

| Metric | Full Name | Definition |
|---|---|---|
| **PGR** | Performance Gap Recovered | (Q_router - Q_weak) / (Q_strong - Q_weak) at a given routing % |
| **APGR** | Average Performance Gap Recovered | Mean of PGR across all routing percentages (0%-100%) |
| **CPT** | Call-Performance Threshold | Minimum % of strong-model calls to reach a target PGR |

RouteLLM also reports:
- **Cost savings** (e.g. "2x+ cost reduction", "85% fewer GPT-4 calls")
- Calls to strong model (%) as a proxy for cost
- Pareto frontier plots (quality vs. cost)

Key: RouteLLM's metrics are **relative to a performance gap**, not absolute resolved value. BudgetFlow's setting is fundamentally different -- we have a fixed hard budget, not a sliding cost-quality curve. RouteLLM tradeoff metrics (PGR/APGR/CPT) are **not reusable** for BudgetFlow's Claim 1, but they could inform Claim 2 ablation analysis (e.g. how much of the performance gap between T2 and T3 does the policy recover per dollar).

### 3.3 HybridLLM (Ding et al., arXiv:2404.14618, ICLR 2024)

Source: <https://arxiv.org/abs/2404.14618>

Metrics:
- **Cost Advantage** = fraction of queries routed to small model
- **Quality Drop** = BART score degradation vs. all-large baseline
- Framing: "at X% cost advantage, quality drops by Y%"

No per-dollar ratio metric.

### 3.4 RouteNLP (Guo et al., arXiv:2604.23577)

Source: <https://arxiv.org/abs/2604.23577>

Metrics:
- **Quality Ratio** = router quality / all-strong quality
- **Cost Ratio** = router cost / all-strong cost
- **p99 Latency** and **SLA Violation Rate**
- "58% cost reduction" framing

No per-dollar ratio metric.

### 3.5 Avengers-Pro (Zhang et al., 2025)

Explicit **Pareto frontier** framing: "By varying alpha, achieves Pareto frontier -- highest accuracy at any given cost, lowest cost at any given accuracy."

### 3.6 Summary for BudgetFlow

None of the routing papers use a "X per Dollar" ratio metric. Their default framing is **quality at cost budget**, not **value per unit spend**. This is a difference in objective, not an oversight:
- Routing papers: given a quality target, minimize cost.
- BudgetFlow: given a fixed hard budget, maximize verified resolved value.

BudgetFlow's VVD metric is **novel in framing but not in spirit** -- it mirrors what CLEAR calls Cost-Normalized Accuracy (CNA) and what SWE-Effi formalizes as "Effectiveness under Cost Budget" (EuCB). These are close cousins, and BudgetFlow should cite them to anchor VVD in existing literature.

## 4. Budgeted Inference Metrics

### 4.1 Reasoning in Token Economies (Wang et al., EMNLP 2024)

Source: <https://aclanthology.org/2024.emnlp-main.1112/>

Key contribution: **budget-normalized evaluation**. Compares reasoning strategies at equal compute budget. Finds that simple strategies (CoT + Self-Consistency) often beat complex ones (multi-agent debate) when compute is equalized.

Metric used: **accuracy at fixed token budget** -- no per-unit ratio.

### 4.2 Compute-Optimal Inference (Wu et al., arXiv:2408.00724)

Source: <https://arxiv.org/abs/2408.00724>

Framing: **Pareto-optimal quality-cost tradeoffs** via model size x decoding strategy. Finds small models + advanced decoding can match large models at 2x fewer FLOPs.

Metric used: accuracy at compute budget. No per-unit ratio.

### 4.3 Decomposing Reasoning Efficiency (Kaiser et al., 2025)

Source: <https://arxiv.org/abs/2602.09805>

Introduces **Token Efficiency E0** = expected correct answers per 1,000 output tokens.

It decomposes efficiency into:
- Completion rate (does the model finish within budget?)
- Conditional correctness (given completion, is the answer correct?)
- Verbosity (tokens per response)

Key finding: accuracy and efficiency rankings diverge (Spearman rho = 0.63). This supports BudgetFlow's case: pass count alone is insufficient.

### 4.4 BudgetThinker (Zhang et al., arXiv:2508.17196)

Source: <https://arxiv.org/abs/2508.17196>

Metrics: **Pass@1 accuracy at multiple budget levels** (2K/4K/6K/10K tokens) + **Budget Following Ratio** (% of runs within budget).

No per-dollar ratio.

### 4.5 BATS (Google Cloud, arXiv:2511.17006, 2025)

Source: <https://arxiv.org/abs/2511.17006>

Metric: **Unified Cost (cents)** = token cost + tool call cost + search call cost, reported alongside accuracy. Reports "X% higher accuracy at 10x less budget" framing.

### 4.6 INTENT (Liu et al., arXiv:2602.11541, 2025)

Source: <https://arxiv.org/abs/2602.11541>

Framing: hard budget constraint on agent tool use. Evaluates **success rate under evolving budget caps**. No per-dollar ratio.

### 4.7 Plan-and-Budget (BBAM, arXiv:2505.16122, 2025)

Introduces **E-cubed (Effectiveness-Efficiency-Economy)** -- a composite metric balancing correctness and cost. Not widely adopted.

### 4.8 Summary

Budgeted inference papers overwhelmingly use **accuracy at budget** as the primary metric, not accuracy-per-dollar. The closest precedent for BudgetFlow's VVD comes from the separate CLEAR/SWE-Effi frameworks (Section 5).

## 5. LLM Agent Benchmark Cost Metrics

### 5.1 CLEAR Framework (Mehta, arXiv:2511.14136, Nov 2025)

Source: <https://arxiv.org/abs/2511.14136>

The CLEAR framework defines **two cost metrics** that are closest to BudgetFlow's VVD:

| Metric | Abbreviation | Formula | BudgetFlow Analog |
|---|---|---|---|
| **Cost-Normalized Accuracy** | **CNA** | Accuracy / Cost * 100 | VVD when all task values = 1 |
| **Cost Per Success** | **CPS** | Total Cost / Successful Tasks | Reciprocal of Pass-per-Dollar |

**CNA is the single most relevant external precedent for VVD.** CLEAR is a published (Nov 2025) framework from a credible author. Citing CLEAR CNA directly addresses Reviewer objections that VVD is invented.

Key finding: CLEAR shows that **CNA rankings differ dramatically from accuracy rankings** (ReAct-GPT4 CNA=25.2 vs Domain-Tuned CNA=260.4, despite ReAct having higher raw accuracy). This is exactly BudgetFlow's argument.

### 5.2 SWE-Effi (Fan et al., arXiv:2509.09853, 2025)

Source: <https://arxiv.org/abs/2509.09853>

Defines four Resource Effectiveness metrics:

| Metric | Full Name | Budget Cap |
|---|---|---|
| **EuCB** | Effectiveness under Cost Budget | $1.00 USD |
| **EuTB** | Effectiveness under Token Budget | 2M tokens |
| **EuCTB** | Effectiveness under CPU Time Budget | 30 min |
| **EuITB** | Effectiveness under Inference Time Budget | 30 min |

Each uses an AUC formulation:

```
Eu_r = (1/S_max) * integral_0^{S_max} R_r(s) ds
```

where R_r(s) is cumulative fraction of issues resolved using at most s units of resource r.

**SWE-Effi is the most direct competitor/comparison paper for BudgetFlow.** Both operate on SWE-bench tasks and both care about resource-constrained evaluation. BudgetFlow should cite SWE-Effi and explain the difference: BudgetFlow uses a single shared hard budget across a batch, while SWE-Effi uses per-task budget caps with AUC integration.

### 5.3 Artificial Analysis Coding Agent Index

Source: <https://artificialanalysis.ai/methodology/coding-agents-benchmarking>

Industry leaderboard. Reports:
- **Cost to Run** (average pay-per-token API cost per task-attempt)
- **Token Usage** (input, output, cache, reasoning tokens)
- **Execution Time** (wall-clock)

Their headline is effectively "cost per task-attempt," not value-weighted.

### 5.4 Industry Leaderboards (ContraCollective, Requesty, Effloow)

Multiple third-party sites now compute **"Cost per Resolved Task"** for SWE-bench:

> Cost per Resolved = Total Attempt Cost / Solve Rate

This is the **reciprocal of Pass-per-Dollar** (when values are uniform). BudgetFlow should report this reciprocal to show it tracks a recognized metric.

## 6. Recommended Metric Set for BudgetFlow

### 6.1 Main Table (Claim 1 evidence)

| Recommended Metric | Current BudgetFlow Name | Reasoning |
|---|---|---|
| **Tasks** | tasks | Number of tasks in the batch. |
| **Resolved** | pass | SWE-bench standard term. Report as count + rate. |
| **Resolved Rate** | not reported separately | % of tasks resolved. The most recognized SWE-bench number. |
| **Verified Resolved Value (VRV)** | Yield | Self-documenting. "Yield" is not used in any surveyed paper. |
| **Total Model Spend ($)** | cost | Exact dollar cost. Standard across all papers. |
| **Verified Value per Dollar (VVD)** | Yield / Dollar | Mirrors CLEAR CNA and industry Cost-per-Resolved. |
| **Avg Spend per Resolved ($)** | avg_cost | Reciprocal framing for industry audience. |

### 6.2 Appendix / Diagnostic Table

| Metric | Current BudgetFlow Name | Reasoning |
|---|---|---|
| **Budget Cap ($)** | budget_cap | Shows bindingness. |
| **Budget Utilization (%)** | utilization | Shows whether budget was binding. |
| **Cost per Resolved Task ($)** | cost_per | Standard industry framing. Reciprocal of Pass-per-Dollar. |
| **Avg Turns per Resolved** | turns | Mechanism diagnostic. |
| **Failure Classes** | failure_classes | Mechanism attribution. |
| **Cost per Unresolved ($)** | abort_cost | Waste diagnostic. Helps show that cheaper routes that fail still cost money. |

### 6.3 Metrics to drop or rename

| Current Name | Action | Reason |
|---|---|---|
| **Yield** | Rename to "Verified Resolved Value" (VRV) | No paper uses "Yield." Reviewer will flag as nonstandard. |
| **Yield / Dollar** | Rename to "Verified Value per Dollar" (VVD) | No paper uses "Yield/Dollar." Cite CLEAR CNA as precedent. |
| **Pass** (column) | Rename to "Resolved" | SWE-bench standard. |
| **Pass per Dollar** | Keep as Appendix diagnostic, rename to "Resolved per Dollar" | Useful for uniform-value sensitivity. |

## 7. Metric Naming Recommendation

### 7.1 Recommended names with justification

| Recommended Name | Abbrev | Justification |
|---|---|---|
| **Verified Resolved Value** | VRV | "Verified" = SWE-bench verifier. "Resolved" = SWE-bench paper term. "Value" = weighted by task value, not raw count. No surveyed paper uses this exact term, but every component is standard. |
| **Verified Value per Dollar** | VVD | Follows the pattern of CLEAR's "Cost-Normalized Accuracy" and SWE-Effi's "Effectiveness under Cost Budget." The "per Dollar" form is universally understood and Googleable. |
| **Resolved Count** | -- | SWE-bench standard. |
| **Resolved Rate** | -- | SWE-bench standard. |
| **Cost per Resolved Task** | CPR | Industry standard reciprocal. Reported as appendix cross-reference. |

### 7.2 Why not these alternatives

| Rejected Name | Reason |
|---|---|
| **Value-weighted Resolve Rate** | Verbose. "Resolve Rate" in SWE-bench means % resolved, not a value-weighted sum. Using it for a sum is confusing. |
| **Efficiency** or **Cost Efficiency** | Too generic. "Efficiency" is an overloaded term (token efficiency, compute efficiency, energy efficiency). |
| **Value Efficiency** | Not Googleable. No paper uses this. |
| **Cost-Normalized Verified Value** | Direct CLEAR analog, but VVD is simpler. Only use "Cost-Normalized Verified Value" in discussions explicitly referencing CLEAR. |
| **Profitability** or **Return on Spend** | Finance framing that overpromises. SWE-bench task values are proxies, not real revenue. |
| **Effectiveness under Shared Budget (EuSB)** | Could follow SWE-Effi naming convention (EuCB style), but "EuSB" is not defined in their framework and BudgetFlow's AUC-free formulation does not fit. |

### 7.3 How to introduce VVD to reviewers

In paper text:

> "We report **Verified Value per Dollar (VVD)**, defined as total verified resolved task value divided by total model spend in USD. VVD follows the cost-normalized accuracy framework of CLEAR (Mehta 2025) and the resource-effectiveness formulation of SWE-Effi (Fan et al. 2025), adapted to the shared-budget setting where tasks compete for a single hard cap rather than receiving independent per-task budgets."

This paragraph:
1. Cites two existing frameworks (not inventing from scratch).
2. Explains the adaptation (shared cap vs. per-task cap).
3. Avoids claiming VVD is "the standard" when it is not.

## 8. Risks and Reviewer Objections

### 8.1 "VVD is a custom metric. Why not just report Resolved Rate?"

**Defense:** SWE-bench's Resolved Rate treats every task equally. BudgetFlow's core question is whether spending scarce budget on higher-value tasks improves total verified resolved value. This cannot be answered by Resolved Rate alone. The CLEAR framework (Mehta 2025, rho=0.83 correlation with expert deployment judgment vs. 0.41 for accuracy alone) and the "Reasoning in Token Economies" paper (Wang 2024, accuracy rankings diverge from cost-normalized rankings) both establish that cost-normalized metrics provide different and more deployment-relevant information than accuracy alone.

**Strength of defense:** High. Two independent papers with emperical evidence.

### 8.2 "Yield / Dollar sounds made up."

**Defense:** Renaming to "Verified Value per Dollar" (VVD) and citing CLEAR CNA addresses this head-on. The naming follows the well-established pattern of normalizing a quality metric by cost. If the Reviewer insists on an existing name, "Cost-Normalized Verified Value" can be used and directly attributed to the CLEAR framework.

**Strength of defense:** High after rename. The current "Yield / Dollar" name has 0 precedent.

### 8.3 "Task values are arbitrary. Your VVD depends entirely on your value proxy."

**Defense:** This is BudgetFlow's primary threat to validity and should be acknowledged, not hidden. The defense requires:
1. Report results under multiple value profiles (equal, current, critical-only) to show sensitivity.
2. Freeze ValueSource before execution (as north_star.md requires).
3. Argue that in real deployment, business stakeholders supply the values -- the proxy is for research reproducibility, not because values are unknowable.
4. Report Resolved Count alongside VVD so reviewers can see the raw (unweighted) result.

**Strength of defense:** Moderate. This is a genuine limitation. Papers in SWE-bench space do not weight by value, so BudgetFlow bears the burden of justifying value weights.

### 8.4 "Why not use SWE-Effi's EuCB? It is an established metric."

**Defense:** SWE-Effi's EuCB integrates across a per-task budget curve. BudgetFlow's setting is a single shared hard budget across a batch. EuCB cannot express "Task A consumed the budget that Task B needed." BudgetFlow's VVD complements EuCB -- it addresses the shared-budget allocation problem that per-task metrics ignore.

**Strength of defense:** High. The settings are genuinely different.

### 8.5 "You should report PGR/APGR like RouteLLM."

**Defense:** RouteLLM's PGR/APGR measures recovery of a performance gap between two model tiers across a sliding cost axis. BudgetFlow has a fixed (compiled) hard budget, not a sliding cost-quality curve. PGR/APGR are useful for Claim 2 (mechanism analysis of how much of the T2-to-T3 gap the policy recovers), but not for Claim 1 (fixed-budget value maximization).

**Strength of defense:** High. Different problem setting.

### 8.6 "No cost-aware baseline. Pure T2/T3 are boundary controls, not state-of-the-art."

**Defense:** North star already identifies this gap. The near-term requirement is to run a routing baseline (e.g. a per-task RouteLLM-style classifier choosing T2 vs T3 based on task features) under the same shared cap and verifier. This must be done before paper submission.

**Strength of defense:** Currently weak. Requires the routing baseline audit.

### 8.7 "SWE-bench Verified is saturating. Your 17/30 result may not be meaningful."

**Defense:** BudgetFlow is not claiming SOTA SWE-bench scores. The contribution is budget allocation governance. However, this objection loses force if the task set is too easy (ceiling tasks) or too hard (floor tasks). The 30-task set should be audited for difficulty distribution.

**Strength of defense:** Moderate. Requires task difficulty analysis in the paper.

## 9. Sources

### SWE-bench
- Jimenez et al. "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?" arXiv:2310.06770, 2023. <https://arxiv.org/abs/2310.06770>
- SWE-bench official site: <https://www.swebench.com>
- SWE-bench FAQ: <https://www.swebench.com/SWE-bench/faq/>
- SWE-bench+ (solution leakage analysis): <https://openreview.net/forum?id=R40rS2afQ3>
- SWE-ABS (adversarial test strengthening): arXiv:2603.00520

### FrugalGPT
- Chen et al. "FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance." arXiv:2305.05176, 2023. <https://arxiv.org/abs/2305.05176>

### RouteLLM
- Ong et al. "RouteLLM: Learning to Route LLMs with Preference Data." arXiv:2406.18665, 2024. <https://arxiv.org/abs/2406.18665>
- LMSYS blog: <https://lmsys.org/blog/2024-07-01-routellm/>

### HybridLLM
- Ding et al. "Hybrid LLM: Cost-Efficient and Quality-Aware Query Routing." arXiv:2404.14618, ICLR 2024. <https://arxiv.org/abs/2404.14618>

### RouteNLP
- Guo et al. "RouteNLP: Closed-Loop LLM Routing with Conformal Cascading and Distillation Co-Optimization." arXiv:2604.23577, 2024. <https://arxiv.org/abs/2604.23577>

### Budgeted Inference
- Wang et al. "Reasoning in Token Economies: Budget-Aware Evaluation of LLM Reasoning Strategies." EMNLP 2024. <https://aclanthology.org/2024.emnlp-main.1112/>
- Wu et al. "An Emperical Analysis of Compute-Optimal Inference for Problem-Solving with Language Models." arXiv:2408.00724, 2024. <https://arxiv.org/abs/2408.00724>
- Kaiser et al. "Decomposing Reasoning Efficiency in Large Language Models." arXiv:2602.09805, 2025. <https://arxiv.org/abs/2602.09805>
- BudgetThinker: arXiv:2508.17196, 2025. <https://arxiv.org/abs/2508.17196>
- BATS: arXiv:2511.17006, 2025. <https://arxiv.org/abs/2511.17006>
- INTENT: arXiv:2602.11541, 2025. <https://arxiv.org/abs/2602.11541>
- Plan-and-Budget (BBAM): arXiv:2505.16122, 2025. <https://arxiv.org/abs/2505.16122>
- Predictive Scheduling: <https://openreview.net/pdf?id=Mn3lrAWy20>
- TimeBill: arXiv:2512.21859, 2025.
- iServe: arXiv:2501.13111, 2025. <https://arxiv.org/abs/2501.13111>

### Agent Benchmark Cost Metrics
- Mehta. "Beyond Accuracy: A Multi-Dimensional Framework for Evaluating Enterprise Agentic AI Systems" (CLEAR). arXiv:2511.14136, 2025. <https://arxiv.org/abs/2511.14136>
- Fan et al. "SWE-Effi: Re-Evaluating Software AI Agent System Effectiveness Under Resource Constraints." arXiv:2509.09853, 2025. <https://arxiv.org/abs/2509.09853>
- LIVE-SWE-AGENT: arXiv:2511.13646, 2025.
- Artificial Analysis Coding Agent Index: <https://artificialanalysis.ai/methodology/coding-agents-benchmarking>

### Industry Cost per Task Trackers
- ContraCollective, "SWE-bench Verified Leaderboard" (May 2026). <https://contracollective.com/blog/swe-bench-verified-frontier-models-leaderboard-2026/>
- Requesty, "Best AI Coding Model (2026): Benchmarks, Cost, and Real World Performance." <https://www.requesty.ai/blog/best-ai-coding-model-2026-benchmarks-cost-performance>
- Morphllm, "Best AI Model for Coding (June 2026): 12 Models Ranked by SWE-bench Pro Score and Cost per Task." <https://www.morphllm.com/best-ai-model-for-coding>

### Additional
- Avengers-Pro (Pareto frontier routing): Zhang et al., 2025.
- TRAFFICBENCH (Pareto-optimal routing): 2025.
