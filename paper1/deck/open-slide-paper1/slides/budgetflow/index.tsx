import type { DesignSystem, Page, SlideMeta } from '@open-slide/core';

export const design: DesignSystem = {
  palette: { bg: '#0f172a', text: '#e2e8f0', accent: '#3b82f6' },
  fonts: {
    display: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace',
    body: 'ui-sans-serif, system-ui, -apple-system, sans-serif',
  },
  typeScale: { hero: 168, body: 40 },
  radius: 4,
};

const muted = '#64748b';
const border = '#1e293b';
const accentBg = '#1e3a5f';
const success = '#10b981';
const warning = '#f59e0b';

const fill = {
  width: '100%',
  height: '100%',
  fontFamily: 'var(--osd-font-body)',
} as const;

const padding = 120;

// ─── 01: Cover ───

const Cover: Page = () => (
  <div
    style={{
      ...fill,
      background: 'var(--osd-bg)',
      color: 'var(--osd-text)',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      padding: `0 ${padding}px`,
    }}
  >
    <div
      style={{
        fontSize: 28,
        color: 'var(--osd-accent)',
        fontFamily: 'var(--osd-font-display)',
        letterSpacing: '0.2em',
        marginBottom: 32,
      }}
    >
      RESEARCH PAPER
    </div>
    <h1
      style={{
        fontFamily: 'var(--osd-font-display)',
        fontSize: 'var(--osd-size-hero)',
        fontWeight: 800,
        lineHeight: 1.1,
        margin: 0,
        color: 'var(--osd-text)',
      }}
    >
      BudgetFlow
    </h1>
    <p
      style={{
        fontSize: 64,
        fontFamily: 'var(--osd-font-display)',
        color: 'var(--osd-accent)',
        margin: '24px 0 48px',
        fontWeight: 500,
      }}
    >
      面向 Agent 工作流的动态预算路由机制
    </p>
    <div style={{ fontSize: 36, color: muted, maxWidth: 1200 }}>
      固定预算下 Agent Workflow 的成本-质量联合优化
    </div>
    <div
      style={{
        position: 'absolute',
        bottom: padding,
        display: 'flex',
        gap: 64,
        fontSize: 28,
        color: muted,
      }}
    >
      <span>Agent OS Workshop 2026</span>
      <span>Single Budget Owner, Multi-Workflow</span>
    </div>
  </div>
);

// ─── 02: Research Problem ───

const Problem: Page = () => (
  <div style={{ ...fill, background: 'var(--osd-bg)', color: 'var(--osd-text)', padding }}>
    <h2 style={{ fontFamily: 'var(--osd-font-display)', fontSize: 80, fontWeight: 800, margin: 0 }}>
      研究主线
    </h2>
    <div
      style={{
        marginTop: 64,
        fontSize: 42,
        lineHeight: 1.6,
        color: 'var(--osd-text)',
        maxWidth: 1600,
      }}
    >
      <p>
        当优化单位从 <span style={{ color: 'var(--osd-accent)', fontWeight: 600 }}>「一次 LLM 请求」</span>
        <br />
        变成 <span style={{ color: 'var(--osd-accent)', fontWeight: 600 }}>「一个完整 Agent Workflow」</span>
        <br />
        多个 workflow 共享同一个预算池与后端配额——
      </p>
      <p style={{ marginTop: 40 }}>
        显式维护 workflow 状态能否显著提高固定预算下的最终成功率？
      </p>
      <div
        style={{
          marginTop: 56,
          padding: 32,
          border: `2px solid ${border}`,
          borderRadius: 8,
          background: accentBg,
          fontSize: 36,
          color: 'var(--osd-accent)',
          fontFamily: 'var(--osd-font-display)',
        }}
      >
        把 Agent Workflow 的 LLM 花费变成一个可审计、可消融、可复现实验的问题
      </div>
    </div>
  </div>
);

// ─── 03: Research Questions ───

