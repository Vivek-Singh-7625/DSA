"""
Nexus Layer 2 - Neo4j Graph Builder
Loads DPRs, CTG edges, and decay alerts into Neo4j
"""

from neo4j import GraphDatabase
from typing import List
from datetime import datetime
from models import load_layer1, DPR, CTGEdge, DecayAlert


def connect_neo4j(uri: str = "bolt://localhost:7687", user: str = "", password: str = ""):
    """
    Connect to Neo4j database
    
    Args:
        uri: Neo4j connection URI
        user: Username (empty for no auth in dev)
        password: Password (empty for no auth in dev)
        
    Returns:
        Neo4j driver instance
    """
    print(f"🔌 Connecting to Neo4j at {uri}...")
    
    if user and password:
        driver = GraphDatabase.driver(uri, auth=(user, password))
    else:
        driver = GraphDatabase.driver(uri, auth=None)
    
    # Test connection
    try:
        driver.verify_connectivity()
        print("✅ Connected to Neo4j successfully")
        return driver
    except Exception as e:
        print(f"❌ Failed to connect to Neo4j: {e}")
        print("\n💡 Make sure Neo4j is running:")
        print("   docker run -p7474:7474 -p7687:7687 neo4j:community")
        raise


def clear_graph(driver):
    """
    Clear all Nexus nodes and relationships from the graph
    Only deletes nodes with :DPR or :DecayAlert labels
    """
    print("\n🧹 Clearing existing Nexus graph data...")
    
    with driver.session() as session:
        # Delete DecayAlert nodes and their relationships
        result = session.run("""
            MATCH (a:DecayAlert)
            DETACH DELETE a
            RETURN count(a) as deleted
        """)
        decay_deleted = result.single()["deleted"]
        
        # Delete DPR nodes and their relationships
        result = session.run("""
            MATCH (d:DPR)
            DETACH DELETE d
            RETURN count(d) as deleted
        """)
        dpr_deleted = result.single()["deleted"]
        
        print(f"  • Deleted {dpr_deleted} DPR nodes")
        print(f"  • Deleted {decay_deleted} DecayAlert nodes")
        print("✅ Graph cleared")


def create_indexes(driver):
    """
    Create indexes for efficient querying
    """
    print("\n📇 Creating indexes...")
    
    indexes = [
        ("DPR", "dpr_id"),
        ("DPR", "component"),
        ("DPR", "blast_radius_estimate"),
        ("DPR", "assumption_decay_risk"),
        ("DPR", "within_window"),
        ("DecayAlert", "already_decaying"),
        ("DecayAlert", "dpr_id"),
    ]
    
    with driver.session() as session:
        for label, property_name in indexes:
            try:
                session.run(f"""
                    CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.{property_name})
                """)
                print(f"  • Created index on {label}.{property_name}")
            except Exception as e:
                print(f"  ⚠️  Index on {label}.{property_name} may already exist: {e}")
    
    print("✅ Indexes created")


def create_dpr_nodes(driver, dprs: List[DPR]):
    """
    Create DPR nodes in Neo4j with all properties
    """
    print(f"\n📝 Creating {len(dprs)} DPR nodes...")
    
    ingested_at = datetime.utcnow().isoformat()
    
    with driver.session() as session:
        for dpr in dprs:
            session.run("""
                CREATE (d:DPR {
                    dpr_id: $dpr_id,
                    title: $title,
                    component: $component,
                    within_window: $within_window,
                    decision_date: $decision_date,
                    decision: $decision,
                    rejected_alternatives: $rejected_alternatives,
                    explicit_constraints: $explicit_constraints,
                    implicit_assumptions: $implicit_assumptions,
                    intended_durability: $intended_durability,
                    durability_reasoning: $durability_reasoning,
                    causal_dependencies: $causal_dependencies,
                    files_involved: $files_involved,
                    commit_refs: $commit_refs,
                    involved_humans: $involved_humans,
                    assumption_decay_risk: $assumption_decay_risk,
                    decay_risk_reasoning: $decay_risk_reasoning,
                    blast_radius_estimate: $blast_radius_estimate,
                    blast_radius_reasoning: $blast_radius_reasoning,
                    active_workarounds: $active_workarounds,
                    ingested_at: $ingested_at
                })
            """, 
                dpr_id=dpr.dpr_id,
                title=dpr.title,
                component=dpr.component,
                within_window=dpr.within_window,
                decision_date=dpr.decision_date,
                decision=dpr.decision,
                rejected_alternatives=dpr.rejected_alternatives,
                explicit_constraints=dpr.explicit_constraints,
                implicit_assumptions=dpr.implicit_assumptions,
                intended_durability=dpr.intended_durability,
                durability_reasoning=dpr.durability_reasoning,
                causal_dependencies=dpr.causal_dependencies,
                files_involved=dpr.files_involved,
                commit_refs=dpr.commit_refs,
                involved_humans=dpr.involved_humans,
                assumption_decay_risk=dpr.assumption_decay_risk,
                decay_risk_reasoning=dpr.decay_risk_reasoning,
                blast_radius_estimate=dpr.blast_radius_estimate,
                blast_radius_reasoning=dpr.blast_radius_reasoning,
                active_workarounds=dpr.active_workarounds,
                ingested_at=ingested_at
            )
    
    print(f"✅ Created {len(dprs)} DPR nodes")


