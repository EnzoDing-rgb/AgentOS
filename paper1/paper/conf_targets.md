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

## 2. 相关工作总表（已发表 · 本地 PDF · 读过正文后的口径）

线索来源：`src/references.bib`、`docs/related_work.html`、AgenticDev 旧稿、以及按第七版会系检索到的近邻。  
收录规则：只收顶会或 CCF 会议上正式发表的论文；纯 arXiv 预印本不进本表，也不进 `reference/`。  
「低垂果实」一栏只谈**不必新开一大套付费实验**、写稿或对照命名上就能顺手做的事；若没有，就直说没有。

| # | 论文 · 去向 · 本地 PDF | 这篇论文在做什么（对照与数据） | 和 BudgetFlow 的差别 | 低垂果实（可顺手改什么） |
|---|------------------------|--------------------------------|----------------------|--------------------------|
| 1 | **BAMAS**<br>AAAI 2026 · CCF A<br>`BAMAS_AAAI26.pdf` | 在给定费用预算下搭建多智能体系统：先用整数线性规划选出一组既够用又不太贵的大模型，再用强化学习决定智能体之间用线性、星形等哪种协作拓扑，最后按选中的模型池和拓扑真正跑起来。对照方法包括 AutoGen、MetaGPT、ChatDev，以及按资源档位贪心选配置的 Naive-CostAware；数据用 GSM8K、MBPP、MATH。作者报告在达到相近正确率的同时，费用最多可降约 86%。 | BAMAS 管的是**单个任务内部**「该用哪些模型、智能体怎么连」；BudgetFlow 管的是**一批任务共用一个硬预算**时，稀缺的模型机会该分给谁、按任务价值怎么分配。 | **有。** Related Work 里把 BAMAS 明确写成「任务内、预算约束下的多智能体构建」，与我们的「批次级 Task Value 分配」对仗写清即可；不必复现他们的整数线性规划和拓扑强化学习。 |
| 2 | **ZeroRouter**<br>AAAI 2026 · CCF A<br>`ZeroRouter_AAAI26.pdf` | 在大约六十个大模型组成的模型池上做零样本查询级路由（训练时没见过目标模型也能用），并在「尽量准 / 尽量省钱 / 尽量低延迟」三组目标权重下比较。对照包括 CIT-LLM-Routing、RouteLLM、GraphRouter、FORC；评测约九套基准（含 IFEval、BBH、MATH、GPQA、MMLU-PRO，以及 ARC-C、HumanEval 等分布外集合）。 | 决策单位是**一条查询选哪个模型**；没有「多任务共享硬预算、按任务价值排队」这一层。 | **基本没有新实验。** 主线里本来就该有 cheap-only / strong-only / 学得或静态路由对照；把 ZeroRouter 当作「大规模模型池零样本路由」的引用代表即可，不必重跑六十模型池。 |
| 3 | **STEER**<br>AAAI 2026 · CCF A<br>`STEER_AAAI26.pdf` | 在推理过程中按**推理步骤**在小模型和大模型之间切换以省算力：在小模型生成下一步之前，看它输出分布上的置信程度（文中用 logits 上的置信分数，并用高斯混合模型做校准）；只有小模型对下一步不够有把握时，才把这一步交给大模型。对照分两组：一组依赖外部训练模块（例如用过程奖励模型做逐步筛选的 RSD，以及 Damani 等人在问题级别决定是否升级到大模型的方法）；另一组尽量不依赖外部训练模块（例如 SpecReason 一类设计）。数据包括 MATH500、AIME、Omni-Math、ACPBench、MuSiQue、KOR-Bench 等。作者报告在 AIME 上相对「全程大模型」大约多 20% 准确率、少约 48% 的浮点运算量。 | 这是**单条推理轨迹内部**的逐步模型切换，信号来自小模型自己的输出置信程度；不是批次任务之间的共享硬预算与 Task Value。 | **不相关，无需调整。** 不要为对齐 STEER 去加逐步置信路由实验；Related Work 里用一两句划清「步骤级置信路由 ≠ 批次级价值分配」即可。 |
| 4 | **RouteLLM**<br>ICLR 2025 · CCF A<br>`RouteLLM_ICLR25.pdf` | 用人类偏好数据训练路由器，在推理时为每条查询在「更强更贵的模型」和「更弱更便宜的模型」之间二选一。训练主要用 Chatbot Arena 的对战偏好，并可用 MMLU 验证集金标、以及 Nectar 上 GPT-4 裁判偏好做数据增强。评测用 MMLU、MT Bench、GSM8K；主对照是在费用约束下随机路由。作者报告在不明显牺牲质量时费用可降一半以上。 | 仍是**单查询、强弱二选一**；没有跨任务的价值竞争。 | **有，而且是我们本来就该有的对照命名。** 确保论文与实验矩阵里把「受 RouteLLM 启发的学得路由 / 任务级路由对照」写清楚、跑在同一共享硬预算和同一验证器下即可；不必按他们的 Arena 偏好数据重新训一套公开路由器。 |
| 5 | **GraphRouter**<br>ICLR 2025 · CCF A<br>`GraphRouter_ICLR25.pdf` | 把任务、查询、大模型建成一张异构图，用边预测估计「把某查询交给某模型」的效果和费用，从而在「效果优先 / 均衡 / 费用优先」三种权重设定下选模型；新模型进来时尽量少重训。数据包括 Alpaca、GSM8K、SQuAD、Multi-News 等拼成的多任务交互数据。作者报告相对既有路由器至少约 12.3% 的提升。 | 图路由仍然服务**单条查询选模型**；不回答「下一笔预算该给批次里哪一个任务」。 | **没有值得顺手复现的实验。** 引用时把它和 RouteLLM 一起归入「查询级路由」族即可。 |
| 6 | **Cascade Routing**<br>ICML 2025 · CCF A<br>`CascadeRouting_ICML25.pdf` | 把「事先选一个模型」的路由，和「从小到大依次调用、看质量估计再决定是否继续」的级联，统一成一个可证明的框架（文中的 cascade routing），并强调事后质量估计是否靠谱决定了省钱效果。对照包括单独做路由、单独做级联、以及常见的阈值级联。评测用 RouterBench，并且在 SWE-Bench 上也报了相对提升。 | 决策对象仍是**单条查询的模型调用链**；SWE-Bench 在这里是质量任务，不是「多任务共享硬预算 + 预注册任务价值」。 | **有一点，只在写作。** Related Work / 实验讨论里点明「同属 SWE 测试床，但他们做查询级级联，我们做批次级价值分配」；不必再实现他们的最优级联算法。 |
| 7 | **RouteNLP**<br>ACL 2026 Industry Track（ACL 主会为 CCF A）<br>`RouteNLP_ACL26.pdf` | 企业场景下跨多种自然语言任务的分层模型路由：难度感知路由器、用共形预测做阈值初始化的置信级联，以及「升级失败聚类 → 针对性蒸馏便宜模型 → 再训路由器」的闭环。对照包括 Always 最高档、Always 便宜档、随机、规则、HybridLLM、RouteLLM 等。他们构造了六任务基准，并在企业客服试点里跑了约八周、每天约五千条查询，报告推理费用约降 58%。 | 单位仍是企业**查询**；质量约束是任务类型上的验收，不是批次 Task Value 与验证型补丁结算。 | **不相关，无需调整实验。** 最多在 Related Work 用一句承认「产业界也在做费用–质量路由」，然后收回批次问题。 |
| 8 | **SWE-bench**<br>ICLR 2024 · CCF A<br>`SWEbench_ICLR24.pdf` | 评测框架本身：从真实 GitHub issue 与对应拉取请求构造两千余个软件工程题，用仓库测试判定补丁是否真正解决问题。原论文对照包括 GPT-3.5、GPT-4、Claude 2，以及他们微调的 SWE-Llama；另有 Lite 子集与约一万九千条训练实例。 | 它是**测试床与验证协议**；BudgetFlow 在其上研究预算治理，而不是再发明一套 issue 基准。 | **不相关，无需为「对齐 SWE-bench 论文」再开实验。** 保持任务集固定、价值冻结、验证器可信即可。 |
| 9 | **Avengers-Pro**（Beyond GPT-5）<br>DAI 2025 · CCF C<br>`AvengersPro_DAI25.pdf` | 测试时把查询嵌入、聚类，再按可调参数 α 在「效果」与「费用」之间打分，把查询路由到最合适的模型，从而画出相对单模型的帕累托前沿。数据包括 GPQA-Diamond、Humanity’s Last Exam、ARC-AGI、SimpleQA、LiveCodeBench 等约六套难题；模型池含 GPT-5-medium、Gemini-2.5-pro、Claude-opus-4.1 等。作者报告可在接近最强单模型表现时明显降费，或在相近费用下超过最强单模型。 | 优化的是**查询级性能–费用曲线**；没有预注册的任务价值，也没有一批任务抢同一硬预算。 | **有，且主要是写法。** 投稿 DAI 或写成本–效果图时，可借用「帕累托前沿 / 可调权衡参数」这种读者熟悉的叙述；不必重跑他们的八模型、六基准矩阵。 |
| 10 | **AgentNet**<br>NeurIPS 2025 · CCF A<br>`AgentNet_NeurIPS25.pdf` | 去中心化的大模型多智能体协作：智能体在动态有向无环图上按本地专长接任务、演化连接，并用检索增强记忆，避免一切都经过中心调度器。对照包括直接让单模型答题，以及 MetaGPT 这类中心化多智能体。数据覆盖数学（MATH）、逻辑问答（BBH）、工具调用（API-Bank）与代码类任务。 | 核心是**协作拓扑与去中心化**；预算与任务价值不是一等公民。 | **不相关，无需调整。** 不要为对齐 AgentNet 去改我们的批次预算实验。 |
| 11 | **SEMAP**<br>APSEC 2025 早期研究成果轨 · CCF C<br>`SEMAP_APSEC25.pdf` | 用多智能体搭软件工程流水线时，失败模式如何分类与观察。开发任务用基于 MetaGPT 的五角色设置，漏洞相关任务用三角色设置；数据包括 HumanEval，以及从 Big-Vul、CVEFixes 抽样的漏洞子集；度量用 MAST 失败分类，并用大模型当裁判。 | 焦点是**多智能体软件工程中的失败类型**；不是共享硬预算下的总解决价值。 | **仅当写 APSEC 短文时有一点。** 可顺手借用「失败分类 / 早期证据」的叙述框架，讨论 harness 或止损；不必复现他们的漏洞子集实验。 |
| 12 | **Hybrid Microservices + LLM-MAS**<br>APSEC 2025 技术轨 · CCF C<br>`HybridMAS_APSEC25.pdf` | 比较研究：从功能封装、编排、接口、自动纠正、通信、运维、质量属性、环境感知等八个架构维度，对照经典微服务与大模型多智能体，提出混合架构的研究问题。不是「谁在某个排行榜分数更高」的数值竞赛文。 | 谈的是**系统架构怎么拼**；不是预算分配策略与 TRV。 | **不相关，无需调整实验。** 写 SE 口味短文时最多借它的架构词汇；不要据此加实验。 |

**总判断（诚实版）：**  
真正和主线实验「顺手相关」的，主要是 RouteLLM 族路由对照的命名与同预算评测（第 4 条），以及 BAMAS / Cascade / Avengers-Pro 在 Related Work 里的分层写法（第 1、6、9 条）。其余多数条目的诚实结论是：**不相关，无需为对齐它们再做实验。** 没有发现「必须新开一大套付费实验才能摘到」的低垂果实。

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
