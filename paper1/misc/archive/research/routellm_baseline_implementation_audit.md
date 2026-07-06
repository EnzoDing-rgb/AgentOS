# RouteLLM-Inspired Learned Router Baseline: Implementation Audit

**Date:** 2026-06-25
**Scope:** RouteLLM official implementation (cloned, read in full), Anyscale llm-router tutorial, lightweight router landscape, training data formats, data leakage prevention.
**Method:** Full codebase read of lm-sys/RouteLLM (cloned at `/tmp/RouteLLM`), Anyscale llm-router tutorial (`/tmp/llm-router`), web search for related implementations and data leakage literature.
**Status:** Research audit. No code changes made.

---

## 1. Executive Summary

**Bottom line:** The RouteLLM official implementation is a full-stack serving framework, not a modular training library. It cannot be directly reused for BudgetFlow without major surgery. However, its core ideas (preference-label training data format, classifier-on-embeddings architecture, threshold-based routing) can be adapted into a decoupled "RouteLLM-inspired learned router" baseline at moderate engineering cost (~1-2 days).

**Key recommendations:**
1. Do not use RouteLLM as a library. Clone the architectural pattern, not the code.
2. Use a **sklearn/XGBoost binary classifier** on SWE-bench task features as the minimal viable learned router.
3. Use **"T3 pass" binary label** with task-level cross-validation splits (5-fold, group by task_id).
4. Integrate via the **existing `FrozenRouterPlan` path** (offline training -> frozen plan -> `enterprise_router` or `budgetflow_same_router` strategy).
5. Name it "RouteLLM-inspired supervised task router" with explicit disclosure of adaptation gaps.

---

## 2. What RouteLLM Actually Provides

### 2.1 Repository Structure

The official repo (`lm-sys/RouteLLM`, cloned to `/tmp/RouteLLM`) has 23 Python files across these modules:

```
routellm/
  __init__.py
  controller.py              # OpenAI-compatible serving layer + threshold routing
  calibrate_threshold.py     # Offline threshold calibration script
  openai_server.py           # OpenAI API server wrapper
  routers/
    routers.py               # Router ABC + 5 implementations (SWRanking, MF, BERT, CausalLLM, Random)
    matrix_factorization/
      model.py               # MFModel (Embedding + text_proj + classifier)
      train_matrix_factorization.py  # Training script with PairwiseDataset
    causal_llm/
      model.py               # CausalLLMClassifier (Llama-3-8B fine-tuned)
      configs.py             # ModelTypeEnum, RouterModelConfig
      llm_utils.py           # Model/tokenizer loading
      prompt_format.py       # Prompt template rendering
    similarity_weighted/
      generate_embeddings.py # Precompute arena battle embeddings
      utils.py               # Elo MLE with ties, tier clustering (DP), battle preprocessing
  evals/
    evaluate.py              # Main evaluation runner (MMLU, MT-Bench, GSM8K)
    benchmarks.py            # Benchmark ABC + MMLU/MTBench/GSM8K impls
    find_contaminated.py     # Decontamination script
```

### 2.2 The Five Router Types

From `routers/routers.py` (read in full):

| Router | Class | Architecture | Training | Hardware | Complexity |
|---|---|---|---|---|---|
| `sw_ranking` | `SWRankingRouter` | Cosine similarity over arena embeddings + weighted Elo MLE | None (non-parametric) | None needed | Lowest |
| `mf` | `MatrixFactorizationRouter` | Embedding(64 models, dim=128) + text_proj(1536->128) + classifier(128->1) | BCEWithLogitsLoss, Adam LR=3e-4, ~10 epochs, batch 64 | 8GB GPU | Low |
| `bert` | `BERTRouter` | BERT_BASE + CLS token -> logistic regression (3-class: win_s/tie/win_w) | Cross-entropy, ~2000 steps, batch 16 | 2xL4 24GB | Medium |
| `causal_llm` | `CausalLLMRouter` | Llama 3 8B fine-tuned, special tokens [[1]]-[[5]], binary thresholding | Instruction fine-tuning, ~2000 steps, batch 8 | 8xA100 80GB | High |
| `random` | `RandomRouter` | Uniform(0,1) | None | None | Trivial |

**All routers implement the same interface:**
```python
class Router(abc.ABC):
    @abc.abstractmethod
    def calculate_strong_win_rate(self, prompt) -> float:
        """Returns P(strong_model_wins | prompt) in [0, 1]."""
        pass

    def route(self, prompt, threshold, routed_pair):
        if self.calculate_strong_win_rate(prompt) >= threshold:
            return routed_pair.strong
        else:
            return routed_pair.weak
```

### 2.3 Training Data Format

From `train_matrix_factorization.py` and the HuggingFace datasets:

