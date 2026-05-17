"""
Nexus Layer 6 - FastAPI Backend
Serves the intelligence pipeline data to the React frontend.
Endpoints: DPRs, graph, decay, counterfactuals, knowledge, risk report, query, analyze.
"""

import os, sys, json, asyncio, threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from collections import deque

if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

SCRIPT_DIR = Path(__file__).resolve().parent
NEXUS_DATA = SCRIPT_DIR / "nexus_data.json"
PDF_PATH = SCRIPT_DIR / "nexus_risk_report.pdf"

# ── Analysis State (in-memory) ─────────────────────────────
_analysis_state = {
    "running": False,
    "repo_url": None,
    "window": None,
    "stage": None,
    "progress": 0,
    "error": None,
    "started_at": None,
    "completed_at": None,
}
_analysis_lock = threading.Lock()


def _set_analysis_state(**kwargs):
    with _analysis_lock:
        _analysis_state.update(kwargs)


# ── App ────────────────────────────────────────────────────
app = FastAPI(
    title="Nexus Causal Intelligence API",
    description="Backend for the Nexus Causal Temporal Graph intelligence platform",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_data():
    if not NEXUS_DATA.exists():
        raise HTTPException(404, "nexus_data.json not found. Run build_nexus_data.py first.")
    with open(NEXUS_DATA, 'r', encoding='utf-8') as f:
        return json.load(f)


# ── Health ─────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    with _analysis_lock:
        analysis_running = _analysis_state["running"]
        analysis_stage = _analysis_state["stage"]
        analysis_progress = _analysis_state["progress"]
        analysis_error = _analysis_state["error"]
    return {
        "status": "ok",
        "nexus_data_exists": NEXUS_DATA.exists(),
        "pdf_exists": PDF_PATH.exists(),
        "analysis_running": analysis_running,
        "analysis_stage": analysis_stage,
        "analysis_progress": analysis_progress,
        "analysis_error": analysis_error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Full Data Dump ─────────────────────────────────────────
@app.get("/api/data")
async def get_all_data():
    """Return the complete nexus_data.json for the frontend."""
    return load_data()


# ── Meta ───────────────────────────────────────────────────
@app.get("/api/meta")
async def get_meta():
    data = load_data()
    return data.get("meta", {})


# ── DPRs ───────────────────────────────────────────────────
@app.get("/api/dprs")
async def get_dprs(
    component: Optional[str] = None,
    blast_radius: Optional[str] = None,
    decay_risk: Optional[str] = None,
):
    data = load_data()
    dprs = data.get("dprs", [])
    if component:
        dprs = [d for d in dprs if d.get("component", "").lower() == component.lower()]
    if blast_radius:
        dprs = [d for d in dprs if d.get("blast_radius", "").lower() == blast_radius.lower()]
    if decay_risk:
        dprs = [d for d in dprs if d.get("decay_risk", "").lower() == decay_risk.lower()]
    return {"count": len(dprs), "dprs": dprs}


@app.get("/api/dprs/{dpr_id}")
async def get_dpr(dpr_id: str):
    data = load_data()
    dpr = next((d for d in data.get("dprs", []) if d["id"] == dpr_id), None)
    if not dpr:
        raise HTTPException(404, f"DPR {dpr_id} not found")
    return dpr


# ── CTG Graph ──────────────────────────────────────────────
@app.get("/api/graph")
async def get_graph():
    """Return nodes and edges for the Causal Temporal Graph visualization."""
    data = load_data()
    dprs = data.get("dprs", [])
    edges = data.get("ctg_edges", [])

    nodes = [{
        "id": d["id"],
        "label": d["title"],
        "component": d["component"],
        "blast_radius": d.get("blast_radius", "medium"),
        "decay_risk": d.get("decay_risk", "low"),
        "within_window": d.get("within_window", False),
    } for d in dprs]

    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


# ── Graph Path Tracing ────────────────────────────────────
@app.get("/api/graph/trace/{dpr_id}")
async def trace_graph_path(
    dpr_id: str,
    direction: str = Query("upstream", regex="^(upstream|downstream|both)$"),
    max_depth: int = Query(10, ge=1, le=50),
):
    """BFS path tracing from a given DPR node.
    
    - upstream: find all nodes that this DPR depends on (ancestors)
    - downstream: find all nodes that depend on this DPR (descendants)
    - both: full dependency tree
    """
    data = load_data()
    edges = data.get("ctg_edges", [])
    dprs = data.get("dprs", [])
    
    # Validate DPR exists
    dpr_ids = {d["id"] for d in dprs}
    if dpr_id not in dpr_ids:
        raise HTTPException(404, f"DPR {dpr_id} not found")
    
    # Build adjacency lists
    # upstream: edges where `to` == current node → follow `from`
    # downstream: edges where `from` == current node → follow `to`
    upstream_adj = {}  # node → list of (neighbor, edge)
    downstream_adj = {}
    for e in edges:
        fr = e.get("from", "")
        to = e.get("to", "")
        if to not in upstream_adj:
            upstream_adj[to] = []
        upstream_adj[to].append({"node": fr, "edge": e})
        if fr not in downstream_adj:
            downstream_adj[fr] = []
        downstream_adj[fr].append({"node": to, "edge": e})
    
    traced_nodes = set()
    traced_edges = []
    
    def bfs(start, adj_map):
        visited = set()
        queue = deque([(start, 0)])
        visited.add(start)
        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for neighbor_info in adj_map.get(current, []):
                neighbor = neighbor_info["node"]
                edge = neighbor_info["edge"]
                traced_edges.append(edge)
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))
        return visited
    
    if direction in ("upstream", "both"):
        traced_nodes |= bfs(dpr_id, upstream_adj)
    if direction in ("downstream", "both"):
        traced_nodes |= bfs(dpr_id, downstream_adj)
    
    traced_nodes.add(dpr_id)  # Always include the source
    
    # Deduplicate edges
    seen_edges = set()
    unique_edges = []
    for e in traced_edges:
        key = (e.get("from", ""), e.get("to", ""), e.get("type", ""))
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(e)
    
    # Return full node data for traced nodes
    traced_dpr_data = [d for d in dprs if d["id"] in traced_nodes]
    
    return {
        "source": dpr_id,
        "direction": direction,
        "max_depth": max_depth,
        "traced_node_count": len(traced_nodes),
        "traced_edge_count": len(unique_edges),
        "traced_nodes": sorted(list(traced_nodes)),
        "traced_edges": unique_edges,
        "traced_dprs": traced_dpr_data,
    }


