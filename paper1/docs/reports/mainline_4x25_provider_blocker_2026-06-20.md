# Mainline 4x25 Provider Blocker

Date: 2026-06-20

## Objective

Start the 4-policy x 25-task diagnostic run after the Budget Compiler
projection-diagnostics fix.

## Result

The run did not enter task execution. Paid readiness passed, but provider
signature preflight blocked before the first task.

Command stem:

- `mainline_4x25_tasklevel_fix_20260620`

Relevant committed code:

- `8c0cfb8 Add budget compiler projection diagnostics`

## Evidence

Paid readiness:

- `tasks=25`
- `strategies=4`
- `step_limit=60`
- budget plan: `mainline_4x25_tasklevel_fix_budget_plan_20260620.json`
- budget plan decision: `PASS`
- task-level projection diagnostic: `tier2=8`, `tier3=17`
- readiness result: `PASS`

Provider signature preflight:

```text
[preflight] FAIL backend=tier2 provider=openai_compatible model=openai/glm-5.1 status=400 error=BadRequestError
[preflight] PASS backend=tier3 provider=openai_compatible model=openai/gpt-5.4
provider signature check failed: tier2:BadRequestError
```

Direct DashScope HTTP checks against several listed models all returned the
same account-state error:

```text
{"error":{"message":"Access denied, please make sure your account is in good standing. For details, see: https://help.aliyun.com/zh/model-studio/error-code#overdue-payment","type":"Arrearage","param":null,"code":"Arrearage"}}
```

Models checked:

- `glm-5.1`
- `ZHIPU/GLM-5.1`
- `qwen3-coder-flash`
- `qwen3.7-plus`

The `/models` endpoint returned status 200, so the key can authenticate for
metadata. Completion calls are blocked by the provider account billing state.

## Decision

Stop here. Do not bypass `--no-provider-signature-check`, because the run would
turn provider billing failures into false BudgetFlow evidence.

Do not run a T3-only substitute under the same claim, because the planned
4-policy comparison requires T2 and task-level T2/T3 routing.

## Next Step

Restore DashScope account billing/access for completion calls, then re-run the
same command with the same committed code and budget plan.
