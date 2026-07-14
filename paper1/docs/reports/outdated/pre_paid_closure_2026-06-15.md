# Pre-Paid Closure Report — June 15, 2026

Six-phase prep pass before next paid counter-review round. No paid experiments.

## Phase Summary

| Phase | What | Verdict |
|---|---|---|
| 1 | Taxonomy closure | CLEAN — 0 old names in active code/tests/preflight |
| 2 | Run/resume ledger hardening | CLEAN — PID locks, sibling detection, cost accounting |
| 3 | Budget regime compiler / readiness gate | CLEAN — pressure contract, calibration audit, BLOCK gate |
| 4 | Cost catalog / sensitivity | CLEAN — model_tiers.t3x3.json, recost CLI, crossover at ~3x |
| 5 | 5×20 postmortem audit | DONE — projection MAPE 53.5%, 22-47% budget utilization |
| 6 | 15-task candidate gold harness gate | DONE — 10 PASS, 5 FAIL, 2 new repos clean |

---

## Files Changed (48 files, +953 / −391)

### New files

| File | Phase |
|---|---|
| `paper1/docs/config/model_tiers.t3x3.json` | 4 |
| `paper1/src/budgetflow/recost.py` | 4 |
| `paper1/src/budgetflow/allocation.py` | (prior) |
| `paper1/docs/reports/mainline_5x20_calibration_audit.json` | 5 |
| `paper1/docs/reports/mainline_5x20_postmortem_2026-06-15.md` | 5 |
| `paper1/docs/reports/15_candidate_gold_harness_gate_2026-06-15.md` | 6 |
| `paper1/docs/reports/5x20_candidate_gate_2026-06-15.md` | 6 |
| `paper1/data/runs/gold_harness_probe_15_candidates.jsonl` | 6 |
| `paper1/tests/test_allocation_context.py` | (prior) |

### Key modified files

| File | Change | Phase |
|---|---|---|
| `paper1/src/budgetflow/run_series.py` | PID lock files, sibling stem detection, repair mode (+114) | 2 |
| `paper1/src/budgetflow/experiments/budget_binding.py` | Pressure contract, calibration audit, readiness gate (+359) | 3 |
| `paper1/src/budgetflow/run_observability/checks.py` | Cost accounting raw/dedup/retry (+58) | 2 |
| `paper1/src/budgetflow/experiments/compare_cli.py` | `--repair` flag, strategy name normalization | 2 |
| `paper1/src/budgetflow/experiments/compare_config.py` | Strategy name normalization | 1 |
| `paper1/src/budgetflow/adapter/strategies.py` | AllocationContext integration | (prior) |
| `paper1/src/budgetflow/adapters/swebench_value.py` | task_value/task_effort schema | (prior) |
| `paper1/src/budgetflow/value_matrix.py` | bootstrap schema split | (prior) |
| `paper1/src/budgetflow/value_efficiency.py` | effort enrichment | (prior) |
| `paper1/tests/test_budget_binding.py` | Updated for pressure contract API (+35) | 3 |
| `paper1/tests/test_run_observability_audit.py` | Cost accounting tests (+98) | 2 |
| `paper1/tests/test_run_series.py` | Sibling detection, lock, repair tests (+91) | 2 |

### Deleted paths

None. All phases are additive — no old files or paths removed.

---

## Design Decisions

1. **target_utilization reference is p75 of the configured paper-mainline strategy set, not any single BudgetFlow policy.** The hard cap `p75 / 0.80` prevents BudgetFlow from inflating its own budget. Proven in tests.

2. **Pressure contract is passive-only.** It writes assertions/violations/grade into the plan but never changes `plan.decision`. Grade=fail is informational, not a gate.

3. **Calibration gate CAN block.** If `prior_calibration.overall_mape > 60%`, `calibrate_budget()` returns `decision=BLOCK`. The 5×20 audit (MAPE=53.47%) would trigger WARNING but not BLOCK.

