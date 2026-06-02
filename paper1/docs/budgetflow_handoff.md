# BudgetFlow Handoff

目标：让下一个 agent 不用重读整段对话，也能立刻接手 BudgetFlow 诊断、503 排查、Automatic Budgeting 决策和后续目录重构。

## 1. 当前项目状态

### 我们看到了什么现象

BudgetFlow 在昨夜和今天的 SWE-style repair 实验里表现不稳定。原始 pass/fail 表不能解释失败原因。最近启动的 3x3 diagnostic run 又被 GPT-5.3 Codex provider 的 `ServiceUnavailableError` / 503 污染。

### 发现了什么问题

当前不能直接说 BudgetFlow 本身失败，因为失败来源混在一起：

- BudgetFlow policy / routing 可能有问题；
- budget cap / reservation accounting 可能有问题；
- model tier line 过去过于混乱；
- patch extraction / submission protocol 可能有问题；
- local harness 不是 official SWE-bench leaderboard harness；
- AiCode007 代理或其上游 GPT-5.3 Codex 服务返回 503；
- 503 之后 budget reservation 疑似没有释放，污染了后续预算状态。

### 如何解决的

已经先把实验系统改成更适合诊断的小矩阵：

- 固定三档模型：
  - T1 = Coder Flash
  - T2 = Coder Plus
  - T3 = GPT-5.3 Codex
- GPT-5.5 从 active code path 移除。
- 新增 `forensic_summary`，提高每条 run record 的诊断密度。
- 修复 `BudgetFlowBudgetError` 被误判为 `infra_fail` 的分类顺序问题。
- 新增 `3x3` preset。
- focused tests 已通过：37 passed。

### 得出的结论

现在最重要的不是扩大实验，而是先把失败归因链路跑干净。当前 3x3 的前 4 条结果不能作为科学结论，只能作为 infra/provider/reservation bug 线索。

## 2. 当前 Agent 框架和数据口径

### Agent 框架

当前跑的是：

- `mini-SWE-agent`
- SWE-bench-style repair tasks
- local worktree harness

SWE-bench 本身不是 agent 框架，它是 benchmark / dataset / evaluation protocol。

### 数据类别

当前代码路径使用 `load_swebench_lite_tasks(...)`，所以当前实验应写成：

> SWE-bench Lite local diagnostic run

不能写成 official SWE-bench leaderboard run。也不能直接写成 Verified 或 Full。

### Local harness vs official SWE-bench

Local harness 用于快速开发和诊断，检查：

- `test_patch`
- `fail_before`
- `model_patch`
- `fail_after`
- `pass_to_pass`

Official SWE-bench leaderboard 使用官方 Docker/container harness 和标准 prediction JSONL。正式论文结论需要 official export / official evaluation 验证。

## 3. 3x3 Diagnostic Run 设计

### Policies

当前诊断矩阵固定为：

- `budget_only_tight`
- `budgetflow_full_tight`
- `budgetflow_auto_v2_tight`

### Tasks

当前 3 个任务：

- `sympy__sympy-13480`：easy/control
- `sympy__sympy-20212`：medium
- `sympy__sympy-16988`：hard sentinel

### 启动命令

```bash
PYTHONPATH="/home/fengde/Projects/AI-learning/agent_learning/AgentOS/paper1/src:/home/fengde/Projects/AI-learning/agent_learning/AgentOS/external/mini-swe-agent/src" \
"/home/fengde/Projects/AI-learning/agent_learning/AgentOS/.venv/bin/python" -u -m budgetflow.run_mini_swe_compare \
  --preset 3x3 \
  --out-stem diagnostic_3x3_forensic_v1 \
  --resume \
  --trace-turns \
  --jobs 1 \
  --heartbeat 60
```

### 当前 run 状态

这轮 run 已停止，原因是结果被 provider 503 和疑似 budget reservation 泄漏污染。

已完成 4/9 rows，5th row 已开始后被停止。

已完成 rows：

