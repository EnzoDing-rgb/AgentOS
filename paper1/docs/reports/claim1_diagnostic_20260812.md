# BudgetFlow 6×30 主线实验 · 2026-08-12

> 一份自洽数据 · 六策略同场 · 完成型预算 · 含 segment 级新策略。
> 本文档整合：证据诊断背景、6×30 实验设计、最终结果、关键发现、数据集调研、当前问题与下一步。

| | | | |
|---|---|---|---|
| **180 / 180** 任务-策略对完成 | **6** 策略同场（含第 6 策略） | **$91.5** 六 lane 总花费 | **13.0** TRV 领跑值 |

---

## 一、背景：旧证据的脆弱性（诊断结论）

在跑 6×30 之前，仓库里 4 个旧运行（4x30 + 三个 5x30）被做了跨运行交叉诊断，三个实锤结论：

1. **旧赢面是单任务运气**：4x30 的赢（TRV 18.5 vs 18.0）完全来自 `flask-4992`（2.5 分）翻转给 BudgetFlow——换平价值表一重打分就变输。
2. **结果跨运行翻转**：任务顺序相同、唯一变量是价值表（5 个任务 2.5 vs 1.0/1.5），BudgetFlow 的胜负随之翻转（1 胜 3 负，含一个被归档的 -6.0 完整运行）。
3. **具体失败机制**：幻影高价值陷阱——为"值钱但所有人解不出"的任务预留预算（$1.22 ≈ $1.22，恰好是纯 T3 解决尾部可解任务的费用）。

结论：旧证据"跨运行不可比"，必须用**一份自洽数据**重建。

---

## 二、6×30 实验设计

| # | 策略 | 一句话 |
|---|---|---|
| 1 | **无脑便宜 T2** | 所有任务一律 DeepSeek-V4-Pro |
| 2 | **无脑最强 T3** | 所有任务一律 GPT-5.4 |
| 3 | **学得路由** | 按任务特征学选模型 · 看不见价值 |
| 4 | **只看预算** | 按剩余预算决策 · 看不见价值 |
| 5 | **BF 任务级** | 价值感知 · 任务级分配（原主线） |
| 6 | **BF 分段级**（新增） | 任务级 + 任务内进展门控升级/止损 |

**协议**：固定 30 任务 · 激进 criticality 价值表（10 高价值，含 4×2.5）· 共享硬预算 cap $20.55（完成型，纯 T2 lane 可跑满）· 价值执行前冻结预注册。

**环境就绪**：Python 3.11 重建 · 六仓库全量镜像 · seaborn/pylint harness venv 预暖 · 6 策略预检门 PASS · 运行全程零 infra 错误。

---

## 三、最终结果

### 总解决价值 TRV

<svg width="560" height="200" viewBox="0 0 560 200" xmlns="http://www.w3.org/2000/svg" style="font-family:system-ui,sans-serif;font-size:12px">
  <g font-size="12" fill="#52514e" text-anchor="end">
    <text x="108" y="26">无脑便宜 T2</text><text x="108" y="58">学得路由</text><text x="108" y="90">无脑最强 T3</text><text x="108" y="122">BF 任务级</text><text x="108" y="154">只看预算</text><text x="108" y="186">BF 分段级</text>
  </g>
  <g>
    <rect x="118" y="15" width="330" height="16" rx="4" fill="#2a78d6"/><text x="456" y="28" font-weight="700" font-size="12">13.0</text>
    <rect x="118" y="47" width="330" height="16" rx="4" fill="#1baf7a"/><text x="456" y="60" font-weight="700" font-size="12">13.0</text>
    <rect x="118" y="79" width="317" height="16" rx="4" fill="#eb6834"/><text x="456" y="92" font-weight="700" font-size="12">12.5</text>
    <rect x="118" y="111" width="290" height="16" rx="4" fill="#e87ba4"/><text x="456" y="124" font-weight="700" font-size="12">11.5</text>
    <rect x="118" y="143" width="290" height="16" rx="4" fill="#eda100"/><text x="456" y="156" font-weight="700" font-size="12">11.5</text>
    <rect x="118" y="175" width="267" height="16" rx="4" fill="#008300"/><text x="456" y="188" font-weight="700" font-size="12">10.5</text>
  </g>
  <g font-size="10" fill="#898781"><text x="118" y="196">0</text><text x="448" y="196" text-anchor="end">13</text></g>
