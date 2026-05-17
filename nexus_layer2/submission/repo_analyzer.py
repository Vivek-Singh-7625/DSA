"""
Nexus - Universal Repository Analyzer
Clones any GitHub repository, analyzes git history + codebase,
extracts Decision Provenance Records (DPRs) using Gemini,
builds the full Causal Temporal Graph data.
"""

import os, sys, json, subprocess, re, time, shutil, hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

# ── Config ─────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
CLONE_DIR = SCRIPT_DIR / "_repos"
GEMINI_MODEL = "gemini-2.5-flash"

ANALYSIS_WINDOWS = {
    "1year": 365,
    "2years": 730,
    "3years": 1095,
    "5years": 1825,
    "all": 36500,
}

# ── Gemini Client ──────────────────────────────────────────
def get_gemini_client():
    try:
        from google import genai
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not set")
        return genai.Client(api_key=key)
    except Exception as e:
        print(f"[!] Gemini unavailable: {e}")
        return None


def gemini_generate(client, prompt, temperature=0.2):
    """Generate text with Gemini, with retry."""
    from google import genai
    config = genai.types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=65536,
    )
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=config,
            )
            return resp.text
        except Exception as e:
            print(f"  [!] Gemini attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
    return None


# ── Git Operations ─────────────────────────────────────────
def clone_repo(repo_url: str) -> Path:
    """Clone a GitHub repo to local disk. Returns path."""
    CLONE_DIR.mkdir(exist_ok=True)
    
    # Create a unique directory name from the URL
    repo_hash = hashlib.md5(repo_url.encode()).hexdigest()[:10]
    parts = repo_url.replace("https://github.com/", "").replace("http://github.com/", "").split("/")
    if len(parts) >= 2:
        repo_name = f"{parts[0]}_{parts[1]}_{repo_hash}"
    else:
        repo_name = repo_hash
    
    repo_path = CLONE_DIR / repo_name
    
    if repo_path.exists():
        # Pull latest instead of re-cloning
        print(f"[*] Repo already exists at {repo_path}, pulling latest...")
        try:
            subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=str(repo_path),
                capture_output=True, text=True, timeout=120,
                encoding='utf-8', errors='replace'
            )
        except:
            pass
        return repo_path
    
    print(f"[*] Cloning {repo_url} to {repo_path}...")
    # Shallow clone to save time — last 500 commits is plenty for architectural analysis
    result = subprocess.run(
        ["git", "clone", "--depth", "500", "--single-branch", repo_url, str(repo_path)],
        capture_output=True, text=True, timeout=600,
        encoding='utf-8', errors='replace'
    )
    if result.returncode != 0:
        raise RuntimeError(f"Git clone failed: {result.stderr[:500]}")
    
    return repo_path


def get_git_log(repo_path: Path, days: int, max_commits: int = 2000) -> str:
    """Get git log summary within the analysis window."""
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    result = subprocess.run(
        ["git", "log", f"--since={since_date}", f"--max-count={max_commits}",
         "--pretty=format:%H|%an|%ad|%s", "--date=short", "--no-merges"],
        cwd=str(repo_path),
        capture_output=True, text=True, timeout=120,
        encoding='utf-8', errors='replace'
    )
    return result.stdout


def get_repo_structure(repo_path: Path, max_files: int = 200) -> str:
    """Get file tree summary of the repo."""
    files = []
    for root, dirs, filenames in os.walk(repo_path):
        # Skip hidden dirs, node_modules, etc.
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', '__pycache__', 'vendor', 'dist', 'build', '.git')]
        for f in filenames:
            rel = os.path.relpath(os.path.join(root, f), repo_path)
            files.append(rel)
            if len(files) >= max_files:
                break
        if len(files) >= max_files:
            break
    return "\n".join(files)


def get_active_contributors(repo_path: Path, days: int) -> str:
    """Get top contributors within the analysis window."""
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    result = subprocess.run(
        ["git", "shortlog", "-sn", "--no-merges", f"--since={since_date}"],
        cwd=str(repo_path),
        capture_output=True, text=True, timeout=60,
        encoding='utf-8', errors='replace'
    )
    return result.stdout[:3000]


