import { useContext, useState } from 'react'
import { DataContext } from '../App'

export default function CounterfactualLab() {
  const { data, API } = useContext(DataContext)
  const [query, setQuery] = useState('')
  const [simulating, setSimulating] = useState(false)
  const [simResult, setSimResult] = useState(null)
  const [simError, setSimError] = useState('')
  
  // Map API traces to display format
  const rawTraces = data?.counterfactuals || []
  const cfs = rawTraces.map(t => {
    const result = t.result || {}
    return {
      id: t.id,
      question: t.question,
      target: t.target_dpr,
      verdict: (result.verdict || 'unknown').toUpperCase(),
      confidence: result.confidence || 0,
      downstream: t.downstream_count || 0,
      upstream: t.upstream_count || 0,
      timeline_narrative: result.timeline_narrative || '',
      modern_relevance: result.modern_relevance || '',
      alternative: t.alternative || '',
      broken_assumptions: result.broken_assumptions || [],
      unnecessary_workarounds: result.unnecessary_workarounds || [],
      new_problems: result.new_problems || [],
      affected_dprs: result.affected_dprs || [],
    }
  })

  const totalRelationships = data?.graph_data?.edge_count ?? data?.dashboard?.meta?.total_relationships ?? data?.graph_data?.edges?.length ?? 0

  const verdictBadge = (v) => {
    const cls = v === 'BETTER' ? 'badge-better' : v === 'WORSE' ? 'badge-worse' : 'badge-tradeoff'
    return <span className={`badge ${cls}`}>{v}</span>
  }

  // SIMULATE — POST to /api/query with the counterfactual question
  const handleSimulate = async () => {
    if (!query.trim()) return
    setSimulating(true)
    setSimResult(null)
    setSimError('')

    try {
      const apiBase = API || 'http://localhost:8000'
      const resp = await fetch(`${apiBase}/api/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query, use_gemini: true }),
      })

      if (!resp.ok) {
        throw new Error(`API returned ${resp.status}`)
      }

      const result = await resp.json()
      setSimResult(result)
    } catch (e) {
      setSimError(e.message || 'Simulation failed')
    } finally {
      setSimulating(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSimulate()
  }

  // Dynamic placeholder based on repo
  const repoName = data?.dashboard?.meta?.repository || ''
  const shortRepo = repoName.split('/').pop() || 'the codebase'
  const placeholder = `What if ${shortRepo} had used a different architecture?`

  // Empty state
  if (cfs.length === 0 && !simResult) {
    return (
      <div className="stack gap-16 fade-in">
        <div className="cf-input-area">
          <input className="cf-input" placeholder={placeholder} value={query} onChange={e => setQuery(e.target.value)} onKeyDown={handleKeyDown} />
          <button className="cf-submit" onClick={handleSimulate} disabled={simulating || !query.trim()}>
            {simulating ? 'RUNNING...' : 'SIMULATE'}
          </button>
        </div>
        {simulating && <div className="cf-sim-loading">Querying Nexus intelligence engine...</div>}
        {simError && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--red)', padding: 12 }}>{simError}</div>}
        <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', padding: 40, border: '1px solid var(--border)' }}>
          No counterfactual traces available. Run the counterfactual engine to generate traces, or use the simulate bar above.
        </div>
      </div>
    )
  }

  return (
    <div className="stack gap-16 fade-in">
      {/* Query Input */}
      <div>
        <div className="cf-input-area">
          <input className="cf-input" placeholder={placeholder} value={query} onChange={e => setQuery(e.target.value)} onKeyDown={handleKeyDown} />
          <button className="cf-submit" onClick={handleSimulate} disabled={simulating || !query.trim()}>
            {simulating ? 'RUNNING...' : 'SIMULATE'}
          </button>
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
          Powered by Gemini · Traces causal consequences through {totalRelationships} relationships
        </div>
      </div>

      {/* Simulate Loading */}
      {simulating && <div className="cf-sim-loading">Querying Nexus intelligence engine...</div>}
      {simError && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--red)', padding: 12, border: '1px solid var(--red-dim)' }}>{simError}</div>}

      {/* Simulate Result */}
      {simResult && (
        <div className="cf-simulate-result fade-in">
          <div className="cf-col-title">Simulation Result</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--teal)', marginBottom: 8 }}>
            Q: {simResult.question}
          </div>
          {simResult.gemini_answer && (
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 12, whiteSpace: 'pre-wrap' }}>
              {simResult.gemini_answer}
            </div>
          )}
          {simResult.results?.length > 0 && (
            <div>
              <div className="cf-col-title" style={{ marginTop: 8 }}>Related DPRs ({simResult.total_matches} matches)</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {simResult.results.map((r, i) => (
                  <div key={i} style={{ padding: 10, background: 'var(--bg-void)', border: '1px solid var(--border)' }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--teal)' }}>{r.dpr?.id} — {r.dpr?.title}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                      {r.dpr?.component} · Relevance: {r.relevance_score}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <button
            style={{ marginTop: 12, background: 'none', border: '1px solid var(--border)', padding: '6px 12px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', cursor: 'pointer' }}
            onClick={() => setSimResult(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Pre-computed Results */}
      <div className="section-title">Pre-Computed Counterfactuals ({cfs.length})</div>
      <div className="stack gap-8">
        {cfs.map((cf, i) => (
          <div key={i} className="cf-card">
            <div className="cf-header">
              <span className="cf-id">{cf.id}</span>
              <span className="cf-question">{cf.question}</span>
              {verdictBadge(cf.verdict)}
            </div>
            <div className="cf-meta">
              <span>Target: <span style={{ color: 'var(--teal)' }}>{cf.target}</span></span>
              <span>Confidence: <span style={{ color: 'var(--text-primary)' }}>{cf.confidence}</span></span>
              <span>Impact: <span style={{ color: 'var(--text-secondary)' }}>{cf.downstream}↓ {cf.upstream}↑</span></span>
            </div>
            <div className="cf-columns">
              <div>
                <div className="cf-col-title">Timeline Narrative</div>
                <div className="cf-col-text">{cf.timeline_narrative || 'N/A'}</div>
              </div>
              <div>
                <div className="cf-col-title">Alternative</div>
                <div className="cf-col-text">{cf.alternative || 'N/A'}</div>
              </div>
            </div>
            {cf.modern_relevance && (
              <div style={{ marginTop: 4 }}>
                <div className="cf-col-title">Modern Relevance</div>
                <div className="cf-col-text" style={{ fontSize: 12 }}>{cf.modern_relevance}</div>
              </div>
            )}
            {cf.broken_assumptions?.length > 0 && (
              <div style={{ marginTop: 4 }}>
                <div className="cf-col-title">Broken Assumptions</div>
                <ul style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--red)', paddingLeft: 16, margin: 0 }}>
                  {cf.broken_assumptions.slice(0, 3).map((a, j) => <li key={j} style={{ marginBottom: 4 }}>{typeof a === 'string' ? a : JSON.stringify(a)}</li>)}
                </ul>
              </div>
            )}
            {cf.new_problems?.length > 0 && (
              <div style={{ marginTop: 4 }}>
                <div className="cf-col-title">New Problems</div>
                <ul style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--orange)', paddingLeft: 16, margin: 0 }}>
                  {cf.new_problems.slice(0, 5).map((p, j) => <li key={j} style={{ marginBottom: 4 }}>{typeof p === 'string' ? p : JSON.stringify(p)}</li>)}
                </ul>
              </div>
            )}
            {cf.affected_dprs?.length > 0 && (
              <div style={{ marginTop: 4 }}>
                <div className="cf-col-title">Affected DPRs</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {cf.affected_dprs.map((d, j) => {
                    const label = typeof d === 'object' ? d.dpr_id : d
                    const impact = typeof d === 'object' ? d.impact : null
                    return (
                      <span key={j} style={{ padding: '2px 6px', border: '1px solid var(--border)', background: 'var(--bg-elevated)' }} title={impact || ''}>
                        {label}
                      </span>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
