# BudgetFlow Refactor Plan — frozen-scaffold pivot

> 目标：让论文回到原始 contribution（runtime-layer budget governance + stage-aware routing），把 scaffold 退还给外部已验证项目。
>
> 一句话：别测「我们的 agent 会不会修 bug」，测「同一 agent、同一 budget，BF 是否分得更对、batch 是否更稳」。
>
> 修订原则：**小步、长期可维护**。每步有 success gate，gate 不过不进下一步。Tier 1 写死默认表，不引入任何 calibration。

---

## 0. Direction lock

| 项 | 决定 |
|---|---|
| Scaffold | **[mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent)** — **公认框架**，frozen commit pin；**仅 bash**（`subprocess.run`），无自建 tool-calling / JSON edit IR |
| BudgetFlow 位置 | LLM-call boundary（wrapper Model class），**不动 mini-SWE 的 bash 循环 / prompt / submit 协议** |
| Harness | **A 优先**：mini-SWE-agent 自带 Docker SWE-bench eval（可与公开 leaderboard 对标）；**B fallback**：`local_harness.py`（Docker 不可用时，论文须明写不可直接比 SOTA） |
| 主指标 | `harness_resolved` |
| Backend pool | **仅 DeepSeek 两档**：Flash = `deepseek_flash`；Pro = `deepseek_pro`。**全文不出现 Claude/GPT**。三策略全在同一对 Flash/Pro 上比 |
| 策略 | **迭代式扩展**。iter-1 = 2 (Full + Budget-Only)；iter-2 加 Workflow-Level；iter-3 加 all_flash + all_pro anchors。每 iter 通过 gate 才扩 |
| 预算档 | **loose + tight 两档**。pilot 自适应（见 Step B.0） |
| Tier 1 校准 | **不做**。`zero_calibration` 默认表（concept §3.4）+ 默认 `w_i` (L=1.0 / R=3.0 / V=2.5) 全程写死 |
| 不做 | 自建 agent framework（`tool_sandbox` / `apply_edits` / staged ReAct 等）/ replay routing eval / progress table 校准 / 在 eval 集上 tune |

---

## 1. Scope: keep / archive / new

### 1.1 保留（runtime core，无改动或小修）

```
src/budgetflow/governor.py
src/budgetflow/ledger.py
src/budgetflow/selector.py
src/budgetflow/scheduler.py
src/budgetflow/policies.py
src/budgetflow/types.py
src/budgetflow/zombie.py
src/budgetflow/loop.py                     # mock / compare 仍可能依赖
src/budgetflow/deepseek_backend.py
src/budgetflow/mock_backend.py
src/budgetflow/local_harness.py
src/budgetflow/lite_tasks.py           # 只保留 task loader + harness 摘要
src/budgetflow/repo_context.py
src/budgetflow/compare.py              # 复用聚合/打印骨架
tests/test_budgetflow_runtime.py
```

### 1.2 归档（**移到 archive 分支，main 删除**）

新建分支 `archive/staged_react_v1`，把以下整体 push 上去，**main 上 `git rm`**：

```
src/budgetflow/monolithic_react_agent.py
src/budgetflow/staged_react_agent.py
src/budgetflow/react_loop.py
src/budgetflow/repair_workspace.py
src/budgetflow/patch_agent.py
src/budgetflow/patch_utils.py
src/budgetflow/stage_classifier.py     # 旧版认自建 tool 名；归档，由 adapter/bash_stage.py 替代
src/budgetflow/tool_sandbox.py
tests/test_tool_sandbox.py
src/budgetflow/run_react_e2e_compare.py
src/budgetflow/run_e2e_compare.py
src/budgetflow/run_e2e_smoke.py
src/budgetflow/run_deepseek_smoke.py   # 旧 connectivity smoke
src/budgetflow/run_deepseek_compare.py # 旧 rubric-based 10-task
src/budgetflow/run_lite_smoke.py       # 仅 mock；保留与否看 RQ1 设计，默认归档
tests/test_repair_workspace.py
```

> 流程：commit 现状到 main → `git checkout -b archive/staged_react_v1` → push → 回 main → `git rm` 上面文件 → commit。**不要 `rm -rf`**。

### 1.3 新增

