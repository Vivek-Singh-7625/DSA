import { useContext } from 'react'
import { DataContext } from '../App'

function heatColor(val, max) {
  const ratio = val / (max || 1)
  if (ratio > 0.7) return 'var(--red)'
  if (ratio > 0.4) return 'var(--orange)'
  return 'var(--teal)'
}

export default function KnowledgeMap() {
  const { data } = useContext(DataContext)

  const knowledge = data?.knowledge || {}
  const riskScore = knowledge.org_risk_score ?? data?.dashboard?.org_risk_score ?? '—'
  const engineers = knowledge.human_profiles || []
  const components = knowledge.component_profiles || []
  const files = knowledge.file_profiles || []
  const maxRisk = Math.max(...engineers.map(e => e.bus_factor_risk_score || 0), 1)
  const maxSpof = Math.max(...components.map(c => c.spof_score || 0), 1)

  // Top SPOF humans and components from API
  const topSpofHumans = knowledge.top_spof_humans || []
  const topSpofComponents = knowledge.top_spof_components || []

  // Empty state
  if (engineers.length === 0 && components.length === 0) {
    return (
      <div className="stack gap-16 fade-in">
        <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', padding: 40, border: '1px solid var(--border)' }}>
          Knowledge map not available. Run the knowledge concentration analysis to populate.
        </div>
      </div>
    )
  }

  return (
    <div className="stack gap-16 fade-in">
      {/* Top Stats */}
      <div className="grid-3">
        <div className="stat-card">
          <div className="stat-value" style={{ color: 'var(--teal)', fontSize: 36 }}>{typeof riskScore === 'number' ? riskScore.toFixed(1) : riskScore}</div>
          <div className="stat-label">Organizational Risk</div>
          <div className="stat-sub">{engineers.length} engineers · {components.length} components</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: 'var(--orange)', fontSize: 24 }}>{engineers[0]?.name || '—'}</div>
          <div className="stat-label">Highest Bus Factor Risk</div>
          <div className="stat-sub">
            {engineers[0] ? `${engineers[0].dpr_count} DPRs · ${engineers[0].component_count} components · risk ${engineers[0].bus_factor_risk_score?.toFixed?.(1) ?? '—'}` : 'No data'}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: 'var(--red)', fontSize: 36 }}>{components.filter(c => (c.spof_score || 0) >= 5).length}</div>
          <div className="stat-label">High-Risk Components</div>
          <div className="stat-sub">{components.filter(c => (c.spof_score || 0) >= 5).map(c => c.component).join(', ') || 'None'}</div>
        </div>
      </div>

      {/* Engineer Table + Component Heatmap */}
      <div className="grid-32">
        <div>
          <div className="section-title">Knowledge Concentration by Engineer ({engineers.length})</div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Engineer</th>
                <th className="text-right">DPRs</th>
                <th>Components</th>
                <th className="text-right">Risk</th>
                <th style={{ width: '20%' }}>Exposure</th>
              </tr>
            </thead>
            <tbody>
              {engineers.map((e, i) => (
                <tr key={i} className={i === 0 ? 'highlight' : ''}>
                  <td style={{ color: 'var(--text-primary)' }}>{e.name}</td>
                  <td className="text-right">{e.dpr_count}</td>
                  <td>{(Array.isArray(e.components) ? e.components : (e.components || '').split(' ').filter(Boolean)).join(', ')}</td>
                  <td className="text-right" style={{ color: e.bus_factor_risk_score > 50 ? 'var(--red)' : 'var(--text-secondary)' }}>{e.bus_factor_risk_score?.toFixed?.(1) || '—'}</td>
                  <td>
                    <div className="risk-bar-bg">
                      <div className="risk-bar" style={{ width: `${((e.bus_factor_risk_score || 0) / maxRisk) * 100}%`, background: e.bus_factor_risk_score > 50 ? 'var(--red)' : e.bus_factor_risk_score > 20 ? 'var(--orange)' : 'var(--teal)' }} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          <div className="section-title">Component Risk Heatmap ({components.length})</div>
          <table className="data-table">
            <thead>
              <tr><th>Component</th><th className="text-right">DPRs</th><th className="text-right">Humans</th><th className="text-right">Decay</th><th className="text-right">SPOF</th></tr>
            </thead>
            <tbody>
              {components.map((c, i) => (
                <tr key={i}>
                  <td style={{ color: 'var(--text-primary)' }}>{c.component}</td>
                  <td className="text-right" style={{ color: heatColor(c.dpr_count, Math.max(...components.map(x => x.dpr_count), 1)) }}>{c.dpr_count}</td>
                  <td className="text-right" style={{ color: heatColor(c.unique_humans, Math.max(...components.map(x => x.unique_humans), 1)) }}>{c.unique_humans}</td>
                  <td className="text-right" style={{ color: heatColor(c.avg_decay_risk || 0, 3) }}>{c.avg_decay_risk?.toFixed?.(1) ?? '—'}</td>
                  <td className="text-right" style={{ color: heatColor(c.spof_score || 0, maxSpof), fontWeight: 600 }}>{c.spof_score?.toFixed?.(1) ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Critical Files */}
      {files.length > 0 && (
        <div>
          <div className="section-title">Critical File Ownership ({files.length} files)</div>
          <table className="data-table">
            <thead>
              <tr><th>File Path</th><th className="text-right">DPRs</th><th className="text-right">Criticality</th></tr>
            </thead>
            <tbody>
              {files.slice(0, 15).map((f, i) => (
                <tr key={i}>
                  <td style={{ color: 'var(--teal)' }}>{f.file}</td>
                  <td className="text-right">{f.dpr_count}</td>
                  <td className="text-right" style={{ color: f.criticality_score >= 7 ? 'var(--red)' : f.criticality_score >= 4 ? 'var(--orange)' : 'var(--teal)' }}>{f.criticality_score?.toFixed?.(1) ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
