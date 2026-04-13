# TrustGate: Intent-Aware Action Governance for LLM Agents

## 核心 Insight

Agent 安全是**意图问题**，不是**身份问题**。一个被授权的 agent 仍然可能因为推理偏差执行危险操作。传统访问控制问的是"谁在调用？"——对 agent 没用，因为调用者就是被授权的 agent 本身。真正该问的是：这个操作在当前任务里合不合理？TrustGate 在每个操作执行前做意图级风险分类，根据 agent 的历史表现动态调整可执行操作的范围（信任分 + 管理员设定的天花板），对可逆操作提供回滚快照，对所有操作维护不可篡改的审计记录。

---

## 问题定位

LLM agent 在生产中执行真实世界操作：写文件、执行代码、调用外部 API、发送邮件、发起支付。这些操作可能产生不可逆后果。现有框架的治理几乎为零：

**无意图分析。** Agent 被要求"清理测试残留数据"，它找到了名字里带 `_test` 的表，推断这是测试数据，执行了 `DROP TABLE user_sessions_test`——但这张表其实是生产库里记录活跃会话的表，命名只是历史遗留。模型的推理在局部是合理的，系统也没拦截，因为 agent 有写权限。真正需要问的是：在"清理测试数据"这个任务上下文里，对生产库执行 DROP 操作是否应该被允许？

**无故障降级。** Agent 连续三次任务都因为误操作失败了，但第四次它仍然拥有和之前完全相同的权限。分布式系统里早就有熔断器（circuit breaker）：一个服务反复出错就自动降级。Agent 系统没有这个机制——失败不会导致权限收缩，也没有"天花板"让管理员限制 agent 能达到的最高权限。

**无系统级回滚。** Agent 误操作后，没有系统性的 undo。用户只能手动恢复，或者接受损失。

**无审计。** 没有不可篡改的记录显示 agent 做了什么、为什么做、结果如何。出事后无法追溯。

**这些问题与 Paper 1 的资源治理正交。** Paper 1 管的是"这个 agent 能用多少 token / 多少 API 调用"（量的约束）。Paper 3 管的是"这个 agent 能不能执行这个特定操作"（质的约束）。一个 agent 可以完全遵守预算限制，但在预算内做出危险操作。

---

## 核心机制

### 治理策略（Governance Policy）

借鉴 Sovereign-OS 的宪章（Charter）思想，TrustGate 使用声明式策略文件定义治理规则：

```yaml
governance:
  trust:
    initial_score: 50
    gain_on_success: 5
    loss_on_failure: 15
    score_ceiling: 90           # 管理员设定的天花板，agent 再怎么表现好也不会超过这个值
    frozen_threshold: 20        # 分数低于此值，agent 冻结为只读，需人工重置

  action_tiers:
    - tier: "read_local"
      min_trust: 10
      risk: low
      rollback: not_needed
    - tier: "write_local"
      min_trust: 40
      risk: medium
      rollback: required
    - tier: "external_api"
      min_trust: 50
      risk: medium
      rollback: best_effort
    - tier: "code_execution"
      min_trust: 60
      risk: high
      rollback: required
    - tier: "financial"
      min_trust: 80
      risk: critical
      rollback: not_possible
      requires_human_approval: true

  forbidden_patterns:
    - "read ~/.ssh/* AND send to external"
    - "rm -rf on non-temp directories"
    - "access credentials files"
```

**策略和代码分离。** 修改治理规则不需要改系统代码，换一个 YAML 文件就行。不同部署场景（内部开发 vs. 面向客户 vs. 金融场景）可以用不同策略，底层系统完全不动。

### 三级意图分类（Semantic Action Gate）

每个 tool call / 外部操作在执行前经过三级门控：

**第一级：静态规则匹配（零 LLM 成本，微秒级）。** 对照策略中的 `forbidden_patterns` 做模式匹配。已知危险操作直接拦截，不需要任何推理。覆盖面窄但 100% 可靠。

**第二级：轻量 LLM 分类（低成本，百毫秒级）。** 对于不命中静态规则的操作，用一个小模型（或 prompt 模板）判断：这个操作在当前任务上下文中的风险等级是什么？输入是操作描述 + 当前任务目标 + 近期操作序列，输出是风险等级分类。

**第三级：人工审批（最高风险操作）。** 策略里标记了 `requires_human_approval: true` 的操作类型，必须人工确认才能执行。这是不可逆高风险操作的最后防线。

**三级设计的原因：** 不同风险等级的操作需要不同的治理成本。对 90% 的低风险操作（读文件、格式化输出），静态规则零开销放行。对 9% 的中风险操作，轻量 LLM 分类。对 1% 的高风险操作，人工兜底。如果所有操作都过 LLM 分类，延迟和 token 成本太高。

### 信任分（Trust Score）

**减分快、加分慢、有天花板。**

每个 agent 初始 50 分。任务成功 → +5，任务失败 → -15。不对称是刻意的：建立信任需要持续的好表现，摧毁信任只需要一次事故。

信任分决定 agent 能做什么——每个 action tier 都有一个 `min_trust` 门槛。分数 50 的 agent 能读写文件、调外部 API；分数掉到 35，写文件的权限就没了；掉到 `frozen_threshold`（20）以下，agent 冻结为只读，需要管理员手动重置。

**天花板是行业适配的关键。** 管理员在策略里设定 `score_ceiling`，agent 的分数永远不会超过这个值。不同行业设不同天花板，同一套系统就能适配不同风险容忍度：

