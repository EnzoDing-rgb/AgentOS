# Nightly Paper Progress Blocker

Date: 2026-06-02T08:05:23+08:00

The night runner stopped before BudgetFlow compare because the Qwen provider preflight failed.

```bash
PYTHONPATH=src:../external/mini-swe-agent/src ../.venv/bin/python -u -m budgetflow.run_deepseek_smoke --tier compare
```

Exit code: `1`

This is an infrastructure/auth blocker, not a BudgetFlow model result. Fix `DASHSCOPE_API_KEY`, then rerun:

```bash
cd /home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1
scripts/run-nightly-paper-progress.sh
```

Log:

```text
/home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1/data/runs/nightly-paper-progress.log
```
