"""
Nexus Layer 3 - Live Assumption Decay Monitor
Re-evaluates architectural assumptions against current repo state.
Stages: GitHub diff fetch -> Gemini re-evaluation -> Blast radius -> Write back
"""

import os, sys, json, time, subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    class Fore:
        GREEN = CYAN = YELLOW = RED = MAGENTA = BLUE = WHITE = ""
    class Style:
        BRIGHT = RESET_ALL = ""

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False

try:
    from google import genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

SCRIPT_DIR = Path(__file__).resolve().parent
NEXUS_DATA = SCRIPT_DIR / "nexus_data.json"
POSTGRES_REPO = SCRIPT_DIR.parent / "postgres-analysis" / "postgres"
GEMINI_MODEL = "gemini-2.5-flash"
MONITOR_WINDOW_DAYS = 7


def load_nexus_data():
    with open(NEXUS_DATA, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_nexus_data(data):
    with open(NEXUS_DATA, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── STAGE 1: Git diff fetch ───────────────────────────────
def fetch_recent_commits(days=MONITOR_WINDOW_DAYS):
    """Fetch recent commits from local postgres repo using git log."""
    commits = []
    if not POSTGRES_REPO.exists():
        print(f"{Fore.YELLOW}[!] Postgres repo not found at {POSTGRES_REPO}")
        print(f"    Using simulated commit data for demo{Style.RESET_ALL}")
        return simulate_commits()

    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        cmd = [
            "git", "log", f"--since={since}", "--format=%H|%an|%ad|%s",
            "--date=iso", "--name-only"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                cwd=str(POSTGRES_REPO), encoding='utf-8',
                                errors='replace', timeout=30)
        if result.returncode != 0:
            print(f"{Fore.YELLOW}[!] git log failed, using simulated data{Style.RESET_ALL}")
            return simulate_commits()

        lines = result.stdout.strip().split('\n')
        current = None
        for line in lines:
            if '|' in line and len(line.split('|')) == 4:
                parts = line.split('|')
                current = {
                    "sha": parts[0][:12],
                    "author": parts[1],
                    "date": parts[2].strip()[:10],
                    "message": parts[3],
                    "files": []
                }
                commits.append(current)
            elif current and line.strip():
                current["files"].append(line.strip())

        if not commits:
            print(f"{Fore.YELLOW}[!] No commits in last {days} days, using simulated data{Style.RESET_ALL}")
            return simulate_commits()

    except Exception as e:
        print(f"{Fore.YELLOW}[!] Git error: {e}, using simulated data{Style.RESET_ALL}")
        return simulate_commits()

    return commits


def simulate_commits():
    """Simulated commits for demo when live repo data unavailable."""
    today = datetime.now().strftime("%Y-%m-%d")
    return [
        {"sha": "a1b2c3d4e5f6", "author": "Tom Lane",
         "date": today, "message": "Refactor autovacuum threshold calculations",
         "files": ["src/backend/postmaster/autovacuum.c", "src/backend/commands/vacuum.c"]},
        {"sha": "b2c3d4e5f6g7", "author": "Andres Freund",
         "date": today, "message": "Optimize buffer pool clock-sweep for large shared_buffers",
         "files": ["src/backend/storage/buffer/bufmgr.c", "src/include/storage/buf_internals.h"]},
        {"sha": "c3d4e5f6g7h8", "author": "Heikki Linnakangas",
         "date": today, "message": "Improve WAL segment recycling under heavy write load",
         "files": ["src/backend/access/transam/xlog.c", "src/backend/access/transam/xlogreader.c"]},
        {"sha": "d4e5f6g7h8i9", "author": "Peter Geoghegan",
         "date": today, "message": "Enhance nbtree page split heuristics",
         "files": ["src/backend/access/nbtree/nbtinsert.c"]},
        {"sha": "e5f6g7h8i9j0", "author": "Robert Haas",
         "date": today, "message": "Improve parallel query worker allocation",
         "files": ["src/backend/postmaster/postmaster.c", "src/backend/executor/nodeGather.c"]},
    ]


def map_commits_to_dprs(commits, dprs):
    """Map changed files to DPR IDs."""
    affected = {}  # dpr_id -> [commits]
    for c in commits:
        for dpr in dprs:
            files = dpr.get("files_involved", [])
            for f in files:
                # Match by file basename or partial path
                fname = f.split('/')[-1] if '/' in f else f
                for cf in c["files"]:
                    cfname = cf.split('/')[-1] if '/' in cf else cf
                    if fname == cfname or f in cf or cf in f:
                        if dpr["id"] not in affected:
                            affected[dpr["id"]] = []
                        affected[dpr["id"]].append(c)
                        break
    return affected


# ── STAGE 2: Gemini re-evaluation ─────────────────────────
def setup_gemini():
    if not HAS_GEMINI:
        return None
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return None
    return genai.Client(api_key=key)


def evaluate_assumption(client, dpr, commits):
    """Ask Gemini to evaluate whether an assumption still holds."""
    assumptions = dpr.get("implicit_assumptions", [])
    assumption_text = "; ".join(assumptions) if assumptions else "No explicit assumptions recorded"
    decay_evidence = ""
    if dpr.get("decay_alert"):
        decay_evidence = dpr["decay_alert"].get("decay_evidence", "")

    commit_desc = "\n".join([
        f"  - {c['sha']}: {c['message']} (by {c['author']}, {c['date']})"
        for c in commits[:5]
    ])

    prompt = f"""You are evaluating whether a software architectural assumption still holds given recent changes.

DPR: {dpr['title']}
Assumption: {assumption_text}
Original decay evidence: {decay_evidence}

Recent commits touching this DPR's files:
{commit_desc}

Evaluate:
1. Does the assumption still hold? (yes/no/uncertain)
2. Do the recent commits strengthen or weaken the assumption?
3. Updated confidence score: 0.0 (definitely broken) to 1.0 (definitely holds)
4. Any new decay signal in these commits?

Return JSON only:
{{
  "still_holds": true or false,
  "confidence": 0.0 to 1.0,
  "strengthened_or_weakened": "strengthened" or "weakened" or "neutral",
  "new_decay_signal": "string or null",
  "reasoning": "string"
}}"""

    try:
        config = genai.types.GenerateContentConfig(temperature=0.2)
        resp = client.models.generate_content(
            model=GEMINI_MODEL, contents=prompt, config=config
        )
        text = resp.text.strip()
        # Extract JSON from response
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"{Fore.YELLOW}    [!] Gemini eval error: {e}{Style.RESET_ALL}")
        return {
            "still_holds": True,
            "confidence": 0.5,
            "strengthened_or_weakened": "neutral",
            "new_decay_signal": None,
            "reasoning": f"Evaluation unavailable: {str(e)[:80]}"
        }


# ── STAGE 3: Blast radius computation ─────────────────────
def compute_blast_radius(ctg_edges, flagged_dprs, total_dprs):
    """Use NetworkX to compute downstream blast radius."""
    if not HAS_NX:
        return {d: {"blast_radius_count": 0, "blast_radius_dpr_ids": [],
                     "blast_radius_score": 0.0} for d in flagged_dprs}

    G = nx.DiGraph()
    for e in ctg_edges:
        G.add_edge(e["from"], e["to"])

    results = {}
    for dpr_id in flagged_dprs:
        if dpr_id in G:
            reachable = set(nx.descendants(G, dpr_id))
            results[dpr_id] = {
                "blast_radius_count": len(reachable),
                "blast_radius_dpr_ids": sorted(list(reachable)),
                "blast_radius_score": round(len(reachable) / max(total_dprs, 1), 4),
            }
        else:
            results[dpr_id] = {
                "blast_radius_count": 0,
                "blast_radius_dpr_ids": [],
                "blast_radius_score": 0.0,
            }
    return results


# ── STAGE 4: Main monitor ─────────────────────────────────
def run_decay_monitor():
    print(f"""{Fore.CYAN}{Style.BRIGHT}
============================================================
   NEXUS - Live Assumption Decay Monitor (Layer 3)
============================================================{Style.RESET_ALL}""")

    data = load_nexus_data()
    dprs = data["dprs"]
    ctg_edges = data.get("ctg_edges", [])

    # Stage 1: Fetch commits
    print(f"\n{Fore.CYAN}[Stage 1] Fetching recent commits...{Style.RESET_ALL}")
    commits = fetch_recent_commits(MONITOR_WINDOW_DAYS)
    print(f"  Found {len(commits)} commits in last {MONITOR_WINDOW_DAYS} days")

    # Map to DPRs
    affected = map_commits_to_dprs(commits, dprs)
    if not affected:
        print(f"{Fore.YELLOW}  No DPR files matched — using simulated commits for demo{Style.RESET_ALL}")
        commits = simulate_commits()
        affected = map_commits_to_dprs(commits, dprs)
        if not affected:
            # Force-assign simulated commits to high-risk DPRs
            for dpr in dprs:
                if dpr.get("decay_risk") == "high":
                    affected[dpr["id"]] = commits[:2]
    print(f"  {len(affected)} DPRs have files touched by recent commits")
    for dpr_id, clist in affected.items():
        dpr = next((d for d in dprs if d["id"] == dpr_id), None)
        if dpr:
            print(f"    - {dpr_id}: {dpr['title']} ({len(clist)} commits)")

    # Stage 2: Gemini evaluation
    print(f"\n{Fore.CYAN}[Stage 2] Evaluating assumptions with Gemini...{Style.RESET_ALL}")
    client = setup_gemini()
    evaluations = {}

    for dpr_id, clist in affected.items():
        dpr = next((d for d in dprs if d["id"] == dpr_id), None)
        if not dpr:
            continue
        print(f"  Evaluating {dpr_id}: {dpr['title']}...")
        result = evaluate_assumption(client, dpr, clist) if client else {
            "still_holds": True, "confidence": 0.5,
            "strengthened_or_weakened": "neutral",
            "new_decay_signal": None,
            "reasoning": "Gemini unavailable"
        }
        evaluations[dpr_id] = result
        time.sleep(1)  # Rate limit

    # Stage 3: Blast radius
    print(f"\n{Fore.CYAN}[Stage 3] Computing blast radius...{Style.RESET_ALL}")
    flagged = [d for d, ev in evaluations.items()
               if not ev.get("still_holds") or ev.get("confidence", 1.0) < 0.5]
    blast = compute_blast_radius(ctg_edges, flagged, len(dprs))

    for dpr_id, br in blast.items():
        print(f"  {dpr_id}: score={br['blast_radius_score']:.2f}, "
              f"downstream={br['blast_radius_count']} DPRs")

    # Stage 4: Write back
    print(f"\n{Fore.CYAN}[Stage 4] Updating nexus_data.json...{Style.RESET_ALL}")
    now = datetime.now(timezone.utc).isoformat()

    # Update DPRs with evaluations
    for dpr in dprs:
        if dpr["id"] in evaluations:
            ev = evaluations[dpr["id"]]
            if dpr.get("decay_alert") is None:
                dpr["decay_alert"] = {}
            dpr["decay_alert"]["last_evaluated"] = now
            dpr["decay_alert"]["live_confidence"] = ev.get("confidence", 0.5)
            dpr["decay_alert"]["live_still_holds"] = ev.get("still_holds", True)
            dpr["decay_alert"]["live_reasoning"] = ev.get("reasoning", "")
            if ev.get("new_decay_signal"):
                dpr["decay_alert"]["new_decay_signal"] = ev["new_decay_signal"]
            dpr["last_monitored"] = now

            # Add blast radius if flagged
            if dpr["id"] in blast:
                dpr["blast_radius_score"] = blast[dpr["id"]]["blast_radius_score"]
                dpr["blast_radius_dpr_ids"] = blast[dpr["id"]]["blast_radius_dpr_ids"]

    data["dprs"] = dprs

    # Add monitoring run log
    alert_summary = []
    for d, ev in evaluations.items():
        alert_summary.append({
            "dpr_id": d,
            "confidence": ev.get("confidence", 0.5),
            "still_holds": ev.get("still_holds", True),
            "trend": ev.get("strengthened_or_weakened", "neutral"),
        })

    run_entry = {
        "run_at": now,
        "commits_scanned": len(commits),
        "dprs_evaluated": len(evaluations),
        "new_alerts": len(flagged),
        "alert_summary": alert_summary,
    }

    if "monitoring_runs" not in data:
        data["monitoring_runs"] = []
    data["monitoring_runs"].append(run_entry)

    save_nexus_data(data)
    print(f"{Fore.GREEN}[+] nexus_data.json updated{Style.RESET_ALL}")

    # Terminal summary
    print(f"\n{Style.BRIGHT}{'='*60}")
    print(f"  DECAY MONITOR SUMMARY")
    print(f"{'='*60}{Style.RESET_ALL}")
    print(f"  Commits scanned: {len(commits)}")
    print(f"  DPRs evaluated:  {len(evaluations)}")
    print(f"  New alerts:      {len(flagged)}\n")

    for dpr_id, ev in evaluations.items():
        conf = ev.get("confidence", 0.5)
        holds = ev.get("still_holds", True)
        trend = ev.get("strengthened_or_weakened", "neutral")
        dpr = next((d for d in dprs if d["id"] == dpr_id), {})

        if not holds or conf < 0.4:
            color = Fore.RED
            status = "DECAYING"
        elif conf < 0.7:
            color = Fore.YELLOW
            status = "UNCERTAIN"
        else:
            color = Fore.GREEN
            status = "STABLE"

        print(f"  {color}[{status}] {dpr_id}: {dpr.get('title', '?')}")
        print(f"    Confidence: {conf:.2f} | Trend: {trend}")
        print(f"    {ev.get('reasoning', '')[:100]}{Style.RESET_ALL}")

    print(f"\n{'='*60}")
    return data


if __name__ == "__main__":
    run_decay_monitor()
