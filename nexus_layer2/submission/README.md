# NEXUS — Causal Intelligence Platform for Software Architecture

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
| Repository | https://github.com/postgres/postgres |
| DPRs Extracted | 15 |
| Graph Nodes | 162 |
| Graph Relationships | 202 |
| Active Decay Alerts | 4 |
| Counterfactual Traces | 5 |
| Org Risk Score | 36.8/100 |

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
- Real-time confidence scores: 6 DPRs actively monitored

### 3. Counterfactual Simulation
- "What if this decision went differently?" analysis
- 5 alternate timeline projections generated
- Traces downstream causal consequences through the CTG
- Verdicts: worse, tradeoff, better, worse, tradeoff

### 4. Knowledge Concentration (SPOF/Bus Factor)
- Top knowledge concentrator: Tom Lane
- Org risk score: 36.8/100
- Component SPOF analysis across 6 components

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
| `/api/dprs/{id}` | GET | Single DPR detail |
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