**Raw Chatbot Arena format (`lmsys/lmsys-arena-human-preference-55k`):**
```json
{
  "prompt": "[\"first user turn text\"]",
  "model_a": "gpt-4-1106-preview",
  "model_b": "mixtral-8x7b-instruct-v0.1",
  "winner_model_a": 1,    // 1 if A won, 0 otherwise
  "winner_model_b": 0,    // 1 if B won, 0 otherwise
  "winner_tie": 0         // 1 if tie, 0 otherwise
}
```

**Preprocessed pairwise format (used by `PairwiseDataset`):**
```json
{
  "idx": "unique_prompt_id",
  "model_a": "gpt-4-1106-preview",
  "model_b": "mixtral-8x7b-instruct-v0.1",
  "winner": "model_a"  // "model_a", "model_b", or "tie" (ties are filtered out)
}
```

**Critical design decisions in RouteLLM's data handling:**
1. **Model responses are discarded.** Only winner identities are kept.
2. **Model tier clustering (DP on Elo scores):** 64 models -> 10 tiers. Top 2 tiers = "strong", tier 3 = "weak".
3. **Pre-computed prompt embeddings** stored in `.npy` files (text-embedding-3-small, dim=1536).
4. **Training labels reduce to binary:** winner is always `model_a` after reordering (winner model becomes `models_a`, loser becomes `models_b`).
5. Loss: `BCEWithLogitsLoss` with labels=1 (the `models_a` entry is always the winner after reordering).

### 2.4 Training and Inference Flow

**MF Router training (`train_matrix_factorization.py`):**
```
1. Load pairwise JSON data -> filter ties, self-battles
2. Shuffle -> 95/5 train/test split (random, NOT task-grouped)
3. PairwiseDataset: reorder (winner -> model_a), embed prompts via precomputed .npy
4. MFModel_Train: P (model embeddings) + Q (frozen prompt embeddings) + text_proj + classifier
5. Forward: classifier((P[model_win] - P[model_loss]) * text_proj(Q[prompt]))
6. BCEWithLogitsLoss, Adam(lr=3e-4, weight_decay=1e-5), ~100 epochs, batch 64
```

**MF Router inference (`model.py:pred_win_rate`):**
```
1. Get model_a and model_b integer IDs
2. Compute model embeddings (learned P table)
3. Get prompt embedding via OpenAI API (text-embedding-3-small) + text_proj
4. Compute logits = classifier(embed_a * prompt_emb) - classifier(embed_b * prompt_emb)
5. Return sigmoid(logits)
```

### 2.5 How RouteLLM Connects to a Budget

RouteLLM does NOT have a budget in the traditional sense. The "budget" is an alpha threshold that controls what fraction of queries go to the strong model:
- `P(strong_wins | q) >= threshold` -> route to strong model
- Lower threshold -> more strong-model calls -> higher cost, higher quality
- The threshold is calibrated offline to hit a target strong-model-call percentage (e.g., 20%, 50%, 80%)

**This means RouteLLM has no:**
- Shared budget ledger
- Dollar cost tracking during routing
- Budget-exhaustion stop condition
- Value-awareness (all queries equal)
- Sequential decision-making under depleting resources

### 2.6 Evaluation Protocol

From `evals/benchmarks.py` and `evals/evaluate.py`:
- Pre-compute `strong_win_rate` for all test prompts (once per router)
- Choose thresholds via `pd.qcut` into N bins
- For each threshold: route each test prompt, measure accuracy, count strong-model calls
- Plot: strong_model_calls% (x) vs. accuracy (y)
- Metrics: AUC, APGR (Area under Performance Gap Recovered), CPT(x%)

**No cross-validation. No task-level splits.** Their evaluation is purely in-distribution threshold sweeping on a fixed test set.

---

## 3. What Can and Cannot Be Reused

### 3.1 Can Be Reused (Architectural Patterns)

| Pattern | Source | Reuse for BudgetFlow |
|---|---|---|
| Pairwise preference data format | `PairwiseDataset` in `train_matrix_factorization.py` | YES -- adapt to (task, tier_A, tier_B, outcome) format |
| Embedding-based text representation | `text-embedding-3-small` in SW Ranking + MF | YES -- use issue text embeddings as features |
| Binary classifier on task features | MF classifier head | YES -- sklearn/XGBoost binary classifier |
| Threshold-based tier selection | `Router.route()` interface | YES -- classifier probability -> T2/T3 decision |
| Precomputed frozen plan | N/A (RouteLLM is online) | YES -- our existing `FrozenRouterPlan` mechanism |
| Deprecating model responses | Only winner identity matters | YES -- keep only pass/fail label, not agent traces |

### 3.2 Cannot Be Reused (Direct Code Reuse Blockers)

