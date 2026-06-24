# Phase 6 Review Report

**Paper:** BudgetFlow: Value-Aware Budget Allocation for LLM Agent Tasks Under a Shared Hard Cap
**Review date:** 2026-06-23
**Scope:** Claim 1 only (Claim 2 parked for future work)

---

## Overall Scores

| Reviewer | Score | Decision Band |
|----------|-------|---------------|
| EIC | 4 | Weak Accept / Borderline |
| R1 (Methods) | 3 | Weak Reject |
| R2 (Related Work) | 4 | Weak Accept |
| R3 (Data/Citations) | 3 | Weak Reject |
| DA | 3 | Weak Reject |
| **Average** | **3.4** | **Borderline** |

NeurIPS scale: 6=Strong Accept, 5=Accept, 4=Weak Accept, 3=Weak Reject, 2=Reject, 1=Strong Reject.

---

## EIC Summary

This paper addresses a genuine and under-explored problem: how should a fixed batch of tasks with heterogeneous pre-registered values share one hard budget? The dominant paradigm in cost-efficient LLM deployment is per-query cost minimization. BudgetFlow reframes the problem as shared-budget value maximization, which is a meaningful conceptual shift. The positioning against three literature clusters is well-structured, and the four-property desideratum (shared hard budget, pre-registered value, runtime allocation, auditable compilation) is crisp.

However, the paper in its current form has fundamental evidential weaknesses that prevent acceptance. The headline result (17/30 vs. 16/30) is a single-task margin on a single 30-task workload with one run. No statistical test, no variance estimate, no multiple seeds, no alternative workload. All sensitivity tables are placeholders. The budget regime compiler is described only in prose with no algorithm, pseudocode, or concrete instantiation. The value registration scheme---the entire basis for differential allocation---is hand-assigned and its sensitivity is not numerically reported (only described directionally). These gaps collectively mean the paper does not yet meet the burden of proof for its central claim.

The paper's conceptual framing and problem statement are strong enough to warrant revision, but the empirical evidence must be substantially strengthened before acceptance. I recommend a **weak accept** contingent on the authors addressing the CRITICAL issues below in a revision cycle.

---

## CRITICAL Issues

- [ ] **C1. Single-run evidence with no statistical backing.** The main result (Table 1) reports one run of 30 tasks. There is no variance estimate, no confidence interval, no multiple random seeds, and no statistical test comparing BudgetFlow to T3-only. With a delta of exactly 1 pass (17 vs. 16), the result could easily be noise. The authors must either run multiple seeds and report variance, use a bootstrap or permutation test on the 30-task batch, or substantially increase the workload size so that a 1-task margin is not the entire claim. Without this, Claim 1 is unestablished.

- [ ] **C2. All sensitivity tables are placeholders.** Tables 2, 3, and 4 (KV-cache sensitivity, value profile sensitivity, budget cap sensitivity) contain no numbers. The text describes directional findings but provides no magnitudes, no table rows, no confirmation that BudgetFlow's advantage is numerically meaningful under alternative configurations. A paper cannot claim robustness on the basis of unwritten tables. These must be populated with actual experimental data before the paper can be evaluated.

- [ ] **C3. Budget regime compiler is unspecified.** Section 3.2 describes the compiler in purely abstract terms---"produces a regime," "partitions the budget into allocation tiers"---but provides no algorithm, no pseudocode, no mathematical formulation, and no concrete instantiation used in the experiments. A reader cannot implement the compiler from the paper, cannot assess whether it is well-defined, and cannot evaluate whether the claimed auditability is real or aspirational. The compiler is listed as one of two core components (Section 3) and as a key differentiator in the positioning table (Section 2.4), yet it is a black box.

- [ ] **C4. Equal-value results not numerically reported.** The draft states (Section 5.3) that BudgetFlow "matches or exceeds T3-only on pass count and exceeds both baselines on Yield and Yield/$" under the equal-value profile. This is the single most important sensitivity check, because equal value removes the signal the policy uses to prioritize. If BudgetFlow still wins, it suggests the regime compiler is doing structural work independent of value. If BudgetFlow does not win, value registration is the entire story. Either way, the actual numbers must be shown. The current directional prose is insufficient.

- [ ] **C5. Value registration scheme is hand-assigned and not defended.** The value annotations (normal=1.0, high=1.5, critical=2.5) are human-assigned. The paper acknowledges this as a threat to validity (north_star.md) but provides no inter-annotator agreement, no sensitivity to alternative value mappings, and no justification for the specific multipliers chosen. The Devil's Advocate question---"is the value registration scheme doing all the work?"---cannot be answered from the current draft.

