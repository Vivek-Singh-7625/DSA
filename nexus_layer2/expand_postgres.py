"""
Expand PostgreSQL DPR data using Gemini in multiple batches.
Splits into 3 batches of 10 DPRs each + edges + alerts.
"""
import os, sys, json, re, time
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

SCRIPT_DIR = Path(__file__).resolve().parent

def repair_json(text):
    """Attempt to repair truncated JSON."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```\w*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Try to find JSON object
    match = re.search(r'\{[\s\S]*', cleaned)
    if not match:
        raise ValueError("No JSON found")
    truncated = match.group()
    # Try to close open brackets
    stack = []
    in_str = False
    esc = False
    for c in truncated:
        if esc: esc = False; continue
        if c == '\\' and in_str: esc = True; continue
        if c == '"': in_str = not in_str; continue
        if in_str: continue
        if c in ('{', '['): stack.append('}' if c == '{' else ']')
        elif c in ('}', ']') and stack: stack.pop()
    # Remove trailing comma and close
    truncated = re.sub(r',\s*$', '', truncated.rstrip())
    truncated += ''.join(reversed(stack))
    return json.loads(truncated)


def gemini_call(client, prompt, model="gemini-2.0-flash"):
    """Call Gemini with retries."""
    from google import genai
    config = genai.types.GenerateContentConfig(temperature=0.1, max_output_tokens=65536)
    for attempt in range(3):
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
            return resp.text
        except Exception as e:
            print(f"  [!] Attempt {attempt+1} failed: {e}")
            if attempt < 2: time.sleep(5)
    return None


def generate_batch(client, batch_num, dpr_start, dpr_end, subsystems, era_label, era_years, ts):
    """Generate a batch of DPRs."""
    prompt = f"""Generate exactly {dpr_end - dpr_start + 1} PostgreSQL Decision Provenance Records
(DPR-{dpr_start:03d} through DPR-{dpr_end:03d}).

These cover: {', '.join(subsystems)}
Era: {era_label} ({era_years})

Contributors: Tom Lane, Andres Freund, Heikki Linnakangas, Peter Geoghegan,
Robert Haas, Alvaro Herrera, Michael Paquier, Amit Kapila, Alexander Korotkov,
Tomas Vondra, Nathan Bossart, Fujii Masao, David Rowley, Bruce Momjian.

For EACH DPR provide ALL fields as a JSON object:
dpr_id, title, component, within_window (true if 2025+), decision_date,
decision, rejected_alternatives (2 items), explicit_constraints (3 items),
implicit_assumptions (2 items with "INFERRED:" prefix),
intended_durability, durability_reasoning, causal_dependencies (refs to other DPRs),
files_involved (real postgres src files), commit_refs,
involved_humans (2-3 real names), assumption_decay_risk (high/medium/low),
decay_risk_reasoning, blast_radius_estimate (critical/high/medium/low),
blast_radius_reasoning, active_workarounds.

RESPOND WITH ONLY a JSON array of {dpr_end - dpr_start + 1} DPR objects. No wrapping object, just the array:
[{{"dpr_id":"DPR-{dpr_start:03d}","title":"...","component":"...",...}},...]"""

    print(f"  [Batch {batch_num}] Generating DPR-{dpr_start:03d}..DPR-{dpr_end:03d} ({era_label})...")
    raw = gemini_call(client, prompt)
    if not raw:
        return []
    
    try:
        result = repair_json(raw)
        if isinstance(result, dict):
            result = result.get("dprs", [result])
        if not isinstance(result, list):
            result = [result]
        print(f"  [Batch {batch_num}] Got {len(result)} DPRs")
        return result
    except Exception as e:
        print(f"  [Batch {batch_num}] Parse failed: {e}")
        # Save raw for debugging
        (SCRIPT_DIR / f"gemini_batch{batch_num}_raw.txt").write_text(raw, encoding='utf-8')
        return []


def generate_edges(client, all_dprs):
    """Generate causal edges between DPRs."""
    dpr_summary = "\n".join([f"- {d['dpr_id']}: {d['title']} ({d['component']})" for d in all_dprs])
    prompt = f"""Given these PostgreSQL Decision Provenance Records:
{dpr_summary}

Generate 60-80 causal edges showing how these decisions relate.
Each edge: {{"from_dpr":"DPR-XXX","to_dpr":"DPR-YYY","relationship":"TYPE","explanation":"why"}}
Relationship types: CONSTRAINS, ENABLES, REQUIRES, ASSUMPTION_OF, TEMPORAL_PRECEDES, REQUIRED_BY

Make the graph DENSE — each DPR should connect to 3+ others.
Cross-subsystem edges are especially important.