| Blocker | Why |
|---|---|
| **Controller `__init__` requires OpenAI API keys** | We are not making live API calls; we do offline training |
| **SW Ranking requires Chatbot Arena battle data** | We don't have pairwise preference data; we have (task, pass/fail) data |
| **MF Model assumes 64-model vocabulary** | Hard-coded `MODEL_IDS` dict with specific LLM names |
| **Causal LLM requires Llama 3 8B + A100s** | Disproportionate cost for a baseline; would need to be re-trained on our data anyway |
| **BERT expects `(query_str, winner)` format** | Would need to retrain from scratch on our SWE-bench issue text, not Chatbot Arena prompts |
| **Threshold calibration assumes per-query cost model** | RouteLLM's alpha threshold uses "% strong calls" not dollars |
| **No cross-validation or task-level splitting** | RouteLLM's random 95/5 split leaks across queries from same user/domain |
| **No budget-awareness or value-awareness** | Our integration requires budget-exhaustion stop and value-weighted evaluation |
| **`Router.route()` is online/synchronous** | Our integration is offline training -> frozen plan -> runtime consumption |

### 3.3 Verdict

**Direct code reuse is not feasible.** The RouteLLM codebase is a tightly coupled serving framework built for Chatbot Arena data and OpenAI-compatible inference. Every router type hard-codes model identifiers, embedding models, and data formats specific to that ecosystem.

**Architectural pattern reuse is the right approach.** The core idea (train a classifier on task features to predict which tier will win) is clean and adaptable. We should build our own lightweight classifier using sklearn/XGBoost with our SWE-bench task features, then integrate via the existing frozen-plan path.

---

## 4. Proposed Learned-Router Baseline Design

### 4.1 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     OFFLINE TRAINING PHASE                       │
│                                                                  │
│  Historical JSONL ──> Feature Extractor ──> Training Data        │
│  (diagnostic runs)    (task_features)      (X, y pairs)          │
│                                                                  │
│  X = [task_features + text_embedding]                            │
│  y = binary label (T3 passes? or T3 worth it?)                   │
│                                                                  │
│  ┌──────────────────────────────────────┐                        │
│  │  sklearn/XGBoost Binary Classifier   │                        │
│  │  - Logistic Regression (simplest)    │                        │
│  │  - XGBoost (default)                 │                        │
│  │  - Random Forest (diagnostic)        │                        │
│  │  Train on 4 folds, eval on held-out  │                        │
│  └──────────────┬───────────────────────┘                        │
│                 │                                                │
│                 ▼                                                │
│  Threshold Calibration ──> Per-Task T2/T3 Assignment             │
│  (calibrate on train only)                                       │
│                 │                                                │
│                 ▼                                                │
│  FrozenRouterPlan JSON ──> {instance_id: {preferred_model, ...}} │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     RUNTIME PHASE (NO CHANGES)                    │
│                                                                  │
│  compare_execution.py ──> load FrozenRouterPlan                  │
│  strategies.py         ──> enterprise_router / budgetflow_same_router │
│  frozen_router.py      ──> FrozenPlanEntry.lookup(instance_id)   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Feature Engineering

**Option A: Raw SWE-bench task adapter features (RECOMMENDED for primary baseline)**
From `SwebenchTaskAdapter.features()` -> `task_features` in `compare_execution.py` line 153:
- `instance_id` (not used as feature, used for group split)
- `repo` (categorical, one-hot encoded)
- `issue_text` (-> text embedding via `text-embedding-3-small` or `all-MiniLM-L6-v2`)
- `base_commit`, `hints_text`, `test_patch`
- Derived: issue length, number of modified files, number of tests

This tests whether a supervised ML router can predict tier success from the same raw task information available before execution. This is the cleanest comparison: BudgetFlow uses explicit value-aware formula; the learned router uses a black-box ML model on the same base features.

**Option B: BudgetFlow's Task Effort + catalog Model Fit (for ablation)**
- `task_effort`, `final_task_effort`
- `tier2_fit`, `tier3_fit`, `fit_gain`
- `criticality_level`, `task_value`

This tests "does a learned weighting of BudgetFlow's own inputs beat BudgetFlow's formula?" Valid ablation, but it tests feature engineering not policy architecture.

**Option C: Both (not recommended)**
Combining both creates an information advantage over BudgetFlow (more features). Use only for diagnostic if we see unexpected results.

### 4.3 Classifier Architecture

**Recommended: XGBoost binary classifier**

Rationale:
- Handles mixed feature types (continuous + categorical + text embeddings)
- Built-in feature importance (interpretability for paper)
- No GPU required
- Single-digit-second training time on ~30-100 task samples
- Well-understood by reviewers
- Can output calibrated probabilities via `predict_proba`

**Fallback: Logistic Regression**
- Even simpler, more interpretable
- Requires feature scaling
- Good for very small sample sizes

**Not recommended: Neural network (BERT, MF, causal LLM)**
- RouteLLM uses these because it has 65K training samples and needs to process free-form natural language queries
- We have 30-100 task samples with structured features + issue text
- A neural net would overfit severely at this sample size
- Reviewer expectation: "Why use a deep net when a tree-based model works better with small tabular data?"

