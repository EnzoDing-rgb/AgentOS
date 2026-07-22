# BudgetFlow 投稿作战图

基准日：2026-07-22。  
问题：任务批共享硬预算 · Task Value · 智能体 / SWE 验证 · Total Resolved Value（TRV）。  
CCF 依据：第七版目录（人工智能 + 软件工程会议分册已扫）。  
本地已发表近邻 PDF：`paper1/paper/reference/`（仅 CCF 会议 / 顶会正式发表件）。  
时间一律 **北京时间**（「世界任意时区当天结束」≈ 北京时间次日 19:59）。

---

## 拍板

**主攻：AAAI 2027。**  
DAI 2026、APSEC 2026 早期研究成果轨是同窗口备投；一稿多投政策以 AAAI 说明为准。

| # | 会议 | CCF | 北京时间截稿 | 判定 |
|---|------|-----|--------------|------|
| 1 | **AAAI 2027** 主技术轨 | A · 人工智能 | 全文 **07-29 19:59**；补充 **08-01 19:59**（摘要已交） | **主投** |
| 2 | **DAI 2026** Research / Industry | C · 人工智能 | 摘要 **07-28 19:59**；全文 **08-04 19:59**；AI Paper Track **08-11 19:59** | 备投（agentic / 多智能体口味） |
| 3 | **APSEC 2026** 早期研究成果轨 | C · 软件工程 | **08-03** | 备投（SE 短文） |

9–10 月已官宣：SANER Agentic AI4SE（B）→ AAMAS（B）→ FSE（A）→ ICSE NIER（A）。

---

## 1. 三个目标会：投稿信息 + 同会近邻 PDF

### 1.1 AAAI 2027（主攻）

| 项 | 内容 |
|----|------|
| 投稿 | https://openreview.net/group?id=AAAI.org/2027/Conference |
| 说明 | https://aaai.org/conference/aaai/aaai-27/submission-instructions/ |
| Author Kit | https://aaai.org/conference/aaai/aaai-27/ |
| 格式 | 双栏 US Letter；正文 ≤7 页；第 8–9 页仅参考文献；双盲；Reproducibility Checklist |

**同会近邻 PDF（3）：**

| 论文 | 本地文件 | Baselines | 数据 |
|------|----------|-----------|------|
| BAMAS | `reference/BAMAS_AAAI26.pdf` · https://ojs.aaai.org/index.php/AAAI/article/view/40226 | AutoGen、MetaGPT、ChatDev；Naive-CostAware | GSM8K、MBPP、MATH |
| ZeroRouter | `reference/ZeroRouter_AAAI26.pdf` · https://ojs.aaai.org/index.php/AAAI/article/view/40970 | CIT-LLM-Routing、RouteLLM、GraphRouter、FORC | IFEval、BBH、MATH、GPQA、MMLU-PRO、ARC-C、HumanEval 等 |
| STEER | `reference/STEER_AAAI26.pdf` · https://ojs.aaai.org/index.php/AAAI/article/view/40413 | RSD；Damani question-level；内部置信度 | MATH500、AIME、Omni-Math、ACPBench、MuSiQue、KOR-Bench |

稿内对照骨架：cheap-only · strong-only · 学得/静态路由 · 预算感知多智能体；主指标 TRV（价值冻结）。

---

### 1.2 DAI 2026（备投）

| 项 | 内容 |
|----|------|
| 官网 | https://www.adai.ai/dai/2026/ |
| 日期 | https://www.adai.ai/dai/2026/dates.html |
| 口味 | Distributed AI · multi-agent · autonomous agents · agentic AI · 部署系统 |
| 会议 | 2026-11-29 – 12-02，香港城市大学 |

**同会系近邻 PDF（DAI 2025 已发表路由文）：**

| 论文 | 本地文件 | Baselines / 设定 | 数据 |
|------|----------|------------------|------|
| Avengers-Pro（Beyond GPT-5: … Optimized Routing） | `reference/AvengersPro_DAI25.pdf` · https://arxiv.org/abs/2508.12631 · ACM DAI’25 程序集 https://dl.acm.org/doi/proceedings/10.1145/3772429 | 相对单模型 Pareto；聚类 + performance-efficiency 分数路由；可调 α | 6 套：GPQA-Diamond、HLE、ARC-AGI、SimpleQA、LiveCodeBench 等；8 个前沿模型（含 GPT-5-medium 等） |

写法提示：强调多任务 / 多智能体场景下的**成本–性能可控路由**；BudgetFlow 再升一层到**批次共享硬预算 + Task Value**。

---

### 1.3 APSEC 2026 早期研究成果轨（备投）

| 项 | 内容 |
|----|------|
| 轨道 | https://conf.researchr.org/track/apsec-2026/apsec-2026-papers |
| 投稿 | https://easychair.org/conferences/?conf=apsec2026 |
| 格式 | IEEE 双栏 A4；Regular ≤5 页；Short ≤2 页；双盲 |

**同会近邻 PDF（APSEC 2025，2）：**

| 论文 | 本地文件 | Baselines / 设定 | 数据 |
|------|----------|------------------|------|
| SEMAP（早期研究成果轨） | `reference/SEMAP_APSEC25.pdf` · https://arxiv.org/abs/2510.12120 | MetaGPT 多智能体（开发五角色 / 漏洞三角色） | HumanEval；Big-Vul 100；vudenc100；MAST + LLM-as-Judge |
| Hybrid Microservices + LLM-MAS（技术轨） | `reference/HybridMAS_APSEC25.pdf` · https://doi.org/10.1109/APSEC66846.2025.00077 | 比较研究：微服务 vs LLM-MAS 八维架构 | 无单一数值竞赛表；给 SE 架构叙事与 RQ 框架 |

