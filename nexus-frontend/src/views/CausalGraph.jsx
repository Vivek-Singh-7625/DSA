import { useContext, useEffect, useRef, useState, useMemo, useCallback } from 'react'
import { DataContext } from '../App'
import * as d3 from 'd3'
import { X, Route, ArrowUpRight, ArrowDownRight, GitBranch } from 'lucide-react'

const EDGE_COLORS = { CONSTRAINS: '#FF8C42', ENABLES: '#00E5CC', REQUIRES: '#3B82F6', ASSUMPTION_OF: '#A855F7', TEMPORAL_PRECEDES: '#484F58', REQUIRED_BY: '#EAB308' }
const TRACE_COLOR = '#FF8C42'
const TRACE_DIM = 0.08

function getNodeColor(node) {
  if (node.decaying) return '#FF3B4F'
  const br = (node.blast_radius || '').toUpperCase()
  if (br === 'CRITICAL') return '#FF8C42'
  if (br === 'HIGH') return '#A855F7'
  return '#00E5CC'
}

function getNodeRadius(node) {
  const br = (node.blast_radius || '').toUpperCase()
  if (br === 'CRITICAL') return 24
  if (br === 'HIGH') return 18
  return 14
}

export default function CausalGraph() {
  const { data } = useContext(DataContext)
  const svgRef = useRef()
  const [filter, setFilter] = useState('ALL')
  const [selected, setSelected] = useState(null)
  const [tracePath, setTracePath] = useState(null)
  const [traceEdges, setTraceEdges] = useState(null)
  const [traceDirection, setTraceDirection] = useState('both') // 'upstream' | 'downstream' | 'both'
  const [traceSource, setTraceSource] = useState(null)

  // Derive the set of decaying DPR IDs from decay alerts
  const decayingIds = useMemo(() => {
    return new Set((data?.decay_alerts || []).filter(a => a.already_decaying).map(a => a.dpr_id))
  }, [data?.decay_alerts])

  // Build nodes from graph API
  const rawNodes = useMemo(() => {
    const apiNodes = data?.graph_data?.nodes || []
    if (apiNodes.length === 0) return []
    return apiNodes.map(n => ({
      id: n.id,
      title: n.label || n.title || n.id,
      component: n.component,
      blast_radius: (n.blast_radius || '').toUpperCase(),
      decaying: decayingIds.has(n.id) || n.decay_risk === 'high',
    }))
  }, [data?.graph_data?.nodes, decayingIds])

  // Build edges from graph API
  const rawEdges = useMemo(() => {
    const apiEdges = data?.graph_data?.edges || []
    if (apiEdges.length === 0) return []
    return apiEdges.map(e => ({
      source: e.from || e.source,
      target: e.to || e.target,
      type: e.type || e.relationship_type,
      explanation: e.explanation || '',
    }))
  }, [data?.graph_data?.edges])

  // Build adjacency lists for path tracing
  const { upstreamAdj, downstreamAdj } = useMemo(() => {
    const up = {}   // node → list of upstream parents (edges pointing TO this node)
    const down = {} // node → list of downstream children (edges pointing FROM this node)
    rawEdges.forEach(e => {
      const s = typeof e.source === 'object' ? e.source.id : e.source
      const t = typeof e.target === 'object' ? e.target.id : e.target
      if (!up[t]) up[t] = []
      up[t].push({ node: s, edge: e })
      if (!down[s]) down[s] = []
      down[s].push({ node: t, edge: e })
    })
    return { upstreamAdj: up, downstreamAdj: down }
  }, [rawEdges])

  // BFS trace in any direction
  const traceFrom = useCallback((nodeId, direction) => {
    const visited = new Set([nodeId])
    const edgeKeys = new Set()
    const queue = [nodeId]

    while (queue.length > 0) {
      const current = queue.shift()
      
      // Upstream: follow edges TO current
      if (direction === 'upstream' || direction === 'both') {
        for (const { node: parent, edge } of (upstreamAdj[current] || [])) {
          const s = typeof edge.source === 'object' ? edge.source.id : edge.source
          const t = typeof edge.target === 'object' ? edge.target.id : edge.target
          edgeKeys.add(`${s}->${t}`)
          if (!visited.has(parent)) {
            visited.add(parent)
            queue.push(parent)
          }
        }
      }
      
      // Downstream: follow edges FROM current
      if (direction === 'downstream' || direction === 'both') {
        for (const { node: child, edge } of (downstreamAdj[current] || [])) {
          const s = typeof edge.source === 'object' ? edge.source.id : edge.source
          const t = typeof edge.target === 'object' ? edge.target.id : edge.target
          edgeKeys.add(`${s}->${t}`)
          if (!visited.has(child)) {
            visited.add(child)
            queue.push(child)
          }
        }
      }
    }

    return { pathNodes: visited, pathEdges: edgeKeys }
  }, [upstreamAdj, downstreamAdj])

  // Handle trace toggle
  const handleTrace = useCallback((nodeId, direction = traceDirection) => {
    if (traceSource === nodeId && tracePath) {
      // Already tracing from this node — clear
      setTracePath(null)
      setTraceEdges(null)
      setTraceSource(null)
    } else {
      const { pathNodes, pathEdges } = traceFrom(nodeId, direction)
      setTracePath(pathNodes)
      setTraceEdges(pathEdges)
      setTraceSource(nodeId)
    }
  }, [traceSource, tracePath, traceFrom, traceDirection])

  // Re-trace when direction changes
  useEffect(() => {
    if (traceSource) {
      const { pathNodes, pathEdges } = traceFrom(traceSource, traceDirection)
      setTracePath(pathNodes)
      setTraceEdges(pathEdges)
    }
  }, [traceDirection, traceSource, traceFrom])

  // Derive unique components for filter buttons from actual data
  const componentList = useMemo(() => {
    const set = new Set(rawNodes.map(n => n.component).filter(Boolean))
    return ['ALL', ...Array.from(set).sort()]
  }, [rawNodes])

  const nodes = filter === 'ALL' ? rawNodes : rawNodes.filter(n => n.component === filter)
  const nodeIds = new Set(nodes.map(n => n.id))
  const edges = rawEdges.filter(e => {
    const sid = typeof e.source === 'object' ? e.source.id : e.source
    const tid = typeof e.target === 'object' ? e.target.id : e.target
    return nodeIds.has(sid) && nodeIds.has(tid)
  })

  // Derive unique edge types for legend from actual data
  const edgeTypes = useMemo(() => {
    const types = {}
    rawEdges.forEach(e => {
      if (e.type && !types[e.type]) {
        types[e.type] = EDGE_COLORS[e.type] || '#484F58'
      }
    })
    return types
  }, [rawEdges])

  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return
    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const w = svgRef.current.clientWidth
    const h = svgRef.current.clientHeight

    const g = svg.append('g')
    svg.call(d3.zoom().scaleExtent([0.3, 4]).on('zoom', e => g.attr('transform', e.transform)))

    // Arrow markers for edge direction
    const defs = svg.append('defs')
    Object.entries(EDGE_COLORS).forEach(([type, color]) => {
      defs.append('marker')
        .attr('id', `arrow-${type}`)
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 20)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', color)
    })

    // Trace arrow
    defs.append('marker')
      .attr('id', 'arrow-trace')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 20).attr('refY', 0)
      .attr('markerWidth', 6).attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path').attr('d', 'M0,-5L10,0L0,5').attr('fill', TRACE_COLOR)

    const sim = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(edges).id(d => d.id).distance(140))
      .force('charge', d3.forceManyBody().strength(-500))
      .force('center', d3.forceCenter(w / 2, h / 2))
      .force('collision', d3.forceCollide().radius(d => getNodeRadius(d) + 12))

    // Edges
    const link = g.append('g').selectAll('line').data(edges).join('line')
      .attr('stroke', d => {
        if (traceEdges) {
          const sid = typeof d.source === 'object' ? d.source.id : d.source
          const tid = typeof d.target === 'object' ? d.target.id : d.target
          return traceEdges.has(`${sid}->${tid}`) ? TRACE_COLOR : (EDGE_COLORS[d.type] || '#484F58')
        }
        return EDGE_COLORS[d.type] || '#484F58'
      })
      .attr('stroke-width', d => {
        if (traceEdges) {
          const sid = typeof d.source === 'object' ? d.source.id : d.source
          const tid = typeof d.target === 'object' ? d.target.id : d.target
          return traceEdges.has(`${sid}->${tid}`) ? 3.5 : 0.8
        }
        return 1.5
      })
      .attr('stroke-opacity', d => {
        if (traceEdges) {
          const sid = typeof d.source === 'object' ? d.source.id : d.source
          const tid = typeof d.target === 'object' ? d.target.id : d.target
          return traceEdges.has(`${sid}->${tid}`) ? 1 : TRACE_DIM
        }
        return 0.5
      })
      .attr('marker-end', d => {
        if (traceEdges) {
          const sid = typeof d.source === 'object' ? d.source.id : d.source
          const tid = typeof d.target === 'object' ? d.target.id : d.target
          if (traceEdges.has(`${sid}->${tid}`)) return 'url(#arrow-trace)'
        }
        return `url(#arrow-${d.type || 'REQUIRES'})`
      })

    // Nodes
    const node = g.append('g').selectAll('g').data(nodes).join('g')
      .call(d3.drag().on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
        .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y })
        .on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null }))
      .style('cursor', 'pointer')
      .on('click', (e, d) => setSelected(d))

    // Glow filters
    const glowFilter = defs.append('filter').attr('id', 'glow')
    glowFilter.append('feGaussianBlur').attr('stdDeviation', 4).attr('result', 'blur')
    glowFilter.append('feMerge').selectAll('feMergeNode').data(['blur', 'SourceGraphic']).join('feMergeNode').attr('in', d => d)

    const traceGlow = defs.append('filter').attr('id', 'traceGlow')
    traceGlow.append('feGaussianBlur').attr('stdDeviation', 6).attr('result', 'blur')
    traceGlow.append('feMerge').selectAll('feMergeNode').data(['blur', 'SourceGraphic']).join('feMergeNode').attr('in', d => d)

    node.append('circle')
      .attr('r', d => getNodeRadius(d))
      .attr('fill', d => {
        if (tracePath) {
          if (d.id === traceSource) return getNodeColor(d) + '88'
          return tracePath.has(d.id) ? getNodeColor(d) + '55' : getNodeColor(d) + '08'
        }
        return getNodeColor(d) + '33'
      })
      .attr('stroke', d => {
        if (tracePath) {
          if (d.id === traceSource) return '#FFFFFF'
          return tracePath.has(d.id) ? getNodeColor(d) : getNodeColor(d) + '20'
        }
        return getNodeColor(d)
      })
      .attr('stroke-width', d => {
        if (d.id === traceSource) return 4
        return tracePath && tracePath.has(d.id) ? 3 : 2
      })
      .attr('filter', d => {
        if (d.id === traceSource) return 'url(#traceGlow)'
        if (tracePath && tracePath.has(d.id)) return 'url(#traceGlow)'
        if (d.decaying) return 'url(#glow)'
        return null
      })

    node.append('text')
      .text(d => d.id)
      .attr('text-anchor', 'middle').attr('dy', 4)
      .attr('fill', d => {
        if (tracePath) return tracePath.has(d.id) ? '#E6EDF3' : '#E6EDF318'
        return '#E6EDF3'
      })
      .attr('font-family', 'JetBrains Mono, monospace')
      .attr('font-size', 10).attr('font-weight', 600)

    // Labels on traced nodes
    if (tracePath) {
      node.filter(d => tracePath.has(d.id)).append('text')
        .text(d => d.title.length > 25 ? d.title.slice(0, 25) + '…' : d.title)
        .attr('text-anchor', 'middle').attr('dy', -getNodeRadius({ blast_radius: 'medium' }) - 6)
        .attr('fill', '#8B949E')
        .attr('font-family', 'JetBrains Mono, monospace')
        .attr('font-size', 8).attr('font-weight', 400)
    }

    sim.on('tick', () => {
      link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
      node.attr('transform', d => `translate(${d.x},${d.y})`)
    })

    return () => sim.stop()
  }, [nodes, edges, tracePath, traceEdges, traceSource])

  const selectedDPR = selected ? { ...selected } : null

  // Empty state
  if (rawNodes.length === 0) {
    return (
      <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', padding: 40, border: '1px solid var(--border)', textAlign: 'center' }}>
        <div style={{ fontSize: 16, marginBottom: 8 }}>No decisions extracted yet</div>
        <div style={{ fontSize: 12 }}>Analysis may still be running</div>
        <button className="filter-btn" style={{ marginTop: 16 }} onClick={() => window.location.reload()}>Refresh</button>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 80px)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
        <div className="graph-filters">
          {componentList.map(f => (
            <button key={f} className={`filter-btn ${filter === f ? 'active' : ''}`} onClick={() => setFilter(f)}>{f}</button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          {tracePath && (
            <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: TRACE_COLOR, marginRight: 8 }}>
                TRACING: {tracePath.size} nodes
              </span>
              <button
                className={`trace-btn ${traceDirection === 'upstream' ? 'active' : ''}`}
                onClick={() => setTraceDirection('upstream')}
                title="Upstream dependencies only"
                style={{ padding: '4px 8px', fontSize: 10 }}
              >
                <ArrowUpRight size={12} /> UP
              </button>
              <button
                className={`trace-btn ${traceDirection === 'both' ? 'active' : ''}`}
                onClick={() => setTraceDirection('both')}
                title="Full dependency tree"
                style={{ padding: '4px 8px', fontSize: 10 }}
              >
                <GitBranch size={12} /> BOTH
              </button>
              <button
                className={`trace-btn ${traceDirection === 'downstream' ? 'active' : ''}`}
                onClick={() => setTraceDirection('downstream')}
                title="Downstream dependents only"
                style={{ padding: '4px 8px', fontSize: 10 }}
              >
                <ArrowDownRight size={12} /> DOWN
              </button>
              <button className="trace-btn" onClick={() => { setTracePath(null); setTraceEdges(null); setTraceSource(null) }}
                style={{ padding: '4px 8px', fontSize: 10, marginLeft: 8 }}>
                <X size={12} /> CLEAR
              </button>
            </div>
          )}
          <div style={{ display: 'flex', gap: 16, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
            {Object.entries(edgeTypes).map(([type, color]) => (
              <span key={type} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 16, height: 2, background: color, display: 'inline-block' }} />
                {type}
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="graph-container" style={{ flex: 1, position: 'relative' }}>
        <svg ref={svgRef} width="100%" height="100%" />

        {/* Quick-trace hint when no node is selected */}
        {!selected && !tracePath && (
          <div style={{
            position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)',
            fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)',
            background: 'var(--surface)', padding: '8px 16px', border: '1px solid var(--border)',
          }}>
            Click any node → select it → Trace Dependencies
          </div>
        )}

        {selectedDPR && (
          <div className="detail-panel fade-in">
            <div className="detail-close" onClick={() => setSelected(null)}><X size={16} /></div>
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 700, color: 'var(--teal)' }}>{selectedDPR.id}</div>
              <div style={{ fontSize: 15, fontWeight: 600, marginTop: 4 }}>{selectedDPR.title}</div>
              <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                <span className="badge badge-stable">{selectedDPR.component}</span>
                <span className={`badge ${selectedDPR.decaying ? 'badge-decaying' : 'badge-monitoring'}`}>{selectedDPR.decaying ? 'DECAYING' : 'STABLE'}</span>
              </div>
            </div>
            <div className="detail-section">
              <div className="detail-section-title">Blast Radius</div>
              <span className={`badge ${selectedDPR.blast_radius === 'CRITICAL' ? 'badge-critical' : 'badge-stable'}`}>{selectedDPR.blast_radius}</span>
            </div>

            {/* TRACE PATH CONTROLS */}
            <div className="detail-section">
              <div className="detail-section-title">Path Trace</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <button
                  className={`trace-btn ${traceSource === selectedDPR.id && traceDirection === 'upstream' ? 'active' : ''}`}
                  onClick={() => { setTraceDirection('upstream'); handleTrace(selectedDPR.id, 'upstream') }}
                  style={{ fontSize: 11, padding: '6px 10px' }}
                >
                  <ArrowUpRight size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                  Upstream
                </button>
                <button
                  className={`trace-btn ${traceSource === selectedDPR.id && traceDirection === 'both' ? 'active' : ''}`}
                  onClick={() => { setTraceDirection('both'); handleTrace(selectedDPR.id, 'both') }}
                  style={{ fontSize: 11, padding: '6px 10px' }}
                >
                  <GitBranch size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                  Full Tree
                </button>
                <button
                  className={`trace-btn ${traceSource === selectedDPR.id && traceDirection === 'downstream' ? 'active' : ''}`}
                  onClick={() => { setTraceDirection('downstream'); handleTrace(selectedDPR.id, 'downstream') }}
                  style={{ fontSize: 11, padding: '6px 10px' }}
                >
                  <ArrowDownRight size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                  Downstream
                </button>
              </div>
              {traceSource === selectedDPR.id && tracePath && (
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: TRACE_COLOR, marginTop: 8 }}>
                  {traceDirection === 'upstream' ? '↑' : traceDirection === 'downstream' ? '↓' : '↕'} {tracePath.size} nodes in {traceDirection} chain
                </div>
              )}
            </div>

            <div className="detail-section">
              <div className="detail-section-title">Connections ({rawEdges.filter(e => {
                const s = typeof e.source === 'object' ? e.source.id : e.source
                const t = typeof e.target === 'object' ? e.target.id : e.target
                return s === selectedDPR.id || t === selectedDPR.id
              }).length})</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', maxHeight: 200, overflowY: 'auto' }}>
                {rawEdges.filter(e => {
                  const s = typeof e.source === 'object' ? e.source.id : e.source
                  const t = typeof e.target === 'object' ? e.target.id : e.target
                  return s === selectedDPR.id || t === selectedDPR.id
                }).map((e, i) => {
                  const s = typeof e.source === 'object' ? e.source.id : e.source
                  const t = typeof e.target === 'object' ? e.target.id : e.target
                  const other = s === selectedDPR.id ? t : s
                  const dir = s === selectedDPR.id ? '→' : '←'
                  return (
                    <div key={i} style={{ padding: '4px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer' }}
                      onClick={() => {
                        const targetNode = rawNodes.find(n => n.id === other)
                        if (targetNode) setSelected(targetNode)
                      }}>
                      <span style={{ color: EDGE_COLORS[e.type] || '#484F58' }}>{dir}</span> <span style={{ color: '#E6EDF3' }}>{other}</span> <span style={{ color: 'var(--text-muted)' }}>({e.type})</span>
                      {e.explanation && <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>{e.explanation}</div>}
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
