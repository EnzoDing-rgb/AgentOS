# TrustGate: Intent-Aware Action Governance for LLM Agent Actions

## 核心 Insight

Agent 安全是**意图问题**，不是**身份问题**。一个被授权的 agent 仍然可能因为幻觉或误解而执行危险操作。传统的访问控制问"谁在调用？"——对 agent 场景没用，因为调用者就是被授权的 agent 本身。我们需要问的是"这个操作在当前上下文里想干什么？这个 agent 是否已经通过足够多的成功执行来赢得执行此类操作的信任？"。TrustGate 实现三件事：对每个操作做意图级风险分类，用累积信任分门控权限，对可逆操作提供操作级回滚，并维护不可篡改的审计日志。

---

## 问题定位

LLM agent 在生产中执行真实世界操作：写文件、执行代码、调用外部 API、发送邮件、发起支付。这些操作可能产生不可逆后果。现有框架的治理几乎为零：

**无意图分析。** Agent 调用 `os.remove("/data/production.db")`——系统只检查 agent 是否有文件权限，不检查"在当前任务上下文中，删除生产数据库是否合理"。一个文案写作任务里出现这种调用，显然是幻觉，但系统放行了。

**无动态信任。** 一个刚创建的 agent 和一个稳定运行了 1000 次的 agent 拥有完全相同的权限。没有"新手期"、没有"能力积累"、没有"信用降级"。

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
    loss_on_budget_overrun: 10

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

**第三级：人工审批（最高风险操作）。** `requires_human_approval: true` 的操作类型，无论信任分多高，都需要人工确认。这是不可逆高风险操作的最后防线。

**三级设计的原因：** 不同风险等级的操作需要不同的治理成本。对 90% 的低风险操作（读文件、格式化输出），静态规则零开销放行。对 9% 的中风险操作，轻量 LLM 分类。对 1% 的高风险操作，人工兜底。如果所有操作都过 LLM 分类，延迟和 token 成本不可接受。

### 累积信任（TrustScore）

**加分慢，减分快——这是核心设计。**

每个 agent 初始 50 分。每次任务成功完成且通过审计 → +5。任务失败 → -15。超预算 → 额外 -10。

从 50 分升到 80 分（解锁金融操作）需要连续 6 次审计通过，零失败。但从 50 分跌到 35 分（丢失写文件权限）只需要 1 次失败。

**信任分与 Paper 1 的预算联动：** 信任分低的 agent 不仅权限被缩减，Paper 1 的 Budget Governor 也可以降低其预算配额（不可信的 agent 不应该拿到大量资源去做可能出错的事情）。

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

如果该操作被 Paper 2 的故障检测判定为失败、或被后续审计判定为错误，系统可以自动回滚到操作前状态。

**对不可逆操作（发邮件、支付、外部 API 调用），回滚不可能。** 这就是为什么这些操作需要更高信任分 + 人工审批——因为出错后没有 undo。

### 不可篡改审计日志

每个操作生成一条审计记录：

```
{
  "timestamp": "...",
  "agent_id": "agent-007",
  "trust_score_at_time": 55,
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

**信任分参数需要调优。** 初始分、加分值、减分值的具体数字是启发式的。过于保守（减分太快）会导致 agent 长期无法解锁高级权限，过于宽松会失去治理意义。最优参数可能因部署场景而异。

**回滚只覆盖本地可逆操作。** 对文件系统操作、配置变更，回滚有效。对跨网络操作（发邮件、API 调用、数据库写入到外部服务），回滚不可能或需要对方系统配合。本文不声称解决跨系统回滚。

**协议级，非强制级。** TrustGate 的治理依附于 AgentOS 暴露的操作路径——意图分类、信任分、审计日志都挂在这条路径上。如果工具调用或出站流量被部署层直接绕过，门控就形同虚设。这是部署前提问题，不是 TrustGate 本身能解决的。

**与沙箱/网络强制的组合关系（相关工作，非本文贡献）。** 一类与本文正交的设计把强制点前移到沙箱或网络边界，让 agent 代码在物理上就无法绕开治理层（典型手段：eBPF 拦截出站流量，配合 TLS 信道绑定保证跨机委托可验证）。Wu 等在 AgenticOS ’26 的 Grimlock 中把这条路线概括为「不可绕过中介 + 证明信道上的最小权限委托」。TrustGate 不做这一层。分工很清楚：底层解决「绕不过」，TrustGate 解决「该不该」——即在请求已进入合规路径后，判断这次操作在当前任务语义和信任状态下是否被允许，并把决策写入审计链。两者可以组合部署，各管一块。

---

## 研究问题与实验计划

### RQ1：意图分类准确率

在标注好的 agent 操作数据集上（包含正常操作 + 已知危险操作 + 边界模糊操作），三级门控的 precision 和 recall 各是多少？按操作类型分类。静态规则覆盖了多少已知风险？LLM 分类的误判率和误放率分别是多少？

### RQ2：信任演化与任务完成率的关系

在长期运行（100+ 任务）的场景下，信任分的演化曲线是什么样的？不同的加分/减分参数对 agent 最终能力（能执行的操作范围）和任务完成率有什么影响？是否存在"最优参数区间"使得安全性和效率取得平衡？

### RQ3：治理延迟开销

三级门控对每个操作增加多少延迟？在典型工作流中（一个任务包含 5–20 个 tool call），端到端延迟增加的百分比是多少？

### RQ4：回滚有效性

在 agent 产生的所有错误操作中，有多少是可逆的（本地文件/配置操作）？操作级回滚 vs. 无回滚，对最终任务状态的恢复率差多少？

---

## 与 Paper 1、Paper 2 的关系

**与 Paper 1（资源治理）的关系：互补的两个维度。** Paper 1 的 Resource Governor 管"量"——agent 能消耗多少 token、多少 API 调用。TrustGate 管"质"——agent 能执行什么类型的操作。一个 agent 可以同时满足 P1 的预算约束但违反 P3 的操作权限（有预算但没信任），也可以有信任但没预算。两者独立检查，都通过才能执行。

**信任分 → 预算的联动：** 信任分低于某个阈值时，Paper 1 的 Governor 可以自动降低该 agent 的预算配额。不可信 + 大预算 = 高风险。

**与 Paper 2（故障恢复）的关系：事前 vs. 事后。** Paper 3 在操作执行前拦截危险操作（事前预防）。Paper 2 在操作失败后尝试恢复（事后修复）。两者不冲突：即使 TrustGate 放行了一个操作，该操作仍可能因为技术原因失败，此时 Paper 2 的 scoped recovery 接管。

**审计日志 → zombie 检测：** P3 的审计日志记录了每个 agent 的操作历史。异常模式（短时间大量高风险操作、反复被门控拦截后换种方式重试）可以作为 Paper 1 zombie detector 的信号源。