4. **Gold harness PASS means harness-admissible, NOT agent-solvable.** The gate only verifies that the local test infrastructure can execute the SWE-bench test spec. Zero information about model capability.

5. **Recost is offline and read-only.** It recalculates cost fields under different T3/T2 price ratios but never modifies outcomes, verdicts, or patches.

6. **No task-id if/else in mechanism code.** pylint, seaborn, pytest, xarray, sklearn are handled through the adapter layer only. The mechanism layer has zero task-id branches.

7. **Cost accounting tracks 3 numbers per strategy.** `raw_paid_cost` (all rows), `dedup_scored_cost` (last row per task, scored only), `duplicate_retry_overhead` (raw − dedup). The 5×20 had 37 duplicate rows costing $1.43 (41% of dedup cost).

---

## Phase 1: Taxonomy Closure

Verified zero occurrences of old strategy names in active code:

| Old Name | Occurrences |
|---|---|
| `budgetflow_full` | 0 (in code/tests; only in historical JSONL) |
| `task_level_control` | 0 |
| `budgetflow_mechanism_diagnostic` | 0 |
| `budgetflow_value_aware` | 0 |

6 paper-facing names active: `bare_t2_baseline`, `bare_t3_baseline`, `enterprise_router_baseline`, `budgetflow_same_enterprise_router`, `budgetflow_task_level`, `budgetflow_segment`.

`compare_config.py` normalizes old→new names at the config boundary. `budget_binding.py._HISTORICAL_NAME_MAP` handles old names in calibration audit.

---

## Phase 2: Run/Resume Ledger Hardening

### PID lock files

`run_series.py` now creates `<stem>.lock` files containing the allocating PID. Before allocating a stem, it checks:
- Lock file exists → read PID
- If PID is alive and not self → SystemExit with clear message
- If PID is dead → stale lock, overwrite

### Sibling stem detection

`detect_sibling_stems()` finds `<series>-v<N>.jsonl` files sharing the same series base. `sibling_stems_exist()` returns True if multiple -N suffixes exist.

### Repair mode

`--repair` CLI flag acknowledges sibling fragmentation and targets the latest -N stem. Without `--repair`, sibling detection blocks new runs.

### Cost accounting

`_check_cost_accounting()` in `checks.py` computes per-strategy:
- `raw_paid_cost` — sum of all rows
- `dedup_scored_cost` — last row per (strategy, instance_id), scored only
- `duplicate_retry_overhead` — raw − dedup

Wired into `check_jsonl()` via `checker.py`.

---

## Phase 3: Budget Regime Compiler / Readiness Gate

### Pressure contract

`_build_pressure_contract()` writes assertions into `plan.pressure_contract`:
- `t2_loose`: bare_t2 utilization < 50% target
- `t3_tight`: bare_t3 utilization > 80% target
- `budgetflow_near_target`: budgetflow_segment within ±20% of target
- Grade: `pass` (all pass), `warn` (violations, no inversion), `fail` (T3 < T2 inverted)

Pressure contract is passive — grade never changes `plan.decision`.

### Calibration audit

`audit_calibration()` compares projected vs actual spend per strategy post-run:
- Computes MAPE per strategy and overall
- Confidence: `high` (MAPE < 30%), `medium` (30-60%), `low` (> 60%)
- Returns `CalibrationAudit` dataclass, writes to JSON

### Readiness gate

`calibrate_budget()` accepts `prior_calibration` parameter:
- MAPE > 60% → `decision=BLOCK`
- MAPE 30-60% → `decision=WARNING`
- MAPE < 30% → high confidence, no gate

The 5×20 calibration audit (MAPE=53.47%) triggers WARNING when passed as `prior_calibration`.

---

## Phase 4: Cost Catalog / Sensitivity

### New model catalog

`docs/config/model_tiers.t3x3.json` — T3 at 3× calibrated transaction price ($0.882/$5.379 per 1M tokens). Base T2 prices unchanged.

### Recost CLI

