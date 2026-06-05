# BudgetFlow Takeaway

持续更新文件。目标：把烧掉的 token、实验成本、调研结论沉淀成可复用经验。即使 paper 最后失败，这里也要留下可复用的判断框架和工程经验。

该 commit 就 commit，该 push 就 push。关键节点必须 commit，能同步远端就同步远端。

### Phase P / Profile Fix + Manifest + Localization Diag Takeaway

1. **Narrative/code consistency is a P0 review risk.** Phase O's `solve_rarity` formula gave 5.0 to no-one-solved tasks while the report said "no-one-solved less informative." This contradiction was caught in review. Fix: rename + re-formula so both match. discriminative_rarity peaks at r=0.5; unsolved_difficulty separately handles "hard/expensive" tasks with clear ceiling-candidate labeling.

2. **Directory-scan without allowlist is a data-governance gap.** `scan_task_universe()` scanning all `data/runs/*.jsonl` means a single dirty run can silently contaminate the value matrix. Fix: explicit clean-run manifest JSON with fail-fast on missing files. The manifest also serves as documentation of what data is trusted and why.

3. **Progress signals can be dead without being absent.** LOCALIZATION has_progress=0% not because the agent is idle, but because the signal fires on file modifications only. Offline regex extraction recovered 63.3% file-activity rate from bash_digest text. Lesson: before concluding "no progress," check whether the instrumentation covers the activity type.

4. **Within-task de-biasing is a cheap partial fix for selection bias.** Raw T2 vs T3 comparison conflates tier effect with task difficulty. Grouping by (stage, task) and only comparing T2/T3 within the same task removes task-level confounding. In our data, 8/12 non-tie within-task pairs still show T3 < T2 — confirming that even within the same task, T3 turns are selected on harder phases.

5. **Two-strategy task pools make discriminative profiles useless.** With rarity ∈ {0, 1}, `discriminative_rarity` is flat at 1.0 for all tasks. A minimum of 3 strategies is needed for intermediate rarity values. This is a data constraint, not a formula problem — the tests verify the formula is correct.

### Phase Q / Runtime Trace + Diagnostic + Paid Smoke Gate Takeaway

1. **Runtime fields beat regex recovery every time.** Adding `touched_file_paths` to turn traces is a one-function change in the bash executor. It replaces a fragile offline regex diagnostic that recovers ~63% of paths from truncated bash_digest text. Capture data at generation time — don't reconstruct it later. The cost is zero: a regex on the bash command string at trace-build time.

2. **Two-pass regex avoids quoted-fragment noise.** Quoted paths with spaces (e.g., `cat 'src/foo bar.py'`) require a separate quoted-path regex before the unquoted-path pass. Without stripping quoted substrings first, the unquoted regex will match fragments like `bar.py` and produce false paths.

3. **API key gate is always step zero.** Even a $0.50 paid smoke can't run without keys. Check env vars before designing the experiment. The smoke design (2 tasks, 2-3 strategies, ≤$0.50) is ready — but blocked until keys exist.

### Phase O / Value Matrix + Progress Calibration Takeaway

1. **Selection-bias is the central challenge for progress calibration.** From 639 turns, REPAIR T2=41% vs T3=24% and VALIDATION T2=50% vs T3=19%. These negative deltas do NOT mean T3 is worse — T3 turns are selected on harder situations. Any naive plug of these rates into `expected_progress_gain` would encode the bias into the router. De-biasing requires held-out calibration or instrumental variable design.
2. **Value profiles must be ex-ante or cross-strategy, never BF-specific.** If value_i depends on "did BF solve this?", the system can reward-hack by allocating budget to tasks BF already solves. All profiles in value_matrix.py use only cross-strategy stats (avg_cost, resolve_rate, solve_rarity) computed across ALL strategies in the JSONL universe.
3. **The `or` pattern fails for empty collections as defaults.** `strategies_seen = strategies or {"s1", "s2"}` silently replaces `set()` with the default because empty set is falsy. Use `x if x is not None else default`. This bug affected 4 tests in test_value_matrix.py and was caught by the test suite.
4. **Different value profiles rank tasks differently.** difficulty vs solve_rarity Spearman ρ=0.44 — only moderate. This means the choice of value model matters: a budget allocator using difficulty would route differently than one using solve_rarity. The paper must justify whichever profile it uses, or show robustness across profiles.
5. **LOCALIZATION progress signal is dead.** 215 turns across T2+T3 with 0% progress rate. This is a data-quality bug: the code that checks whether the touched file is in the gold patch is not populating `has_progress` for localization turns. This must be fixed before any paid run that tests stage-aware routing.

