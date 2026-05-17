"""
Nexus Layer 4 - Counterfactual Simulation Engine
"What if decision X had gone differently?" — Traces causal consequences.
Uses Gemini + graph traversal to generate alternate-timeline projections.
"""

import os, sys, json, time
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

try:
    from google import genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False

SCRIPT_DIR = Path(__file__).resolve().parent
NEXUS_DATA = SCRIPT_DIR / "nexus_data.json"
GEMINI_MODEL = "gemini-2.5-flash"


def load_nexus_data():
    with open(NEXUS_DATA, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_nexus_data(data):
    with open(NEXUS_DATA, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def build_graph(ctg_edges):
    G = nx.DiGraph() if HAS_NX else None
    if G:
        for e in ctg_edges:
            G.add_edge(e["from"], e["to"], type=e.get("type", ""), explanation=e.get("explanation", ""))
    return G


def get_downstream(G, dpr_id):
    if not G or dpr_id not in G:
        return []
    return sorted(list(nx.descendants(G, dpr_id)))


def get_upstream(G, dpr_id):
    if not G or dpr_id not in G:
        return []
    return sorted(list(nx.ancestors(G, dpr_id)))


def setup_gemini():
    if not HAS_GEMINI:
        return None
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return None
    return genai.Client(api_key=key)


# ── PREDEFINED COUNTERFACTUAL SCENARIOS ────────────────────
SCENARIOS = [
    {
        "id": "CF-001",
        "target_dpr": "DPR-001",
        "alternative": "16KB page size instead of 8KB",
        "question": "What if PostgreSQL used 16KB pages from the start?",
    },
    {
        "id": "CF-002",
        "target_dpr": "DPR-003",
        "alternative": "Undo-log MVCC instead of heap-based tuple versioning",
        "question": "What if PostgreSQL used undo logs like Oracle/MySQL InnoDB?",
    },
    {
        "id": "CF-003",
        "target_dpr": "DPR-004",
        "alternative": "64-bit transaction IDs from the beginning",
        "question": "What if XID was always 64-bit, no wraparound risk?",
    },
    {
        "id": "CF-004",
        "target_dpr": "DPR-009",
        "alternative": "Thread-based architecture instead of multi-process",
        "question": "What if PostgreSQL used threads instead of forking processes?",
    },
    {
        "id": "CF-005",
        "target_dpr": "DPR-007",
        "alternative": "Group commit WAL with async replication default",
        "question": "What if WAL defaulted to async group commits?",
    },
]


def simulate_counterfactual(client, scenario, dpr, downstream_dprs, all_dprs):
    """Ask Gemini to trace the ripple effects of an alternative decision."""
    downstream_desc = ""
    for did in downstream_dprs[:8]:
        match = next((d for d in all_dprs if d["id"] == did), None)
        if match:
            downstream_desc += f"  - {did}: {match['title']} (blast_radius: {match.get('blast_radius', 'N/A')})\n"

    prompt = f"""You are a senior PostgreSQL architect reasoning about counterfactual architectural decisions.

ORIGINAL DECISION:
  DPR: {dpr['id']} — {dpr['title']}
  Decision: {dpr['decision']}
  Constraints: {json.dumps(dpr.get('explicit_constraints', []))}

COUNTERFACTUAL SCENARIO:
  Alternative: {scenario['alternative']}
  Question: {scenario['question']}

DOWNSTREAM DPRs THAT WOULD BE AFFECTED:
{downstream_desc or '  None identified'}

For each affected DPR, trace the specific consequences. Then assess:
1. Which assumptions would break?
2. Which workarounds would become unnecessary?
3. What new problems would emerge?
4. Overall: would this alternative be better or worse today?

Return JSON only:
{{
  "verdict": "better" or "worse" or "tradeoff",
  "confidence": 0.0 to 1.0,
  "broken_assumptions": ["list of assumptions that break"],
  "unnecessary_workarounds": ["list of workarounds that become unnecessary"],
  "new_problems": ["list of new problems that emerge"],
  "affected_dprs": [
    {{"dpr_id": "DPR-xxx", "impact": "description of impact"}}
  ],
  "timeline_narrative": "A 3-4 sentence narrative of what the alternate timeline looks like",
  "modern_relevance": "Is this alternative worth revisiting today? Why or why not?"
}}"""

    try:
        config = genai.types.GenerateContentConfig(temperature=0.3)
        resp = client.models.generate_content(
            model=GEMINI_MODEL, contents=prompt, config=config
        )
        text = resp.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        return {
            "verdict": "tradeoff",
            "confidence": 0.5,
            "broken_assumptions": [],
            "unnecessary_workarounds": [],
            "new_problems": [f"Analysis unavailable: {str(e)[:80]}"],
            "affected_dprs": [],
            "timeline_narrative": "Counterfactual analysis could not be completed.",
            "modern_relevance": "Requires further analysis."
        }


def run_counterfactual_engine():
    print("=" * 60)
    print("  NEXUS - Counterfactual Simulation Engine (Layer 4)")
    print("=" * 60)

    data = load_nexus_data()
    dprs = data["dprs"]
    ctg_edges = data.get("ctg_edges", [])
    G = build_graph(ctg_edges)

    client = setup_gemini()
    if not client:
        print("[!] Gemini unavailable — counterfactuals will use placeholder data")

    traces = []
    for scenario in SCENARIOS:
        target_id = scenario["target_dpr"]
        dpr = next((d for d in dprs if d["id"] == target_id), None)
        if not dpr:
            print(f"  [!] {target_id} not found, skipping {scenario['id']}")
            continue

        downstream = get_downstream(G, target_id) if G else dpr.get("causal_out", [])
        upstream = get_upstream(G, target_id) if G else dpr.get("causal_in", [])

        print(f"\n  [{scenario['id']}] {scenario['question']}")
        print(f"    Target: {target_id} ({dpr['title']})")
        print(f"    Downstream: {len(downstream)} DPRs | Upstream: {len(upstream)} DPRs")

        if client:
            result = simulate_counterfactual(client, scenario, dpr, downstream, dprs)
            time.sleep(2)  # Rate limit
        else:
            result = {
                "verdict": "tradeoff", "confidence": 0.5,
                "broken_assumptions": ["Analysis pending"],
                "unnecessary_workarounds": [], "new_problems": [],
                "affected_dprs": [{"dpr_id": d, "impact": "pending"} for d in downstream[:3]],
                "timeline_narrative": "Counterfactual analysis requires Gemini.",
                "modern_relevance": "Pending."
            }

        trace = {
            "id": scenario["id"],
            "target_dpr": target_id,
            "alternative": scenario["alternative"],
            "question": scenario["question"],
            "downstream_count": len(downstream),
            "upstream_count": len(upstream),
            "downstream_dprs": downstream,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "result": result,
        }
        traces.append(trace)

        verdict = result.get("verdict", "?")
        conf = result.get("confidence", 0)
        print(f"    Verdict: {verdict.upper()} (confidence: {conf:.2f})")
        print(f"    Narrative: {result.get('timeline_narrative', '')[:120]}")

    # Write back
    data["counterfactual_traces"] = traces
    save_nexus_data(data)

    print(f"\n{'='*60}")
    print(f"  [+] {len(traces)} counterfactual traces written to nexus_data.json")
    print(f"{'='*60}")
    return traces


if __name__ == "__main__":
    run_counterfactual_engine()
