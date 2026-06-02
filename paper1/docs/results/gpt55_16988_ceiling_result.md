# GPT-5.5 16988 Ceiling Result

Date: 2026-06-02

## Purpose

Probe whether GPT-5.5 can rescue the hard repair case `sympy__sympy-16988`, where GPT-5.3 Codex text mode found the gold file and produced an applicable patch but failed `fail_after`.

This was an explicit ceiling probe, not normal BudgetFlow routing.

## Command

```bash
cd /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1
scripts/run-gpt55-textmode-16988-ceiling.sh gpt55_textmode_16988_ceiling
```

## Result

```text
all_gpt55: 0/1 PASS
cost: 982.2 governor units
turns: 5
failure_class: extract_fail
exit_reason: format_error_text_action
```

| task | verdict | turns | cost | failure |
| --- | --- | ---: | ---: | --- |
| sympy__sympy-16988 | FAIL | 5 | 982.2 | no patch extracted; repeated format errors |

Output:

```text
data/runs/gpt55_textmode_16988_ceiling.jsonl
data/runs/gpt55_textmode_16988_ceiling.summary.log
data/runs/gpt55_textmode_16988_ceiling.driver.log
```

## Interpretation

This is not a clean "GPT-5.5 cannot solve 16988" result.

It is a protocol/cost result:

- GPT-5.5 was correctly routed only by explicit `all_gpt55`.
- It spent `982.2` governor units in 5 turns.
- All turns stayed in localization/explore.
- It did not find the gold file.
- It extracted no patch.
- The run stopped on `format_error_text_action`.

Paper implication:

- GPT-5.5 must remain ceiling-only.
- Automatic Budget must not call GPT-5.5 without a compatibility/protocol gate.
- If T5 is ever allowed, it needs a much stricter stop-loss: one or two invalid format turns should stop the task before spending near a full per-task cap.

Follow-up implemented:

- Tier-5 format/protocol stop-loss is now stricter than normal tiers.
- T5 stops after 2 consecutive format errors.
- T4 and below keep the existing threshold of 5 consecutive format errors.
