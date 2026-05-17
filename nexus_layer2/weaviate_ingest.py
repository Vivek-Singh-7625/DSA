"""
Nexus Layer 2 - Weaviate Vector Search Integration
Ingests DPR data into Weaviate Cloud for semantic search over decisions,
assumptions, constraints, and decay alerts.
"""
import json
import os
import sys
import weaviate
from weaviate.auth import AuthApiKey
from weaviate.classes.config import Configure, Property, DataType
from weaviate.classes.query import MetadataQuery
from pathlib import Path

# ── Config ─────────────────────────────────────────────────
WEAVIATE_URL = "https://xgysxhhosmiqqawovgtguq.c0.asia-southeast1.gcp.weaviate.cloud"
WEAVIATE_KEY = "YVN1enphUHBqSUNIMkRlal96Um8yUEpLSzEyaWViaEFEK0tTdlUwZzA4SGNBU1pUYlc1ZDVZbEU3K3RJPV92MjAw"

COLLECTION_NAME = "NexusDPR"

# ── Connection ─────────────────────────────────────────────
def connect_weaviate():
    """Connect to Weaviate Cloud instance."""
    url = os.getenv("WEAVIATE_URL", WEAVIATE_URL)
    key = os.getenv("WEAVIATE_KEY", WEAVIATE_KEY)
    
    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=url,
        auth_credentials=AuthApiKey(key),
    )
    print(f"✅ Connected to Weaviate Cloud")
    print(f"   Ready: {client.is_ready()}")
    return client


# ── Schema Creation ────────────────────────────────────────
def create_collection(client):
    """Create the NexusDPR collection with properties for semantic search."""
    # Delete if exists (idempotent)
    if client.collections.exists(COLLECTION_NAME):
        client.collections.delete(COLLECTION_NAME)
        print(f"   Deleted existing '{COLLECTION_NAME}' collection")

    collection = client.collections.create(
        name=COLLECTION_NAME,
        # Use Weaviate's built-in vectorizer
        vectorizer_config=Configure.Vectorizer.text2vec_weaviate(),
        properties=[
            Property(name="dpr_id", data_type=DataType.TEXT),
            Property(name="title", data_type=DataType.TEXT),
            Property(name="component", data_type=DataType.TEXT),
            Property(name="decision", data_type=DataType.TEXT),
            Property(name="decision_date", data_type=DataType.TEXT),
            Property(name="durability_reasoning", data_type=DataType.TEXT),
            Property(name="decay_risk", data_type=DataType.TEXT),
            Property(name="decay_risk_reasoning", data_type=DataType.TEXT),
            Property(name="blast_radius", data_type=DataType.TEXT),
            Property(name="blast_radius_reasoning", data_type=DataType.TEXT),
            Property(name="constraints", data_type=DataType.TEXT),
            Property(name="assumptions", data_type=DataType.TEXT),
            Property(name="workarounds", data_type=DataType.TEXT),
            Property(name="rejected_alternatives", data_type=DataType.TEXT),
            Property(name="files_involved", data_type=DataType.TEXT),
            Property(name="involved_humans", data_type=DataType.TEXT),
            Property(name="causal_dependencies", data_type=DataType.TEXT),
            Property(name="full_text", data_type=DataType.TEXT),  # Combined searchable text
        ],
    )
    print(f"✅ Created '{COLLECTION_NAME}' collection with text2vec-weaviate vectorizer")
    return collection


# ── Data Loading ───────────────────────────────────────────
def load_dprs():
    """Load DPR data from Layer 1 JSON."""
    script_dir = Path(__file__).resolve().parent
    json_path = script_dir.parent / "postgres-analysis" / "output" / "nexus_layer1_dprs.json"
    
    if not json_path.exists():
        print(f"❌ JSON not found: {json_path}")
        sys.exit(1)
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    dprs = data.get("nexus_layer1_output", {}).get("dprs", [])
    print(f"   Loaded {len(dprs)} DPRs from {json_path.name}")
    return dprs, data


def build_full_text(dpr):
    """Create a rich combined text for semantic embedding."""
    parts = [
        f"Decision: {dpr.get('title', '')}",
        f"Component: {dpr.get('component', '')}",
        f"Description: {dpr.get('decision', '')}",
        f"Durability: {dpr.get('durability_reasoning', '')}",
        f"Decay Risk: {dpr.get('decay_risk_reasoning', '')}",
        f"Blast Radius: {dpr.get('blast_radius_reasoning', '')}",
    ]
    
    constraints = dpr.get("explicit_constraints", [])
    if constraints:
        parts.append(f"Constraints: {'; '.join(constraints)}")
    
    assumptions = dpr.get("implicit_assumptions", [])
    if assumptions:
        parts.append(f"Assumptions: {'; '.join(assumptions)}")
    
    workarounds = dpr.get("active_workarounds", [])
    if workarounds:
        parts.append(f"Workarounds: {'; '.join(workarounds)}")
    
    rejected = dpr.get("rejected_alternatives", [])
    if rejected:
        parts.append(f"Rejected Alternatives: {'; '.join(rejected)}")
    
    return " | ".join(parts)


