# BudgetFlow Handoff

This is the current handoff for BudgetFlow. The project has two main workstreams now:

1. Architecture refactor needed for safety and future model expansion.
2. Historical-based Automatic Budgeting, with stronger trace observability as a hard prerequisite.

Trace is not optional. Every future model change can break protocol, routing, or provider behavior. The system must show what happened before we trust experiments.

## Current Direction

Mainline work:

- Build trace first, because current failures are not root-cause observable.
- Refactor the unsafe seams that caused current bugs.
- Build Automatic Budgeting from historical priors, not from pilot.
- Run small clean probes only after trace/protocol/tier semantics are fixed.

## Required Deliverables

The work is not complete unless it produces:

- Code changes.
- Tests for the changed behavior.
- A run/report at `paper1/docs/reports/next_agent_report.md`.
- If Automatic Budgeting ETL is touched:
  - `paper1/data/task_cost_history.jsonl`
  - `paper1/docs/reports/historical_budgeting_prior.md`
- A clean run id/stem and exact command.
- A short answer to:
  - Is GPT-5.4 parser-clean?
  - Is `all_pro` really T3?
  - Does `budget_only` start from the cheap available tier?
  - Does each failed row have enough trace evidence to diagnose?

## What To Do Now

Do these in this order:

1. Strengthen trace observability.
2. Add the architecture seams needed to stop current bugs from recurring:
   - `ModelCatalog / TierRegistry`
   - `ActionProtocolAdapter`
   - `RouterDecision`
   - `BudgetAllocator` shell for historical priors
3. Fix GPT-5.4 action protocol.
4. Fix `all_pro` and `budget_only` tier semantics.
5. Run a small clean probe.
6. Build historical data ETL for Automatic Budgeting.

## What Not To Do Now

Do not do these:

- Do not rewrite the compare runner wholesale.
- Do not build a full T10 plugin framework.
- Do not move broad directory trees.
- Do not replace T2 with Qwen3.7-Max in the main tier line.
- Do not run large 15x7/105-row experiments.
- Do not make paper claims from current `policy_5x3-2`.
- Do not implement a complex learned allocator before historical priors exist.
- Do not treat `RunSpec` as a main refactor unless it is needed for reproducibility. CLI sprawl is annoying, but not the current root bug.

## Required Refactor Scope

These are real refactors, not optional notes:

1. `ModelCatalog / TierRegistry`
   - Problem: `defaults.py`, `adapter/strategies.py`, and `run_mini_swe_compare.py` each interpret tiers differently.
   - Current bug: `all_pro` means tier 2 in code but should mean strongest tier.
   - Required shape: one interface answers `cheapest`, `strongest`, `tier=N`, model id, provider, protocol, display name, cost.

2. `ActionProtocolAdapter`
   - Problem: GPT-5.4 appears to return a format the current parser cannot consume.
   - Current bug: T3/GPT-5.4 exits with `format_error_text_action`.
   - Required shape: each tier/model declares protocol mode: tool-call, text regex, or other supported action format. Parser choice must be explicit and traced.

3. `RouterDecision`
   - Problem: routers return only a backend, so failures cannot explain why T2/T3 was selected.
   - Current bug: `budget_only` jumped to T3 and the row does not explain the branch.
   - Required shape: router returns or records `{backend, reason, scores, pressure, branch}`.

4. `BudgetAllocator`
   - Problem: budget logic is scattered across pilot caps, frozen caps, tight/loose rules, pressure, rescue, and stop-loss.
   - Required shape now: historical prior loader and soft-cap recommendation; no complex runtime learner yet.
   - Required shape later: active soft-cap/reallocation policy.

5. `RunSpec`
   - Status: lower priority than the first four.
   - Reason: CLI args are messy, but not the main cause of the current failures.
   - Only do now if it is cheap to save the exact run config into JSONL/trace.

## Current Facts

- Date: 2026-06-02.
- Current active tiers:
  - T1 = `qwen3-coder-flash` (`tier1`, DashScope)
  - T2 = `qwen3-coder-plus` (`tier2`, DashScope)
  - T3 = `GPT-5.4` (`tier3`, AiCode007, `openai/gpt-5.4`)
- GPT-5.3 Codex is no longer exposed by the provider. Any old GPT-5.3 references must be rewritten to GPT-5.4 or archived as historical.
- Latest run: `paper1/data/runs/policy_5x3-2.jsonl`, 15/15 complete, 1/15 PASS.
- Old useful run: `paper1/data/runs/policy_5x7-0.jsonl`, 35 rows, old tier pool. It is useful for task selection, not for current model conclusions.