### 4.4 Threshold Selection

Unlike RouteLLM's alpha sweep (which controls % strong-model calls without a budget), we need a threshold that works under a shared dollar budget:

**Option 1: Probability threshold (offline calibration on train set)**
- For each candidate threshold, simulate batch execution:
  - For each task, if P(T3_pass) >= threshold, assign T3, else T2
  - Track total expected cost (using task_effort * per-turn-cost / model_fit)
  - If total expected cost exceeds shared cap, downgrade lowest-probability T3 tasks
- Pick threshold that maximizes expected Yield on training set
- Fix threshold before evaluation run

**Option 2: RouteLLM-style percentile threshold (simplest)**
- After training, compute `P(T3_pass)` for all tasks
- Pick threshold so exactly N% of tasks route to T3 (e.g., same % as BudgetFlow's T3 allocation)
- This makes it a direct same-%-allocation comparison

**Option 3: Budget-constrained greedy (most realistic)**
- Sort tasks by `P(T3_pass)`, assign T3 in descending order until expected cost exhausts cap
- No single threshold; it's a budget-constrained selection
- This is the closest to how a real router would work under a cap

**Recommendation: Option 3 for primary, Option 2 for sensitivity analysis.**

---

## 5. Training Data and Label Options

### 5.1 Label Definitions

| Label | Definition | Pros | Cons | Recommendation |
|---|---|---|---|---|
| **A. Binary: T3 pass** | `y=1` if task passed on T3 in diagnostic run | Simplest; requires only T3 diagnostic data | Ignores counterfactual (T2 might also pass); learns "what tasks are easy enough for T3" not "when is T3 needed" | **Primary** |
| **B. T3 better than T2** | `y=1` if T3 passed AND T2 failed on same task | True counterfactual; no approximation | Requires paired outcomes (same task run on both T2 and T3); expensive (2x runs) | **Gold standard if available** |
| **C. Value-aware: T3 worth cost** | `y=1` if task_value * (T3_pass - T2_pass) > extra_t3_cost | Reflects true allocation objective | Requires task_value (value-awareness leak); requires counterfactuals; label becomes policy-specific | **Rejected** -- leaks value-awareness |
| **D. Model Fit estimate: E[T3_pass] > E[T2_pass]** | Continuous: P(pass|T3) - P(pass|T2) from Model Fit | No counterfactual needed; uses existing estimates | Trains classifier to mimic Model Fit; becomes "learned Model Fit" not "learned router" | **Diagnostic only** |

### 5.2 Detailed Analysis

**Label A (Binary: T3 pass) -- RECOMMENDED**

This is the simplest label. The classifier learns P(pass | task_features, T3). A high probability task routes to T3; a low probability task routes to T2 (assuming T3 isn't worth the cost if it won't pass).

**Critical limitation:** In a world where T2 passes everything T3 passes plus some tasks T3 fails (T2 is strictly better), the classifier would learn the wrong thing. We need to check: is T3 ever worse than T2 on specific tasks? If yes, label A is misleading. [Uncertainty -- needs data audit of historical diagnostic runs.]

**Mitigation:** Add a diagnostic check: on the training set, report `P(pass | T3) - P(pass | T2)` for tasks routed to T3 by the classifier. If this is close to 0 or negative for many tasks, label A is misaligned with our objective.

**Label B (T3 better than T2 counterfactual) -- GOLD STANDARD**

This requires each task to be run on both T2 and T3 in the diagnostic set. Creates three categories:
- `y=1`: T3 pass, T2 fail (T3 is genuinely better)
- `y=0`: T2 pass, T3 fail (T2 is better -- routing to T3 would be a loss)
- `y=0` (or exclude): both pass or both fail (no routing signal)

This is what we actually care about for routing. The downside is data cost: we need paired outcomes, which requires ~2x the diagnostic budget.

**Data requirement estimate:** If we use a 30-task evaluation set, we need ~30-60 tasks for training. With paired outcomes that's 60-120 diagnostic runs. Each run costs $0.50-$2.00. Total diagnostic cost: $30-$240. This is reasonable if we already have historical data.

**Label C (Value-aware) -- REJECTED**

Using task_value in the label definition leaks BudgetFlow's value-awareness into the baseline. The classifier becomes "learned value-aware routing" rather than "learned value-oblivious routing." This is precisely the confound we want to avoid: we want to test whether explicit value-awareness beats learned pattern-matching on task features alone.

**Label D (Model Fit estimates) -- DIAGNOSTIC ONLY**

If we train on Model Fit estimates (P(pass|T3) - P(pass|T2)), the classifier learns to reproduce BudgetFlow's own Model Fit estimate. This is circular: it tests "can a classifier mimic BudgetFlow's prior" not "can a classifier predict routing outcomes." Only useful as a sanity check that the classifier architecture can express the relevant function.

### 5.3 Recommended Data Strategy

1. **For the first implementation:** Use label A (T3 pass binary) with XGBoost. Accept and disclose the limitation that we are predicting task success, not routing benefit.

2. **If paired T2/T3 outcomes exist:** Switch to label B. This is the cleanest label for a routing baseline.

3. **Construct a small paired diagnostic set if needed:** Run 20-30 tasks on both T2 and T3 as a one-time calibration pass. Use these to train the router. The evaluation set of 30 tasks is held out and never run in calibration.

4. **Document the label choice in the paper** with a table like the one above, stating what the classifier is and is not learning.

---

## 6. Fairness Risks (Data Leakage, Label Contamination, Value-Awareness Leak)

### 6.1 Task-Level Data Leakage (CRITICAL)

**Risk:** Using a simple random train/test split on individual (task, outcome) samples will put different tasks from the same repo, issue type, or difficulty class in both train and test. This inflates apparent router performance.

**Why this matters for us specifically:**
- SWE-bench tasks from the same repo (e.g., django, sympy) share structural patterns
- Random split leaks repo-specific information: the classifier could learn "django tasks always route to T3" and appear to generalize, when it's just memorizing the repo effect
- The evaluation set of 30 tasks is small enough that leakage from even 1-2 tasks can meaningfully inflate metrics

**Mitigation: Task-level grouped split**

```python
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut

# instance_id is the group key -- each task is in exactly one fold
groups = [task.instance_id for task in training_tasks]
gkf = GroupKFold(n_splits=5)
for train_idx, val_idx in gkf.split(X, y, groups=groups):
    # train on tasks in train_idx, validate on tasks in val_idx
    # NO task appears in both train and val
```

**Additional guard:** If tasks share a repo, consider repo-level grouping. But with only ~10-20 repos for 30 tasks, this would make splits too small. Task-level grouping is the minimum defense; repo-level grouping is desirable but may not be practical with our sample size.

### 6.2 Label Leakage from Historical Data

**Risk:** If the diagnostic runs used for training include any task in the evaluation set, the classifier has seen the test labels. This is an absolute disqualifier.

**Mitigation:**
- Use a strict train/test task separation:
  - `train_tasks`: 20-30 diagnostic tasks (can be from held-out SWE-bench instances or a separate diagnostic split)
  - `eval_tasks`: The fixed 30-task batch used for all policy comparisons
- Never run a task on T3 in diagnostic mode that will later appear in the evaluation set under any policy
- If we only have 30 total tasks, use cross-validation on those 30 for training the router, but then we cannot test on the same 30. **[Uncertainty]** How do we handle this? Options:
  - a) Train on a separate set of SWE-bench tasks (80 tasks held out from evaluation) -> best, if we have historical data
  - b) Train on the 30 evaluation tasks but report results only on the same tasks (training on evaluation set) -> disqualifying for paper
  - c) Cross-validate: train on 25 tasks, test router on the held-out 5, repeat. The router's performance is the average across folds. But then the router baseline is themselves cross-validated, not evaluated on a fresh set.

