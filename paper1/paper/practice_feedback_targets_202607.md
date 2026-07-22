# BudgetFlow 投稿作战图

基准日：2026-07-22。  
问题：任务批共享硬预算 · Task Value · 智能体 / SWE 验证 · Total Resolved Value（TRV）。  
CCF 依据：第七版《中国计算机学会推荐国际学术会议和期刊目录》（正式版），已全文扫描人工智能与软件工程两个会议分册。  
已发表近邻 PDF：`paper1/paper/reference/`。  
时间一律写 **北京时间**（截稿按「世界任意时区当天结束」换算：该日历日结束后 ≈ 北京时间次日 19:59）。

---

## 拍板（先看这里）

**7–8 月窗口里，方向匹配且仍可投的只有三条线：**

| # | 会议 | CCF | 北京时间截稿 | 判定 |
|---|------|-----|--------------|------|
| 1 | **AAAI 2027** 主技术轨 | A · 人工智能 | 全文 **07-29 19:59**；补充材料 **08-01 19:59**（摘要已交） | **主投。立刻交 Author Kit PDF。** |
| 2 | **DAI 2026** Research / Industry | C · 人工智能 | 摘要登记 **07-28 19:59**；Research/Industry 全文 **08-04 19:59**；另有 AI Paper Track **08-11 19:59** | **强烈备投。** 征稿直接覆盖 multi-agent / agentic AI / 部署系统。 |
| 3 | **APSEC 2026** 早期研究成果轨 | C · 软件工程 | **08-03**（按会议日计；以 EasyChair 页面为准） | **SE 短文备投。** 技术轨已截止；只走早期研究成果轨。 |

**9–10 月已官宣、方向匹配的下一批：** SANER 2027 Agentic AI4SE（B）→ AAMAS 2027（B，约 10 月初）→ FSE 2027（A）→ ICSE 2027 NIER（A 短想法轨）。  
ICLR 2027：相关工作大量发在此会，但 **官方 2027 截稿页尚未挂出**——不进本窗口决策表，只在附录记「盯官网」。

---

## 1. 可投会议（相关在前）

### 1.1 AAAI 2027（CCF A · 立刻）

| 项 | 内容 |
|----|------|
| 北京时间 | 摘要已交；全文 **2026-07-29 19:59**；补充材料/代码 **2026-08-01 19:59** |
| 投稿 | https://openreview.net/group?id=AAAI.org/2027/Conference |
| 说明 | https://aaai.org/conference/aaai/aaai-27/submission-instructions/ |
| Author Kit | https://aaai.org/conference/aaai/aaai-27/ |
| 格式 | 双栏 US Letter；正文 ≤7 页；第 8–9 页仅参考文献；双盲；另传 Reproducibility Checklist |
| 一稿政策 | 全文截止前，同一工作不得同时在审于其他存档会议/期刊 |

**同会系已发表近邻（本地 PDF → 对照口径）：**

| 论文 | 文件 | Baselines | 数据 |
|------|------|-----------|------|
| BAMAS | `reference/BAMAS_AAAI26.pdf` | AutoGen、MetaGPT、ChatDev；Naive-CostAware | GSM8K、MBPP、MATH |
| ZeroRouter | `reference/ZeroRouter_AAAI26.pdf` | CIT-LLM-Routing、RouteLLM、GraphRouter、FORC | IFEval、BBH、MATH、GPQA、MMLU-PRO、ARC-C、HumanEval 等约 9 套 |
| STEER | `reference/STEER_AAAI26.pdf` | RSD；Damani question-level；内部置信度 | MATH500、AIME、Omni-Math、ACPBench、MuSiQue、KOR-Bench |

稿内对照建议：cheap-only · strong-only · 学得/静态路由 · 预算感知多智能体；主指标仍用冻结价值下的 TRV。

---

### 1.2 DAI 2026（CCF C · 7 月底—8 月初）

| 项 | 内容 |
|----|------|
| 会议 | 2026-11-29 – 12-02，香港城市大学 |
| 北京时间 | 摘要登记 **07-28 19:59**；Research / Industry **08-04 19:59**；AI Paper Track **08-11 19:59** |
| 官网 | https://www.adai.ai/dai/2026/ |
| 日期 | https://www.adai.ai/dai/2026/dates.html |
| 口味 | Distributed AI · multi-agent · autonomous agents · **agentic AI** · 部署系统 |

这是扫完整个人工智能 C 类名单后，**唯一在 7–8 月仍开、且征稿与 agent/多智能体直接对齐**的 CCF 会议（相对 ACML / ICTAI / PRICAI / NLPCC 等已关闭项）。  
写法侧重点：多任务共享资源、agent 协调与成本约束；SWE 批次作为部署/评测证据。

---

### 1.3 APSEC 2026 早期研究成果轨（CCF C · 8 月）