```
external/mini-swe-agent/                       # submodule 或 vendor，PINNED_COMMIT 文件记 hash
src/budgetflow/adapter/__init__.py
src/budgetflow/adapter/mini_swe_proxy.py       # BF-wrapped Model class
src/budgetflow/adapter/strategies.py           # 路由策略
src/budgetflow/adapter/bash_stage.py           # 从 mini-SWE bash action/observation 推断 L/R/V（concept §8.5）
src/budgetflow/defaults.py                     # 写死的 zero_calibration 表 + w_i 默认
src/budgetflow/run_mini_swe_compare.py         # RQ2 runner
src/budgetflow/run_pilot.py                    # Step B.0 budget pilot
src/budgetflow/run_batch_governance.py         # RQ1 runner
docs/refactor_plan.md                          # 本文件
docs/protocol.md                               # frozen 实验协议
```

**`defaults.py` 内容大致：**

```python
# concept.md §3.3 / §3.4 cold-start 默认。论文复现的唯一来源。
W_I = {"localization": 1.0, "repair": 3.0, "validation": 2.5}

# zero_calibration: 每升一档 +0.05，repair +0.10
PROGRESS_TABLE = {
    ("localization", "flash"): 0.30,
    ("localization", "pro"):   0.35,
    ("repair",       "flash"): 0.20,
    ("repair",       "pro"):   0.30,
    ("validation",   "flash"): 0.25,
    ("validation",   "pro"):   0.30,
}

BUDGET_PRESSURE_INIT = 0.35   # 与旧 FROZEN_BUDGET_PRESSURE 一致
```

任何运行器只读这些常量，**不接受命令行 override**。

**`bash_stage.py` 规则（concept §8.5，对齐 mini-SWE bash 词汇）：**

```python
# 输入：上一条 bash command 字符串 + observation 文本
# ls / cat / find / grep / rg / head / sed -n → LOCALIZATION
# sed -i / patch / diff / git apply / echo >> file → REPAIR
# python / pytest / pip test / COMPLETE_TASK → VALIDATION（或 submit）
# 默认 → LOCALIZATION
```

旧 `stage_classifier.py`（`apply_edits` / `grep` tool 名）**归档**，不得再进主路径。

---

## 2. Execution order

> 顺序刚性：A → B → C → D。每步 success gate 不过，**不进下一步**。

### Step A — Adapter

**输入**：mini-SWE-agent 仓库 (`SWE-agent/mini-swe-agent`)，DeepSeek API key（已在 env）。

**动作**：
1. Vendor：
   - `git submodule add https://github.com/SWE-agent/mini-swe-agent external/mini-swe-agent`
   - 或拷贝 tag 到 `external/mini-swe-agent/`，commit hash 写 `external/PINNED_COMMIT`
2. 阅读 mini-SWE-agent 的 `Model` / `query()` 入口（litellm 调用点）。
3. `adapter/mini_swe_proxy.py`：
   - 类 `BudgetFlowModel`，签名匹配 mini-SWE-agent 期望的 Model 接口。
   - 流程：
     1. `classify_bash_stage(last_bash_command, last_observation) -> Stage`（**新** `adapter/bash_stage.py`；读 mini-SWE 的 bash command + observation，**不用**旧 `stage_classifier.py` 的 `apply_edits`/`grep` tool 名）。
     2. 当前 strategy 调用 `strategies.choose_tier(turn_info, governor.state())` 返回 `(tier, model_id)`。
     3. `governor.reserve(workflow_id, tier, max_output_tokens)`，不通过 → downgrade 或拒绝。
     4. 调 `deepseek_backend` 实际调用。
     5. `governor.settle(workflow_id, actual_tokens)`。
     6. 写 `TurnInfo` 到 ledger。
4. `adapter/strategies.py`：
   ```python
   class Strategy(Protocol): ...
   class AllFlash: ...        # 常量 flash
   class AllPro: ...          # 常量 pro
   class WorkflowLevelRouter: # workflow 开始按 issue/repo 选一档，整 workflow 不变
   class BudgetOnly:          # 只看 budget_pressure + reserved_cost
   class BudgetFlowFull:      # concept §3.1 公式，读 defaults.PROGRESS_TABLE / W_I
   ```

