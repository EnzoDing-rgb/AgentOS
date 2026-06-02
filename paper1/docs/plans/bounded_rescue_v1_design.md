# Bounded Rescue v1

This is the replacement for the failed static repair-floor rule.

## Rule

BudgetFlow opens one short T4 rescue window only when all conditions hold:

- The task has concrete repair evidence: `edit_gold`, `patch_prep`, or `test`.
- The evidence has persisted for several turns.
- The current selected tier is below T4.
- The task still has budget headroom.
- The rescue window has not already been used for this task.

Default v1 values:

```text
trigger_turns = 6
window_turns = 3
min_headroom_frac = 0.18
rescue_tier = T4
```

## Why This Is Not Repair-Floor v1

Repair-floor v1 made repair/validation expensive forever. It preserved the same
pass count and more than doubled cost on the gold-pass-5 probe.

Bounded rescue v1 is narrower:

- No gold/edit/test evidence means no rescue.
- Low budget headroom means no rescue.
- The rescue window is one-shot.
- After the window, normal routing and stop-loss continue.

## Paper Framing

This is the automatic-budget claim in miniature:

```text
cheap first
if there is evidence the task is worth saving, spend a bounded rescue budget
if the rescue fails, stop wasting expensive calls
```

GPT-5.5 remains ceiling-only. GPT-5.3 Codex can be tested later as a bounded
rescue tier after its API/model path is verified.