const ResearchQuestions: Page = () => (
  <div style={{ ...fill, background: 'var(--osd-bg)', color: 'var(--osd-text)', padding }}>
    <h2 style={{ fontFamily: 'var(--osd-font-display)', fontSize: 80, fontWeight: 800, margin: 0 }}>
      三个研究问题
    </h2>
    <div
      style={{
        marginTop: 40,
        display: 'grid',
        gridTemplateColumns: '80px 1fr 480px',
        gap: '20px 16px',
        fontSize: 30,
      }}
    >
      {/* Header */}
      <div style={{ fontFamily: 'var(--osd-font-display)', color: 'var(--osd-accent)' }}>RQ</div>
      <div style={{ fontFamily: 'var(--osd-font-display)', color: 'var(--osd-accent)' }}>问题</div>
      <div style={{ fontFamily: 'var(--osd-font-display)', color: 'var(--osd-accent)' }}>
        主要指标
      </div>
      {/* RQ1 */}
      <div style={{ fontFamily: 'var(--osd-font-display)', color: success, fontWeight: 700 }}>1</div>
      <div>多 workflow 在固定预算与共享后端限流下并行运行时，预算浪费在何处？</div>
      <div style={{ color: muted }}>
        预算违规率、429 率、队列延迟、回收预算、僵尸取消数
      </div>
      {/* RQ2 */}
      <div style={{ fontFamily: 'var(--osd-font-display)', color: success, fontWeight: 700 }}>2</div>
      <div>利用 workflow 阶段状态做 step 选模，能否 resolve 更多任务？</div>
      <div style={{ color: muted }}>固定预算下 resolved rate；Full vs WF vs Budget-Only</div>
      {/* RQ3 */}
      <div style={{ fontFamily: 'var(--osd-font-display)', color: success, fontWeight: 700 }}>3</div>
      <div>削弱 prefix-cache 局部性时，阶段调度仍能带来净收益？</div>
      <div style={{ color: muted }}>换模频率、prefill 延迟、cached-token 比例</div>
    </div>
    <h2
      style={{
        fontFamily: 'var(--osd-font-display)',
        fontSize: 52,
        fontWeight: 800,
        margin: '40px 0 24px',
      }}
    >
      五个独特贡献
    </h2>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 20px', fontSize: 28 }}>
      {[
        '连续质量视角：质量 ∈ [0,1] 连续变量',
        '预算硬约束 + 动态配速：budget_factor ≈ λ',
        '显式任务价值 w_i：调用方声明的可解释信号',
        '僵尸止损：截断「成本涨、质量不涨」',
        '无需训练：启发式，即时部署',
      ].map((s, i) => (
        <div key={i} style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
          <span style={{ color: 'var(--osd-accent)', fontFamily: 'var(--osd-font-display)' }}>
            {i + 1}.
          </span>
          <span>{s}</span>
        </div>
      ))}
    </div>
  </div>
);

// ─── 04: Architecture ───