### Phase N / Value Rescore Takeaway

1. **BF 仍然不赢 BO。** 030（10 tasks）和 031（5 tasks）在 equal-value 和 heuristic 两种 profile 下，BO 和 BF 解决的 task 完全相同，但 BF 更贵。Routing overhead ~28-42% 无 pass 回报。
2. **Value profile 不改变相对排序当 task set 相同时。** 如果两种策略解决同一批 task，value profile 只会等比例放大 val/$ 的绝对数值，不会改变谁赢。Value profile 有意义的前提是策略解决了**不同**的 task（尤其是不同 value 的 task）。
3. **Second-claim 证据是 WEAK。** Progress table 未 calibrate（tier2 score 恒为 0.0），`has_progress` < 30%。公式 `stage_weight × expected_progress_gain / marginal_cost` 在代码中存在但以 zero_calibration 运行。BF 的 stage-aware routing 是方向性的（REPAIR 更多 T3），但不能证明 cost efficiency。
4. **下一轮 paid run 前必须做两件事：** (a) 设计 task value proxy，让 task pool 有异质 value；(b) calibrate progress table，从 public SWE-bench trajectory replay 或 held-out calibration split。缺任一，paid run 只会重复 BO ≥ BF 的结论。
5. **离线 rescore 工具是正确的基础设施。** `value_rescore.py` 很小（~220 lines），32 tests，支持 equal/heuristic/custom profile。等 value proxy 定下来，改一行 `--profile custom --custom-map values.json` 就能重算。

## 0. 最新关键判断（2026-06-05）

### North Star / Value Proposition Takeaway

1. **BudgetFlow 的核心价值是 shared budget governance，不是单点 smart routing。** 一个组织里的工程、文职、研究、运营任务共享同一预算池；系统应按任务价值、难度、成功概率和预算压力分配模型能力，而不是按人或团队硬切额度。
2. **论文指标必须转向 `resolved value per dollar`。** 030/031 默认 `value_i=1`，所以只能说明 equal-value setting 下的成本/通过率；新主张必须衡量同一 hard budget 下解决了多少 verified value。
3. **BudgetMemory 应升级为 value memory。** 它要学习的不只是 task cost，还包括 task value、difficulty、cap sufficiency、model success、failure axis 和 escalation 的 marginal value。
4. **冷启动与 warm-up 要分开写。** Cold start 允许企业通过 easy API 注入 priority/value hints，也可用 heuristic 估 value；warm-up 依赖 verified outcomes 持续学习，而不是 hard-code 每个任务的 value。
5. **030/031 没有失败，只是回答了旧问题。** 它们仍证明了 fallback safety、true LOO cascade、checker hygiene 和 BudgetMemory source discipline；但不能直接支撑最新 Value Proposition。

### AutoResearch Takeaway

