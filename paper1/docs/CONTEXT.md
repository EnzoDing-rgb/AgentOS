# BudgetFlow Context

Shared vocabulary for agents and researchers working on this project.

## Domain Terms

### Tier 1 claim
The paper's North Star claim: under a hard shared budget pool, the system should maximize verified resolved value per dollar. This is a governance/allocation claim, not merely a per-task cost claim. A run only supports this claim when task values are non-equal and the JSONL rows show a real `value_source=value_matrix` (or another explicit non-equal source), not fallback equal values.

### Tier 2 claim
The mechanism claim: the routing heuristic should reduce waste from strong models and improve cost efficiency or pass/cost tradeoffs against static, dummy, or simpler routing baselines. Tier 2 can be supported by equal-value routing evidence, but it does not by itself prove Tier 1.

### task value proxy
Task value is an observable proxy, not ground truth. Current preferred cold-start proxy is model success rarity / solve rarity: tasks solved by fewer capable policies or models receive higher value. Do not describe the current primary proxy as human-effort value. Long term, the system should learn value, difficulty, model success probability, progress signal quality, and cost online from verified outcomes.

### AutoResearch / Auto-reset coordinator
AutoResearch is implemented as a semi-automatic coordinator, but it is currently an infrastructure tool, not the driver of the BudgetFlow paper. It may run bounded Worker issues, collect reports, retry small failures, and preserve on-disk evidence. It must not autonomously change Tier 1/Tier 2 claims, launch large paid experiments, or iterate paper direction without Codex/owner approval.

### current research discipline
Treat JSONL, checker output, summary logs, and turn traces as facts. Treat Worker reports as ledgers that must be checked against artifacts. A small paid run can support Tier 2 routing behavior, but Tier 1 requires non-equal task values loaded from an explicit value source. If a non-equal value profile falls back to equal values, the run is invalid for Tier 1.

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

## Current Decisions

- Main development branch is `main`; `feature/issue-1` has been merged.
- AutoResearch / Auto-reset coordinator exists and is useful for infra loops, but it is paused as a paper-iteration engine. Codex remains the reviewer/front-end for owner decisions.
- Tier 1 is the paper compass: maximize verified resolved value per dollar under a shared hard budget.
- Tier 2 is a mechanism claim: route stages/models more efficiently than simpler baselines.
- Current P0 for experiments: non-equal value profiles must fail fast when the value matrix/profile/task lookup misses. Silent fallback to equal values corrupts Tier 1 evidence.
