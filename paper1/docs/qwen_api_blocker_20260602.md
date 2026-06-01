# Qwen API Blocker

Date: 2026-06-02

## Check

Ran a tiny API ping:

```bash
PYTHONPATH=src:../external/mini-swe-agent/src python -m budgetflow.run_deepseek_smoke --tier flash,pro
```

## Result

Both Qwen routes failed before any agent/harness run:

```text
openai/qwen3-coder-flash -> AuthenticationError: Incorrect API key provided
openai/qwen3.6-plus      -> AuthenticationError: Incorrect API key provided
```

Log:

```text
data/runs/qwen_api_ping_20260602.log
```

## Interpretation

No BudgetFlow model-performance conclusion should be drawn while this persists. Qwen-backed strategies would fail for provider/auth reasons, not because of routing, budget, scaffold, or model capability.

## Resume

After replacing/fixing `DASHSCOPE_API_KEY`, rerun:

```bash
cd /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1
PYTHONPATH=src:../external/mini-swe-agent/src ../.venv/bin/python -u -m budgetflow.run_deepseek_smoke --tier flash,pro
```

Only if this passes should the Qwen BudgetFlow goldpass5 run be resumed.