</svg>

### 价值效率 TRV/$

<svg width="560" height="200" viewBox="0 0 560 200" xmlns="http://www.w3.org/2000/svg" style="font-family:system-ui,sans-serif;font-size:12px">
  <g font-size="12" fill="#52514e" text-anchor="end">
    <text x="108" y="26">无脑最强 T3</text><text x="108" y="58">BF 分段级</text><text x="108" y="90">学得路由</text><text x="108" y="122">BF 任务级</text><text x="108" y="154">无脑便宜 T2</text><text x="108" y="186">只看预算</text>
  </g>
  <g>
    <rect x="118" y="15" width="330" height="16" rx="4" fill="#eb6834"/><text x="456" y="28" font-weight="700" font-size="12">1.27</text>
    <rect x="118" y="47" width="271" height="16" rx="4" fill="#008300"/><text x="456" y="60" font-weight="700" font-size="12">1.04</text>
    <rect x="118" y="79" width="215" height="16" rx="4" fill="#1baf7a"/><text x="456" y="92" font-weight="700" font-size="12">0.83</text>
    <rect x="118" y="111" width="188" height="16" rx="4" fill="#e87ba4"/><text x="456" y="124" font-weight="700" font-size="12">0.72</text>
    <rect x="118" y="143" width="165" height="16" rx="4" fill="#2a78d6"/><text x="456" y="156" font-weight="700" font-size="12">0.63</text>
    <rect x="118" y="175" width="155" height="16" rx="4" fill="#eda100"/><text x="456" y="188" font-weight="700" font-size="12">0.60</text>
  </g>
</svg>

### 各 lane 花费（美元，cap $20.55）

<svg width="560" height="200" viewBox="0 0 560 200" xmlns="http://www.w3.org/2000/svg" style="font-family:system-ui,sans-serif;font-size:12px">
  <g font-size="12" fill="#52514e" text-anchor="end">
    <text x="108" y="26">无脑最强 T3</text><text x="108" y="58">BF 分段级</text><text x="108" y="90">学得路由</text><text x="108" y="122">BF 任务级</text><text x="108" y="154">只看预算</text><text x="108" y="186">无脑便宜 T2</text>
  </g>
  <g>
    <rect x="118" y="15" width="158" height="16" rx="4" fill="#eb6834"/><text x="456" y="28" font-weight="700" font-size="12">9.85</text>
    <rect x="118" y="47" width="163" height="16" rx="4" fill="#008300"/><text x="456" y="60" font-weight="700" font-size="12">10.13</text>
    <rect x="118" y="79" width="252" height="16" rx="4" fill="#1baf7a"/><text x="456" y="92" font-weight="700" font-size="12">15.72</text>
    <rect x="118" y="111" width="256" height="16" rx="4" fill="#e87ba4"/><text x="456" y="124" font-weight="700" font-size="12">15.96</text>
    <rect x="118" y="143" width="309" height="16" rx="4" fill="#eda100"/><text x="456" y="156" font-weight="700" font-size="12">19.24</text>
    <rect x="118" y="175" width="330" height="16" rx="4" fill="#2a78d6"/><text x="456" y="188" font-weight="700" font-size="12">20.55</text>
  </g>
</svg>

### 明细表