---

## MAJOR Issues

- [ ] **M1. Single workload, single benchmark.** All experiments use one fixed 30-task batch from SWE-bench. Results may not generalize to different task distributions, different domains, different verification criteria, or different model families. The paper acknowledges this limitation (Section 6.4) but does not mitigate it. At minimum, results on a second workload or a different task distribution would substantially strengthen the claim.

- [ ] **M2. T3-only does not reach the budget cap.** T3-only spends $5.8303 against a $6.0000 cap, leaving $0.1697 unspent. The paper argues this is not a policy failure (Section 6.2), but the fact remains that T3-only is not budget-saturated. This means the comparison is not between two policies operating at the same budget utilization. A T3-only variant that uses the remaining budget (e.g., retrying failed tasks with T3, or executing an additional task) could close or reverse the gap. The authors should either tighten the cap so both policies are saturated, or add a T3+retry baseline that consumes the full cap.

- [ ] **M3. No ablation of the regime compiler vs. the runtime policy.** The two components (compiler + runtime) are presented as a package. It is impossible to tell whether the gain comes from the compiler's allocation plan, the runtime's per-task model selection, or their interaction. An ablation that replaces the compiler with a uniform allocation and tests the runtime policy alone (or vice versa) would clarify where the mechanism lives.

- [ ] **M4. Model tiers T2/T3 are opaque.** The paper uses normalized tier slots T2 and T3 but never specifies what physical models they correspond to, what their token prices are, or what capability gap exists between them. This makes it impossible to assess whether the result depends on a specific price/capability ratio. A reader cannot determine whether BudgetFlow would work with a different pair of models.

- [ ] **M5. No code or artifact availability statement.** There is no link to code, no reproducibility checklist, no mention of whether the budget regime compiler implementation, runtime policy, or experimental harness will be released. For a systems paper claiming auditable budget governance, the absence of an artifact commitment is a significant weakness.

- [ ] **M6. The "Cost Is Not Token Price" argument (Section 5.2) is undersupported.** The paper claims that "a nominally cheaper model can become more expensive when it takes more turns or stalls" but provides no turn-count data, no stall-rate data, and no per-task cost breakdown to support this claim. Table 1 shows only aggregate costs. The reader cannot verify that T2 tasks systematically took more turns than T3 tasks on the same problems.

- [ ] **M7. Task order is fixed but not disclosed or analyzed.** The paper states tasks are executed in fixed order across all policies (Section 4.1) but does not provide the order, discuss whether it is randomized or sorted, or analyze whether order effects (e.g., budget depletion hitting high-value tasks late in the sequence) influence the result. If high-value tasks happen to appear early in the sequence, BudgetFlow's advantage may be an artifact of task ordering under budget depletion.

---

## MINOR Issues

- [ ] **m1. Reference list is incomplete and inconsistent.** The draft lists 18 references. The literature review (`literature-review.md`) and BibTeX file (`references.bib`) contain 20 references, including CoRL (Jin et al., 2025) and FutureWeaver (Jung et al., 2025), which are absent from the draft. Several references ([3] Ding et al., [4] Aggarwal et al., [5] Guo et al., [9] Kleinman et al., [16] McCleary & Ghawaly, [17] Zhang et al., [18] Moslem & Kelleher) lack arXiv IDs, venue information, or both, making them difficult to verify.

- [ ] **m2. Positioning table differs between draft and literature review.** The literature review's positioning table includes a row for CoRL / FutureWeaver (multi-agent per-task) that is absent from the draft's Section 2.4. If these are relevant enough for the lit review, they should appear in the paper, or their exclusion should be justified.

- [ ] **m3. The "Yield" metric is not normalized.** Yield is defined as the sum of pre-registered values of passing tasks. Since value annotations are on an arbitrary scale (normal=1.0, high=1.5, critical=2.5), Yield is not comparable across different value profiles. The paper reports Yield numbers (21.0, 18.5, 14.5) without clarifying that these depend on the specific value mapping. A normalized metric (e.g., Yield / maximum possible Yield given the value profile) would be more interpretable.

- [ ] **m4. Abstract reports Yield/$ to 4 decimal places but pass count is integers.** This precision mismatch (3.5000 vs. 17) is jarring and implies measurement precision that is not justified by the single-run design.

