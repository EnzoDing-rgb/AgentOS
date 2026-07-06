# Past Ideas

Scratchpad for earlier BudgetFlow / paper directions.

Final Title
Use the paper title:
Spend Tokens Where They Matter: Workflow-Aware Budgeting for LLM Agents
Use BudgetFlow as the system name throughout the paper. Replace AgentOS rather than merely weakening it. In the body, describe BudgetFlow as a training-free workflow-aware budgeting runtime, not an agent operating system.
Latest Corrections
This plan supersedes the earlier wording in four ways:
- Remove dummy baselines such as always_expensive and per_request_greedy from the main paper. Keep only strong baselines and diagnostic ablations.
- Explain BoPO from first principles wherever it appears; do not assume the reader understands lambda, soft budgets, hard caps, BoSFT, or BoPO.
- Treat N-ary routing as an engineering-realism and extension experiment, not a standalone core novelty claim, because BoPO's formulation can in principle expand its action space.
- Make the strongest systems contribution the multi-workflow runtime: shared budget pool, hard reservation, RPM/concurrency limits.
Latest Corrections (Round 2)
- The paper body should focus on BudgetFlow's own contributions in plain language. Avoid sentences that require the reader to know what BoPO, BCD, soft-budget training, or lambda are. BoPO is mentioned only in related work and future work.
- Delete dummy baselines completely (do not even keep them in the appendix).
- Address the benchmark mismatch with a two-benchmark design: AppWorld for BoPO head-to-head, SWE-bench Verified for the multi-workflow runtime track.
- Keep the contribution to exactly two axes: training-free hard-cap adaptation, and multi-workflow runtime governance. Do not add a third unless an experiment forces it.
Latest Corrections (Final)
- Do not mix AppWorld and SWE-bench in the main paper. The main experiment stays on SWE-bench Verified.
- BoPO is not a main baseline. It appears in Related Work as evidence that step-level routing for long-horizon agents is a legitimate research problem, and in Future Work as a possible learned selector that could replace BudgetFlow's heuristic ModelSelector.
- The main baseline set is exactly:
  - workflow_level_router: choose one model or routing profile at the start of the workflow.
  - budget_only_step_router: make per-step decisions using budget progress and estimated/reserved cost, but remove step importance w_i and observation type.
- BudgetFlow_full: per-step routing with budget pressure, step importance, observation-aware signals, ledger, admission control, and zombie recovery.
- Delete BoPO head-to-head, AppWorld tracks, BudgetFlow+BoPO primary result, First-Large, sticky, per-call router, and all dummy baselines from the main experimental plan.
Benchmark Plan: Single Main Benchmark
Use SWE-bench Verified as the main benchmark. Do not mix AppWorld and SWE-bench in the same main experimental story.
Rationale:
- SWE-bench Verified is the strongest benchmark for coding-agent workflows and is the right venue fit for a software-engineering systems paper.
- AppWorld/ALFWorld/SciWorld are useful for understanding BoPO, but mixing them with SWE-bench would create incomparable model pools, scaffolds, metrics, and task semantics.
- Re-implementing or retraining BoPO on SWE-bench would turn this paper into a BoPO reproduction effort and weaken the training-free runtime message.
BoPO is therefore used as related work, not as a main experimental baseline.
Core Judgment
The paper's real claim is:
At a fixed budget on SWE-bench Verified, BudgetFlow tests whether step-level workflow-aware routing improves solved tasks over workflow-level routing and budget-only step routing, while enforcing shared budget, provider RPM, concurrency limits, and zombie recovery across many concurrent workflows.
KV/cache locality cannot be cleanly quantified across models with different tokenizers and architectures. It belongs in threats to validity, not in the main experiment.
What BoPO Itself Admits
BoPO's method and limitations section motivates two important comparison axes, but the paper should not be framed as only attacking BoPO:
- Training overhead: BoSFT data synthesis + boundary-anchored RL is expensive, even if amortized.
- Static risk profile: policy is trained with a fixed soft-budget tradeoff parameter lambda; even with budget in the system prompt and Budget-Constrained Decoding at inference, the learned behavior does not dynamically adapt across different hard caps K.
- Model scope: published evaluation is binary cheap/large; N-ary is described as straightforward but not demonstrated. This is not a core novelty claim by itself because BoPO's formulation can expand the action space. Treat it as an engineering-realism and extension experiment, not the main contribution.
BudgetFlow naturally answers the two strong points: it is training-free, and it uses runtime closed-loop budget pressure rather than a fixed trained risk profile. Its strongest unique systems claim is multi-workflow shared-budget execution under RPM/concurrency limits. The experimental design must make these advantages visible and falsifiable without making BoPO dominate the entire paper narrative.
Paper Body Should Focus On BudgetFlow, Not BoPO
In the paper body, focus on BudgetFlow's own contributions in plain first-principles language. Do not require readers to know what BoPO, BCD, soft-budget training, or lambda are. The first time BudgetFlow is introduced, write it like this:
- The system handles one LLM call at a time across many concurrent workflows.
- For each call, it asks: given the remaining global budget, the burn rate, and the current backend pressure (RPM and concurrency), is it worth using a more expensive model on this step? Or should we use a cheaper one, queue, switch backend, or refuse?
- The decision uses a runtime threshold called budget_pressure that rises when budget is tight and falls when budget is loose, so the same heuristic adapts to different hard caps without retraining.
- A workflow ledger records reserved budget and actual spend per workflow; if a workflow stalls, its reserved budget and concurrency slot are released.
BoPO appears only in related work and future work. When mentioning BoPO, give one sentence of context (a routing policy trained with reinforcement learning to trade success against cost) and move on. Do not explain BoSFT, BCD, or lambda in the paper body; these belong in a brief related-work paragraph at most.
Reframe The Headline
Update [/Lishun/_archive/.local_env_bak/research/AgentOS/paper1/paper1_concept_opus.md](/Lishun/_archive/.local_env_bak/research/AgentOS/paper1/paper1_concept_opus.md) §0 and abstract to claim:
- Training-free hard-cap adaptation: at different per-task budget caps, BudgetFlow's runtime threshold adapts at runtime instead of requiring a retrained policy.
- Multi-workflow runtime governance: when many agents share one global budget, provider RPM, and concurrency slots, BudgetFlow decides per call whether to admit, queue, downgrade, switch backend, or cancel a stalled workflow.
Drop language that implies "frequent model switching is automatically cheaper."
Experimental Design: Three Main Systems
Run all main experiments on SWE-bench Verified with the same agent scaffold and backend pool.
System A. Workflow-Level Router
Choose a model or routing profile once at the beginning of a workflow, using only the initial issue/task context. The choice then applies to the whole workflow.
This is the key baseline because many practical routers operate at request/task level. It tests whether step-level routing is actually necessary.
System B. Budget-Only Step Router
Make routing decisions at each step, but remove step importance and observation type from the formula.
It uses only budget pacing signals:
- spent_budget / total_budget
- global progress such as completed_tasks / total_tasks
- estimated or reserved cost of the current call
It does not use whether the current step is planning, search, debugging, traceback analysis, or validation. This isolates whether BudgetFlow gains come from workflow-aware step value rather than simple budget pacing.
System C. BudgetFlow Full
The full system: per-step routing with budget pressure, step importance, observation-aware signals, workflow ledger, hard-budget reservation, backend admission control, and zombie recovery.
Main metrics:
- resolved count / resolved rate under fixed total budget
- cost per resolved task
- budget violation rate
- 429 rate under provider RPM limits
- p50/p99 queue latency
- recovered budget from cancelled/zombie workflows
- backend admission decisions: admit, queue, downgrade, alternate backend, reject
Methodology
To make these tracks comparable and reviewable:
- Use SWE-bench Verified as the primary benchmark. If BoPO publishes on a tool-using coding benchmark not in SWE-bench, replicate BoPO on SWE-bench Verified using their open code if available; otherwise re-implement faithfully and document any deviation.
- Use one agent scaffold (SWE-agent or mini-SWE-agent) consistently across systems; do not let scaffold differences leak into the result.
- Cost accounting uses provider billing as actual_cost. Report cached-token discount when the provider returns it. Do not invent synthetic switching penalty in the main numbers.
- Pre-register the three-outcome decision tree from Track 1 in §7 of the paper.
- For BoPO comparisons, document the exact training compute, dataset construction, and any assumed lambda. If we cannot rerun BoPO training, evaluate the released checkpoint and clearly mark this.
Simplify Baselines
The minimum baseline set for the headline:
- Workflow-Level Router
- Budget-Only Step Router
- BudgetFlow Full
Completely delete: BoPO head-to-head, AppWorld tracks, BudgetFlow+BoPO primary experiments, always_expensive, per_request_greedy, sticky-per-workflow, per-call router, LiteLLM auto router, multiple sticky variants, and the elaborate cache-aware variants from earlier plans. They do not appear in the main paper or the appendix. Do not let baselines dilute the core story: step-level workflow-aware routing under fixed SWE-bench budget.
Demote KV/Cache Locality To Limitation
Cross-model KV/cache cost is methodologically uncomparable: different tokenizers, different output distributions, different cache architectures, different provider billing.
- Remove cache-aware effective_cost as a main experimental axis.
- Keep cost accounting as expected_cost / reserved_cost / actual_cost. actual_cost reflects provider billing (with cached-token discount when available). No synthetic switching penalty in main numbers.
- Add a threats-to-validity subsection explaining that same-model continuation may benefit from prefix/KV/prompt caching, that BudgetFlow may underestimate this benefit when routing across models, and that this cannot be cleanly isolated cross-model.
- Optional bounded side experiment: single local backend (vLLM/SGLang) measuring prefix-cache hit and latency for sticky vs switching. Single page in appendix.
BoPO Placement
Put BoPO in Related Work and Future Work, not in the main experiment.
Related Work wording:
BoPO shows that step-level model routing in long-horizon agents is a meaningful problem, but it studies a learned RL router on ALFWorld/SciWorld/AppWorld. This paper instead studies a training-free runtime for SWE-bench-style coding workflows and multi-workflow shared-budget execution.
Future Work wording:
A natural extension is to replace BudgetFlow's heuristic ModelSelector with a learned selector, following ideas from BoPO-style boundary-guided training.
Tighten The Scope Claim
In §0 and §11:
- This paper validates the claim only on SWE-bench-style coding workflows with machine-checkable progress signals.
- It does not claim universal generalization to all agent tasks.
- Its broader value is the runtime contract and an experimental methodology for fixed-budget, multi-workflow agent execution. BoPO is the strongest learned-router comparison, not the whole story.
Concrete Edits To paper1_concept_opus.md
1. §0 and abstract: change framing from cost-aware routing to fixed-budget utility maximization on SWE-bench.
2. §2.3 and §7: replace the long baseline table with the three-system design: Workflow-Level Router, Budget-Only Step Router, BudgetFlow Full.
3. §3.4: remove effective_cost and synthetic switching penalty from the main cost model. Keep only expected/reserved/actual.
4. §7 RQs: replace with RQs about step-level vs workflow-level routing, budget-only vs workflow-aware routing, and multi-workflow runtime governance.
5. §8.3 and §11: move BoPO to Related Work/Future Work with restrained wording; remove BoPO from main experimental claims.
6. New short threats-to-validity subsection covering KV/prompt caching, tokenizer differences, and cross-model output-length variance.
7. §12 future work: keep cache-aware scheduling and provider-integrated prefix caching as future work.



