"""
Test script to demonstrate query_cli.py functionality
Simulates a successful query execution
"""

import sys
from io import StringIO

# Mock the nl_query function to return sample results
def mock_nl_query(question: str, uri: str = "bolt://localhost:7687") -> str:
    """Mock nl_query that returns sample results"""
    print(f"\n[?] Question: {question}\n")
    print(f"[*] Mapped to query: foundational_decisions")
    print(f"[i] Description: Find all foundational decisions with high/critical blast radius\n")
    
    return """Found 3 foundational decisions with high/critical blast radius:

• DPR-001: MVCC Tuple Versioning
  Component: MVCC
  Blast radius: critical
  Decay risk: medium

• DPR-003: WAL Sequential Write Design
  Component: WAL
  Blast radius: critical
  Decay risk: low

• DPR-005: Heap-Only Tuples (HOT)
  Component: Storage
  Blast radius: high
  Decay risk: medium
"""

# Test the query formatting
if __name__ == "__main__":
    print("=" * 60)
    print("NEXUS CTG QUERY CLI - TEST DEMONSTRATION")
    print("=" * 60)
    print("\nThis demonstrates what the CLI looks like when querying:")
    print("\nSample Question: 'Show me all foundational decisions'\n")
    print("=" * 60)
    
    # Execute mock query
    result = mock_nl_query("Show me all foundational decisions")
    
    # Display formatted result
    print("\n" + "=" * 60)
    print("[>] Query executed in 0.15s\n")
    print(result)
    print("=" * 60)
    
    print("\n[+] CLI Features:")
    print("  * Natural language query processing")
    print("  * Colored output for better readability")
    print("  * Special commands: help, stats, clear, exit")
    print("  * Error handling for Neo4j connection issues")
    print("  * Query execution timing")
    print("  * 8 example questions to guide users")
    
    print("\n[+] To use the actual CLI:")
    print("  1. Start Neo4j: docker run -p 7474:7474 -p 7687:7687 neo4j:community")
    print("  2. Load graph: python nexus_layer2/graph_builder.py")
    print("  3. Run CLI: python nexus_layer2/query_cli.py")
    print()

# Made with Bob