const Architecture: Page = () => (
  <div style={{ ...fill, background: 'var(--osd-bg)', color: 'var(--osd-text)', padding }}>
    <h2 style={{ fontFamily: 'var(--osd-font-display)', fontSize: 72, fontWeight: 800, margin: 0 }}>
      项目架构
    </h2>
    <div style={{ marginTop: 32, fontSize: 26, fontFamily: 'var(--osd-font-display)' }}>
      {/* Top */}
      <div style={{ textAlign: 'center', padding: 8, color: muted }}>
        Agent Workflow（N 个 LLM 调用步骤）× J 个并发 workflow
      </div>
      <div style={{ textAlign: 'center', fontSize: 36, color: 'var(--osd-accent)' }}>▼</div>

      {/* BudgetFlow box */}
      <div
        style={{
          border: `2px solid var(--osd-accent)`,
          borderRadius: 6,
          padding: 16,
          margin: '4px 0',
        }}
      >
        <div
          style={{
            textAlign: 'center',
            fontSize: 28,
            fontWeight: 800,
            color: 'var(--osd-accent)',
            marginBottom: 12,
            letterSpacing: '0.1em',
          }}
        >
          ═══ BUDGETFLOW ═══
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr',
            gap: 10,
          }}
        >
          {[
            ['Governor', '预算预留/结算 + 后端级限流 + 并发准入', 'policy-agnostic'],
            [
              'ModelSelector',
              '预计进展增益 + budget_pressure · 可插拔 RL policy',
              '唯一 routing policy',
            ],
            ['ZombieDetector + Preemption', '僵尸截断 + 交互式任务抢占', 'policy-agnostic'],
            ['Multi-Workflow Scheduler', '跨 WF 协调 + admission control', 'policy-agnostic'],
          ].map(([name, desc, tag], i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '10px 16px',
                background: border,
                borderRadius: 4,
              }}
            >
              <div style={{ color: 'var(--osd-accent)', fontWeight: 600 }}>
                【{tag}】 {name}
              </div>
              <div style={{ color: 'var(--osd-text)' }}>{desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Bottom */}
      <div style={{ textAlign: 'center', fontSize: 36, color: 'var(--osd-accent)' }}>▼</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', color: muted }}>
        <span>LLM 后端池</span>
        <span>→</span>
        <span>events.jsonl</span>
        <span>→</span>
        <span>指标计算</span>
      </div>
    </div>
  </div>
);

// ─── 05: Related Work ───

const RelatedWork: Page = () => (
  <div style={{ ...fill, background: 'var(--osd-bg)', color: 'var(--osd-text)', padding }}>
    <h2 style={{ fontFamily: 'var(--osd-font-display)', fontSize: 80, fontWeight: 800, margin: 0 }}>
      相关工作一览
    </h2>
    <div
      style={{
        marginTop: 48,
        fontSize: 26,
        fontFamily: 'var(--osd-font-display)',
      }}
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '220px 260px 90px 90px 90px 1fr',
          gap: 12,
          padding: '12px 0',
          borderBottom: `2px solid ${border}`,
        }}
      >
        <div style={{ color: 'var(--osd-accent)', fontWeight: 700 }}>聚类</div>
        <div style={{ color: 'var(--osd-accent)', fontWeight: 700 }}>工作</div>
        <div style={{ color: 'var(--osd-accent)', fontWeight: 700, textAlign: 'center' }}>①</div>
        <div style={{ color: 'var(--osd-accent)', fontWeight: 700, textAlign: 'center' }}>②</div>
        <div style={{ color: 'var(--osd-accent)', fontWeight: 700, textAlign: 'center' }}>③</div>
        <div style={{ color: 'var(--osd-accent)', fontWeight: 700 }}>差异</div>
      </div>
      {/* BudgetFlow */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '220px 260px 90px 90px 90px 1fr',
          gap: 12,
          padding: '14px 0',
          background: accentBg,
          borderRadius: 4,
          margin: '4px 0',
        }}
      >
        <div style={{ color: success, fontWeight: 700 }}>(本文)</div>
        <div style={{ color: success, fontWeight: 700 }}>BudgetFlow</div>
        <div style={{ color: success, textAlign: 'center' }}>✓</div>
        <div style={{ color: success, textAlign: 'center' }}>✓</div>
        <div style={{ color: success, textAlign: 'center' }}>✓</div>
        <div>—</div>
      </div>
      {/* AgentRM */}
      {[
        ['OS资源管理', 'AgentRM', '✗', '✗', '✓', 'RPM/回收，非$硬账本'],
        ['OS资源管理', 'AgentCgroup', '✗', '✗', '✓', '主机 CPU/Mem cgroup'],
        ['任务-模型路由', 'RouteLLM', '✗', '✗', '✗', '偏好学习，无预算账本'],
        ['任务-模型路由', 'CARROT', '✗', '✗', '✓', 'Per-query，无跨步状态'],
        ['Step RL路由', 'BoPO', '✗', '✓', '✗', '单任务 RL，可作 ModelSelector'],
        ['Step RL路由', 'xRouter', '✗', '✓', '✗', 'RL 多模型编排，无共享池'],
        ['GPU预算', 'ATHENA-Serve', '✗', '✗', '✗', 'Serving 侧 KV/batch'],
      ].map((row, i) => (
        <div
          key={i}
          style={{
            display: 'grid',
            gridTemplateColumns: '220px 260px 90px 90px 90px 1fr',
            gap: 12,
            padding: '10px 0',
            borderBottom: `1px solid ${border}`,
          }}
        >
          <div style={{ color: muted }}>{row[0]}</div>
          <div style={{ fontWeight: 600 }}>{row[1]}</div>
          <div style={{ textAlign: 'center', color: row[2] === '✓' ? success : warning }}>
            {row[2]}
          </div>
          <div style={{ textAlign: 'center', color: row[3] === '✓' ? success : warning }}>
            {row[3]}
          </div>
          <div style={{ textAlign: 'center', color: row[4] === '✓' ? success : warning }}>
            {row[4]}
          </div>
          <div style={{ color: muted }}>{row[5]}</div>
        </div>
      ))}
      <div style={{ marginTop: 16, fontSize: 24, color: muted }}>① 共享硬顶 · ② 状态选档 · ③ 免训练</div>
    </div>
  </div>
);

