# BudgetFlow Takeaway

持续更新文件。目标：把烧掉的 token、实验成本、调研结论沉淀成可复用经验。即使 paper 最后失败，这里也要留下可复用的判断框架和工程经验。

该 commit 就 commit，该 push 就 push。关键节点必须 commit，能同步远端就同步远端。

## 0. 最新关键判断（2026-06-03）

### 竞争模型与论文定位

Liquid LFM2.5、Ling-2.6-flash、OpenSquilla、Hermes/OpenClaw 会影响 paper 的表述方式，但不会直接打掉 BudgetFlow。

分层判断：

- `Liquid LFM2.5`、`Ling-2.6-flash` 主要是 **backend / model-intrinsic efficiency**：模型本身更便宜、更短、更快。它们是 T1/T2 候选 backend，不是 BudgetFlow 的直接替代。
- `OpenSquilla`、`Hermes/OpenClaw` 是 **runtime / orchestration competitor**：它们也讲 routing、memory、skills、cost tracking，是真竞争。
- 这些系统的 marketing claim 不能直接当事实；只把官方自述当定位参考，性能结论必须自己跑。

BudgetFlow 的 claim 必须收窄：

- 不说“通用 token efficiency 最强”。
- 不说“最强模型路由器”。
- 主张改成：**在固定经济预算下，BudgetFlow 用 workflow/progress-aware routing 提升 agentic code-repair 的 clean resolved per dollar**。
- 关键差异是 fixed budget、batch governor、verified repair outcome、failure attribution、auto-budget learning，而不是单次调用更省 token。

远期增强方向：

- 把 Ling/LFM 作为候选 T1/T2 backend 做小规模同题同 cap 对照。
- 把 OpenSquilla/Hermes 的 memory compression、tool-output truncation、skills/on-demand context 作为 future work 或 ablation。
- 在 related work 里明确区分：model efficiency、agent runtime orchestration、BudgetFlow budget governance。

### Official Harness 定位

当前 HPC 容器不能直接跑 official SWE-bench Docker harness：

- 本地有 `paper1/data/SWE-bench`，`swebench` Python 包可 import，`run_evaluation --help` 可跑。
- 但容器里没有 `docker` CLI、没有 `/var/run/docker.sock`、没有 `dockerd/containerd/podman/nerdctl/apptainer`。
- 所以官方 harness 代码在，Docker 执行层不在。

当前策略：

- local harness 继续做 inner loop：gold sanity、debug、failure attribution、BudgetFlow 对比。
- official SWE-bench harness 做 outer audit：等 clean rows 出来后，把 prediction JSONL 拿到 Docker-capable 节点/VM/Modal/sb-cli 验证。
- paper 里必须区分 `local harness resolved` 和 `official SWE-bench resolved`。headline 结果最终最好有 official audit 支撑。

### `postfix_011_sanity` 当前状态

不要把当前 run 解读成“14 个全过所以重大突破”。真实状态：

- 已完成 22/25 rows，20/22 PASS，1 true budget fail，另有 1 crash 后 checkpoint/jsonl 状态需复核。
- `all_pro` 已确认是 T3-only、`batch_budget_cap=null`、`budget_tier=uncapped`，不属于 BudgetFlow。
- pass 的 local harness 证据基本强：`test_patch=ok; fail_before=fail; model_patch=ok; fail_after=pass; pass_to_pass=pass`。
- 但所有 rows 缺 `turn_traces`，只能做 outcome-level attribution，不能做 turn-level 细诊断。
- `budget_only_tight` 仍有 worktree add exit 128 崩溃，说明 010/011 的 worktree P0 没有实跑闭环。
- `budget_only_loose × sympy-18057` 是真 budget/repair fail：gold file edited，patch extracted，P2P pass，但 F2P 仍 fail，cap 几乎耗尽。

结论：当前实验值得继续，但必须先修/验证 worktree crash 和 checkpoint/jsonl 一致性；不要扩大到大矩阵。

## 1. 当前硬规则

### HPC / NFS / 容器

当前实验运行在 HPC 的 Kubernetes/Docker 容器里。HPC 的价值是 CPU 并行空间大；GPU 暂时不是本论文实验关键资源。

`/Lishun` 是 NFS：持久，但小文件慢。`/tmp` 是本机临时盘：快，但不持久。实验前必须设置：

```bash
export TMPDIR=/tmp
export PIP_CACHE_DIR=/Lishun/.cache/pip
```

规则：

- 临时构建、pytest tmp、解压、scratch 走 `/tmp`。
- pip 缓存走 `/Lishun/.cache/pip`。
- JSONL、checkpoint、report、final trace 必须落 `/Lishun`。
- 避免在 `/Lishun` 上做大范围 `find`、`du`、全仓库扫描；优先精确路径、`rg --files`、`find -maxdepth`。
- `exit 137` 通常是外部 `SIGKILL`，先查 cgroup/OOM/session log，再判断是不是代码问题。
- 长实验不要依赖交互式 shell 生命周期；必须支持 `--resume`、checkpoint、run-series，必要时用 tmux/nohup。