- [ ] **m5. "Directional advantage" language is vague.** The phrase appears repeatedly in Section 5.3 ("directionally achieves," "directional ordering persists," "directional advantage") as a hedge for missing numerical results. This language should be replaced with actual numbers or removed.

- [ ] **m6. Section 4.2 budget cap description is circular.** "The cap is chosen to be active: T2-only and BudgetFlow reach the full $6.0000 cap, while T3-only finishes at $5.8303." This describes the outcome of the cap choice, not the principle by which the cap was set. The north_star.md specifies a target utilization regime (~80-90%) and a Strongest Model runway floor, but the draft itself does not explain how $6.0000 was derived.

- [ ] **m7. The paper claims "17/30 pass" but SWE-bench verification is binary per task.** There is no discussion of partial credit, test-level granularity, or whether the 17 passes represent 17 distinct tasks vs. possibly overlapping passes across policies. The per-task pass/fail mapping across policies should be reported (e.g., a Venn diagram or confusion matrix of which tasks each policy solved).

- [ ] **m8. No discussion of compute cost for the budget regime compiler itself.** If the compiler requires calibration runs, those runs consume budget and compute. The paper should account for the compiler's own cost in the total resource picture, or explicitly state that compiler calibration is amortized over many batches.

- [ ] **m9. Abstract and introduction claim "Yield/$ 3.5000" without noting it is value-profile-dependent.** The Yield/$ number is a function of the chosen value mapping (normal=1.0, high=1.5, critical=2.5). A different mapping would produce a different Yield/$ even with identical pass patterns. This dependence should be surfaced early, not buried in Section 6.4.

---

## Weakness Routing

| Issue | Target Phase | Action |
|-------|-------------|--------|
| C1 (single-run, no statistics) | Phase 4 (empirical) | Run multiple seeds; add variance/CIs; statistical test BudgetFlow vs. T3 |
| C2 (placeholder tables) | Phase 4 (empirical) | Populate Tables 2-4 with actual sensitivity data |
| C3 (compiler unspecified) | Phase 5 (drafting) | Add algorithm/pseudocode/concrete instantiation to Section 3.2 |
| C4 (equal-value numbers) | Phase 4 (empirical) | Report full equal-value results numerically in Section 5.3 |
| C5 (value scheme defense) | Phase 4+5 | Report sensitivity to value mapping; justify multipliers |
| M1 (single workload) | Phase 4 | Add second workload or task distribution |
| M2 (T3 below cap) | Phase 4 | Tighten cap or add T3+retry baseline |
| M3 (no ablation) | Phase 4 | Ablate compiler vs. runtime policy |
| M4 (opaque tiers) | Phase 5 | Disclose model identity and price/capability ratio |
| M5 (no artifact) | Phase 5+8 | Add reproducibility statement and artifact link |
| M6 (no turn data) | Phase 4 | Report per-task turn counts and cost breakdowns |
| M7 (task order) | Phase 5 | Disclose and analyze task order effects |
| m1-m9 (minor) | Phase 5 | Fix references, metrics, precision, and prose |

---

## Reviewer 1: Methodology and Experimental Design

**Score: 3 (Weak Reject)**

### Strengths
- The experimental question is clearly stated: does value-aware allocation achieve higher Yield and Yield/$ than uniform-tier baselines under a fixed shared hard budget?
- The baseline selection (T2-only, T3-only) is clean and avoids straw-man comparisons. Both baselines represent real deployment choices.
- The sensitivity dimensions (KV-cache discount, value profile, budget cap) are well-chosen and address plausible threats to the main result.
- The metrics (Yield, Yield/$, Pass count, Total Cost) are appropriate for the claim, and the paper correctly identifies Yield as the primary metric.
- The task batch is fixed across conditions, eliminating task-selection confounds.