# ── Decay Alerts ───────────────────────────────────────────
@app.get("/api/decay")
@app.get("/api/decay-alerts")
async def get_decay_alerts():
    data = load_data()
    alerts = data.get("decay_alerts", [])
    runs = data.get("monitoring_runs", [])
    return {
        "alerts": alerts,
        "total_alerts": len(alerts),
        "active_decay": sum(1 for a in alerts if a.get("already_decaying")),
        "monitoring_runs": runs[-5:] if runs else [],
    }


@app.get("/api/decay/live")
async def get_live_decay():
    """Get live monitoring results from DPR-level decay_alert fields."""
    data = load_data()
    results = []
    for d in data.get("dprs", []):
        alert = d.get("decay_alert")
        if alert and alert.get("live_confidence") is not None:
            results.append({
                "dpr_id": d["id"],
                "title": d["title"],
                "component": d["component"],
                "confidence": alert.get("live_confidence"),
                "still_holds": alert.get("live_still_holds"),
                "reasoning": alert.get("live_reasoning", ""),
                "last_evaluated": alert.get("last_evaluated", ""),
            })
    return {"count": len(results), "live_evaluations": results}


# ── Counterfactuals ────────────────────────────────────────
@app.get("/api/counterfactuals")
async def get_counterfactuals():
    data = load_data()
    traces = data.get("counterfactual_traces", [])
    return {"count": len(traces), "traces": traces}


@app.get("/api/counterfactuals/{cf_id}")
async def get_counterfactual(cf_id: str):
    data = load_data()
    trace = next((t for t in data.get("counterfactual_traces", []) if t["id"] == cf_id), None)
    if not trace:
        raise HTTPException(404, f"Counterfactual {cf_id} not found")
    return trace


# ── Knowledge Concentration ────────────────────────────────
@app.get("/api/knowledge")
async def get_knowledge_concentration():
    data = load_data()
    kc = data.get("knowledge_concentration", {})
    return {
        "org_risk_score": data.get("org_risk_score", 0),
        **kc,
    }


