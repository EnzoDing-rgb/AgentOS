# BudgetFlow 投稿调研（按参考文献去向 · 7–10 月窗口）

时间基准：2026-07-22。  
论文主题：任务批共享硬预算 · Task Value · 智能体 / SWE 验证 · Total Resolved Value（TRV）。  
本地 PDF：`paper1/paper/reference/`。

**怎么用这份文档：** 先看「总表」，再按需要下钻到会议细则或相关工作实验。HPCA 等体系结构会议的材料保留备查，但不作为有效投稿方向。

---

## 0. 总表（能投在前）

| 优先级 | 会议 / 轨道 | CCF | 截止 | 与本稿匹配 | 动作 |
|--------|-------------|-----|------|------------|------|
| 1 | **AAAI 2027** 主技术轨 | A · 人工智能 | 全文 **07-28** AoE（摘要已交） | 高：预算感知智能体 / 路由同会已有 BAMAS、ZeroRouter、STEER | 交 Author Kit PDF + 复现清单 |
| 2 | **APSEC 2026** 早期研究成果轨（Early Research Achievements） | C · 软件工程 | **08-03** | 中高：SE 短文、初步证据；技术轨已于 07-13 截止 | 写 ≤5 页 IEEE 双栏短文 |
| 3 | **SANER 2027** Agentic AI4SE 轨（新轨） | B · 软件工程 | 摘要 **10-19** · 全文 **10-23** AoE | **很高**：征稿直接写 agentic AI4SE、成本、benchmark、约束下执行 | 按 SE + agent harness / TRV 叙事准备 |
| 4 | **AAMAS 2027** 主轨 | B · 人工智能 | **约 early Oct 2026**（官网 TBC） | 很高：多智能体旗舰会 | 盯 Warwick 官网定稿日期 |
| 5 | **FSE 2027** Research Papers | A · 软件工程 | **10-02** | 中：需强调 harness、验证、软件过程，少写纯 ML 路由 | SE 口味改写后可冲 |
| 6 | **ICSE 2027** New Ideas and Emerging Results（NIER） | A · 软件工程（短文轨） | **10-23** AoE | 中：≤4 页 + Future Plans；适合早期主张 | 有初步实验即可 |
| 7 | **ICLR 2027** | A · 人工智能（第七版升 A） | 历史窗口约 **9 月下旬**；**官方 2027 日期未挂** | 高（RouteLLM、SWE-bench 同会） | 盯 iclr.cc；勿用第三方站当死线 |
| — | COLING 2027（经 ACL Rolling Review 10 月轮） | B · 人工智能 | ARR **10-12** | 低：NLP 口味偏重 | 仅当稿件明显 NLP 化再考虑 |
| — | **HPCA 2027** | A · 体系结构 | 题录 07-24 · 全文 07-31 | **方向不匹配**（硬件 / 推理集群） | 材料见文末备查，不进主线 |
| — | ASE 2027 主轨 | A · 软件工程 | **未官宣**（ASE 2026 主截稿在春季） | — | 不进本窗口 |
| — | NeurIPS 2026 / ICSE 2027 主轨 | A | 已过（NeurIPS 05-04/06；ICSE 主轨 06-23/30） | — | 已关闭 |

---

## 1. 参考文献 → 会议地图（投稿去向）

来源：`paper1/paper/src/references.bib` + Related Work 中的近邻工作。只列有明确会议/期刊归属、且对选会有用的条目。

