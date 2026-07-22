# BudgetFlow：按论文主题筛选的 CCF A 类目标

时间基准：2026 年 7 月 22 日。

## 0. 先看论文是什么

BudgetFlow 研究的是：一批多智能体 / 软件工程式任务**共享一个硬预算**，按任务价值、估计 token 需求、模型适配把算力分出去，用验证器结算，目标是提高已验证解决价值（TRV）及其效率。

因此相关社区是：

| 相关 | 理由 |
|------|------|
| 人工智能（智能体、模型路由、代价—性能） | 主叙事 |
| 软件工程（仓库级修复、验证、自动化 SE） | 证据域是 SWE-bench 风格任务 |
| 系统 / 体系结构（推理服务、调度、资源分配） | 可改写成 runtime / 预算调度，但要换叙事 |
| 数据挖掘 / 检索（批决策、资源分配） | 边缘相关 |
| 交叉里的 WWW | 边缘相关 |

**直接排除的领域（整领域 A 类会都不进候选）：**

| 排除 | 理由 |
|------|------|
| 计算机网络 | 与任务价值预算无关 |
| 网络与信息安全 | 安全攻防，不对口 |
| 计算机科学理论 | 形式理论，不对口 |
| 计算机图形学与多媒体 | 视觉 / 图形，不对口 |
| 人机交互与普适计算 | 交互体验主线，不对口 |

目录来源：中国计算机学会官网分领域页（2026-07-22 逐页打开核对）。  
总入口：https://www.ccf.org.cn/Academic_Evaluation/By_category/

---

## 1. 相关领域：全部 A 类会议清单（来自官网）

下面不是「只有 7 个」，而是**与主题可能沾边的领域里，官网列出的全部 A 类会议**。

### 1.1 人工智能（官网页）

来源：https://www.ccf.org.cn/Academic_Evaluation/AI/

| 会议 | 相关度初判 | 说明 |
|------|------------|------|
| **AAAI** | 9 · 高 | 主目标；预算多智能体、代价路由已有中稿先例 |
| **NeurIPS** | 7 · 高 | 学习系统 / 路由 / 效率；本周期已截稿 |
| **ICML** | 6 · 中高 | 学习方法与系统；本周期已截稿 |
| **ACL** | 5 · 中 | 偏语言；代码 / agent 偶发 |
| **CVPR** | 1 · 低 | 视觉，排除 |
| **ICCV** | 1 · 低 | 视觉，排除 |
| **IJCAI** | 6 · 中高 | 官网页仍列 A；正式通告称第七版降为 B——以官网页为准并记下冲突 |

正式通告还写 ICLR 升 A；**官网页今天仍未列出 ICLR**。若你单位按通告认 ICLR 为 A，则 ICLR 相关度约 7（路由 / 表示学习），下一截稿约在 2026 年 9 月。

### 1.2 软件工程 / 系统软件 / 程序设计语言（官网页）

来源：https://www.ccf.org.cn/Academic_Evaluation/TCSE_SS_PDL/

| 会议 | 相关度初判 | 说明 |
|------|------------|------|
| **ICSE** | 8 · 高 | SE 旗舰；仓库级修复 + 预算最贴 |
| **FSE** | 8 · 高 | 同上 |
| **ASE** | 8 · 高 | 自动化 SE，很贴 |
| **ISSTA** | 6 · 中高 | 测试与分析；可写验证 / 修复 |
| **OSDI** | 6 · 中高 | 系统实现；可写服务端预算调度 |
| **SOSP** | 5 · 中 | 操作系统原理；要强系统味 |
| **PLDI** | 2 · 低 | 语言实现，排除主投 |
| **POPL** | 2 · 低 | 语言理论，排除主投 |
| **OOPSLA** | 3 · 低 | 语言 / 对象系统，弱相关 |
| **FM** | 2 · 低 | 形式化方法，排除主投 |

### 1.3 计算机体系结构 / 并行与分布 / 存储（官网页）

来源：https://www.ccf.org.cn/Academic_Evaluation/ARCH_DCP_SS/

