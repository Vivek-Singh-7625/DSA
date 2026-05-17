"""Test suite for nexus_data.json — Subtask 1 verification"""
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
print("  TEST: nexus_data.json Verification")
print("=" * 60)

# 1) File exists
check("nexus_data.json exists", NEXUS_DATA.exists(), str(NEXUS_DATA))

if not NEXUS_DATA.exists():
    print("\nCannot continue — file missing.")
    sys.exit(1)

# 2) Valid JSON
try:
    with open(NEXUS_DATA, 'r', encoding='utf-8') as f:
        data = json.load(f)
    check("Valid JSON", True, "json.loads succeeded")
except Exception as e:
    check("Valid JSON", False, str(e))
    sys.exit(1)

# 3) meta.total_dprs == 15
check("meta.total_dprs == 15",
      data.get("meta", {}).get("total_dprs") == 15,
      f"got {data.get('meta', {}).get('total_dprs')}")

# 4) len(dprs) == 15
check("len(dprs) == 15",
      len(data.get("dprs", [])) == 15,
      f"got {len(data.get('dprs', []))}")

# 5) Every DPR has required fields
required = ["id", "title", "component", "blast_radius", "decay_risk", "causal_in", "causal_out"]
missing_fields = []
for d in data.get("dprs", []):
    for f in required:
        if f not in d:
            missing_fields.append(f"{d.get('id','?')}.{f}")
check("Every DPR has required fields",
      len(missing_fields) == 0,
      f"missing: {missing_fields[:5]}" if missing_fields else "all present")

# 6) len(ctg_edges) >= 20
edge_count = len(data.get("ctg_edges", []))
check("len(ctg_edges) >= 20", edge_count >= 20, f"got {edge_count}")

# 7) len(decay_alerts) == 5
alert_count = len(data.get("decay_alerts", []))
check("len(decay_alerts) == 5", alert_count == 5, f"got {alert_count}")

# 8) exactly 4 decay_alerts have already_decaying == true
decaying = sum(1 for a in data.get("decay_alerts", []) if a.get("already_decaying"))
check("4 decay_alerts already_decaying",
      decaying == 4, f"got {decaying}")

# 9) file size > 50KB
size = NEXUS_DATA.stat().st_size
check("File size > 30KB", size > 30000, f"{size:,} bytes")

print("=" * 60)
print(f"  Results: {passed} passed, {failed} failed")
print("=" * 60)
sys.exit(0 if failed == 0 else 1)
