# SANER 2027 × BudgetFlow（CCF B）

时间：**2026-07-22**。这是 **目光目标**，不是今晚截稿。

## 从零能不能投？

**现在不能交终稿；九月窗口。** 适合 AAAI/ERA 之后的 CCF B 备选。

- CCF：第七版 **软件工程 B 类**（SANER）  
- 常见日程（以官网为准）：abs/full 约 **2026-09-21 / 09-25**，通知约 **12-01**  
- 参考：https://www.myhuiban.com/conference/1922（投前再核官网）

## 相关吗？

**中。** SANER 吃软件分析、演化、再工程、缺陷修复、仓库级实证。  
BudgetFlow 可包装为：**仓库级 issue 批在共享预算下如何分配修复算力**。

不如 AAAI 贴「预算/多代理」，但比硬蹭网络/数据库顶会干净。

## 同类论文怎么找 PDF

- DBLP：https://dblp.org/db/conf/wcre/  
- IEEE Xplore 搜 `SANER LLM agent repair`  
- 常见近邻主题：automated program repair、repository mining、LLM for maintenance  

（SANER 也是分篇 IEEE，无单一「全会打包免费 PDF」。）

## 预期 baseline / 数据（按 SE 修复线）

| 维 | 常见做法 |
|----|----------|
| **Baseline** | 单模型 agent、无预算优先队列、经典 APR 工具、强模型全程 |
| **数据** | Defects4J、SWE-bench（Lite/Verified）、项目演化历史 |
| **指标** | 修复率、定位准确率、成本/时间、误报 |

你们应保留：**同一硬帽下的 cheap/strong/router/budget-only**，并强调 **TRV 预注册**。

## 判决

**七月不交；CCF B SE 主候选之一。** 先打 AAAI 或 ERA，再视结果转 SANER。
