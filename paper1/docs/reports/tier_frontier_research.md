# Tier Frontier Calibration Research — 2026-06-10

Analysis of 4×12 paid diagnostic to inform BudgetFlow routing policy changes.
All data from `mainline_4x12_paid_diagnostic.jsonl` (48 runs, $0.98 total).

## 1. Root Cause Hypothesis

**Primary: BudgetFlow routing has baked-in "T3 is expensive" priors that are wrong for the current ModelCatalog.**

Under current pricing (T2=$0.28/$1.12, T3=$0.294/$1.793 per 1M), T3 input is only 1.05× T2.
The per-turn cost difference is ~$0.001 vs ~$0.0017, but T3 solves in 3-5 turns vs T2's 14+.
The router's implicit model is from an era when T3 was 10× T2, and it hasn't been recalibrated.

**Secondary contributors (each smaller than the primary):**

| Factor | Mechanism | Impact | Evidence |
|---|---|---|---|
| `_budgetflow_max_tier` default=T2 | Caps strongest tier until pressure ≥ 0.15 | Prevents early T3 use | bf_full 13480: 14 T2 turns before any T3 consideration |
| `progress_prior` delta T3−T2 ≈ 0.01−0.03 | Tiny delta → large upgrade threshold | Makes T3 seem not worth the cost | delta_progress=0.01 means upgrade_threshold ≈ 100× delta_cost |
| `conservation_factor` in ValueAwareSelector | pressure>0.3 → conservation=1+max(0,p−0.3)×1.5 | Escalation gets HARDER as budget depletes | Opposite of correct behavior for solvable tasks |
| Frozen plan no-T3 for new tasks | Static T2 cap on zero-history tasks | Guaranteed failure on unseen hard tasks | same_router 0/4 on new tasks, enterprise 1/4 |
| `BUDGET_PRESSURE_INIT = 0.01` | Starts at 1% of budget consumed | Router doesn't feel pressure until significant budget is spent | All familiar tasks stay at pressure < 0.09, never consider T3 |

**Tertiary: protocol/parser sensitivity.**
- bare_strong had 3 extract_fail aborts (parser errors with T3)
- budgetflow_full had only 1 abort
- T2 has fewer parser errors but more true_fails from capability gaps
- This is an interaction effect, not the root cause

## 2. How Routing Decides T2 vs T3 (Current Code)

### Per-turn decision pipeline (mini_swe_proxy.py:303-377):

```
1. choose_backend()          → Selector picks tier based on pressure × progress × value × cost
2. Adaptive starting tier    → Override if memory says start stronger
3. Strongest starter window  → Frontload T3 for a window
4. Evidence rescue           → T3 window when gold-edit evidence threshold met
5. Value-triggered escalation → T3 window for high-value stalled tasks
6. _apply_progress_escalation → Patience/max_turns force tier change
7. Gold edit repair guard    → Force T3 if T2 repair loop after gold edit
8. Provider fallback         → Retry on lower/higher tier if primary unavailable
```

### Selector upgrade formula (selector.py:50-55):

```
upgrade_threshold = delta_cost / (delta_progress × 0.3 × w_i)
```

Where:
- `delta_cost` = cost_diff(T_new, T_current) ← from catalog
- `delta_progress` = progress_prior[stage][T_new] − progress_prior[stage][T_current] ← near-zero for T3−T2
- `w_i` = stage weight × value_multiplier (ValueAwareSelector only)
- `PROGRESS_SCALE = 0.3`

**Why T3 is rarely chosen on familiar tasks:**
- delta_progress(T3−T2) = 0.68−0.67 = 0.01 (localization) or 0.68−0.65 = 0.03 (repair)
- delta_cost ≈ 0.0002 per turn
- upgrade_threshold ≈ 0.0002 / (0.01 × 0.3 × 1.0) = 0.067
- budget_pressure starts at 0.01 and rises slowly → takes many turns to reach 0.067

### _budgetflow_max_tier (strategies.py:135-165):

```python
max_tier = second_cheapest.tier  # T2
if budget_pressure >= 0.15:      # 15% of budget spent
    max_tier = strongest.tier     # T3 unlocked
```

For bf_full with $2.70 cap: need to spend $0.40 before T3 is even allowed.
By then, 3-5 tasks have already completed (or failed) suboptimally on T2.

### ValueAwareSelector conservation (selector.py:132-133):

```python
conservation = 1.0 + max(0.0, budget_pressure - 0.3) × 1.5
```