1. `budget_only_tight / sympy__sympy-13480`
   - FAIL
   - `exit_status=ServiceUnavailableError`
   - `failure_class=infra_fail`
   - `forensic_summary.primary_axis=protocol`
   - T3 GPT-5.3 Codex
   - no patch, no gold edit

2. `budget_only_tight / sympy__sympy-20212`
   - FAIL
   - `exit_status=ServiceUnavailableError`
   - `failure_class=infra_fail`
   - `forensic_summary.primary_axis=protocol`
   - T3 GPT-5.3 Codex
   - no patch, no gold edit

3. `budget_only_tight / sympy__sympy-16988`
   - FAIL
   - `exit_status=BudgetFlowBudgetError`
   - `exit_reason=budget_exhausted`
   - `failure_class=budget_fail`
   - `forensic_summary.primary_axis=budget`
   - T2 Coder Plus
   - no patch, no gold edit

4. `budgetflow_full_tight / sympy__sympy-13480`
   - FAIL
   - `exit_status=ServiceUnavailableError`
   - `failure_class=infra_fail`
   - `forensic_summary.primary_axis=protocol`
   - T3 GPT-5.3 Codex

第 5 条启动过：

- `budgetflow_full_tight / sympy__sympy-20212`
- 前两轮 route 使用 `qwen3-coder-plus`

### 当前判断

这轮 3x3 不能解释 BudgetFlow repair quality。它只能说明：

- AiCode007 / GPT-5.3 Codex provider 路径不稳定；
- provider error 的 forensic axis 映射不够准确；
- failed provider call 后 budget reservation 疑似没有释放；
- 需要修完 infra/reservation 后干净重跑。

## 4. 503 / AiCode007 问题

### 我们看到了什么现象

T3 GPT-5.3 Codex 请求返回：

- `ServiceUnavailableError`
- HTTP 503 语义
- task cost 为 0
- 但 batch available budget 下降，说明 reservation 可能没释放

### 503 是什么意思

这里的 503 不是 SWE-bench 的错误，也不是任务本身失败。它表示 AiCode007 代理或其上游服务暂时无法处理请求。

可能原因：

- AiCode007 代理自身不可用；
- AiCode007 上游 GPT-5.3 Codex 不可用；
- model name / base URL / API key / route 配置不匹配；
- payload 太大或参数不被代理支持；
- 代理侧额度、并发、套餐、队列限制；
- 代理把上游错误包装成 503。

### 发现了什么问题

当前还没有看到 AiCode007 返回的完整 raw response body。只看到本地封装后的 `ServiceUnavailableError`。因此不能确定是代理宕机、上游拒绝、配置错误，还是 payload 参数问题。

### 下一步怎么查

下一个 agent 应优先查：

1. `paper1/src/budgetflow/adapter/mini_swe_proxy.py`
   - T3 是否走 AiCode007；
   - base URL 从哪里读；
   - model name 是否为 `openai/gpt-5.3-codex`；
   - headers / payload 是否符合 AiCode007 要求。

2. run log / trace
   - 找完整 `ServiceUnavailableError`；
   - 找 raw response body；
   - 如果 body 被吞掉，先增强日志。

3. provider smoke test
   - 单独用最小 prompt 请求 AiCode007 的 GPT-5.3 Codex；
   - 不经过 BudgetFlow；
   - 确认是 provider 不通，还是 BudgetFlow payload 导致 503。

4. reservation cleanup
   - provider error 后必须释放 reserved budget；
   - task cost 为 0 时不应减少 batch available budget。

### 得出的结论

503 是 provider/代理链路问题，不是 SWE-bench 任务问题，也不是 BudgetFlow repair 结论。当前必须先修 503 可观测性和 reservation cleanup，再重跑 3x3。

## 5. 已增加的可观测性

### 新增 forensic summary

每条 run record 新增：

- `primary_axis`
- `failure_chain`
- `patch`
- `harness`
- `budget`
- `policy`
- `confidence`
- `missing_evidence`

