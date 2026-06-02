# Gold-pass 5-task Qwen Policy Probe v2

Run:

```text
stem: data/runs/budgetflow_goldpass5_qwen5pol_v2
tasks: sympy__sympy-13480, sympy__sympy-13647, sympy__sympy-16988, sympy__sympy-20212, sympy__sympy-17139
policies: budget_only_tight, stage_blind_tight, budgetflow_full_tight, all_pro, all_t4
budget: per-task cap 3000 governor units
jobs: 1
docker: no
gpt-5.5: no
```

All five tasks come from `data/gold_pass_easy5_instance_ids.json`; requests tasks remain excluded because prior probes showed HTTP/DNS instability.

## Result Table

| strategy | resolved | cost | avg cost/pass | avg turns | failure notes |
|---|---:|---:|---:|---:|---|
| `budget_only_tight` | 3/5 | 3944.3 | 1314.8 | 38.8 | 16988:repair_fail, 20212:repair_fail |
| `stage_blind_tight` | 4/5 | 3296.6 | 824.2 | 41.4 | 16988:repair_fail |
| `budgetflow_full_tight` | 4/5 | 2712.6 | 678.2 | 31.2 | 16988:repair_fail |
| `all_pro` | 5/5 | 6079.8 | 1216.0 | 38.6 | - |
| `all_t4` | 3/5 | 7332.7 | 2444.2 | 32.4 | 16988:budget_exhausted + fail_after, 17139:repair_fail |

Per task format: `PASS|FAIL / cost / turns`.

| task | budget_only | stage_blind | budgetflow | all_pro | all_t4 |
|---|---|---|---|---|---|
| `sympy__sympy-13480` | PASS/243/18 | PASS/277/16 | PASS/237/17 | PASS/142/14 | PASS/265/19 |
| `sympy__sympy-13647` | PASS/573/23 | PASS/284/24 | PASS/493/22 | PASS/536/24 | PASS/993/30 |
| `sympy__sympy-16988` | FAIL/1575/101 | FAIL/1122/75 | FAIL/759/52 | PASS/3000/64 | FAIL/2998/48 |
| `sympy__sympy-20212` | FAIL/920/30 | PASS/1302/62 | PASS/554/31 | PASS/1677/52 | PASS/2444/42 |
| `sympy__sympy-17139` | PASS/632/22 | PASS/313/30 | PASS/669/34 | PASS/725/39 | FAIL/633/23 |

## Interpretation

BudgetFlow full is not yet the ceiling policy, but it is already the best cost-efficiency policy in this run:

- It solves 4/5, same as `stage_blind_tight`.
- It spends 2712.6, less than `stage_blind_tight` at 3296.6.
- It beats `budget_only_tight` on both resolved count and cost efficiency.
- It is far cheaper than `all_pro`, but misses `sympy__sympy-16988`.

`all_pro` is the current Qwen ceiling on this set: 5/5, but high cost. `all_t4` is not a better ceiling: it costs more than `all_pro` and solves only 3/5. This supports keeping `qwen3-coder-plus` as an important SWE tier, but not using it blindly for every turn.

## Main Failure Pattern

The repeated failure mode is not localization alone. Several policies reach the relevant file, then spend many repair turns on weak or poorly chosen tiers:

- `sympy__sympy-16988`: BudgetFlow full reaches `sympy/sets/sets.py`, then fails repair.
- `sympy__sympy-20212`: BudgetFlow full solves it cheaply, while `all_pro` and `all_t4` spend much more.
- `all_t4` on `sympy__sympy-16988` reaches the file early but still fails after spending almost the full cap.

Conclusion: expensive model use must be evidence-based. Stronger is not monotonic. The right trigger is not "always use T4/GPT"; it is "use stronger repair when the task has evidence of being close, and stop when extra spend is not improving evaluator-facing state."

## Code Change Triggered By This Run

This run motivated an evidence-based repair floor:

> In `budgetflow_full`, once the route is repair/validation or the agent enters edit/test phases, do not let routing/reserve fallback drop below T3.

This is a conservative first step. It does not add GPT-5.3 or GPT-5.5. It only prevents BudgetFlow from wasting near-solved repair turns on T1/T2 after evidence has appeared.

## Next Experiment

Run the same 5-task probe after the repair-floor change, using a new stem:

```bash
cd /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1 && \
FORCE_COLOR=1 HF_HOME=$PWD/data/hf_cache PYTHONPATH=src:../external/mini-swe-agent/src \
../.venv/bin/python -u -m budgetflow.run_mini_swe_compare \
  --ids sympy__sympy-13480,sympy__sympy-13647,sympy__sympy-16988,sympy__sympy-20212,sympy__sympy-17139 \
  --strategies budgetflow_full_tight,stage_blind_tight,all_pro \
  --out-stem budgetflow_goldpass5_repairfloor_v1 \
  --step-limit 120 \
  --heartbeat 45 \
  --jobs 1 \
  --trace-quiet \
  --per-task-cap 3000 \
  2>&1 | tee data/runs/budgetflow_goldpass5_repairfloor_v1.run.log
```

Keep GPT-5.5 out of this run. GPT-5.3 Codex should be tested separately as a rescue tier only after its model name/API path is verified.

