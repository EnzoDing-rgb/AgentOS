# GPT-5.3 Codex Probe Results

Date: 2026-06-02

## Run

```bash
BF_T4_PROVIDER=gpt53_codex python -m budgetflow.run_mini_swe_compare \
  --ids sympy__sympy-13480 \
  --strategies all_gpt53 \
  --out-stem gpt53_codex_sympy13480_probe \
  --step-limit 80 \
  --per-task-cap 3000 \
  --resume
```

## Result

`all_gpt53` failed `0/1`.

Key fields:

```text
task=sympy__sympy-13480
model=tier4_gpt53_codex
turns=45
cost=1224.276 governor units
patch_extracted=false
failure_class=extract_fail
exit_reason=stagnation_repeat_command
```

## Interpretation

This is not valid evidence that GPT-5.3 Codex cannot solve the task.

The run exposed scaffold/protocol contamination:

1. The agent used `python`, but the local task environment only exposed `python3`.
2. The agent later attempted to submit with one combined command:

```bash
sed ... && git diff ... > patch.txt && cat patch.txt && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt
```

mini-SWE local submission requires the marker to be the first output line, and the config already asks for patch creation and final submission as separate commands. This combined command printed source text before the marker, so it could not submit.

3. No real task file change remained in the worktree, so no patch was extracted.
4. The trace previously marked `submitted=true` when the command text contained the marker. That was wrong; command text only means attempted submission. Real submission must come from mini-SWE's `Submitted` event or submitted exit status.

## Fixes Added

- Trace now records marker-in-command as `attempted_submit=true`, not `submitted=true`.
- `submitted=true` is set only when the runner receives real submitted exit state.
- Local mini-SWE runs now add a `python` shim pointing to the active interpreter, so old repos and model commands using `python` do not fail only because the binary name is absent.
- Consecutive missing/invalid tool-call responses now stop early as `format_error_no_tool_calls` or `format_error_invalid_tool_call` instead of wasting dozens of turns.

## Next Use

After this fix, a tiny GPT-5.3 Codex probe can be rerun on one gold-pass task. If it still fails, inspect whether the failure is:

- `submitted=false`, `attempted_submit=false`: model/scaffold did not reach submit.
- `attempted_submit=true`, `submitted=false`: submit protocol problem.
- `submitted=true`, `patch_extracted=true`, harness fail: real repair quality problem.

GPT-5.5 remains ceiling-only. GPT-5.3 Codex is the only GPT candidate allowed as regular T4 in small controlled probes.

## Protocol Smoke

After the fixes, a short protocol smoke was run:

```bash
BF_T4_PROVIDER=gpt53_codex python -m budgetflow.run_mini_swe_compare \
  --ids sympy__sympy-13480 \
  --strategies all_gpt53 \
  --out-stem gpt53_codex_protocol_smoke \
  --step-limit 8 \
  --per-task-cap 800 \
  --resume
```

Result:

```text
turns=5
cost=62.754 governor units
exit_reason=format_error_no_tool_calls
patch_extracted=false
agent_attempted_submit=false
agent_submitted=false
```

This confirms the guard works: the same protocol mismatch now stops after 5 turns instead of wasting 45 turns. It also confirms the trace no longer reports a false submission.
