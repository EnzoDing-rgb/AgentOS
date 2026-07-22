# BudgetFlow：七八月投稿时间线（CCF）

时间基准：2026-07-22。  
论文主题：任务批共享硬预算 · Task Value · 智能体 / SWE 验证 · TRV。

**两个 CCF A：**（1）AAAI 2027（摘要已交，待全文 PDF）；（2）HPCA 2027（题录 07-24，全文 07-31）。  
本地 PDF 目录：`paper1/paper/reference/`（已精读并摘 baseline / 数据集）。

---

## 一、现在到 7 月 28 日｜AAAI 2027（CCF A · 人工智能）

| 项 | 内容 |
|----|------|
| 状态 | 摘要已在 OpenReview 登记；**下一步交全文 PDF** |
| 全文截止 | 2026-07-28 23:59 AoE |
| 补充材料 | 2026-07-31 AoE |
| 投稿 | https://openreview.net/group?id=AAAI.org/2027/Conference |
| 格式 | AAAI-27 Author Kit：双栏、US Letter、正文 ≤7 页、参考文献可到总 9 页、双盲、另传 Reproducibility Checklist |
| 说明 | https://aaai.org/conference/aaai/aaai-27/submission-instructions/ |
| Author Kit | https://aaai.org/conference/aaai/aaai-27/ |

### 精读：AAAI-26 已接收论文（baseline + 数据集）

#### 1. BAMAS: Structuring Budget-Aware Multi-Agent Systems

- 录用页：https://ojs.aaai.org/index.php/AAAI/article/view/40226  
- 本地 PDF：`reference/BAMAS_AAAI26.pdf`（经本机 V2Ray `127.0.0.1:10809` 从 AAAI OJS 下载）  
- 文字摘录备份：`reference/BAMAS_AAAI26_text_extract.txt`  
- **Baselines（文中写明）：** AutoGen、MetaGPT、ChatDev；另加启发式 **Naive-CostAware**（按 Level 1–5 贪心选配置）。对照时固定 LLM 类型，分别跑 DeepSeek-V3 与 GPT-4.1 nano 两套。  
- **Datasets：** **GSM8K**（数学应用题）、**MBPP**（Python 编程，训练集约 374 题作 RL 语料）、**MATH**（高阶数学）。预算档：GSM8K/MBPP 为 500–2000；MATH 更高档（文中以 1000 为双模型参考成本量级）。

#### 2. ZeroRouter（Breaking Model Lock-in: Cost-Efficient Zero-Shot LLM Routing）

- 录用页：https://ojs.aaai.org/index.php/AAAI/article/view/40970  
- 本地 PDF：`reference/ZeroRouter_AAAI26.pdf`  
- **Baselines：** **CIT-LLM-Routing**、**RouteLLM**、**GraphRouter**、**FORC**。  
- **Datasets（9 个）：**  
  - ID：IFEval、BBH、MATH、GPQA、（顺序推理一类基准）、MMLU-PRO  
  - OOD：ARC-C、以及文中另两个 OOD（含 HumanEval 代码评测）  
  - 路由策略目标：Max-Acc / Min-Cost / Min-Lat 三组权重。模型池约 60 个 LLM。

#### 3. STEER（Confidence-Guided Stepwise Model Routing）

- 录用页：https://ojs.aaai.org/index.php/AAAI/article/view/40413  
- 本地 PDF：`reference/STEER_AAAI26.pdf`  
- **Baselines：**  
  - External-models 组：RSD；Damani et al. 的 question-level 分配  
  - Internal-signal 组：文中 “No external models” 对照，只用模型内部置信度  
- **Datasets / Benchmarks：** MATH500、AIME、Omni-Math、ACPBench、MuSiQue、KOR-Bench（Cipher / Counterfactual / Logic 子集）。报告在 AIME 上相对大模型约 +20% 准确率、约 48% 更少 FLOPs。

**对 BudgetFlow 的用法：** 对照里要有 cheap-only / strong-only / 学习型路由 / 预算感知多智能体构建；数据上 AAAI 审稿人熟悉 GSM8K/MBPP/MATH/路由基准——你们的 30-task SWE 批次是差异化，需用 TRV 语言解释清楚。

---

## 二、7 月 24 日—7 月 31 日｜HPCA 2027（CCF A · 体系结构）

第二个立刻相关时间窗内的 **CCF A**。主题是硬件 / 推理集群；投此会须改写成运行时、缓存、调度、能耗 / SLO。

| 项 | 内容 |
|----|------|
| 题录 + 摘要 | 2026-07-24 23:59 AoE |
| 全文 | 2026-07-31 23:59 AoE |
| 征稿 | https://conf.researchr.org/track/hpca-2027/hpca-2027-main-conference |
| 篇幅 | 正文最多 11 页（参考文献另计） |

### 精读：HPCA 2025 已接收论文（baseline + 数据 / 负载）

#### 1. DynamoLLM

