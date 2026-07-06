BLOCKER: the current North Star and the current draft are not terminology-consistent. `paper1/docs/north_star.md` retires `Yield` / `Yield per Dollar` in reviewer-facing prose and says the paper must always separate SWE-bench-standard outcomes from paper-defined value metrics, but `paper1/docs/draft.md` still headlines `Yield`, `Yield/$`, and `pass` throughout the abstract, introduction, setup, results, and discussion. That inconsistency is severe because it makes the metric story look post-hoc even if the underlying design is defensible.

# Independent Review of Metric Design

## Bottom line

The current six-metric set is broadly defensible if the paper is explicit about three layers:

1. **Community-standard SWE-bench outcomes:** `Resolved Count`, `Resolved Rate`.
2. **Cost accounting / efficiency diagnostics:** `Total Spend`, `Cost per Resolved Task`.
3. **Paper-defined value objective:** `Total Resolved Value`, with `Total Resolved Value per Dollar` as a secondary efficiency diagnostic.

The design becomes misleading if `Total Resolved Value` is presented as if it were a SWE-bench metric, or if `Total Resolved Value per Dollar` is allowed to displace `Resolved Rate` in the headline.

## 1. Is this metric set honest about SWE-bench official metrics?

**Yes, if and only if** the main table always includes `Resolved Count` and `Resolved Rate`, and the paper explicitly states that these are the official SWE-bench-style outcome metrics.

`Total Spend` and `Cost per Resolved Task` are reasonable external cost diagnostics. `Total Resolved Value` and `Total Resolved Value per Dollar` are **not** SWE-bench metrics and must never be described that way.

## 2. Is Total Resolved Value properly labeled as paper-defined rather than community-standard?

**In `north_star.md`: yes. In the draft as a whole: not yet.**

`north_star.md` is directionally correct: it says `Total Resolved Value` is paper-defined and not an official SWE-bench metric. But the draft still uses `Yield` as a headline term without enough repeated disclosure that this is a paper-defined objective. Reviewers will read that as metric laundering unless the draft is normalized to the North Star vocabulary.

## 3. Should Total Resolved Value be the Claim 1 objective, or should the paper use only Resolved Rate / Cost per Resolved Task?

`Total Resolved Value` should remain the **Claim 1 objective**.

Reason:

- The paper’s claimed problem is **shared-budget allocation across tasks with heterogeneous pre-registered value**.
- `Resolved Rate` alone cannot express that problem because it assigns every task weight 1.
- `Cost per Resolved Task` is useful, but it optimizes average cost of an unweighted success, not value captured under a shared cap.

If the paper abandons `Total Resolved Value` as the objective, it is no longer testing its own stated claim. Instead, it collapses back to a standard unweighted SWE-bench efficiency comparison.

The defense is not to hide the custom objective. The defense is to state clearly that:

- SWE-bench official outcome is unweighted resolved rate.
- Paper Claim 1 is a different, explicitly paper-defined objective because the decision problem is different.

## 4. Is Total Resolved Value per Dollar too misleading for the main table, or acceptable as an efficiency diagnostic?

**Acceptable as an efficiency diagnostic. Too risky as the lead column.**

It should stay in the main table only if it appears **after** `Resolved Count`, `Resolved Rate`, `Total Spend`, and `Cost per Resolved Task`, and only if the text calls it a paper-defined value-efficiency diagnostic.

Why the caution:

- It is a ratio of a paper-defined quantity to spend.
- Ratios are easy to over-read when the numerator is unfamiliar.
- It can look like a disguised attempt to replace standard accuracy-style reporting.

So: keep it, but subordinate it.

## 5. What main table ordering best defends the paper?

Best ordering:

1. `Policy`
2. `Resolved Count`
3. `Resolved Rate`
4. `Total Spend`
5. `Cost per Resolved Task`
6. `Total Resolved Value`
7. `Total Resolved Value per Dollar`

This ordering is the most defensible because it moves from:

- official benchmark outcome,
- to plain cost accounting,
- to the paper-defined objective,
- to the paper-defined efficiency ratio.

That ordering shows the paper is not trying to smuggle a custom metric into the place normally occupied by SWE-bench resolution.

## 6. What exact text must appear in the paper body to avoid post-hoc value-weighting objections?

The paper should contain text close to the following:

> SWE-bench’s community-standard outcome is whether an instance is verified resolved, reported as Resolved Count and Resolved Rate. We report those metrics in every main result table.

> Our Claim 1 objective is different and paper-defined: under a shared hard budget, tasks may have different pre-registered importance. We therefore define Total Resolved Value as the sum of pre-registered task values over verified resolved tasks: \(\sum_i v_i \cdot \mathbf{1}[\text{task } i \text{ is resolved}]\).

> The task values \(v_i\) were fixed before running the evaluated policies, derived from a pre-registered ValueSource, and were not tuned on outcomes from the compared runs.

> To show that the result is not an artifact of favorable weighting, we also report an equal-value sensitivity in which all task values are set to 1.0. Under that setting, Total Resolved Value reduces to Resolved Count.

> We therefore distinguish three metric layers: standard SWE-bench outcomes (Resolved Count, Resolved Rate), cost diagnostics (Total Spend, Cost per Resolved Task), and our paper-defined value objective (Total Resolved Value, with Total Resolved Value per Dollar as a secondary efficiency diagnostic).

That text, or very close equivalent, should appear in the metrics section and be reflected in table captions.

## 7. Are there better established cost-aware metrics we should use instead?

**Not as replacements.**

There is no stable, peer-established cost-aware coding-agent metric that cleanly replaces the current design.

What exists:

- `Cost per Resolved Task`: widely understandable and worth keeping.
- Cost-performance curves / AUC-style measures such as SWE-Effi-style resource curves: useful appendix diagnostics, but not a substitute for the fixed-cap shared-budget question.
- Pareto frontier reporting: useful in sensitivity analysis, but not the primary Claim 1 readout.

Recommendation:

- Keep the current six metrics.
- Add, in appendix or sensitivity sections, one cost-curve view if available.
- Do **not** swap the main claim onto EuCB/AUC/Pareto metrics, because those answer a broader cost-performance frontier question, not the paper’s specific fixed shared-cap objective.

## 8. Are there any severe inconsistencies in current North Star terminology?

**Yes.**

1. `north_star.md` retires `Yield` / `Yield per Dollar`, but `draft.md` still uses them as headline terms.
2. `north_star.md` says SWE-bench-standard wording is `Resolved Count` / `Resolved Rate`, but the draft still leans on `pass`, `Pass count`, and `17/30 pass`.
3. `north_star.md` says the paper must separate standard metrics, paper-defined objective, and diagnostics, but the draft still presents `Yield` and `Yield/$` as the natural headline without enough guardrails.

These are not cosmetic issues. They directly affect whether the metric story looks honest.

## Final recommendation

The underlying metric design is defensible. The presentation is not yet safe.

Use:

- `Resolved Count` and `Resolved Rate` as the unmistakable SWE-bench-standard anchor.
- `Total Resolved Value` as the explicit paper-defined Claim 1 objective.
- `Total Resolved Value per Dollar` only as a secondary efficiency diagnostic.

Do not defend the paper by renaming `Yield`. Defend it by making the metric hierarchy explicit and by showing equal-value sensitivity alongside the main value-weighted results.