| 文献（本稿引用或近邻） | 发表去向 | CCF 启示 | 对 BudgetFlow 的含义 |
|------------------------|----------|----------|----------------------|
| SWE-bench | **ICLR 2024** | A · 人工智能 | 验证型 coding agent 的主战场之一 |
| RouteLLM | **ICLR 2025** | A · 人工智能 | 单查询强弱模型路由；成本–质量曲线是审稿人熟悉语言 |
| Cascade Routing | **ICML 2025** | A · 人工智能 | 路由 + cascading；实验含 **RouterBench** 与 **SWE-Bench** |
| BAMAS | **AAAI 2026** | A · 人工智能 | 预算感知多智能体；与 AAAI-27 同会系 |
| ZeroRouter / STEER | **AAAI 2026** | A · 人工智能 | 零样本路由 / 逐步路由；AAAI 审稿人已见过此类对照 |
| RouteNLP | **ACL 2026 Industry Track** | ACL 主会为 A；Industry Track 评价口径不同 | 企业查询路由；口味偏 NLP 落地 |
| INTENT | arXiv:2602.11541（2026） | 预印本 | **单任务内** 工具预算；与批次级 TRV 互补 |
| UCCI | arXiv:2605.18796（2026） | 预印本 | 校准置信度 → cascade；生产 NER 负载 |
| Claw-SWE-Bench | arXiv:2606.12344（2026） | 预印本 | harness / 成本报告；SE 叙事素材 |
| vLLM | **SOSP 2023** | A · 系统 | 执行底座，不是投稿主会 |
| SGLang | **NeurIPS 2024** | A · 人工智能 | 同上：系统优化侧 |

**选会结论（锋利版）：**  
竞品与相关工作主要落在 **ICLR / ICML / AAAI**（人工智能 A）与 **SWE / agent harness** 叙事；软件工程侧应盯 **SANER Agentic AI4SE、FSE、ICSE NIER、APSEC**。体系结构顶会（HPCA）与本稿问题陈述不对齐。

---

## 2. 能投会议细则（按时间）

### 2.1 AAAI 2027（立刻 · CCF A）

| 项 | 内容 |
|----|------|
| 状态 | 摘要已在 OpenReview 登记；下一步交全文 PDF |
| 全文 | 2026-07-28 23:59 AoE |
| 补充材料 | 2026-07-31 AoE |
| 投稿 | https://openreview.net/group?id=AAAI.org/2027/Conference |
| 说明 / Kit | https://aaai.org/conference/aaai/aaai-27/submission-instructions/ |
| 格式 | Author Kit：双栏 US Letter；正文 ≤7 页；参考文献可到总 9 页；双盲；另传 Reproducibility Checklist |

**同会系已接收工作（实验口径，本地 PDF）：**

#### BAMAS（`BAMAS_AAAI26.pdf`）

- **Baselines：** AutoGen、MetaGPT、ChatDev；启发式 Naive-CostAware（Level 1–5 贪心）。固定 LLM 类型，分别跑 DeepSeek-V3 与 GPT-4.1 nano。  
- **Datasets：** GSM8K、MBPP、MATH；预算档 GSM8K/MBPP 约 500–2000。

#### ZeroRouter（`ZeroRouter_AAAI26.pdf`）

- **Baselines：** CIT-LLM-Routing、RouteLLM、GraphRouter、FORC。  
- **Datasets（约 9 个）：** ID 含 IFEval、BBH、MATH、GPQA、MMLU-PRO 等；OOD 含 ARC-C、HumanEval 等。目标 Max-Acc / Min-Cost / Min-Lat；模型池约 60。

#### STEER（`STEER_AAAI26.pdf`）

- **Baselines：** RSD；Damani 等 question-level 分配；内部置信度对照。  
- **Benchmarks：** MATH500、AIME、Omni-Math、ACPBench、MuSiQue、KOR-Bench 子集。

**对稿件：** 对照里保留 cheap-only / strong-only / 学习型路由 / 预算感知多智能体；用 TRV + 固定 30-task SWE 批次说明与「单查询路由」的差异。

---

### 2.2 APSEC 2026 早期研究成果轨（8 月 · CCF C）

| 项 | 内容 |
|----|------|
| 截稿 | 2026-08-03 |
| 通知 | 2026-09-21 |
| 轨道 | https://conf.researchr.org/track/apsec-2026/apsec-2026-papers |
| 投稿 | https://easychair.org/conferences/?conf=apsec2026 |
| 格式 | IEEE 双栏 A4，`IEEEtran` 10pt；Regular ≤5 页（含参考文献）；Short ≤2 页；双盲 |

**同会系范文 SEMAP（`SEMAP_APSEC25.pdf`，早期研究成果轨）：**