### 并行与 Resume

- 单个 policy 内部顺序跑 task，因为共享 batch-level `BudgetGovernor`。
- 不同 policy 可以并行；`run_mini_swe_compare --jobs N` 用 git worktree 做隔离。
- 并行度先保守，再扩。provider、worktree、harness 任一不稳，都不要盲目加 `--jobs`。
- resume 后必须检查重复 `(instance_id, strategy)`；重复行不能进论文表。
- 如果出现重复 JSONL、checkpoint 不一致、missing row，先判定 runner/observability bug，不要解释成模型或 BudgetFlow 失败。

## 1. Harness Gate

Local harness 必须先证明 gold patch 能过，再允许跑模型实验。这个 gate 是每次扩 task pool 的实验卫生规则，不是一次性启动条件。

当前已确认：

- `sympy__sympy-14774`: gold sanity PASS。
- `django__django-12113`: gold sanity PASS。
- `django__django-10924`: gold sanity PASS。
- 证据：`paper1/data/runs/gold_probe_harness_fix_v3.jsonl`。
- 修复报告：`paper1/docs/reports/004.md`。
- 009 新增 gold-PASS pool：7 个新 SymPy + 1 个 Requests；Requests 先不进主矩阵。
- 新 Django candidate 大量卡在 `INSTALLED_APPS` / bare-pytest gap，不能当模型失败。

必须停止并判定 harness 暂不可信的情况：

- gold patch 不能做到 `fail_before=fail` 且 `fail_after=pass`。
- P2P 在干净 base 或 gold patch 后失败。
- pytest node id mapping 失败。
- repo-specific env/compat 没有通过 adapter 显式记录。
- submitted model patch 混入 harness compatibility edit。
- worktree 残留导致某个 policy 系统性 crash。
- resume/checkpoint 造成重复结果且 summary 未去重。

最小验收命令：

```bash
cd paper1 && PYTHONPATH=src:../external/mini-swe-agent/src \
../.venv/bin/python -u -m budgetflow.gold_harness_probe \
  --ids sympy__sympy-14774,django__django-12113,django__django-10924 \
  --out data/runs/gold_probe_harness_fix_v3.jsonl
```

跨 repo 经验：

- 不要假设 Django/Requests 比 SymPy 简单；每个 repo 先 gold sanity。
- LocalHarness 要保留 repo adapter seam：SymPy/Django/Requests 的 compat、test-id mapping、settings patch 不能塞进 generic path。
- SymPy 旧依赖兼容、Django SWE-bench test id mapping、Django `INSTALLED_APPS` 都是 harness 问题，不是模型能力问题。
- local harness 是开发诊断工具；official SWE-bench 才是论文级验证工具。两者要分开解释。

## 2. 当前实验判断（009 后）

已有 008/009 model batches，共 56 recorded rows。能看到 BudgetFlow 正向信号，但数据还不够干净，不能直接上大矩阵当论文结论。

当前判断：

- `all_pro` 是 uncapped GPT-5.4 ceiling/control，不属于 BudgetFlow，不应被 Automatic Budgeting cap 限制。
- `budgetflow_full_tight` 是目前最强 budget 策略，接近 `all_pro`，且多次以更低 cost PASS。
- `all_pro` 总体仍更强；BudgetFlow 的经济性卖点还需要更干净、更大样本证明。
- GPT-5.4 有非确定性，同一 task 单次 PASS/FAIL 不能当稳定天花板。
- `django__django-12113`、`sympy__sympy-21612` 目前像 ceiling/unsolvable task，不适合证明 budget policy 差。
- `budget_only_tight` 系统性 worktree crash/缺行，修好前不能作为完整 baseline。
- 内部 `$cost` 只是 governor/provider cost unit，不是真实 USD；真实世界 API 价格需要单独校准。

当前 P0：

- 修 worktree 清理：`git worktree add` 前必须处理 stale dir / stale registration。
- 验证 checkpoint/JSONL/summary 幂等性。
- 清理 auto-budget memory，移除 `resolved=None` 污染记录。
- 新增回归测试，确保 learning signal 使用 `harness_resolved`。
- 校准真实 API 价格，避免 paper 在错误成本口径上优化。

## 3. 证据解释原则

### Pass/Fail 不够

一个失败可能来自：

- routing 策略错误；
- budget cap 太紧；
- rescue 开得太晚；
- 模型能力不够；
- task 本身太难；
- patch extraction / submission 协议失败；
- local harness 与 official SWE-bench 不一致；
- provider/API/session/worktree 基础设施问题。

所以论文核心不是只看 pass rate，而是看 failure attribution。

### Observability 是决策压缩器

日志多不等于可诊断。每条 run record 至少要能回答：

- patch 是否存在，来源是 submitted patch 还是 worktree fallback；
- gold file 是否真的被编辑；
- harness 哪个阶段失败：test patch / fail-before / model patch / fail-after / P2P；
- budget 是否在 repair progress 后耗尽；
- policy 是否触发 rescue / escalation / stop-loss；
- 模型是 localization fail、repair_quality fail、protocol fail，还是 task ceiling。

