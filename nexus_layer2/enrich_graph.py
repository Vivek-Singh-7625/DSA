"""Enrich the Neo4j graph with File, Human, and Component nodes"""
from neo4j import GraphDatabase

d = GraphDatabase.driver("bolt://localhost:7687", auth=None)
d.verify_connectivity()
print("Connected to Neo4j")

with d.session() as s:
    # 1. Add File nodes from files_involved
    r1 = s.run("""
    MATCH (dpr:DPR) WHERE dpr.files_involved IS NOT NULL
    UNWIND dpr.files_involved AS file_path
    MERGE (f:File {path: file_path})
    MERGE (dpr)-[:TOUCHES]->(f)
    RETURN count(DISTINCT f) as cnt
    """)
    print(f"File nodes created: {r1.single()['cnt']}")

    # 2. Add Human nodes from involved_humans
    r2 = s.run("""
    MATCH (dpr:DPR) WHERE dpr.involved_humans IS NOT NULL
    UNWIND dpr.involved_humans AS human_name
    MERGE (h:Human {name: human_name})
    MERGE (dpr)-[:INVOLVES]->(h)
    RETURN count(DISTINCT h) as cnt
    """)
    print(f"Human nodes created: {r2.single()['cnt']}")

    # 3. Add Component nodes
    r3 = s.run("""
    MATCH (dpr:DPR) WHERE dpr.component IS NOT NULL
    MERGE (c:Component {name: dpr.component})
    MERGE (dpr)-[:BELONGS_TO]->(c)
    RETURN count(DISTINCT c) as cnt
    """)
    print(f"Component nodes created: {r3.single()['cnt']}")

    # 4. Add Constraint nodes from explicit_constraints
    r4 = s.run("""
    MATCH (dpr:DPR) WHERE dpr.explicit_constraints IS NOT NULL
    UNWIND dpr.explicit_constraints AS constraint_text
    MERGE (ct:Constraint {text: constraint_text})
    MERGE (dpr)-[:HAS_CONSTRAINT]->(ct)
    RETURN count(DISTINCT ct) as cnt
    """)
    print(f"Constraint nodes created: {r4.single()['cnt']}")

    # 5. Add Assumption nodes from implicit_assumptions
    r5 = s.run("""
    MATCH (dpr:DPR) WHERE dpr.implicit_assumptions IS NOT NULL
    UNWIND dpr.implicit_assumptions AS assumption_text
    MERGE (a:Assumption {text: assumption_text})
    MERGE (dpr)-[:HAS_ASSUMPTION]->(a)
    RETURN count(DISTINCT a) as cnt
    """)
    print(f"Assumption nodes created: {r5.single()['cnt']}")

    # 6. Count totals
    total_n = s.run("MATCH (n) RETURN count(n) as c").single()["c"]
    total_r = s.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
    
    # Label breakdown
    labels = s.run("""
    MATCH (n) 
    WITH labels(n) AS lbls, count(n) AS cnt
    RETURN lbls, cnt ORDER BY cnt DESC
    """)
    
    print(f"\nTotal nodes: {total_n}")
    print(f"Total relationships: {total_r}")
    print("\nNode breakdown:")
    for rec in labels:
        print(f"  {rec['lbls']}: {rec['cnt']}")

    # Relationship breakdown
    rels = s.run("""
    MATCH ()-[r]->()
    RETURN type(r) as rel_type, count(r) as cnt
    ORDER BY cnt DESC
    """)
    print("\nRelationship breakdown:")
    for rec in rels:
        print(f"  {rec['rel_type']}: {rec['cnt']}")

d.close()
print("\nDone! Graph is now enriched.")