### primary axis

当前 primary axis 候选：

- `pass`
- `budget`
- `protocol`
- `localization`
- `repair_quality`
- `harness`
- `model_behavior`
- `infra`

### patch 维度

记录：

- patch 是否提取成功；
- patch 来源是 submitted patch 还是 worktree fallback；
- gold file 是否被编辑；
- agent 是否尝试 submit；
- agent 是否成功 submit。

### harness 维度

从 detail 中解析：

- `test_patch`
- `fail_before`
- `model_patch`
- `fail_after`
- `pass_to_pass`

### budget 维度

记录：

- budget 是否耗尽；
- 是否在 patch 之后耗尽；
- task cost；
- batch spent / reserved / available；
- budget pressure；
- cap / overrun 线索。

### policy 维度

记录：

- strategy；
- backend picks；
- tier mix；
- rescue / escalation 是否发生。

### 当前仍需增强的可观测性

1. Provider raw error body
   - 保存 HTTP status；
   - 保存 provider error code；
   - 保存 response body 摘要；
   - 保存 request id，如果 provider 返回。

2. Reservation lifecycle
   - 记录 reservation id；
   - 记录 reserve / commit / release；
   - provider error 后明确写入 `reservation_released=true/false`。

3. Provider axis
   - `ServiceUnavailableError` 应归到 `infra` 或更细的 `provider`，不应归到 `protocol`。

4. Retry policy
   - provider 503 是否 retry；
   - retry 次数；
   - retry 后是否复用/释放 reservation。

## 6. Automatic Budgeting 当前判断

### 我们看到了什么现象

代码里已有预算相关机制：

- frozen/protocol caps；
- tight / loose；
- `tight_scale` / `loose_scale`；
- `soft_budget` / `max_overrun`；
- `per_task_cap`；
- budget pressure；
- auto-v2 rescue / stop-loss。

### 发现了什么问题

这些还不是完整 Automatic Budgeting。当前更像：

> budget parameterization + guards + routing pressure

完整 Automatic Budgeting 应该根据 task difficulty、early evidence、model progress、remaining global budget 动态分配预算，而不是只套固定 cap。

### 为什么暂时没有立刻做

因为当前失败轴还没干净。现在如果马上实现 Automatic Budgeting，可能把 provider 503、reservation leak、protocol 问题一起掩盖掉。

### 什么时候应该做

干净重跑 3x3 后，根据 `forensic_summary.primary_axis` 决策：

- 如果失败集中在 `budget`：立即实现 Automatic Budgeting；
- 如果失败集中在 `protocol`：先修 submission / patch extraction；
- 如果失败集中在 `infra`：先修 provider / retry / reservation；
- 如果失败集中在 `localization`：先做更早升级或定位阶段 rescue；
- 如果失败集中在 `repair_quality`：检查 GPT-5.3 Codex 是否来得太晚、是否需要 earlier escalation。

### Automatic Budgeting 初版建议

建议实现一个轻量版本，不要直接做大系统：

1. Task-level budget estimator
   - easy/control：低初始 cap；
   - medium：中 cap；
   - hard sentinel：高 cap 或更早 T3；
   - 可先用 instance id 白名单和历史 trace，不急着训练模型。

2. Progress-aware reallocation
   - 有 gold edit / patch / failing tests improvement：允许继续花；
   - no progress 多轮：stop-loss；
   - localization 已正确但 repair 未过：升级模型；
   - patch 已存在但 fail_after fail：给高 tier repair budget。

3. Global budget governor
   - 每个 task 有 soft cap；
   - 全局 batch 有 hard cap；
   - 未使用预算回流；
   - failed provider reservation 必须 release。

4. Rescue trigger
   - 早期 no-progress：T2/T3；
   - patch-after-fail：T3 repair rescue；
   - repeated format/protocol issue：切 protocol repair 或 terminate。

5. Observability
   - 每次 budget adjustment 写入 record；
   - 输出为什么加预算、为什么停、为什么升级。

