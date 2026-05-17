"""
Nexus Layer 2 - nexus_data.json Builder
Merges Layer 1 JSON + Neo4j graph into a single dashboard-optimized JSON.
IDEMPOTENT: Running multiple times preserves existing data.
"""

import os, sys, json, time
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

from neo4j import GraphDatabase

# ── Paths ──────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
L1_JSON = PROJECT_ROOT / "postgres-analysis" / "output" / "nexus_layer1_dprs.json"
OUTPUT_JSON = SCRIPT_DIR / "nexus_data.json"
NEO4J_URI = "bolt://localhost:7687"


def load_layer1():
    with open(L1_JSON, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    return raw["nexus_layer1_output"]


def query_neo4j(driver, cypher, params=None):
    try:
        with driver.session() as s:
            return [dict(r) for r in s.run(cypher, **(params or {}))]
    except Exception as e:
        print(f"  [!] Neo4j query error: {e}")
        return []


def get_causal_edges(driver, dpr_id):
    """Get inbound and outbound causal edges for a DPR."""
    out_q = """
        MATCH (d:DPR {dpr_id: $id})-[r]->(t:DPR)
        RETURN t.dpr_id as target, type(r) as rel
    """
    in_q = """
        MATCH (s:DPR)-[r]->(d:DPR {dpr_id: $id})
        RETURN s.dpr_id as source, type(r) as rel
    """
    causal_out = [r["target"] for r in query_neo4j(driver, out_q, {"id": dpr_id})
                  if r.get("target")]
    causal_in = [r["source"] for r in query_neo4j(driver, in_q, {"id": dpr_id})
                 if r.get("source")]
    return list(set(causal_in)), list(set(causal_out))


def get_graph_stats(driver):
    stats = query_neo4j(driver, "MATCH (n) RETURN count(n) as nodes")
    rels = query_neo4j(driver, "MATCH ()-[r]->() RETURN count(r) as rels")
    return (
        stats[0]["nodes"] if stats else 0,
        rels[0]["rels"] if rels else 0,
    )


def get_all_ctg_edges(driver):
    q = """
        MATCH (a:DPR)-[r]->(b:DPR)
        RETURN a.dpr_id as from_id, b.dpr_id as to_id,
               type(r) as rel_type, r.explanation as explanation
    """
    rows = query_neo4j(driver, q)
    edges = []
    for r in rows:
        edges.append({
            "from": r["from_id"],
            "to": r["to_id"],
            "type": r["rel_type"],
            "explanation": r.get("explanation", ""),
        })
    return edges


def build_nexus_data():
    print("=" * 60)
    print("  NEXUS - Building nexus_data.json")
    print("=" * 60)

    # ── Load existing data (idempotent) ────────────────────
    existing = {}
    if OUTPUT_JSON.exists():
        print(f"[*] Loading existing nexus_data.json...")
        with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
            existing = json.load(f)

    # ── Load Layer 1 ───────────────────────────────────────
    print(f"[*] Loading Layer 1 from {L1_JSON.name}...")
    l1 = load_layer1()
    dprs_raw = l1["dprs"]
    edges_raw = l1["ctg_edges"]
    alerts_raw = l1["assumption_decay_prescan"]

    # ── Connect Neo4j ──────────────────────────────────────
    driver = None
    total_nodes, total_rels = 0, 0
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=None)
        driver.verify_connectivity()
        print("[+] Neo4j connected")
        total_nodes, total_rels = get_graph_stats(driver)
        print(f"    Nodes: {total_nodes}, Relationships: {total_rels}")
    except Exception as e:
        print(f"[!] Neo4j unavailable: {e}")
        total_nodes = len(dprs_raw)
        total_rels = len(edges_raw)

    # ── Build meta ─────────────────────────────────────────
    meta = {
        "repository": l1["repository"],
        "analysis_window": l1["analysis_window"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_dprs": len(dprs_raw),
        "total_nodes": total_nodes,
        "total_relationships": total_rels,
    }

    # ── Build DPR entries ──────────────────────────────────
    alert_map = {}
    for a in alerts_raw:
        alert_map[a["dpr_id"]] = {
            "already_decaying": a["already_decaying"],
            "decay_evidence": a["decay_evidence"],
            "earliest_signal_date": a["earliest_signal_date"],
            "recommended_monitor_query": a["recommended_monitor_query"],
        }

    dprs = []
    for d in dprs_raw:
        dpr_id = d["dpr_id"]

        # Get causal edges from Neo4j if available
        causal_in, causal_out = [], []
        if driver:
            causal_in, causal_out = get_causal_edges(driver, dpr_id)
        else:
            # Fallback: derive from L1 edges
            for e in edges_raw:
                if e["from_dpr"] == dpr_id:
                    causal_out.append(e["to_dpr"])
                if e["to_dpr"] == dpr_id:
                    causal_in.append(e["from_dpr"])
            causal_in = list(set(causal_in))
            causal_out = list(set(causal_out))

        dprs.append({
            "id": dpr_id,
            "title": d["title"],
            "component": d["component"],
            "blast_radius": d["blast_radius_estimate"],
            "decay_risk": d["assumption_decay_risk"],
            "within_window": d["within_window"],
            "decision_date": d["decision_date"],
            "decision": d["decision"],
            "implicit_assumptions": d["implicit_assumptions"],
            "explicit_constraints": d["explicit_constraints"],
            "active_workarounds": d["active_workarounds"],
            "files_involved": d["files_involved"],
            "involved_humans": d["involved_humans"],
            "rejected_alternatives": d.get("rejected_alternatives", []),
            "intended_durability": d.get("intended_durability", ""),
            "durability_reasoning": d.get("durability_reasoning", ""),
            "decay_risk_reasoning": d.get("decay_risk_reasoning", ""),
            "blast_radius_reasoning": d.get("blast_radius_reasoning", ""),
            "commit_refs": d.get("commit_refs", []),
            "causal_dependencies": d.get("causal_dependencies", []),
            "causal_in": causal_in,
            "causal_out": causal_out,
            "decay_alert": alert_map.get(dpr_id, None),
        })

    # ── Build CTG edges (merge Neo4j + L1 for full explanations) ──
    ctg_edges = []
    # Build a lookup of L1 edge explanations
    l1_edge_map = {}
    for e in edges_raw:
        key = (e["from_dpr"], e["to_dpr"], e["relationship"])
        l1_edge_map[key] = e["explanation"]

    if driver:
        neo4j_edges = get_all_ctg_edges(driver)
        seen = set()
        for e in neo4j_edges:
            key = (e["from"], e["to"], e["type"])
            expl = e.get("explanation") or l1_edge_map.get(key, "")
            ctg_edges.append({"from": e["from"], "to": e["to"], "type": e["type"], "explanation": expl})
            seen.add((e["from"], e["to"]))
        # Add L1-only edges
        for e in edges_raw:
            if (e["from_dpr"], e["to_dpr"]) not in seen:
                ctg_edges.append({"from": e["from_dpr"], "to": e["to_dpr"],
                                  "type": e["relationship"], "explanation": e["explanation"]})
    else:
        for e in edges_raw:
            ctg_edges.append({"from": e["from_dpr"], "to": e["to_dpr"],
                              "type": e["relationship"], "explanation": e["explanation"]})

    # ── Build decay alerts ─────────────────────────────────
    decay_alerts = []
    for a in alerts_raw:
        dpr_match = next((d for d in dprs_raw if d["dpr_id"] == a["dpr_id"]), None)
        decay_alerts.append({
            "dpr_id": a["dpr_id"],
            "title": dpr_match["title"] if dpr_match else "",
            "component": dpr_match["component"] if dpr_match else "",
            "blast_radius": dpr_match["blast_radius_estimate"] if dpr_match else "",
            "already_decaying": a["already_decaying"],
            "decay_evidence": a["decay_evidence"],
            "earliest_signal_date": a["earliest_signal_date"],
            "recommended_monitor_query": a["recommended_monitor_query"],
        })

    # ── Assemble (preserving existing populated fields) ────
    output = {
        "meta": meta,
        "dprs": dprs,
        "ctg_edges": ctg_edges,
        "decay_alerts": decay_alerts,
        "knowledge_concentration": existing.get("knowledge_concentration", {}),
        "counterfactual_traces": existing.get("counterfactual_traces", []),
        "risk_forecast": existing.get("risk_forecast", {}),
        "org_risk_score": existing.get("org_risk_score", 0),
        "monitoring_runs": existing.get("monitoring_runs", []),
    }

    # ── Write ──────────────────────────────────────────────
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    size = OUTPUT_JSON.stat().st_size
    print(f"\n[+] Written: {OUTPUT_JSON}")
    print(f"    Size: {size:,} bytes")
    print(f"    DPRs: {len(dprs)}")
    print(f"    CTG Edges: {len(ctg_edges)}")
    print(f"    Decay Alerts: {len(decay_alerts)}")
    print(f"    Preserved keys: knowledge_concentration, counterfactual_traces, risk_forecast")

    if driver:
        driver.close()

    return output


if __name__ == "__main__":
    build_nexus_data()
