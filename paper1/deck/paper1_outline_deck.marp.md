---
marp: true
theme: gaia
size: 16:9
paginate: true
footer: BudgetFlow · 论文汇报大纲
style: |
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
  section {
    font-family: 'Noto Sans SC', 'PingFang SC', 'Hiragino Sans GB',
      'Source Han Sans SC', 'Microsoft YaHei', 'WenQuanYi Micro Hei', SimHei, sans-serif;
    font-size: 26px;
    line-height: 1.58;
    letter-spacing: 0.018em;
    color: #1e293b;
    background: linear-gradient(165deg, #f8fafc 0%, #f1f5f9 48%, #eef2ff 100%);
    box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.25);
  }
  h1 {
    font-weight: 700;
    font-size: 42px;
    color: #0f172a;
    margin-bottom: 0.35em;
    letter-spacing: -0.02em;
  }
  h2 {
    font-weight: 600;
    font-size: 32px;
    color: #1e3a8a;
    padding-bottom: 0.22em;
    margin-top: 0;
    margin-bottom: 0.55em;
    border-bottom: 4px solid #3b82f6;
  }
  h3 {
    font-size: 24px;
    color: #334155;
    font-weight: 600;
    margin-top: 0.45em;
    margin-bottom: 0.35em;
  }
  strong { color: #1d4ed8; font-weight: 600; }
  ul, ol { margin: 0.35em 0 0 0; padding-left: 1.15em; }
  li { margin: 0.38em 0; }
  p { margin: 0.5em 0; }
  section.lead {
    background: linear-gradient(155deg, #0c1222 0%, #1e3a5f 38%, #2563eb 55%, #4f46e5 100%);
    color: #e8eef9;
    justify-content: center;
    box-shadow: none;
  }
  section.lead h1 {
    color: #ffffff;
    font-size: 52px;
    text-shadow: 0 4px 28px rgba(0,0,0,.4);
    border: none;
  }
  section.lead h2 {
    color: #bfdbfe;
    font-size: 30px;
    font-weight: 500;
    border: none;
    margin-top: 0.55em;
    line-height: 1.45;
  }
  section.lead h3 {
    color: #94a3b8;
    font-size: 20px;
    margin-top: 1.25em;
    font-weight: 400;
  }
  section.lead footer { color: #64748b; }
  table {
    width: 100%;
    font-size: 17px;
    border-collapse: separate;
    border-spacing: 0;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 8px 28px rgba(15, 23, 42, 0.12);
    margin-top: 0.45em;
  }
  th {
    background: linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%);
    color: #fff !important;
    font-weight: 600;
    padding: 14px 11px;
    text-align: left;
    font-size: 17px;
  }
  td {
    padding: 12px 11px;
    border-bottom: 1px solid #e2e8f0;
    background: #fff;
    vertical-align: top;
    font-size: 16px;
    line-height: 1.45;
  }
  tr:nth-child(even) td { background: #f8fafc; }
  tr:last-child td { border-bottom: none; }
  code {
    font-family: 'JetBrains Mono', 'Noto Sans Mono CJK SC', Consolas, monospace;
    font-size: 0.9em;
    background: #eff6ff;
    color: #1e40af;
    padding: 0.14em 0.4em;
    border-radius: 5px;
  }
  pre {
    font-family: 'JetBrains Mono', 'Noto Sans Mono CJK SC', monospace;
    font-size: 14px;
    line-height: 1.42;
    background: linear-gradient(180deg, #ffffff 0%, #f1f5f9 100%);
    border-left: 5px solid #3b82f6;
    border-radius: 10px;
    padding: 18px 20px;
    text-align: left;
    box-shadow: 0 6px 22px rgba(15, 23, 42, 0.08);
  }
  section.diagram pre {
    font-size: 15px;
    line-height: 1.48;
    padding: 20px 22px;
  }
  section.diagram-tall pre {
    font-size: 13px;
    line-height: 1.38;
    padding: 14px 16px;
  }
  blockquote {
    border-left: 5px solid #6366f1;
    background: rgba(255,255,255,0.85);
    margin: 0.55em 0;
    padding: 0.65em 1.1em;
    color: #475569;
    border-radius: 0 10px 10px 0;
    font-size: 24px;
    line-height: 1.55;
  }
---

<!-- _class: lead -->
<!-- _paginate: false -->

# BudgetFlow

## 面向 Agent 工作流的动态预算路由机制

### 论文汇报大纲 · Marp 幻灯片

---

## 1. 论文主线：从单次调用到整条 workflow

在一个甚至多个完整的 agent workflow（每个 workflow 包含多步 LLM 调用）中，核心问题是：如何利用 **workflow 级的结构信息**——例如哪一步更关键、还剩多少预算、多个 workflow 之间如何共享同一套后端资源——来做 **整体的成本与质量分配**，而不是孤立地对每一次调用做启发式决策。

本文的研究问题可以表述为：当优化单位从「一次 LLM 请求」提升到「一个完整的 agent workflow」，并且多个 workflow **共享同一个预算池**以及多条后端路径上的 **RPM / 并发配额**时，**显式维护 workflow 状态**是否会改变 **固定预算**约束下的最终成功率？若答案是肯定的，则需要进一步追问：收益主要来自 **预算配速**、**步骤重要性**、**进展先验**，还是 **多 workflow 调度**？本文的目标之一，是把 agent workflow 上的 LLM 花费变成一个 **可审计、可消融、可复现** 的实验对象。

---

## 2.1 三个研究问题（Research Questions）

下表概括三条研究问题及其对应的主要观测指标；措辞与论文大纲一致，便于对照实验设计与图表。

| RQ | 研究问题（完整表述） | 主要指标 |
| :--- | :--- | :--- |
| **RQ1** | 多个 workflow 在 **同一固定预算** 与 **共享后端限流** 条件下并行运行时，预算浪费主要发生在何处？哪些运行时限制最先成为系统瓶颈？ | 预算违规率、HTTP 429 比例、队列延迟、可回收预算、僵尸任务取消次数等 |
| **RQ2** | 在 **相同预算** 下，利用 workflow **阶段状态** 做多步模型档位选择，是否比「仅按 workflow 粒度」或「仅按预算」的调度策略 **resolve 更多** SWE-bench 类任务？ | 固定预算下的 resolved rate；对比 **BudgetFlow Full**、**Workflow-Level Router**、**Budget-Only Step Scheduler** |
| **RQ3** | 当频繁更换模型削弱 **prefix-cache** 局部性时，基于 workflow 阶段的调度是否仍能带来 **净收益**？ | 换模频率、prefill 延迟、cached-token 占比；对比 **BudgetFlow Full** 与 **BudgetFlow Cache-Sticky** |

---

## 2.2 本文的独特贡献（五点）

1. **连续质量视角**：将 LLM 输出质量建模为 **[0, 1]** 区间上的连续变量，便于在同一框架内讨论性价比与帕累托权衡，而不是只用离散成败标签。
2. **预算硬约束与动态配速**：在运行时维持硬预算上限的同时，用 **`budget_factor`** 近似刻画预算的 **边际价值 λ**，从而指导「该省则省、该花则花」的配速行为。
3. **显式任务价值 w_i**：由调用方声明的可解释权重信号，使系统在多个 workflow 并存时能够与业务优先级对齐，而非隐含在黑盒策略中。
4. **僵尸止损（ZombieDetector）**：识别并截断那些 **成本持续上升但质量或进展不再提升** 的无效调用链，释放预算与并发槽位。
5. **无需训练的部署路径**：整体采用 **优化启发式**即可上线，对比需要大规模离线训练或 RL 的方法更加 **轻量、即时**，且易于作为强基线参与消融。

---

## 3. 项目架构（四层 BudgetFlow）

下方的结构图说明：`N` 步 LLM 调用构成的 agent workflow 与 `J` 个并发 workflow 进入 BudgetFlow 后的分层职责；其中 **Governor、止损层与调度层** 与具体 routing policy 解耦，**ModelSelector** 是默认的可插拔路由策略入口。

<!-- _class: diagram -->

```
Agent Workflow（N 个 LLM 调用步骤）× J 个并发 workflow
        │
        ▼
═══════════════════ BudgetFlow ═══════════════════
│ 【约束层】Governor                           │  ← policy-agnostic
│   预算预留 / 结算 + 后端级限流 + 并发准入       │
│                                              │
│ 【优化层】ModelSelector（可插拔）             │  ← 唯一 routing policy
│   本文默认：预计进展增益 + budget_pressure    │
│   可替换为：RL policy / CARROT / …           │
│                                              │
│ 【止损层】ZombieDetector + Preemption        │  ← policy-agnostic
│   僵尸截断 + 交互式任务抢占                   │
│                                              │
│ 【调度层】Multi-Workflow Scheduler           │  ← policy-agnostic
│   跨 workflow 协调 + admission control       │
═══════════════════════════════════════════════
        │
        ▼
LLM 后端池 → events.jsonl → 指标计算
```

---

## 4. 相关工作分类（与 §5 表格同一批文献）

下列条目与下一节一览表中的「§4 聚类」列 **一一对应**；表中 **不会** 收录未在此出现的论文（例如 **Aragog**、**Parrot** 等推理栈仅在附录分层示意中出现）。

- **操作系统资源管理**：AgentRM，AgentCgroup，AIOS，pMVX  
- **任务–模型路由**：RouteLLM，CARROT，OmniRouter  
- **分步骤强化学习的模型路由策略**：BoPO（同类还包括面向工具 / 多模型编排 RL 的 **xRouter**）  
- **GPU 资源预算控制**：Athena-Serve  
- **硬件资源编排**：Murakkab  

---

## 5. 符号 ①②③④ 的含义（读表前先对齐定义）

在相关工作一览表中，列 **①～③** 与 **④** 的含义如下（与 `paper1_ppt_outline.md` 完全一致）：

- **①**：多个并发 agent workflow **共享美元或 token 形式的硬顶预算**，并在运行时配套 **预留–结算** 语义。  
- **②**：在 **同一条** agent 轨迹上，对多轮 LLM 调用做 **带状态** 的档位选择（而非彼此独立的 per-query 决策）。  
- **③**：**不依赖特定任务域**的大规模离线训练或强化学习即可运行（若仅需小规模表格标定仍记为 ✓）。  
- **④**：与本文的一句话差分说明（概括该方法 **不是什么** 或 **缺哪一块**）。

---

## 5. 相关工作一览（上：本文至 OmniRouter）

| §4 聚类 | 工作 | ① | ② | ③ | ④ 与本文 |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **（本文）** | **BudgetFlow** | ✓ | ✓ | ✓ | — |
| 操作系统资源管理 | **AgentRM**（arxiv:2603.13110） | ✗ | ✗ | ✓ | 侧重 RPM / 稳定性 / 回收；**非** API 美元硬账本 |
| 操作系统资源管理 | **AgentCgroup**（arxiv:2602.09345） | ✗ | ✗ | ✓ | 主机 CPU / 内存 **cgroup** 隔离 |
| 操作系统资源管理 | **AIOS**（arxiv:2403.16971） | ✗ | ✗ | ✓ | **Agent OS** 抽象与资源视图 |
| 操作系统资源管理 | **pMVX**（Agentic OS Workshop 2026） | ✗ | ✗ | ✗ | **Kernel** 多版本策略自调优 |
| 任务–模型路由 | **RouteLLM**（Ong et al., 2024） | ✗ | ✗ | ✗ | Strong / weak **偏好学习**；无运行期预算账本 |
| 任务–模型路由 | **CARROT**（Somerstep et al., 2025, arxiv:2502.03261） | ✗ | ✗ | ✓ | **Per-query** minimax；缺跨步联合状态 |
| 任务–模型路由 | **OmniRouter**（Mei et al., 2026） | ✗ | ✗ | ✗ | **Per-query** Lagrangian；非多 workflow **共享池** |

---

## 5. 相关工作一览（下：BoPO 至 Murakkab）

| §4 聚类 | 工作 | ① | ② | ③ | ④ 与本文 |
| :--- | :--- | :---: | :---: | :---: | :--- |
| 分步骤强化学习的模型路由策略 | **BoPO** / Budget-Aware Agentic Routing（Zhang et al., 2026, arxiv:2602.21227） | ✗ | ✓ | ✗ | **单任务** RL 逐步路由；可作 **ModelSelector**；无 **①** |
| 分步骤强化学习的模型路由策略 | **xRouter**（arxiv:2510.08439；*Training Cost-Aware LLMs Orchestration via RL*） | ✗ | ✓ | ✗ | RL **工具 / 多模型编排**；非多 agent **共享池**账本 |
| GPU 资源预算控制 | **ATHENA-Serve**（Liang & Wu；ICLR 2026 投稿，OpenReview #10330） | ✗ | ✗ | ✗ | **Serving** 长尾与 KV / 算力 **budget**；非 agent **计价**意义的 **①** |
| 硬件资源编排 | **Murakkab**（待投） | ✗ | ✗ | ✗ | **云 / workflow** 级成本与并行；无 **美元或 token 硬顶** 账本 |

**Murakkab**、**ATHENA-Serve** 等与本文可在工程上 **纵向叠放**（Serving 与编排之上再叠 workflow 花费治理）；表中仅收录 §4 已索引文献。

---

## 5. 论文边界：本文明确覆盖的范围

**单一预算主体（single budget owner）**：多个并发 workflow **共享同一预算池**以及后端 **RPM / 并发配额**；全局账本、准入控制、结算、ZombieDetector、以及跨 workflow 调度器共同构成本文的 **runtime** 研究命题。

**决策单位**：每一次 workflow 内的 LLM 调用步骤，联合 **全局预算池状态**；评测场景常与 **SWE-bench Verified** 上的批量并发运行以及 **固定总预算** 等设定对齐，以便报告在相同花费下的任务完成率。

---

## 5. 论文边界：本文不 Claim 的内容（留作扩展）

- **Multi-tenant**：跨团队预算与服务等级协议（SLA）——自然的续作方向，与 §8 中参照 vLLM 的 **第二阶段叙事**一致。  
- **非 GPU Serving 独占**：本文 **不主张**取代 Athena-Serve / vLLM 一侧关于 **KV / batch** 的全集最优；本文焦点是 **workflow 花费治理与步骤配额**。  
- **ZombieDetector**：作为运行时 **止损构件**可消融验证；**不是**独立 RL / ML 方法论层面的主贡献声明。  
- **成本模型**：不绑定具体云厂商 SKU；采用抽象的 **dollar / token** 计价即可复现实验结论。

---

## 6. 关键差异分析（轴向对照）

本节从三条轴线对照本文与既有工作：**Budget-Aware Agentic Routing（BoPO）**、**per-query 路由器**、以及 **OS 启发式系统**。符号 **①②③** 与 §4、§5 中的聚类含义一致，便于读者把「方法类别」和「能力勾选」对应起来。

接下来三页分别给出 **6.1 BoPO**、**6.2 Per-query Routers**、**6.3 OS-Inspired** 的对照表。

---

## 6.1 本文 vs Budget-Aware Agentic Routing（BoPO）

这是 **最重要** 的一组对比：BoPO 代表「逐步 RL 路由」路线，本文强调「免训练的全局治理底座 + 可插拔选模」。

| 维度 | Budget-Aware Agentic Routing（BoPO） | **本文（BudgetFlow）** |
| :--- | :--- | :--- |
| **方法** | 强化学习（BoPO）：需要训练数据与 GPU 训练 | 优化启发式：**无需训练**，可即时部署 |
| **可解释性** | RL 策略难以向工程团队解释 | **边际性价比排序** 与 **`budget_factor`**，决策链路可解释 |
| **预算处理** | 训练期 soft-budget，推理期 BCD 等机制 | 运行时 **hard budget** 硬约束与账本语义 |
| **任务价值** | 隐含在策略参数中（由 RL **学出**） | 显式 **w_i**（调用方声明） |
| **止损** | 无专门机制 | **ZombieDetector** 截断无效调用链 |
| **互补性** | 本文启发式可作为 RL 的 **warm-start 基线** | — |

---

## 6.2 本文 vs Per-query Routers（RouteLLM, CARROT, OmniRouter）

| 维度 | Per-query Routers | **本文（BudgetFlow）** |
| :--- | :--- | :--- |
| **决策粒度** | 每条 query **独立**追求局部最优 | **跨 N 步**满足联合预算约束 |
| **状态** | 本质上 **无状态**（或不追踪全局 burn rate） | **有状态**：跟踪剩余预算与消耗速率 |
| **预算** | 忽略预算，或只做 per-query 成本预测 | **Hard budget**：硬上限贯穿运行时 |
| **任务价值** | 通常 **不区分** 任务优先级 | 显式 **w_i** |

---

## 6.3 本文 vs OS-Inspired 工作（AgentRM, AgentCgroup, AIOS, pMVX）

| 维度 | OS-Inspired 工作 | **本文（BudgetFlow）** |
| :--- | :--- | :--- |
| **核心问题** | 系统 **稳定性** 与 **资源隔离** | **质量–成本** 联合优化 |
| **优化目标** | 延迟、吞吐量、隔离 | QWCR、**Q / 成本**、帕累托前沿 |
| **资源类型** | CPU、内存、并发度、RPM | LLM 调用的 **质量与货币化成本** |

---

## 7. 最接近的相关工作：BoPO（论文信息）

**Budget-Aware Agentic Routing via Boundary-Guided Training**（Zhang et al., arXiv:2602.21227，2026）。

核心算法 **BoPO** = **Boundary-Guided Policy Optimization**：在 agent 的 **每一步** 上做 RL 路由。训练流程通常包含 **BoSFT**；在线阶段配合 **GRPO** 等边界引导手段，用来缓解 **稀疏奖励** 带来的优化困难。

---

## 7.1 BoPO 与本文的整体关系

BoPO 产出的是 **单任务、逐步（step 级）路由策略**；在 BudgetFlow 的分层架构里，它正好对应 **ModelSelector 的一种可插拔实现**。本文的独立贡献在于 **运行时治理底座**：全局账本（**预留 / 结算**）、硬预算与后端 **RPM / 并发准入**、多 workflow 调度器、以及 ZombieDetector 等横切机制。

因此：**BoPO 若脱离该底座**，无法单独解决「多并发 workflow **共享同一全局预算与配额**」时的系统性问题；反过来，**底座与 BoPO 兼容**：可以把 RL 策略接入 ModelSelector，由运行时继续保证 **全局硬约束**，并在系统层面放大其每一步决策的收益。

---

## 7.2 极简场景：与 SWE-bench 类任务对齐

设想 **单条** 代码修复轨迹：**阅读 issue → 搜索仓库 → 阅读文件 → 定位根因 → 撰写补丁 → 运行测试 → 迭代**；若 **单任务** 预算约为 **0.5 美元**，每一步在强模型与弱模型之间抉择。

**BoPO** 的路线是：在同 **任务域** 的大量轨迹上进行预训练；执行时每一步依据上下文、历史以及 **该任务剩余预算** 输出档位；奖励与 **该任务** 的成败及花费绑定，边界引导促使模型在 **关键步骤** 更愿意调用强模型。

**本文的评测焦点** 则更常落在 **多实例并发**：例如多个实例共享同一 **总预算 B_total**；系统在 **全局就绪的 LLM 调用集合** 上，依据加权边际进展、budget pressure 等量在 **系统级** 做择优，优化的是 **汇总完成率**，而不限于单条轨迹内部的局部最优。

---

## 7.3 BudgetFlow vs BoPO：层级与能力对照

| 维度 | BudgetFlow（本文） | BoPO（相关工作） |
| :--- | :--- | :--- |
| **优化目标（典型）** | 在共享硬预算与后端配额下最大化 **全局**任务完成率（或等价系统指标） | **单任务**内部预算–成功率折中；**单轨迹**意义下的局部最优 |
| **决策视野** | 全局账本 + **跨 workflow** 的就绪 / 排队集合 | 单 trajectory + **该任务**剩余预算 |
| **预算与配额** | 运行时 **预留–结算**、硬上限、429 与并发准入 | 训练期 soft-budget + 推理 BCD 等（**非**本文级原子账本） |
| **止损与回收** | ZombieDetector、抢占、释放预留与槽位 | **无**对等机制 |
| **部署** | Training-free，跨框架接入 | **域专属**轨迹与训练；换域成本高 |
| **重叠与组合** | Step 重要性驱动路由；**BoPO 策略可插 ModelSelector** | 仅解决逐步选模；**不替代**全局治理层 |

---

## 7.4 BoPO 明确不覆盖的差分点（本文补齐）

- 多个 agent **共享单一全局预算** 时的跨任务分配，以及 **前期耗光预算、后期饥饿** 的现象。  
- 生产环境中 **RPM / 并发** 的强准入与 **HTTP 429** 治理。  
- **僵尸或无进展** 任务长期占用预算与槽位时的 **回收** 机制。  
- **本地推理 / KV cache** 切换代价的显式建模。  
- **零域冷启动** 场景下、**免训练** 的可部署路由策略。

---

## 8. 叙事参照 vLLM（第一段：问题分期）

**vLLM** 是加州大学伯克利分校 2023 年发布的开源 LLM 推理引擎（**SOSP 2023**）。其首篇论文处理的是 **single-tenant** 问题：给定一台 GPU 服务器上的多个独立推理请求，引擎应如何 **batch 与调度** 以提升吞吐？该工作隐含假设硬件由 **单一运营方** 持有，**并未**对竞争用户之间的策略仲裁展开论述。

后续工作——例如 **Andes（OSDI 2024）**、**SGLang router** 等——在相同底层机制之上，引入 **multi-tenant** 设定：多个用户、团队或服务共享推理基础设施，系统在 **优先级、配额、SLA** 等约束下进行仲裁。

---

## 8. 叙事参照 vLLM（第二段：两阶段研究路径）

「**先优化单一决策主体，再引入多主体仲裁**」这种两阶段演进，是 systems 社区较为成熟的研究路径：**第一阶段**建立核心机制——在 vLLM 的语境下即 **paged KV-cache** 与 **continuous batching**；**第二阶段**在 single-tenant 案例被充分理解之后，再在该机制之上叠加 **政策层（policy layer）**。

BudgetFlow 自觉地遵循同一条路径：**本文（paper 1）** 讨论 **single-budget-owner**：某一实体持有固定的算力或 token 预算，在其上并行运行多个 agent workflow；贡献在于构造 **cost-model-agnostic**、在该预算之上完成 **跨 workflow 分配** 的调度器。

---

## 8. 叙事参照 vLLM（第三段：续作与本文定位）

自然的续作方向是 **multi-tenant agent 计算资源分配**：多个团队或外部客户各自持有 **独立预算、优先级与 SLA**，共享同一 agent 执行底层。由此会带来 **cross-tenant 隔离**、异构负载混合下的 **quota 仲裁**、以及 **budget-aware admission control** 等新问题——这些问题超出本文 scope，但都可视为本文框架的 **直接扩展**。

重要的是：本文调度器的 **cost-model-agnostic** 性质在 multi-tenant 扩展中仍可保留——不同租户可采用 **不同的底层模型与成本结构**，而 **无需修改仲裁层**。因此我们把本文定位为：**未来 multi-tenant workflow 研究可以在其上搭建的 single-tenant 基础层**。

---

## Appendix A.1 · BudgetFlow 集成架构（三种接入方式）

<!-- _class: diagram-tall -->

```
+----------------------------------+       +-----------------------------+
| LangChain / SWE-agent / AutoGen  |       | Self-built agent platform   |
+----------------------------------+       +-----------------------------+
       |                    |                         |
       | Proxy mode:        | Callback mode:          | Explicit mode:
       | LLM request msgs   | tool events + metadata  | task_type + w_i
       v                    v                         v
+------------------+ +------------------+      +------------------+
| BudgetFlow Proxy | | BudgetFlow Adapter|     | BudgetFlow SDK   |
+------------------+ +------------------+      +------------------+
          \                  |                         /
           \                 |                        /
            +----------------+-----------------------+
                             |
                             v
                    +----------------------+
                    | BudgetFlow Runtime   |
                    +----------------------+
                             |
          +------------------------------------------+
          | Governor: budget + backend quotas       |
          +------------------------------------------+
                             |
       +---------------------------------------------+
       | ModelSelector: budget_pressure + importance|
       +---------------------------------------------+
                             |
          +--------------------------------+
          | Multi-workflow Scheduler       |
          +--------------------------------+
                             |
          +--------------------------------+
          | LLM Backend Pool               |
          +--------------------------------+
```

---

## Appendix A.2 · Agent 计算栈分层对比（全景示意）

<!-- _class: diagram-tall -->

```
+-----------------------------------------------------------------------------+
| Murakkab（顶层）                                                             |
| 全栈 SLO 编排：在整个 agent 工作流维度全局优化硬件成本，并力争按时完成任务    |
| 核心问题：云侧如何用更少 GPU 跑完所有 agent · 目标：最小化云硬件成本          |
| 决策单位：整条工作流 · 预算：仅优化单位成本，无美元硬上限                     |
+-----------------------------------------------------------------------------+
                                      ↓
+-----------------------------------------------------------------------------+
| BudgetFlow（上层）                                                           |
| 全局预算：在固定金额（例如「100 美元」）内尽可能多解决任务，不超支也不浪费    |
| 核心问题：固定预算下如何最大化成功率 · 决策单位：单步 + 全局预算池           |
| 预算：**硬上限**是核心约束                                                   |
+-----------------------------------------------------------------------------+
                                      ↓
+-----------------------------------------------------------------------------+
| Aragog（中层，附录示意）                                                     |
| 动态模型路由：每一步选何种模型能让 GPU 尽快完成负载                           |
| 核心问题：GPU 尽量不休眠 · 目标：系统吞吐 · 预算：不为单次调用计价           |
+-----------------------------------------------------------------------------+
                                      ↓
+-----------------------------------------------------------------------------+
| Parrot（底层，附录示意）                                                     |
| 多轮请求流水线：同一 agent 的多轮对话如何更快执行                             |
| 核心问题：单次请求的延时 · 决策单位：单请求内部 token 流 · 预算：不涉及金额   |
+-----------------------------------------------------------------------------+
                                      ↓
| LLM Backends + GPU / CPU Hardware                                           |
```

**说明**：**Aragog** 与 **Parrot** 与 §5 文献索引 **正交**，仅在分层故事中帮助听众建立直觉；正式相关工作仍以 §4–§5 为准。