`src/budgetflow/recost.py` — standalone offline tool:
- `recost_record(record, t3_multiplier)` — recalculates costs for a single row
- `run_sensitivity(jsonl_path, ratios)` — sweeps across ratios (1.5x, 2x, 3x, 5x, 10x)
- `rank_strategies(report, metric)` — ranks by yield/$ or any metric

Usage: `python -m budgetflow.recost <jsonl_path> [output_path]`

### Key finding: crossover at ~3x

At T3/T2 = 1.5x → bare_t3 beats bare_t2 in yield/$
At T3/T2 = 2.0x → bare_t3 still ahead (35.0 vs 29.0)
At T3/T2 = 3.0x → bare_t2 overtakes (27.9 vs 23.3)
At T3/T2 = 5.0x → bare_t2 dominates (25.8 vs 14.0)

The crossover point is ~3x the calibrated T3 transaction price.

---

## Phase 5: 5×20 Postmortem Audit

Full report: `docs/reports/mainline_5x20_postmortem_2026-06-15.md`
Calibration audit: `docs/reports/mainline_5x20_calibration_audit.json`

### Budget was not binding

- Raw spend: $3.50 across 137 rows (22 duplicate)
- Actual utilization: 22-47% against $1.2262/task hard cap
- Root cause: projection overestimated costs by 24-73% (MAPE=53.5%)

### Per-strategy projection error

| Strategy | Projected | Actual | Error |
|---|---|---|---|
| bare_t2_baseline | $0.75 | $0.57 | −24% |
| bare_t3_baseline | $1.51 | $0.40 | −73% |
| enterprise_router_baseline | $0.75 | $0.37 | −51% |
| budgetflow_same_enterprise_router | $0.75 | $0.27 | −65% |
| budgetflow_segment | $0.98 | $0.45 | −54% |

### Task quality

| Repo | Pass Rate | Verdict |
|---|---|---|
| sympy (16 tasks) | 41.7% | Core signal |
| django (4 tasks) | 10.0% | 2 admissible, 2 infra-contaminated |
| sphinx-doc (2 tasks) | 20.0% | 1 solvable (7975), 1 ceiling (10325) |
| psf/requests (2 tasks) | 0.0% | Protocol/parser noise — drop |

### Cost accounting

| Metric | Value |
|---|---|
| Raw rows | 137 |
| Raw paid cost | $3.50 |
| Dedup unique (strategy, task) | 100 |
| Dedup scored cost | $2.06 |
| Duplicate rows | 37 |
| Duplicate retry overhead | $1.43 (41% of dedup) |

---

## Phase 6: 15-Task Candidate Gold Harness Gate

Full report: `docs/reports/15_candidate_gold_harness_gate_2026-06-15.md`
Raw data: `data/runs/gold_harness_probe_15_candidates.jsonl`

### Results

| Status | Count | Tasks |
|---|---|---|
| PASS | 10 | sympy×3, django-13447, sphinx×2, pylint×2, seaborn×2 |
| FAIL | 5 | django-16527, pytest×2, xarray-4248, sklearn-13584 |

### New repo health

| Repo | Status | Ready? |
|---|---|---|
| pylint-dev/pylint | CLEAN | Yes — standard pytest, pip install works |
| mwaskom/seaborn | CLEAN | Yes — pip install works |
| pytest-dev/pytest | BLOCKED | No — needs conftest/fixture adapter |
| pydata/xarray | BLOCKED | No — needs scientific Python deps |
| scikit-learn/scikit-learn | BLOCKED | No — build chain too heavy |

All 5 failures share the same root: the local test harness cannot execute the SWE-bench test spec. `fail_before=False` means pre-patch tests don't register as failing. These are harness adapter problems, not task or agent problems.

---

## Residual Risks

1. **pylint and seaborn are untested in paid experiments.** The 5×20 showed new repos (Requests, Django, Sphinx) had high parser failure rates. pylint/seaborn may have similar protocol issues despite clean gold harness passes.

