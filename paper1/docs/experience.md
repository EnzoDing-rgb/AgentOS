# BudgetFlow Experience Notes

持续更新文件。目标：把烧掉的 token、实验成本、调研结论沉淀成可复用经验。即使 paper 最后失败，这里也要留下有价值的判断框架和工程经验。

## 1. 总结结论

### 我们看到了什么现象

昨夜和今天的实验里，BudgetFlow 在若干 SWE-style repair 任务上表现不好。结果表里出现了不少失败：`repair_fail`、`extract_fail`、`infra_fail`、`budget_fail` 等。

### 发现了什么问题

原来的结果表只能告诉我们“失败了”，不能告诉我们“为什么失败”。很多失败被压成粗标签：

- `repair_fail`：只说明 patch 存在、gold file 被编辑过，但最终没过测试。
- `extract_fail`：可能是模型没提交、协议问题、格式问题、stagnation。
- `infra_fail`：可能混入了 budget exhaustion。

这些标签不够支持 paper 决策。

### 如何解决的

我们加了 `forensic_summary`，把每条 run record 压缩成高密度诊断摘要：

- `primary_axis`
- `failure_chain`
- patch 状态
- harness 阶段状态
- budget 状态
- policy/rescue 线索
- confidence
- missing evidence

同时修复了 `BudgetFlowBudgetError` 被误判为 `infra_fail` 的问题。

### 得出的结论

现在的核心任务是诊断 BudgetFlow 失败原因，而不是扩大实验规模。3x3 diagnostic run 是当前最合理的下一步。

## 2. Paper 层面的经验

### 我们看到了什么现象

BudgetFlow 的 pass rate 没有稳定表现出优势。昨夜的结果让人怀疑系统本身存在问题。

### 发现了什么问题

pass rate 表不足以支撑论文判断。一个失败可能来自：

- routing 策略错误；
- budget cap 太紧；
- rescue 开得太晚；
- 模型能力不够；
- 任务本身太难；
- patch extraction 协议失败；
- local harness 和 official SWE-bench 不一致。

如果只看 pass/fail，就会把这些问题混在一起。

### 如何解决的

我们把实验设计改成小而清晰的 3x3：

Policies:

- `budget_only_tight`
- `budgetflow_full_tight`
- `budgetflow_auto_v2_tight`

Tasks:

- `sympy__sympy-13480`：easy/control
- `sympy__sympy-20212`：medium
- `sympy__sympy-16988`：hard sentinel

### 得出的结论

paper 当前最重要的证据不是“大表格”，而是小矩阵里的 failure attribution。先把失败拆清楚，再决定是否 scale。

## 3. Observability 层面的经验

### 我们看到了什么现象

项目里已经有很多日志和 trace：

- JSONL rows
- summary logs
- run logs
- driver logs
- trace dirs
- `steps.jsonl`
- `trajectory.json`
- `submitted.patch`
- `worktree.patch`

### 发现了什么问题

日志很多，但诊断密度不够。研究者看完表格后仍然不知道：

- patch 从哪里来；
- gold file 是否真的被编辑；
- harness 哪个阶段失败；
- budget 是否在 repair progress 后耗尽；
- policy 是否触发 rescue；
- 模型是否 stagnation；
- 还缺什么证据。

### 如何解决的

我们没有继续堆 raw trace，而是加了 forensic attribution layer。

`forensic_summary.primary_axis` 直接给出主因候选：

- `budget`
- `protocol`
- `localization`
- `repair_quality`
- `harness`
- `model_behavior`
- `infra`
- `pass`

### 得出的结论

好的 observability 不是日志越多越好，而是每条实验记录都能帮助研究者做下一步决策。

## 4. Failure Taxonomy 层面的经验

### 我们看到了什么现象

一个具体样例里：

- `exit_status=BudgetFlowBudgetError`
- `exit_reason=budget_exhausted`
- `patch_extracted=true`
- `patch_source=worktree`
- `agent_gold_edited=true`
- `agent_submitted=false`
- harness detail 显示 `model_patch=ok; fail_after=fail`

原分类器可能给出 `infra_fail`。

### 发现了什么问题

分类器先检查 generic `"error" in status.lower()`，再检查 budget reason。`BudgetFlowBudgetError` 因为包含 `Error`，会被提前打成 infra。

### 如何解决的

分类器现在先检查 budget/cap，再检查 infra。

新增测试覆盖：

- `BudgetFlowBudgetError + budget_exhausted` 应该是 `budget_fail`。
- forensic summary 应该记录 `budget.exhausted_after_patch=true`。

