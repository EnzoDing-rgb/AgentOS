# AAAI-27 Main × BudgetFlow（CCF A）

时间：**2026-07-22**。证据级：官网 + AAAI-26 可下载 PDF。

## 从零能不能投？

**能，但窗口以小时计。**

- Abstract / 开稿：`2026-07-21 23:59 UTC-12` ≈ **北京 07-22 19:59**  
- Full PDF：`2026-07-28`  
- 规则：必须先有真实 title+abstract，才能交全文；placeholder 会被删。  
- 投稿：https://openreview.net/group?id=AAAI.org/2027/Conference  
- 说明：https://aaai.org/conference/aaai/aaai-27/submission-instructions/  
- 页数：正文 ≤7 + 参考文献至多总 9  

这不是「上周交过 abstract 才能续」——**今天从零注册 OpenReview 开稿也算 fresh start**。过了今晚，七月 CCF A 归零。

## 相关吗？接收过什么类似论文？

**相关：高。** Multiagent / LLM agents / resource allocation 都在 AAAI 主轨范围内。

### 必读 PDF（直接下载）

1. **BAMAS: Structuring Budget-Aware Multi-Agent Systems**（AAAI-26，Multiagent Systems）  
   - PDF：https://ojs.aaai.org/index.php/AAAI/article/download/40226/44187  
   - 卷页：https://ojs.aaai.org/index.php/AAAI/issue/view/717  
   - DOI 页：https://ojs.aaai.org/index.php/AAAI/article/view/40226  

2. **RouteLLM**（ICLR-25；AAAI 路由审稿常引对照）  
   - PDF：https://proceedings.iclr.cc/paper_files/paper/2025/file/5503a7c69d48a2f86fc00b3dc09de686-Paper-Conference.pdf  
   - arXiv：https://arxiv.org/pdf/2406.18665  

AAAI **没有**「全年论文一个大 PDF」的 OS 会式打包；用 issue 卷 + 单篇 download。

## BAMAS：写法 / baseline / 数据集

| 维 | 内容 |
|----|------|
| **问题** | 多代理系统如何在 **显式成本预算** 下选 LLM 池 + 协作拓扑 |
| **方法** | ILP 选模型 → RL 选拓扑 → 实例化执行 |
| **Baseline** | AutoGen、MetaGPT、ChatDev、Naive CostAware |
| **数据集** | GSM8K、MBPP、MATH（代码生成 + 数学） |
| **指标** | Accuracy、平均金钱成本、超预算次数、cost–performance 曲线；报告可降成本至约 **86%** |
| **写法** | 标准 AAAI：形式化 → 方法 → 表 + 消融 → 边界 |

## 和 BudgetFlow 的边界（审稿人会盯）

| | BAMAS / RouteLLM | BudgetFlow 应主张 |
|--|------------------|-------------------|
| 单位 | 单任务建 MAS / 单查询选模型 | **一批任务共享一个硬预算** |
| 价值 | 准确率（任务等权） | **预注册 Task Value → TRV** |
| 验收 | 基准对错 | **Verifier（SWE-bench 测试）** |
| 决策 | 选池/拓扑或 per-query 路由 | **跨任务分配强模型机会** |

## 审稿人偏好（推断）

- **奖：** 清晰新问题、形式化、强 baseline、cost–value 曲线、可复现 checklist  
- **罚：** 「又一个 router」；TRV 事后拟合；30 任务当全体证据；把 harness 当贡献  
- **你们应对标 baseline：** cheap-only、strong-only、learned task-router、budget-only、BudgetFlow  

## 判决

**七月唯一对口 CCF A。今晚不开稿 = 没有七月顶会。**
