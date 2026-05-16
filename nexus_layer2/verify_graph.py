"""
Nexus Layer 2 - Graph Health Verification
Prints comprehensive health report for the Neo4j CTG
"""

from neo4j import GraphDatabase
from collections import defaultdict


def connect_neo4j(uri: str = "bolt://localhost:7687"):
    """Connect to Neo4j"""
    return GraphDatabase.driver(uri, auth=None)


def verify_graph(uri: str = "bolt://localhost:7687"):
    """
    Print comprehensive health report for the Nexus graph
    
    Args:
        uri: Neo4j connection URI
    """
    print("=" * 60)
    print("NEXUS GRAPH HEALTH REPORT")
    print("=" * 60)
    
    driver = connect_neo4j(uri)
    
    try:
        with driver.session() as session:
            # 1. Total node counts
            print("\n📊 NODE COUNTS:")
            result = session.run("MATCH (d:DPR) RETURN count(d) as count")
            dpr_count = result.single()["count"]
            print(f"  • Total DPR nodes: {dpr_count}")
            
            result = session.run("MATCH (a:DecayAlert) RETURN count(a) as count")
            alert_count = result.single()["count"]
            print(f"  • Total DecayAlert nodes: {alert_count}")
            
            # 2. Total edge counts by type
            print("\n🔗 RELATIONSHIP COUNTS:")
            result = session.run("""
                MATCH ()-[r]->()
                RETURN type(r) as rel_type, count(r) as count
                ORDER BY count DESC
            """)
            total_edges = 0
            for record in result:
                rel_type = record["rel_type"]
                count = record["count"]
                total_edges += count
                print(f"  • {rel_type}: {count}")
            print(f"  • TOTAL EDGES: {total_edges}")
            
            # 3. Decay alert breakdown
            print("\n🚨 DECAY ALERT BREAKDOWN:")
            result = session.run("""
                MATCH (a:DecayAlert)
                WHERE a.already_decaying = true
                RETURN count(a) as count
            """)
            already_decaying = result.single()["count"]
            print(f"  • Already decaying: {already_decaying}")
            print(f"  • Monitoring recommended: {alert_count - already_decaying}")
            
            # 4. Blast radius breakdown
            print("\n⚠️  BLAST RADIUS BREAKDOWN:")
            result = session.run("""
                MATCH (d:DPR)
                RETURN d.blast_radius_estimate as level, count(d) as count
                ORDER BY 
                    CASE d.blast_radius_estimate
                        WHEN 'critical' THEN 1
                        WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3
                        WHEN 'low' THEN 4
                        ELSE 5
                    END
            """)
            for record in result:
                level = record["level"]
                count = record["count"]
                print(f"  • {level.capitalize()}: {count} DPRs")
            
            # 5. Decay risk breakdown
            print("\n🔻 ASSUMPTION DECAY RISK:")
            result = session.run("""
                MATCH (d:DPR)
                RETURN d.assumption_decay_risk as level, count(d) as count
                ORDER BY 
                    CASE d.assumption_decay_risk
                        WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2
                        WHEN 'low' THEN 3
                        ELSE 4
                    END
            """)
            for record in result:
                level = record["level"]
                count = record["count"]
                print(f"  • {level.capitalize()}: {count} DPRs")
            
            # 6. Component breakdown
            print("\n🏗️  COMPONENTS:")
            result = session.run("""
                MATCH (d:DPR)
                RETURN d.component as component, count(d) as count
                ORDER BY count DESC
            """)
            components = []
            for record in result:
                component = record["component"]
                count = record["count"]
                components.append(component)
                print(f"  • {component}: {count} DPRs")
            
            # 7. Top 3 DPRs by inbound edges
            print("\n📥 TOP 3 DPRs BY INBOUND EDGES (most depended upon):")
            result = session.run("""
                MATCH (d:DPR)
                OPTIONAL MATCH ()-[r]->(d)
                WITH d, count(r) as inbound
                WHERE inbound > 0
                RETURN d.dpr_id, d.title, d.component, inbound
                ORDER BY inbound DESC
                LIMIT 3
            """)
            for i, record in enumerate(result, 1):
                print(f"  {i}. {record['d.dpr_id']}: {record['d.title']}")
                print(f"     Component: {record['d.component']}, Inbound: {record['inbound']}")
            
            # 8. Top 3 DPRs by outbound edges
            print("\n📤 TOP 3 DPRs BY OUTBOUND EDGES (most influential):")
            result = session.run("""
                MATCH (d:DPR)
                OPTIONAL MATCH (d)-[r]->()
                WITH d, count(r) as outbound
                WHERE outbound > 0
                RETURN d.dpr_id, d.title, d.component, outbound
                ORDER BY outbound DESC
                LIMIT 3
            """)
            for i, record in enumerate(result, 1):
                print(f"  {i}. {record['d.dpr_id']}: {record['d.title']}")
                print(f"     Component: {record['d.component']}, Outbound: {record['outbound']}")
            
            # 9. High risk + critical blast (most dangerous)
            print("\n🔥 HIGH RISK + CRITICAL BLAST (Most Dangerous):")
            result = session.run("""
                MATCH (d:DPR)
                WHERE d.assumption_decay_risk = 'high' 
                  AND d.blast_radius_estimate = 'critical'
                RETURN d.dpr_id, d.title, d.component
                ORDER BY d.dpr_id
            """)
            dangerous = list(result)
            if dangerous:
                for record in dangerous:
                    print(f"  • {record['d.dpr_id']}: {record['d.title']} ({record['d.component']})")
            else:
                print("  • None found (good!)")
            
            # 10. Workaround proliferation
            print("\n🔧 WORKAROUND PROLIFERATION (3+ workarounds):")
            result = session.run("""
                MATCH (d:DPR)
                WHERE size(d.active_workarounds) >= 3
                RETURN d.dpr_id, d.title, size(d.active_workarounds) as count
                ORDER BY count DESC
            """)
            workaround_dprs = list(result)
            if workaround_dprs:
                for record in workaround_dprs:
                    print(f"  • {record['d.dpr_id']}: {record['d.title']} ({record['count']} workarounds)")
            else:
                print("  • None found")
            
            # 11. Within window decisions
            print("\n📅 RECENT DECISIONS (within analysis window):")
            result = session.run("""
                MATCH (d:DPR)
                WHERE d.within_window = true
                RETURN count(d) as count
            """)
            within_window = result.single()["count"]
            print(f"  • {within_window} DPRs made within the analysis window")
            
            # 12. Foundational decisions
            print("\n🏛️  FOUNDATIONAL DECISIONS:")
            result = session.run("""
                MATCH (d:DPR)
                WHERE d.intended_durability = 'foundational'
                RETURN count(d) as count
            """)
            foundational = result.single()["count"]
            print(f"  • {foundational} foundational decisions")
            
            # 13. Graph density
            print("\n📈 GRAPH METRICS:")
            if dpr_count > 0:
                max_edges = dpr_count * (dpr_count - 1)
                density = (total_edges / max_edges * 100) if max_edges > 0 else 0
                avg_degree = (total_edges * 2 / dpr_count) if dpr_count > 0 else 0
                print(f"  • Graph density: {density:.2f}%")
                print(f"  • Average degree: {avg_degree:.2f}")
                print(f"  • Edges per DPR: {total_edges / dpr_count:.2f}")
            
            # 14. Isolated nodes check
            result = session.run("""
                MATCH (d:DPR)
                WHERE NOT (d)-[]-()
                RETURN count(d) as count
            """)
            isolated = result.single()["count"]
            if isolated > 0:
                print(f"\n⚠️  WARNING: {isolated} isolated DPR nodes (no relationships)")
            else:
                print(f"\n✅ No isolated nodes - all DPRs are connected")
            
            print("\n" + "=" * 60)
            print("✅ HEALTH CHECK COMPLETE")
            print("=" * 60)
            
            # Summary
            print("\n📋 SUMMARY:")
            print(f"  • {dpr_count} DPRs across {len(components)} components")
            print(f"  • {total_edges} causal relationships")
            print(f"  • {alert_count} decay alerts ({already_decaying} already decaying)")
            print(f"  • {len(dangerous)} high-risk critical decisions")
            print(f"  • {foundational} foundational decisions")
            
    except Exception as e:
        print(f"\n❌ Error during verification: {e}")
        print("\n💡 Make sure:")
        print("   1. Neo4j is running (docker run -p7474:7474 -p7687:7687 neo4j:community)")
        print("   2. Graph has been loaded (python nexus_layer2/graph_builder.py)")
        raise
    
    finally:
        driver.close()


if __name__ == "__main__":
    """Run graph health verification"""
    try:
        verify_graph()
    except Exception as e:
        print(f"\n❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()

# Made with Bob