### 得出的结论

失败分类顺序会影响 paper 结论。taxonomy 不是小工具，它直接决定研究解释。

## 5. 模型能力层面的经验

### 我们看到了什么现象

实验中出现过多种模型路径：Qwen Flash、Qwen Coder、Qwen Max、GPT-5.3 Codex、GPT-5.4、GPT-5.5。

低 tier 模型容易出现：

- no progress；
- weak localization；
- weak repair；
- patch protocol 不稳定。

强模型更适合做 ceiling/control。

### 发现了什么问题

模型池太复杂会污染 BudgetFlow 结论。旧代码里混着 T1/T2/T3/T4/T5，且 GPT-5.5 曾作为 ceiling probe 存在 active code path。

这样会带来几个问题：

- 成本解释混乱；
- routing tier 解释混乱；
- paper 里 baseline 和 system path 混在一起；
- GPT-5.5 过贵，不适合作为当前正常路径。

### 如何解决的

当前 active model line 收敛到三档：

- T1 = `qwen3-coder-flash`
- T2 = `qwen3-coder-plus`
- T3 = `GPT-5.4`

GPT-5.3 Codex 已经不再暴露接口，只能作为历史 artifact。GPT-5.5 从 active code path 移除。历史 artifact 可以保留，但当前实验不路由到 GPT-5.5。

### 得出的结论

BudgetFlow 需要一个清晰、稳定、可解释的 tier line。否则失败时无法判断是 policy 问题还是 model pool 设计问题。

## 6. GPT-5.3 Codex、GPT-5.4 与 GPT-5.5 的经验

### 我们看到了什么现象

GPT-5.3 Codex 曾经是当前项目里的 practical anchor，但现在已经不可用。GPT-5.4 是新的 T3 anchor。GPT-5.5 有历史 ceiling probe 价值，但成本高，不适合当前常规实验路径。

### 发现了什么问题

如果把 GPT-5.5 留在 active path，系统会变得贵，且 paper 解释会变复杂。BudgetFlow 的目标是预算感知，不应该依赖一个过贵 ceiling 模型来撑结果。

### 如何解决的

当前统一写法：**GPT-5.4**。

当前 active tier：

- GPT-5.4 = T3。
- GPT-5.3 Codex = 历史不可用模型，只能解释旧 artifact。
- GPT-5.5 = 移出当前 code path。

### 得出的结论

强模型最有价值的用途是诊断和控制变量。GPT-5.4 用来判断任务/协议/路由是否有上界可达性，但它必须先通过 action protocol/trace gate。GPT-5.5 暂时不参与当前推理链。

## 7. 小模型/小 agent 的经验

### 我们看到了什么现象

小模型 agent 能快速搬运信息：找文件、读日志、总结 artifact、列 schema。

### 发现了什么问题

小模型不适合做最终研究判断。它可能遗漏上下文，也可能机械重复结论。

### 如何解决的

小模型只负责：

- 搬数据；
- 搬信息；
- 搬证据；
- 做局部检索。

主判断由主 agent 完成。

### 得出的结论

小模型是研究助理，不是 PI。证据可以外包，判断不能外包。

## 8. Harness 层面的经验

### 我们看到了什么现象

项目使用 local worktree harness 快速跑 SWE-style repair。它检查：

- test patch；
- fail-before；
- model patch；
- fail-after；
- pass-to-pass。

### 发现了什么问题

local harness 的结果不能直接当 official SWE-bench leaderboard 结果。official SWE-bench 使用 Docker/container harness 和标准 prediction JSONL。

### 如何解决的

项目保留 official prediction export：

- `instance_id`
- `model_name_or_path`
- `model_patch`

local harness 用于快速开发和诊断，official export 用于后续正式验证。

### 得出的结论

local harness 是开发工具，official SWE-bench 是论文级验证工具。两者要分开解释。

## 9. Patch Extraction 层面的经验

### 我们看到了什么现象

patch 有两个来源：

- model submission；
- worktree fallback diff。

### 发现了什么问题

worktree fallback 能救回一些 patch，但它和 clean submission 不是同一种证据。一个任务如果靠 worktree fallback 才有 patch，说明 protocol/submission 层面也有信号。

### 如何解决的

forensic summary 记录：

- `patch.extracted`
- `patch.source`
- `patch.gold_edited`
- `patch.submitted`
- `patch.attempted_submit`

### 得出的结论