**Recommendation:** Use a separate held-out SWE-bench split for training (option a). The current SWE-bench Verified has 500 tasks; we can use 30 for evaluation and 30-80 for diagnostic/training purposes. [Uncertainty -- what SWE-bench instances are available?]

### 6.3 Value-Awareness Leak

**Risk:** If the classifier is trained to predict "T3 worth it" using a label that incorporates task_value, the baseline implicitly learns value-awareness. This confounds the comparison: we can no longer claim "explicit value-awareness beats value-oblivious routing."

**Mitigation:**
- Use label A (T3 pass binary) or label B (T3 better than T2 counterfactual). Neither incorporates task_value.
- Do NOT use label C (value-aware worth-it).
- The classifier should see task_features but NOT task_value, criticality_level, or value_source.
- The comparison is: "does learning P(pass|features) beat BudgetFlow's formula with explicit value?"

### 6.4 Feature Overlap with BudgetFlow

**Risk:** If the classifier uses the same Task Effort and Model Fit features that BudgetFlow consumes, the comparison tests "formula vs. learned weighting of same inputs" rather than "value-awareness vs. task-feature prediction."

**Mitigation:**
- Primary baseline: classifier uses raw SWE-bench task features (repo, issue text embedding, test count, file count). Does NOT use Task Effort or Model Fit.
- Ablation: classifier uses the same Task Effort + Model Fit inputs. This tests a narrower question.
- Report both. The primary comparison is the raw-features version.

### 6.5 Budget-Pressure Leak

**Risk:** The learned router allocates T3 statically (pre-computed frozen plan). It does not adapt to budget pressure. This is by design (value-oblivious), but under a very tight cap, it may assign T3 to early tasks and leave none for later tasks. This is a legitimate behavior difference, not a fairness issue, as long as we report it.

