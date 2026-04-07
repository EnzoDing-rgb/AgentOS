# AgentOS: A User-Space Resource Kernel for Concurrent LLM Agents

## 核心 Insight（一句话）

把 **上下文窗口（context window）** 当作一种可被抢占、可被调度的 OS 级资源，在用户态实现一个 LLM 资源内核，使多个并发 Agent 之间能做到真正的资源隔离、优先级抢占和 **QoS（服务质量）** 保证。

---

## 术语与缩写

读后面章节前先扫一眼；正文里第一次出现的缩写可回看这里。

| 缩写 / 术语 | 全称或含义 | 在 AgentOS 里指什么 |
|-------------|------------|---------------------|
| **QoS** | Quality of Service，服务质量 | 对交互延迟、吞吐、公平性等给出**可预期的保证**（例如高优先级任务不被后台任务拖死），不是「跑得更快」的口号。 |
| **SCC** | Semantic Context Checkpoint，语义上下文检查点 | 把当前 LLM **对话状态**做成可恢复的「检查点」：摘要 + 恢复指令，存进 Context Store。用于抢占、僵尸回收、安全 abort 后接着跑，不是二进制内存 dump。 |
| **Turn** | （无标准缩写）一轮交互 | 一次完整的 agent 工作单元：一轮模型推理 + 可能多步 tool，是**调度与计量的单位**，不是单次 HTTP 请求。 |
| **preemption / 抢占** | — | 高优先级任务打断低优先级，迫使其让出 context / 槽位；LLM 侧靠 SCC 实现，不能像 CPU 那样直接拷寄存器。 |
| **Admission Control** | 准入控制 | 任务**进队列前**检查 token、rate limit、并发槽是否够；不够就排队或拒绝，避免承诺了资源却跑不起来（overcommit）。 |
| **overcommit** | 过度承诺 | 接纳的任务所需资源总和超过系统能提供的上限，导致大面积失败或饿死。 |
| **API Rate Limit** | 接口速率限制 | 云厂商对「单位时间内调用次数 / token 量」的上限；类比网络带宽，可滑动窗口计数。 |
| **TTFT** | Time To First Token，首 token 延迟 | 从发起请求到模型**输出第一个 token**的时间，衡量交互流畅度的常用指标。 |
| **RBAC** | Role-Based Access Control | 基于角色的访问控制：按身份/角色授权；本文强调 agent 风险常在**操作组合**而非单角色。 |
| **MAC** | Mandatory Access Control，强制访问控制 | 系统级强制策略（不随应用自己改规则）；语义防火墙可类比「策略引擎」，但判定对象是**工具效应与数据流**。 |

---

## 调度 vs 约束：不是一回事，也不要假装 SCC 统一了两者

| | **约束（Constraint / Policy）** | **调度（Scheduling）** |
|---|-------------------------------|------------------------|
| **在问什么** | 「这件事**允不允许**？花多少**上限**？**安不安全**？」 | 「在合法前提下，**谁先谁后**？谁被**抢占**？这次**走哪个后端**？」 |
| **典型机制** | Admission、预算上限、rate limit 余量、语义防火墙（commit 前门控） | 优先级队列、SCC 抢占、Zombie 回收让槽、异构后端路由 |
| **类比传统 OS** | `ulimit`、cgroup、MAC——画红线 | CPU 调度器——在红线内分配顺序与时间片 |

**一句话**：**约束画可行域，调度在域内排序。** Budget / admission / rate limit **不依赖** SCC——FIFO + 计数器也能做限额；SCC 主要服务 **抢占与恢复**，是调度子系统的机制，不是「统领全局的唯一原语」。

---

## 问题定位：现有框架的根本性空白

LangChain、CrewAI、AutoGen 解决了 Agent **编排**（让 AI 能跑起来），但没有解决 **资源治理**：

- 10 个并发 Agent 同时运行，共享同一个 API Key 的 rate limit 和 token budget，没有任何协调机制
- 高优先级任务（用户实时交互）和低优先级任务（后台批处理）争抢同一个上下文窗口，互相阻塞
- 没有 admission control：系统会因为并发请求过多直接打到 API 限流错误，崩掉整个流水线
- 没有 preemption：一个跑偏的 Agent 可以把 token budget 耗尽，其他 Agent 只能饿死
- **没有 zombie detection**：一个卡死/超时的 Agent Turn 继续占着 context window 和并发槽，用户只能手动 kill 掉重开——这正是 Cursor 用户频繁遭遇"agent 动着动着就不动了、不得不 new context"的根本原因

