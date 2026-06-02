# Result1 Report — 2026-06-02

## Files Changed

| File | Change |
|------|--------|
| `paper1/src/budgetflow/adapter/mini_swe_proxy.py` | Broaden text regex from `mswea_bash_command` only to `(?:mswea_bash_command\|bash\|sh)`. Add `_try_extract_json_command` fallback for `{"command": "..."}` JSON format. Add `_TEXT_ACTION_REGEX` constant. |
| `paper1/tests/test_gpt54_text_parser.py` | NEW: 19 tests covering regex patterns, JSON extraction, protocol safety, trace evidence |

## Test Results

```
48 passed — test_p0_refactor (17) + test_trace_fields (12) + test_gpt54_text_parser (19)
```

New test coverage:
- `test_regex_matches_mswea_bash_command` — legacy format still works
- `test_regex_matches_bash_fenced_block` — GPT-5.4 actual output (```bash)
- `test_regex_matches_sh_fenced_block` — ```sh variant
- `test_regex_real_gpt54_output` — real clean_gold2-0 trace content
- `test_regex_rejects_prose_only` — no false match on prose
- `test_regex_only_one_match_per_block` — single match enforcement
- `test_regex_handles_windows_newlines` — \r\n handling
- `test_json_extract_simple` — basic JSON extraction
- `test_json_extract_with_escaped_newlines` — escaped chars in JSON
- `test_json_extract_with_bash_prefix` — [bash] prefix variant
- `test_json_extract_real_gpt54_output` — real clean_gold2-0 JSON output
- `test_json_extract_returns_none_for_prose_only` — no false JSON match
- `test_json_extract_skips_invalid_json` — broken JSON → None
- `test_parse_regex_actions_still_works_with_new_regex` — integration with mini-swe-agent
- `test_tool_call_protocol_unchanged_for_t1` — T1 tool_call safe
- `test_tool_call_protocol_unchanged_for_t2` — T2 tool_call safe
- `test_t3_stays_text_regex` — T3 protocol unchanged (regex broadened, not protocol switched)
- `test_parser_failure_trace_has_required_fields` — trace evidence on failure

## Result1 Probe

**Command:**
```bash
cd paper1 && PYTHONPATH=src:../external/mini-swe-agent/src \
  ../.venv/bin/python -u -m budgetflow.run_mini_swe_compare \
    --read-frozen-caps --limit 1 --step-limit 20 \
    --strategies all_pro \
    --ids sympy__sympy-14774 \
    --trace-turns --trace-max-turns 20 \
    --run-series result1
```

**JSONL:** `paper1/data/runs/result1-0.jsonl`

## Answers

### Is all_pro still T3/GPT-5.4?

Yes. `all_pro` uses `ModelCatalog.strongest()` → T3 → GPT-5.4 (AiCode007, `openai/gpt-5.4`). Trace confirms `protocol=text_regex`, `parser=parse_regex_actions` on all 7 turns.

### Did GPT-5.4 bash commands execute?

**Yes.** Turn 1 had a FormatError (prose-only response), but turns 2-7 parsed successfully via regular ```bash blocks. The agent:
1. Grepped the latex printer source (LOC)
2. Edited `sympy/printing/latex.py` (gold file)
3. Submitted a patch via `submit`

No `format_error_text_action` stagnation. Exit status: `Submitted`.

### Why did it fail?

`repair_fail` — `pass_to_pass=FAIL`. The model's patch fixes the target test (`fail_after=OK`) but introduces a regression in a previously passing test. This is a repair quality issue, not a protocol/parser bug.

Full harness verdict:
```
test_patch=OK fail_before=OK model_patch=OK fail_after=OK pass_to_pass=FAIL
```

Forensic summary:
- `primary_axis=repair_quality`
- `failure_chain`: FormatError → patch_extracted → gold_file_edited → agent_submitted → harness_pass_to_pass_fail

### What should the main agent analyze next?

1. Check if pass_to_pass failure is a real regression or a flaky test (re-run harness on same patch)
2. If real regression: model needs better validation before submission
3. BudgetFlow policy question: T3 at 117 cost units failed repair_quality on an easy task — does this affect the tier strategy?

## Diff Summary

`_TEXT_ACTION_REGEX` changed from:
```
```mswea_bash_command\s*\n(.*?)\n```
```
to:
```
```(?:mswea_bash_command|bash|sh)\s*\n(.*?)\n```
```

`_parse_actions` text_mode branch now has JSON fallback after FormatError:
1. Try regex (mswea_bash_command, bash, sh)
2. If fail: try `_try_extract_json_command` → `{"command": "..."}` or `[bash] {"command": "..."}`
3. If both fail: raise FormatError (existing behavior, with trace evidence)