1. **AutoResearch 的产品目标是减少 owner 人肉搬运，而不是替 owner 做重大决策。** Codex 仍是 review front-end；Worker 可以改代码/测试/文档，但重大事项必须暂停给 owner/Codex gate。
2. **非侵入式路线已经跑通原型。** 034 coordinator、035 CLI、036 fake-worker smoke、038 thin API worker、039 goal loop 证明 workflow artifact 可以落盘、恢复、审计。
3. **`claude -p` 不是合适的小任务 Worker adapter。** 037 证明 Claude Code session overhead 会吞掉小额预算；thin API worker 才适合 low-cost smoke。
4. **Phase K 已实现真正的闭环。** goal-loop 自动化了 issue 遍历 → worker 执行 → 确定性 review → mark-complete/retry/pause → owner_decision → 报告 → commit/push。Exit code 0/1/2 让调用方（CI/CD 或 owner shell）能判断下一步动作。
5. **owner_decision.md 是合适的 Codex 前端。** 它不是复杂的 UI，就是结构化 markdown。Owner 读到 "Why Paused" → "Recommended Decision" → "Resume Command"，一分钟内决定 approve/reject/retry。简单，但有效。
6. **所有 Worker 交付必须落盘 MD。** 口头 summary 只能辅助；Codex review 的事实源应是 state.json、worker_output.md、worker_metadata.json、codex_review.md、报告和测试输出。
7. **goal-loop exit code 设计要能区分三种结果。** 0=all complete（可自动 proceed），2=owner review required（有人读 owner_decision.md 后 approve），1=actual failure（需要 debug）。这个三态设计比 pass/fail 更适合半自动流程。
8. **Safe commit/push 需要多层 gate。** 至少需要：`git diff --check`（检测冲突标记）、secret scan（API key/token 模式）、可选的 pytest。只 stage 特定目录（`.autoresearch/`、`docs/`），不要 `git add -A`。
9. **`.gitignore` 的 trailing slash 陷阱。** `dir/` 只匹配目录，不匹配同名 symlink。如果一个路径既可能是目录也可能是 symlink，需要在 `.gitignore` 里写两行（`dir/` 和 `dir`）。
10. **goal-loop 测试不能用预创建 metadata 的方式测 WARN。** 因为 goal-loop 会 re-run worker 并覆盖。正确做法：写一个 custom worker command 产出 WARN-triggering 输出（real API profile + marker_appended）。
11. **Dispatch wrapper 比 per-issue worker-cmd 更轻量。** 不需要修改 goal-loop 架构，只需在 prompt 里加 `<!-- WORKER:fake -->` 或 `<!-- WORKER:api -->` HTML comment marker。一个 worker-cmd 就能同时支持 fake 和 real API profile。
12. **Real API smoke 必须考虑模型输出截断。** deepseek-v4-flash max_tokens=2048 时，长篇 prompt + 大段 doc 会导致输出在 marker 前截断。修复：缩短 prompt + 引用真正会被 worker 发送的 docs。

### 031 / True LOO / BudgetMemory Cascade Takeaway

1. **True LOO BudgetMemory cascade works.** 5 held-out tasks with 030 JSONL as training (LOO excluded) → all held-out hit `repo_median`, 0 `exact_task` leakage. Gate verified via `--budget-memory-dry-run` before API calls.
2. **BudgetFlow still not beating BudgetOnly.** 031: both 4/5 PASS, bf-T $0.70 vs bo-T $0.49. Same pattern as 030 (7/10 tied, bf more expensive). On easy tasks, routing overhead adds cost without pass gain.
3. **Auto-budget `history_exact` is NOT leakage.** It comes from hardcoded `_HISTORICAL_PRIOR` (separate system from BudgetMemory). `budget_prior_source` and `budget_memory_budget_source` are different fields with different semantics.
4. **sympy-18057 is a persistent budget_fail.** Failed for both strategies in 030 and 031. Auto-budget cap $0.12 insufficient — but task-specific, not cascade bug.
5. **Gate/dry-run pipeline works without API.** `--budget-memory-dry-run` + `--budget-memory-exclude-ids` validates LOO source distribution offline.

### 032 / Runner Path Audit Takeaway