**Mitigation:** Report the learned router's budget utilization alongside BudgetFlow's. If the learned router exhausts budget on the first 5 tasks while BudgetFlow conserves, that's evidence (BudgetFlow's budget-pressure adaptation matters), not a confound.

### 6.6 Summary of Fairness Guards

| Risk | Severity | Mitigation | Implementation |
|---|---|---|---|
| Task-level data leakage | **CRITICAL** | GroupKFold by instance_id | `tools/train_learned_router.py` |
| Evaluation set contamination | **CRITICAL** | Train on diagnostic-only tasks, not eval tasks | Task set management in experiment config |
| Value-awareness leak | **HIGH** | Binary pass label, exclude task_value from features | Feature exclusion in training script |
| Feature overlap confound | **MEDIUM** | Separate feature sets for primary vs ablation | Two classifier variants |
| Budget-pressure absent | **LOW** | Document as feature, not bug | Paper discussion section |

---

## 7. Integration Plan with Current BudgetFlow Code

### 7.1 Integration Path: Offline Training -> Frozen Plan

The existing code already supports this integration with **zero runtime changes**:

```
tools/train_learned_router.py (NEW)
  │
  │ reads historical JSONL + SWE-bench task features
  │ trains XGBoost classifier
  │ outputs FrozenRouterPlan JSON
  │
  ▼
paper1/data/plans/learned_router_plan.json (NEW artifact)
  │
  │ loaded by compare_execution.py via --frozen-plan
  │
  ▼
strategies.py:choose_backend() -> "enterprise_router" branch
  │
  │ calls _backend_from_frozen_plan()
  │
  ▼
frozen_router.py:FrozenRouterPlan.lookup(instance_id)
```

### 7.2 New File: `tools/train_learned_router.py`

This is the only new code file. It is a script, not a library module -- no new imports into `budgetflow/`.

```python
# Pseudocode (not actual implementation)
def main(historical_jsonl, task_manifest, output_plan_path):
    # 1. Load historical diagnostic data
    records = load_jsonl(historical_jsonl)  # from diagnostic T3 runs

    # 2. Extract task features + labels
    X, y, groups = build_training_data(records, task_manifest)

    # 3. Train with cross-validation
    classifier = xgb.XGBClassifier(...)
    cv_scores = cross_val_score(classifier, X, y, groups=groups, cv=GroupKFold(5))

    # 4. Train final model on all training data
    classifier.fit(X, y)

    # 5. Predict T3 probability for evaluation tasks
    X_eval = build_eval_features(task_manifest)
    probas = classifier.predict_proba(X_eval)[:, 1]

    # 6. Convert to FrozenRouterPlan
    plan = threshold_or_greedy(probas, task_costs, shared_cap)
    write_frozen_plan(plan, output_plan_path)
```

### 7.3 Files Touched

| File | Change | Reason |
|---|---|---|
| `tools/train_learned_router.py` | **NEW** | Offline training script |
| `paper1/data/plans/learned_router_plan.json` | **NEW** | Generated frozen plan artifact |
| `paper1/src/budgetflow/frozen_router.py` | **No change needed** | Existing `FrozenRouterPlan` supports this |
| `paper1/src/budgetflow/adapter/strategies.py` | **No change needed** | `enterprise_router` and `budgetflow_same_router` strategies exist |
| `paper1/src/budgetflow/experiments/compare_execution.py` | **No change needed** | `frozen_plan` parameter already plumbed through |
| `paper1/src/budgetflow/experiments/compare_config.py` | **Minimal** | Add `"learned_router"` as a strategy name alias mapping to `enterprise_router` routing |
| `paper1/src/budgetflow/task_level_routing.py` | **No change needed** | Not involved in learned router path |

### 7.4 How to Wire in CompareConfig

The simplest approach: add a strategy alias. The `enterprise_router` routing strategy already exists and reads from a `FrozenRouterPlan`. We just need to make it discoverable:

```python
# In compare_config.py or wherever strategy dispatch happens:
ROUTING_ALIASES = {
    "learned_router": "enterprise_router",  # consumes frozen plan
    "learned_router_bf": "budgetflow_same_router",  # BudgetFlow wrapper
}
```

The CLI would be:
```bash
python -m budgetflow.experiments.compare_execution \
    --strategy learned_router \
    --frozen-plan paper1/data/plans/learned_router_plan.json \
    ...
```

### 7.5 Optional: New Strategy Branch in `strategies.py`

If we want a dedicated strategy name for observability (separate from generic `enterprise_router`), we could add a ~5-line branch:

```python
# In choose_backend():
if ctx.strategy == "learned_task_router":
    backend = _backend_from_frozen_plan(ctx, turn)
    ctx.last_decision = RouterDecision(
        backend=backend, reason="learned_router_frozen_plan",
        scores={}, pressure=ctx.budget_pressure, branch="learned_router",
    )
    return backend
```

