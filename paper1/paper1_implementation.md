# Paper 1 Implementation Runbook

> 这份文档是 **"怎么在某台机器上跑起来/复现实验"** 的操作手册（runbook）。
>
> - **想搞清楚系统要做成什么样、怎么验收**：看 `paper1_design.md`
> - **想在实验服务器上按步骤跑出数据**：看本文（`paper1_implementation.md`）

> 术语、DoD、Phase 定义、对象模型、events 字段规范、policy 集合、workload schema——统一在 `paper1_design.md`，本文不重复，只写"具体命令"。

---

## 0. 一条命令产出一次 run（目标形态）

```bash
python paper1/agentos-exp/runner.py \
  --workload paper1/workloads/mixed_v1.json \
  --policy agentos \
  --seed 42 \
  --out paper1/runs/$(date -u +%Y-%m-%dT%H%M%SZ)/
```

输出目录包含：
- `events.jsonl` — 唯一真相（所有指标从这里算）
- `summary.json` — 本次 run 汇总，字段与 `paper1_design.md §3.2` 对齐
- `config_snapshot/` — workload/policy/backends 配置的快照

**主线实验默认用 MockDriver**（可控、可复现）；真实 vLLM 只做 sanity。

---

## 1. 当前服务器环境（2026-04，写死）

| 项目 | 值 |
|---|---|
| Python | Conda base，3.11.5；`httpx/numpy/pandas` 可直接 import |
| 真实 LLM | vLLM OpenAI-compatible，`http://127.0.0.1:30019`，model `qwen3.5` |
| 待探端口 | `0.0.0.0:30023`（未知用途，可能是第二个 backend） |
| 不可用 | `8000`（未 listen）；`11434`（litellm stopped + 需要 API key） |
| 代码目录 | 本地写 → `git push` → 服务器 `git pull /Lishun/projects/AgentOS/` |
| 输出目录 | `/Lishun/projects/AgentOS/paper1/runs/<ts>/` |

---

## 2. 目录结构（建好再跑）

```
paper1/
├── agentos-exp/
│   ├── runner.py          # 主入口：读 workload → 跑 policy → 写 events.jsonl + summary.json
│   ├── drivers.py         # MockDriver + RealDriver（OpenAI-compatible）
│   ├── governor.py        # BudgetGovernor + RateLimiter + AdmissionControl
│   ├── scheduler.py       # PriorityQueue + ModelSelector + ZombieDetector
│   └── analyze.py         # 从 events.jsonl 算指标/出图（论文用）
├── workloads/
│   ├── rq1_mixed.json     # RQ1：混合 short/long，无 zombie
│   ├── rq2_mixed.json     # RQ2：混合 interactive/batch，两个后端
│   └── rq3_zombie.json    # RQ3：注入 20% zombie（卡死/烧钱）
├── backends/
│   └── backends.yaml      # BackendProfile 手填配置
└── runs/                  # 实验输出（gitignore 大文件，只提交 summary.json）
```

服务器上建目录：

```bash
cd /Lishun/projects/AgentOS
mkdir -p paper1/{agentos-exp,workloads,backends,runs}
```

---

## 3. Phase 0：骨架 + events.jsonl writer（先跑通再说）

**验收目标**：跑 3 个 Turn，events 出现 `created → completed`，`summary.json` 能生成。

### 3.1 写 `drivers.py`