1. **Repo cache at `paper1/data/repo_cache/` is a HIGH blocker.** Full git clones inside the paper1 repo → NFS I/O lag on every fetch, risk of accidental commit. Must move to `/tmp/budgetflow-runtime/repos/`.
2. **Trace scratch at `paper1/data/runs/trace_*/` should move to `/tmp`.** 031 traces = 1.3MB (10 dirs). At 10x5 scale = ~50MB of per-turn churn in the results directory. Trajectory files are audit trail, should be copied to results on completion.
3. **`external/mini-swe-agent` symlink to `/Lishun` is fragile.** Breaks if archive is removed. Should be proper git submodule or pip-installed.
4. **`budget_prior_source` ≠ `budget_memory_budget_source`.** 030 confirmed: auto-budget was OFF (field MISSING), BudgetMemory hit `global_fallback` (empty training). 031 confirmed: auto-budget = `history_exact` (hardcoded prior), BudgetMemory = `repo_median` (LOO cascade correct). Conflating these two fields would produce wrong conclusions.
5. **Current lock design is correct in scope** (fcntl on worktree add/remove only) but does NOT cover repo cache clone/fetch. When jobs>1 with same-repo tasks, concurrent `_ensure_main_repo()` calls could race.

### 033 / Runtime-Root Refactor Takeaway

1. **Moving high-churn artifacts to /tmp is low-risk, high-reward.** Four path categories (worktrees, repos, locks, traces) moved from NFS/repo paths to `/tmp/budgetflow-runtime`. Zero experiment semantic changes. Persistent evidence stays in `paper1/data/runs`.
2. **NFS fail-fast guard prevents recurrence.** `is_nfs_or_banned()` catches any `/Lishun` path at startup. Must explicitly pass `--allow-nfs-runtime` to bypass. This prevents the NLM fcntl deadlock that plagued earlier experiments.
3. **Lock scope unchanged — do not expand.** The fcntl lock protects only git worktree add/remove. Agent repair is intentionally un-locked. Expanding lock scope to cover agent execution would create false contention.
4. **jobs>1 is safe now.** With locks on local `/tmp` fs (no NFS NLM), worktrees on local fs, and repo caches on local fs, multi-process execution should not hit filesystem deadlocks.
5. **Two symlinks remain as tech debt.** `external/mini-swe-agent` and `paper1/data/swebench_lite_export` are still symlinks to `/Lishun/_archive/`. The new resolution functions (`resolve_mini_swe_src()`, `resolve_swebench_export_dir()`) support env var overrides but the default fallback reads from NFS.

### 034 / AutoResearch Coordinator Takeaway

1. **Coordinator is a state machine, not an agent.** It manages workflow dirs, writes prompts, enforces pause conditions, and tracks retries. It does not call the Worker, make API calls, or auto-commit. Those are external integrations.
2. **On-disk-first design.** Every state transition writes to disk immediately. Workflows survive crashes — reload from `state.json`.
3. **Pause conditions are explicit flags.** The coordinator doesn't guess — the caller supplies flags like `paid_experiment_scale=(3,10)` or `northstar_change=True`. This keeps the coordinator non-invasive.
4. **Manual mode bridges the gap.** When no Worker CLI exists, `manual_mode=True` prints the prompt path and output path so the operator can execute manually. This removes the copy-paste loop without requiring full automation.
5. **Auto commit/push intentionally deferred.** The coordinator writes to `.autoresearch/` but does not touch git. Auto-commit should only be enabled after Codex gate approval is proven reliable in practice.

### 030 / BudgetMemory / 决策纪律 Takeaway

1. **`harness_resolved` 是唯一 PASS/FAIL 主口径。** `exit_reason` 只是过程解释。030 里 `rescue_timeout_gold_edited` 5 个中 4 个是 PASS；把它们按 exit_reason 全算 FAIL，会把 `bf_tight` 从 7/10 错报成 5/10，直接扭曲论文结论。