- **Baseline：** MetaGPT 多智能体（开发五角色 / 漏洞三角色）。  
- **Datasets：** HumanEval；Big-Vul 抽 100；vudenc100（CVEFixes）。  
- **度量：** MAST 失败分类；LLM-as-Judge（gpt-4o）。

技术轨摘要/全文已于 7 月中截止；本窗口只剩早期研究成果轨。

---

### 2.3 九月—十月主候选

#### SANER 2027 · Agentic AI4SE 轨（CCF B · 强烈推荐盯）

| 项 | 内容 |
|----|------|
| 摘要（强制） | 2026-10-19 AoE |
| 全文 | 2026-10-23 AoE |
| 通知 | 2026-12-08 |
| 征稿 | https://conf.researchr.org/track/saner-2027/saner-2027-agentic-ai4se-track |
| 投稿 | https://easychair.org/my/conference?conf=saner2027（选 Agentic AI4SE） |
| 篇幅 | ≤10 页 + 参考文献 ≤2 页；IEEE；双盲 |

征稿明确欢迎：agent 作 SE 系统、成本与可靠性约束、benchmarking、tool use、multi-agent workflow。与 BudgetFlow（批次硬预算 + SWE 验证 + harness）对齐度高于「纯体系结构」或「纯 NLP」会。

同系列研究轨更早：摘要 09-21 / 全文 09-25（常规 Research Track）。若稿件更偏软件演化分析而非 agentic，可走研究轨；agent 主叙事优先新轨。

#### AAMAS 2027（CCF B · 多智能体旗舰）

| 项 | 内容 |
|----|------|
| 会议 | 2027-05-03–07，Hanoi |
| 截稿 | **early Oct 2026（TBC）** |
| 官网 | https://warwick.ac.uk/fac/sci/dcs/aamas2027/ |
| 参照 AAMAS 2026 | 摘要约 Oct 1 · 全文约 Oct 8 AoE；主轨 8 页 + 参考文献 |

题目匹配极强；以官网最终日期为准。

#### FSE 2027 Research Papers（CCF A · 软件工程）

| 项 | 内容 |
|----|------|
| 全文 | 2026-10-02 |
| 日期页 | https://conf.researchr.org/dates/fse-2027 |
| 会议 | 2027-07-12–16，深圳 |

适合「agent harness / 验证 / 预算治理作为软件工程问题」；不宜写成纯路由算法短文。

#### ICSE 2027 NIER（CCF A · 短想法轨）

| 项 | 内容 |
|----|------|
| 截稿 | 2026-10-23 AoE |
| 通知 | 2026-12-18 |
| 篇幅 | 正文 ≤4 页 + 参考文献 1 页；须含 Future Plans |
| 投稿 | https://icse2027-nier.hotcrp.com/ |
| CFP | https://conf.researchr.org/track/icse-2027/icse-2027-new-ideas-and-emerging-results--nier- |

主轨已关闭；NIER 适合把 TRV / Value-Triggered Escalation 写成可检验主张。

#### ICLR 2027（CCF A · 盯官方）

相关工作 RouteLLM、SWE-bench 均在 ICLR。历史节奏：摘要约 9 月 19 日前后、全文约 9 月 24 日 AoE（以 ICLR 2026 为准）。**ICLR 2027 官方日期页尚未发布**；第三方「Sep 19/24 2026」仅作规划锚点，以 https://iclr.cc/ 为准。

---

## 3. 参考文献实验对照（精读摘要）

