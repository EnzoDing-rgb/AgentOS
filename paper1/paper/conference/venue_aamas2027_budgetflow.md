# AAMAS 2027 × BudgetFlow（CCF B）

时间：**2026-07-22**。这是 **目光目标**，不是今晚截稿。

## 从零能不能投？

**现在不能交终稿；官网写 Oct 2026（TBC）。**

- CCF：第七版 **人工智能 B 类**（AAMAS）  
- 官网：https://warwick.ac.uk/fac/sci/dcs/aamas2027/  
- Calls：https://warwick.ac.uk/fac/sci/dcs/aamas2027/calls/  
- 会议：2027-05-03–07，Hanoi  

## 相关吗？

**中高。** AAMAS 是多代理旗舰。资源分配、协作、LLM agents 都说得通。  
比 SANER 更贴「agent / allocation」，比 AAAI 档次低一档但同属 AI 多代理社区。

## 同类论文 PDF 怎么找

- 往年 AAMAS proceedings（ACM / IFAAMAS）  
- 近邻可读：**BAMAS（AAAI-26）** 仍是最强预算多代理对照  
  PDF：https://ojs.aaai.org/index.php/AAAI/article/download/40226/44187  
- MasRouter（ACL-25，MAS 路由）：https://aclanthology.org/2025.acl-long.757.pdf  

## 预期 baseline / 数据

| 维 | 常见做法 |
|----|----------|
| **Baseline** | 固定拓扑 MAS、单一 LLM 全员、启发式选模型、无预算约束协作 |
| **数据** | 协作/规划基准、代码/数学任务、仿真环境 |
| **指标** | 任务成功、通信成本、金钱/token 成本、可扩展性 |

BudgetFlow 主张应强调：**跨任务共享硬预算 + 预注册价值 + verifier**，避免写成又一个 MAS 框架。

## 判决

**七月不交；秋冬 CCF B（多代理）主候选。** 与 SANER 二选一做 archival，勿并行同文。