This is cosmetic (better trace labels) but optional. Using the existing `enterprise_router` path requires zero code changes.

**Recommendation:** Use existing `enterprise_router` path for the initial implementation. Add a dedicated branch only if trace readability becomes an issue during analysis.

---

## 8. Minimal Implementation Path (Step-by-Step)

### Phase 1: Data Preparation (1-2 hours)

1. **Audit available historical data:**
   - Count JSONL rows with T3 outcomes (diagnostic runs).
   - Check how many tasks have paired T2/T3 outcomes.
   - Identify which tasks overlap with the evaluation set (mark as off-limits).

2. **Select training task set:**
   - If enough non-eval tasks exist: use 20-30 held-out SWE-bench tasks.
   - If not: determine whether to run a small calibration batch.
   - Record train/eval task split in a frozen manifest.

3. **Extract features:**
   - Use existing `SwebenchTaskAdapter.features()` to get `task_features` dict.
   - Embed `issue_text` using `text-embedding-3-small` or local `all-MiniLM-L6-v2` (384-dim, no API cost).
   - One-hot encode `repo`.
   - Build feature matrix X (n_tasks, n_features).

4. **Construct labels:**
   - Label A: `y = 1 if task_pass_on_T3 else 0` from historical JSONL.
   - Label B (if paired): `y = 1 if (T3_pass and not T2_pass) else 0`.
   - Build label vector y (n_tasks,).

### Phase 2: Training (1-2 hours)

5. **Write `tools/train_learned_router.py`:**
   - Accept: `--historical-jsonl`, `--task-manifest`, `--output-plan`, `--label-type`, `--shared-cap`.
   - Load data, build X/y/groups.
   - Train with `GroupKFold(n_splits=5)` for internal validation.
   - Fit final model on all training data.
   - Report CV scores (accuracy, precision, recall, ROC-AUC).
   - Output feature importance plot (for paper supplement).

6. **Threshold selection and plan generation:**
   - For each eval task, compute `P(T3_pass)` via `classifier.predict_proba`.
   - Use greedy budget-constrained allocation:
     - Sort eval tasks by `P(T3_pass)` descending.
     - Assign T3 until `sum(E[cost | T3]) >= shared_cap * safety_factor`.
     - Remaining tasks get T2.
   - Write `FrozenRouterPlan` JSON.

### Phase 3: Integration (30 minutes)

7. **Wire into experiment runner:**
   - Copy `learned_router_plan.json` to `paper1/data/plans/`.
   - Run: `python -m budgetflow.experiments.compare_execution --strategy enterprise_router --frozen-plan paper1/data/plans/learned_router_plan.json --routing enterprise_router ...`
   - Verify: frozen plan entries loaded correctly, backend picks match plan.

### Phase 4: Validation (1 hour)

8. **Sanity checks:**
   - Does the classifier output non-trivial probabilities (not all 0.5)?
   - Does the frozen plan assign a mix of T2 and T3 (not all one tier)?
   - Does the budget-constrained plan stay within the cap?
   - Are any eval tasks missing from the plan?

9. **Ablation:**
   - Train with different feature sets (raw features vs. task_effort+model_fit).
   - Compare router performance under both.
   - Report in paper supplement.

### Phase 5: Paper Writeup

10. **Describe in draft:**
    - Baseline name: "RouteLLM-inspired supervised task router."
    - Training data source, feature set, label definition.
    - Cross-validation protocol (GroupKFold).
    - Budget-constrained allocation mechanism.
    - Disclosure of adaptation gaps (see Section 9 below).

---

## 9. Open Questions for Main Agent

1. **Historical data availability:** How many JSONL rows exist with T3 outcomes? Are there any tasks with paired T2/T3 outcomes (same task run on both tiers)? If zero paired outcomes, we default to label A (T3 pass binary) with explicit acknowledgment that we are learning "which tasks T3 can solve" not "which tasks benefit from T3 over T2." [Uncertainty]

2. **Training task set:** Are there 20+ SWE-bench instances NOT in the 30-task evaluation set that have been run in diagnostic mode? If not, we need to decide whether to: (a) run a small diagnostic batch (cost: ~$30-60); (b) use a subset of the evaluation tasks for training (with GroupKFold reporting, but this weakens the baseline); (c) train on the full evaluation set and acknowledge the contamination. [Uncertainty]

3. **Text embedding model:** Should we use OpenAI's `text-embedding-3-small` (paid API, dim=1536) or a local model like `all-MiniLM-L6-v2` (free, dim=384)? The local model avoids API costs for feature extraction but may be less semantically rich for SWE-bench issue text. For 30-100 tasks, either is fine. [Uncertainty]

