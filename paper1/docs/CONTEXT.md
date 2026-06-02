# BudgetFlow Context

Shared vocabulary for agents and researchers working on this project.

## Domain Terms

### tier contract
A tier is a stable system identity (T1/T2/T3), not a specific model. T1 = cheapest, T3 = strongest. Each tier has a fixed cost per token, provider, and action protocol. Models behind tiers can change, but the contract stays the same. This means `all_pro` should always mean strongest tier, regardless of what model sits at T3.

### action protocol
How a model emits SWE agent actions. Two modes:
- **tool_call**: model returns native function-call blocks. Parser: `parse_toolcall_actions`.
- **text_regex**: model returns fenced bash blocks (```` ```mswea_bash_command ``` ````). Parser: `parse_regex_actions`.

Protocol is declared per-tier in `TierConfig.text_mode`. `ActionProtocolAdapter` resolves the protocol and records the decision in trace. Never guess between parsers silently.

### router decision
A structured record of why a tier was selected for a turn. Fields: `{backend, reason, scores, pressure, branch}`. Replaces bare `Backend` return. Recorded in `RoutingContext.last_decision` and persisted in turn trace as `router_reason`, `router_scores`, `router_branch`.

### budget prior
Historical cost/resolve data for a task instance, extracted from old JSONL runs via `historical_etl.py`. Stored in `data/task_cost_history.jsonl`. Used to estimate soft cap before running a task. Two confidence levels: `clean` (resolved, no errors) and `usable_task_prior` (patch existed, harness failed).

### soft cap
Per-task spending recommendation derived from historical median successful cost. Not a hard cut. The BudgetAllocator uses soft cap to decide when to escalate or stop. Hard cap is the Governor's total_budget; soft cap is the allocator's signal.

### rescue
Evidence-based forced upgrade to a stronger tier when the agent finds and edits a gold file but repair stalls. Controlled by `EvidenceRescueState`: opens a bounded window after gold edit, forces tier upgrade within the window, and triggers stop-loss if rescue doesn't produce a passing patch.

### headroom
Remaining budget minus reserved cost. `spend_headroom = max(0, total_budget - spent_budget)`. Billable cost is clamped to headroom (`billable = min(actual_cost, spend_headroom)`). Governs whether rescue should engage and whether to downgrade.

### clean row
A JSONL record that passes ETL filtering: no infra errors, no parser failures, known tier mapping, enough turns to be meaningful. Rows marked `confidence=clean` or `confidence=usable_task_prior` in `task_cost_history.jsonl`.

### protocol fail
Exit caused by parser/format mismatch, not model capability. `exit_reason` starts with `format_error_`. Distinguished from `infra_fail` (provider 404/503) and `repair_fail` (patch exists but tests fail). P0 trace must capture raw output, parser input, and parser error for every protocol fail.

### equal-weight ablation
A BudgetFlow variant where all workflow stages (LOC/REP/VAL) get `w_i=1.0` instead of the default repair-heavy profile (1.0/3.0/2.5). Strategy name: `budgetflow_equal_weight`. Legacy name `budgetflow_auto_v2` aliases to this. Used to test whether repair-weighting matters.

### Automatic Budgeting
Task budget estimation from historical priors, not per-task-set pilot runs. Two phases:
- **Plan B (cold start)**: difficulty bucket from task features + pilot calibration.
- **Plan C (continuous)**: kNN over `task_cost_history.jsonl` once ≥10 records exist.

Current state: historical ETL exists, soft-cap recommendations exist, runtime wiring waits for clean traces.