// ─── 06: Key Differentiation ───

const Differentiation: Page = () => (
  <div style={{ ...fill, background: 'var(--osd-bg)', color: 'var(--osd-text)', padding }}>
    <h2 style={{ fontFamily: 'var(--osd-font-display)', fontSize: 80, fontWeight: 800, margin: 0 }}>
      关键差异
    </h2>
    <div
      style={{
        marginTop: 48,
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 40,
        fontSize: 30,
      }}
    >
      {/* vs BoPO */}
      <div>
        <div
          style={{
            fontFamily: 'var(--osd-font-display)',
            fontSize: 32,
            color: 'var(--osd-accent)',
            marginBottom: 20,
            paddingBottom: 12,
            borderBottom: `2px solid ${border}`,
          }}
        >
          vs BoPO (Budget-Aware Agentic Routing)
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {[
            ['方法', 'RL 需训练', '启发式，即时部署'],
            ['可解释', '策略黑盒', '边际性价比 + budget_factor'],
            ['预算', 'soft-budget', '运行时 hard constraint'],
            ['任务价值', '隐式', '显式 w_i'],
            ['止损', '无机制', 'ZombieDetector'],
          ].map(([dim, bop, bf], i) => (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div style={{ color: muted, fontSize: 26 }}>{dim}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: warning }}>BoPO: {bop}</span>
                <span style={{ color: success, fontWeight: 600 }}>BudgetFlow: {bf}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
      {/* vs Per-query */}
      <div>
        <div
          style={{
            fontFamily: 'var(--osd-font-display)',
            fontSize: 32,
            color: 'var(--osd-accent)',
            marginBottom: 20,
            paddingBottom: 12,
            borderBottom: `2px solid ${border}`,
          }}
        >
          vs Per-query Routers (RouteLLM, CARROT)
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {[
            ['决策', '单 query 独立最优', '跨 N 步联合预算约束'],
            ['状态', '无状态', '有状态（预算/burn rate）'],
            ['预算', '不管或仅预测', 'Hard budget 硬约束'],
            ['任务价值', '不区分', '显式 w_i'],
          ].map(([dim, pq, bf], i) => (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div style={{ color: muted, fontSize: 26 }}>{dim}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: warning }}>Per-query: {pq}</span>
                <span style={{ color: success, fontWeight: 600 }}>BudgetFlow: {bf}</span>
              </div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 24, padding: 20, background: accentBg, borderRadius: 6 }}>
          <div style={{ color: 'var(--osd-accent)', fontWeight: 600 }}>兼容性：</div>
          <div style={{ fontSize: 28, color: 'var(--osd-text)' }}>
            BoPO / CARROT policy 可作 BudgetFlow ModelSelector 的 plug-in
          </div>
        </div>
      </div>
    </div>
  </div>
);

