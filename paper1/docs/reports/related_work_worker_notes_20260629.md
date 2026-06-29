# Related Work Worker Notes — 2026-06-29

Status: agents dispatched, awaiting results.

| Paper | Agent | Status |
|---|---|---|
| RouteLLM | Agent 1 | ✅ done — per-query soft α threshold, NO task value, NO verified outcomes. Original = related work boundary; RouteLLM-inspired adaptation = Claim 1 baseline. |
| RouteNLP | Agent 2 | ✅ done — NO shared budget, NO task value, per-query routing. Related work boundary. |
| FrugalGPT | Agent 3 | ✅ done — soft average E[cost]≤b, NO task value, NO routing baselines. Related work boundary. |
| UCCI | Agent 4 | ✅ done — per-query NER calibration, NO shared budget, NO task value. Related work boundary. |
| Topaz | Agent 5 | ✅ done — CHI workshop demo, no baselines, DP in appendix only. Explainability neighbor, NOT Claim 1 baseline. |
| INTENT | Agent 6 | ✅ done — per-task tool planning, independent B=50, NO cross-task allocation. Related work boundary. |
| Cascade Routing | Agent 7 | ✅ done — per-query expected cost, formal optimality proofs, SWE-bench oracle only. Related work boundary. Replaces FrugalGPT. |
| BAMAS | Agent 8 | ✅ done — per-task budget, within-task architecture optimization (ILP+RL). Related work boundary, not cross-task. |
| Freshness Auditor | Agent 9 | ✅ done — recommends: KEEP RouteLLM/RouteNLP/UCCI/INTENT, REPLACE FrugalGPT→Cascade Routing, REPLACE Topaz→BAMAS |

## Final deliverable

HTML written to: `paper1/docs/reports/related_work_budgetflow_boundary_table_20260629.html` (336 lines, 30KB)

Final 6 papers:
1. RouteLLM (Ong 2024, NeurIPS)
2. Cascade Routing (Dekoninck 2025, ICLR) — replaces FrugalGPT
3. RouteNLP (Guo 2026, ACL Industry)
4. BAMAS (Yang 2026, AAAI Oral) — replaces Topaz
5. UCCI (Kotte 2026)
6. INTENT (Liu 2025, ICML)

Key finding: NONE of the 6 solve BudgetFlow's problem. All are per-query or per-task. None have shared hard budget + task value + verified outcomes. This is BudgetFlow's core distinction.