patch 是否存在不够，patch 从哪里来更重要。

## 10. Automatic Budgeting 的经验

### 我们看到了什么现象

代码里已有预算机制：

- frozen/protocol caps；
- tight/loose；
- `tight_scale` / `loose_scale`；
- `soft_budget` / `max_overrun`；
- `per_task_cap`；
- budget pressure；
- auto-v2 rescue/stop-loss。

### 发现了什么问题

这些机制还没有形成完整 Automatic Budgeting。当前更像 budget parameterization + guards + routing pressure。

### 如何解决的

先跑 forensic 3x3。根据 `primary_axis` 决定是否立刻实现 Automatic Budgeting：

- 如果失败集中在 `budget`：立即做 Automatic Budgeting。
- 如果失败集中在 `protocol`：先修 submission/patch extraction。
- 如果失败集中在 `localization`：先修早期升级。
- 如果失败集中在 `repair_quality`：先看 GPT-5.3 Codex 是否来得太晚。

### 得出的结论

Automatic Budgeting 很重要，但应该由证据触发。现在先跑 3x3，再决定它是不是下一刀。

## 11. 当前已完成的工程改动

### 我们看到了什么现象

旧代码路径里模型 tier 混乱，failure taxonomy 粗，table next_action 机械。

### 发现了什么问题

这些问题会直接影响下一轮实验的解释质量。

### 如何解决的

已完成：

- 加 `forensic_summary`。
- 修 `BudgetFlowBudgetError` 分类。
- 表格新增 `forensic_axes`。
- `next_action` 改成 forensic axis 优先。
- active model pool 改成 T1/T2/T3。
- GPT-5.5 active path 清除。
- GPT-5.4 作为 T3。
- `3x3` preset 接入 compare runner。
- focused tests 通过：37 passed。

### 得出的结论

现在的代码更适合做诊断实验。下一轮 3x3 的结果会比昨夜结果更有解释价值。

## 12. 面试级 takeaway

### 12.1 研究系统先死于解释不清

实验失败不可怕。可怕的是失败后不知道为什么。这个项目最重要的进展，是把“失败了”变成“失败在哪个轴上”。

### 12.2 好的 observability 是决策压缩器

日志不是目的。诊断摘要才是目的。`forensic_summary` 的价值在于让每条实验记录都能指导下一步。

### 12.3 强模型是诊断工具

GPT-5.4 不只是更强模型，也是 control/ceiling。它帮助判断任务能不能被强模型解决，以及 BudgetFlow 是否把强模型用在了正确时机。前提是先修好 action protocol，否则强模型信号会被 parser failure 污染。

### 12.4 预算路由需要稳定 tier line

如果模型池本身不断变化，BudgetFlow 的实验结论就会不稳定。先固定 T1/T2/T3，再判断 policy。

### 12.5 自动预算要靠证据驱动

Automatic Budgeting 是重要功能，但实现时机要看失败轴。先诊断，再动大模块。

## 13. 后续更新规则

每次有新实验，按这个格式追加：

1. 我们看到了什么现象。
2. 发现了什么问题。
3. 如何解决的。
4. 得出了什么结论和经验。

不要写空话。不要写绕话。直接写证据和判断。

## 14. Agent Skills / Claude Code 实践经验

### 我们看到了什么现象

Matt Pocock Skills 系统里有几条实践对本项目有价值：

- 用 `CLAUDE.md` / `CONTEXT.md` 固化项目约束和领域词汇。
- 用 `/diagnose` 思路先建反馈回路，再猜原因。
- 用 `/handoff` 思路把会话状态压缩成交接文件。
- 用小而可组合的能力单元，不让一个流程黑箱接管全部开发。
- 周期性做架构审计，防止 agent 加速代码熵增。

### 发现了什么问题

这些实践不能直接替代 BudgetFlow 的工程实现。它们不是新算法，也不是 Automatic Budgeting。

但它们能修复本项目反复出现的工程问题：

- 会话信息散在聊天里，下一轮 agent 容易丢上下文。
- T1/T2/T3、action protocol、trace、rescue、headroom 等词没有统一定义。
- 当前最严重 bug 是协议/解析不可观测，符合 `/diagnose` 说的“先建反馈回路”。
- 重构边界如果不写清楚，agent 容易把局部修复做成新的硬编码。

### 如何解决

把有价值的部分固化成项目文件和代码，不靠临时 prompt：

