# BudgetFlow Next Steps

Pending-review entry point. Use this file together with `north_star.md` and
`related_work.html`. Treat `paper1/misc/archive/progress.md` as historical
context.

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

## Narrative Revision

The next draft should start from the general problem, then instantiate it on
SWE-bench. The paper should first define the transferable setting: many
valuable tasks share one hard budget; each task exposes Task Value, runway/cap
planning information from Estimated Token Demand, Model Fit, and a Verifier;
the system allocates scarce model opportunities to maximize verified value.

SWE-bench should then appear as a strict testbed for that setting: a task batch,
pre-registered values, different model tiers, measurable spend, and a
test-based verifier. This ordering makes BudgetFlow read as a general
batch-budget interface with one rigorous instantiation, rather than a
SWE-bench-specific system followed by a portability claim.

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
- Move Related Work directly after Introduction so readers see the per-query,
  per-task, serving-systems, and batch-budget boundaries before the method.
- Use `paper1/docs/related_work.html` as the source for Related Work.
- Expand the method section around the actual allocation policy, not decorative
  formulas.
- Add clearer figures and tables for the cost-value curve, operating
  conditions, and sensitivity results.
- Replace the current placeholder-style result visuals with two main figures:
  a multi-run main-evidence figure and a latest-5x30 sensitivity figure.
- Keep wording direct, technical, and readable.

## Policy Comparison Table

Replace the current bullet list of five policies with a compact table. The
table should compare policy inputs and the shared outcome contract, not prose
definitions.

| Policy | Same shared budget | **Task Value** | Runway / cap planning | Model choice | Same verifier |
|---|---:|---:|---:|---|---:|
| cheap-model-only | yes |  |  | fixed cheap model | yes |
| strong-model-only | yes |  |  | fixed strong model | yes |
| learned task-router | yes |  |  | value-blind learned choice | yes |
| budget-only | yes |  | yes | budget-pressure choice | yes |
| **BudgetFlow** | yes | **yes** | yes | value-aware choice | yes |

The table should make Task Value visually prominent. The shared budget and the
Verifier are held constant across all policies; the key contrast is whether
Task Value enters allocation of scarce model opportunities. Explain that
runway/cap planning is the decision-facing form of Estimated Token Demand.

## Figure Plan

Use two separate visual dimensions.

1. **Multi-Run Main Evidence.** This figure supports the main claim. It should
   show the 4x30 run plus the three 5x30 runs as operating conditions, with
   BudgetFlow, cheap-model-only, strong-model-only, learned task-router, and
   budget-only policies shown consistently. It should make the main positive
   signals visible: the latest 5x30 full win, the 4x30 TRV/TRV-per-Dollar win,
   and the close boundary cases where the strong model leads.
2. **Latest 5x30 Sensitivity.** This figure supports robustness and diagnosis.
   It should use only the latest audited 5x30 run for Task Value sensitivity,
   budget sensitivity, and KV Cache Cost-Discount sensitivity.

Tables and figures should guide the reader's eye to the positive signals.
Use boldface and red text in tables for the winning or most important positive
entries, such as the latest 5x30 BudgetFlow wins and the 4x30 TRV/TRV-per-Dollar
wins. Use color, larger markers, frontier lines, and concise annotations in
figures. The visual style should be closer to frontier/scaling-law figures:
clean grid, colored policy curves or point series, clear boundary line, and a
few labeled key points.

## Future Work Emphasis

- Finer-grained strong-model allocation inside a task: stage/segment routing,
  escalation, and stop/defer policy.
- Continual policy learning: using completed runs to improve future allocation
  while preserving auditability.
- Serving-aware and multi-tenant BudgetFlow: connect Task Value, remaining
  budget, and outcome history to serving substrates such as vLLM, SGLang, and
  NVIDIA Dynamo, then extend from one budget owner to multiple budget owners.

## Submission Strategy

Use the conference survey files under `paper1/paper/reference/` as reference
material, then verify the target CFP page again before any submission.

Submission targets are planning inputs, not writing constraints. The draft
should stay faithful to the Main Claim rather than bending the narrative toward
one venue.

Current strategy: list five candidate venues, but act on the top one or two
first. The goal of the first submission is reviewer feedback, not maximizing
the prestige of the first target.

Recommended short list:

1. **AgenticDev 2026 @ ASE** — first-choice practice target. It is the closest
   topic match for agentic software development and has a fast workshop review
   cycle.
2. **RASE 2026 @ ASE** — strong practice backup if the paper is framed around
   reliability, trustworthy automation, or software-engineering implications.
3. **APSEC 2026** — C-class main-conference path for formal external feedback,
   pending final deadline confirmation on the official submission page.
4. **ICECCS 2026** — engineering-systems backup with a near-term deadline.
5. **AAAI-27** — high-risk feedback source with a near deadline and two-phase
   review. Use it to test whether broad AI reviewers buy the claim, not as the
   only first submission plan.

Execution plan after the next draft:

- Prepare an AgenticDev-ready version first.
- Keep an AAAI abstract/title version ready if the draft quality is strong by
  the July deadline.
- Pick one main-conference practice target from APSEC or ICECCS after checking
  the live CFP and formatting constraints.
- Preserve stronger later targets such as AAMAS, SANER, MSR, or FSE for a
  revised paper that has benefited from the first review cycle.

## Guardrails

- Use the canonical terms in `north_star.md`.
- Use cheap model and strong model in paper prose.
- Report boundary cases as part of the cost-value frontier story.
- Keep Related Work respectful and concrete.
- Keep HTML as auxiliary visual material; the paper workflow is PDF-first
  LaTeX.
