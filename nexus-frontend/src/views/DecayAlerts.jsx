import { useContext } from 'react'
import { DataContext } from '../App'

export default function DecayAlerts() {
  const { data } = useContext(DataContext)

  // All data from /api/decay endpoint
  const decayData = data?.decay_data || {}
  const alerts = data?.decay_alerts || []
  const totalAlerts = decayData.total_alerts ?? alerts.length
  const activeDecayCount = decayData.active_decay ?? alerts.filter(a => a.already_decaying).length

  // Latest monitoring run
  const runs = decayData.monitoring_runs || []
  const latestRun = runs.length > 0 ? runs[runs.length - 1] : null
  const lastScanTime = latestRun?.run_at
    ? new Date(latestRun.run_at).toLocaleString('sv-SE', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).replace('T', ' ')
    : '—'

  const active = alerts.filter(a => a.already_decaying)
  const monitoring = alerts.filter(a => !a.already_decaying)

  // Empty state
  if (alerts.length === 0) {
    return (
      <div className="stack gap-16 fade-in">
        <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', padding: 40, border: '1px solid var(--border)' }}>
          No decay alerts available. Run the decay scanner to generate alerts.
        </div>
      </div>
    )
  }

  return (
    <div className="stack gap-16 fade-in">
      {/* Summary */}
      <div className="grid-3">
        <div className="stat-card">
          <div className="stat-value" style={{ color: 'var(--text-primary)', fontSize: 36 }}>{totalAlerts}</div>
          <div className="stat-label">Total Alerts</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: 'var(--red)', fontSize: 36 }}>{activeDecayCount}</div>
          <div className="stat-label">Actively Decaying</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: 'var(--text-muted)', fontSize: 14, fontFamily: 'var(--font-mono)' }}>{lastScanTime}</div>
          <div className="stat-label">Last Scan</div>
          {latestRun && (
            <div className="stat-sub">{latestRun.commits_scanned} commits · {latestRun.dprs_evaluated} DPRs evaluated · {latestRun.new_alerts} new alerts</div>
          )}
        </div>
      </div>

      {/* Active Alerts */}
      <div className="stack gap-8">
        {active.map((a, i) => (
          <div key={i} className="alert-row" style={{ padding: 20 }}>
            <div className="alert-header">
              <span className="alert-id" style={{ fontSize: 15 }}>{a.dpr_id}</span>
              <span className="alert-title" style={{ fontSize: 14, fontWeight: 600 }}>{a.title || a.dpr_id}</span>
              <span className="badge badge-critical">{(a.blast_radius || 'critical').toUpperCase()}</span>
              <span className="badge badge-decaying">DECAYING</span>
            </div>
            <div style={{ marginTop: 8 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>COMPONENT</span>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>{a.component || '—'}</div>
            </div>
            <div style={{ marginTop: 8 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>EVIDENCE</span>
              <div className="alert-evidence" style={{ marginTop: 4 }}>{a.decay_evidence || a.evidence_summary || 'Decay signals detected'}</div>
            </div>
            <div style={{ display: 'flex', gap: 24, marginTop: 12, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
              <span>Signal: <span style={{ color: 'var(--text-secondary)' }}>{a.earliest_signal_date || '—'}</span></span>
            </div>
            {a.recommended_monitor_query && (
              <div style={{ marginTop: 12, background: 'var(--bg-void)', border: '1px solid var(--border)', padding: 12, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'pre-wrap', overflowX: 'auto' }}>
                {a.recommended_monitor_query}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Monitoring */}
      {monitoring.length > 0 && (
        <div className="stack gap-8">
          <div className="section-title">Monitoring (No Decay Detected)</div>
          {monitoring.map((a, i) => (
            <div key={i} className="alert-row stable" style={{ padding: 16 }}>
              <div className="alert-header">
                <span className="alert-id">{a.dpr_id}</span>
                <span className="alert-title">{a.title}</span>
                <span className="badge badge-monitoring">MONITORING</span>
              </div>
              <div className="alert-evidence">{a.decay_evidence || 'No significant decay signals detected'}</div>
              {a.recommended_monitor_query && (
                <div style={{ marginTop: 8, background: 'var(--bg-void)', border: '1px solid var(--border)', padding: 10, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'pre-wrap', overflowX: 'auto' }}>
                  {a.recommended_monitor_query}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
