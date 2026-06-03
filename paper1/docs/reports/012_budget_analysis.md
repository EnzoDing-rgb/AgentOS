# 012_budget_analysis — BudgetFlow Routing/Cap Tuning Recommendations

Date: 2026-06-03
Based on: postfix_011_sanity 25 rows (5 tasks x 5 strategies)

## Executive Summary

BudgetFlow Full (both tight and loose): **10/10 PASS, $1.13 total cost**. Budget Only: 7/10 PASS, $2.45 total cost. The core gap is caused by BudgetOnlyStepRouter never escalating to T3 (GPT-5.4), not by budget cap miscalibration. Two changes would close the gap: (a) allow budget_only to escalate to T3 under low pressure, (b) tune auto-budget to use tier-aware estimation.

---

## 1. Data Analysis

### 1.1 Strategy Comparison

| strategy | resolved | total_cost | avg_cost | avg_turns | dominant_tier |
|---|---|---|---|---|---|
| all_pro | 5/5 | $0.47 | $0.094 | 5.8 | T3 (100%) |
| budgetflow_full_tight | 5/5 | $0.53 | $0.105 | 6.4 | T3 (100%) |
| budgetflow_full_loose | 5/5 | $0.60 | $0.120 | 6.6 | T3 (100%) |
| budget_only_loose | 4/5 | $0.97 | $0.193 | 29.8 | T2 (100%) |
| budget_only_tight | 3/5 | $1.48 | $0.295 | 38.2 | T2 (100%) |

Key finding: budgetflow_full always routes to T3 (GPT-5.4), budget_only always routes to T2 (qwen3-coder-plus). This is deterministic from the router code, not a runtime behavior emergence.

### 1.2 Tier Usage (100% confirmation)

```
budget_only_tight: 190 picks, 100% T2
budget_only_loose: 147 picks, 100% T2
budgetflow_full_tight: 31 picks, 100% T3
budgetflow_full_loose: 32 picks, 100% T3
all_pro: 29 picks, 100% T3
```

No T1 usage at all (T1 is qwen3-coder-flash, marked as skipped in this run).

### 1.3 Cap Sufficiency Analysis

| task | est_cost | cap | source | budget_only cost | budgetflow_full cost | all_pro cost |
|---|---|---|---|---|---|---|
| sympy-14774 | $0.01 | $0.05 | history_exact | $0.026-$0.028 | $0.050 (hits cap) | $0.047 |
| sympy-18189 | $0.20 | $0.30 | global_fallback | $0.103-$0.175 | $0.119-$0.186 | $0.116 |
| sympy-18057 | $0.20 | $0.30 | global_fallback | $0.299-$0.415 | $0.062-$0.094 | $0.060 |
| sympy-18621 | $0.20 | $0.30 | global_fallback | $0.202-$0.294 | $0.087-$0.260 | $0.089 |
| django-10924 | $1.00 | $1.50 | global_fallback/repo_floor | $0.245-$0.656 | $0.107-$0.109 | $0.160 |

For budget_only_tight and budget_only_loose, memory_exact estimates are MORE accurate (using actual T2 costs from previous runs):
- sympy-18057 memory_exact: est=$0.4487, cap=$0.6731 (vs global_fallback est=$0.20, cap=$0.30)
- sympy-18621 memory_exact: est=$0.2601, cap=$0.3901 (vs global_fallback est=$0.20, cap=$0.30)
- django-10924 memory_exact: est=$0.1597, cap=$1.00 (but this was T3-based, so underestimates T2)

The global_fallback of $0.20 for "easy" bucket is calibrated for T3 costs (from the all_pro/budgetflow_full pilot) and is ~2x too low for budget_only (T2-only) costs.

### 1.4 Failure Deep-Dive

**django-10924 budget_only_tight (repair_fail):**
- 67 turns, $0.656, T2-only
- Agent submitted a patch (source=submission), gold_file_edited=true
- Harness: fail_after=fail — patch existed but was wrong
- Budget still had $0.344 remaining. NOT a budget issue.
- budgetflow_full_tight solved in 7 turns T3 at $0.109
- Root cause: T2 (qwen3-coder-plus) cannot produce a correct patch for this task, even after 67 turns