```python
# paper1/agentos-exp/drivers.py
import asyncio, time, random
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class DriverResult:
    text: str
    input_tokens: int
    output_tokens: int
    ttft_ms: float
    total_latency_ms: float
    error_type: Optional[str] = None   # http_429 / timeout / http_5xx / driver_error / none
    quality_score: Optional[float] = None

class MockDriver:
    """可控延迟/失败/token/质量分。主线实验用它保证可复现。"""
    def __init__(self, backend_id: str, profile: dict):
        self.backend_id = backend_id
        self.profile = profile  # 来自 backends.yaml 的 BackendProfile

    async def call(self, turn: dict, rng: random.Random) -> DriverResult:
        m = turn.get("mock", {})
        latency_ms = m.get("latency_ms", 500) * rng.uniform(0.8, 1.2)
        ttft_ms    = m.get("ttft_ms", 100)    * rng.uniform(0.8, 1.2)
        error      = m.get("error", "none")

        if error == "timeout":
            await asyncio.sleep(latency_ms / 1000)
            return DriverResult("", 0, 0, 0, latency_ms, error_type="timeout", quality_score=0.0)
        if error == "http_429":
            await asyncio.sleep(0.05)
            return DriverResult("", 0, 0, 0, 50, error_type="http_429", quality_score=0.0)
        if error == "burn":  # 烧钱 zombie：正常完成但输出 token 异常多
            out_tok = m.get("output_tokens", 200) * rng.randint(5, 20)
            await asyncio.sleep(latency_ms / 1000)
            return DriverResult("burn", m.get("input_tokens", 100), out_tok,
                                 ttft_ms, latency_ms, error_type=None,
                                 quality_score=m.get("quality_score", 0.3))

        await asyncio.sleep(latency_ms / 1000)
        return DriverResult(
            text="mock_ok",
            input_tokens=m.get("input_tokens", 100),
            output_tokens=m.get("output_tokens", 200),
            ttft_ms=ttft_ms,
            total_latency_ms=latency_ms,
            error_type=None,
            quality_score=m.get("quality_score", 0.85),
        )

class RealDriver:
    """OpenAI-compatible（vLLM）。只做 sanity，不作主线。"""
    def __init__(self, backend_id: str, base_url: str, model: str, profile: dict):
        import httpx
        self.backend_id = backend_id
        self.base_url = base_url
        self.model = model
        self.profile = profile
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def call(self, turn: dict, rng: random.Random) -> DriverResult:
        import httpx, time
        client = await self._get_client()
        prompt = turn.get("prompt", "Reply with exactly: ok")
        payload = {"model": self.model,
                   "messages": [{"role": "user", "content": prompt}],
                   "temperature": 0, "stream": True}
        t0 = time.perf_counter()
        ttft_ms = None
        try:
            async with client.stream("POST", f"{self.base_url}/v1/chat/completions",
                                     json=payload) as resp:
                if resp.status_code == 429:
                    return DriverResult("", 0, 0, 0,
                                        (time.perf_counter()-t0)*1000, "http_429", 0.0)
                if resp.status_code >= 500:
                    return DriverResult("", 0, 0, 0,
                                        (time.perf_counter()-t0)*1000, "http_5xx", 0.0)
                tokens = 0
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line[6:].strip() != "[DONE]":
                        if ttft_ms is None:
                            ttft_ms = (time.perf_counter()-t0)*1000
                        tokens += 1
            lat = (time.perf_counter()-t0)*1000
            return DriverResult("real_ok", 0, tokens, ttft_ms or lat, lat)
        except Exception as e:
            return DriverResult("", 0, 0, 0,
                                 (time.perf_counter()-t0)*1000, f"driver_error:{e}", 0.0)
```

### 3.2 写 `runner.py`（最小版，Phase 0）