`forensic_summary.primary_axis` 是关键字段：`budget`、`protocol`、`localization`、`repair_quality`、`harness`、`model_behavior`、`infra`、`pass`。

### Failure Taxonomy 会改变论文结论

`BudgetFlowBudgetError` 不能因为字符串里有 `Error` 就被归为 `infra_fail`。分类顺序必须先检查 budget/cap，再检查 generic infra。否则 budget failure 会被误报成系统异常，直接污染结论。

Patch extraction 也要分层：

- submitted patch = clean protocol 证据；
- worktree fallback diff = 有 patch，但 submission/protocol 也有问题；
- harness compatibility edit 绝不能混进 submitted model patch。

## 4. BudgetFlow 论文判断

BudgetFlow 的卖点不是“永远比 all_pro 强”，而是：在固定 batch 经济预算下，progress-aware routing 能否比 budget-only / cheap-only 获得更多 clean harness resolved。

当前正向信号：

- `budgetflow_full_tight` 在部分 solvable task 上比 `all_pro` 更便宜通过。
- 在 Django-10924 等任务上，full routing 比 budget-only 更有效。
- budget-only cheap model 经常 turn 多、修不好，最后总成本反而高；这反而支持 tiered routing 的必要性。

当前负向信号：

- `all_pro` 仍是强 baseline，且很多 easy task 一把梭更便宜。
- routing 的 LOC/REP/VAL 多轮开销会吃掉 cheap model 节省。
- auto-budget cap floor、history memory、worktree missing row 还会污染结果。

下一步论文策略：

- 先修 P0 bug，再做小 batch 回归。
- 主表只收 clean rows：gold-PASS、无重复、无 missing、无 worktree crash、cost 口径明确。
- unsolvable/ceiling task 单独标注，不拿来证明 policy 差。
- `all_pro` ceiling、`budgetflow_full_*`、`budget_only_*` 必须同时保留。

## 5. Automatic Budgeting

Automatic Budgeting 是 BudgetFlow 的核心卖点之一，但必须从 clean history 学，不要靠拍脑袋 tight 值。

已有信号：

- 历史 7×15 数据能提取 task difficulty prior。
- 任务相对难度在不同策略下有稳定性。
- 008/009 已经有 memory 写入和 auto-budget v1。
- `resolved=None` 污染曾导致 underbudget 判断错误，必须清理旧 memory 并测试。

设计原则：

- cold start：用 task 特征和历史难度 prior 估 cap。
- warm start：同 task / 相似 task 用历史 actual cost 更新估计。
- continuous learning 只吃 clean rows；crash、missing、duplicate、harness-fail、ceiling task 不应直接训练预算。
- cap floor 不能太低；过小 cap 会制造假 fail，浪费 token。
- `all_pro` 不参与 budget cap；它是 ceiling/control。

## 6. Model Tier 语义

当前 active model line 必须稳定：

| Tier | backend | litellm id | provider |
|---|---|---|---|
| T1 | `tier1` | `openai/qwen3-coder-flash` | DashScope 百炼 |
| T2 | `tier2` | `openai/qwen3-coder-plus` | DashScope 百炼 |
| T3 | `tier3` | `openai/gpt-5.4` | AiCode007 |

经验：

- 低 tier 容易 no progress、weak localization、weak repair、protocol 不稳。
- 强模型适合作 ceiling/control，不应和 BudgetFlow path 混在一起解释。
- GPT-5.3 Codex 是历史 artifact，当前不可用。
- GPT-5.5 过贵，不在当前 active path。
- 模型池不稳定会污染成本、routing、paper baseline 三件事。

## 7. Agent / 工程协作经验

小模型 / sub-agent 适合搬数据、读日志、跑局部检查、写初稿；最终研究判断不能外包。

Claude Code / skills 的价值不是“装一堆技能”，而是把隐性协作规则固化到仓库：

- `CLAUDE.md`：当前 tiers、禁止事项、常用命令、运行环境风险。
- `CONTEXT.md`：统一术语，如 tier contract、action protocol、router decision、budget prior、soft cap、rescue、headroom、clean row、protocol fail、Automatic Budgeting。
- 每次实验后更新 progress/report/takeaway，不靠聊天记忆。
- 用 diagnose 思路：先建立可复现反馈回路，再猜原因。
- 重构保持小 seam：ModelCatalog、ActionProtocolAdapter、RouterDecision、BudgetAllocator；不要重写 runner。

## 8. 当前不要做什么

- 不把 dirty/duplicate/missing rows 写进论文主表。
- 不把未过 gold sanity 的 task 纳入模型结论。
- 不把 local harness 结果直接写成 official SWE-bench 结果。
- 不把内部 cost unit 写成真实 USD。
- 不在 P0 bug 未修时盲目上 5×30 / 5×50。
- 不为了扩 repo 而忽略 Django/Requests adapter gap。
- 不把 `budgetflow_equal_weight` 当独立机制；它只是 stage weight 消融。
- 不让 harness compatibility edit 进入 submitted patch。