| 工作 | 去向 | Baselines（文中） | 数据 / 负载 | 与 BudgetFlow 的差一层 |
|------|------|-------------------|-------------|------------------------|
| RouteLLM（`RouteLLM_ICLR25.pdf`） | ICLR 2025 | 随机路由；多类学得路由器（矩阵分解 / BERT / causal LLM 等） | 训练：Chatbot Arena 偏好；增强 MMLU val、Nectar+GPT-4 judge。评测：MMLU、MT Bench、GSM8K（OOD） | **单查询** 强弱二选一；无任务批硬预算、无 TRV |
| Cascade Routing（`CascadeRouting_ICML25.pdf`） | ICML 2025 | 单独 routing、单独 cascading、既有 threshold cascade | RouterBench；**SWE-Bench**；文称相对对照最高约 +8% / +14% | 仍是查询级模型选择；SWE 作质量任务，不是批次价值分配 |
| SWE-bench（`SWEbench_ICLR24.pdf`） | ICLR 2024 | GPT-3.5、GPT-4、Claude 2、SWE-Llama；BM25 / oracle retrieval | 2,294 GitHub issue→PR；SWE-bench Lite；train ~19k | **测试床**；BudgetFlow 在其上做预算与价值，不重造基准 |
| INTENT（`INTENT_arXiv2602.pdf`） | arXiv 2026 | Soft（指令/提示预算）与 Enforce（硬阻断）两组 | cost-augmented **StableToolBench** | **单 agent 任务内** 工具花费；与批次级共享预算正交 |
| UCCI（`UCCI_arXiv2605.pdf`） | arXiv 2026 | entropy 阈值、split-conformal、FrugalGPT 风格学得阈值；单模型 4B/12B | 生产 NER 75k 查询；H100 实测延迟作成本 | 生产 cascade；领域窄（NER），无多任务价值 |
| BAMAS / ZeroRouter / STEER | AAAI 2026 | 见 §2.1 | GSM8K/MBPP/MATH；路由基准套件；数学/推理套件 | AAAI 审稿人熟悉的对照语言 |
| SEMAP | APSEC 2025 ERA | MetaGPT 角色智能体 | HumanEval；漏洞子集 | SE 短文写法与度量参考 |

**统一对照建议（写进稿）：**  
cheap-only · strong-only · 学得/静态路由（RouteLLM 类）· 预算感知多智能体（BAMAS 类）·（可选）任务内预算规划（INTENT 类）。主指标保持 TRV / Resolved Value per Dollar；SWE 批次固定、价值冻结。

---

## 4. 备查：方向不匹配或窗口外（保留材料）

### HPCA 2027（CCF A · 体系结构）— 不作为有效方向

题录 07-24 / 全文 07-31；征稿 https://conf.researchr.org/track/hpca-2027/hpca-2027-main-conference。  
问题是硬件、缓存、能耗、SLO 集群调度；与「任务价值驱动的批次预算治理」不是同一审稿共同体。本地已留 DynamoLLM / BitMoD / InstAttention 精读，仅作系统侧对照，**不进投稿主线**。

| 论文 | Baseline / 负载（摘要） |
|------|-------------------------|
| DynamoLLM（`DynamoLLM_HPCA25.pdf`） | SinglePool、MultiPool、Scale*；Azure Coding/Conversation trace；对接 vLLM |
| BitMoD（`BitMoD_HPCA25.pdf`） | FP16；ANT、OliVe；六类 LLM |
| InstAttention（`InstAttention_HPCA25.pdf`） | FlexGen 等卸载；长序列吞吐 |

### 其它同窗但匹配偏低

| 时间 | 会议 | 说明 |
|------|------|------|
| 约 07-25 / 08-01 | VLDB / PVLDB 八月轮 | 数据库；口味远 |
| 08-03 | PPoPP 2027 | 并行；口味远 |
| ARR 08-03 / 10-12 | EACL 2027 / COLING·NAACL 2027 | NLP 主；本稿非主战场 |

### 已关闭或未到本窗口

NeurIPS 2026（05-04/06）、ICSE 2027 主轨（06-23/30）、ASE 2026 主轨（已过；ASE 2027 未宣）、APSEC 2026 技术轨（07-13）。

---

## 5. 建议动作顺序

1. **07-28 前：** AAAI Author Kit 全文 + checklist。  
2. **08-03：** 若要快速 SE 反馈，交 APSEC 早期研究成果轨短文（可与 AAAI 错开叙事侧重点，注意一稿多投政策）。  
3. **9–10 月主线：** 优先准备 **SANER Agentic AI4SE**；并行盯 **AAMAS** 官宣日期与 **ICLR** 官方 CFP；有 SE 全长证据再冲 **FSE**；想法轨备用 **ICSE NIER**。  
4. 实验写作：对齐 §3 表中的对照与数据语言；主证据仍是冻结价值下的 TRV，而非另开 GSM8K 主实验。
