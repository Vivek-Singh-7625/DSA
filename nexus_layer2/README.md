# Nexus Layer 2 - CTG Ingestion Pipeline for Neo4j

This directory contains the Python implementation for loading Nexus Layer 1 output into Neo4j as a queryable Causal Temporal Graph (CTG).

## Files

1. **models.py** - Pydantic v2 models for data validation
2. **graph_builder.py** - Neo4j ingestion pipeline
3. **cypher_queries.py** - Predefined Cypher query library
4. **nl_query.py** - Natural language query interface
5. **verify_graph.py** - Graph health verification

## Prerequisites

### 1. Install Python Dependencies

```bash
pip install pydantic neo4j
```

### 2. Start Neo4j

Using Docker (recommended):
```bash
docker run -p7474:7474 -p7687:7687 neo4j:community
```

Or download Neo4j Community Edition from: https://neo4j.com/download/

## Usage

### Step 1: Validate Layer 1 Data

```bash
python nexus_layer2/models.py
```

This will:
- Load `postgres-analysis/output/nexus_layer1_dprs.json`
- Validate against Pydantic schemas
- Print data summary

**Expected Output:**
```
✅ VALIDATION SUCCESSFUL
Repository: https://github.com/postgres/postgres
Total DPRs: 28
CTG Edges: 25
Decay Alerts: 5
```

### Step 2: Load Data into Neo4j

```bash
python nexus_layer2/graph_builder.py
```

This will:
1. Connect to Neo4j at `bolt://localhost:7687`
2. Clear existing Nexus graph data
3. Create indexes for efficient querying
4. Create DPR nodes with all properties
5. Create CTG relationship edges
6. Create DecayAlert nodes linked to DPRs
7. Verify graph integrity

**Expected Output:**
```
✅ INGESTION COMPLETE
Created 28 DPR nodes
Created 25 CTG edges
Created 5 DecayAlert nodes
```

### Step 3: Verify Graph Health

```bash
python nexus_layer2/verify_graph.py
```

This prints a comprehensive health report:
- Node counts (DPRs, DecayAlerts)
- Relationship counts by type
- Blast radius breakdown
- Decay risk breakdown
- Component breakdown
- Top connected DPRs
- High-risk critical decisions
- Workaround proliferation

### Step 4: Query the Graph

#### Option A: Use Predefined Cypher Queries

```python
from neo4j import GraphDatabase
from cypher_queries import NEXUS_QUERIES

driver = GraphDatabase.driver("bolt://localhost:7687", auth=None)

with driver.session() as session:
    # Find critical blast radius DPRs
    result = session.run(NEXUS_QUERIES["critical_blast_radius"]["cypher"])
    for record in result:
        print(record)
```

#### Option B: Use Natural Language Interface

```bash
python nexus_layer2/nl_query.py
```

Interactive mode - ask questions in plain English:
```
❓ Your question: What decisions are already decaying?
❓ Your question: Show me the most dangerous decisions
❓ Your question: What led to DPR-003?
❓ Your question: What does DPR-001 impact?
```

Or programmatically:
```python
from nl_query import nl_query

result = nl_query("What decisions have critical blast radius?")
print(result)
```

## Available Queries

Run to see all available queries:
```bash
python nexus_layer2/cypher_queries.py
```

Key queries include:
- **critical_blast_radius** - DPRs with critical blast radius
- **high_decay_risk** - DPRs with high assumption decay risk
- **already_decaying** - Decay alerts where assumptions are breaking
- **causal_chain_from** - Downstream impacts of a decision
- **causal_chain_to** - What led to a decision
- **foundational_decisions** - Core architectural decisions
- **active_workarounds** - Technical debt indicators
- **within_window_changes** - Recent decisions (last 2 years)
- **most_connected_dprs** - Most influential decisions

## Neo4j Browser

Access the Neo4j Browser at: http://localhost:7474

Example queries to run:

```cypher
// Find all DPRs
MATCH (d:DPR) RETURN d LIMIT 25

// Visualize the entire CTG
MATCH (d:DPR)-[r]->(other:DPR)
RETURN d, r, other

// Find high-risk critical decisions
MATCH (d:DPR)
WHERE d.assumption_decay_risk = 'high' 
  AND d.blast_radius_estimate = 'critical'
RETURN d

// Show decay alerts
MATCH (d:DPR)-[:HAS_ALERT]->(a:DecayAlert)
WHERE a.already_decaying = true
RETURN d, a
```

## Data Model

### Node Types

**:DPR** (Decision Provenance Record)
- `dpr_id` - Unique identifier (e.g., "DPR-001")
- `title` - Decision title
- `component` - Component (MVCC, WAL, Storage, etc.)
- `within_window` - Boolean, made in last 2 years
- `decision_date` - When decision was made
- `decision` - The actual decision text
- `blast_radius_estimate` - critical/high/medium/low
- `assumption_decay_risk` - high/medium/low
- `intended_durability` - foundational/medium-term/short-term
- `active_workarounds` - List of workarounds in use
- Plus: constraints, assumptions, reasoning, files, commits, humans

**:DecayAlert**
- `dpr_id` - Associated DPR
- `assumption` - The assumption being monitored
- `already_decaying` - Boolean
- `decay_evidence` - Evidence of decay
- `earliest_signal_date` - When decay was first detected
- `recommended_monitor_query` - SQL query to monitor

### Relationship Types

- **CONSTRAINS** - Decision A constrains decision B
- **ENABLES** - Decision A enables decision B
- **REQUIRES** - Decision A requires decision B
- **ASSUMPTION_OF** - Decision A assumes decision B holds
- **TEMPORAL_PRECEDES** - Decision A came before B
- **HAS_ALERT** - DPR has a decay alert

## Troubleshooting

### Neo4j Connection Issues

If you see "Failed to connect to Neo4j":
1. Make sure Neo4j is running: `docker ps`
2. Check Neo4j is on port 7687: `netstat -an | findstr 7687`
3. Try accessing Neo4j Browser: http://localhost:7474

### Unicode Encoding Issues (Windows)

If you see `UnicodeEncodeError`, run with UTF-8:
```powershell
$env:PYTHONIOENCODING="utf-8"; python nexus_layer2/models.py
```

### Module Not Found

Install dependencies:
```bash
pip install pydantic neo4j
```

## Architecture

```
Layer 1 (Analysis)
    ↓
nexus_layer1_dprs.json
    ↓
models.py (Validation)
    ↓
graph_builder.py (Ingestion)
    ↓
Neo4j Graph Database
    ↓
cypher_queries.py / nl_query.py / verify_graph.py (Querying)
```

## Next Steps

After loading the graph:

1. **Explore in Neo4j Browser** - Visualize the CTG
2. **Run Health Checks** - `python verify_graph.py`
3. **Query Patterns** - Use predefined queries or write custom Cypher
4. **Natural Language** - Ask questions via `nl_query.py`
5. **Monitor Decay** - Track assumptions using recommended queries

## Notes

- **Single Repo Mode**: Currently configured for PostgreSQL only
- **No Auth**: Neo4j connection uses no authentication (dev mode)
- **Local Pattern Matching**: NL queries use keyword matching, no LLM API
- **Cypher Only**: No vector similarity layer (as per requirements)