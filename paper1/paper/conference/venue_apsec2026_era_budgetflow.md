# APSEC 2026 ERA × BudgetFlow（CCF C）

时间：**2026-07-22**。APSEC Technical（07-20）已过；只谈 **ERA**。

## 从零能不能投？

**能。** EasyChair 直接交匿名 PDF，**不要求你上周已经交 abstract**。

- 截稿：**2026-08-03**  
- 通知：**2026-09-21**  
- Camera-ready：**2026-10-19**  
- Track：https://conf.researchr.org/track/apsec-2026/apsec-2026-papers  
- EasyChair：https://easychair.org/conferences/?conf=apsec2026  
- 页数：Regular **≤5（含参考文献）**；Short ≤2  
- 审稿：双盲，≥3 人  
- CCF：第七版 **软件工程 C 类**（APSEC）

## 相关吗？接收过什么类似论文？

**相关：中高。** ERA 明确收 early / preliminary；近年 AI4SE、multi-agent、效率都见过。

### 必读 PDF

1. **SEMAP — Towards Engineering Multi-Agent LLMs: A Protocol-Driven Approach**（APSEC 2025 ERA）  
   - PDF：https://arxiv.org/pdf/2510.12120  
   - HTML：https://arxiv.org/html/2510.12120  

2. **Chart2Code-MoLA: Efficient Multi-Modal Code Generation via Adaptive Expert Routing**（APSEC 2025 Technical）  
   - PDF：https://arxiv.org/pdf/2511.23321  

3. **ChatGPT for Vulnerability Detection… How Far Are We?**（APSEC 2023 ERA，大样本负结果范例）  
   - PDF：https://arxiv.org/pdf/2310.09810  

APSEC 一般是 IEEE 分篇入库，**没有**「一册打尽」的巨型免费 PDF；靠 arXiv / IEEE Xplore 单篇。

## SEMAP：写法 / baseline / 数据集

| 维 | 内容 |
|----|------|
| **问题** | LLM 多代理缺 SE 结构 → under-spec / 协调错位 / 验证不当 |
| **方法** | 协议层：行为契约、结构化消息、生命周期验证（A2A） |
| **评价** | MAST 失败分类；失败计数下降（开发最高约 69.6%） |
| **数据** | HumanEval、ProgramDev、漏洞子集（Python/C++） |
| **写法** | 短页 ERA：问题 → 协议 → 实证表 → 局限 |

## Chart2Code-MoLA（对照「routing」词）

- **Baseline：** 标准 fine-tune、LoRA-only 等  
- **数据：** Chart2Code-160k  
- **注意：** 这是 **模型内 MoE 专家路由**，不是 batch shared budget。写 BudgetFlow 时必须划清。

## 审稿人偏好（推断）

- Early-stage **可以**，但不能空概念  
- 要有：固定 SE 任务、可观察 outcome、能打脸的对照、威胁有效性  
- 喜 SE 叙事（修复/测试/仓库任务），厌「通用 LLM 更聪明」  

## BudgetFlow ERA 建议主张

> 在固定共享硬预算下，对一批经 verifier 结算的编码任务做 Task Value 感知分配，可在部分工况改善 cost–value frontier；strong-only / learned-router 仍是重要边界。

## 判决

**八月最近的 CCF 正式口（C）。适合 5 页实证 pilot，不适合吹成通用治理终局。**
