"""
Nexus - Universal Repository Analyzer
Clones any GitHub repository, analyzes git history + codebase,
extracts DPRs using WatsonX/Gemini via unified LLM provider,
builds the full Causal Temporal Graph data.
Supports chunked/small-packet LLM requests and streamed clone progress.
"""

import os, sys, json, subprocess, re, time, shutil, hashlib, threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

# ── Config ─────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
CLONE_DIR = SCRIPT_DIR / "_repos"

ANALYSIS_WINDOWS = {
    "1year": 365, "2years": 730, "3years": 1095,
    "5years": 1825, "all": 36500,
}


# ── Git Operations ─────────────────────────────────────────
def clone_repo(repo_url: str, progress_callback: Callable = None) -> Path:
    """Clone a GitHub repo with streamed progress. Fixes stuck-at-30%."""
    CLONE_DIR.mkdir(exist_ok=True)

    repo_hash = hashlib.md5(repo_url.encode()).hexdigest()[:10]
    parts = repo_url.replace("https://github.com/", "").replace("http://github.com/", "").split("/")
    repo_name = f"{parts[0]}_{parts[1]}_{repo_hash}" if len(parts) >= 2 else repo_hash
    repo_path = CLONE_DIR / repo_name

    if repo_path.exists():
        print(f"[*] Repo exists at {repo_path}, pulling latest...")
        if progress_callback:
            progress_callback(stage="pulling", progress=12)
        try:
            subprocess.run(
                ["git", "pull", "--ff-only"], cwd=str(repo_path),
                capture_output=True, text=True, timeout=120,
                encoding='utf-8', errors='replace')
        except: pass
        if progress_callback:
            progress_callback(stage="cloned", progress=18)
        return repo_path

    print(f"[*] Cloning {repo_url} → {repo_path}...")
    if progress_callback:
        progress_callback(stage="cloning", progress=8)

    # Use --progress flag to stream clone progress from stderr
    proc = subprocess.Popen(
        ["git", "clone", "--depth", "500", "--single-branch", "--progress",
         repo_url, str(repo_path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding='utf-8', errors='replace')

    # Stream stderr for progress updates (git writes progress to stderr)
    def _stream_progress():
        for line in proc.stderr:
            line = line.strip()
            if not line:
                continue
            # Parse percentage from git clone output
            pct_match = re.search(r'(\d+)%', line)
            if pct_match and progress_callback:
                git_pct = int(pct_match.group(1))
                # Map git 0-100% to our 8-18% range
                mapped = 8 + int(git_pct * 0.10)
                progress_callback(stage="cloning", progress=mapped)
            if line:
                print(f"  [git] {line}")

    t = threading.Thread(target=_stream_progress, daemon=True)
    t.start()

    try:
        proc.wait(timeout=600)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError("Git clone timed out after 600 seconds")

    t.join(timeout=5)

    if proc.returncode != 0:
        raise RuntimeError(f"Git clone failed (exit {proc.returncode})")

    if progress_callback:
        progress_callback(stage="cloned", progress=18)

    return repo_path


def get_git_log(repo_path: Path, days: int, max_commits: int = 2000) -> str:
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    result = subprocess.run(
        ["git", "log", f"--since={since}", f"--max-count={max_commits}",
         "--pretty=format:%H|%an|%ad|%s", "--date=short", "--no-merges"],
        cwd=str(repo_path), capture_output=True, text=True, timeout=120,
        encoding='utf-8', errors='replace')
    return result.stdout


def get_repo_structure(repo_path: Path, max_files: int = 200) -> str:
    files = []
    for root, dirs, filenames in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in
                   ('node_modules', '__pycache__', 'vendor', 'dist', 'build', '.git')]
        for f in filenames:
            rel = os.path.relpath(os.path.join(root, f), repo_path)
            files.append(rel)
            if len(files) >= max_files: break
        if len(files) >= max_files: break
    return "\n".join(files)


def get_active_contributors(repo_path: Path, days: int) -> str:
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    result = subprocess.run(
        ["git", "shortlog", "-sn", "--no-merges", f"--since={since}"],
        cwd=str(repo_path), capture_output=True, text=True, timeout=60,
        encoding='utf-8', errors='replace')
    return result.stdout[:3000]


def get_recent_diffs_sample(repo_path: Path, days: int, num_samples: int = 15) -> str:
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    result = subprocess.run(
        ["git", "log", f"--since={since}", f"--max-count={num_samples}",
         "--pretty=format:--- COMMIT %H by %an on %ad ---\n%s\n%b",
         "--stat", "--date=short", "--no-merges"],
        cwd=str(repo_path), capture_output=True, text=True, timeout=120,
        encoding='utf-8', errors='replace')
    return result.stdout[:15000]


def get_readme(repo_path: Path) -> str:
    for name in ["README.md", "README.rst", "README.txt", "README"]:
        p = repo_path / name
        if p.exists():
            try: return p.read_text(encoding='utf-8', errors='replace')[:8000]
            except: pass
    return ""


# ── DPR Extraction via Unified LLM (WatsonX/Gemini) ───────
def extract_dprs(repo_url: str, repo_path: Path, window_key: str,
                 progress_callback: Callable = None) -> dict:
    """Extract DPRs using NexusLLM (WatsonX primary, Gemini fallback).
    Sends context in small packets to avoid timeouts."""
    from llm_provider import get_llm

    llm = get_llm()
    if not llm.is_available:
        raise RuntimeError("No LLM provider available. Set WATSONX_API_KEY or GEMINI_API_KEY.")

    days = ANALYSIS_WINDOWS.get(window_key, 365)

    # Gather context
    if progress_callback:
        progress_callback(stage="gathering_context", progress=20)

    git_log = get_git_log(repo_path, days)
    structure = get_repo_structure(repo_path)
    contributors = get_active_contributors(repo_path, days)
    diffs = get_recent_diffs_sample(repo_path, days)
    readme = get_readme(repo_path)

    total_commits = len(git_log.strip().split("\n")) if git_log.strip() else 0
    print(f"[*] Context: {total_commits} commits, {len(structure.split(chr(10)))} files")
    print(f"[*] Using LLM provider: {llm.provider_name}")

    if progress_callback:
        progress_callback(stage="indexing", progress=25)

    # Build the DPR extraction instruction
    now_iso = datetime.now(timezone.utc).isoformat()
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    instruction = f"""You are Nexus, an architectural decision intelligence engine.
Analyze this GitHub repository and extract ALL significant DPRs.

REPOSITORY: {repo_url}
ANALYSIS WINDOW: {window_key} (last {days} days)
TOTAL COMMITS: {total_commits}

TASK: Extract 25-50 Decision Provenance Records (DPRs).
Each DPR has: dpr_id, title, component, within_window, decision_date, decision,
rejected_alternatives, explicit_constraints, implicit_assumptions,
intended_durability, durability_reasoning, causal_dependencies, files_involved,
commit_refs, involved_humans, assumption_decay_risk, decay_risk_reasoning,
blast_radius_estimate, blast_radius_reasoning, active_workarounds.

ALSO provide:
- ctg_edges: 40-80 causal edges (from_dpr, to_dpr, relationship, explanation)
- assumption_decay_prescan: for high/medium decay risk DPRs

Extract REAL decisions from actual code/history, not generic patterns.

Return ONLY valid JSON:
{{
  "nexus_layer1_output": {{
    "repository": "{repo_url}",
    "analysis_window": "{window_key}",
    "window_cutoff_date": "{cutoff}",
    "analysis_timestamp": "{now_iso}",
    "total_dprs": <number>,
    "dprs_within_window": <number>,
    "dprs_pre_window_active": <number>,
    "dprs": [...],
    "ctg_edges": [...],
    "assumption_decay_prescan": [...]
  }}
}}"""

    # Context sections — each sent as small packet
    context_sections = {
        "README": readme[:4000],
        "FILE_STRUCTURE": structure[:5000],
        "GIT_LOG": git_log[:8000],
        "RECENT_DIFFS": diffs[:8000],
        "CONTRIBUTORS": contributors[:2000],
    }

    print(f"[*] Sending to {llm.provider_name} in small packets...")
    if progress_callback:
        progress_callback(stage="extracting", progress=30)

    # Use chunked generation — sends each section as small packet
    result = llm.generate_json_chunked(
        instruction=instruction,
        context_sections=context_sections,
        temperature=0.1,
        max_tokens=8192,
        progress_callback=progress_callback,
    )

    if not result:
        # Fallback: try single call with truncated context
        print("  [!] Chunked generation failed, trying single call...")
        combined = (f"README:\n{readme[:2000]}\n\nFILES:\n{structure[:2000]}\n\n"
                    f"GIT LOG:\n{git_log[:4000]}\n\nDIFFS:\n{diffs[:4000]}\n\n"
                    f"CONTRIBUTORS:\n{contributors[:1000]}\n\n---\n\n{instruction}")
        result = llm.generate_json(combined, temperature=0.1, max_tokens=8192)

    if not result:
        raise RuntimeError("LLM returned no valid response")

    return result


# ── Full Pipeline ──────────────────────────────────────────
def build_nexus_data_from_extraction(l1_data: dict, output_path: Path) -> dict:
    """Convert Layer 1 extraction into nexus_data.json format."""
    l1 = l1_data.get("nexus_layer1_output", l1_data)
    dprs_raw = l1.get("dprs", [])
    edges_raw = l1.get("ctg_edges", [])
    alerts_raw = l1.get("assumption_decay_prescan", [])

    alert_map = {}
    for a in alerts_raw:
        alert_map[a["dpr_id"]] = {
            "already_decaying": a.get("already_decaying", False),
            "decay_evidence": a.get("decay_evidence", ""),
            "earliest_signal_date": a.get("earliest_signal_date", ""),
            "recommended_monitor_query": a.get("recommended_monitor_query", ""),
        }

    dprs = []
    for d in dprs_raw:
        dpr_id = d.get("dpr_id", d.get("id", ""))
        causal_in, causal_out = [], []
        for e in edges_raw:
            fr = e.get("from_dpr", e.get("from", ""))
            to = e.get("to_dpr", e.get("to", ""))
            if fr == dpr_id: causal_out.append(to)
            if to == dpr_id: causal_in.append(fr)

        dprs.append({
            "id": dpr_id, "title": d.get("title", ""),
            "component": d.get("component", "Unknown"),
            "blast_radius": d.get("blast_radius_estimate", d.get("blast_radius", "medium")),
            "decay_risk": d.get("assumption_decay_risk", d.get("decay_risk", "low")),
            "within_window": d.get("within_window", False),
            "decision_date": d.get("decision_date", ""),
            "decision": d.get("decision", ""),
            "implicit_assumptions": d.get("implicit_assumptions", []),
            "explicit_constraints": d.get("explicit_constraints", []),
            "active_workarounds": d.get("active_workarounds", []),
            "files_involved": d.get("files_involved", []),
            "involved_humans": d.get("involved_humans", []),
            "rejected_alternatives": d.get("rejected_alternatives", []),
            "intended_durability": d.get("intended_durability", ""),
            "durability_reasoning": d.get("durability_reasoning", ""),
            "decay_risk_reasoning": d.get("decay_risk_reasoning", ""),
            "blast_radius_reasoning": d.get("blast_radius_reasoning", ""),
            "commit_refs": d.get("commit_refs", []),
            "causal_dependencies": d.get("causal_dependencies", []),
            "causal_in": list(set(causal_in)),
            "causal_out": list(set(causal_out)),
            "decay_alert": alert_map.get(dpr_id, None),
        })

    ctg_edges = [{"from": e.get("from_dpr", e.get("from", "")),
                  "to": e.get("to_dpr", e.get("to", "")),
                  "type": e.get("relationship", e.get("type", "REQUIRES")),
                  "explanation": e.get("explanation", "")} for e in edges_raw]

    decay_alerts = []
    for a in alerts_raw:
        dm = next((d for d in dprs_raw if d.get("dpr_id", d.get("id", "")) == a["dpr_id"]), None)
        decay_alerts.append({
            "dpr_id": a["dpr_id"],
            "title": dm.get("title", "") if dm else "",
            "component": dm.get("component", "") if dm else "",
            "blast_radius": dm.get("blast_radius_estimate", dm.get("blast_radius", "")) if dm else "",
            "already_decaying": a.get("already_decaying", False),
            "decay_evidence": a.get("decay_evidence", ""),
            "earliest_signal_date": a.get("earliest_signal_date", ""),
            "recommended_monitor_query": a.get("recommended_monitor_query", ""),
        })

    # Knowledge concentration
    human_map = {}
    for d in dprs:
        for h in d.get("involved_humans", []):
            if h not in human_map:
                human_map[h] = {"name": h, "dprs": [], "components": set()}
            human_map[h]["dprs"].append(d["id"])
            human_map[h]["components"].add(d["component"])

    human_profiles = []
    for h in human_map.values():
        blast_scores = []
        for did in h["dprs"]:
            dm = next((dd for dd in dprs if dd["id"] == did), None)
            if dm:
                blast_scores.append({"critical": 4, "high": 3, "medium": 2, "low": 1}.get(dm["blast_radius"], 2))
        avg_blast = sum(blast_scores) / len(blast_scores) if blast_scores else 2
        human_profiles.append({
            "name": h["name"], "dpr_count": len(h["dprs"]), "dprs": h["dprs"],
            "components": sorted(list(h["components"])),
            "component_count": len(h["components"]),
            "avg_blast_score": round(avg_blast, 2),
            "bus_factor_risk_score": round(len(h["dprs"]) * len(h["components"]) * avg_blast, 1),
        })
    human_profiles.sort(key=lambda x: x["bus_factor_risk_score"], reverse=True)

    comp_map = {}
    for d in dprs:
        c = d["component"]
        if c not in comp_map:
            comp_map[c] = {"component": c, "dprs": [], "humans": set()}
        comp_map[c]["dprs"].append(d["id"])
        for h in d.get("involved_humans", []):
            comp_map[c]["humans"].add(h)

    component_profiles = []
    for c in comp_map.values():
        decay_s, blast_s = [], []
        for did in c["dprs"]:
            dm = next((dd for dd in dprs if dd["id"] == did), None)
            if dm:
                decay_s.append({"high": 3, "medium": 2, "low": 1}.get(dm["decay_risk"], 1))
                blast_s.append({"critical": 4, "high": 3, "medium": 2, "low": 1}.get(dm["blast_radius"], 2))
        avg_d = sum(decay_s) / len(decay_s) if decay_s else 1
        avg_b = sum(blast_s) / len(blast_s) if blast_s else 2
        component_profiles.append({
            "component": c["component"], "dpr_count": len(c["dprs"]), "dprs": c["dprs"],
            "unique_humans": len(c["humans"]), "humans": sorted(list(c["humans"])),
            "avg_decay_risk": round(avg_d, 2), "avg_blast_radius": round(avg_b, 2),
            "spof_score": round(avg_d * avg_b, 2),
        })
    component_profiles.sort(key=lambda x: x["spof_score"], reverse=True)

    file_map = {}
    for d in dprs:
        for f in d.get("files_involved", []):
            if f not in file_map:
                file_map[f] = {"file": f, "dprs": []}
            file_map[f]["dprs"].append(d["id"])

    file_profiles = []
    for fp in file_map.values():
        blast_scores = []
        for did in fp["dprs"]:
            dm = next((dd for dd in dprs if dd["id"] == did), None)
            if dm:
                blast_scores.append({"critical": 4, "high": 3, "medium": 2, "low": 1}.get(dm["blast_radius"], 2))
        avg_b = sum(blast_scores) / len(blast_scores) if blast_scores else 2
        file_profiles.append({
            "file": fp["file"], "dpr_count": len(fp["dprs"]), "dprs": fp["dprs"],
            "avg_blast_score": round(avg_b, 2),
            "criticality_score": round(len(fp["dprs"]) * avg_b, 1),
        })
    file_profiles.sort(key=lambda x: x["criticality_score"], reverse=True)

    active_decay = sum(1 for a in decay_alerts if a.get("already_decaying"))
    total_dprs = len(dprs)
    critical_blast = sum(1 for d in dprs if d["blast_radius"] == "critical")
    high_decay = sum(1 for d in dprs if d["decay_risk"] == "high")
    org_risk = round(
        (active_decay / max(len(decay_alerts), 1)) * 40 +
        (critical_blast / max(total_dprs, 1)) * 30 +
        (high_decay / max(total_dprs, 1)) * 30, 1)

    cf_traces = generate_counterfactuals(dprs, ctg_edges)

    graph_nodes = [{"id": d["id"], "label": d["title"], "component": d["component"],
                    "blast_radius": d.get("blast_radius", "medium"),
                    "decay_risk": d.get("decay_risk", "low"),
                    "within_window": d.get("within_window", False)} for d in dprs]

    repo_url = l1.get("repository", "")
    components = sorted(list(set(d["component"] for d in dprs if d.get("component"))))

    output = {
        "meta": {
            "repository": repo_url,
            "analysis_window": l1.get("analysis_window", "1year"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_dprs": len(dprs),
            "total_nodes": len(dprs) + len(decay_alerts) + sum(len(d.get("implicit_assumptions", [])) for d in dprs),
            "total_relationships": len(ctg_edges),
            "components": components,
            "llm_provider": "watsonx+gemini",
        },
        "dprs": dprs, "ctg_edges": ctg_edges,
        "graph_data": {"nodes": graph_nodes, "edges": ctg_edges},
        "decay_alerts": decay_alerts,
        "knowledge_concentration": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "human_profiles": human_profiles,
            "component_profiles": component_profiles,
            "file_profiles": file_profiles,
            "top_spof_humans": [h["name"] for h in human_profiles[:5]],
            "top_spof_components": [c["component"] for c in component_profiles[:5]],
        },
        "counterfactual_traces": cf_traces,
        "risk_forecast": {}, "org_risk_score": org_risk, "monitoring_runs": [],
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    size = output_path.stat().st_size
    print(f"\n[+] Written: {output_path}")
    print(f"    Size: {size:,} bytes | DPRs: {len(dprs)} | Edges: {len(ctg_edges)}")
    print(f"    Decay Alerts: {len(decay_alerts)} | Org Risk: {org_risk}")
    return output


def generate_counterfactuals(dprs, edges):
    traces = []
    sorted_dprs = sorted(dprs, key=lambda d: (
        {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(d["blast_radius"], 1),
        len(d.get("causal_out", []))), reverse=True)

    for i, d in enumerate(sorted_dprs[:5]):
        downstream_ids = d.get("causal_out", [])
        upstream_ids = d.get("causal_in", [])
        alt = d.get("rejected_alternatives", ["a different approach"])[0] if d.get("rejected_alternatives") else "a different approach"
        question = f"What if {d['title']} had been implemented differently — using {alt}?"
        traces.append({
            "id": f"CF-{i+1:03d}", "question": question,
            "target_dpr": d["id"], "alternative": alt,
            "downstream_count": len(downstream_ids),
            "upstream_count": len(upstream_ids),
            "result": {
                "verdict": "worse" if d["blast_radius"] == "critical" else "tradeoff",
                "confidence": round(0.6 + (i * 0.05), 2),
                "timeline_narrative": f"If {d['title'].lower()} used {alt.split(' - ')[0].lower()}, downstream effects on {', '.join(downstream_ids[:3])} would cascade.",
                "modern_relevance": f"Given modern infrastructure, this alternative {'remains problematic' if d['blast_radius'] == 'critical' else 'could be reconsidered'}.",
                "broken_assumptions": d.get("implicit_assumptions", [])[:2],
                "unnecessary_workarounds": [],
                "new_problems": [f"Would affect {len(downstream_ids)} downstream decisions"],
                "affected_dprs": downstream_ids[:5],
            },
        })
    return traces


# ── Main Entry Point ───────────────────────────────────────
def analyze_repo(repo_url: str, window_key: str = "1year",
                 progress_callback: Callable = None) -> dict:
    """Full pipeline: clone → analyze → build nexus_data.json
    Progress callback receives (stage=, progress=) for granular updates."""
    print("=" * 60)
    print(f"  NEXUS - Analyzing {repo_url}")
    print(f"  Window: {window_key}")
    print("=" * 60)

    output_path = SCRIPT_DIR / "nexus_data.json"

    # Step 1: Clone with streamed progress
    print("\n[1/4] Cloning repository...")
    if progress_callback:
        progress_callback(stage="cloning", progress=5)
    repo_path = clone_repo(repo_url, progress_callback)
    print(f"  Cloned to: {repo_path}")

    # Step 2: Extract DPRs with unified LLM (WatsonX/Gemini)
    print("\n[2/4] Extracting DPRs with WatsonX/Gemini...")
    if progress_callback:
        progress_callback(stage="extracting", progress=20)

    l1_data = extract_dprs(repo_url, repo_path, window_key, progress_callback)

    # Save L1 data
    l1_path = SCRIPT_DIR / "last_extraction.json"
    with open(l1_path, 'w', encoding='utf-8') as f:
        json.dump(l1_data, f, indent=2, ensure_ascii=False)
    print(f"  L1 extraction saved to {l1_path}")

    # Step 3: Build nexus_data.json
    print("\n[3/4] Building nexus_data.json...")
    if progress_callback:
        progress_callback(stage="building_data", progress=75)
    result = build_nexus_data_from_extraction(l1_data, output_path)

    # Step 4: Done
    print("\n[4/4] Analysis complete!")
    if progress_callback:
        progress_callback(stage="finalizing", progress=95)

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Nexus Universal Repository Analyzer")
    parser.add_argument("repo_url", help="GitHub repository URL")
    parser.add_argument("--window", default="1year", choices=ANALYSIS_WINDOWS.keys())
    args = parser.parse_args()
    analyze_repo(args.repo_url, args.window)