这和 1960 年代没有 OS 的计算机一样——每个程序都裸跑，互相踩踏。

---

## 核心抽象：三类 LLM 一等资源

| 资源 | OS 类比 | 独特性 |
|------|---------|--------|
| **Context Window** | 内存（RAM） | 内容相关，不只是大小；preemption 需要语义压缩 |
| **Token Budget** | 电池电量（可耗竭） | 花完不是「等等就有」，是业务停摆；类比手机低电量降频 |
| **API Rate Limit** | I/O 带宽 | 时间窗口语义（sliding window），可自动探测 |

---

## 关键技术贡献：Context Preemption（调度子系统）

**新颖点主要在「有损抢占」这条线**，与约束层分开说才清楚。

CPU 抢占：保存寄存器 → 换进程 → 恢复，**无损**。

LLM 抢占：上下文是**语义状态**，不能像内存那样逐字节 snapshot；SCC 用摘要近似，**本质有损**——这和 OS context switch **不同构**，QoS/公平性的严格论证会变成**概率或误差界**，不能照搬 OS 证明。

我们提出 **Semantic Context Checkpoint（SCC，语义上下文检查点）**——见上文术语表：

```
抢占时：Summarizer(当前 context) → 压缩摘要 + 恢复指令 → 存入 Context Store
恢复时：从 Context Store 取出摘要 → 重建 context → 继续执行
```

核心挑战（**可行性先于架构铺陈**）：
1. **有损 vs 无损**：若摘要—恢复在真实 agent 任务上成功率或语义漂移不可接受，调度这条 claim 会塌——需要先 dirty prototype 量化的不是「优化空间」，而是**能不能用**。
2. **递归开销**：生成摘要本身要调 LLM，烧的正是被管理的 token/rate limit——抢占越频繁，管理税越重，可能出现「越调度越亏」。
3. **压缩保真度**：如何量化 context 恢复误差；抢占时机（token 边界 vs 语义边界）；恢复代价是否让 preemption 在实际负载下不如排队。

SCC 有三条触发路径，共享同一套 checkpoint/restore 机制：
- **主动抢占**：调度器换入高优先级任务，当前 Turn 被打断并 checkpoint。
- **Zombie 回收**：Turn 被判定为僵尸，强制 checkpoint 后释放资源。
- **安全 abort**：语义防火墙拦截危险操作，abort 后回到上一 SCC（与横切安全内核对齐）。

**定位**：这是调度路径上的机制；**不是** budget、admission、防火墙的「统一抽象」——那些可以独立存在。

---

## 系统架构：用户态 LLM Kernel（实为中间件，见下）

```
┌──────────────────────────────────────────────────────────┐
│                Agent 应用层 (LangChain / CrewAI etc.)     │
├──────────────────────────────────────────────────────────┤
│                      AgentOS API                          │
│   submit_task(priority, resource_spec) → task_id         │
│   yield_context() / checkpoint() / restore()             │
│   tool_call(...) → prepare → semantic gate → commit/abort │
├────────────┬──────────────┬──────────────────────────────┤
│  Scheduler │  Admission   │       Zombie Detector        │
│ (priority +│  Control     │  (timeout/liveness           │
│ preemption)│ (budget check│   → SCC + reclaim)           │
├────────────┴──────────────┴──────────────────────────────┤
│     Safety Kernel: Semantic Firewall + Transaction Log     │
│     (intent-level gating, atomic rollback, audit trail)    │
├──────────────────────────────────────────────────────────┤
│                  Context Store (SCC 存储)                 │
├──────────────────────────────────────────────────────────┤
│           LLM Driver Layer (Claude/GPT/Local 统一接口)    │
└──────────────────────────────────────────────────────────┘
```

**Scheduler**：维护多级优先级队列，支持抢占式调度。调度单位是 Turn（一次完整的 agent 交互），不是单次 LLM 调用。

**Admission Control**：Turn 进入调度队列前，估算 token 消耗，检查预算余额和 rate limit 余量，拒绝或延迟低优先级任务。（可复用 Sovereign-OS 的 CFO 三道检查。）

**Zombie Detector**：对每个活跃 Turn 做活性监控与资源回收。只靠「没输出」不够，因为 LLM zombie 往往是**语义上不前进**（在循环、在空烧预算）。检测分三层：

- **心跳超时**：T 秒无 token 输出、无 tool 返回 → 抓 API 沉默 / 工具阻塞。
- **进展预言机（progress oracle）**：追踪 Turn 的「状态指纹」（tool 序列、输出 hash、关键变量），连续 N 步无新状态 → 判定语义 livelock。
- **烧钱速率异常**：token burn rate 偏离同类任务基线 → 提前止损（与 Budget 机制联动）。