**Success gate A**：
- harness 与 `protocol.md` 一致（Docker A 优先；不可用才 B + disclaimer）。
- lite 前 3 task smoke（**不绑特定 id**）。strategy=`all_pro`，DeepSeek Pro，mini-SWE 默认 prompt。
- **≥1 task `harness_resolved=True`** → A 过。
- 3 task 全 0 → 查 env（API key / Docker harness / repo checkout），换更易 Lite task；**禁止**改 mini-SWE prompt/tools，**不换** backend vendor。
- ledger 完整，无未结算 budget。

### Step B — RQ2 harness compare

**输入**：Step A 通过的 adapter；lite eval 子集任务列表（n=20，task id list 写入 protocol.md，hash 锁定）。

#### B.0 — Budget pilot（一次性，结果写 protocol.md）

- 跑 `run_pilot.py`：lite eval 集前 3 task × `all_pro`，无 budget cap。
- 计算 `M = median(per_task_actual_cost)`（3 个任务的中位数，USD 或 governor unit 统一口径）。
- 锁定 **per-task** budget cap（RQ2 串行，每 task 独立 governor）：
  - `loose_per_task = 2 × M`
  - `tight_per_task = 0.5 × M`
- 写入 protocol.md，**之后实验只读不改**（勿 × n；× n 是 batch 共享池语义，留给 RQ1）。
- pilot **只产出 M**；iter-3 **不得**复用 pilot 的 resolved/cost（pilot 无 budget cap，与 loose/tight 不可比）。

#### B.1 — Iter-1: BF Full vs Budget-Only（核心 decisive experiment）

- strategies = `{budgetflow_full, budget_only}`
- budgets = `{tight_per_task, loose_per_task}`
- n = 20 lite tasks（id list 来自 protocol.md）
- 网格：`2 strat × 2 budget × 20 task = 80 runs`，**串行**
- 每 run 记 jsonl：`instance_id, strategy, budget_arm, harness_resolved, actual_cost, picks, llm_turns, violations(reservation_denied/rate_limited/zombie_cancelled)`
- 输出汇总：`data/runs/rq2_iter1_summary.md`

**Iter-1 gate**：
- 任一 budget arm 下两策略 `resolved` 差 ≥ 1 task **或** `cost@iso-resolved` 差 ≥ 10% → **过，进 B.2**
- 两 budget arm 都打平且 cost 接近 → **gate fail**：论文头条切 RQ1，先做 Step C；iter-2/3 之后视 RQ1 结果决定是否补

#### B.2 — Iter-2: + Workflow-Level Router

- strategies 加 `workflow_level`，同 n / 同 budgets
- 增量 `1 strat × 2 budget × 20 task = 40 runs`
- 汇总 3-way 比较表 → `rq2_iter2_summary.md`
- gate：表完整可读，无 hard budget violation → 进 B.3

#### B.3 — Iter-3: + all_flash + all_pro anchors

- strategies 加 `all_flash`, `all_pro`，同 n / 同 budgets
- 增量 `2 strat × 2 budget × 20 task = 80 runs`（全跑，无 pilot 复用）
- 汇总 5-strategy 完整表 → `rq2_iter3_summary.md`
- gate：表完整 → 论文 RQ2 可投

> **iter-3 完成前，n 不扩到 50。** 5-strategy × 2 budget × 20 = 200 run 已经覆盖 paper headline。n=50 扩展放 paper revision 阶段。

### Step C — RQ1 mock batch governance

**输入**：runtime core（governor / scheduler / zombie），mock_backend。**不依赖** mini-SWE-agent。

**动作**：
1. `run_batch_governance.py`：
   - 参数：`--J {10|50}`, `--budget`, `--rpm_limit`, `--concurrency_slots`, `--zombie_rate`, `--seed`
   - 模拟 J 条 workflow 并发，每条由 L/R/V stage 序列构成；mock_backend 返回 (cost, latency)
   - 注入：(a) `zombie_rate` 比例的 workflow 卡死（无新 token > n 秒），(b) 部分调用超 RPM 触发 429
2. 报告：
   - `budget_violations`（应 = 0）
   - `429_rate` observed
   - `p50 / p99 queue_latency`
   - `recovered_budget`（zombie 回收）
   - `cancelled_zombies`
   - `wasted_reservation_ratio`
   - `admission_throughput (calls/min)`