def create_ctg_edges(driver, edges: List[CTGEdge]):
    """
    Create directed relationships between DPRs based on CTG edges
    """
    print(f"\n🔗 Creating {len(edges)} CTG edges...")
    
    relationship_counts = {}
    
    with driver.session() as session:
        for edge in edges:
            # Normalize relationship name to uppercase with underscores
            rel_type = edge.relationship.upper().replace(" ", "_").replace("-", "_")
            relationship_counts[rel_type] = relationship_counts.get(rel_type, 0) + 1
            
            session.run(f"""
                MATCH (from:DPR {{dpr_id: $from_dpr}})
                MATCH (to:DPR {{dpr_id: $to_dpr}})
                CREATE (from)-[r:{rel_type} {{
                    explanation: $explanation,
                    within_window: $within_window
                }}]->(to)
            """,
                from_dpr=edge.from_dpr,
                to_dpr=edge.to_dpr,
                explanation=edge.explanation,
                within_window=edge.within_window
            )
    
    print(f"✅ Created {len(edges)} CTG edges:")
    for rel_type, count in sorted(relationship_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {rel_type}: {count}")


def create_decay_alerts(driver, alerts: List[DecayAlert]):
    """
    Create DecayAlert nodes and link them to DPRs via HAS_ALERT relationship
    """
    print(f"\n🚨 Creating {len(alerts)} DecayAlert nodes...")
    
    with driver.session() as session:
        for alert in alerts:
            session.run("""
                MATCH (d:DPR {dpr_id: $dpr_id})
                CREATE (a:DecayAlert {
                    dpr_id: $dpr_id,
                    assumption: $assumption,
                    decay_signals_found: $decay_signals_found,
                    earliest_signal_date: $earliest_signal_date,
                    already_decaying: $already_decaying,
                    decay_evidence: $decay_evidence,
                    recommended_monitor_query: $recommended_monitor_query
                })
                CREATE (d)-[:HAS_ALERT]->(a)
            """,
                dpr_id=alert.dpr_id,
                assumption=alert.assumption,
                decay_signals_found=alert.decay_signals_found,
                earliest_signal_date=alert.earliest_signal_date,
                already_decaying=alert.already_decaying,
                decay_evidence=alert.decay_evidence,
                recommended_monitor_query=alert.recommended_monitor_query
            )
    
    already_decaying = sum(1 for alert in alerts if alert.already_decaying)
    print(f"✅ Created {len(alerts)} DecayAlert nodes:")
    print(f"  • Already decaying: {already_decaying}")
    print(f"  • Monitoring recommended: {len(alerts) - already_decaying}")


def verify_graph(driver):
    """
    Verify the graph was created correctly and print summary
    """
    print("\n🔍 Verifying graph integrity...")
    
    with driver.session() as session:
        # Count nodes
        result = session.run("MATCH (d:DPR) RETURN count(d) as count")
        dpr_count = result.single()["count"]
        
        result = session.run("MATCH (a:DecayAlert) RETURN count(a) as count")
        alert_count = result.single()["count"]
        
        # Count relationships
        result = session.run("MATCH ()-[r]->() RETURN type(r) as rel_type, count(r) as count")
        relationships = {record["rel_type"]: record["count"] for record in result}
        
        print(f"\n📊 GRAPH SUMMARY:")
        print(f"  • DPR nodes: {dpr_count}")
        print(f"  • DecayAlert nodes: {alert_count}")
        print(f"  • Total relationships: {sum(relationships.values())}")
        
        if relationships:
            print(f"\n🔗 RELATIONSHIPS:")
            for rel_type, count in sorted(relationships.items(), key=lambda x: x[1], reverse=True):
                print(f"  • {rel_type}: {count}")
        
        print("\n✅ Graph verification complete")


def main():
    """
    Main pipeline: Load Layer 1 data and ingest into Neo4j
    """
    print("=" * 60)
    print("NEXUS LAYER 2 - CTG INGESTION PIPELINE")
    print("=" * 60)
    
    try:
        # Step 1: Load and validate Layer 1 data
        output = load_layer1()
        
        # Step 2: Connect to Neo4j
        driver = connect_neo4j()
        
        # Step 3: Clear existing graph
        clear_graph(driver)
        
        # Step 4: Create indexes
        create_indexes(driver)
        
        # Step 5: Create DPR nodes
        create_dpr_nodes(driver, output.dprs)
        
        # Step 6: Create CTG edges
        create_ctg_edges(driver, output.ctg_edges)
        
        # Step 7: Create decay alerts
        create_decay_alerts(driver, output.assumption_decay_prescan)
        
        # Step 8: Verify graph
        verify_graph(driver)
        
        # Close connection
        driver.close()
        
        print("\n" + "=" * 60)
        print("✅ INGESTION COMPLETE")
        print("=" * 60)
        print("\n💡 Next steps:")
        print("   • Open Neo4j Browser: http://localhost:7474")
        print("   • Run queries from cypher_queries.py")
        print("   • Use nl_query.py for natural language queries")
        print("   • Run verify_graph.py for health checks")
        
    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        print("\n💡 Make sure the Layer 1 analysis has been run first")
    except Exception as e:
        print(f"\n❌ Error during ingestion: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

# Made with Bob