2. **030 是 cold-start fallback test，不是 LOO generalization。** 这次排除了全部 10 个已知 task，训练数据变成 0 records，BudgetMemory 全部走 `global_fallback`。因此它只能证明 fallback safety，不证明 repo_median 泛化，也不证明 BudgetFlow 优势。

3. **BudgetFlow > BudgetOnly 仍未稳定成立。** 030 中双方 7/10 打平，但 BudgetFlow 更贵。此前 023/024/029 有正向信号，但样本小、方差高、部分 run 语义被 BudgetMemory source bug 污染。当前主张必须收窄为：机制在逐步变干净，但优势还需要真正 LOO + repeats 验证。

4. **BudgetMemory 的核心风险是 reward hacking / exact-task leakage。** warm-start exact_task 能跑通不等于泛化。论文级证据必须区分 exact_task、repo_median、global_fallback；真正 LOO 要 held-out 当前 tasks，同时保留其它历史 tasks，避免把训练集排空。

5. **worker agent 不能决定研究路线。** worker 可以跑实验、写报告、修 bug、交付证据，但“下一步推荐”只能作为输入材料。主 agent 必须用 JSONL/checker/heartbeat/log 自己判断，否则会被错误报告和局部指标带偏。

6. **当前最佳下一步不是扩大规模。** 先重跑一个真正的 5x2 LOO，验收点是 `repo_median` source 命中、0 exact_task leakage、checker clean、pass/cost 口径正确。机制过关后再做 repeats 或 10-task 方差实验。

7. **工作目录迁移是工程纪律，不是实验变量。** 交互开发使用 `/root/.dev/AgentOS`；旧 `/Lishun` 路径只作为持久数据来源。Git 慢、status 卡、NFS 小文件 I/O 不能再混入 BudgetFlow 实验结论。

### 012 核心 Takeaway

1. **Worktree "missing but locked" 是真实崩溃模式，本地测试抓不到。** 010/011 的 3 层清理 + contract 测试通过了，但并行实验跑到 row 22 就 crash。"missing but locked"（目录已删，`.git/worktrees/<name>` 元数据还在）只在并行 worktree 场景出现。修复必须同时在 `_remove_worktree`（删除元数据 dir）和 `_worktree_add`（add 失败后 unlock+prune+retry）两处做防御。

2. **BudgetFlow Full (tight + loose) 在这个 5-task pool 上均 100% resolve。** Tight $0.5259 total, Loose $0.5977 total。两者都 10/10 PASS。验证 routing 方法本身不制造假 fail。

3. **budget_only (without tiered routing) 丢失 1-2 tasks。** Tight 3/5 ($1.48), Loose 4/5 ($0.97)。更差且更贵。原因：只用 T2 在 hard task 上需要更多 turns，总成本反而高。这支持 BudgetFlow 的 tiered routing 价值主张。

4. **all_pro 仍然是这个 easy pool 上最便宜的解决方式（$0.47）。** GPT-5.4 5 turns 直接解决 sympy-14774、4 turns 解决 sympy-18057。但 BudgetFlow 的额外开销（routing overhead ~12%）在 easy task 上不显优势，在 hard task 上有价值。

5. **min_cap=$0.10 比 $0.05 更合理。** 实测 easy task cost 范围 $0.05-$0.16。$0.05 对 T3 场景不够（all_pro 单个 14774 就 $0.05）。$0.10 是安全的 floor。

6. **Checkpoint 韧性很重要。** `batch_cap:null` 在 JSON 中合法，但 `from_dict` 不处理 None 会导致 resume 崩溃。all_pro 的 null cap 是合法语义（uncapped），必须序列化/反序列化支持。

7. **Auto-budget memory 从 5→10 task 冷启动能力增强，但仍小。** kNN 在老 task 上 exact match，新 task 上靠 bucket fallback。需要更多 clean rows 才能真正启用 continuous learning。

