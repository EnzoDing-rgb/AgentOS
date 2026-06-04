# BudgetFlow AutoResearch Read-Only Smoke

Verify that AutoResearch can run against BudgetFlow as a read-only test case.

## Scope

This issue tests the AutoResearch loop itself. It does not advance the paper and does not change BudgetFlow code.

## Acceptance Criteria

- [ ] Read `docs/autoresearch_workflow.md`.
- [ ] Read `docs/north_star.md`.
- [ ] Read `docs/takeaway.md`.
- [ ] Confirm the configured hard constraints: owner approval for 3x10 or larger paid experiments, policy-level parallelism with policy-internal sequencing, and accepted-stage checkpointing.
- [ ] Run a read-only command that confirms the repository is accessible.
- [ ] Do not modify `src/`, `tests/`, or `data/runs/`.
- [ ] Do not start any paid API experiment.
- [ ] Produce a concise worker report in the AutoResearch workflow log.
