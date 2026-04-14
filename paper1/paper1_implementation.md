# Paper 1 Implementation Runbook（与 `paper1_design.md` 对齐）

> 本文是 **复现实验的操作手册**：怎么组织 workload、怎么跑 `policy`、怎么保存 `runs/`，以及怎么做最小 sanity。
>
> - 规格/算法/验收标准/events 字段规范：以 `paper1_design.md` 为准
> - 本文不重复设计细节，只写“命令与复现约定”

---

## 0. 一条命令 = 一次 run（目标形态）

```bash
agentos run --workload <path> --policy <policy> --out paper1/runs/<ts>/
```

输出目录（每次 run 一套）：
- `events.jsonl`：唯一真相源（所有指标从这里复算）
- `summary.json`：汇总快照（字段定义见 `paper1_design.md §3.2`）
- （可选）`config_snapshot/`：workload/policy/backends 的快照，便于复现

主线实验默认使用 **MockBackend**（见 `paper1_design.md §1.4`）。

---

## 1. 目录结构（建议）

```
paper1/
├── workloads/             # workload JSON（见 §3）
├── backends/              # backend profiles（如果实现需要外置配置）
└── runs/                  # runs/<ts>/{events.jsonl,summary.json,...}
```

初始化：

```bash
mkdir -p paper1/{workloads,backends,runs}
```

---

## 2. policy 集合（必须一致）

论文与脚本统一使用下列 7 个 policy 名称（见 `paper1_design.md §8.1`）：

- `raw`
- `governor_only`
- `baseline_A_fixed_expensive`
- `baseline_B_per_request_router`
- `baseline_C_budget_aware_router`
- `agentos_no_preempt`
- `agentos`

---

## 3. workload schema（必须一致）

workload 是一份 JSON 文件（见 `paper1_design.md §8.2`）。关键点：

- 每个 turn 的 `mock` 是一个 map：`mock[backend_id] -> {input_tokens, output_tokens, latency_ms, ttft_ms, error, quality_score}`
- `mock[backend_id].error` 只用于**非速率类**错误注入：`timeout / http_5xx / backend_error / none`
- **429 不写在 workload 里**：429 由 MockBackend 的 **动态 RPM 计数器**触发（见 `paper1_design.md §8.2 MockBackend 读取规则`）

最小示例（节选）：

```json
{
  "workload_id": "toy_3turns_v1",
  "concurrency_slots": 4,
  "turns": [
    {
      "turn_id": "t001",
      "at_ms": 0,
      "priority": "interactive",
      "task_type": "generation",
      "mock": {
        "gpt4":    { "input_tokens": 200, "output_tokens": 120, "latency_ms": 900, "ttft_ms": 120, "error": "none", "quality_score": 0.90 },
        "llama7b": { "input_tokens": 200, "output_tokens": 110, "latency_ms": 350, "ttft_ms": 70,  "error": "none", "quality_score": 0.66 }
      }
    }
  ]
}
```

---

## 4. RQ1：裸跑 vs Governor-only（限流治理）

对同一份 RQ1 workload 各跑一次：

```bash
TS=$(date -u +%Y-%m-%dT%H%M%SZ)

agentos run --workload paper1/workloads/rq1_mixed.json --policy raw           --out paper1/runs/${TS}_rq1_raw/
agentos run --workload paper1/workloads/rq1_mixed.json --policy governor_only --out paper1/runs/${TS}_rq1_gov/
```

最小验收点（见 `paper1_design.md §2 RQ1`）：
- `error_429_rate`：raw 显著更高；governor_only 接近 0
- `turn_completed/turn_total`：governor_only 更高（通常 ≥95%）
- `cost_total_usd`：不超预算（治理层硬约束）

---

## 5. RQ2：预算约束下的模型选择（完成数 vs 质量）

对同一份 RQ2 workload 跑 4 个 policy（见 `paper1_design.md §2 RQ2`）：

```bash
TS=$(date -u +%Y-%m-%dT%H%M%SZ)
for POLICY in baseline_A_fixed_expensive baseline_B_per_request_router baseline_C_budget_aware_router agentos_no_preempt; do
  agentos run --workload paper1/workloads/rq2_mixed.json --policy ${POLICY} --out paper1/runs/${TS}_rq2_${POLICY}/
done
```

最小验收点：
- A：完成数显著偏少（花光预算停工）
- `agentos_no_preempt`：总花费接近用满预算（0.90–1.00），且 `quality_avg` 高于 baseline C

---

## 6. RQ3：抢占 + 僵尸回收（交互尾延迟与吞吐）

对同一份 RQ3 workload 跑两次（见 `paper1_design.md §2 RQ3`）：

```bash
TS=$(date -u +%Y-%m-%dT%H%M%SZ)

agentos run --workload paper1/workloads/rq3_resource_contention.json --policy agentos_no_preempt --out paper1/runs/${TS}_rq3_no_preempt/
agentos run --workload paper1/workloads/rq3_resource_contention.json --policy agentos           --out paper1/runs/${TS}_rq3_agentos/
```

最小验收点：
- `events.jsonl` 出现 `preempted / archived / resumed`
- `events.jsonl` 出现 `zombie_reaped`
- `summary.json` 的 `ttft_p99` 与吞吐指标明显改善
- 抢占恢复开销必须显式报告：`resume_cost_usd`、`resume_prefill_ms`（见 `paper1_design.md §7.3`），并给出 break-even 对比

---

## 7. Sanity：真实后端跑 3 条请求（可选）

真实后端只用于“能跑通 + 字段齐全”的验证，不作为主线对照数据来源。

```bash
agentos run --workload paper1/workloads/sanity_real.json --policy raw --out paper1/runs/sanity_real/
```

质量分要求：
- `quality_score` 必须来自确定性 grader（见 `paper1_design.md §3.3`），不能用 LLM-as-judge

---

## 8. 输出保存与论文复现约定

目录命名示例：

```
paper1/runs/
├── 2026-04-13T120000Z_rq1_raw/
│   ├── events.jsonl
│   └── summary.json
└── ...
```

git 策略（建议）：
- **提交**：`paper1/workloads/*.json`、（可选）`paper1/backends/*`、`paper1/runs/*/summary.json`
- **不提交**：`paper1/runs/*/events.jsonl`（大文件；本地/服务器保留即可）

---

## 9. 跑前强制对齐清单（避免“跑了但不可用”）

- **policy 名称**：必须是上述 7 个字符串
- **workload schema**：必须使用 `mock[backend_id]`，而不是单个 `mock` 对象
- **429 注入**：只能来自 MockBackend 的动态 RPM（workload 里不写 `http_429`）
- **summary 字段**：必须与 `paper1_design.md §3.2` 对齐（例如 `quality_avg`、`ttft_p99`、`turn_reaped`）
- **RQ3 对照**：必须是 `agentos_no_preempt` vs `agentos`，且 events 中确实出现抢占与回收事件