8. **turn_trace_count=0 是严重缺陷。** 所有 25 rows 缺 turn traces。只能做 outcome 诊断，不能做 turn-level 细分析。下一轮必须开 `--trace-turns`。

### 竞争模型与论文定位

Liquid LFM2.5、Ling-2.6-flash、OpenSquilla、Hermes/OpenClaw 会影响 paper 的表述方式，但不会直接打掉 BudgetFlow。

分层判断：

- `Liquid LFM2.5`、`Ling-2.6-flash` 主要是 **backend / model-intrinsic efficiency**：模型本身更便宜、更短、更快。它们是 T1/T2 候选 backend，不是 BudgetFlow 的直接替代。
- `OpenSquilla`、`Hermes/OpenClaw` 是 **runtime / orchestration competitor**：它们也讲 routing、memory、skills、cost tracking，是真竞争。
- 这些系统的 marketing claim 不能直接当事实；只把官方自述当定位参考，性能结论必须自己跑。

BudgetFlow 的 claim 必须收窄：

- 不说"通用 token efficiency 最强"。
- 不说"最强模型路由器"。
- 主张改成：**在固定经济预算下，BudgetFlow 用 workflow/progress-aware routing 提升 agentic code-repair 的 clean resolved per dollar**。
- 关键差异是 fixed budget、batch governor、verified repair outcome、failure attribution、auto-budget learning，而不是单次调用更省 token。
- **2026-06-05 更新：** 以上竞争定位写于 paper pivot 前。当前 First Claim 已转向 value-driven shared budget governance（见 §0 North Star Takeaway）。本节保留为竞争格局历史参考，第二 claim 的 routing/cost 主张仍是机制层的有效假设。

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

## 1. 当前硬规则

### HPC / NFS / 容器

当前实验运行在容器环境里。HPC/容器的价值是 CPU 并行空间大；GPU 暂时不是本论文实验关键资源。

`/Lishun` 是 NFS：持久，但小文件慢。`/tmp` 是本机临时盘：快，但不持久。实验前必须设置：

```bash
export TMPDIR=/tmp
export BUDGETFLOW_RUNTIME_ROOT=/tmp/budgetflow-runtime
```

规则：

- 临时构建、pytest tmp、解压、worktree、repo cache、lock、trace scratch 走 `/tmp/budgetflow-runtime`。
- JSONL、checkpoint、report、final evidence 仍落 `paper1/data/runs` 或 `paper1/docs/reports`。
- pip cache 不得硬编码 `/Lishun`；使用环境变量或 runtime/path resolver。
- 避免在 `/Lishun` 上做大范围 `find`、`du`、全仓库扫描；优先精确路径、`rg --files`、`find -maxdepth`。
- `exit 137` 通常是外部 `SIGKILL`，先查 cgroup/OOM/session log，再判断是不是代码问题。
- 长实验不要依赖交互式 shell 生命周期；必须支持 `--resume`、checkpoint、run-series，必要时用 tmux/nohup。
- `/root/.dev/AgentOS` 是当前开发目录；旧 `/Lishun/.../AgentOS` 只当历史来源，不作为交互开发主目录。

### 并行与 Resume

- 单个 policy 内部顺序跑 task，因为共享 batch-level `BudgetGovernor`。
- 不同 policy 可以并行；`run_mini_swe_compare --jobs N` 用 git worktree 做隔离。
- 并行度先保守，再扩。provider、worktree、harness 任一不稳，都不要盲目加 `--jobs`。
- resume 后必须检查重复 `(instance_id, strategy)`；重复行不能进论文表。
- 如果出现重复 JSONL、checkpoint 不一致、missing row，先判定 runner/observability bug，不要解释成模型或 BudgetFlow 失败。

### Worktree 崩溃模式经验（012）

"missing but locked" 是并行 worktree 场景的独特崩溃模式：