**sympy-18057 budget_only_tight (repair_fail):**
- 45 turns, $0.415, T2-only
- Same pattern: agent submitted, gold_edited=true, harness fail_after=fail
- Budget had $0.258 remaining
- budgetflow_full_tight solved in 6 turns T3 at $0.094
- Root cause: T2 repair quality insufficient

**sympy-18057 budget_only_loose (budget_fail):**
- 46 turns, $0.299, T2-only, cap=$0.30 exhausted
- Patch existed in worktree (source=worktree), gold_file_edited=true, but agent never submitted
- Harness: test_patch=ok, fail_before=fail, model_patch=ok, fail_after=fail, pass_to_pass=pass
- The patch was on disk but wrong (fail_after=fail). If it had been correct, worktree fallback would have rescued this.
- Root cause: T2 couldn't fix the bug in 46 turns; budget_only_loose never escalated to T3 because BudgetOnlyStepRouter has no code path to T3

### 1.5 Worktree Fallback "Rescues"

sympy-14774 budgetflow_full_tight and budgetflow_full_loose both show:
- Exit: BudgetFlowBudgetError (budget exhausted)
- Patch source: worktree (agent never submitted)
- Harness: fail_after=FAIL → PASS (gold file was correctly edited on disk)
- Cost: exactly $0.050 (hits the $0.05 cap)

This is a true rescue: the agent ran out of money, but the worktree contained the correct patch. The harness evaluates the worktree diff and declares PASS.

This is NOT a timing bug. The agent correctly edited the gold file, passed the reproducer test (test_patch=ok), but failed to submit within budget. The patch quality was good — the agent just needed more time (or should have submitted earlier).

---

## 2. Question Answers

### Q1: Auto-budget calibration

**SymPy easy tasks ($0.05-$0.17 estimates):** For budgetflow_full (T3), all 4 sympy tasks pass comfortably under the $0.30 global_fallback cap, with actual costs of $0.06-$0.26. The $0.05 min_cap is tight for sympy-14774 budgetflow_full (100% used) but the worktree rescue mechanism saves it. For budget_only (T2), the global_fallback cap of $0.30 is too low for some tasks (sympy-18057 loose exhausted $0.30 at 99.7%).

**scale=1.5:** Works well for T3 strategies (actual costs typically 20-90% of cap). For T2 strategies, actual costs can be 2-5x higher than T3 costs, so the 1.5x factor applied to a T3-calibrated estimate produces a cap that is 0.3-0.75x of actual T2 cost. The scale should NOT be global — it should be tier-aware.

**min_cap=$0.10:** This is reasonable for T3 strategies — sympy tasks with T3 cost $0.05-$0.26, so $0.10 provides a safety margin for all except the absolute cheapest tasks. For T2 strategies, $0.10 is far too low (actual T2 costs range $0.03-$0.66). The per-task cap from the estimator (not min_cap) is the binding constraint for most tasks.