3. 两挡 `J=10` / `J=50`；每挡跑 with/without ZombieDetector → ablation
4. 汇总 `result_batch.md`

**Success gate C**：
- `budget_violations == 0`
- ZombieDetector off 与 on 的 `recovered_budget` 有差距
- Governor RPM 限流开启时 `429_rate` 显著低于关闭版本

### Step D — Docs update

**动作**：
1. `paper1_concept.md`：
   - §2 强调 "BudgetFlow does not own the scaffold; mini-SWE-agent is the agent substrate"
   - §5.4 删 calibration replay 那段或标 **(Tier 2, out of scope for this paper)**
   - §8.5 Tier 1 表：scaffold 从 "mini-SWE-agent (planned)" 改成 "mini-SWE-agent (pinned commit <hash>)"
   - §3.4 整段移到 future work / Tier 2 章节
2. `paper1_design.md`：
   - §2.1–2.3 把自建 mini scaffold 改成 mini-SWE-agent 接入说明
   - 加一节 `2.x mini-SWE-agent integration`，描述 `BudgetFlowModel` 接口
3. `progress.md`：清空旧 5/26 entries，写新 milestone（A / B.0 / B.1 / B.2 / B.3 / C 完成时点）
4. `result.md`：
   - 旧 E2E 2-task / 10-task rubric 章节加标记 **(superseded — see archive/staged_react_v1)**，不删（论文 motivation 要解释为何换路线）
   - 新增 §RQ2 iter-1/2/3 表、§RQ1 batch governance 表
5. `protocol.md`（新建，**冻结**，只增不改）：
   - eval task id list（hash）
   - scaffold commit hash
   - harness flavor（A=mini-SWE Docker / B=local_harness）；若 B，附 disclaimer 模板
   - backend pool：Flash + Pro 具体 model_id（来自 deepseek_backend.py 暴露的名称）+ 单价（pilot 时点抓取）
   - `loose_per_task`, `tight_per_task` 数值（B.0 输出）
   - `defaults.py` 路径与 git hash
   - 5 个 strategy 的实现入口

---

## 3. Anti-overfit guardrails（必须遵守）

| 规矩 | 怎么落地 |
|---|---|
| `progress_table` 全程写死 | `defaults.PROGRESS_TABLE` 常量，concept §3.4 zero_calibration；运行器禁止 override |
| `w_i` 全程写死 | `defaults.W_I`，concept §3.3 默认 |
| `budget_pressure` 启动值写死 | `defaults.BUDGET_PRESSURE_INIT`；运行时闭环调整规则也是 concept §3.1 默认，不依赖任务 |
| eval task list 冻结 | `protocol.md` 记 id list；runner 启动时校验 task hash |
| scaffold 冻结 | submodule pin commit；任何 mini-SWE-agent 源码改动 = 实验作废 |
| mini-SWE prompt / tool 协议只读 | 若实验发现需改 prompt 才能跑通某 task → 立即停跑、换 task 或换 backend；**禁止 fork mini-SWE 改 prompt**。一旦改了，scaffold 不再"公认"，实验等于回到自建路线 |
| 完整报告 | 同时报 violations + resolved + cost，不挑赢的指标 |

---

## 4. 取消列表（**禁做**）

- 不在自研 scaffold 上继续迭代（prompt / IR / repair retry）
- 不在 eval 集上做 hyperparameter sweep
- **不做 replay routing eval**（concept §3.4 第 2 项 Tier 2 / out of scope）
- **Tier 1 不做 progress table 校准**（zero_calibration 默认表为最终值）
- 不为追求 "BudgetFlow 一定要赢" 调整 routing 参数；若 Budget-Only 已够好，论文 claim 即收敛到 RQ1
- 不引入 continual learning / RLB / SweRank / SweLoc 作为主实验（保留为 future work 段落）
- 不把 `workflow_steps_ok` 当 `harness_resolved` 写进论文 headline
- 不在 iter-3 完成前把 n 扩到 50

---

## 5. 失败分支应对

