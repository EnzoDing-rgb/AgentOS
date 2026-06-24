# Independent Review: RouteLLM-Inspired Baseline for Claim 1

No `BLOCKER`.

## Bottom line

The proposed **RouteLLM-inspired learned task router** is the right next strong baseline for Claim 1, with one important constraint: it must remain a **non-value-aware, route-only baseline** that selects `T2` or `T3` at task start from pre-execution task features and frozen historical outcomes, then runs under the **same fixed task set, same backend pool, same shared hard cap, and same verifier** as BudgetFlow. If it is allowed to ingest Task Value, use value-derived frozen-plan builders, or receive BudgetFlow runtime advantages beyond static route choice, it stops being a clean baseline for the paper's main question.

## 1. What the experiment is trying to prove

The experiment is trying to prove a narrow and important point:

> BudgetFlow's value-aware shared-budget allocation beats a strong learned router baseline that also chooses `T2`/`T3` per task, but does so without Task Value and without runtime shared-budget reasoning.

That is the missing comparison after pure `T2` and pure `T3`. The question is no longer "does BudgetFlow beat uniform tiers?" but "does BudgetFlow beat a serious learned routing control inspired by the routing literature?" This matches the North Star framing in [north_star.md](/root/.dev/AgentOS/paper1/docs/north_star.md) and the related-work audit.

## 2. Is the baseline fair?

Yes, **if implemented in the strict form above**.

Fair conditions:

- same fixed task set and order
- same `T2`/`T3` backend pool
- same shared hard cap, enforced the same way
- same verifier and harness
- task-start routing only
- no mid-task escalation
- no runtime learning
- no task reordering

The current codebase already has a clean path for this: [frozen_router.py](/root/.dev/AgentOS/paper1/src/budgetflow/frozen_router.py) keeps the frozen plan separate from caps, and [strategies.py](/root/.dev/AgentOS/paper1/src/budgetflow/adapter/strategies.py) already supports a static frozen-plan route via `enterprise_router`.

The main fairness caveat is that the learned-router baseline should run as the plain frozen router path, not as a BudgetFlow-wrapped variant such as `budgetflow_same_router`, because that would mix "router quality" with BudgetFlow runtime behavior.

## 3. Should the learned router use Task Value?

**No, not for the primary baseline.**

Plain English: if the baseline is allowed to see Task Value, then it is no longer a neutral learned router. It starts using the same privileged signal that BudgetFlow is supposed to make useful. That collapses the comparison.

The clean question is:

- BudgetFlow: has Task Value and shared-budget reasoning
- Learned router baseline: does not have Task Value; only learns which tasks look like `T3` tasks

Then, if BudgetFlow wins, the paper can honestly say that **value-aware budget governance** adds something beyond normal routing.

A Task-Value-aware learned router can still be useful as a **supplemental ablation**, but not as the main strong baseline.

## 4. Is offline training -> FrozenRouterPlan the cleanest integration path?

Yes.

This is the cleanest path both experimentally and architecturally:

- training stays offline and auditable
- runtime consumes a static artifact
- the runtime comparison stays simple
- the frozen plan can be logged per task
- budget enforcement remains external and identical across policies

This also avoids contaminating the baseline with online adaptation that would turn it into a different class of policy.

## 5. What training labels are valid?

Best primary label:

- **`T3 better than T2`** on the same task, defined from frozen historical verified outcomes

Why:

- `T3 pass` alone is weak because it does not tell the router whether `T2` would also have passed
- `T3 better than T2` directly matches the routing decision
- it stays closer to the RouteLLM spirit: predict when the strong model is the better choice

Label comparison:

- **`T3 pass`**: valid but weak; it over-routes `T3` on tasks where both tiers pass
- **`T3 better than T2`**: best primary label; directly answers the routing question
- **`T3 worth extra cost`**: dangerous for the primary baseline if "worth" includes Task Value; then the label bakes Claim 1 logic into the baseline

If a cost-aware variant is desired, use a value-free version such as:

- `T3 better than T2 and not dominated on expected cost`

But the main baseline should stay simple.

## 6. Leakage risks and prevention

Main leakage risks:

1. **Task-value leakage**
   - Do not use Task Value as a feature or label component.
   - Do not build the plan with [frozen_router_plan_builder.py](/root/.dev/AgentOS/paper1/src/budgetflow/frozen_router_plan_builder.py), which is explicitly value/effort based and would invalidate the baseline.

2. **Train/test leakage across tasks**
   - Training data must exclude evaluation tasks.
   - Split by `instance_id`, and preferably by evaluation batch or held-out task set, not random row split.

3. **Outcome leakage from the same run family**
   - Do not train on rows produced under the same evaluation batch being scored.
   - Freeze the training corpus before the comparison.

4. **Catalog/model-fit leakage**
   - If model-fit-like features are used, they must come from same-catalog, same-physical-backend evidence only.
   - Do not mix historical rows across different catalog hashes/revisions.

5. **Budget leakage**
   - Do not encode the answer from the compiled budget regime or downstream budget outcomes into the router features.
   - The router may know only pre-execution task features, not "how much cap is left later."

6. **Verifier leakage / post-hoc threshold tuning**
   - Threshold calibration must happen on training or validation data only.
   - Do not tune the `T3` fraction on the evaluation batch after seeing outcomes.

## 7. Are there stronger replacement baselines?

Not as the **next** baseline.

From the related-work audit, the strongest replacement candidate is not another literature router but a **static oracle DP / knapsack allocation control**. That is a valuable follow-on because it tests whether BudgetFlow beats a stronger static allocator under the same cap. But it is not a better immediate replacement for the RouteLLM-inspired baseline:

- RouteLLM-inspired router answers the most obvious reviewer question now: "does BudgetFlow beat a learned router?"
- static DP answers a different question: "does runtime value-aware allocation beat static global assignment?"

So my recommendation is:

1. implement RouteLLM-inspired learned router first
2. add static oracle DP as the next diagnostic control

I would not replace the RouteLLM-inspired baseline with UCCI-, FrugalGPT-, INTENT-, BATS-, or RouteNLP-style baselines for Claim 1.

## 8. What would make this baseline misleading or invalid?

Any of the following would weaken or invalidate it:

- giving the learned router **Task Value**
- training labels that already encode **value-weighted worth**
- using the existing **value/effort frozen-plan builder**
- allowing **mid-task escalation** or stage-aware switching
- comparing it under a different cap, verifier, or backend pool
- tuning the threshold on the evaluation tasks
- mixing training data from different physical model catalogs
- using `budgetflow_same_router` and then calling that a plain learned-router baseline
- letting the baseline reorder tasks or use runtime shared-budget state

## Recommendation

Proceed with the RouteLLM-inspired learned router as the next strong baseline, but define it narrowly:

- offline supervised training
- route-only `FrozenRouterPlan`
- primary label = `T3 better than T2`
- no Task Value input
- runtime = plain frozen router under the same shared hard cap

That design gives the paper a credible strong baseline and preserves the clean Claim 1 story: BudgetFlow is being tested against a serious learned router without quietly giving the baseline BudgetFlow's core advantage.
