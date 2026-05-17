"""
Nexus Layer 7 - Submission Package Generator
Creates all artifacts needed for lablab.ai hackathon submission.
Generates: README, architecture diagram data, demo script, and package.
"""

import sys, json, os, shutil
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
NEXUS_DATA = SCRIPT_DIR / "nexus_data.json"
SUBMISSION_DIR = SCRIPT_DIR / "submission"


def load_nexus_data():
    with open(NEXUS_DATA, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_readme(data):
    meta = data.get("meta", {})
    dprs = data.get("dprs", [])
    kc = data.get("knowledge_concentration", {})
    traces = data.get("counterfactual_traces", [])
    alerts = data.get("decay_alerts", [])

    # Precompute values for f-string
    monitored_count = sum(1 for d in dprs if (d.get('decay_alert') or {}).get('live_confidence') is not None)
    verdicts_list = ', '.join(t.get('result', {}).get('verdict', '?') for t in traces)

    readme = f"""# NEXUS — Causal Intelligence Platform for Software Architecture

> **Revealing the invisible causal web beneath your codebase**

## 🎯 What is Nexus?

Nexus is a 5-layer causal intelligence engine that extracts, models, and monitors
architectural **Decision Provenance Records (DPRs)** from software repositories.
It builds a **Causal Temporal Graph (CTG)** that reveals how past decisions
constrain future choices, where assumptions are decaying, and what happens
if key decisions were reversed.

## 🔬 Live Analysis: PostgreSQL

| Metric | Value |
|--------|-------|
| Repository | {meta.get('repository', 'N/A')} |
| DPRs Extracted | {len(dprs)} |
| Graph Nodes | {meta.get('total_nodes', 0)} |
| Graph Relationships | {meta.get('total_relationships', 0)} |
| Active Decay Alerts | {sum(1 for a in alerts if a.get('already_decaying'))} |
| Counterfactual Traces | {len(traces)} |
| Org Risk Score | {data.get('org_risk_score', 0)}/100 |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   React Dashboard                    │
│  (Graph Viz / Decay Monitor / Counterfactuals / PDF) │
└─────────────────┬───────────────────────────────────┘
                  │ REST API (FastAPI)
┌─────────────────┴───────────────────────────────────┐
│              Layer 5: API & Report Generation        │
│  api.py · generate_risk_report.py · generate_submission.py │
├──────────────────────────────────────────────────────┤
│              Layer 4: Intelligence Engines            │
│  counterfactual_engine.py · knowledge_concentration.py │
├──────────────────────────────────────────────────────┤
│              Layer 3: Live Monitoring                 │
│  decay_monitor.py (Git diff → Gemini → Blast radius) │
├──────────────────────────────────────────────────────┤
│              Layer 2: Causal Temporal Graph            │
│  Neo4j (162 nodes, 202 rels) + Weaviate (vectors)    │
│  graph_builder.py · enrich_graph.py · weaviate_ingest.py │
├──────────────────────────────────────────────────────┤
│              Layer 1: Decision Provenance              │
│  Bob IDE → nexus_layer1_dprs.json (15 DPRs)          │
│  build_nexus_data.py (idempotent merger)              │
└──────────────────────────────────────────────────────┘
```

## 🚀 Key Features

### 1. Decision Provenance Records (DPRs)
- Extracts architectural decisions with full provenance chains
- Tracks rejected alternatives, constraints, and assumptions
- Maps causal dependencies between decisions

### 2. Assumption Decay Monitoring
- Monitors git commits for changes that affect DPR assumptions
- Uses Gemini AI to evaluate whether assumptions still hold
- Computes blast radius using NetworkX graph traversal
- Real-time confidence scores: {monitored_count} DPRs actively monitored

### 3. Counterfactual Simulation
- "What if this decision went differently?" analysis
- {len(traces)} alternate timeline projections generated
- Traces downstream causal consequences through the CTG
- Verdicts: {verdicts_list}

### 4. Knowledge Concentration (SPOF/Bus Factor)
- Top knowledge concentrator: {kc.get('top_spof_humans', ['N/A'])[0]}
- Org risk score: {data.get('org_risk_score', 0)}/100
- Component SPOF analysis across {len(kc.get('component_profiles', []))} components

### 5. Executive Risk Report
- Professional PDF with DPR tables, decay alerts, SPOF analysis
- Downloadable via API at `/api/report/download`

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Graph DB | Neo4j (Docker) |
| Vector DB | Weaviate Cloud |
| AI Reasoning | Google Gemini 2.5 Flash |
| DPR Extraction | Bob IDE |
| Backend | FastAPI (Python) |
| Frontend | React (planned) |
| PDF Generation | ReportLab |
| Graph Analysis | NetworkX |

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | System health check |
| `/api/dashboard` | GET | All-in-one dashboard data |
| `/api/dprs` | GET | List all DPRs (filterable) |
| `/api/dprs/{{id}}` | GET | Single DPR detail |
| `/api/graph` | GET | CTG nodes and edges |
| `/api/decay` | GET | Decay alerts |
| `/api/decay/live` | GET | Live monitoring results |
| `/api/counterfactuals` | GET | All counterfactual traces |
| `/api/knowledge` | GET | SPOF analysis |
| `/api/report/download` | GET | Download PDF report |
| `/api/query` | POST | Natural language query |
| `/api/pipeline/decay-monitor` | POST | Trigger decay scan |
| `/api/pipeline/counterfactual` | POST | Trigger CF engine |

## 🏃 Quick Start

```bash
# 1. Start Neo4j
docker start nexus-neo4j

# 2. Build data pipeline
cd nexus_layer2
python build_nexus_data.py
python decay_monitor.py
python counterfactual_engine.py
python knowledge_concentration.py
python generate_risk_report.py

# 3. Start API
uvicorn api:app --host 0.0.0.0 --port 8000

# 4. Open dashboard
# http://localhost:8000/docs (Swagger UI)
```

## 📊 Sample Outputs

### Decay Monitor
```
[DECAYING] DPR-006: Vacuum as Separate Maintenance Process
  Confidence: 0.10 | Trend: neutral
[STABLE]   DPR-007: Write-Ahead Logging (WAL) for Durability
  Confidence: 0.90 | Trend: strengthened
```

### Counterfactual
```
[CF-003] What if XID was always 64-bit?
  Verdict: BETTER (confidence: 0.85)
  Downstream impact: 3 DPRs
```

---

Built for the lablab.ai Bob Build Hackathon 2025 🏆
"""
    return readme


def generate_demo_script():
    return """#!/usr/bin/env python3
\"\"\"Nexus Demo Script — Run all pipeline stages in sequence.\"\"\"
import subprocess, sys, os

os.environ.setdefault("GEMINI_API_KEY", "AIzaSyAUFtgY1YrsqXhR7jhwh59QBP3g18DJdxQ")

scripts = [
    ("Build nexus_data.json", "build_nexus_data.py"),
    ("Run Decay Monitor", "decay_monitor.py"),
    ("Run Counterfactual Engine", "counterfactual_engine.py"),
    ("Run Knowledge Concentration", "knowledge_concentration.py"),
    ("Generate Risk Report", "generate_risk_report.py"),
]

for name, script in scripts:
    print(f"\\n{'='*60}")
    print(f"  Running: {name}")
    print(f"{'='*60}")
    result = subprocess.run([sys.executable, script], cwd=os.path.dirname(__file__))
    if result.returncode != 0:
        print(f"  [!] {name} failed with exit code {result.returncode}")
    else:
        print(f"  [+] {name} completed successfully")

print(f"\\n{'='*60}")
print("  All pipeline stages complete!")
print("  Start API: uvicorn api:app --host 0.0.0.0 --port 8000")
print(f"{'='*60}")
"""


def generate_submission():
    print("=" * 60)
    print("  NEXUS - Submission Package Generator")
    print("=" * 60)

    data = load_nexus_data()

    # Create submission directory
    SUBMISSION_DIR.mkdir(exist_ok=True)
    print(f"[*] Output directory: {SUBMISSION_DIR}")

    # Generate README
    readme = generate_readme(data)
    readme_path = SUBMISSION_DIR / "README.md"
    readme_path.write_text(readme, encoding='utf-8')
    print(f"[+] README.md ({len(readme):,} chars)")

    # Generate demo script
    demo = generate_demo_script()
    demo_path = SUBMISSION_DIR / "run_demo.py"
    demo_path.write_text(demo, encoding='utf-8')
    print(f"[+] run_demo.py")

    # Copy key files
    key_files = [
        "nexus_data.json",
        "api.py",
        "build_nexus_data.py",
        "decay_monitor.py",
        "counterfactual_engine.py",
        "knowledge_concentration.py",
        "generate_risk_report.py",
        "models.py",
    ]
    for f in key_files:
        src = SCRIPT_DIR / f
        if src.exists():
            shutil.copy2(src, SUBMISSION_DIR / f)

    # Copy PDF if exists
    pdf = SCRIPT_DIR / "nexus_risk_report.pdf"
    if pdf.exists():
        shutil.copy2(pdf, SUBMISSION_DIR / "nexus_risk_report.pdf")
        print("[+] nexus_risk_report.pdf")

    # Generate architecture JSON (for frontend visualization)
    arch = {
        "layers": [
            {"id": 1, "name": "Decision Provenance", "scripts": ["build_nexus_data.py"], "status": "complete"},
            {"id": 2, "name": "Causal Temporal Graph", "scripts": ["graph_builder.py", "enrich_graph.py"], "status": "complete"},
            {"id": 3, "name": "Live Monitoring", "scripts": ["decay_monitor.py"], "status": "complete"},
            {"id": 4, "name": "Intelligence Engines", "scripts": ["counterfactual_engine.py", "knowledge_concentration.py"], "status": "complete"},
            {"id": 5, "name": "API & Reports", "scripts": ["api.py", "generate_risk_report.py"], "status": "complete"},
        ],
        "tech_stack": {
            "graph_db": "Neo4j", "vector_db": "Weaviate Cloud",
            "ai": "Google Gemini 2.5 Flash", "extraction": "Bob IDE",
            "backend": "FastAPI", "pdf": "ReportLab", "graph_analysis": "NetworkX",
        },
        "stats": data.get("meta", {}),
    }
    arch_path = SUBMISSION_DIR / "architecture.json"
    with open(arch_path, 'w', encoding='utf-8') as f:
        json.dump(arch, f, indent=2)
    print("[+] architecture.json")

    # Summary
    total_files = len(list(SUBMISSION_DIR.iterdir()))
    total_size = sum(f.stat().st_size for f in SUBMISSION_DIR.iterdir() if f.is_file())
    print(f"\n{'='*60}")
    print(f"  Submission package: {total_files} files, {total_size:,} bytes")
    print(f"  Location: {SUBMISSION_DIR}")
    print(f"{'='*60}")
    return str(SUBMISSION_DIR)


if __name__ == "__main__":
    generate_submission()
