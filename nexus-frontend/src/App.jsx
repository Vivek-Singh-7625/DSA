import { useState, useEffect, useCallback, createContext } from 'react'
import { Routes, Route, NavLink, Navigate, useSearchParams } from 'react-router-dom'
import { LayoutDashboard, GitBranch, AlertTriangle, Users, FlaskConical, Clock, Bell } from 'lucide-react'
import Overview from './views/Overview'
import CausalGraph from './views/CausalGraph'
import DecayAlerts from './views/DecayAlerts'
import KnowledgeMap from './views/KnowledgeMap'
import CounterfactualLab from './views/CounterfactualLab'

export const DataContext = createContext(null)

const API = 'http://localhost:8000'
const DEFAULT_REPO = 'https://github.com/postgres/postgres'
const DEFAULT_WINDOW = '1year'
const WINDOWS = [
  { value: '1year', label: '1 year' },
  { value: '2years', label: '2 years' },
  { value: '3years', label: '3 years' },
  { value: '5years', label: '5 years' },
  { value: 'all', label: 'All time' },
]

const PROGRESS_STAGES = [
  { at: 0, text: 'Cloning repository' },
  { at: 30, text: 'Indexing files and git history' },
  { at: 60, text: 'Extracting architectural decisions' },
  { at: 120, text: 'Building causal graph' },
  { at: 180, text: 'Running assumption decay analysis' },
  { at: 240, text: 'Computing knowledge concentration' },
  { at: 300, text: 'Generating counterfactual traces' },
  { at: 360, text: 'Finalising risk report' },
]

const NAV = [
  { path: '/', icon: LayoutDashboard, label: 'Overview' },
  { path: '/graph', icon: GitBranch, label: 'Graph' },
  { path: '/alerts', icon: AlertTriangle, label: 'Alerts' },
  { path: '/knowledge', icon: Users, label: 'Knowledge' },
  { path: '/lab', icon: FlaskConical, label: 'Lab' },
]

function getRepoHistory() {
  try { return JSON.parse(localStorage.getItem('nexus_repo_history') || '[]') } catch { return [] }
}
function pushRepoHistory(url) {
  const list = getRepoHistory().filter(r => r !== url)
  list.unshift(url)
  localStorage.setItem('nexus_repo_history', JSON.stringify(list.slice(0, 5)))
}

function isValidRepoUrl(url) {
  return url && url.includes('github.com/') && url.split('github.com/')[1]?.includes('/')
}

function formatRepoUrl(input) {
  let u = input.trim()
  if (!u.startsWith('http')) u = 'https://' + u
  return u
}

function repoDisplay(url) {
  if (!url) return '—'
  const parts = url.replace('https://github.com/', '').replace('http://github.com/', '').split('/')
  return parts.length >= 2 ? `${parts[0]} / ${parts[1]}` : url
}