## Latest 5x3 Result

```text
strategy               | 13480          | 14774          | 16988
----------------------------------------------------------------------
budget_only_tight      | FAIL ext_fail  | FAIL ext_fail  | FAIL ext_fail
budgetflow_full_tight  | FAIL ext_fail  | FAIL ext_fail  | FAIL rep_fail
budget_only_loose      | FAIL ext_fail  | FAIL ext_fail  | FAIL ext_fail
budgetflow_full_loose  | FAIL ext_fail  | FAIL ext_fail  | FAIL rep_fail
all_pro                | PASS           | FAIL rep_fail  | FAIL rep_fail
```

High-confidence findings:

- T3/GPT-5.4 runs fail at `format_error_text_action`; no patch, no gold edit, no submit. This is a response-format/action-parser boundary problem until proven otherwise.
- `all_pro` is currently wrong. `paper1/src/budgetflow/adapter/strategies.py` hardcodes `all_pro` to tier 2. The JSONL confirms `all_pro` used only `tier2`, so it was Qwen Coder Plus, not GPT-5.4.
- `budget_only` currently chooses tier 3 when only [T2,T3] are available. `paper1/src/budgetflow/policies.py` returns the most expensive backend for `n == 2 and budget_pressure < 0.5`. That is not a cheap baseline.
- T2/Qwen Coder Plus can follow the action protocol, but in this run it only solved `sympy__sympy-13480`.

## Task Anchors

From `policy_5x7-0`:

```text
sympy__sympy-14774  7/7  all strategies passed
sympy__sympy-20212  7/7  all strategies passed
sympy__sympy-13480  6/7  all except old all_pro passed
sympy__sympy-13647  6/7  all except old all_pro passed
sympy__sympy-16988  2/7  budget_only_loose and budgetflow_full_tight passed
```

Use `sympy__sympy-14774` as the first gold sanity task because it was historically universal-pass but failed under current T2 in `policy_5x3-2`. Use `sympy__sympy-13480` as easy/control. Use `sympy__sympy-16988` only as hard sentinel after the protocol is clean.

## Hard Priority

Do these in order:

1. Observability gate.
2. GPT-5.4 parser/protocol root cause and fix.
3. Strategy/tier mapping fixes.
4. Clean 2-task rerun.
5. Historical data ETL for Automatic Budgeting.
6. Optional Qwen3.7-Max side probe.

Do not treat pass/fail tables as scientific evidence before steps 1-3 pass.

## P0: Observability Gate

Current observability is enough for smoke-test attribution, not enough for root-cause repair. The next agent must strengthen it before attempting parser fixes.

Existing `--trace-turns` captures routing/cost fields, but not enough parser evidence. Extend the existing trace schema in `paper1/src/budgetflow/adapter/mini_swe_proxy.py`; do not create a separate logging system.

Required per-turn fields:

- `provider`, `model`, `backend`, `backend_tier`
- `text_mode`, `tool_mode`, and the parser selected
- raw assistant content snippet, capped and redacted, e.g. `assistant_content_head`
- raw tool calls summary, e.g. count + function names
- parser input snippet
- parser exception type/message
- provider HTTP status/error code/body snippet/request id when available
- reservation lifecycle: `reservation_id`, `reserved_cost`, `reservation_released`, `reservation_settled`
- router reasoning: expected costs, budget pressure, selector score or budget-only branch reason

Acceptance criteria:

- A GPT-5.4 format failure row contains enough evidence to answer: "what did the model output, which parser consumed it, and exactly why did parsing fail?"
- A provider failure row contains provider/model/status/body snippet without API key leakage.
- A route decision row explains why T2 or T3 was selected.
- `turn_trace_count > 0` for diagnostic reruns.
- `forensic_summary.missing_evidence` no longer includes `turn_traces` when `--trace-turns` is used.

Suggested tests:

- Add/update tests near `paper1/tests/test_format_error_stoploss.py` and `paper1/tests/test_provider_fallback.py`.
- Test that a text-mode parser failure records parser evidence.
- Test that provider fallback/release records reservation lifecycle.
- Test that budget-only with two backends records the exact branch reason.

## P0: GPT-5.4 Protocol Fix

After observability passes, reproduce on one task:

```bash
cd /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1
FORCE_COLOR=1 PYTHONPATH=src:../external/mini-swe-agent/src \
/home/fengde/Projects/AI-learning/agent_learning/AgentOS/.venv/bin/python -u -m budgetflow.run_mini_swe_compare \
  --read-frozen-caps --limit 1 --step-limit 20 \
  --strategies all_t3 \
  --ids sympy__sympy-14774 \
  --trace-turns --trace-max-turns 20 \
  --run-series gpt54_protocol_probe
```

Then inspect the trace:

- If GPT-5.4 returns text commands in a different fenced format, update text parser or prompt.
- If GPT-5.4 returns tool calls while `text_mode=True`, switch T3 to tool mode or normalize tool calls.
- If GPT-5.4 returns prose only, tighten system prompt and format-error retry template.

Protocol non-compliance policy:

- First, declare the expected protocol per model in `ActionProtocolAdapter`.
- Second, prompt the model to use that protocol.
- Third, parse only through the declared parser.
- If parse fails, record raw output, parser input, parser error, model, provider, protocol, and retry prompt in trace.
- If the same model repeatedly violates the declared protocol, do not keep burning task turns. Stop with `protocol_fail` or fall back to another declared protocol only if that fallback is explicitly configured.
- Do not silently guess between tool-call and text parsers without trace evidence.

Current suspected failure:

- The model should produce an action that invokes the bash tool or emits the expected text command block.
- The harness cannot parse GPT-5.4's output into a bash action.
- Therefore no shell command runs, no patch is produced, and the agent exits via `format_error_text_action`.

Acceptance criteria:

- `all_t3` on `sympy__sympy-14774` no longer exits with `format_error_text_action`.
- It either submits or fails as `repair_fail`/`model_behavior`, not `extract_fail` from parser format.
- The trace proves the selected parser matched the model response mode.

## P0: Strategy/Tier Mapping Fixes

Files:

- `paper1/src/budgetflow/adapter/strategies.py`
- `paper1/src/budgetflow/run_mini_swe_compare.py`
- `paper1/src/budgetflow/policies.py`
- tests under `paper1/tests/`

Required decisions:

- `all_pro` must mean strongest current tier. Change it to tier 3, or rename the T2 baseline to `all_t2`. Recommended: make `all_pro -> tier3`, keep explicit `all_tier2`.
- `_required_backends_for_strategies()` must require T3 for `all_pro`, not T2.
- `BudgetOnlyStepRouter` should be a cheap budget baseline. With only [T2,T3], it should choose T2 unless budget pressure is near zero and the experiment explicitly defines "spend-up" behavior. Recommended: make `budget_only` choose cheapest available tier under normal pressure, and add a separate name if we want "budget ceiling".

Acceptance criteria:

- Unit test: `all_pro` selects `tier3`.
- Unit test: `all_tier2` selects `tier2`.
- Unit test: `budget_only` with [T2,T3] and initial pressure selects `tier2`.
- `policy_5x3` rerun no longer shows `all_pro` as only `tier2`.

Refactor requirement here:

- Add one central helper/module for tier lookup if needed.
- Strategy code should ask for `strongest`, `cheapest`, or `tier=N`.
- Do not let strategy code hardcode provider/model ids.

## P1: Clean Rerun

After P0 items pass, run a small clean matrix first:

```bash
cd /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1
FORCE_COLOR=1 PYTHONPATH=src:../external/mini-swe-agent/src \
/home/fengde/Projects/AI-learning/agent_learning/AgentOS/.venv/bin/python -u -m budgetflow.run_mini_swe_compare \
  --read-frozen-caps --limit 2 --step-limit 80 \
  --strategies all_tier2,all_pro,budget_only_tight,budgetflow_full_tight \
  --jobs 4 \
  --ids sympy__sympy-14774,sympy__sympy-13480 \
  --trace-turns --trace-max-turns 80 \
  --run-series clean_gold2
```

Only if this is interpretable, run the 5x3 again:

```bash
cd /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1
FORCE_COLOR=1 PYTHONPATH=src:../external/mini-swe-agent/src \
/home/fengde/Projects/AI-learning/agent_learning/AgentOS/.venv/bin/python -u -m budgetflow.run_mini_swe_compare \
  --read-frozen-caps --limit 3 --step-limit 150 \
  --strategies budget_only_tight,budget_only_loose,budgetflow_full_tight,budgetflow_full_loose,all_pro \
  --jobs 5 \
  --ids sympy__sympy-13480,sympy__sympy-14774,sympy__sympy-16988 \
  --trace-turns --trace-max-turns 150 \
  --run-series policy_5x3_clean
```

Acceptance criteria:

- No `turn_trace_count=0`.
- No unexplained `extract_fail`.
- `all_pro` is T3/GPT-5.4.
- `budget_only` starts from T2 unless the trace explains a deliberate exception.

## P1: Historical Data ETL for Automatic Budgeting

This is the first Automatic Budgeting step. It does not change runtime behavior yet.

Goal:

- Build a clean historical prior from old runs.
- Use history first, not pilot.
- Treat T1/T2/T3 as system tier contracts, not permanent real-model identities.

Good source files:

- `paper1/data/runs/policy_5x7-0.jsonl`
- `paper1/data/runs/budgetflow_goldpass5_qwen5pol_v2.jsonl`
- selected clean rows from `paper1/data/runs/policy_15x7-12.jsonl` and `paper1/data/runs/policy_15x7-13.jsonl`

Filter out rows with:

- provider/infra errors
- unsupported model / `BadRequestError`
- parser/protocol failures
- unknown or inconsistent tier mapping
- missing harness detail when the row is used as success/cost evidence

Output:

- `paper1/data/task_cost_history.jsonl`
- `paper1/docs/reports/historical_budgeting_prior.md`

Each history row should include:

- `instance_id`
- `run_id`
- `strategy`
- normalized tier mix
- resolved/pass boolean
- total cost
- turns
- failure class / exit reason
- whether patch was extracted
- whether gold file was edited
- confidence: `clean`, `usable_task_prior`, or `exclude`
- exclusion reason if excluded

First allocator design, not runtime implementation:

- Known task: lookup historical difficulty prior.
- Unknown task: fallback to simple feature bucket.
- Soft cap comes from historical min/median successful cost.
- Add budget only if there is evidence: gold edit, patch, failing-test improvement.
- Stop-loss on no progress.

Do not wire this into live routing yet. Just prepare the data and report what it would recommend for `13480`, `14774`, `16988`, and `20212`.

## P1: Qwen3.7-Max Decision

Do not put Qwen3.7-Max into the main line yet. It is a model-selection probe, not a blocker for fixing the system.

Recommended decision:

- Keep main tiers as T1/T2/T3 above while fixing observability/protocol/routing.
- Add Qwen3.7-Max as an opt-in candidate, e.g. `qwen37_max_probe` or temporary `all_qwen37_max`, after DashScope access is verified.
- Compare on only `sympy__sympy-14774` and `sympy__sympy-13480` first.

Why:

- Current failures include parser and strategy bugs. Swapping T2 now can hide those bugs.
- User remembers Qwen3.7-Max being strong; that is plausible and worth testing.
- The paper needs cost-resolved evidence under the same scaffold, not model folklore.

Acceptance criteria:

- Same tasks, same scaffold, same trace fields.
- Report pass/fail, turns, cost, failure class, and whether it needed fewer rescue/escalation turns than `qwen3-coder-plus`.
- Promote Qwen3.7-Max only if it improves resolved-per-cost or acts as a better T3/T4 ceiling in a controlled probe.

## P2: Failure Taxonomy

`ServiceUnavailableError` and provider unavailable cases should map to infra/provider, not protocol. Keep `protocol` for parser/action/submission format failures.

Acceptance criteria:

- Provider 404/503: `failure_class=infra_fail`, `primary_axis=infra` or `provider`.
- Parser format failure with successful provider response: `failure_class=extract_fail`, `primary_axis=protocol`.
- Repair patch fails tests: `failure_class=repair_fail`, `primary_axis=repair_quality`.

## P2: Automatic Budgeting

Delay runtime Automatic Budgeting until the clean rerun is interpretable and historical ETL exists.

When it is time, implement a small version:

- task difficulty prior from known anchor tasks
- soft per-task cap with global hard cap
- continue budget only when there is evidence: gold edit, patch, failing-test improvement
- stop-loss on no progress
- every budget adjustment must be written to JSONL

Do not build a complex learner until at least 10 clean task records exist.

## Suggested Skills

- `superpowers:systematic-debugging` for root-cause work.
- `superpowers:test-driven-development` for parser/router/trace fixes.
- `superpowers:verification-before-completion` before claiming any run is clean.

## What Not To Do

- Do not scale to larger experiments before P0/P1.
- Do not interpret old GPT-5.3 rows as current GPT-5.4 evidence.
- Do not silently change model tiers without recording model id/provider/base URL in traces.
- Do not delete old run artifacts; they are still task-selection evidence.
- Do not let `all_pro` mean different tiers across runs without explicit record fields.