```python
# paper1/agentos-exp/runner.py  ——  Phase 0 最小版
import argparse, asyncio, json, os, random, time, uuid
from pathlib import Path
from drivers import MockDriver, RealDriver

EPOCH_MS = time.time() * 1000  # 相对时间基准

def ts_ms() -> int:
    return int(time.time() * 1000)

class EventWriter:
    def __init__(self, path: str):
        self._f = open(path, "w")

    def write(self, event: dict):
        self._f.write(json.dumps(event) + "\n")
        self._f.flush()

    def close(self):
        self._f.close()

def load_backends(yaml_path: str) -> dict:
    import yaml
    with open(yaml_path) as f:
        return {b["backend_id"]: b for b in yaml.safe_load(f)["backends"]}

def make_driver(backend_id: str, profile: dict, real_base_url: str = None):
    if backend_id.startswith("mock"):
        return MockDriver(backend_id, profile)
    return RealDriver(backend_id, real_base_url or profile["base_url"],
                      profile["model"], profile)

async def run_turn(turn: dict, driver, writer: EventWriter,
                   policy: str, rng: random.Random, sem: asyncio.Semaphore):
    tid = turn["turn_id"]
    writer.write({"ts_ms": ts_ms(), "event": "created",  "turn_id": tid, "policy": policy})
    writer.write({"ts_ms": ts_ms(), "event": "admitted", "turn_id": tid})

    q0 = time.perf_counter()
    async with sem:
        queue_wait_ms = (time.perf_counter() - q0) * 1000
        writer.write({"ts_ms": ts_ms(), "event": "queued",
                      "turn_id": tid, "queue_wait_ms": round(queue_wait_ms, 1)})
        writer.write({"ts_ms": ts_ms(), "event": "dispatched",
                      "turn_id": tid, "backend_id": driver.backend_id})
        writer.write({"ts_ms": ts_ms(), "event": "running", "turn_id": tid})

        result = await driver.call(turn, rng)

    ok = result.error_type in (None, "none")
    price_in  = driver.profile.get("price_usd_per_1k_input",  0.001)
    price_out = driver.profile.get("price_usd_per_1k_output", 0.002)
    cost_usd  = (result.input_tokens * price_in + result.output_tokens * price_out) / 1000

    backend_event = {
        "ts_ms": ts_ms(), "event": "backend_call", "turn_id": tid,
        "backend_id": driver.backend_id,
        "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
        "cost_usd": round(cost_usd, 6),
        "ttft_ms": round(result.ttft_ms, 1),
        "total_latency_ms": round(result.total_latency_ms, 1),
        "error_type": result.error_type or "none",
        "quality_score": result.quality_score,
    }
    writer.write(backend_event)

    final_event = "completed" if ok else "failed"
    writer.write({"ts_ms": ts_ms(), "event": final_event, "turn_id": tid})

    return {"ok": ok, "cost_usd": cost_usd,
            "ttft_ms": result.ttft_ms, "latency_ms": result.total_latency_ms,
            "quality": result.quality_score, "error_type": result.error_type}

def pct(vals, p):
    if not vals: return None
    s = sorted(vals); k = (len(s)-1)*(p/100); f = int(k); c = min(f+1, len(s)-1)
    return s[f] if f == c else s[f] + (s[c]-s[f])*(k-f)

def build_summary(run_id, policy, workload_id, seed, stats, wall_s) -> dict:
    oks    = [s for s in stats if s["ok"]]
    fails  = [s for s in stats if not s["ok"]]
    ttfts  = [s["ttft_ms"] for s in oks if s["ttft_ms"]]
    quals  = [s["quality"] for s in oks if s["quality"] is not None]
    errs_429 = sum(1 for s in stats if s.get("error_type") == "http_429")
    errs_to  = sum(1 for s in stats if s.get("error_type") == "timeout")
    total_cost = sum(s["cost_usd"] for s in stats)
    n = len(stats)
    return {
        "run_id": run_id, "policy": policy,
        "workload_id": workload_id, "seed": seed,
        "turn_total": n, "turn_completed": len(oks), "turn_failed": len(fails),
        "turn_reaped": 0,
        "quality_mean": round(sum(quals)/len(quals), 4) if quals else None,
        "quality_std":  round((sum((q-sum(quals)/len(quals))**2 for q in quals)/len(quals))**0.5, 4) if len(quals)>1 else None,
        "ttft_mean": round(sum(ttfts)/len(ttfts), 1) if ttfts else None,
        "ttft_p95":  round(pct(ttfts, 95), 1) if ttfts else None,
        "ttft_p99":  round(pct(ttfts, 99), 1) if ttfts else None,
        "cost_total_usd": round(total_cost, 6),
        "budget_total_usd": None,
        "budget_time_exhausted_s": None,
        "error_429_rate":  round(errs_429/n, 4) if n else 0,
        "timeout_rate":    round(errs_to/n, 4)  if n else 0,
        "wall_time_s": round(wall_s, 2),
        "throughput_turns_per_s": round(n/wall_s, 3) if wall_s > 0 else 0,
    }

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workload",  required=True)
    ap.add_argument("--policy",    required=True,
                    choices=["raw","governor_only","baseline_A_fixed_expensive",
                             "baseline_B_per_request_router","agentos"])
    ap.add_argument("--backends",  default="paper1/backends/backends.yaml")
    ap.add_argument("--seed",      type=int, default=42)
    ap.add_argument("--concurrency", type=int, default=50)  # raw 模式用
    ap.add_argument("--max-inflight", type=int, default=16) # governor 模式用
    ap.add_argument("--out",       required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "config_snapshot").mkdir(exist_ok=True)

    import shutil
    shutil.copy(args.workload, out / "config_snapshot/workload.json")
    shutil.copy(args.backends, out / "config_snapshot/backends.yaml")

    with open(args.workload) as f:
        workload = json.load(f)
    backends = load_backends(args.backends)

    rng = random.Random(args.seed)
    writer = EventWriter(str(out / "events.jsonl"))
    run_id = str(uuid.uuid4())[:8]
    workload_id = workload.get("workload_id", Path(args.workload).stem)

    # 选并发上限（raw vs governor）
    if args.policy == "raw":
        concurrency = args.concurrency
    else:
        concurrency = args.max_inflight
    sem = asyncio.Semaphore(concurrency)

    # 选 backend（简单策略：raw/governor_only/baseline_A 用第一个；其他暂同）
    default_backend_id = workload.get("default_backend", list(backends.keys())[0])
    driver = make_driver(default_backend_id, backends[default_backend_id])

    turns = workload["turns"]
    t0 = time.perf_counter()
    tasks = [run_turn(t, driver, writer, args.policy, rng, sem) for t in turns]
    all_stats = await asyncio.gather(*tasks)
    wall_s = time.perf_counter() - t0

    writer.close()

    summary = build_summary(run_id, args.policy, workload_id, args.seed,
                             list(all_stats), wall_s)
    with open(out / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
```