| 项 | 内容 |
|----|------|
| 截稿 | **2026-08-03** |
| 通知 | 2026-09-21 |
| 轨道 | https://conf.researchr.org/track/apsec-2026/apsec-2026-papers |
| 投稿 | https://easychair.org/conferences/?conf=apsec2026 |
| 格式 | IEEE 双栏 A4，`IEEEtran` 10pt；Regular ≤5 页；Short ≤2 页；双盲 |

范文：`reference/SEMAP_APSEC25.pdf`（MetaGPT 角色智能体；HumanEval / 漏洞子集；MAST + LLM-as-Judge）。

注意与 AAAI 的一稿多投政策：AAAI 在审期间，同一存档贡献不要并行投其他存档会；短文若叙事错开且政策允许，再单独判断。

---

### 1.4 九月—十月（已官宣截稿）

| 会议 | CCF | 北京时间截稿 | 链接 | 用法 |
|------|-----|--------------|------|------|
| **SANER 2027** Agentic AI4SE 轨 | B · 软件工程 | 摘要 **10-20 19:59**；全文 **10-24 19:59** | https://conf.researchr.org/track/saner-2027/saner-2027-agentic-ai4se-track | **最对齐的 SE 专轨**：agent + 成本 + benchmark + 工具使用 |
| **SANER 2027** Research Track | B | 摘要 **09-22 19:59**；全文 **09-26 19:59** | https://conf.researchr.org/track/saner-2027/saner-2027-papers | 偏演化分析时走此轨 |
| **AAMAS 2027** | B · 人工智能 | 官网写 **early Oct 2026**（具体日以 Warwick 页更新为准） | https://warwick.ac.uk/fac/sci/dcs/aamas2027/ | 多智能体旗舰；参照 AAMAS 2026 约为 10 月初摘要/全文 |
| **FSE 2027** Research | A · 软件工程 | **10-03 19:59** | https://conf.researchr.org/dates/fse-2027 | harness / 验证 / 预算治理写成 SE 问题 |
| **ICSE 2027** NIER | A · 软件工程（短想法） | **10-24 19:59** | https://conf.researchr.org/track/icse-2027/icse-2027-new-ideas-and-emerging-results--nier- | ≤4 页 + Future Plans；HotCRP：https://icse2027-nier.hotcrp.com/ |

---

## 2. 参考文献 → 会议地图

来自 `src/references.bib` 与同会近邻；只列已发表去向。

| 工作 | 去向 | CCF | 启示 |
|------|------|-----|------|
| SWE-bench | ICLR 2024 | A · 人工智能 | 验证型 coding agent 测试床 |
| RouteLLM | ICLR 2025 | A · 人工智能 | 单查询强弱路由 |
| Cascade Routing | ICML 2025 | A · 人工智能 | 路由+cascading；含 RouterBench 与 SWE-Bench |
| BAMAS / ZeroRouter / STEER | AAAI 2026 | A · 人工智能 | 预算多智能体 / 路由；支撑投 AAAI-27 |
| RouteNLP | ACL 2026 Industry Track | ACL 主会 A；Industry 口径另计 | NLP 落地路由 |
| SEMAP | APSEC 2025 ERA | C · 软件工程 | SE 短文写法 |
| vLLM | SOSP 2023 | A · 系统 | 执行底座 |
| SGLang | NeurIPS 2024 | A · 人工智能 | 执行底座 |

竞品会系：**ICLR / ICML / AAAI + SE（APSEC / SANER / FSE / ICSE）**。  
体系结构会系（HPCA 等）与本稿问题陈述不对齐——见附录。

---

## 3. `reference/` 内实验对照（已发表 PDF）

| 工作 | 文件 | Baselines | 数据 / 负载 | 与本稿差一层 |
|------|------|-----------|-------------|--------------|
| RouteLLM | `RouteLLM_ICLR25.pdf` | 随机路由；矩阵分解 / BERT / causal LLM 等学得路由 | 训练 Chatbot Arena；评测 MMLU、MT Bench、GSM8K | 单查询二选一 |
| Cascade Routing | `CascadeRouting_ICML25.pdf` | 单独 routing、单独 cascading、threshold cascade | RouterBench；SWE-Bench | 查询级选择；非批次价值分配 |
| SWE-bench | `SWEbench_ICLR24.pdf` | GPT-3.5、GPT-4、Claude 2、SWE-Llama | 2294 GitHub issue→PR；Lite；train ~19k | 测试床本身 |
| BAMAS / ZeroRouter / STEER | 见 §1.1 | 见上表 | 见上表 | AAAI 审稿人熟悉语言 |
| SEMAP | `SEMAP_APSEC25.pdf` | MetaGPT 角色智能体 | HumanEval；漏洞子集 | SE 短文度量参考 |

统一对照骨架：cheap-only · strong-only · RouteLLM 类路由 · BAMAS 类预算多智能体。主证据：固定 30-task、冻结价值、TRV / Resolved Value per Dollar。

---

## 4. 建议动作顺序