def get_recent_diffs_sample(repo_path: Path, days: int, num_samples: int = 15) -> str:
    """Get a sample of recent commit diffs to understand code changes."""
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    result = subprocess.run(
        ["git", "log", f"--since={since_date}", f"--max-count={num_samples}",
         "--pretty=format:--- COMMIT %H by %an on %ad ---\n%s\n%b",
         "--stat", "--date=short", "--no-merges"],
        cwd=str(repo_path),
        capture_output=True, text=True, timeout=120,
        encoding='utf-8', errors='replace'
    )
    return result.stdout[:15000]


def get_readme(repo_path: Path) -> str:
    """Read the README if it exists."""
    for name in ["README.md", "README.rst", "README.txt", "README"]:
        p = repo_path / name
        if p.exists():
            try:
                return p.read_text(encoding='utf-8', errors='replace')[:8000]
            except:
                pass
    return ""


# ── DPR Extraction via Gemini ──────────────────────────────
def extract_dprs(client, repo_url: str, repo_path: Path, window_key: str) -> dict:
    """Use Gemini to extract DPRs from the repository."""
    days = ANALYSIS_WINDOWS.get(window_key, 365)
    
    # Gather context
    git_log = get_git_log(repo_path, days)
    structure = get_repo_structure(repo_path)
    contributors = get_active_contributors(repo_path, days)
    diffs = get_recent_diffs_sample(repo_path, days)
    readme = get_readme(repo_path)
    
    total_commits = len(git_log.strip().split("\n")) if git_log.strip() else 0
    
    print(f"[*] Context gathered: {total_commits} commits, {len(structure.split(chr(10)))} files")
    
    # Build the mega prompt
    prompt = f"""You are Nexus, an architectural decision intelligence engine. Analyze this GitHub repository
and extract ALL significant architectural Decision Provenance Records (DPRs).

REPOSITORY: {repo_url}
ANALYSIS WINDOW: {window_key} (last {days} days)
TOTAL COMMITS IN WINDOW: {total_commits}

=== README ===
{readme[:4000]}

=== FILE STRUCTURE (sample) ===
{structure[:5000]}

=== GIT LOG (sample — {total_commits} total commits) ===
{git_log[:8000]}

=== RECENT DIFFS / CHANGES ===
{diffs[:8000]}

=== TOP CONTRIBUTORS ===
{contributors[:2000]}

---

TASK: Extract 25-50 Decision Provenance Records (DPRs) from this repository.
Each DPR represents a significant architectural decision — a choice that constrains
the system's evolution and has downstream consequences.

For EACH DPR, provide:
- dpr_id: "DPR-001" through "DPR-0XX"
- title: Short descriptive title
- component: Which subsystem/module (derive from the repo structure)
- within_window: true if the decision was made/modified within the analysis window
- decision_date: When it was made (YYYY or "pre-window")
- decision: One-sentence description of the decision
- rejected_alternatives: List of alternatives that were NOT chosen and why
- explicit_constraints: Technical constraints this decision imposes
- implicit_assumptions: Assumptions that MUST hold for this decision to work (prefix with "INFERRED:")
- intended_durability: "foundational" | "medium-term" | "short-term"
- durability_reasoning: Why
- causal_dependencies: List like ["DPR-XXX: explanation"]
- files_involved: Key source files
- commit_refs: Relevant commits or versions
- involved_humans: Contributors who made/maintain this decision
- assumption_decay_risk: "high" | "medium" | "low"
- decay_risk_reasoning: Why this assumption might break
- blast_radius_estimate: "critical" | "high" | "medium" | "low"
- blast_radius_reasoning: What breaks if this assumption fails
- active_workarounds: Current patches/hacks working around limitations

ALSO provide:
- ctg_edges: Causal edges between DPRs. Each edge has:
  - from_dpr, to_dpr, relationship (CONSTRAINS|ENABLES|REQUIRES|ASSUMPTION_OF|TEMPORAL_PRECEDES|REQUIRED_BY), explanation
  - Provide 40-80 edges showing the full causal web

- assumption_decay_prescan: For DPRs with high/medium decay risk, provide:
  - dpr_id, assumption (which assumption is at risk), decay_signals_found, earliest_signal_date,
    already_decaying (true/false), decay_evidence, recommended_monitor_query

IMPORTANT:
- Extract REAL decisions from the actual code and history, not generic software patterns
- Include decisions from ALL major subsystems/components you can identify
- The causal graph should be DENSE — most DPRs should have 3+ connections
- Be specific about file paths, contributors, and commit references
- For "already_decaying", mark true ONLY if you see clear evidence in recent commits/issues

Respond with ONLY valid JSON in this exact structure:
{{
  "nexus_layer1_output": {{
    "repository": "{repo_url}",
    "analysis_window": "{window_key}",
    "window_cutoff_date": "{(datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')}",
    "analysis_timestamp": "{datetime.now(timezone.utc).isoformat()}",
    "total_dprs": <number>,
    "dprs_within_window": <number>,
    "dprs_pre_window_active": <number>,
    "dprs": [...],
    "ctg_edges": [...],
    "assumption_decay_prescan": [...]
  }}
}}
"""
    
    print("[*] Sending to Gemini for DPR extraction (this takes 30-60 seconds)...")
    raw = gemini_generate(client, prompt, temperature=0.1)
    
    if not raw:
        raise RuntimeError("Gemini returned no response")
    
    # Parse JSON from response
    # Strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```\w*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)
    
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        # Try to extract JSON from the response
        match = re.search(r'\{[\s\S]*\}', cleaned)
        if match:
            result = json.loads(match.group())
        else:
            raise RuntimeError(f"Failed to parse Gemini response as JSON: {e}")
    
    return result


