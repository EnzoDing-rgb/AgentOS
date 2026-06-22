# Agent Shell Venv Contamination Fix

## Objective

Stop paid runs from contaminating global Python with editable installs from
runtime worktrees.

## Change

- Added a per-worktree agent-shell venv under
  `/tmp/budgetflow-runtime/agent_shell_venvs/...`.
- `build_agent_shell_env()` now puts that venv first on `PATH`, sets
  `VIRTUAL_ENV`, `PYTHONNOUSERSITE=1`, and `PIP_REQUIRE_VIRTUALENV=1`.
- The venv uses system site packages so existing local harness dependencies
  remain visible, while `pip install -e .` writes into the task-local venv
  instead of global conda site-packages.

## Paid Run Impact

The stopped run
`mainline_4x30_cold_contractfix_stage1_20260622` halted correctly on
`host_dependency_contamination`. Trusted scoreable rows before the halt remain
diagnostic evidence; invalid abort rows must be retried and must not enter
ModelFit or paper metrics.

## Verification

- `196 passed, 5 skipped`
- `py_compile` passed for the touched harness modules.
- `git diff --check` passed.
- Runtime contamination detector now reports `contamination_count 0`.

## Residual Risk

For tonight's paid line, prefer stable local-harness repos and avoid newly
exposed Matplotlib/Seaborn dependency-sensitive tasks unless explicitly running
a harness diagnostic.