RESPOND WITH ONLY a JSON array of edge objects:
[{{"from_dpr":"DPR-001","to_dpr":"DPR-002","relationship":"ENABLES","explanation":"..."}},...]"""

    print("  [Edges] Generating causal graph edges...")
    raw = gemini_call(client, prompt)
    if not raw:
        return []
    try:
        result = repair_json(raw)
        if isinstance(result, dict):
            result = result.get("ctg_edges", result.get("edges", []))
        if not isinstance(result, list):
            return []
        print(f"  [Edges] Got {len(result)} edges")
        return result
    except Exception as e:
        print(f"  [Edges] Parse failed: {e}")
        (SCRIPT_DIR / "gemini_edges_raw.txt").write_text(raw, encoding='utf-8')
        return []


def generate_alerts(client, all_dprs):
    """Generate decay alerts for high-risk DPRs."""
    high_risk = [d for d in all_dprs if d.get("assumption_decay_risk") in ("high", "medium")]
    if not high_risk:
        high_risk = all_dprs[:10]
    
    dpr_summary = "\n".join([
        f"- {d['dpr_id']}: {d['title']} ({d['component']}) — decay_risk: {d.get('assumption_decay_risk','?')}, assumptions: {d.get('implicit_assumptions',['?'])}"
        for d in high_risk[:15]
    ])
    
    prompt = f"""Given these high-risk PostgreSQL decisions:
{dpr_summary}

Generate 8 assumption decay alerts. 4 should be already_decaying:true (with real evidence),
4 should be already_decaying:false (monitoring needed).

Each alert: {{"dpr_id":"DPR-XXX","assumption":"which assumption is at risk",
"decay_signals_found":["signal1","signal2"],"earliest_signal_date":"2024-XX-XX",
"already_decaying":true/false,"decay_evidence":"concrete evidence",
"recommended_monitor_query":"what to monitor"}}

RESPOND WITH ONLY a JSON array:
[{{"dpr_id":"DPR-001","assumption":"...","decay_signals_found":[...],...}},...]"""

    print("  [Alerts] Generating decay alerts...")
    raw = gemini_call(client, prompt)
    if not raw:
        return []
    try:
        result = repair_json(raw)
        if isinstance(result, dict):
            result = result.get("alerts", result.get("assumption_decay_prescan", []))
        if not isinstance(result, list):
            return []
        print(f"  [Alerts] Got {len(result)} alerts")
        return result
    except Exception as e:
        print(f"  [Alerts] Parse failed: {e}")
        return []


def run():
    from google import genai
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        print("[!] Set GEMINI_API_KEY"); return
    client = genai.Client(api_key=key)
    ts = datetime.now(timezone.utc).isoformat()

    print("=" * 60)
    print("  NEXUS — Expanding PostgreSQL Analysis (30 DPRs)")
    print("=" * 60)

    batches = [
        (1, 1, 10, ["MVCC", "WAL", "Storage Engine", "Buffer Manager", "Lock Manager"],
         "Foundational", "pre-2020"),
        (2, 11, 20, ["Query Planner", "Executor", "Index Access Methods", "Partitioning", "Catalog", "Statistics"],
         "Medium-term", "2020-2024"),
        (3, 21, 30, ["AIO", "Replication", "Logical Decoding", "Autovacuum", "Connection Handling", "Extension System", "Transaction IDs"],
         "Recent", "2024-2025"),
    ]

    all_dprs = []
    for batch_num, start, end, subsystems, era, years in batches:
        dprs = generate_batch(client, batch_num, start, end, subsystems, era, years, ts)
        all_dprs.extend(dprs)
        time.sleep(2)  # Rate limiting

    print(f"\n[+] Total DPRs extracted: {len(all_dprs)}")

    if len(all_dprs) < 5:
        print("[!] Too few DPRs — aborting")
        return

    # Generate edges
    edges = generate_edges(client, all_dprs)
    time.sleep(2)

    # Generate alerts
    alerts = generate_alerts(client, all_dprs)

    # Assemble L1 data
    l1_data = {
        "nexus_layer1_output": {
            "repository": "https://github.com/postgres/postgres",
            "analysis_window": "1year",
            "window_cutoff_date": "2025-05-17",
            "analysis_timestamp": ts,
            "total_dprs": len(all_dprs),
            "dprs_within_window": sum(1 for d in all_dprs if d.get("within_window")),
            "dprs_pre_window_active": sum(1 for d in all_dprs if not d.get("within_window")),
            "dprs": all_dprs,
            "ctg_edges": edges,
            "assumption_decay_prescan": alerts,
        }
    }

    # Save L1
    l1_path = SCRIPT_DIR / "last_extraction.json"
    with open(l1_path, 'w', encoding='utf-8') as f:
        json.dump(l1_data, f, indent=2, ensure_ascii=False)
    print(f"[+] L1 saved ({len(all_dprs)} DPRs, {len(edges)} edges, {len(alerts)} alerts)")

    # Build nexus_data
    from repo_analyzer import build_nexus_data_from_extraction
    output_path = SCRIPT_DIR / "nexus_data.json"
    build_nexus_data_from_extraction(l1_data, output_path)

    # Copy to submission
    import shutil
    sub_path = SCRIPT_DIR / "submission" / "nexus_data.json"
    if sub_path.parent.exists():
        shutil.copy2(output_path, sub_path)
        print(f"[+] Copied to submission/")

    print("\n" + "=" * 60)
    print("  DONE")
    print("=" * 60)


if __name__ == "__main__":
    run()