### 3.3 写 `backends.yaml`

```yaml
# paper1/backends/backends.yaml
backends:
  - backend_id: mock_expensive
    context_window: 128000
    price_usd_per_1k_input:  0.030
    price_usd_per_1k_output: 0.060
    rpm_limit: 60
    tpm_limit: 100000
    quality_prior:
      codegen: 0.92
      code_edit: 0.90
      debug: 0.88
      test: 0.86
      retrieval: 0.85
      transform: 0.95
      docs: 0.84

  - backend_id: mock_cheap
    context_window: 32000
    price_usd_per_1k_input:  0.003
    price_usd_per_1k_output: 0.006
    rpm_limit: 120
    tpm_limit: 200000
    quality_prior:
      codegen: 0.70
      code_edit: 0.68
      debug: 0.62
      test: 0.65
      retrieval: 0.75
      transform: 0.93
      docs: 0.72

  - backend_id: real_vllm
    base_url: http://127.0.0.1:30019
    model: qwen3.5
    context_window: 32000
    price_usd_per_1k_input:  0.001
    price_usd_per_1k_output: 0.002
    rpm_limit: 60
    tpm_limit: 50000
    quality_prior:
      codegen: 0.80
      code_edit: 0.80
      debug: 0.80
      test: 0.80
      retrieval: 0.80
      transform: 0.80
      docs: 0.80
```

### 3.4 生成 Phase 0 最小 workload（3 个 Turn）并验收

```bash
cd /Lishun/projects/AgentOS
cat > paper1/workloads/phase0_smoke.json << 'EOF'
{
  "workload_id": "phase0_smoke",
  "default_backend": "mock_expensive",
  "turns": [
    {"turn_id": "t001", "at_ms": 0,   "priority": "interactive", "task_type": "codegen",
     "mock": {"input_tokens": 200, "output_tokens": 150, "latency_ms": 300, "ttft_ms": 80,  "error": "none", "quality_score": 0.90}},
    {"turn_id": "t002", "at_ms": 100, "priority": "batch",       "task_type": "transform",
     "mock": {"input_tokens": 100, "output_tokens": 80,  "latency_ms": 200, "ttft_ms": 60,  "error": "none", "quality_score": 0.80}},
    {"turn_id": "t003", "at_ms": 200, "priority": "interactive", "task_type": "debug",
     "mock": {"input_tokens": 500, "output_tokens": 400, "latency_ms": 800, "ttft_ms": 150, "error": "none", "quality_score": 0.88}}
  ]
}
EOF

pip install pyyaml -q

python paper1/agentos-exp/runner.py \
  --workload paper1/workloads/phase0_smoke.json \
  --policy raw \
  --out paper1/runs/phase0_smoke/ \
  --seed 42

# 验收：events.jsonl 应有 3×(created/admitted/queued/dispatched/running/backend_call/completed)
grep '"event"' paper1/runs/phase0_smoke/events.jsonl | wc -l   # 应 >= 21
cat paper1/runs/phase0_smoke/summary.json | python -m json.tool
```

