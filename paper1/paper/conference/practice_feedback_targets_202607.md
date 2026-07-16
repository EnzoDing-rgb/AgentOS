# BudgetFlow / AgentOS 练手投稿目标（2026 年 7 月）

时间基准：**2026-07-16**。

**原则：** 只列 **现在还能交、拿反馈练手** 的口。已过注册/截稿的（如 SoCC R2 新开稿）不写。Agent / LLM / budget / routing / SWE-bench **能蹭边就行**——目标是交出去拿审稿，不是保中。

---

## 调研置顶：#3 ICECCS / #4 APSEC Technical / #5 AAAI-27（2026-07-16）

调研对象对应下表 **#3–#5**。BudgetFlow 核心是：**任务批共享硬预算 + Task Value + 模型档位分配 + SWE-bench 类 verifier + TRV**。

### 截稿：3 和 4 同日是巧合，不是搞混

| # | 会 | 官网当前截稿 | 证据与说明 |
|---|-----|--------------|------------|
| **3** | **ICECCS 2026** | abs+full **07-20 AoE** | [正式站](https://formal-analysis.com/iceccs/2026/)：原 06-29 / 07-06，**延期**到 07-20。EasyChair=`iceccs2026`。勿投同名山寨会（Electronics…） |
| **4** | **APSEC 2026 Technical** | Full **07-20**；Abstract optional **07-13** | [Dates](https://conf.researchr.org/dates/apsec-2026) 与 [Technical Track](https://conf.researchr.org/track/apsec-2026/apsec-2026-technical-track)（约 **07-16** 更新）。更早缓存曾写 Full=07-13，后改到 07-20 |
| **5** | **AAAI-27 Main** | abs **07-21** / full **07-28** | [投稿说明](https://aaai.org/conference/aaai/aaai-27/submission-instructions/) |

**结论：** 两个独立 CCF **C**、都偏 SE，各自延期/改期后 **碰巧撞在 07-20**；不是同一会议、也不是文档抄串。

### 领域像不像？

| 会 | 能蹭边？ | 有没有几乎同题？ |
|----|----------|------------------|
| **ICECCS** | CFP 明文含 *LLM-based Agents / AI4SE / efficiency* | **几乎没有** batch shared budget + value ledger 主线；会更偏复杂系统/形式化/可靠 AI |
| **APSEC** | 近年 AI4SE / multi-agent SE 常见 | **少见** batch-value-budget；更多生成/协议/修复 |
| **AAAI** | **最近** | **最接近**：已有 budget-aware multi-agent / LLM routing，但多数不是 SWE-bench 批级 TRV |

### 写法 / baseline / 数据集（往年与近邻）

**ICECCS（LNCS；Full≤20 含参考文献；Short≤11；单盲）**

- **写法：** 问题 → 方法/系统 → 案例或实验 → 讨论；口味偏复杂系统与可靠 AI。包装成 *agent 工作负载下的资源/预算治理*，少写成纯 SE bake-off。
- **典型 baseline：** 单模型直接跑、无预算多代理流水线。
- **典型数据：** HumanEval/MBPP 类或系统案例；**很少**固定 30-task SWE-bench 批 + 美元硬帽主表。
- **对 BudgetFlow：** topic 开了，同题少；审稿人可能问「复杂系统在哪」。

**APSEC Technical（IEEE；≤10 含参考文献；双盲）**

- **写法：** 标准 SE：贡献点、RQ、实验、威胁有效性。近年有 AI4SE 会话。
- **近邻例：** SEMAP（APSEC 2025 ERA）多代理协议 + MAST 失败计数，数据为函数级/部署级开发与漏洞子集；Chart2Code-MoLA（APSEC 2025 Technical）含 *adaptive expert routing*（MoE 路由，不是 batch budget）。
- **典型 baseline：** 无协议/无路由对照；你们应对标 **cheap-only / strong-only / learned router / budget-only**。
- **对 BudgetFlow：** 能进 AI4SE；双盲勿露作者/仓库身份。

**AAAI Main（正文≤7 + 参考文献至多总 9；checklist）**

- **写法：** 形式化 → 方法 → 强 baseline → 消融；用 multiagent / resource allocation 语言，少写 harness。
- **近邻例：** **BAMAS（AAAI-26）** budget-aware multi-agent：ILP 选 LLM + RL 选拓扑；baseline≈AutoGen/MetaGPT/greedy；数据≈代码生成+数学推理；报告准确率+成本（可降约 86%）。邻域常引 RouteLLM / FrugalGPT / MasRouter（多为 **per-query/per-task**）。
- **对 BudgetFlow：** 审稿最懂 budget/routing；必须讲清 **batch-level value governance ≠ 单查询路由 ≠ 只选拓扑**。

### 实操对齐（投这三会时）

| 会 | 建议叙事 | 建议 baseline | 建议数据叙事 |
|----|----------|---------------|--------------|
| ICECCS | AI-driven complex workload / resource control | 无预算 agent vs 预算治理 | SWE-bench 作复杂仓库任务实例 |
| APSEC | AI4SE + cost-aware agent execution | cheap/strong/router/budget-only | 固定 30-task 批 + shared $ 帽；双盲 |
| AAAI | 与 BAMAS/RouteLLM **层级不同**（批级 value） | 同上 + 点名层级差异 | SWE-bench + TRV；少写 harness |

**差异化一句：** 这三会里几乎没人写 **Task Value + 批共享硬预算 + TRV**——既是 novelty，也是要讲清边界的审稿风险。

---

## 0. 可以立刻练手了（按截稿早晚）

| # | 会 | 档次 | 截稿 | 反馈节点 | 蹭边角度 |
|---|-----|------|------|----------|----------|
| **1** | **AgenticDev 2026** | 无 CCF（workshop） | **07-15** AoE（已投 #68） | 通知 **08-21** | agentic SE；short/vision 最快 |
| **2** | **MAS-GAIN 2026** | 无 CCF（workshop） | abs **07-17** / full **07-22** AoE | 通知 **08-23** | multi-agent / routing / tool |
| **3** | **ICECCS 2026** | CCF **C** | **07-20** AoE（已延期） | 通知 **08-24** AoE | LLM agents / AI4SE |
| **4** | **APSEC 2026 Technical** | CCF **C** | Full **07-20**（abs optional **07-13**） | 通知 **09-14** | SE technical；正式会练手 |
| **5** | **AAAI-27 Main** | CCF **A** | abs **07-21** / full **07-28** | Phase 1 **09-24**（拒也能见审稿） | multiagent / resource allocation |
| **6** | **RASE 2026** | 无 CCF（workshop） | **07-24** AoE | 以官网为准 | trustworthy ASE / cost-aware eval |
| **7** | **ARR Aug → EACL 2027** | *CL 审稿；EACL=CCF **B** | **08-03** | reviews **09-07**；meta **10-08** | LLM Agents / code / evaluation |
| **8** | **APSEC 2026 ERA** | CCF **C** | **08-03** | 通知 **09-21** | early / preliminary 反馈 |

**Dual-submission：** AAAI 与 ARR（及多数正式会 archival）**不能并行**。Workshop 一般可并行，以各自 CFP 为准。一次主投只锁一个 archival。

---

## 1. Workshop（无 CCF；ASE 主会 A 不继承）

Workshop / Short / Demo **不计** CCF 推荐会议条目。挂靠主会 ASE 2026 = CCF **A** 只适用于主会 Research 等 full paper。

### 1.1 AgenticDev 2026

- **CCF：无** · @ ASE 2026
- **截稿：** **2026-07-15 AoE**（今天/明天；以官网为准）
- **页数：** Full ≤10 / Short ≤5 / Demo ≤5（+2 页参考文献）
- **投稿：** <https://agenticdev2026.hotcrp.com>
- **CFP：** <https://conf.researchr.org/home/ase-2026/agenticdev-2026>
- **匹配：** agentic SE 极强；适合 short/vision 求反馈
- **立刻动作：** **今天交**（最紧）

### 1.2 MAS-GAIN 2026

- **CCF：无** · @ ASE 2026
- **截稿：** abs **07-17** / full **07-22** AoE（已延期，以 [站点](https://masgain.github.io/masgain/masgain2026/) 为准）
- **页数：** Regular ≤8 / Short ≤4
- **投稿：** <https://easychair.org/conferences/?conf=masgain2026>
- **CFP：** <https://conf.researchr.org/home/ase-2026/mas-gain-2026>
- **匹配：** multi-agent / routing / tool / experience
- **立刻动作：** **先交 abstract（07-17）→ full（07-22）**

### 1.3 RASE 2026

- **CCF：无** · @ ASE 2026
- **截稿：** **2026-07-24 AoE**
- **页数：** Regular ≤8 / Short-Demo ≤4 / Position ≤2
- **投稿：** <https://easychair.org/conferences/?conf=rase2026>
- **CFP：** <https://conf.researchr.org/home/ase-2026/rase-2026>
- **匹配：** trustworthy ASE / benchmark / cost-aware evaluation
- **立刻动作：** 本周可写，**07-24 前交**

---

## 2. 正式会练手（仍开着的 C / A / ARR）

### 2.1 ICECCS 2026

- **CCF：C** · abs+full **07-20 AoE**（已延期；通知约 **08-24**）
- 官网：<https://formal-analysis.com/iceccs/2026/> · EasyChair：<https://easychair.org/conferences/?conf=iceccs2026>
- Topic 含 LLM-based Agents、AI4SE；领域调研见文首「调研置顶」
- **立刻动作：** **07-20 前交**

### 2.2 APSEC 2026 Technical

- **CCF：C** · Full **07-20**（abs optional **07-13**）· 通知 **09-14**
- EasyChair：<https://easychair.org/conferences/?conf=apsec2026>
- 双盲 IEEE；领域调研见文首「调研置顶」
- **立刻动作：** **07-20 前交**

### 2.3 AAAI-27 Main Technical Track

- **CCF：A** · 两阶段审稿；**Phase 1 被拒也能立刻看到审稿**（练手反馈强）
- **截稿：** abstract **07-21 AoE**；full **07-28**；补充 **07-31**
- **页数：** 正文 ≤7 + 参考文献至多总 9 页；reproducibility checklist
- **投稿：** [OpenReview](https://openreview.net/group?id=AAAI.org/2027/Conference)
- **CFP：** [Main Track](https://aaai.org/conference/aaai/aaai-27/main-technical-track-call/) · [说明](https://aaai.org/conference/aaai/aaai-27/submission-instructions/)
- **包装：** multi-agent / planning / resource allocation；少写纯 harness
- **立刻动作：** **本周交 abstract（最晚 07-21）→ 07-28 full**
- **注意：** 投后勿并行其他 archival

### 2.4 ARR August 2026 → EACL 2027

- ***CL 审稿**；commit EACL = CCF **B**
- **为何练手：** ARR **非 desk-reject 必出 reviews**
- **截稿：** **08-03 AoE**；作者 reviewer 注册 **08-05**
- **反馈：** reviews due **09-07**；response **09-14–19**；meta **10-08**；commit EACL **10-11**
- **来源：** [ARR dates](http://aclrollingreview.org/dates) · [EACL CFP](https://2027.eacl.org/calls/papers/)
- **立刻动作：** 若不上 AAAI（或已撤），**08-03 交 ARR**；与 AAAI **不可并行**

### 2.5 APSEC 2026 ERA

- **CCF：C** · ERA **08-03** · 通知 **09-21**
- EasyChair：<https://easychair.org/conferences/?conf=apsec2026>
- **立刻动作：** early / preliminary 叙事，**08-03 前交**

---

## 3. 本周执行顺序（只练手）

1. **今天–明天：** AgenticDev（**07-15**）— 最紧  
2. **本周：** MAS-GAIN abstract（**07-17**）→ ICECCS / APSEC Technical（**07-20**）  
3. **若要严审练手：** AAAI abstract（**07-21**）→ full（**07-28**）  
4. **下周：** RASE（**07-24**）；MAS-GAIN full（**07-22**）  
5. **八月初：** 不上 AAAI 则 ARR 或 APSEC ERA（**08-03**）

**不在本表：** SoCC R2 新开稿（registration 已过）、九月及以后尚未到练手窗口的会。