# ── Ingestion ──────────────────────────────────────────────
def ingest_dprs(client, dprs):
    """Ingest all DPRs into Weaviate with semantic embeddings."""
    collection = client.collections.get(COLLECTION_NAME)
    
    objects = []
    for dpr in dprs:
        obj = {
            "dpr_id": dpr.get("dpr_id", ""),
            "title": dpr.get("title", ""),
            "component": dpr.get("component", ""),
            "decision": dpr.get("decision", ""),
            "decision_date": dpr.get("decision_date", ""),
            "durability_reasoning": dpr.get("durability_reasoning", ""),
            "decay_risk": dpr.get("assumption_decay_risk", ""),
            "decay_risk_reasoning": dpr.get("decay_risk_reasoning", ""),
            "blast_radius": dpr.get("blast_radius_estimate", ""),
            "blast_radius_reasoning": dpr.get("blast_radius_reasoning", ""),
            "constraints": "; ".join(dpr.get("explicit_constraints", [])),
            "assumptions": "; ".join(dpr.get("implicit_assumptions", [])),
            "workarounds": "; ".join(dpr.get("active_workarounds", [])),
            "rejected_alternatives": "; ".join(dpr.get("rejected_alternatives", [])),
            "files_involved": "; ".join(dpr.get("files_involved", [])),
            "involved_humans": "; ".join(dpr.get("involved_humans", [])),
            "causal_dependencies": "; ".join(dpr.get("causal_dependencies", [])),
            "full_text": build_full_text(dpr),
        }
        objects.append(obj)
    
    # Batch insert
    with collection.batch.dynamic() as batch:
        for obj in objects:
            batch.add_object(properties=obj)
    
    print(f"✅ Ingested {len(objects)} DPRs into Weaviate")
    
    # Also ingest decay alerts
    decay_alerts = []
    for dpr in dprs:
        if dpr.get("decay_signals_found"):
            for signal in dpr["decay_signals_found"]:
                alert_obj = {
                    "dpr_id": dpr["dpr_id"],
                    "title": f"DECAY ALERT: {dpr['title']}",
                    "component": dpr.get("component", ""),
                    "decision": dpr.get("decision", ""),
                    "decay_risk": dpr.get("assumption_decay_risk", ""),
                    "decay_risk_reasoning": dpr.get("decay_risk_reasoning", ""),
                    "blast_radius": dpr.get("blast_radius_estimate", ""),
                    "blast_radius_reasoning": dpr.get("blast_radius_reasoning", ""),
                    "full_text": f"DECAY ALERT for {dpr['title']}: {signal.get('assumption', '')} — Evidence: {signal.get('evidence', '')} — Status: {signal.get('status', '')}",
                    "assumptions": signal.get("assumption", ""),
                    "constraints": "",
                    "workarounds": "",
                    "rejected_alternatives": "",
                    "files_involved": "",
                    "involved_humans": "",
                    "causal_dependencies": "",
                    "decision_date": signal.get("earliest_signal_date", ""),
                    "durability_reasoning": "",
                }
                decay_alerts.append(alert_obj)
    
    if decay_alerts:
        with collection.batch.dynamic() as batch:
            for obj in decay_alerts:
                batch.add_object(properties=obj)
        print(f"✅ Ingested {len(decay_alerts)} decay alerts into Weaviate")
    
    return len(objects) + len(decay_alerts)


# ── Semantic Search ────────────────────────────────────────
def semantic_search(client, query, limit=5):
    """Search DPRs by semantic meaning."""
    collection = client.collections.get(COLLECTION_NAME)
    
    results = collection.query.near_text(
        query=query,
        limit=limit,
        return_metadata=MetadataQuery(distance=True, certainty=True),
    )
    
    output = []
    for obj in results.objects:
        props = obj.properties
        meta = obj.metadata
        output.append({
            "dpr_id": props.get("dpr_id"),
            "title": props.get("title"),
            "component": props.get("component"),
            "decision": props.get("decision", "")[:200],
            "decay_risk": props.get("decay_risk"),
            "blast_radius": props.get("blast_radius"),
            "certainty": round(meta.certainty, 4) if meta.certainty else None,
            "distance": round(meta.distance, 4) if meta.distance else None,
        })
    return output


def search_and_print(client, query, limit=5):
    """Search and pretty-print results."""
    print(f"\n🔍 Semantic Search: \"{query}\"")
    print("=" * 60)
    results = semantic_search(client, query, limit)
    for i, r in enumerate(results, 1):
        cert = f"{r['certainty']:.1%}" if r['certainty'] else "N/A"
        print(f"\n  [{i}] {r['dpr_id']}: {r['title']}")
        print(f"      Component: {r['component']} | Certainty: {cert}")
        print(f"      Decay Risk: {r['decay_risk']} | Blast Radius: {r['blast_radius']}")
        print(f"      Decision: {r['decision'][:120]}...")
    return results


# ── Main ───────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  NEXUS - Weaviate Vector Search Integration")
    print("=" * 60)
    
    # Connect
    client = connect_weaviate()
    
    # Create collection
    create_collection(client)
    
    # Load and ingest
    dprs, data = load_dprs()
    total = ingest_dprs(client, dprs)
    
    # Verify
    collection = client.collections.get(COLLECTION_NAME)
    count = collection.aggregate.over_all(total_count=True).total_count
    print(f"\n📊 Weaviate Collection: {COLLECTION_NAME}")
    print(f"   Total objects: {count}")
    
    # Run demo searches
    print("\n" + "=" * 60)
    print("  DEMO: Semantic Search Results")
    print("=" * 60)
    
    queries = [
        "performance degradation due to bloat",
        "database shutdown risk",
        "storage efficiency and page size tradeoffs",
        "concurrent transaction handling",
        "crash recovery and data durability",
    ]
    
    for q in queries:
        search_and_print(client, q, limit=3)
    
    # Interactive mode
    print("\n" + "=" * 60)
    print("  Interactive Semantic Search (type 'quit' to exit)")
    print("=" * 60)
    
    while True:
        try:
            query = input("\n🔎 Search: ").strip()
            if not query or query.lower() in ("quit", "exit", "q"):
                break
            search_and_print(client, query)
        except (KeyboardInterrupt, EOFError):
            break
    
    client.close()
    print("\n✅ Weaviate connection closed.")


if __name__ == "__main__":
    main()
