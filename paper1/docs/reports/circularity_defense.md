# Circularity Defense: Manual Value Profile and Sensitivity Requirements

**Date:** 2026-06-09
**Context:** mainline_3x8_v2_mechanism (089) with three value profiles

## The Circularity Risk

The `manual_value` profile pre-registers task values. A critic can argue: if you pick task values that favor budgetflow, you bake the conclusion into the metric. The risk is real — any single value profile can be gamed.

## The Defense: Mandatory Multi-Profile Sensitivity

The paper must never report `manual_value` as the sole headline. Three profiles run together:

| Profile | Source | Role |
|---------|--------|------|
| `equal` | All tasks = 1.0 | Null hypothesis — if bf wins here, it wins without any value signal |
| `manual_value` | Human pre-registered | Primary claim — reflects actual repair priorities |
| `bootstrap_difficulty` | Formula from task metadata (patch_lines, f2p_count, p2p_count, problem_words, gold_file_count) | Algorithmic cross-check — no human judgment |

### Formula for `bootstrap_difficulty`

```
1 + patch_lines + 2*f2p_count + log1p(p2p_count) + 0.01*problem_words + 1.5*gold_file_count
```

This uses only SWE-bench metadata fields that exist before any run. No outcomes, no model behavior, no budgetflow internals.

## Evidence: All Three Profiles Agree

From canonical run 089 (8 tasks × 3 strategies):

| Profile | bf Yield | bare Yield | enterprise Yield | bf leads? |
|---------|----------|------------|-------------------|-----------|
| equal | 6.00 | 4.00 | 2.00 | Yes |
| manual_value | 7.70 | 5.80 | 2.50 | Yes |
| bootstrap_difficulty | 196.62 | 125.07 | 80.94 | Yes |

Budgetflow leads enterprise_router_baseline on Yield and Yield/total$ across all three profiles in this 8-task diagnostic. The direction does not flip when you change the value profile — only the magnitude changes. Scale is small (8 tasks, 24 rows); direction is consistent but magnitude estimates have wide intervals.

## Protocol Requirements

1. **Pre-register before the run.** Both `manual_value` and `bootstrap_difficulty` are fixed in the value matrix JSON before experiment execution. The frozen router plan is also pre-registered. No post-hoc tuning.

2. **Report all three profiles in the paper.** The sensitivity table showing bf leads on equal/manual/bootstrap is the primary robustness check. A reader who distrusts manual_value can look at bootstrap_difficulty (algorithmic) or equal (no value signal) and see the same direction.

3. **Yield/total$ as the T1 headline metric.** This metric includes abort cost in the denominator, so strategies can't game it by aborting cheap tasks. Both yield_per_scoreable_dollar and yield_per_total_dollar appear in compact audit output.

## Remaining Risks (Honest Accounting)

- **8-task scale.** 24 rows total. Direction is clear but magnitude estimates have wide intervals. Scaling to 20+ tasks is needed before claiming generalizability.
- **FormatError/parser noise.** Some aborts are extraction protocol failures, not budget governance failures. The abort taxonomy (extraction_protocol_fail vs budget_exhaustion vs stagnation) is diagnostic but not yet cleaned.
- **Task set is all SymPy.** SWE-bench Lite has other repos. The four new zero-history tasks were selected for complete test_patch/FAIL_TO_PASS metadata, not for diversity. This is a diagnostic limitation, not a circularity one.
- **manual_value has no inter-annotator check.** Values were set by one researcher pre-registration. A second annotator would strengthen the claim but isn't required given bootstrap_difficulty agreement.

## Bottom Line

Circularity is defended by: (a) pre-registration, (b) multi-profile sensitivity with agreement across all three profiles, (c) bootstrap_difficulty as an algorithmic cross-check that uses zero human judgment. The paper's claim is "bf leads enterprise on Yield/$ across value profiles in this 8-task diagnostic," not "bf wins on our favorite value profile." The `manual_value` profile is a pre-registered objective function input (fixed before the run, not derived from outcomes). The paper's robustness argument depends on three-profile directional consistency, not on the absolute values in any single profile.
