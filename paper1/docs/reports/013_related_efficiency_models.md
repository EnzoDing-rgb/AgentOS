# 013 - Related Efficiency Models

Date: 2026-06-03

## Health Check

- Status: `continue`
- Recent artifacts look healthy: `paper1/data/runs/postfix_011_sanity-0.jsonl` and `paper1/data/runs/auto_budget_memory.jsonl` both parsed cleanly (14 rows each, 0 JSON errors, 0 duplicates, 0 `resolved=None`, 0 `harness_resolved=None`).
- `paper1/data/runs/postfix_011_sanity.log` and `paper1/data/runs/postfix_011_sanity-0.summary.log` end normally, with no UTF-8 corruption or truncation markers; the only warnings are routine long-output notices.
- No sign of provider-wide failure, worktree crash, or row-level pollution in the latest run artifacts. The current run state looks like ordinary mixed pass/fail/budget-exhausted behavior, not a stop condition.

## Model Read

- **Liquid LFM2.5**: real model family, but mainly a backend/model-efficiency story. Official docs frame `LFM2.5-350M` as an ultra-compact edge model with native tool calling and mobile/embedded deployment. That is not a direct BudgetFlow competitor; it is a candidate backend.
- **Ling-2.6-flash**: also mostly backend/model-efficiency, but closer to our surface area. The official card says it targets inference efficiency, token efficiency, and agent performance, and explicitly mentions agent benchmarks and frameworks like OpenClaw/Hermes in evaluation. Useful as a backend candidate, not as a competing orchestration system.
- **OpenSquilla**: likely a true agent/runtime competitor, not just a model backend. The official site frames it as a microkernel AI agent with smart routing, persistent memory, sandboxing, and cost tracking. Treat the marketing claims as *official self-description*, not independently verified measurements.
- **Hermes / OpenClaw**: also system/runtime competitors. Official pages describe them as persistent, self-hostable agent runtimes with memory, skills, cron, browser/tool use, and model routing. Same caveat: useful for positioning, but keep performance claims low-confidence unless we run our own measurements.

## BudgetFlow Claim

- Narrow the headline to: **BudgetFlow improves task success per dollar for agentic code-repair workloads under fixed budget caps**.
- Do **not** claim general model efficiency, fastest inference, or universal routing superiority. That would put us in direct marketing-claim crossfire with LFM/Ling/OpenSquilla/Hermes, and most of those claims are not independently verified here.
- Separate layers explicitly: `BudgetFlow = budget-aware policy/orchestration`; `LFM/Ling = backend/model efficiency`; `OpenSquilla/Hermes/OpenClaw = agent runtime/orchestration`.

## What To Borrow

- From **LFM2.5**: edge deployment, native tool calling, compact-backend ablations.
- From **Ling-2.6-flash**: token-efficiency training, hybrid attention / sparse-MoE-style efficiency framing, and “shorter useful outputs” as an ablation axis.
- From **OpenSquilla**: routing tiers, prompt-cache isolation, explicit cost tracking, and sandbox policy separation.
- From **Hermes/OpenClaw**: persistent memory, skills, cron/workflow persistence, and model-failover as runtime policy.

## Backend Candidates

- `LFM2.5-350M` is worth a **T1 smoke backend** only if we want a cheap, compact baseline.
- `Ling-2.6-flash` is worth a **T2/T3 small-run backend** only if provider access is stable and the same task/cap protocol can be held constant.
- Do **not** promote either to main-paper claims without head-to-head runs on the same tasks, same caps, and same routing policy.

## Sources

- [Liquid AI docs: LFM2.5-350M](https://docs.liquid.ai/lfm/models/lfm25-350m)
- [Liquid AI homepage](https://www.liquid.ai/)
- [Ling-2.6-flash model card](https://huggingface.co/inclusionAI/Ling-2.6-flash-fp8)
- [OpenSquilla official site](https://opensquilla.ai/)
- [Hermes Agent official site](https://hermes-agent.ai/)
- [OpenClaw official site](https://openclaw.ai/)
