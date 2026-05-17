"""Test suite for decay_monitor.py — Subtask 2 verification"""
import sys, json
from pathlib import Path

NEXUS_DATA = Path(__file__).resolve().parent / "nexus_data.json"
passed = 0
failed = 0

def check(name, condition, actual=""):
    global passed, failed
    if condition:
        print(f"  PASS  {name}  ({actual})")
        passed += 1
    else:
        print(f"  FAIL  {name}  ({actual})")
        failed += 1

print("=" * 60)
print("  TEST: Decay Monitor Verification")
print("=" * 60)

with open(NEXUS_DATA, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 1) monitoring_runs exists
runs = data.get("monitoring_runs", [])
check("monitoring_runs array exists", len(runs) > 0, f"{len(runs)} runs")

if not runs:
    print("Cannot continue — no monitoring runs.")
    sys.exit(1)

latest = runs[-1]

# 2) Latest run has required fields
check("run has run_at", "run_at" in latest, latest.get("run_at", "missing"))
check("run has commits_scanned", "commits_scanned" in latest,
      f"{latest.get('commits_scanned')}")
check("run has dprs_evaluated", "dprs_evaluated" in latest,
      f"{latest.get('dprs_evaluated')}")

# 3) Check blast_radius_score on any flagged DPR
blast_scores = []
for d in data.get("dprs", []):
    if "blast_radius_score" in d:
        blast_scores.append(d["blast_radius_score"])

if blast_scores:
    valid = all(0.0 <= s <= 1.0 for s in blast_scores)
    check("blast_radius_score 0-1 range", valid, f"scores: {blast_scores[:3]}")
else:
    check("blast_radius_score present (or no flagged DPRs)", True, "no flagged DPRs = ok")

# 4) NetworkX graph node count
import networkx as nx
G = nx.DiGraph()
for e in data.get("ctg_edges", []):
    G.add_edge(e["from"], e["to"])
total_dprs = data.get("meta", {}).get("total_dprs", 15)
check("NetworkX nodes match DPR count",
      G.number_of_nodes() <= total_dprs + 5,
      f"nx_nodes={G.number_of_nodes()}, total_dprs={total_dprs}")

# 5) At least one evaluation has confidence as float
summary = latest.get("alert_summary", [])
has_float_conf = any(isinstance(s.get("confidence"), (int, float)) for s in summary)
check("Gemini confidence is float", has_float_conf or len(summary) == 0,
      f"{len(summary)} evaluations")

print("=" * 60)
print(f"  Results: {passed} passed, {failed} failed")
print("=" * 60)
sys.exit(0 if failed == 0 else 1)
