"""
Nexus Layer 2 - Natural Language Query Interface
Maps natural language questions to Cypher queries (local pattern matching, no API)
"""

import re
from neo4j import GraphDatabase
from cypher_queries import NEXUS_QUERIES


def connect_neo4j(uri: str = "bolt://localhost:7687"):
    """Connect to Neo4j"""
    return GraphDatabase.driver(uri, auth=None)


def extract_component(question: str) -> str:
    """Extract component name from question"""
    components = ["MVCC", "WAL", "Storage", "Autovacuum", "ProcessModel", "Replication"]
    question_upper = question.upper()
    
    for component in components:
        if component.upper() in question_upper:
            return component
    
    return None


def extract_dpr_id(question: str) -> str:
    """Extract DPR ID from question"""
    match = re.search(r'DPR-\d+', question, re.IGNORECASE)
    if match:
        return match.group(0).upper()
    return None


def map_question_to_query(question: str) -> tuple:
    """
    Map natural language question to Cypher query
    
    Returns:
        (query_name, parameters_dict) or (None, None) if no match
    """
    question_lower = question.lower()
    
    # Keyword mappings
    keyword_mappings = [
        # Critical/dangerous decisions
        (["blast radius", "critical", "dangerous", "high impact"], "critical_blast_radius"),
        
        # Decay-related
        (["decay", "decaying", "breaking", "fragile", "failing"], "already_decaying"),
        (["high risk", "risky assumption", "assumption risk"], "high_decay_risk"),
        (["decay timeline", "when did", "decay history"], "decay_timeline"),
        
        # Causal chains
        (["what led to", "why was", "history of", "caused by", "depends on what"], "causal_chain_to"),
        (["depends on", "downstream", "impacts", "affects", "enables what"], "causal_chain_from"),
        (["assumption", "assumes"], "assumption_chain"),
        
        # Foundational/important
        (["foundational", "most important", "core decision", "fundamental"], "foundational_decisions"),
        
        # Workarounds
        (["workaround", "hack", "technical debt", "band-aid"], "active_workarounds"),
        (["proliferat", "many workaround", "lots of workaround"], "workaround_proliferation"),
        
        # Recent changes
        (["recent", "last 2 years", "new decision", "within window"], "within_window_changes"),
        
        # Component-specific
        (["component", "in storage", "in mvcc", "in wal"], "component_subgraph"),
        
        # Relationships
        (["constrains", "constraint", "limits"], "constrains_relationships"),
        (["enables", "allows", "makes possible"], "enables_relationships"),
        (["requires", "needs", "depends on"], "requires_relationships"),
        
        # Most connected
        (["most connected", "most important", "central", "hub"], "most_connected_dprs"),
        
        # High risk + critical
        (["most dangerous", "highest risk", "critical and high"], "high_risk_critical_blast"),
        
        # Stats
        (["statistics", "stats", "overview", "summary"], "full_graph_stats"),
        (["component depend", "cross-component"], "component_dependencies"),
    ]
    
    # Check for matches
    for keywords, query_name in keyword_mappings:
        if any(keyword in question_lower for keyword in keywords):
            # Extract parameters if needed
            query_info = NEXUS_QUERIES[query_name]
            params = {}
            
            if "component" in query_info["parameters"]:
                component = extract_component(question)
                if component:
                    params["component"] = component
                else:
                    # Ask user for component
                    return (query_name, "NEED_COMPONENT")
            
            if "dpr_id" in query_info["parameters"]:
                dpr_id = extract_dpr_id(question)
                if dpr_id:
                    params["dpr_id"] = dpr_id
                else:
                    # Ask user for DPR ID
                    return (query_name, "NEED_DPR_ID")
            
            return (query_name, params)
    
    return (None, None)