| 策略 | 完成 | PASS | 花费 $ | TRV | TRV/$ |
|---|---:|---:|---:|---:|---:|
| **无脑便宜 T2** | 30 | **11** | 20.55 | **13.0** | 0.63 |
| **学得路由** | 30 | **11** | 15.72 | **13.0** | 0.83 |
| 无脑最强 T3 | 30 | **11** | 9.85 | 12.5 | **1.27** |
| BF 任务级 | 29 | 10 | 15.96 | 11.5 | 0.72 |
| 只看预算 | 30 | 10 | 19.24 | 11.5 | 0.60 |
| BF 分段级 | 30 | 9 | 10.13 | 10.5 | 1.04 |

> ⚠️ **核心结论：这一轮运行里，价值感知机制没有赢。** TRV 并列第一的是「无脑便宜」与「学得路由」；两个 BudgetFlow 均垫底。极端策略即前沿，是当前操作条件的真实形状。

---

## 四、关键发现

| 发现 | 内容 |
|---|---|
| **极端策略即前沿** | 纯 T2（便宜到底）与学得路由并列 TRV 第一（13.0）；纯 T3 花费最少（$9.85）且 TRV/$ 最高（1.27）。中间态策略（两个 BF）反而不如两头。 |
| **价值信号未兑现** | BF 任务级与「只看预算」完全打平（11.5 = 11.5）——本轮里看见价值没有带来任何增量；学得路由（13.0）反超它。「价值感知 > 价值盲」在本轮不被支持。 |
| **任务级 BF 的 T2 保守主义** | 前 9 个任务里 8 个纯 T2 起步，轮数 23–53 vs 纯 T3 的 5–11。便宜模型空转烧钱（flask-4045 花 $1.04 未解出）——路由先验仍停留在「T3 很贵」的时代。 |
| **分段级尾部崩塌** | BF 分段级中段排第二（TRV 7.0），最终垫底（10.5）。进展门控的止损过激：$10.13 全场最少花费，但尾部能硬磨出来的任务被放弃。 |

---

## 五、数据集调研 · E2 文本任务

| 数据集 | 年份 | 人工标注 | 绝对评分 | 许可证 | 结论 |
|---|---|---|---|---|---|
| **SummEval** | 2020 | 专家 4 维评分（1600 条 × 8 人） | 原生 1–5 | 研究使用 | ✅ 使用 |
| **MT-Bench** | 2023 | 3.3K 专家判断 | 原生 1–10 | CC BY 4.0 | ✅ 使用 |
| AlpacaEval 2.0 | 2024 | 无（纯 LLM 成对胜率） | 非原生 | CC BY-NC | ⚠️ 放弃 |

**定稿**：E2 文本任务 = **4 × SummEval**（人类评分可验证 judge 对齐）+ **6 × MT-Bench**（原生绝对分、权威基准）。弃 AlpacaEval：无人工标签、绝对分非原生、非商用许可。judge 方案：冻结细则 + 盲评 + 与人类评分一致性对照。

---

## 六、当前问题与下一步

| 问题 / 下一步 | 内容 |
|---|---|
| 🔴 问题 1 | **核心主张在本轮不被支持**：「价值感知 > 价值盲」在本份数据上是反例；旧证据的赢面（4x30 的 flask-4992）已被证明是单任务运气。 |
| 🔴 问题 2 | **结果强依赖操作条件**：同任务集换价值表、换预算档胜负即翻转（旧审计已见）；本轮激进表 + 完成型预算下极端策略占优。 |
| 🟢 下一步 1 · 免费 | **oracle 与敏感性分析**：数据已完整，立即算——观测分层上限（价值感知天花板）、价值表重打分、预算档回放。回答「机制不行还是条件不给机会」。 |
| 🟢 下一步 2 | **路由先验校准 + E2 泛化**：任务级 BF 的 T2 保守主义是具体病灶（校准方向已定位）；E2 用 10+10 混合批次验证跨验证器形态的泛化性。 |

---

*数据源：`mainline_6x30_20260812`（180/180 完成，零 infra 错误，official crosscheck 清单已生成）。本文件内嵌 SVG 图表均为本地计算，GitHub 可直接渲染。*
