# BudgetFlow：CCF 可投目标（仅 A/B/C）

时间基准：**2026-07-22 12:00（北京）**。

**硬过滤：** 只保留 **CCF 第七版 A/B/C 正式会议**。Workshop / ARR→EACL（EACL **不在**第七版目录）全部删除。  
**投稿前提：** 你 **从未交过任何 abstract**；下列均为 **从零新开稿**。  
**模型说明：** 你要求只用 Grok 3 做子代理调研——当前 Cursor 子代理 **没有 Grok 3**（可用含 `cursor-grok-4.5-high`）。本文件结论由当前会话直接核官网 + CCF 第七版 PDF + 可下载论文 PDF 写成。

---

## 调研结论置顶（先看这里）

### 七月从零能投的 CCF，真实清单

| # | 会 | CCF | 从零能否立刻开稿 | 截稿 | 相关度 | 判决 |
|---|-----|-----|------------------|------|--------|------|
| **1** | **AAAI-27 Main** | **A**（人工智能） | **能——但今天必须开稿** | 开稿/题录截止约 **今晚北京 ~19:59**（07-21 AoE）；全文 **07-28** | **高**（已有 budget-aware multi-agent） | **唯一七月顶会窗口** |
| **2** | **APSEC 2026 ERA** | **C**（软件工程） | **能**（直接交 PDF，无“上周 abstract”门槛） | **08-03** | **中高**（AI4SE / agent） | **最近的 SE 正式口** |
| **3** | **SANER 2027** | **B**（软件工程） | 现在可准备，**九月才交** | abs/full 约 **09-21 / 09-25** | **中**（演化/分析/修复） | **目光放这里做下一档 B** |
| **4** | **AAMAS 2027** | **B**（人工智能） | 现在可准备，**约十月才交** | 官网暂定 **Oct 2026** | **中高**（multi-agent） | **目光放这里做 agent 向 B** |

**没有第 5 个七月立刻能交的、又对口的 CCF A/B。**  
ICECCS / APSEC Technical（07-20）、ICSE/FSE 等七月前或九月后窗口，**不在「立刻从零」里**。

**目光该放哪：**

1. **今天晚上之前：AAAI**（唯一 CCF A；不开稿 = 七月顶会归零）  
2. **八月初：APSEC ERA**（CCF C，5 页 early empirical）  
3. **九月/十月：SANER（B）或 AAMAS（B）**——不是七月立刻交，但是下一档正经 CCF B  

**Dual-submission：** AAAI 与 APSEC ERA / SANER / AAMAS 同文 **不能并行 archival**。一次只锁一个主投。

### 相关证据怎么读（有 PDF，没有「一整本杂志打包」也照样能读）

AAAI **没有**像某些 OS 会那样一个「全年所有论文一个 PDF」的方便册；正规做法是：

- **分卷页面：** [AAAI-26 Technical Tracks 35](https://ojs.aaai.org/index.php/AAAI/issue/view/717)（Multiagent Systems 卷）  
- **单篇 PDF 直链（必下）：**

| 论文 | 为何相关 | PDF |
|------|----------|-----|
| **BAMAS**（AAAI-26）budget-aware multi-agent | **最近邻**：显式预算下选 LLM + 拓扑 | https://ojs.aaai.org/index.php/AAAI/article/download/40226/44187 |
| **RouteLLM**（ICLR-25，AAAI 审稿常引） | per-query 路由 baseline 标杆 | https://proceedings.iclr.cc/paper_files/paper/2025/file/5503a7c69d48a2f86fc00b3dc09de686-Paper-Conference.pdf |
| **SEMAP**（APSEC 2025 ERA） | APSEC ERA 口味：multi-agent SE + 实证 | https://arxiv.org/pdf/2510.12120 |
| **Chart2Code-MoLA**（APSEC 2025 Technical） | APSEC「routing/efficiency」近邻（MoE，不是 batch budget） | https://arxiv.org/pdf/2511.23321 |

细节、baseline、数据集见下方子页。

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