### Acceptance criteria

Automatic Budgeting 初版完成后应满足：

- 所有 budget adjustment 可在 JSONL 中解释；
- provider error 不消耗有效预算；
- no-progress task 会 stop-loss；
- repair-progress task 可获得额外预算；
- 同一 3x3 上能比较 fixed budget vs auto budget；
- table 能显示 auto budget 的收益或失败原因。

## 7. 后续 bugfix 计划

### P0：修 503 可观测性

目标：看到 AiCode007 返回的原始错误信息。

具体做法：

1. 在 provider proxy 层捕获 HTTP status、error body、request id。
2. 将 provider error 写入 run record / trace。
3. summary log 中打印 provider 错误摘要。
4. 不泄露 API key。

验收标准：

- 下一次 503 时，JSONL 能看到 provider、model、status、error body 摘要；
- 能区分 AiCode007 自身 503 和上游模型 503；
- 不需要重跑整轮就能定位 provider 错误。

### P0：修 reservation release

目标：provider 调用失败且 cost=0 时，不减少 available budget。

具体做法：

1. 找 BudgetGovernor reservation 生命周期。
2. 确认正常路径 reserve -> commit。
3. 在 exception 路径确保 reserve -> release。
4. 对 `ServiceUnavailableError`、timeout、rate limit、format error 分别测试。

验收标准：

- provider 503 后 `reserved_budget` 回到调用前；
- `task_cost=0` 的 failed provider call 不降低 batch available；
- 单元测试覆盖 exception release；
- 3x3 重跑时不会因为前序 503 污染后序 budget。

### P1：修 forensic axis 映射

目标：`ServiceUnavailableError` 不再归到 `protocol`。

具体做法：

1. 在 `failure_classification.py` 中识别 provider/service unavailable。
2. `primary_axis` 映射到 `infra`，或新增 `provider` axis。
3. failure_chain 记录 `provider_error`。

验收标准：

- `ServiceUnavailableError` row 的 `failure_class=infra_fail`；
- `forensic_summary.primary_axis=infra` 或 `provider`；
- table next_action 指向 provider/infra fix。

### P1：重跑 clean 3x3

目标：拿到可解释的 BudgetFlow 诊断结果。

具体做法：

1. 清理或换新 out stem，例如 `diagnostic_3x3_forensic_v2`。
2. 先跑 AiCode007 smoke test。
3. provider 正常后再跑 3x3。
4. heartbeat 报告必须包含 `done/9`、pass/fail、当前 strategy/task。

验收标准：

- 9/9 rows 完成；
- 无 provider contamination；
- 每条 fail 都有可信 `primary_axis`；
- table 能给出下一步：Automatic Budgeting / protocol fix / localization fix / repair quality fix。

## 8. 后续目录重构计划

用户要求：3x3 诊断完成并修完关键 bug 后，再做目录重构。不要现在删除文件。

### 当前问题

目录中存在：

- `external/`、`paper1/`、repo root 配置混杂；
- `paper1/docs` 文档多但生命周期不清；
- `paper1/src` 中混入 data-like 子目录；
- run outputs、logs、raw artifacts、paper docs、scripts 混在一起；
- GPT-5.5 历史 artifact 仍在，但 active path 已移除。

### 目标结构建议

```text
AgentOS/
  README.md
  CLAUDE.md
  pyproject.toml / uv.lock / requirements.txt
  pyrightconfig.json
  external/
    mini-swe-agent/
  paper1/
    README.md
    docs/
      concept.md
      experience.md
      budgetflow_handoff.md
      plans/
      reports/
      archive/
    src/
      budgetflow/
    tests/
    scripts/
    configs/
    data/
      tasks/
      runs/
      traces/
      official_predictions/
      raw_archive/
    notebooks/
    paper/
      figures/
      tables/
      draft/
```

### docs 规则

保留：