The data shows the actual run used min_cap=$0.05, not $0.10 (based on sympy-14774's $0.05 cap).

### Q2: BudgetFlow routing behavior

**budgetflow_full_tight overly favors T2?** No. It uses T3 100% of the time (31/31 picks). The BudgetFlowSelector scores every step and always finds the delta_progress/delta_cost ratio favorable for T3 upgrade at tight budget pressure levels. This is correct behavior for a 3-tier pool where the gap from T2 to T3 is large in both capability and cost.

**budgetflow_full_loose wastes money on unnecessary T3?** One case: sympy-18621 loose at $0.260 vs tight at $0.087 (loose is 3x more expensive). But loose still PASS. Overall loose costs $0.60 total vs tight's $0.53 — a 13% premium. Not a significant waste. The looser pressure lets the selector stay on T3 longer, which can overshoot on easy tasks but provides safety on harder ones.

**Why 100% for full vs 70% for only?** BudgetOnlyStepRouter (policies.py lines 32-64) has no code path that returns T3. With 3 tiers:
- pressure >= 1.2: T1
- pressure >= 0.7: T1
- pressure >= 0.35: T2
- pressure < 0.35: T2

T3 is unreachable. This appears to be a design choice: "budget_only" means "stick to cheap/medium models and never use the premium tier." The problem is that T2 alone cannot solve all tasks even with unlimited budget.

### Q3: Worktree fallback passes (sympy-14774)

These are legitimate rescues, not timing bugs. The agent correctly edited the gold file, passed the reproducer test (harness test_patch=ok), but ran out of budget before submitting. The worktree contained a valid patch.

The agent SHOULD submit earlier. Current behavior: the agent keeps iterating even after gold_edited=true and passing the reproducer test, wasting budget on unnecessary refinement. An early-submit mechanism would:
1. Detect gold_edited + test_patch_ok + 2+ turns of no further gold changes
2. Force submission

This would prevent budget exhaustion on cheap tasks.

### Q4: budget_only failures

**django-10924 tight:** T3 would likely have solved it. All five T3 strategies (all_pro, bf-T, bf-L) solved it in 7-8 turns at $0.11-$0.16. T2 couldn't in 67 turns at $0.66. The fault is not in the budget cap ($1.0 was plenty) but in the model capability gap.

**sympy-18057 tight:** Same answer. T3 solves in 4-6 turns at $0.06-$0.09. T2 fails in 45 turns at $0.42. The T2 model (qwen3-coder-plus) simply cannot produce a correct patch for this task.

**sympy-18057 loose:** The global_fallback cap of $0.30 was too small for T2-only operation. At 46 turns (all T2), the cap exhausted. But even if the cap were $0.67 (memory_exact), the result would likely still be repair_fail — T2 just can't solve this task. Loose didn't escalate to T3 because BudgetOnlyStepRouter has no T3 path, not because of budget pressure.

---

## 3. Concrete Recommendations

### 3.1 min_cap: Raise from $0.05 to $0.10

**Current:** $0.05
**Recommended:** $0.10

Evidence: sympy-14774 budgetflow_full_tight/loose hit the $0.05 cap exactly (100% utilization) and survived only via worktree rescue. $0.10 provides 2x headroom for the cheapest tasks while adding at most $0.05 to total batch cost (negligible). The code default is already $0.10 — the run used $0.05 via `--auto-budget-min 0.05`. Stick with $0.10.

### 3.2 Scale factor: Keep 1.5x global, but add tier-aware override

**Current:** scale=1.5 global, same for all strategies
**Recommended:** scale=1.5 for T3-capable strategies (budgetflow_full, all_pro); scale=2.5 for budget_only (T2-only)

Evidence: budget_only actual costs are 1.7-4.1x the T3-based estimated cost for the same task:
- sympy-18057: T3 cost $0.06, T2 cost $0.30-$0.42 → 5-7x
- sympy-18621: T3 cost $0.09, T2 cost $0.20-$0.29 → 2.3-3.3x
- django-10924: T3 cost $0.11, T2 cost $0.24-$0.66 → 2.2-6x

A scale of 2.5x applied to the T3-calibrated estimate would give:
- sympy-18057: $0.20 * 2.5 = $0.50 (actual T2: $0.30-$0.42, provides headroom)
- sympy-18621: $0.20 * 2.5 = $0.50 (actual T2: $0.20-$0.29, generous)
- django-10924: $1.0 * 2.5 = $2.50 (actual T2: $0.24-$0.66, very generous)

Implementation: add a `strategy_scale` parameter to `AutoBudgetEstimator.estimate()` that multiplies the final cap. Or make the estimator's `_compute_cap` accept a per-strategy override. The estimator itself should remain strategy-agnostic; the caller (run_mini_swe_compare.py) should pass `scale` per strategy.

### 3.3 BudgetFlow routing: Add T3 escalation path to budget_only

**Current:** BudgetOnlyStepRouter returns T1 or T2 only. T3 unreachable.
**Recommended:** Add T3 path at `budget_pressure < 0.15` (very low pressure).

```python
# In BudgetOnlyStepRouter.choose_backend, after n==2 check, before n>=2:
if n >= 3 and budget_pressure < 0.15:
    return RouterDecision(
        backend=ordered[2], reason=f"very_low_pressure={budget_pressure:.3f}_tier3",
        scores={}, pressure=budget_pressure, branch="budget_only",
    )
```

This gives budget_only a narrow path to T3 when budget is abundant (used < 15%). Combined with the scale=2.5 recommendation, budget_only_loose would have cap=$0.50 for sympy-18057, giving pressure ~0.60 at $0.30 spent — not quite qualifying for T3. But budget_only_loose with cap=$0.50 would have enough budget to keep trying T2 longer (46 turns was at $0.30, could reach ~75 turns at $0.50) and pressure would drop into the T3 window after more spending… actually the pressure INCREASES with spending, so this doesn't help. The pressure falls as you spend MORE of the budget.

Correction: budget_pressure = init + used_frac * (max - init). With init=0.01, max=1.5:
- At used_frac=0 (start): pressure=0.01 → qualifies for T3
- At used_frac=0.15: pressure = 0.01 + 0.15 * 1.49 = 0.234 → still qualifies by threshold 0.35
- At used_frac=0.30: pressure = 0.01 + 0.30 * 1.49 = 0.457 → no longer qualifies

So T3 would only be accessible in the first 15% of budget. Better approach: add a "starting pressure" based on estimated cost relative to cap. This lets the router use T3 early when cap is generous, before switching to T2 as pressure rises.

Actually, the real fix is simpler: **Give budget_only early access to T3 when cap is generous relative to estimated cost.** Compute `cap_ratio = cap / estimated_cost`. If cap_ratio >= 2.0, let the starting 3 turns use T3.

Even simpler: for the next experiment, just remove the "T3 is unreachable" restriction from budget_only entirely. Make it behave like budgetflow_full but with a much higher pressure threshold for T3. That is: `budget_pressure * 3.0` for the T3 upgrade threshold, vs the normal threshold.

### 3.4 Auto-budget floor: Django vs SymPy

**Current:** `_REPO_FLOOR_ESTIMATED_COST` has `"django/django": 1.00`
**Recommended:** Keep the $1.00 floor for Django. Add floor for all repos to prevent pathological min_cap binding.

The $1.00 Django floor is working correctly: django-10924 with T3 costs $0.11-$0.16 (7% of $1.50 cap), and even T2 costs $0.25-$0.66 (16-44% of $1.50). The floor prevents under-budgeting. Do NOT add a SymPy floor — sympy tasks have median costs of $0.05-$0.17 with T3 and the global_fallback + scale=1.5 gives adequate $0.30-$0.26 caps for T3 operation.

For budget_only, use the tier-aware scale (2.5x) rather than per-repo floors. This is cleaner — costs correlate more with strategy/tier than with repo for these tasks.

### 3.5 Next experiment parameters

Run a new postfix_012_tuned experiment with these exact parameters:

**Matrix:** Same 5 tasks, test against these strategy variants:

| strategy | routing | budget | scale | min_cap | description |
|---|---|---|---|---|---|
| bf-tight | budgetflow_full | tight | 1.5 | $0.10 | Baseline (unchanged) |
| bf-loose | budgetflow_full | loose | 1.5 | $0.10 | Baseline (unchanged) |
| bo-tight-v2 | budget_only | tight | 2.5 | $0.10 | Tier-aware scale |
| bo-loose-v2 | budget_only | loose | 2.5 | $0.10 | Tier-aware scale |
| bo-esc-tight | budget_only | tight | 1.5 | $0.10 | With T3 escalation (pressure < 0.15) |
| bo-esc-loose | budget_only | loose | 1.5 | $0.10 | With T3 escalation (pressure < 0.15) |
| bf-tight-fix | budgetflow_full | tight | 1.5 | $0.10 | + early submit at gold_edited + 2 turns no progress |
| all_pro | all_pro | uncapped | N/A | N/A | Baseline (unchanged) |

This is 8 strategies x 5 tasks = 40 rows. Focus on answering:
1. Does tier-aware scale (2.5x) let budget_only survive long enough to solve?
2. Does T3 escalation path let budget_only actually solve tasks T2 can't?
3. Does early submit save budget on cheap tasks without hurting resolve rate?
4. Are the 3 budget_only failures from 011 convertable to PASS?

**Expected outcomes:**
- bo-esc-* should reduce or eliminate the T3-unreachable gap, potentially solving all 5 tasks
- bo-v2-* should eliminate budget_fail (sympy-18057 loose) by giving more headroom
- bf-tight-fix should eliminate the worktree-rescue pattern (submit before budget exhausts)
- Total cost should be comparable to budgetflow_full, validating that tier-aware budgeting + T3 escalation achieves similar results to the full selector

---

## 4. Parameter Summary

| Parameter | Current | Recommended | Rationale |
|---|---|---|---|
| min_cap | $0.05 (in run), $0.10 (default) | $0.10 | Use default. $0.05 causes worktree rescue on cheapest tasks |
| scale (global) | 1.5 | 1.5 (keep for T3-capable) | Works for budgetflow_full/all_pro |
| scale (budget_only) | 1.5 | 2.5 | T2 costs 2-5x higher than T3 for same task |
| budget_only T3 threshold | unreachable | pressure < 0.15 | Gives T3 a narrow window when budget is mostly unspent |
| early submit | none | gold_edited + 2 quiet turns | Prevents budget exhaustion on easy tasks |
| Django floor | $1.00 | $1.00 (keep) | Adequate for both T2 and T3 |

---

## 5. Code Changes Required

### 5.1 `auto_budget.py` — Strategy-aware scale

In `run_mini_swe_compare.py` line ~1326, pass `scale` per strategy rather than globally:

```python
# Current (line 1326-1328):
est = estimator.estimate(
    task, scale=args.auto_budget_scale, ...

# Proposed:
strategy_scale = args.auto_budget_scale
if strategy.startswith("budget_only"):
    strategy_scale = args.auto_budget_scale * 1.67  # 1.5 -> 2.5
est = estimator.estimate(
    task, scale=strategy_scale, ...
```

Or add `--auto-budget-scale-budget-only` as a separate CLI flag.

### 5.2 `policies.py` — Add T3 path to BudgetOnlyStepRouter

Insert between lines 55 and 61 (after `budget_pressure >= 0.35` check, before default):

```python
if n >= 3 and budget_pressure < 0.15:
    return RouterDecision(
        backend=ordered[2], reason=f"very_low_pressure={budget_pressure:.3f}_tier3",
        scores={}, pressure=budget_pressure, branch="budget_only",
    )
```

### 5.3 `adaptive_routing.py` — Early submit trigger

Add to `EvidenceRescueState` or create a new `EarlySubmitState` that forces submission after:
- gold_edited=true AND
- 2+ consecutive turns with no further gold changes AND
- harness test_patch=ok (from the last run step)

Or simpler: in the main loop (`mini_swe_proxy.py`), after each step check if gold_edited and remaining budget < 2 * expected_step_cost and test_patch_ok, then submit.

---

## 6. Verification

Before running the full 40-row experiment, run a 2-task smoke test:
- sympy-18057 (hardest for budget_only — both tight and loose fail)
- sympy-14774 (easiest — tight cap, worktree rescue pattern)

Test matrix: all 8 strategy variants above. This is 2 x 8 = 16 rows, quick to run. Verify:
- bo-esc-* solves sympy-18057 (currently budget_only fails)
- bo-v2-* doesn't exhaust budget on sympy-18057
- bf-tight-fix submits before exhaustion on sympy-14774
- No regression on sympy-14774 (all strategies should still PASS)