export default function App() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Repo input state
  const [repoInput, setRepoInput] = useState(searchParams.get('repo') || DEFAULT_REPO)
  const [windowVal, setWindowVal] = useState(searchParams.get('window') || DEFAULT_WINDOW)
  const [inputError, setInputError] = useState('')
  const [showHistory, setShowHistory] = useState(false)

  // Analysis overlay state
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisRepo, setAnalysisRepo] = useState('')
  const [analysisWindow, setAnalysisWindow] = useState('')
  const [analysisStart, setAnalysisStart] = useState(0)
  const [stageIdx, setStageIdx] = useState(0)
  const [notifyEnabled, setNotifyEnabled] = useState(false)

  // Current loaded repo
  const [currentRepo, setCurrentRepo] = useState('')

  // Fetch all data from API
  const fetchAllData = useCallback(async () => {
    setLoading(true)
    setError(null)
    setData(null) // Clear previous repo data completely
    try {
      const [dash, graph, decay, knowledge, cf] = await Promise.all([
        fetch(`${API}/api/dashboard`).then(r => r.ok ? r.json() : null).catch(() => null),
        fetch(`${API}/api/graph`).then(r => r.ok ? r.json() : null).catch(() => null),
        fetch(`${API}/api/decay`).then(r => r.ok ? r.json() : null).catch(() => null),
        fetch(`${API}/api/knowledge`).then(r => r.ok ? r.json() : null).catch(() => null),
        fetch(`${API}/api/counterfactuals`).then(r => r.ok ? r.json() : null).catch(() => null),
      ])
      if (!dash && !graph && !decay && !knowledge && !cf) {
        setError('All API endpoints unreachable')
      } else {
        const newData = {
          dashboard: dash,
          graph_data: graph,
          decay_data: decay,
          decay_alerts: decay?.alerts || [],
          knowledge: knowledge,
          counterfactuals: cf?.traces || cf,
        }
        setData(newData)
        const repo = dash?.meta?.repository || ''
        setCurrentRepo(repo)
        if (repo) {
          setRepoInput(repo)
          pushRepoHistory(repo)
          document.title = `Nexus — ${repoDisplay(repo)}`
        }
      }
    } catch (e) {
      console.error('API fetch failed', e)
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    fetchAllData()
  }, [fetchAllData])

  // Update URL params when repo/window changes
  useEffect(() => {
    if (currentRepo) {
      const newParams = new URLSearchParams()
      newParams.set('repo', currentRepo)
      newParams.set('window', windowVal)
      setSearchParams(newParams, { replace: true })
    }
  }, [currentRepo, windowVal, setSearchParams])

  // Analysis overlay progress timer
  useEffect(() => {
    if (!analyzing) return
    const interval = setInterval(() => {
      const elapsed = (Date.now() - analysisStart) / 1000
      let idx = 0
      for (let i = PROGRESS_STAGES.length - 1; i >= 0; i--) {
        if (elapsed >= PROGRESS_STAGES[i].at) { idx = i; break }
      }
      setStageIdx(idx)
    }, 1000)
    return () => clearInterval(interval)
  }, [analyzing, analysisStart])

  // Poll during analysis using /api/analyze/status
  useEffect(() => {
    if (!analyzing) return
    const poll = setInterval(async () => {
      try {
        const status = await fetch(`${API}/api/analyze/status`).then(r => r.json())
        if (status.stage === 'complete') {
          setAnalyzing(false)
          await fetchAllData()
          if (notifyEnabled && 'Notification' in window && Notification.permission === 'granted') {
            new Notification('Nexus Analysis Complete', {
              body: `Analysis complete for ${repoDisplay(analysisRepo)}`,
              icon: '/vite.svg',
            })
          }
        } else if (status.stage === 'error') {
          setAnalyzing(false)
          setInputError(status.error || 'Analysis failed')
        } else if (status.progress) {
          // Map backend stage to frontend stage index
          const stageMap = { cloning: 0, indexing: 1, extracting: 2, building_graph: 3, building_data: 4, finalizing: 5 }
          const idx = stageMap[status.stage] ?? stageIdx
          setStageIdx(Math.min(idx, PROGRESS_STAGES.length - 1))
        }
      } catch { /* polling silently */ }
    }, 3000)
    return () => clearInterval(poll)
  }, [analyzing, analysisRepo, notifyEnabled, fetchAllData])

  // Handle ANALYZE button
  const handleAnalyze = async () => {
    setInputError('')
    const url = formatRepoUrl(repoInput)

    if (!isValidRepoUrl(url)) {
      setInputError('Enter a valid GitHub repository URL')
      return
    }

    // If it's the same repo that's already loaded, just refresh
    if (url === currentRepo) {
      await fetchAllData()
      return
    }

    try {
      const resp = await fetch(`${API}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_url: url, window: windowVal }),
      })

      if (resp.ok) {
        const result = await resp.json()
        if (result.status === 'complete') {
          await fetchAllData()
        } else {
          // Queued — show overlay
          setAnalyzing(true)
          setAnalysisRepo(url)
          setAnalysisWindow(windowVal)
          setAnalysisStart(Date.now())
          setStageIdx(0)
        }
      } else if (resp.status === 409) {
        // Analysis already running
        setAnalyzing(true)
        setAnalysisRepo(url)
        setAnalysisWindow(windowVal)
        setAnalysisStart(Date.now())
        setStageIdx(0)
      } else {
        const err = await resp.json().catch(() => ({}))
        setInputError(err.detail || `Analysis failed (${resp.status})`)
      }
    } catch (e) {
      // Network error — still try to show data for current repo
      if (url === currentRepo || url.includes('postgres/postgres')) {
        await fetchAllData()
      } else {
        setInputError(`Connection error: ${e.message}`)
      }
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleAnalyze()
  }

  const handleHistorySelect = (url) => {
    setRepoInput(url)
    setShowHistory(false)
    setInputError('')
  }

  const handleNotify = async () => {
    if ('Notification' in window) {
      const perm = await Notification.requestPermission()
      setNotifyEnabled(perm === 'granted')
    }
  }

  const dismissOverlay = () => {
    setAnalyzing(false)
  }

  // Progress bar percentage
  const elapsed = analyzing ? (Date.now() - analysisStart) / 1000 : 0
  const progressPct = Math.min((elapsed / 420) * 100, 95)

  const repoName = currentRepo
  const displayName = repoDisplay(repoName)

  return (
    <DataContext.Provider value={{ data, loading, error, fetchAllData, currentRepo, API }}>
      <div className="app-shell">
        <nav className="sidebar">
          <div className="sidebar-logo">NEXUS</div>
          {NAV.map(n => (
            <NavLink key={n.path} to={{ pathname: n.path, search: window.location.search }} end={n.path === '/'} className={({ isActive }) => `sidebar-icon ${isActive ? 'active' : ''}`} title={n.label}>
              <n.icon size={18} />
            </NavLink>
          ))}
        </nav>
        <div className="main-area">
          <header className="top-bar">
            <span className="top-bar-title">NEXUS</span>
            <div className="repo-bar">
              <input
                className={`repo-input ${inputError ? 'repo-input-error' : ''}`}
                value={repoInput}
                onChange={e => { setRepoInput(e.target.value); setInputError('') }}
                onKeyDown={handleKeyDown}
                onFocus={() => setInputError('')}
                placeholder="github.com/owner/repo"
                spellCheck={false}
              />
              <div className="repo-history-wrap">
                <button className="repo-history-btn" onClick={() => setShowHistory(!showHistory)} title="Recent repos">
                  <Clock size={14} />
                </button>
                {showHistory && (
                  <div className="repo-history-dropdown">
                    <div className="repo-history-title">Recently Analysed</div>
                    {getRepoHistory().length === 0 && (
                      <div className="repo-history-empty">No history</div>
                    )}
                    {getRepoHistory().map((url, i) => (
                      <button key={i} className="repo-history-item" onClick={() => handleHistorySelect(url)}>
                        {url.replace('https://', '')}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <select className="repo-window" value={windowVal} onChange={e => setWindowVal(e.target.value)}>
                {WINDOWS.map(w => <option key={w.value} value={w.value}>{w.label}</option>)}
              </select>
              <button className="repo-analyze-btn" onClick={handleAnalyze} disabled={loading}>
                ANALYZE →
              </button>
            </div>
            {inputError && <span className="repo-error">{inputError}</span>}
            <div className="top-bar-status">
              <span className="status-dot" style={{ background: loading ? 'var(--orange)' : data ? 'var(--green)' : 'var(--red)' }} />
              {loading ? 'LOADING' : data ? 'CONNECTED' : 'OFFLINE'}
            </div>
          </header>
          <div className="content">
            {analyzing && (
              <div className="analysis-overlay fade-in">
                <div className="analysis-box">
                  <div className="analysis-title">NEXUS ANALYSIS IN PROGRESS</div>
                  <div className="analysis-meta">
                    <span>Repository: <span style={{ color: 'var(--teal)' }}>{analysisRepo.replace('https://', '')}</span></span>
                    <span>Window: <span style={{ color: 'var(--text-primary)' }}>{WINDOWS.find(w => w.value === analysisWindow)?.label || analysisWindow}</span></span>
                  </div>
                  <div className="analysis-progress-wrap">
                    <div className="analysis-progress-bar">
                      <div className="analysis-progress-fill" style={{ width: `${progressPct}%` }} />
                    </div>
                    <div className="analysis-stage">{PROGRESS_STAGES[stageIdx]?.text}</div>
                  </div>
                  <div className="analysis-note">
                    This takes 5–20 minutes for large repos. You can leave this tab open.
                  </div>
                  <div className="analysis-actions">
                    <button className="analysis-notify-btn" onClick={handleNotify} disabled={notifyEnabled}>
                      <Bell size={14} /> {notifyEnabled ? 'Notifications enabled' : 'Notify me'}
                    </button>
                    <button className="analysis-dismiss-btn" onClick={dismissOverlay}>
                      Continue browsing
                    </button>
                  </div>
                </div>
              </div>
            )}
            {loading && !analyzing ? (
              <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', padding: 40 }}>
                Initializing Nexus Intelligence Engine...
              </div>
            ) : (
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/graph" element={<CausalGraph />} />
                <Route path="/alerts" element={<DecayAlerts />} />
                <Route path="/knowledge" element={<KnowledgeMap />} />
                <Route path="/lab" element={<CounterfactualLab />} />
                <Route path="*" element={<Navigate to="/" />} />
              </Routes>
            )}
          </div>
        </div>
      </div>
    </DataContext.Provider>
  )
}