---

## 4. Phase 1：MockDriver 429 / 限流验收

```bash
# 生成带 429 的 workload
python - << 'PY'
import json, random
rng = random.Random(1)
turns = []
for i in range(20):
    error = "http_429" if rng.random() < 0.3 else "none"
    turns.append({
        "turn_id": f"t{i:03d}", "at_ms": i*50,
        "priority": "batch", "task_type": "transform",
        "mock": {"input_tokens": 100, "output_tokens": 80, "latency_ms": 200,
                 "ttft_ms": 60, "error": error, "quality_score": 0.75}
    })
print(json.dumps({"workload_id":"phase1_429","default_backend":"mock_expensive","turns":turns},indent=2))
PY > paper1/workloads/phase1_429.json

python paper1/agentos-exp/runner.py \
  --workload paper1/workloads/phase1_429.json \
  --policy raw \
  --out paper1/runs/phase1_429/ \
  --seed 1
# 验收：error_429_rate 应 ~0.3；summary 中 turn_failed > 0
```

---

## 5. RQ1 实验：裸跑 vs Governor-only

### 5.1 生成 RQ1 workload（200 Turn，20% 长任务）

```bash
python - << 'PY'
import json, random
rng = random.Random(42)
turns = []
for i in range(200):
    long = rng.random() < 0.2
    turns.append({
        "turn_id": f"t{i:03d}", "at_ms": i * 100,
        "priority": "interactive" if rng.random() < 0.5 else "batch",
        "task_type": rng.choice(["codegen","code_edit","debug","test","retrieval","transform","docs"]),
        "mock": {
            "input_tokens":  500 if long else 100,
            "output_tokens": 600 if long else 80,
            "latency_ms":   1200 if long else 250,
            "ttft_ms":       200 if long else 60,
            "error": "none",
            "quality_score": round(rng.uniform(0.75, 0.95), 2)
        }
    })
with open("paper1/workloads/rq1_mixed.json","w") as f:
    json.dump({"workload_id":"rq1_mixed","default_backend":"mock_expensive","turns":turns},f,indent=2)
print("done:", len(turns), "turns")
PY
```

### 5.2 跑两次

```bash
TS=$(date -u +%Y-%m-%dT%H%M%SZ)

# baseline: 裸跑（policy=raw，并发 50）
python paper1/agentos-exp/runner.py \
  --workload paper1/workloads/rq1_mixed.json \
  --policy raw \
  --concurrency 50 \
  --seed 42 \
  --out paper1/runs/${TS}_rq1_raw/

# treatment: governor_only（限并发 16）
python paper1/agentos-exp/runner.py \
  --workload paper1/workloads/rq1_mixed.json \
  --policy governor_only \
  --max-inflight 16 \
  --seed 42 \
  --out paper1/runs/${TS}_rq1_gov/
```

### 5.3 对比（手动或用 analyze.py）

```bash
python - << 'PY'
import json
for label, path in [("raw",      "paper1/runs/_rq1_raw/summary.json"),
                    ("governor", "paper1/runs/_rq1_gov/summary.json")]:
    try:
        s = json.load(open(path))
        print(f"{label:12s}  ok_rate={s['turn_completed']/s['turn_total']:.2%}"
              f"  ttft_p95={s['ttft_p95']}ms  cost={s['cost_total_usd']:.4f}$"
              f"  429_rate={s['error_429_rate']:.2%}")
    except FileNotFoundError:
        print(f"{label}: 找不到 summary（路径里带了 TS，手动替换一下）")
PY
```

> 论文 RQ1 图表：用两个 `summary.json` 里的 `ttft_p95`、`error_429_rate`、`turn_completed/turn_total`。

---

## 6. RQ2 实验：多后端调度收益

### 6.1 生成 RQ2 workload（两后端；interactive vs batch；混合 task_type）