### Weaknesses
- **CRITICAL.** The experiment consists of a single run of 30 tasks. There is no variance estimate, no confidence interval, no statistical test, and no multiple random seeds. A delta of 1 pass out of 30 (17 vs. 16) is well within the range of sampling noise. The authors cannot establish Claim 1 on this evidence. Standard practice in LLM agent evaluation requires either multiple runs with variance reporting or a workload large enough that the effect size exceeds reasonable noise thresholds.
- **CRITICAL.** All sensitivity tables (Tables 2-4) are placeholders with directional prose. The paper claims robustness but provides no numbers to evaluate that claim. This alone would prevent acceptance at any venue that requires empirical evidence.
- **MAJOR.** No ablation separates the budget regime compiler from the runtime policy. The two components are presented as a package, making it impossible to attribute the (small) observed gain to either mechanism.
- **MAJOR.** T3-only does not saturate the budget cap ($5.8303 vs. $6.0000), which means the baseline is not operating under the same effective constraint. The authors should either tighten the cap so all policies are binding, or introduce a T3 baseline that uses the residual budget productively.
- **MAJOR.** The model tiers T2 and T3 are never specified. Without knowing the price ratio and capability gap, the reader cannot assess whether the result depends on a particular model pair or would generalize.
- **MAJOR.** No per-task cost or turn-count breakdown is provided. The "cost is not token price" argument (Section 5.2) requires showing that T2 tasks systematically consume more turns than T3 tasks on the same problems. Aggregate costs cannot support this claim.
- **MINOR.** Task order is fixed but undisclosed. If high-value tasks appear early in the sequence, BudgetFlow's allocation advantage may be an artifact of budget depletion dynamics rather than value-aware decision-making.

### Questions for Authors
1. What is the variance of pass count and Yield across multiple random seeds? Can you reject the null hypothesis that BudgetFlow and T3-only have the same expected Yield?
2. What are the physical models behind T2 and T3, and what is their per-token price ratio?
3. What fraction of BudgetFlow's gain comes from the compiler's allocation plan vs. the runtime's per-task model selection?
4. If you randomize task order, does BudgetFlow's advantage persist?
5. How many turns did T2 tasks consume on average compared to T3 tasks on the same problems?

---

## Reviewer 2: Theory and Related Work Coverage

**Score: 4 (Weak Accept)**

### Strengths
- The three-cluster organization (cascade routing, inference-time budget control, explainable/agent-level routing) is clean and covers the relevant literature landscape.
- The four-property desideratum is crisp and provides a clear test for whether any existing system subsumes BudgetFlow. The positioning table (Table in Section 2.4) makes the gap visually obvious.
- The paper correctly identifies that no existing system combines shared hard budget, pre-registered value, verified outcomes, and auditable budget compilation.
- The discussion of individual papers is accurate and fair. FrugalGPT, RouteLLM, UCCI, Topaz, BCAS, INTENT, BATS, and AVA are each characterized correctly with respect to their decision unit, budget scope, and limitations.
- The BAR Conjecture citation (Zhou et al., 2025) provides useful formal grounding for the impossibility of simultaneous optimization along all dimensions.
- The related work boundary in north_star.md correctly positions UCCI and Topaz as Claim 2 neighbors rather than Claim 1 competitors.

### Weaknesses
- **MAJOR.** The reference list in the draft omits CoRL (Jin et al., 2025) and FutureWeaver (Jung et al., 2025), both of which appear in the literature review and BibTeX file. These are the only works addressing multi-agent budget coordination, and their exclusion from the draft creates a gap in the multi-agent section of the related work coverage. Either include them or explain their exclusion.
- **MAJOR.** The positioning table in the draft (Section 2.4) is a simplified version of the table in the literature review. The literature review includes a separate row for CoRL/FutureWeaver (multi-agent per-task) and uses "Task success (binary)" for INTENT/BATS/AVA. The draft merges these distinctions. The richer table from the literature review should be used.
- **MINOR.** Several references lack arXiv IDs or venue information ([3] Ding et al., [4] Aggarwal et al., [5] Guo et al., [9] Kleinman et al., [16] McCleary & Ghawaly, [17] Zhang et al., [18] Moslem & Kelleher). At minimum, arXiv IDs should be provided for verifiability.
- **MINOR.** The survey by Moslem & Kelleher (2026) is cited but its taxonomy (eight routing paradigms, three-dimensional conceptual framework) is not used to situate BudgetFlow. Engaging with the survey's framework would strengthen the positioning.
- **MINOR.** The paper claims BudgetFlow "may spend more when expected verified value justifies the spend" (Section 1, Section 6.2) but the related work section does not discuss any prior work on value-of-information or expected value of computation in the context of LLM routing. This connection to decision theory would enrich the theoretical framing.

### Questions for Authors
1. Why are CoRL and FutureWeaver excluded from the draft's reference list when they appear in the literature review?
2. Can you map BudgetFlow onto the Moslem & Kelleher (2026) three-dimensional framework (when, what, how) to clarify its architectural decisions?
3. The paper uses pre-registered human-assigned values. Is there any connection to the value-of-information literature or decision-theoretic allocation that could ground this choice theoretically?