1. **现在 → 07-29 19:59：** 交 AAAI Author Kit 全文 + Reproducibility Checklist。  
2. **07-28 19:59 前：** 若走 DAI，完成摘要登记；**08-04 19:59** 前交 Research/Industry 全文（注意与 AAAI 一稿政策）。  
3. **08-03：** 需要 SE 短反馈时交 APSEC 早期研究成果轨。  
4. **9–10 月：** 主准备 SANER Agentic AI4SE；并行盯 AAMAS 官宣日；有 SE 全长证据冲 FSE；想法轨备用 ICSE NIER。

---

## 附录 A. CCF 人工智能 / 软件工程会议扫描结论

扫描范围：第七版目录中 **人工智能** 与 **软件工程/系统软件/程序设计语言** 全部会议 A/B/C（本地副本：`archive/survey/CCF7_recommended_conferences_journals.pdf`）。  
判定口径：主题是否贴近「预算 / 路由 / 智能体 / SWE 验证」；截稿是否落在 2026-07–10 且仍开放。

### A.1 7–8 月已关闭或口味偏离（不进主决策）

| 会议 | CCF | 截稿情况（北京时间口径） | 说明 |
|------|-----|--------------------------|------|
| NeurIPS 2026 | A · AI | 已过（约 05-04/06） | 下届太远 |
| ICML 2026 | A · AI | 已开会（首尔） | 下届约 2027 年初截稿 |
| ACL / EMNLP / NAACL / COLING 主线 | A/B · AI | 本窗口无匹配开放轨，或偏 NLP | RouteNLP 类才贴 |
| CVPR / ICCV / ECCV / ICRA / IROS | A/B/C · 视觉/机器人 | — | 方向偏离 |
| COLT / KR / UAI / ALT | B/C · 理论 | — | 方向偏离 |
| ACML 2026 | C · AI | 已过（延至 07-05） | 已关闭 |
| ICTAI 2026 | C · AI | 已过（约 06-30） | 已关闭 |
| PRICAI 2026 | C · AI | 已过（约 06-27） | 已关闭 |
| NLPCC 2026 | C · AI | 已过（延至 06-20） | 已关闭 |
| ICONIP / KSEM / GECCO / IEEE CEC 等 | C · AI | 本窗口已过或偏演化/神经网络 | 不优先 |
| ICSE 2027 主轨 | A · SE | 已过（06-23/30） | 改走 NIER（10 月） |
| ASE 2026 主轨 | A · SE | 已过（约 03-26） | ASE 2027 未宣 |
| APSEC 2026 技术轨 | C · SE | 已过（07-13） | 改走早期研究成果轨 |
| SEKE / QRS / COMPSAC / TASE 2026 | C · SE | 已过 | — |
| ICECCS 2026（formal-analysis 系列） | C · SE | 已过（延至 07-20 当天结束 ≈ 07-21 19:59） | 虽列 LLM-based Agents，但窗口已关：https://formal-analysis.com/iceccs/2026/ |
| ECAI 2026 | B · AI | 已过 | — |

### A.2 方向不匹配：体系结构 / 网络 / 数据库等同窗 A 类

社区 DDL 站在 7–8 月还会刷出 HPCA、INFOCOM、VLDB、PPoPP、SIGKDD、UbiComp 等。  
它们是 CCF A，但审稿共同体是体系结构 / 网络 / 数据库 / HCI，**不是本稿主战场**。HPCA 相关 PDF 已迁至 `archive/arch-hpca/`，不进 `reference/`。

### A.3 官方截稿尚未挂出、因此不进本窗口决策表

| 会议 | CCF | 状态 | 盯梢链接 |
|------|-----|------|----------|
| ICLR 2027 | A · AI | 历史节奏约 9 月下旬；**iclr.cc 尚未公布 2027 截稿** | https://iclr.cc/ |
| AAMAS 2027 精确日 | B · AI | 官网仅写 early Oct 2026 | https://warwick.ac.uk/fac/sci/dcs/aamas2027/ |
| ASE 2027 | A · SE | 未宣（系列主截稿常在春季） | https://conf.researchr.org/series/ase |
| IJCAI 2027 | B · AI（第七版由 A 降 B） | 未进本窗口 | https://www.ijcai.org/ |
| ICAPS 2027 | B · AI | 规划/调度相关，日期未进本窗口 | https://www.icaps-conference.org/ |

### A.4 目录约定（本次整理）

| 路径 | 内容 |
|------|------|
| `paper/practice_feedback_targets_202607.md` | 本作战图（唯一主调研入口） |
| `paper/reference/*.pdf` | 仅已发表、且用于对齐实验的近邻 PDF |
| `paper/archive/survey/` | CCF 原件与旧调研 md |
| `paper/archive/arxiv/` | 纯预印本（INTENT、UCCI） |
| `paper/archive/arch-hpca/` | 体系结构方向材料 |
| `paper/archive/agenticdev/` | 已放弃的 AgenticDev 稿 |