| 会议 | 相关度初判 | 说明 |
|------|------------|------|
| **ASPLOS** | 5 · 中 | 体系 + 系统；LLM serving 可投 |
| **EuroSys** | 5 · 中 | 欧洲系统会 |
| **USENIX ATC** | 5 · 中 | 系统实践 |
| **HPCA** | 4 · 中低 | 硬件 / 推理集群；须改叙事 |
| **MICRO** | 3 · 低 | 微架构 |
| **ISCA** | 3 · 低 | 体系结构旗舰 |
| **PPoPP** | 2 · 低 | 并行编程 |
| **SC** | 2 · 低 | HPC |
| **FAST** | 2 · 低 | 存储 |
| **DAC** | 1 · 低 | EDA |

### 1.4 数据库 / 数据挖掘 / 内容检索（官网页）

来源：https://www.ccf.org.cn/Academic_Evaluation/DM_CS/

| 会议 | 相关度初判 | 说明 |
|------|------------|------|
| **SIGKDD** | 4 · 中低 | 可硬写成批决策 / 分配；题录已过 |
| **VLDB** | 2 · 低 | 数据库引擎；滚动截稿仍开 |
| **SIGMOD** | 2 · 低 | 数据库 |
| **ICDE** | 2 · 低 | 数据工程 |
| **SIGIR** | 2 · 低 | 信息检索 |

### 1.5 交叉 / 综合 / 新兴（官网页）

来源：https://www.ccf.org.cn/Academic_Evaluation/Cross_Compre_Emerging/

| 会议 | 相关度初判 | 说明 |
|------|------------|------|
| **WWW** | 4 · 中低 | Web / 平台系统；边缘 |
| **RTSS** | 1 · 低 | 实时系统，排除 |
| **WINE** | 1 · 低 | 网络经济，排除 |

---

## 2. 筛选后的「相关 A 类」主名单

去掉低相关（视觉、PL 理论、EDA、实时等）之后，**值得认真看的 A 类**如下。

### 高相关（≥7）

| 会议 | 领域 | 当前窗口（2026-07-22） | 官方依据 |
|------|------|------------------------|----------|
| **AAAI 2027** | 人工智能 | **开放**：摘要今晚；全文 07-28 | https://aaai.org/conference/aaai/aaai-27/submission-instructions/ |
| **ICSE** | 软件工程 | **已关**：ICSE 2027 摘要 06-23、全文 06-30 | https://conf.researchr.org/track/icse-2027/icse-2027-research-track |
| **FSE** | 软件工程 | 下一截稿约 **2026-10-02**（本文件不作今晚动作） | https://conf.researchr.org/dates/fse-2027 |
| **ASE** | 软件工程 | ASE 2026 研究轨已过；ASE 2027 主截稿待官宣 | https://conf.researchr.org/dates/ase-2026 |
| **NeurIPS** | 人工智能 | **已关**：2026 摘要 05-04、全文 05-06 | https://neurips.cc/Conferences/2026/Dates |
| **ICML** | 人工智能 | 本周期已关（通常年初截稿） | 以当年 CFP 为准 |
| **ICLR**（若认第七版通告） | 人工智能 | 约 **2026-09** 截稿（本文件不作今晚动作） | 以 ICLR 官网当年 CFP 为准 |

### 中相关（4–6）

| 会议 | 领域 | 当前窗口 | 官方依据 |
|------|------|----------|----------|
| **ISSTA** | 软件工程 | 本窗口无从零主投节奏 | 以当年 CFP 为准 |
| **OSDI / SOSP** | 系统 | 通常春夏周期；本窗口非主开 | 以 USENIX / ACM 当年 CFP 为准 |
| **ASPLOS / EuroSys / ATC** | 系统 | 本窗口非主开 | 以当年 CFP 为准 |
| **ACL** | NLP | 本周期已关 | 以 ACL 当年 CFP 为准 |
| **HPCA 2027** | 体系结构 | **开放**：题录 07-24；全文 07-31 | https://conf.researchr.org/track/hpca-2027/hpca-2027-main-conference |
| **SIGKDD** | 数据 | 题录约 07-19 **已过** | 以 KDD 官网为准 |
| **WWW** | 交叉 | 本窗口非主开 | 以 TheWebConf 当年 CFP 为准 |

### 低相关但仍开放的 A（备胎，须改叙事）