- 本地：`reference/DynamoLLM_HPCA25.pdf`（arXiv:2408.00741）  
- **Baselines / 消融对照：** SinglePool、MultiPool、ScaleInst、ScaleShard、ScaleFreq，以及完整 DynamoLLM。评测在 H100 集群、对接 **vLLM**。  
- **数据 / 负载：** Azure 生产 trace——**Coding** 与 **Conversation** 两类 LLM 服务调用；按请求长度、负载、模型与 SLO 做剖析。指标含能耗、碳排、TTFT、TBT、客户成本。

#### 2. BitMoD

- 本地：`reference/BitMoD_HPCA25.pdf`（arXiv:2411.11745）  
- **Baselines：** FP16 加速器基线；SOTA 加速器 **ANT**、**OliVe**。  
- **模型 / 评测：** 六个代表性 LLM；判别任务与生成任务（困惑度等）。报告相对 ANT / OliVe 约 1.69× / 1.48× 加速。

#### 3. InstAttention（预印本亦称 InstInfer）

- 本地：`reference/InstAttention_HPCA25.pdf`（arXiv:2409.04992）  
- **Baselines：** 以 **FlexGen** 等 SSD / 主机内存卸载方案为对照。  
- **设置：** 13B 级模型 + NVIDIA A6000；长序列推理吞吐（文中相对 SSD 方案最高约 11.1×）。

---

## 三、8 月 3 日｜APSEC 2026 早期研究成果轨（CCF C · 软件工程）

SE 口味、篇幅短（常规 ≤5 页含参考文献），适合有初步证据的早期写法。

| 项 | 内容 |
|----|------|
| 截稿 | 2026-08-03 |
| 通知 | 2026-09-21 |
| 轨道 | https://conf.researchr.org/track/apsec-2026/apsec-2026-papers |
| 投稿 | https://easychair.org/conferences/?conf=apsec2026 |
| 格式 | IEEE 双栏 A4，`IEEEtran` 10pt，双盲 |

### 精读：APSEC 2025 SEMAP（早期研究成果轨）

- 本地：`reference/SEMAP_APSEC25.pdf`（arXiv:2510.12120）  
- **Baseline：** 基于 **MetaGPT** 的多智能体；开发任务用 CEO / Planner / Coder / Reviewer / Tester 五角色；漏洞任务用 Auditor / Critic / Tester 三角色。  
- **Datasets：**  
  - 开发：HumanEval（函数级）；另有部署级开发任务  
  - 漏洞：C/C++ 自 Big-Vul 抽 100 条（50 脆弱 / 50 安全）；Python 用 **vudenc100**（自 CVEFixes 抽样 100）  
- **度量：** MAST 失败分类（under-specification / misalignment / verification），LLM-as-Judge（gpt-4o）。

另两篇 APSEC 2025 程序内相关文（便于继续挖 SE 口味）：  
- Hybrid Microservices + LLM-MAS（技术轨）PDF：https://pureadmin.qub.ac.uk/ws/portalfiles/portal/660480405/A_Comparative_Study_Towards_Designing_a_Hybrid_Architecture_of_Microservices_and_LLM-based_Multi-Agent_Systems.pdf  
- Trace（技术轨）程序：https://conf.researchr.org/details/apsec-2025/apsec-2025-papers/5/Trace-Test-Repair-via-Agent-based-Context-Extraction-with-LLMs  

---

## 四、同窗期内其它仍开放、相关度偏低的 A（备查）

| 时间 | 会议 | CCF | 动作节点 | 官网 |
|------|------|-----|----------|------|
| 题录约 07-25 · 全文约 08-01（PT） | VLDB / PVLDB Vol.20 八月轮 | A · 数据库 | 滚动月截稿 | https://www.vldb.org/2027/important-dates.html |
| 全文 08-03 | PPoPP 2027 | A · 并行 | 全文一包交 | https://ppopp27.sigplan.org/dates |

---

## 五、九月—十月相关目光（放后）

| 约略时间 | 会议 | CCF | 官网 / 日期页 |
|----------|------|-----|----------------|
| 约 2026-09（ICLR 2027 摘要/全文，以官宣为准） | ICLR | 第七版通告升 A；官网页同步情况以 https://www.ccf.org.cn/Academic_Evaluation/AI/ 为准 | https://iclr.cc/ |
| 约 2026-10-02 | FSE 2027 | A · 软件工程 | https://conf.researchr.org/dates/fse-2027 |
| ASE 2027 主截稿待官宣 | ASE | A · 软件工程 | 跟 https://conf.researchr.org/home/ase-2027 或系列 dates 页 |

NeurIPS 2026：摘要 2026-05-04 AoE，全文 2026-05-06 AoE（https://neurips.cc/Conferences/2026/Dates）。  
ICSE 2027：摘要 2026-06-23，全文 2026-06-30（https://conf.researchr.org/track/icse-2027/icse-2027-research-track）。

---

## 六、你接下来的顺序

1. **AAAI 全文 PDF**（Author Kit + 复现清单）→ 07-28 前上传。  
2. 精读 `reference/` 里 BAMAS / ZeroRouter / STEER，把对照与数据口径对齐进稿。  
3. 若保留第二个 A：07-24 前完成 **HPCA** 题录，叙事改成推理集群调度。  
4. SE 短文备选：08-03 **APSEC 早期研究成果轨**。
