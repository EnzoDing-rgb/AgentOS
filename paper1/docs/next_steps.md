# BudgetFlow Next Steps

Pending-review entry point. Use this file together with `north_star.md` and
`related_work.html`. Treat `archive/progress.md` as historical context.

## Current State

- Current artifact:
  `paper1/paper/BudgetFlow_Value_Aware_Budget_Governance_for_Agent_Tasks.pdf`.
- Status: short ICML-style draft is ready for Fengde Ding's first review.
- Reviewer for the next step: Fengde Ding `<fengde_ding@uir.edu.cn>`.
- Current action: wait for review of the short PDF before expanding the paper.
- Keep the current PDF anonymous until the draft mode changes.

## Paper Direction

- Core problem: **Batch-Level Task Budget Allocation**.
- Main idea: BudgetFlow turns "budget flows to higher-value tasks" into a
  concrete system design under one shared hard budget.
- Main metrics: Resolved Rate, Total Resolved Value (TRV), and TRV per Dollar.
- Main evidence: use the 4x30 run plus the three 5x30 runs as a boundary-aware
  cost-value story, with the latest audited 5x30 as the strongest positive case.
- Sensitivity families: Task Value sensitivity, budget sensitivity, and
  KV Cache Cost-Discount sensitivity.

## System Design Position

Present BudgetFlow's design as the bridge between the value objective and the
runtime policy. The important abstraction is that each task exposes four
interfaces:

- Task Value
- Estimated Token Demand
- Model Fit
- Verifier

These signals enter different decisions: route, cap, escalate, stop, and defer.
This should appear in the Method/System section as a compact figure or table.
It should read as an auditable budget-governance interface, not as a broad
software-engineering manifesto.

SWE-bench repo-specific adapters, harness patches, and local compatibility
layers are engineering infrastructure. They should stay out of the paper's main
mechanism because they are narrow to the benchmark.

## v0.2 After Review

- Expand only after Fengde Ding reviews the short PDF.
- Target a complete 8--10 page ICML-style draft when the content justifies it.
- Move Related Work after Introduction.
- Use `paper1/docs/related_work.html` as the source for Related Work.
- Expand the method section around the actual allocation policy, not decorative
  formulas.
- Add clearer figures and tables for the cost-value curve, operating
  conditions, and sensitivity results.
- Keep wording direct, technical, and readable.

## Future Work Emphasis

- Finer-grained strong-model allocation inside a task: stage/segment routing,
  escalation, and stop/defer policy.
- Continual policy learning: using completed runs to improve future allocation
  while preserving auditability.
- Serving-aware and multi-tenant BudgetFlow: connect Task Value, remaining
  budget, and outcome history to serving substrates such as vLLM, SGLang, and
  NVIDIA Dynamo, then extend from one budget owner to multiple budget owners.

## Guardrails

- Use the canonical terms in `north_star.md`.
- Use cheap model and strong model in paper prose.
- Report boundary cases as part of the cost-value frontier story.
- Keep Related Work respectful and concrete.
- Keep HTML as auxiliary visual material; the paper workflow is PDF-first
  LaTeX.