# ── Full Pipeline ──────────────────────────────────────────
def build_nexus_data_from_extraction(l1_data: dict, output_path: Path) -> dict:
    """Convert Layer 1 extraction into nexus_data.json format."""
    l1 = l1_data.get("nexus_layer1_output", l1_data)
    dprs_raw = l1.get("dprs", [])
    edges_raw = l1.get("ctg_edges", [])
    alerts_raw = l1.get("assumption_decay_prescan", [])
    
    # Build alert lookup
    alert_map = {}
    for a in alerts_raw:
        alert_map[a["dpr_id"]] = {
            "already_decaying": a.get("already_decaying", False),
            "decay_evidence": a.get("decay_evidence", ""),
            "earliest_signal_date": a.get("earliest_signal_date", ""),
            "recommended_monitor_query": a.get("recommended_monitor_query", ""),
        }
    
    # Build DPRs
    dprs = []
    for d in dprs_raw:
        dpr_id = d.get("dpr_id", d.get("id", ""))
        
        # Derive causal connections from edges
        causal_in = []
        causal_out = []
        for e in edges_raw:
            fr = e.get("from_dpr", e.get("from", ""))
            to = e.get("to_dpr", e.get("to", ""))
            if fr == dpr_id:
                causal_out.append(to)
            if to == dpr_id:
                causal_in.append(fr)
        
        dprs.append({
            "id": dpr_id,
            "title": d.get("title", ""),
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
    
    # Build CTG edges
    ctg_edges = []
    for e in edges_raw:
        ctg_edges.append({
            "from": e.get("from_dpr", e.get("from", "")),
            "to": e.get("to_dpr", e.get("to", "")),
            "type": e.get("relationship", e.get("type", "REQUIRES")),
            "explanation": e.get("explanation", ""),
        })
    
    # Build decay alerts
    decay_alerts = []
    for a in alerts_raw:
        dpr_match = next((d for d in dprs_raw if d.get("dpr_id", d.get("id", "")) == a["dpr_id"]), None)
        decay_alerts.append({
            "dpr_id": a["dpr_id"],
            "title": dpr_match.get("title", "") if dpr_match else "",
            "component": dpr_match.get("component", "") if dpr_match else "",
            "blast_radius": dpr_match.get("blast_radius_estimate", dpr_match.get("blast_radius", "")) if dpr_match else "",
            "already_decaying": a.get("already_decaying", False),
            "decay_evidence": a.get("decay_evidence", ""),
            "earliest_signal_date": a.get("earliest_signal_date", ""),
            "recommended_monitor_query": a.get("recommended_monitor_query", ""),
        })
    
    # Build knowledge concentration
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
                bs = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(dm["blast_radius"], 2)
                blast_scores.append(bs)
        avg_blast = sum(blast_scores) / len(blast_scores) if blast_scores else 2
        human_profiles.append({
            "name": h["name"],
            "dpr_count": len(h["dprs"]),
            "dprs": h["dprs"],
            "components": sorted(list(h["components"])),
            "component_count": len(h["components"]),
            "avg_blast_score": round(avg_blast, 2),
            "bus_factor_risk_score": round(len(h["dprs"]) * len(h["components"]) * avg_blast, 1),
        })
    human_profiles.sort(key=lambda x: x["bus_factor_risk_score"], reverse=True)
    
    # Component profiles
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
        decay_scores = []
        blast_scores = []
        for did in c["dprs"]:
            dm = next((dd for dd in dprs if dd["id"] == did), None)
            if dm:
                ds = {"high": 3, "medium": 2, "low": 1}.get(dm["decay_risk"], 1)
                bs = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(dm["blast_radius"], 2)
                decay_scores.append(ds)
                blast_scores.append(bs)
        avg_decay = sum(decay_scores) / len(decay_scores) if decay_scores else 1
        avg_blast = sum(blast_scores) / len(blast_scores) if blast_scores else 2
        component_profiles.append({
            "component": c["component"],
            "dpr_count": len(c["dprs"]),
            "dprs": c["dprs"],
            "unique_humans": len(c["humans"]),
            "humans": sorted(list(c["humans"])),
            "avg_decay_risk": round(avg_decay, 2),
            "avg_blast_radius": round(avg_blast, 2),
            "spof_score": round(avg_decay * avg_blast, 2),
        })
    component_profiles.sort(key=lambda x: x["spof_score"], reverse=True)
    
    # File profiles
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
                bs = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(dm["blast_radius"], 2)
                blast_scores.append(bs)
        avg_blast = sum(blast_scores) / len(blast_scores) if blast_scores else 2
        file_profiles.append({
            "file": fp["file"],
            "dpr_count": len(fp["dprs"]),
            "dprs": fp["dprs"],
            "avg_blast_score": round(avg_blast, 2),
            "criticality_score": round(len(fp["dprs"]) * avg_blast, 1),
        })
    file_profiles.sort(key=lambda x: x["criticality_score"], reverse=True)
    
    # Compute org risk score
    active_decay = sum(1 for a in decay_alerts if a.get("already_decaying"))
    total_dprs = len(dprs)
    critical_blast = sum(1 for d in dprs if d["blast_radius"] == "critical")
    high_decay = sum(1 for d in dprs if d["decay_risk"] == "high")
    org_risk = round(
        (active_decay / max(len(decay_alerts), 1)) * 40 +
        (critical_blast / max(total_dprs, 1)) * 30 +
        (high_decay / max(total_dprs, 1)) * 30,
        1
    )
    
    # Counterfactual traces (generate a few interesting ones)
    cf_traces = generate_counterfactuals(dprs, ctg_edges)
    
    # Assemble
    repo_url = l1.get("repository", "")
    output = {
        "meta": {
            "repository": repo_url,
            "analysis_window": l1.get("analysis_window", "1year"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_dprs": len(dprs),
            "total_nodes": len(dprs) + len(decay_alerts) + sum(len(d.get("implicit_assumptions", [])) for d in dprs),
            "total_relationships": len(ctg_edges),
        },
        "dprs": dprs,
        "ctg_edges": ctg_edges,
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
        "risk_forecast": {},
        "org_risk_score": org_risk,
        "monitoring_runs": [],
    }
    
    # Write
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    size = output_path.stat().st_size
    print(f"\n[+] Written: {output_path}")
    print(f"    Size: {size:,} bytes")
    print(f"    DPRs: {len(dprs)}")
    print(f"    CTG Edges: {len(ctg_edges)}")
    print(f"    Decay Alerts: {len(decay_alerts)}")
    print(f"    Human Profiles: {len(human_profiles)}")
    print(f"    Component Profiles: {len(component_profiles)}")
    print(f"    Org Risk Score: {org_risk}")
    
    return output


def generate_counterfactuals(dprs, edges):
    """Generate interesting counterfactual traces from the graph."""
    traces = []
    # Find high-blast-radius DPRs with lots of connections
    sorted_dprs = sorted(dprs, key=lambda d: (
        {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(d["blast_radius"], 1),
        len(d.get("causal_out", []))
    ), reverse=True)
    
    for i, d in enumerate(sorted_dprs[:5]):
        downstream_ids = d.get("causal_out", [])
        upstream_ids = d.get("causal_in", [])
        
        # Build a counterfactual question
        alt = d.get("rejected_alternatives", ["a different approach"])[0] if d.get("rejected_alternatives") else "a different approach"
        question = f"What if {d['title']} had been implemented differently — using {alt}?"
        
        traces.append({
            "id": f"CF-{i+1:03d}",
            "question": question,
            "target_dpr": d["id"],
            "alternative": alt,
            "downstream_count": len(downstream_ids),
            "upstream_count": len(upstream_ids),
            "result": {
                "verdict": "worse" if d["blast_radius"] == "critical" else "tradeoff",
                "confidence": round(0.6 + (i * 0.05), 2),
                "timeline_narrative": f"If {d['title'].lower()} used {alt.split(' - ')[0].lower()}, the downstream effects on {', '.join(downstream_ids[:3])} would cascade.",
                "modern_relevance": f"Given modern infrastructure, this alternative {'remains problematic' if d['blast_radius'] == 'critical' else 'could be reconsidered'}.",
                "broken_assumptions": d.get("implicit_assumptions", [])[:2],
                "unnecessary_workarounds": [],
                "new_problems": [f"Would affect {len(downstream_ids)} downstream decisions"],
                "affected_dprs": downstream_ids[:5],
            },
        })
    
    return traces


# ── Main Entry Point ───────────────────────────────────────
def analyze_repo(repo_url: str, window_key: str = "1year") -> dict:
    """Full pipeline: clone → analyze → build nexus_data.json"""
    print("=" * 60)
    print(f"  NEXUS - Analyzing {repo_url}")
    print(f"  Window: {window_key}")
    print("=" * 60)
    
    output_path = SCRIPT_DIR / "nexus_data.json"
    
    # Step 1: Clone
    print("\n[1/4] Cloning repository...")
    repo_path = clone_repo(repo_url)
    print(f"  Cloned to: {repo_path}")
    
    # Step 2: Extract DPRs with Gemini
    print("\n[2/4] Extracting DPRs with Gemini...")
    client = get_gemini_client()
    if not client:
        raise RuntimeError("Gemini API key required for analysis")
    
    l1_data = extract_dprs(client, repo_url, repo_path, window_key)
    
    # Save L1 data
    l1_path = SCRIPT_DIR / "last_extraction.json"
    with open(l1_path, 'w', encoding='utf-8') as f:
        json.dump(l1_data, f, indent=2, ensure_ascii=False)
    print(f"  L1 extraction saved to {l1_path}")
    
    # Step 3: Build nexus_data.json
    print("\n[3/4] Building nexus_data.json...")
    result = build_nexus_data_from_extraction(l1_data, output_path)
    
    # Step 4: Done
    print("\n[4/4] Analysis complete!")
    
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Nexus Universal Repository Analyzer")
    parser.add_argument("repo_url", help="GitHub repository URL")
    parser.add_argument("--window", default="1year", choices=ANALYSIS_WINDOWS.keys())
    args = parser.parse_args()
    analyze_repo(args.repo_url, args.window)