- `concept.md`；
- `experience.md`；
- `budgetflow_handoff.md`；
- 当前仍被引用的实验计划；
- 论文关键设计文档。

迁移到 `docs/plans/`：

- 还没执行完的计划；
- 未来重构计划；
- Automatic Budgeting 设计计划。

迁移到 `docs/reports/`：

- 已完成实验报告；
- 3x3 诊断报告；
- paper result tables 的解释文档。

迁移到 `docs/archive/`：

- 历史模型探索；
- GPT-5.5 ceiling probe 说明；
- 过时但可能有证据价值的记录。

删除条件：

- 文件是重复副本；
- 文件内容已经被更高质量文档吸收；
- 文件没有被代码、README、paper draft、docs index 引用；
- 删除前必须先列清单，不直接删。

### data 规则

建议：

- `data/runs/`：JSONL、summary log、checkpoint；
- `data/traces/`：per-run trace dirs；
- `data/official_predictions/`：official SWE-bench prediction JSONL；
- `data/raw_archive/`：历史 raw artifact，例如 GPT-5.5 probe；
- `data/tasks/`：固定 task lists / splits。

不要把实验输出放在 `src/`。

### scripts 规则

保留 CLI / one-off analysis，但分层：

- `scripts/run/`：启动实验；
- `scripts/analyze/`：表格、统计、diagnosis；
- `scripts/export/`：official prediction export；
- `scripts/dev/`：smoke test、provider test。

### src 规则

`src/budgetflow/` 只放库代码：

- routing；
- budget governor；
- adapter；
- failure classification；
- experiment runner；
- table/report builder 可考虑移到 scripts，如果不是库 API。

### 重构步骤

1. 诊断结束后先生成 inventory：列出 docs/data/scripts/src 下所有文件和用途。
2. 标记每个文件：keep / move / archive / delete-candidate。
3. 先 move，不 delete。
4. 更新 imports、paths、README、docs links。
5. 跑 tests。
6. 跑一个 smoke run。
7. 生成迁移报告。
8. 用户确认后再删除 delete-candidate。

### 风险控制

- 不直接删除实验 artifact；
- 不移动 active run 输出直到 run 完成；
- 不改 official prediction 格式；
- 不把 historical ceiling probe 当 active experiment；
- 每一批 move 单独 commit；
- 每批 move 后跑 tests 或 smoke。

### 重构验收标准

- `pytest paper1/tests` 通过；
- 3x3 run command 可正常启动；
- docs links 不断；
- active configs 路径不坏；
- paper table script 能找到 run outputs；
- official prediction export 仍能生成；
- root README / paper1 README 能解释目录结构；
- archive/delete 清单明确；
- 用户确认后才真正删除 delete-candidate。

## 9. 下一个 agent 的执行顺序

按这个顺序做：

1. 不要继续解释旧 3x3 结果。
2. 先查 AiCode007 503 raw error body。
4. 修 reservation release。
5. 修 forensic axis：`ServiceUnavailableError` -> infra/provider。
6. 写/跑 focused tests。
7. smoke test AiCode007 GPT-5.3 Codex。
8. 用新 out stem 重跑 clean 3x3。
9. 根据 clean 3x3 决定是否实现 Automatic Budgeting。
10. 诊断完成后再提交目录重构执行计划。

## 10. 当前禁止事项

- 不要把当前 4/9 polluted run 当 BudgetFlow 结论。
- 不要现在大规模删除或重构目录。
- 不要重新引入 GPT-5.5 active path。
- 不要把 local harness 分数写成 official SWE-bench leaderboard 分数。
- 不要在没看到 raw provider body 前断言 AiCode007 503 的唯一原因。

## 11. 当前最短结论

当前最优先任务是：

> 修 AiCode007 / GPT-5.3 Codex 503 可观测性和 budget reservation release，然后干净重跑 3x3。Automatic Budgeting 很重要，但应由 clean 3x3 的 failure axis 触发。目录重构等诊断完成后再做，先 move/archive，后 delete。