- **触发条件：** worktree 目录被删（rmtree/手动），但 `.git/worktrees/<name>` 元数据残留。`git worktree add` 看到元数据认为 worktree 存在，尝试 lock 时发现目录不存在，报 "missing but locked"。
- **修复层级：** 必须在 add 路径（`_worktree_add` stderr 解析 + retry）和 remove 路径（`_remove_worktree` 显式删除 meta_dir）两处防御。
- **教训：** lab 单线程测试抓不到这个 bug。只有并行 run（多个 job 共享同一个 main repo）才会暴露。

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

## 2. 当前实验判断（012 后，旧 equal-value 口径）

本节保留为历史机制判断。012 证明 routing 修复和 runner 稳定性；但它默认任务 value 相等，不能直接作为 2026-06-05 之后 value-driven paper claim 的最终证据。

已有 clean 25 rows (012) + 56 noisy rows (008/009) + 35 historical rows (7x15)。012 数据可信，可做初步分析。

当前判断：

- `all_pro` 是 uncapped GPT-5.4 ceiling/control，不属于 BudgetFlow，不应被 Automatic Budgeting cap 限制。
- `budgetflow_full_*` 两档均在 5-task easy pool 上 100% resolve，routing 方法已验证有效。
- `budget_only_*` 无 tiered routing 时丢失 1-2 tasks 且总成本更高。这支持 BudgetFlow 核心主张。
- 在 easy task 上 `all_pro` 最便宜（$0.47 for 5 tasks）。BudgetFlow 的 routing overhead 在 easy task 上不划算，但在 hard task 上提供 protection。
- Worktree crash 已闭环：25/25 rows clean, 0 crash。修复覆盖 add 和 remove 两条路径。
- GPT-5.4 有非确定性，同一 task 单次 PASS/FAIL 不能当稳定天花板。
- `django-12113`、`sympy-21612` 目前像 ceiling/unsolvable task，不适合证明 budget policy 差。

当前 P0：

- **开启 turn traces**：下一轮必须加 `--trace-turns`。
- **构建 consistency checker**：checkpoint ↔ JSONL ↔ summary.log。
- **扩 task pool**：从 5 → 10+ Gold-PASS tasks。
- **T1 启用评估**：测试 qwen3-coder-flash 在 BudgetFlow 中的表现。

已解决的 P0：

- ✅ Worktree crash 修复并验证（012）
- ✅ Checkpoint `batch_cap:null` 修复（012）
- ✅ Auto-budget 记忆清理并扩充至 10 task（012）
- ✅ `min_cap` $0.05→$0.10 校准（012）
- ✅ 真实 API 价格校准并验证（010/011）
- ✅ Cost display observability（011）
- ✅ 回归测试 35/35 pass（012）

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

### 012 新增：Harness Pass 证据链

local harness 的 forensic_summary 提供完整的 pass/fail 证据链：

```
test_patch=ok → fail_before=fail → model_patch=ok → fail_after=pass → pass_to_pass=pass
```

22/25 PASS 全部满足上述链。无 P2P false pass。3 FAIL 的证据也完整：
- 2 repair_fail：fail_after=fail（修了 gold file 但测试不过）
- 1 budget_fail：cap 耗尽

这个证据链应该是后续所有实验的验收标准。

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

BudgetFlow 的卖点不是"永远比 all_pro 强"，而是：在固定 batch 经济预算下，progress-aware routing 能否比 budget-only / cheap-only 获得更多 clean harness resolved。

当前正向信号（012 强化）：

- `budgetflow_full_*` 在 5-task easy pool 上 100% resolve（10/10），routing 方法验证有效。
- `budget_only_*` 丢失 1-2 tasks 且总成本更高：tight 多花了 $1.48 只拿到 3/5，loose 多花了 $0.97 拿到 4/5。
- BudgetFlow Full tight 总成本 $0.53，Full loose $0.60，两者都比 budget_only 便宜且更强。
- Worktree crash 闭环验证，runner 稳定性达到可生产级别。