1. 论文

- 本文研究的三个问题：
  1. RQ1：很多智能体任务共用一个总预算、同一套后端（RPM、并发等）时，钱主要浪费在哪、瓶颈是预算还是限流/排队？
  2. RQ2：在同样预算下，调度时带上「当前是工作流哪一步」（而不只靠预算或粗粒度路由），能不能多解出几道 SWE-bench？
  3. RQ3：频繁换模型会伤前缀缓存/预填延迟，在这种代价下，工作流感知的调度是否仍然净收益？
- 本文的两个核心贡献点：
  1. 按工作流状态决定要不要升档：不是孤立地问「这一步用哪个模型」，而是结合预算松紧（budget pressure）和这一步有多关键（权重），算「多花一块钱能多买多少预期进展」，再决定升不升档。
  2. 硬预算 + 可审计的治理：用预留–结算把总花费钉死在预算内，再配合准入/排队/调度和无进展/僵尸回收，避免卡死占坑、把资源留给还能推进的任务。

- 同领域论文汇总表格：
[图片]

[图片]

[图片]

- 结论：目前市面上没有类似的工作，值得尽快推进
- 论文薄弱点与增强：本论文涉及频繁切换模型，导致KV cache缓存命中率下降、有切换成本（penalty）
  - 因此，增加一个实验：充分利用实验室本地qwen模型，打开KV cache相关的参数，直观统计缓存命中率的下降带来的损失，通过数据回答研究问题：我的系统切换模型带来的收益是否能够抹平缓存下降的损失
  - 该问题的意义：
    - 市面上其他per request切换的论文，没有考虑/量化这一点，单单是量化这一点本身，就是实打实的贡献
    - 如果说我的系统收益能够抹平缓存下降带来的损失，证明该论文有工业界更大规模实验的价值，顶会很看重工业界的大规模实质价值


2. 总览
- 论文数据收集：
  - 确认SWE-bench数据集不含步骤分类，改用Agentless论文提出的通用分类
  - 从SWE-bench/expriments下载实际agent的运行轨迹，用来得到离线得到【模型，能力】的元组
  - PPT汇报：BudgetFlow_ 面向Agent工作流的动态预算路由机制
- 软件所实习照常，全栈开发，本周与罗老师线下见面
- cs149并行计算，了解硬件和加速训练的基本原理，快速完成实验
- 国家安全学博生课程照常进行，完成一次课堂汇报


Appendix

