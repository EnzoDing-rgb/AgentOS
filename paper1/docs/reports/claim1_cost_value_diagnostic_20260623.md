# Claim 1 Cost And Value Diagnostic

Date: 2026-06-23

## Scope

This note answers three draft-critical questions after the patch-cleaner false-negative fix:

1. Why is BudgetFlow cost higher than pure T3 if some BudgetFlow tasks also use T3?
2. Is the current 3 x 30 run complete?
3. Does the Claim 1 signal depend on the narrow current Task Value profile?

## Evidence Source

Primary completed run: `paper1/data/runs/mainline_3x30_lhm_cycle_routefix_kv50_20260623.jsonl`.

This is a complete 3-policy x 30-task run: pure T2, pure T3, and BudgetFlow task-level, 90 scoreable rows total.

Historical JSONL is immutable. Metrics below apply the forensic corrections from the patch-cleaner false-negative audit:

- `django__django-11049`: pure T2, pure T3, and BudgetFlow become pass.
- `sphinx-doc__sphinx-8801`: BudgetFlow becomes pass.

## Corrected Headline

| Strategy | Passes | Yield | Cost | Yield/$ | Turns |
|---|---:|---:|---:|---:|---:|
| pure T2 | 18 | 19.5 | 9.7729 | 1.9953 | 969 |
| pure T3 | 16 | 17.5 | 5.1336 | 3.4089 | 226 |
| BudgetFlow task-level | 20 | 22.0 | 7.1727 | 3.0672 | 615 |

For the initial draft, the Claim 1 headline is Yield: BudgetFlow resolves the most normalized verified value under the same completed task set. Yield/$ is a required efficiency diagnostic; pure T3 remains the strongest efficiency boundary.

## Why BudgetFlow Costs More Than Pure T3

BudgetFlow is not slower when it actually runs all-T3. Split by BudgetFlow's actual route:

| BudgetFlow route | Tasks | BF turns | pure T3 turns on same tasks | BF cost | pure T3 cost | BF Yield | pure T3 Yield |
|---|---:|---:|---:|---:|---:|---:|---:|
| BF all-T3 | 13 | 102 | 103 | 2.6358 | 2.4952 | 10.0 | 9.0 |
| BF all-T2 | 17 | 512 | 123 | 4.5369 | 2.6384 | 12.0 | 8.5 |

So the extra BudgetFlow turns come from T2-routed tasks, not from a systemic T3 runtime slowdown. T2 has lower per-turn price, but on this task mix it often needs many more turns. That is a real result: BudgetFlow wins Yield by letting T2 solve more tasks, but it does not beat pure T3 on Yield/$ because T3 is much more turn-efficient.

## T2 vs T3 Cost Frontier

Corrected pure-tier frontier:

| Bucket | Tasks | T2 total cost | T3 total cost | Avg T2 turns | Avg T3 turns |
|---|---:|---:|---:|---:|---:|
| both pass | 15 | 4.8030 | 2.2409 | 31.4 | 7.0 |
| T2 only | 3 | 0.9724 | 0.7444 | 35.7 | 9.0 |
| T3 only | 1 | 0.3246 | 0.1771 | 39.0 | 8.0 |
| both fail | 11 | 3.6730 | 1.9712 | 32.0 | 7.8 |

Despite higher per-turn price, pure T3 is cheaper in aggregate because it uses far fewer turns. This is a cost-frontier limitation of the current catalog/task mix, not a patch-cleaner bug.

## Value Signal Width

Current ValueSource is narrow:

- `normal=1.0`: 24 tasks
- `high=1.5`: 6 tasks
- `critical=2.5`: 0 tasks

This is a threat to validity. However, the direction of the Claim 1 Yield signal does not depend on the current narrow profile:

| Value profile | pure T2 Yield | pure T3 Yield | BudgetFlow Yield |
|---|---:|---:|---:|
| equal values | 18.0 | 16.0 | 20.0 |
| current values | 19.5 | 17.5 | 22.0 |
| top 20% Task Effort as critical | 21.0 | 19.0 | 23.0 |
| top 33% Task Effort as critical | 24.0 | 20.5 | 27.5 |
| effort tertiles as 1.0 / 1.5 / 2.5 | 27.5 | 24.0 | 31.5 |
| both-fail tasks critical, else current | 19.5 | 17.5 | 23.5 |
| top 10 Task Effort critical, else current | 24.5 | 21.5 | 28.5 |

Interpretation: the current Claim 1 signal is not caused only by the 1.0/1.5 value spread. A broader pre-registered criticality profile would likely strengthen BudgetFlow's Yield advantage on this run, but should be presented as sensitivity unless rerun as a new pre-registered ValueSource.

## Routing Diagnostic

Capability buckets after correction:

| Bucket | Tasks | Avg Task Effort | Avg current value |
|---|---:|---:|---:|
| both pass | 15 | 25.22 | 1.07 |
| T2 only | 3 | 21.61 | 1.17 |
| T3 only | 1 | 23.17 | 1.50 |
| both fail | 11 | 36.59 | 1.09 |

BudgetFlow route by bucket:

| Bucket | BF routed T2 | BF routed T3 |
|---|---:|---:|
| both pass | 8 | 7 |
| T2 only | 2 | 1 |
| T3 only | 0 | 1 |
| both fail | 7 | 4 |

If "should start T3" is defined as the rare T3-only task, BudgetFlow has full recall but low precision: `tp=1`, `fp=12`, `fn=0`, precision `0.077`, recall `1.0`, F1 `0.143`. That metric is intentionally harsh because this task set has only one T3-only task. More useful diagnostics are:

| T3-positive definition | Precision | Recall | F1 |
|---|---:|---:|---:|
| T3-only | 0.077 | 1.000 | 0.143 |
| T3-solved high-value tasks | 0.154 | 0.667 | 0.250 |
| high Task Effort >= 40 | 0.231 | 0.429 | 0.300 |
| high Task Effort and T2 fails | 0.154 | 0.400 | 0.222 |
| both-fail tasks as probe/stop targets | 0.308 | 0.364 | 0.333 |

The next routing issue is therefore not simple T3 recall. It is precision and stop discipline: avoid spending long T2 runs on ceiling tasks, preserve T2 wins where T2 is enough, and use T3 probes only when value/effort/fit justify the attempt.

## Next Paid-Run Hypothesis

Do not change CostSource. The current result already shows T3 is often cheaper in total because it uses far fewer turns, even though its per-turn price is higher. Moving cost would make the evidence less defensible.

The next paid-run candidate should change two pre-registered inputs/mechanisms instead:

1. ValueSource sensitivity: use a wider but auditable criticality gradient, such as `normal=1.0`, `high=1.5`, and `critical=2.5`, with criticality assigned before execution from Task Effort, historical ceiling risk, or explicit task metadata. This is a sensitivity profile, not post-hoc outcome fitting.
2. Runtime stop-loss precision: for high-effort tasks that show no patch/progress evidence after a bounded window, stop earlier or require a stronger-tier probe rather than allowing long T2 spins. The goal is higher Yield under the same shared budget, not cosmetic tier diversity.

## Draft Position

- Claim 1 can be stated from this run: BudgetFlow maximizes corrected Yield among the three policies on the completed 30-task SWE-bench Mini testbed.
- Do not claim Claim 2 yet.
- Do not claim BudgetFlow beats pure T3 on Yield/$.
- State the main limitation honestly: T3 is currently turn-efficient enough to be the best efficiency boundary, while BudgetFlow is the best value-maximizing policy.
