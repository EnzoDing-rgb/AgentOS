# BudgetFlow：七八月 CCF 投稿目标

时间基准：2026 年 7 月 22 日。

## 怎么核的（先读这段）

本文件不用第三方截稿聚合站当权威。核对分两步：

1. **会议是否在 CCF 目录里**：打开中国计算机学会官网「推荐国际学术会议和期刊目录」对应领域页，看第七版推荐列表。  
   - 人工智能会议 A 类（2026-07-22 直接打开官网页核对）：[ccf.org.cn · 人工智能](https://www.ccf.org.cn/Academic_Evaluation/AI/)  
     列出的 A 类会议是：AAAI、NeurIPS、ACL、CVPR、ICCV、ICML、IJCAI。  
   - 说明：CCF 2026-03-31 正式通告里写过 ICLR 进入 A 类、IJCAI 调整为 B 类；但截至今天官网「人工智能」会议表仍显示 IJCAI 为 A、且未列出 ICLR。本文以**今天能打开的官网领域页**为准，并记下这一不一致。  
   - 正式通告入口：[第七版目录发布说明](https://www.ccf.org.cn/Academic_Evaluation/By_category/)

2. **截稿与投稿规则**：对每一个候选会，打开该会**官方征稿页 / OpenReview / HotCRP**，记录截止日期与页数。下面凡写截稿，都附官方链接。

**本窗口（2026-07-22 起两到四周）实际做了什么：**

| 动作 | 结果 |
|------|------|
| 逐一核对中国人工智能 A 类七个会的近期截稿 | 当前仍开放、且可从零新开的，只有 **AAAI 2027** |
| 核对中国软件工程方向近期仍开放的正式轨 | **APSEC 2026 早期研究成果轨**（技术全文轨已于 7 月 20 日截稿） |
| 核对中国体系结构 A 类里仍开放的会 | **HPCA 2027**（题录 7 月 24 日）、**PPoPP 2027**（全文 8 月 3 日）；主题离 BudgetFlow 远 |
| 核对 VLDB 滚动轮次 | 八月轮次题录约 7 月 25 日、全文约 8 月 1 日（太平洋时间）；数据库会，相关度低 |
| 九月、十月会议 | **本文件不写** |

**相关度：** 满分 10，对照 BudgetFlow（任务批共享硬预算、任务价值、智能体修复、已验证解决价值）。高 7–10 · 中 4–6 · 低 1–3。  
**排序：** 同窗期内 A 类优先于 C 类；同档比相关度。

---

## 立刻要做的三件事

| 优先 | 会议 | CCF | 相关度 | 动作 |
|------|------|-----|--------|------|
| 1 | AAAI 2027 主技术轨 | A（人工智能） | 9 | 今晚 OpenReview 登记完整题目与摘要；7 月 28 日前交 AAAI 格式全文 |
| 2 | APSEC 2026 早期研究成果轨 | C（软件工程） | 7 | 8 月 3 日前交 IEEE 格式 PDF（约 5 页） |
| 3 | HPCA 2027 | A（体系结构） | 4 | 仅当你愿意改写成运行时 / 缓存 / 调度叙事时再投；题录 7 月 24 日 |

同一篇稿件只投其中一个正式会议。

**AAAI 入口：** https://openreview.net/group?id=AAAI.org/2027/Conference

---

## AAAI 格式：今晚要不要管？

**今晚摘要登记：不用交 PDF，也不用套模板。**  
按官方说明，摘要截止时只要填真实完整的题目与摘要；占位符题目或空摘要会被删，之后不能再交全文。

**全文（官方：2026-07-28 AoE）：必须满足 AAAI 格式。**

| 项 | 要求（来源：AAAI-27 Submission Instructions） |
|----|-----------------------------------------------|
| 版式 | AAAI 双栏相机就绪样式；用 **AAAI-27 Author Kit** |
| 纸张 | US Letter，高分辨率 PDF |
| 篇幅 | 正文最多 7 页；第 8–9 页只能放参考文献（总共最多 9 页） |
| 匿名 | 双盲：正文去掉作者与单位 |
| 复现清单 | 全文投稿时另传 Author Kit 里的 Reproducibility Checklist |
| Author Kit | 官网页顶栏「AAAI-27 Author Kit」：https://aaai.org/conference/aaai/aaai-27/ |

补充材料与代码可延到 7 月 31 日。

---

## 1. AAAI 2027 主技术轨（CCF A）

| 项目 | 内容 |
|------|------|
| 官网 | https://aaai.org/conference/aaai/aaai-27/ |
| 投稿 | https://openreview.net/group?id=AAAI.org/2027/Conference |
| 题录 / 摘要 | 2026-07-21 23:59 AoE（≈ 北京时间 7 月 22 日约 19:59） |
| 全文 | 2026-07-28 23:59 AoE |
| 页数 | 正文 ≤7 + 参考文献至多到总 9 页 |
| 官方说明 | https://aaai.org/conference/aaai/aaai-27/submission-instructions/ |

**为什么贴：** AAAI-26 已接收预算感知多智能体、代价感知模型路由类工作。你们应强调「一批任务共享硬预算 + 预注册任务价值 + 验证器结算」，而不是再写一个单查询路由器。

### 必读：AAAI-26 已接收论文（3 篇，均来自 AAAI 正式录用，带 PDF）

读这三篇，看审稿社区接受的问题设定、对照方法和数据。

| 论文 | 会 / 轨 | 看什么 | PDF |
|------|---------|--------|-----|
| **BAMAS: Structuring Budget-Aware Multi-Agent Systems** | AAAI-26 · Multiagent Systems | 预算约束下如何选模型池与协作拓扑；对照 AgentVerse / AutoGen 类构建方法；数据偏 GSM8K / HumanEval 一类 | https://ojs.aaai.org/index.php/AAAI/article/download/40226/44187 |
| **Breaking Model Lock-in: Cost-Efficient Zero-Shot LLM Routing via a Universal Latent Space**（ZeroRouter） | AAAI-26 · Planning, Routing, and Scheduling | 查询难度表征与模型选择解耦；代价 / 精度 / 延迟多目标；看他们怎么摆 router 对照 | https://ojs.aaai.org/index.php/AAAI/article/view/40970/44931 · 预印本 https://arxiv.org/pdf/2601.06220 |
| **Confidence-Guided Stepwise Model Routing for Cost-Efficient Reasoning**（STEER） | AAAI-26 · NLP | 步级大小模型切换；置信度信号；数学推理 / 多跳问答等数据 | https://ojs.aaai.org/index.php/AAAI/article/download/40413/44374 · 预印本 https://arxiv.org/pdf/2511.06190 |

录用页（可核对作者与分轨）：  
- BAMAS：https://ojs.aaai.org/index.php/AAAI/article/view/40226  
- ZeroRouter：https://ojs.aaai.org/index.php/AAAI/article/view/40970  
- STEER：https://ojs.aaai.org/index.php/AAAI/article/view/40413  

**从这三篇能读到的偏好：** 明确预算或代价目标、可复现对照（仅强模型 / 仅弱模型 / 学习型路由）、标准公开基准。你们的 30 任务 SWE-bench 风格批次 + 美元硬帽是差异点，也是风险点——要用 AAAI 读者能懂的「价值—预算」语言解释清楚。

---

## 2. APSEC 2026 早期研究成果轨（CCF C）

亚太软件工程大会（Asia-Pacific Software Engineering Conference）当前仍开放的是**早期研究成果轨**（Early Research Achievements Track）：面向有初步证据的早期工作。技术全文轨（Technical Track）已于 2026-07-20 截稿。

| 项目 | 内容 |
|------|------|
| 轨道说明 | https://conf.researchr.org/track/apsec-2026/apsec-2026-papers |
| 投稿 | https://easychair.org/conferences/?conf=apsec2026 |
| 截稿 | 2026-08-03 |
| 通知 | 2026-09-21 |
| 篇幅 | 常规稿最多 5 页（含参考文献）；短稿最多 2 页 |
| 格式 | IEEE 双栏，`\documentclass[10pt,conference]{IEEEtran}`，A4，双盲 |

### 必读：APSEC 2025 已接收论文（3 篇，均在 APSEC 程序中，带 PDF）

| 论文 | 轨 | 看什么 | PDF |
|------|----|--------|-----|
| **Towards Engineering Multi-Agent LLMs: A Protocol-Driven Approach**（SEMAP） | APSEC 2025 早期研究成果轨 | 多智能体软件工程协议层；失败类型与验证；看 ERA 篇幅与叙事密度 | https://arxiv.org/pdf/2510.12120 · 程序条目 https://conf.researchr.org/details/apsec-2025/apsec-2025-early-research-achievements--era-/20/Towards-Engineering-Multi-Agent-LLMs-A-Protocol-Driven-Approach |
| **A Comparative Study Towards Designing a Hybrid Architecture of Microservices and LLM-based Multi-Agent Systems** | APSEC 2025 技术全文轨 | 多智能体与工程系统架构对照；看完整 Technical 文怎么写维度与研究问题 | https://pureadmin.qub.ac.uk/ws/portalfiles/portal/660480405/A_Comparative_Study_Towards_Designing_a_Hybrid_Architecture_of_Microservices_and_LLM-based_Multi-Agent_Systems.pdf · 程序条目 https://conf.researchr.org/details/apsec-2025/apsec-2025-papers/70/A-Comparative-Study-Towards-Designing-a-Hybrid-Architecture-of-Microservices-and-LLM- |
| **Trace: Test Repair via Agent-based Context Extraction with LLMs** | APSEC 2025 技术全文轨 | 仓库级 agent 检索上下文 + 测试修复；看 SE 会偏好的任务与对照 | 程序摘要 https://conf.researchr.org/details/apsec-2025/apsec-2025-papers/5/Trace-Test-Repair-via-Agent-based-Context-Extraction-with-LLMs · IEEE 正式版 https://doi.org/10.1109/APSEC66846.2025.00005（机构网可下） |

**从这三篇能读到的偏好：** AI for SE、多智能体协作、仓库级修复 / 测试、早期想法可用 5 页 ERA 讲清动机与初步证据。你们应固定共享预算，并对照仅便宜模型、仅强模型、学习型路由、仅预算压力。

---

## 3. HPCA 2027（CCF A · 体系结构 · 相关度中低）

只在你愿意把故事改成「大模型推理集群的资源 / 能耗 / 调度」时才有意义。BudgetFlow 原叙事不对口。

| 项目 | 内容 |
|------|------|
| 征稿 | https://conf.researchr.org/track/hpca-2027/hpca-2027-main-conference |
| 题录 | 2026-07-24 23:59 AoE |
| 全文 | 2026-07-31 23:59 AoE |
| 篇幅 | 正文最多 11 页（不含参考文献） |

### 必读：HPCA 2025 已接收 LLM 系统论文（3 篇，带 PDF）

| 论文 | 会 | 看什么 | PDF |
|------|----|--------|-----|
| **DynamoLLM: Designing LLM Inference Clusters for Performance and Energy Efficiency** | HPCA 2025 | 推理集群在 SLO 下动态调实例数 / 并行度 / 频率；能耗与成本 | https://arxiv.org/pdf/2408.00741 · 作者页 https://jovans2.github.io/files/DynamoLLM_HPCA2025.pdf |
| **BitMoD: Bit-serial Mixture-of-Datatype LLM Acceleration** | HPCA 2025 | 量化与加速器协同；硬件评测口径 | https://arxiv.org/pdf/2411.11745 |
| **throttLL’eM / 同类能耗调度文** | 见 HPCA 2025 程序 LLM 分组 | 若投 HPCA，再从官方主程序补第三篇同组论文 | 程序入口 https://hpca-conf.org/2025/main-program/ |

（DynamoLLM 与 BitMoD 已核对为 HPCA 2025 录用；第三篇请你打开官方主程序 LLM 分组自行点开同组论文，避免我用非 HPCA 会的路由文冒充。）

---

## 本窗口已核对、但不作主投的会

| 会议 | CCF | 官方截稿（已核） | 为何放下 |
|------|-----|------------------|----------|
| PPoPP 2027 | A（并行） | 全文 2026-08-03：https://ppopp27.sigplan.org/dates | 并行编程会，主题远 |
| VLDB / PVLDB Vol.20 八月轮 | A（数据库） | 题录约每月 25 日、全文约每月 1 日（PT）：https://www.vldb.org/2027/important-dates.html | 数据库会；八月轮题录约 7 月 25 日 |
| NeurIPS / ICML / ACL / CVPR / ICCV | A（人工智能） | 本窗口均已过从零开稿节奏 | 与 AAAI 同属 AI A，但当前窗口关着 |
| APSEC 2026 技术全文轨 | C | 2026-07-20 已截稿 | 只剩早期研究成果轨 |

---

## 执行顺序

1. **今天：** OpenReview 完成 AAAI 摘要登记（真实题目 + 完整摘要）。  
2. **今晚后到 7 月 28 日：** 按 AAAI Author Kit 改全文；另传复现清单。  
3. **读 AAAI 三篇 PDF：** BAMAS → ZeroRouter → STEER。  
4. **若 AAAI 放弃或需要 SE 短文：** 8 月 3 日前准备 APSEC 早期研究成果轨 5 页稿，并读 SEMAP + Hybrid MS/LLM-MAS + Trace。