顺序
变量 / 量
启发式硬编码（先验/规则表/未标定常数）
可从实际轨迹或运行日志中给出依据
1
三阶段名（Localization / Repair / Validation）
借用 Agentless 标签的固定词表，不是从单次轨迹“学”出来的
无；属于论文约定的分类骨架
2
classify(...) → stage
固定函数（附录规则 + 少量示例）；代理模式下的文本/小分类器也是工程规则
有 .traj 时：action 串、工具名、观测文本可作可审计的输入；Tier1 用 regex/lookup 映射（文档 §8.5）
3
w_i（默认按阶段）
冷启动表：Localization 1.0、Repair 3.0、Validation 2.5；L3 任务类型表（planning→3 等）；L0 的 w_i≡1
L4/L2：平台显式传、框架回调元数据来自真实运行；也可在标定集上做敏感性网格（非“单次 traj 显示”，而是实验设计）
4
q_i（逐步可核查进步）
定义哪件事算进步（金补丁路径、git apply、FAIL_TO_PASS 计数规则）是事先写死的评价协议
数值 0/1 或计数：由该轮实际动作/补丁/测试结果对照金标签或沙箱执行得到；回放公开 run 的 trajs/*.traj + results/ 可复算（§1、§3.4、§5.3）
5
Progress[stage, tier] / expected_progress_gain
zero_calibration：手写“每升一档 +小常数、Repair 略大”的默认表（§3.4、§8.5）
Tier2：对 (stage, tier) 上历史 q_i 的均值及相邻档差分；来源为 SWE-bench/experiments 的 .traj 回放或不相交标定 split上的真实/回放日志（§3.4）
6
c_i、actual_cost
单价 p_in/p_out 来自价目表（外部假设）
token 用量来自提供商回单/日志；与真实调用轨迹一一对应（§4.3）
7
expected_cost、extra_cost（用于排序）
输出 token 的预测用任务类型/模型的历史均值或滑动平均——初值常是启发式
随运行滚动更新后主要由历史真实调用统计支撑（§4.1）
8
reserved_cost
选用 max_output_tokens 作为保守上界是策略/配置
输入 token 数来自已构造好的请求（轨迹上可见）； settle 后与 actual_cost 对齐（§4.2）
9
budget_pressure
在线调节（花得快调高、花得慢调低）是控制律式启发式
初值可由标定 split 上升级分数分布的中位数/分位数估计（§3.1）；属批量统计而非单条 traj 展示
10
Ledger 派生量（如 reserved_budget/total_budget、队列状态）
聚合方式由系统设计固定

数值完全由并发运行与结算事件产生，可在日志中复现（§5.3、§7）
11

无进步 / Zombie 信号（重复动作、超时、成本涨而步进不涨等）
阈值（重复几次、多久无 token 等）是硬编码熔断规则
触发计数来自实际工具事件、时间戳、账本（§5.3、§7.1）
12
switch_penalty（Cache-Sticky）
后端不暴露缓存时扫一组合成惩罚是启发式
若 vLLM/SGLang 等暴露 prefill/缓存 token，可由实测估计（§6.4）
13
resolved（任务级）
.harness 规则固定
由最终补丁 + 官方测试在轨迹外执行得到；不用于在线路由（§5.2–5.3）

[图片]




封面页
BudgetFlow: 面向Agent工作流的动态预算路由机制
- 汇报人：XXX
- 日期：2026年5月
- 核心目标：固定预算下最大化Agent任务成功率

---

1. 论文主线
核心问题
- 优化单位：单次LLM请求 → 完整Agent工作流
- 多工作流共享预算/配额时，显式跟踪状态能否提升成功率？
- 收益来源：预算配速/步骤重要性/进展先验/多工作流调度？
研究目标
- 把Agent的LLM花费变成可审计、可消融、可复现的工程问题

---

2. 本文核心贡献（5点）
✅ 连续质量视角：LLM质量是[0,1]连续值，非0/1二元  
✅ 硬预算+动态配速：实时调整每步花费，绝对不超支  
✅ 显式任务价值：调用方声明步骤重要性，完全可解释  
✅ 僵尸止损：自动砍掉"花钱不涨质量"的无效调用  
✅ 零训练成本：纯启发式，开箱即用，比RL轻量百倍


---

3. 项目架构（4层·策略与机制分离）
Agent Workflows (多步+并发)
        ↓
══════════════════════════════
│ 【约束层】Governor          │ 预算结算/后端限流/并发准入
│ 【优化层】ModelSelector     │ 唯一路由策略：进展增益+预算压力
│ 【止损层】ZombieDetector    │ 僵尸截断/高优先级任务抢占
│ 【调度层】Multi-Workflow    │ 跨工作流资源协调
══════════════════════════════
        ↓
LLM后端池 → 指标输出
- 路由算法可插拔：支持RL/CARROT/OmniRouter等任意策略

---

4. 相关工作分类
领域
代表工作
OS资源管理
AgentRM, AgentCgroup, AIOS, pMVX
单查询路由
RouteLLM, CARROT, OmniRouter
多步RL路由
BoPO (2026), xRouter (2025)
GPU预算控制
Athena-Serve
硬件编排
Murakkab


---

5. 完整对比总表（所有相关工作）
论文
类型
预算约束
多步
方法
与本文关系
本文
优化启发式
Hard budget
有
边际性价比+budget_factor配速
-
Budget-Aware Agentic Routing (Zhang et al. 2026)
RL (BoPO)
Hard+Soft
有(sequential)
Boundary-Guided Training+BoPO
最直接竞争者：RL vs 启发式
OmniRouter (Mei et al. 2026)
约束优化
有(Lagrangian dual)
无(独立query)
Hybrid predictor+Lagrangian optimizer
全局优化但per-query
xRouter (2025)
RL
Cost-aware reward
有(episode)
Tool-calling RL router
RL方法论对手
CARROT (2025)
统计
Per-query cost预测
无
Minimax optimal plug-in router
Per-query baseline
RouteLLM (2024)
学习型二元
无
无
偏好数据训练+强弱二分
Per-query baseline
pMVX (2026)
Agentic OS/内核
无
无
多版本策略执行+内核自调优
平行工作：偏内核优化
AgentRM (2026)
OS-inspired
并发槽/RPM
无
MLFQ+僵尸回收+上下文管理
平行工作：侧重稳定性
AgentCgroup (2026)
OS内核级
CPU/内存
无
eBPF+cgroup
平行工作：OS级资源
AIOS (2024)
OS架构
无
无
内核服务抽象
概念相似但更宽泛


---

6. 关键差异1：本文 vs BoPO（最重要对比）
维度
Budget-Aware Agentic Routing (BoPO)
本文
方法
RL，需训练数据+GPU
优化启发式，零训练，即时部署
可解释性
RL策略黑盒，难以解释
边际性价比排序+budget_factor，100%可解释
预算处理
训练时soft-budget+推理时BCD
运行时hard budget硬约束
任务价值
隐式（RL自动学习）
显式wᵢ（调用方声明）
止损
无专门机制
ZombieDetector截断无效调用
互补性
-
本文启发式可作为RL warm-start baseline


---

7. 关键差异2：本文 vs 单查询路由
维度
Per-query Routers (RouteLLM/CARROT/OmniRouter)
本文
决策
每条query独立最优
跨N步联合预算约束
状态
无状态
有状态（跟踪预算/消耗速率）
预算
不管或仅预测单query成本
Hard budget硬约束
任务价值
不区分步骤重要性
显式wᵢ


---

8. 关键差异3：本文 vs OS类工作
维度
OS-Inspired工作 (AgentRM/AgentCgroup/AIOS/pMVX)
本文
核心问题
系统稳定性/资源隔离
质量-成本优化
优化目标
延迟/吞吐量/隔离性
QWCR, Q/$, Pareto最优
资源类型
CPU/内存/并发槽/RPM
LLM调用质量与成本


---

9. 论文边界：互补而非竞争
Agent计算栈分层优化
┌─────────────────────────────────────────┐
│ Murakkab (顶层) 全栈SLO编排             │
│ 目标：最小化云厂商硬件成本               │
├─────────────────────────────────────────┤
│ BudgetFlow (本文) 全局预算控制          │
│ 目标：固定预算下最大化用户任务成功率     │
├─────────────────────────────────────────┤
│ Aragog (中层) 动态模型路由              │
│ 目标：最大化GPU利用率和系统吞吐量       │
├─────────────────────────────────────────┤
│ Parrot (底层) 多轮请求流水线            │
│ 目标：最小化单请求延迟                  │
└─────────────────────────────────────────┘
- 四层完全独立、可叠加，互不冲突
- 本文解决用户最关心的"钱怎么花最值"问题

---

10. 叙事：参照vLLM的演进路径
vLLM的两阶段发展
1. 单租户阶段：解决单服务器请求批处理与调度
2. 多租户阶段：扩展到多用户共享，处理优先级与配额
BudgetFlow的路线图
- 本文（阶段1）：单预算所有者场景，一个团队用固定预算跑多个Agent
- 未来（阶段2）：多租户场景，多个团队共享Agent执行底层
- 优势：架构天生支持多租户扩展，无需修改核心机制

---

11. 总结与展望
本文总结
- 首次提出工作流级预算-质量联合优化框架
- 纯启发式算法：零训练、可解释、即时部署
- 固定预算下显著提升Agent任务成功率
- 与现有所有Agent优化工作完全互补
未来工作
- 多租户预算仲裁与隔离
- 异构工作流混合调度
- 自适应预算分配算法

---

Appendix A：集成方式
第三方Agent框架        自研平台
(LangChain等)            ↓
    ↓ Proxy模式      Explicit模式
BudgetFlow Proxy/Adapter/SDK
            ↓
      BudgetFlow Runtime
            ↓
        LLM后端池
- 三种集成模式：零侵入代理/轻量回调/原生SDK

---

需要我帮你补充实验结果页的标准模板（包含成功率-预算曲线、消融实验、不同工作流类型的性能对比），或者把这个PPT转换成可直接导入Google Slides/PPTX的格式吗？



w我是cs phd 我在找研究课题 请你批判性思考一下 给我一些idea 准确的说是一个idea 我要设计一个agent资源管理器 不做进入linux内核 但是是一个用户态的操作系统的感觉

我给你以下信息 你可以裁剪 可以批判 可以添加 总之给我一个最neat的idea 一定不要大杂烩大拼盘 要有意义

它将 LLM 资源抽象为三类可调度的系统一级资源：
1. 上下文窗口大小（context window size）
2. 令牌预算（token budget，单位时间内可消耗的总 token 数）
3. API 速率限制（API rate limit，单位时间内可发起的调用次数）
这些资源不是硬编码的固定值，而是可配置的资源配额，支持用户根据自己的模型（本地 / 云端）、API 密钥、硬件能力动态设置。（用户配置可能还是太麻烦了 有没有自动探测或者什么 总之能跟Linux差不多开箱用的）


类比传统 OS 进程调度，具体算法未实现
✅ 论文明确写了：
- 调度器的核心逻辑和传统 OS 的 CPU 调度器完全一致：
  - 所有 LLM 调用请求都必须向调度器申请资源，不能直接调用模型
  - 调度器维护一个全局的资源池和任务队列
  - 支持优先级调度：高优先级任务（如用户实时交互）可以抢占低优先级任务（如后台邮件整理）的资源
  - 支持资源回收：任务完成或超时后，自动回收未使用的资源
- 它解决的核心问题是：避免多个并发代理任务同时耗尽 LLM 资源导致的 OOM、API 超限和系统崩溃。


✅ 论文明确写了：
- Agent Kernel 提供了统一的 LLM 调用抽象接口，所有技能模块和代理线程只能通过这个接口调用大语言模型，不能直接访问模型 API。
- 这个接口对上层屏蔽了底层模型的差异（支持 Claude、GPT、本地模型等），上层只需要提交请求和所需的资源规格，调度器会负责分配资源并转发请求。


好，咱们用大白话把这篇Sovereign-OS的论文给你讲明白，你开车听着就行，不用费脑子记复杂公式，核心逻辑我给你串得清清楚楚，全程口语化，不整晦涩的学术黑话。

首先先搞懂，这篇论文到底解决了什么要命的问题。
现在咱们都知道，AI agent早就不是只会聊天的工具了，LangChain、CrewAI、AutoGen这些框架，能让AI组队当自动打工团队，接软件赏金、写文案、做调研，甚至能自己接活赚钱，成了能自主花钱的经济实体。但这里有个天大的漏洞：这些框架只做了「编排」，也就是让AI把活跑起来，完全没做「治理」。
说白了，就像你开了家公司，只招了干活的员工，没定财务制度、没设权限、没找审计、没定公司章程，结果就是：接50美元的活，AI能花120美元的API成本直接亏麻；5美元的单子预估成本30，它也敢接；甚至刚招进来的新员工，上来就能直接执行服务器shell命令、随便动公司的钱，完全没门槛。现有框架只会忠实地让AI把活跑完，根本不管它亏不亏钱、有没有权限瞎操作、干的活合不合格，更没地方给你查账。
这篇论文的Sovereign-OS，就是专门解决这个问题的。

接下来，Sovereign-OS到底是什么？
它不是又一个agent编排框架，而是一套给AI agent用的、治理优先的操作系统。你可以把它理解成，给你的AI打工团队，直接装了一套完整的现代公司治理体系：有宪法、有CEO、有CFO、有员工权限制度、有审计合规、有不可篡改的财务账本，从根上管住AI的每一笔花钱、每一个操作、每一次交付。
整个系统的核心逻辑特别简单：所有行为都必须围着一份「宪章」转，宪章定死的规矩，底层系统强制执行，AI想突破根本不可能。

然后咱们用开公司的类比，把它的五层核心架构给你讲明白，一层一层顺下来，你一听就懂。

第一层，宪章（Charter）——公司的宪法。
这就是一个YAML文本文件，一句话代码都不用写，里面定死了整个AI团队的所有规矩：它的使命是什么、只能干什么活、每天最多花多少钱、总预算上限是多少、接活最少要赚多少毛利率、干的活要达到什么KPI才算合格。
整个系统是完全被宪章驱动的，想改AI的行为，不用改代码，换个宪章文件就行。比如你把宪章从「内容工作室」改成「科研实验室」，AI立刻就切换行为模式，底层系统完全不用动。

第二层，CEO（战略师）——公司的首席执行官。
你给它一句自然语言的目标，比如「写一套开发信邮件序列」，它就会把这个大目标，拆成一套有前后依赖关系的任务流，比如先做客户调研、再写邮件草稿、最后润色优化。每个任务都会标清楚：需要什么技能、预估要花多少token、优先级是高还是低，相当于给团队出了完整的执行方案。

第三层，CFO（财务官）——整个系统最核心的守门员，也是这篇论文最大的亮点。
任何任务想执行，必须先过CFO这关，它有三道死检查，一条不满足，直接打回，连一个token都不会让AI花：
第一，余额检查：这个任务预估花的钱，会不会让公司账户余额低于最低储备金，不能干着干着没钱了；
第二，日限额检查：今天已经花的钱，加上这个任务的开销，会不会超了宪章里定的单日消费上限；
第三，盈利检查：如果这个活有收入，必须保证能赚到宪章里定的最低利润，比如默认毛利率不能低于35%，亏本买卖绝对不接。
除了管钱，它还有个招标机制：每个任务会给符合技能要求的AI工人发招标书，工人报价格、交付时间、完成信心分，CFO会用公式算性价比，选最优的工人来干；要是报价超了剩余预算，还会直接跟工人砍价，逼着它压缩token预算，绝对不超支。

第四层，工人+权限系统——干活的员工，权限是「赚来的」，不是天生就有的。
这里用了一个叫TrustScore（信任分）的机制，满分100，每个AI工人初始只有50分，分不够，就没权限干高危操作，门槛卡得死死的：
10分才能读本地文件，40分才能写文件，50分才能调用外部API，60分才能执行shell命令，80分才能动真金白银花钱。
最关键的是，加分减分是不对称的：活干成了、审计通过，只加5分；活干砸了、审计没通过，直接扣15分；超预算额外再扣10分。
举个例子，初始50分的工人，想解锁花钱的权限，得连续6次审计全过，才能从50涨到80；但只要搞砸一次，50直接掉到35，连写文件的权限都给你收了。这就从根本上避免了新AI上来就瞎操作的问题，必须靠靠谱的干活，一步步赚权限。

第五层，审计官+不可篡改账本——公司的审计部+财务台账。
AI把活干完，审计官立刻上线，拿着宪章里定的KPI，给输出打分，0.5分以上才算合格。
最关键的是，每一份审计报告，都会生成一个SHA-256的哈希值，也就是「证据哈希」——报告里的任何一个字、一个数字改了，哈希值就对不上，完全防篡改。而且所有审计记录、花钱流水，都存在一个「只能追加、不能修改删除」的账本里，永久留痕，随时能查，谁都改不了。
审计结果还会直接反馈到信任分：过了就加分，没过就扣分，还会把问题记下来，让AI下次别再犯同样的错。

接下来给你说，这套系统实际效果怎么样，论文里的测试结果，全是硬数据，大白话给你说清楚：
第一，财务管控：他们模拟了30种违规场景，比如超预算、接亏本活、超日消费限额，Sovereign-OS100%全拦住了，一个漏网的都没有，绝对不会让AI乱花一分钱；
第二，权限管控：200次任务测试，权限放行和拒绝的准确率达到94%，那6%的误差，全是卡在分数刚好等于门槛线、审计结果还没更新的瞬间，下一个审计周期就自动修正了，完全不影响实际使用；
第三，审计完整性：1200多份审计报告，哈希校验全过，没有一个被篡改、哈希对不上的，账本绝对靠谱，没有任何数据 integrity 问题。

然后咱们说，它和现在市面上的工具，到底有啥本质区别？
现在主流的LangChain、CrewAI、AutoGen这些，都只能做多agent编排，也就是让AI组队干活，但预算管控、权限管理、输出校验、审计留痕，要么完全没有，要么只能靠第三方插件凑活，不是原生就有的。而Sovereign-OS是把这些治理能力，直接做进了操作系统的底层，不是打补丁，是从根上就管住了。
还有像Guardrails AI这种工具，只能管AI输出的内容合不合规，管不了AI花钱、管不了权限、管不了审计；区块链上的Fetch.ai、SingularityNET，是做AI之间的交易市场，管不了单个AI团队内部的财务纪律。
Sovereign-OS的定位特别清晰：专门给自主AI agent，做一套原生的、全流程的治理和财务管控系统，让AI从「只会干活的工具」，变成「有规矩、能管钱、负责任、可审计的经济主体」。
而且它已经做了落地能力，直接对接了Stripe支付，活干完、审计过了，直接就能给客户发起收款，从接活、规划、花钱、干活、审计、收钱，全流程闭环，直接就能当一个自动赚钱的AI公司用。

最后给你收个尾，说下这篇论文的核心贡献和未来方向。
这篇论文最大的创新，就是别人都在卷「怎么让AI把活干得更快、更好」，它跳出来解决了「怎么让AI把活干得合规、省钱、靠谱、可追溯」的核心问题，第一次给自主AI agent做了一套完整的、治理优先的操作系统。而且它是完全宪章驱动的，灵活性极强，换个YAML文件，就能切换AI的全部行为模式，一行代码都不用改。
未来他们还想做的，包括把账本放到区块链上做第三方公证、多个AI团队之间跨宪章合作、让信任分的加减更智能，而不是固定数值，还有在真实生产环境里长期跑，验证实际的省钱效果和用户信任度。

说白了，这篇论文干的事，就是给现在野蛮生长的AI agent，装了一套严丝合缝的现代公司治理体系，从宪法、CEO、CFO、员工权限、审计、财务账本，全给你配齐了，从根上解决了AI乱花钱、瞎操作、干了活没保障的行业痛点。

【我感觉这里的宪章 cfo 和budegt token预算能联系起来】


话核心结论先给你
这篇论文解决的是多智能体 LLM 系统服务架构太死板的致命问题 —— 现在你熟悉的 MCP、Google A2A 这类 Agent 通信协议，都是开发者写代码时就定死了通信模式，没法根据系统实时运行状态动态调整，导致性能严重拉胯。他们借鉴软件定义网络 SDN 的思路，做了一套可编程、全局自适应的智能体服务框架，实测吞吐量最高提升 3.6 倍，再加底层 Agent 控制能力，还能再提升 2.3 倍。

---
第一部分：他们到底要解决什么核心痛点
现在 LLM 早就不是单轮对话了，主流都是多智能体流水线。比如最典型的代码开发场景：一个开发 Agent 写函数，一个测试 Agent 给反馈，两个 Agent 要频繁通信，还要调用各种工具、数据库、其他模型。为了让 Agent 之间能通上话，业界出了 MCP、A2A、ACP 这类标准协议，它们解决了Agent 能不能连上的问题，但完全没解决怎么连才最高效的问题。
核心矛盾非常直白：Agent 之间的通信模式，根本没有永远最优的固定解。
- 系统负载高、请求多的时候，把所有函数一次性打包发的批处理模式，能扛住吞吐量，减少排队；
- 系统负载低、要交互式响应的时候，token 级流式传输，延迟最低，体验最丝滑。
但现在的所有协议，全是开发者写代码时就把通信模式写死了，定了流式就永远流式，定了批处理就永远批处理，不管系统运行时是闲是忙都没法改，最终结果就是性能暴跌、资源浪费、用户体验差。

---
第二部分：现有架构的三个致命缺陷
论文把现有方案的问题总结得非常透彻，三个核心硬伤：
1. 提前绑定，写死就改不了。比如用 A2A 写代码，代码里定了流式通信，那不管系统负载多高，都只能用流式，没法动态切批处理。论文实测，选错模式性能直接掉 3.6 倍。
2. 没有全局视野。每个 Agent 都是 “瞎子”，不知道其他 Agent 的状态。比如下游测试 Agent 的队列已经堵炸了，上游开发 Agent 还在疯狂发数据，根本没法绕路、没法减速，全是各自为战。
3. 没有端到端全局控制。你没法给整个 Agent 流水线定高层规则，比如 “交互式请求优先走流式，后台任务走批处理”，也没法做请求优先级调度、KV 缓存预加载这类优化，全靠开发者手动调每个 Agent 的参数，系统一复杂根本管不过来。

---
第三部分：他们的解决方案 ——SDN 启发的三层软件定义架构
他们没有搞新的通信协议，而是给现有的 MCP、A2A 这些协议，加了一个全局可编程的控制大脑，把 Agent 服务的控制面和数据面分离，复刻了当年 SDN 对网络架构的革命。整个架构分三层，逻辑非常清晰：
第一层：可配置的数据面
这是 Agent 之间传话的通道，他们做了一个薄薄的兼容层，夹在现有的 MCP/A2A 协议和底层网络之间。最大的好处是：你不用改原来的 Agent 代码，不用换协议，这个兼容层就能让控制器在运行时，动态调整通信模式—— 负载高了直接从流式切全量批处理，负载降下来再切回流式，全程不停服务、不改代码。支持从 token 级流式、单函数流水线到全量批处理的所有粒度，全都是动态可调的。
第二层：指标面
说白了就是给控制器装眼睛和耳朵，让它能看见全系统的状态。他们做了两级采集架构：
- 每个机器上有本地采集器，收两类核心数据：一类是系统级的，比如 GPU/CPU 利用率、队列长度、内存压力；另一类是应用级的，比如请求延迟、首包时间 TTFT、单 token 生成时间 TPT 这些 LLM 核心指标。
- 中央控制器按需拉取数据，不用一直传输，开销极低。同时还能给指标加语义，告诉控制器 “GPU 利用率高是好事，队列太长是坏事”，让它知道该怎么决策。
第三层：控制面 —— 整个系统的大脑
这是最核心的部分，是一个逻辑集中的中央控制器，干三件核心事：
1. 拿到全系统的所有指标，拥有全局视野，知道每个 Agent 忙不忙、哪里堵了、哪里有空闲资源，彻底解决了之前 “瞎子” 的问题。
2. 能听懂高层业务目标，比如 “90% 的交互式请求延迟要低于 200ms”“最大化吞吐量”，不用你写一堆底层规则，它自己会把目标翻译成实时控制指令。
3. 既能给数据面发规则、动态调整通信模式，还能直接控制 Agent 本身的行为 —— 比如动态改 vLLM 的最大批处理大小、Agent 过载时提前迁移 KV 缓存到空闲实例、给请求绕路、调整优先级，甚至暂停非核心后台任务，全都是运行时直接操作，不用改代码。
为了兼容各种各样的 Agent 和工具，他们做了极简的统一 API，就两个函数：set()和reset()。不管你是什么 Agent、什么底层框架，只要写个薄薄的适配层，控制器就能用这两个函数控制所有参数，扩展性极强。

---
第四部分：实测效果怎么样
他们做了完整的原型机，基于 Google A2A 协议，搭了开发 Agent + 测试 Agent 的 MetaGPT 代码开发工作流，实测结果非常能打：
1. 只靠动态调整通信模式，吞吐量就比固定模式的基线，最高提升 3.6 倍，不管负载高低，都能自动切到最优模式。
2. 再加底层 Agent 控制能力，比如 KV 缓存迁移、负载均衡、预加载提示，吞吐量比基线再提升 2.3 倍，其中带预加载提示的方案，比不带的性能好 1.8 倍。

---
第五部分：核心意义与未来方向
首先，它最大的落地价值是：不推翻现有生态，不是要做新的协议替代 MCP、A2A，而是给这些现有协议加了一个动态控制的大脑，完全兼容现有代码，拿来就能用。其次，它把 Agent 服务从 “开发者写死的静态架构”，变成了 “可编程、自适应、全局优化的动态系统”，相当于给多智能体系统做了一个核心 “操作系统内核”，解决了现在多智能体系统越做越复杂、性能越来越难管控的核心痛点，复刻了当年 SDN 对网络行业的变革。
未来的方向也非常明确：可以做声明式的策略语言，运维只用说人话定目标，不用写代码；可以做在线策略自学习，自动根据系统状态优化规则；还能支持混合云架构，同时管理本地 Agent 和云端第三方工具，给未来大规模多智能体系统搭了核心底层架构。


w我是cs phd 我在找研究课题 请你批判性思考一下 给我一些idea 准确的说是一个idea 我要设计一个agent资源管理器 不做进入linux内核 但是是一个用户态的操作系统的感觉

我给你以下信息 你可以裁剪 可以批判 可以添加 总之给我一个最neat的idea 一定不要大杂烩大拼盘 要有意义

它将 LLM 资源抽象为三类可调度的系统一级资源：
1. 上下文窗口大小（context window size）
2. 令牌预算（token budget，单位时间内可消耗的总 token 数）
3. API 速率限制（API rate limit，单位时间内可发起的调用次数）
这些资源不是硬编码的固定值，而是可配置的资源配额，支持用户根据自己的模型（本地 / 云端）、API 密钥、硬件能力动态设置。（用户配置可能还是太麻烦了 有没有自动探测或者什么 总之能跟Linux差不多开箱用的）


类比传统 OS 进程调度，具体算法未实现
✅ 论文明确写了：
- 调度器的核心逻辑和传统 OS 的 CPU 调度器完全一致：
  - 所有 LLM 调用请求都必须向调度器申请资源，不能直接调用模型
  - 调度器维护一个全局的资源池和任务队列
  - 支持优先级调度：高优先级任务（如用户实时交互）可以抢占低优先级任务（如后台邮件整理）的资源
  - 支持资源回收：任务完成或超时后，自动回收未使用的资源
- 它解决的核心问题是：避免多个并发代理任务同时耗尽 LLM 资源导致的 OOM、API 超限和系统崩溃。


✅ 论文明确写了：
- Agent Kernel 提供了统一的 LLM 调用抽象接口，所有技能模块和代理线程只能通过这个接口调用大语言模型，不能直接访问模型 API。
- 这个接口对上层屏蔽了底层模型的差异（支持 Claude、GPT、本地模型等），上层只需要提交请求和所需的资源规格，调度器会负责分配资源并转发请求。


好，咱们用大白话把这篇Sovereign-OS的论文给你讲明白，你开车听着就行，不用费脑子记复杂公式，核心逻辑我给你串得清清楚楚，全程口语化，不整晦涩的学术黑话。

首先先搞懂，这篇论文到底解决了什么要命的问题。
现在咱们都知道，AI agent早就不是只会聊天的工具了，LangChain、CrewAI、AutoGen这些框架，能让AI组队当自动打工团队，接软件赏金、写文案、做调研，甚至能自己接活赚钱，成了能自主花钱的经济实体。但这里有个天大的漏洞：这些框架只做了「编排」，也就是让AI把活跑起来，完全没做「治理」。
说白了，就像你开了家公司，只招了干活的员工，没定财务制度、没设权限、没找审计、没定公司章程，结果就是：接50美元的活，AI能花120美元的API成本直接亏麻；5美元的单子预估成本30，它也敢接；甚至刚招进来的新员工，上来就能直接执行服务器shell命令、随便动公司的钱，完全没门槛。现有框架只会忠实地让AI把活跑完，根本不管它亏不亏钱、有没有权限瞎操作、干的活合不合格，更没地方给你查账。
这篇论文的Sovereign-OS，就是专门解决这个问题的。

接下来，Sovereign-OS到底是什么？
它不是又一个agent编排框架，而是一套给AI agent用的、治理优先的操作系统。你可以把它理解成，给你的AI打工团队，直接装了一套完整的现代公司治理体系：有宪法、有CEO、有CFO、有员工权限制度、有审计合规、有不可篡改的财务账本，从根上管住AI的每一笔花钱、每一个操作、每一次交付。
整个系统的核心逻辑特别简单：所有行为都必须围着一份「宪章」转，宪章定死的规矩，底层系统强制执行，AI想突破根本不可能。

然后咱们用开公司的类比，把它的五层核心架构给你讲明白，一层一层顺下来，你一听就懂。

第一层，宪章（Charter）——公司的宪法。
这就是一个YAML文本文件，一句话代码都不用写，里面定死了整个AI团队的所有规矩：它的使命是什么、只能干什么活、每天最多花多少钱、总预算上限是多少、接活最少要赚多少毛利率、干的活要达到什么KPI才算合格。
整个系统是完全被宪章驱动的，想改AI的行为，不用改代码，换个宪章文件就行。比如你把宪章从「内容工作室」改成「科研实验室」，AI立刻就切换行为模式，底层系统完全不用动。

第二层，CEO（战略师）——公司的首席执行官。
你给它一句自然语言的目标，比如「写一套开发信邮件序列」，它就会把这个大目标，拆成一套有前后依赖关系的任务流，比如先做客户调研、再写邮件草稿、最后润色优化。每个任务都会标清楚：需要什么技能、预估要花多少token、优先级是高还是低，相当于给团队出了完整的执行方案。

第三层，CFO（财务官）——整个系统最核心的守门员，也是这篇论文最大的亮点。
任何任务想执行，必须先过CFO这关，它有三道死检查，一条不满足，直接打回，连一个token都不会让AI花：
第一，余额检查：这个任务预估花的钱，会不会让公司账户余额低于最低储备金，不能干着干着没钱了；
第二，日限额检查：今天已经花的钱，加上这个任务的开销，会不会超了宪章里定的单日消费上限；
第三，盈利检查：如果这个活有收入，必须保证能赚到宪章里定的最低利润，比如默认毛利率不能低于35%，亏本买卖绝对不接。
除了管钱，它还有个招标机制：每个任务会给符合技能要求的AI工人发招标书，工人报价格、交付时间、完成信心分，CFO会用公式算性价比，选最优的工人来干；要是报价超了剩余预算，还会直接跟工人砍价，逼着它压缩token预算，绝对不超支。

第四层，工人+权限系统——干活的员工，权限是「赚来的」，不是天生就有的。
这里用了一个叫TrustScore（信任分）的机制，满分100，每个AI工人初始只有50分，分不够，就没权限干高危操作，门槛卡得死死的：
10分才能读本地文件，40分才能写文件，50分才能调用外部API，60分才能执行shell命令，80分才能动真金白银花钱。
最关键的是，加分减分是不对称的：活干成了、审计通过，只加5分；活干砸了、审计没通过，直接扣15分；超预算额外再扣10分。
举个例子，初始50分的工人，想解锁花钱的权限，得连续6次审计全过，才能从50涨到80；但只要搞砸一次，50直接掉到35，连写文件的权限都给你收了。这就从根本上避免了新AI上来就瞎操作的问题，必须靠靠谱的干活，一步步赚权限。

第五层，审计官+不可篡改账本——公司的审计部+财务台账。
AI把活干完，审计官立刻上线，拿着宪章里定的KPI，给输出打分，0.5分以上才算合格。
最关键的是，每一份审计报告，都会生成一个SHA-256的哈希值，也就是「证据哈希」——报告里的任何一个字、一个数字改了，哈希值就对不上，完全防篡改。而且所有审计记录、花钱流水，都存在一个「只能追加、不能修改删除」的账本里，永久留痕，随时能查，谁都改不了。
审计结果还会直接反馈到信任分：过了就加分，没过就扣分，还会把问题记下来，让AI下次别再犯同样的错。

接下来给你说，这套系统实际效果怎么样，论文里的测试结果，全是硬数据，大白话给你说清楚：
第一，财务管控：他们模拟了30种违规场景，比如超预算、接亏本活、超日消费限额，Sovereign-OS100%全拦住了，一个漏网的都没有，绝对不会让AI乱花一分钱；
第二，权限管控：200次任务测试，权限放行和拒绝的准确率达到94%，那6%的误差，全是卡在分数刚好等于门槛线、审计结果还没更新的瞬间，下一个审计周期就自动修正了，完全不影响实际使用；
第三，审计完整性：1200多份审计报告，哈希校验全过，没有一个被篡改、哈希对不上的，账本绝对靠谱，没有任何数据 integrity 问题。

然后咱们说，它和现在市面上的工具，到底有啥本质区别？
现在主流的LangChain、CrewAI、AutoGen这些，都只能做多agent编排，也就是让AI组队干活，但预算管控、权限管理、输出校验、审计留痕，要么完全没有，要么只能靠第三方插件凑活，不是原生就有的。而Sovereign-OS是把这些治理能力，直接做进了操作系统的底层，不是打补丁，是从根上就管住了。
还有像Guardrails AI这种工具，只能管AI输出的内容合不合规，管不了AI花钱、管不了权限、管不了审计；区块链上的Fetch.ai、SingularityNET，是做AI之间的交易市场，管不了单个AI团队内部的财务纪律。
Sovereign-OS的定位特别清晰：专门给自主AI agent，做一套原生的、全流程的治理和财务管控系统，让AI从「只会干活的工具」，变成「有规矩、能管钱、负责任、可审计的经济主体」。
而且它已经做了落地能力，直接对接了Stripe支付，活干完、审计过了，直接就能给客户发起收款，从接活、规划、花钱、干活、审计、收钱，全流程闭环，直接就能当一个自动赚钱的AI公司用。

最后给你收个尾，说下这篇论文的核心贡献和未来方向。
这篇论文最大的创新，就是别人都在卷「怎么让AI把活干得更快、更好」，它跳出来解决了「怎么让AI把活干得合规、省钱、靠谱、可追溯」的核心问题，第一次给自主AI agent做了一套完整的、治理优先的操作系统。而且它是完全宪章驱动的，灵活性极强，换个YAML文件，就能切换AI的全部行为模式，一行代码都不用改。
未来他们还想做的，包括把账本放到区块链上做第三方公证、多个AI团队之间跨宪章合作、让信任分的加减更智能，而不是固定数值，还有在真实生产环境里长期跑，验证实际的省钱效果和用户信任度。

说白了，这篇论文干的事，就是给现在野蛮生长的AI agent，装了一套严丝合缝的现代公司治理体系，从宪法、CEO、CFO、员工权限、审计、财务账本，全给你配齐了，从根上解决了AI乱花钱、瞎操作、干了活没保障的行业痛点。

【我感觉这里的宪章 cfo 和budegt token预算能联系起来】


话核心结论先给你
这篇论文解决的是多智能体 LLM 系统服务架构太死板的致命问题 —— 现在你熟悉的 MCP、Google A2A 这类 Agent 通信协议，都是开发者写代码时就定死了通信模式，没法根据系统实时运行状态动态调整，导致性能严重拉胯。他们借鉴软件定义网络 SDN 的思路，做了一套可编程、全局自适应的智能体服务框架，实测吞吐量最高提升 3.6 倍，再加底层 Agent 控制能力，还能再提升 2.3 倍。

---
第一部分：他们到底要解决什么核心痛点
现在 LLM 早就不是单轮对话了，主流都是多智能体流水线。比如最典型的代码开发场景：一个开发 Agent 写函数，一个测试 Agent 给反馈，两个 Agent 要频繁通信，还要调用各种工具、数据库、其他模型。为了让 Agent 之间能通上话，业界出了 MCP、A2A、ACP 这类标准协议，它们解决了Agent 能不能连上的问题，但完全没解决怎么连才最高效的问题。
核心矛盾非常直白：Agent 之间的通信模式，根本没有永远最优的固定解。
- 系统负载高、请求多的时候，把所有函数一次性打包发的批处理模式，能扛住吞吐量，减少排队；
- 系统负载低、要交互式响应的时候，token 级流式传输，延迟最低，体验最丝滑。
但现在的所有协议，全是开发者写代码时就把通信模式写死了，定了流式就永远流式，定了批处理就永远批处理，不管系统运行时是闲是忙都没法改，最终结果就是性能暴跌、资源浪费、用户体验差。

---
第二部分：现有架构的三个致命缺陷
论文把现有方案的问题总结得非常透彻，三个核心硬伤：
1. 提前绑定，写死就改不了。比如用 A2A 写代码，代码里定了流式通信，那不管系统负载多高，都只能用流式，没法动态切批处理。论文实测，选错模式性能直接掉 3.6 倍。
2. 没有全局视野。每个 Agent 都是 “瞎子”，不知道其他 Agent 的状态。比如下游测试 Agent 的队列已经堵炸了，上游开发 Agent 还在疯狂发数据，根本没法绕路、没法减速，全是各自为战。
3. 没有端到端全局控制。你没法给整个 Agent 流水线定高层规则，比如 “交互式请求优先走流式，后台任务走批处理”，也没法做请求优先级调度、KV 缓存预加载这类优化，全靠开发者手动调每个 Agent 的参数，系统一复杂根本管不过来。

---
第三部分：他们的解决方案 ——SDN 启发的三层软件定义架构
他们没有搞新的通信协议，而是给现有的 MCP、A2A 这些协议，加了一个全局可编程的控制大脑，把 Agent 服务的控制面和数据面分离，复刻了当年 SDN 对网络架构的革命。整个架构分三层，逻辑非常清晰：
第一层：可配置的数据面
这是 Agent 之间传话的通道，他们做了一个薄薄的兼容层，夹在现有的 MCP/A2A 协议和底层网络之间。最大的好处是：你不用改原来的 Agent 代码，不用换协议，这个兼容层就能让控制器在运行时，动态调整通信模式—— 负载高了直接从流式切全量批处理，负载降下来再切回流式，全程不停服务、不改代码。支持从 token 级流式、单函数流水线到全量批处理的所有粒度，全都是动态可调的。
第二层：指标面
说白了就是给控制器装眼睛和耳朵，让它能看见全系统的状态。他们做了两级采集架构：
- 每个机器上有本地采集器，收两类核心数据：一类是系统级的，比如 GPU/CPU 利用率、队列长度、内存压力；另一类是应用级的，比如请求延迟、首包时间 TTFT、单 token 生成时间 TPT 这些 LLM 核心指标。
- 中央控制器按需拉取数据，不用一直传输，开销极低。同时还能给指标加语义，告诉控制器 “GPU 利用率高是好事，队列太长是坏事”，让它知道该怎么决策。
第三层：控制面 —— 整个系统的大脑
这是最核心的部分，是一个逻辑集中的中央控制器，干三件核心事：
1. 拿到全系统的所有指标，拥有全局视野，知道每个 Agent 忙不忙、哪里堵了、哪里有空闲资源，彻底解决了之前 “瞎子” 的问题。
2. 能听懂高层业务目标，比如 “90% 的交互式请求延迟要低于 200ms”“最大化吞吐量”，不用你写一堆底层规则，它自己会把目标翻译成实时控制指令。
3. 既能给数据面发规则、动态调整通信模式，还能直接控制 Agent 本身的行为 —— 比如动态改 vLLM 的最大批处理大小、Agent 过载时提前迁移 KV 缓存到空闲实例、给请求绕路、调整优先级，甚至暂停非核心后台任务，全都是运行时直接操作，不用改代码。
为了兼容各种各样的 Agent 和工具，他们做了极简的统一 API，就两个函数：set()和reset()。不管你是什么 Agent、什么底层框架，只要写个薄薄的适配层，控制器就能用这两个函数控制所有参数，扩展性极强。

---
第四部分：实测效果怎么样
他们做了完整的原型机，基于 Google A2A 协议，搭了开发 Agent + 测试 Agent 的 MetaGPT 代码开发工作流，实测结果非常能打：
1. 只靠动态调整通信模式，吞吐量就比固定模式的基线，最高提升 3.6 倍，不管负载高低，都能自动切到最优模式。
2. 再加底层 Agent 控制能力，比如 KV 缓存迁移、负载均衡、预加载提示，吞吐量比基线再提升 2.3 倍，其中带预加载提示的方案，比不带的性能好 1.8 倍。

---
第五部分：核心意义与未来方向
首先，它最大的落地价值是：不推翻现有生态，不是要做新的协议替代 MCP、A2A，而是给这些现有协议加了一个动态控制的大脑，完全兼容现有代码，拿来就能用。其次，它把 Agent 服务从 “开发者写死的静态架构”，变成了 “可编程、自适应、全局优化的动态系统”，相当于给多智能体系统做了一个核心 “操作系统内核”，解决了现在多智能体系统越做越复杂、性能越来越难管控的核心痛点，复刻了当年 SDN 对网络行业的变革。
未来的方向也非常明确：可以做声明式的策略语言，运维只用说人话定目标，不用写代码；可以做在线策略自学习，自动根据系统状态优化规则；还能支持混合云架构，同时管理本地 Agent 和云端第三方工具，给未来大规模多智能体系统搭了核心底层架构。



1. 论文主线

- 在一个甚至多个完整的 agent workflow（每个 workflow 包含多步 LLM 调用）中，如何利用 workflow 级的结构信息（哪一步关键、剩多少预算、多个 workflow 怎么共享资源），做整体的成本-质量分配？
- 本文的研究问题是：当优化单位从"一次 LLM 请求"变成"一个完整 agent workflow"，并且多个 workflow 共享同一个预算池和多条后端路径的 RPM / 并发配额时，显式维护 workflow 状态是否会改变固定预算下的最终成功率？ 如果答案是肯定的，再进一步问：这个收益来自预算配速、步骤重要性、进展先验，还是多 workflow 调度？把 agent workflow 的 LLM 花费变成一个可审计、可消融、可复现实验的问题。


2. 本文的三个研究问题与独特贡献

暂时无法在飞书文档外展示此内容

1. 连续质量视角：将 LLM 质量视为 [0,1] 连续变量
2. 预算硬约束 + 动态配速：budget_factor 近似预算边际价值 λ
3. 显式任务价值 wi：调用方声明的可解释信号
4. 僵尸止损：截断"成本涨、质量不涨"的无效调用
5. 无需训练：优化启发式，即时部署，对比 RL 方法更轻量


3. 项目架构

Agent Workflow（N 个 LLM 调用步骤）× J 个并发 workflow
        │
        ▼
═══════════════════ BudgetFlow ═══════════════════
│ 【约束层】Governor                           │  ← policy-agnostic
│   预算预留/结算 + 后端级限流 + 并发准入       │
│                                              │
│ 【优化层】ModelSelector（可插拔）             │  ← 唯一 routing policy
│   本文默认：预计进展增益 + budget_pressure    │
│   可替换为：RL policy / CARROT / ...         │
│                                              │
│ 【止损层】ZombieDetector + Preemption        │  ← policy-agnostic
│   僵尸截断 + 交互式任务抢占                   │
│                                              │
│ 【调度层】Multi-Workflow Scheduler           │  ← policy-agnostic
│   跨 workflow 协调 + admission control       │
═══════════════════════════════════════════════
        │
        ▼
LLM 后端池 → events.jsonl → 指标计算

4. 相关工作分类

- 操作系统资源管理：AgentRM, AgentCgroup, AIOS, pMVX
- 任务-模型路由：RouteLLM, CARROT, OmniRouter
- 分步骤强化学习的模型路由策略：BoPo
- GPU资源预算控制：Athena-Serve
- 硬件资源编排：Murakkab


5. 汇总表
[图片]

6. 关键差异分析

[图片]


[图片]

7. 和本文最接近的论文：BoPo

暂时无法在飞书文档外展示此内容

8. 论文边界

暂时无法在飞书文档外展示此内容


9. 叙事：参照vLLM

[图片]


- vLLM 是 UC Berkeley 于 2023 年发布的开源 LLM 推理引擎（SOSP 2023）。其第一篇论文处理的是 single-tenant 问题：给定一台 GPU 服务器收到多个独立推理请求，引擎应如何 batch 与调度以最大化吞吐？该工作假设硬件由单一运营方拥有，未对竞争用户之间的策略仲裁做任何主张。后续工作——包括 Andes（OSDI 2024）、SGLang router 等——把这一基础扩展到 multi-tenant 设定：多个用户、团队或服务共享同一推理基础设施，系统在 priority、quota、SLA 约束下做仲裁。
- 这种"先优化单决策主体、再引入多决策主体仲裁"的两阶段演进，是 systems 社区的成熟研究路径。第一阶段建立核心机制（在 vLLM 的例子中是 paged KV-cache 与 continuous batching）；第二阶段在 single-tenant 案例被充分理解之后，在该机制之上叠加政策层。
- BudgetFlow 走同样的路径。本文（paper 1）处理 single-budget-owner 情形：一个实体持有固定的算力 / token 预算，在其上运行多个 agent workflow；本文的贡献是构建在该预算之上做跨 workflow 分配的 cost-model-agnostic scheduler。
- 自然的续作是 multi-tenant agent compute resource allocation：多个团队、部门或外部客户各自持有独立预算、优先级与 SLA，共享同一个 agent 执行底层。这一设定引入新的问题——cross-tenant 隔离、异构 workload 混合下的 quota 仲裁、budget-aware admission control——超出本文 scope，但都是本文框架的直接扩展。
- 重要的是，本文 scheduler 的 cost-model-agnostic 性质在 multi-tenant 扩展中得以保留：租户可以使用不同的底层模型与成本结构，无需修改仲裁层。
- 我们因此把本文定位为：multi-tenant workflows 工作可以在其上构建的 single-tenant 基础。




Appendix

 +----------------------------------+       +-----------------------------+
 | LangChain / SWE-agent / AutoGen  |       | Self-built agent platform   |
 +----------------------------------+       +-----------------------------+
       |                    |                         |
       | Proxy mode:        | Callback mode:          | Explicit mode:
       | LLM request msgs   | tool events + metadata  | task_type + w_i
       v                    v                         v
 +------------------+ +------------------+      +------------------+
 |  BudgetFlow Proxy   | | BudgetFlow Adapter  |      |   BudgetFlow SDK    |
 +------------------+ +------------------+      +------------------+
          \                  |                         /
           \                 |                        /
            +----------------+-----------------------+
                             |
                             v
                    +--------------------+
                    |  BudgetFlow Runtime   |
                    +--------------------+
                             |
                             v
          +-------------------------------------+
          | Governor: budget + backend quotas |
          +-------------------------------------+
                             |
                             v
       +------------------------------------------+
       | ModelSelector: budget_pressure + importance |
       +------------------------------------------+
                             |
                             v
          +-----------------------------+
          | Multi-workflow Scheduler    |
          +-----------------------------+
                             |
                             v
          +-----------------------------+
          | LLM Backend Pool            |
          +-----------------------------+

暂时无法在飞书文档外展示此内容

[图片]

+-----------------------------------------------------------------------------+
|                               Murakkab (Top Layer)                          |
|  全栈SLO编排：整个agent工作流怎么全局优化硬件成本，保证按时完成任务          |
+-----------------------------------------------------------------------------+
|  核心问题：云怎么用最少的GPU跑所有agent | 优化目标：最小化云的硬件成本       |
|  决策单位：整个工作流                   | 预算约束：❌ 只优化单位成本，无硬上限 |
+-----------------------------------------------------------------------------+
                                      ↓
+-----------------------------------------------------------------------------+
|                              BudgetFlow (Upper Layer)                        |
|  全局预算控制：给你固定100块钱，怎么花能解最多的bug，不超支也不浪费          |
+-----------------------------------------------------------------------------+
|  核心问题：用户怎么用固定的钱完成最多任务 | 优化目标：固定预算下最大化成功率   |
|  决策单位：单个步骤 + 全局预算池         | 预算约束：✅ 核心就是硬预算上限     |
+-----------------------------------------------------------------------------+
                                      ↓
+-----------------------------------------------------------------------------+
|                               Aragog (Middle Layer)                         |
|  动态模型路由：每个步骤用哪个模型能最快跑完，不浪费空闲GPU                  |
+-----------------------------------------------------------------------------+
|  核心问题：怎么让GPU一直忙，不闲着        | 优化目标：最大化系统吞吐量         |
|  决策单位：单个步骤                     | 预算约束：❌ 只要GPU闲着就用，不管多贵 |
+-----------------------------------------------------------------------------+
                                      ↓
+-----------------------------------------------------------------------------+
|                               Parrot (Bottom Layer)                         |
|  多轮请求流水线：同一个agent的多轮对话怎么跑更快，减少等待时间              |
+-----------------------------------------------------------------------------+
|  核心问题：单轮请求怎么跑更快            | 优化目标：最小化单请求延迟         |
|  决策单位：单请求内部的token流           | 预算约束：❌ 完全不考虑钱           |
+-----------------------------------------------------------------------------+
                                      ↓
+-----------------------------------------------------------------------------+
|                          LLM Backends + GPU/CPU Hardware                    |
+-----------------------------------------------------------------------------+