4. **Label definition final choice:** Label A (binary T3 pass) is simplest but has the confounding issue described in Section 5. If T2 is sometimes better than T3, this label is misaligned. We should check the data before committing. If T2 is never better than T3, label A is a good approximation. [Uncertainty -- needs data audit]

5. **Value-oblivious vs value-agnostic naming:** The classifier ignores task_value by design. Should we call this "value-agnostic" (neutral framing, acknowledges value exists but is not used) or "value-oblivious" (stronger framing, suggests a blind spot)? Recommendation: "value-oblivious" in internal discussion, "value-agnostic" in paper text. [Uncertainty]

6. **One classifier or per-tier?** Currently proposed: single classifier predicting P(T3_pass). Alternative: two classifiers (P(T2_pass) and P(T3_pass)) with routing = argmax over expected value. This adds complexity but better handles the T2-better-than-T3 case. Recommendation: start with single classifier; add two-classifier version only if the single-classifier results show a clear problem.

7. **Paper positioning:** Section 4.3 (Related Work Baselines) should add:
   - "RouteLLM-inspired supervised task router" with ~3 sentences: what it is, what data it trains on, how it differs from original RouteLLM.
   - A "Limitations of this baseline" paragraph: single-tier training labels, no counterfactuals, no value-awareness.

8. **Budget utilization reporting:** Should we report what fraction of the shared cap the learned router actually used? Yes -- this is a required diagnostic. If the learned router exhausts the budget on early tasks, it's spending inefficiently. If it leaves budget unused, it's leaving value on the table. Both are informative.

---

## 10. Sources

### Code repositories (read in full from local clones)

- **lm-sys/RouteLLM** -- Official implementation. Cloned to `/tmp/RouteLLM`. 23 Python files across `routellm/routers/`, `routellm/evals/`, `routellm/`. Key files: `routers.py` (5 routers), `model.py` (MF model), `train_matrix_factorization.py` (training), `controller.py` (serving), `calibrate_threshold.py` (threshold calibration), `benchmarks.py` (evaluation benchmarks). https://github.com/lm-sys/RouteLLM

- **anyscale/llm-router** -- Tutorial notebook. Cloned to `/tmp/llm-router`. Jupyter notebook (`README.ipynb`) + `src/ft.py` (fine-tuning submission), `src/utils.py` (data preprocessing, judge prompt formatting). Demonstrates the Causal LLM approach using Anyscale's managed fine-tuning API. https://github.com/anyscale/llm-router

### Papers

- **RouteLLM paper:** Ong et al., "RouteLLM: Learning to Route LLMs with Preference Data." arXiv:2406.18665. https://arxiv.org/abs/2406.18665

### HuggingFace Datasets (used by RouteLLM)

- `lmsys/lmsys-arena-human-preference-55k` -- Chatbot Arena battle data (55K rows). Columns: `prompt`, `model_a`, `model_b`, `winner_model_a`, `winner_model_b`, `winner_tie`. https://huggingface.co/datasets/lmsys/lmsys-arena-human-preference-55k

- `routellm/mf_gpt4_augmented` -- Pre-trained MF router checkpoint (GPT-4 augmented). https://huggingface.co/routellm/mf_gpt4_augmented

- `routellm/gpt4_dataset` -- 109K GPT-4 judge-labeled training samples for Causal LLM router. https://huggingface.co/datasets/routellm/gpt4_dataset

### Data Leakage Literature

- "Machine Learning VLSI CAD Experiments Should Consider Atomic Data Groups." MLCAD 2024. Demonstrates 38% overestimation from random (non-grouped) splits vs. atomic-group (task-level) splits. https://dl.acm.org/doi/10.1145/3670474.3685970

- `bioLeak` R package -- Leakage-aware resampling and post-hoc auditing. https://cran.imr.no/web/packages/bioLeak/

### Related Implementations

- **Anyscale blog post:** "Building an LLM Router for High-Quality and Cost-Effective Responses." Covers full pipeline: Nectar data -> GPT-4 judge labels -> Llama-3-8B fine-tuning -> RouteLLM evaluation. https://www.anyscale.com/blog/building-an-llm-router-for-high-quality-and-cost-effective-responses

- **Reasoning Router blog (HuggingFace):** Lightweight router using a small classifier to decide whether to use a reasoning model. Conceptual neighbor. https://huggingface.co/blog/AmirMohseni/reasoning-router

### BudgetFlow Files Read for This Audit

- `paper1/docs/north_star.md` (full)
- `paper1/docs/research/related_work_baseline_audit.md` (full)
- `paper1/src/budgetflow/task_level_routing.py` (full)
- `paper1/src/budgetflow/frozen_router.py` (full)
- `paper1/src/budgetflow/adapter/strategies.py` (full)
- `paper1/src/budgetflow/experiments/compare_execution.py` (full)

---

*This audit was produced by the baseline implementation research worker. No code changes were made. All [Uncertainty] markers indicate questions for the main agent before implementation begins.*