2. **No agent solvability data for any of the 15 candidates.** Gold harness PASS only verifies test infrastructure. BudgetFlow has no prior JSONL for pylint or seaborn — first paid round will be cold-start diagnostic.

3. **Projection model MAPE=53.5%.** Any `target_utilization` budget will trigger WARNING. Use `frozen_plan_cap_sum` instead.

4. **Django-13447 is the only Django task that passed the harness.** Single-task repo coverage is weak evidence.

5. **pytest and xarray are scientifically valuable but blocked.** They exercise failure modes (plugin systems, scientific computing) that would stress-test BudgetFlow generalization. Defer to future round after harness adapter work.

6. **Sibling stem fragmentation addressed but unverified in paid context.** The PID lock and sibling detection code is tested in isolation. The real test will be the next multi-strategy paid run.

7. **Gold harness probe polluted site-packages.** The `pip install -e .` commands for seaborn and pytest left .pth files in `/root/anaconda3/lib/python3.*/site-packages/`. These were cleaned up post-probe. Future gold harness probes should use `--target` isolation or virtualenvs.

---

## Next Paid Round Recommendation

### Strategy set: paper mainline 6-policy set

The next mainline run must use the versioned strategy set in
`docs/config/paper_mainline_strategies.v1.json`, not an ad hoc
`--strategies` string:

1. `bare_t2_baseline`
2. `bare_t3_baseline`
3. `enterprise_router_baseline`
4. `budgetflow_same_enterprise_router`
5. `budgetflow_task_level`
6. `budgetflow_segment`

`budgetflow_task_level` is the Claim 1 main policy. `budgetflow_segment` is
the Claim 2 segment-aware enhancement.

### Task set direction: 25-30 tasks × 6 strategies

Do not keep iterating on 5×20. The next evidence-producing run should move to
6×25 or 6×30, preferably staged so the first 20 tasks form an audit checkpoint
and the remaining tasks continue under the same run identity after inspection.

The 10 harness-admissible candidates from this gate are ready to join the next
larger pool:

- 3 sympy (22714, 12171, 17655) — known repo, known signal
- 1 django (13447) — known repo, single task
- 2 sphinx (8273, 7686) — known repo, compat issues fixed in round3
- 2 pylint (7993, 6506) — new repo, cold start
- 2 seaborn (3010, 2848) — new repo, cold start

### Budget mode: frozen_plan_cap_sum

Do NOT use `target_utilization`. The 5×20 calibration audit MAPE=53.47% triggers WARNING. Bootstrap zero-history estimates for pylint/seaborn would inflate projections by 2-5×.

Suggested hard cap should come from the generated frozen router plan for the
selected 25-30 tasks. Use `model_tiers.t3x3.json` for the scarcity diagnostic
unless the run is explicitly a real-billing-cost audit.

### Command shape

```bash
PYTHONPATH=src python -m budgetflow.run_mini_swe_compare \
  --ids "<25-30 pre-registered harness-admissible task ids>" \
  --strategy-set docs/config/paper_mainline_strategies.v1.json \
  --budget-mode frozen_plan_cap_sum \
  --frozen-plan docs/reports/mainline_6x25_frozen_router_plan.json \
  --budget-plan docs/reports/mainline_6x25_budget_plan.json \
  --model-catalog docs/config/model_tiers.t3x3.json \
  --value-profile manual_value \
  --value-matrix docs/reports/mainline_6x25_manual_value_matrix.json \
  --run-series mainline_6x25_v1
```

### Pre-flight checklist

- [ ] Generate frozen router plan for the selected 25-30 tasks
- [ ] Generate manual value matrix for the selected 25-30 tasks
- [ ] Verify provider balance covers $3.00 hard cap
- [ ] Run gold harness sanity on the exact task set
- [ ] Check for sibling stems in `data/runs/` before starting
- [ ] If previous run fragmented, use `--repair` to target latest stem

### Test status

```
506 passed, 1 skipped — all clean
py_compile: clean (recost, budget_binding, run_series, checks, checker)
git diff --check: clean
```
