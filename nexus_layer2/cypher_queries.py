"""
Nexus Layer 2 - Cypher Query Library
Predefined queries for common CTG analysis patterns
"""

NEXUS_QUERIES = {
    "critical_blast_radius": {
        "description": "Find all DPRs with critical blast radius",
        "cypher": """
            MATCH (d:DPR)
            WHERE d.blast_radius_estimate = 'critical'
            RETURN d.dpr_id, d.title, d.component, d.blast_radius_reasoning
            ORDER BY d.dpr_id
        """,
        "parameters": []
    },
    
    "high_decay_risk": {
        "description": "Find all DPRs with high assumption decay risk",
        "cypher": """
            MATCH (d:DPR)
            WHERE d.assumption_decay_risk = 'high'
            RETURN d.dpr_id, d.title, d.component, d.decay_risk_reasoning
            ORDER BY d.dpr_id
        """,
        "parameters": []
    },
    
    "already_decaying": {
        "description": "Find all decay alerts where assumptions are already decaying",
        "cypher": """
            MATCH (d:DPR)-[:HAS_ALERT]->(a:DecayAlert)
            WHERE a.already_decaying = true
            RETURN d.dpr_id, d.title, a.assumption, a.decay_evidence, a.earliest_signal_date
            ORDER BY a.earliest_signal_date
        """,
        "parameters": []
    },
    
    "component_subgraph": {
        "description": "Get all DPRs and their relationships within a specific component",
        "cypher": """
            MATCH (d:DPR)
            WHERE d.component = $component
            OPTIONAL MATCH (d)-[r]->(other:DPR)
            WHERE other.component = $component
            RETURN d, r, other
        """,
        "parameters": ["component"]
    },
    
    "causal_chain_from": {
        "description": "Traverse outgoing causal edges from a DPR (what this decision enables/constrains)",
        "cypher": """
            MATCH path = (start:DPR {dpr_id: $dpr_id})-[*1..5]->(end:DPR)
            RETURN path, 
                   start.dpr_id as from_dpr, 
                   start.title as from_title,
                   end.dpr_id as to_dpr, 
                   end.title as to_title,
                   length(path) as depth
            ORDER BY depth, to_dpr
        """,
        "parameters": ["dpr_id"]
    },
    
    "causal_chain_to": {
        "description": "Traverse incoming causal edges to a DPR (what led to this decision)",
        "cypher": """
            MATCH path = (start:DPR)-[*1..5]->(end:DPR {dpr_id: $dpr_id})
            RETURN path,
                   start.dpr_id as from_dpr,
                   start.title as from_title,
                   end.dpr_id as to_dpr,
                   end.title as to_title,
                   length(path) as depth
            ORDER BY depth, from_dpr
        """,
        "parameters": ["dpr_id"]
    },
    
    "foundational_decisions": {
        "description": "Find foundational decisions with high or critical blast radius",
        "cypher": """
            MATCH (d:DPR)
            WHERE d.intended_durability = 'foundational' 
              AND d.blast_radius_estimate IN ['high', 'critical']
            RETURN d.dpr_id, d.title, d.component, d.blast_radius_estimate, 
                   d.assumption_decay_risk, d.durability_reasoning
            ORDER BY 
                CASE d.blast_radius_estimate 
                    WHEN 'critical' THEN 1 
                    WHEN 'high' THEN 2 
                    ELSE 3 
                END,
                d.dpr_id
        """,
        "parameters": []
    },
    
    "active_workarounds": {
        "description": "Find DPRs with active workarounds (indicating design pressure)",
        "cypher": """
            MATCH (d:DPR)
            WHERE size(d.active_workarounds) > 0
            RETURN d.dpr_id, d.title, d.component, d.active_workarounds,
                   d.assumption_decay_risk, d.blast_radius_estimate
            ORDER BY size(d.active_workarounds) DESC, d.dpr_id
        """,
        "parameters": []
    },
    
    "within_window_changes": {
        "description": "Find DPRs made within the analysis window (recent decisions)",
        "cypher": """
            MATCH (d:DPR)
            WHERE d.within_window = true
            RETURN d.dpr_id, d.title, d.component, d.decision_date, d.decision
            ORDER BY d.decision_date DESC, d.dpr_id
        """,
        "parameters": []
    },
    
    "assumption_chain": {
        "description": "Find all assumption_of relationships (what assumptions depend on what)",
        "cypher": """
            MATCH path = (assuming:DPR)-[r:ASSUMPTION_OF]->(assumed:DPR)
            RETURN assuming.dpr_id as assuming_dpr,
                   assuming.title as assuming_title,
                   assumed.dpr_id as assumed_dpr,
                   assumed.title as assumed_title,
                   r.explanation as explanation
            ORDER BY assuming_dpr
        """,
        "parameters": []
    },
    
    "high_risk_critical_blast": {
        "description": "Find DPRs with both high decay risk AND critical blast radius (most dangerous)",
        "cypher": """
            MATCH (d:DPR)
            WHERE d.assumption_decay_risk = 'high' 
              AND d.blast_radius_estimate = 'critical'
            OPTIONAL MATCH (d)-[:HAS_ALERT]->(a:DecayAlert)
            RETURN d.dpr_id, d.title, d.component, 
                   d.decay_risk_reasoning, d.blast_radius_reasoning,
                   collect(a.assumption) as decay_alerts
            ORDER BY d.dpr_id
        """,
        "parameters": []
    },
    
    "component_dependencies": {
        "description": "Show how components depend on each other through DPR relationships",
        "cypher": """
            MATCH (from:DPR)-[r]->(to:DPR)
            WHERE from.component <> to.component
            RETURN DISTINCT from.component as from_component,
                   type(r) as relationship,
                   to.component as to_component,
                   count(*) as edge_count
            ORDER BY edge_count DESC, from_component, to_component
        """,
        "parameters": []
    },
    
    "most_connected_dprs": {
        "description": "Find DPRs with the most incoming and outgoing connections",
        "cypher": """
            MATCH (d:DPR)
            OPTIONAL MATCH (d)-[out]->()
            OPTIONAL MATCH ()-[in]->(d)
            WITH d, count(DISTINCT out) as outgoing, count(DISTINCT in) as incoming
            RETURN d.dpr_id, d.title, d.component,
                   incoming, outgoing, (incoming + outgoing) as total_connections
            ORDER BY total_connections DESC, d.dpr_id
            LIMIT 10
        """,
        "parameters": []
    },
    
    "decay_timeline": {
        "description": "Show decay alerts ordered by earliest signal date",
        "cypher": """
            MATCH (d:DPR)-[:HAS_ALERT]->(a:DecayAlert)
            RETURN d.dpr_id, d.title, d.component,
                   a.assumption, a.earliest_signal_date, a.already_decaying,
                   a.decay_signals_found
            ORDER BY a.earliest_signal_date, d.dpr_id
        """,
        "parameters": []
    },
    
    "workaround_proliferation": {
        "description": "Identify DPRs where workarounds are proliferating (3+ workarounds)",
        "cypher": """
            MATCH (d:DPR)
            WHERE size(d.active_workarounds) >= 3
            RETURN d.dpr_id, d.title, d.component,
                   size(d.active_workarounds) as workaround_count,
                   d.active_workarounds,
                   d.assumption_decay_risk
            ORDER BY workaround_count DESC, d.dpr_id
        """,
        "parameters": []
    },
    
    "constrains_relationships": {
        "description": "Find all CONSTRAINS relationships (design constraints)",
        "cypher": """
            MATCH (from:DPR)-[r:CONSTRAINS]->(to:DPR)
            RETURN from.dpr_id, from.title as constraining_decision,
                   to.dpr_id, to.title as constrained_decision,
                   r.explanation
            ORDER BY from.dpr_id, to.dpr_id
        """,
        "parameters": []
    },
    
    "enables_relationships": {
        "description": "Find all ENABLES relationships (what decisions enable what)",
        "cypher": """
            MATCH (from:DPR)-[r:ENABLES]->(to:DPR)
            RETURN from.dpr_id, from.title as enabling_decision,
                   to.dpr_id, to.title as enabled_decision,
                   r.explanation
            ORDER BY from.dpr_id, to.dpr_id
        """,
        "parameters": []
    },
    
    "requires_relationships": {
        "description": "Find all REQUIRES relationships (hard dependencies)",
        "cypher": """
            MATCH (from:DPR)-[r:REQUIRES]->(to:DPR)
            RETURN from.dpr_id, from.title as requiring_decision,
                   to.dpr_id, to.title as required_decision,
                   r.explanation
            ORDER BY from.dpr_id, to.dpr_id
        """,
        "parameters": []
    },
    
    "full_graph_stats": {
        "description": "Get comprehensive statistics about the entire graph",
        "cypher": """
            MATCH (d:DPR)
            OPTIONAL MATCH (d)-[:HAS_ALERT]->(a:DecayAlert)
            OPTIONAL MATCH (d)-[r]->()
            WITH 
                count(DISTINCT d) as total_dprs,
                count(DISTINCT a) as total_alerts,
                count(DISTINCT r) as total_edges,
                collect(DISTINCT d.component) as components,
                sum(CASE WHEN d.blast_radius_estimate = 'critical' THEN 1 ELSE 0 END) as critical_blast,
                sum(CASE WHEN d.assumption_decay_risk = 'high' THEN 1 ELSE 0 END) as high_decay,
                sum(CASE WHEN a.already_decaying = true THEN 1 ELSE 0 END) as already_decaying_count
            RETURN total_dprs, total_alerts, total_edges, components,
                   critical_blast, high_decay, already_decaying_count
        """,
        "parameters": []
    }
}


def list_queries():
    """Print all available queries with descriptions"""
    print("\n📚 AVAILABLE NEXUS QUERIES")
    print("=" * 60)
    
    for query_name, query_info in NEXUS_QUERIES.items():
        params = f" (params: {', '.join(query_info['parameters'])})" if query_info['parameters'] else ""
        print(f"\n🔍 {query_name}{params}")
        print(f"   {query_info['description']}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    """List all available queries"""
    list_queries()
    print(f"\n✅ Total queries available: {len(NEXUS_QUERIES)}")

# Made with Bob
