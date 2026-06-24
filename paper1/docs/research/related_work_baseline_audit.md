# Related Work Baseline Audit — BudgetFlow Claim 1

**Date:** 2026-06-25
**Scope:** 7 papers — FrugalGPT, RouteLLM, UCCI, Topaz, INTENT, BATS, RouteNLP
**Method:** All papers read in full from original sources (arXiv HTML/PDF via
`arxiv_read_paper`). No second-hand summaries.

## Reader Notes

This audit was originally written from the literature-review and draft summaries
(second-hand). After the main agent flagged that original-paper reading was
necessary, all six papers were re-read in full. Key corrections from the
original reading:

- **FrugalGPT:** Budget is E[cost] ≤ b (soft average), not a hard cap. The
  DistilBERT scorer needs per-task (query, answer, correctness) training triples
  we do not have for SWE-bench agent tasks. Baselines are individual LLMs only
  — no comparison against other routers.
- **RouteLLM:** Trained on Chatbot Arena human preference data ("which model
  wins?"), not on task correctness. Cost is "% queries routed to strong model,"
  not actual dollars. No hard budget — an alpha threshold sweeps the tradeoff.
  Four router architectures with full training details.
- **UCCI:** Strictly per-query, no batch constraint. Two-model cascade (4B/12B)
  with isotonic regression calibration on token-margin uncertainty. Evaluated
  on a single proprietary NER workload only. Assumes large-model accuracy is
  invariant to which queries are escalated.
- **Topaz:** CHI 2026 HCXAI Workshop paper. No empirical baselines against
  routing systems. One 6-task case study. DP formulation in appendix with no
  results. Model skill profiles derived from LLM-profiled benchmarks, not
  execution data.
- **INTENT:** Per-task monetary budget (credit units), no cross-task allocation.
  Explicitly rejects MCTS in favor of single-trajectory lookahead. Learned
  world model (Qwen2.5-3B) + intention predictor trained on ~186k tool
  interaction trajectories.
- **BATS:** Per-question per-tool call-count budget. Budget Tracker is pure
  prompt-level text injection. "Dig deeper" vs "Pivot" via self-verification
  module. Unified cost is post-hoc only. Web search QA domain.
- **RouteNLP:** Solves the **inverse** problem: minimize cost subject to
  per-task quality constraints, not maximize value under a budget. No DP, no
  budget cap, no cross-task allocation. ACL 2026 Industry Track with 8-week
  enterprise pilot (~5K queries/day). Four-tier conformal cascade with
  distillation co-optimization. 0.971 quality retention at 0.159 cost ratio.
  Closest deployment-level neighbor but fundamentally different optimization
  objective.

**Bottom line:** RouteLLM is the strongest baseline candidate by a wide margin,
but the adaptation gap (human preference data → task success data) is real.
Topaz's DP mode is the best theoretical baseline but calling it "Topaz-style"
may overstate the connection to a workshop paper with no empirical routing
results. UCCI belongs in Claim 2 mechanism analysis, not Claim 1 baselines.
FrugalGPT, INTENT, and BATS are not viable Claim 1 baselines.

---

## 1. Executive Summary

### Recommended for priority implementation (1 baseline)

1. **Learned task router (RouteLLM-inspired)** — Train a classifier on frozen
   task features to predict T2 vs T3 per task. This is the most direct
   head-to-head: "does value-aware allocation beat a supervised ML router?"
   Highest reviewer credibility because RouteLLM is the canonical router paper.
   **Important caveat:** RouteLLM trains on human preference data (Chatbot
   Arena), not task success. Our adaptation trains on (task_features →
   T3_worth_it) from historical diagnostic data. This is a material deviation
   and must be disclosed as "RouteLLM-inspired" not "RouteLLM."

### Consider for implementation (1 additional baseline)

2. **Knapsack DP allocation (Topaz-inspired)** — Pre-compute per-task (expected
   value, expected cost) for T2/T3, then run value-weighted 0/1 knapsack DP to
   assign tiers under the shared cap. Tests whether BudgetFlow's runtime
   adaptive allocation beats optimal static (oracular) assignment. **Caveat:**
   Topaz is a workshop paper with no empirical routing results; the DP is a
   textbook algorithm, not unique to Topaz. Frame as "static oracle DP" rather
   than "Topaz baseline."

### Not recommended (5 papers)

3. **FrugalGPT** — Soft average budget E[cost] ≤ b, not hard cap. DistilBERT
   scorer needs (query, answer, correctness) triples per task type. No
   value-awareness. The cascade adaptation ("T2-first, escalate on stall") is
   a stall-guard heuristic, not FrugalGPT.

4. **UCCI** — Valuable Claim 2 mechanism (calibrated Model Fit), not a
   standalone Claim 1 policy. Reducing it to a baseline creates a confound:
   "better calibration" vs. "different allocation."

5. **INTENT** — Wrong decision unit (within-task tool planning). Adapting would
   require building a Qwen2.5-3B world model + intention predictor for SWE-bench
   tasks (~186k training trajectories needed), then repurposing the lookahead
   for cross-task tier selection. Disproportionate engineering; tests the wrong
   question.

6. **BATS** — Core insight (budget awareness enables scaling) already designed
   into BudgetFlow. Budget Tracker = prompt-level text. Per-task tool-call caps
   ≠ cross-task shared budget. Already covered by per-task-cap diagnostic
   controls.

7. **RouteNLP** — Solves inverse problem (minimize cost s.t. quality ≥ τ, not
   maximize value s.t. cost ≤ B). No DP, no budget cap, no cross-task
   allocation, no task value. Four-tier conformal cascade + distillation
   co-optimization. Valuable as a deployment-scale neighbor in Related Work
   (§2.1), not as a Claim 1 baseline.

---

## 2. Candidate Baseline Table

| Paper | Original Decision Unit | Original Metric | Original Budget Type | Adapted Policy Idea | Required Inputs | Code Integration Points | Fairness Risks | Complexity | Recommendation |
|---|---|---|---|---|---|---|---|---|---|
| **FrugalGPT** (Chen 2023) | Per-query | Accuracy, cost ($) | Soft average: E[cost] ≤ b | T2-first cascade, escalate on no-progress | Per-turn progress signal, stall threshold, budget remaining | `strategies.py` new branch + mid-task escalation hook in agent loop | Mid-task escalation ≠ task-level commitment; no quality scorer for agent tasks; soft avg budget ≠ hard cap | Medium | **No** — wrong budget model, no value-awareness, scorer needs data we lack |
| **RouteLLM** (Ong 2024) | Per-query | CPT(x%), PGR, cost (%) | None (α threshold on P(win)) | Classifier: task features → T2/T3 (trained on historical pass data, not preference data) | Frozen task features, historical T2/T3 pass data, budget remaining | `strategies.py` new branch or `FrozenRouterPlan` pre-computed; offline training script | Train/test split critical; trains on pass data not preference data (material deviation); no value-awareness in original | Medium | **Yes** — strongest head-to-head; must disclose adaptation gap |
| **UCCI** (Kotte 2026) | Per-query | Micro-F1, ECE, cost (H100 latency) | None (cost minimization s.t. F1 ≥ τ) | Calibrated Model Fit → threshold T2/T3 | Calibrated fit scores via isotonic regression, same-catalog historical data | `AllocationContext.model_fit` population in `compare_execution.py`; new `calibrated_fit.py` | Calibration needs historical data; reduces to "better Model Fit" not new policy | Medium-High | **No for Claim 1** — Claim 2 mechanism (calibrated fit estimation) |
| **Topaz** (Okamoto 2026) | Per-subtask | Match score, cost ($) | Soft parameter c_global∈[0,1] OR hard cap B for DP (appendix only) | Value-weighted 0/1 knapsack DP over (task, tier) pairs | Per-task E[pass] and E[cost] for T2/T3, shared cap B | Pre-run DP solver → `FrozenRouterPlan` → existing `enterprise_router` path | DP has oracle advantage (sees all tasks upfront); expected costs ≠ actual costs; Topaz itself has no empirical routing results | Medium | **Yes** — but frame as "static oracle DP" not "Topaz baseline" |
| **INTENT** (Liu 2025a) | Per-task | Pass rate, feasible rate, avg cost (credit units) | Per-task hard monetary budget (B=50 credits) | Not adaptable as cross-task baseline | N/A | N/A | Wrong decision unit; would need world model (Qwen2.5-3B) + ~186k training trajectories for SWE-bench | Very High | **No** — wrong unit, massive engineering |
| **BATS** (Liu 2025b) | Per-question | Accuracy, unified cost (cents) | Per-question per-tool call-count cap | Per-task cap with agent budget awareness (prompt-level) | Per-task cap, budget text injected into agent prompt | `compare_execution.py` per-task cap mode (exists) + modify agent prompt template | Tests per-task caps, not shared-budget allocation; different research question | Low (infra exists) | **No** — already covered by per-task-cap controls |
| **RouteNLP** (Guo 2026) | Per-query (4-tier cascade) | Quality Ratio, Cost Ratio, p99 latency, SLA viol. rate | None (per-task quality floor τ_t; minimize cost) | Not adaptable — solves inverse problem | N/A | N/A | Inverse objective (min cost s.t. quality ≥ τ vs max value s.t. cost ≤ B); no DP/budget/task-value; per-query not cross-task | N/A | **No** — wrong optimization direction; closest deployment neighbor for Related Work §2.1 |

---

## 3. Per-Paper Audit

### 3.1 FrugalGPT (Chen et al., 2023, arXiv:2305.05176)

#### A. Original Paper Facts

- **Problem:** Reduce LLM inference cost while maintaining or improving
  performance. Observes that different queries need different model strengths
  and that the best individual LLM varies by query.
- **Decision unit:** Per-query. Each query processed independently.
- **Baselines:** 12 individual LLM APIs only — GPT-4, GPT-3, ChatGPT, GPT-Curie
  (OpenAI); J1-Large, J1-Grande, J1-Jumbo (AI21); Xlarge (Cohere); QA
  (ForeFrontAI); GPT-J, FAIRSEQ, GPT-Neox (Textsynth). **No comparison against
  other cascade/routing systems.** The paper predates RouteLLM, HybridLLM, etc.
- **Metrics:**
  - Accuracy: fractional correctness of generated answer vs. ground truth
    (exact-match for the classification/QA datasets used).
  - Cost ($): per-API pricing with 3 components — cost_per_output_token ×
    ||output|| + cost_per_input_token × ||input|| + fixed_per_request_cost.
  - Maximum Performance Improvement (MPI): P(A correct, B incorrect) —
    pairwise complementarity metric for diversity analysis only.
- **Budget type:** Soft average constraint: E[cost(s, q)] ≤ b. The expectation
  is over the query distribution. Individual queries can exceed b as long as
  the average holds. **Not a hard cap, not a shared budget, not per-batch.**
- **Inputs to routing policy:**
  - Query text q and LLM-generated answer f_i(q) (concatenated).
  - DistilBERT regression model (66M params, ~257× smaller than GPT-3):
    concatenation of query + answer → scalar score ∈ [0,1] predicting
    correctness.
  - Two thresholds T1, T2 (learned via specialized mixed-integer optimizer).
  - Cascade list L = [L1, L2, L3] (3 LLMs, ordered cheapest → most expensive).
- **Output:** Return cheapest LLM's answer whose score ≥ threshold; if none,
  fall through to L3 (most expensive).
- **Cascade algorithm (exact):**
  ```
  Input: query q, cascade L=[L1,L2,L3], thresholds T=[T1,T2], scorer g
  1. answer = f_{L1}(q); score = g(q, answer)
  2. if score >= T1: return answer
  3. answer = f_{L2}(q); score = g(q, answer)
  4. if score >= T2: return answer
  5. return f_{L3}(q)
  ```
- **Datasets:** HEADLINES (finance, 10K, 4-class), OVERRULING (law, 2.4K,
  binary), COQA (reading comprehension, 7,982, extractive QA). All are
  classification/extractive with short answers — nothing like SWE-bench agent
  tasks.
- **Scorer training:** DistilBERT with regression head. Trained on (query,
  LLM_answer, correctness_label) triples from same distribution as test.
  Training details (epochs, batch size, LR) not reported in paper.
- **Value-awareness:** None. All queries treated identically.

#### B. BudgetFlow-Compatible Adaptation

**Adaptation concept:** T2-first, escalate-to-T3 on no-progress signals. Each
task starts on T2. After N turns without progress (no file edits, no test
passes), escalate to T3. Shared budget cap gates all spend.

**Why this is NOT FrugalGPT:**
1. FrugalGPT's budget is E[cost] ≤ b (soft average). Ours is a hard shared cap
   depleting in real time. These are different constraint types.
2. FrugalGPT's scorer (DistilBERT) judges answer quality from (query, answer)
   text. SWE-bench agent tasks have no intermediate "answer" to score before
   verification. The natural substitute — no-progress streak — is a stall guard,
   not a quality scorer.
3. FrugalGPT cascades through 3+ models with a fixed order. Our adaptation uses
   exactly 2 models (T2→T3) with a different escalation trigger.
4. FrugalGPT has no value-awareness. All queries are equal.

**Shared-cap handling:** Under a shared hard cap, the cascade starts every task
on T2. If budget is exhausted mid-task, the task fails (same as all policies).
The cascade has a structural advantage: it gets to "sample" T2 cheaply and only
commit to T3 after observing T2 behavior. BudgetFlow task-level must commit
upfront. This is a legitimate comparison ("does upfront commitment lose to
try-then-escalate?") but is really a test of task-level vs. stage-aware routing,
not FrugalGPT vs. BudgetFlow.

**Required inputs:**
- Per-turn progress signal (binary: made progress / no progress).
- Stall threshold N (needs pre-registration to avoid tuning on eval).
- T2 and T3 per-turn costs.
- Remaining shared budget.

**Code integration:**
- New strategy branch `"cascade_stall"` in `strategies.py:choose_backend()`.
  Task start returns T2.
- Mid-task escalation hook: reuse the existing per-turn routing path (used by
  `budgetflow_segment` strategies) to re-evaluate tier choice each turn.
- `compare_execution.py`: no changes needed (strategy dispatch handles it).

**Fairness risks:**
- Mid-task escalation breaks task-level design. The cascade can adapt to
  within-task signals; BudgetFlow task-level cannot. Comparisons across this
  boundary must be explicit about the extra degree of freedom.
- Stall threshold N can be tuned to favor either side. Must pre-register.
- Under a very tight cap, the cascade ≈ pure T2 (early tasks exhaust budget
  before any escalation triggers), making the comparison uninformative.

**Implementation complexity:** Medium. Per-turn routing path exists. Main work
is defining the escalation condition and ensuring it's auditable.

**Recommendation:** **No — wrong budget model, no value-awareness, and the
adaptation tests a different question (task-level vs. stage-aware) than what
FrugalGPT actually studied.** If needed as a diagnostic, label it "stall-
escalation cascade" not "FrugalGPT baseline" and position it as a Claim 2
mechanism variant, not a Claim 1 baseline.

---

### 3.2 RouteLLM (Ong et al., 2024, arXiv:2406.18665)

#### A. Original Paper Facts

- **Problem:** Route each query to the most appropriate LLM (strong vs. weak)
  for cost-quality tradeoff. Unlike cascades, RouteLLM queries ONE model per
  input and must decide upfront based on the query text alone.
- **Decision unit:** Per-query. One query → one model call.
- **Baselines:**
  - Random router (internal baseline).
  - Academic: LLM-Blender, FrugalGPT, AutoMix, HybridLLM, Zooter (discussed in
    Related Work, not all run head-to-head).
  - Commercial: Unify AI (best config from dashboard), Martian (optimized for
    max $10.45/M tokens, 1:1 input:output, 50% GPT-4 calls). RouteLLM matched
    performance with up to 40% fewer GPT-4 calls vs. both.
- **Metrics:**
  - c(M_R^α) = fraction of queries routed to strong model (= cost proxy).
  - r(M_R^α) = average response quality over all queries.
  - PGR (Performance Gap Recovered) = (r(router) − r(weak)) / (r(strong) − r(weak)).
    PGR=1 → router matches strong model; PGR=0 → matches weak model.
  - APGR = integral of PGR over all cost levels (area under cost-performance curve).
  - CPT(x%) = minimum % strong-model calls to recover x% of the quality gap.
    CPT(50%)=13.4% on MT Bench means 13.4% GPT-4 calls recover 50% of the gap.
- **Budget type:** No actual budget. Cost-quality tradeoff parameterized by a
  single α ∈ [0,1] threshold. α=0 → all queries to strong model. α=1 → all
  queries to weak model. CPT metrics are aggregate, not binding constraints.
  **No shared budget. No hard cap. No dollar costs in routing decision.**
- **Router architecture (4 variants):**
  1. **SW Ranking:** Cosine similarity (text-embedding-3-small) to training
     queries + Bradley-Terry coefficients. No training. γ=10.
  2. **Matrix Factorization:** Bilinear model/query embeddings + Hadamard
     product. 8GB GPU, ~10 epochs, batch 64, Adam LR 3e-4, weight decay 1e-5.
  3. **BERT:** BERT_BASE, CLS token → logistic regression. 2×L4 24GB, ~2000
     steps, batch 16, max_seq 512, LR 1e-5, weight decay 0.01.
  4. **Causal LLM:** Llama 3 8B, instruction-following prompt with comparison
     labels as vocab tokens. 8×A100 80GB, ~2000 steps, batch 8, max_seq 2048,
     LR 1e-6.
- **Training data:** Chatbot Arena — 80K human preference battles (users submit
  prompts, receive two anonymous model responses, vote winner/tie). 5K held for
  validation. 65K after pruning short prompts. 81% English across 100+ languages.
  Models clustered into 10 tiers via DP; top 2 = strong class, tier 3 = weak
  class. **Model responses are excluded from training — only winner identities
  kept.** Result: {(q, l_{s,w})} where l ∈ {win_s, tie, win_w}.
  - Data augmentation: D_gold (MMLU validation, ~1500 samples, <2% of training),
    D_judge (GPT-4-as-judge synthetic labels).
- **Routing decision formula:**
  ```
  P_θ(win_s | q) = probability strong model beats weak model on query q
  R^α(q) = M_weak if P(win_s | q) < α else M_strong
  ```
- **Cost model:** GPT-4: $24.70/M tokens (avg), Mixtral 8x7B: $0.24/M tokens
  (Together.AI). Ratio ≈ 103×. Cost savings = inverse ratio of GPT-4 calls.
  Router overhead: BERT = $3.19/M requests (g2-standard-4, L4 GPU).
- **Datasets:** MMLU (14K), MT Bench (160), GSM8K (1K+). Default pair:
  GPT-4-1106-preview (strong) + Mixtral 8x7B (weak). Cross-model: Claude 3
  Opus/Sonnet, Llama 3.1 70B/8B.
- **Value-awareness:** None. All queries equal.

#### B. BudgetFlow-Compatible Adaptation

**Adaptation concept:** Train a task-level classifier that maps frozen task
features to T2 vs. T3 decision. The classifier learns from historical (task,
pass/fail, cost) data rather than human preference data. Under the shared cap,
the classifier routes each task; if budget exhausted, remaining tasks fail.

**Critical adaptation gaps (must be disclosed in paper):**
1. **Training signal:** RouteLLM trains on "which model do humans prefer?"
   (Chatbot Arena). We train on "which tier produced a verified pass?" (SWE-bench
   verifier). These are different constructs. Preference ≠ correctness for agent
   tasks. This is the single biggest validity concern — we are adapting the
   architecture but not the training objective.
2. **Cost model:** RouteLLM measures cost as "% queries to strong model." We
   measure cost in actual dollars/tokens. This is actually an improvement, but
   it means the α threshold doesn't directly translate.
3. **No value-awareness in original:** RouteLLM treats all queries equally. Under
   heterogeneous task values, the classifier must either ignore value (making it
   value-oblivious — which is the point of the comparison) or be extended to
   incorporate value (which would be our contribution, not RouteLLM's).
4. **Single-query vs. agent-task:** RouteLLM routes single-turn LLM calls. Our
   tasks are multi-turn agent trajectories. Task features replace query text,
   and pass/fail replaces win/loss.

**Task-start output:** The classifier outputs T2 or T3 at task start. This is
identical to BudgetFlow task-level in decision timing — both commit upfront.

**Shared-cap handling:** Each task is routed per the classifier. Remaining
budget is checked: if the classifier picks T3 but remaining budget cannot cover
expected T3 cost, the task either downgrades to T2 or fails. This is fair:
BudgetFlow also faces budget-exhaustion constraints.

**Training data requirements:**
- Historical (task_features, tier_used, pass/fail, cost) from prior diagnostic
  runs.
- **[Uncertainty]** We need counterfactual outcomes (what would have happened
  if T2 had been used on T3 tasks and vice versa). If we only have single-tier
  outcomes per task, training labels must be based on Model Fit estimates rather
  than observed counterfactuals.
- Label options: (a) "did T3 pass?" (binary, ignores T2 counterfactual);
  (b) "was T3's outcome better than T2's expected outcome?" (requires Model Fit
  estimates); (c) "was T3 worth the extra cost given pass/fail and task value?"
  (requires a value model). **[Uncertainty — needs design decision.]**

**Required inputs from runtime:**
- Frozen task features from `SwebenchTaskAdapter.features()`.
- Historical pass/fail/cost data for classifier training.
- Remaining shared budget (for budget-exhaustion stop).
- T2/T3 per-turn cost (for affordability check).

**Classifier architecture options (from simplest to most sophisticated):**
1. **Gradient-boosted tree** (XGBoost/LightGBM) on tabular task features.
   Simplest, most practical, matches the "lightweight router" spirit. No GPU
   needed.
2. **BERT on issue text** — closer to original RouteLLM but SWE-bench issue
   descriptions may not carry enough signal alone.
3. **Matrix factorization** — if we treat tasks and tiers as the two dimensions,
   analogous to RouteLLM's SW Ranking variant.

Recommend option 1 as the primary implementation: it's simpler, faster to train,
and the feature engineering question is the same regardless of architecture.

**Code integration:**
- **Offline training:** New script `tools/train_learned_router.py`. Reads
  historical JSONL, extracts task features and pass/fail labels, trains
  classifier, outputs a frozen plan (per-task T2/T3 assignment).
- **Runtime:** Consume the pre-computed plan via existing `FrozenRouterPlan` →
  `enterprise_router` or `budgetflow_same_router` branch in
  `strategies.py:choose_backend()`.
- **Alternative (online inference):** Load serialized classifier at runtime,
  new strategy branch `"learned_router"` in `strategies.py`. Simpler but
  requires classifier dependencies in the runtime environment.
- **Files touched:**
  - New: `tools/train_learned_router.py`
  - `strategies.py`: optionally new `"learned_router"` branch
  - `frozen_router.py`: no changes if using frozen plan format
  - `compare_execution.py`: load classifier-generated frozen plan

**Fairness risks:**
- **Data leakage (critical):** Training on evaluation-set outcomes → invalid
  comparison. Must use strict train/test split or cross-validation with
  task-level separation. A single diagnostic run on held-out tasks can provide
  training data; the evaluation must use different tasks.
- **Label definition:** Without counterfactuals, we don't know if T3 was "worth
  it" for a given task. This is a fundamental limitation of any learned router
  trained on single-tier observations. **[Uncertainty — needs audit of available
  historical data.]**
- **Value-oblivious comparison:** The classifier ignores task value (by design).
  Under equal value this is fine. Under heterogeneous value, the classifier is
  disadvantaged — which is exactly what BudgetFlow claims matters. Fair
  comparison: report results under both equal-value and heterogeneous-value
  profiles.
- **Feature overlap with BudgetFlow:** If the classifier uses the same Task
  Effort and Model Fit features that BudgetFlow consumes, it's really testing
  "does the formula beat a learned weighting of the same inputs?" rather than
  "does value-awareness beat task features?" Both are valid but must be
  distinguished.

**Implementation complexity:** Medium. Offline training is straightforward
(sklearn/XGBoost). Runtime integration via frozen plan path is minimal. The
main work is feature engineering and label construction.

**Recommendation:** **Yes — strongest head-to-head baseline, but must be
positioned as "RouteLLM-inspired learned router" with explicit disclosure of
the adaptation gaps (preference data → task success data, single-turn →
multi-turn agent tasks, no value-awareness → value-oblivious).** This is the
baseline reviewers will most expect. The comparison directly tests whether
BudgetFlow's explicit value-awareness + budget-pressure formula beats a
supervised ML approach trained to predict which tier will succeed.

---

### 3.3 UCCI (Kotte, 2026, arXiv:2605.18796)

#### A. Original Paper Facts

- **Problem:** Cascade routers use uncalibrated confidence scores, requiring
  per-workload threshold tuning. UCCI replaces these with rigorously calibrated
  uncertainty estimates that make escalation thresholds transferable across
  workloads.
- **Decision unit:** Per-query. Independent routing decisions.
- **Baselines:**
  - Always-small / Always-large (single-model deployment).
  - Entropy threshold: uncalibrated mean token entropy → threshold tuned on
    validation set.
  - Conformal prediction: split conformal on binary "small model is correct"
    event, using raw token-margin uncertainty as nonconformity score.
  - FrugalGPT-style: confidence threshold tuned on validation to meet accuracy
    target. (This is a simplified single-threshold cascade, not the full
    FrugalGPT with learned cascade list and multiple thresholds.)
  - Does NOT run RouteLLM or HybridLLM (those need preference/quality-gap
    labels unavailable for their proprietary workload).
- **Metrics:**
  - Micro-averaged F1 across 6 entity types (camera, lens, aperture, shutter
    speed, ISO, focal length).
  - Expected Calibration Error (ECE): binned |fraction_correct − mean_predicted|.
    Uncalibrated=0.12, UCCI=0.03 (95% CI [0.02, 0.04]).
  - Cost: normalized per-query inference cost. c_s=1.0, c_l=3.02 (from measured
    H100 latency, not API pricing). 31% cost reduction (95% CI [27%, 35%]) at
    F1=0.91.
- **Budget type:** None. Cost minimization subject to F1 ≥ τ (population-level
  expected constraint, not per-batch hard cap). **No shared budget. No
  batch-level allocation.**
- **Calibration method (exact):**
  - Input: token-margin uncertainty u(x) = 1 − (1/T)·Σ m_t, where m_t =
    p_{t,1} − p_{t,2} is the top-2 token probability margin at generation
    step t.
  - Isotonic regression (Zadrozny & Elkan, 2002) on calibration set
    {(u_i, e_i)}_{i=1}^n, where e_i = 1 if small model output ≠ ground truth.
    n=22,500 (30% of 75K).
  - Output: monotonic map g: [0,1] → [0,1] where g(u) ≈ P(error | u).
  - Ablation: isotonic (ECE=0.03) beats temperature scaling (ECE=0.08).
- **Cascade structure:** Two models (4B, 12B). Single binary escalation:
  ```
  π_θ(x) = small if ĝ(x) ≤ θ else large
  ```
  Threshold θ* chosen by grid search on validation: min cost s.t. F1 ≥ τ.
- **Cost model:** H100 latency, not API dollars. c_s=1.0, c_l=3.02 (ratio from
  measured latency over 100 queries). Sensitivity analysis at 5× and 10× ratios
  shows savings increase but routing decisions unchanged.
- **Dataset:** Single proprietary NER workload — 75K manually labeled queries
  from an enterprise photo management system. Mean 6.2 words/query. 89% contain
  ≥1 entity. Train/cal/val/test = 30/30/20/50 split. **No CoNLL, no multi-task
  evaluation.** Paper acknowledges single-domain limitation.
- **Theoretical guarantee (Theorem 1):** Under three assumptions — (i) c_l > c_s,
  (ii) large model accuracy α_l is invariant to which queries are escalated
  (strong assumption), (iii) perfect calibration ĝ = P(error|u) — threshold
  policies on ĝ are cost-optimal among all policies depending only on u.
  Sample complexity: E[ECE] = O(n^{−1/3}).

#### B. BudgetFlow-Compatible Adaptation

UCCI contributes calibrated Model Fit estimation, not a new routing policy. Its
threshold policy structure is: if calibrated_error_prob > θ, escalate. This is
conceptually identical to BudgetFlow's marginal-yield formula with a different
threshold logic.

**What UCCI would change in BudgetFlow:**
- Replace catalog-based Model Fit (`tier2_fit`, `tier3_fit`) with UCCI-style
  isotonic-regression-calibrated fit estimates.
- The routing formula (`task_start_tier_decision`) stays the same. Only the
  Model Fit inputs change.
- This is an **input-quality ablation**, not a policy comparison.

**Why this is Claim 2, not Claim 1:**
- Claim 1 tests "does BudgetFlow's policy architecture beat other policies?"
- UCCI changes "how good are BudgetFlow's Model Fit estimates?"
- These are different questions. Mixing them creates a confound: if
  UCCI-augmented BudgetFlow wins, we don't know if it's the calibration or
  the policy.

**Code integration (if implemented as Claim 2 mechanism):**
- New module: `budgetflow/calibrated_fit.py` implementing isotonic regression
  on historical (fit_estimate, actual_outcome) pairs.
- `compare_execution.py`: populate `calibrated_model_fit` from UCCI source
  instead of raw catalog priors.
- `task_level_routing.py`: no changes (consumes Model Fit transparently through
  `AllocationContext`).

**Fairness risks:**
- Calibration requires same-catalog historical data with both T2 and T3
  outcomes. Without counterfactuals, calibration can only correct for observed
  tiers.
- If calibration set overlaps with evaluation set, information leaks.

**Implementation complexity:** Medium-High. Isotonic regression is standard
(sklearn), but the calibration pipeline (data collection, split management,
ECE validation) adds infrastructure.

**Recommendation:** **No for Claim 1 baselines; yes for Claim 2 mechanism
analysis.** UCCI is correctly positioned in draft §6.3 as a natural extension.
Implementing calibrated Model Fit as a Claim 2 variant ("does improving Model
Fit calibration improve BudgetFlow's decisions?") is valuable. Presenting it
as a Claim 1 baseline ("UCCI vs. BudgetFlow") is misleading — it's the same
policy with better inputs. **[Uncertainty]** UCCI's empirical validation is on
a single NER workload with a specific two-model setup. Transfer to multi-turn
SWE-bench agent tasks is untested. The token-margin uncertainty signal may not
carry the same information for code-generation tasks as for structured NER.

---

### 3.4 Topaz (Okamoto et al., 2026, arXiv:2604.03527, CHI 2026 HCXAI Workshop)

#### A. Original Paper Facts

- **Problem:** Model routing decisions in agentic workflows are opaque.
  Developers cannot inspect why a model was chosen for a subtask.
- **Decision unit:** Per-subtask. User submits an agentic workflow decomposed
  into subtasks t ∈ T (manual decomposition, not automated).
- **Baselines: None.** This is a workshop systems/demonstration paper. No
  comparison against FrugalGPT, RouteLLM, HybridLLM, or any other routing
  system. No accuracy/F1/win-rate tables.
- **Metrics:**
  - Match score (Eq. 2): Σ_s min(1, C_{m,s} / (k_t · R_{t,s})) · R_{t,s}.
    Per-skill fulfillment capped at 1.0, weighted by task requirements.
    Unitless ∈ [0,1].
  - Cost: absolute dollars (DP mode) or min-max-normalized (objective mode).
  - Objective score (Eq. 3): weighted quality-cost combination.
  - DP table value Q[i,c]: cumulative match quality. **No downstream task
    accuracy is measured.**
- **Budget type:** Two modes:
  - Objective-based: soft parameter c_global ∈ [0,1], scalarized per-task.
  - Budget-based: hard cap B (dollars), enforced via DP. **This mode is only
    in Appendix B.6 — no results in the main paper body.**
- **8 skill dimensions:** Mathematical reasoning, Logical reasoning, Code
  generation, Tool use, Factual knowledge, Writing quality, Instruction
  following, Summarization. These are the shared vocabulary.
- **Model skill profiles (static):**
  1. For each benchmark b, LLM (Gemini 3.0 Flash) produces L1-normalized skill
     weights w_{b,s}.
  2. Collect third-party leaderboard scores S_{m,b}.
  3. 0-max normalize: S̃_{m,b} = S_{m,b} / S_{b,max}.
  4. Per-skill capability: C_{m,s} = Σ_b (S̃_{m,b} · w_{b,s}) / Σ_b w_{b,s}.
  5. Values in [0,1]. Example: Claude Opus 4.5 — Math 0.967, Logic 0.966.
- **Task skill requirements:** LLM (Gemini Flash) profiles each subtask
  description → (R_{t,s}: skill weights, k_t: complexity, σ_in/σ_out: token
  estimates, q_t: quality sensitivity). q_t is user-adjustable.
- **Objective-based routing (Eq. 3):**
  ```
  m* = argmax_m [q_t · max(1−c_global, ε) · Match_{m,t}
                 − c_global · max(1−q_t, ε) · Cost_rel_minmax(m, σ_t_io)]
  ```
  Per-task independent argmax. ε=0.01. Min-max normalized relative cost.
- **Budget-based DP (Eq. 4, from appendix):**
  ```
  Q[i, c] = max_m (Q[i−1, c − Cost_abs(m, σ_t)] + q_{t_i} · Match_{m,t_i})
  ```
  Standard 0/1 knapsack over sequential tasks. States: (task_index, remaining
  budget). Action: choose model m. Cost_abs = σ_in·p_{m,in} + σ_out·p_{m,out}.
  Complexity: O(n · B_discrete · |M|).
- **Case study:** One 6-task customer support pipeline (Ticket Classification,
  KB Search, Technical Diagnosis, Refund Calculation, Response Drafting,
  Escalation Summary). 5 models: Gemini 3 Pro, Claude Opus 4.5, GPT 5.2,
  Llama 4 Maverick, Mistral Small 3.1.
- **Audit trail:** Structured log of all decisions → LLM transforms to natural
  language explanations. Two granularities: per-task (why model X for task Y)
  and global (overall router strategy characterization).
- **Key limitation:** No downstream accuracy measurement. Match score is an
  untested proxy. No open-source code.

#### B. BudgetFlow-Compatible Adaptation

**Adaptation concept:** Pre-compute per-task (expected value, expected cost) for
T2 and T3, then run a value-weighted 0/1 knapsack DP to assign tiers under the
shared cap. This tests "does BudgetFlow's sequential, pressure-adaptive
allocation beat a globally optimal (in expectation) static assignment?"

**Why "Topaz-style" is misleading:**
1. Topaz's DP is a textbook knapsack algorithm, not a novel contribution. The
   paper's contribution is explainability + skill taxonomy, not the DP.
2. Topaz has no empirical routing results — the DP mode is only in the appendix.
3. Topaz's match score is untested as a quality proxy. We would use actual
   pass probability, which is a different objective.
4. The skill taxonomy (8 dimensions, LLM-profiled) would need to be rebuilt for
   SWE-bench tasks — a significant undertaking with unclear validity.

**Better framing:** "Static oracle DP allocation" — the DP uses the same
expected-value and expected-cost estimates that BudgetFlow consumes, but sees
all tasks upfront (oracle advantage) and solves the optimal static assignment.
This is a clean theoretical baseline.

**Task-start output:** Pre-computed tier assignment (T2 or T3 per task),
consumed via frozen plan at task start. No runtime adaptation.

**Shared-cap handling:** The DP constraint is Σ cost_i ≤ B (in expectation).
Actual costs may deviate, so the DP plan may still overspend. If budget
exhausted before batch completion, remaining tasks fail (same as all policies).

**DP formulation (value-weighted):**
```
Q[i, c] = max quality achievable for first i tasks with budget c
Q[0, c] = 0 for all c ≥ 0
Q[i, c] = max(
    Q[i−1, c − E[cost_T2(t_i)]] + v_i · P(pass | t_i, T2),   # choose T2
    Q[i−1, c − E[cost_T3(t_i)]] + v_i · P(pass | t_i, T3)    # choose T3
)
```
Where P(pass | t_i, tier) comes from Model Fit estimates and v_i is the
pre-registered task value.

**Required inputs:**
- Per-task P(pass | T2) and P(pass | T3) — from Model Fit.
- Per-task E[cost | T2] and E[cost | T3] — from Task Effort + per-turn costs.
- Task values v_i — from ValueSource.
- Shared budget cap B.

**Code integration:**
- New script: `tools/compute_dp_allocation.py`. Runs once before batch.
  Reads ValueSource, Model Fit, Task Effort. Writes frozen plan.
- Runtime: consume via existing `FrozenRouterPlan` → `enterprise_router` path.
  No changes to `strategies.py` or `compare_execution.py`.
- **Files touched:**
  - New: `tools/compute_dp_allocation.py`
  - `frozen_router.py`: no changes (standard frozen plan format)
  - `compare_execution.py`: load DP-generated plan (existing infrastructure)

**Fairness risks:**
- **Oracle advantage (critical):** The DP sees all tasks and their expected
  costs/pass probabilities upfront. BudgetFlow sees tasks sequentially and
  adapts based on actual (not expected) remaining budget. The DP has a
  structural information advantage. If BudgetFlow beats the DP, that's a very
  strong result. If the DP wins, it's expected and must be discussed honestly
  as "the cost of sequential decision-making under uncertainty."
- **Expected vs. actual cost gap:** The DP optimizes expected costs, but actual
  costs vary per task. If T3 systematically costs more than expected, the DP
  plan becomes infeasible. Report budget utilization for both policies.
- **Estimate source coupling:** The DP should use the same Model Fit and Task
  Effort estimates as BudgetFlow. Otherwise the comparison is about estimate
  quality, not allocation strategy.

**Implementation complexity:** Medium. The DP is ~20 lines of Python (textbook
0/1 knapsack). The main work is extracting per-task estimates from existing
infrastructure.

**Recommendation:** **Yes — but frame as "static oracle DP" not "Topaz
baseline."** The DP is a clean theoretical comparison: optimal static allocation
vs. adaptive runtime allocation. It has higher theoretical purity than the
RouteLLM-style learned router (no training data leakage concerns, no
counterfactual label problem) because it uses the same estimates BudgetFlow
uses. The downside: it's less recognizable to reviewers (it's not associated
with a well-known paper).

**[Uncertainty]** Topaz's DP result is only in the appendix, with no experimental
validation. The paper itself does not demonstrate that the DP improves over
objective-based routing. Citing Topaz as the source of the DP baseline may
invite scrutiny of Topaz's own limitations (no accuracy measurement, no
empirical routing comparisons). Recommend citing the DP as "oracle knapsack
allocation (cf. Topaz budget-based mode, Okamoto et al. 2026)" rather than
"Topaz baseline."

---

### 3.5 INTENT (Liu et al., ICML 2025, arXiv:2602.11541)

#### A. Original Paper Facts

- **Problem:** LLM agents augmented with tools need to plan tool calls under
  strict monetary budgets. Naive tool use exhausts budget; conservative use
  leaves value on the table.
- **Decision unit:** Per-task. Each task instance I = (q, B, M) is an
  independent MDP. No state carried across tasks.
- **Baselines:**
  - **Soft:** Raw (ReAct, no cost info), Prompt (natural-language cost info).
  - **Enforce:** DFSDT (depth-first search with budget pruning, width=10),
    BTP (multi-knapsack tool quota allocation + tool similarity scoring),
    BATS (adapted from per-tool budgets to unified global budget, self-
    verification capped at K=5).
- **Metrics:**
  - Pass Rate (PR): % tasks solved (LLM judge, majority voting of 3).
  - Budget-Optimal Pass Rate (OR): PR / (tasks solvable under budget).
  - Win Rate (WR): % tasks where agent outperforms Prompt baseline.
  - Feasible Rate (FR): % tasks not exceeding budget.
  - Average Cost (AC), Average Price (AP).
  - End-to-end time, latency (40-worker multi-threaded), token consumption
    (ratio vs. Raw).
- **Budget type:** Per-task hard monetary budget (credit units). Default B=50.
  Synthetic tool prices sampled from Uniform(5, 50) per tool per task. 20 tools
  per task. **Hard indicator: reward = 0 if total_cost > B.**
- **Method (NOT MCTS — paper explicitly rejects MCTS):**
  - **Language World Model (LWM):** Qwen2.5-3B-Instruct. Predicts tool
    observation structure (format, schema), not exact content. Trained on
    ~100K MirrorAPI-Cache trajectories. Hardware: single RTX Pro 6000.
  - **Conditional Generator:** Qwen2.5-3B-Instruct (separate instance).
    Generates observation conditioned on intention satisfaction z_t ∈ {0,1}.
  - **Intention Predictor:** Qwen3-0.6B-Embedding + classification head.
    Predicts P(z_t=1 | reasoning, tool_spec, arguments). Trained on 86K
    (reasoning, action, observation) triples. Temperature scaling calibration:
    ECE 0.0443 → 0.0077.
  - **MCO (Monte Carlo Oracle):** Single stochastic rollout → accept if
    projected cost ≤ B_t, else reject with feedback.
  - **INTENT:** Deterministic ideal trajectory (z_k=1 forced) → geometric cost
    calibration (Cost(a_k) / ρ̂_k) → accept if γ·Σ calibrated_costs ≤ B_t
    (γ=0.5 default). Simulation reuse on plan continuity.
- **Dataset:** StableToolBench (stable fork of ToolBench). 765 test instances.
  16K+ real RapidAPI tools across 49 categories. Synthetic tool prices.
  6 task groups.
- **Training data total:** ~186K trajectories (100K MirrorAPI + 86K ToolBench
  Reproduction).
- **Key result (GPT-5-nano):** INTENT 76.0% PR / 92.6% OR / 100% FR vs.
  Prompt 48.5% / 59.1% / 87.6%. ~2.4× token consumption overhead, ~2.2×
  latency vs. Raw.
- **Cross-task allocation: None.** Each of the 765 tasks gets independent B=50.

#### B. BudgetFlow-Compatible Adaptation

**Not adaptable.** INTENT addresses within-task tool-call planning under a
per-task budget. BudgetFlow addresses cross-task model-tier allocation under
a shared budget. These are different decision layers:

- INTENT: given a per-task budget B, which tools should the agent call and
  when should it stop?
- BudgetFlow: given a shared budget B_shared, which tasks should get T2 vs.
  T3 access?

To repurpose INTENT as a cross-task baseline, we would need to:
1. Train a Qwen2.5-3B language world model on SWE-bench agent trajectories
   (~186K trajectories needed — we don't have this data).
2. Train an intention predictor on SWE-bench (reasoning, action, verification)
   triples.
3. Redesign the lookahead from "simulate tool outcomes" to "simulate model-tier
   outcomes for different tasks" — a fundamentally different prediction target.
4. Build a meta-controller that allocates fractions of the shared budget to
   individual tasks using INTENT as the inner loop.

The result would not be INTENT — it would be a new system that borrows INTENT's
concept of learned world-model lookahead. The engineering cost is
disproportionate to the baseline's value.

**Recommendation:** **No.** INTENT is correctly positioned in the draft (§2.2)
as a per-example budget enforcement system. The paper should add one sentence
explaining: "INTENT addresses within-task tool-call planning under per-task
budgets; BudgetFlow addresses cross-task model-tier allocation under a shared
budget. These are complementary decision layers, not competing policies."

---

### 3.6 BATS (Liu et al., 2025, arXiv:2511.17006)

#### A. Original Paper Facts

- **Problem:** Giving agents larger tool-call budgets is ineffective without
  budget *awareness*. Agents prematurely terminate — either they think they
  found the answer or they give up, unaware of unused resources.
- **Decision unit:** Per-question. Each question gets an independent per-tool
  budget. No cross-question allocation.
- **Baselines:**
  - Model-only: GPT-4o, Claude-3.7-Sonnet, Gemini-2.5-Flash/Pro, OpenAI o1.
  - Training-based agents: ASearcher, WebSailor, DeepDive, WebExplorer,
    OpenAI Deep Research.
  - ReAct variants: ReAct + Gemini/Claude backbones, ReAct + Budget Tracker,
    ReAct + sequential scaling (budget-forcing prompt), ReAct + parallel
    scaling (Majority Vote, Best-of-N, Pass@N).
  - BATS ablations: w/o Planning, w/o Verification, w/o both (= ReAct +
    Budget Tracker).
- **Metrics:**
  - Accuracy: exact match judged by Gemini-2.5-Flash (deterministic, T=0.0).
  - Average search calls, average browse calls per question.
  - Unified cost (cents): c_token + Σ_i (c_i · P_i) — post-hoc analysis only,
    NOT a runtime constraint.
  - Cost-performance Pareto frontier plots.
- **Budget type:** Per-question per-tool call-count hard cap. Budget b =
  (b_search, b_browse). Each tool independently capped. **Hard constraint:**
  stops when any budget exhausted. Typical budgets: 3, 5, 10, 30, 50, 100, 200
  (per tool). **Not monetary, not shared across questions.**
- **Budget Tracker (exact format):**
  ```
  Budget Tracker
  <budget>
  Tool1 Budget Used: ##, Tool1 Budget Remaining: ##
  Tool2 Budget Used: ##, Tool2 Budget Remaining: ##
  Make the best use of the available resources.
  </budget>
  ```
  Pure prompt-level text injection after each tool response. No training, no
  architectural changes. First-iteration: includes policy guideline describing
  budget regimes and tool-use recommendations.
- **Self-verification decisions:**
  - SUCCESS: all constraints satisfied → final answer.
  - CONTINUE ("dig deeper"): unverifiable but promising AND sufficient budget
    for deeper exploration → compressed trajectory summary, continue direction.
  - PIVOT: contradictions found OR insufficient budget → compressed summary,
    switch to alternative path.
- **Key experiment ("budget awareness matters"):** ReAct budget=10: 10.3% acc.
  ReAct budget=100: 12.6% acc (barely scales — saturates). ReAct + Budget
  Tracker budget=10: 12.8% acc (exceeds ReAct's best with 10× less budget).
  40.4% fewer search calls, 21.4% fewer browse calls, 31.3% lower unified cost.
  **Figure 3 is central:** ReAct saturates at budget=100 — uses zero additional
  tool calls beyond that. Budget Tracker continues scaling.
- **Datasets:** BrowseComp (1,266 questions), BrowseComp-ZH (289 Chinese),
  HLE-Search (200 curated from Human's Last Exam). All web search QA.
- **Token+tool unification:** c_unified = c_token + Σ_i (c_i · P_i). Post-hoc
  metric for comparison, not a runtime budget.
- **Cross-task allocation: None.** Each question gets identical independent
  per-tool budgets.

#### B. BudgetFlow-Compatible Adaptation

**Core insight already absorbed.** BATS's central finding — that budget
awareness is necessary for effective budget-constrained agents — is foundational
to BudgetFlow's design. BudgetFlow tracks remaining shared budget
(`budget_pressure`) and uses it to tighten T3 access as budget depletes. The
Budget Tracker's function (surface remaining resources) is implemented in
BudgetFlow through the structured `AllocationContext` and `budget_pressure`
signal, which is a stronger mechanism than prompt-level text.

**What a BATS-style control would test:**
- Give each task its own per-task cap (like existing `per_task_cap` mode in
  `compare_execution.py`).
- Surface remaining per-task budget to the agent during execution (prompt-level
  text injection, like BATS).
- Let the agent decide when to stop within its cap.

This tests "per-task budgets with agent awareness vs. shared budget with
centralized allocation" — a different question from Claim 1 ("which
cross-task allocation policy maximizes Yield under one shared cap?").

**Why not a Claim 1 baseline:**
1. BATS operates per-question with independent budgets. It makes no cross-task
   tradeoffs. Using it as a Claim 1 baseline would mean comparing "N independent
   per-task budgets" to "one shared budget" — the comparison is about budget
   structure, not allocation policy.
2. The Budget Tracker is a prompt-level mechanism for within-task awareness.
   BudgetFlow's `budget_pressure` is a structured policy input for cross-task
   allocation. They don't compete — they operate at different levels.
3. The per-task-cap diagnostic already tests the "each task gets its own budget"
   regime. Adding BATS branding doesn't change the comparison.

**Recommendation:** **No.** BATS is correctly positioned in draft §2.2 as
per-example budget enforcement. The per-task-cap diagnostic already covers the
comparison. If we want to isolate "does within-task budget awareness help?"
that's a Claim 2 mechanism question (add Budget Tracker prompt text to the
agent loop and measure the effect under fixed BudgetFlow routing), not a Claim 1
baseline.

---

### 3.7 RouteNLP (Guo et al., 2026, ACL 2026 Industry Track)

#### A. Original Paper Facts

- **Problem:** Minimize LLM inference cost while meeting per-task quality
  constraints in a production multi-task setting. Deployed at an enterprise
  customer-service division over an 8-week pilot (~5K queries/day).
- **Decision unit:** Per-query, 4-tier cascade (T1 → T2 → T3 → T4). Each
  query processed independently through the cascade chain.
- **Model portfolio:** T1: DistilBERT ($0.01/1K tokens), T2: Mistral-7B-Instruct
  + LoRA ($0.10/1K), T3: Mixtral-8x7B + AWQ quantization ($0.80/1K), T4:
  GPT-4-Turbo via API ($8.00/1K). ~800× cost range. T1-T3 served via vLLM with
  speculative decoding.
- **Baselines:** Always-T4, Always-T2, Random, Rule-Based, FrugalGPT (adapted to
  4 tiers), HybridLLM (extended to 4 tiers), RouteLLM (extended to 4 tiers),
  AutoMix (POMDP 4 actions). Plus 4 ablation variants of RouteNLP itself.
- **Metrics:**
  - *Quality Ratio:* Quality relative to Always-T4 (upper bound = 1.0).
  - *Cost Ratio:* Cumulative cascade cost relative to Always-T4. Cost(x) =
    Σ_{k=1}^{k*(x)} c_{k,t} — all tiers attempted in the cascade chain.
  - *p99 latency:* From M/M/c queueing simulation under production load.
  - *SLA violation rate:* Coverage violations exceeding the conformal α = 0.05
    target.
  - Task-specific: F1 (NER, intent, clause extraction), ROUGE-L (summarization),
    BERTScore (response generation), Accuracy (risk assessment).
  - Human eval: Win/Tie/Loss, Likert 5-point (factual accuracy, completeness,
    fluency, helpfulness), Krippendorff's α.
  - Statistical: 5 seeds, paired bootstrap (p < 0.001 for cost vs. RouteLLM).
- **Budget type:** **None.** The word "budget" appears zero times in the paper.
  The optimization is the inverse of budget-constrained: **minimize cost subject
  to per-task quality constraints** (Eq. 1):
  ```
  min_{r_θ} E_x[Σ_{k=1}^{k*(x)} c_{k,t}]  s.t.  E_x[q(m_k*(x), x)] ≥ τ_t
  ```
  Cost is unbounded; the constraint is on quality, not on spending.
- **Router architecture:** Shared DistilBERT encoder with multi-task head. Task
  type t encoded as learned 64-dim embedding concatenated with [CLS]. Jointly
  predicts difficulty level and minimum model tier. Training labels: all queries
  evaluated on all models, each (x, m_k) labeled with binary quality indicator
  (exceeds τ_t or not). Augmented with preference data from pairwise model
  comparisons (RouteLLM-style).
- **Conformal cascading:** Token-level uncertainty u(m_k, x) = (1/L) ×
  Σ_i (1 − p(y_i | y_<i, x)). Thresholds δ_{k,t} set via conformal risk control
  on 500 calibration examples per task per tier. Marginal guarantee (not
  per-query): Pr[q < τ_t ∧ u < δ] ≤ α (α = 0.05). Thresholds monitored and
  recalibrated weekly.
- **Distillation co-optimization:** Offline loop (2-3 iterations):
  1. Collect escalation logs (queries that cascaded up).
  2. Cluster failures via PCA (128-d) + k-means (k=10, silhouette score).
  3. Rank clusters by size × average quality gap; select top-5 per task.
  4. Generate distillation data from T4 (frontier) on cluster exemplars.
  5. Fine-tune T1-T3 via Sequence-Level Knowledge Distillation (SeqKD).
  6. Retrain router; recalibrate thresholds.
  7. Converge when |ΔCostRatio| < 0.005.
  This is "closed-loop" because deployment failures feed back to improve the
  portfolio, which changes routing, reducing future failures. It runs offline
  (periodic), not online/streaming.
- **Key results:** RouteNLP: Quality 0.971, Cost 0.159, p99 387ms, SLA viol.
  2.3%. Vs. RouteLLM (4-tier): Quality 0.969, Cost 0.246. Targeted distillation
  reduces cost from 0.203 to 0.159 (21.7% reduction), >2× the improvement of
  random distillation.
- **8-week pilot:** ~5K queries/day, shadow deployment (not randomized A/B,
  "limiting causal attribution"). 58% cost reduction vs. Always-T4. Quality
  audit (500 responses, 2 domain experts): 91% acceptable, 2.6% unacceptable
  (vs. 1.8% Always-T4). Customer complaint rate: no significant change.
- **Datasets:** 40,200 train / 8,800 test across 6 tasks (Financial NER from SEC
  EDGAR, Financial Summarization, CS Intent Classification from BANKING77, CS
  Response Generation, Legal Clause Extraction from CUAD, Legal Risk Assessment).
- **Task value awareness:** None. All tasks treated with equal weight. The only
  per-task differentiation is the quality threshold τ_t (fixed per task type,
  not adjustable per-query).
- **No dynamic programming, no knapsack, no resource allocation, no budget cap,
  no cross-task optimization.**

#### B. BudgetFlow Claim 1 Compatibility

**Why RouteNLP is not a Claim 1 baseline:**

1. **Inverse optimization objective.** RouteNLP minimizes cost subject to
   quality ≥ τ_t. BudgetFlow maximizes verified value subject to cost ≤ B. These
   are different problems. RouteNLP has no concept of a budget cap — it would
   happily spend more if quality demanded it.

2. **No shared budget.** RouteNLP processes each query independently. There is
   no pool of resources shared across tasks, no depletion tracking, no
   allocation decision when budget is scarce. Adapting it to a shared-budget
   setting would require building a fundamentally new system on top of the
   conformal cascade.

3. **No task value.** The only per-task parameter is τ_t (quality floor), which
   is a constraint, not a value function. There is no mechanism to say "Task A
   is worth 3× more than Task B, so allocate more budget to it."

4. **No DP-based budget allocation.** The user's question assumed a DP-based
   budget routing mode. This does not exist in the paper. The paper's Eq. 1 is a
   constrained cost minimization, not a knapsack or DP formulation.

**Why RouteNLP matters for the paper anyway:**

RouteNLP is the closest deployment-level neighbor to BudgetFlow. Both operate at
production scale across heterogeneous task types. Both use a tiered model
portfolio. Both care about cost-quality tradeoffs. RouteNLP's conformal
cascading and distillation co-optimization are orthogonal techniques that
could, in principle, be layered on top of BudgetFlow's shared-budget allocation
in future work.

**Positioning:** RouteNLP belongs in Related Work §2.1 as the state-of-the-art
deployment-level cascade router — the best existing answer to "how do you route
queries cost-effectively in production?" It should be contrasted with
BudgetFlow's shared-budget problem: RouteNLP solves the per-query cost
minimization problem well, but cannot answer the question "what if we have one
fixed budget for 30 tasks of varying value?"

**Recommendation:** **No as a Claim 1 baseline** (wrong optimization objective,
no budget model, no cross-task allocation). **Yes as a Related Work positioning
anchor** — the strongest existing deployment system that BudgetFlow
complements. Frame in §2.1: "RouteNLP demonstrates that per-query cascade
routing can achieve near-frontier quality at 16% cost. However, it provides no
mechanism for allocating a shared budget across tasks of heterogeneous value."

---

## 4. Proposed Next Experiment Policy Set

| # | Policy | Role | Priority | Status |
|---|---|---|---|---|
| 1 | **Pure T2** | Lower boundary control | Required | Exists |
| 2 | **Pure T3** | Upper boundary / efficiency reference | Required | Exists |
| 3 | **BudgetFlow task-level** | Proposed method | Required | Exists |
| 4 | **Learned router (RouteLLM-inspired)** | Tests "does value-aware formula beat supervised ML?" | **Highest** | Implement |
| 5 | **Static oracle DP (Topaz-inspired)** | Tests "does adaptive runtime beat optimal static plan?" | **High** | Implement |
| 6 | **Stall-escalation cascade** | Diagnostic: tests "does upfront commitment lose to try-then-escalate?" | Low | Optional |

### Rationale for ordering

**RouteLLM-inspired first** because:
- Highest reviewer recognition. Every reviewer who knows LLM routing knows
  RouteLLM. Not having a learned-router comparison is the most conspicuous
  gap in the current baseline set.
- The comparison is clean: same decision timing (task start), same information
  available at decision time (task features), different decision mechanism
  (learned weights vs. explicit value-aware formula).
- Implementation is straightforward (offline training → frozen plan).
- Even if we lose to the learned router, the result is informative: it tells
  us whether task features alone can predict optimal tier choice, which is a
  necessary diagnostic for understanding the allocation problem.

**Static oracle DP second** because:
- Clean theoretical interpretation: optimal static vs. adaptive runtime.
- No training data concerns (uses same estimates as BudgetFlow).
- Simple implementation (~20 lines of DP).
- If we beat the DP, that's a very strong signal that runtime adaptation to
  actual costs matters.
- Downside: less recognizable to reviewers (not associated with a flagship
  paper).

**Both baselines together** provide complementary coverage:
- RouteLLM-inspired: "Does learned pattern-matching on task features beat
  explicit value-aware allocation?"
- Oracle DP: "Does runtime adaptation to actual costs beat optimal static
  planning?"

### Shared comparison protocol (all policies)

1. Same 30-task batch, same task order (pre-registered).
2. Same T2/T3 backends (identical model binding, identical per-turn costs).
3. Same shared hard budget cap ($6.00 or compiler-generated).
4. Same verifier (SWE-bench pass/fail via local harness).
5. Same ValueSource (pre-registered, frozen before execution).
6. Same CostSource (frozen model catalog).
7. Budget exhaustion → remaining tasks not executed (uniform stop rule).
8. Report: Pass count, Yield, Yield/$, total cost, budget utilization, per-task
   audit trail.

---

## 5. Open Questions for Main Agent

1. **RouteLLM training data availability:** How many historical JSONL rows do
   we have with both T2 and T3 outcomes on the same task? If each task only
   ran on one tier, we have no counterfactuals and must train on Model Fit
   estimates rather than observed outcomes. This fundamentally changes the
   nature of the learned router (it learns to mimic Model Fit, not to predict
   actual outcomes). **[Needs data audit before implementation.]**

2. **RouteLLM label definition:** What should the classifier learn to predict?
   Options: (a) P(pass | T3) — binary, ignores that T2 might also pass;
   (b) E[Yield | T3] − E[Yield | T2] — continuous, requires counterfactual
   estimates; (c) "did T3 pass and was the extra cost justified given task
   value?" — requires a value model. Choice affects interpretation and must
   be pre-registered. **[Needs design decision.]**

3. **RouteLLM feature engineering:** What task features should the classifier
   use? Options: (a) Task Effort + catalog Model Fit (same inputs as BudgetFlow
   — tests "formula vs. learned weighting"); (b) raw SWE-bench features from
   `SwebenchTaskAdapter` (repo, issue text, file count, test count — tests
   "explicit value model vs. implicit features"); (c) both. Choice determines
   what the comparison actually tests. **[Recommend: option (b) for the primary
   baseline, (a) as an ablation.]**

4. **Oracle DP estimate source:** Should the DP use the same Model Fit and
   Task Effort estimates as BudgetFlow, or separate estimates from a
   calibration run? Using the same estimates makes the comparison about the
   allocation algorithm. Using separate estimates tests robustness but adds a
   confound. **[Recommend: same estimates for primary comparison.]**

5. **One baseline or both in first round?** Implementing both the learned
   router and the oracle DP in one revision cycle is ~2-3 days of work
   (mostly offline training + DP script). Is this feasible, or should we
   prioritize one? **[Recommend: learned router first, DP as fast-follow if
   results are close.]**

6. **Cascade stall-escalation threshold pre-registration:** If we implement
   the cascade variant (even as a diagnostic), the stall threshold N must be
   pre-registered. What's a principled way to set it without tuning on eval?
   Options: (a) N = catalog reference runway turns / 4; (b) N fixed at 5 for
   all tasks; (c) N derived from Task Effort (harder tasks get more patience).
   **[Needs pre-registration before any implementation.]**

7. **Paper framing of learned router:** Should we call it "RouteLLM-inspired
   learned router" (acknowledging the adaptation gap) or "supervised task
   router" (generic, avoiding RouteLLM association)? The first is more
   recognizable to reviewers but invites scrutiny of the adaptation gap. The
   second is safer but less recognizable. **[Recommend: "RouteLLM-inspired"
   with explicit disclosure of the adaptation differences in §4.3.]**

8. **FrugalGPT/UCCI/INTENT/BATS positioning:** Should the paper add explicit
   "why not a baseline" sentences for each of these in §4.3? Or is the
   Related Work positioning table in §2.4 sufficient? **[Recommend: add one
   sentence each in §4.3 for FrugalGPT ("soft average budget, not hard cap")
   and INTENT/BATS ("within-task budget enforcement, not cross-task
   allocation"). UCCI can be mentioned in §6.3 as future mechanism work.]**