// ─── 07: BoPO Deep Dive ───

const BoPODive: Page = () => (
  <div style={{ ...fill, background: 'var(--osd-bg)', color: 'var(--osd-text)', padding }}>
    <h2 style={{ fontFamily: 'var(--osd-font-display)', fontSize: 80, fontWeight: 800, margin: 0 }}>
      BoPO：最接近的工作
    </h2>
    <div style={{ marginTop: 32, fontSize: 32, lineHeight: 1.5 }}>
      <p style={{ margin: 0, color: muted }}>
        Budget-Aware Agentic Routing via Boundary-Guided Policy Optimization（Zhang et al.,
        arXiv:2602.21227）
      </p>
      <div style={{ marginTop: 32, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 48 }}>
        <div>
          <div style={{ color: warning, fontFamily: 'var(--osd-font-display)', marginBottom: 20 }}>
            BoPO 做什么
          </div>
          <ul style={{ paddingLeft: 28, margin: 0 }}>
            <li style={{ marginBottom: 12 }}>单任务 step 级 RL 路由策略</li>
            <li style={{ marginBottom: 12 }}>同域大量轨迹预训练</li>
            <li style={{ marginBottom: 12 }}>每步根据上下文、历史、该任务剩余预算输出档位</li>
            <li>奖励绑定该任务成败与花费</li>
          </ul>
        </div>
        <div>
          <div
            style={{
              color: 'var(--osd-accent)',
              fontFamily: 'var(--osd-font-display)',
              marginBottom: 20,
            }}
          >
            BudgetFlow 补充什么
          </div>
          <ul style={{ paddingLeft: 28, margin: 0 }}>
            <li style={{ marginBottom: 12 }}>全局账本：预留/结算</li>
            <li style={{ marginBottom: 12 }}>硬预算 + RPM/并发准入</li>
            <li style={{ marginBottom: 12 }}>多 workflow 调度</li>
            <li style={{ marginBottom: 12 }}>ZombieDetector：回收无进度任务</li>
            <li>零域数据：免训练冷启动</li>
          </ul>
        </div>
      </div>
      <div
        style={{
          marginTop: 36,
          padding: 24,
          border: `2px solid var(--osd-accent)`,
          borderRadius: 8,
          background: accentBg,
          fontFamily: 'var(--osd-font-display)',
          fontSize: 30,
        }}
      >
        <span style={{ color: warning }}>BoPO</span>
        <span style={{ color: 'var(--osd-text)', margin: '0 12px' }}>→</span>
        <span style={{ color: 'var(--osd-accent)' }}>ModelSelector plug-in</span>
        <span style={{ color: 'var(--osd-text)', margin: '0 12px' }}>→</span>
        <span style={{ color: success }}>运行时底座保证全局硬约束</span>
      </div>
    </div>
  </div>
);

// ─── 08: vLLM Narrative ───