---

## Reviewer 3: Data, Citations, and Reproducibility

**Score: 3 (Weak Reject)**

### Strengths
- The 30-task SWE-bench workload is a standard benchmark, which aids reproducibility in principle.
- The task batch is fixed across all runs, eliminating data leakage concerns from dynamic task selection.
- The value annotation scheme (normal=1.0, high=1.5, critical=2.5) is explicitly stated, which is better than leaving it unspecified.
- The metrics (Yield, Yield/$, Pass count, Total Cost) are clearly defined and directly measurable from experimental outputs.
- The BibTeX file exists and is largely complete, which is a positive sign for eventual artifact release.

### Weaknesses
- **CRITICAL.** The paper's central numerical result (Table 1) is a single observation with no variance information. A reader cannot assess whether 17/30 vs. 16/30 is a meaningful difference or sampling noise. Reproducibility requires more than one run.
- **CRITICAL.** All sensitivity tables are empty. The paper is essentially an incomplete draft from a data perspective. The claim of robustness across KV-cache levels, value profiles, and budget caps is unsupported.
- **MAJOR.** Six of 18 references ([3], [4], [5], [9], [16], [17], [18]) lack arXiv IDs or DOIs. Two references that appear in the BibTeX file and literature review (CoRL, FutureWeaver) are absent from the draft. The reference list is both incomplete and inconsistent with the project's own supporting materials.
- **MAJOR.** There is no code repository link, no artifact availability statement, no reproducibility checklist, and no mention of whether the budget regime compiler or runtime policy will be open-sourced. For a paper whose contribution includes "auditable budget compilation," the absence of auditability for the paper's own artifacts is a credibility problem.
- **MAJOR.** The internal consistency of the numbers in Table 1 is questionable. Yield/$ = Yield / Cost. For T2-only: 14.5 / 6.0000 = 2.4167 (consistent). For T3-only: 18.5 / 5.8303 = 3.1731 (consistent). For BudgetFlow: 21.0 / 6.0000 = 3.5000 (consistent). However, the relationship between Yield and pass count depends on the value profile. With 17 passes yielding 21.0, the average value per passing task is 21.0/17 = 1.235. With 16 passes yielding 18.5, the average is 18.5/16 = 1.156. With 12 passes yielding 14.5, the average is 14.5/12 = 1.208. These differing averages suggest BudgetFlow is passing tasks with higher average value, which is the intended mechanism, but also means the result is sensitive to which specific tasks pass. A single-task swap (BudgetFlow passing a critical-value task that T3-only fails) could account for the entire Yield gap. The authors should report which tasks passed under each policy and their individual values.
- **MINOR.** The abstract reports Yield/$ to 4 decimal places (3.5000, 2.4167, 3.1731) while the underlying measurements are from a single run of 30 binary-outcome tasks. This precision is not justified.
- **MINOR.** The paper claims the budget cap is "chosen to be active" but does not explain the procedure. The north_star.md specifies a target utilization regime and a Strongest Model runway floor, but the draft itself provides no derivation of the $6.0000 figure.

### Questions for Authors
1. Can you provide a per-task pass/fail matrix showing which of the 30 tasks each policy solved, along with each task's pre-registered value?
2. What is the pass count and Yield if you run the experiment with 5 or 10 different random seeds?
3. Will the budget regime compiler implementation, runtime policy, and experimental harness be released as open source?
4. How exactly was the $6.0000 budget cap derived? What was the target utilization, and what calibration data informed it?

---

## Devil's Advocate Assessment

**Score: 3 (Weak Reject)**

### Standing CRITICAL? **YES**

Three facts, taken together, mean Claim 1 is not established:

1. **The margin is one task.** 17/30 vs. 16/30. On a 30-task batch, this is a 3.3 percentage point difference. No statistical test is provided. The binomial probability of observing a >=1 task advantage for BudgetFlow under the null hypothesis that both policies have identical per-task pass probability p=16/30 is approximately 0.5---flipping a coin. This is not evidence.

