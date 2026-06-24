# Metrics Red-Team Audit — BudgetFlow Paper 1

**Status:** Red-team research audit. Not a code change. Not a polishing pass.
**Author:** Metrics red-team research worker, 2026-06-25.
**Method:** All external claims verified via web search, arXiv, ACL Anthology, OpenReview, GitHub, and official websites. No second-hand summaries.

---

## 1. Executive Summary

### Metrics that CAN be primary table columns

1. **Resolved Count / Resolved Rate** — SWE-bench official. Community-standard. Every reviewer knows this metric. Required.

2. **Total Model Spend ($)** — Mandatory cost anchor. Reports actual API dollar expenditure across the batch.

3. **Cost per Resolved Task ($)** — Industry-standard framing (Artificial Analysis, ContraCollective, Requesty, CLEAR CPS). Not peer-reviewed, but reviewers will recognize it. Formula: Total Model Spend / Resolved Count.

### Metrics that should be SECONDARY or APPENDIX only

4. **Value-Weighted Resolved Value** (currently "Yield") — Paper-specific. Zero community precedent as a benchmark metric. Must be justified in-text as "the metric that matches the claim." Keep in main table only if the paper's thesis demands it, but label explicitly as "paper-defined."

5. **Value-Weighted Resolved per Dollar** (currently "Yield/$") — Paper-specific derivative. Reciprocally related to Cost per Resolved Value, which has a weak precedent in BIE (Writer/AlShikh et al., arXiv only) and CLEAR CNA (Mehta, arXiv only, not peer-reviewed). Neither precedent was peer-reviewed.

### Metrics that should NOT be used or must be renamed

6. **"Yield"** — Zero hits on Google Scholar, SWE-bench leaderboard, or any routing/benchmark paper. Not a term of art. Delete.

7. **"VRV" / "VVD" abbreviations** — These suggest community-standard acronyms where none exist. Don't invent abbreviations for paper-specific metrics. Spell them out.

8. **"Yield per Dollar" as-is** — The reciprocal "Cost per Resolved" framing is more standard than "per dollar." If you use a ratio, prefer the form with cost in the denominator only when comparing to CLEAR CNA directly, otherwise prefer "Cost per X" as the standard industry framing.

### One-sentence conclusion: previous metrics audit was overly optimistic

The previous audit recommended renaming "Yield" → "VRV" and "Yield/$" → "VVD" and presenting VVD as the headline. It cited CLEAR and SWE-Effi as if they were established, peer-reviewed frameworks. They are not. CLEAR is a 2-month-old arXiv preprint. SWE-Effi is a 9-month-old arXiv preprint. Neither has been accepted at a peer-reviewed venue. "Cost per Resolved Task" is an industry blog convention, not an academic metric. **The previous audit's framing overstated the community acceptance of every cost-aware metric it cited.**

---

## 2. SWE-bench Official Metrics

### 2.1 The single official metric: % Resolved (Resolved Rate)

Source: Jimenez et al., "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?" ICLR 2024. arXiv:2310.06770.

Official definition:
- A task instance is **resolved** iff:
  1. The patch applies cleanly.
  2. All FAIL_TO_PASS tests now pass.
  3. All PASS_TO_PASS tests still pass (no regression).