@app.get("/api/knowledge/humans")
async def get_human_profiles():
    data = load_data()
    kc = data.get("knowledge_concentration", {})
    return kc.get("human_profiles", [])


@app.get("/api/knowledge/components")
async def get_component_profiles():
    data = load_data()
    kc = data.get("knowledge_concentration", {})
    return kc.get("component_profiles", [])


# ── Risk Report ────────────────────────────────────────────
@app.get("/api/report/download")
async def download_report():
    if not PDF_PATH.exists():
        raise HTTPException(404, "Risk report not generated. Run generate_risk_report.py first.")
    return FileResponse(
        path=str(PDF_PATH),
        media_type="application/pdf",
        filename="nexus_risk_report.pdf"
    )


@app.post("/api/report/generate")
async def trigger_report(background_tasks: BackgroundTasks):
    """Trigger PDF report generation in background."""
    def generate():
        try:
            from generate_risk_report import generate_report
            generate_report()
        except Exception as e:
            print(f"[!] Report generation failed: {e}")
    background_tasks.add_task(generate)
    return {"status": "generating", "message": "PDF report generation started"}


# ── Query Engine ───────────────────────────────────────────
class QueryRequest(BaseModel):
    question: str
    use_gemini: bool = True


@app.post("/api/query")
async def query_engine(req: QueryRequest):
    """Natural language query against the intelligence pipeline."""
    data = load_data()

    # Simple keyword search through DPRs
    results = []
    q = req.question.lower()
    for d in data.get("dprs", []):
        score = 0
        searchable = json.dumps(d, default=str).lower()
        for word in q.split():
            if len(word) > 2 and word in searchable:
                score += 1
        if score > 0:
            results.append({"dpr": d, "relevance_score": score})

    results.sort(key=lambda x: x["relevance_score"], reverse=True)

    # If Gemini requested, try to get richer answer
    gemini_answer = None
    if req.use_gemini:
        try:
            from google import genai
            key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if key:
                client = genai.Client(api_key=key)
                context = json.dumps(results[:3], default=str)[:4000]
                config = genai.types.GenerateContentConfig(temperature=0.3)
                resp = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=f"Based on this context:\n{context}\n\nAnswer: {req.question}",
                    config=config
                )
                gemini_answer = resp.text
        except Exception as e:
            gemini_answer = f"Gemini unavailable: {str(e)[:100]}"

    return {
        "question": req.question,
        "results": results[:5],
        "gemini_answer": gemini_answer,
        "total_matches": len(results),
    }


# ── Universal Repo Analysis ───────────────────────────────
class AnalyzeRequest(BaseModel):
    repo_url: str
    window: str = "1year"