| 会议 | 窗口 | 官方依据 |
|------|------|----------|
| **PPoPP 2027** | 全文 08-03 | https://ppopp27.sigplan.org/dates |
| **VLDB / PVLDB** 滚动 | 题录约每月 25 日；全文约每月 1 日（PT） | https://www.vldb.org/2027/important-dates.html |

---

## 3. 七八月真正能动手的目标

在「相关 A」里，**现在还能从零新开**的只有：

| 优先 | 会议 | CCF | 相关度 | 动作 |
|------|------|-----|--------|------|
| **1** | **AAAI 2027** | A · 人工智能 | 9 | 今晚摘要；07-28 全文 |
| **2** | **HPCA 2027** | A · 体系结构 | 4 | 仅当改写成推理集群 / 调度时；题录 07-24 |
| （非 A） | **APSEC 2026 早期研究成果轨** | C · 软件工程 | 7 | 08-03 交 5 页；SE 口味最近的正式口 |

高相关 SE A（ICSE / FSE / ASE）和 NeurIPS / ICML **不是不存在**，而是**本窗口截稿已过或尚未到下一轮**。ICSE 2027 刚在 6 月底关；FSE 2027 约 10 月 2 日；ICLR（若认 A）约 9 月。

同一篇稿件只投一个正式会议。

**AAAI：** https://openreview.net/group?id=AAAI.org/2027/Conference

---

## 4. AAAI 格式（今晚 vs 全文）

**今晚摘要：不用套模板、不用交 PDF。** 真实完整题目 + 摘要即可。

**全文（07-28 AoE）：必须用 AAAI-27 Author Kit**——双栏、US Letter、正文 ≤7 页、参考文献可到总 9 页、双盲、另传复现清单。  
https://aaai.org/conference/aaai/aaai-27/submission-instructions/

---

## 5. 主投会：该会已接收论文（各 3 篇 + PDF）

### AAAI（AAAI-26 正式录用）

| 论文 | 看什么 | PDF |
|------|--------|-----|
| BAMAS | 预算约束多智能体构建 | https://ojs.aaai.org/index.php/AAAI/article/download/40226/44187 |
| ZeroRouter | 代价感知零样本路由 | https://ojs.aaai.org/index.php/AAAI/article/view/40970/44931 · https://arxiv.org/pdf/2601.06220 |
| STEER | 步级大小模型路由 | https://ojs.aaai.org/index.php/AAAI/article/download/40413/44374 · https://arxiv.org/pdf/2511.06190 |

### APSEC（APSEC 2025 程序中的录用文）

| 论文 | 看什么 | PDF |
|------|--------|-----|
| SEMAP（早期研究成果轨） | 多智能体 SE 协议 | https://arxiv.org/pdf/2510.12120 |
| Hybrid Microservices + LLM-MAS（技术全文轨） | 多智能体工程架构 | https://pureadmin.qub.ac.uk/ws/portalfiles/portal/660480405/A_Comparative_Study_Towards_Designing_a_Hybrid_Architecture_of_Microservices_and_LLM-based_Multi-Agent_Systems.pdf |
| Trace（技术全文轨） | 仓库级 agent 测试修复 | 程序 https://conf.researchr.org/details/apsec-2025/apsec-2025-papers/5/Trace-Test-Repair-via-Agent-based-Context-Extraction-with-LLMs · DOI https://doi.org/10.1109/APSEC66846.2025.00005 |

### HPCA（HPCA 2025 录用）

| 论文 | 看什么 | PDF |
|------|--------|-----|
| DynamoLLM | 推理集群能耗 / SLO 调度 | https://arxiv.org/pdf/2408.00741 |
| BitMoD | LLM 量化加速 | https://arxiv.org/pdf/2411.11745 |
| InstAttention（预印本 InstInfer） | 长上下文 attention 卸载 | https://arxiv.org/pdf/2409.04992 |

---

## 6. 执行顺序

1. **今晚：** AAAI 摘要登记。  
2. **到 07-28：** AAAI 格式全文 + 复现清单；精读 BAMAS / ZeroRouter / STEER。  
3. **若走 SE 短文：** 08-03 前 APSEC 早期研究成果轨；读 SEMAP 等三篇。  
4. **高相关 A 的下一波：** ICSE 已过 → 盯 **FSE（约 10-02）**、**ASE 2027**、以及（若认通告）**ICLR（约 9 月）**。
