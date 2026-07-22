# BudgetFlow：CCF 可投目标（仅 A/B/C）

时间基准：**2026-07-22 12:10（北京）**。  
数据源：[ccf4sc 实时 DDL](https://ccf.tjunsl.com/) + 各会官网（HPCA / KDD / INFOCOM / VLDB）。

**硬过滤：** 只保留 **CCF 第七版 A/B/C 正式会议**。Workshop 全删。  
**投稿前提：** 从零新开稿（你还没交过任何题录）。  
**说明：** 八月 **不是没有 A**——有一串体系结构/网络/数据库/安全 A；之前漏报是因为我按「必须强 AI/SE 相关」滤太狠。下面 **分相关度** 写清楚。

---

## 调研结论置顶

### A. 七月立刻能动手的 4 个候选（从零）

| # | 会 | CCF | 今天能否开稿 | 关键截稿 | 相关度 | 官网/投稿 |
|---|-----|-----|--------------|----------|--------|-----------|
| **1** | **AAAI-27 Main** | **A** 人工智能 | **今晚前必须开** | 题录约 **今晚 ~19:59**；全文 **07-28** | **高** | [OpenReview](https://openreview.net/group?id=AAAI.org/2027/Conference) · [说明](https://aaai.org/conference/aaai/aaai-27/submission-instructions/) |
| **2** | **HPCA 2027** | **A** 体系结构 | **能**（题录还开） | 题录 **07-24 AoE**；全文 **07-31 AoE** | **低–中**（写成 LLM/agent serving · runtime · 资源调度才蹭得上） | [CFP](https://conf.researchr.org/track/hpca-2027/hpca-2027-main-conference) |
| **3** | **VLDB 2027（本轮）** | **A** 数据库 | **能**（滚动轮次） | 本轮题录约 **07-26**；全文 **08-02** | **低**（硬蹭：workload / cost-aware scheduling；审稿会问你是不是 DB） | [vldb.org/2027](https://www.vldb.org/2027/) |
| **4** | **APSEC 2026 ERA** | **C** 软件工程 | **能**（直接交 PDF） | **08-03** | **中高**（AI4SE） | [ERA](https://conf.researchr.org/track/apsec-2026/apsec-2026-papers) · [EasyChair](https://easychair.org/conferences/?conf=apsec2026) |

**主投排序：** **① AAAI（今晚）→ ② APSEC ERA（正统 SE C）→ ③ HPCA 仅当你要硬冲系统 A 且愿意改包装 → ④ VLDB 基本不建议。**

**已错过题录、七月别再幻想从零开的 A：**

| 会 | CCF | 原因 |
|----|-----|------|
| SIGKDD 2027 | A | 题录 **07-19** 已过；全文 07-26 也救不了新开稿 |
| INFOCOM 2027 | A | 题录 **07-17** 已过 |

---

### B. 八月到底有没有 CCF A / B？——有

来自 [ccf.tjunsl.com](https://ccf.tjunsl.com/)（2026-07-22 更新）：

#### 八月 CCF **A**（真实存在）

| 会 | 截止（约） | 领域 | 和 BudgetFlow |
|----|------------|------|----------------|
| **HPCA 2027** | 题录 07-24 / 全文 07-31 | 体系结构 | 蹭边：agent/LLM **runtime · cache · scheduling** |
| **INFOCOM 2027** | 全文约 07-24（题录已过） | 网络 | **从零已晚** |
| **VLDB 2027** | 本轮 08-02 | 数据库 | 蹭边弱 |
| **UbiComp/ISWC 2026** | 08-02 | HCI/普适 | 基本不相关 |
| **PPoPP 2027** | 08-04 | 并行 | 蹭边弱（并行调度） |
| **NDSS 2027** | 08-20 | 安全 A | 不相关（除非硬写 agent 安全） |
| **USENIX Security 2027** | 08-26 | 安全 A | 不相关 |

#### 八月 CCF **B**

| 会 | 截止（约） | 说明 |
|----|------------|------|
| **CSFW 2027** | 08-04 | 安全 B，和你们不对口 |
| **EMNLP 2026 commitment** | 08-02 | CCF **B**，但必须 **五月 ARR 已审完** 才能 commit——**从零开不了** |
| **ARR Aug → EACL** | 08-03 交 ARR | EACL **不在** CCF 第七版；别当 CCF B 报 |

**八月没有「又一个 AAAI 这种正对口的 AI A」。**  
八月的 A 主要是 **系统/网络/库/安全**；要正统 AI/SE 顶会，下一档是：

| 会 | CCF | 大约截稿 | 相关度 |
|----|-----|----------|--------|
| **ASPLOS 2027** | A 系统 | ~09-09 | 中（AI/ML systems 包装） |
| **EuroSys 2027 Fall** | A 系统 | ~09-17/24 | 中 |
| **FSE 2027** | **A 软件工程** | ~10-02 | **高（SE 主战场）** |
| **SANER 2027** | **B 软件工程** | ~09-21 | 中 |
| **AAMAS 2027** | **B 人工智能** | ~10（TBC） | 中高 |

---

### C. 你今晚 + 本周目光

1. **今晚：AAAI OpenReview 开稿**（唯一正对口 CCF A）  
   https://openreview.net/group?id=AAAI.org/2027/Conference  
2. **若还想多占一个系统 A 坑：** **07-24 前** 开 **HPCA** 题录（接受「蹭边」前提）  
3. **八月 SE 正式：** **APSEC ERA（C）**  
4. **秋：FSE（A SE）/ SANER（B）/ AAMAS（B）**

**Dual-submission：** 同文同时投多个 archival = 违规。AAAI 开了就别并行 HPCA/ERA 同稿。

### 相关 PDF（先下这三个）

| 论文 | PDF |
|------|-----|
| BAMAS（AAAI-26） | https://ojs.aaai.org/index.php/AAAI/article/download/40226/44187 |
| RouteLLM（ICLR-25） | https://proceedings.iclr.cc/paper_files/paper/2025/file/5503a7c69d48a2f86fc00b3dc09de686-Paper-Conference.pdf |
| SEMAP（APSEC ERA） | https://arxiv.org/pdf/2510.12120 |

细节子页：[`venue_aaai27_budgetflow.md`](./venue_aaai27_budgetflow.md) · [`venue_apsec2026_era_budgetflow.md`](./venue_apsec2026_era_budgetflow.md) · [`venue_saner2027_budgetflow.md`](./venue_saner2027_budgetflow.md) · [`venue_aamas2027_budgetflow.md`](./venue_aamas2027_budgetflow.md)

---

## 1. AAAI-27 Main｜CCF A｜**今天必须动手**

**子页：** [`venue_aaai27_budgetflow.md`](./venue_aaai27_budgetflow.md)

| 项 | 内容 |
|----|------|
| 官网 | https://aaai.org/conference/aaai/aaai-27/ |
| 投稿 | https://openreview.net/group?id=AAAI.org/2027/Conference |
| 页数 | 正文 ≤7 + 参考文献至多总 9 |
| 从零开稿 | OpenReview 注册 → **今天交完整 title+abstract** → **07-28 交 PDF** |
| 反馈 | Phase 1 拒约 **09-24**（拒也能见审稿） |

**相关度：高。** AAAI-26 已收 **BAMAS**（预算约束多代理）。你们要比的是 **batch 共享硬预算 + Task Value + SWE verifier + TRV**，不是再写一个 per-query 路由器。

**他们常用 baseline（从 BAMAS / 路由线）：** AutoGen / MetaGPT / ChatDev；cheap-only / strong-only；RouteLLM 类 learned router。  
**他们常用数据：** GSM8K / MBPP / MATH / HumanEval；**很少**你们这种 30-task SWE-bench 批 + 美元硬帽——这是差异化也是风险。

**立刻动作：** 今晚 AoE 前开稿；否则七月 CCF A 没了。

---

## 2. APSEC 2026 ERA｜CCF C｜08-03 从零交 PDF

**子页：** [`venue_apsec2026_era_budgetflow.md`](./venue_apsec2026_era_budgetflow.md)

| 项 | 内容 |
|----|------|
| Track | https://conf.researchr.org/track/apsec-2026/apsec-2026-papers |
| 投稿 | https://easychair.org/conferences/?conf=apsec2026 |
| 页数 | Regular **≤5 页含参考文献**；Short ≤2 |
| 审稿 | 双盲；≥3 审稿人 |
| 通知 | **09-21** |

**相关度：中高。** APSEC 近年收 AI4SE / multi-agent / 效率；Technical 主轨 07-20 **已过**，只剩 ERA。

**他们常用 baseline：** 无协议 MAS、ChatGPT vs 专用模型、覆盖率工具对比等。  
**他们常用数据：** HumanEval、TFix、Big-Vul、漏洞集、图表→代码集。  
**你们应对标：** cheap / strong / learned-router / budget-only + 固定共享预算。

---

## 3. SANER 2027｜CCF B｜九月（目光，不是今晚）

**子页：** [`venue_saner2027_budgetflow.md`](./venue_saner2027_budgetflow.md)

| 项 | 内容 |
|----|------|
| CCF | **B**（软件工程） |
| 截稿 | 约 **2026-09-21**（以官网为准） |
| 口味 | 软件分析、演化、再工程、修复 |

**相关度：中。** 可写成「仓库级 issue 批在共享预算下的价值感知分配」。七月不能交，但是 **下一档正经 SE CCF B**。

---

## 4. AAMAS 2027｜CCF B｜约十月（目光）

**子页：** [`venue_aamas2027_budgetflow.md`](./venue_aamas2027_budgetflow.md)

| 项 | 内容 |
|----|------|
| CCF | **B**（人工智能 · 多代理） |
| 官网 | https://warwick.ac.uk/fac/sci/dcs/aamas2027/ |
| 截稿 | 官网写 **Oct 2026（TBC）** |

**相关度：中高。** 多代理旗舰会；预算/资源分配叙事比 SANER 更贴 AI。七月不能交。

---

## 已删除 / 不要再看

| 类型 | 例子 | 原因 |
|------|------|------|
| Workshop | AgenticDev / MAS-GAIN / RASE / TRUST / SWGeno… | **无 CCF** |
| ARR→EACL | EACL 2027 | **第七版目录无 EACL** |
| 已过 CCF | ICECCS、APSEC Technical（07-20） | 截稿已过 |
| 需上周 abstract 才能续交 | （不适用 AAAI——AAAI 是 **今天仍可新开**） | — |

---

## 一句话执行令

**今天：AAAI OpenReview 从零开稿（唯一 CCF A）。**  
**八月：APSEC ERA（CCF C）。**  
**目光：SANER / AAMAS（CCF B，秋）。**  
**先下 PDF：BAMAS → RouteLLM → SEMAP。**