**回收协议**：判定 zombie → 强制 SCC checkpoint（保留已完成中间结果）→ 释放 context 槽位 / 并发槽 / 预算预留 / 工具锁，避免级联卡死。等价于把用户手动「new context window」变成系统自动行为。

**Auto-Probe**：启动时自动探测 API rate limit（读响应头的 `X-RateLimit-*`），无需用户手动配置。

---

## 横切安全内核：语义防火墙 + 事务性工具提交

如果 agent 能读本地文件、能发外网、能写配置，风险不在「谁调用了工具」，而在「这些操作组合起来想干嘛」。工具执行走 OS 风格的事务：

- **Prepare**：生成效应摘要（读/写什么、数据往哪流、目标域是本地还是外网）。
- **Semantic Gate**：语义防火墙做意图级判定（例如读 `~/.ssh/id_rsa` + 外发 → 拦）。
- **Commit / Abort**：通过才提交；否则 abort，按事务日志做原子回滚（对齐 SCC 与原子快照）。

不变式：**未经门控的效应不可提交**。出错回滚到本次原子操作或本层执行域，不必整任务重来。

**与调度的关系**：工具安全（prepare/gate/commit）与资源调度 **正交**——没有调度也能做防火墙，没有防火墙也能做限额排队。本文把二者**同栈部署**是为了系统完整性，但论文叙事上要分清：**一篇稿子可以主投调度+SCC，安全另文或附录**，否则贡献焦点会被稀释。

---

## 诚实边界：类比哪里成立、哪里会误导

**Context window ≈ 内存**：只在「容量有限、需要换出」层面类比。内存页近似可互换；context 里 token **语义耦合**，不能假设「换出一半」无损——Paper 3 的 cost-aware 置换是在承认这一点，而不是 LRU 翻版。

**「用户态 kernel」**：真实 kernel 能强制进程无法绕过；这里 agent 若直接调厂商 API 可**绕过**本层—— enforcement 是**协作式**（应用走 AgentOS API），类似编排中间件 + 策略插件，不是硬件级隔离。叙事里避免暗示与真内核等价的强制力。

**进展预言机 / 语义 livelock**：若依赖额外 LLM 调用判断「是否在循环」，同样消耗被管理资源——需说明规则优先、模型为辅的成本模型。

---

## 与相关工作的本质区别

| 系统 | 解决什么 | 没解决什么 |
|------|---------|-----------|
| Sovereign-OS | 财务治理、权限、审计 | 多 Agent 并发调度、有损抢占（SCC） |
| AgentRM | Zombie Turn 检测、Turn 级资源计量 | 主动抢占、SCC、跨 agent 全局调度 |
| vLLM | 服务端 KV cache 调度 | 客户端多 Agent 的资源治理 |
| **AgentOS（目标）** | 协作式中间件：调度（SCC+Zombie）+ 约束（budget/admission）+ 可选工具事务（防火墙） | **待验证**：SCC 保真与开销；绕过 API 时的 enforcement；安全与调度分论文时的边界 |

最后一行不写「—」：prototype 前诚实地列 **open problems**，审稿人比「全能破折号」舒服。

---

## 研究问题（可发论文的 claim）

1. **SCC 可行性（应先做）**：摘要—恢复—继续跑在真实任务上的成功率、语义漂移、token 税；抢占频率与「不如排队」的临界点。
2. **调度算法**：在 token budget **约束**下，考虑 zombie 回收代价的多 Agent 策略（约束与调度分工明确）。
3. **实验 — 抢占**：SCC 能否在预算内降低高优先级任务的 TTFT，还是开销吃掉收益？
4. **实验 — Zombie**：自动回收 vs 人工重启：资源利用率、完成率、误判（长思考 vs 死循环）。

---

## 为什么这个 idea 仍然值得做（收敛后的 neat）

- **问题真**：多 agent 共享 key、僵尸占槽、跑飞烧预算——工程上痛，不是假想。
- **贡献可分两层写清楚**：**调度 + SCC** 是一条线；**约束（budget/admission）** 是一条线；**工具事务 + 防火墙** 正交，可同栈可另文——避免「一个抽象统领一切」的 overstretch。
- **OS 类比**：作直觉导航，不在有损 SCC 处假装与无损 context switch 同构。
- **Scope**：纯用户态、不改服务端，但要诚实写清 **协作式 enforcement** 的边界。