- **Resolved Rate** = (# resolved) / (total instances) × 100%.

The leaderboard at [swebench.com](https://www.swebench.com) uses "% Resolved" as the sole primary column. There is **no cost column, no value column, no weighted metric, no efficiency ratio** on the official leaderboard.

### 2.2 Does SWE-bench define any cost-aware metric?

**No.** SWE-bench provides tasks, a Docker-based test harness, and a grading script. Cost tracking is entirely external. The FAQ at swebench.com does not mention cost. The original paper does not report cost per task or any efficiency metric.

### 2.3 Does SWE-bench support value weighting?

**No.** All tasks count equally toward "% Resolved." There is no task priority, no value function, no criticality tier. A resolved critical security bug and a resolved typo fix both contribute 1 to the numerator.

### 2.4 SWE-bench Verified vs. Lite vs. Full

| Variant | Instances | Role |
|---|---|---|
| SWE-bench Full | 2,294 | Original; noisy (some issues unfixable) |
| SWE-bench Verified | 500 | Human-filtered; **de facto leaderboard standard** |
| SWE-bench Lite | 300 | Cheaper subset for rapid iteration |

All three use identical metric definitions. None includes cost or value.

### 2.5 Verdict

**SWE-bench endorses exactly one metric: % Resolved.** Everything else (cost, value, efficiency ratios) is external. BudgetFlow must report % Resolved. Failing to report it in the main table would be a reviewer red flag.

---

## 3. Cost-Aware Metrics in Coding-Agent Evaluation

### 3.1 "Cost per Resolved Task"

**Status: Industry blog convention. Zero peer-reviewed papers define it as a formal metric.**

Sources:
- Artificial Analysis Coding Agent Index ([artificialanalysis.ai](https://artificialanalysis.ai/methodology/coding-agents-benchmarking)) — reports "Cost to run" and token breakdowns. Industry leaderboard, not a paper.
- ContraCollective blog (May 2026) — "SWE-bench Verified Frontier Models Leaderboard." Reports cost per task. Blog post.
- Requesty model pages — report SWE-bench score alongside API pricing. Commercial tool.
- Morphllm — "Best AI Model for Coding (June 2026)." Blog post.

Formula (convergent across all sources):
```
Cost per Resolved Task = Total Attempt Cost / Number Resolved
```

This is the **reciprocal** of "Resolved per Dollar." It is recognized, understood, and expected by industry readers. But it has **never been peer-reviewed as a formal evaluation metric.** Reviewers will not object to seeing it; they WILL object if you claim it as a community-standard metric rather than an industry convention.

**Strength for BudgetFlow:** High recognition, low formal authority. Safe to include as a secondary column. Not safe to claim as "the standard metric."

### 3.2 "Cost-of-Pass" (Erol et al., 2025)

Source: Erol et al., "Cost-of-Pass: An Economic Framework for Evaluating Language Models." arXiv:2504.13359, April 2025.

**Peer-review status: arXiv preprint. Not accepted at any venue.** (Checked: no conference/journal acceptance found.)

Formula:
```
Cost-of-Pass = Cost per inference attempt / Success rate (pass@1)
```

This is identical to "Cost per Resolved Task" but with a formal name. The paper shows cost-of-pass halving every few months on AIME/MATH 500. It is the closest thing to a formal cost-per-success metric, but it has not passed peer review.

**Strength for BudgetFlow:** Moderate (formal definition, not yet peer-reviewed). Can be cited as "Cost-of-Pass (Erol et al., 2025)" to anchor the cost-per-resolved column in existing literature.

### 3.3 CLEAR CNA and CPS (Mehta, 2025)

Source: Mehta, "Beyond Accuracy: A Multi-Dimensional Framework for Evaluating Enterprise Agentic AI Systems." arXiv:2511.14136, November 2025.

**Peer-review status: arXiv preprint. 2 months old. Not peer-reviewed.** (Checked: no conference/journal acceptance found. Featured on HuggingFace Daily Papers — that is not peer review.)

Formulas:
- **CNA** = Accuracy / Cost × 100
- **CPS** = Total Cost / # Successful Tasks

CNA is the closest formal analogue to BudgetFlow's "Yield/$" (if task values are all 1.0). But CNA uses **unweighted accuracy**, not value-weighted resolved value. They are NOT equivalent.

CPS is identical to "Cost per Resolved Task."

**Key risk for BudgetFlow:** The previous audit cited CLEAR as if it established "X per Dollar" as a community standard. CLEAR is a 2-month-old preprint with zero citations on Semantic Scholar (as of search date). It does not establish a standard.

**Strength for BudgetFlow:** Weak (unreviewed, very recent). Can be cited as "related work in cost-aware evaluation" but NOT as evidence of community standardization.

### 3.4 SWE-Effi EuCB (Fan et al., 2025)

Source: Fan et al., "SWE-Effi: Re-Evaluating Software AI Agent System Effectiveness Under Resource Constraints." arXiv:2509.09853, September 2025.

**Peer-review status: arXiv preprint. Not accepted at any venue.** (Checked: no conference/journal acceptance found. Has a leaderboard website at GitHub Pages — that is not peer review.)

Formula:
```
EuCB = Normalized AUC of cumulative resolve rate vs. cost curve, capped at $1.00
```

EuCB measures **area under the cost-resolve curve**, not a point estimate. A system that resolves more tasks earlier (cheaper) gets a higher EuCB. This is fundamentally different from both "Resolved per Dollar" and "Cost per Resolved Task" — it's an integral over the whole cost range, not a ratio at one budget point.

**Critically: SWE-Effi does NOT support value-weighted resolved per dollar.** EuCB is unweighted. Every resolved task counts equally. The $1.00 cap is a fixed evaluation budget, not a shared batch budget.

**Strength for BudgetFlow:** Weak (unreviewed, different metric shape). Cite as evidence that cost-aware SWE-bench evaluation is an emerging concern, not as support for any specific BudgetFlow metric.

### 3.5 "The Price of Progress" (Gundlach et al., NeurIPS 2025 Workshop)

Source: Gundlach et al., "The Price of Progress: Algorithmic Efficiency and the Falling Cost of AI Inference." NeurIPS 2025 **Workshop** (not main conference).

**Peer-review status: Workshop paper.** NeurIPS workshops have lighter review than the main conference. Reports Pareto frontier analysis of cost vs. benchmark performance. Estimates 5-10×/year price decline on frontier models.

**Strength for BudgetFlow:** Weak (workshop, not about metric definitions). Cite for the trend observation that cost-aware evaluation matters, not for metric standardization.

### 3.6 Verdict on Cost-Aware Metrics

**There is no peer-reviewed, community-standard cost-aware metric for coding agents.** The entire space is arXiv preprints, workshop papers, and industry blogs. This is both a problem and an opportunity:

- **Problem:** BudgetFlow cannot point to "the standard cost metric" because none exists.
- **Opportunity:** BudgetFlow can define its cost columns without violating any standard.

The honest framing: "Cost-aware evaluation of coding agents is an active area (Mehta 2025, Fan et al. 2025, Erol et al. 2025), but no standard metric has been established. We report both the industry-standard Cost per Resolved Task and our paper-defined Value-Weighted Resolved per Dollar."

---

## 4. Value-Weighted Metrics: Do They Exist?

### 4.1 Direct search: "task value × binary resolved"

**No prior art found.** No SWE-bench paper, LLM agent benchmark, routing paper, or budgeted-inference paper defines a metric that multiplies a per-task utility weight by a binary resolved/failed outcome and sums across a batch.

### 4.2 Related but NOT equivalent weighted metrics

| Work | Weighting | Peer-Reviewed? | Equivalent to Yield? |
|---|---|---|---|
| EMDM (Etzine et al., TrustNLP 2025) | Weights by difficulty, not utility | TrustNLP Workshop at NAACL | **No.** Difficulty ≠ value. |
| H-Bench (Waggoner, 2025) | Conjoint-derived utility weights | arXiv only | **No.** Theoretical framework, no empirical results with task-value weighting. |
| BIE (AlShikh et al., 2025) | KPI monetary value / cost | arXiv only | **Closest.** BIE = KPI_monetary_value / total_operational_cost. But BIE is a ratio, not a sum, and it's unreviewed. |
| LMUNIT (ACL Findings 2025) | Bayesian-optimized criterion weights from human preferences | ACL Findings (light review) | **No.** Criterion weights for eval rubrics, not per-task value. |
| EvalScope | Business-priority weights for benchmark sampling | Industry tool, not a paper | **No.** Sampling weights, not outcome weights. |
| xbench (HSG) | Profession-aligned utility weights | Industry blog | **No.** |

### 4.3 Verdict

**BudgetFlow's "Yield" (value-weighted resolved value) is a paper-specific metric with no community precedent.** This is not a reason to remove it — it matches Claim 1 exactly — but it MUST be:

1. **Explicitly labeled as paper-defined** ("Value-Weighted Resolved Value, defined as Σ v_i × resolved_i").
2. **Justified in-text** as the natural metric for the shared-budget value-maximization problem.
3. **Accompanied by unweighted Resolved Rate** so reviewers can decompose "does BudgetFlow resolve more tasks?" from "does BudgetFlow resolve more valuable tasks?"
4. **Pre-registered:** The value profile must be declared before the run, not fitted post-hoc. The previous audit and north_star.md already require this. It must be visible in the paper.

---

## 5. LLM Routing Metrics

### 5.1 RouteLLM (Ong et al., 2024)

**Venue:** NeurIPS 2024. Peer-reviewed.

Metrics:
- **CPT(x%):** Call-Performance Threshold. The % of queries routed to the strong model when the cost budget allows x% of queries to use the strong model. Sweeps the tradeoff curve. Per-query metric.
- **PGR:** Performance Gap Recovery. (Router_accuracy − Cheap_accuracy) / (Strong_accuracy − Cheap_accuracy). Measures what fraction of the strong model's performance advantage is recovered by routing.
- **APGR:** Average PGR across all CPT levels. Summary statistic.
- **Cost (%):** Percent of queries routed to the strong model (proxy for cost, not actual dollars).

**Can these be used for BudgetFlow?** **No.** PGR/APGR require a per-query setting with a cheap/strong model pair and a reference accuracy. BudgetFlow operates on batch-level shared-budget allocation. CPT sweeps are for per-query threshold routing, not cross-task allocation. RouteLLM's cost is "% to strong model" — not dollars, not a hard cap.

**What to borrow:** PGR's framing of "what fraction of the gap did you recover?" This could inspire a BudgetFlow-specific variant: "Yield Gap Recovery = (BF_Yield − T2_Yield) / (Oracle_Yield − T2_Yield)." But this would be paper-specific, not a RouteLLM metric.

### 5.2 FrugalGPT (Chen et al., 2023)

**Venue:** arXiv preprint. Not peer-reviewed at a top venue.

Metrics:
- **Accuracy:** Task-specific (exact match, F1).
- **Cost ($):** Sum of per-API-call costs.
- **Cost Savings (%):** (Best_Single_LLM_Cost − FrugalGPT_Cost) / Best_Single_LLM_Cost.
- **Performance at Matched Cost:** Dual-axis reporting: "how much cost do we save at fixed accuracy?" and "how much accuracy do we gain at fixed cost?"

**Can these be used for BudgetFlow?** **Partially.** The dual-axis framing (accuracy vs. cost, cost vs. accuracy) is clean and intuitive. But FrugalGPT's budget is an average E[cost] ≤ b, not a hard cap. Its metrics don't involve task value.

**What to borrow:** Report both the "cost savings at matched resolved rate" and "resolved gain at matched cost" as dual-axis diagnostics in the appendix or sensitivity tables. The paper already does this implicitly via Table 4 (cap sensitivity).

### 5.3 RouteNLP (Guo et al., 2026)

**Venue:** ACL 2026 Industry Track. Peer-reviewed (industry track).

Metrics:
- **Quality Ratio:** Quality / Quality(Always-T4). Values >1.0 not possible. Measures quality retention.
- **Cost Ratio:** Cost / Cost(Always-T4). Lower is better.
- **p99 Latency:** From M/M/c queueing simulation.
- **SLA Violation Rate:** Coverage violations exceeding conformal α = 0.05.

**Can these be used for BudgetFlow?** **No.** Quality/Cost Ratios are relative to an Always-T4 upper bound. BudgetFlow has no single "best possible" model tier to normalize against. RouteNLP's ratios assume a fixed reference point (Always-T4) that BudgetFlow doesn't share.

**What to borrow:** The idea of reporting ratios relative to a reference. BudgetFlow could define "Relative Yield = Yield / Yield(T3-only)" as a diagnostic. But this is paper-specific.

### 5.4 Budgeted Inference Papers (INTENT, BATS, BudgetThinker, Predictive Scheduling)

- **INTENT:** Pass rate, feasible rate, avg cost (credit units). Per-task. No cross-task allocation.
- **BATS:** Accuracy, unified cost (cents). Post-hoc cost analysis. No shared budget.
- **BudgetThinker:** Accuracy across budget fractions. Per-example token budget.
- **Predictive Scheduling:** Accuracy at fixed token budget. Per-example.

**None of these metrics are transferable to BudgetFlow.** They all measure per-example or per-run outcomes, not batch-level value allocation.

### 5.5 Verdict on Routing Metrics

**No existing routing metric directly supports BudgetFlow's evaluation.** RouteLLM's PGR is the closest in spirit (measuring recovery toward an upper bound) but operates in a different setting. The paper should NOT claim that any routing paper's metrics validate BudgetFlow's metric choices.

---

## 6. Recommended Metric Set for BudgetFlow

### 6.1 Primary Table (Main Result)

| # | Metric | Status | Definition |
|---|---|---|---|
| 1 | **Resolved Count** | Community-standard | Number of tasks (out of 30) passing verification |
| 2 | **Resolved Rate (%)** | Community-standard | Resolved Count / 30 × 100% |
| 3 | **Total Model Spend ($)** | Mandatory cost anchor | Sum of per-task API costs across the batch |
| 4 | **Cost per Resolved Task ($)** | Industry-standard | Total Model Spend / Resolved Count |
| 5 | **Value-Weighted Resolved Value** | **Paper-defined** | Σ v_i × resolved_i. This is the only metric that directly measures Claim 1. Must be labeled as paper-defined. |
| 6 | **Value-Weighted Resolved per Dollar** | **Paper-defined** | Value-Weighted Resolved Value / Total Model Spend. Efficiency diagnostic. |

### 6.2 Proposed Table Format

```
Policy        | Resolved | Rate  | Spend  | $/Resolved | VWRV  | VWRV/$
--------------|----------|-------|--------|------------|-------|-------
BudgetFlow    | 17/30    | 56.7% | $6.000 | $0.353     | 21.0  | 3.500
T3-only       | 16/30    | 53.3% | $5.830 | $0.364     | 18.5  | 3.173
T2-only       | 12/30    | 40.0% | $6.000 | $0.500     | 14.5  | 2.417
```

This table lets reviewers:
- See the community-standard metric (Resolved Rate).
- See the industry-standard cost metric ($/Resolved).
- See the paper-specific value metrics (VWRV, VWRV/$).
- Decompose "does BudgetFlow resolve more?" from "does BudgetFlow resolve more valuable ones?"

### 6.3 Secondary / Appendix Metrics

| Metric | Where | Purpose |
|---|---|---|
| Resolved count by value tier | Appendix | Shows allocation quality per value band |
| Cost per value-weighted resolved task | Appendix | Reciprocal of VWRV/$ in $ terms (more intuitive for some readers) |
| Tasks not executed (budget exhausted) | Appendix | Quantifies budget pressure |
| Average cost per executed task | Appendix | Diagnoses per-task spend distribution |
| Pareto frontier (Resolved Rate vs. Total Cost) | Sensitivity section | Already implicit in cap sensitivity (Table 4) |

---

## 7. Naming Recommendation

### 7.1 Most honest names

| Current Name | Recommendation | Why |
|---|---|---|
| Yield | **Value-Weighted Resolved Value (VWRV)** | "Yield" has zero precedent. Spell out "value-weighted resolved value" in prose. Abbreviation VWRV is acceptable within the paper ONLY if defined at first use. |
| Yield per Dollar | **Value-Weighted Resolved per Dollar (VWR/$)** or **Value-Weighted Resolved Value per Dollar** | "Yield per Dollar" has zero hits. The "/$" abbreviation with spelled-out metric name is clearer than "VVD." |
| — | **Cost per Resolved Task ($/Resolved)** | Use this as the unweighted, industry-recognized cost column. |

### 7.2 Should "Yield" be kept as an internal name?

**No.** Eliminate "Yield" from the paper entirely. Keep it in code only if you want, but the paper should use "Value-Weighted Resolved Value." Code habits leak into prose; if an arXiv reviewer Googles "yield LLM benchmark" and finds nothing, it looks like the authors didn't do their homework.

### 7.3 Should we avoid VRV/VVD abbreviations?

**Partially.** VWRV is a long abbreviation but it's self-documenting: "Value-Weighted Resolved Value." VVD is meaningless — it could mean anything. Avoid VVD. VWRV is acceptable if defined. But in tables, spell out "Value-Weighted Resolved Value" in the column header. Abbreviations save space in prose, not in 8.5"-wide LaTeX tables.

### 7.4 Table column headers

Recommended:
- `Resolved` (or `Resolved / 30`)
- `Rate (%)`
- `Spend ($)`
- `$/Resolved`
- `Value-Wtd Resolved`  (or `VWRV`)
- `VWRV/$`

Do not use:
- `Yield` — not a term
- `VRV` — opaque
- `VVD` — meaningless
- `Value/$` — ambiguous (which value?)

---

## 8. Reviewer Objections and Responses

### 8.1 "Your 'value' is custom, not a benchmark metric."

**Anticipated severity: HIGH.** This is the most likely major objection.

**Honest response:**
- Concede. "Value-Weighted Resolved Value is paper-defined. It is not a SWE-bench metric."
- Justify. "Claim 1 is about maximizing verified value under a shared budget. An unweighted resolved count would not measure this — it would treat all tasks as equally valuable, erasing the core motivation of the paper (heterogeneous task value)."
- Show both. "We report unweighted Resolved Rate and Cost per Resolved Task in the same table so readers can decompose the value-weighted metric into its components."
- Pre-registration defense. "All value profiles were pre-registered before experiments. We report results under 9 profiles (§4.3) including equal-weight, showing the metric is not fitted post-hoc."

### 8.2 "Why not just use SWE-bench Resolved Rate?"

**Anticipated severity: MEDIUM-HIGH.**

**Honest response:**
- "SWE-bench Resolved Rate is our first column. We agree it is the community-standard metric."
- "But Resolved Rate alone cannot measure Claim 1. If BudgetFlow resolves 1 critical bug and T3-only resolves 10 cosmetic bugs, Resolved Rate says T3-only wins. Our operator has $6.00 and cares about the critical bug. This distinction is the entire motivation for shared-budget value-aware allocation."
- Report both. Show that BudgetFlow achieves the highest Resolved Rate (17/30) anyway — it wins on BOTH the weighted and unweighted metric. This is the ideal scenario: value-aware allocation resolves more tasks AND more valuable ones.

### 8.3 "Why not use Cost per Resolved Task?"

**Anticipated severity: MEDIUM.**

**Honest response:**
- "We do. It's column 4 in our main table."
- "But Cost per Resolved Task is unweighted — it treats all resolved tasks as equal. Under heterogeneous task value, a policy could have excellent Cost per Resolved Task by resolving many cheap, low-value tasks while ignoring critical ones. That violates the operator's objective."
- "We report both: Cost per Resolved Task for the unweighted view, VWRV/$ for the value-weighted view."

### 8.4 "Per-dollar ratios can be misleading."

**Anticipated severity: MEDIUM.**

**Honest response:**
- "Per-dollar ratios are one diagnostic, not the headline. The headline is Value-Weighted Resolved Value — did BudgetFlow maximize total verified value under the cap?"
- "We report the absolute Total Model Spend in the same table so readers can verify that per-dollar comparisons are at comparable cost levels."
- "At very low budgets, per-dollar ratios can be unstable because small cost differences produce large ratio swings. Our cap sensitivity (§4.5) reports the full cost range so readers can assess this."

### 8.5 "Is your value weighting post-hoc fitted?"

**Anticipated severity: HIGH.**

**Honest response:**
- "No. All value profiles were pre-registered as part of the Budget Regime Compiler's input. The compiler does not see task outcomes."
- "We report 9 value profiles (Table 3) including equal-weight to show the metric is not cherry-picked."
- "Task Value and Task Effort are separate AllocationContext fields (§3.1). Value does not depend on how much a task cost to resolve. North Star explicitly prohibits historical spend as Task Value."
- This is a procedural defense, not a metric-name defense. It must be in the paper body, not just the appendix.

### 8.6 "CLEAR CNA already exists. Why invent your own?"

**Anticipated severity: LOW-MEDIUM.**

**Honest response:**
- "CLEAR CNA = Accuracy / Cost. Our VWRV/$ = Σ v_i × resolved_i / Cost. They coincide only if all v_i = 1 and 'accuracy' means resolved rate — i.e., only for equal-weight unweighted evaluation."
- "CLEAR (Mehta, 2025) is a recent arXiv preprint. We cite it as related work in cost-aware evaluation but do not claim it as a community standard."
- "CLEAR CNA and our VWRV/$ serve different purposes: CNA is an unweighted cost-efficiency ratio for comparing agents across benchmarks. VWRV/$ is a value-weighted efficiency ratio for comparing allocation policies under a shared budget. They are methodologically related but not interchangeable."

### 8.7 "None of your cost metrics are peer-reviewed."

**Anticipated severity: LOW (because it's true for everyone).**

**Honest response:**
- "Correct. Cost-aware evaluation for coding agents is an active, largely pre-peer-review area. We cite Erol et al. (2025), Mehta (2025), and Fan et al. (2025) as concurrent work. No community standard exists yet. We define our metrics transparently and report both weighted and unweighted views so readers can verify our claims regardless of which metric they prefer."

---

## 9. Final Recommendation

### What the draft should report

**Main table (replaces current Table 1):**
6 columns: Resolved, Rate (%), Spend ($), $/Resolved, VWRV, VWRV/$.

**Headline claim:** "BudgetFlow achieves the highest Value-Weighted Resolved Value (21.0) and highest Resolved Rate (56.7%) under the shared $6.00 cap."

**Important:** BudgetFlow wins on Resolved Rate too (17 vs. 16 vs. 12). Lead with this. Say "BudgetFlow resolves more tasks AND more valuable ones." Don't bury the unweighted win behind the value-weighted metric — let both metrics tell the same story. When the weighted metric diverges from the unweighted one (e.g., under different value profiles), explain why the divergence is expected and desirable.

### Which metric is the headline?

**Value-Weighted Resolved Value (VWRV).** But always reported alongside Resolved Rate. The headline is: "BudgetFlow maximizes verified value under the cap. It also resolves more tasks. The value-weighted metric captures what Claim 1 promises; the unweighted metric confirms the result is not an artifact of value engineering."

### Which metrics go to appendix?

- Cost per value-weighted resolved task (reciprocal framing)
- Resolved count by value tier
- Tasks not executed due to budget exhaustion
- Pareto frontier plots (Resolved Rate vs. Total Spend) — already implicit in cap sensitivity

### What must be explained carefully in the body text

1. **Why Value-Weighted Resolved Value exists.** "Because Claim 1 is about value, not count. An operator with heterogeneous bugs needs this metric. But we also report unweighted Resolved Rate."

2. **How values are set.** "Pre-registered value profiles. Not fitted from outcomes. Nine profiles tested including equal-weight."

3. **What "Cost per Resolved Task" means and doesn't mean.** "Industry convention, not peer-reviewed standard. Reported for accessibility, not as an endorsement."

4. **That cost-aware evaluation is pre-peer-review.** "No community-standard cost metric exists. We define our metrics transparently. We encourage the community to converge on standards."

### Final one-sentence instruction to main agent

**Replace all instances of "Yield" and "Yield/$" with "Value-Weighted Resolved Value (VWRV)" and "VWRV/$", add Resolved Rate and $/Resolved to the main table as co-equal columns, and add a paragraph in §4.1 (Experimental Setup: Metrics) acknowledging that cost-aware coding-agent evaluation lacks a community standard metric and that VWRV is paper-defined.**

---

## References (this audit)

- Jimenez et al. "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?" ICLR 2024. arXiv:2310.06770.
- Mehta. "Beyond Accuracy: A Multi-Dimensional Framework for Evaluating Enterprise Agentic AI Systems" (CLEAR). arXiv:2511.14136, Nov 2025. **Not peer-reviewed.**
- Fan et al. "SWE-Effi: Re-Evaluating Software AI Agent System Effectiveness Under Resource Constraints." arXiv:2509.09853, Sep 2025. **Not peer-reviewed.**
- Erol et al. "Cost-of-Pass: An Economic Framework for Evaluating Language Models." arXiv:2504.13359, Apr 2025. **Not peer-reviewed.**
- Gundlach et al. "The Price of Progress: Algorithmic Efficiency and the Falling Cost of AI Inference." NeurIPS 2025 Workshop. **Workshop paper.**
- Ong et al. "RouteLLM: Learning to Route LLMs with Preference Data." NeurIPS 2024. **Peer-reviewed.**
- Chen et al. "FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance." arXiv:2305.05176, 2023. **Not peer-reviewed at a top venue.**
- Guo et al. "RouteNLP: Closed-Loop LLM Routing with Conformal Cascading and Distillation Co-Optimization." ACL 2026 Industry Track. **Peer-reviewed (industry track).**
- Etzine et al. "Revitalizing Saturated Benchmarks: A Weighted Metric Approach for Differentiating LLM Performance" (EMDM). TrustNLP Workshop at NAACL 2025. **Workshop paper.**
- Waggoner. "A Theoretical Framework for Adaptive Utility-Weighted Benchmarking" (H-Bench). arXiv:2602.12356, 2025. **Not peer-reviewed.**
- AlShikh et al. "Towards Outcome-Oriented, Task-Agnostic Evaluation of AI Agents." arXiv:2511.08242, 2025. **Not peer-reviewed.**
- Artificial Analysis. Coding Agent Index Methodology. https://artificialanalysis.ai/methodology/coding-agents-benchmarking. **Industry leaderboard.**
- ContraCollective. "SWE-bench Verified Leaderboard." May 2026. https://contracollective.com/blog/swe-bench-verified-frontier-models-leaderboard-2026/. **Blog post.**

---

*This is a red-team audit. It identifies what BudgetFlow's metrics lack (community precedent) and does not attempt to make the metrics look more established than they are.*