At pressure=0.5: conservation=1.3 → upgrade threshold ×1.3 (harder to escalate).
This is **correct for budget depletion** (don't waste last dollars on hard tasks)
but **wrong when pressure comes from T2 inefficiency** (spending budget on T2 turns
that don't produce progress).

### Frozen plan mechanism (strategies.py:286-303):

```python
# enterprise_router and budgetflow_same_router:
entry = ctx.frozen_plan.lookup(turn.workflow_id)
preferred_model = entry.preferred_model  # "tier2" for 10/12 tasks
# Falls back to cheapest if lookup fails
```

10 of 12 frozen plan entries specify tier2. The two tier3 entries (16988, 20639) use T3.
Zero-history tasks are all tier2, so they get 0% T3.

## 3. Evidence from 4×12 Data

### 3.1 T2 is false economy on solvable tasks

| Task | bare T3 cost | bf_full cost | ratio | T3% in bf | Why |
|---|---|---|---|---|---|
| 13480 | $0.0025 (3 turns) | $0.0190 (14 turns) | 7.6× | 0% | Stayed T2 all 14 turns, never reached pressure threshold |
| 14774 | $0.0026 (3 turns) | $0.0046 (5 turns) | 1.8× | 20% | Brief T3 at end |
| 20154 | $0.0036 (3 turns) | $0.0072 (5 turns) | 2.0× | 60% | Earlier T3 escalation |

### 3.2 Value-aware pressure correctly identifies zero-history tasks

New tasks get eff_p > 0.4 after 2-3 turns, enabling T3 in bf_full:
- 15011: 90% T3, pass
- 16792: 89% T3, true_fail
- 23117: 86% T3, pass
- 21055: 90% T3, true_fail

Same tasks under frozen plan (same_router/enterprise): 0% T3, 0/4 pass.

### 3.3 Two bf_full failures that T3 didn't rescue

- **16988** ($0.0211 abort): 6 T2 preamble consumed $0.013 before T3 escalated.
  T2 turns were pure waste — T3 could have solved in 5 turns.
- **21055** ($0.0149 true_fail): 90% T3 but still failed. This is a genuine capability gap,
  not a routing failure. Same as 19007 and 20639 (fail under ALL strategies).

### 3.4 Two bf_full rescues over bare_strong

- **12419**: bare abort (extract_fail after 5 T3 turns), bf pass $0.0186 (mixed T2/T3)
- **20212**: bare abort (extract_fail after 4 T3 turns), bf pass $0.0338 (mixed T2/T3)

bf_full's multi-tier approach with progress-triggered escalation rescued these
from parser failures that killed bare_strong early.

### 3.5 3×8 → 4×12 signal changes

The 4 new zero-history tasks shift results significantly:
- On 8 familiar tasks: bf_full and bare likely closer in pass rate
- On 4 new tasks: bf_full passes 2/4 (value-aware escalates), bare passes 3/4 (always T3)
- The frozen-plan strategies fail 3-4/4 on new tasks

Signal is not from T3 price change (current T3 is already cheap). Signal is from
**task composition** — more unseen tasks → bigger gap between adaptive (bf_full) and static (frozen plan).

## 4. Recommended Changes

### 4.1 Tier Frontier Calibration (new, lightweight)

Add `src/budgetflow/tier_frontier.py`:

```python
@dataclass(frozen=True)
class TierFrontier:
    """Calibrates the upgrade frontier from ModelCatalog prices and priors."""
    t2_in: float   # $/1M input
    t2_out: float
    t3_in: float
    t3_out: float
    t3_t2_input_ratio: float
    t3_t2_output_ratio: float
    # Derived
    per_turn_premium: float        # T3 cost premium per typical turn
    upgrade_pressure_threshold: float  # When to allow T3
    t3_willingness: float          # 0-1, how eager to use T3

    @classmethod
    def from_catalog(cls) -> TierFrontier:
        """Auto-calibrate from current MODEL_CATALOG."""
        ...

    def effective_max_tier_pressure(self) -> float:
        """Return the budget_pressure at which T3 should be allowed."""
        # When T3/T2 input ratio < 1.5: return 0.02 (essentially always allow)
        # When 1.5-3.0: return 0.10
        # When > 3.0: return 0.20 (expensive, be conservative)
```

**How it integrates:**
- `_budgetflow_max_tier()` reads `frontier.effective_max_tier_pressure()` instead of hardcoded 0.15
- `BudgetFlowSelector` reads `frontier.upgrade_pressure_threshold` as base pressure floor
- `ValueAwareSelector.conservation` slope scales with `frontier.t3_willingness`
- Computed once at startup from catalog, frozen for the run

### 4.2 Fix progress_prior delta

Current progress_prior values make T3−T2 delta near-zero:

| Stage | T2 | T3 | Δ |
|---|---|---|---|
| localization | 0.67 | 0.68 | 0.01 |
| repair | 0.65 | 0.68 | 0.03 |
| validation | 0.63 | 0.66 | 0.03 |

These should be calibrated from actual run data, not hand-set. For now:
- Increase T3 repair prior to 0.75 (was 0.68)
- Increase T2 repair prior to 0.60 (was 0.65) — T2 repair is demonstrably worse
- This widens repair Δ from 0.03 to 0.15, making upgrade threshold 5× lower

### 4.3 Fix _budgetflow_max_tier threshold

Current: T3 allowed when budget_pressure ≥ 0.15 (15% of $2.70 = $0.40 spent).
Change to: configurable via TierFrontier, default 0.02 when T3/T2 ratio < 1.5.

### 4.4 Bare T2 baseline (already supported)

`all_tier2` routing already exists in `choose_backend()` line 186. Add as `DIAGNOSTIC_STRATEGIES` entry:
```python
CompareStrategy("bare_t2_baseline", "all_tier2"),
```
Or reuse existing `budget_only_t2` (always picks cheapest = T2 since T1 excluded).

### 4.5 What NOT to change

- **Don't change frozen plan semantics** — it must remain static/pre-registered for mechanism isolation
- **Don't change ValueAwareSelector's value multiplier** — it works correctly (new tasks get T3)
- **Don't remove conservation factor entirely** — it prevents budget exhaustion on hard tasks
- **Don't change the per-turn pipeline order** — it's well-structured
- **Don't introduce model adapter or ML** — keep calibration as static math
- **Don't universally default to T3** — T2 is still useful for cheap tasks and as fallback

## 5. Next-Round Strategy Design

Recommended 4 strategies for next diagnostic:

| # | Strategy | Routing | Purpose |
|---|---|---|---|
| 1 | bare_t2_baseline | `all_tier2` | Cost floor: pure T2, no routing |
| 2 | enterprise_router_baseline | `enterprise_router` | Frozen plan baseline (unchanged) |
| 3 | budgetflow_same_router | `budgetflow_same_router` | +shared ledger over frozen plan |
| 4 | budgetflow_full | `budgetflow_value_aware` | +value-aware routing WITH tier_frontier calibration |

Or if keeping 4:
`bare_t2, enterprise_router, budgetflow_same_router, budgetflow_full`
(drop bare_strong_model since it's no longer the right baseline — T3 is cheap)

## 6. Price Sensitivity: T3 ×2 Impact

| Strategy | current cost | T3×2 cost | increase |
|---|---|---|---|
| bare_strong_model | $0.08 | $0.17 | +100% |
| enterprise_router_baseline | $0.43 | $0.44 | +3% |
| budgetflow_same_router | $0.27 | $0.29 | +5% |
| budgetflow_full | $0.19 | $0.30 | +55% |

T3×2 would:
- Make bare_strong 2× more expensive but still cheaper than enterprise_router ($0.17 vs $0.44)
- Nearly close the gap between bf_full ($0.30) and enterprise_router ($0.44)
- Justify bf_full's T2/T3 balancing more strongly
- Make the tier_frontier_calibration even more important

**Recommendation: don't change catalog now.** Run one more diagnostic with current prices + tier_frontier calibration first. This gives a clean A/B: same prices, better routing. Then evaluate T3×2 as a separate sensitivity analysis.

## 7. Observability Gaps

### Current JSONL is sufficient for:
- Per-task pass/fail/cost breakdown
- Turn-level tier choice, pressure, router branch
- Failure classification (failure_class, failure_stage)
- Per-tier turn counts and token usage

### Missing for tier frontier debugging:

| Field | Location | Purpose |
|---|---|---|
| `tier_frontier_*` | top-level run row | What calibration was active (threshold, willingness, ratios) |
| `selector_upgrade_threshold` | turn trace | The actual threshold the selector compared against |
| `selector_delta_progress` | turn trace | The delta_progress used in the upgrade decision |
| `selector_delta_cost` | turn trace | The cost delta used in the upgrade decision |
| `max_tier_reason` | turn trace | Why max_tier was set (default/pressure_lift/adaptive) |
| `conservation_factor` | turn trace | The conservation multiplier applied |

These are all low-cost additions (pass-through of already-computed values).

## 8. Verification Plan (No-Paid)

Before next paid run, verify with no-paid tests:

1. **Unit test**: `TierFrontier.from_catalog()` produces correct calibration for current catalog
2. **Unit test**: `TierFrontier.from_catalog()` with mock T3×2 catalog produces higher thresholds
3. **Unit test**: `_budgetflow_max_tier()` uses frontier threshold instead of hardcoded 0.15
4. **Unit test**: `all_tier2` strategy exists in catalog with correct routing
5. **Paid-readiness-only**: new 4-strategy set passes with correct budget, memory=off, value=pre_registered_manual
6. **Mock turn trace**: verify upgrade_threshold and delta_progress appear in traces
7. **Focused tests**: all existing tests pass (no regression on selector, frozen plan, routing)

## 9. Summary

| Item | Answer |
|---|---|
| Root cause | progress_prior delta T3−T2 ≈ 0 makes router blind to T3 value; max_tier threshold too high; conservation factor double-penalizes |
| Min code changes | 1) `tier_frontier.py` (new, ~80 lines), 2) `strategies.py` plug frontier into `_budgetflow_max_tier`, 3) `model_tiers.json` widen progress_prior T3−T2 gap, 4) `compare_config.py` add `bare_t2_baseline` strategy |
| Don't change | Frozen plan, ValueAwareSelector value_multiplier, turn pipeline order, no ML/adapter |
| No-paid verification | TierFrontier unit tests, strategy catalog test, paid-readiness-only, 373 tests no regression |
| T3×2 recommendation | Not yet. Run one diagnostic with current prices + better routing first |