```bash
python - << 'PY'
import json, random
rng = random.Random(42)
turns = []
for i in range(100):
    priority = "interactive" if i < 20 or rng.random() < 0.3 else "batch"
    task_type = rng.choice(["codegen","code_edit","debug","test","retrieval","transform","docs"])
    long = task_type in ("codegen","code_edit","debug","test")
    turns.append({
        "turn_id": f"t{i:03d}", "at_ms": i * 150,
        "priority": priority, "task_type": task_type,
        "mock": {
            "input_tokens":  400 if long else 100,
            "output_tokens": 500 if long else 80,
            "latency_ms":   1000 if long else 200,
            "ttft_ms":       180 if long else 55,
            "error": "none",
            "quality_score": round(rng.uniform(0.70, 0.95), 2)
        }
    })
with open("paper1/workloads/rq2_mixed.json","w") as f:
    json.dump({"workload_id":"rq2_mixed","default_backend":"mock_expensive","turns":turns},f,indent=2)
print("done:", len(turns), "turns")
PY
```

### 6.2 跑三个 policy（A/B/AgentOS）

```bash
TS=$(date -u +%Y-%m-%dT%H%M%SZ)
for POLICY in baseline_A_fixed_expensive baseline_B_per_request_router agentos; do
  python paper1/agentos-exp/runner.py \
    --workload paper1/workloads/rq2_mixed.json \
    --policy ${POLICY} \
    --max-inflight 16 \
    --seed 42 \
    --out paper1/runs/${TS}_rq2_${POLICY}/
done
```

> 当前 runner.py 里三个 policy 共用同一 backend（`default_backend`）——这已经够验证 admission 差异。  
> **完整 ModelSelector 分路**（expensive vs cheap）在 Phase 4 实现后再接入；届时在 `runner.py` 里按 `policy==agentos` 加路由逻辑即可，workload 不用改。

---

## 7. RQ3 实验（场景 C）：Zombie 回收效果

### 7.1 生成带 zombie 的 workload（20% 注入）

```bash
python - << 'PY'
import json, random
rng = random.Random(99)
turns = []
for i in range(60):
    r = rng.random()
    if r < 0.10:
        zombie_type = "timeout"     # 卡死：模拟超时
        mock = {"input_tokens": 200, "output_tokens": 0,   "latency_ms": 30000,
                "ttft_ms": 0, "error": "timeout", "quality_score": 0.0}
    elif r < 0.20:
        zombie_type = "burn"        # 烧钱：输出 token 异常多
        mock = {"input_tokens": 200, "output_tokens": 200, "latency_ms": 2000,
                "ttft_ms": 100, "error": "burn", "quality_score": 0.3}
    else:
        zombie_type = "none"
        mock = {"input_tokens": 150, "output_tokens": 200, "latency_ms": 400,
                "ttft_ms": 80, "error": "none", "quality_score": 0.85}
    turns.append({
        "turn_id": f"t{i:03d}", "at_ms": i * 200,
        "priority": "batch", "task_type": "code_edit",
        "_zombie_type": zombie_type,    # 方便事后分析；runner 忽略此字段
        "mock": mock
    })
with open("paper1/workloads/rq3_zombie.json","w") as f:
    json.dump({"workload_id":"rq3_zombie","default_backend":"mock_expensive","turns":turns},f,indent=2)
zombies = sum(1 for t in turns if t["_zombie_type"]!="none")
print(f"done: {len(turns)} turns, {zombies} zombies ({zombies/len(turns):.0%})")
PY
```

### 7.2 跑两次（无回收 vs 有回收）

```bash
TS=$(date -u +%Y-%m-%dT%H%M%SZ)

# 无回收（raw，zombie 占满并发槽）
python paper1/agentos-exp/runner.py \
  --workload paper1/workloads/rq3_zombie.json \
  --policy raw \
  --concurrency 50 \
  --seed 99 \
  --out paper1/runs/${TS}_rq5_no_reap/

# 有回收（agentos，并发槽被 ZombieDetector 释放）
python paper1/agentos-exp/runner.py \
  --workload paper1/workloads/rq3_zombie.json \
  --policy agentos \
  --max-inflight 16 \
  --seed 99 \
  --out paper1/runs/${TS}_rq5_reap/
```

> ZombieDetector 完整实现在 Phase 5（`scheduler.py`）。在 Phase 5 之前，`policy=agentos` 也可以先只限并发，zombie turn 会自然 timeout 并写 `failed` 事件；Phase 5 加入检测后再补写 `zombie_reaped` 事件。

---