@app.post("/api/analyze")
async def analyze_repository(req: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Trigger full analysis of any GitHub repository."""
    with _analysis_lock:
        if _analysis_state["running"]:
            return JSONResponse(
                status_code=409,
                content={
                    "status": "busy",
                    "message": f"Analysis already running for {_analysis_state['repo_url']}",
                    "stage": _analysis_state["stage"],
                    "progress": _analysis_state["progress"],
                }
            )
    
    # Validate URL
    url = req.repo_url.strip().rstrip("/")
    if not url.startswith("https://github.com/"):
        if url.startswith("github.com/"):
            url = f"https://{url}"
        elif "/" in url and not url.startswith("http"):
            url = f"https://github.com/{url}"
        else:
            raise HTTPException(400, "Invalid GitHub repository URL")
    
    # Validate window
    valid_windows = {"1year", "2years", "3years", "5years", "all"}
    window = req.window.replace(" ", "").replace("-", "")
    if window not in valid_windows:
        window = "1year"
    
    # Start background analysis
    _set_analysis_state(
        running=True,
        repo_url=url,
        window=window,
        stage="cloning",
        progress=5,
        error=None,
        started_at=datetime.now(timezone.utc).isoformat(),
        completed_at=None,
    )
    
    def run_analysis():
        try:
            # Import the analyzer
            sys.path.insert(0, str(SCRIPT_DIR))
            from repo_analyzer import clone_repo, extract_dprs, build_nexus_data_from_extraction, get_gemini_client
            
            # Stage 1: Clone
            _set_analysis_state(stage="cloning", progress=10)
            repo_path = clone_repo(url)
            
            # Stage 2: Indexing
            _set_analysis_state(stage="indexing", progress=20)
            
            # Stage 3: Extraction
            _set_analysis_state(stage="extracting", progress=30)
            client = get_gemini_client()
            if not client:
                raise RuntimeError("GEMINI_API_KEY not set. Cannot analyze without AI.")
            
            l1_data = extract_dprs(client, url, repo_path, window)
            
            # Stage 4: Graph Building
            _set_analysis_state(stage="building_graph", progress=60)
            
            # Stage 5: Building nexus_data
            _set_analysis_state(stage="building_data", progress=70)
            output_path = NEXUS_DATA
            build_nexus_data_from_extraction(l1_data, output_path)
            
            # Stage 6: Done
            _set_analysis_state(stage="finalizing", progress=95)
            
            import time
            time.sleep(1)
            
            _set_analysis_state(
                running=False,
                stage="complete",
                progress=100,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            print(f"[+] Analysis complete for {url}")
            
        except Exception as e:
            print(f"[!] Analysis failed: {e}")
            import traceback
            traceback.print_exc()
            _set_analysis_state(
                running=False,
                stage="error",
                progress=0,
                error=str(e)[:500],
            )
    
    background_tasks.add_task(run_analysis)
    
    return {
        "status": "started",
        "message": f"Analysis started for {url} (window: {window})",
        "repo_url": url,
        "window": window,
    }


@app.get("/api/analyze/status")
async def analyze_status():
    """Get the current analysis pipeline status."""
    with _analysis_lock:
        return dict(_analysis_state)


# ── Pipeline Triggers ──────────────────────────────────────
@app.post("/api/pipeline/decay-monitor")
async def trigger_decay_monitor(background_tasks: BackgroundTasks):
    def run():
        try:
            from decay_monitor import run_decay_monitor
            run_decay_monitor()
        except Exception as e:
            print(f"[!] Decay monitor failed: {e}")
    background_tasks.add_task(run)
    return {"status": "running", "message": "Decay monitor started"}


@app.post("/api/pipeline/counterfactual")
async def trigger_counterfactual(background_tasks: BackgroundTasks):
    def run():
        try:
            from counterfactual_engine import run_counterfactual_engine
            run_counterfactual_engine()
        except Exception as e:
            print(f"[!] Counterfactual engine failed: {e}")
    background_tasks.add_task(run)
    return {"status": "running", "message": "Counterfactual engine started"}


@app.post("/api/pipeline/knowledge")
async def trigger_knowledge(background_tasks: BackgroundTasks):
    def run():
        try:
            from knowledge_concentration import run_knowledge_concentration
            run_knowledge_concentration()
        except Exception as e:
            print(f"[!] Knowledge analysis failed: {e}")
    background_tasks.add_task(run)
    return {"status": "running", "message": "Knowledge analysis started"}


# ── Dashboard Summary ──────────────────────────────────────
@app.get("/api/dashboard")
async def get_dashboard():
    """All-in-one endpoint for the React dashboard."""
    data = load_data()
    dprs = data.get("dprs", [])
    alerts = data.get("decay_alerts", [])
    kc = data.get("knowledge_concentration", {})
    traces = data.get("counterfactual_traces", [])

    return {
        "meta": data.get("meta", {}),
        "org_risk_score": data.get("org_risk_score", 0),
        "dpr_summary": {
            "total": len(dprs),
            "critical_blast": sum(1 for d in dprs if d.get("blast_radius") == "critical"),
            "high_decay": sum(1 for d in dprs if d.get("decay_risk") == "high"),
            "components": list(set(d.get("component", "") for d in dprs)),
        },
        "decay_summary": {
            "total_alerts": len(alerts),
            "active_decay": sum(1 for a in alerts if a.get("already_decaying")),
            "latest_run": data.get("monitoring_runs", [{}])[-1] if data.get("monitoring_runs") else None,
        },
        "knowledge_summary": {
            "top_humans": kc.get("top_spof_humans", []),
            "top_components": kc.get("top_spof_components", []),
        },
        "counterfactual_summary": {
            "total_traces": len(traces),
            "verdicts": {t.get("result", {}).get("verdict", "unknown"): 0 for t in traces},
        },
        "pdf_available": PDF_PATH.exists(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