const VLLMNarrative: Page = () => (
  <div style={{ ...fill, background: 'var(--osd-bg)', color: 'var(--osd-text)', padding }}>
    <h2 style={{ fontFamily: 'var(--osd-font-display)', fontSize: 80, fontWeight: 800, margin: 0 }}>
      叙事：参照 vLLM
    </h2>
    <div style={{ marginTop: 48, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 64 }}>
      {/* vLLM path */}
      <div>
        <div
          style={{
            fontFamily: 'var(--osd-font-display)',
            fontSize: 36,
            color: 'var(--osd-accent)',
            marginBottom: 24,
          }}
        >
          vLLM 演进路径
        </div>
        <div style={{ fontSize: 30, lineHeight: 1.5, display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div
            style={{
              padding: 20,
              border: `2px solid ${border}`,
              borderRadius: 6,
            }}
          >
            <div style={{ fontWeight: 600, color: 'var(--osd-accent)' }}>Phase 1</div>
            <div style={{ color: 'var(--osd-text)' }}>
              SOSP 2023：Single-tenant，多独立请求 batch 调度
            </div>
            <div style={{ color: muted, fontSize: 26 }}>核心机制：paged KV-cache + continuous batching</div>
          </div>
          <div
            style={{
              padding: 20,
              border: `2px solid var(--osd-accent)`,
              borderRadius: 6,
              background: accentBg,
            }}
          >
            <div style={{ fontWeight: 600, color: 'var(--osd-accent)' }}>Phase 2</div>
            <div style={{ color: 'var(--osd-text)' }}>
              Andes / SGLang router：Multi-tenant，跨团队 SLA / quota 仲裁
            </div>
            <div style={{ color: muted, fontSize: 26 }}>
              在充分理解单主体机制后叠加政策层
            </div>
          </div>
        </div>
      </div>
      {/* BudgetFlow path */}
      <div>
        <div
          style={{
            fontFamily: 'var(--osd-font-display)',
            fontSize: 36,
            color: 'var(--osd-accent)',
            marginBottom: 24,
          }}
        >
          BudgetFlow 定位
        </div>
        <div style={{ fontSize: 30, lineHeight: 1.5, display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div
            style={{
              padding: 20,
              border: `2px solid var(--osd-accent)`,
              borderRadius: 6,
              background: accentBg,
            }}
          >
            <div style={{ fontWeight: 600, color: success }}>Paper 1 (本文)</div>
            <div style={{ color: 'var(--osd-text)' }}>
              Single-Budget-Owner：一个实体持固定预算，跨 workflow 分配
            </div>
            <div style={{ color: muted, fontSize: 26 }}>
              核心机制：cost-model-agnostic scheduler
            </div>
          </div>
          <div
            style={{
              padding: 20,
              border: `2px dashed ${border}`,
              borderRadius: 6,
              opacity: 0.7,
            }}
          >
            <div style={{ fontWeight: 600, color: 'var(--osd-accent)' }}>Paper 2 (续作)</div>
            <div style={{ color: 'var(--osd-text)' }}>
              Multi-tenant：多团队各持独立预算、优先级与 SLA
            </div>
            <div style={{ color: muted, fontSize: 26 }}>
              Cross-tenant 隔离、异构 workload 混合、budget-aware admission
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
);

// ─── 09: Closing ───

const Closing: Page = () => (
  <div
    style={{
      ...fill,
      background: 'var(--osd-bg)',
      color: 'var(--osd-text)',
      padding,
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
    }}
  >
    <h1
      style={{
        fontFamily: 'var(--osd-font-display)',
        fontSize: 140,
        fontWeight: 800,
        margin: 0,
        color: 'var(--osd-accent)',
      }}
    >
      Thank You
    </h1>
    <div style={{ marginTop: 48, fontSize: 44, lineHeight: 1.5, maxWidth: 1400 }}>
      <div>
        BudgetFlow：当优化单位从「一次 LLM 请求」变成「一个完整 Agent Workflow」
      </div>
      <div style={{ marginTop: 24, color: muted, fontSize: 36 }}>
        共享硬预算 + 状态选档 + 免训练 → 固定预算下更高的任务成功率
      </div>
    </div>
    <div
      style={{
        marginTop: 64,
        display: 'flex',
        gap: 32,
        fontSize: 32,
        fontFamily: 'var(--osd-font-display)',
        color: muted,
      }}
    >
      <span>Agent OS Workshop 2026</span>
      <span>|</span>
      <span>Single Budget Owner, Multi-Workflow</span>
    </div>
  </div>
);

export const meta: SlideMeta = { title: 'BudgetFlow' };
export default [
  Cover,
  Problem,
  ResearchQuestions,
  Architecture,
  RelatedWork,
  BoPODive,
  Differentiation,
  VLLMNarrative,
  Closing,
] satisfies Page[];
