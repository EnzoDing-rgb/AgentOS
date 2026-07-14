# Tool-Call 2x2 Canary

Date: 2026-06-16

## Command Shape

Run series: `toolcall_2x2_canary_20260616b`

- Tasks: `sympy__sympy-22714`, `sympy__sympy-12171`
- Strategies: `bare_t3_baseline`, `budgetflow_segment`
- Catalog: `docs/config/model_tiers.t3x3.json`
- Budget: `$0.25` shared batch cap per policy
- Runtime/worktrees: `/tmp/budgetflow-runtime`

Artifact:

- `data/runs/toolcall_2x2_canary_20260616b-0.jsonl`
- `data/runs/toolcall_2x2_canary_20260616b-0.checkpoint.json`

## Result

| Strategy | Pass | True Fail | Abort | Cost | Notes |
|---|---:|---:|---:|---:|---|
| `bare_t3_baseline` | 1 | 1 | 0 | `$0.1365` | T3 native tool-call path works; one pass and one evaluated validation failure |
| `budgetflow_segment` | 0 | 0 | 2 | `$0.0041` | T2 returned text fenced commands, not native tool calls |

## Protocol Finding

The canary did not reproduce the old `text_regex` runtime path. All turn traces report `protocol=tool_call`.

However, both `budgetflow_segment` rows aborted with:

- `exit_reason=format_error_no_tool_calls`
- `abort_owner=protocol`
- `failure_stage=extraction`
- `protocol_retry_used=True`
- `protocol_retry_success=False`

The trace evidence shows T2/qwen returned content like:

```text
THOUGHT: ...
```mswea_bash_command
ls -la
```
```

but returned no `message.tool_calls`. So the current issue is not regex parsing; it is that the T2 provider/model path does not actually produce native tool calls even when called with `tools=[BASH_TOOL]`.

T3/GPT-5.4 did produce usable tool calls:

- `sympy__sympy-22714`: `PASS`, 5 turns, no protocol retry.
- `sympy__sympy-12171`: `true_fail`, 15 turns, protocol retry eventually succeeded, harness evidence trusted.

## Budget Finding

This 2x2 canary is not a valid 90% scarcity-regime test. It only verifies budget accounting fields:

- Both strategies used `budget_mode=shared_batch_hard_budget`.
- Both had `batch_budget_cap=0.25`.
- Checkpoint preserved separate policy-local `batch_spent`.

Observed utilization:

- `bare_t3_baseline`: `0.1365 / 0.25 = 54.6%`
- `budgetflow_segment`: `0.0041 / 0.25 = 1.6%`

The BudgetFlow utilization is meaningless for scarcity because it died at protocol extraction.

## Stop Decision

Do not run `6x5` yet. The next larger run would mostly test T2 tool-call incompatibility, not BudgetFlow.

Next engineering decision:

1. Either remove T2/qwen from active BudgetFlow routes until it can emit native tool calls;
2. or implement a clean provider/model protocol adapter that converts non-native text action outputs into the same internal action IR without reintroducing brittle, model-specific regex behavior.

The current single native `tool_call` path is clean, but the 2x2 evidence shows it is not supported by every configured tier.