当前负向信号：

- `all_pro` 仍是强 baseline，easy task 上一把梭更便宜（$0.47 for 5 tasks）。
- BudgetFlow routing overhead ~12% 在 easy task 上不提供经济优势。
- Turn traces 缺失，无法做 turn-level attribution。
- Task pool 只有 5 easy tasks，hard task 上的相对优势未验证。

下一步论文策略：

- 开启 turn traces，构建 consistency checker。
- 扩 task pool 到 10+，覆盖更多难度级别。
- 主表只收 clean rows：gold-PASS、无重复、无 missing、无 worktree crash、cost 口径明确。
- unsolvable/ceiling task 单独标注，不拿来证明 policy 差。
- `all_pro` ceiling、`budgetflow_full_*`、`budget_only_*` 必须同时保留。

## 5. Automatic Budgeting

Automatic Budgeting 是 BudgetFlow 的核心卖点之一，但必须从 clean history 学，不要靠拍脑袋 tight 值。

012 进展：

- `_HISTORICAL_PRIOR` 从 5 → 10 task，覆盖当前 active 的 6 task（含 django-10924）。
- `min_cap` $0.05→$0.10，基于 real-USD 实测。
- kNN memory 在 exact match task 上可靠（budget_prior_source=memory_exact, confidence=high）。
- 新 task 仍靠 bucket fallback + repo floor。

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
- T1 仍 marked skipped，BudgetFlow 的低 tier 优势未经实验证明。

## 7. Agent / 工程协作经验

小模型 / sub-agent 适合搬数据、读日志、跑局部检查、写初稿；最终研究判断不能外包。

Claude Code / skills 的价值不是"装一堆技能"，而是把隐性协作规则固化到仓库：

- `CLAUDE.md`：当前 tiers、禁止事项、常用命令、运行环境风险。
- `CONTEXT.md`：统一术语，如 tier contract、action protocol、router decision、budget prior、soft cap、rescue、headroom、clean row、protocol fail、Automatic Budgeting。
- 每次实验后更新 progress/report/takeaway，不靠聊天记忆。
- 用 diagnose 思路：先建立可复现反馈回路，再猜原因。
- 重构保持小 seam：ModelCatalog、ActionProtocolAdapter、RouterDecision、BudgetAllocator；不要重写 runner。

### 012 工程经验

- **Worktree bug 必须在并行场景测试。** 单线程 lab test 抓不到 "missing but locked"。下次改 worktree 代码，必须跑 `--jobs > 1` 的集成测试。
- **Checkpoint schema 要向后兼容。** `batch_cap:null` 是合法语义（uncapped），新增 nullable 字段时必须确保 `from_dict` 处理 None。JSON 不区分 null 和 missing。
- **Auto-budget prior 数据直接嵌入代码即可。** 10 task prior 很小，不需要外部文件。等历史数据 > 50 task 再考虑分离。
- **回归测试从 31 → 35 是正常的增量增长。** 每次修一个 bug 加对应测试，不为了数字而写测试。

## 8. 当前不要做什么

- 不把 dirty/duplicate/missing rows 写进论文主表。
- 不把未过 gold sanity 的 task 纳入模型结论。
- 不把 local harness 结果直接写成 official SWE-bench 结果。
- 不把内部 cost unit 写成真实 USD。
- 不在 turn traces 缺失时做 turn-level 结论。
- 不在 runner 不稳定时盲目上 5×30 / 5×50。
- 不为了扩 repo 而忽略 Django/Requests adapter gap。
- 不把 `budgetflow_equal_weight` 当独立机制；它只是 stage weight 消融。
- 不让 harness compatibility edit 进入 submitted patch。
- 不在单个 5-task easy pool 上过度推广结论。