def format_results(records, query_name: str) -> str:
    """Format query results as plain English"""
    if not records:
        return "No results found."
    
    output = []
    
    # Format based on query type
    if query_name == "critical_blast_radius":
        output.append(f"Found {len(records)} DPRs with critical blast radius:\n")
        for record in records:
            output.append(f"• {record['d.dpr_id']}: {record['d.title']}")
            output.append(f"  Component: {record['d.component']}")
            output.append(f"  Reasoning: {record['d.blast_radius_reasoning']}\n")
    
    elif query_name == "already_decaying":
        output.append(f"Found {len(records)} assumptions already decaying:\n")
        for record in records:
            output.append(f"• {record['d.dpr_id']}: {record['d.title']}")
            output.append(f"  Assumption: {record['a.assumption']}")
            output.append(f"  Evidence: {record['a.decay_evidence']}")
            output.append(f"  First signal: {record['a.earliest_signal_date']}\n")
    
    elif query_name == "high_decay_risk":
        output.append(f"Found {len(records)} DPRs with high decay risk:\n")
        for record in records:
            output.append(f"• {record['d.dpr_id']}: {record['d.title']}")
            output.append(f"  Component: {record['d.component']}")
            output.append(f"  Risk reasoning: {record['d.decay_risk_reasoning']}\n")
    
    elif query_name == "foundational_decisions":
        output.append(f"Found {len(records)} foundational decisions with high/critical blast radius:\n")
        for record in records:
            output.append(f"• {record['d.dpr_id']}: {record['d.title']}")
            output.append(f"  Component: {record['d.component']}")
            output.append(f"  Blast radius: {record['d.blast_radius_estimate']}")
            output.append(f"  Decay risk: {record['d.assumption_decay_risk']}\n")
    
    elif query_name == "active_workarounds":
        output.append(f"Found {len(records)} DPRs with active workarounds:\n")
        for record in records:
            workarounds = record['d.active_workarounds']
            output.append(f"• {record['d.dpr_id']}: {record['d.title']} ({len(workarounds)} workarounds)")
            for wa in workarounds:
                output.append(f"  - {wa}")
            output.append("")
    
    elif query_name in ["causal_chain_from", "causal_chain_to"]:
        direction = "downstream from" if query_name == "causal_chain_from" else "upstream to"
        output.append(f"Found {len(records)} causal paths {direction} the specified DPR:\n")
        for record in records:
            output.append(f"• Depth {record['depth']}: {record['from_dpr']} → {record['to_dpr']}")
            output.append(f"  {record['from_title']} → {record['to_title']}\n")
    
    elif query_name == "most_connected_dprs":
        output.append(f"Top {len(records)} most connected DPRs:\n")
        for record in records:
            output.append(f"• {record['d.dpr_id']}: {record['d.title']}")
            output.append(f"  Incoming: {record['incoming']}, Outgoing: {record['outgoing']}, Total: {record['total_connections']}\n")
    
    elif query_name == "full_graph_stats":
        record = records[0]
        output.append("Graph Statistics:\n")
        output.append(f"• Total DPRs: {record['total_dprs']}")
        output.append(f"• Total Decay Alerts: {record['total_alerts']}")
        output.append(f"• Total Edges: {record['total_edges']}")
        output.append(f"• Components: {', '.join(record['components'])}")
        output.append(f"• Critical blast radius: {record['critical_blast']} DPRs")
        output.append(f"• High decay risk: {record['high_decay']} DPRs")
        output.append(f"• Already decaying: {record['already_decaying_count']} alerts")
    
    else:
        # Generic formatting
        output.append(f"Found {len(records)} results:\n")
        for record in records:
            output.append(str(dict(record)))
            output.append("")
    
    return "\n".join(output)


def nl_query(question: str, uri: str = "bolt://localhost:7687") -> str:
    """
    Execute natural language query against Neo4j
    
    Args:
        question: Natural language question
        uri: Neo4j connection URI
        
    Returns:
        Plain English formatted results
    """
    print(f"\n❓ Question: {question}\n")
    
    # Map question to query
    query_name, params = map_question_to_query(question)
    
    if query_name is None:
        return ("I couldn't understand that question. Try asking about:\n"
                "• Critical or dangerous decisions\n"
                "• Decaying assumptions\n"
                "• What led to a decision (causal history)\n"
                "• What a decision impacts (downstream effects)\n"
                "• Foundational decisions\n"
                "• Workarounds and technical debt\n"
                "• Recent changes\n"
                "• Graph statistics")
    
    if params == "NEED_COMPONENT":
        return ("Please specify a component: MVCC, WAL, Storage, Autovacuum, ProcessModel, or Replication\n"
                "Example: 'Show me all decisions in the Storage component'")
    
    if params == "NEED_DPR_ID":
        return ("Please specify a DPR ID (e.g., DPR-001)\n"
                "Example: 'What led to DPR-003?'")
    
    # Get query
    query_info = NEXUS_QUERIES[query_name]
    print(f"🔍 Mapped to query: {query_name}")
    print(f"📝 Description: {query_info['description']}\n")
    
    # Execute query
    driver = connect_neo4j(uri)
    
    try:
        with driver.session() as session:
            result = session.run(query_info["cypher"], **params)
            records = list(result)
            
            # Format and return results
            formatted = format_results(records, query_name)
            return formatted
    
    finally:
        driver.close()


if __name__ == "__main__":
    """Interactive query interface"""
    print("=" * 60)
    print("NEXUS NATURAL LANGUAGE QUERY INTERFACE")
    print("=" * 60)
    print("\nType your questions in natural language.")
    print("Type 'exit' to quit.\n")
    
    while True:
        try:
            question = input("❓ Your question: ").strip()
            
            if question.lower() in ['exit', 'quit', 'q']:
                print("\n👋 Goodbye!")
                break
            
            if not question:
                continue
            
            result = nl_query(question)
            print("\n" + "=" * 60)
            print(result)
            print("=" * 60 + "\n")
        
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")

# Made with Bob