写法提示：短文突出 **SWE 验证 harness + 批次预算治理** 的早期证据；SEMAP 管失败分类与多智能体，Hybrid 管架构语言。

---

## 2. 相关工作总表（已发表 · 本地 PDF · 实验口径）

线索来源：`src/references.bib`、`docs/related_work.html`、AgenticDev 旧稿、第七版会系检索。  
规则：只收 **顶会 / CCF 会议正式发表**；纯 arXiv 预印本不进本表、不进 `reference/`。

| # | 论文 | 去向 | CCF | 本地 PDF | Baselines（文中） | 数据 / 负载 | 与 BudgetFlow 差一层 |
|---|------|------|-----|----------|-------------------|-------------|----------------------|
| 1 | BAMAS | AAAI 2026 | A | `BAMAS_AAAI26.pdf` | AutoGen、MetaGPT、ChatDev；Naive-CostAware | GSM8K、MBPP、MATH | 任务**内**角色配模型；非批次间价值分配 |
| 2 | ZeroRouter | AAAI 2026 | A | `ZeroRouter_AAAI26.pdf` | CIT、RouteLLM、GraphRouter、FORC | 约 9 套 ID/OOD 路由基准 | 单查询零样本路由 |
| 3 | STEER | AAAI 2026 | A | `STEER_AAAI26.pdf` | RSD；Damani；内部置信度 | MATH500、AIME 等 | 逐步路由；非共享硬预算批次 |
| 4 | RouteLLM | ICLR 2025 | A | `RouteLLM_ICLR25.pdf` | 随机路由；矩阵分解 / BERT / causal LLM 等 | Arena 偏好训练；MMLU、MT Bench、GSM8K | 单查询强弱二选一 |
| 5 | GraphRouter | ICLR 2025 | A | `GraphRouter_ICLR25.pdf` | 既有路由器；PF/BL/CF 三权重 | Alpaca、GSM8K、SQuAD、Multi-News；多 LLM 交互图 | 图路由；仍是查询级 |
| 6 | Cascade Routing | ICML 2025 | A | `CascadeRouting_ICML25.pdf` | 单独 routing / cascading / threshold cascade | RouterBench；**SWE-Bench** | 查询级 cascade；非跨任务价值 |
| 7 | RouteNLP | ACL 2026 Industry | A（主会） | `RouteNLP_ACL26.pdf` | Always-T4/T2、Random、Rule、HybridLLM、RouteLLM 等 | 六任务企业基准 + 8 周试点 ~5K 查询/日 | 企业查询路由；Industry Track |
| 8 | SWE-bench | ICLR 2024 | A | `SWEbench_ICLR24.pdf` | GPT-3.5、GPT-4、Claude 2、SWE-Llama | 2294 issue→PR；Lite；train ~19k | **测试床**；本稿在其上做预算治理 |
| 9 | Avengers-Pro | DAI 2025 | C | `AvengersPro_DAI25.pdf` | 单模型 Pareto；可调 α 路由 | GPQA、HLE、ARC-AGI、SimpleQA、LiveCodeBench 等 | 性能–效率路由；非 Task Value 批次 |
| 10 | AgentNet | NeurIPS 2025 | A | `AgentNet_NeurIPS25.pdf` | Direct 单智能体；MetaGPT 等中心化多智能体 | MATH、BBH、API-Bank / 代码任务 | 去中心化多智能体协调；预算维度弱 |
| 11 | SEMAP | APSEC 2025 ERA | C | `SEMAP_APSEC25.pdf` | MetaGPT 角色智能体 | HumanEval；漏洞子集 | SE 短文 / 失败分类 |
| 12 | Hybrid MAS+MS | APSEC 2025 | C | `HybridMAS_APSEC25.pdf` | 架构比较（非数值排行榜） | 八维设计空间 | SE 架构叙事 |

**凑满 10+ 之后的用法：**  
主文 Related Work 按「查询路由 → 任务内预算 → SWE/多智能体 → 批次共享硬预算」四层写；实验对照至少覆盖 #4/#6/#1 三类 + strong-only/cheap-only。

---

## 3. 建议动作

1. **现在 → 07-29 19:59：** 交 AAAI Author Kit 全文 + checklist（主路径）。  
2. **07-28 19:59：** 若保留 DAI，完成摘要登记；全文看 AAAI 一稿政策后再定。  
3. **08-03：** 需要 SE 短反馈时交 APSEC 早期研究成果轨。  
4. 精读顺序：`BAMAS` → `AvengersPro_DAI25` → `SEMAP` + `HybridMAS` → `RouteLLM` / `GraphRouter` / `CascadeRouting`。

---

## 附录 A. 扫描过、本窗口不进主决策的会

| 类型 | 例子 | 说明 |
|------|------|------|
| 7–8 月已关闭匹配会 | ACML、ICTAI、PRICAI、NLPCC、ICECCS、APSEC 技术轨、ICSE 主轨 | 截稿已过 |
| 方向偏离同窗 A | HPCA、INFOCOM、VLDB、PPoPP、SIGKDD | 体系结构/网络/数据库；材料在 `archive/arch-hpca/` |
| 官方截稿未挂 | ICLR 2027、ASE 2027、IJCAI 2027 精确日 | 盯官网，不进本窗口表 |
| 纯预印本 | INTENT、UCCI、Claw-SWE-Bench | 在 `archive/arxiv/`；正文可提一句，不进 `reference/` |
| TMLR 经典 cascade | FrugalGPT（TMLR 2024） | 不在 CCF 会议表；PDF 在 `archive/journals/` |

CCF 原件与旧调研：`archive/survey/`。