2. **The value registration scheme can produce the result by construction.** The paper uses human-assigned values (normal=1.0, high=1.5, critical=2.5). If BudgetFlow's runtime policy preferentially assigns T3 to critical-value tasks and T2 to normal-value tasks, and if T3 has any capability advantage on those tasks (which it must, or T3-only would not outperform T2-only), then BudgetFlow will mechanically achieve higher Yield than T3-only even if it solves exactly the same set of tasks, simply because its pass set is tilted toward higher-value tasks. The paper does not report which tasks passed under each policy, so we cannot rule out that BudgetFlow and T3-only solve the same 16 tasks plus BudgetFlow solves one additional normal-value task---which would produce a Yield delta much smaller than the reported 2.5. The reported Yield gap (21.0 vs. 18.5 = +2.5) is suspiciously close to the delta between a critical task (2.5) and a normal task (1.0), suggesting the gap may be driven by a single high-value task that T3-only failed.

3. **The budget regime compiler is a black box that could encode the answer.** Without an algorithm specification, the compiler could be implementing anything from "allocate uniformly" to "give T3 to every task with value > 1.0." If the latter, BudgetFlow is just T3-only with a value filter, and the claimed "value-aware allocation" reduces to a threshold rule on hand-assigned values. The paper provides no evidence that the compiler does anything more sophisticated.

### Conceded Claims

The paper does not concede these points explicitly, but the limitations section (6.4) acknowledges:
- Single workload (SWE-bench only)
- Human-assigned values (acknowledged as a threat in north_star.md)
- Claim 2 is entirely parked

### Alternative Explanations for the Results

1. **Sampling noise.** With 30 Bernoulli trials per policy, the standard error of the pass rate is approximately sqrt(p*(1-p)/30) ~ 0.086 for p=0.53, giving a 95% CI of roughly +/- 5 passes. The observed 1-pass difference is deep inside the noise floor.

2. **Task ordering under budget depletion.** If high-value tasks appear early, BudgetFlow spends budget on them with T3 and succeeds, then runs low on budget for later tasks. T3-only also spends on early tasks but may waste expensive capacity on low-value early tasks, leaving less budget for high-value late tasks. The relative performance depends entirely on the interaction between task order and value distribution. The paper does not report or analyze this.

3. **The regime compiler is selecting on the dependent variable.** If the compiler uses any information correlated with task difficulty (e.g., historical pass rates, repo characteristics, issue length), it may be assigning T3 to tasks that are easier for T3 to solve, rather than tasks that are higher-value. The paper claims value is pre-registered and independent of difficulty, but provides no evidence that value and difficulty are uncorrelated in the chosen task batch.

4. **T3-only's unspent budget ($0.1697) could change the result.** If T3-only used that residual budget to retry its highest-value failed task with a different prompt or more turns, it might close or reverse the 1-pass gap.

### Verdict

The core premise---that shared-budget value maximization is a distinct and important problem---is compelling. But the experimental evidence does not establish that BudgetFlow solves it. The result is consistent with noise, with a threshold rule on hand-assigned values, and with task-ordering artifacts. To establish Claim 1, the authors need: (a) statistical evidence that the effect is real, (b) demonstration that the regime compiler adds value beyond a simple value-threshold rule, (c) per-task pass/fail transparency, and (d) evidence that the result is not an artifact of task ordering.

---

## Detailed Questions for Authors (Consolidated)

1. **Statistical significance:** What is the p-value for the hypothesis that BudgetFlow and T3-only have equal expected Yield? Report results from at least 5 random seeds or bootstrap resamples.

2. **Per-task transparency:** Provide a table mapping each of the 30 tasks to its value, which policy passed it, and its cost under each policy. This is essential for readers to assess whether the Yield gap is driven by value-tilted pass sets rather than more passes.

3. **Compiler specification:** Provide pseudocode or a formal description of the budget regime compiler used in the experiments. What inputs does it consume? What optimization does it solve? How are tiers defined?

4. **Value sensitivity:** Report the equal-value results numerically. If BudgetFlow outperforms T3-only under equal value, explain what mechanism produces the gain when value signal is absent.

5. **Task ordering:** Report whether task order was randomized. If not, provide the order and analyze whether BudgetFlow's advantage depends on the position of high-value tasks in the sequence.

6. **Model disclosure:** What physical models correspond to T2 and T3? What are their per-token prices and relative capabilities?

7. **Ablation:** What is the separate contribution of the regime compiler vs. the runtime policy? Report results with the runtime policy operating under a uniform budget allocation (no compiler).

8. **Artifact release:** Will code, configuration files, value matrices, budget plans, and experimental harness be released?

---

*Review generated by Phase 6a peer review coordinator (multi-role: EIC + R1-R3 + DA).*