| 情形 | 应对 |
|---|---|
| Step A：3 task all_pro 全 0 resolved | 查 harness/Docker/API；换更易 Lite task；**仍只用 DeepSeek Flash+Pro，不改 scaffold** |
| Step B.1 gate fail（两策略打平） | 论文头条切 RQ1（"shared-budget runtime governance"），先做 Step C；iter-2/3 视 RQ1 结果决定是否补 |
| Step B.3：BF Full 输给 Budget-Only | 诚实报告；论文 claim 落到 cost-saving + RQ1，concept §8.6 已预案 |
| Step C：mock 不真实 | 论文里明确 "mock 限于 governance 机制压力测试，不 claim 真实 throughput"；不引真 API 并发 burning |

---

## 6. 完成定义（paper-ready）

- `external/mini-swe-agent/` pin commit，`PINNED_COMMIT` 文件存在
- `adapter/mini_swe_proxy.py` + `strategies.py` + `defaults.py` 全 type-checked，1-task smoke 测试通过
- B.0 pilot 完成，`protocol.md` 含 `loose_per_task` / `tight_per_task`
- B.1 / B.2 / B.3 各 iter gate 通过，对应 summary md 存在
- C J=10 / J=50 跑通，`result_batch.md` 存在
- `paper1_concept.md` / `paper1_design.md` / `result.md` 同步
- `archive/staged_react_v1` 分支推上，main 干净
- `protocol.md` 完整冻结

---

## 7. 一句话给执行 AI

> vendor **mini-SWE-agent（bash-only）** → **BudgetFlowModel**（DeepSeek Flash/Pro only）→ iter 1/2/3 + RQ1 batch → 改文档。**禁止**自建 scaffold / 改 mini-SWE prompt / 换非 DeepSeek backend。

---

## 8. 计划够简单吗？跑完应看到什么

**够简单。** 四步、两个产物类型：

```
A  接 mini-SWE + BF wrapper     → smoke：all_pro 至少 1/3 resolved
B  RQ2 对照（DeepSeek F/P）     → 一张 resolved/cost 表（论文 RQ2）
C  RQ1 mock 并发               → 一张 governance 表（论文 RQ1）
D  文档同步
```

### Step A 完成后

- `external/mini-swe-agent/` + `PINNED_COMMIT`
- `adapter/mini_swe_proxy.py` 能跑
- **预期**：3 task × `all_pro` → **≥1 `harness_resolved=True`**；ledger 有 flash/pro picks

### Step B 完成后（论文 RQ2 主表）

**文件**：`data/runs/rq2_iter*.jsonl` + `rq2_iter3_summary.md`

**预期看到类似表**（数字示意，非承诺）：

| strategy | budget | resolved ( /20 ) | avg cost/task | violations |
|---|---|---|---|---|
| all_pro | loose | 8–12 | 高 | 0 |
| all_flash | loose | 3–6 | 低 | 0 |
| budgetflow_full | **tight** | **≥ budget_only** | 中 | 0 |
| budget_only | tight | 低 | 中 | 0 |
| workflow_level | tight | 中 | 中 | 0 |

**好结果（RQ2 成立）**：tight 下 `budgetflow_full` resolved **≥** budget_only，cost **<** all_pro。  
**可接受（RQ2 弱）**：loose 打平，tight 下 Full 多 1–2 题。  
**仍可写论文（RQ1 头条）**：策略全打平 → Step C batch 表撑系统贡献。

**BF picks 预期**：多数 task 仍是 **flash/pro/flash** 混用（Repair 步 Pro）。

### Step C 完成后（论文 RQ1 主表）

**文件**：`result_batch.md`

**预期**：

| 配置 | budget_violations | 429_rate | recovered_budget | p99 queue |
|---|---|---|---|---|
| Governor+Zombie ON | **0** | 低 | **>0** | 可控 |
| Zombie OFF | 0 | 低 | ≈0 | 略差 |
| 无 Governor | **>0** 或失控 | 高 | — | 崩 |

### paper-ready 时 `result.md` 应有

1. **RQ2 表**：5 strategy × 2 budget × resolved + cost（DeepSeek Flash/Pro）
2. **RQ1 表**：J=10/50 governance 指标
3. **一句结论**：BF 在 tight budget 下 resolved/cost 相对谁赢；或 honest fallback「batch governance 为主贡献」
4. 旧 2-task 自建 scaffold 结果标 **superseded**
