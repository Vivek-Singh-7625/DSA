import { useContext } from 'react'
import { DataContext } from '../App'

export default function Overview() {
  const { data } = useContext(DataContext)

  // ── Top-level metrics from /api/dashboard ──
  const dash = data?.dashboard || {}
  const meta = dash.meta || {}
  const riskScore = dash.org_risk_score ?? '—'
  const decayCount = dash.decay_summary?.active_decay ?? data?.decay_alerts?.filter?.(a => a.already_decaying)?.length ?? 0
  const totalAlerts = dash.decay_summary?.total_alerts ?? data?.decay_alerts?.length ?? 0
  const totalNodes = meta.total_nodes ?? '—'
  const totalRelationships = meta.total_relationships ?? '—'
  const totalDprs = meta.total_dprs ?? dash.dpr_summary?.total ?? 0
  const components = dash.dpr_summary?.components || []

  // ── Bus factor from /api/knowledge ──
  const engineers = data?.knowledge?.human_profiles || []
  const topEngineer = engineers[0]
  const criticalBusFactors = engineers.filter(e => (e.bus_factor_risk_score || 0) > 50)

  // ── Live alerts from /api/decay ──
  const activeAlerts = data?.decay_alerts?.filter?.(a => a.already_decaying) || []

  // ── Component risk from /api/knowledge ──
  const compProfiles = data?.knowledge?.component_profiles || []

  // ── Causal chain: find the longest connected chain from graph edges ──
  const edges = data?.graph_data?.edges || []
  const nodes = data?.graph_data?.nodes || []
  const decayingIds = new Set(data?.decay_alerts?.filter?.(a => a.already_decaying)?.map(a => a.dpr_id) || [])

  // Build a simple chain: start from the most-connected decaying node
  function buildChain() {
    if (edges.length === 0) return []
    const adj = {}
    edges.forEach(e => {
      const from = e.from || e.source
      const to = e.to || e.target
      if (!adj[from]) adj[from] = []
      adj[from].push(to)
    })
    // Start from first decaying DPR that has outgoing edges
    const starts = [...decayingIds].filter(id => adj[id]?.length)
    if (starts.length === 0) return Object.keys(adj).slice(0, 5)
    // BFS to find longest path from first start
    const visited = new Set()
    const chain = []
    let queue = [starts[0]]
    while (queue.length > 0 && chain.length < 6) {
      const curr = queue.shift()
      if (visited.has(curr)) continue
      visited.add(curr)
      chain.push(curr)
      const next = adj[curr] || []
      queue.push(...next)
    }
    return chain
  }
  const causalChain = buildChain()

  function getChainColor(id) {
    if (decayingIds.has(id)) return 'var(--red)'
    const node = nodes.find(n => n.id === id)
    const br = (node?.blast_radius || '').toLowerCase()
    if (br === 'critical') return 'var(--orange)'
    if (br === 'high') return 'var(--purple)'
    return 'var(--teal)'
  }

  function getCompLevel(spof) {
    if (spof >= 5) return 'critical'
    if (spof >= 3) return 'high'
    return 'low'
  }

  return (
    <div className="stack gap-16 fade-in">
      {/* Top Stats */}
      <div className="grid-3">
        <div className="stat-card">
          <div className="stat-value" style={{ color: 'var(--teal)' }}>
            {typeof riskScore === 'number' ? riskScore.toFixed(1) : riskScore}
            <span style={{ fontSize: 18, color: 'var(--text-muted)' }}>/100</span>
          </div>
          <div className="stat-label">Organizational Risk Score</div>
          <div className="stat-sub">{totalNodes} nodes · {totalRelationships} relationships analyzed</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: 'var(--red)' }}>{decayCount}</div>
          <div className="stat-label">Assumptions Breaking</div>
          <div className="stat-sub">of {totalAlerts} monitored · {decayCount} critical blast radius</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: 'var(--orange)' }}>{criticalBusFactors.length || (topEngineer ? 1 : 0)}</div>
          <div className="stat-label">Critical Bus Factor</div>
          <div className="stat-sub">{topEngineer ? `${topEngineer.name}: ${topEngineer.dpr_count} DPRs, ${topEngineer.component_count} components` : 'Analysis pending'}</div>
        </div>
      </div>

      {/* Alerts + Components */}
      <div className="grid-32">
        <div className="stack gap-8">
          <div className="section-title">Live Alerts ({activeAlerts.length})</div>
          {activeAlerts.length > 0 ? activeAlerts.map((a, i) => (
            <div key={i} className="alert-row">
              <div className="alert-header">
                <span className="alert-id">{a.dpr_id}</span>
                <span className="alert-title">{a.title || a.dpr_id}</span>
                <span className="badge badge-critical">{a.severity || a.blast_radius?.toUpperCase() || 'CRITICAL'}</span>
                <span className="badge badge-decaying">DECAYING</span>
              </div>
              <div className="alert-evidence">{a.decay_evidence || a.evidence_summary || a.evidence || 'Decay detected'}</div>
            </div>
          )) : (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', padding: 20, border: '1px solid var(--border)' }}>
              No active decay alerts. All assumptions holding.
            </div>
          )}
        </div>
        <div>
          <div className="section-title">Component Risk ({compProfiles.length || components.length})</div>
          <div className="grid-2 gap-8" style={{ gap: 8 }}>
            {compProfiles.length > 0 ? compProfiles.map(c => {
              const level = getCompLevel(c.spof_score || 0)
              return (
                <div key={c.component} className={`comp-card ${level}`}>
                  <div className="comp-name">{c.component}</div>
                  <div className="comp-metric">SPOF: <span style={{ color: level === 'critical' ? 'var(--red)' : level === 'high' ? 'var(--orange)' : 'var(--teal)' }}>{c.spof_score?.toFixed?.(1) ?? '—'}</span></div>
                  <div className="comp-metric">{c.dpr_count} DPRs</div>
                </div>
              )
            }) : components.map(name => (
              <div key={name} className="comp-card low">
                <div className="comp-name">{name}</div>
                <div className="comp-metric">{totalDprs} total DPRs</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Causal Chain */}
      {causalChain.length > 0 && (
        <div>
          <div className="section-title">Causal Chain Preview</div>
          <div className="chain">
            {causalChain.map((id, i) => (
              <span key={id} style={{ display: 'flex', alignItems: 'center' }}>
                <span className="chain-node" style={{ borderLeftColor: getChainColor(id), borderLeftWidth: 3 }}>{id}</span>
                {i < causalChain.length - 1 && <span className="chain-arrow">→</span>}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