- 建项目根目录 `CLAUDE.md`，给 Claude Code 默认加载，写清楚当前 tiers、P0 trace、禁止事项、常用测试命令。
- 建 `paper1/docs/CONTEXT.md`，定义 BudgetFlow 领域词汇：tier contract、action protocol、router decision、budget prior、soft cap、rescue、headroom、clean row、protocol fail、equal-weight ablation、Automatic Budgeting。
- 继续维护 `paper1/docs/handoff.md`，只写下一步执行状态，不重复 PRD/实验表。
- 把 observability gate 写进代码和测试：没有 turn trace 的 parser failure 不算可诊断。
- 对重构保持小步：先做 `ModelCatalog / TierRegistry`、`ActionProtocolAdapter`、`RouterDecision`、`BudgetAllocator` 四个必要 seam，不重写 runner。

### 得出的结论

这篇文章的价值不是“安装一堆 skills”，而是提醒我们把隐性协作规则变成项目资产。

当前最值得立刻做的是：

1. 建 `CLAUDE.md`，约束 Claude Code。
2. 建 `CONTEXT.md`，统一 BudgetFlow 语言。
3. 用 `/diagnose` 的反馈回路标准推进 P0 trace。
4. 用 `/handoff` 的思路保持 `handoff.md` 可执行、短、最新。

不需要现在安装额外 skills。需要的是把这些规则固化到仓库和测试里。

## 15. Agent Patterns Applied to BudgetFlow

评估 6 个 agent 工程模式对 BudgetFlow 的适用性，每个映射到具体执行方式。

### 15.1 小而可组合

**适用。** BudgetFlow 不搞大流程 agent。拆成独立模块：

- trace → `_build_turn_trace` + helper functions
- protocol adapter → `adapter/protocol_adapter.py`
- tier registry → `ModelCatalog` in `defaults.py`
- router decision → `RouterDecision` dataclass in `selector.py`
- budget allocator → `historical_etl.py` (data), runtime shell TBD

执行方式：固化成代码架构。每个模块有单一职责、独立测试。

### 15.2 /diagnose 反馈回路

**非常适用。** GPT-5.4 parse bug 的修法：

1. 先跑单题 probe + `--trace-turns`（`gpt54_protocol_probe`）。
2. 从 trace 提取：`assistant_content_head`、`parser`、`parser_error_type`、`parser_error_message`。
3. 判据明确后才修 parser/prompt。
4. 修复结果固化成测试（`test_trace_fields.py` 已验证 trace schema）。

当前状态：trace schema 就绪，protocol adapter 就绪。等 probe 跑完才有 parser 修复判据。

### 15.3 TDD 垂直切片

**适用。** 四个重构（ModelCatalog、ProtocolAdapter、RouterDecision、BudgetAllocator）的切法：

- ModelCatalog：先写 `test_all_pro_picks_tier3_not_tier2`（失败）→ 实现 `ModelCatalog.strongest()` → 通过。
- ProtocolAdapter：先写 `test_tier3_is_text_regex` → 实现 `ActionProtocolAdapter.resolve()` → 通过。
- RouterDecision：先写 `test_all_pro_records_decision` → 实现 `RouterDecision` + `ctx.last_decision` → 通过。
- BudgetAllocator：等 P0 trace clean 后再切。

每个切片 = 一个失败测试 + 最小实现。不要一次性写完四个重构再跑测试。

### 15.4 /handoff

**已在做。** handoff.md 的维护规则：

- 不重复所有历史。历史在 progress.md 和 run 登记表。
- 只写：当前判断、边界条件、交付物列表、禁止事项。
- 执行方式：由 agent 在每次实验后更新。

### 15.5 /improve-codebase-architecture

**适用，但不是现在。** 触发时机：P0 trace + protocol + tier semantics 全部 clean 后。

审计问题：
- `ModelCatalog` 是否真正消除了硬编码 tier 查找？
- `ActionProtocolAdapter` 是否让 parser 选择变成显式声明？
- `RouterDecision` 是否在所有路由分支都有 reason？
- `_build_turn_trace` 18 个新字段是否形成深模块（接口简单、实现深）？

等 clean_gold2 probe 跑完再做。不要提前扫。

### 15.6 CONTEXT.md / 共享语言

**已完成。** `paper1/docs/CONTEXT.md` 定义：

- tier contract
- action protocol
- router decision
- budget prior
- soft cap
- rescue
- headroom
- clean row
- protocol fail
- equal-weight ablation
- Automatic Budgeting

每轮 agent 会话先读 CONTEXT.md 对齐语言。不靠临时 prompt 解释术语。
