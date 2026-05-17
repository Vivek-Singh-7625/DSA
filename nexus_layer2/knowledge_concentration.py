"""
Nexus Layer 4 - Knowledge Concentration & SPOF Analysis
Identifies organizational single points of failure (bus factor risk).
Analyzes which humans/components concentrate critical knowledge.
"""

import os, sys, json
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False

SCRIPT_DIR = Path(__file__).resolve().parent
NEXUS_DATA = SCRIPT_DIR / "nexus_data.json"


def load_nexus_data():
    with open(NEXUS_DATA, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_nexus_data(data):
    with open(NEXUS_DATA, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def analyze_human_concentration(dprs):
    """Analyze which humans concentrate knowledge across critical DPRs."""
    human_dprs = defaultdict(list)
    human_components = defaultdict(set)
    human_blast = defaultdict(list)

    for dpr in dprs:
        for h in dpr.get("involved_humans", []):
            human_dprs[h].append(dpr["id"])
            human_components[h].add(dpr.get("component", ""))
            blast = dpr.get("blast_radius", "low")
            blast_score = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(blast, 1)
            human_blast[h].append(blast_score)

    profiles = []
    for human, dpr_ids in human_dprs.items():
        avg_blast = sum(human_blast[human]) / max(len(human_blast[human]), 1)
        components = sorted(list(human_components[human]))
        # Bus factor: unique components * critical DPRs
        bus_factor_risk = len(components) * len(dpr_ids) * avg_blast
        profiles.append({
            "name": human,
            "dpr_count": len(dpr_ids),
            "dprs": sorted(dpr_ids),
            "components": components,
            "component_count": len(components),
            "avg_blast_score": round(avg_blast, 2),
            "bus_factor_risk_score": round(bus_factor_risk, 2),
        })

    profiles.sort(key=lambda x: x["bus_factor_risk_score"], reverse=True)
    return profiles


def analyze_component_concentration(dprs):
    """Analyze which components concentrate risk."""
    component_data = defaultdict(lambda: {
        "dprs": [], "humans": set(), "decay_risks": [], "blast_radii": []
    })

    for dpr in dprs:
        comp = dpr.get("component", "Unknown")
        component_data[comp]["dprs"].append(dpr["id"])
        for h in dpr.get("involved_humans", []):
            component_data[comp]["humans"].add(h)
        component_data[comp]["decay_risks"].append(dpr.get("decay_risk", "low"))
        component_data[comp]["blast_radii"].append(dpr.get("blast_radius", "low"))

    results = []
    risk_map = {"critical": 4, "high": 3, "medium": 2, "low": 1}

    for comp, info in component_data.items():
        avg_decay = sum(risk_map.get(r, 1) for r in info["decay_risks"]) / max(len(info["decay_risks"]), 1)
        avg_blast = sum(risk_map.get(r, 1) for r in info["blast_radii"]) / max(len(info["blast_radii"]), 1)
        unique_humans = len(info["humans"])
        dpr_count = len(info["dprs"])

        # SPOF score: higher if few humans and high blast/decay
        spof_score = (avg_blast * avg_decay * dpr_count) / max(unique_humans, 1)

        results.append({
            "component": comp,
            "dpr_count": dpr_count,
            "dprs": sorted(info["dprs"]),
            "unique_humans": unique_humans,
            "humans": sorted(list(info["humans"])),
            "avg_decay_risk": round(avg_decay, 2),
            "avg_blast_radius": round(avg_blast, 2),
            "spof_score": round(spof_score, 2),
        })

    results.sort(key=lambda x: x["spof_score"], reverse=True)
    return results


def analyze_file_concentration(dprs):
    """Analyze which files are touched by most critical DPRs."""
    file_dprs = defaultdict(list)
    file_blast = defaultdict(list)

    for dpr in dprs:
        for f in dpr.get("files_involved", []):
            file_dprs[f].append(dpr["id"])
            blast = dpr.get("blast_radius", "low")
            blast_score = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(blast, 1)
            file_blast[f].append(blast_score)

    results = []
    for f, dpr_ids in file_dprs.items():
        avg_blast = sum(file_blast[f]) / max(len(file_blast[f]), 1)
        results.append({
            "file": f,
            "dpr_count": len(dpr_ids),
            "dprs": sorted(dpr_ids),
            "avg_blast_score": round(avg_blast, 2),
            "criticality_score": round(len(dpr_ids) * avg_blast, 2),
        })

    results.sort(key=lambda x: x["criticality_score"], reverse=True)
    return results


def compute_org_risk_score(human_profiles, component_profiles):
    """Compute an overall organizational risk score 0-100."""
    if not human_profiles or not component_profiles:
        return 0

    # Factor 1: Top contributor concentration (Gini-like)
    total_dprs = sum(h["dpr_count"] for h in human_profiles)
    top_dprs = human_profiles[0]["dpr_count"] if human_profiles else 0
    concentration = top_dprs / max(total_dprs, 1)

    # Factor 2: Average component SPOF
    avg_spof = sum(c["spof_score"] for c in component_profiles) / max(len(component_profiles), 1)

    # Factor 3: Bus factor (how many people need to leave to lose coverage)
    components_with_one = sum(1 for c in component_profiles if c["unique_humans"] <= 2)
    bus_factor_ratio = components_with_one / max(len(component_profiles), 1)

    # Weighted composite
    score = (concentration * 30) + (min(avg_spof / 10, 1) * 40) + (bus_factor_ratio * 30)
    return round(min(score, 100), 1)


def run_knowledge_concentration():
    print("=" * 60)
    print("  NEXUS - Knowledge Concentration & SPOF Analysis")
    print("=" * 60)

    data = load_nexus_data()
    dprs = data["dprs"]

    # Human concentration
    print("\n[1] Analyzing human knowledge concentration...")
    human_profiles = analyze_human_concentration(dprs)
    for h in human_profiles[:5]:
        print(f"    {h['name']}: {h['dpr_count']} DPRs, "
              f"{h['component_count']} components, "
              f"bus_factor_risk={h['bus_factor_risk_score']:.1f}")

    # Component concentration
    print("\n[2] Analyzing component SPOF risk...")
    component_profiles = analyze_component_concentration(dprs)
    for c in component_profiles:
        print(f"    {c['component']}: {c['dpr_count']} DPRs, "
              f"{c['unique_humans']} humans, SPOF={c['spof_score']:.1f}")

    # File concentration
    print("\n[3] Analyzing file criticality...")
    file_profiles = analyze_file_concentration(dprs)
    for f in file_profiles[:5]:
        print(f"    {f['file']}: {f['dpr_count']} DPRs, "
              f"criticality={f['criticality_score']:.1f}")

    # Org risk score
    org_score = compute_org_risk_score(human_profiles, component_profiles)
    print(f"\n[4] Overall Organizational Risk Score: {org_score}/100")

    # Write back
    data["knowledge_concentration"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "human_profiles": human_profiles,
        "component_profiles": component_profiles,
        "file_profiles": file_profiles[:15],
        "top_spof_humans": [h["name"] for h in human_profiles[:3]],
        "top_spof_components": [c["component"] for c in component_profiles[:3]],
    }
    data["org_risk_score"] = org_score
    save_nexus_data(data)

    print(f"\n{'='*60}")
    print(f"  [+] Knowledge concentration analysis written to nexus_data.json")
    print(f"{'='*60}")
    return data


if __name__ == "__main__":
    run_knowledge_concentration()