## 8. Sanity：用真实 vLLM 验证 3 条请求

```bash
cat > paper1/workloads/sanity_real.json << 'EOF'
{
  "workload_id": "sanity_real",
  "default_backend": "real_vllm",
  "turns": [
    {"turn_id": "r001", "at_ms": 0,   "priority": "interactive", "task_type": "transform",
     "prompt": "Reply with exactly: ok",
     "mock": {"input_tokens": 10, "output_tokens": 5, "latency_ms": 500, "ttft_ms": 100, "error": "none", "quality_score": null}},
    {"turn_id": "r002", "at_ms": 200, "priority": "batch",       "task_type": "docs",
     "prompt": "What is 2+2? Answer with just the number.",
     "mock": {"input_tokens": 15, "output_tokens": 3, "latency_ms": 500, "ttft_ms": 100, "error": "none", "quality_score": null}},
    {"turn_id": "r003", "at_ms": 400, "priority": "interactive", "task_type": "codegen",
     "prompt": "Write a one-line Python hello world.",
     "mock": {"input_tokens": 20, "output_tokens": 15, "latency_ms": 800, "ttft_ms": 150, "error": "none", "quality_score": null}}
  ]
}
EOF

python paper1/agentos-exp/runner.py \
  --workload paper1/workloads/sanity_real.json \
  --policy raw \
  --concurrency 3 \
  --seed 42 \
  --out paper1/runs/sanity_real/

cat paper1/runs/sanity_real/summary.json
```

> `RealDriver` 目前忽略 `mock` 字段，改用 `turn["prompt"]`；mock 字段只是占位（保证 workload schema 一致）。如果服务器 vLLM 不通，`error_type` 会是 `driver_error`，不影响主线。

---

## 9. 输出保存与论文复现约定

### 9.1 目录命名

```
paper1/runs/
├── 2026-04-13T120000Z_rq1_raw/
│   ├── events.jsonl
│   ├── summary.json
│   └── config_snapshot/
│       ├── workload.json
│       └── backends.yaml
├── 2026-04-13T120000Z_rq1_gov/
│   └── ...
└── ...
```

### 9.2 git 策略

- `paper1/workloads/*.json`、`paper1/backends/backends.yaml`：**提交**
- `paper1/runs/*/summary.json`：**提交**（小文件，方便论文引用）
- `paper1/runs/*/events.jsonl`：`.gitignore`（大文件；只在服务器保留）

### 9.3 论文图表来源

| 论文图/表 | 数据来源 |
|---|---|
| RQ1 完成率/429 率柱状图 | `rq1_raw/summary.json` vs `rq1_gov/summary.json` |
| RQ1 TTFT CDF | 从 `events.jsonl` 中 `backend_call` 事件的 `ttft_ms` 字段算 |
| RQ2 cost vs quality 散点图 | 四个 `rq2_*/summary.json` 的 `cost_total_usd` + `quality_mean` |
| RQ3 吞吐/完成时间对比 | `rq3_no_reap/summary.json` vs `rq3_reap/summary.json` |

---

## 10. Phase 4/5 补充（待实现时填写）

### Phase 4：ModelSelector 接入 runner.py

在 `runner.py` 的 `run_turn` 里，当 `policy in ("baseline_B_per_request_router", "agentos")` 时：
1. 按 `turn["task_type"]` + `turn["priority"]` + 当前预算水位，用 design §7.2 评分公式选 backend
2. `make_driver(selected_backend_id, backends[selected_backend_id])`
3. 写 Scheduler 事件：`{"event":"model_selected","backend_id":..., "score":...}`

### Phase 5：ZombieDetector 接入 runner.py

在 `run_turn` 里包一层 `asyncio.wait_for`：
- 超时（`latency_ms > T`）→ 写 `{"event":"zombie_reaped","reap_reason":"timeout",...}` 并释放 sem
- 烧钱（`cost_usd > k * baseline`）→ 写 `{"event":"zombie_reaped","reap_reason":"cost_overrun",...}`
- `summary.json` 中 `turn_reaped` 字段从这里统计

### Phase 6（预留接口）

`events.jsonl` 里保留事件类型：`archived / resumed / preempted`；runner.py 暂不写这三种事件，但 `analyze.py` 里已按 unknown event 跳过，不会崩。