| 场景 | `score_ceiling` | 效果 |
|---|---|---|
| 内部开发工具 | 90 | agent 表现好，最终能做几乎所有事 |
| 面向客户的 SaaS | 60 | agent 永远到不了 code_execution（需 60）和 financial（需 80）这两级 |
| 银行 / 医疗 | 40 | agent 只能读写文件，外部 API 和代码执行永远需要人批 |

这样 agent 不是"自己挣来权限"——它的权限上限由管理员划定，它只能在这个范围内靠好表现恢复到满状态。天花板之上的操作，再怎么表现好也需要人工审批。

**与 Paper 1 的预算联动：** 信任分低的 agent 不仅权限被缩减，Paper 1 的 Budget Governor 也可以同步降低其预算配额——一个持续出错的 agent 不该继续烧钱。

### 操作级回滚（Operation-Level Rollback）

对标记为 `rollback: required` 的操作类型，在执行前记录回滚信息：

```
Before: write_file("/config/app.yaml", new_content)
Rollback record: {
  "action": "write_file",
  "path": "/config/app.yaml",
  "original_content_hash": "abc123",
  "original_content_snapshot": <stored>,
  "timestamp": "..."
}
```

如果操作执行后被判定为失败，或者被后续审计标记为错误，系统可以自动回滚到操作前状态。

**对不可逆操作（发邮件、支付、外部 API 调用），回滚不可能。** 这就是为什么这些操作在策略里标为 `requires_human_approval`——因为出错后没有 undo，必须事前拦住。

### 不可篡改审计日志

每个操作生成一条审计记录：

```
{
  "timestamp": "...",
  "agent_id": "agent-007",
  "trust_score": 55,
  "action": "write_file('/config/app.yaml', ...)",
  "intent_classification": "配置更新, risk=medium",
  "gate_decision": "passed (tier 1: no pattern match, tier 2: risk=medium, trust 55 >= 40)",
  "outcome": "success",
  "token_cost": 0,
  "prev_hash": "def456..."
}
```

每条记录的哈希包含上一条记录的哈希（hash chain），任何篡改都会导致后续所有记录的哈希对不上。

---

## 执行模型的诚实限制

**LLM 意图分类本身不可靠。** 第二级门控用 LLM 做风险分类，但 LLM 自身可能误判。一个精心构造的操作描述可能骗过分类器。这就是为什么我们不依赖单一级别：静态规则兜底已知风险，人工审批兜底最高风险，LLM 分类只处理中间地带。

**信任分参数需要调优。** 加分值、减分值、天花板、冻结阈值的具体数字是启发式的。减分太快，agent 偶尔犯一次错就被大幅降级，影响正常工作；减分太慢，连续出错了还没降到限制线，损失已经扩大。天花板设多高取决于行业——这是运维决策，不是算法问题。

**回滚只覆盖本地可逆操作。** 对文件系统操作、配置变更，回滚有效。对跨网络操作（发邮件、API 调用、数据库写入到外部服务），回滚不可能或需要对方系统配合。本文不声称解决跨系统回滚。

---

## 研究问题与实验计划

### RQ1：三级门控 + 信任分到底管不管用？

核心想验证两件事：**门控该拦的拦住了吗？信任分的升降和天花板在不同行业配置下表现怎么样？**

门控这边——agent 被要求"清理临时日志"，它试图执行 `rm -rf /var/log/*`。静态规则应该直接拦住。另一边，agent 要读一个本地配置文件，门控不应该挡路。我们要度量：危险操作的拦截率和正常操作的放行率。

信任分这边——我们用三种天花板配置（90 / 60 / 40，对应开发、SaaS、银行场景）分别跑长任务（100+ 轮）。观察：agent 的分数怎么变化？天花板为 40 时，agent 是不是确实被限制在只读/写文件这两级、永远碰不到外部 API？天花板为 90 时，agent 是不是能在持续成功后解锁更多操作？连续失败时，分数下降是否足够快，能在造成大损失之前把 agent 降级到安全范围？

### RQ2：门控带来多少额外延迟？

agent 每次调工具都要过三级门控，这会变慢。慢多少？

举个例子：agent 一个任务里调了 10 次工具（读文件、写文件、跑命令……），没有门控的话总共花 8 秒。加了门控之后变成 9 秒还是 15 秒？如果门控把每个操作多加了几百毫秒，用户可能感觉不到；但如果 LLM 意图分类那一级每次要跑一两秒，累积起来就很明显了。我们要量化这个开销，看它在可接受范围内还是需要优化。

---

## 与 Paper 1、Paper 2 的关系

**与 Paper 1（资源治理）：量 vs. 质。** Paper 1 管 agent 能消耗多少资源（token、API 调用次数）。Paper 3 管 agent 能执行什么类型的操作。两者独立检查，都通过才放行。

**信任分 → 预算联动：** 信任分低的 agent，Paper 1 的 Governor 可以同步降低其预算配额。一个持续出错的 agent 不该继续烧钱。

**审计日志 → zombie 检测：** P3 的审计日志记录每个 agent 的操作历史。异常模式（短时间大量高风险操作、反复被拦截后换方式重试）可以作为 Paper 1 zombie detector 的信号源。

**与 Paper 2（故障恢复）：回滚 vs. 重试，方向相反。** Paper 3 的操作级回滚是**往回退**——agent 写坏了一个文件，从快照恢复原文件，消除伤害。Paper 2 的 scoped recovery 是**往前走**——任务步骤失败了，从检查点恢复上下文，让 LLM 换个方式重试，把任务完成。一个管"擦屁股"，一个管"重新来"。两者可以协作：Paper 3 先回滚消除损害，然后 Paper 2 接管重试完成任务。

